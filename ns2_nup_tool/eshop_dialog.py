"""Review optional store metadata before importing it into the current draft."""

from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QProgressBar, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from .jobs import JobRunner
from .retro import ArtworkBox, TitleBar, WindowButton
from .sizing import LayoutMetrics, fit_window, scaled_stylesheet


class ShopDialog(QDialog):
    def __init__(self, query, title_id, eligible, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nintendo eShop · Find missing metadata")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        fit_window(self, (930, 850), (680, 460))
        self.setStyleSheet("QDialog { background:#111e37; border:2px solid #425778; }")
        self.title_id, self.eligible = title_id, set(eligible)
        self.details, self.selected = None, {}
        self.close_pending = False
        self.runner = JobRunner(self)
        self.runner.busy_changed.connect(self.set_busy)
        self.runner.finished.connect(self.finished_job)
        self.runner.progress.connect(lambda event: self.status.setText(event["message"]))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        chrome = TitleBar()
        chrome_layout = QHBoxLayout(chrome)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("NINTENDO eSHOP / METADATA")
        title.setObjectName("accent")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        chrome_layout.addWidget(title, 1)
        chrome_layout.addWidget(WindowButton("close", self.reject))
        layout.addWidget(chrome)
        root = layout
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(content)
        root.addWidget(area, 1)
        heading = QLabel("Find the finishing touches")
        heading.setObjectName("title")
        layout.addWidget(heading)
        privacy = QLabel("Nintendo US store · Sends your search text and downloads public metadata/artwork.\nYour dump files stay on this computer. Existing fields and manual edits are preserved.")
        privacy.setWordWrap(True)
        privacy.setObjectName("muted")
        layout.addWidget(privacy)
        row = QHBoxLayout()
        self.query = QLineEdit(query)
        self.query.setPlaceholderText("Game name, or paste a Nintendo US product URL")
        self.search_button = QPushButton("Search Nintendo")
        self.search_button.setDefault(True)
        self.search_button.setObjectName("primary")
        self.search_button.clicked.connect(self.search)
        row.addWidget(self.query, 1)
        row.addWidget(self.search_button)
        layout.addLayout(row)
        self.results = QListWidget()
        self.results.setMinimumHeight(110)
        self.results.currentItemChanged.connect(self.choose_result)
        layout.addWidget(self.results, 1)
        preview = QHBoxLayout()
        self.artwork = ArtworkBox(240)
        preview.addWidget(self.artwork)
        self.fields_layout = QVBoxLayout()
        self.identity = QLabel("Select a result to check its application ID against the dump.")
        self.identity.setWordWrap(True)
        self.identity.setTextFormat(Qt.TextFormat.PlainText)
        self.fields_layout.addWidget(self.identity)
        self.checks = {}
        for key, name in (("name", "Game name"), ("publisher", "Publisher"), ("icon", "Artwork"), ("title_id", "Title ID")):
            checkbox = QCheckBox(name + " — not loaded")
            checkbox.setEnabled(False)
            checkbox.toggled.connect(self.update_apply)
            self.checks[key] = checkbox
            self.fields_layout.addWidget(checkbox)
        preview.addLayout(self.fields_layout, 1)
        layout.addLayout(preview)
        self.confirm_match = QCheckBox("I checked that this product is the same game as my dump")
        self.confirm_match.hide()
        self.confirm_match.toggled.connect(self.update_apply)
        layout.addWidget(self.confirm_match)
        self.notices = QLabel("Display version, build ID, and update numbers remain tied to your dump.")
        self.notices.setTextFormat(Qt.TextFormat.PlainText)
        self.notices.setWordWrap(True)
        self.notices.setObjectName("muted")
        layout.addWidget(self.notices)
        self.status = QLabel("Search when you are ready.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        self.progress.hide()
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        self.open_button = QPushButton("View product page ↗")
        self.open_button.setAutoDefault(False)
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_product)
        actions.addWidget(self.open_button)
        actions.addStretch()
        self.close_button = QPushButton("Close")
        self.close_button.setAutoDefault(False)
        self.close_button.clicked.connect(self.reject)
        actions.addWidget(self.close_button)
        self.apply_button = QPushButton("Fill missing fields")
        self.apply_button.setAutoDefault(False)
        self.apply_button.setObjectName("primary")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply)
        actions.addWidget(self.apply_button)
        root.addLayout(actions)
        scale = max(.7, min(1., self.width() / 930, self.height() / 850))
        LayoutMetrics(self).apply(scale)
        theme = getattr(parent, "theme_style", "")
        self.setStyleSheet(scaled_stylesheet(theme, scale) + "QDialog { background:#111e37; border:2px solid #425778; }")
        self.artwork.set_ui_scale(scale)
        for control in self.findChildren(WindowButton):
            control.set_ui_scale(scale)

    def set_busy(self, busy):
        self.search_button.setEnabled(not busy)
        self.query.setEnabled(not busy)
        self.results.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.progress.setRange(0, 0 if busy else 100)
        self.close_button.setText("Cancel lookup" if busy else "Close")
        self.update_apply()

    def search(self):
        if self.runner.busy:
            return
        query = self.query.text().strip()
        if query.startswith("https://"):
            self.load_url(query)
        elif query:
            self.clear_preview()
            self.results.clear()
            self.runner.start({"operation": "shop_search", "query": query})

    def choose_result(self, current, previous=None):
        if current and not self.runner.busy:
            self.load_url(current.data(Qt.ItemDataRole.UserRole))

    def clear_preview(self):
        self.details = None
        self.artwork.show_artwork(QPixmap(), "Artwork\npreview")
        self.open_button.setEnabled(False)
        self.confirm_match.setChecked(False)
        self.confirm_match.hide()
        self.identity.setText("Checking product metadata…")
        for key, checkbox in self.checks.items():
            checkbox.setChecked(False)
            checkbox.setEnabled(False)
            checkbox.setText(key.replace("_", " ").title() + " — not loaded")
        self.notices.clear()
        self.update_apply()

    def load_url(self, url):
        self.clear_preview()
        cache = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)) / "artwork"
        self.runner.start({"operation": "shop_details", "url": url, "title_id": self.title_id, "cache_dir": str(cache)})

    def finished_job(self, operation, event):
        if self.close_pending:
            super().reject()
            return
        if event["status"] != "ok":
            self.status.setText(event.get("message", "Lookup failed. Try a Nintendo product URL."))
            return
        result = event["result"]
        if operation == "shop_search":
            for match in result["results"]:
                item = QListWidgetItem(f"{match['name']}  ·  {match['platform']}")
                item.setData(Qt.ItemDataRole.UserRole, match["url"])
                item.setToolTip(match["url"])
                self.results.addItem(item)
            self.status.setText(f"{self.results.count()} results. Select a game to preview its metadata." if self.results.count()
                                else "No games found. Try a shorter title, or paste the Nintendo product URL.")
            self.identity.setText("Select the correct game, edition, and platform.")
        else:
            self.show_product(result)

    def show_product(self, result):
        self.details = result
        values, identity = result["values"], result["identity"]
        self.open_button.setEnabled(True)
        found = values.get("title_id", "not provided")
        label = {"match": "Application ID matches your dump", "mismatch": "Different game — import disabled",
                 "unconfirmed": "Application ID could not be confirmed"}[identity]
        self.identity.setText(f"{label}\n{found} · {result['platform']}")
        self.confirm_match.setVisible(identity == "unconfirmed")
        if values.get("icon"):
            pixmap = QPixmap(values["icon"])
            if not pixmap.isNull():
                self.artwork.show_artwork(pixmap)
        for key, checkbox in self.checks.items():
            value = values.get(key, "")
            description = ("Square store artwork" if result["square_artwork"] else "Store artwork") if key == "icon" and value else value
            available = bool(value and key in self.eligible and identity != "mismatch")
            text = f"{key.replace('_', ' ').title()}: {description or 'not provided'}"
            text += "  (existing value kept)" if key not in self.eligible else ""
            checkbox.setText(text.replace("&", "&&"))
            checkbox.setToolTip(str(value))
            checkbox.setEnabled(available)
            checkbox.setChecked(available)
        self.notices.setText("\n".join(result["notices"]))
        self.status.setText("Review the checked fields, then apply them to this draft.")
        self.update_apply()

    def update_apply(self):
        ready = self.details and self.details["identity"] != "mismatch" and not self.runner.busy
        if ready and self.details["identity"] == "unconfirmed":
            ready = self.confirm_match.isChecked()
        self.apply_button.setEnabled(bool(ready and any(box.isEnabled() and box.isChecked() for box in self.checks.values())))

    def apply(self):
        if self.apply_button.isEnabled():
            self.selected = {key: self.details["values"][key] for key, box in self.checks.items()
                             if box.isEnabled() and box.isChecked()}
            self.accept()

    def open_product(self):
        if self.details:
            QDesktopServices.openUrl(QUrl(self.details["url"]))

    def reject(self):
        if self.runner.busy:
            self.close_pending = True
            self.runner.cancel()
            self.status.setText("Cancelling lookup…")
            self.close_button.setEnabled(False)
        else:
            super().reject()
