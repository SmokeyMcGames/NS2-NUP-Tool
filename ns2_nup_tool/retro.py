"""Crisp native pixel artwork and window chrome; no external image dependencies."""

import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QRegion
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QWidget

THEMES = {
    "Classic Red": ("#ff5268", "#f5c94a", "#99b5d2"),
}

GLYPHS = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 +-/.:", (
    "01110100011000111111100011000110001", "11110100011000111110100011000111110",
    "01111100001000010000100001000001111", "11110100011000110001100011000111110",
    "11111100001000011110100001000011111", "11111100001000011110100001000010000",
    "01111100001000010111100011000101111", "10001100011000111111100011000110001",
    "11111001000010000100001000010011111", "00111000100001000010000101001001100",
    "10001100101010011000101001001010001", "10000100001000010000100001000011111",
    "10001110111010110101100011000110001", "10001110011010110011100011000110001",
    "01110100011000110001100011000101110", "11110100011000111110100001000010000",
    "01110100011000110001101011001001101", "11110100011000111110101001001010001",
    "01111100001000001110000010000111110", "11111001000010000100001000010000100",
    "10001100011000110001100011000101110", "10001100011000110001100010101000100",
    "10001100011000110101101011101110001", "10001100010101000100010101000110001",
    "10001100010101000100001000010000100", "11111000010001000100010001000011111",
    "01110100011001110101110011000101110", "00100011000010000100001000010001110",
    "01110100010000100010001000100011111", "11110000010000101110000010000111110",
    "00010001100101010010111110001000010", "11111100001000011110000010000111110",
    "01110100001000011110100011000101110", "11111000010001000100010000100001000",
    "01110100011000101110100011000101110", "01110100011000101111000010000101110",
    "00000000000000000000000000000000000", "00000001000010011111001000010000000",
    "00000000000000011111000000000000000", "00001000100001000100010000100010000",
    "00000000000000000000000000011000110", "00000001100011000000001100011000000",
)))


def pixel_text(painter, text, x, y, scale=3, color="#f5f7ff"):
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    for letter in text.upper():
        glyph = GLYPHS.get(letter, GLYPHS[" "])
        for index, bit in enumerate(glyph):
            if bit == "1":
                painter.drawRect(QRectF(x + index % 5 * scale, y + index // 5 * scale, scale, scale))
        x += 6 * scale


def stepped_rect(rect, cut=8):
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    path = QPainterPath()
    path.addPolygon(QPolygonF([QPointF(x+cut,y), QPointF(x+w-cut,y), QPointF(x+w-cut,y+cut),
        QPointF(x+w,y+cut), QPointF(x+w,y+h-cut), QPointF(x+w-cut,y+h-cut),
        QPointF(x+w-cut,y+h), QPointF(x+cut,y+h), QPointF(x+cut,y+h-cut),
        QPointF(x,y+h-cut), QPointF(x,y+cut), QPointF(x+cut,y+cut)]))
    path.closeSubpath()
    return path


def pixel_art(kind):
    """Draw 64px sprites once; display with nearest-neighbor scaling."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setPen(Qt.PenStyle.NoPen)
    def rect(x, y, w, h, color):
        p.fillRect(x, y, w, h, QColor(color))
    def poly(points, color):
        p.setBrush(QColor(color))
        p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
    if kind == 0:
        # Four discrete light rays and folded box faces.
        poly([(29,33),(10,3),(18,3),(34,32)], "#10a9bb")
        poly([(29,32),(27,0),(35,0),(35,32)], "#39ffe4")
        poly([(32,33),(47,3),(53,3),(36,34)], "#08c6e0")
        poly([(8,30),(31,22),(56,30),(33,40)], "#b9ffff")
        poly([(9,32),(32,40),(32,61),(9,52)], "#6795ff")
        poly([(32,40),(55,32),(55,53),(32,61)], "#4060df")
        poly([(9,31),(31,23),(23,36),(1,29)], "#edeeff")
        poly([(32,24),(55,31),(63,39),(41,43)], "#a6e7ff")
        rect(12,39,3,11,"#94bdff")
        pixel_text(p,"NUP",35,47,1,"#c3d8ff")
        rect(4,12,3,3,"#ffde64"); rect(53,13,4,4,"#ffde64")
        rect(41,1,6,6,"#36fff2"); rect(16,19,2,2,"#ffffff")
    elif kind == 1:
        poly([(5,12),(8,9),(23,9),(28,15),(56,15),(58,18),(58,54),(5,54)],"#b95d15")
        poly([(5,9),(8,6),(22,6),(27,12),(57,12),(60,15),(60,50),(5,50)],"#ffc13d")
        rect(10,8,11,2,"#fff2a6")
        rect(16,17,34,30,"#9b7ab6"); rect(18,15,32,29,"#e2d5ff")
        rect(23,22,33,24,"#bda6df"); rect(25,20,31,24,"#f6efff")
        poly([(8,30),(12,26),(62,26),(58,56),(53,60),(4,60)],"#d66b00")
        poly([(9,28),(13,24),(63,24),(57,54),(53,57),(4,57)],"#ffb812")
        rect(14,26,43,2,"#ffe791")
        pixel_text(p,"NUP",23,37,1,"#9a480a")
    elif kind == 2:
        poly([(12,7),(17,3),(55,3),(58,8),(53,54),(46,61),(8,61),(5,56)],"#432278")
        poly([(10,49),(48,49),(52,53),(47,58),(10,58),(7,55)],"#fff0d8")
        rect(10,53,37,2,"#c7b5bd")
        poly([(12,5),(17,1),(56,1),(52,48),(46,52),(6,52)],"#ae66ff")
        poly([(17,4),(53,4),(48,46),(12,46)],"#7a35e1")
        rect(15,9,2,31,"#c791ff")
        rect(29,11,13,3,"#ece0ff"); rect(26,14,4,5,"#ece0ff")
        rect(39,14,4,6,"#ece0ff"); rect(34,19,8,3,"#ece0ff")
        rect(33,22,4,4,"#ece0ff"); rect(33,28,4,3,"#ece0ff")
        rect(23,36,20,3,"#c39aff"); rect(22,42,14,3,"#c39aff")
        poly([(36,52),(46,52),(46,64),(41,61),(36,64)],"#ff51c5")
    else:
        rect(7,26,50,34,"#71303c")
        rect(10,29,44,28,"#db6576")
        rect(14,33,36,20,"#ffe4dd")
        pixel_text(p,"NUP",23,40,1,"#71303c")
        poly([(31,0),(49,17),(39,17),(39,30),(24,30),(24,17),(14,17)],"#ffca4e")
        rect(28,15,4,12,"#fff1b1")
        rect(4,8,4,4,"#fff1b1"); rect(54,12,4,4,"#fff1b1")
    p.end()
    return pixmap


class RetroCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.phase, self.motion = 0., True
        self.accent = QColor("#00e5ef")
        self.clock = QTimer(self)
        self.clock.setInterval(50)
        self.clock.timeout.connect(self.tick)
        self.clock.start()

    def tick(self):
        if self.motion and self.isVisible() and not self.window().isMinimized():
            self.phase += .026
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#0b1127"))
        gradient.setColorAt(1, QColor("#152346"))
        p.fillRect(self.rect(), gradient)
        p.setPen(Qt.PenStyle.NoPen)
        # Large stepped celestial shapes echo the reference without smoothing pixels.
        for index, (cx, cy, radius, color) in enumerate(((.06,.27,150,"#073a58"),(.97,.38,150,"#162b69"),
                (.02,.84,150,"#28215e"),(.70,-.02,110,"#302064"),(.97,.90,145,"#17295f"))):
            drift_x = math.cos(self.phase * .8 + index) * 48
            drift_y = math.sin(self.phase + index) * 35
            p.setBrush(QColor(color))
            for y in range(-radius, radius, 12):
                half = int(math.sqrt(max(0, radius * radius - y * y)) // 12) * 12
                p.drawRect(QRectF(cx*self.width()-half+drift_x, cy*self.height()+y+drift_y, half*2, 12))
        for i in range(48):
            speed = 24 + (i % 5) * 9
            x = (i*193+61 + self.phase*speed) % max(1,self.width())
            y = (i*97+119 + self.phase*(12+i%4*7)) % max(1,self.height())
            color = QColor(self.accent)
            color.setAlpha(int(38 + 28*(1+math.sin(self.phase*2+i))))
            p.fillRect(int(x), int(y), 4 if i % 7 == 0 else 3, 4 if i % 7 == 0 else 3, color)


class TitleBar(QFrame):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            window.showNormal() if window.isMaximized() else window.showMaximized()


class PixelWordmark(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(328, 62)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_ui_scale(self, scale):
        self.setFixedSize(round(328 * scale), round(62 * scale))

    def paintEvent(self, event):
        p = QPainter(self)
        p.scale(self.width() / 328, self.height() / 62)
        p.fillRect(0, 5, 52, 52, QColor("#ff5268"))
        p.fillRect(4, 9, 44, 4, QColor("#ffd0d6"))
        pixel_text(p,"N",14,17,4,"#10172d")
        p.fillRect(67, 12, 3, 38, QColor("#61789f"))
        pixel_text(p,"NS2 NUP TOOL",86,23,3)


class WindowButton(QPushButton):
    def __init__(self, kind, callback):
        super().__init__()
        self.kind = kind
        self.setAutoDefault(False)
        self.setObjectName("windowClose" if kind == "close" else "windowControl")
        self.setAccessibleName({"close":"Close", "max":"Maximize or restore", "min":"Minimize"}[kind])
        self.setToolTip(self.accessibleName())
        self.setFixedSize(54, 48)
        self.clicked.connect(callback)

    def set_ui_scale(self, scale):
        self.setFixedSize(round(54 * scale), round(48 * scale))

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.scale(self.width() / 54, self.height() / 48)
        p.setPen(QPen(QColor("#f5f7ff"), 3))
        if self.kind == "min":
            p.drawLine(17,26,37,26)
        elif self.kind == "max":
            p.drawRect(18,15,19,19)
        else:
            p.drawLine(18,15,36,33)
            p.drawLine(36,15,18,33)


class ResizeBorder(QWidget):
    """Only the outer 7px intercept input, leaving all normal controls usable."""
    def __init__(self, window):
        super().__init__(window)
        self.setMouseTracking(True)
        self.drag_origin = None
        self.drag_geometry = None
        self.drag_edges = Qt.Edge(0)

    def fit(self):
        self.setGeometry(self.parentWidget().rect())
        self.setMask(QRegion(self.rect()) - QRegion(self.rect().adjusted(7,7,-7,-7)))
        self.raise_()

    def edges(self, point):
        result = Qt.Edge(0)
        if point.x() < 7: result |= Qt.Edge.LeftEdge
        if point.x() > self.width()-8: result |= Qt.Edge.RightEdge
        if point.y() < 7: result |= Qt.Edge.TopEdge
        if point.y() > self.height()-8: result |= Qt.Edge.BottomEdge
        return result

    def mouseMoveEvent(self, event):
        if self.drag_origin is not None:
            delta = event.globalPosition().toPoint() - self.drag_origin
            geometry = self.drag_geometry.adjusted(0, 0, 0, 0)
            minimum = self.window().minimumSize()
            if self.drag_edges & Qt.Edge.LeftEdge:
                geometry.setLeft(min(geometry.right() - minimum.width() + 1, geometry.left() + delta.x()))
            if self.drag_edges & Qt.Edge.RightEdge:
                geometry.setWidth(max(minimum.width(), geometry.width() + delta.x()))
            if self.drag_edges & Qt.Edge.TopEdge:
                geometry.setTop(min(geometry.bottom() - minimum.height() + 1, geometry.top() + delta.y()))
            if self.drag_edges & Qt.Edge.BottomEdge:
                geometry.setHeight(max(minimum.height(), geometry.height() + delta.y()))
            self.window().setGeometry(geometry)
            event.accept()
            return
        edges = self.edges(event.position())
        horizontal = bool(edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge))
        vertical = bool(edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge))
        if horizontal and vertical:
            forward = bool(edges & Qt.Edge.LeftEdge) == bool(edges & Qt.Edge.TopEdge)
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if forward else Qt.CursorShape.SizeBDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeHorCursor if horizontal else Qt.CursorShape.SizeVerCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.window().isMaximized():
            # Qt logical coordinates keep custom frameless resizing consistent at every DPI.
            self.drag_origin = event.globalPosition().toPoint()
            self.drag_geometry = self.window().geometry()
            self.drag_edges = self.edges(event.position())
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_origin = self.drag_geometry = None
        self.drag_edges = Qt.Edge(0)
        super().mouseReleaseEvent(event)


class ArtworkBox(QLabel):
    def __init__(self, size=224):
        super().__init__("NO ARTWORK")
        self.setObjectName("artworkBox")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.base_size = size
        self.original = QPixmap()
        self.setFixedSize(size, size)

    def set_ui_scale(self, scale):
        size = round(self.base_size * scale)
        self.setFixedSize(size, size)
        self.refresh_artwork()

    def show_artwork(self, pixmap, fallback="NO ARTWORK"):
        self.original = pixmap
        self.setToolTip(fallback)
        if pixmap.isNull():
            self.clear()
            self.setText(fallback)
        else:
            self.refresh_artwork()

    def refresh_artwork(self):
        if not self.original.isNull():
            ratio = self.devicePixelRatioF()
            size = max(1, round((self.width() - 18) * ratio))
            pixmap = self.original.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
            pixmap.setDevicePixelRatio(ratio)
            self.setPixmap(pixmap)

    def resizeEvent(self, event):
        self.refresh_artwork()
        super().resizeEvent(event)
