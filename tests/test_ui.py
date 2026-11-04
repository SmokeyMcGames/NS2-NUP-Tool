"""Qt widget and real child-process workflow checks (no console content)."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import time
import unittest
import struct
from unittest.mock import Mock
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QMimeData, QPoint, QPointF, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea

from ns2_nup_tool.app import MainWindow, STYLE
from ns2_nup_tool.backend import run_operation
from ns2_nup_tool.console import transparent_snapshot
from ns2_nup_tool.widgets import MetadataForm
from ns2_nup_tool.eshop_dialog import ShopDialog
from tests.fixtures import TITLE_ID, make_dump


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings_dir = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, cls.settings_dir.name)
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    @classmethod
    def tearDownClass(cls):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        cls.settings_dir.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "Synthetic dump"
        make_dump(self.source)
        settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)
        settings.setValue("auto_store_lookup", False)
        self.window = MainWindow(settings)
        self.errors = []
        self.window.show_error = self.errors.append
        self.window.show()

    def tearDown(self):
        if self.window.runner.busy:
            self.window.cancel()
            self.wait_for_job()
        self.window.close()
        self.window.deleteLater()
        # processEvents alone does not drain deferred deletion without app.exec().
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def wait_for_job(self):
        deadline = time.monotonic() + 25
        while self.window.runner.busy and time.monotonic() < deadline:
            QTest.qWait(25)
        self.assertFalse(self.window.runner.busy, "Worker did not finish")
        self.assertEqual(self.errors, [])

    def test_full_ui_workflow_through_worker_processes(self):
        self.window.source.setText(str(self.source))
        self.window.scan()
        self.wait_for_job()
        self.assertEqual(self.window.packages.rowCount(), 3)
        self.window.pack_metadata.fields["name"].setText("UI test")
        self.window.pack()
        self.wait_for_job()
        output = Path(self.window.output.text())
        self.assertTrue(output.is_file())
        self.window.container.pathChosen.emit(str(output))
        self.wait_for_job()
        self.assertEqual(self.window.package_choice.count(), 3)
        self.assertEqual(self.window.current["packages"][0]["name"], "UI test")
        self.assertGreater(self.window.tree.topLevelItem(0).childCount(), 0)
        self.window.file_filter.setText("raw.bin")
        self.assertEqual(self.window.proxy.rowCount(), 1)
        self.window.package_choice.setCurrentIndex(2)
        self.window.extract_scope.setCurrentIndex(1)
        self.window.extract_output.setText(str(self.root / "extracted"))
        self.window.extract()
        self.wait_for_job()
        self.assertTrue((self.root / "extracted/romfs/addon.bin").exists())
        self.window.edit_metadata.actions["name"].setCurrentText("Set")
        self.window.edit_metadata.fields["name"].setText("Edited DLC")
        self.window.edit()
        self.wait_for_job()
        self.assertEqual(self.window.current["packages"][2]["name"], "Edited DLC")
        self.window.verify()
        self.wait_for_job()
        self.assertIn("passed", self.window.verify_result.toPlainText())

    def test_automatic_lookup_finishes_before_pending_pack_and_keeps_manual_fields(self):
        self.window.source.setText(str(self.source))
        scanned = run_operation({"operation": "scan", "source": str(self.source)}, lambda: None, lambda *args: None)
        self.window.auto_store_lookup.setChecked(True)
        self.window.pack_metadata.fields["publisher"].setText("My publisher")
        self.window._pack_after_scan = True
        self.window.start_job = Mock()
        self.window.job_finished("scan", {"status": "ok", "result": scanned})
        self.assertEqual(self.window.start_job.call_args.args[0], "shop_auto")
        self.assertTrue(self.window._pack_after_scan)
        self.window.job_finished("shop_auto", {"status": "ok", "result": {"matched": True, "message": "Found", "product": {
            "values": {"name": "Store name", "publisher": "Store publisher"}, "url": "https://www.nintendo.com/"}}})
        self.assertEqual(self.window.start_job.call_args.args[0], "pack")
        self.assertEqual(self.window.start_job.call_args.args[1]["name"], "Store name")
        self.assertEqual(self.window.start_job.call_args.args[1]["publisher"], "My publisher")
        self.assertFalse(self.window._pack_after_scan)

    def test_default_full_extraction_repackages_all_packages_through_workers(self):
        self.assertFalse(self.window.keep_listings.isChecked())
        self.window.source.setText(str(self.source))
        self.window.pack()
        self.wait_for_job()
        self.window.inspect()
        self.wait_for_job()
        self.assertEqual(self.window.extract_scope.currentData(), "all")
        self.assertFalse(self.window.subtree.isEnabled())
        self.window.package_choice.setCurrentIndex(2)
        self.window.subtree.setText("romfs")
        restored = self.root / "complete"
        self.window.extract_output.setText(str(restored))
        self.window.extract()
        self.wait_for_job()
        self.assertFalse((restored / "base/romfs/.listing").exists())
        self.assertTrue((restored / "updates/458752/romfs/data/repeated.bin").is_file())
        self.assertTrue((restored / "dlc/040074A01BF13001/0/romfs/addon.bin").is_file())
        self.window.source.setText(str(restored))
        self.window.output.setText(str(self.root / "repacked.nup"))
        self.window.pack()
        self.wait_for_job()
        self.window.inspect()
        self.wait_for_job()
        self.assertEqual(len(self.window.current["packages"]), 3)
        self.window.extract_scope.setCurrentIndex(1)
        self.assertTrue(self.window.subtree.isEnabled())
        self.assertIn("only", self.window.extract_hint.text())

    def test_responsive_layout_keeps_chrome_footer_and_pages_inside_window(self):
        self.window.reduce_motion.setChecked(True)
        for width, height in ((840, 560), (960, 600), (1280, 720), (1440, 1040), (1920, 1080), (2560, 1440)):
            with self.subTest(size=(width, height)):
                self.window.resize(width, height)
                QTest.qWait(140)
                self.assertEqual((self.window.width(), self.window.height()), (width, height))
                for control in (self.window.wordmark, self.window.nav, self.window.close_button, self.window.progress,
                                self.window.reveal_button, self.window.cancel_button, self.window.log_button):
                    top = control.mapTo(self.window, QPoint(0, 0))
                    bottom = control.mapTo(self.window, control.rect().bottomRight())
                    self.assertGreaterEqual(top.x(), 0)
                    self.assertGreaterEqual(top.y(), 0)
                    self.assertLess(bottom.x(), width)
                    self.assertLess(bottom.y(), height)
                self.assertLess(self.window.progress.mapTo(self.window, self.window.progress.rect().bottomRight()).x(),
                                self.window.reveal_button.mapTo(self.window, QPoint(0, 0)).x())
                for section in range(3):
                    self.window.nav.setCurrentRow(section)
                    self.app.processEvents()
                    self.assertGreater(self.window.pages.currentWidget().height(), 200)
                for section, tabs in enumerate((self.window.pack_tabs, self.window.open_tabs)):
                    self.window.nav.setCurrentRow(section)
                    for index in range(tabs.count()):
                        tabs.setCurrentIndex(index)
                        QTest.qWait(10)
                        pane = tabs.widget(index)
                        if isinstance(pane, QScrollArea):
                            self.assertEqual(pane.horizontalScrollBar().maximum(), 0, f"Horizontal clipping in section {section}, tab {index}")
                self.window.show_home()
                self.app.processEvents()
                for tile in self.window.home_screen.tiles:
                    self.assertGreater(tile.height(), 170)
                    self.assertTrue(self.window.home_screen.rect().contains(tile.mapTo(self.window.home_screen, tile.rect().bottomRight())))

    def test_metadata_requires_explicit_changes(self):
        form = MetadataForm(editing=True)
        form.setParent(self.window)
        form.load_package({"name": "Keep me", "lang_names": {"ja": "Keep localized"}, "lang_icons": ["ja"]})
        self.assertEqual(form.values(), {})
        form.locales.cellWidget(0, 1).setCurrentText("Clear")
        self.assertEqual(form.values(), {"lang_names": {"ja": ""}})
        form.actions["name"].setCurrentText("Clear")
        self.assertTrue(form.values()["clear_name"])

    def test_add_update_workflow_uses_real_workers_and_reloads(self):
        self.window.source.setText(str(self.source))
        self.window.scan()
        self.wait_for_job()
        self.window.pack()
        self.wait_for_job()
        self.window.inspect()
        self.wait_for_job()
        incoming = self.root / "524288"
        (incoming / "exefs").mkdir(parents=True)
        (incoming / "exefs/main.npdm").write_bytes(b"ACI0" + bytes(12) + struct.pack("<Q", TITLE_ID))
        self.window.update_source.setText(str(incoming))
        self.window.update_source.pathChosen.emit(str(incoming))
        self.wait_for_job()
        self.assertEqual(self.window.update_version.text(), "524288")
        self.assertTrue(self.window.add_update_button.isEnabled())
        self.window.add_updates()
        self.wait_for_job()
        self.assertEqual(len(self.window.current["packages"]), 3)
        self.assertEqual(self.window.current["packages"][-1]["version"], 524288)

    def test_update_main_prompt_choices_control_creation_and_cancel_before_changes(self):
        from tests.fixtures import add_update_program
        add_update_program(self.source / "updates/458752", 7, 458752)
        self.window.source.setText(str(self.source))
        self.window.scan()
        self.wait_for_job()
        self.assertTrue(self.window.prefer_update_executable.isEnabled())
        self.window.start_job = Mock()
        self.window.ask_update_executable = Mock(return_value=QMessageBox.StandardButton.Cancel)
        self.window.pack()
        self.window.start_job.assert_not_called()
        for choice, expected in ((QMessageBox.StandardButton.No, False), (QMessageBox.StandardButton.Yes, True)):
            self.window._launch_review_key = None
            self.window.ask_update_executable.return_value = choice
            self.window.pack()
            self.assertEqual(self.window.start_job.call_args.args[1]["prefer_update_executable"], expected)
        self.window.ask_update_executable.reset_mock()
        self.window.pack()
        self.window.ask_update_executable.assert_not_called()

    def test_replacement_prompt_explains_both_folders_and_missing_romfs(self):
        observed = {}

        def cancel_dialog():
            dialog = self.app.activeModalWidget()
            observed["text"] = dialog.informativeText()
            observed["yes"] = dialog.button(QMessageBox.StandardButton.Yes).text()
            dialog.done(QMessageBox.StandardButton.Cancel)

        QTimer.singleShot(0, cancel_dialog)
        choice = self.window.ask_update_executable({"version": 0, "has_romfs": False})
        self.assertEqual(choice, QMessageBox.StandardButton.Cancel)
        self.assertIn("complete exefs/ and romfs/ folders", observed["text"])
        self.assertIn("no RomFS", observed["text"])
        self.assertEqual(observed["yes"], "Use update as base")

    def test_output_suggestion_tracks_scan_store_and_manual_title(self):
        self.window.source.setText(str(self.source))
        self.assertEqual(Path(self.window.output.text()).name, "Synthetic dump.nup")
        self.window.scan()
        self.wait_for_job()
        self.assertEqual(Path(self.window.output.text()).name, f"Synthetic dump [{TITLE_ID:016X}].nup")
        self.window.apply_automatic_lookup({"matched": True, "message": "Found", "product": {
            "values": {"name": "Store game"}, "url": "https://www.nintendo.com/"}})
        self.assertEqual(Path(self.window.output.text()).name, f"Store game [{TITLE_ID:016X}].nup")
        self.window.pack_metadata.fields["name"].setText("Manual game")
        self.assertEqual(Path(self.window.output.text()).name, f"Manual game [{TITLE_ID:016X}].nup")
        self.window.title_override.setText("0100000000002000")
        self.assertEqual(Path(self.window.output.text()).name, "Manual game [0100000000002000].nup")

    def test_custom_output_survives_metadata_and_source_changes(self):
        self.window.source.setText(str(self.source))
        custom = str(self.root / "My chosen name.nup")
        self.window.output.setText(custom)
        self.window.scan()
        self.wait_for_job()
        self.window.pack_metadata.fields["name"].setText("Different game")
        self.window.title_override.setText("0100000000002000")
        other = self.root / "Another dump"
        make_dump(other)
        self.window.source.setText(str(other))
        self.assertEqual(self.window.output.text(), custom)

    def test_explicit_update_main_toggle_packs_through_worker_and_source_change_resets_it(self):
        from tests.fixtures import add_update_program
        add_update_program(self.source / "updates/458752", 7, 458752)
        self.window.source.setText(str(self.source))
        self.window.scan()
        self.wait_for_job()
        self.window.prefer_update_executable.click()
        self.window.ask_update_executable = Mock(side_effect=AssertionError("Explicit toggle was already reviewed"))
        self.window.pack()
        self.wait_for_job()
        self.window.inspect()
        self.wait_for_job()
        base = self.window.current["packages"][0]
        self.assertTrue(base["prefer_update_executable"])
        self.assertEqual(base["build_id"], (bytes([7]) * 32).hex().upper())
        self.window.source.setText(str(self.root / "other dump"))
        self.assertFalse(self.window.prefer_update_executable.isChecked())
        self.assertFalse(self.window.prefer_update_executable.isEnabled())

    def test_update_browse_defaults_to_zero_with_visible_warning_and_can_save(self):
        from tests.fixtures import make_npdm
        self.window.source.setText(str(self.source))
        self.window.pack()
        self.wait_for_job()
        self.window.inspect()
        self.wait_for_job()
        incoming = self.root / "Unnumbered update"
        (incoming / "exefs").mkdir(parents=True)
        (incoming / "exefs/main.npdm").write_bytes(make_npdm())
        self.window.update_source.setText(str(incoming))
        self.window.update_source.pathChosen.emit(str(incoming))
        self.wait_for_job()
        self.assertEqual(self.window.update_version.text(), "0")
        self.assertFalse(self.window.update_version_warning.isHidden())
        self.assertIn("placeholder", self.window.update_version_warning.text())
        self.assertTrue(self.window.add_update_button.isEnabled())
        self.window.add_updates()
        self.wait_for_job()
        self.assertEqual([p["version"] for p in self.window.current["packages"] if p["kind"] == "update"], [0])
        self.assertEqual(self.window.current["packages"][0]["display_version"], "V0")

    def test_unnumbered_update_stays_visible_and_version_entry_refreshes_scan(self):
        from tests.fixtures import make_flat_dump
        source = self.root / "Direct update layout"
        make_flat_dump(source)
        self.window.source.setText(str(source))
        self.window.scan()
        self.wait_for_job()
        self.window.nav.setCurrentRow(0)
        self.window.reduce_motion.setChecked(True)
        self.window.pack_tabs.setCurrentIndex(0)
        self.assertEqual(self.window.packages.rowCount(), 2)
        self.assertEqual(self.window.packages.item(1, 2).text(), "0 (V0 default)")
        self.assertEqual(self.window.bundle_update_version.text(), "0")
        self.assertEqual(self.window.pack_metadata.fields["display_version"].text(), "V0")
        self.assertFalse(self.window.bundle_version_warning.isHidden())
        self.assertIn("updates/0/", self.window.bundle_layout_notice.text())
        self.assertFalse(self.window.bundle_update_version.isHidden())
        self.window.bundle_update_version.setText("65536")
        self.window.bundle_update_version.editingFinished.emit()
        self.wait_for_job()
        self.assertFalse(self.window.preview["version_defaulted"])
        self.assertTrue(self.window.bundle_version_warning.isHidden())
        self.assertEqual(self.window.pack_metadata.fields["display_version"].text(), "V65536")
        self.assertIn("updates/65536/", self.window.bundle_layout_notice.text())
        self.assertTrue((source / "updates/romfs").is_dir())
        self.window.pack()
        self.wait_for_job()
        self.assertTrue((source / "updates/65536/romfs").is_dir())
        self.assertFalse((source / "updates/romfs").exists())
        self.assertIn("Dump folders corrected", self.window.bundle_layout_notice.text())

    def test_frameless_controls_theme_and_visible_motion(self):
        self.assertTrue(self.window.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertEqual(self.window.settings.value("theme"), "Classic Red")
        self.window.reduce_motion.setChecked(False)
        self.app.processEvents()
        self.window.nav.setCurrentRow(0)
        stack = self.window.shell_pages
        self.assertIsNotNone(stack.transition)
        self.assertEqual(len(stack.overlays), 2)
        first_position = stack.overlays[-1].pos()
        QTest.qWait(170)
        self.assertNotEqual(stack.overlays[-1].pos(), first_position)
        self.assertGreater(stack.overlays[-1].graphicsEffect().opacity(), 0.)
        QTest.qWait(300)
        self.assertIsNone(stack.transition)
        self.assertTrue(stack.currentWidget().isVisible())
        self.window.reduce_motion.setChecked(True)
        self.window.show_home()
        self.assertIsNone(stack.transition)
        self.assertEqual(self.window.icon_preview.width(), round(256 * self.window.ui_scale))

    def test_transition_snapshot_has_no_background_rectangle(self):
        self.app.processEvents()
        image = transparent_snapshot(self.window.home_screen).toImage()
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(image.pixelColor(image.width()//2, 2).alpha(), 0)
        self.assertGreater(sum(image.pixelColor(x, image.height()//2).alpha() > 0
            for x in range(0, image.width(), 8)), 5)

    def test_frameless_corner_drag_resizes_window(self):
        self.window.resize(1440, 1040)
        QTest.qWait(100)
        border = self.window.resize_border
        corner = QPoint(border.width() - 3, border.height() - 3)
        QTest.mousePress(border, Qt.MouseButton.LeftButton, pos=corner)
        QTest.mouseMove(border, corner - QPoint(400, 300))
        QTest.mouseRelease(border, Qt.MouseButton.LeftButton)
        QTest.qWait(100)
        self.assertEqual((self.window.width(), self.window.height()), (1040, 740))
        self.assertIsNone(border.drag_origin)

    def test_home_update_tile_and_header_open_update_workflow_directly(self):
        self.window.reduce_motion.setChecked(True)
        self.window.home_screen.tiles[2].click()
        self.assertEqual(self.window.open_heading.text(), "Update a NUP")
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.assertEqual(self.window.open_tabs.currentIndex(), 5)
        self.assertTrue(self.window.nav.buttons[2].isChecked())
        self.window.show_home()
        self.window.nav.buttons[2].click()
        self.assertEqual(self.window.shell_pages.currentIndex(), 1)
        self.assertEqual(self.window.open_tabs.currentIndex(), 5)

    def test_tab_motion_interruption_and_compact_header(self):
        self.window.resize(1120, 760)
        self.window.nav.setCurrentRow(0)
        QTest.qWait(400)
        self.assertLess(self.window.nav.mapTo(self.window, QPoint(0, 0)).y(), 120)
        self.assertLessEqual(self.window.close_button.mapTo(self.window, self.window.close_button.rect().bottomRight()).x(), self.window.width())
        self.window.pack_tabs.setCurrentIndex(1)
        QTest.qWait(80)
        self.assertIsNotNone(self.window.pack_tabs.transition)
        self.window.pack_tabs.setCurrentIndex(2)
        QTest.qWait(400)
        self.assertTrue(self.window.pack_tabs.currentWidget().isVisible())
        self.assertFalse(self.window.pack_tabs.overlays)
        self.window.reduce_motion.setChecked(True)
        self.window.pack_tabs.setCurrentIndex(0)
        self.assertIsNone(self.window.pack_tabs.transition)

    def test_scan_and_store_preserve_manual_edits_and_clear_auto_fields(self):
        form = self.window.pack_metadata
        form.apply_detected({"values": {"name": "Folder title", "publisher": "Original publisher"}, "sources": {}})
        form.fields["publisher"].setText("My publisher")
        form.fields["display_version"].setText("1.0")
        form.fields["display_version"].clear()
        self.assertEqual(form.missing_fields(["name"]), {"name", "icon"})
        self.assertEqual(form.apply_missing({"name": "Store title", "publisher": "Store publisher", "icon": "art.png"},
                                            "https://www.nintendo.com/", ["name"]), ["name", "icon"])
        self.assertEqual(form.fields["name"].text(), "Store title")
        self.assertEqual(form.fields["publisher"].text(), "My publisher")
        self.assertEqual(form.fields["display_version"].text(), "")
        form.clear_detected()
        self.assertEqual(form.fields["name"].text(), "")
        self.assertEqual(form.fields["icon"].text(), "")
        self.assertEqual(form.fields["publisher"].text(), "My publisher")

    def test_store_review_requires_identity_match_or_explicit_confirmation(self):
        dialog = ShopDialog("Example", "0400000000001000", {"name", "icon"}, self.window)
        result = {"identity": "mismatch", "values": {"name": "Store title", "publisher": "Publisher", "title_id": "0400000000009999"},
                  "url": "https://www.nintendo.com/us/store/products/example/", "square_artwork": True,
                  "platform": "Nintendo Switch 2", "notices": []}
        dialog.show_product(result)
        self.assertFalse(dialog.apply_button.isEnabled())
        result["identity"] = "unconfirmed"
        dialog.show_product(result)
        self.assertFalse(dialog.apply_button.isEnabled())
        dialog.confirm_match.setChecked(True)
        self.assertTrue(dialog.apply_button.isEnabled())
        self.assertFalse(dialog.checks["publisher"].isEnabled())
        dialog.apply()
        self.assertEqual(dialog.selected, {"name": "Store title"})
        dialog.deleteLater()

    def test_summary_reflects_store_fill_and_manual_edits_after_scan(self):
        self.window.source.setText(str(self.source))
        self.window.scan()
        self.wait_for_job()
        self.assertIn("Publisher unavailable", self.window.detected_text.text())
        values = {"name": "Store name", "publisher": "Store publisher", "icon": "artwork.png"}
        self.window.pack_metadata.apply_missing(values, "https://www.nintendo.com/", ["name"])
        self.window.refresh_metadata_summary()
        text = self.window.detected_text.text()
        self.assertIn("Store publisher", text)
        self.assertIn("V458752", text)
        self.assertNotIn("folder-name suggestion", text)
        self.window.pack_metadata.fields["publisher"].setText("Manual publisher")
        self.assertIn("Manual publisher", self.window.detected_text.text())
        self.assertIn("Entered manually", self.window.detected_text.toolTip())

    def test_drop_events_scan_folders_and_open_containers(self):
        def drop(path):
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(path))])
            enter = QDragEnterEvent(QPoint(50, 50), Qt.DropAction.CopyAction, mime,
                                   Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(self.window, enter)
            self.assertTrue(enter.isAccepted())
            event = QDropEvent(QPointF(50, 50), Qt.DropAction.CopyAction, mime,
                               Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(self.window, event)
            self.wait_for_job()

        drop(self.source)
        self.assertEqual(self.window.packages.rowCount(), 3)
        self.assertEqual(self.window.pages.currentIndex(), 0)
        self.window.pack()
        self.wait_for_job()
        drop(Path(self.window.output.text()))
        self.assertEqual(self.window.package_choice.count(), 3)
        self.assertEqual(self.window.pages.currentIndex(), 1)

    def test_enter_starts_one_shop_request_without_cancelling_dialog(self):
        dialog = ShopDialog("https://www.nintendo.com/us/store/products/example/", "", {"name"}, self.window)
        requests = []

        def start(request):
            requests.append(request)
            dialog.runner.process = object()
            dialog.set_busy(True)

        dialog.runner.start = start
        dialog.runner.cancel = Mock()
        dialog.show()
        dialog.query.setFocus()
        self.app.processEvents()
        try:
            QTest.keyClick(dialog.query, Qt.Key.Key_Return)
            self.app.processEvents()
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]["operation"], "shop_details")
            self.assertFalse(dialog.close_pending)
            self.assertTrue(dialog.isVisible())
            dialog.runner.cancel.assert_not_called()
        finally:
            dialog.runner.process = None
            dialog.close()
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
