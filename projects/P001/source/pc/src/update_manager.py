from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from PySide6.QtCore import QUrl

from .app_metadata import PROGRAM_VERSION
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in str(value or "").strip().split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            digits = "".join(ch for ch in chunk if ch.isdigit())
            parts.append(int(digits or 0))
    return tuple(parts or [0])


class UpdatePopup(QDialog):
    def __init__(self, current_version: str, latest_info: dict[str, Any], parent=None):
        super().__init__(parent)
        self.latest_info = dict(latest_info or {})
        self.setWindowTitle("업데이트 확인")
        self.setModal(True)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        title = QLabel("새 버전이 있습니다")
        title.setStyleSheet("font-size:20px; font-weight:900; color:#1C1917;")
        root.addWidget(title)

        current_label = QLabel(f"현재 버전: {current_version}")
        current_label.setStyleSheet("font-size:13px; font-weight:700; color:#44403C;")
        root.addWidget(current_label)

        latest_label = QLabel(f"최신 버전: {self.latest_info.get('version', '-')}")
        latest_label.setStyleSheet("font-size:13px; font-weight:700; color:#44403C;")
        root.addWidget(latest_label)

        note_box = QFrame()
        note_box.setStyleSheet("background:#FAFAF9; border:1px solid #E7E5E4; border-radius:12px;")
        note_layout = QVBoxLayout(note_box)
        note_layout.setContentsMargins(6, 6, 6, 6)
        note_layout.setSpacing(6)

        note_title = QLabel("업데이트 내용")
        note_title.setStyleSheet("font-size:12px; font-weight:900; color:#57534E;")
        note_layout.addWidget(note_title)

        notes = str(self.latest_info.get("notes") or "업데이트 설명이 없습니다.").strip()
        note_text = QLabel(notes)
        note_text.setWordWrap(True)
        note_text.setStyleSheet("font-size:12px; font-weight:600; color:#57534E;")
        note_layout.addWidget(note_text)
        root.addWidget(note_box)

        guide = QLabel("업그레이드를 누르면 다운로드 페이지를 엽니다.")
        guide.setWordWrap(True)
        guide.setStyleSheet("font-size:12px; font-weight:600; color:#78716C;")
        root.addWidget(guide)

        buttons = QHBoxLayout()
        buttons.addStretch()

        later_btn = QPushButton("나중에")
        later_btn.setFixedHeight(30)
        later_btn.setStyleSheet("background:#FFFFFF; color:#57534E; border:1px solid #D6D3D1; border-radius:9px; padding: 0 6px; font-weight:800;")
        later_btn.clicked.connect(self.reject)
        buttons.addWidget(later_btn)

        upgrade_btn = QPushButton("업그레이드")
        upgrade_btn.setFixedHeight(30)
        upgrade_btn.setStyleSheet("background:#FF6A1A; color:#FFFFFF; border:1px solid #EA580C; border-radius:9px; padding: 0 6px; font-weight:900;")
        upgrade_btn.clicked.connect(self._open_upgrade_url)
        buttons.addWidget(upgrade_btn)

        root.addLayout(buttons)

    def _open_upgrade_url(self):
        raw = str(self.latest_info.get("url") or "").strip()
        if not raw:
            QMessageBox.information(self, "업데이트", "다운로드 주소가 아직 설정되지 않았습니다.")
            return
        if QDesktopServices.openUrl(QUrl(raw)):
            self.accept()
            return
        QMessageBox.warning(self, "업데이트", "다운로드 주소를 열지 못했습니다.")


class UpdateManager:
    def __init__(self, storage_manager):
        self.storage = storage_manager
        self.storage.ensure_structure()

    def load_settings(self) -> dict[str, Any]:
        settings = self.storage.load_update_settings({})
        if settings.get("current_version") != self._current_version():
            settings["current_version"] = self._current_version()
            self.storage.save_update_settings(settings)
        return settings

    def _current_version(self) -> str:
        return PROGRAM_VERSION

    def fetch_latest_info(self) -> dict[str, Any] | None:
        settings = self.load_settings()
        if not settings.get("enabled", True):
            return None
        if not settings.get("auto_check_on_start", True):
            return None
        info_url = str(settings.get("update_info_url") or "").strip()
        if not info_url:
            return None
        try:
            timeout = max(1, min(15, int(settings.get("check_timeout_seconds", 3) or 3)))
        except (TypeError, ValueError):
            timeout = 3

        try:
            with urlopen(info_url, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return None
        except (URLError, OSError, json.JSONDecodeError, TimeoutError, ValueError):
            return None

        settings["last_checked_at"] = _utc_now_iso()
        self.storage.save_update_settings(settings)
        return payload

    def should_show_popup(self, latest_info: dict[str, Any] | None) -> bool:
        if not latest_info:
            return False
        latest_version = str(latest_info.get("version") or "").strip()
        if not latest_version:
            return False
        settings = self.load_settings()
        skip_version = str(settings.get("skip_version") or "").strip()
        if skip_version and skip_version == latest_version:
            return False
        current_version = str(settings.get("current_version") or self._current_version()).strip()
        return _version_tuple(latest_version) > _version_tuple(current_version)

    def check_and_prompt(self, parent: QWidget | None = None) -> bool:
        latest_info = self.fetch_latest_info()
        if not self.should_show_popup(latest_info):
            return False
        current_version = str(self.load_settings().get("current_version") or self._current_version()).strip()
        dialog = UpdatePopup(current_version, latest_info or {}, parent=parent)
        dialog.exec()
        return True
