#!/usr/bin/env python3
"""Build a dense technical diagram (.drawio + previews) from a JSON spec.

Usage:
  python3 scripts/make_tad.py spec.json --out Name.drawio [--png preview.png] [--svg preview.svg]
                              [--pdf Name.pdf] [--renderer builtin|drawio]
  python3 scripts/make_tad.py spec.json --dry-run      # validate and report limits; builds nothing
  python3 scripts/make_tad.py --limits [--kind network] # print every enforced limit

The first line of the report is RESULT: PASS, FIX, or INVALID.
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tad import __version__  # noqa: E402
from tad import checks as C  # noqa: E402
from tad import drawio as D  # noqa: E402
from tad import layout as LY  # noqa: E402
from tad import limits as L  # noqa: E402
from tad import render as R  # noqa: E402
from tad import spec as SP  # noqa: E402
from tad import styles as S  # noqa: E402
from tad import svg as SV  # noqa: E402
from tad import text as T  # noqa: E402


def print_limits(kind=None):
    print("LIMITS (enforced by the checker; boxes grow to fit, so these do not depend on layout)")
    for name, val, meaning in L.as_table():
        print(f"  {name:28s} {str(val):>6s}  {meaning}")
    kinds = [kind] if kind else list(S.KINDS)
    for k in kinds:
        print(f"\nKIND {k}: direction {S.DEFAULT_DIRECTION[k]}, default shape {S.DEFAULT_SHAPE[k]}, "
              f"default container {S.DEFAULT_CONTAINER_TYPE[k]}")
        print("  edge types: " + ", ".join(f"{n} ({v['label']})" for n, v in S.EDGE_TYPES[k].items()))
    print("\ncontainer types: " + ", ".join(S.CONTAINER_TYPES))
    print("node shapes: " + ", ".join(S.NODE_SHAPES))
    print("page sizes: " + ", ".join(S.PAGE_SIZES))


def dedupe(issues):
    seen, out = set(), []
    for i in issues:
        k = (i["level"], i["path"], i["msg"])
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out


def fmt_issue(n, i):
    s = f"  {n}. [{i['level']}] {i['path']}: {i['msg']}."
    if i.get("fix"):
        s += f" FIX: {i['fix']}."
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?")
    ap.add_argument("--out", help="output .drawio file")
    ap.add_argument("--png", help="preview PNG base name (one file per page: name-1.png, ...)")
    ap.add_argument("--svg", help="preview SVG base name (one file per page)")
    ap.add_argument("--pdf", help="PDF file (one page per view)")
    ap.add_argument("--renderer", choices=["builtin", "drawio"], default="builtin",
                    help="how PNG/PDF are rendered: builtin (default) or the draw.io desktop CLI")
    ap.add_argument("--dry-run", action="store_true", help="validate and report; build nothing")
    ap.add_argument("--limits", action="store_true", help="print every enforced limit and exit")
    ap.add_argument("--kind", help="with --limits: show one kind")
    ap.add_argument("--version", action="version", version=f"tad {__version__}")
    a = ap.parse_args(argv)

    if a.limits:
        print_limits(a.kind)
        return 0
    if not a.spec:
        ap.error("spec is required")
    if not a.out and not a.dry_run:
        stem = os.path.splitext(os.path.basename(a.spec))[0].replace(".normalized", "")
        a.out = stem + ".drawio"

    report = {"result": None, "issues": [], "autofixes": [], "outputs": {}, "views": []}

    try:
        raw = SP.load(a.spec)
        spec, fixes, issues = SP.normalize(raw)
    except SP.SpecError as e:
        print("RESULT: INVALID")
        print(f"  1. [INVALID] spec: {e}. FIX: correct the JSON and rerun.")
        return 2

    # Clean spec (edit this one during the fix loop)
    base = a.spec[:-len(".normalized.json")] if a.spec.endswith(".normalized.json") else os.path.splitext(a.spec)[0]
    clean_path = base + ".normalized.json"
    with open(clean_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
    with open(clean_path, "rb") as f:
        report["spec_sha256"] = hashlib.sha256(f.read()).hexdigest()
    report["tool_version"] = __version__
    report["provenance"] = spec.get("provenance", "light")
    report["provenance_default"] = bool(spec.get("provenance_default"))
    report["title_block"] = bool(spec.get("title_block"))

    issues += SP.content_checks(spec)
    if not T.font_available():
        issues.append(SP.issue("INFO", "fonts", "Liberation Sans / Arial not found; text widths are estimated"))

    if any(i["level"] == "INVALID" for i in issues):
        _print(report, "INVALID", None, clean_path, fixes, dedupe(issues), None)
        return 2

    if a.dry_run:
        views = spec.get("views") or [None]
        print("RESULT: DRY-RUN")
        print(f"CLEAN SPEC: {clean_path}")
        print(f"KIND: {spec['kind']}  DIRECTION: {spec['direction']}  PAGE: {spec['page']}")
        print(f"PROVENANCE: {spec.get('provenance', 'light')}"
              + (" (default for kind)" if spec.get("provenance_default") else ""))
        for v in views:
            c, n, e = LY.select(spec, v)
            print(f"VIEW {(v or {}).get('name', 'Overview')!r}: {len(n)} nodes, {len(c)} containers, {len(e)} edges "
                  f"(warn above {L.NODES_PER_VIEW_WARN} nodes, FIX above {L.NODES_PER_VIEW_MAX})")
        print()
        print_limits(spec["kind"])
        iss = dedupe(issues + C.spec_checks(spec))
        acts = [i for i in iss if i["level"] in ("ERROR", "WARNING")]
        if acts:
            print("\nNEXT ACTIONS (before building):")
            for k, i in enumerate(acts, 1):
                print(fmt_issue(k, i))
        return 0

    issues += C.spec_checks(spec)
    views = spec.get("views") or [None]
    total_pages = len(views) + (1 if spec.get("interface_table") and spec["edges"] else 0)
    scenes = []
    try:
        for vi, v in enumerate(views):
            spec["_sheet"] = f"{vi + 1} of {total_pages}"
            sc = LY.layout_view(spec, v, issues, "" if vi == 0 else "v")
            issues += C.scene_checks(sc, spec, len(views) > 1)
            scenes.append(sc)
            report["views"].append({"name": sc["name"], "nodes": len(sc["nodes"]), "edges": len(sc["edges"]),
                                    "crossings": sc.get("_crossings"), "size": [sc["width"], sc["height"]]})
    except LY.LayoutError as e:
        issues.append(SP.issue("INVALID", "layout", str(e), "check that Node.js 16+ is installed"))
        _print(report, "INVALID", None, clean_path, fixes, dedupe(issues), None)
        return 2
    if spec.get("interface_table") and spec["edges"]:
        spec["_sheet"] = f"{total_pages} of {total_pages}"
        scenes.append(LY.table_scene(spec, scenes[0]))

    D.write(scenes, a.out)
    report["outputs"]["drawio"] = a.out
    extras = []

    svgs = [SV.render(sc) for sc in scenes]
    if a.svg:
        sb = os.path.splitext(a.svg)[0]
        for k, s in enumerate(svgs, 1):
            p = f"{sb}-{k}.svg"
            with open(p, "w", encoding="utf-8") as f:
                f.write(s)
            extras.append(("SVG", p))
    if a.png:
        pb = os.path.splitext(a.png)[0]
        for k, s in enumerate(svgs, 1):
            p = f"{pb}-{k}.png"
            try:
                if a.renderer == "drawio":
                    R.drawio_export(os.path.abspath(a.out), os.path.abspath(p), "png", page_index=k, scale=1.5)
                else:
                    R.builtin_png(s, p)
                extras.append(("PREVIEW", p))
            except Exception as ex:  # noqa: BLE001
                issues.append(SP.issue("INFO", "png", f"PNG export failed: {ex}"))
    if a.pdf:
        try:
            if a.renderer == "drawio":
                R.drawio_export(os.path.abspath(a.out), os.path.abspath(a.pdf), "pdf", all_pages=True)
            else:
                R.builtin_pdf([(s, sc["width"], sc["height"]) for s, sc in zip(svgs, scenes)], a.pdf, spec["page"])
            extras.append(("PDF", a.pdf))
        except Exception as ex:  # noqa: BLE001
            issues.append(SP.issue("INFO", "pdf", f"PDF export failed: {ex}"))

    issues = dedupe(issues)
    result = "FIX" if any(i["level"] == "ERROR" for i in issues) else "PASS"
    _print(report, result, a.out, clean_path, fixes, issues, extras)
    rp = os.path.splitext(a.out)[0] + ".report.json"
    report.update(result=result, issues=issues, autofixes=fixes, clean_spec=clean_path,
                  outputs=dict(report["outputs"], extras=[{"type": t, "path": p} for t, p in extras]))
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"REPORT: {rp}")
    return 0 if result == "PASS" else 1


def _print(report, result, out, clean, fixes, issues, extras):
    print(f"RESULT: {result}")
    if out:
        print(f"OUTPUT: {out}")
    for t, p in extras or []:
        print(f"{t}: {p}")
    print(f"CLEAN SPEC: {clean}")
    if report.get("provenance"):
        print(f"PROVENANCE: {report['provenance']}"
              + (" (default for kind)" if report.get("provenance_default") else "")
              + f"  TITLE BLOCK: {'on' if report.get('title_block') else 'off'}"
              + f"  TOOL: tad {report.get('tool_version', '')}  SPEC SHA256: {report.get('spec_sha256', '')[:16]}...")
    for v in report["views"]:
        print(f"VIEW {v['name']!r}: {v['nodes']} nodes, {v['edges']} edges, {v['crossings']} crossings, "
              f"{v['size'][0]}x{v['size'][1]} px")
    if fixes:
        print(f"AUTO-FIXES APPLIED ({len(fixes)}):")
        for f in fixes[:25]:
            print(f"  - {f}")
        if len(fixes) > 25:
            print(f"  - ... {len(fixes) - 25} more in the report")
    acts = [i for i in issues if i["level"] in ("INVALID", "ERROR", "WARNING")]
    notes = [i for i in issues if i["level"] == "INFO"]
    if acts:
        print("NEXT ACTIONS (do all ERROR items, then rerun on the clean spec):")
        acts.sort(key=lambda i: {"INVALID": 0, "ERROR": 1, "WARNING": 2}[i["level"]])
        for k, i in enumerate(acts, 1):
            print(fmt_issue(k, i))
    if notes:
        print("NOTES (no action required):")
        for i in notes:
            print(f"  - {i['path']}: {i['msg']}")


if __name__ == "__main__":
    sys.exit(main())
