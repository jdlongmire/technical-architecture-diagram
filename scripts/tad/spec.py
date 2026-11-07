"""Load, normalize and validate a diagram spec.

The normalized ("clean") spec is flat: every container and node lists its parent
in "in", and every edge endpoint is an id. All issue paths refer to the clean spec,
because that is the file edited during the fix loop.
"""
import json
import re
from collections import OrderedDict

from . import limits as L
from . import styles as S


class SpecError(Exception):
    pass


def issue(level, path, msg, fix=None):
    return {"level": level, "path": path, "msg": msg, "fix": fix}


# Loading -----------------------------------------------------------------------

def strip_comments(text):
    """Remove // line comments and /* */ blocks outside strings, plus trailing commas."""
    out, i, n = [], 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    s = "".join(out)
    return re.sub(r",(\s*[}\]])", r"\1", s)


def load(path):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    try:
        return json.loads(strip_comments(raw), object_pairs_hook=OrderedDict)
    except json.JSONDecodeError as e:
        raise SpecError(f"{path}: not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}")


# Helpers -----------------------------------------------------------------------

def slug(text):
    s = re.sub(r"[^A-Za-z0-9]+", "_", str(text)).strip("_").lower()
    return s or "item"


def _pick(d, names, fixes, path, canonical):
    """Return the first present alias; record a rename if it was not the canonical name."""
    for n in names:
        if n in d and d[n] not in (None, ""):
            if n != canonical:
                fixes.append(f"{path}: '{n}' read as '{canonical}'")
            return d[n]
    return None


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


_DIRS = {"right": "RIGHT", "lr": "RIGHT", "left-right": "RIGHT", "horizontal": "RIGHT",
         "down": "DOWN", "tb": "DOWN", "td": "DOWN", "top-down": "DOWN", "vertical": "DOWN", "auto": "AUTO"}
_SIDES = {"n": "NORTH", "north": "NORTH", "top": "NORTH", "s": "SOUTH", "south": "SOUTH", "bottom": "SOUTH",
          "e": "EAST", "east": "EAST", "right": "EAST", "w": "WEST", "west": "WEST", "left": "WEST"}
_COMPARTMENTS = ("parts", "references", "values", "operations", "constraints", "ports", "flows", "notes")


# Normalization -----------------------------------------------------------------

def normalize(raw):
    """raw dict -> (clean_spec dict, autofixes list[str], issues list)."""
    fixes, issues = [], []
    if not isinstance(raw, dict):
        raise SpecError("top level of the spec must be a JSON object")

    spec = OrderedDict()
    spec["title"] = _pick(raw, ["title", "name"], fixes, "spec", "title") or "Untitled Diagram"
    sub = _pick(raw, ["subtitle", "description", "desc"], fixes, "spec", "subtitle")
    if sub:
        spec["subtitle"] = sub

    kind = _pick(raw, ["kind", "diagram", "type"], fixes, "spec", "kind")
    kind_s = str(kind or "").strip().lower()
    kind_alias = {"deployment": "network", "net": "network", "icd": "interface", "interfaces": "interface",
                  "dfd": "dataflow", "data_flow": "dataflow", "data-flow": "dataflow", "data flow": "dataflow",
                  "block": "bdd", "block definition": "bdd", "internal block": "ibd", "internal": "ibd"}
    kind_s = kind_alias.get(kind_s, kind_s)
    if not kind_s:
        kind_s = "network"
        fixes.append("spec.kind: missing, defaulted to 'network'")
    if kind_s not in S.KINDS:
        issues.append(issue("INVALID", "kind", f"unknown kind '{kind}'",
                            f"set kind to one of: {', '.join(S.KINDS)}"))
        kind_s = "network"
    spec["kind"] = kind_s

    d = _pick(raw, ["direction", "dir", "flow"], fixes, "spec", "direction")
    if d:
        dd = _DIRS.get(str(d).strip().lower())
        if not dd:
            issues.append(issue("ERROR", "direction", f"unknown direction '{d}'", "use RIGHT, DOWN or AUTO"))
        else:
            spec["direction"] = dd
    spec.setdefault("direction", S.DEFAULT_DIRECTION[kind_s])

    m = raw.get("marking") or raw.get("classification") or raw.get("banner")
    if m:
        spec["marking"] = str(m).strip()

    page = str(raw.get("page", "auto")).strip().lower().replace(" ", "")
    if page not in S.PAGE_SIZES:
        issues.append(issue("ERROR", "page", f"unknown page size '{page}'",
                            f"use one of: {', '.join(S.PAGE_SIZES)}"))
        page = "auto"
    spec["page"] = page

    if isinstance(raw.get("theme"), dict):
        spec["theme"] = OrderedDict((k, str(v).lstrip("#")) for k, v in raw["theme"].items())
    if isinstance(raw.get("elk"), dict):
        spec["elk"] = OrderedDict((str(k), str(v)) for k, v in raw["elk"].items())
    spec["legend"] = bool(raw.get("legend", True))
    spec["icons"] = bool(raw.get("icons", False))
    it = raw.get("interface_table", raw.get("table"))
    spec["interface_table"] = bool(it) if it is not None else (kind_s == "interface")

    # Edge types: defaults for the kind, merged with custom ones.
    etypes = OrderedDict((k, dict(v)) for k, v in S.EDGE_TYPES[kind_s].items())
    for name, val in (raw.get("edge_types") or {}).items():
        base = dict(etypes.get(name, dict(label=name, dash="none", color="edge", start="none", end="arrow", width=1.5)))
        if isinstance(val, dict):
            base.update(val)
        etypes[name] = base
    spec["edge_types"] = etypes

    # Containers and nodes (nested or flat) ---------------------------------------
    containers, nodes = [], []

    def walk_container(c, path, parent):
        if not isinstance(c, dict):
            issues.append(issue("INVALID", path, "container must be an object"))
            return
        has_children = any(c.get(k) for k in ("containers", "groups", "children_containers", "nodes", "children"))
        looks_like_node = any(k in c for k in ("shape", "ports", "detail", "compartments", "attributes", "icon"))
        if looks_like_node and not has_children:
            fixes.append(f"{path}: has node fields and no children, read as a node")
            walk_node(c, path, parent)
            return
        cc = OrderedDict()
        label = _pick(c, ["label", "title", "name"], fixes, path, "label")
        cid = c.get("id")
        if not label and not cid:
            issues.append(issue("INVALID", path, "container has no id or label", "add a label"))
            return
        cc["id"] = str(cid) if cid else slug(label)
        if not cid:
            fixes.append(f"{path}: id derived from label -> '{cc['id']}'")
        cc["label"] = str(label or cid)
        ctype = _pick(c, ["type", "kind", "boundary"], fixes, path, "type")
        ctype = str(ctype).strip().lower() if ctype else S.DEFAULT_CONTAINER_TYPE[kind_s]
        ctype = {"trust boundary": "trust", "trust_boundary": "trust", "boundary": "trust", "network": "zone",
                 "vlan": "zone", "subnet": "zone", "segment": "zone", "facility": "site", "building": "site",
                 "block": "system", "class": "classification", "level": "classification"}.get(ctype, ctype)
        if ctype not in S.CONTAINER_TYPES:
            issues.append(issue("WARNING", path + ".type", f"unknown container type '{ctype}', drawn as group",
                                f"use one of: {', '.join(S.CONTAINER_TYPES)}"))
            ctype = "group"
        cc["type"] = ctype
        inn = parent or _pick(c, ["in", "parent", "container", "within"], fixes, path, "in")
        if inn:
            cc["in"] = str(inn)
        st = _pick(c, ["stereotype", "stereo"], fixes, path, "stereotype")
        if st:
            cc["stereotype"] = str(st).strip("«»<> ")
        if c.get("marking"):
            cc["marking"] = str(c["marking"]).strip()
        containers.append(cc)
        for j, sub_c in enumerate(_as_list(c.get("containers") or c.get("groups") or c.get("children_containers"))):
            walk_container(sub_c, f"{path}.containers[{j}]", cc["id"])
        for j, n in enumerate(_as_list(c.get("nodes") or c.get("children"))):
            walk_node(n, f"{path}.nodes[{j}]", cc["id"])

    def walk_node(n, path, parent):
        if isinstance(n, str):
            n = {"label": n}
        if not isinstance(n, dict):
            issues.append(issue("INVALID", path, "node must be an object or a string"))
            return
        nn = OrderedDict()
        label = _pick(n, ["label", "title", "name"], fixes, path, "label")
        nid = n.get("id")
        if not label and not nid:
            issues.append(issue("INVALID", path, "node has no id or label", "add a label"))
            return
        nn["id"] = str(nid) if nid else slug(label)
        if not nid:
            fixes.append(f"{path}: id derived from label -> '{nn['id']}'")
        nn["label"] = str(label or nid)
        st = _pick(n, ["stereotype", "stereo", "role"], fixes, path, "stereotype")
        shape = _pick(n, ["shape"], fixes, path, "shape")
        ntype = n.get("type") or n.get("kind")
        if ntype and not shape:
            t = str(ntype).strip().lower()
            if t in S.NODE_SHAPES or t in S.SHAPE_ALIASES:
                shape = t
                fixes.append(f"{path}: 'type' read as 'shape'")
            elif not st:
                st = ntype
                fixes.append(f"{path}: 'type' read as 'stereotype'")
        if shape:
            s = str(shape).strip().lower()
            s = S.SHAPE_ALIASES.get(s, s)
            if s not in S.NODE_SHAPES:
                issues.append(issue("WARNING", path + ".shape", f"unknown shape '{shape}', drawn as box",
                                    f"use one of: {', '.join(S.NODE_SHAPES)}"))
                s = "box"
            nn["shape"] = s
        if st:
            nn["stereotype"] = str(st).strip("«»<> ")
        det = _pick(n, ["detail", "desc", "description", "address", "ip", "version"], fixes, path, "detail")
        if det:
            nn["detail"] = str(det)
        inn = parent or _pick(n, ["in", "parent", "container", "zone", "group", "within"], fixes, path, "in")
        if inn:
            nn["in"] = str(inn)
        ports = []
        for k, p in enumerate(_as_list(n.get("ports"))):
            pp = OrderedDict()
            if isinstance(p, str):
                name, _, side = p.partition(":")
                pp["id"] = slug(name)
                pp["label"] = name.strip()
                if side:
                    pp["side"] = side.strip()
            elif isinstance(p, dict):
                pl = p.get("label") or p.get("name") or p.get("title") or p.get("id")
                if not pl:
                    issues.append(issue("INVALID", f"{path}.ports[{k}]", "port has no id or label"))
                    continue
                pp["id"] = str(p.get("id") or slug(pl))
                pp["label"] = str(pl)
                if p.get("side"):
                    pp["side"] = str(p["side"])
            else:
                issues.append(issue("INVALID", f"{path}.ports[{k}]", "port must be a string or object"))
                continue
            if "side" in pp:
                sd = _SIDES.get(pp["side"].strip().lower())
                if not sd:
                    issues.append(issue("WARNING", f"{path}.ports[{k}].side", f"unknown side '{pp['side']}' was "
                                        "dropped, so the layout picks the side", "set side to N, S, E or W"))
                    del pp["side"]
                else:
                    pp["side"] = sd
            ports.append(pp)
        if ports:
            nn["ports"] = ports
        comps = OrderedDict()
        if isinstance(n.get("compartments"), dict):
            for k, v in n["compartments"].items():
                comps[str(k)] = [str(x) for x in _as_list(v)]
        for k in _COMPARTMENTS:
            if k in n and k != "ports":
                comps[k] = [str(x) for x in _as_list(n[k])]
        if n.get("attributes"):
            comps["values"] = comps.get("values", []) + [str(x) for x in _as_list(n["attributes"])]
            fixes.append(f"{path}: 'attributes' read as compartment 'values'")
        if comps:
            nn["compartments"] = comps
        if n.get("icon"):
            nn["icon"] = str(n["icon"])
        if n.get("marking"):
            nn["marking"] = str(n["marking"]).strip()
        nodes.append(nn)

    for i, c in enumerate(_as_list(raw.get("containers") or raw.get("groups") or raw.get("boundaries"))):
        walk_container(c, f"containers[{i}]", None)
    for i, n in enumerate(_as_list(raw.get("nodes"))):
        walk_node(n, f"nodes[{i}]", None)

    # Unique ids (containers and nodes share one namespace) ---------------------------
    seen = {}
    for coll, name in ((containers, "containers"), (nodes, "nodes")):
        for i, x in enumerate(coll):
            if x["id"] in seen:
                issues.append(issue("INVALID", f"{name}[{i}].id",
                                    f"duplicate id '{x['id']}' (also {seen[x['id']]})",
                                    "give each container and node a unique id"))
            else:
                seen[x["id"]] = f"{name}[{i}]"

    spec["containers"] = containers
    spec["nodes"] = nodes

    # Lookup by id, then by label (case-insensitive) ----------------------------------
    by_id = {x["id"]: x for x in containers + nodes}
    by_label = {}
    for x in containers + nodes:
        by_label.setdefault(x["label"].strip().lower(), []).append(x)

    def resolve(ref):
        if ref is None:
            return None
        r = str(ref).strip()
        if r in by_id:
            return by_id[r]
        hits = by_label.get(r.lower(), [])
        if len(hits) == 1:
            return hits[0]
        sl = slug(r)
        if sl in by_id:
            return by_id[sl]
        squash = re.sub(r"[^a-z0-9]", "", r.lower())
        hits = [x for x in containers + nodes if re.sub(r"[^a-z0-9]", "", x["id"].lower()) == squash
                or re.sub(r"[^a-z0-9]", "", x["label"].lower()) == squash]
        if len(hits) == 1:
            return hits[0]
        return None

    for coll, name in ((containers, "containers"), (nodes, "nodes")):
        for i, x in enumerate(coll):
            if "in" in x:
                p = resolve(x["in"])
                if p is None or p in nodes:
                    issues.append(issue("INVALID", f"{name}[{i}].in", f"parent '{x['in']}' is not a container",
                                        "set 'in' to the id of a container, or remove it"))
                elif p["id"] != x["in"]:
                    fixes.append(f"{name}[{i}].in: '{x['in']}' resolved to id '{p['id']}'")
                    x["in"] = p["id"]

    # Parent cycles / depth
    cmap = {c["id"]: c for c in containers}
    for i, c in enumerate(containers):
        seen_p, cur, depth = set(), c, 0
        while "in" in cur:
            if cur["id"] in seen_p:
                issues.append(issue("INVALID", f"containers[{i}].in", "containers are nested in a cycle",
                                    "fix the 'in' chain so it ends at the top level"))
                break
            seen_p.add(cur["id"])
            cur = cmap.get(cur["in"], {})
            depth += 1
        if depth + 1 > L.CONTAINER_DEPTH_MAX:
            issues.append(issue("ERROR", f"containers[{i}]",
                                f"nesting depth {depth + 1} exceeds {L.CONTAINER_DEPTH_MAX}",
                                "flatten one level (merge a container into its parent)"))

    # Edges -------------------------------------------------------------------------
    edges = []
    for i, e in enumerate(_as_list(raw.get("edges") or raw.get("links") or raw.get("flows") or raw.get("connections"))):
        path = f"edges[{i}]"
        if not isinstance(e, dict):
            issues.append(issue("INVALID", path, "edge must be an object"))
            continue
        ee = OrderedDict()
        ends = {}
        for side, names in (("from", ["from", "source", "src", "a"]), ("to", ["to", "target", "dst", "b"])):
            ref = _pick(e, names, fixes, path, side)
            port = e.get(side + "_port")
            target = resolve(ref)
            if target is None and ref is not None and "." in str(ref) and port is None:
                head, _, tail = str(ref).rpartition(".")
                target = resolve(head)
                if target is not None:
                    port = tail
            if target is None:
                issues.append(issue("INVALID", f"{path}.{side}", f"'{ref}' does not match any node or container id/label",
                                    "use an existing id, or 'node_id.port_id' for a port"))
                ends[side] = None
                ee[side] = str(ref)
                continue
            ee[side] = target["id"]
            if port is not None:
                pts = target.get("ports", [])
                pm = [p for p in pts if p["id"] == str(port) or p["label"].lower() == str(port).lower()
                      or p["id"] == slug(port)]
                if not pm and target in containers:
                    issues.append(issue("INVALID", f"{path}.{side}",
                                        f"'{target['id']}' is a container, and only nodes have ports",
                                        f"if '{target['id']}' is a component, move it from a 'containers' list "
                                        f"into a 'nodes' list"))
                elif not pm:
                    issues.append(issue("INVALID", f"{path}.{side}",
                                        f"'{target['id']}' has no port '{port}'",
                                        f"add the port to {target['id']}.ports or use one of: "
                                        f"{', '.join(p['id'] for p in pts) or '(none defined)'}"))
                else:
                    ee[side + "_port"] = pm[0]["id"]
                if not pm:
                    ee[side + "_port"] = str(port)
            ends[side] = target
        if not ends.get("from") or not ends.get("to"):
            edges.append(_keep_rest(ee, e))
            continue
        et = _pick(e, ["type", "kind"], fixes, path, "type")
        style = e.get("style")
        if not et and style and str(style) in etypes:
            et = style
        et = str(et).strip().lower() if et else S.DEFAULT_EDGE_TYPE[kind_s]
        if et not in etypes:
            issues.append(issue("WARNING", f"{path}.type", f"unknown edge type '{et}' for kind '{kind_s}'",
                                f"use one of: {', '.join(etypes)}, or define it under edge_types"))
            et = S.DEFAULT_EDGE_TYPE[kind_s]
        ee["type"] = et
        for key, names in (("id", ["id", "ifid", "interface", "interface_id"]),
                           ("label", ["label", "name", "title"]),
                           ("data", ["data", "payload", "message", "item", "items"]),
                           ("protocol", ["protocol", "proto"]),
                           ("port", ["port", "tcp", "udp", "port_number"]),
                           ("marking", ["marking", "classification"])):
            v = _pick(e, names, fixes, path, key)
            if v not in (None, ""):
                ee[key] = str(v)
        if e.get("dashed") is True or (style in ("dashed", "dotted")):
            ee["dash"] = "dotted" if style == "dotted" else "dashed"
        # container <-> own descendant is not drawable
        a, b = ends["from"], ends["to"]
        if _is_ancestor(a["id"], b, cmap) or _is_ancestor(b["id"], a, cmap):
            issues.append(issue("INVALID", path, f"edge joins '{a['id']}' to its own contents",
                                "connect to a node inside the container instead"))
        elif a["id"] == b["id"]:
            issues.append(issue("INVALID", path, "edge starts and ends on the same element", "remove it"))
        edges.append(ee)
    spec["edges"] = edges

    # Interface ids
    if kind_s == "interface":
        n = 0
        for i, ee in enumerate(edges):
            if "id" not in ee and etypes[ee["type"]].get("ifid", True):
                n += 1
                ee["id"] = f"IF-{n:02d}"
                fixes.append(f"edges[{i}].id: assigned '{ee['id']}'")

    # Views -------------------------------------------------------------------------
    views = []
    for i, v in enumerate(_as_list(raw.get("views"))):
        if not isinstance(v, dict):
            issues.append(issue("INVALID", f"views[{i}]", "view must be an object"))
            continue
        vv = OrderedDict()
        vv["name"] = str(v.get("name") or v.get("title") or f"View {i + 1}")
        for key, names in (("include", ["include", "only", "show"]), ("exclude", ["exclude", "hide"]),
                           ("collapse", ["collapse", "collapsed"])):
            refs = []
            for r in _as_list(_pick(v, names, fixes, f"views[{i}]", key)):
                t = resolve(r)
                if t is None:
                    issues.append(issue("ERROR", f"views[{i}].{key}", f"'{r}' does not match any id",
                                        "use container or node ids"))
                elif key == "collapse" and t not in containers:
                    issues.append(issue("ERROR", f"views[{i}].collapse", f"'{r}' is not a container",
                                        "collapse only applies to containers"))
                else:
                    refs.append(t["id"])
            if refs:
                vv[key] = refs
        ets = _as_list(v.get("edge_types") or v.get("types"))
        if ets:
            bad = [t for t in ets if t not in etypes]
            if bad:
                issues.append(issue("ERROR", f"views[{i}].edge_types", f"unknown edge types: {', '.join(bad)}",
                                    f"use: {', '.join(etypes)}"))
            vv["edge_types"] = [t for t in ets if t in etypes]
        if v.get("direction"):
            dd = _DIRS.get(str(v["direction"]).strip().lower())
            if dd:
                vv["direction"] = dd
        if v.get("subtitle"):
            vv["subtitle"] = str(v["subtitle"])
        if v.get("hide_unlinked"):
            vv["hide_unlinked"] = True
        views.append(vv)
    if views:
        spec["views"] = views

    if not nodes:
        issues.append(issue("INVALID", "nodes", "the spec has no nodes", "add at least one node"))
    return spec, fixes, issues


def _keep_rest(ee, e):
    """Keep the descriptive fields of an edge that failed to resolve, so the clean spec still holds it."""
    for k in ("type", "id", "label", "data", "protocol", "port", "marking"):
        if e.get(k) not in (None, "") and k not in ee:
            ee[k] = str(e[k])
    return ee


def _is_ancestor(cid, x, cmap):
    cur = x
    guard = 0
    while cur is not None and "in" in cur and guard < 50:
        if cur["in"] == cid:
            return True
        cur = cmap.get(cur["in"])
        guard += 1
    return False


# Content checks that need no layout ------------------------------------------------

def edge_label_lines(e, kind):
    """Edge label as a list of lines: [id: label], [data], [protocol:port]; portion mark on line 1."""
    lines = []
    first = e.get("label", "")
    if e.get("id"):
        first = f"{e['id']}: {first}" if first else e["id"]
    if first:
        lines.append(first)
    if e.get("data") and e.get("data") != e.get("label"):
        lines.append(e["data"])
    proto = e.get("protocol", "")
    if e.get("port"):
        proto = f"{proto}/{e['port']}" if proto else f"port {e['port']}"
    if proto:
        lines.append(proto)
    if e.get("marking") and lines:
        lines[0] = f"{S.portion_mark(e['marking'])} {lines[0]}"
    return lines


def content_checks(spec):
    """Length and placeholder checks against limits.py."""
    out = []

    def chk(path, text, mx, what, field):
        if text is None:
            return
        if "<<" in str(text) or ">>" in str(text):
            out.append(issue("ERROR", path, f"placeholder left in: {text!r}",
                             "replace it with real content or delete the item"))
        elif len(str(text)) > mx:
            out.append(issue("ERROR", path, f"{what} {text!r} is {len(str(text))} characters (limit {mx})",
                             f"shorten {field} to at most {mx} characters"))

    for i, c in enumerate(spec["containers"]):
        chk(f"containers[{i}].label", c["label"], L.CONTAINER_LABEL_MAX_CHARS, "container label", "it")
    for i, n in enumerate(spec["nodes"]):
        p = f"nodes[{i}]"
        chk(p + ".label", n["label"], L.NODE_LABEL_MAX_CHARS, "label", "it")
        chk(p + ".stereotype", n.get("stereotype"), L.STEREOTYPE_MAX_CHARS, "stereotype", "it")
        chk(p + ".detail", n.get("detail"), L.DETAIL_MAX_CHARS, "detail", "it")
        for k, pt in enumerate(n.get("ports", [])):
            chk(f"{p}.ports[{k}].label", pt["label"], L.PORT_LABEL_MAX_CHARS, "port label", "it")
        total = 0
        for cname, lines in n.get("compartments", {}).items():
            total += len(lines)
            for k, ln in enumerate(lines):
                chk(f"{p}.compartments.{cname}[{k}]", ln, L.ATTR_MAX_CHARS, "compartment line", "it")
        if total > L.ATTR_MAX_LINES:
            out.append(issue("ERROR", p + ".compartments", f"{total} compartment lines (limit {L.ATTR_MAX_LINES})",
                             f"remove {total - L.ATTR_MAX_LINES} lines, or move detail to a separate view"))
    # Any placeholder anywhere else in the spec
    reported = {i["path"] for i in out}

    def scan(x, path):
        if isinstance(x, str):
            if ("<<" in x or ">>" in x) and path not in reported:
                out.append(issue("ERROR", path, f"placeholder left in: {x!r}",
                                 "replace it with real content or delete it"))
        elif isinstance(x, dict):
            for k, v in x.items():
                scan(v, f"{path}.{k}" if path else k)
        elif isinstance(x, list):
            for k, v in enumerate(x):
                scan(v, f"{path}[{k}]")
    for key in ("title", "subtitle", "marking", "edges", "views"):
        if key in spec:
            scan(spec[key], key)
    for i, e in enumerate(spec["edges"]):
        p = f"edges[{i}]"
        lines = edge_label_lines(e, spec["kind"])
        if len(lines) > L.EDGE_LABEL_MAX_LINES:
            out.append(issue("ERROR", p, f"edge label has {len(lines)} lines (limit {L.EDGE_LABEL_MAX_LINES})",
                             "drop 'data' or 'label' (keep the one that says more)"))
        for ln in lines:
            if len(ln) > L.EDGE_LABEL_MAX_LINE_CHARS:
                field = _which_field(e, ln)
                over = len(ln) - L.EDGE_LABEL_MAX_LINE_CHARS
                out.append(issue("ERROR", f"{p}.{field}", f"edge label line {ln!r} is {len(ln)} characters "
                                 f"(limit {L.EDGE_LABEL_MAX_LINE_CHARS})",
                                 f"shorten {field} by at least {over} characters"))
    return out


def _which_field(e, line):
    for k in ("protocol", "data", "label", "port", "id"):
        if e.get(k) and e[k] in line:
            return k
    return "label"
