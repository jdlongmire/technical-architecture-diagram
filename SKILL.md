---
name: technical-architecture-diagram
description: Make dense, editable technical diagrams as draw.io files (network/deployment, interface/ICD with an interface table, data flow with trust and classification boundaries, SysML-style block definition and internal block diagrams). Use when the user wants a detailed engineering diagram with many components, containers, ports, protocols or interfaces, or asks for draw.io output.
---

# Technical Architecture Diagram

You write a JSON **spec** describing the model. A script lays it out with ELK (the Eclipse Layout Kernel), writes an editable `.drawio` file, renders previews, and reports exactly what to fix. **You never place shapes or choose coordinates.**

For a slide-style overview with a handful of boxes, the `enterprise-architecture-diagram` skill (PowerPoint) is the better fit. This skill is for dense engineering diagrams: dozens of nodes, nested boundaries, named ports, protocol labels, interface tables, several views of one model.

Everything is in this folder:
- `scripts/make_tad.py` is the only command you run.
- `templates/` has one fill-in spec per kind. Always start from one.
- `examples/` has finished specs with their `.drawio` files and preview images.
- `reference/spec_reference.md` lists every field. `reference/limits.md` lists every limit and vocabulary word. `reference/report_guide.md` explains every report message.

Requirements: Python 3 with `pip install -r requirements.txt` (Pillow, cairosvg, pypdf) and Node.js 16 or newer. ELK is bundled, so no npm install is needed. Optional: the draw.io desktop app, for `--renderer drawio`.

---

## Step 1: Choose the template

| The user wants... | Template | kind |
|---|---|---|
| Servers, networks, zones, sites, firewalls, links, deployment | `templates/network.json` | `network` |
| Interfaces between units: ports, signals, protocols, an ICD table | `templates/interface.json` | `interface` |
| How data moves across trust or classification boundaries (security review) | `templates/dataflow.json` | `dataflow` |
| System structure: what is part of what, what is a kind of what | `templates/bdd.json` | `bdd` |
| Parts inside one block, their ports and item flows | `templates/ibd.json` | `ibd` |

## Step 2: Fill the template

Copy the template (for example to `spec.json`) and replace every `<<...>>` with content from the user's request.

**Rules:**
1. Use only facts the user gave or clearly implied. Do not invent addresses, part numbers, protocols, vendors or markings.
2. **Markings:** set `marking` only when the user gives one. The tool draws markings as written and does not determine classification.
3. **Order matters.** List containers and nodes roughly in the order the flow runs (inputs first), and write each edge in the direction the flow starts. The layout follows spec order.
4. **Two-way links:** use one edge with a two-way type (`tunnel`, `bidir`), not two opposite edges.
5. **Ports:** when interfaces matter, give nodes named ports with sides (`"CMD:E"`) and connect `"node.PORT"` to `"node.PORT"`. Put output ports on the side facing where the flow goes.
6. **Containers vs nodes:** things with children go in `containers`; components go in `nodes`. Ids may be omitted (derived from labels); edges may reference labels.
7. **Labels:** short and specific. An edge label has at most three lines: label, data, protocol/port. Put long detail in the interface table rather than on the line.
8. **Delete** template items you have no content for. Never leave `<<...>>`.
9. **Density:** more than about 40 nodes on one page gets hard to read. Add `views`: a full view plus summary views that `collapse` containers, filter `edge_types`, or `include` one area.

Before the first build, check the spec and see the limits:
```
python3 scripts/make_tad.py spec.json --dry-run
```

## Step 3: Build

```
python3 scripts/make_tad.py spec.json --out <Topic>.drawio --png preview.png
```

Add `--pdf <Topic>.pdf` for a PDF (one page per view) and `--svg preview.svg` for SVGs. `--renderer drawio` renders PNG/PDF with the draw.io desktop app instead of the built-in renderer.

The `.drawio` file holds one page per view (plus an Interfaces page when there is an interface table). Containers, nodes, ports and edges are native draw.io cells: nodes sit inside their containers, ports inside their nodes, and edges are attached to nodes or ports.

Read the first line of the report:

| RESULT | Meaning | What you do |
|---|---|---|
| `PASS` | Good. | Step 5. |
| `FIX` | Built, but has `[ERROR]` items. | Step 4. |
| `INVALID` | Nothing built. | Step 4. |

## Step 4: Fix and rebuild (up to 4 rounds)

1. Edit the file named on the `CLEAN SPEC:` line (`*.normalized.json`) from now on. All report paths refer to it.
2. Do every `[INVALID]` and `[ERROR]` item under `NEXT ACTIONS`. Each gives a path, the problem and a `FIX:` with exact numbers. Count characters; do not guess.
3. Rebuild on the clean spec:
   ```
   python3 scripts/make_tad.py spec.normalized.json --out <Topic>.drawio --png preview.png
   ```
4. Stop at `PASS`. `[WARNING]` items never block a PASS; fix them when easy.

If it is still `FIX` after 4 rounds, deliver anyway and tell the user which items remain.

## Step 5: Check and deliver

1. Look at every preview PNG. Confirm labels are readable, no line crosses a box, boundaries enclose the right things, and the flow reads in one direction. If the main flow doubles back, reorder the spec (rule 3) and rebuild.
2. Deliver the `.drawio` file, plus the previews or PDF if asked. Say in one or two sentences what each page shows, and that everything is editable in draw.io (diagrams.net), with edges attached to their boxes and ports.
3. Do not paste the spec unless asked.

---

## Worked example

User: *"Diagram the payload interfaces: C&DH sends 1553 commands to the payload controller and gets telemetry back, EPS feeds 28 V to a PDU that powers the FPA and thermal controller, the controller talks SpaceWire to both, the FPA sends Camera Link frames to an image processor, which sends imagery to the X-band transmitter."*

1. **Template:** `interface.json`. Containers: Spacecraft Bus, Imaging Payload (with Payload Electronics and Sensor Head inside), Ground Segment.
2. **Ports with sides** on every unit; commands and telemetry as two `interface` edges (they are different interfaces); power as `power` edges; controller-to-FPA as `bidir`.
3. **Build:** `RESULT: PASS`, with the telemetry edge noted as closing a loop (drawn straight back to the bus). Page 2 is the generated interface table.

The finished version is `examples/payload_interfaces.json`, with `examples/payload_interfaces-1.preview.png` and `-2.preview.png`.
