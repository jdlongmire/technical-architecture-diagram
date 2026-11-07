"""Raster/PDF export: built-in (SVG -> cairosvg) or the draw.io desktop CLI."""
import io
import os
import shutil
import subprocess

from . import styles as S


def builtin_png(svg_text, path, scale=1.5):
    import cairosvg
    cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), write_to=path, scale=scale)


def builtin_pdf(svgs_and_sizes, path, page="auto"):
    """svgs_and_sizes: list of (svg_text, w, h). One PDF page per scene."""
    import cairosvg
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter()
    ps = S.PAGE_SIZES.get(page)
    for svg, w, h in svgs_and_sizes:
        if ps:
            pw, ph = ps
            if h > w and pw > ph:
                pass  # keep landscape; content is scaled to fit
            s = min(pw / w, ph / h, 1.0)
            ox, oy = (pw - w * s) / 2, (ph - h * s) / 2
            inner = svg.split(">", 1)[1].rsplit("</svg>", 1)[0]
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{pw}" height="{ph}" viewBox="0 0 {pw} {ph}">'
                   f'<rect width="{pw}" height="{ph}" fill="#FFFFFF"/>'
                   f'<svg x="{ox:.1f}" y="{oy:.1f}" width="{w * s:.1f}" height="{h * s:.1f}" viewBox="0 0 {w} {h}">'
                   f'{inner}</svg></svg>')
        buf = io.BytesIO()
        cairosvg.svg2pdf(bytestring=svg.encode("utf-8"), write_to=buf, dpi=100)
        buf.seek(0)
        for p in PdfReader(buf).pages:
            writer.add_page(p)
    with open(path, "wb") as f:
        writer.write(f)


def find_drawio():
    for c in ("drawio", "draw.io", "/opt/drawio/drawio",
              "/Applications/draw.io.app/Contents/MacOS/draw.io",
              "C:/Program Files/draw.io/draw.io.exe"):
        p = shutil.which(c) or (c if os.path.exists(c) else None)
        if p:
            return p
    return None


def drawio_export(drawio_file, out, fmt, page_index=None, all_pages=False, scale=None):
    exe = find_drawio()
    if not exe:
        raise RuntimeError("draw.io desktop not found (install it or use --renderer builtin)")
    cmd = [exe, "--no-sandbox", "-x", "-f", fmt]
    if all_pages:
        cmd += ["-a"]
    if page_index is not None:
        cmd += ["-p", str(page_index)]
    if scale:
        cmd += ["--scale", str(scale)]
    cmd += ["-o", out, drawio_file, "--disable-gpu"]
    if os.name == "posix" and not os.environ.get("DISPLAY") and shutil.which("xvfb-run") and \
            not exe.startswith("/Applications"):
        cmd = ["xvfb-run", "-a"] + cmd
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if not os.path.exists(out):
        raise RuntimeError("draw.io export failed: " + (r.stderr.strip().splitlines() or ["no output"])[-1])
