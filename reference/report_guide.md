# Report guide

`make_tad.py` prints a report. The first line is the result.

| RESULT | Meaning | What to do |
|---|---|---|
| `PASS` | Built, no errors. | Check the previews, then deliver. |
| `FIX` | Built, but at least one `[ERROR]`. | Fix every `[ERROR]` in the clean spec and rebuild. |
| `INVALID` | Nothing built; the spec cannot be read or a reference is broken. | Fix the `[INVALID]` items in the clean spec and rebuild. |
| `DRY-RUN` | `--dry-run`: validated and counted, nothing built. | Fix any listed items before the first build. |

Other lines:

- `OUTPUT`: the `.drawio` file (all pages).
- `PREVIEW` / `SVG` / `PDF`: the extra files made.
- `CLEAN SPEC`: the normalized spec. **Edit this file during the fix loop.** Every path in the report refers to it.
- `VIEW`: per page, node and edge counts, edge crossings and size in px.
- `AUTO-FIXES APPLIED`: aliases read, ids derived, interface ids assigned. No action needed.
- `NEXT ACTIONS`: numbered `[INVALID]`, `[ERROR]` and `[WARNING]` items, each with a path, the problem and a `FIX:`.
- `NOTES`: information only.

`[WARNING]` never blocks a PASS. Fix warnings when it is easy.

## Messages

| Message | Usual fix |
|---|---|
| `does not match any node or container id/label` | Use an existing id. For a port, `node_id.port_id`. |
| `is a container, and only nodes have ports` | The item was listed under `containers`; move it into a `nodes` list. |
| `has no port` | Add the port to the node's `ports`, or use one listed in the fix. |
| `parent '...' is not a container` | Set `in` to a container id. |
| `edge joins '...' to its own contents` | Connect to a node inside the container instead. |
| `... is N characters (limit M)` | Shorten that field to M characters or fewer. Keep the meaning. |
| `label ... wraps to N lines` | Shorten the label to the character count given. |
| `edge label line ... is N characters` | Shorten the named field (`label`, `data` or `protocol`) by the amount given. |
| `edge label has N lines` | Drop `data` or `label`, keeping the one that says more. |
| `placeholder left in` | Replace the `<<...>>` text or delete the item. |
| `N nodes on one page` | Add views: one per top-level container, or collapse containers in a summary view. |
| `passes through node` | Reorder nodes in the spec (layout follows spec order), give ports explicit sides, or change direction. |
| `label of edge ... overlaps node` | Shorten the label lines or drop the `data` line. |
| `two labels overlap` | Shorten one, or move the detail into the interface table (`interface_table: true`). |
| `N edge crossings` | Put tightly linked nodes in one container, list nodes in flow order, or split by `edge_types` into views. |
| `fits <page> only at N%` | Use a larger page, `page: auto`, or split into views. |
| `crosses a trust boundary with no protocol` | Add `protocol` (and `port`). |
| `port ... is not used by any edge` | Connect an edge to it or remove it. |
| `container ... is empty` | Put nodes in it or remove it. |
| `unknown side ... was dropped` | Set the side to N, S, E or W. |
| `close a loop` (note) | No action. If the link is really two-way, one edge with a two-way type reads better. |
