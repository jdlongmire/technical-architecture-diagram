"""Every numeric limit the checker enforces lives here.

Boxes grow to fit their text, so these limits do not depend on layout.
`make_tad.py --limits` prints them and `gen_reference.py` writes
reference/limits.md from this file, so the docs cannot drift from the code.
Pixel widths are measured with Liberation Sans (metric-compatible with Arial).
"""

# Node text ------------------------------------------------------------------
NODE_MAX_WIDTH = 200            # px; longer labels wrap
NODE_MIN_WIDTH = 96             # px
NODE_LABEL_MAX_LINES = 2        # wrapped lines of the bold label
NODE_LABEL_MAX_CHARS = 40       # hard cap regardless of wrapping
STEREOTYPE_MAX_CHARS = 24       # text inside the guillemets
DETAIL_MAX_CHARS = 34           # optional small line (address, version, part no.)
ATTR_MAX_CHARS = 38             # one compartment line (bdd/ibd blocks)
ATTR_MAX_LINES = 10             # lines across all compartments of one block

# Ports, edges, containers --------------------------------------------------
PORT_LABEL_MAX_CHARS = 16
EDGE_LABEL_MAX_LINE_CHARS = 30  # each line of an edge label
EDGE_LABEL_MAX_LINES = 3        # label + data + protocol lines combined
CONTAINER_LABEL_MAX_CHARS = 44

# Density, per view (one view = one page) -----------------------------------
NODES_PER_VIEW_WARN = 40
NODES_PER_VIEW_MAX = 70
EDGES_PER_VIEW_MAX = 110
CROSSINGS_WARN_RATIO = 0.25     # warn when crossings > ratio * edges (and > 6)
CROSSINGS_WARN_MIN = 6
CONTAINER_DEPTH_MAX = 4

# Page fit -------------------------------------------------------------------
PAGE_MIN_SCALE = 0.60           # below this a fixed page is unreadable -> FIX
FIX_ROUNDS = 4

# Font sizes (px) -------------------------------------------------------------
FONT_TITLE = 22
FONT_SUBTITLE = 13
FONT_LABEL = 12
FONT_STEREO = 10
FONT_DETAIL = 10
FONT_ATTR = 10
FONT_EDGE = 10
FONT_PORT = 9
FONT_CONTAINER = 12
FONT_BANNER = 12
FONT_LEGEND = 10
FONT_TABLE = 10


def as_table():
    """(name, value, meaning) rows for docs and --limits."""
    return [
        ("NODE_LABEL_MAX_CHARS", NODE_LABEL_MAX_CHARS, "node label, characters"),
        ("NODE_LABEL_MAX_LINES", NODE_LABEL_MAX_LINES, f"node label lines after wrapping at {NODE_MAX_WIDTH}px"),
        ("STEREOTYPE_MAX_CHARS", STEREOTYPE_MAX_CHARS, "stereotype text (without guillemets)"),
        ("DETAIL_MAX_CHARS", DETAIL_MAX_CHARS, "node detail line"),
        ("ATTR_MAX_CHARS", ATTR_MAX_CHARS, "one compartment line (attributes, operations, values)"),
        ("ATTR_MAX_LINES", ATTR_MAX_LINES, "compartment lines per block"),
        ("PORT_LABEL_MAX_CHARS", PORT_LABEL_MAX_CHARS, "port label"),
        ("EDGE_LABEL_MAX_LINE_CHARS", EDGE_LABEL_MAX_LINE_CHARS, "each line of an edge label"),
        ("EDGE_LABEL_MAX_LINES", EDGE_LABEL_MAX_LINES, "edge label lines (label, data, protocol/port)"),
        ("CONTAINER_LABEL_MAX_CHARS", CONTAINER_LABEL_MAX_CHARS, "container header"),
        ("NODES_PER_VIEW_WARN", NODES_PER_VIEW_WARN, "nodes in one view before a warning"),
        ("NODES_PER_VIEW_MAX", NODES_PER_VIEW_MAX, "nodes in one view before FIX (split or collapse)"),
        ("EDGES_PER_VIEW_MAX", EDGES_PER_VIEW_MAX, "edges in one view before FIX"),
        ("CONTAINER_DEPTH_MAX", CONTAINER_DEPTH_MAX, "container nesting depth"),
        ("PAGE_MIN_SCALE", PAGE_MIN_SCALE, "smallest scale allowed when a fixed page size is set"),
    ]
