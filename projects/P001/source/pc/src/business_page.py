from __future__ import annotations

import re
from copy import deepcopy

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from .background_workers import FunctionWorkerThread
from .business_certificate_ocr import extract_business_registration, get_ocr_engine_status
from .table_column_manager import install_resizable_table_columns
from .widgets import MiniMetricCard, Panel, PAGE_OUTER_MARGINS, PAGE_OUTER_SPACING, PAGE_INNER_MARGINS, PAGE_INNER_SPACING


class RegistrationDialog(QDialog):
    def __init__(self, state, mode: str, record: dict | None = None, parent_business: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.mode = mode
        self.record = deepcopy(record or {})
        self.record_source = self.record.get("original_form", self.record) if self.record else None
        self.record_name = self.record_source.get("name") if self.record_source else None
        self.saved_name = ""
        self.saved_business_name = parent_business or ""
        self.parent_business = parent_business
        self.certificate_path = self.record_source.get("certificate_path", "") if self.record_source else ""
        self.ocr_raw_text = str(self.record.get("ocr_raw_text", "") or "")
        self.ocr_parsed_data = deepcopy(self.record.get("ocr_parsed_data", {})) if isinstance(self.record.get("ocr_parsed_data"), dict) else {}
        self._ocr_worker: FunctionWorkerThread | None = None

        is_business = mode == "business"
        is_work_site = mode == "work_site"
        # 근무 사업장 등록도 사업자 신규 등록창의 입력 방식과 동일하게 사용합니다.
        use_business_form = is_business or is_work_site
        title_text = ("사업자 " if is_business else "근무 사업장 ") + ("수정" if record else "신규 등록")
        self.setWindowTitle(title_text)
        self.setModal(True)
        # 사업자 등록창과 근무 사업장 등록창의 표시 방식을 동일하게 맞춥니다.
        self.resize(520, 760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header = QLabel(title_text)
        header.setObjectName("DetailName")
        layout.addWidget(header)

        if use_business_form:
            self.ocr_container = QWidget()
            ocr_box = QVBoxLayout(self.ocr_container)
            ocr_box.setContentsMargins(0, 0, 0, 0)
            ocr_box.setSpacing(6)

            button_row = QHBoxLayout()
            self.load_certificate_btn = QPushButton("등록증 불러오기")
            self.load_certificate_btn.setObjectName("GhostButton")
            self.load_certificate_btn.clicked.connect(self.load_certificate_image)
            button_row.addWidget(self.load_certificate_btn)

            self.run_ocr_btn = QPushButton("자동 인식")
            self.run_ocr_btn.setObjectName("GhostButton")
            self.run_ocr_btn.clicked.connect(self.run_certificate_ocr)
            button_row.addWidget(self.run_ocr_btn)
            button_row.addStretch()
            ocr_box.addLayout(button_row)

            self.certificate_path_label = QLabel(self.certificate_path if self.certificate_path else "불러온 등록증 파일이 없습니다.")
            self.certificate_path_label.setObjectName("DetailMeta")
            self.certificate_path_label.setWordWrap(True)
            ocr_box.addWidget(self.certificate_path_label)

            self.ocr_status_badge = QLabel("OCR 대기")
            self.ocr_status_badge.setObjectName("StatusBadge")
            ocr_box.addWidget(self.ocr_status_badge)
            layout.addWidget(self.ocr_container)
        else:
            self.ocr_container = None
            self.load_certificate_btn = None
            self.run_ocr_btn = None
            self.certificate_path_label = None
            self.ocr_status_badge = None

        form = QFormLayout()
        form.setContentsMargins(0, 6, 0, 0)
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(6)

        self.name_edit = QLineEdit()
        self.manager_name_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        self.address_edit = QLineEdit()
        self.note_edit = QTextEdit()
        self.site_code_edit = None
        self.default_work_type_edit = None
        self.note_edit.setFixedHeight(78)

        self.active_combo = QComboBox()
        self.active_combo.addItems(["사용", "중지"])

        self.work_site_business_combo = None
        self._business_name_options = [str(row.get("name", "") or "").strip() for row in self.state.business_records()] if self.state is not None else []

        if use_business_form:
            self.business_number_edit = QLineEdit()
            self.representative_name_edit = QLineEdit()
            self.email_edit = QLineEdit()
            self.business_type_edit = QLineEdit()
            self.business_item_edit = QLineEdit()
            self.opening_date_edit = QDateEdit()
            self.opening_date_edit.setCalendarPopup(True)
            self.opening_date_edit.setDisplayFormat("yyyy-MM-dd")
            self.opening_date_edit.setMinimumDate(QDate(1900, 1, 1))
            self.opening_date_edit.setDate(QDate(1900, 1, 1))
            self.issue_date_edit = QDateEdit()
            self.issue_date_edit.setCalendarPopup(True)
            self.issue_date_edit.setDisplayFormat("yyyy-MM-dd")
            self.issue_date_edit.setMinimumDate(QDate(1900, 1, 1))
            self.issue_date_edit.setDate(QDate(1900, 1, 1))

            if is_work_site:
                self.work_site_business_combo = QComboBox()
                business_names = [name for name in self._business_name_options if name]
                if business_names:
                    self.work_site_business_combo.addItems(business_names)
                form.addRow("소속 사업자", self.work_site_business_combo)

            form.addRow("사업자명", self.name_edit)
            form.addRow("사업자번호", self.business_number_edit)
            form.addRow("대표자", self.representative_name_edit)
            form.addRow("연락처", self.phone_edit)
            form.addRow("이메일", self.email_edit)
            form.addRow("주소", self.address_edit)
            form.addRow("개업일", self.opening_date_edit)
            form.addRow("업태", self.business_type_edit)
            form.addRow("종목", self.business_item_edit)
            form.addRow("발행일", self.issue_date_edit)
            form.addRow("운영 상태", self.active_combo)
            form.addRow("메모", self.note_edit)
        else:
            # 현재 사업자 관리에서는 사용하지 않는 예비 분기입니다.
            self.work_site_business_combo = QComboBox()
            self.site_code_edit = QLineEdit()
            self.default_work_type_edit = QLineEdit()
            form.addRow("근무 사업장명", self.name_edit)
            form.addRow("대표 연락처", self.phone_edit)
            form.addRow("주소", self.address_edit)
            form.addRow("운영 상태", self.active_combo)
            form.addRow("메모", self.note_edit)

        layout.addLayout(form)
        layout.addStretch()

        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = QPushButton("취소")
        cancel_btn.setObjectName("GhostButton")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("저장")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self.save)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(save_btn)
        layout.addLayout(button_row)

        if use_business_form:
            self._refresh_ocr_availability()
        if is_work_site and not self.record_source:
            self._set_work_site_business(self.parent_business or "")
        if self.record_source:
            self.load_record(self.record_source)

    def load_record(self, source: dict):
        self.name_edit.setText(source.get("name", ""))
        self.manager_name_edit.setText(source.get("manager_name", ""))
        self.phone_edit.setText(source.get("phone", ""))
        self.address_edit.setText(source.get("address", ""))
        self.note_edit.setPlainText(source.get("note", ""))
        self.active_combo.setCurrentText("사용" if source.get("active", True) else "중지")

        if self.mode in ("business", "work_site"):
            if self.mode == "work_site" and self.work_site_business_combo is not None:
                business_name = str(source.get("business_name", self.parent_business or "") or "").strip()
                self._set_work_site_business(business_name)
            self.business_number_edit.setText(source.get("business_number", ""))
            self.representative_name_edit.setText(source.get("representative_name", ""))
            self.email_edit.setText(source.get("email", ""))
            self.business_type_edit.setText(source.get("business_type", ""))
            self.business_item_edit.setText(source.get("business_item", ""))
            self._set_date_text(self.opening_date_edit, source.get("opening_date", ""))
            self._set_date_text(self.issue_date_edit, source.get("issue_date", ""))
        else:
            business_name = source.get("business_name", self.parent_business or "")
            if business_name:
                self.work_site_business_combo.setCurrentText(business_name)
            if self.site_code_edit is not None:
                self.site_code_edit.setText(source.get("site_code", ""))
            if self.default_work_type_edit is not None:
                self.default_work_type_edit.setText(source.get("default_work_type", ""))

    def _set_work_site_business(self, business_name: str):
        if self.work_site_business_combo is None:
            return
        target = str(business_name or "").strip()
        if target and self.work_site_business_combo.findText(target) < 0:
            self.work_site_business_combo.addItem(target)
        if target:
            self.work_site_business_combo.setCurrentText(target)

    def _set_date_text(self, edit: QDateEdit, date_str: str):
        if not date_str:
            return
        numbers = re.findall(r"\d+", str(date_str))
        if len(numbers) >= 3:
            try:
                year, month, day = int(numbers[0]), int(numbers[1]), int(numbers[2])
                if year < 100:
                    year += 2000
                edit.setDate(QDate(year, month, day))
            except Exception:
                edit.setDate(edit.minimumDate())
        else:
            edit.setDate(edit.minimumDate())

    def _get_date_text(self, edit: QDateEdit) -> str:
        return "" if edit.date() == edit.minimumDate() else edit.date().toString("yyyy-MM-dd")

    def _refresh_ocr_availability(self):
        if self.mode not in ("business", "work_site") or self.run_ocr_btn is None:
            return
        available, _ = get_ocr_engine_status()
        self.run_ocr_btn.setEnabled(available)
        if self.ocr_status_badge is not None and not available:
            self.ocr_status_badge.setText("OCR 사용 불가")

    def load_certificate_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "등록증 선택", "", "이미지 (*.png *.jpg *.jpeg)")
        if path:
            self.certificate_path = path
            if self.certificate_path_label is not None:
                self.certificate_path_label.setText(path)
            if self.ocr_status_badge is not None:
                self.ocr_status_badge.setText("OCR 준비")

    def run_certificate_ocr(self):
        if not self.certificate_path:
            QMessageBox.warning(self, "사업자 관리", "등록증 파일을 먼저 불러와 주세요.")
            return
        if self._ocr_worker is not None and self._ocr_worker.isRunning():
            return

        self._set_ocr_busy(True)
        if self.ocr_status_badge is not None:
            self.ocr_status_badge.setText("OCR 실행 중...")
        self._ocr_worker = FunctionWorkerThread(
            extract_business_registration,
            self.certificate_path,
            progress_keyword="progress_callback",
        )
        if self.ocr_status_badge is not None:
            self._ocr_worker.progress_changed.connect(self.ocr_status_badge.setText)
        self._ocr_worker.result_ready.connect(self._handle_business_ocr_result)
        self._ocr_worker.error_occurred.connect(self._handle_business_ocr_error)
        self._ocr_worker.finished.connect(self._cleanup_business_ocr_worker)
        self._ocr_worker.start()

    def _set_ocr_busy(self, is_busy: bool):
        if self.load_certificate_btn is not None:
            self.load_certificate_btn.setEnabled(not is_busy)
        if self.run_ocr_btn is not None:
            self.run_ocr_btn.setEnabled(not is_busy)

    def _handle_business_ocr_result(self, result: dict):
        for key, widget in [
            ("name", self.name_edit),
            ("business_number", self.business_number_edit),
            ("representative_name", self.representative_name_edit),
            ("address", self.address_edit),
            ("business_type", self.business_type_edit),
            ("business_item", self.business_item_edit),
            ("email", self.email_edit),
        ]:
            if result.get(key):
                widget.setText(str(result[key]))

        if result.get("opening_date"):
            self._set_date_text(self.opening_date_edit, str(result["opening_date"]))
        if result.get("issue_date"):
            self._set_date_text(self.issue_date_edit, str(result["issue_date"]))

        self.ocr_raw_text = str(result.get("raw_text", "") or "")
        self.ocr_parsed_data = {key: value for key, value in result.items() if key != "raw_text" and value not in (None, "")}
        if self.ocr_status_badge is not None:
            self.ocr_status_badge.setText("OCR 완료")

    def _handle_business_ocr_error(self, message: str):
        QMessageBox.warning(self, "OCR 오류", message)
        if self.ocr_status_badge is not None:
            self.ocr_status_badge.setText("OCR 실패")

    def _cleanup_business_ocr_worker(self):
        self._set_ocr_busy(False)
        self._refresh_ocr_availability()
        worker = self._ocr_worker
        self._ocr_worker = None
        if worker is not None:
            worker.deleteLater()

    def save(self):
        payload = {
            "name": self.name_edit.text().strip(),
            "phone": self.phone_edit.text().strip(),
            "address": self.address_edit.text().strip(),
            "active": self.active_combo.currentText() == "사용",
            "note": self.note_edit.toPlainText().strip(),
        }
        if self.mode in ("business", "work_site"):
            payload.update({
                "business_number": self.business_number_edit.text().strip(),
                "representative_name": self.representative_name_edit.text().strip(),
                "email": self.email_edit.text().strip(),
                "opening_date": self._get_date_text(self.opening_date_edit),
                "business_type": self.business_type_edit.text().strip(),
                "business_item": self.business_item_edit.text().strip(),
                "issue_date": self._get_date_text(self.issue_date_edit),
                "certificate_path": self.certificate_path,
                "ocr_raw_text": self.ocr_raw_text,
                "ocr_parsed_data": deepcopy(self.ocr_parsed_data),
            })

        if not payload["name"]:
            label = "사업자명" if self.mode == "business" else "근무 사업장명"
            QMessageBox.warning(self, "사업자 관리", f"{label}을 입력해 주세요.")
            return

        try:
            if self.mode == "business":
                if self.record_name:
                    self.state.update_business(self.record_name, payload)
                else:
                    self.state.add_business(payload)
            else:
                business_name = ""
                if self.work_site_business_combo is not None:
                    business_name = self.work_site_business_combo.currentText().strip()
                if not business_name:
                    business_name = (self.parent_business or "").strip()
                if not business_name and self.record_source:
                    business_name = str(self.record_source.get("business_name", "") or "").strip()
                if not business_name:
                    QMessageBox.warning(self, "사업자 관리", "소속 사업자를 선택해 주세요.")
                    return
                payload["business_name"] = business_name
                # 기존 사업장 코드/기본 근무형태 값이 있으면 보존합니다.
                payload["site_code"] = self.record_source.get("site_code", "") if self.record_source else ""
                payload["default_work_type"] = self.record_source.get("default_work_type", "") if self.record_source else ""
                if self.record_name:
                    old_parent = self.record_source.get("business_name") if self.record_source else self.parent_business
                    self.state.update_work_site(old_parent, self.record_name, payload)
                else:
                    self.state.add_work_site(business_name, payload)
            self.saved_name = str(payload.get("name", "") or "").strip()
            self.saved_business_name = str(payload.get("business_name", self.parent_business or "") or "").strip()
            self.accept()
        except ValueError as err:
            QMessageBox.warning(self, "사업자 관리", str(err))


class BulkWorkSiteDialog(QDialog):
    def __init__(self, parent=None, state=None, parent_business: str | None = None):
        super().__init__(parent)
        self.state = state
        self.parent_business = parent_business
        self.setWindowTitle("근무 사업장 일괄 등록")
        self.setModal(True)
        self.resize(820, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header = QLabel("근무 사업장 일괄 등록")
        header.setObjectName("DetailName")
        layout.addWidget(header)

        info = QLabel("사업장명은 필수입니다. 한 번에 여러 현장을 넣을 때 사용합니다.")
        info.setObjectName("DetailValue")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.business_combo = QComboBox()
        businesses = [row.get("name", "") for row in self.state.business_master_records() if row.get("name")]
        for b_name in businesses:
            self.business_combo.addItem(b_name)
        if self.parent_business:
            self.business_combo.setCurrentText(self.parent_business)
        form.addRow("소속 사업자", self.business_combo)
        layout.addLayout(form)

        self.table = QTableWidget(10, 5)
        self.table.setHorizontalHeaderLabels(["근무 사업장명 (*)", "주소", "담당자", "연락처", "메모"])
        install_resizable_table_columns(
            self.table,
            state=self.state,
            key="business/bulk_work_site_dialog",
            default_widths=[160, 210, 110, 118, 180],
            min_widths=[120, 130, 82, 96, 110],
        )
        layout.addWidget(self.table)

        button_row = QHBoxLayout()
        self.add_row_btn = QPushButton("+ 5행 추가")
        self.add_row_btn.setObjectName("SecondaryButton")
        self.add_row_btn.clicked.connect(self._add_rows)
        button_row.addWidget(self.add_row_btn)
        button_row.addStretch()
        cancel_btn = QPushButton("취소")
        cancel_btn.setObjectName("GhostButton")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("일괄 저장")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self.save)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(save_btn)
        layout.addLayout(button_row)

    def _add_rows(self):
        self.table.setRowCount(self.table.rowCount() + 5)

    def save(self):
        business_name = self.business_combo.currentText().strip()
        if not business_name:
            QMessageBox.warning(self, "사업자 관리", "소속 사업자를 선택해 주세요.")
            return

        pending_rows: list[dict] = []
        seen_names: set[str] = set()
        duplicate_names: list[str] = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            name = name_item.text().strip() if name_item else ""
            if not name:
                continue
            normalized_name = name.lower()
            if normalized_name in seen_names:
                duplicate_names.append(name)
                continue
            seen_names.add(normalized_name)
            pending_rows.append({
                "name": name,
                "address": self.table.item(row, 1).text().strip() if self.table.item(row, 1) else "",
                "manager_name": self.table.item(row, 2).text().strip() if self.table.item(row, 2) else "",
                "phone": self.table.item(row, 3).text().strip() if self.table.item(row, 3) else "",
                "note": self.table.item(row, 4).text().strip() if self.table.item(row, 4) else "",
                "business_name": business_name,
            })

        if not pending_rows:
            QMessageBox.warning(self, "사업자 관리", "입력된 근무 사업장이 없습니다.")
            return

        if duplicate_names:
            QMessageBox.warning(self, "사업자 관리", "중복 입력된 근무 사업장명이 있습니다.\n\n" + "\n".join(duplicate_names[:10]))
            return

        existing_names = {
            str(row.get("name", "") or "").strip().lower()
            for row in self.state.work_site_records(business_name)
            if str(row.get("name", "") or "").strip()
        }
        already_registered = [
            row["name"] for row in pending_rows
            if str(row.get("name", "") or "").strip().lower() in existing_names
        ]
        if already_registered:
            QMessageBox.warning(
                self,
                "사업자 관리",
                "이미 등록된 근무 사업장명이 있어 저장하지 않았습니다.\n\n" + "\n".join(already_registered[:10]),
            )
            return

        try:
            for payload in pending_rows:
                self.state.add_work_site(business_name, payload)
            QMessageBox.information(self, "사업자 관리", f"근무 사업장 {len(pending_rows)}건을 등록했습니다.")
            self.accept()
        except Exception as err:
            QMessageBox.warning(self, "사업자 관리", str(err))

class BusinessPage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.records: list[dict] = []
        self.filtered_records: list[dict] = []
        self.work_site_records: list[dict] = []
        self.filtered_work_site_records: list[dict] = []
        self.selected_name: str | None = None
        self.selected_work_site_name: str | None = None

        self.state.employees_changed.connect(self.refresh_from_state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*PAGE_OUTER_MARGINS)
        layout.setSpacing(PAGE_OUTER_SPACING)

        outer_frame = QFrame()
        outer_frame.setObjectName("ScrollPageOuterFrame")
        outer_layout = QVBoxLayout(outer_frame)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(PAGE_INNER_SPACING)

        # 상단 고정 배너는 MainWindow에서 표시합니다.
        outer_layout.addWidget(self._create_summary_panel())
        outer_layout.addWidget(self._create_content(), 1)
        layout.addWidget(outer_frame, 1)

        self.refresh_from_state()

    def _create_hero(self):
        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero.setFixedHeight(78)
        row = QHBoxLayout(hero)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(6)
        texts = QVBoxLayout()
        texts.setSpacing(6)
        badge = QLabel("사업자 운영")
        badge.setObjectName("HeroBadge")
        title = QLabel("사업자 · 근무 사업장 관리")
        title.setObjectName("HeroTitle")
        desc = QLabel("사업자와 근무 사업장을 새로 등록하고, 선택한 항목을 바로 수정하거나 삭제할 수 있습니다.")
        desc.setObjectName("HeroDesc")
        desc.setWordWrap(True)
        texts.addWidget(badge)
        texts.addWidget(title)
        texts.addWidget(desc)
        texts.addStretch()
        row.addLayout(texts, 1)
        return hero

    def _create_summary_panel(self):
        panel = Panel("사업자 현황 요약", "사업자와 근무 사업장 등록 현황")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        self.total_registered_card = MiniMetricCard("등록 사업자", "0", "현재 등록된 사업자 수", "business")
        self.active_business_card = MiniMetricCard("운영 중 사업자", "0", "현재 사용 중인 사업자 수", "presence")
        self.inactive_business_card = MiniMetricCard("중지 사업자", "0", "현재 중지된 사업자 수", "alert")
        self.total_site_card = MiniMetricCard("근무 사업장", "0", "등록된 사업장 수", "home")
        for i, card in enumerate([self.total_registered_card, self.active_business_card, self.inactive_business_card, self.total_site_card]):
            card.setMinimumHeight(88)
            grid.addWidget(card, 0, i)
        panel.body_layout.addLayout(grid)
        return panel

    def _create_content(self):
        wrap = QWidget()
        root = QVBoxLayout(wrap)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        business_panel = Panel("사업자 목록", "사업자 등록/수정/삭제 전용 영역")
        controls = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("사업자 검색")
        self.search_edit.textChanged.connect(self.refresh_table)
        controls.addWidget(self.search_edit, 1)
        self.count_label = QLabel("0건")
        self.count_label.setObjectName("StatusBadge")
        controls.addWidget(self.count_label)
        add_btn = QPushButton("등록")
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(self.add_business)
        controls.addWidget(add_btn)
        self.b_edit_btn = QPushButton("수정")
        self.b_edit_btn.setObjectName("GhostButton")
        self.b_edit_btn.clicked.connect(self.edit_business)
        controls.addWidget(self.b_edit_btn)
        self.b_del_btn = QPushButton("삭제")
        self.b_del_btn.setObjectName("DangerButton")
        self.b_del_btn.clicked.connect(self.delete_business)
        controls.addWidget(self.b_del_btn)
        business_panel.body_layout.addLayout(controls)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["사업자", "사업자번호", "대표자", "상태"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellClicked.connect(self._handle_click)
        self.table.cellDoubleClicked.connect(self.edit_business)
        install_resizable_table_columns(
            self.table,
            state=self.state,
            key="business/business_table",
            default_widths=[190, 134, 112, 72],
            min_widths=[130, 108, 82, 62],
        )
        business_panel.body_layout.addWidget(self.table)
        splitter.addWidget(business_panel)

        site_panel = Panel("근무 사업장 목록", "선택한 사업자 아래 사업장 등록/수정/삭제 영역")
        site_controls = QHBoxLayout()
        self.work_site_search_edit = QLineEdit()
        self.work_site_search_edit.setPlaceholderText("근무 사업장 검색")
        self.work_site_search_edit.textChanged.connect(self.refresh_work_site_table)
        site_controls.addWidget(self.work_site_search_edit, 1)
        self.w_count_label = QLabel("0건")
        self.w_count_label.setObjectName("StatusBadge")
        site_controls.addWidget(self.w_count_label)
        self.w_add_btn = QPushButton("등록")
        self.w_add_btn.setObjectName("PrimaryButton")
        self.w_add_btn.clicked.connect(self.add_work_site)
        site_controls.addWidget(self.w_add_btn)
        self.w_edit_btn = QPushButton("수정")
        self.w_edit_btn.setObjectName("GhostButton")
        self.w_edit_btn.clicked.connect(self.edit_work_site)
        site_controls.addWidget(self.w_edit_btn)
        self.w_del_btn = QPushButton("삭제")
        self.w_del_btn.setObjectName("DangerButton")
        self.w_del_btn.clicked.connect(self.delete_work_site)
        site_controls.addWidget(self.w_del_btn)
        site_panel.body_layout.addLayout(site_controls)

        self.work_site_table = QTableWidget(0, 6)
        self.work_site_table.setHorizontalHeaderLabels(["근무 사업장", "사업자번호", "대표자", "관리자", "연락처", "상태"])
        self.work_site_table.verticalHeader().setVisible(False)
        self.work_site_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.work_site_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.work_site_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.work_site_table.cellClicked.connect(self._handle_work_site_click)
        self.work_site_table.cellDoubleClicked.connect(self.edit_work_site)
        install_resizable_table_columns(
            self.work_site_table,
            state=self.state,
            key="business/work_site_table",
            default_widths=[170, 132, 104, 112, 118, 72],
            min_widths=[118, 104, 78, 88, 96, 62],
        )
        site_panel.body_layout.addWidget(self.work_site_table)
        splitter.addWidget(site_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)
        return wrap

    def refresh_from_state(self):
        self.records = self.state.business_records()
        business_count = len(self.records)
        operating = sum(1 for row in self.records if row.get("active", True))
        inactive = max(business_count - operating, 0)
        total_site = sum(int(row.get("work_site_count", row.get("client_count", 0)) or 0) for row in self.records)

        self.total_registered_card.set_value(str(business_count))
        self.active_business_card.set_value(str(operating))
        self.inactive_business_card.set_value(str(inactive))
        self.total_site_card.set_value(str(total_site))

        if self.selected_name and not any(row.get("name") == self.selected_name for row in self.records):
            self.selected_name = None
            self.selected_work_site_name = None

        self.refresh_table()
        self.refresh_work_site_table()

    def refresh_table(self):
        keyword = self.search_edit.text().strip().lower()
        self.filtered_records = []
        for row in self.records:
            haystack = " ".join(str(v) for v in row.values()).lower()
            if not keyword or keyword in haystack:
                self.filtered_records.append(row)

        self.count_label.setText(f"{len(self.filtered_records)}건")
        self.table.setRowCount(len(self.filtered_records))
        selected_row = -1
        for index, row in enumerate(self.filtered_records):
            self.table.setItem(index, 0, QTableWidgetItem(row.get("name", "")))
            self.table.setItem(index, 1, QTableWidgetItem(row.get("business_number", "")))
            self.table.setItem(index, 2, QTableWidgetItem(row.get("representative_name", "")))
            self.table.setItem(index, 3, QTableWidgetItem("운영중" if row.get("active", True) else "중지"))
            if row.get("name") == self.selected_name:
                selected_row = index
        if selected_row >= 0:
            self.table.selectRow(selected_row)
        else:
            self.selected_name = None
        self.b_edit_btn.setEnabled(self.selected_name is not None)
        self.b_del_btn.setEnabled(self.selected_name is not None)
        self.w_add_btn.setEnabled(True)

    def refresh_work_site_table(self):
        self.work_site_records = self.state.work_site_records(self.selected_name) if self.selected_name else []
        keyword = self.work_site_search_edit.text().strip().lower()
        self.filtered_work_site_records = []
        for row in self.work_site_records:
            haystack = " ".join(str(v) for v in row.values()).lower()
            if not keyword or keyword in haystack:
                self.filtered_work_site_records.append(row)

        self.w_count_label.setText(f"{len(self.filtered_work_site_records)}건")
        self.work_site_table.setRowCount(len(self.filtered_work_site_records))
        selected_row = -1
        for index, row in enumerate(self.filtered_work_site_records):
            self.work_site_table.setItem(index, 0, QTableWidgetItem(row.get("name", "")))
            self.work_site_table.setItem(index, 1, QTableWidgetItem(row.get("business_number", "")))
            self.work_site_table.setItem(index, 2, QTableWidgetItem(row.get("representative_name", "")))
            self.work_site_table.setItem(index, 3, QTableWidgetItem(row.get("manager_name", "")))
            self.work_site_table.setItem(index, 4, QTableWidgetItem(row.get("phone", "")))
            self.work_site_table.setItem(index, 5, QTableWidgetItem(row.get("status_text", "운영중")))
            if row.get("name") == self.selected_work_site_name:
                selected_row = index
        if selected_row >= 0:
            self.work_site_table.selectRow(selected_row)
        else:
            self.selected_work_site_name = None
        self.w_edit_btn.setEnabled(self.selected_work_site_name is not None)
        self.w_del_btn.setEnabled(self.selected_work_site_name is not None)

    def _handle_click(self, row, _col):
        self.selected_name = self.filtered_records[row].get("name")
        self.selected_work_site_name = None
        self.refresh_table()
        self.refresh_work_site_table()

    def _handle_work_site_click(self, row, _col):
        self.selected_work_site_name = self.filtered_work_site_records[row].get("name")
        self.refresh_work_site_table()

    def add_business(self):
        dialog = RegistrationDialog(self.state, "business", None, None, self)
        if dialog.exec():
            saved_name = str(getattr(dialog, "saved_name", "") or dialog.name_edit.text()).strip()
            if saved_name:
                self.selected_name = saved_name
                self.search_edit.clear()
            self.refresh_from_state()

    def _open_bulk_add_dialog(self):
        if not self.selected_name:
            QMessageBox.warning(self, "사업자 관리", "먼저 사업자를 선택해 주세요.")
            return
        dialog = BulkWorkSiteDialog(parent=self, state=self.state, parent_business=self.selected_name)
        if dialog.exec():
            self.refresh_from_state()

    def edit_business(self):
        if not self.selected_name:
            return
        record = self.state.get_business(self.selected_name)
        dialog = RegistrationDialog(self.state, "business", record, None, self)
        if dialog.exec():
            saved_name = str(getattr(dialog, "saved_name", "") or dialog.name_edit.text()).strip()
            if saved_name:
                self.selected_name = saved_name
                self.search_edit.clear()
            self.refresh_from_state()

    def delete_business(self):
        if not self.selected_name:
            return
        confirm = QMessageBox.question(self, "사업자 관리", f"{self.selected_name} 사업자를 삭제할까요?")
        if confirm == QMessageBox.Yes:
            try:
                self.state.delete_business(self.selected_name)
                self.selected_name = None
                self.selected_work_site_name = None
                self.refresh_from_state()
            except ValueError as err:
                QMessageBox.warning(self, "사업자 관리", str(err))

    def add_work_site(self):
        if not self.state.business_records():
            QMessageBox.warning(self, "사업자 관리", "먼저 사업자를 등록해 주세요.")
            return
        dialog = RegistrationDialog(self.state, "work_site", None, self.selected_name, self)
        if dialog.exec():
            saved_business = str(getattr(dialog, "saved_business_name", "") or self.selected_name or "").strip()
            saved_name = str(getattr(dialog, "saved_name", "") or dialog.name_edit.text()).strip()
            if saved_business:
                self.selected_name = saved_business
            if saved_name:
                self.selected_work_site_name = saved_name
                self.work_site_search_edit.clear()
            self.refresh_from_state()

    def edit_work_site(self):
        if not self.selected_name or not self.selected_work_site_name:
            return
        record = self.state.get_work_site(self.selected_name, self.selected_work_site_name)
        dialog = RegistrationDialog(self.state, "work_site", record, self.selected_name, self)
        if dialog.exec():
            saved_business = str(getattr(dialog, "saved_business_name", "") or self.selected_name or "").strip()
            saved_name = str(getattr(dialog, "saved_name", "") or dialog.name_edit.text()).strip()
            if saved_business:
                self.selected_name = saved_business
            if saved_name:
                self.selected_work_site_name = saved_name
                self.work_site_search_edit.clear()
            self.refresh_from_state()

    def delete_work_site(self):
        if not self.selected_name or not self.selected_work_site_name:
            return
        confirm = QMessageBox.question(self, "사업자 관리", f"{self.selected_work_site_name} 근무 사업장을 삭제할까요?")
        if confirm == QMessageBox.Yes:
            try:
                self.state.delete_work_site(self.selected_name, self.selected_work_site_name)
                self.selected_work_site_name = None
                self.refresh_from_state()
            except ValueError as err:
                QMessageBox.warning(self, "사업자 관리", str(err))
