"""Native Windows UI for creating and managing NUP containers."""

from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QDateTime, QEvent, QSettings, QSortFilterProxyModel, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QKeySequence, QPainter, QPalette, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QSpinBox, QTableView, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import UPSTREAM_COMMIT, __version__
from .jobs import JobRunner
from .console import AnimatedStack, AnimatedTabs, ConsoleNav, HomeScreen
from .retro import ArtworkBox, PixelWordmark, ResizeBorder, RetroCanvas, THEMES, TitleBar, WindowButton, pixel_text
from .widgets import FileTableModel, MetadataForm, PathField, human_size
from .sizing import LayoutMetrics, fit_window, scaled_stylesheet
from .discovery import VERSION_FALLBACK_WARNING
from .naming import nup_filename

STYLE = """
QWidget { color: #e5edf5; font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow, QWidget#canvas { background: #12161e; }
QFrame#card { background: #1c222d; border: 1px solid #333c49; border-radius: 16px; }
QFrame#systemBar { background: #12161e; border-bottom: 1px solid #333b48; }
QLabel#wordmark { font-size: 16pt; font-weight: 700; letter-spacing: 3px; color: #f5f7fa; }
QLabel#homeTitle { font-size: 30pt; font-weight: 600; color: #f7f9fc; }
QLabel#homeHint { color: #9eacbf; letter-spacing: 2px; font-size: 9pt; }
QLabel#clock { color: #f3f7fb; font-size: 16pt; font-weight: 600; }
QPushButton#dockButton { background: transparent; border: 1px solid transparent; border-radius: 18px; padding: 8px 17px; }
QPushButton#dockButton:hover { border-color: #69778b; background: #262e3a; }
QPushButton#dockButton:checked { color: #60ddf3; background: #213845; border-color: #4ed6ef; }
QPushButton#homeButton { color: #151b22; background: #f2f5f9; border-color: #f2f5f9; border-radius: 18px; padding: 8px 19px; }
QLabel#brand { font-size: 23pt; font-weight: 700; color: #f5f9fc; }
QLabel#title { font-size: 22pt; font-weight: 600; }
QLabel#section { font-size: 13pt; font-weight: 600; }
QLabel#muted { color: #a5b6ca; }
QLabel#accent { color: #60ddf3; font-weight: 600; }
QLabel#warning { color: #ffd166; }
QLineEdit, QSpinBox, QComboBox { background: #0f1825; border: 1px solid #3a4b63; border-radius: 5px; padding: 8px; selection-background-color: #216b65; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid #60ddf3; }
QLineEdit:disabled, QComboBox:disabled { color: #697e95; background: #151e2b; }
QComboBox QAbstractItemView { background: #172130; selection-background-color: #24534f; }
QPushButton { background: #2b3442; border: 1px solid #48576b; border-radius: 10px; padding: 10px 18px; font-weight: 600; }
QPushButton:hover { background: #2e435d; border-color: #7a93af; }
QPushButton:pressed { background: #142335; }
QPushButton:disabled { color: #687d92; border-color: #28364a; background: #182333; }
QPushButton#primary { background: #5bdcf2; border-color: #5bdcf2; color: #10252c; }
QPushButton#primary:hover { background: #8beafa; }
QPushButton#primary:disabled { background: #244e4d; border-color: #244e4d; color: #7b9e9b; }
QTabWidget::pane { border: none; padding-top: 14px; }
QTabBar::tab { background: #1c232e; color: #adc0d4; padding: 12px 19px; border-bottom: 3px solid #343e4d; }
QTabBar::tab:selected { color: #f7f9fc; border-bottom: 3px solid #ff8679; }
QTableWidget, QTableView, QTreeWidget, QListWidget, QPlainTextEdit, QTextBrowser { background: #101a28; border: 1px solid #2e4058; border-radius: 5px; alternate-background-color: #162232; selection-background-color: #24534f; gridline-color: #25364b; }
QListWidget::item { padding: 8px; }
QHeaderView::section { background: #1d2d41; color: #b7cadc; padding: 9px; border: none; border-right: 1px solid #2a3d54; }
QTableWidget::item, QTreeWidget::item { padding: 5px; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; }
QProgressBar { background: #1c2b3e; border: none; border-radius: 4px; height: 8px; text-align: center; }
QProgressBar::chunk { background: #5bdcf2; border-radius: 4px; }
QScrollArea { background: transparent; border: none; }
QWidget#scrollContent { background: #12161e; }
QScrollBar:vertical { background: #142032; width: 11px; }
QScrollBar::handle:vertical { background: #3c516b; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #22364c; color: #ecf5fd; border: 1px solid #4e6c8a; padding: 6px; }
"""

# Keep form text readable while the shell uses native pixel lettering and sprites.
STYLE += """
QWidget { font-family: 'Consolas'; font-size: 10pt; color: #eef3ff; }
QMainWindow { background: #0b1127; }
QFrame#systemBar { background: transparent; border: none; }
QFrame#card { background: #17233c; border: 2px solid #425778; border-radius: 3px; }
QLabel#title { font-family: 'Consolas'; font-size: 23pt; font-weight: 700; color: #f5f7ff; }
QLabel#section { font-family: 'Consolas'; font-size: 13pt; font-weight: 700; }
QLabel#muted { color: #b1c1dd; }
QLabel#accent { color: #00e5ef; }
QLabel#homeHint { font-family: 'Consolas'; letter-spacing: 1px; color: #879bbd; font-size: 9pt; }
QLabel#artworkBox { background: #101a31; color: #00e5ef; border: 4px solid #00e5ef; padding: 5px; }
QPushButton { border-radius: 2px; border: 2px solid #50658c; background: #263553; padding: 9px 14px; }
QPushButton:hover { border-color: #00e5ef; background: #344c72; }
QPushButton:pressed { background: #0a162e; padding-top: 11px; padding-bottom: 7px; }
QPushButton#primary { background: #00e5ef; color: #091e2c; border-color: #85ffff; }
QPushButton#primary:hover { background: #80ffff; }
QPushButton#windowControl, QPushButton#windowClose { background: #1f2c49; border: 2px solid #445679; padding: 0; }
QPushButton#windowControl:hover { background: #345273; border-color: #00e5ef; }
QPushButton#windowClose:hover { background: #b82d48; border-color: #ff5268; }
QLineEdit, QSpinBox, QComboBox { background: #0d1830; border: 2px solid #3b5076; border-radius: 2px; padding: 7px; selection-background-color: #365b80; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 2px solid #00e5ef; }
QTabBar::tab { background: #1b2946; border-bottom: 4px solid #34476a; padding: 10px 15px; }
QTabBar::tab:selected { background: #28385b; border-bottom-color: #ff5268; color: #ffffff; }
QTableWidget, QTableView, QTreeWidget, QListWidget, QPlainTextEdit, QTextBrowser { background: #0f1b32; border: 2px solid #344b70; border-radius: 0; alternate-background-color: #16243e; selection-background-color: #31577b; }
QHeaderView::section { background: #263755; color: #d0e1fa; padding: 8px; }
QWidget#scrollContent { background: #111e37; }
QProgressBar { border: 2px solid #456080; background: #101d34; border-radius: 0; min-height: 16px; }
QProgressBar::chunk { background: #ff5268; border: none; border-radius: 0; }
QCheckBox::indicator { background: #0c1830; border: 2px solid #527091; }
QCheckBox::indicator:checked { background: #00e5ef; border: 3px solid #b2ffff; }
"""


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    if primary:
        widget.setObjectName("primary")
    return widget


def page(title, subtitle):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(32, 18, 32, 14)
    layout.setSpacing(16)
    layout.addWidget(label(title, "title"))
    layout.addWidget(label(subtitle, "muted", True))
    return widget, layout


def card(title):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    layout.addWidget(label(title, "section"))
    return frame, layout


def scroll(widget):
    widget.setObjectName("scrollContent")
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    return area


def app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.fillRect(4, 4, 56, 56, QColor("#ff5268"))
    painter.fillRect(8, 8, 48, 4, QColor("#ffd0d6"))
    pixel_text(painter, "N", 19, 18, 5, "#10172d")
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.setWindowTitle("NS2 NUP Tool")
        self.setWindowIcon(app_icon())
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        fit_window(self, (1440, 1040), (840, 560))
        self.ui_scale = None
        self.setAcceptDrops(True)
        self.settings = settings if settings is not None else QSettings("NS2 NUP Tool", "NS2 NUP Tool")
        self.runner = JobRunner(self)
        self.runner.busy_changed.connect(self.set_busy)
        self.runner.progress.connect(self.show_progress)
        self.runner.finished.connect(self.job_finished)
        self.current = None
        self.last_output = None
        self.close_when_done = False
        self.preview = None
        self.auto_title_id = ""
        self._pack_after_scan = False
        self._launch_review_key = None
        self.suggested_output = ""
        canvas = self.canvas = RetroCanvas()
        root = QVBoxLayout(canvas)
        root.setContentsMargins(18, 6, 18, 16)
        root.setSpacing(0)
        self.setCentralWidget(canvas)
        root.addWidget(self.make_system_bar())
        self.pages = AnimatedStack()
        self.pages.addWidget(self.make_pack_page())
        self.pages.addWidget(self.make_open_page())
        self.pages.addWidget(self.make_help_page())
        self.home_screen = HomeScreen()
        self.home_screen.selected.connect(self.nav.setCurrentRow)
        self.shell_pages = AnimatedStack()
        self.shell_pages.addWidget(self.home_screen)
        self.shell_pages.addWidget(self.pages)
        self.nav.currentRowChanged.connect(self.open_section)
        self.nav.homeRequested.connect(self.show_home)
        root.addWidget(self.shell_pages, 1)
        root.addWidget(self.make_status())
        self.reduce_motion.toggled.connect(self.change_motion)
        self.reduce_motion.setChecked(str(self.settings.value("reduced_motion", "false")).lower() == "true")
        self.change_motion(self.reduce_motion.isChecked())
        self.apply_theme()
        self.home_shortcut = QShortcut(QKeySequence("Alt+Home"), self)
        self.home_shortcut.activated.connect(self.show_home)
        self.source.setText(self.settings.value("source", ""))
        self.container.setText(self.settings.value("container", ""))
        self.resize_border = ResizeBorder(self)
        self.resize_border.fit()
        self.layout_metrics = LayoutMetrics(canvas)
        self.scale_timer = QTimer(self)
        self.scale_timer.setSingleShot(True)
        self.scale_timer.setInterval(60)
        self.scale_timer.timeout.connect(self.apply_ui_scale)
        self.apply_ui_scale()
        self.home_screen.tiles[0].setFocus()

    def make_system_bar(self):
        bar = TitleBar()
        bar.setObjectName("systemBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 10, 12)
        self.wordmark = PixelWordmark()
        layout.addWidget(self.wordmark)
        self.nav = ConsoleNav()
        self.nav.set_compact(True)
        self.nav.setFixedWidth(446)
        layout.addWidget(self.nav)
        layout.addStretch()
        self.reduce_motion = QCheckBox("Reduce motion")
        layout.addWidget(self.reduce_motion)
        layout.addSpacing(8)
        self.minimize_button = WindowButton("min", self.showMinimized)
        self.maximize_button = WindowButton("max", self.toggle_maximized)
        self.close_button = WindowButton("close", self.close)
        for control in (self.minimize_button, self.maximize_button, self.close_button):
            layout.addWidget(control)
        return bar

    def toggle_maximized(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "resize_border"):
            self.resize_border.fit()
        if hasattr(self, "scale_timer"):
            self.scale_timer.start()

    def apply_ui_scale(self):
        scale = round(max(.65, min(1.5, self.width() / 1440, self.height() / 1040)), 3)
        if scale == self.ui_scale:
            return
        self.ui_scale = scale
        for stack in (self.pages, self.shell_pages, self.pack_tabs, self.open_tabs):
            stack.finish_transition()
        self.setStyleSheet(scaled_stylesheet(self.theme_style, scale))
        self.layout_metrics.apply(scale)
        self.wordmark.set_ui_scale(scale)
        self.nav.set_ui_scale(scale)
        self.home_screen.set_ui_scale(scale)
        for widget in self.findChildren(WindowButton) + self.findChildren(ArtworkBox):
            widget.set_ui_scale(scale)
        for field in self.findChildren(PathField):
            field.button.setFixedWidth(max(80, round(96 * scale)))
        for form in (self.pack_metadata, self.edit_metadata):
            form.locales.setMinimumHeight(round(130 * scale))
            form.locales.setMaximumHeight(round(210 * scale))
            form.locales.verticalHeader().setDefaultSectionSize(max(38, round(44 * scale)))
            for action in form.actions.values():
                action.setFixedWidth(max(76, round(90 * scale)))
        self.level.setMaximumWidth(round(130 * scale))
        self.packages.setMinimumHeight(round(150 * scale))
        self.scan_warnings.setMaximumHeight(round(95 * scale))
        self.tree.setMinimumHeight(round(180 * scale))
        self.log.setMaximumHeight(round(120 * scale))

    def apply_theme(self):
        name = "Classic Red"
        accent, secondary, _ = THEMES[name]
        self.theme_style = STYLE.replace("#00e5ef", accent).replace("#ff5268", secondary)
        self.setStyleSheet(self.theme_style)
        self.canvas.accent = QColor(accent)
        self.canvas.update()
        self.home_screen.set_theme(name)
        self.nav.set_theme(name)
        self.settings.setValue("theme", name)

    def open_section(self, index):
        self.pages.transition_style = self.shell_pages.transition_style = index
        updating = index == 3
        self.open_heading.setText("Update a NUP" if updating else "Open a NUP")
        self.open_description.setText("Open your existing NUP, choose a newer update, and save the updated copy." if updating
                                      else "Browse, add newer updates, extract, edit metadata, or verify a container.")
        self.pages.setCurrentIndex(1 if updating else index)
        if updating:
            self.open_tabs.setCurrentIndex(5)
        self.shell_pages.setCurrentIndex(1)

    def show_home(self):
        self.nav.clear_selection()
        self.shell_pages.setCurrentIndex(0)
        self.home_screen.tiles[0].setFocus(Qt.FocusReason.ShortcutFocusReason)

    def change_motion(self, reduced):
        self.canvas.motion = not reduced
        self.pages.motion = self.shell_pages.motion = not reduced
        self.home_screen.set_motion(not reduced)
        for stack in (self.pages, self.shell_pages, self.pack_tabs, self.open_tabs):
            stack.motion = not reduced
            if reduced:
                stack.finish_transition()
        self.settings.setValue("reduced_motion", reduced)

    def make_pack_page(self):
        widget, layout = page("Create a NUP", "Bring your base game, updates, and add-ons together in one container.")
        self.pack_tabs = AnimatedTabs()
        layout.addWidget(self.pack_tabs, 1)
        source_tab = QWidget()
        source_layout = QVBoxLayout(source_tab)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(16)
        frame, fields = card("Choose your decrypted dump")
        self.source = PathField("folder", "Drop a dump folder here, or browse…")
        self.source.edit.textChanged.connect(self.source_changed)
        self.source.pathChosen.connect(lambda _: self.scan())
        self.source.edit.editingFinished.connect(self.scan_if_needed)
        self.output = PathField("save", "Save outside the source dump folder", "NUP containers (*.nup)")
        self.title_override = QLineEdit()
        self.title_override.setPlaceholderText("Auto-detect from main.npdm · optional 16-digit hex override")
        self.title_override.textChanged.connect(self.invalidate_preview)
        self.title_override.textChanged.connect(self.update_output_suggestion)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Dump folder", self.source)
        form.addRow("Output NUP", self.output)
        form.addRow("Title ID", self.title_override)
        self.bundle_update_version = QLineEdit()
        self.bundle_update_version.setPlaceholderText("Auto-detected numeric version, or 0 when unavailable")
        self.bundle_update_version.textChanged.connect(self.invalidate_preview)
        self.bundle_update_version.editingFinished.connect(self.scan_if_needed)
        form.addRow("Update version", self.bundle_update_version)
        self.source_form = form
        form.setRowVisible(self.bundle_update_version, False)
        fields.addLayout(form)
        self.bundle_version_warning = label(VERSION_FALLBACK_WARNING, "warning", True)
        self.bundle_version_warning.hide()
        fields.addWidget(self.bundle_version_warning)
        self.bundle_layout_notice = label("", "warning", True)
        self.bundle_layout_notice.hide()
        fields.addWidget(self.bundle_layout_notice)
        fields.addWidget(label("Select the folder containing base / updates / dlc, or a single folder containing exefs / romfs.", "muted", True))
        actions = QHBoxLayout()
        actions.addWidget(button("Scan packages", self.scan, True))
        actions.addWidget(button("Find missing info online…", self.find_store_metadata))
        actions.addStretch()
        actions.addWidget(button("See folder layout", lambda: self.nav.setCurrentRow(2)))
        fields.addLayout(actions)
        self.auto_store_lookup = QCheckBox("Auto-fill missing fields from Nintendo eShop")
        self.auto_store_lookup.setToolTip("After scanning, look for an exact title-ID match and fill missing fields automatically.")
        self.auto_store_lookup.setChecked(str(self.settings.value("auto_store_lookup", "true")).lower() == "true")
        self.auto_store_lookup.toggled.connect(lambda checked: self.settings.setValue("auto_store_lookup", checked))
        fields.addWidget(self.auto_store_lookup)
        self.auto_store_status = label("Automatic lookup uses the detected title ID and available title text; game files stay local.", "muted", True)
        fields.addWidget(self.auto_store_status)
        source_layout.addWidget(frame)
        self.scan_summary = label("Scan the folder to preview exactly which packages will be included.", "muted", True)
        source_layout.addWidget(self.scan_summary)
        detected = QHBoxLayout()
        self.detected_art = ArtworkBox(192)
        self.detected_text = label("Scan reads title ID, artwork, names and publisher, and sets V<newest update number> or V0.", "muted", True)
        detected.addWidget(self.detected_art)
        detected.addWidget(self.detected_text, 1)
        source_layout.addLayout(detected)
        self.packages = QTableWidget(0, 6)
        self.packages.setHorizontalHeaderLabels(["Kind", "Title ID", "Version", "Files", "Size", "Source"])
        self.packages.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.packages.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.packages.verticalHeader().hide()
        self.packages.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.packages.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.packages.setMinimumHeight(150)
        source_layout.addWidget(self.packages, 1)
        self.scan_warnings = QPlainTextEdit()
        self.scan_warnings.setReadOnly(True)
        self.scan_warnings.setMaximumHeight(95)
        self.scan_warnings.setPlaceholderText("Skipped folders and discovery notices will appear here.")
        source_layout.addWidget(self.scan_warnings)
        source_layout.addWidget(button("Next: metadata →", lambda: self.pack_tabs.setCurrentIndex(1)))
        self.pack_tabs.addTab(scroll(source_tab), "1   Source && packages")

        metadata_tab = QWidget()
        metadata_layout = QVBoxLayout(metadata_tab)
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        frame, fields = card("Make the package easy to recognize")
        fields.addWidget(label("Scan fills available metadata automatically. Edit any field below to override it. Metadata goes on the base or first package.", "muted", True))
        self.pack_metadata = MetadataForm()
        self.pack_metadata.fields["icon"].edit.textChanged.connect(self.update_artwork)
        for field in self.pack_metadata.fields.values():
            edit = field.edit if isinstance(field, PathField) else field
            edit.textChanged.connect(self.refresh_metadata_summary)
        fields.addWidget(self.pack_metadata)
        fields.addWidget(button("Find missing info on Nintendo eShop…", self.find_store_metadata))
        metadata_layout.addWidget(frame)
        metadata_layout.addStretch()
        metadata_layout.addWidget(button("Next: compression && create →", lambda: self.pack_tabs.setCurrentIndex(2)))
        self.pack_tabs.addTab(scroll(metadata_tab), "2   Names && artwork")

        create_tab = QWidget()
        create_layout = QVBoxLayout(create_tab)
        create_layout.setContentsMargins(0, 0, 0, 0)
        frame, options = card("Compression & integrity")
        self.level = QSpinBox()
        self.level.setRange(-5, 22)
        self.level.setValue(3)
        self.level.setMaximumWidth(130)
        form = QFormLayout()
        form.addRow("Zstandard level", self.level)
        options.addLayout(form)
        options.addWidget(label("3 is the upstream default. Lower levels favor speed; higher levels use more time and memory. Files that do not shrink are stored raw.", "muted", True))
        self.keep_listings = QCheckBox("Include dump-tool .listing files")
        self.keep_listings.setChecked(False)
        self.keep_listings.toggled.connect(self.invalidate_preview)
        self.verify_after = QCheckBox("Verify every file's SHA-256 after packing (recommended)")
        self.verify_after.setChecked(True)
        options.addWidget(self.keep_listings)
        options.addWidget(self.verify_after)
        self.prefer_update_executable = QCheckBox("Replace base with update ExeFS and RomFS")
        self.prefer_update_executable.setEnabled(False)
        self.prefer_update_executable.clicked.connect(self.review_launch_choice)
        self.prefer_update_executable.toggled.connect(self.update_create_summary)
        options.addWidget(self.prefer_update_executable)
        self.launch_hint = label("Scan a dump to check whether an update contains its own main executable.", "muted", True)
        options.addWidget(self.launch_hint)
        options.addWidget(label("The container structure and TOC hash are always checked before saving. Source files are read in chunks; temporary data uses the output drive.", "muted", True))
        create_layout.addWidget(frame)
        summary, fields = card("Ready when you are")
        self.create_summary = label("Choose a dump folder and an output filename on the Source tab.", None, True)
        self.create_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fields.addWidget(self.create_summary)
        fields.addWidget(label("Existing output files are never overwritten. Build IDs and available NPDM metadata are carried through automatically.", "muted", True))
        fields.addWidget(button("Create NUP", self.pack, True))
        create_layout.addWidget(summary)
        create_layout.addStretch()
        self.output.edit.textChanged.connect(self.update_create_summary)
        self.pack_tabs.addTab(scroll(create_tab), "3   Compression && create")
        return widget

    def make_open_page(self):
        widget, layout = page("Open a NUP", "Browse, add newer updates, extract, edit metadata, or verify a container.")
        self.open_heading = layout.itemAt(0).widget()
        self.open_description = layout.itemAt(1).widget()
        row = QHBoxLayout()
        self.container = PathField("file", "Choose an existing .nup", "NUP containers (*.nup);;All files (*)")
        self.container.pathChosen.connect(lambda _: self.inspect())
        row.addWidget(self.container, 1)
        row.addWidget(button("Open", self.inspect, True))
        layout.addLayout(row)
        self.open_summary = label("No container loaded. Drop a .nup file onto the window to open it.", "muted", True)
        layout.addWidget(self.open_summary)
        layout.addWidget(label("Selected Package", "section"))
        self.package_choice = QComboBox()
        self.package_choice.setAccessibleName("Selected Package")
        self.package_choice.currentIndexChanged.connect(self.package_changed)
        layout.addWidget(self.package_choice)
        self.open_tabs = AnimatedTabs()
        self.open_tabs.setEnabled(False)
        layout.addWidget(self.open_tabs, 1)

        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        top = QHBoxLayout()
        self.icon_preview = ArtworkBox(256)
        top.addWidget(self.icon_preview, 0, Qt.AlignmentFlag.AlignTop)
        details_column = QVBoxLayout()
        self.package_details = label("", None, True)
        self.package_details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_column.addWidget(self.package_details)
        top.addLayout(details_column, 1)
        overview_layout.addLayout(top, 1)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Package tree", "Original size", "Codec"])
        self.tree.setColumnWidth(0, 400)
        self.tree.itemExpanded.connect(self.expand_tree)
        self.tree.setMinimumHeight(180)
        details_column.addWidget(self.tree, 1)
        self.open_tabs.addTab(scroll(overview), "Overview && tree")

        files = QWidget()
        file_layout = QVBoxLayout(files)
        file_layout.addWidget(label("All file nodes across all packages. Use the tree to view their paths.", "muted", True))
        self.file_filter = QLineEdit()
        self.file_filter.setPlaceholderText("Filter filenames…")
        self.file_filter.textChanged.connect(self.filter_files)
        file_layout.addWidget(self.file_filter)
        self.file_table = QTableView()
        self.file_table.setAlternatingRowColors(True)
        self.file_table.setSortingEnabled(True)
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        file_layout.addWidget(self.file_table)
        self.open_tabs.addTab(files, "File list")

        extract = QWidget()
        extract_layout = QVBoxLayout(extract)
        frame, fields = card("Extract NUP contents")
        self.extract_scope = QComboBox()
        self.extract_scope.addItem("Entire NUP — base, updates and DLC (recommended)", "all")
        self.extract_scope.addItem("Selected package only", "package")
        fields.addWidget(self.extract_scope)
        self.extract_hint = label("", "muted", True)
        fields.addWidget(self.extract_hint)
        self.extract_output = PathField("folder", "Choose a parent folder, then add a new folder name")
        self.extract_output.button.clicked.disconnect()
        self.extract_output.button.clicked.connect(self.choose_extract_parent)
        self.subtree = QLineEdit()
        self.subtree.setPlaceholderText("Entire package · or exefs, romfs, romfs/data…")
        form = QFormLayout()
        form.addRow("New output folder", self.extract_output)
        form.addRow("Subtree (optional)", self.subtree)
        fields.addLayout(form)
        fields.addWidget(label("Choose a folder that does not exist yet. It appears only after extraction completes successfully.", "muted", True))
        self.extract_button = button("Extract entire NUP", self.extract, True)
        fields.addWidget(self.extract_button)
        self.extract_scope.currentIndexChanged.connect(self.extraction_scope_changed)
        self.extraction_scope_changed()
        extract_layout.addWidget(frame)
        extract_layout.addStretch()
        self.open_tabs.addTab(scroll(extract), "Extract")

        edit = QWidget()
        edit_layout = QVBoxLayout(edit)
        edit_layout.addWidget(label("Change metadata on the selected package. Content, title ID, numeric version, build ID, and provenance are preserved.", "muted", True))
        self.edit_metadata = MetadataForm(editing=True)
        edit_layout.addWidget(self.edit_metadata)
        self.edit_output = PathField("save", "Save an edited copy", "NUP containers (*.nup)")
        edit_layout.addWidget(self.edit_output)
        self.edit_inplace = QCheckBox("Replace the original after validating the edited file")
        self.edit_inplace.toggled.connect(lambda checked: self.edit_output.setEnabled(not checked))
        edit_layout.addWidget(self.edit_inplace)
        edit_layout.addWidget(button("Save metadata changes", self.edit, True))
        edit_layout.addStretch()
        self.open_tabs.addTab(scroll(edit), "Edit metadata")

        verify = QWidget()
        verify_layout = QVBoxLayout(verify)
        frame, fields = card("Check this container")
        self.deep_verify = QCheckBox("Full verification: recompute every file's SHA-256")
        self.deep_verify.setChecked(True)
        fields.addWidget(self.deep_verify)
        fields.addWidget(label("With this unchecked, verification checks structure and the TOC hash only. It does not validate payload content.", "muted", True))
        self.max_problems = QSpinBox()
        self.max_problems.setRange(1, 10000)
        self.max_problems.setValue(20)
        form = QFormLayout()
        form.addRow("Maximum listed problems", self.max_problems)
        fields.addLayout(form)
        fields.addWidget(button("Verify container", self.verify, True))
        self.verify_result = QPlainTextEdit()
        self.verify_result.setReadOnly(True)
        self.verify_result.setPlaceholderText("Verification results will appear here.")
        fields.addWidget(self.verify_result, 1)
        verify_layout.addWidget(frame, 1)
        self.open_tabs.addTab(verify, "Verify")
        self.open_tabs.addTab(self.make_updates_tab(), "Add updates")
        return widget

    def make_updates_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        frame, fields = card("Give this game its next update")
        fields.addWidget(label("Replace this game's older updates with the newest update. The base game, DLC, and their metadata are preserved. The original NUP stays unchanged.", "muted", True))
        self.update_source = PathField("folder", "Decrypted update folder, update-only bundle, or update NUP")
        self.update_source.edit.textChanged.connect(self.update_source_changed)
        self.update_source.pathChosen.connect(lambda _: self.preview_updates())
        fields.addWidget(self.update_source)
        fields.addWidget(button("Browse update NUP…", self.choose_update_nup))
        self.update_version = QLineEdit()
        self.update_version.setPlaceholderText("Filled automatically; defaults to 0 when unavailable")
        self.update_version.textChanged.connect(self.invalidate_update_plan)
        self.update_version.editingFinished.connect(self.check_update_version_if_needed)
        self.update_output = PathField("save", "Save a new updated copy", "NUP containers (*.nup)")
        form = QFormLayout()
        form.addRow("Numeric version", self.update_version)
        self.update_version_warning = label("", "warning", True)
        form.addRow(self.update_version_warning)
        self.update_version_warning.hide()
        form.addRow("Updated NUP", self.update_output)
        fields.addLayout(form)
        fields.addWidget(button("Recheck update", self.preview_updates))
        self.update_plan_text = label("Browse to an update to check its game ID and fill its version automatically.", "muted", True)
        fields.addWidget(self.update_plan_text)
        self.confirm_update_identity = QCheckBox("I checked that this update belongs to this game (its title ID is unavailable)")
        self.confirm_update_identity.setVisible(False)
        self.confirm_update_identity.toggled.connect(self.update_add_enabled)
        fields.addWidget(self.confirm_update_identity)
        fields.addWidget(label("Only the newest incoming update is included. Previous update packages are removed from the saved copy. Retained game data is copied without recompression, then every file is SHA-256 verified.", "muted", True))
        self.add_update_button = button("Replace update && save new NUP", self.add_updates, True)
        self.add_update_button.setEnabled(False)
        fields.addWidget(self.add_update_button)
        layout.addWidget(frame)
        layout.addStretch()
        self.update_preview = None
        return scroll(widget)

    def invalidate_update_plan(self):
        self.update_preview = None
        if hasattr(self, "update_plan_text"):
            self.update_plan_text.setText("Choose an update with Browse to check it automatically, or use Recheck update for a pasted path.")
            self.confirm_update_identity.setChecked(False)
            self.confirm_update_identity.hide()
            self.add_update_button.setEnabled(False)
            self.update_version_warning.hide()

    def update_source_changed(self):
        if hasattr(self, "update_version"):
            self.update_version.clear()
        self.invalidate_update_plan()

    def check_update_version_if_needed(self):
        if self.current and self.update_source.text() and self.update_version.text().strip() and self.update_preview is None:
            self.preview_updates()

    def choose_update_nup(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Choose update-only NUP", "", "NUP containers (*.nup)")
        if path:
            self.update_source.setText(path)
            self.preview_updates()

    def update_request(self):
        return {"file": self.current["path"], "update_source": self.update_source.text(),
                "update_version": self.update_version.text().strip()}

    def preview_updates(self):
        if self.current and not self.runner.busy:
            self.invalidate_update_plan()
            self.start_job("preview_updates", self.update_request())

    def update_add_enabled(self):
        self.add_update_button.setEnabled(bool(self.update_preview) and
            (not self.update_preview["requires_confirmation"] or self.confirm_update_identity.isChecked()))

    def add_updates(self):
        if self.current and self.update_preview:
            self.start_job("add_updates", {**self.update_request(), "output": self.update_output.text(),
                "confirm_identity": self.confirm_update_identity.isChecked()})

    def make_help_page(self):
        widget, layout = page("Folder layout & help", "The complete NUP workflow, powered by our GPLv3 format implementation.")
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(f"""
        <style>body {{font-family:'Segoe UI'; color:#dbe8f5;}} h2 {{color:#6de6d0;}}
        pre {{background:#17283b; padding:16px;}} a {{color:#71e3d1;}} p,li {{line-height:1.5;}}</style>
        <h2>Start with decrypted content</h2>
        <p>Select a dump folder containing extracted <b>exefs</b> and/or <b>romfs</b> directories.
        Encrypted NSP/XCI/NCA files are not converted or decrypted by this app.</p>
        <pre>My Game/\n  base/\n    exefs/\n    romfs/\n  updates/\n    458752/\n      exefs/\n      romfs/\n  dlc/\n    040074a01bf13001/\n      0/\n        romfs/</pre>
        <p>Update directory names are <b>decimal numeric versions</b>, not display versions like 1.2.3.
        DLC title directories use exactly <b>16 hex digits</b>. Each index folder contains its content tree.
        A folder containing exefs/romfs directly becomes a single base package. A folder with updates/ but no base/
        produces standalone update packages. Invalid layout entries are skipped by discovery and listed in Scan notices.</p>
        <h2>Create</h2>
        <ol><li>Choose the dump and an output outside it. Scan to review packages, IDs, counts, and skipped entries.</li>
        <li>Scan fills available control metadata and artwork. Review or edit the results.</li>
        <li>Use Find missing info online to search Nintendo US or paste a product URL. Preview the match and artwork,
        then fill missing fields. The lookup preserves scanned values and manual edits; it can replace a folder-name suggestion.</li>
        <li>Choose compression and create. Full SHA-256 verification is enabled by default.</li></ol>
        <p>The title ID comes from main.npdm when available. An explicit override applies to the base and is the fallback
        for updates without an ID; DLC IDs come from their folder names. A display version is metadata and does not change
        a package's numeric version. Build IDs are read automatically from supported main executable headers.</p>
        <p>Control metadata is read from decrypted control.nacp and standard icon files. When several versions exist,
        the newest update's metadata takes priority. Missing original metadata cannot always be reconstructed.
        The version field defaults to V followed by the newest included numeric update version, or V0 without an update.
        The shop supplies names, publisher, artwork, and sometimes the exact application ID. A mismatched application ID blocks import.</p>
        <p>Automatic shop lookup is enabled on the Source tab. After scanning it searches by the detected title ID,
        then available title text, and fills missing name, publisher and artwork only on an exact application-ID match.
        If no exact match is found, use Find missing info online to search by game title and select a result.</p>
        <p>Online lookup is optional. Only the search text and public webpage/image requests leave the computer.
        Downloaded artwork is stored in the local app cache, with a source link. No game files are uploaded.</p>
        <h2>Browse, extract, edit, verify</h2>
        <p><b>Replace base with update ExeFS and RomFS</b> is on Compression &amp; create. When an update contains
        main, Create asks whether to use its content as the base or keep standard loading. Enabling it replaces the
        base content with only the selected update's exefs/ and romfs/ folders. Original base-only files are omitted;
        a missing update RomFS remains absent. The update package and DLC stay included. Source files are not
        overwritten. NPDM and build ID come from the update. This changes actual packaged content;
        emulator behavior and game compatibility still depend on its loader.</p>
        <p>The choice is recorded for this tool, displayed in the package overview, and maintained when you later
        replace the update. It resets for a different dump. Cancel in the question stops before creating output.</p>
        <p>Extract defaults to the entire NUP, restoring base/, updates/&lt;version&gt;/ and dlc/&lt;title ID&gt;/&lt;index&gt;/.
        Choose the extracted parent folder in Create to repack every package. Keep the .ns2-nup metadata folder alongside
        them to preserve package identities, icons and other NUP metadata. Selected package only remains available,
        including optional subtree extraction. Every extracted file is SHA-256 verified.</p>
        <p>Metadata editing starts with every action set to Keep. Choose Set or Clear for the fields you want to change.
        Save to a new copy, or enable replacement of the original. Package content and identity are preserved.
        Fast verification checks structure and TOC; full verification also hashes content.</p>
        <h2>Add newer updates later</h2>
        <p>Choose <b>Update NUP</b> on Home or <b>Update</b> beside the title, then open an existing NUP.
        Browse to a decrypted update folder,
        an update-only bundle containing updates/&lt;numeric version&gt;/, or an update-only NUP.
        A numeric folder name or readable executable version supplies the decimal version automatically.</p>
        <p>Choosing an update with Browse checks it and fills its numeric version automatically. Use Recheck update
        for a pasted path. A different game is rejected; known nonzero duplicate or older versions are rejected too.
        If no ID is available, explicitly confirm the game match.
        Save to a new NUP filename. The newest incoming update replaces this game's previous update packages;
        older incoming versions are ignored. Base and DLC content is kept, and the base and new update display version
        is refreshed to V followed by the new numeric version. Other retained metadata is kept.
        Retained compressed content is copied unchanged; only new decrypted content needs compression.
        Every file is fully verified before the new copy appears. The original NUP is never replaced by this workflow.</p>
        <p>A single update directly inside updates/exefs or updates/romfs is supported too. If its numeric version
        cannot be read, the app fills <b>0</b>, displays <b>V0</b>, and shows a warning beside the field.
        V0 is a placeholder, not a detected release. You can create or update the NUP with it, or enter the actual
        numeric version if known. Update order cannot be verified for V0; saving replaces the existing update with
        the selected content. The original NUP remains unchanged.</p>
        <p>When creating a NUP from a flat updates/ folder, the app fixes the source dump itself:
        all update content moves into updates/&lt;Update version&gt;/ before packing. Scan previews the move.
        Successful creation keeps the corrected folders; an error or cooperative cancellation restores the old layout.
        Already numbered dumps are left alone. Conflicting layouts are rejected for review.</p>
        <h2>Retro menu &amp; motion</h2>
        <p>The Classic Red top bar has navigation and window controls. Drag the title area to move the window,
        double-click it to maximize or restore, or drag an edge to resize. Use Home/Create/Open/Update/Guide beside the title,
        or Alt+Home. Page changes slide and fade in both directions. Reduce motion disables transitions and idle movement.</p>
        <p>The taller starting window fits your available desktop. Controls, text, spacing and artwork scale with
        the window, while Windows display scaling is handled separately. Longer forms remain scrollable.</p>
        <h2>Large dumps & cancellation</h2>
        <p>File contents are streamed in 4 MiB chunks. Compression still uses Zstandard's level-dependent memory.
        Packing reserves a conservative disk-space allowance for the uncompressed input plus its largest file.
        Metadata editing needs room for another container. Extraction needs room for uncompressed content.</p>
        <p>Cancel is cooperative; the current chunk completes before cleanup. New output files and extracted folders
        are published only on success. A power loss or forced process termination may leave a hidden temporary folder
        beside the intended output. It is never presented as a finished NUP.</p>
        <h2>Compatibility</h2>
        <p>NUP format credit: <a href="https://github.com/a55uka/nup">a55uka/nup</a>, specification revision {UPSTREAM_COMMIT[:12]}.
        NS2 NUP Tool uses its own GPLv3 implementation, with Windows-safe transactions, streaming payload I/O,
        and validation for extraction filenames. No upstream implementation code is bundled. Containers target NUP v1.
        Packaging and hash verification do not establish game or emulator compatibility.</p>
        <p><a href="https://github.com/a55uka/nup/blob/{UPSTREAM_COMMIT}/README.md">Upstream README</a> &nbsp;·&nbsp;
        <a href="https://github.com/a55uka/nup/blob/{UPSTREAM_COMMIT}/SPEC.md">Format specification</a></p>
        """)
        layout.addWidget(browser, 1)
        return widget

    def make_status(self):
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 12, 18, 12)
        row = QHBoxLayout()
        self.status = label("Ready", "accent", True)
        self.status.setMinimumWidth(100)
        row.addWidget(label("●", "accent"))
        row.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setTextVisible(False)
        layout.addLayout(row)
        actions = QHBoxLayout()
        actions.addWidget(self.progress, 1)
        self.reveal_button = button("Show output", self.reveal_output)
        self.reveal_button.setEnabled(False)
        actions.addWidget(self.reveal_button)
        self.cancel_button = button("Cancel", self.cancel)
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.cancel_button)
        self.log_button = button("Show log", self.toggle_log)
        actions.addWidget(self.log_button)
        layout.addLayout(actions)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        self.log.document().setMaximumBlockCount(2000)
        self.log.hide()
        layout.addWidget(self.log)
        return frame

    def source_changed(self):
        self._launch_review_key = None
        if hasattr(self, "prefer_update_executable"):
            self.prefer_update_executable.setChecked(False)
            self.prefer_update_executable.setEnabled(False)
        self.shop_metadata = None
        if hasattr(self, "auto_store_status"):
            self.auto_store_status.setText("Scan this dump to check Nintendo eShop automatically.")
        if hasattr(self, "bundle_update_version"):
            self.bundle_update_version.clear()
            self.source_form.setRowVisible(self.bundle_update_version, False)
            self.bundle_version_warning.hide()
            self.bundle_layout_notice.hide()
        if not hasattr(self, "output"):
            return
        if hasattr(self, "pack_metadata"):
            self.pack_metadata.clear_detected()
            self.detected_text.setText("Scan to read metadata from this dump. Manual overrides are preserved.")
        if self.auto_title_id and self.title_override.text() == self.auto_title_id:
            self.title_override.clear()
        self.auto_title_id = ""
        self.update_output_suggestion()
        self.invalidate_preview()

    def update_output_suggestion(self, *_):
        if not hasattr(self, "pack_metadata"):
            return
        source = Path(self.source.text())
        if not source.is_dir() or (self.output.text() and self.output.text() != self.suggested_output):
            return
        title = self.pack_metadata.fields["name"].text().strip() or source.name
        self.suggested_output = str(source.parent / nup_filename(title, self.title_override.text()))
        self.output.setText(self.suggested_output)

    def scan_if_needed(self):
        if not self.runner.busy and self.preview is None and self.source.text() and Path(self.source.text()).is_dir():
            self.scan()

    def find_store_metadata(self):
        if self.runner.busy:
            return
        from .eshop_dialog import ShopDialog
        suggested = self.preview.get("metadata", {}).get("suggested", []) if self.preview else []
        eligible = self.pack_metadata.missing_fields(suggested)
        if not self.title_override.text().strip():
            eligible.add("title_id")
        query = self.pack_metadata.fields["name"].text() or Path(self.source.text()).name
        dialog = ShopDialog(query, self.title_override.text().strip(), eligible, self)
        if dialog.exec():
            self.shop_metadata = {"values": dialog.selected, "url": dialog.details["url"]}
            applied = self.pack_metadata.apply_missing(dialog.selected, dialog.details["url"], suggested)
            if dialog.selected.get("title_id") and not self.title_override.text().strip():
                self.title_override.setText(dialog.selected["title_id"])
                self.auto_title_id = dialog.selected["title_id"]
                applied.append("title_id")
            self.status.setText("Nintendo metadata applied: " + ", ".join(key.replace("_", " ") for key in applied))
            self.log.appendPlainText(self.status.text() + "\n" + dialog.details["url"])
            self.refresh_metadata_summary()
            self.pack_tabs.setCurrentIndex(1)
        dialog.deleteLater()

    def start_automatic_lookup(self):
        if not self.auto_store_lookup.isChecked() or not self.preview:
            return False
        suggested = self.preview.get("metadata", {}).get("suggested", [])
        if not (self.pack_metadata.missing_fields(suggested) & {"name", "publisher", "icon"}):
            self.auto_store_status.setText("The dump already supplied the name, publisher and artwork.")
            return False
        detected = self.title_override.text().strip()
        if not re.fullmatch(r"[0-9a-fA-F]{16}", detected) or not int(detected, 16):
            self.auto_store_status.setText("No title ID detected. Use Find missing info online to search by game title.")
            return False
        cache = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)) / "artwork"
        query = self.pack_metadata.fields["name"].text() or Path(self.source.text()).name
        self.auto_store_status.setText("Searching Nintendo eShop for the detected title ID…")
        self.start_job("shop_auto", {"title_id": detected, "query": query, "cache_dir": str(cache)})
        return True

    def apply_automatic_lookup(self, result):
        message = result["message"]
        if result["matched"]:
            product = result["product"]
            self.shop_metadata = {"values": product["values"], "url": product["url"]}
            suggested = self.preview.get("metadata", {}).get("suggested", []) if self.preview else []
            applied = self.pack_metadata.apply_missing(product["values"], product["url"], suggested)
            self.refresh_metadata_summary()
            message = "Nintendo eShop matched the title ID. Filled: " + (", ".join(applied) or "no remaining fields")
            self.log.appendPlainText(product["url"])
            for notice in product.get("notices", []):
                self.log.appendPlainText(notice)
        self.auto_store_status.setText(message)
        return message

    def refresh_metadata_summary(self, *_):
        fields = self.pack_metadata.fields
        values = {key: field.text().strip() for key, field in fields.items()}
        description = values["name"] or "Metadata scan complete"
        if fields["name"].toolTip().startswith("Detected from Folder name suggestion:"):
            description += "  (folder-name suggestion)"
        description += f"\n{values['publisher'] or 'Publisher unavailable'}  ·  {values['display_version'] or 'Version unavailable'}"
        missing = [key.replace("_", " ") for key, value in values.items() if not value]
        if missing:
            description += "\nStill blank: " + ", ".join(missing)
        self.detected_text.setText(description)
        self.detected_text.setToolTip("\n".join(f"{key}: {field.toolTip()}" for key, field in fields.items()
                                              if field.text() and field.toolTip()))
        self.update_output_suggestion()

    def update_artwork(self, path):
        if not hasattr(self, "detected_art"):
            return
        pixmap = QPixmap(path) if path and Path(path).is_file() else QPixmap()
        self.detected_art.show_artwork(pixmap)

    def invalidate_preview(self):
        self.preview = None
        if hasattr(self, "scan_summary"):
            self.scan_summary.setText("Source options changed. Scan to refresh the package preview.")
            self.packages.setRowCount(0)
            self.scan_warnings.clear()
            self.update_create_summary()

    def update_create_summary(self):
        if hasattr(self, "create_summary"):
            summary = f"Source: {self.source.text() or 'Not selected'}\n\nOutput: {self.output.text() or 'Not selected'}"
            if self.preview:
                summary += f"\n\n{len(self.preview['packages'])} packages · {self.preview['files']:,} files · {human_size(self.preview['size'])} before compression"
                plan = self.preview.get("update_executable", {})
                if plan.get("available"):
                    summary += (f"\n\nBase content: replaced with update V{plan['version']} ExeFS and RomFS; original base files are omitted."
                                if self.prefer_update_executable.isChecked() else
                                "\n\nExecutable: standard package layout; the emulator chooses how to apply the update.")
                for repair in self.preview.get("layout_repairs", []):
                    summary += "\n\n" + repair
            else:
                summary += "\n\nThe source will be scanned again before packing."
            self.create_summary.setText(summary)

    def source_request(self):
        return {"source": self.source.text(), "title_id": self.title_override.text().strip(),
                "update_version": self.bundle_update_version.text().strip(),
                "keep_listings": self.keep_listings.isChecked()}

    def start_job(self, operation, request):
        if self.runner.busy:
            return
        self.log.appendPlainText(f"\n{operation.upper()} started")
        operation_name = {"preview_updates": "Update check", "add_updates": "Updating container",
                          "shop_auto": "Automatic Nintendo lookup"}.get(operation, operation.capitalize())
        self.status.setText(f"{operation_name} in progress…")
        self.settings.setValue("source", self.source.text())
        self.settings.setValue("container", self.container.text())
        self.runner.start({"operation": operation, **request})

    def scan(self):
        self.start_job("scan", self.source_request())

    def pack(self):
        if self.runner.busy:
            return
        if self.preview is None:
            self._pack_after_scan = True
            self.scan()
            return
        plan = self.preview.get("update_executable", {})
        if plan.get("available") and self._launch_review_key != self.launch_choice_key():
            choice = self.ask_update_executable(plan)
            if choice == QMessageBox.StandardButton.Cancel:
                self.status.setText("Creation cancelled — no files changed")
                return
            self.prefer_update_executable.setChecked(choice == QMessageBox.StandardButton.Yes)
            self._launch_review_key = self.launch_choice_key()
        try:
            request = {**self.source_request(), **self.pack_metadata.values(),
                       "output": self.output.text(), "level": self.level.value(),
                       "verify_after": self.verify_after.isChecked(),
                       "prefer_update_executable": self.prefer_update_executable.isChecked()}
            self.start_job("pack", request)
        except ValueError as error:
            self.show_error(str(error))

    def launch_choice_key(self):
        plan = (self.preview or {}).get("update_executable", {})
        return (plan.get("main"), plan.get("version"), plan.get("build_id"))

    def review_launch_choice(self):
        self._launch_review_key = self.launch_choice_key()

    def ask_update_executable(self, plan):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Update main executable found")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(f"Update V{plan['version']} contains its own main executable. Use this update as the base?")
        dialog.setInformativeText(
            "Replace the new NUP's base content with the update's complete exefs/ and romfs/ folders. "
            "Original base-only files will not be included. The update package and DLC stay included, "
            "and source files stay untouched.\n\n"
            + ("This update has no romfs/ folder, so the replacement base will have no RomFS.\n\n"
               if not plan.get("has_romfs") else "")
            + "Keep standard loading to retain the original base. Compatibility with Eglantine/PokeDinner "
            "still depends on its loader."
        )
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
        dialog.button(QMessageBox.StandardButton.Yes).setText("Use update as base")
        dialog.button(QMessageBox.StandardButton.No).setText("Keep standard loading")
        dialog.setDefaultButton(QMessageBox.StandardButton.Yes if self.prefer_update_executable.isChecked() else QMessageBox.StandardButton.No)
        return QMessageBox.StandardButton(dialog.exec())

    def inspect(self):
        self.start_job("inspect", {"file": self.container.text()})

    def loaded_request(self):
        return {"file": self.current["path"], "package": self.package_choice.currentIndex()}

    def extract(self):
        self.start_job("extract", {**self.loaded_request(), "output": self.extract_output.text(),
                                   "scope": self.extract_scope.currentData(),
                                   "subtree": self.subtree.text().strip() if self.extract_scope.currentData() == "package" else ""})

    def extraction_scope_changed(self):
        entire = self.extract_scope.currentData() == "all"
        self.subtree.setEnabled(not entire)
        self.extract_button.setText("Extract entire NUP" if entire else "Extract selected package")
        self.extract_hint.setText(
            "Extracts every base, update and DLC package into a repackable bundle, including package metadata. "
            "Choose the resulting parent folder in Create. Every file's SHA-256 is checked."
            if entire else "Extracts only the package selected above. Other packages are not included. "
            "Leave Subtree blank to include all files in that package.")

    def choose_extract_parent(self):
        from PySide6.QtWidgets import QFileDialog
        parent = QFileDialog.getExistingDirectory(self, "Choose parent for a new extraction folder")
        if parent:
            stem = Path(self.current["path"]).stem
            suffix = "-dump" if self.extract_scope.currentData() == "all" else f"-package-{self.package_choice.currentIndex()}"
            self.extract_output.setText(str(Path(parent) / f"{stem}{suffix}"))

    def edit(self):
        try:
            self.start_job("edit", {**self.loaded_request(), **self.edit_metadata.values(),
                                    "output": self.edit_output.text(), "inplace": self.edit_inplace.isChecked()})
        except ValueError as error:
            self.show_error(str(error))

    def verify(self):
        self.verify_result.setPlainText("Verification in progress…")
        self.start_job("verify", {**self.loaded_request(), "deep": self.deep_verify.isChecked(),
                                  "max_problems": self.max_problems.value()})

    def set_busy(self, busy):
        self.pages.setEnabled(not busy)
        self.nav.setEnabled(not busy)
        self.home_screen.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.cancel_button.setText("Cancel")
        self.reveal_button.setEnabled(not busy and self.last_output is not None)
        self.progress.setRange(0, 0 if busy else 100)

    def show_progress(self, event):
        message = event["message"]
        self.status.setText(message if len(message) <= 105 else message[:102] + "…")
        self.status.setToolTip(message)
        if event["total"]:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(event["done"] * 1000 / event["total"]))
        else:
            self.progress.setRange(0, 0)

    def cancel(self):
        self.runner.cancel()
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("Cancelling…")
        self.status.setText("Cancellation requested; finishing the current chunk…")

    def job_finished(self, operation, event):
        status = event["status"]
        if status != "ok":
            self._pack_after_scan = False
            self.status.setText("Cancelled" if status == "cancelled" else "Operation failed")
            self.progress.setValue(0)
            self.log.appendPlainText(event.get("details", event["message"]))
            if operation == "verify":
                self.verify_result.setPlainText(event["message"])
            if status == "error" and not self.close_when_done:
                self.show_error(event["message"])
        else:
            result = event["result"]
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            if operation == "scan":
                self.show_scan(result)
                message = "Scan complete — review packages and notices"
                if not self.close_when_done and self.start_automatic_lookup():
                    return
                if self._pack_after_scan and not self.close_when_done:
                    self._pack_after_scan = False
                    self.pack()
                    return
            elif operation == "shop_auto":
                message = self.apply_automatic_lookup(result)
                if self._pack_after_scan and not self.close_when_done:
                    self._pack_after_scan = False
                    self.pack()
                    return
            elif operation == "inspect":
                self.show_container(result)
                message = "Container loaded — structure checked"
            elif operation == "preview_updates":
                self.update_preview = result
                version = result["updates"][0]["version"]
                self.update_version.blockSignals(True)
                self.update_version.setText(str(version))
                self.update_version.blockSignals(False)
                versions = f"V{version}"
                self.update_version_warning.setText("\n".join(result.get("warnings", [])))
                self.update_version_warning.setVisible(bool(result.get("warnings")))
                removed = ", ".join(map(str, result["replaced_versions"])) or "none"
                ignored = ", ".join(map(str, result["ignored_versions"])) or "none"
                self.update_plan_text.setText(f"Game {result['title_id']} · current numeric update {result['current_version']}\n"
                    f"Use newest: {versions} · remove previous updates: {removed}.\n"
                    f"Keep {result['kept_packages']} other packages · ignore older incoming versions: {ignored}.\n"
                    + ("The update has no readable title ID. Confirm the match below." if result["requires_confirmation"] else "Title ID matches the existing game.")
                    + ("\nThis NUP replaces its base ExeFS and RomFS with the incoming update when it contains main."
                       if result.get("replace_base_content") else
                       "\nThis older NUP uses the legacy update-ExeFS overlay policy."
                       if result.get("prefer_update_executable") else ""))
                self.confirm_update_identity.setVisible(result["requires_confirmation"])
                self.update_add_enabled()
                message = ("Update checked — using V0 placeholder; see warning" if result.get("version_defaulted")
                           else "Update checked automatically — ready to save")
            elif operation == "verify":
                message = f"Verification {'passed' if result['ok'] else 'FAILED'} · {result['mode']}"
                details = "\n".join(result["problems"])
                if result["problem_count"] > len(result["problems"]):
                    details += f"\n…and {result['problem_count'] - len(result['problems'])} more problems."
                self.verify_result.setPlainText(message + ("\n\n" + details if details else ""))
                if not result["ok"]:
                    self.progress.setValue(0)
            else:
                self.last_output = Path(result["output"])
                self.reveal_button.setEnabled(True)
                action_name = "Update addition" if operation == "add_updates" else operation.capitalize()
                message = f"{action_name} complete · {self.last_output.name}"
                self.log.appendPlainText(f"Output: {self.last_output}")
                if operation == "pack":
                    self.container.setText(result["output"])
                    if result.get("layout_corrected"):
                        self.invalidate_preview()
                        self.bundle_layout_notice.setText("Dump folders corrected: " + result["layout_corrected"])
                        self.bundle_layout_notice.show()
                        self.log.appendPlainText(self.bundle_layout_notice.text())
                    message += f" · {human_size(result['size'])}"
                    for warning in result.get("warnings", []):
                        self.log.appendPlainText(warning)
                elif operation in ("edit", "add_updates"):
                    self.container.setText(result["output"])
                    # Reload after editing so a second edit cannot use stale metadata.
                    self.status.setText(message)
                    self.log.appendPlainText(message)
                    if not self.close_when_done:
                        self.inspect()
                        return
            self.status.setText(message)
            self.status.setToolTip(message)
            self.log.appendPlainText(message)
        if self.close_when_done:
            self.close()

    def show_scan(self, result):
        self.preview = result
        launch = result.get("update_executable", {})
        self.prefer_update_executable.setEnabled(launch.get("available", False))
        if not launch.get("available"):
            self.prefer_update_executable.setChecked(False)
        self.launch_hint.setText(
            f"Update V{launch['version']} has main. Enable this to replace the NUP's base with the update's ExeFS and RomFS. "
            "Original base-only files are omitted; source files stay unchanged."
            + (" This update has no RomFS; the replacement base will have none." if not launch.get("has_romfs") else "")
            if launch.get("available") else launch.get("reason", "No update main executable found.")
        )
        direct = next((p for p in result["packages"] if p.get("flat_update")), None)
        self.source_form.setRowVisible(self.bundle_update_version, direct is not None)
        self.bundle_version_warning.setVisible(result.get("version_defaulted", False))
        self.bundle_layout_notice.setText("\n".join(result.get("layout_repairs", [])))
        self.bundle_layout_notice.setVisible(bool(result.get("layout_repairs")))
        if direct:
            self.bundle_update_version.blockSignals(True)
            self.bundle_update_version.setText(str(direct["version"]))
            self.bundle_update_version.blockSignals(False)
        metadata = result.get("metadata", {"values": {}, "sources": {}, "notices": [], "missing": []})
        self.pack_metadata.apply_detected(metadata)
        if getattr(self, "shop_metadata", None):
            self.pack_metadata.apply_missing(self.shop_metadata["values"], self.shop_metadata["url"], metadata.get("suggested", []))
        detected_id = metadata["values"].get("title_id", "")
        if detected_id and (not self.title_override.text() or self.title_override.text() == self.auto_title_id):
            self.title_override.blockSignals(True)
            self.title_override.setText(detected_id)
            self.title_override.blockSignals(False)
            self.title_override.setToolTip("Detected from " + metadata["sources"].get("title_id", "main.npdm"))
            self.auto_title_id = detected_id
        missing = ", ".join(key.replace("_", " ") for key in metadata["missing"])
        self.refresh_metadata_summary()
        self.scan_summary.setText(f"{len(result['packages'])} packages · {result['files']:,} files · {human_size(result['size'])} uncompressed")
        self.packages.setRowCount(len(result["packages"]))
        for row, package in enumerate(result["packages"]):
            kind = package["kind"] + (" (standalone)" if package["standalone"] else "")
            version = f"{package['version']} (V0 default)" if package.get("version_defaulted") else str(package["version"])
            values = [kind, package["title_id"], version, f"{package['files']:,}",
                      human_size(package["size"]), package["source"]]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.packages.setItem(row, column, item)
        notices = result.get("layout_repairs", []) + result["warnings"] + metadata["notices"]
        if missing:
            notices.append("Some fields could not be detected. Include decrypted control.nacp and icon files if available, or enter values manually.")
        self.scan_warnings.setPlainText("\n".join(notices) or "Metadata detected. No skipped layout entries or discovery warnings.")
        self.update_create_summary()

    def show_container(self, result):
        self.current = result
        self.container.setText(result["path"])
        self.package_choice.blockSignals(True)
        self.package_choice.clear()
        for package in result["packages"]:
            self.package_choice.addItem(f"[{package['index']}]  {package['kind'].upper()}  ·  {package['title_id']}  ·  v{package['version']}  {package['name']}")
        self.package_choice.blockSignals(False)
        self.open_summary.setText(f"{human_size(result['size'])} · {len(result['packages'])} packages · {len(result['files']):,} files\nLoaded: {result['path']}")
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(FileTableModel(result["files"], self.proxy))
        self.proxy.setFilterKeyColumn(1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        old = self.file_table.model()
        self.file_table.setModel(self.proxy)
        if old:
            old.deleteLater()
        self.file_table.setColumnWidth(0, 70)
        self.file_table.setColumnWidth(1, 260)
        self.file_table.setColumnWidth(2, 110)
        self.file_table.setColumnWidth(3, 110)
        self.file_table.setColumnWidth(4, 70)
        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.filter_files(self.file_filter.text())
        self.edit_inplace.setChecked(False)
        path = Path(result["path"])
        self.edit_output.setText(str(path.with_name(path.stem + ".edited.nup")))
        self.update_output.setText(str(path.with_name(path.stem + ".updated.nup")))
        self.invalidate_update_plan()
        self.verify_result.clear()
        self.open_tabs.setEnabled(True)
        self.package_changed(0)

    def package_changed(self, index):
        if self.current is None or index < 0:
            return
        package = self.current["packages"][index]
        details = [package["name"] or "Untitled package",
                   f"{package['kind'].upper()} · {package['title_id']} · numeric v{package['version']} ({package['version_str']})",
                   f"Display version: {package['display_version'] or '—'}   |   Publisher: {package['publisher'] or '—'}",
                   f"Build ID: {package['build_id'] or 'Not present'}",
                   f"Source: {package['source_dump'] or 'Not present'}  |  UUID: {self.current['uuid']}"]
        if package["standalone"]:
            details.append("Standalone update")
        if package.get("replace_base_content"):
            details.append("Base content: replaced with the selected update's ExeFS and RomFS folders")
        elif package.get("prefer_update_executable"):
            details.append("Legacy preference: update ExeFS overlaid onto the original base (0.2.3)")
        if package["lang_names"]:
            details.append("Localized: " + "; ".join(f"{key}={value}" for key, value in package["lang_names"].items()))
        self.package_details.setText("\n".join(details))
        pixmap = QPixmap()
        pixmap.loadFromData(base64.b64decode(package["icon"]))
        self.icon_preview.show_artwork(pixmap, "Icon embedded" if package["icon_size"] else "NO ARTWORK")
        self.edit_metadata.load_package(package)
        self.tree.clear()
        root = QTreeWidgetItem([f"[{index}] {package['kind']} /", "", ""])
        root.setData(0, Qt.ItemDataRole.UserRole, package["root"])
        root.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        self.tree.addTopLevelItem(root)
        root.setExpanded(True)

    def expand_tree(self, item):
        directory = item.data(0, Qt.ItemDataRole.UserRole)
        if directory is None or item.childCount():
            return
        _, first, count = self.current["dirs"][directory]
        for node in self.current["children"][first:first + count]:
            if node < len(self.current["dirs"]):
                child = QTreeWidgetItem([self.current["dirs"][node][0] + "/", "", ""])
                child.setData(0, Qt.ItemDataRole.UserRole, node)
                if self.current["dirs"][node][2]:
                    child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            else:
                name, size, codec, stored, sha = self.current["files"][node - len(self.current["dirs"])]
                child = QTreeWidgetItem([name, human_size(size), codec])
                child.setToolTip(0, f"SHA-256: {sha}\nStored: {human_size(stored)}")
            item.addChild(child)

    def filter_files(self, text):
        if hasattr(self, "proxy"):
            self.proxy.setFilterFixedString(text)

    def show_error(self, text):
        QMessageBox.warning(self, "NS2 NUP Tool", text)

    def toggle_log(self):
        self.log.setVisible(not self.log.isVisible())
        self.log_button.setText("Hide log" if self.log.isVisible() else "Show log")

    def reveal_output(self):
        if self.last_output:
            folder = self.last_output if self.last_output.is_dir() else self.last_output.parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.runner.busy:
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if not paths or self.runner.busy:
            return
        path = paths[0]
        if path.is_dir():
            self.source.setText(str(path))
            self.nav.setCurrentRow(0)
            self.pack_tabs.setCurrentIndex(0)
            self.scan()
        elif path.suffix.lower() == ".nup":
            self.container.setText(str(path))
            self.nav.setCurrentRow(1)
            self.inspect()

    def closeEvent(self, event):
        if self.runner.busy:
            self.close_when_done = True
            self.cancel()
            event.ignore()
        else:
            # Retire snapshot effects while their widgets and QApplication exist.
            self.scale_timer.stop()
            for stack in (self.pages, self.shell_pages, self.pack_tabs, self.open_tabs):
                stack.finish_transition()
            self.canvas.clock.stop()
            for tile in self.home_screen.tiles:
                tile.clock.stop()
                tile.animation.stop()
            self.settings.setValue("source", self.source.text())
            self.settings.setValue("container", self.container.text())
            event.accept()


def run_app():
    application = QApplication(sys.argv)
    application.setApplicationName("NS2 NUP Tool")
    application.setApplicationVersion(__version__)
    application.setStyle("Fusion")
    palette = application.palette()
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#47d7f0"))
    palette.setColor(QPalette.ColorRole.Accent, QColor("#47d7f0"))
    application.setPalette(palette)
    application.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    exit_code = application.exec()
    # Dispose widgets while QApplication is alive, including queued Qt deletes.
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return exit_code
