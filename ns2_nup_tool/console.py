"""Retro console menu, accessible navigation, and slide/fade transitions."""

import math

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, Property, QParallelAnimationGroup,
                            QPropertyAnimation, QRect, QRectF, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF, QRegion
from PySide6.QtWidgets import (QAbstractButton, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from .retro import THEMES, pixel_art, pixel_text, stepped_rect


def transparent_snapshot(widget):
    """Render children without baking the parent's background into a rectangle."""
    ratio = widget.devicePixelRatioF()
    pixmap = QPixmap(widget.size() * ratio)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    widget.render(pixmap, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return pixmap


class PageMotion:
    """Shared snapshot animation for primary pages and tabbed workflows."""
    def setup_motion(self):
        self.motion = True
        self.transition = None
        self.overlays = []
        self.transition_style = 0

    def finish_transition(self):
        if self.transition:
            self.transition.stop()
            self.transition.deleteLater()
            self.transition = None
        for overlay in self.overlays:
            overlay.hide()
            overlay.deleteLater()
        self.overlays.clear()
        if self.currentWidget():
            self.currentWidget().show()

    def animate_page(self, before, direction=1):
        page = self.currentWidget()
        parent, area = page.parentWidget(), page.geometry()
        after = transparent_snapshot(self.currentWidget())
        page.hide()
        self.transition = QParallelAnimationGroup(self)
        horizontal = min(430, area.width() // 3) * direction
        vertical = min(170, area.height() // 3) * direction
        dx, dy = ((horizontal, 38*direction), (-horizontal, vertical), (60*direction, -vertical))[self.transition_style % 3]
        def transformed(scale, x, y):
            width, height = int(area.width()*scale), int(area.height()*scale)
            return QRect(area.x()+(area.width()-width)//2+x, area.y()+(area.height()-height)//2+y, width, height)
        for pixmap, start, end, opacity, incoming in (
                (before, area, transformed(1.08,-dx,-dy), (1.,0.), False),
                (after, transformed(.91,dx,dy), area, (0.,1.), True)):
            overlay = QLabel(parent)
            overlay.setAutoFillBackground(False)
            overlay.setStyleSheet("background: transparent; border: none;")
            overlay.setPixmap(pixmap)
            overlay.setScaledContents(True)
            overlay.setGeometry(start)
            overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            effect = QGraphicsOpacityEffect(overlay)
            overlay.setGraphicsEffect(effect)
            effect.setOpacity(opacity[0])
            overlay.show()
            self.overlays.append(overlay)
            for target, prop, first, last in ((overlay, b"geometry", start, end),
                                                (effect, b"opacity", *opacity)):
                animation = QPropertyAnimation(target, prop, self.transition)
                animation.setDuration(350)
                animation.setStartValue(first)
                animation.setEndValue(last)
                curve = QEasingCurve(QEasingCurve.Type.OutBack if incoming and prop == b"geometry" else QEasingCurve.Type.InOutCubic)
                curve.setOvershoot(.65)
                animation.setEasingCurve(curve)
                self.transition.addAnimation(animation)
        self.transition.finished.connect(self.finish_transition)
        self.transition.start()


class AnimatedStack(QStackedWidget, PageMotion):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_motion()

    def resizeEvent(self, event):
        self.finish_transition()
        super().resizeEvent(event)

    def setCurrentIndex(self, index):
        if index == self.currentIndex() or not 0 <= index < self.count():
            return
        self.finish_transition()
        previous = self.currentIndex()
        animate = self.motion and self.isVisible() and self.currentWidget() is not None
        before = transparent_snapshot(self.currentWidget()) if animate else None
        super().setCurrentIndex(index)
        self.layout().activate()
        if animate:
            self.animate_page(before, 1 if index > previous else -1)


class AnimatedTabs(QTabWidget, PageMotion):
    def __init__(self):
        super().__init__()
        self.setup_motion()
        self.previous = None
        self.currentChanged.connect(self.animate_tab)

    def animate_tab(self, index):
        self.finish_transition()
        old, self.previous = self.previous, self.currentWidget()
        if old is None or old is self.previous or not self.motion or not self.isVisible():
            return
        self.transition_style = index
        self.animate_page(transparent_snapshot(old), 1 if index >= self.indexOf(old) else -1)

    def resizeEvent(self, event):
        self.finish_transition()
        super().resizeEvent(event)


class ConsoleTile(QAbstractButton):
    navigate = Signal(int)

    def __init__(self, title, subtitle, accent, kind):
        super().__init__()
        self.title, self.subtitle = title, subtitle
        self.accent, self.kind = QColor(accent), kind
        self.art = pixel_art(kind)
        self.motion, self.phase, self._focus = True, 0., 0.
        self.ui_scale = 1.
        self.setMinimumSize(260, 280)
        self.setMaximumSize(380, 370)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(title)
        self.setToolTip(subtitle)
        self.animation = QPropertyAnimation(self, b"focusAmount", self)
        self.animation.setDuration(170)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.clock = QTimer(self)
        self.clock.setInterval(33)
        self.clock.timeout.connect(self.tick)
        self.clock.start()

    def set_ui_scale(self, scale):
        self.ui_scale = scale
        self.setMinimumSize(round(260 * scale), round(280 * scale))
        self.setMaximumSize(round(380 * scale), round(370 * scale))
        self.update()

    def get_focus(self):
        return self._focus

    def set_focus(self, value):
        self._focus = value
        self.update()

    focusAmount = Property(float, get_focus, set_focus)

    def tick(self):
        if self.motion and self.isVisible() and not self.window().isMinimized():
            self.phase += .065
            self.update()

    def highlight(self, enabled):
        self.animation.stop()
        if self.motion:
            self.animation.setStartValue(self._focus)
            self.animation.setEndValue(1. if enabled else 0.)
            self.animation.start()
        else:
            self.set_focus(1. if enabled else 0.)

    def enterEvent(self, event):
        self.highlight(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.highlight(self.hasFocus())
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self.highlight(True)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.highlight(False)
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Left):
            self.navigate.emit(1 if event.key() == Qt.Key.Key_Right else -1)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.scale(self.ui_scale, self.ui_scale)
        rect = QRectF(12, 14-self._focus*10, self.width()/self.ui_scale-24, self.height()/self.ui_scale-27)
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(stepped_rect(rect.translated(0,8)), QColor("#050b1b"))
        if self._focus:
            for spread in (9, 6, 3):
                glow = QColor(self.accent)
                glow.setAlpha(int((40-spread*3)*self._focus))
                p.setPen(QPen(glow, spread*2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(stepped_rect(rect, 12))
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, self.accent.darker(120 if self.kind else 240))
        gradient.setColorAt(1, self.accent.darker(330 if self.kind else 490))
        p.setBrush(gradient)
        p.setPen(QPen(self.accent.lighter(145), 3 if self._focus else 2))
        p.drawPath(stepped_rect(rect, 12))
        p.save()
        p.setClipPath(stepped_rect(rect.adjusted(3,3,-3,-3),10))
        p.setPen(Qt.PenStyle.NoPen)
        # Pixel cloud terraces and diagonal highlight bands.
        sheen = QColor("#ffffff"); sheen.setAlpha(18)
        p.setBrush(sheen)
        p.drawPolygon(QPolygonF([rect.topLeft()+QPointF(25,0),rect.topLeft()+QPointF(90,0),
                                rect.topLeft()+QPointF(0,90),rect.topLeft()+QPointF(0,25)]))
        for i in range(9):
            cloud = QColor(self.accent); cloud.setAlpha(25+i%3*12)
            height = 25+(i*13)%42
            p.fillRect(QRectF(rect.x()+i*rect.width()/9,rect.bottom()-92-height,
                             rect.width()/9+1,height+92),cloud)
        float_y = math.sin(self.phase+self.kind)*12 if self.motion else 0
        art_size = min(228, int(rect.height()-120), int(rect.width()-44))
        p.drawPixmap(int(rect.center().x()-art_size/2),int(rect.top()+28+float_y),art_size,art_size,self.art)
        text_scale = 3 if rect.width() >= 290 else 2
        text_width = len(self.title)*6*text_scale
        pixel_text(p,self.title,rect.center().x()-text_width/2,rect.bottom()-59,text_scale)
        p.setPen(QColor("#e0efff"))
        p.setFont(QFont("Consolas", max(9, round(9 / self.ui_scale))))
        p.drawText(rect.adjusted(8,rect.height()-29,-8,-6),Qt.AlignmentFlag.AlignCenter,self.subtitle)
        p.restore()


class HomeScreen(QWidget):
    selected = Signal(int)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 10, 24, 8)
        layout.addStretch(1)
        center = self.center = QWidget()
        center.setMaximumWidth(1520)
        tiles = QHBoxLayout(center)
        tiles.setContentsMargins(0,0,0,0)
        tiles.setSpacing(12)
        self.tiles = []
        colors = THEMES["Classic Red"]
        entries = (("Create NUP", "BASE + UPDATES + DLC", 0, colors[0]),
                   ("Open Package", "BROWSE / EXTRACT / EDIT", 1, colors[1]),
                   ("Update NUP", "REPLACE THE OLD UPDATE", 3, colors[0]),
                   ("Dump Guide", "YOUR QUICK START MANUAL", 2, colors[2]))
        for index, (title, subtitle, destination, accent) in enumerate(entries):
            tile = ConsoleTile(title, subtitle, accent, destination)
            tile.clicked.connect(lambda checked=False, idx=destination: self.selected.emit(idx))
            tile.navigate.connect(lambda direction, idx=index: self.tiles[(idx+direction)%len(self.tiles)].setFocus())
            self.tiles.append(tile)
            tiles.addWidget(tile,1)
        row = QHBoxLayout()
        row.addStretch(1); row.addWidget(center,12); row.addStretch(1)
        layout.addLayout(row,8)
        layout.addStretch(1)
        self.resume = QLabel("DROP A DUMP FOLDER OR .NUP  /  ARROWS TO SELECT  /  ENTER TO OPEN")
        self.resume.setObjectName("homeHint")
        self.resume.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.resume.setWordWrap(True)
        layout.addWidget(self.resume)

    def set_ui_scale(self, scale):
        self.center.setMaximumWidth(round(1520 * scale))
        for tile in self.tiles:
            tile.set_ui_scale(scale)

    def set_theme(self, name):
        colors = THEMES[name]
        for tile, accent in zip(self.tiles, (colors[0], colors[1], colors[0], colors[2])):
            tile.accent = QColor(accent)
            tile.update()

    def set_motion(self, enabled):
        for tile in self.tiles:
            tile.motion = enabled
            if not enabled:
                tile.animation.stop()
                tile.set_focus(1. if tile.hasFocus() else 0.)
            tile.update()


class DockButton(QAbstractButton):
    def __init__(self, title, kind, accent):
        super().__init__()
        self.title, self.kind, self.accent = title, kind, QColor(accent)
        self.setAccessibleName(title)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.compact = False
        self.ui_scale = 1.
        self.setFixedSize(120,128)

    def set_ui_scale(self, scale):
        self.ui_scale = scale
        self.setFixedSize(round((78 if self.compact else 120) * scale),
                          round((80 if self.compact else 128) * scale))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.scale(self.ui_scale, self.ui_scale)
        diameter = 46 if self.compact else 84
        width = self.width() / self.ui_scale
        x, y = (width-diameter)/2, 9
        rect = QRectF(x,y,diameter,diameter)
        gradient = QLinearGradient(rect.topLeft(),rect.bottomRight())
        gradient.setColorAt(0,self.accent.lighter(130)); gradient.setColorAt(1,self.accent.darker(145))
        p.setPen(QPen(QColor("#e7fcff") if self.isChecked() or self.hasFocus() else self.accent,3))
        p.setBrush(gradient if self.kind else QColor("#12334f"))
        p.drawPath(stepped_rect(rect,diameter/4))
        if self.isChecked():
            p.setPen(QPen(self.accent,2)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(stepped_rect(rect.adjusted(-5,-5,5,5),diameter/4))
        p.save(); p.translate(rect.center()); p.scale(diameter/64,diameter/64)
        p.setPen(QPen(QColor("#ffffff"),4,Qt.PenStyle.SolidLine,Qt.PenCapStyle.SquareCap,Qt.PenJoinStyle.MiterJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.kind == 0:
            p.setBrush(QColor("#ffffff")); p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(QPolygonF([QPointF(-19,-2),QPointF(0,-20),QPointF(19,-2),QPointF(14,-2),
                QPointF(14,19),QPointF(4,19),QPointF(4,5),QPointF(-4,5),QPointF(-4,19),QPointF(-14,19),QPointF(-14,-2)]))
        elif self.kind == 1:
            p.drawLine(-17,0,17,0); p.drawLine(0,-17,0,17)
        elif self.kind == 2:
            p.drawPolyline(QPolygonF([QPointF(-19,-12),QPointF(-19,-18),QPointF(-4,-18),QPointF(1,-12),QPointF(19,-12),QPointF(19,17),QPointF(-19,17),QPointF(-19,-12)]))
            p.drawLine(-8,-3,9,-3)
        elif self.kind == 4:
            p.drawPolyline(QPolygonF([QPointF(-16,-2),QPointF(0,-18),QPointF(16,-2)]))
            p.drawLine(0,-18,0,12)
            p.drawPolyline(QPolygonF([QPointF(-18,8),QPointF(-18,19),QPointF(18,19),QPointF(18,8)]))
        else:
            p.drawPolyline(QPolygonF([QPointF(0,17),QPointF(-18,12),QPointF(-18,-16),QPointF(-8,-18),QPointF(0,-12),QPointF(8,-18),QPointF(18,-16),QPointF(18,12),QPointF(0,17),QPointF(0,-12)]))
        p.restore()
        scale = 2
        pixel_text(p,self.title,(width-len(self.title)*6*scale)/2,rect.bottom()+12,scale)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter): self.click()
        else: super().keyPressEvent(event)


class ConsoleNav(QWidget):
    currentRowChanged = Signal(int)
    homeRequested = Signal()

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0,2,0,4)
        layout.setSpacing(12)
        layout.addStretch()
        self.home = DockButton("Home",0,"#00e5ef")
        self.home.setChecked(True)
        self.home.clicked.connect(self.homeRequested)
        layout.addWidget(self.home)
        self.buttons = []
        self.destinations = (0, 1, 3, 2)
        for title, accent, index, kind in (("Create","#ff5268",0,1),("Open","#ffbd35",1,2),
                                          ("Update","#ff5268",3,4),("Guide","#99b5d2",2,3)):
            button = DockButton(title,kind,accent)
            button.clicked.connect(lambda checked=False,idx=index:self.setCurrentRow(idx))
            layout.addWidget(button)
            self.buttons.append(button)
        layout.addStretch()

    def set_compact(self, compact):
        for button in [self.home,*self.buttons]:
            button.compact = compact
            button.set_ui_scale(button.ui_scale)

    def set_ui_scale(self, scale):
        self.setFixedWidth(round(446 * scale))
        for button in [self.home, *self.buttons]:
            button.set_ui_scale(scale)

    def set_theme(self, name):
        colors = THEMES[name]
        for button, accent in zip([self.home,*self.buttons], [colors[0],colors[0],colors[1],colors[0],colors[2]]):
            button.accent = QColor(accent)
            button.update()

    def setCurrentRow(self,index):
        self.home.setChecked(False)
        for destination, button in zip(self.destinations, self.buttons):
            button.setChecked(destination == index)
        self.currentRowChanged.emit(index)

    def clear_selection(self):
        self.home.setChecked(True)
        for button in self.buttons: button.setChecked(False)
