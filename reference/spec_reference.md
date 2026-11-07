# Spec reference

A spec is one JSON file describing one diagram model. `//` and `/* */` comments and trailing commas are allowed. Field names have aliases (for example `name`/`title` for `label`, `source`/`target` for `from`/`to`); every alias that was used is listed under `AUTO-FIXES` in the report, and the clean spec (`*.normalized.json`) always uses the canonical names below.

Numeric limits are not repeated here. See `reference/limits.md` or run `python3 scripts/make_tad.py --limits`.

## Top level

| Field | Required | Meaning |
|---|---|---|
| `title` | yes | Page title. |
| `subtitle` | no | One sentence under the title. |
| `kind` | yes | `network`, `interface`, `dataflow`, `bdd` or `ibd`. Sets the default edge types, shapes and direction. |
| `direction` | no | `RIGHT`, `DOWN` or `AUTO` (default for every kind except `bdd`). |
| `marking` | no | Page banner text, top and bottom, e.g. `UNCLASSIFIED` or `CUI`. Drawn as given. |
| `page` | no | `auto` (default), `letter`, `legal`, `tabloid`, `a4`, `a3`, `a2`. With a fixed page, the PDF is scaled to fit and the checker fails the build if the scale would drop below the minimum. |
| `containers` | no | Boundaries and groups (see below). |
| `nodes` | yes | Components (see below). Nodes can also be listed inside containers. |
| `edges` | no | Connections (see below). |
| `views` | no | Several pages from one model (see below). Without views there is one page called Overview. |
| `edge_types` | no | Add or override edge types: `{"name": {"label", "dash", "color", "start", "end", "width"}}`. |
| `legend` | no | `true` (default) draws a legend of the line styles and container types actually used. |
| `icons` | no | `true` draws a node's `icon` (a Lucide icon name) at the left of the box. Off by default. |
| `interface_table` | no | Adds an Interfaces page generated from the edges. On by default for `interface`. |
| `theme` | no | Colour overrides: `text`, `muted`, `node_fill`, `node_stroke`, `port`, `edge`, `accent`, `alert`, `title`, and `font` (draw.io font family). |
| `elk` | no | Advanced: raw ELK layout options passed to the root graph, e.g. `{"layered.thoroughness": "30"}`. |

## Containers

| Field | Meaning |
|---|---|
| `id` | Unique id. Derived from `label` when missing. Containers and nodes share one id namespace. |
| `label` | Header text. |
| `type` | `site`, `zone`, `enclave`, `trust`, `classification`, `system`, `subsystem`, `group`, `cloud`. Default depends on kind. |
| `in` | Parent container id (flat style). |
| `containers`, `nodes` | Children (nested style). Flat and nested styles can be mixed. |
| `stereotype` | Shown before the label in guillemets. |
| `marking` | Badge in the header's top-right corner. A `classification` container takes its border colour from it. |

An item in a `containers` list that has node fields (`shape`, `ports`, `detail`, compartments, `icon`) and no children is read as a node.

## Nodes

| Field | Meaning |
|---|---|
| `id`, `label` | As for containers. The label wraps at the maximum box width. |
| `stereotype` | Small italic line above the label, e.g. `server`, `LRU`, `block`. |
| `shape` | `box`, `rounded`, `cylinder`, `store`, `external`, `process`, `actor`, `block`, `part`, `note`. Aliases such as `database` or `person` are accepted. A node `type` is read as a shape when it names one, otherwise as the stereotype. |
| `detail` | Small line under the label: an address, version or part number. |
| `in` | Parent container id. |
| `ports` | List of `"NAME:SIDE"` strings or `{"id", "label", "side"}` objects. Sides: `N`, `S`, `E`, `W`. Without sides the layout chooses. |
| `values`, `parts`, `references`, `operations`, `constraints` | Compartments (lists of strings), drawn in that order under the label. `attributes` is read as `values`. |
| `marking` | Portion mark in front of the label, e.g. `(CUI)`. |
| `icon` | Icon name (used only when top-level `icons` is true). |

## Edges

| Field | Meaning |
|---|---|
| `from`, `to` | A node or container id or label. `"node.port"` attaches to a port; `from_port`/`to_port` do the same. |
| `type` | An edge type for the kind (see `reference/limits.md`). Default depends on kind. |
| `label` | First line. In `interface` diagrams the interface id is prefixed: `IF-03: label`. |
| `data` | Data or item carried (second line, and the Data column of the interface table). |
| `protocol`, `port` | Shown as `protocol/port` on the last line. |
| `id` | Interface id. Assigned automatically (`IF-01`, ...) in `interface` diagrams; power edges get none. |
| `marking` | Portion mark in front of the first label line. |
| `dashed` | `true` draws this one edge dashed regardless of its type. |

Write edges in the direction the flow starts, and list nodes and containers roughly in flow order: the layout follows spec order. An edge that closes a loop (between nodes, or between their containers) is laid out reversed so the main flow stays one-directional; its arrowheads still show the real direction, and the report lists it as a note. For a link that is genuinely two-way, use one edge with a two-way type (`tunnel`, `bidir`) instead of two opposite edges.

## Views

Each view is one page in the `.drawio` file and one preview image.

| Field | Meaning |
|---|---|
| `name` | Page name. |
| `subtitle` | Replaces the spec subtitle on this page. |
| `include` | Ids to show. A container brings its contents; ancestors are kept for context. |
| `exclude` | Ids to hide, with their contents. |
| `collapse` | Container ids drawn as a single double-bordered box. Edges to anything inside are rerouted to the box, and duplicates are merged into one edge labelled `N flows`. |
| `edge_types` | Only these edge types are drawn. |
| `hide_unlinked` | `true` hides nodes that have no edge in this view. |
| `direction` | Overrides the spec direction for this page. |

If you define views and also want a full page, add `{"name": "Full"}` as one of them.

## Dataflow boundaries

In `dataflow` diagrams, containers of type `trust`, `classification` or `enclave` are boundaries. A `flow` edge whose two ends sit inside different sets of boundaries is drawn as the `crossing` type (alert colour, heavier line) and listed in the legend. The checker warns when a crossing flow has no `protocol`.
