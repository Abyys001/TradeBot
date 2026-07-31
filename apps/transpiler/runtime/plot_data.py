"""Plot data collector for visual Pine Script builtins.

Accumulates data from ``plot()``, ``plotshape()``, ``plotchar()``,
``bgcolor()``, ``barcolor()``, ``hline()``, ``fill()``, ``alert()``
and ``alertcondition()`` during interpretation.  The collected data is
serialised into the ``plot_data`` field of ``BacktestResult`` so the
frontend can render overlays on the chart.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlotLine:
    """A single ``plot()`` call — a numeric series rendered as a line."""
    title: str
    values: list  # list[float | None]
    color: str = "#2196f3"
    linewidth: int = 1
    style: str = "solid"  # "solid" | "dashed" | "dotted"


@dataclass
class PlotShape:
    """A ``plotshape()`` marker — shown at bars where the series is truthy."""
    bar_indices: list  # list[int]
    color: str = "#2196f3"
    style: str = "circle"  # "circle" | "cross" | "triangleup" | "triangledown" | "flag" | "arrowup" | "arrowdown"
    location: str = "above"  # "above" | "below" | "top" | "bottom" | "middle"
    text: str = ""
    title: str = ""


@dataclass
class PlotChar:
    """A ``plotchar()`` marker — character shown at bars where the series is truthy."""
    bar_indices: list  # list[int]
    char: str = "●"
    color: str = "#2196f3"
    location: str = "above"  # "above" | "below" | "top" | "bottom" | "middle"
    text: str = ""
    title: str = ""


@dataclass
class PlotBarColor:
    """Per-bar colour from ``barcolor()``."""
    colors: list  # list[str | None]


@dataclass
class PlotBgColor:
    """Per-bar background colour from ``bgcolor()``."""
    colors: list  # list[str | None]


@dataclass
class PlotHLine:
    """A horizontal reference line from ``hline()``."""
    price: float
    color: str = "#9598a1"
    linestyle: str = "solid"  # "solid" | "dashed" | "dotted"
    linewidth: int = 1
    title: str = ""


@dataclass
class PlotFill:
    """A filled area between two plot lines (``fill()``)."""
    top_values: list  # list[float | None]
    bottom_values: list  # list[float | None]
    color: str = "rgba(76, 175, 80, 0.2)"
    title: str = ""


@dataclass
class PlotAlert:
    """An ``alert()`` call."""
    bar_index: int
    message: str


@dataclass
class PlotAlertCondition:
    """An ``alertcondition()`` definition — condition series + message."""
    condition: list  # list[bool] — one per bar
    title: str = ""
    message: str = ""


@dataclass
class PlotData:
    """All visual outputs collected during a backtest run."""
    lines: list = field(default_factory=list)  # list[PlotLine]
    shapes: list = field(default_factory=list)  # list[PlotShape]
    chars: list = field(default_factory=list)  # list[PlotChar]
    bar_colors: list = field(default_factory=list)  # list[PlotBarColor]
    bg_colors: list = field(default_factory=list)  # list[PlotBgColor]
    hlines: list = field(default_factory=list)  # list[PlotHLine]
    fills: list = field(default_factory=list)  # list[PlotFill]
    alerts: list = field(default_factory=list)  # list[PlotAlert]
    alert_conditions: list = field(default_factory=list)  # list[PlotAlertCondition]

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON."""
        return {
            "lines": [_d(l) for l in self.lines],
            "shapes": [_d(s) for s in self.shapes],
            "chars": [_d(c) for c in self.chars],
            "bar_colors": [_d(c) for c in self.bar_colors],
            "bg_colors": [_d(c) for c in self.bg_colors],
            "hlines": [_d(h) for h in self.hlines],
            "fills": [_d(f) for f in self.fills],
            "alerts": [_d(a) for a in self.alerts],
            "alert_conditions": [_d(a) for a in self.alert_conditions],
        }


def _d(obj) -> dict:
    """Dataclass → dict (handles nested dataclasses and lists)."""
    if hasattr(obj, "__dataclass_fields__"):
        out = {}
        for fname in obj.__dataclass_fields__:
            val = getattr(obj, fname)
            if isinstance(val, list):
                out[fname] = [_d(v) if hasattr(v, "__dataclass_fields__") else v for v in val]
            else:
                out[fname] = val
        return out
    return obj


# Pine Script named colors → CSS hex
PINE_COLORS = {
    "red": "#ef4444",
    "blue": "#3b82f6",
    "green": "#22c55e",
    "yellow": "#eab308",
    "orange": "#f97316",
    "purple": "#a855f7",
    "white": "#ffffff",
    "black": "#000000",
    "gray": "#9ca3af",
    "grey": "#9ca3af",
    "silver": "#c0c0c0",
    "lime": "#84cc16",
    "aqua": "#06b6d4",
    "teal": "#14b8a6",
    "maroon": "#800000",
    "olive": "#808000",
    "navy": "#000080",
    "fuchsia": "#d946ef",
    "maroon": "#800000",
    "color.red": "#ef4444",
    "color.blue": "#3b82f6",
    "color.green": "#22c55e",
    "color.yellow": "#eab308",
    "color.orange": "#f97316",
    "color.purple": "#a855f7",
    "color.white": "#ffffff",
    "color.black": "#000000",
    "color.gray": "#9ca3af",
    "color.grey": "#9ca3af",
    "color.silver": "#c0c0c0",
    "color.lime": "#84cc16",
    "color.aqua": "#06b6d4",
    "color.teal": "#14b8a6",
    "color.maroon": "#800000",
    "color.olive": "#808000",
    "color.navy": "#000080",
    "color.fuchsia": "#d946ef",
    "color.na": "",
}


def resolve_color(raw) -> str:
    """Resolve a Pine colour value to a CSS hex string."""
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    # Already hex
    if s.startswith("#"):
        return s[:7]  # strip any alpha
    # Named colour
    return PINE_COLORS.get(s.lower(), s)
