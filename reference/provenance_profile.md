# Provenance profile

TAD diagrams are technical architecture views, not a SysML model
repository. Provenance therefore lives in the spec as data, in the
MBSE manner, and is rendered on the canvas only where a reviewer
needs it. This profile formalizes that split. It is implemented in
tad 0.2.0: the fields, the rendering rules, and the QA gates below
are what the tool enforces.

## Levels

| Level | Applies to | Rule |
|---|---|---|
| `light` | `network`, `bdd`, `ibd`, and any kind by default | Header and spec metadata required. Provenance tags render when supplied. No completeness gates. |
| `strict` | `interface` and `dataflow` by default | Completeness gates below are enforced and reported like other build errors. |

A spec may set `"provenance": "strict"` or `"provenance": "light"`
to override the default for its kind. The level in force is named
in the build report.

## Diagram header

Every page carries a frame header in the top-left, generated from
spec metadata, in the SysML frame form:

```
tad [kind] [context] [diagram name]
```

- `kind` is the spec `kind`.
- `context` is the containing package, system, or program the
  diagram belongs to (new optional top-level field `context`).
- `diagram name` is the spec `title` (per view, the view `name`).

Status chips follow the header line when the fields are set:
`marking` (already supported), plus new optional top-level fields
`version` and `status` (`draft`, `review`, `approved`). The tool
draws markings as given and never determines classification
(existing rule 2 of the skill).

## Spec metadata (the digital title block)

Authorship, dates, and revision history are configuration
management data. They live in the repository that holds the spec,
not in drawn margins. A conforming spec may carry, and a strict
spec must carry, these top-level fields:

| Field | Meaning |
|---|---|
| `id` | Stable diagram identifier, independent of title. |
| `context` | Package, system, or program the diagram belongs to. |
| `owner` | Person or organization accountable for the diagram. |
| `sources` | List of authority references the diagram rests on (documents, requirement sets, ADRs), each with an id and title. |
| `version` | Diagram version, drawn as a header chip. |
| `status` | `draft`, `review`, or `approved`. |

The same metadata is embedded in the generated `.drawio` file as
diagram properties, and the build report records the spec hash and
tool version, so a rendered page can be traced back to the exact
spec that produced it.

## Generated title block

The released-sheet layer: a title block in the engineering drawing
manner, drawn at the bottom right of every page and generated
entirely from the spec metadata above. It is **on by default in
strict mode and off in light mode**; a spec overrides either way
with `"title_block": true` or `false`.

Cells: title; diagram id, context, owner, organization; version,
status, date, marking; sheet (page n of m), scale (always NTS:
these diagrams are not to scale), and the source ids. Approval
cells (prepared by, checked by, approved by, from the optional
`prepared_by`, `checked_by`, `approved_by` fields) appear only when
the spec supplies them; the tool never invents an approver or a
date, so a missing `date` leaves the date cell blank. Revision
history itself stays with the repository; the version cell carries
the current revision.

## Element provenance

Nodes and containers may carry:

| Field | Meaning | Rendering |
|---|---|---|
| `stereotype` | Already supported. Provenance stereotypes: `source`, `allocated`, `external`, `authority`, `assumption`. | Guillemets above the label (existing behavior). |
| `owner` | Organization or person accountable for the element. | Not drawn in light mode. In strict mode, drawn as a small muted line under the detail line when set. |
| `source_ref` | Id of an entry in top-level `sources`, or a direct reference id (for example `ICD-04`). | Drawn as a compact tag after the stereotype line, for example «source» ICD-04. Full text stays in `sources`. |

## Relationship provenance

Edges may use these types in any kind (added to the kind's edge
vocabulary, drawn dashed with an open arrowhead):

| Type | Meaning |
|---|---|
| `trace` | This element or diagram traces to an authority: a requirement, regulation, source document, or decision. The edge `label` carries the target id (for example `REQ-014`, `ADR-TMF-0004`). |
| `allocate` | Allocation of a function, requirement, or responsibility to this element. |
| `verify` | This element or test verifies the target. |
| `satisfy` | This element satisfies the target requirement. |

Information flows keep their existing provenance: `data`,
`protocol`/`port`, and `marking` on the edge and in the interface
table state what crosses an interface, how, and at what
classification.

## Rationale and problem notes

A spec may carry top-level `notes` entries:

```json
{"id": "R-1", "kind": "rationale", "anchor": "node_id",
 "text": "Why this choice was made.", "show": true}
```

`kind` is `rationale` or `problem`. Notes are part of the model
data; a note with `show` true is drawn in a notes panel under the
legend, keyed by its anchor element's label.

## Strict-mode gates

In strict mode the build reports an `[ERROR]` (RESULT: FIX) when:

- an `external` node or any node outside the diagram's home
  containers lacks `owner` or `source_ref`;
- a flow crossing a trust or classification boundary lacks
  `marking`, and the diagram has no page `marking` for it to fall
  under (the existing crossing warning for missing `protocol` is
  unchanged);
- a `trace`, `verify`, or `satisfy` edge's target id does not
  resolve to a `sources` entry, a requirement id named in the spec,
  or another element id;
- top-level `id`, `owner`, or `status` is missing.

In light mode the same conditions are `[WARNING]` items at most,
and only when the relevant fields are partially supplied.

Human-Curated, AI-Enabled (HCAE)
