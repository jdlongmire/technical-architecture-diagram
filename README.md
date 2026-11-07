# Technical Architecture Diagram

Make dense, editable technical diagrams as draw.io files from a small JSON spec:

- **Network / deployment:** sites, zones and enclaves nested to any depth; firewalls, servers and links with addresses, protocols and ports.
- **Interface (ICD-style):** units with named ports on fixed sides, auto-numbered interfaces, and a generated interface table page.
- **Data flow:** processes, stores, external entities and actors across trust and classification boundaries; flows that cross a boundary are highlighted automatically.
- **SysML-style block definition:** blocks with compartments, composition, aggregation, generalization and dependency.
- **SysML-style internal block:** parts, ports, item flows, connectors and bindings.

One spec can produce several **views** (pages): a full view, summaries with containers collapsed, or pages filtered by edge type.

Layout is done by the Eclipse Layout Kernel (ELK), which handles nested containers, ports and orthogonal edge routing. Edge labels are placed in free space after layout, and only labels that find no room are handed back to ELK, which keeps diagrams compact. Edges that close a loop are laid out reversed so the main flow stays one-directional, with arrowheads still showing the real direction.

Output is an uncompressed `.drawio` file in which every container, node, port and edge is a native draw.io cell, so the diagram stays editable and edges stay attached. Previews (PNG, SVG) and PDF are rendered from the same layout. A checker measures the drawn geometry (lines through boxes, overlapping labels, crossings, density, page fit) and the content (lengths, placeholders, broken references), and reports each problem with a path into the spec and an exact fix.

Start with `SKILL.md`. It walks through the workflow: pick a template, fill it in, build, fix, deliver.

## Quick start

```
pip install -r requirements.txt          # Pillow, cairosvg, pypdf; Node.js 16+ is also required
python3 scripts/make_tad.py examples/payload_interfaces.json --out payload.drawio --png preview.png --pdf payload.pdf
python3 scripts/make_tad.py --limits     # every enforced limit, edge type, container type and shape
```

## Layout of this repository

| Path | Contents |
|---|---|
| `SKILL.md` | Entry point and workflow. |
| `scripts/make_tad.py` | The command. |
| `scripts/tad/` | Spec normalizer, ELK layout, draw.io writer, SVG renderer, checks. |
| `scripts/tad/limits.py` | Every enforced limit, in one place. |
| `scripts/gen_reference.py` | Regenerates `reference/limits.md` from the code. |
| `scripts/vendor/` | Bundled elkjs (EPL-2.0). |
| `templates/` | One fill-in spec per kind. |
| `examples/` | Finished specs with `.drawio` files and previews. |
| `reference/` | Spec fields, limits and vocabulary, report messages. |

## Notes

- Classification markings are drawn exactly as supplied. The tool does not determine, check or validate classification; marking decisions stay with the author and the responsible authority.
- All example content is fictional.

## Author

James D. (JD) Longmire\
Senior Technical Fellow, Aerospace and Defense Sector\
Independent Researcher\
ORCID: 0009-0009-1383-7698\
Correspondence: jd.longmire@ologos.co

## License

MIT License; see `LICENSE`. Third-party components (elkjs under EPL-2.0, Lucide icons under ISC) keep their own licenses; see `THIRD-PARTY-LICENSES.md`.
