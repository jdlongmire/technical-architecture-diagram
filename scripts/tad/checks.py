"""Geometric and semantic checks on laid-out scenes."""
from . import limits as L
from . import styles as S
from .geom import rect_hit_segment, rect_overlap, seg_cross, segs
from .spec import issue


def scene_checks(sc, spec, multi_view):
    out = []
    tag = f"[view '{sc['name']}'] " if multi_view else ""
    nidx = {n["id"]: i for i, n in enumerate(spec["nodes"])}
    vpath = ""

    def epath(e, field=None):
        p = f"edges[{e['spec_index']}]" if e.get("spec_index") is not None else "edges"
        return p + (f".{field}" if field else "")

    def npath(nid, field=None):
        p = f"nodes[{nidx[nid]}]" if nid in nidx else f"containers[id={nid}]"
        return p + (f".{field}" if field else "")

    # Density -------------------------------------------------------------------
    nn, ne = len(sc["nodes"]), len(sc["edges"])
    top = [c["id"] for c in sc["containers"] if not c["parent"]]
    split_hint = ("add views (one per top-level container: " + ", ".join(top[:6]) + ")" if top
                  else "add views that include subsets of nodes") + ", or collapse containers in a view"
    if nn > L.NODES_PER_VIEW_MAX:
        out.append(issue("ERROR", "views", f"{tag}{nn} nodes on one page (limit {L.NODES_PER_VIEW_MAX})", split_hint))
    elif nn > L.NODES_PER_VIEW_WARN:
        out.append(issue("WARNING", "views", f"{tag}{nn} nodes on one page (dense above {L.NODES_PER_VIEW_WARN})",
                         split_hint))
    if ne > L.EDGES_PER_VIEW_MAX:
        out.append(issue("ERROR", "views", f"{tag}{ne} edges on one page (limit {L.EDGES_PER_VIEW_MAX})",
                         "split by edge_types (e.g. a data-flow view and a management view)"))

    nodes = {n["id"]: n for n in sc["nodes"]}
    rects = {n["id"]: (n["x"], n["y"], n["w"], n["h"]) for n in sc["nodes"]}

    # Edges through nodes ---------------------------------------------------------
    for e in sc["edges"]:
        for a, b in segs(e["points"]):
            for nid, r in rects.items():
                if nid in (e["src"], e["dst"]):
                    continue
                if rect_hit_segment(r, a, b):
                    out.append(issue("ERROR", epath(e), f"{tag}edge {e['src']} -> {e['dst']} passes through "
                                     f"node '{nid}'",
                                     "reorder nodes in the spec (layout follows spec order), set ports with sides, "
                                     "or change direction"))
                    break
            else:
                continue
            break

    # Labels ----------------------------------------------------------------------
    labels = []
    for e in sc["edges"]:
        if e.get("label_box"):
            labels.append(("edge", e, e["label_box"]))
    for n in sc["nodes"]:
        for p in n["ports"]:
            labels.append(("port", (n, p), p["label_box"]))
    for kind, ref, box in labels:
        for nid, r in rects.items():
            if kind == "port" and nid == ref[0]["id"]:
                continue
            hit, area = rect_overlap(box, r, pad=1)
            if hit:
                if kind == "edge":
                    out.append(issue("ERROR", epath(ref, "label"), f"{tag}label of edge {ref['src']} -> "
                                     f"{ref['dst']} overlaps node '{nid}'",
                                     "shorten the label lines or drop the 'data' line"))
                else:
                    n, p = ref
                    out.append(issue("WARNING", npath(n["id"], f"ports[{p['id']}]"),
                                     f"{tag}port label '{p['label']}' overlaps node '{nid}'",
                                     f"shorten it, or give the port an explicit side"))
                break
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            hit, area = rect_overlap(labels[i][2], labels[j][2], pad=1)
            if not hit:
                continue
            k1, r1, b1 = labels[i]
            k2, r2, b2 = labels[j]
            small = min(b1[2] * b1[3], b2[2] * b2[3]) or 1
            lvl = "ERROR" if area / small > 0.25 and k1 == k2 == "edge" else "WARNING"
            p = epath(r1, "label") if k1 == "edge" else (epath(r2, "label") if k2 == "edge"
                                                       else npath(r1[0]["id"], "ports"))
            out.append(issue(lvl, p, f"{tag}two labels overlap ({_lname(k1, r1)} and {_lname(k2, r2)})",
                             "shorten one of them, or move one detail into the interface table"))

    # Crossings ---------------------------------------------------------------------
    crossings = 0
    es = [list(segs(e["points"])) for e in sc["edges"]]
    for i in range(len(es)):
        for j in range(i + 1, len(es)):
            for a, b in es[i]:
                for c, d in es[j]:
                    if seg_cross(a, b, c, d):
                        crossings += 1
    sc["_crossings"] = crossings
    if crossings > max(L.CROSSINGS_WARN_MIN, L.CROSSINGS_WARN_RATIO * max(1, ne)):
        out.append(issue("WARNING", "edges", f"{tag}{crossings} edge crossings",
                         "group tightly linked nodes in one container, list nodes in flow order, or split by "
                         "edge_types into views"))

    # Page fit --------------------------------------------------------------------
    ps = S.PAGE_SIZES.get(spec.get("page", "auto"))
    if ps:
        scale = min(ps[0] / sc["width"], ps[1] / sc["height"])
        sc["_page_scale"] = scale
        if scale < L.PAGE_MIN_SCALE:
            fits = [n for n, sz in S.PAGE_SIZES.items()
                    if sz and min(sz[0] / sc["width"], sz[1] / sc["height"]) >= L.PAGE_MIN_SCALE]
            opts = (f"use page {' or '.join(fits)}, " if fits else "") + "use page 'auto', or split into views"
            out.append(issue("ERROR", "page", f"{tag}content is {sc['width']}x{sc['height']} px; fits "
                             f"{spec['page']} only at {scale:.0%} (minimum {L.PAGE_MIN_SCALE:.0%})", opts))
        elif scale < 1:
            out.append(issue("INFO", "page", f"{tag}PDF page is scaled to {scale:.0%} to fit {spec['page']}"))

    # Semantics -------------------------------------------------------------------
    if spec["kind"] == "dataflow":
        for e in sc["edges"]:
            if e["crossing"] and not e.get("protocol"):
                out.append(issue("WARNING", epath(e, "protocol"),
                                 f"{tag}flow {e['src']} -> {e['dst']} crosses a trust boundary with no protocol",
                                 "add 'protocol' (and 'port') so reviewers can see how the crossing is protected"))
            if e["crossing"] and not e.get("marking") and not spec.get("marking"):
                lvl = "ERROR" if spec.get("provenance") == "strict" else "WARNING"
                out.append(issue(lvl, epath(e, "marking"),
                                 f"{tag}flow {e['src']} -> {e['dst']} crosses a trust boundary with no marking",
                                 "add 'marking' to the flow, or set the page 'marking' it falls under"))
    if spec["kind"] == "bdd":
        for n in sc["nodes"]:
            if not n.get("stereotype") and not n.get("collapsed"):
                out.append(issue("INFO", npath(n["id"], "stereotype"), f"{tag}block '{n['id']}' has no stereotype"))
    return out


def spec_checks(spec):
    """Checks that need the whole spec rather than one view."""
    out = []
    used_ports = set()
    for e in spec["edges"]:
        if e.get("from_port"):
            used_ports.add((e["from"], e["from_port"]))
        if e.get("to_port"):
            used_ports.add((e["to"], e["to_port"]))
    for i, n in enumerate(spec["nodes"]):
        for k, p in enumerate(n.get("ports", [])):
            if (n["id"], p["id"]) not in used_ports:
                out.append(issue("WARNING", f"nodes[{i}].ports[{k}]", f"port '{p['id']}' on '{n['id']}' is not used "
                                 "by any edge", "connect an edge to it ('node.port') or remove it"))
    # Loops: the layered layout must reverse one edge of every loop, which usually means a long detour.
    # Each edge is lifted to the two children of the lowest common container, because a
    # container cannot sit both before and after another one (container-level loops count too).
    parent = {x["id"]: x.get("in") for x in spec["containers"] + spec["nodes"]}

    def chain(i):
        out, g = [i], 0
        while parent.get(out[-1]) and g < 50:
            out.append(parent[out[-1]])
            g += 1
        return out
    adj = {}
    for i, e in enumerate(spec["edges"]):
        if spec["edge_types"][e["type"]].get("reverse_layout"):
            a, b = e["to"], e["from"]
        else:
            a, b = e["from"], e["to"]
        ca, cb = chain(a), chain(b)
        common = next((x for x in ca if x in cb), None)
        la = ca[ca.index(common) - 1] if common in ca else ca[-1]
        lb = cb[cb.index(common) - 1] if common in cb else cb[-1]
        adj.setdefault(la, []).append((lb, i))
    state, back = {}, []

    def dfs(u):
        state[u] = 1
        for v, i in adj.get(u, []):
            if state.get(v) == 1:
                back.append(i)
            elif v not in state:
                dfs(v)
        state[u] = 2
    import sys
    sys.setrecursionlimit(max(1000, 4 * len(spec["nodes"]) + 100))
    order = [x["id"] for x in spec["containers"] + spec["nodes"]]
    for u in order:
        if u not in state:
            dfs(u)
    if back:
        names = ", ".join(f"edges[{i}]" for i in back[:6])
        out.append(issue("INFO", "edges", f"{len(back)} edge(s) close a loop ({names}); they are laid out "
                         "reversed so the flow stays one-directional, and their arrows keep the real direction"))

    has_child = {x.get("in") for x in spec["containers"] + spec["nodes"]}
    for i, c in enumerate(spec["containers"]):
        if c["id"] not in has_child:
            out.append(issue("WARNING", f"containers[{i}]", f"container '{c['id']}' is empty",
                             "put nodes in it ('in') or remove it"))
    linked = {e["from"] for e in spec["edges"]} | {e["to"] for e in spec["edges"]}
    for i, n in enumerate(spec["nodes"]):
        if n["id"] not in linked and spec["kind"] not in ("bdd",):
            out.append(issue("INFO", f"nodes[{i}]", f"node '{n['id']}' has no edges"))
    if spec.get("marking"):
        out.append(issue("INFO", "marking", "markings are drawn as given; the tool does not determine or "
                                            "validate classification"))

    # Provenance gates (reference/provenance_profile.md) -------------------------
    strict = spec.get("provenance", "light") == "strict"
    gate = "ERROR" if strict else "WARNING"
    missing = [k for k in ("id", "owner", "status") if not spec.get(k)]
    if missing and (strict or len(missing) < 3):
        out.append(issue(gate, "provenance",
                         ("strict provenance requires spec metadata; missing: " if strict
                          else "provenance metadata is partially supplied; missing: ") + ", ".join(missing),
                         "add 'id', 'owner' and 'status' at the top level of the spec"))
    for coll, name in ((spec["containers"], "containers"), (spec["nodes"], "nodes")):
        for i, x in enumerate(coll):
            if x.get("shape") == "external" or x.get("stereotype") == "external":
                miss = [k for k in ("owner", "source_ref") if not x.get(k)]
                if miss:
                    out.append(issue(gate, f"{name}[{i}]",
                                     f"external element '{x['id']}' has no {', '.join(miss)}",
                                     "set 'owner' and 'source_ref' on external elements"))
    elements = {x["id"] for x in spec["containers"] + spec["nodes"]}
    known = elements | {s["id"] for s in spec.get("sources", [])}
    import re as _re
    for n in spec["nodes"]:
        for lines in (n.get("compartments") or {}).values():
            for ln in lines:
                known.update(_re.findall(r"[A-Za-z][A-Za-z0-9_.]*-\d+", ln))
    for i, e in enumerate(spec["edges"]):
        if e["type"] in ("trace", "allocate", "verify", "satisfy"):
            target = e.get("ref")
            if not target and e.get("label"):
                target = e["label"].strip().split()[0].strip(",;:")
            if not target:
                out.append(issue(gate, f"edges[{i}]",
                                 f"{e['type']} edge has no target id",
                                 "set 'ref' (or start the label with the target id, e.g. 'REQ-014')"))
            elif target not in known:
                out.append(issue(gate, f"edges[{i}].ref",
                                 f"{e['type']} target '{target}' does not resolve to an element, a source, "
                                 "or an id named in the spec",
                                 "add the target to 'sources', name it in a compartment, or fix 'ref'"))
    return out


def _lname(kind, ref):
    if kind == "edge":
        return f"edge {ref['src']}->{ref['dst']}"
    return f"port {ref[0]['id']}.{ref[1]['id']}"
