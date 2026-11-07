"""Diagram kinds, default edge types, container and node styles, markings, theme."""

KINDS = ("network", "interface", "dataflow", "bdd", "ibd")

# Default layout direction per kind (ELK: RIGHT or DOWN).
DEFAULT_DIRECTION = {
    "network": "AUTO",      # AUTO lays out RIGHT and DOWN and keeps the better page fit
    "interface": "AUTO",
    "dataflow": "AUTO",
    "bdd": "DOWN",
    "ibd": "AUTO",
}

DEFAULT_THEME = {
    "font": "Helvetica",          # draw.io family; previews use Liberation Sans (Arial metrics)
    "text": "1F2933",
    "muted": "52606D",
    "node_fill": "FFFFFF",
    "node_stroke": "3E4C59",
    "port": "3E4C59",
    "edge": "3E4C59",
    "accent": "1F5FAD",           # data flows
    "alert": "C2410C",            # boundary-crossing flows, trust boundaries
    "title": "102A43",
    "legend_fill": "FFFFFF",
}

# Edge types --------------------------------------------------------------------
# Keys: label (legend text), dash (none|dashed|dotted), color (theme key or hex),
# start/end (none|arrow|open|diamond|odiamond|triangle), width, reverse_layout.
# reverse_layout=True lays the edge out target->source (keeps generals/wholes on top in bdd).
_E = dict
EDGE_TYPES = {
    "network": {
        "link":     _E(label="Network link", dash="none", color="edge", start="none", end="none", width=1.5),
        "flow":     _E(label="Data flow", dash="none", color="accent", start="none", end="arrow", width=1.5),
        "tunnel":   _E(label="Encrypted tunnel", dash="dashed", color="accent", start="arrow", end="arrow", width=1.5),
        "wireless": _E(label="Wireless / RF", dash="dotted", color="edge", start="none", end="none", width=1.5),
        "mgmt":     _E(label="Management", dash="dashed", color="muted", start="none", end="arrow", width=1),
    },
    "interface": {
        "interface": _E(label="Interface", dash="none", color="accent", start="none", end="arrow", width=1.5),
        "bidir":     _E(label="Bidirectional interface", dash="none", color="accent", start="arrow", end="arrow", width=1.5),
        "control":   _E(label="Command / control", dash="dashed", color="edge", start="none", end="arrow", width=1.5),
        "power":     _E(label="Power", dash="none", color="alert", start="none", end="arrow", width=2, ifid=False),
        "physical":  _E(label="Physical connection", dash="none", color="edge", start="none", end="none", width=1.5),
    },
    "dataflow": {
        "flow":    _E(label="Data flow", dash="none", color="accent", start="none", end="arrow", width=1.5),
        "control": _E(label="Control flow", dash="dashed", color="edge", start="none", end="arrow", width=1.5),
        "crossing": _E(label="Crosses a trust boundary", dash="none", color="alert", start="none", end="arrow", width=2.25),
    },
    "bdd": {
        "composition":    _E(label="Composition (part of)", dash="none", color="edge", start="diamond", end="none", width=1.25),
        "aggregation":    _E(label="Aggregation (shared part)", dash="none", color="edge", start="odiamond", end="none", width=1.25),
        "generalization": _E(label="Generalization (kind of)", dash="none", color="edge", start="none", end="triangle",
                             width=1.25, reverse_layout=True),
        "association":    _E(label="Association", dash="none", color="edge", start="none", end="none", width=1.25),
        "dependency":     _E(label="Dependency", dash="dashed", color="edge", start="none", end="open", width=1.25),
    },
    "ibd": {
        "flow":      _E(label="Item flow", dash="none", color="accent", start="none", end="arrow", width=1.5),
        "connector": _E(label="Connector", dash="none", color="edge", start="none", end="none", width=1.5),
        "binding":   _E(label="Binding", dash="dashed", color="muted", start="none", end="none", width=1.25),
    },
}
# Provenance edge types (reference/provenance_profile.md): available in every kind.
# They carry no interface id in interface diagrams (ifid=False).
PROVENANCE_EDGE_TYPES = {
    "trace":    _E(label="Trace (to authority)", dash="dashed", color="muted", start="none", end="open",
                   width=1.25, ifid=False),
    "allocate": _E(label="Allocate", dash="dashed", color="edge", start="none", end="open",
                   width=1.25, ifid=False),
    "verify":   _E(label="Verify", dash="dashed", color="accent", start="none", end="open",
                   width=1.25, ifid=False),
    "satisfy":  _E(label="Satisfy", dash="dashed", color="accent", start="none", end="open",
                   width=1.25, ifid=False),
}
for _k in EDGE_TYPES:
    EDGE_TYPES[_k].update(PROVENANCE_EDGE_TYPES)

DEFAULT_EDGE_TYPE = {"network": "link", "interface": "interface", "dataflow": "flow",
                     "bdd": "association", "ibd": "connector"}

# Container types -------------------------------------------------------------
# fill/stroke hex, dash, stroke width, legend label.
CONTAINER_TYPES = {
    "site":           dict(label="Site / facility", fill="F0F4F8", stroke="486581", dash="none", width=1.5),
    "zone":           dict(label="Network zone", fill="EAF2FB", stroke="5B8DC9", dash="none", width=1.25),
    "enclave":        dict(label="Enclave", fill="F3EEFB", stroke="7C5CBF", dash="none", width=2),
    "trust":          dict(label="Trust boundary", fill="none", stroke="C2410C", dash="dashed", width=1.75),
    "classification": dict(label="Classification boundary", fill="none", stroke="marking", dash="none", width=2.5),
    "system":         dict(label="System", fill="F7F9FB", stroke="3E4C59", dash="none", width=1.5),
    "subsystem":      dict(label="Subsystem", fill="FFFFFF", stroke="7B8794", dash="none", width=1.25),
    "group":          dict(label="Group", fill="none", stroke="9AA5B1", dash="dotted", width=1.25),
    "cloud":          dict(label="Cloud / external service", fill="F5FAF6", stroke="3F9142", dash="none", width=1.25),
}
DEFAULT_CONTAINER_TYPE = {"network": "zone", "interface": "system", "dataflow": "trust",
                          "bdd": "group", "ibd": "system"}
# Container types that count as boundaries for dataflow crossing detection.
BOUNDARY_TYPES = ("trust", "classification", "enclave")

# Node shapes -----------------------------------------------------------------
NODE_SHAPES = ("box", "rounded", "cylinder", "store", "external", "process", "actor", "block", "part", "note")
DEFAULT_SHAPE = {"network": "box", "interface": "box", "dataflow": "process", "bdd": "block", "ibd": "part"}
SHAPE_ALIASES = {
    "rect": "box", "rectangle": "box", "server": "box", "node": "box", "component": "box", "device": "box",
    "round": "rounded", "service": "rounded",
    "db": "cylinder", "database": "cylinder", "datastore": "store", "data store": "store", "data_store": "store",
    "ext": "external", "entity": "external", "external entity": "external", "terminator": "external",
    "proc": "process", "function": "process",
    "person": "actor", "user": "actor", "human": "actor",
    "class": "block", "uml": "block",
    "property": "part",
    "comment": "note",
}

# Classification markings -----------------------------------------------------
# Standard banner colours. The tool only draws markings the author supplies; it
# does not determine or validate classification. Marking authority stays with the author.
MARKINGS = {
    "UNCLASSIFIED": ("007A33", "FFFFFF"),
    "CUI": ("502B85", "FFFFFF"),
    "CONFIDENTIAL": ("0033A0", "FFFFFF"),
    "SECRET": ("C8102E", "FFFFFF"),
    "TOP SECRET": ("FF8C00", "000000"),
}
PORTION = {"UNCLASSIFIED": "U", "CUI": "CUI", "CONFIDENTIAL": "C", "SECRET": "S", "TOP SECRET": "TS"}


def marking_colors(marking):
    if not marking:
        return ("7B8794", "FFFFFF")
    base = marking.upper().split("//")[0].strip()
    return MARKINGS.get(base, ("7B8794", "FFFFFF"))


def portion_mark(marking):
    if not marking:
        return ""
    base = marking.upper().split("//")[0].strip()
    return "(" + PORTION.get(base, base) + ")"


def resolve_color(value, theme):
    """Theme key or hex -> 6-digit hex (no #)."""
    if value is None or value == "none":
        return "none"
    v = str(value).lstrip("#")
    if v in theme:
        return str(theme[v]).lstrip("#")
    return v.upper()


# Page sizes in px (landscape). draw.io works in px at 100% zoom.
PAGE_SIZES = {
    "letter": (1100, 850),
    "legal": (1400, 850),
    "tabloid": (1700, 1100),
    "a4": (1169, 827),
    "a3": (1654, 1169),
    "a2": (2339, 1654),
    "auto": None,
}
