"""Write scenes to an uncompressed .drawio file (one page per scene).

Every container, node, port and edge is a native draw.io cell: nodes are children
of their containers, ports are children of their nodes, and edges are attached to
node or port cells, so edges stay connected when things are moved.
"""
import base64
import xml.etree.ElementTree as ET
from html import escape as hesc

from . import limits as L
from . import styles as S
from .geom import nearest_on_path
from .layout import BANNER_H, MARGIN, ICON, PAD_X
from .svg import icon_markup

ARROWS = {
    "none": ("none", 0),
    "arrow": ("block", 1),
    "open": ("open", 0),
    "triangle": ("block", 0),
    "diamond": ("diamondThin", 1),
    "odiamond": ("diamondThin", 0),
}


def _h(c):
    return "none" if c in (None, "none") else "#" + str(c).lstrip("#")


def _style(d):
    """dict -> draw.io style string. A key with value None is written bare (e.g. 'text;')."""
    return ";".join(k if v is None else f"{k}={v}" for k, v in d.items()) + ";"


def _dash(d, w):
    if d == "dashed":
        return {"dashed": 1, "dashPattern": f"{round(6 + w * 2)} {round(4 + w)}"}
    if d == "dotted":
        return {"dashed": 1, "dashPattern": "1 3"}
    return {}


class Page:
    def __init__(self, name, w, h):
        self.diagram = ET.Element("diagram", name=name, id=_safe_id(name))
        self.model = ET.SubElement(self.diagram, "mxGraphModel", dx="0", dy="0", grid="1", gridSize="10",
                                   guides="1", tooltips="1", connect="1", arrows="1", fold="1", page="1",
                                   pageScale="1", pageWidth=str(w), pageHeight=str(h), math="0", shadow="0")
        self.root = ET.SubElement(self.model, "root")
        ET.SubElement(self.root, "mxCell", id="0")
        ET.SubElement(self.root, "mxCell", id="1", parent="0")
        self.n = 0

    def vertex(self, cid, value, style, x, y, w, h, parent="1"):
        c = ET.SubElement(self.root, "mxCell", id=cid, value=value, style=_style(style), vertex="1", parent=parent)
        ET.SubElement(c, "mxGeometry", x=f"{x:.2f}", y=f"{y:.2f}", width=f"{w:.2f}", height=f"{h:.2f}",
                      **{"as": "geometry"})
        return c

    def edge(self, cid, value, style, source=None, target=None, points=None, parent="1",
             src_pt=None, dst_pt=None, label_geo=None):
        attrs = dict(id=cid, value=value, style=_style(style), edge="1", parent=parent)
        if source:
            attrs["source"] = source
        if target:
            attrs["target"] = target
        c = ET.SubElement(self.root, "mxCell", **attrs)
        g = ET.SubElement(c, "mxGeometry", relative="1", **{"as": "geometry"})
        if label_geo:
            g.set("x", f"{label_geo[0]:.4f}")
            g.set("y", "0")
            ET.SubElement(g, "mxPoint", x=f"{label_geo[1]:.2f}", y=f"{label_geo[2]:.2f}", **{"as": "offset"})
        if src_pt:
            ET.SubElement(g, "mxPoint", x=f"{src_pt[0]:.2f}", y=f"{src_pt[1]:.2f}", **{"as": "sourcePoint"})
        if dst_pt:
            ET.SubElement(g, "mxPoint", x=f"{dst_pt[0]:.2f}", y=f"{dst_pt[1]:.2f}", **{"as": "targetPoint"})
        if points:
            arr = ET.SubElement(g, "Array", **{"as": "points"})
            for (px, py) in points:
                ET.SubElement(arr, "mxPoint", x=f"{px:.2f}", y=f"{py:.2f}")
        return c


def _safe_id(s):
    return "".join(ch if ch.isalnum() else "_" for ch in s)[:40] or "page"


def page_from_scene(sc):
    th = sc["theme"]
    W, H = sc["width"], sc["height"]
    pg = Page(sc["name"], W, H)

    def bare(kind, **kw):
        """Style dict that starts with a bare shape keyword (e.g. 'text')."""
        d = {kind: None} if kind else {}
        d.update(kw)
        return d

    y0 = MARGIN
    if sc.get("marking"):
        bg, fg = S.marking_colors(sc["marking"])
        for i, by in enumerate((8, H - 8 - BANNER_H)):
            pg.vertex(f"banner{i}", sc["marking"].upper(),
                      {"rounded": 0, "html": 1, "whiteSpace": "wrap", "fillColor": _h(bg), "strokeColor": "none",
                       "fontColor": _h(fg), "fontStyle": 1, "fontSize": L.FONT_BANNER, "fontFamily": th["font"],
                       "align": "center", "verticalAlign": "middle", "locked": 1}, 0, by, W, BANNER_H)
        y0 += BANNER_H
    pg.vertex("title", hesc(sc["title"]),
              bare("text", html=1, align="left", verticalAlign="top", fontSize=L.FONT_TITLE, fontStyle=1,
                   fontFamily=th["font"], fontColor=_h(th["title"]), whiteSpace="nowrap"),
              MARGIN, y0 - 4, max(200, sc["title_w"] + 20), L.FONT_TITLE + 10)
    if sc.get("subtitle"):
        pg.vertex("subtitle", hesc(sc["subtitle"]),
                  bare("text", html=1, align="left", verticalAlign="top", fontSize=L.FONT_SUBTITLE,
                       fontFamily=th["font"], fontColor=_h(th["muted"]), whiteSpace="nowrap"),
                  MARGIN, y0 + L.FONT_TITLE + 8, max(300, sc["title_w"] + 200), L.FONT_SUBTITLE + 8)
    pg.vertex("viewname", "View: " + hesc(sc["name"]),
              bare("text", html=1, align="right", verticalAlign="top", fontSize=11, fontFamily=th["font"],
                   fontColor=_h(th["muted"])), W - MARGIN - 260, y0 + 6, 260, 18)

    if sc.get("table"):
        _table(pg, sc, th)
        return pg.diagram

    absb = {}
    cell_of = {}
    for c in sc["containers"]:
        absb[c["id"]] = (c["x"], c["y"])
        px, py = absb.get(c["parent"], (0, 0)) if c["parent"] else (0, 0)
        cid = "c_" + c["id"]
        cell_of[c["id"]] = cid
        label = ""
        if c.get("stereotype"):
            label += f'<i style="font-weight:normal;font-size:{L.FONT_STEREO}px;color:{_h(th["muted"])}">' \
                     f'«{hesc(c["stereotype"])}»</i> '
        label += f"<b>{hesc(c['label'])}</b>"
        st = {"rounded": 1, "arcSize": 2, "absoluteArcSize": 1, "html": 1, "whiteSpace": "wrap", "container": 1,
              "collapsible": 0, "recursiveResize": 0, "fillColor": _h(c["fill"]), "strokeColor": _h(c["stroke"]),
              "strokeWidth": c["width"], "verticalAlign": "top", "align": "left", "spacingLeft": 10,
              "spacingTop": 2, "fontSize": L.FONT_CONTAINER, "fontFamily": th["font"], "fontColor": _h(th["text"])}
        st.update(_dash(c["dash"], c["width"]))
        pg.vertex(cid, label, st, c["x"] - px, c["y"] - py, c["w"], c["h"],
                  parent=cell_of.get(c["parent"], "1") if c["parent"] else "1")
        if c.get("marking"):
            bg, fg = S.marking_colors(c["marking"])
            from .text import width as tw
            bw = tw(c["marking"], 9, bold=True) + 12
            pg.vertex(cid + "_mk", hesc(c["marking"].upper()),
                      {"rounded": 1, "arcSize": 20, "html": 1, "fillColor": _h(bg), "strokeColor": "none",
                       "fontColor": _h(fg), "fontStyle": 1, "fontSize": 9, "fontFamily": th["font"],
                       "movable": 1, "resizable": 0}, c["w"] - bw - 8, 7, bw, 16, parent=cid)

    for n in sc["nodes"]:
        px, py = absb.get(n["parent"], (0, 0)) if n["parent"] else (0, 0)
        nid = "n_" + n["id"]
        cell_of[n["id"]] = nid
        st = _node_style(n, th)
        value = _node_html(n, th)
        if n["shape"] == "actor":
            fw = 30
            pg.vertex(nid, value, st, n["x"] - px + (n["w"] - fw) / 2, n["y"] - py, fw, 40,
                      parent=cell_of.get(n["parent"], "1") if n["parent"] else "1")
        else:
            pg.vertex(nid, value, st, n["x"] - px, n["y"] - py, n["w"], n["h"],
                      parent=cell_of.get(n["parent"], "1") if n["parent"] else "1")
        if n.get("icon"):
            mk = icon_markup(n["icon"])
            if mk:
                svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
                       f'fill="none" stroke="{_h(th["accent"])}" stroke-width="2" stroke-linecap="round" '
                       f'stroke-linejoin="round">{mk}</svg>').replace("'", '"')
                b64 = base64.b64encode(svg.encode()).decode()
                iy = (n["h"] - ICON) / 2 if not n["comps"] else 8
                pg.vertex(nid + "_icon", "", {"shape": "image", "image": "data:image/svg+xml," + b64,
                                               "imageAspect": 0, "aspect": "fixed", "html": 1},
                          PAD_X, iy, ICON, ICON, parent=nid)
        for p in n["ports"]:
            pcid = f"p_{n['id']}__{p['id']}"
            cell_of[(n["id"], p["id"])] = pcid
            pst = {"rounded": 0, "html": 1, "fillColor": _h(th["port"]), "strokeColor": "none",
                   "fontSize": L.FONT_PORT, "fontFamily": th["font"], "fontColor": _h(th["muted"]),
                   "resizable": 0, "points": "[]"}
            side = p["side"]
            if side == "WEST":
                pst.update(labelPosition="left", align="right", verticalLabelPosition="top", verticalAlign="bottom",
                           spacingRight=2)
            elif side == "SOUTH":
                pst.update(labelPosition="right", align="left", verticalLabelPosition="bottom",
                           verticalAlign="top", spacingLeft=2)
            else:
                pst.update(labelPosition="right", align="left", verticalLabelPosition="top",
                           verticalAlign="bottom", spacingLeft=2)
            pg.vertex(pcid, hesc(p["label"]), pst, p["x"] - n["x"], p["y"] - n["y"], p["w"], p["h"], parent=nid)

    bounds = {}
    for c in sc["containers"]:
        bounds[c["id"]] = (c["x"], c["y"], c["w"], c["h"])
    for n in sc["nodes"]:
        bounds[n["id"]] = (n["x"], n["y"], n["w"], n["h"])
        if n["shape"] == "actor":
            bounds[n["id"]] = (n["x"] + (n["w"] - 30) / 2, n["y"], 30, 40)
        for p in n["ports"]:
            bounds[(n["id"], p["id"])] = (p["x"], p["y"], p["w"], p["h"])

    for e in sc["edges"]:
        st = _edge_style(e["style"], th)
        skey = (e["src"], e["src_port"]) if e["src_port"] else e["src"]
        dkey = (e["dst"], e["dst_port"]) if e["dst_port"] else e["dst"]
        pts = e["points"]
        if len(pts) >= 2:
            st.update(_anchor("exit", pts[0], bounds[skey]))
            st.update(_anchor("entry", pts[-1], bounds[dkey]))
        value = "<br>".join(hesc(x) for x in e["lines"])
        lg = None
        if e.get("label_box") and e["lines"] and len(pts) >= 2:
            x, y, w, h = e["label_box"]
            c = (x + w / 2, y + h / 2)
            t, q = nearest_on_path(pts, c)
            lg = (2 * t - 1, c[0] - q[0], c[1] - q[1])
        pg.edge("e_" + e["id"], value, st, source=cell_of[skey], target=cell_of[dkey], points=pts[1:-1],
                label_geo=lg)

    if sc.get("legend"):
        _legend(pg, sc["legend"], th)
    return pg.diagram


def _anchor(prefix, pt, b):
    x, y, w, h = b
    fx = 0 if w == 0 else max(0.0, min(1.0, (pt[0] - x) / w))
    fy = 0 if h == 0 else max(0.0, min(1.0, (pt[1] - y) / h))
    return {f"{prefix}X": round(fx, 4), f"{prefix}Y": round(fy, 4), f"{prefix}Dx": 0, f"{prefix}Dy": 0,
            f"{prefix}Perimeter": 0}


def _edge_style(est, th):
    col = S.resolve_color(est.get("color", "edge"), th)
    w = est.get("width", 1.5)
    ea, ef = ARROWS.get(est.get("end", "none"), ("none", 0))
    sa, sf = ARROWS.get(est.get("start", "none"), ("none", 0))
    st = {"edgeStyle": "orthogonalEdgeStyle", "rounded": 0, "orthogonalLoop": 1, "jettySize": "auto", "html": 1,
          "strokeColor": _h(col), "strokeWidth": w, "endArrow": ea, "endFill": ef, "startArrow": sa,
          "startFill": sf, "endSize": 8 if ea != "diamondThin" else 12, "startSize": 8 if sa != "diamondThin" else 12,
          "fontSize": L.FONT_EDGE, "fontFamily": th["font"], "fontColor": _h(th["text"]),
          "labelBackgroundColor": "#FFFFFF"}
    st.update(_dash(est.get("dash"), w))
    return st


def _node_style(n, th):
    base = {"html": 1, "whiteSpace": "wrap", "fillColor": _h(th["node_fill"]), "strokeColor": _h(th["node_stroke"]),
            "strokeWidth": 1.25, "fontSize": L.FONT_LABEL, "fontFamily": th["font"], "fontColor": _h(th["text"]),
            "verticalAlign": "middle", "align": "center", "spacing": 4}
    sh = n["shape"]
    if sh == "rounded":
        base.update(rounded=1, arcSize=8, absoluteArcSize=1)
    elif sh == "process":
        base.update(rounded=1, arcSize=16, absoluteArcSize=1)
    elif sh == "external":
        base.update(rounded=0, strokeWidth=2.5)
    elif sh == "store":
        return dict({"shape": "partialRectangle", "right": 1, "top": 1, "bottom": 1, "left": 1},
                    **dict(base, strokeWidth=1.5))
    elif sh == "cylinder":
        return dict({"shape": "cylinder3", "boundedLbl": 1, "backgroundOutline": 1, "size": 7}, **base)
    elif sh == "actor":
        return dict({"shape": "umlActor", "verticalLabelPosition": "bottom", "labelPosition": "center"},
                    **dict(base, verticalAlign="top", whiteSpace="nowrap"))
    elif sh == "note":
        return dict({"shape": "note", "size": 10}, **dict(base, fillColor="#FFFBEA"))
    else:
        base.update(rounded=0)
    if n.get("collapsed"):
        base.update(shape="ext", double=1)
    if n["comps"]:
        base.update(verticalAlign="top", spacingTop=0)
    if n.get("icon"):
        base.update(spacingLeft=ICON + 6)
    return base


def _node_html(n, th):
    parts = []
    for (s, size, bold, italic, colkey, _a) in n["blocks"]:
        tag = hesc(s)
        if bold:
            tag = f"<b>{tag}</b>"
        if italic:
            tag = f"<i>{tag}</i>"
        if size != L.FONT_LABEL or colkey != "text":
            tag = f'<span style="font-size:{size}px;color:{_h(th[colkey])}">{tag}</span>'
        parts.append(tag)
    html = "<br>".join(parts)
    if n["comps"]:
        rows = [f'<div style="text-align:center;padding:6px 4px 4px 4px;">{html}</div>']
        for cname, lines in n["comps"]:
            body = "<br>".join(hesc(x) for x in lines)
            rows.append(f'<div style="border-top:1px solid {_h(th["node_stroke"])};text-align:left;'
                        f'padding:2px 8px 3px 8px;font-size:{L.FONT_ATTR}px;">'
                        f'<div style="text-align:center;font-style:italic;color:{_h(th["muted"])};font-size:'
                        f'{L.FONT_ATTR - 1}px;">{hesc(cname)}</div>{body}</div>')
        html = "".join(rows)
    return html


def _legend(pg, lg, th):
    gid = "legend"
    pg.vertex(gid, "<b>Legend</b>", {"rounded": 1, "arcSize": 3, "absoluteArcSize": 1, "html": 1, "container": 1,
                                     "collapsible": 0, "fillColor": "#FFFFFF", "strokeColor": "#CBD2D9",
                                     "verticalAlign": "top", "align": "left", "spacingLeft": 8, "spacingTop": 2,
                                     "fontSize": 11, "fontFamily": th["font"], "fontColor": _h(th["text"])},
              lg["x"], lg["y"], lg["w"], lg["h"])
    for i, it in enumerate(lg["items"]):
        ix, iy = it["dx"], it["dy"]
        mid = iy + lg["row_h"] / 2
        if it["kind"] == "edge":
            st = _edge_style(it["ref"], th)
            st["edgeStyle"] = "none"
            pg.edge(f"legend_e{i}", "", st, parent=gid, src_pt=(ix + 2, mid), dst_pt=(ix + 40, mid))
        elif it["kind"] == "container":
            c = it["ref"]
            st = {"rounded": 1, "arcSize": 15, "html": 1, "fillColor": _h(c["fill"]), "strokeColor": _h(c["stroke"]),
                  "strokeWidth": min(c["width"], 2)}
            st.update(_dash(c["dash"], 1.2))
            pg.vertex(f"legend_c{i}", "", st, ix + 4, mid - 6, 32, 12, parent=gid)
        elif it["kind"] == "port":
            pg.vertex(f"legend_p{i}", "", {"html": 1, "fillColor": _h(th["port"]), "strokeColor": "none"},
                      ix + 16, mid - 4, 8, 8, parent=gid)
        elif it["kind"] == "collapsed":
            pg.vertex(f"legend_x{i}", "", {"shape": "ext", "double": 1, "html": 1, "fillColor": "#FFFFFF",
                                           "strokeColor": _h(th["node_stroke"])}, ix + 4, mid - 7, 32, 14, parent=gid)
        pg.vertex(f"legend_t{i}", hesc(it["label"]),
                  {"text": None, "html": 1, "align": "left", "verticalAlign": "middle", "fontSize": L.FONT_LEGEND,
                   "fontFamily": th["font"], "fontColor": _h(th["text"]), "whiteSpace": "nowrap"},
                  ix + 46, mid - 8, max(60, len(it["label"]) * 6.2), 16, parent=gid)


def _table(pg, sc, th):
    t = sc["table"]
    x0, y0, rh = t["x"], t["y"], t["row_h"]
    cx = x0
    for ci, (title, key, w) in enumerate(t["cols"]):
        pg.vertex(f"th{ci}", f"<b>{hesc(title)}</b>",
                  {"html": 1, "whiteSpace": "wrap", "fillColor": "#E4E7EB", "strokeColor": "#9AA5B1", "align": "left",
                   "spacingLeft": 6, "fontSize": L.FONT_TABLE, "fontFamily": th["font"], "fontColor": _h(th["text"])},
                  cx, y0, w, rh)
        for r, row in enumerate(t["rows"]):
            pg.vertex(f"td{r}_{ci}", hesc(str(row[key])),
                      {"html": 1, "whiteSpace": "wrap", "fillColor": "#F5F7FA" if r % 2 else "#FFFFFF",
                       "strokeColor": "#CBD2D9", "align": "left", "spacingLeft": 6, "fontSize": L.FONT_TABLE,
                       "fontFamily": th["font"], "fontColor": _h(th["text"])},
                      cx, y0 + rh * (r + 1), w, rh)
        cx += w


def write(scenes, path):
    mx = ET.Element("mxfile", host="technical-architecture-diagram", agent="tad 0.1", version="24.0.0", type="device")
    for sc in scenes:
        mx.append(page_from_scene(sc))
    tree = ET.ElementTree(mx)
    ET.indent(tree, space=" ")
    # ElementTree writes bare style keys like "text;" fine because styles are pre-joined strings.
    tree.write(path, encoding="utf-8", xml_declaration=True)
