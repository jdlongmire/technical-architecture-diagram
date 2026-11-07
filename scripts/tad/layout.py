"""View selection, node sizing, ELK layout, and scene construction.

A scene is a renderer-neutral description of one page with absolute coordinates.
Both the draw.io writer and the SVG previewer draw from the same scene, and the
geometric checks measure it, so what is checked is what is drawn.
"""
import json
import math
import os
import shutil
import subprocess
from collections import OrderedDict

from . import limits as L
from . import styles as S
from . import text as T
from .spec import edge_label_lines, issue

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ELK_SCRIPT = os.path.join(HERE, "elk_layout.js")

PAD_X, PAD_Y = 10, 7
HEADER_H = 30
CONTAINER_PAD = 14
PORT_SIZE = 8
MARGIN = 36
BANNER_H = 22
ICON = 18


class LayoutError(Exception):
    pass


# View selection ----------------------------------------------------------------

def select(spec, view):
    containers = OrderedDict((c["id"], dict(c)) for c in spec["containers"])
    nodes = OrderedDict((n["id"], dict(n)) for n in spec["nodes"])
    parent = {x["id"]: x.get("in") for x in list(containers.values()) + list(nodes.values())}

    def ancestors(i):
        out, cur, g = [], parent.get(i), 0
        while cur and g < 50:
            out.append(cur)
            cur = parent.get(cur)
            g += 1
        return out

    keep = set(containers) | set(nodes)
    if view and view.get("include"):
        inc = set(view["include"])
        keep = {i for i in keep if i in inc or any(a in inc for a in ancestors(i))}
        for i in list(keep):
            keep.update(ancestors(i))
    if view and view.get("exclude"):
        exc = set(view["exclude"])
        keep = {i for i in keep if i not in exc and not any(a in exc for a in ancestors(i))}

    collapsed = set(view.get("collapse", [])) if view else set()
    collapsed &= keep
    remap = {}
    for i in list(keep):
        anc = [a for a in ancestors(i) if a in collapsed]
        if anc:
            remap[i] = anc[-1]          # outermost collapsed ancestor
            keep.discard(i)
    for cid in collapsed:
        if cid in remap:                # collapsed inside another collapsed container
            continue
        c = containers.pop(cid)
        inner = sum(1 for k, v in remap.items() if v == cid and k in nodes)
        nodes[cid] = OrderedDict(id=cid, label=c["label"],
                                 stereotype=c.get("stereotype") or S.CONTAINER_TYPES[c["type"]]["label"].split(" /")[0],
                                 detail=f"{inner} elements (collapsed)", shape="box", collapsed=True)
        if c.get("in"):
            nodes[cid]["in"] = c["in"]
        if c.get("marking"):
            nodes[cid]["marking"] = c["marking"]

    containers = OrderedDict((k, v) for k, v in containers.items() if k in keep)
    nodes = OrderedDict((k, v) for k, v in nodes.items() if k in keep)

    etypes = set(view.get("edge_types", [])) if view and view.get("edge_types") else None
    edges, merged = [], {}
    for idx, e in enumerate(spec["edges"]):
        if etypes is not None and e["type"] not in etypes:
            continue
        a = remap.get(e["from"], e["from"])
        b = remap.get(e["to"], e["to"])
        if a not in keep or b not in keep or a == b:
            continue
        ee = dict(e)
        ee["_src_index"] = idx
        if a != e["from"]:
            ee.pop("from_port", None)
        if b != e["to"]:
            ee.pop("to_port", None)
        ee["from"], ee["to"] = a, b
        key = (a, b, ee["type"], ee.get("from_port"), ee.get("to_port"))
        if key in merged and (a != e["from"] or b != e["to"]):
            m = merged[key]
            m["_merged"] = m.get("_merged", 1) + 1
            continue
        merged[key] = ee
        edges.append(ee)
    for ee in edges:
        if ee.get("_merged"):
            n = ee["_merged"]
            for k in ("data", "protocol", "port", "id"):
                ee.pop(k, None)
            ee["label"] = f"{n} flows"
    if view and view.get("hide_unlinked"):
        linked = {e["from"] for e in edges} | {e["to"] for e in edges}
        nodes = OrderedDict((k, v) for k, v in nodes.items() if k in linked)
    # Drop containers left empty by filtering (but keep ones that were empty in the spec).
    nonempty = set()
    for x in list(nodes.values()) + list(containers.values()):
        nonempty.update(a for a in ancestors(x["id"]) if a in containers)
    spec_children = {c["id"] for c in spec["containers"]
                     if any(x.get("in") == c["id"] for x in spec["containers"] + spec["nodes"])}
    containers = OrderedDict((k, v) for k, v in containers.items() if k in nonempty or k not in spec_children)
    return containers, nodes, edges


# Node sizing -------------------------------------------------------------------

def measure_node(n, kind, icons_on, issues, path):
    shape = n.get("shape") or S.DEFAULT_SHAPE[kind]
    n["shape"] = shape
    icon = bool(icons_on and n.get("icon"))
    icon_w = ICON + 6 if icon else 0
    inner_max = L.NODE_MAX_WIDTH - 2 * PAD_X - icon_w

    label_text = n["label"]
    if n.get("marking"):
        label_text = S.portion_mark(n["marking"]) + " " + label_text
    label_lines = T.wrap(label_text, L.FONT_LABEL, inner_max, bold=True)
    if len(label_lines) > L.NODE_LABEL_MAX_LINES and path:
        avg = T.width(n["label"], L.FONT_LABEL, True) / max(1, len(n["label"]))
        budget = int(inner_max * L.NODE_LABEL_MAX_LINES / avg * 0.92)
        issues.append(issue("ERROR", path + ".label",
                            f"label {n['label']!r} wraps to {len(label_lines)} lines (limit {L.NODE_LABEL_MAX_LINES})",
                            f"shorten it to at most {budget} characters"))
    blocks = []  # (text, size, bold, italic, color_key, align)
    if n.get("stereotype"):
        blocks.append(("«" + n["stereotype"] + "»", L.FONT_STEREO, False, True, "muted", "center"))
    for ln in label_lines:
        blocks.append((ln, L.FONT_LABEL, True, False, "text", "center"))
    if n.get("detail"):
        blocks.append((n["detail"], L.FONT_DETAIL, False, False, "muted", "center"))

    text_w = max([T.width(b[0], b[1], b[2], b[3]) for b in blocks] + [0])
    text_h = sum(T.line_height(b[1]) for b in blocks)

    comps = []
    comp_w = 0
    for cname, lines in (n.get("compartments") or {}).items():
        comps.append((cname, lines))
        comp_w = max([comp_w, T.width(cname, L.FONT_ATTR - 1, italic=True)] +
                     [T.width(x, L.FONT_ATTR) for x in lines])
    comp_h = sum(T.line_height(L.FONT_ATTR - 1) + 6 + len(ls) * T.line_height(L.FONT_ATTR) for _, ls in comps)

    w = max(L.NODE_MIN_WIDTH, text_w + 2 * PAD_X + icon_w, comp_w + 2 * PAD_X)
    h = text_h + 2 * PAD_Y + comp_h
    if shape == "cylinder":
        h += 16
    elif shape == "actor":
        w = max(60, text_w + 8)
        h = 46 + text_h
    elif shape == "process":
        w += 8
        h = max(h, 44)
    elif shape == "note":
        w += 10
    h = max(h, 38)

    # Ports need room along their side.
    ports = n.get("ports", [])
    if ports:
        by_side = {}
        for p in ports:
            by_side.setdefault(p.get("side", "AUTO"), []).append(p)
        ns = len(by_side.get("NORTH", [])) + len(by_side.get("SOUTH", []))
        ew = max(len(by_side.get("EAST", [])), len(by_side.get("WEST", [])), (len(by_side.get("AUTO", [])) + 1) // 2)
        nsm = max(len(by_side.get("NORTH", [])), len(by_side.get("SOUTH", [])))
        if ns:
            maxlab = max(T.width(p["label"], L.FONT_PORT) for p in by_side.get("NORTH", []) + by_side.get("SOUTH", []))
            w = max(w, (nsm + 1) * max(24, 0.6 * maxlab + 10))
        h = max(h, (ew + 1) * 18)
    n["_w"], n["_h"] = round(w), round(h)
    n["_blocks"], n["_comps"], n["_icon"], n["_text_h"] = blocks, comps, icon, text_h
    return n


def measure_container(c):
    lab = c["label"]
    w = T.width(lab, L.FONT_CONTAINER, bold=True) + 2 * CONTAINER_PAD
    if c.get("stereotype"):
        w += T.width("«" + c["stereotype"] + "» ", L.FONT_STEREO, italic=True)
    if c.get("marking"):
        w += T.width(c["marking"], 9, bold=True) + 22
    c["_minw"] = round(w + 8)
    return c


def back_edges(spec, containers, nodes, edges):
    """Indices of view edges that close a loop, found by DFS in spec order with every
    edge lifted to the children of its lowest common container. Laying these out
    reversed gives ELK an acyclic graph; arrowheads keep the real direction."""
    parent = {}
    for x in list(containers.values()) + list(nodes.values()):
        p = x.get("in")
        parent[x["id"]] = p if p in containers else None

    def chain(i):
        out, g = [i], 0
        while parent.get(out[-1]) and g < 50:
            out.append(parent[out[-1]])
            g += 1
        return out
    adj = {}
    for k, e in enumerate(edges):
        a, b = e["from"], e["to"]
        if spec["edge_types"][e["type"]].get("reverse_layout"):
            a, b = b, a
        ca, cb = chain(a), chain(b)
        common = next((x for x in ca if x in cb), None)
        la = ca[ca.index(common) - 1] if common else ca[-1]
        lb = cb[cb.index(common) - 1] if common else cb[-1]
        adj.setdefault(la, []).append((lb, k))
    state, back = {}, set()
    order = list(containers) + list(nodes)

    def dfs(u):
        state[u] = 1
        for v, k in adj.get(u, []):
            if state.get(v) == 1:
                back.add(k)
            elif v not in state:
                dfs(v)
        state[u] = 2
    import sys
    sys.setrecursionlimit(max(1000, 4 * len(order) + 100))
    for u in order:
        if u not in state:
            dfs(u)
    return back


# ELK ---------------------------------------------------------------------------

def _opts(direction, root=False):
    o = {
        "elk.algorithm": "layered",
        "elk.direction": direction,
        "elk.edgeRouting": "ORTHOGONAL",
        "elk.spacing.nodeNode": "30",
        "elk.layered.spacing.nodeNodeBetweenLayers": "56",
        "elk.spacing.edgeNode": "18",
        "elk.spacing.edgeEdge": "12",
        "elk.layered.spacing.edgeNodeBetweenLayers": "20",
        "elk.layered.spacing.edgeEdgeBetweenLayers": "12",
        "elk.spacing.edgeLabel": "4",
        "elk.spacing.labelLabel": "4",
        "elk.spacing.portPort": "14",
        "elk.edgeLabels.placement": "CENTER",
        "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
        "elk.layered.unnecessaryBendpoints": "false",
        "elk.layered.mergeEdges": "false",
        "elk.spacing.componentComponent": "40",
    }
    if root:
        o["elk.layered.considerModelOrder.strategy"] = "NODES_AND_EDGES"
        o["elk.hierarchyHandling"] = "INCLUDE_CHILDREN"
        o["elk.padding"] = "[top=8,left=8,bottom=8,right=8]"
    return o


def find_node_exe():
    for n in ("node", "nodejs"):
        p = shutil.which(n)
        if p:
            return p
    return None


def run_elk(graph):
    exe = find_node_exe()
    if not exe:
        raise LayoutError("Node.js is required for layout (install node 16+)")
    r = subprocess.run([exe, ELK_SCRIPT], input=json.dumps(graph), capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise LayoutError(r.stderr.strip() or "ELK layout failed")
    return json.loads(r.stdout)


def build_graph(spec, containers, nodes, edges, direction, label_edges=None):
    etypes = spec["edge_types"]
    elk_nodes = {}
    root = {"id": "__root__", "layoutOptions": _opts(direction, True), "children": [], "edges": []}

    def mk_container(c):
        return {"id": c["id"], "children": [], "edges": [],
                "layoutOptions": dict(_opts(direction), **{
                    "elk.padding": f"[top={HEADER_H + 6},left={CONTAINER_PAD},bottom={CONTAINER_PAD},right={CONTAINER_PAD}]",
                    "elk.nodeSize.constraints": "[MINIMUM_SIZE]",
                    "elk.nodeSize.minimum": f"({c['_minw']},{HEADER_H + 30})",
                })}

    for c in containers.values():
        elk_nodes[c["id"]] = mk_container(c)
    for n in nodes.values():
        en = {"id": n["id"], "width": n["_w"], "height": n["_h"], "layoutOptions": {}}
        ports = n.get("ports", [])
        if ports:
            fixed = any("side" in p for p in ports)
            en["layoutOptions"]["elk.portConstraints"] = "FIXED_SIDE" if fixed else "FREE"
            en["layoutOptions"]["elk.portLabels.placement"] = "[OUTSIDE]"
            en["ports"] = []
            for p in ports:
                lw = T.width(p["label"], L.FONT_PORT)
                ep = {"id": f"{n['id']}::{p['id']}", "width": PORT_SIZE, "height": PORT_SIZE,
                      "labels": [{"text": p["label"], "width": round(lw + 2), "height": T.line_height(L.FONT_PORT)}],
                      "layoutOptions": {}}
                if fixed:
                    ep["layoutOptions"]["elk.port.side"] = p.get("side", "EAST")
                en["ports"].append(ep)
        elk_nodes[n["id"]] = en

    back = back_edges(spec, containers, nodes, edges)
    parent = {}
    for x in list(containers.values()) + list(nodes.values()):
        p = x.get("in")
        parent[x["id"]] = p if p in containers else None
    for c in containers.values():
        (elk_nodes[parent[c["id"]]]["children"] if parent[c["id"]] else root["children"]).append(elk_nodes[c["id"]])
    for n in nodes.values():
        (elk_nodes[parent[n["id"]]]["children"] if parent[n["id"]] else root["children"]).append(elk_nodes[n["id"]])

    def chain(i):
        out, cur = [], parent.get(i)
        while cur:
            out.append(cur)
            cur = parent.get(cur)
        return out

    for k, e in enumerate(edges):
        et = etypes[e["type"]]
        a = f"{e['from']}::{e['from_port']}" if e.get("from_port") else e["from"]
        b = f"{e['to']}::{e['to_port']}" if e.get("to_port") else e["to"]
        e["_rev"] = bool(et.get("reverse_layout")) != (k in back)
        if e["_rev"]:
            a, b = b, a
        lines = edge_label_lines(e, spec["kind"])
        e["_lines"] = lines
        ee = {"id": f"e{k}", "sources": [a], "targets": [b]}
        if lines and (label_edges is None or k in label_edges):
            lw = max(T.width(x, L.FONT_EDGE) for x in lines)
            ee["labels"] = [{"text": "\n".join(lines), "width": round(lw + 8),
                             "height": len(lines) * T.line_height(L.FONT_EDGE) + 4}]
        ca, cb = [e["from"]] + chain(e["from"]), [e["to"]] + chain(e["to"])
        lca = next((x for x in ca if x in cb and x in containers), None)
        (elk_nodes[lca]["edges"] if lca else root["edges"]).append(ee)
    return root


# Scene -------------------------------------------------------------------------

def layout_view(spec, view, issues, vpath):
    """Lay out one view. Labels are placed in free space after layout; only labels that
    find no room are handed to ELK (which then reserves space for them)."""
    kind = spec["kind"]
    direction = (view or {}).get("direction") or spec["direction"]
    containers, nodes, edges = select(spec, view)
    idx = {n["id"]: i for i, n in enumerate(spec["nodes"])}
    for n in nodes.values():
        p = f"nodes[{idx[n['id']]}]" if n["id"] in idx and vpath == "" else ""
        measure_node(n, kind, spec.get("icons"), issues, p)
    for c in containers.values():
        measure_container(c)

    def attempt(d):
        elk_labels = set()
        sc = None
        for _ in range(4):
            sc = _scene(spec, view, containers, nodes, edges, d, elk_labels)
            failed = place_labels(sc, elk_labels)
            if not failed:
                return sc
            elk_labels |= failed
        return _scene(spec, view, containers, nodes, edges, d, None)

    if direction == "AUTO":
        # Fixed port sides imply a flow direction: E/W ports suit RIGHT, N/S ports suit DOWN.
        ew = sum(1 for n in nodes.values() for p in n.get("ports", []) if p.get("side") in ("EAST", "WEST"))
        ns = sum(1 for n in nodes.values() for p in n.get("ports", []) if p.get("side") in ("NORTH", "SOUTH"))
        candidates = ("RIGHT", "DOWN")
        if ew >= 4 and ew > 2 * ns:
            candidates = ("RIGHT",)
        elif ns >= 4 and ns > 2 * ew:
            candidates = ("DOWN",)
        best = None
        for d in candidates:
            sc = attempt(d)
            target = 1.41
            score = abs(math.log((sc["width"] / max(1, sc["height"])) / target))
            if best is None or score < best[0] - 0.05:
                best = (score, sc)
        sc = best[1]
    else:
        sc = attempt(direction)
    return sc


def _scene(spec, view, containers, nodes, edges, direction, label_edges):
    kind = spec["kind"]
    graph = build_graph(spec, containers, nodes, edges, direction, label_edges)
    for k, v in (spec.get("elk") or {}).items():
        graph["layoutOptions"][k if k.startswith("elk.") else "elk." + k] = str(v)
    try:
        out = run_elk(graph)
    except LayoutError:
        # ELK 0.9 can fail on model-order with some hierarchies; retry without it.
        graph["layoutOptions"].pop("elk.layered.considerModelOrder.strategy", None)
        out = run_elk(graph)

    # Absolute positions
    abspos = {}

    def walk(g, ox, oy, depth):
        for ch in g.get("children", []):
            x, y = ox + ch.get("x", 0), oy + ch.get("y", 0)
            abspos[ch["id"]] = (x, y, ch.get("width", 0), ch.get("height", 0), depth, ch)
            walk(ch, x, y, depth + 1)

    walk(out, out.get("x", 0), out.get("y", 0), 0)

    # Edges: find each in its container and offset accordingly.
    elk_edges = {}

    def collect(g, ox, oy):
        for e in g.get("edges", []):
            elk_edges[e["id"]] = (e, ox, oy)
        for ch in g.get("children", []):
            if ch.get("children") or ch.get("edges"):
                collect(ch, ox + ch.get("x", 0), oy + ch.get("y", 0))

    collect(out, 0, 0)

    title_h = 0
    title_h += L.FONT_TITLE + 10
    sub = (view or {}).get("subtitle") or spec.get("subtitle")
    if sub:
        title_h += L.FONT_SUBTITLE + 8
    if view and spec.get("views") and len(spec["views"]) > 1:
        title_h += 0
    top = MARGIN + (BANNER_H + 8 if spec.get("marking") else 0) + title_h + 14
    left = MARGIN
    dx, dy = left - out.get("x", 0), top

    theme = dict(S.DEFAULT_THEME, **(spec.get("theme") or {}))
    sc = OrderedDict()
    sc["name"] = (view or {}).get("name", "Overview")
    sc["direction"] = direction
    sc["title"] = spec["title"]
    sc["subtitle"] = sub
    sc["marking"] = spec.get("marking")
    sc["theme"] = theme
    sc["kind"] = kind
    sc["containers"], sc["nodes"], sc["edges"] = [], [], []

    for cid, c in containers.items():
        x, y, w, h, depth, _ = abspos[cid]
        ct = S.CONTAINER_TYPES[c["type"]]
        stroke = ct["stroke"]
        if stroke == "marking":
            stroke = S.marking_colors(c.get("marking") or spec.get("marking"))[0]
        sc["containers"].append(dict(id=cid, label=c["label"], type=c["type"], stereotype=c.get("stereotype"),
                                     marking=c.get("marking"), parent=c.get("in") if c.get("in") in containers else None,
                                     x=x + dx, y=y + dy, w=w, h=h, depth=depth,
                                     fill=ct["fill"], stroke=stroke, dash=ct["dash"], width=ct["width"]))
    sc["containers"].sort(key=lambda c: c["depth"])

    for nid, n in nodes.items():
        x, y, w, h, depth, raw = abspos[nid]
        ports = []
        for rp in raw.get("ports", []):
            pid = rp["id"].split("::", 1)[1]
            px, py = x + rp["x"] + dx, y + rp["y"] + dy
            pw, ph = rp.get("width", PORT_SIZE), rp.get("height", PORT_SIZE)
            # side from geometry
            cx, cy = px + pw / 2 - (x + dx), py + ph / 2 - (y + dy)
            dists = {"WEST": abs(cx), "EAST": abs(cx - w), "NORTH": abs(cy), "SOUTH": abs(cy - h)}
            side = min(dists, key=dists.get)
            lab = next(p["label"] for p in n["ports"] if p["id"] == pid)
            lw, lh = T.width(lab, L.FONT_PORT) + 2, T.line_height(L.FONT_PORT)
            lb = _port_label_box(px, py, pw, ph, side, lw, lh)
            ports.append(dict(id=pid, label=lab, x=px, y=py, w=pw, h=ph, side=side, label_box=lb))
        sc["nodes"].append(dict(id=nid, label=n["label"], stereotype=n.get("stereotype"), detail=n.get("detail"),
                                shape=n["shape"], parent=n.get("in") if n.get("in") in containers else None,
                                x=x + dx, y=y + dy, w=w, h=h, ports=ports, blocks=n["_blocks"], comps=n["_comps"],
                                icon=n.get("icon") if n["_icon"] else None, marking=n.get("marking"),
                                collapsed=n.get("collapsed", False), text_h=n["_text_h"]))

    etypes = spec["edge_types"]
    boundary_of = _boundaries(spec, containers)
    for k, e in enumerate(edges):
        raw, ox, oy = elk_edges[f"e{k}"]
        pts = []
        for s in raw.get("sections", []):
            seq = [s["startPoint"]] + s.get("bendPoints", []) + [s["endPoint"]]
            for p in seq:
                q = (round(p["x"] + ox + dx, 2), round(p["y"] + oy + dy, 2))
                if not pts or pts[-1] != q:
                    pts.append(q)
        et = dict(etypes[e["type"]])
        if e.get("_rev"):
            pts.reverse()
        etype = e["type"]
        crossing = False
        if kind == "dataflow" and boundary_of(e["from"]) != boundary_of(e["to"]):
            crossing = True
            if etype == "flow" and "crossing" in etypes:
                etype = "crossing"
                et = dict(etypes["crossing"])
        if e.get("dash"):
            et["dash"] = e["dash"]
        lb = None
        if raw.get("labels"):
            l0 = raw["labels"][0]
            lb = (l0["x"] + ox + dx, l0["y"] + oy + dy, l0["width"], l0["height"])
        sc["edges"].append(dict(id=f"e{k}", k=k, src=e["from"], dst=e["to"], src_port=e.get("from_port"),
                                dst_port=e.get("to_port"), type=etype, style=et, points=pts,
                                lines=e.get("_lines", []), label_box=lb, crossing=crossing,
                                spec_index=e.get("_src_index"), protocol=e.get("protocol"),
                                ifid=e.get("id"), data=e.get("data"), label=e.get("label"),
                                port=e.get("port"), marking=e.get("marking")))

    gw = out.get("width", 0)
    gh = out.get("height", 0)
    sc["diagram_box"] = (left, top, gw, gh)
    width = left + gw + MARGIN
    height = top + gh
    sc["title_w"] = T.width(spec["title"], L.FONT_TITLE, bold=True)
    if sub:
        sc["title_w"] = max(sc["title_w"], T.width(sub, L.FONT_SUBTITLE))
    width = max(width, MARGIN * 2 + sc["title_w"])

    # Legend
    if spec.get("legend", True):
        leg = build_legend(sc, spec)
        if leg:
            leg["x"], leg["y"] = left, height + 18
            sc["legend"] = leg
            height = leg["y"] + leg["h"]
            width = max(width, leg["x"] + leg["w"] + MARGIN)
    height += MARGIN + (BANNER_H + 8 if spec.get("marking") else 0)
    sc["width"], sc["height"] = round(width), round(height)
    return sc


def _port_label_box(px, py, pw, ph, side, lw, lh):
    if side == "WEST":
        return (px - lw - 3, py - lh - 1, lw, lh)
    if side == "EAST":
        return (px + pw + 3, py - lh - 1, lw, lh)
    if side == "NORTH":
        return (px + pw + 3, py - lh - 1, lw, lh)
    return (px + pw + 3, py + ph + 1, lw, lh)


def _boundaries(spec, containers):
    cmap = {c["id"]: c for c in spec["containers"]}
    nmap = {n["id"]: n for n in spec["nodes"]}

    def f(i):
        out, cur = [], (cmap.get(i) or nmap.get(i) or {}).get("in")
        if i in cmap and cmap[i]["type"] in S.BOUNDARY_TYPES:
            out.append(i)
        g = 0
        while cur and g < 50:
            c = cmap.get(cur)
            if c and c["type"] in S.BOUNDARY_TYPES:
                out.append(cur)
            cur = (c or {}).get("in")
            g += 1
        return tuple(out)
    return f


def build_legend(sc, spec):
    items = []
    seen = set()
    for e in sc["edges"]:
        key = (e["type"], e["style"].get("dash"))
        if key in seen:
            continue
        seen.add(key)
        lab = e["style"].get("label", e["type"])
        if e["style"].get("dash") != spec["edge_types"].get(e["type"], {}).get("dash"):
            lab += " (" + e["style"]["dash"] + ")"
        items.append(("edge", lab, e["style"]))
    seen_c = set()
    for c in sc["containers"]:
        if c["type"] in seen_c:
            continue
        seen_c.add(c["type"])
        items.append(("container", S.CONTAINER_TYPES[c["type"]]["label"], c))
    if any(n["ports"] for n in sc["nodes"]):
        items.append(("port", "Port / interface point", None))
    if any(n.get("collapsed") for n in sc["nodes"]):
        items.append(("collapsed", "Collapsed group (see other view)", None))
    if not items:
        return None
    lh = 20
    col_w = max(T.width(i[1], L.FONT_LEGEND) for i in items) + 56
    ncol = 1 if len(items) <= 4 else (2 if len(items) <= 10 else 3)
    rows = -(-len(items) // ncol)
    w = ncol * col_w + 16
    h = 26 + rows * lh + 6
    placed = []
    for i, it in enumerate(items):
        c, r = divmod(i, rows)
        placed.append(dict(kind=it[0], label=it[1], ref=it[2], dx=8 + c * col_w, dy=26 + r * lh))
    return dict(w=round(w), h=round(h), items=placed, row_h=lh)


# Interface table ---------------------------------------------------------------

TABLE_COLS = [("ID", "ifid"), ("From", "src"), ("To", "dst"), ("Type", "type"),
              ("Data / item", "data"), ("Protocol / port", "proto"), ("Marking", "marking")]


def table_scene(spec, base_scene):
    names = {n["id"]: n["label"] for n in spec["nodes"]}
    names.update({c["id"]: c["label"] for c in spec["containers"]})
    plabel = {(n["id"], p["id"]): p["label"] for n in spec["nodes"] for p in n.get("ports", [])}
    rows = []
    for e in spec["edges"]:
        et = spec["edge_types"][e["type"]]
        proto = e.get("protocol", "")
        if e.get("port"):
            proto = f"{proto}/{e['port']}" if proto else str(e["port"])
        src = names.get(e["from"], e["from"]) + (f" [{plabel[(e['from'], e['from_port'])]}]" if e.get("from_port") else "")
        dst = names.get(e["to"], e["to"]) + (f" [{plabel[(e['to'], e['to_port'])]}]" if e.get("to_port") else "")
        data = e.get("data") or e.get("label") or ""
        rows.append(dict(ifid=e.get("id", ""), src=src, dst=dst, type=et.get("label", e["type"]),
                         data=data, proto=proto, marking=e.get("marking", "")))
    rows.sort(key=lambda r: (r["ifid"] == "", r["ifid"]))
    widths = []
    for title, key in TABLE_COLS:
        w = max([T.width(title, L.FONT_TABLE, bold=True)] + [T.width(str(r[key]), L.FONT_TABLE) for r in rows])
        widths.append(round(min(w, 260) + 16))
    if not any(r["marking"] for r in rows):
        drop = [i for i, (_, k) in enumerate(TABLE_COLS) if k == "marking"][0]
    else:
        drop = None
    cols = [(t, k, w) for i, ((t, k), w) in enumerate(zip(TABLE_COLS, widths)) if i != drop]
    rh = 22
    top = MARGIN + (BANNER_H + 8 if spec.get("marking") else 0) + L.FONT_TITLE + 10 + L.FONT_SUBTITLE + 8 + 14
    sc = OrderedDict(name="Interfaces", title=spec["title"], subtitle="Interface table (generated from edges)",
                     marking=spec.get("marking"), theme=base_scene["theme"], kind="table",
                     containers=[], nodes=[], edges=[])
    tw = sum(c[2] for c in cols)
    sc["table"] = dict(x=MARGIN, y=top, cols=cols, rows=rows, row_h=rh, w=tw, h=rh * (len(rows) + 1))
    sc["title_w"] = T.width(spec["title"], L.FONT_TITLE, bold=True)
    sc["width"] = round(max(MARGIN * 2 + tw, MARGIN * 2 + sc["title_w"]))
    sc["height"] = round(top + rh * (len(rows) + 1) + MARGIN + (BANNER_H + 8 if spec.get("marking") else 0))
    sc["diagram_box"] = (MARGIN, top, tw, rh * (len(rows) + 1))
    return sc


# Label placement ---------------------------------------------------------------

def place_labels(sc, elk_placed):
    """Place edge labels in free space along their own edge.

    Returns the set of edge indices (k) whose labels found no collision-free spot;
    those are handed to ELK on the next pass.
    """
    from .geom import rect_hit_segment, rect_overlap, segs, path_length
    lh_line = T.line_height(L.FONT_EDGE)
    hard = [(n["x"], n["y"], n["w"], n["h"]) for n in sc["nodes"]]
    for n in sc["nodes"]:
        hard += [p["label_box"] for p in n["ports"]]
        hard += [(p["x"], p["y"], p["w"], p["h"]) for p in n["ports"]]
    for c in sc["containers"]:
        hw = T.width(c["label"], L.FONT_CONTAINER, bold=True) + 28 + \
            (T.width("«" + c["stereotype"] + "» ", L.FONT_STEREO, italic=True) if c.get("stereotype") else 0)
        hard.append((c["x"], c["y"], hw, HEADER_H - 4))
        if c.get("marking"):
            bw = T.width(c["marking"], 9, bold=True) + 12
            hard.append((c["x"] + c["w"] - bw - 10, c["y"] + 4, bw + 4, 22))
    placed = [e["label_box"] for e in sc["edges"] if e.get("label_box")]
    all_segs = [(e["k"], a, b) for e in sc["edges"] for a, b in segs(e["points"])]
    borders = []
    for c in sc["containers"]:
        x, y, w, h = c["x"], c["y"], c["w"], c["h"]
        borders += [((x, y), (x + w, y)), ((x, y + h), (x + w, y + h)), ((x, y), (x, y + h)), ((x + w, y), (x + w, y + h))]
    bx0, by0, bw0, bh0 = sc["diagram_box"]

    failed = set()
    order = sorted([e for e in sc["edges"] if e["lines"] and not e.get("label_box")],
                   key=lambda e: path_length(e["points"]))
    for e in order:
        lw = max(T.width(x, L.FONT_EDGE) for x in e["lines"]) + 8
        lh = len(e["lines"]) * lh_line + 4
        total = path_length(e["points"]) or 1
        best = None
        acc = 0.0
        for a, b in segs(e["points"]):
            seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
            horiz = abs(a[1] - b[1]) < 0.5
            for f in (0.5, 0.3, 0.7, 0.15, 0.85):
                cx, cy = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
                t_mid = abs((acc + seg_len * f) / total - 0.5)
                if horiz:
                    cands = [((cx - lw / 2, cy - lh - 2), 0.0), ((cx - lw / 2, cy + 2), 0.5),
                             ((cx - lw / 2, cy - lh / 2), 2.0)]
                    if seg_len < lw * 0.8:
                        cands = [(p, s + 2.5) for p, s in cands]
                else:
                    cands = [((cx + 3, cy - lh / 2), 0.3), ((cx - lw - 3, cy - lh / 2), 0.6),
                             ((cx - lw / 2, cy - lh / 2), 2.2)]
                    if seg_len < lh * 1.2:
                        cands = [(p, s + 2.5) for p, s in cands]
                for (x, y), pen in cands:
                    box = (x, y, lw, lh)
                    if x < bx0 - 4 or y < by0 - 4 or x + lw > bx0 + bw0 + 4 or y + lh > by0 + bh0 + 4:
                        continue
                    if any(rect_overlap(box, r, pad=-3)[0] for r in hard):
                        continue
                    if any(rect_overlap(box, r, pad=-2)[0] for r in placed):
                        continue
                    score = pen + t_mid * 3
                    for kk, s1, s2 in all_segs:
                        if rect_hit_segment(box, s1, s2, shrink=1):
                            score += 2.5 if kk != e["k"] else 0.4
                    for s1, s2 in borders:
                        if rect_hit_segment(box, s1, s2, shrink=1):
                            score += 1.5
                    if best is None or score < best[0]:
                        best = (score, box)
            acc += seg_len
        if best is None or best[0] >= 6:
            failed.add(e["k"])
        else:
            e["label_box"] = best[1]
            placed.append(best[1])
    return failed
