"""Small geometry helpers shared by renderers and checks."""
import math


def arrowhead(p_from, p_tip, kind, size=9):
    """Polygon points for an arrowhead at p_tip pointing away from p_from.

    Returns (points, filled) or None. Diamonds are drawn with their tip at p_tip.
    """
    if kind in (None, "none"):
        return None
    dx, dy = p_tip[0] - p_from[0], p_tip[1] - p_from[1]
    d = math.hypot(dx, dy) or 1.0
    ux, uy = dx / d, dy / d
    px, py = -uy, ux
    tx, ty = p_tip
    if kind in ("arrow", "open", "triangle"):
        s = size if kind != "triangle" else size + 3
        w = s * (0.45 if kind != "triangle" else 0.6)
        bx, by = tx - ux * s, ty - uy * s
        pts = [(tx, ty), (bx + px * w, by + py * w), (bx - px * w, by - py * w)]
        return pts, (kind == "arrow"), (kind == "open")
    if kind in ("diamond", "odiamond"):
        s = size + 5
        w = size * 0.5
        mx, my = tx - ux * s / 2, ty - uy * s / 2
        bx, by = tx - ux * s, ty - uy * s
        pts = [(tx, ty), (mx + px * w, my + py * w), (bx, by), (mx - px * w, my - py * w)]
        return pts, (kind == "diamond"), False
    return None


def head_setback(kind, size=9):
    """How far the line must stop short of the tip so it does not poke through hollow heads."""
    if kind == "triangle":
        return size + 3
    if kind in ("diamond", "odiamond"):
        return size + 5
    if kind == "arrow":
        return size * 0.6
    return 0


def shorten(points, start_by, end_by):
    pts = list(points)
    if len(pts) < 2:
        return pts

    def move(a, b, by):
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        if d <= by or d == 0:
            return a
        return (a[0] + dx / d * by, a[1] + dy / d * by)
    if start_by:
        pts[0] = move(pts[0], pts[1], start_by)
    if end_by:
        pts[-1] = move(pts[-1], pts[-2], end_by)
    return pts


def segs(points):
    return list(zip(points[:-1], points[1:]))


def rect_hit_segment(r, a, b, shrink=2.0):
    """True if segment a-b passes through the interior of rect r=(x,y,w,h)."""
    x, y, w, h = r
    x0, y0, x1, y1 = x + shrink, y + shrink, x + w - shrink, y + h - shrink
    if x1 <= x0 or y1 <= y0:
        return False
    # Liang-Barsky clip
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                if t > t1:
                    return False
                t0 = max(t0, t)
            else:
                if t < t0:
                    return False
                t1 = min(t1, t)
    return t1 - t0 > 1e-6


def rect_overlap(a, b, pad=0.0):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = min(ax + aw, bx + bw) - max(ax, bx) - pad
    iy = min(ay + ah, by + bh) - max(ay, by) - pad
    return ix > 0 and iy > 0, max(0, ix) * max(0, iy)


def seg_cross(a, b, c, d):
    """Proper crossing of two axis-aligned-ish segments (shared endpoints do not count)."""
    def orient(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return o1 * o2 < 0 and o3 * o4 < 0


def path_length(points):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs(points))


def nearest_on_path(points, c):
    """(t in [0,1] along the path, nearest point) for point c."""
    total = path_length(points) or 1.0
    best, acc = None, 0.0
    for a, b in segs(points):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((c[0] - a[0]) * dx + (c[1] - a[1]) * dy) / L2))
        q = (a[0] + u * dx, a[1] + u * dy)
        dist = math.hypot(c[0] - q[0], c[1] - q[1])
        seglen = math.sqrt(L2)
        if best is None or dist < best[0]:
            best = (dist, (acc + u * seglen) / total, q)
        acc += seglen
    return best[1], best[2]
