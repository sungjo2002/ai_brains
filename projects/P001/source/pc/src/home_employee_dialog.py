from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .icons import get_svg_icon


class HomeEmployeeDetailDialog(QDialog):
    _raw_photo_cache: dict[tuple[str, int], QPixmap] = {}
    _scaled_photo_cache: dict[tuple[str, int, int, int], QPixmap] = {}
    _default_photo_icon: QPixmap | None = None

    def __init__(self, employee: dict, state, parent=None):
        super().__init__(parent)
        self.employee = employee
        self.state = state
        self.is_resigned = str(self.employee.get("status") or "").strip() == "퇴사"
        self.setWindowTitle("근로자 상세 프로필")
        self.setFixedWidth(660)
        self.setMinimumHeight(760)
        self.setStyleSheet(
            """
            QDialog {
                background: #F8FAFC;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QFrame#HeaderCard, QFrame#SectionCard {
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 18px;
            }
            QLabel#HeaderTitle {
                font-size: 14px;
                font-weight: 800;
                color: #475569;
            }
            QLabel#ProfileName {
                font-size: 24px;
                font-weight: 900;
                color: #0F172A;
            }
            QLabel#ProfileId {
                font-size: 12px;
                font-weight: 700;
                color: #64748B;
                background: #EFF6FF;
                border: 1px solid #BFDBFE;
                border-radius: 12px;
                padding: 6px 6px;
            }
            QLabel#ProfileState {
                font-size: 12px;
                font-weight: 900;
                color: #B91C1C;
                background: #FEE2E2;
                border: 1px solid #FECACA;
                border-radius: 12px;
                padding: 6px 6px;
            }
            QLabel#SectionTitle {
                font-size: 14px;
                font-weight: 900;
                color: #1E293B;
            }
            QLabel#InfoKey {
                color: #64748B;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#InfoValue {
                color: #0F172A;
                font-size: 13px;
                font-weight: 800;
            }
            QLabel#TableHead {
                color: #475569;
                font-size: 12px;
                font-weight: 900;
                padding: 6px 6px;
                background: #F8FAFC;
                border-bottom: 1px solid #E2E8F0;
            }
            QFrame#HistoryHeader {
                background: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
            }
            QFrame#HistoryRow {
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
            }
            QLabel#HistoryCell {
                color: #0F172A;
                font-size: 12px;
                font-weight: 700;
                padding: 6px 6px;
            }
            QLabel#HistoryStatus {
                color: #1D4ED8;
                font-size: 11px;
                font-weight: 900;
                padding: 6px 6px;
                background: #DBEAFE;
                border: 1px solid #BFDBFE;
                border-radius: 10px;
            }
            QLabel#HistoryStatusResigned {
                color: #B91C1C;
                font-size: 11px;
                font-weight: 900;
                padding: 6px 6px;
                background: #FEE2E2;
                border: 1px solid #FECACA;
                border-radius: 10px;
            }
            QTextEdit#MemoEdit {
                background: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-radius: 12px;
                padding: 6px;
                font-size: 13px;
                color: #0F172A;
            }
            QPushButton#PrimaryButton {
                background: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: 800;
                padding: 6px 6px;
            }
            QPushButton#PrimaryButton:hover {
                background: #1D4ED8;
            }
            QPushButton#GhostButton {
                background: #E2E8F0;
                color: #0F172A;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: 700;
                padding: 6px 6px;
            }
            QPushButton#GhostButton:hover {
                background: #CBD5E1;
            }
            QPushButton#HistoryDeleteButton {
                background: #FEE2E2;
                color: #B91C1C;
                border: 1px solid #FECACA;
                border-radius: 8px;
                font-size: 11px;
                font-weight: 900;
                padding: 6px 6px;
                min-width: 24px;
            }
            QPushButton#HistoryDeleteButton:hover {
                background: #FECACA;
            }
            QLabel#PhotoFrame {
                background: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-radius: 16px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        root.addWidget(self._build_header_card())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.content_layout = QVBoxLayout(body)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)

        self._rebuild_detail_sections()

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_btn = QPushButton("닫기")
        close_btn.setObjectName("GhostButton")
        close_btn.clicked.connect(self.reject)
        save_btn = QPushButton("변경사항 저장")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self._save_changes)
        button_row.addWidget(close_btn)
        button_row.addWidget(save_btn)
        root.addLayout(button_row)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            widget = item.widget()
            if child_layout is not None:
                self._clear_layout(child_layout)
            if widget is not None:
                widget.deleteLater()

    def _rebuild_detail_sections(self):
        memo_text = self.memo_edit.toPlainText() if hasattr(self, "memo_edit") else None
        self._clear_layout(self.content_layout)
        self.content_layout.addWidget(self._build_work_info_card())
        self.content_layout.addWidget(self._build_history_card())
        self.content_layout.addWidget(self._build_memo_card())
        self.content_layout.addStretch(1)
        if memo_text is not None:
            self.memo_edit.setText(memo_text)

    def _build_header_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.photo_lbl = QLabel()
        self.photo_lbl.setObjectName("PhotoFrame")
        self.photo_lbl.setAlignment(Qt.AlignCenter)
        self.photo_lbl.setFixedSize(126, 160)
        self.photo_lbl.setAttribute(Qt.WA_StaticContents, True)
        self._load_photo()
        layout.addWidget(self.photo_lbl, 0, Qt.AlignTop)

        right = QVBoxLayout()
        right.setSpacing(6)
        title = QLabel("기본 및 인적 정보")
        title.setObjectName("HeaderTitle")
        right.addWidget(title)

        self.name_lbl = QLabel(self.employee.get("name", "이름 없음"))
        self.name_lbl.setObjectName("ProfileName")
        right.addWidget(self.name_lbl)

        english_name = str(self.employee.get("english_name") or self.employee.get("name_english") or "").strip()
        if english_name:
            english_lbl = QLabel(f"영문이름: {english_name}")
            english_lbl.setObjectName("InfoValue")
            english_lbl.setWordWrap(True)
            right.addWidget(english_lbl)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(6)
        display_no = self.state.employee_display_number(self.employee) if hasattr(self.state, "employee_display_number") else str(self.employee.get("id", "-"))
        id_badge = QLabel(display_no)
        id_badge.setObjectName("ProfileId")
        badge_row.addWidget(id_badge, 0, Qt.AlignLeft)
        if self.is_resigned:
            state_badge = QLabel("퇴사자")
            state_badge.setObjectName("ProfileState")
            badge_row.addWidget(state_badge, 0, Qt.AlignLeft)
        badge_row.addStretch(1)
        right.addLayout(badge_row)

        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(6)
        info_grid.setVerticalSpacing(6)
        info_grid.setColumnStretch(1, 1)
        info_grid.setColumnStretch(3, 1)
        rows = [
            ("국적", self.employee.get("nation") or "-", "성별", self.employee.get("gender") or "-"),
            ("생년월일", self.employee.get("birth_date") or "-", "연락처", self.employee.get("phone") or "-"),
        ]
        for row_idx, (k1, v1, k2, v2) in enumerate(rows):
            info_grid.addWidget(self._kv_label(k1, "InfoKey"), row_idx, 0)
            info_grid.addWidget(self._kv_label(v1, "InfoValue", wrap=True), row_idx, 1)
            info_grid.addWidget(self._kv_label(k2, "InfoKey"), row_idx, 2)
            info_grid.addWidget(self._kv_label(v2, "InfoValue", wrap=True), row_idx, 3)
        right.addLayout(info_grid)
        right.addStretch(1)
        layout.addLayout(right, 1)
        return card

    def _latest_history(self) -> dict:
        history = self.employee.get("work_history") or []
        if history:
            return history[-1]
        return {}

    def _build_work_info_card(self) -> QFrame:
        latest = self._latest_history()
        if self.is_resigned:
            card, body = self._create_section_card("퇴사 정보")
            grid = QGridLayout()
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(6)
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(3, 1)
            rows = [
                ("현재 근무", "없음", "마지막 근무현장", latest.get("work_site") or self.employee.get("work_site") or "-"),
                ("퇴사일", self.employee.get("actual_end") or latest.get("end_date") or "-", "퇴사사유", self.employee.get("resign_reason") or latest.get("reason") or "-"),
            ]
            for row_idx, (k1, v1, k2, v2) in enumerate(rows):
                grid.addWidget(self._kv_label(k1, "InfoKey"), row_idx, 0)
                grid.addWidget(self._kv_label(v1, "InfoValue", wrap=True), row_idx, 1)
                grid.addWidget(self._kv_label(k2, "InfoKey"), row_idx, 2)
                grid.addWidget(self._kv_label(v2, "InfoValue", wrap=True), row_idx, 3)
            body.addLayout(grid)
            resign_note = str(self.employee.get("resign_note") or "").strip()
            if resign_note:
                note_title = QLabel("퇴사 비고")
                note_title.setObjectName("InfoKey")
                body.addWidget(note_title)
                body.addWidget(self._kv_label(resign_note, "InfoValue", wrap=True))
            return card

        card, body = self._create_section_card("근무 및 급여 정보")
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        rows = [
            ("소속사업자", self.employee.get("affiliated_business") or "-", "근무현장", self.employee.get("work_site") or "-"),
            ("입사일", self.employee.get("hire_date", self.employee.get("join_date", "-")) or "-", "급여형태", self.employee.get("pay_type") or "-"),
        ]
        for row_idx, (k1, v1, k2, v2) in enumerate(rows):
            grid.addWidget(self._kv_label(k1, "InfoKey"), row_idx, 0)
            grid.addWidget(self._kv_label(v1, "InfoValue", wrap=True), row_idx, 1)
            grid.addWidget(self._kv_label(k2, "InfoKey"), row_idx, 2)
            grid.addWidget(self._kv_label(v2, "InfoValue", wrap=True), row_idx, 3)
        body.addLayout(grid)
        return card

    def _build_history_card(self) -> QFrame:
        card, body = self._create_section_card("근무 이력")
        raw_history = self.employee.get("work_history") or []
        indexed_history = list(enumerate(raw_history))
        indexed_history.reverse()

        header = QFrame()
        header.setObjectName("HistoryHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        for text, stretch in [("근무기간", 30), ("근무현장", 19), ("상태", 16), ("비고", 27), ("", 8)]:
            lbl = QLabel(text)
            lbl.setObjectName("TableHead")
            header_layout.addWidget(lbl, stretch)
        body.addWidget(header)

        if not indexed_history:
            indexed_history = [(-1, {"start_date": "-", "end_date": "", "work_site": "-", "status": "-", "reason": "", "note": ""})]

        history_count = len(raw_history)
        for original_index, row in indexed_history:
            row_card = QFrame()
            row_card.setObjectName("HistoryRow")
            row_layout = QHBoxLayout(row_card)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(0)

            period = f'{row.get("start_date") or "-"} ~ {row.get("end_date") or "현재"}'
            note_parts = []
            reason = str(row.get("reason") or "").strip()
            note = str(row.get("note") or "").strip()
            if reason:
                note_parts.append(reason)
            if note:
                note_parts.append(note)
            extra = " / ".join(note_parts) if note_parts else "-"

            row_layout.addWidget(self._history_cell(period), 30)
            row_layout.addWidget(self._history_cell(str(row.get("work_site") or "-")), 19)
            row_layout.addWidget(self._history_status_cell(str(row.get("status") or "-")), 16)
            row_layout.addWidget(self._history_cell(extra, wrap=True), 27)
            row_layout.addWidget(self._history_delete_cell(row, original_index, history_count), 8)
            body.addWidget(row_card)
        return card

    def _is_deletable_work_history_row(self, row: dict, history_count: int) -> bool:
        if history_count <= 1:
            return False
        if not isinstance(row, dict):
            return False
        if bool(row.get("active")):
            return False
        if not str(row.get("end_date") or "").strip():
            return False
        return True

    def _history_delete_cell(self, row: dict, original_index: int, history_count: int) -> QWidget:
        wrap = QWidget()
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)
        layout.addStretch(1)
        if original_index >= 0 and self._is_deletable_work_history_row(row, history_count):
            button = QPushButton("X")
            button.setObjectName("HistoryDeleteButton")
            button.setToolTip("과거 근무이력 삭제")
            button.clicked.connect(lambda _checked=False, idx=original_index: self._confirm_delete_work_history(idx))
            layout.addWidget(button, 0, Qt.AlignCenter)
        return wrap

    def _confirm_delete_work_history(self, history_index: int):
        history = self.employee.get("work_history") or []
        if history_index < 0 or history_index >= len(history):
            QMessageBox.warning(self, "삭제 불가", "삭제할 근무이력을 찾을 수 없습니다.")
            return
        row = history[history_index]
        if not self._is_deletable_work_history_row(row, len(history)):
            QMessageBox.warning(self, "삭제 불가", "현재 적용 중인 근무이력은 삭제할 수 없습니다.")
            return
        period = f'{row.get("start_date") or "-"} ~ {row.get("end_date") or "현재"}'
        work_site = str(row.get("work_site") or "-")
        status = str(row.get("status") or "-")
        reply = QMessageBox.question(
            self,
            "근무이력 삭제 확인",
            "선택한 근무이력을 삭제하시겠습니까?\n"
            "삭제 후에는 복구할 수 없습니다.\n\n"
            f"기간: {period}\n"
            f"근무현장: {work_site}\n"
            f"상태: {status}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            updated = self.state.delete_employee_work_history_entry(int(self.employee["id"]), history_index)
            self.employee = updated
            self.is_resigned = str(self.employee.get("status") or "").strip() == "퇴사"
            self._rebuild_detail_sections()
            QMessageBox.information(self, "삭제 완료", "선택한 근무이력을 삭제했습니다.")
        except Exception as error:
            QMessageBox.critical(self, "삭제 실패", f"근무이력 삭제 중 오류가 발생했습니다.\n{error}")

    def _build_memo_card(self) -> QFrame:
        card, body = self._create_section_card("관리자 메모")
        self.memo_edit = QTextEdit()
        self.memo_edit.setObjectName("MemoEdit")
        self.memo_edit.setPlaceholderText("근로자에 대한 참고사항을 입력하세요...")
        self.memo_edit.setText(self.employee.get("note", ""))
        self.memo_edit.setMinimumHeight(132)
        body.addWidget(self.memo_edit)
        return card

    def _create_section_card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("SectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("SectionTitle")
        layout.addWidget(title_lbl)
        return card, layout

    def _kv_label(self, text: str, object_name: str, wrap: bool = False) -> QLabel:
        label = QLabel(str(text))
        label.setObjectName(object_name)
        label.setWordWrap(wrap)
        return label

    def _history_cell(self, text: str, wrap: bool = False) -> QLabel:
        label = QLabel(str(text))
        label.setObjectName("HistoryCell")
        label.setWordWrap(wrap)
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        return label

    def _history_status_cell(self, text: str) -> QWidget:
        wrap = QWidget()
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)
        badge = QLabel(text)
        badge.setObjectName("HistoryStatusResigned" if str(text).strip() == "퇴사" else "HistoryStatus")
        layout.addWidget(badge, 0, Qt.AlignLeft | Qt.AlignVCenter)
        layout.addStretch(1)
        return wrap

    def _save_changes(self):
        new_note = self.memo_edit.toPlainText().strip()
        try:
            self.state.update_employee(int(self.employee["id"]), {"note": new_note})
            QMessageBox.information(self, "저장 완료", "관리자 메모가 저장되었습니다.")
            self.accept()
        except Exception as error:
            QMessageBox.critical(self, "저장 실패", f"정보 저장 중 오류가 발생했습니다.\n{error}")

    def _resize_photo_box(self, pixmap: QPixmap):
        if pixmap.isNull():
            return
        img_w = max(1, pixmap.width())
        img_h = max(1, pixmap.height())
        max_w, max_h = 126, 160
        min_w, min_h = 88, 116
        scale = min(max_w / img_w, max_h / img_h)
        box_w = max(min_w, int(img_w * scale))
        box_h = max(min_h, int(img_h * scale))
        self.photo_lbl.setFixedSize(min(max_w, box_w), min(max_h, box_h))

    def _photo_mtime_key(self, portrait_path: str) -> int:
        try:
            return int(Path(portrait_path).stat().st_mtime_ns)
        except Exception:
            return 0

    def _load_photo_pixmap_cached(self, portrait_path: str, mtime_key: int) -> QPixmap:
        cache_key = (portrait_path, mtime_key)
        cached = self._raw_photo_cache.get(cache_key)
        if cached is None:
            loaded = QPixmap(str(portrait_path))
            cached = loaded if not loaded.isNull() else QPixmap()
            self._raw_photo_cache[cache_key] = cached
        return cached

    def _scaled_photo_pixmap_cached(self, portrait_path: str, mtime_key: int, width: int, height: int) -> QPixmap:
        cache_key = (portrait_path, mtime_key, width, height)
        cached = self._scaled_photo_cache.get(cache_key)
        if cached is None:
            raw = self._load_photo_pixmap_cached(portrait_path, mtime_key)
            cached = raw.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not raw.isNull() else QPixmap()
            self._scaled_photo_cache[cache_key] = cached
        return cached

    def _load_photo(self):
        portrait_raw = str(self.employee.get("portrait_path", "") or "").strip()
        portrait_path = self.state.resolve_storage_file_path(portrait_raw)
        if not portrait_path:
            target_path, _rel = self.state.get_employee_portrait_storage_path(self.employee["id"], ".png")
            portrait_path = str(target_path) if target_path.exists() else ""
        if portrait_path and Path(portrait_path).exists():
            mtime_key = self._photo_mtime_key(portrait_path)
            raw = self._load_photo_pixmap_cached(portrait_path, mtime_key)
            if not raw.isNull():
                self._resize_photo_box(raw)
                scaled = self._scaled_photo_pixmap_cached(
                    portrait_path,
                    mtime_key,
                    max(1, self.photo_lbl.width()),
                    max(1, self.photo_lbl.height()),
                )
                if not scaled.isNull():
                    self.photo_lbl.setPixmap(scaled)
                    return
        if self.__class__._default_photo_icon is None or self.__class__._default_photo_icon.isNull():
            self.__class__._default_photo_icon = get_svg_icon("employee", "#94A3B8", 72)
        self.photo_lbl.setPixmap(self.__class__._default_photo_icon)
