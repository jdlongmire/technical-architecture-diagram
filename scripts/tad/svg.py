"""Render a scene to SVG (preview, PNG and PDF are made from this)."""
import json
import os
from xml.sax.saxutils import escape

from . import limits as L
from . import styles as S
from . import text as T
from .geom import arrowhead, head_setback, shorten
from .layout import BANNER_H, MARGIN, ICON, PAD_X, PAD_Y, HEADER_H

FONT = "Liberation Sans, Arial, Helvetica, sans-serif"
_ICONS = None


def icons():
    global _ICONS
    if _ICONS is None:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons.json")
        try:
            with open(p, encoding="utf-8") as f:
                _ICONS = json.load(f)
        except OSError:
            _ICONS = {}
    return _ICONS


def icon_markup(name):
    ic = icons()
    key = str(name).lower().strip()
    return ic.get(key) or ic.get(key.replace(" ", "-")) or ic.get(key.split("-")[0])


def _c(h):
    return "none" if h in (None, "none") else "#" + str(h).lstrip("#")


def _dash(d, w):
    if d == "dashed":
        return f' stroke-dasharray="{round(6 + w * 2)},{round(4 + w)}"'
    if d == "dotted":
        return f' stroke-dasharray="{max(1.5, w)},{round(3 + w)}" stroke-linecap="round"'
    return ""


def _text(x, y, s, size, color, bold=False, italic=False, anchor="start"):
    attrs = f'x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{_c(color)}" text-anchor="{anchor}"'
    if bold:
        attrs += ' font-weight="bold"'
    if italic:
        attrs += ' font-style="italic"'
    return f'<text {attrs}>{escape(str(s))}</text>'


def render(sc):
    th = sc["theme"]
    W, H = sc["width"], sc["height"]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="{FONT}">', f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>']

    y0 = MARGIN
    if sc.get("marking"):
        bg, fg = S.marking_colors(sc["marking"])
        for by in (8, H - 8 - BANNER_H):
            o.append(f'<rect x="0" y="{by}" width="{W}" height="{BANNER_H}" fill="{_c(bg)}"/>')
            o.append(_text(W / 2, by + BANNER_H / 2 + L.FONT_BANNER * 0.36, sc["marking"].upper(),
                           L.FONT_BANNER, fg, bold=True, anchor="middle"))
        y0 += BANNER_H + 8 - 8
    o.append(_text(MARGIN, y0 + L.FONT_TITLE, sc["title"], L.FONT_TITLE, th["title"], bold=True))
    yy = y0 + L.FONT_TITLE + 10
    if sc.get("subtitle"):
        o.append(_text(MARGIN, yy + L.FONT_SUBTITLE, sc["subtitle"], L.FONT_SUBTITLE, th["muted"]))
    o.append(_text(W - MARGIN, y0 + L.FONT_TITLE, "View: " + sc["name"], 11, th["muted"], anchor="end"))

    if sc.get("table"):
        o += _table(sc, th)
        o.append("</svg>")
        return "\n".join(o)

    # Containers
    for c in sc["containers"]:
        w = c["width"]
        o.append(f'<rect x="{c["x"]:.1f}" y="{c["y"]:.1f}" width="{c["w"]:.1f}" height="{c["h"]:.1f}" rx="4" '
                 f'fill="{_c(c["fill"])}" stroke="{_c(c["stroke"])}" stroke-width="{w}"{_dash(c["dash"], w)}/>')
        tx = c["x"] + 12
        ty = c["y"] + 20
        if c.get("stereotype"):
            st = "«" + c["stereotype"] + "» "
            o.append(_text(tx, ty, st, L.FONT_STEREO, th["muted"], italic=True))
            tx += T.width(st, L.FONT_STEREO, italic=True)
        o.append(_text(tx, ty, c["label"], L.FONT_CONTAINER, th["text"], bold=True))
        if c.get("marking"):
            bg, fg = S.marking_colors(c["marking"])
            bw = T.width(c["marking"], 9, bold=True) + 12
            bx = c["x"] + c["w"] - bw - 8
            o.append(f'<rect x="{bx:.1f}" y="{c["y"] + 7:.1f}" width="{bw:.1f}" height="16" rx="3" fill="{_c(bg)}"/>')
            o.append(_text(bx + bw / 2, c["y"] + 18.5, c["marking"].upper(), 9, fg, bold=True, anchor="middle"))

    # Edges (lines and heads)
    for e in sc["edges"]:
        o += _edge(e, th)

    # Nodes
    for n in sc["nodes"]:
        o += _node(n, th)

    # Edge labels on top
    for e in sc["edges"]:
        if e.get("label_box") and e["lines"]:
            x, y, w, h = e["label_box"]
            o.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2" fill="#FFFFFF" '
                     f'fill-opacity="0.94"/>')
            lh = T.line_height(L.FONT_EDGE)
            col = th["text"]
            for i, ln in enumerate(e["lines"]):
                o.append(_text(x + w / 2, y + 2 + lh * (i + 0.78), ln, L.FONT_EDGE, col, anchor="middle"))

    if sc.get("legend"):
        o += _legend(sc["legend"], th)
    o.append("</svg>")
    return "\n".join(o)


def _edge(e, th):
    st = e["style"]
    col = S.resolve_color(st.get("color", "edge"), th)
    w = st.get("width", 1.5)
    pts = e["points"]
    if len(pts) < 2:
        return []
    ps = shorten(pts, head_setback(st.get("start")), head_setback(st.get("end")))
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in ps)
    out = [f'<polyline points="{path}" fill="none" stroke="{_c(col)}" stroke-width="{w}" '
           f'stroke-linejoin="round"{_dash(st.get("dash"), w)}/>']
    for kind, tip, frm in ((st.get("end"), pts[-1], pts[-2]), (st.get("start"), pts[0], pts[1])):
        ah = arrowhead(frm, tip, kind)
        if not ah:
            continue
        poly, filled, open_v = ah
        pp = " ".join(f"{x:.1f},{y:.1f}" for x, y in poly)
        if open_v:
            a, b, c = poly
            out.append(f'<polyline points="{b[0]:.1f},{b[1]:.1f} {a[0]:.1f},{a[1]:.1f} {c[0]:.1f},{c[1]:.1f}" '
                       f'fill="none" stroke="{_c(col)}" stroke-width="{w}"/>')
        else:
            out.append(f'<polygon points="{pp}" fill="{_c(col) if filled else "#FFFFFF"}" stroke="{_c(col)}" '
                       f'stroke-width="{max(1, w * 0.8)}" stroke-linejoin="round"/>')
    return out


def _node(n, th):
    x, y, w, h = n["x"], n["y"], n["w"], n["h"]
    fill, stroke = _c(th["node_fill"]), _c(th["node_stroke"])
    sh = n["shape"]
    o = []
    sw = 1.25
    if sh == "cylinder":
        ry = 7
        o.append(f'<path d="M{x},{y + ry} A{w / 2},{ry} 0 0 1 {x + w},{y + ry} V{y + h - ry} '
                 f'A{w / 2},{ry} 0 0 1 {x},{y + h - ry} Z" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
        o.append(f'<path d="M{x},{y + ry} A{w / 2},{ry} 0 0 0 {x + w},{y + ry}" fill="none" stroke="{stroke}" '
                 f'stroke-width="{sw}"/>')
    elif sh == "store":
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="none"/>')
        o.append(f'<path d="M{x + w},{y} H{x} V{y + h} H{x + w} V{y}" fill="none" stroke="{stroke}" stroke-width="1.5"/>')
    elif sh == "actor":
        cx = x + w / 2
        o.append(f'<circle cx="{cx}" cy="{y + 7}" r="6" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
        o.append(f'<path d="M{cx},{y + 13} V{y + 29} M{cx - 11},{y + 19} H{cx + 11} M{cx},{y + 29} L{cx - 9},{y + 40} '
                 f'M{cx},{y + 29} L{cx + 9},{y + 40}" fill="none" stroke="{stroke}" stroke-width="{sw}"/>')
    elif sh == "note":
        f = 10
        o.append(f'<path d="M{x},{y} H{x + w - f} L{x + w},{y + f} V{y + h} H{x} Z" fill="#FFFBEA" stroke="{stroke}" '
                 f'stroke-width="{sw}"/>')
        o.append(f'<path d="M{x + w - f},{y} V{y + f} H{x + w}" fill="none" stroke="{stroke}" stroke-width="{sw}"/>')
    else:
        rx = {"rounded": 8, "process": 16}.get(sh, 2)
        swd = 2.5 if sh == "external" else sw
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" '
                 f'stroke-width="{swd}"/>')
        if n.get("collapsed"):
            o.append(f'<rect x="{x + 3}" y="{y + 3}" width="{w - 6}" height="{h - 6}" rx="{max(0, rx - 2)}" '
                     f'fill="none" stroke="{stroke}" stroke-width="0.75"/>')

    icon_w = ICON + 6 if n.get("icon") else 0
    if n["comps"]:
        cy = y + PAD_Y + (16 if sh == "cylinder" else 0)
    elif sh == "cylinder":
        cy = y + 14 + (h - 14 - n["text_h"]) / 2
    else:
        cy = y + (h - n["text_h"]) / 2
    if sh == "actor":
        cy = y + 44
    if n.get("icon"):
        mk = icon_markup(n["icon"])
        if mk:
            iy = cy + max(0, (n["text_h"] - ICON) / 2)
            o.append(f'<g transform="translate({x + PAD_X:.1f},{iy:.1f}) scale({ICON / 24})" fill="none" '
                     f'stroke="{_c(th["accent"])}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                     f'{mk}</g>')
    cx = x + icon_w + (w - icon_w) / 2
    for (s, size, bold, italic, colkey, _align) in n["blocks"]:
        lh = T.line_height(size)
        o.append(_text(cx, cy + lh * 0.78, s, size, th[colkey], bold=bold, italic=italic, anchor="middle"))
        cy += lh
    if n["comps"]:
        cy += PAD_Y - 2
        for cname, lines in n["comps"]:
            o.append(f'<line x1="{x}" y1="{cy:.1f}" x2="{x + w}" y2="{cy:.1f}" stroke="{stroke}" stroke-width="1"/>')
            cy += 3
            lh = T.line_height(L.FONT_ATTR - 1)
            o.append(_text(x + w / 2, cy + lh * 0.78, cname, L.FONT_ATTR - 1, th["muted"], italic=True,
                           anchor="middle"))
            cy += lh
            for ln in lines:
                lh2 = T.line_height(L.FONT_ATTR)
                o.append(_text(x + PAD_X, cy + lh2 * 0.78, ln, L.FONT_ATTR, th["text"]))
                cy += lh2
            cy += 3
    for p in n["ports"]:
        o.append(f'<rect x="{p["x"]:.1f}" y="{p["y"]:.1f}" width="{p["w"]}" height="{p["h"]}" '
                 f'fill="{_c(th["port"])}"/>')
        lx, ly, lw, lh = p["label_box"]
        o.append(_text(lx + (lw if p["side"] == "WEST" else 0), ly + lh * 0.8, p["label"], L.FONT_PORT, th["muted"],
                       anchor="end" if p["side"] == "WEST" else "start"))
    return o


def _legend(lg, th):
    x, y = lg["x"], lg["y"]
    o = [f'<rect x="{x}" y="{y}" width="{lg["w"]}" height="{lg["h"]}" rx="3" fill="#FFFFFF" stroke="#CBD2D9"/>',
         _text(x + 8, y + 17, "Legend", 11, th["text"], bold=True)]
    for it in lg["items"]:
        ix, iy = x + it["dx"], y + it["dy"]
        mid = iy + lg["row_h"] / 2
        if it["kind"] == "edge":
            st = it["ref"]
            fake = dict(style=st, points=[(ix + 2, mid), (ix + 40, mid)])
            o += _edge(fake, th)
        elif it["kind"] == "container":
            c = it["ref"]
            o.append(f'<rect x="{ix + 4}" y="{mid - 6}" width="32" height="12" rx="2" fill="{_c(c["fill"])}" '
                     f'stroke="{_c(c["stroke"])}" stroke-width="{min(c["width"], 2)}"{_dash(c["dash"], 1.2)}/>')
        elif it["kind"] == "port":
            o.append(f'<rect x="{ix + 16}" y="{mid - 4}" width="8" height="8" fill="{_c(th["port"])}"/>')
        elif it["kind"] == "collapsed":
            o.append(f'<rect x="{ix + 4}" y="{mid - 7}" width="32" height="14" rx="2" fill="#FFFFFF" '
                     f'stroke="{_c(th["node_stroke"])}"/><rect x="{ix + 6}" y="{mid - 5}" width="28" height="10" '
                     f'fill="none" stroke="{_c(th["node_stroke"])}" stroke-width="0.75"/>')
        o.append(_text(ix + 48, mid + L.FONT_LEGEND * 0.36, it["label"], L.FONT_LEGEND, th["text"]))
    return o


def _table(sc, th):
    t = sc["table"]
    o = []
    x0, y0, rh = t["x"], t["y"], t["row_h"]
    o.append(f'<rect x="{x0}" y="{y0}" width="{t["w"]}" height="{rh}" fill="#E4E7EB"/>')
    for r in range(len(t["rows"])):
        if r % 2 == 1:
            o.append(f'<rect x="{x0}" y="{y0 + rh * (r + 1)}" width="{t["w"]}" height="{rh}" fill="#F5F7FA"/>')
    cx = x0
    for title, key, w in t["cols"]:
        o.append(_text(cx + 8, y0 + rh * 0.68, title, L.FONT_TABLE, th["text"], bold=True))
        for r, row in enumerate(t["rows"]):
            val = str(row[key])
            while val and T.width(val, L.FONT_TABLE) > w - 12:
                val = val[:-2] + "…" if len(val) > 2 else ""
                val = val.replace("……", "…")
            o.append(_text(cx + 8, y0 + rh * (r + 1) + rh * 0.68, val, L.FONT_TABLE, th["text"]))
        cx += w
    o.append(f'<rect x="{x0}" y="{y0}" width="{t["w"]}" height="{t["h"]}" fill="none" stroke="#9AA5B1"/>')
    cx = x0
    for _, _, w in t["cols"][:-1]:
        cx += w
        o.append(f'<line x1="{cx}" y1="{y0}" x2="{cx}" y2="{y0 + t["h"]}" stroke="#CBD2D9"/>')
    for r in range(1, len(t["rows"]) + 1):
        o.append(f'<line x1="{x0}" y1="{y0 + rh * r}" x2="{x0 + t["w"]}" y2="{y0 + rh * r}" stroke="#CBD2D9"/>')
    return o
