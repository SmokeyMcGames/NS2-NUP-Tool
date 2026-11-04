"""Shared form controls and scalable file-list model."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)


def human_size(value):
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.2f} {unit}"
        value /= 1024


class PathField(QWidget):
    pathChosen = Signal(str)

    def __init__(self, mode="file", placeholder="", file_filter="All files (*)"):
        super().__init__()
        self.mode, self.file_filter = mode, file_filter
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.button = QPushButton("Browse…")
        self.button.setFixedWidth(96)
        self.button.clicked.connect(self.browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    def text(self):
        return self.edit.text().strip().strip('"')

    def setText(self, text):
        self.edit.setText(text)

    def browse(self):
        if self.mode == "folder":
            value = QFileDialog.getExistingDirectory(self, "Choose folder", self.text())
        elif self.mode == "save":
            value, _ = QFileDialog.getSaveFileName(self, "Choose output file", self.text(), self.file_filter)
        else:
            value, _ = QFileDialog.getOpenFileName(self, "Choose file", self.text(), self.file_filter)
        if value:
            self.setText(value)
            self.pathChosen.emit(value)


class MetadataForm(QWidget):
    def __init__(self, editing=False):
        super().__init__()
        self.editing = editing
        self.fields = {}
        self.actions = {}
        self._filling = False
        self._manual_fields = set()
        self._detected_fields = {}
        self._detected_rows = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        for key, label, placeholder in (
            ("name", "Game name", "Optional title"),
            ("publisher", "Publisher", "Optional publisher"),
            ("display_version", "Display version", "Auto: V<newest update number>, or V0"),
            ("icon", "Default icon", "Optional PNG, JPEG, or console icon file"),
        ):
            field = PathField(placeholder=placeholder) if key == "icon" else QLineEdit()
            if key != "icon":
                field.setPlaceholderText(placeholder)
            self.fields[key] = field
            edit = field.edit if isinstance(field, PathField) else field
            edit.textChanged.connect(lambda text, field_key=key: self.mark_manual(field_key))
            row = QHBoxLayout()
            if editing:
                action = QComboBox()
                action.addItems(["Keep", "Set", "Clear"])
                action.setFixedWidth(90)
                self.actions[key] = action
                row.addWidget(action)
                field.setEnabled(False)
                action.currentTextChanged.connect(lambda text, widget=field: widget.setEnabled(text == "Set"))
            row.addWidget(field, 1)
            form.addRow(label, row)
        layout.addLayout(form)
        hint = QLabel("Localized names & icons  ·  language tags such as en, ja, fr, zh-hans")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        layout.addWidget(hint)
        self.locales = QTableWidget(0, 5)
        self.locales.setHorizontalHeaderLabels(["Language", "Name action", "Localized title", "Icon action", "Icon file"])
        self.locales.verticalHeader().hide()
        self.locales.verticalHeader().setDefaultSectionSize(44)
        self.locales.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.locales.setMinimumHeight(130)
        self.locales.setMaximumHeight(210)
        header = self.locales.horizontalHeader()
        for column in (0, 1, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        for column in (2, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.locales)
        buttons = QHBoxLayout()
        for label, callback in (("+ Language", self.add_row), ("Remove row", self.remove_row),
                                ("Choose localized icon…", self.choose_icon)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        if editing:
            hint = QLabel("Keep preserves existing metadata. Clear removes it. Removing a row discards that proposed change.")
            hint.setWordWrap(True)
            hint.setObjectName("muted")
            layout.addWidget(hint)

    def add_row(self, checked=False, language="", name="", has_icon=False):
        row = self.locales.rowCount()
        self.locales.insertRow(row)
        for column, value in ((0, language), (2, name), (4, "")):
            item = QTableWidgetItem(value)
            if column == 4 and has_icon:
                item.setToolTip("An icon is already embedded. Keep retains it; Set selects a replacement.")
            self.locales.setItem(row, column, item)
        for column in (1, 3):
            combo = QComboBox()
            combo.addItems(["Keep", "Set", "Clear"] if self.editing else ["Skip", "Set"])
            if not self.editing and column == 1:
                combo.setCurrentText("Set")
            self.locales.setCellWidget(row, column, combo)
        self.locales.selectRow(row)

    def mark_manual(self, key):
        if not self._filling:
            self._manual_fields.add(key)
            self.fields[key].setToolTip("Entered manually")

    def row_snapshot(self, row):
        return (self.locales.item(row, 0).text(), self.locales.cellWidget(row, 1).currentText(),
                self.locales.item(row, 2).text(), self.locales.cellWidget(row, 3).currentText(),
                self.locales.item(row, 4).text())

    def clear_detected(self):
        self._filling = True
        try:
            for key in self._detected_fields:
                if key not in self._manual_fields:
                    self.fields[key].setText("")
                    self.fields[key].setToolTip("")
            for row in reversed(range(self.locales.rowCount())):
                snapshot = self.row_snapshot(row)
                if self._detected_rows.get(snapshot[0]) == snapshot:
                    self.locales.removeRow(row)
        finally:
            self._filling = False
        self._detected_fields.clear()
        self._detected_rows.clear()

    def apply_detected(self, metadata):
        self.clear_detected()
        values = metadata["values"]
        applied = []
        self._filling = True
        try:
            for key, field in self.fields.items():
                if values.get(key) and key not in self._manual_fields:
                    field.setText(values[key])
                    field.setToolTip("Detected from " + metadata["sources"].get(key, "dump files"))
                    self._detected_fields[key] = values[key]
                    applied.append(key)
            existing = {self.locales.item(row, 0).text().strip().lower() for row in range(self.locales.rowCount())}
            names, icons = values.get("lang_names", {}), values.get("lang_icons", {})
            for language in sorted(set(names) | set(icons)):
                if language in existing:
                    continue
                self.add_row(language=language, name=names.get(language, ""))
                row = self.locales.rowCount() - 1
                self.locales.cellWidget(row, 1).setCurrentText("Set" if names.get(language) else "Skip")
                self.locales.cellWidget(row, 3).setCurrentText("Set" if icons.get(language) else "Skip")
                self.locales.item(row, 4).setText(icons.get(language, ""))
                self._detected_rows[language] = self.row_snapshot(row)
        finally:
            self._filling = False
        return applied

    def missing_fields(self, suggested=()):
        return {key for key, field in self.fields.items() if key not in self._manual_fields
                and (not field.text().strip() or key in suggested)}

    def apply_missing(self, values, source, suggested=()):
        eligible = self.missing_fields(suggested)
        applied = []
        self._filling = True
        try:
            for key, value in values.items():
                if key in eligible and value:
                    self.fields[key].setText(value)
                    self.fields[key].setToolTip("From Nintendo eShop: " + source)
                    self._detected_fields[key] = value
                    applied.append(key)
        finally:
            self._filling = False
        return applied

    def remove_row(self):
        rows = sorted({index.row() for index in self.locales.selectedIndexes()}, reverse=True)
        for row in rows:
            self.locales.removeRow(row)

    def choose_icon(self):
        row = self.locales.currentRow()
        if row < 0:
            self.add_row()
            row = self.locales.currentRow()
        path, _ = QFileDialog.getOpenFileName(self, "Choose localized icon")
        if path:
            self.locales.item(row, 4).setText(path)
            self.locales.cellWidget(row, 3).setCurrentText("Set")

    def values(self):
        values = {}
        for key, field in self.fields.items():
            text = field.text()
            if self.editing:
                action = self.actions[key].currentText()
                if action == "Clear":
                    values[f"clear_{key}"] = True
                elif action == "Set":
                    if not text:
                        raise ValueError(f"Enter a value for {key.replace('_', ' ')} or choose Clear.")
                    values[key] = text
            elif text:
                values[key] = text
        seen = set()
        for row in range(self.locales.rowCount()):
            language = self.locales.item(row, 0).text().strip().lower()
            active = any(self.locales.cellWidget(row, col).currentText() in ("Set", "Clear") for col in (1, 3))
            if not active:
                continue
            if not language:
                raise ValueError(f"Enter a language tag in row {row + 1}.")
            if language in seen:
                raise ValueError(f"Duplicate language tag: {language}")
            seen.add(language)
            for action_column, value_column, key in ((1, 2, "lang_names"), (3, 4, "lang_icons")):
                action = self.locales.cellWidget(row, action_column).currentText()
                if action in ("Set", "Clear"):
                    text = "" if action == "Clear" else self.locales.item(row, value_column).text()
                    if action == "Set" and not text:
                        raise ValueError(f"Enter a {key.replace('_', ' ')} value for {language}.")
                    values.setdefault(key, {})[language] = text
        return values

    def load_package(self, package):
        for key, field in self.fields.items():
            field.setText(package.get(key, "") if key != "icon" else "")
            self.actions[key].setCurrentText("Keep")
        self.locales.setRowCount(0)
        for language in sorted(set(package["lang_names"]) | set(package["lang_icons"])):
            self.add_row(language=language, name=package["lang_names"].get(language, ""),
                         has_icon=language in package["lang_icons"])


class FileTableModel(QAbstractTableModel):
    HEADERS = ("Index", "Filename", "Original size", "Stored size", "Codec", "SHA-256")

    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.rows = rows

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return (str(index.row()), row[0], human_size(row[1]), human_size(row[3]), row[2], row[4])[index.column()]
        if role == Qt.ItemDataRole.UserRole:
            return (index.row(), row[0], row[1], row[3], row[2], row[4])[index.column()]
