"""Window-relative sizing in Qt logical pixels (Windows handles monitor DPI)."""

import re

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QBoxLayout, QFormLayout, QLayout


def fit_window(window, preferred, minimum):
    available = window.screen().availableGeometry().size() - QSize(40, 40)
    window.setMinimumSize(QSize(*minimum).boundedTo(available))
    window.resize(QSize(*preferred).boundedTo(available))


def scaled_stylesheet(stylesheet, scale):
    def dimension(match):
        value, unit = float(match[1]), match[2]
        value = max(9 if unit == "pt" else 1, value * scale) if value else 0
        return f"{value:.2f}{unit}"
    return re.sub(r"(\d+(?:\.\d+)?)(px|pt)\b", dimension, stylesheet)


class LayoutMetrics:
    """Keep original spacing so repeated resizes never accumulate rounding errors."""

    def __init__(self, widget):
        self.layouts = []
        for layout in widget.findChildren(QLayout):
            if isinstance(layout, (QBoxLayout, QFormLayout)):
                margins = layout.contentsMargins()
                spacing = ((layout.horizontalSpacing(), layout.verticalSpacing())
                           if isinstance(layout, QFormLayout) else (layout.spacing(),))
                self.layouts.append((layout, (margins.left(), margins.top(), margins.right(), margins.bottom()), spacing))
                if isinstance(layout, QFormLayout):
                    layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

    def apply(self, scale):
        for layout, margins, spacing in self.layouts:
            layout.setContentsMargins(*(round(value * scale) for value in margins))
            values = [round(value * scale) if value >= 0 else -1 for value in spacing]
            if isinstance(layout, QFormLayout):
                layout.setHorizontalSpacing(values[0])
                layout.setVerticalSpacing(values[1])
            else:
                layout.setSpacing(values[0])
