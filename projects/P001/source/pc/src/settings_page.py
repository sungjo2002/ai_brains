from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QScrollArea,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from .defaults import ATTENDANCE_SCORE_SETTINGS, REJOIN_GRADES
from .app_metadata import PROGRAM_VERSION, STORAGE_VERSION
from .table_column_manager import install_resizable_table_columns
from .widgets import Panel, PAGE_OUTER_MARGINS, PAGE_OUTER_SPACING, PAGE_INNER_MARGINS, PAGE_INNER_SPACING


GROUP_TEXT_TO_KEY = {"요약": "summary", "수당": "allowance", "공제": "deduction"}
GROUP_KEY_TO_TEXT = {value: key for key, value in GROUP_TEXT_TO_KEY.items()}
MODE_TEXT_TO_KEY = {"읽기전용": "readonly", "수동입력": "manual"}
MODE_KEY_TO_TEXT = {value: key for key, value in MODE_TEXT_TO_KEY.items()}
LOCATION_TEXT_TO_KEY = {"상세": "detail", "명세서": "slip", "둘다": "both"}
LOCATION_KEY_TO_TEXT = {value: key for key, value in LOCATION_TEXT_TO_KEY.items()}
PAYROLL_NUMBER_LABELS = {
    "day_hourly_rate": "주간 시급 (원)",
    "night_hourly_rate": "야간 시급 (원)",
    "night_multiplier": "야간 수당 배율",
    "late_deduct": "지각 1회 차감 (원)",
    "absent_deduct": "결근 1일 차감 (원)",
    "unauthorized_absence_deduct": "무단결근 차감 (원)",
    "default_meal_deduct": "식대 공제 기본값 (원)",
    "severance_multiplier": "퇴직금 배율",
    "attendance_base_hours": "기본 시간 (시간)",
    "attendance_over_hours": "연장 시간 (시간)",
    "attendance_night_hours": "심야 시간 (시간)",
}
SHIFT_GROUP_OPTIONS = ["주간", "야간"]
PAYROLL_ATTENDANCE_TREATMENT_OPTIONS = ["근무", "결근", "휴무"]
PAYROLL_HOURS_MODE_OPTIONS = ["기본시간 적용", "0시간", "절반 적용", "수동 조정"]


class DocumentPreviewDialog(QDialog):
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

    def __init__(self, path: str, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.path = str(path or "")
        self._original_pixmap: QPixmap | None = None
        self.image_scroll: QScrollArea | None = None
        self.image_label: QLabel | None = None
        file_name = Path(self.path).name if self.path else "문서"
        self.setWindowTitle(f"{title} 미리보기 - {file_name}")
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        name_label = QLabel(file_name)
        name_label.setObjectName("DetailName")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        suffix = Path(self.path).suffix.lower()
        if suffix in self.IMAGE_EXTENSIONS:
            pixmap = QPixmap(self.path)
            if pixmap.isNull():
                info = QLabel("이미지를 불러오지 못했습니다.")
                info.setObjectName("DetailMeta")
                layout.addWidget(info)
            else:
                self._original_pixmap = pixmap
                self.image_scroll = QScrollArea()
                self.image_scroll.setWidgetResizable(True)
                self.image_scroll.setFrameShape(QScrollArea.NoFrame)
                self.image_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                self.image_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                self.image_label = QLabel()
                self.image_label.setAlignment(Qt.AlignCenter)
                self.image_label.setMinimumSize(0, 0)
                self.image_scroll.setWidget(self.image_label)
                layout.addWidget(self.image_scroll, 1)
                self._update_image_preview()
        else:
            info = QLabel("이미지 파일이 아니라서 기본 프로그램으로 열 수 있습니다.")
            info.setObjectName("DetailMeta")
            info.setWordWrap(True)
            layout.addWidget(info, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        open_btn = QPushButton("파일 열기")
        open_btn.setObjectName("GhostButton")
        open_btn.clicked.connect(self._open_external)
        close_btn = QPushButton("닫기")
        close_btn.setObjectName("PrimaryButton")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(open_btn)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_image_preview()

    def _update_image_preview(self):
        if not self._original_pixmap or not self.image_scroll or not self.image_label:
            return
        viewport = self.image_scroll.viewport().size()
        if viewport.width() <= 1 or viewport.height() <= 1:
            return
        scaled = self._original_pixmap.scaled(
            viewport,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.size())

    def _open_external(self):
        if self.path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))


class VehicleRegistrationDialog(QDialog):
    def __init__(self, state, vehicle: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.vehicle = deepcopy(vehicle or {})
        self.contract_document_source = self.state.resolve_storage_file_path(self.vehicle.get("contract_document_path", ""))
        self.attachment_document_source = self.state.resolve_storage_file_path(self.vehicle.get("attachment_document_path", ""))

        self.setWindowTitle("차량 신규 등록" if not self.vehicle else "차량 정보 수정")
        self.setModal(True)
        self.resize(560, 660)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.form = form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)
        form.setHorizontalSpacing(6)
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.vehicle_type_combo = QComboBox()
        self.vehicle_type_combo.addItems(["자차", "렌트카"])
        self.vehicle_type_combo.currentIndexChanged.connect(self._toggle_rental_fields)

        self.vehicle_name_edit = QLineEdit()
        self.plate_number_edit = QLineEdit()

        self.business_combo = QComboBox()
        for row in self.state.business_master_records():
            name = str(row.get("name", "") or "").strip()
            if name:
                self.business_combo.addItem(name, deepcopy(row))
        self.business_combo.currentIndexChanged.connect(self._reload_work_sites)

        self.work_site_combo = QComboBox()
        self.work_site_combo.currentIndexChanged.connect(self._reload_driver_candidates)
        self.driver_combo = QComboBox()
        self._configure_driver_combo(self.driver_combo, "기본 주 운전자 검색 또는 직접 입력")
        self._reload_driver_candidates()

        self.status_combo = QComboBox()
        self.status_combo.addItems(["운행중", "대기", "정비중", "미사용"])
        self.baseline_odometer_edit = QLineEdit()
        self.baseline_odometer_edit.setPlaceholderText("예: 24500")

        self.note_edit = QTextEdit()
        self.note_edit.setFixedHeight(68)

        self.attachment_doc_name_btn = QPushButton("선택된 첨부 파일 없음")
        self.attachment_doc_name_btn.setObjectName("GhostButton")
        self.attachment_doc_name_btn.setStyleSheet("text-align:left; padding-left: 6px;")
        self.attachment_doc_name_btn.setEnabled(False)
        self.attachment_doc_name_btn.clicked.connect(lambda: self._preview_document(self.attachment_document_source, "첨부 서류"))
        self.attachment_doc_btn = QPushButton("파일 선택")
        self.attachment_doc_btn.setObjectName("GhostButton")
        self.attachment_doc_btn.clicked.connect(self._pick_attachment_document)
        self.attachment_doc_clear_btn = QPushButton("삭제")
        self.attachment_doc_clear_btn.setObjectName("GhostButton")
        self.attachment_doc_clear_btn.clicked.connect(self._clear_attachment_document)

        self.rental_company_edit = QLineEdit()
        self.contract_start_edit = QDateEdit()
        self.contract_start_edit.setCalendarPopup(True)
        self.contract_start_edit.setDisplayFormat("yyyy-MM-dd")
        self.contract_start_edit.dateChanged.connect(self._update_limit_preview)
        self.contract_end_edit = QDateEdit()
        self.contract_end_edit.setCalendarPopup(True)
        self.contract_end_edit.setDisplayFormat("yyyy-MM-dd")
        self.contract_end_edit.dateChanged.connect(self._update_limit_preview)
        self.annual_limit_edit = QLineEdit()
        self.annual_limit_edit.setPlaceholderText("예: 20000")
        self.annual_limit_edit.textChanged.connect(self._update_limit_preview)
        self.unlimited_check = QCheckBox("무제한")
        self.unlimited_check.toggled.connect(self._toggle_unlimited)
        self.contract_limit_preview = QLabel("총 허용 km: -")
        self.contract_limit_preview.setObjectName("DetailMeta")
        self.contract_doc_name_btn = QPushButton("선택된 계약서 없음")
        self.contract_doc_name_btn.setObjectName("GhostButton")
        self.contract_doc_name_btn.setStyleSheet("text-align:left; padding-left: 6px;")
        self.contract_doc_name_btn.setEnabled(False)
        self.contract_doc_name_btn.clicked.connect(lambda: self._preview_document(self.contract_document_source, "임대계약서"))
        self.contract_doc_btn = QPushButton("파일 선택")
        self.contract_doc_btn.setObjectName("GhostButton")
        self.contract_doc_btn.clicked.connect(self._pick_contract_document)
        self.contract_doc_clear_btn = QPushButton("삭제")
        self.contract_doc_clear_btn.setObjectName("GhostButton")
        self.contract_doc_clear_btn.clicked.connect(self._clear_contract_document)

        self._rental_rows: list[QWidget] = []

        form.addRow("차량 구분", self.vehicle_type_combo)
        form.addRow("차량명", self.vehicle_name_edit)
        form.addRow("차량번호", self.plate_number_edit)
        form.addRow("사업자", self.business_combo)
        form.addRow("근무 사업장", self.work_site_combo)
        form.addRow("기본 주 운전자", self.driver_combo)
        form.addRow("상태", self.status_combo)
        form.addRow("시작 계기판 km", self.baseline_odometer_edit)
        attach_wrap = QWidget()
        attach_layout = QHBoxLayout(attach_wrap)
        attach_layout.setContentsMargins(0, 0, 0, 0)
        attach_layout.setSpacing(6)
        attach_layout.addWidget(self.attachment_doc_name_btn, 1)
        attach_layout.addWidget(self.attachment_doc_btn, 0)
        attach_layout.addWidget(self.attachment_doc_clear_btn, 0)
        form.addRow("첨부 서류", attach_wrap)
        form.addRow("메모", self.note_edit)

        self._add_rental_row(form, "렌트 회사명", self.rental_company_edit)
        self._add_rental_row(form, "계약 시작일", self.contract_start_edit)
        self._add_rental_row(form, "계약 종료일", self.contract_end_edit)
        self._add_rental_row(form, "연간 허용 km", self.annual_limit_edit)
        self._add_rental_row(form, "무제한", self.unlimited_check)
        self._add_rental_row(form, "총 허용 km", self.contract_limit_preview)
        doc_wrap = QWidget()
        doc_layout = QHBoxLayout(doc_wrap)
        doc_layout.setContentsMargins(0, 0, 0, 0)
        doc_layout.setSpacing(6)
        doc_layout.addWidget(self.contract_doc_name_btn, 1)
        doc_layout.addWidget(self.contract_doc_btn, 0)
        doc_layout.addWidget(self.contract_doc_clear_btn, 0)
        self._add_rental_row(form, "임대계약서", doc_wrap)

        layout.addLayout(form)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.save_btn = QPushButton("저장")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.setObjectName("GhostButton")
        self.cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(self.save_btn)
        button_row.addWidget(self.cancel_btn)
        layout.addLayout(button_row)

        self._load_vehicle()

    def _add_rental_row(self, form: QFormLayout, label: str, widget: QWidget):
        form.addRow(label, widget)
        self._rental_rows.append(widget)

    def _configure_driver_combo(self, combo: QComboBox, placeholder: str):
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        if combo.lineEdit() is not None:
            combo.lineEdit().setPlaceholderText(placeholder)
        completer = QCompleter(combo.model(), combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        combo.setCompleter(completer)

    def _reload_driver_candidates(self):
        current = self.driver_combo.currentText().strip()
        business_name = self.business_combo.currentText().strip()
        work_site_name = self.work_site_combo.currentText().strip()
        if hasattr(self.state, "vehicle_main_driver_candidates"):
            names = self.state.vehicle_main_driver_candidates(business_name, work_site_name)
        else:
            names = self.state.vehicle_driver_candidates(business_name)
        self.driver_combo.blockSignals(True)
        self.driver_combo.clear()
        for name in names:
            self.driver_combo.addItem(name)
        if current:
            idx = self.driver_combo.findText(current)
            if idx >= 0:
                self.driver_combo.setCurrentIndex(idx)
            else:
                # 직접 입력값이나 기존 차량의 저장값은 입력칸에는 유지하되,
                # 기본 주 운전자 후보 목록에는 임시 운행기록 이름을 섞지 않습니다.
                self.driver_combo.setCurrentIndex(-1)
                self.driver_combo.setEditText(current)
        else:
            self.driver_combo.setCurrentIndex(-1)
            if self.driver_combo.lineEdit() is not None:
                self.driver_combo.lineEdit().clear()
        self.driver_combo.blockSignals(False)

    def _reload_work_sites(self):
        current = self.work_site_combo.currentData()
        current_id = ""
        current_name = ""
        if isinstance(current, dict):
            current_id = str(current.get("work_site_id", "") or "").strip()
            current_name = str(current.get("name", "") or current.get("work_site_name", "") or "").strip()
        else:
            current_name = str(current or self.work_site_combo.currentText() or "").strip()
        self.work_site_combo.blockSignals(True)
        self.work_site_combo.clear()
        business_name = self.business_combo.currentText().strip()
        rows = [row for row in self.state.work_site_records() if str(row.get("business_name", "") or "").strip() == business_name]
        for row in rows:
            name = str(row.get("name", "") or "").strip()
            if name:
                self.work_site_combo.addItem(name, deepcopy(row))
        if current_id or current_name:
            for idx in range(self.work_site_combo.count()):
                item = self.work_site_combo.itemData(idx) or {}
                item_id = str(item.get("work_site_id", "") or "").strip() if isinstance(item, dict) else ""
                item_name = str(item.get("name", "") or "").strip() if isinstance(item, dict) else str(item or "").strip()
                if (current_id and item_id == current_id) or (current_name and item_name == current_name):
                    self.work_site_combo.setCurrentIndex(idx)
                    break
        self.work_site_combo.blockSignals(False)
        self._reload_driver_candidates()

    def _set_document_button(self, button: QPushButton, path: str, empty_text: str):
        file_path = self.state.resolve_storage_file_path(path)
        if file_path and Path(file_path).exists():
            button.setText(Path(file_path).name)
            button.setEnabled(True)
            button.setToolTip(file_path)
        else:
            button.setText(empty_text)
            button.setEnabled(False)
            button.setToolTip("")

    def _set_attachment_document(self, path: str):
        self.attachment_document_source = self.state.resolve_storage_file_path(path)
        self._set_document_button(self.attachment_doc_name_btn, self.attachment_document_source, "선택된 첨부 파일 없음")

    def _clear_attachment_document(self):
        self._set_attachment_document("")

    def _set_contract_document(self, path: str):
        self.contract_document_source = self.state.resolve_storage_file_path(path)
        self._set_document_button(self.contract_doc_name_btn, self.contract_document_source, "선택된 계약서 없음")

    def _clear_contract_document(self):
        self._set_contract_document("")

    def _preview_document(self, path: str, title: str):
        file_path = self.state.resolve_storage_file_path(path)
        if not file_path or not Path(file_path).exists():
            QMessageBox.information(self, "첨부 파일", "파일을 찾을 수 없습니다. 첨부 경로를 다시 확인해 주세요.")
            return
        suffix = Path(file_path).suffix.lower()
        if suffix in DocumentPreviewDialog.IMAGE_EXTENSIONS:
            dialog = DocumentPreviewDialog(file_path, title, self)
            dialog.exec()
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))

    def _pick_contract_document(self):
        path, _ = QFileDialog.getOpenFileName(self, "자동차 임대계약서 선택", "", "문서/이미지 (*.pdf *.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        self._set_contract_document(path)

    def _pick_attachment_document(self):
        path, _ = QFileDialog.getOpenFileName(self, "차량 첨부 서류 선택", "", "문서/이미지 (*.pdf *.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        self._set_attachment_document(path)

    def _toggle_unlimited(self):
        unlimited = self.unlimited_check.isChecked()
        self.annual_limit_edit.setEnabled(not unlimited)
        self.contract_start_edit.setEnabled(not unlimited)
        self.contract_end_edit.setEnabled(not unlimited)
        self._update_limit_preview()

    def _update_limit_preview(self):
        if self.vehicle_type_combo.currentText() != "렌트카":
            self.contract_limit_preview.setText("총 허용 km: -")
            return
        if self.unlimited_check.isChecked():
            self.contract_limit_preview.setText("총 허용 km: 무제한")
            return
        try:
            annual = float(self.annual_limit_edit.text().replace(",", "") or 0)
        except ValueError:
            annual = 0
        total = self.state.estimate_contract_total_limit_km(annual, self.contract_start_edit.date().toString("yyyy-MM-dd"), self.contract_end_edit.date().toString("yyyy-MM-dd"))
        self.contract_limit_preview.setText(f"총 허용 km: {int(total):,} km" if total > 0 else "총 허용 km: -")

    def _toggle_rental_fields(self):
        is_rental = self.vehicle_type_combo.currentText() == "렌트카"
        for widget in self._rental_rows:
            label_widget = self.form.labelForField(widget)
            if label_widget is not None:
                label_widget.setVisible(is_rental)
            widget.setVisible(is_rental)
        self._update_limit_preview()

    def _load_vehicle(self):
        today = QDate.currentDate()
        self.contract_start_edit.setDate(today)
        self.contract_end_edit.setDate(today.addYears(1).addDays(-1))

        current_type = str(self.vehicle.get("vehicle_type", "자차") or "자차")
        self.vehicle_type_combo.setCurrentText("렌트카" if current_type == "렌트카" else "자차")
        self.vehicle_name_edit.setText(str(self.vehicle.get("vehicle_name", "") or ""))
        self.plate_number_edit.setText(str(self.vehicle.get("plate_number", "") or ""))
        self.baseline_odometer_edit.setText(str(int(float(self.vehicle.get("baseline_odometer", 0) or 0))))
        self.note_edit.setPlainText(str(self.vehicle.get("note", "") or ""))
        self.status_combo.setCurrentText(str(self.vehicle.get("status", "운행중") or "운행중"))

        business_id = str(self.vehicle.get("business_id", "") or "").strip()
        business_name = str(self.vehicle.get("business_name", "") or self.vehicle.get("business", "") or "").strip()
        if business_id or business_name:
            for idx in range(self.business_combo.count()):
                item = self.business_combo.itemData(idx) or {}
                item_id = str(item.get("business_id", "") or "").strip() if isinstance(item, dict) else ""
                item_name = str(item.get("name", "") or "").strip() if isinstance(item, dict) else str(self.business_combo.itemText(idx) or "").strip()
                if (business_id and item_id == business_id) or (business_name and item_name == business_name):
                    self.business_combo.setCurrentIndex(idx)
                    break
        self._reload_work_sites()
        work_site_id = str(self.vehicle.get("work_site_id", "") or "").strip()
        work_site_name = str(self.vehicle.get("work_site_name", "") or self.vehicle.get("work_site", "") or self.vehicle.get("site", "") or "").strip()
        if work_site_id or work_site_name:
            for idx in range(self.work_site_combo.count()):
                item = self.work_site_combo.itemData(idx) or {}
                item_id = str(item.get("work_site_id", "") or "").strip() if isinstance(item, dict) else ""
                item_name = str(item.get("name", "") or "").strip() if isinstance(item, dict) else str(self.work_site_combo.itemText(idx) or "").strip()
                if (work_site_id and item_id == work_site_id) or (work_site_name and item_name == work_site_name):
                    self.work_site_combo.setCurrentIndex(idx)
                    break
        driver_name = str(self.vehicle.get("main_driver", "") or "")
        if driver_name:
            idx = self.driver_combo.findText(driver_name)
            if idx < 0:
                self.driver_combo.addItem(driver_name)
                idx = self.driver_combo.findText(driver_name)
            self.driver_combo.setCurrentIndex(idx)

        self.rental_company_edit.setText(str(self.vehicle.get("rental_company", "") or ""))
        contract_start = str(self.vehicle.get("contract_start", "") or "")
        if contract_start:
            parsed = QDate.fromString(contract_start, "yyyy-MM-dd")
            if parsed.isValid():
                self.contract_start_edit.setDate(parsed)
        contract_end = str(self.vehicle.get("contract_end", "") or "")
        if contract_end:
            parsed = QDate.fromString(contract_end, "yyyy-MM-dd")
            if parsed.isValid():
                self.contract_end_edit.setDate(parsed)
        self.annual_limit_edit.setText(str(int(float(self.vehicle.get("annual_limit_km", 0) or 0))) if self.vehicle.get("annual_limit_km") else "")
        self.unlimited_check.setChecked(bool(self.vehicle.get("unlimited")))
        existing_doc = self.state.resolve_storage_file_path(self.vehicle.get("contract_document_path", ""))
        self._set_contract_document(existing_doc)
        existing_attachment = self.state.resolve_storage_file_path(self.vehicle.get("attachment_document_path", ""))
        self._set_attachment_document(existing_attachment)
        self._toggle_rental_fields()

    def vehicle_payload(self) -> dict:
        business_row = self.business_combo.currentData() or {}
        work_site_row = self.work_site_combo.currentData() or {}
        if not isinstance(business_row, dict):
            business_row = {}
        if not isinstance(work_site_row, dict):
            work_site_row = {}
        business_id = str(business_row.get("business_id", "") or "").strip()
        business_name = str(business_row.get("name", "") or self.business_combo.currentText() or "").strip()
        work_site_id = str(work_site_row.get("work_site_id", "") or "").strip()
        work_site_name = str(work_site_row.get("name", "") or self.work_site_combo.currentText() or "").strip()
        return {
            "vehicle_id": str(self.vehicle.get("vehicle_id", "") or ""),
            "vehicle_type": self.vehicle_type_combo.currentText(),
            "vehicle_name": self.vehicle_name_edit.text().strip(),
            "plate_number": self.plate_number_edit.text().strip(),
            "car_model": "",
            "business_id": business_id,
            "business_name": business_name,
            "business": business_name,
            "work_site_id": work_site_id,
            "work_site_name": work_site_name,
            "work_site": work_site_name,
            "site": work_site_name,
            "site_name": work_site_name,
            "main_driver": self.driver_combo.currentText().strip(),
            "status": self.status_combo.currentText().strip(),
            "baseline_odometer": self.baseline_odometer_edit.text().replace(",", "").strip() or "0",
            "note": self.note_edit.toPlainText().strip(),
            "attachment_document_source": self.attachment_document_source if Path(str(self.attachment_document_source)).exists() else "",
            "rental_company": self.rental_company_edit.text().strip(),
            "contract_start": self.contract_start_edit.date().toString("yyyy-MM-dd"),
            "contract_end": self.contract_end_edit.date().toString("yyyy-MM-dd"),
            "annual_limit_km": self.annual_limit_edit.text().replace(",", "").strip() or "0",
            "unlimited": self.unlimited_check.isChecked(),
            "contract_document_source": self.contract_document_source if Path(str(self.contract_document_source)).exists() else "",
        }



class SettingsPage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.score_edits: dict[str, QLineEdit] = {}
        self.grade_edits: list[tuple[str, QLineEdit]] = []
        self._payroll_edits: dict[str, QLineEdit | QComboBox] = {}
        self._current_site_name: str = ""
        self._current_business_name: str = ""
        self._site_selectors: list[tuple[QComboBox, QLabel, QLineEdit]] = []
        self.payroll_preset_combo: QComboBox | None = None
        self.payroll_item_preset_combo: QComboBox | None = None
        self.time_conversion_table: QTableWidget | None = None
        self.apply_payroll_preset_btn: QPushButton | None = None
        self.vehicle_alert_remaining_edit: QLineEdit | None = None
        self.vehicle_alert_days_edit: QLineEdit | None = None
        self.vehicle_sync_base_url_label: QLabel | None = None
        self.vehicle_sync_count_label: QLabel | None = None
        self.vehicle_sync_status_label: QLabel | None = None
        self.autosave_minutes_combo: QComboBox | None = None
        self.holiday_api_enabled_check: QCheckBox | None = None
        self.holiday_api_key_edit: QLineEdit | None = None
        self.holiday_api_status_label: QLabel | None = None
        self.backup_dir_edit: QLineEdit | None = None
        self.backup_default_dir_label: QLabel | None = None
        self.server_mode_checkbox: QCheckBox | None = None
        self.server_base_url_edit: QLineEdit | None = None
        self.server_timeout_edit: QLineEdit | None = None
        self.server_sync_key_edit: QLineEdit | None = None
        self.server_status_label: QLabel | None = None
        self._selected_vehicle_id: str = ""
        self._selected_admin_username: str = ""
        self.admin_table: QTableWidget | None = None
        self.admin_name_edit: QLineEdit | None = None
        self.admin_username_edit: QLineEdit | None = None
        self.admin_phone_edit: QLineEdit | None = None
        self.admin_role_edit: QComboBox | None = None
        self.admin_password_edit: QLineEdit | None = None
        self.admin_created_at_edit: QLineEdit | None = None
        self.admin_updated_at_edit: QLineEdit | None = None
        self.admin_assignment_summary_label: QLabel | None = None
        self.admin_business_combo: QComboBox | None = None
        self.admin_work_site_table: QTableWidget | None = None
        self.admin_active_check: QCheckBox | None = None
        self.admin_note_edit: QTextEdit | None = None
        self.settings_hero_badge: QLabel | None = None
        self.settings_hero_title: QLabel | None = None
        self.settings_hero_desc: QLabel | None = None

        self.state.settings_changed.connect(self.load_from_state)
        self.state.employees_changed.connect(self._handle_people_changed)
        self.state.vehicles_changed.connect(self.load_from_state)
        if hasattr(self.state, "holidays_changed"):
            self.state.holidays_changed.connect(self._handle_holiday_sync_status)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*PAGE_OUTER_MARGINS)
        layout.setSpacing(PAGE_OUTER_SPACING)

        outer_frame = QFrame()
        outer_frame.setObjectName("ScrollPageOuterFrame")
        outer_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer_layout = QVBoxLayout(outer_frame)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(PAGE_INNER_SPACING)

        # 상단 고정 배너는 MainWindow에서 표시합니다.

        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_score_tab(), "근태 점수 기준")
        self.tabs.addTab(self._create_payroll_tab(), "현장별 급여 기준")
        self.tabs.addTab(self._create_payroll_item_tab(), "현장별 급여 항목")
        self.tabs.addTab(self._create_time_conversion_tab(), "사업장별 시간 환산 기준")
        self.tabs.addTab(self._create_vehicle_tab(), "차량관리 설정")
        self.tabs.addTab(self._create_admin_tab(), "계정권한관리")
        self.tabs.addTab(self._create_backup_tab(), "백업관리")
        self.tabs.addTab(self._create_misc_tab(), "기타설정")
        self.tabs.currentChanged.connect(self._refresh_settings_hero)
        outer_layout.addWidget(self.tabs, 1)
        layout.addWidget(outer_frame, 1)

        self._refresh_settings_hero(self.tabs.currentIndex())
        self.load_from_state()

    def _site_records(self) -> list[dict]:
        return self.state.work_site_records()

    def _site_display_text(self, row: dict) -> str:
        # 근무 사업장 선택 화면에는 사업자명을 함께 붙이지 않고 공장명만 표시합니다.
        # 내부 데이터는 currentData의 (사업자명, 공장명)으로 유지해서 저장 연결은 그대로 보존합니다.
        return str(row.get("name", "") or "").strip()

    def _handle_people_changed(self):
        self._refresh_work_site_selectors()
        self._load_admin_table()
        self._reload_admin_business_combo()

    def _combo_style(self) -> str:
        return (
            "QComboBox {"
            "padding: 0px 6px 0px 6px;"
            "min-height: 30px;"
            "max-height: 30px;"
            "font-size: 12px;"
            "font-weight: 600;"
            "color: #1E293B;"
            "background: #FFFFFF;"
            "border: 1px solid #CBD5E1;"
            "border-radius: 9px;"
            "}"
            "QComboBox::drop-down {"
            "subcontrol-origin: padding;"
            "subcontrol-position: top right;"
            "width: 15px;"
            "border-left: 1px solid #CBD5E1;"
            "border-top-right-radius: 9px;"
            "border-bottom-right-radius: 9px;"
            "background: #F8FAFC;"
            "}"
            "QComboBox::down-arrow {"
            "image: url(assets/combo_arrow_down.svg);"
            "width: 10px;"
            "height: 6px;"
            "}"
            "QComboBox QAbstractItemView {"
            "background: #FFFFFF;"
            "color: #1E293B;"
            "border: 1px solid #CBD5E1;"
            "selection-background-color: #EEF4FF;"
            "selection-color: #1D4ED8;"
            "border-radius: 8px;"
            "padding: 6px;"
            "}"
        )

    def _create_settings_hero(self):
        hero = QFrame()
        hero.setObjectName("SettingsHero")
        hero.setMinimumHeight(78)
        hero.setMaximumHeight(78)
        hero.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hero.setStyleSheet(
            "QFrame#SettingsHero {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #EFF6FF, stop:1 #F8FAFC);"
            "border: 1px solid #BFDBFE;"
            "border-radius: 14px;"
            "}"
            "QLabel#SettingsHeroBadge {"
            "color: #2563EB;"
            "font-size: 11px;"
            "font-weight: 900;"
            "letter-spacing: 0.4px;"
            "}"
            "QLabel#SettingsHeroTitle {"
            "color: #0F172A;"
            "font-size: 18px;"
            "font-weight: 900;"
            "}"
            "QLabel#SettingsHeroDesc {"
            "color: #475569;"
            "font-size: 12px;"
            "font-weight: 700;"
            "}"
        )

        row = QHBoxLayout(hero)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(6)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(6)

        self.settings_hero_badge = QLabel("설정")
        self.settings_hero_badge.setObjectName("SettingsHeroBadge")
        self.settings_hero_title = QLabel("설정 관리")
        self.settings_hero_title.setObjectName("SettingsHeroTitle")
        self.settings_hero_desc = QLabel("근태, 급여, 차량, 기타 사용 기준을 관리합니다.")
        self.settings_hero_desc.setObjectName("SettingsHeroDesc")
        self.settings_hero_desc.setWordWrap(True)

        text_col.addWidget(self.settings_hero_badge)
        text_col.addWidget(self.settings_hero_title)
        text_col.addWidget(self.settings_hero_desc)
        text_col.addStretch(1)
        row.addLayout(text_col, 1)
        return hero

    def _refresh_settings_hero(self, index: int = 0):
        if not all([self.settings_hero_badge, self.settings_hero_title, self.settings_hero_desc]):
            return
        tab_text = self.tabs.tabText(index) if hasattr(self, "tabs") and index >= 0 else "설정"
        hero_texts = {
            "근태 점수 기준": (
                "설정",
                "근태 점수 기준",
                "무단결근, 무단이탈, 지각, 조퇴 등 근태 평가 기준을 관리합니다.",
            ),
            "현장별 급여 기준": (
                "설정",
                "현장별 급여 기준",
                "근무 사업장별 시급, 공제, 수당, 근무시간 기본값을 관리합니다.",
            ),
            "현장별 급여 항목": (
                "설정",
                "현장별 급여 항목",
                "급여 상세와 명세서에 표시할 수당·공제 항목을 관리합니다.",
            ),
            "사업장별 시간 환산 기준": (
                "설정",
                "사업장별 시간 환산 기준",
                "광명산업, 지스틸, 현우, 에코인슈텍처럼 사업장마다 다른 시간·마감·배율 기준을 저장합니다.",
            ),
            "차량관리 설정": (
                "차량관리 설정",
                "차량 등록과 렌트카 기준 관리",
                "차량 등록, 렌트카 계약 기준, 운전자, 주행거리 경고 기준을 이 화면에서 관리합니다.",
            ),
            "계정권한관리": (
                "설정",
                "계정권한관리",
                "로그인 계정의 권한, 사용 여부, 담당 사업자와 근무사업장 배정을 관리합니다.",
            ),
            "백업관리": (
                "설정",
                "백업관리",
                "백업 위치, 즉시 백업, 복구 작업을 단순하게 관리합니다.",
            ),
            "기타설정": (
                "설정",
                "기타설정",
                "자동저장, 백업, 서버 연결, 공휴일 자동갱신 기준을 관리합니다.",
            ),
        }
        badge, title, desc = hero_texts.get(tab_text, ("설정", "설정 관리", "프로그램 사용 기준을 관리합니다."))
        self.settings_hero_badge.setText(badge)
        self.settings_hero_title.setText(title)
        self.settings_hero_desc.setText(desc)

    def select_settings_tab(self, tab_name: str):
        if not hasattr(self, "tabs"):
            return False
        target = str(tab_name or "").strip()
        if not target:
            return False
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == target:
                self.tabs.setCurrentIndex(index)
                self._refresh_settings_hero(index)
                return True
        return False

    def select_score_settings_tab(self):
        return self.select_settings_tab("근태 점수 기준")

    def select_payroll_settings_tab(self):
        return self.select_settings_tab("현장별 급여 기준")

    def select_payroll_item_settings_tab(self):
        return self.select_settings_tab("현장별 급여 항목")

    def select_vehicle_settings_tab(self):
        return self.select_settings_tab("차량관리 설정")

    def select_admin_settings_tab(self):
        return self.select_settings_tab("계정권한관리")

    def _apply_compact_field_width(self, widget: QWidget, kind: str = "medium"):
        width_map = {
            "small": 120,
            "medium": 170,
            "large": 240,
            "wide": 340,
            "path": 440,
        }
        max_width = width_map.get(kind, 170)
        if hasattr(widget, "setMaximumWidth"):
            widget.setMaximumWidth(max_width)
        try:
            policy = widget.sizePolicy()
            widget.setSizePolicy(QSizePolicy.Preferred, policy.verticalPolicy())
        except Exception:
            pass

    def _payroll_field_kind(self, key: str) -> str:
        if key.endswith("_note"):
            return "large"
        if key in {
            "work_type",
            "pay_type",
            "shift_start_group",
            "severance_method",
            "hospital_payroll_treatment",
            "hospital_hours_mode",
            "late_payroll_treatment",
            "late_hours_mode",
            "early_leave_payroll_treatment",
            "early_leave_hours_mode",
        }:
            return "medium"
        return "small"

    def _create_site_selector_row(self, title_text: str) -> QWidget:
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        title = QLabel(title_text)
        title.setObjectName("FieldLabel")
        title.setMinimumWidth(78)

        selector_field_width = 280

        search_edit = QLineEdit()
        search_edit.setFixedHeight(30)
        search_edit.setMinimumWidth(selector_field_width)
        search_edit.setMaximumWidth(selector_field_width)
        search_edit.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        search_edit.setPlaceholderText("근무 사업장명 검색")

        combo = QComboBox()
        combo.setFixedHeight(30)
        combo.setMinimumWidth(selector_field_width)
        combo.setMaximumWidth(selector_field_width)
        combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        combo.setStyleSheet(self._combo_style())
        combo.currentIndexChanged.connect(lambda _idx, c=combo: self._on_selector_changed(c))

        status = QLabel("선택된 현장이 없습니다.")
        status.setObjectName("DetailMeta")
        status.setWordWrap(False)
        status.setMinimumWidth(240)

        search_edit.textChanged.connect(lambda _text, c=combo, e=search_edit: self._filter_site_selector(c, e))

        row.addWidget(title, 0, Qt.AlignLeft | Qt.AlignVCenter)
        row.addWidget(search_edit, 0, Qt.AlignLeft | Qt.AlignVCenter)
        row.addWidget(combo, 0, Qt.AlignLeft | Qt.AlignVCenter)
        row.addWidget(status, 1, Qt.AlignLeft | Qt.AlignVCenter)
        row.addStretch(1)

        self._site_selectors.append((combo, status, search_edit))
        return wrap

    def _current_site_context(self) -> tuple[str, str]:
        if not self._site_selectors:
            return "", ""
        data = self._site_selectors[0][0].currentData()
        if isinstance(data, tuple) and len(data) == 2:
            return str(data[0] or ""), str(data[1] or "")
        return "", ""

    def _populate_site_selector_combo(self, combo: QComboBox, current: tuple[str, str], search_text: str = ""):
        sites = self._site_records()
        search_value = str(search_text or "").strip().lower()
        filtered = [row for row in sites if not search_value or search_value in str(row.get("name", "") or "").lower()]
        combo.blockSignals(True)
        combo.clear()
        if not filtered:
            combo.addItem("검색 결과 없음", ("", ""))
            combo.setEnabled(False)
        else:
            combo.setEnabled(True)
            for row in filtered:
                combo.addItem(self._site_display_text(row), (row.get("business_name", ""), row.get("name", "")))
            target_index = 0
            for idx in range(combo.count()):
                if combo.itemData(idx) == current:
                    target_index = idx
                    break
            combo.setCurrentIndex(target_index)
        combo.blockSignals(False)

    def _filter_site_selector(self, combo: QComboBox, search_edit: QLineEdit):
        current = (self._current_business_name, self._current_site_name)
        self._populate_site_selector_combo(combo, current, search_edit.text().strip())
        self._on_selector_changed(combo)

    def _refresh_work_site_selectors(self):
        sites = self._site_records()
        current = (self._current_business_name, self._current_site_name) if self._current_site_name else self._current_site_context()
        for combo, _status, search_edit in self._site_selectors:
            self._populate_site_selector_combo(combo, current, search_edit.text().strip())
        if sites:
            active = current if current[1] else self._site_selectors[0][0].itemData(0)
            if isinstance(active, tuple) and len(active) == 2:
                self._apply_site_context(str(active[0] or ""), str(active[1] or ""))
                return
        self._apply_site_context("", "")

    def _on_selector_changed(self, source_combo: QComboBox):
        data = source_combo.currentData()
        if isinstance(data, tuple) and len(data) == 2:
            self._apply_site_context(str(data[0] or ""), str(data[1] or ""), source_combo)
        else:
            self._apply_site_context("", "")

    def _apply_site_context(self, business_name: str, site_name: str, source_combo: QComboBox | None = None):
        self._current_business_name = business_name
        self._current_site_name = site_name
        for combo, status, _search_edit in self._site_selectors:
            if combo is not source_combo:
                combo.blockSignals(True)
                for idx in range(combo.count()):
                    if combo.itemData(idx) == (business_name, site_name):
                        combo.setCurrentIndex(idx)
                        break
                combo.blockSignals(False)
            status.setText(
                f"현재 설정 대상: {self._site_display_text({'business_name': business_name, 'name': site_name})}"
                if site_name
                else "선택된 현장이 없습니다."
            )
        self._load_payroll_preset_names()
        if site_name:
            self._load_payroll_item_preset_names()
            self._load_site_settings()
            self._load_payroll_item_settings()

    # ───────────── 탭 1: 근태 점수 기준 ─────────────
    def _create_score_tab(self):
        wrap = QWidget()
        grid = QGridLayout(wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        def _add_inline_score_row(parent_layout: QVBoxLayout, label_text: str, edit: QLineEdit, label_width: int = 128):
            row_wrap = QWidget()
            row = QHBoxLayout(row_wrap)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            label = QLabel(label_text)
            label.setObjectName("FieldLabel")
            label.setFixedWidth(label_width)
            edit.setMinimumHeight(30)
            self._apply_compact_field_width(edit, "small")
            row.addWidget(label, 0)
            row.addWidget(edit, 0)
            row.addStretch(1)
            parent_layout.addWidget(row_wrap)

        score_panel = Panel("근태 점수 기준", "", icon_name="attendance")
        score_panel.body_layout.setSpacing(6)
        for label_text, key in [
            ("기본 시작 점수", "base_score"),
            ("무단결근 차감", "unauthorized_absence"),
            ("무단이탈 차감", "unauthorized_leave"),
            ("지각 차감", "late"),
            ("조퇴 차감", "early_leave"),
            ("경고 차감", "warning"),
        ]:
            edit = QLineEdit()
            self.score_edits[key] = edit
            _add_inline_score_row(score_panel.body_layout, label_text, edit)
        grid.addWidget(score_panel, 0, 0)

        grade_panel = Panel("재입사 참고등급 기준", "", icon_name="business")
        grade_panel.body_layout.setSpacing(6)
        for _minimum, name in REJOIN_GRADES:
            edit = QLineEdit()
            self.grade_edits.append((name, edit))
            _add_inline_score_row(grade_panel.body_layout, f"{name} 최소 점수", edit)
        grid.addWidget(grade_panel, 0, 1)

        guide_panel = Panel("점수 저장", "", icon_name="settings")
        button_row = QHBoxLayout()
        save_btn = QPushButton("저장")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self.save_settings)
        reset_btn = QPushButton("초기화")
        reset_btn.setObjectName("GhostButton")
        reset_btn.clicked.connect(self.reset_settings)
        button_row.addWidget(save_btn)
        button_row.addWidget(reset_btn)
        button_row.addStretch()
        guide_panel.body_layout.addLayout(button_row)
        grid.addWidget(guide_panel, 2, 0, 1, 2)
        return wrap

    # ───────────── 탭 2: 현장별 급여 기준 ─────────────
    def _create_payroll_tab(self):
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        top_note_row = QHBoxLayout()
        top_note_row.setContentsMargins(0, 0, 0, 0)
        top_note_row.addStretch(1)
        top_note = QLabel("항목 삭제 없음 · 위치만 재정리")
        top_note.setStyleSheet("color:#f97316; font-weight:600; font-size:11px;")
        top_note_row.addWidget(top_note)
        layout.addLayout(top_note_row)

        def _compact_panel(panel: Panel) -> Panel:
            try:
                panel.header.layout().setContentsMargins(6, 6, 6, 6)
                panel.header.layout().setSpacing(6)
                panel.header.setMinimumHeight(38)
                panel.body_layout.setContentsMargins(6, 6, 6, 6)
                panel.body_layout.setSpacing(6)
            except Exception:
                pass
            return panel

        selector_panel = Panel("근무 사업장 선택", "")
        selector_panel.body_layout.addWidget(self._create_site_selector_row("근무 사업장"))
        _compact_panel(selector_panel)
        layout.addWidget(selector_panel)

        def _new_line_edit(kind: str = "small", placeholder: str = "") -> QLineEdit:
            edit = QLineEdit()
            edit.setMinimumHeight(30)
            edit.setPlaceholderText(placeholder)
            self._apply_compact_field_width(edit, kind)
            return edit

        def _new_combo(options: list[str], kind: str = "medium") -> QComboBox:
            combo = QComboBox()
            combo.addItems(options)
            combo.setMinimumHeight(30)
            combo.setStyleSheet(self._combo_style())
            self._apply_compact_field_width(combo, kind)
            return combo

        def _new_grid(columns: int = 3) -> QGridLayout:
            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(6)
            for col in range(columns):
                grid.setColumnStretch(col, 1)
            return grid

        def _set_field(key: str, widget):
            self._payroll_edits[key] = widget
            return widget

        def _compact_panel(panel: Panel) -> Panel:
            try:
                panel.header.layout().setContentsMargins(6, 6, 6, 6)
                panel.header.layout().setSpacing(6)
                panel.header.setMinimumHeight(38)
                panel.body_layout.setContentsMargins(6, 6, 6, 6)
                panel.body_layout.setSpacing(6)
            except Exception:
                pass
            return panel

        def _add_inline_field(grid: QGridLayout, row: int, col: int, key: str, label_text: str, widget=None, kind: str | None = None):
            field_kind = kind or self._payroll_field_kind(key)
            if widget is None:
                widget = _new_line_edit(field_kind)
            else:
                self._apply_compact_field_width(widget, field_kind)
            _set_field(key, widget)

            container = QWidget()
            row_layout = QHBoxLayout(container)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            label = QLabel(label_text)
            label.setObjectName("FieldLabel")
            label.setMinimumWidth(88)
            row_layout.addWidget(label, 0, Qt.AlignLeft | Qt.AlignVCenter)
            row_layout.addWidget(widget, 0, Qt.AlignLeft | Qt.AlignVCenter)
            row_layout.addStretch(1)
            grid.addWidget(container, row, col)

        def _build_exception_row(title: str, payroll_key: str, hours_key: str, note_key: str) -> QWidget:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_widget.setMinimumHeight(30)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            title_label = QLabel(title)
            title_label.setStyleSheet("font-weight:700; color:#0f172a; font-size:13px;")
            title_label.setFixedWidth(36)
            row_layout.addWidget(title_label, 0, Qt.AlignLeft | Qt.AlignVCenter)

            pay_combo = _new_combo(PAYROLL_ATTENDANCE_TREATMENT_OPTIONS, "medium")
            _set_field(payroll_key, pay_combo)
            pay_wrap = QWidget()
            pay_row = QHBoxLayout(pay_wrap)
            pay_row.setContentsMargins(0, 0, 0, 0)
            pay_row.setSpacing(6)
            pay_label = QLabel(f"{title} 급여 반영")
            pay_label.setObjectName("FieldLabel")
            pay_label.setMinimumWidth(90)
            pay_row.addWidget(pay_label)
            pay_row.addWidget(pay_combo)
            row_layout.addWidget(pay_wrap, 1)

            hours_combo = _new_combo(PAYROLL_HOURS_MODE_OPTIONS, "medium")
            _set_field(hours_key, hours_combo)
            hours_wrap = QWidget()
            hours_row = QHBoxLayout(hours_wrap)
            hours_row.setContentsMargins(0, 0, 0, 0)
            hours_row.setSpacing(6)
            hours_label = QLabel(f"{title} 기본시간 반영")
            hours_label.setObjectName("FieldLabel")
            hours_label.setMinimumWidth(106)
            hours_row.addWidget(hours_label)
            hours_row.addWidget(hours_combo)
            row_layout.addWidget(hours_wrap, 1)

            note_edit = _new_line_edit("wide", "메모를 입력하세요")
            _set_field(note_key, note_edit)
            note_wrap = QWidget()
            note_row = QHBoxLayout(note_wrap)
            note_row.setContentsMargins(0, 0, 0, 0)
            note_row.setSpacing(6)
            note_label = QLabel(f"{title} 처리 메모")
            note_label.setObjectName("FieldLabel")
            note_label.setMinimumWidth(84)
            note_row.addWidget(note_label)
            note_row.addWidget(note_edit, 1)
            row_layout.addWidget(note_wrap, 2)

            return row_widget

        work_type_combo = _new_combo(["주간", "야간", "교대"], "medium")
        pay_type_combo = _new_combo(["월급제", "일급제", "시급제"], "medium")

        section1 = Panel("1. 기본 근무/급여 방식", "공장 기본값입니다. 근로자 개인설정에 값이 있으면 개인값이 우선 적용됩니다.")
        section1_grid = _new_grid(2)
        _add_inline_field(section1_grid, 0, 0, "work_type", "기본 근무형태", work_type_combo)
        _add_inline_field(section1_grid, 0, 1, "pay_type", "기본 급여형태", pay_type_combo)
        section1.body_layout.addLayout(section1_grid)
        _compact_panel(section1)
        layout.addWidget(section1)

        section2 = Panel("2. 근무 시간 기준", "")
        section2_grid = _new_grid(4)
        _add_inline_field(section2_grid, 0, 0, "day_start", "주간 시작 시각")
        _add_inline_field(section2_grid, 0, 1, "day_end", "주간 종료 시각")
        _add_inline_field(section2_grid, 0, 2, "night_start", "야간 시작 시각")
        _add_inline_field(section2_grid, 0, 3, "night_end", "야간 종료 시각")
        _add_inline_field(section2_grid, 1, 0, "attendance_base_hours", "기본 시간")
        _add_inline_field(section2_grid, 1, 1, "attendance_over_hours", "연장 시간")
        _add_inline_field(section2_grid, 1, 2, "attendance_night_hours", "심야 시간")
        section2.body_layout.addLayout(section2_grid)
        _compact_panel(section2)
        layout.addWidget(section2)

        section3 = Panel("3. 시급 / 공제 기준", "")
        section3_grid = _new_grid(4)
        _add_inline_field(section3_grid, 0, 0, "day_hourly_rate", "주간 시급")
        _add_inline_field(section3_grid, 0, 1, "night_hourly_rate", "야간 시급")
        _add_inline_field(section3_grid, 0, 2, "night_multiplier", "야간 수당 배율")
        _add_inline_field(section3_grid, 0, 3, "late_deduct", "지각 1회 차감")
        _add_inline_field(section3_grid, 1, 0, "absent_deduct", "결근 1일 차감")
        _add_inline_field(section3_grid, 1, 1, "unauthorized_absence_deduct", "무단결근 차감")
        _add_inline_field(section3_grid, 1, 2, "default_meal_deduct", "식대 공제 기본값")
        section3.body_layout.addLayout(section3_grid)
        _compact_panel(section3)
        layout.addWidget(section3)

        severance_method = QComboBox()
        severance_method.addItem("두 방식 모두 표시", "both")
        severance_method.addItem("법정 계산식만", "legal")
        severance_method.addItem("고정 합의 방식만", "fixed")
        severance_method.setMinimumHeight(30)
        severance_method.setStyleSheet(self._combo_style())
        self._apply_compact_field_width(severance_method, "medium")

        section4 = Panel("4. 퇴직금 기준", "")
        section4_grid = _new_grid(3)
        _add_inline_field(section4_grid, 0, 0, "severance_method", "퇴직금 방식", severance_method)
        _add_inline_field(section4_grid, 0, 1, "severance_multiplier", "퇴직금 배율")
        _add_inline_field(section4_grid, 0, 2, "manual_severance", "수기 퇴직금")
        section4.body_layout.addLayout(section4_grid)
        _compact_panel(section4)
        layout.addWidget(section4)

        section5 = Panel("5. 예외 급여 처리", "")
        section5.body_layout.setSpacing(6)
        section5.body_layout.addWidget(_build_exception_row("병원", "hospital_payroll_treatment", "hospital_hours_mode", "hospital_note"))
        section5.body_layout.addWidget(_build_exception_row("지각", "late_payroll_treatment", "late_hours_mode", "late_note"))
        section5.body_layout.addWidget(_build_exception_row("조퇴", "early_leave_payroll_treatment", "early_leave_hours_mode", "early_leave_note"))
        _compact_panel(section5)
        section5.setMinimumHeight(170)
        layout.addWidget(section5)

        layout.addSpacing(6)

        save_row = QHBoxLayout()
        save_row.setContentsMargins(0, 6, 0, 6)
        save_row.setSpacing(6)
        load_preset_btn = QPushButton("기본값 불러오기")
        load_preset_btn.setObjectName("GhostButton")
        load_preset_btn.clicked.connect(self._open_payroll_preset_apply_dialog)
        manage_preset_btn = QPushButton("기본값 관리")
        manage_preset_btn.setObjectName("GhostButton")
        manage_preset_btn.clicked.connect(self._open_payroll_preset_manage_dialog)
        save_row.addWidget(load_preset_btn)
        save_row.addWidget(manage_preset_btn)
        save_row.addStretch(1)
        save_btn = QPushButton("현재 현장 설정 저장")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self.save_payroll_settings)
        save_row.addWidget(save_btn, 0, Qt.AlignRight)
        layout.addLayout(save_row)

        scroll.setWidget(wrap)
        outer_layout.addWidget(scroll)
        return outer

    # ───────────── 탭 4: 사업장별 시간 환산 기준 ─────────────
    def _create_time_conversion_tab(self):
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        selector_panel = Panel("근무 사업장 선택", "선택한 사업장을 기준으로 새 행을 빠르게 추가합니다.")
        selector_panel.body_layout.addWidget(self._create_site_selector_row("근무 사업장"))
        layout.addWidget(selector_panel)

        guide_panel = Panel("적용 기준", "이 화면은 급여 계산식 변경이 아니라 사업장별 환산 기준 저장용입니다.", icon_name="settings")
        guide = QLabel(
            "시간대별, 마감환산표, 날짜별 월간표, 항목별 배율 계산을 한 표에 저장합니다. "
            "마감환산표 값은 이미 배율이 반영된 값이므로 급여 계산에서 다시 배율을 곱하지 않도록 값 종류를 구분합니다."
        )
        guide.setObjectName("DetailMeta")
        guide.setWordWrap(True)
        guide_panel.body_layout.addWidget(guide)
        layout.addWidget(guide_panel)

        action_panel = Panel("사업장별 시간 환산 기준표", "사업장·지역·구분·시간·환산값을 등록합니다.", icon_name="settings")
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)

        load_defaults_btn = QPushButton("기본 사업장 환산표 불러오기")
        load_defaults_btn.setObjectName("GhostButton")
        load_defaults_btn.clicked.connect(self._load_default_time_conversion_rules)
        add_current_btn = QPushButton("선택 사업장 행 추가")
        add_current_btn.setObjectName("GhostButton")
        add_current_btn.clicked.connect(lambda: self._add_time_conversion_rule_row(use_current_site=True))
        add_blank_btn = QPushButton("빈 행 추가")
        add_blank_btn.setObjectName("GhostButton")
        add_blank_btn.clicked.connect(lambda: self._add_time_conversion_rule_row(use_current_site=False))
        delete_btn = QPushButton("선택 행 삭제")
        delete_btn.setObjectName("GhostButton")
        delete_btn.clicked.connect(self._delete_time_conversion_selected_rows)
        save_btn = QPushButton("시간 환산 기준 저장")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self.save_time_conversion_rules)

        button_row.addWidget(load_defaults_btn)
        button_row.addWidget(add_current_btn)
        button_row.addWidget(add_blank_btn)
        button_row.addWidget(delete_btn)
        button_row.addStretch(1)
        button_row.addWidget(save_btn)
        action_panel.body_layout.addLayout(button_row)

        self.time_conversion_table = QTableWidget(0, 17)
        self.time_conversion_table.setHorizontalHeaderLabels([
            "사업자",
            "사업장",
            "지역/세부",
            "환산방식",
            "구분",
            "근무형태",
            "출근/일자",
            "퇴근",
            "기본",
            "연장",
            "심야",
            "특근",
            "특근연장",
            "공휴특근",
            "주휴",
            "값종류",
            "메모",
        ])
        self.time_conversion_table.verticalHeader().setVisible(False)
        self.time_conversion_table.setAlternatingRowColors(True)
        self.time_conversion_table.setMinimumHeight(360)
        self.time_conversion_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.time_conversion_table.horizontalHeader().setStretchLastSection(True)
        self.time_conversion_table.setColumnWidth(0, 110)
        self.time_conversion_table.setColumnWidth(1, 120)
        self.time_conversion_table.setColumnWidth(2, 90)
        self.time_conversion_table.setColumnWidth(3, 120)
        self.time_conversion_table.setColumnWidth(6, 90)
        self.time_conversion_table.setColumnWidth(7, 90)
        for col in range(8, 15):
            self.time_conversion_table.setColumnWidth(col, 68)
        install_resizable_table_columns(
            self.time_conversion_table,
            key="settings/site_time_conversion_table",
            default_widths=[110, 120, 90, 120, 88, 88, 90, 90, 68, 68, 68, 68, 76, 76, 68, 90, 180],
        )
        action_panel.body_layout.addWidget(self.time_conversion_table)
        layout.addWidget(action_panel, 1)

        scroll.setWidget(wrap)
        outer_layout.addWidget(scroll)
        self._load_time_conversion_rules()
        return outer

    def _time_conversion_columns(self) -> list[str]:
        return [
            "business_name",
            "work_site_name",
            "area_name",
            "conversion_type",
            "day_type",
            "shift_type",
            "start_time",
            "end_time",
            "base_hours",
            "over_hours",
            "night_hours",
            "special_hours",
            "special_over_hours",
            "holiday_special_hours",
            "weekly_holiday_hours",
            "value_type",
            "memo",
        ]

    def _set_time_conversion_item(self, row: int, col: int, value):
        item = QTableWidgetItem("" if value in (None, "") else str(value))
        if col >= 8 and col <= 14:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.time_conversion_table.setItem(row, col, item)

    def _append_time_conversion_table_row(self, row_data: dict | None = None):
        if self.time_conversion_table is None:
            return
        row_data = row_data or {}
        row = self.time_conversion_table.rowCount()
        self.time_conversion_table.insertRow(row)
        for col, key in enumerate(self._time_conversion_columns()):
            value = row_data.get(key, "")
            self._set_time_conversion_item(row, col, value)

    def _add_time_conversion_rule_row(self, use_current_site: bool = False):
        row_data: dict = {
            "conversion_type": "시간대별",
            "value_type": "실제시간",
        }
        if use_current_site:
            row_data["business_name"] = self._current_business_name
            row_data["work_site_name"] = self._current_site_name
        self._append_time_conversion_table_row(row_data)
        if self.time_conversion_table is not None and self.time_conversion_table.rowCount() > 0:
            self.time_conversion_table.scrollToBottom()
            self.time_conversion_table.selectRow(self.time_conversion_table.rowCount() - 1)

    def _delete_time_conversion_selected_rows(self):
        if self.time_conversion_table is None:
            return
        rows = sorted({index.row() for index in self.time_conversion_table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "시간 환산 기준", "삭제할 행을 선택하세요.")
            return
        for row in rows:
            self.time_conversion_table.removeRow(row)

    def _time_conversion_duplicate_key(self, row_data: dict) -> tuple[str, ...]:
        def _clean(key: str) -> str:
            return str(row_data.get(key, "") or "").strip()
        return (
            _clean("business_name"),
            _clean("work_site_name"),
            _clean("area_name"),
            _clean("conversion_type"),
            _clean("day_type"),
            _clean("shift_type"),
            _clean("start_time"),
            _clean("end_time"),
            _clean("base_hours"),
            _clean("over_hours"),
            _clean("night_hours"),
            _clean("special_hours"),
            _clean("special_over_hours"),
            _clean("holiday_special_hours"),
            _clean("weekly_holiday_hours"),
            _clean("value_type"),
            _clean("memo"),
        )

    def _load_default_time_conversion_rules(self):
        if self.time_conversion_table is None:
            return
        try:
            from .site_time_conversion_defaults import DEFAULT_SITE_TIME_CONVERSION_RULES
        except Exception as exc:
            QMessageBox.warning(self, "시간 환산 기준", f"기본 환산표를 불러오지 못했습니다.\n{exc}")
            return

        existing_rows = self._collect_time_conversion_rows()
        existing_keys = {self._time_conversion_duplicate_key(row) for row in existing_rows}
        added = 0
        self.time_conversion_table.blockSignals(True)
        try:
            for rule in DEFAULT_SITE_TIME_CONVERSION_RULES:
                key = self._time_conversion_duplicate_key(rule)
                if key in existing_keys:
                    continue
                self._append_time_conversion_table_row(rule)
                existing_keys.add(key)
                added += 1
        finally:
            self.time_conversion_table.blockSignals(False)

        before_sites = {
            (str(row.get("business_name", "") or "").strip(), str(row.get("name", "") or "").strip())
            for row in self.state.work_site_records()
        } if hasattr(self.state, "work_site_records") else set()
        rows = self._collect_time_conversion_rows()
        if hasattr(self.state, "update_site_time_conversion_rules"):
            self.state.update_site_time_conversion_rules(rows)
        self._refresh_work_site_selectors()
        self._reload_admin_business_combo()
        after_sites = {
            (str(row.get("business_name", "") or "").strip(), str(row.get("name", "") or "").strip())
            for row in self.state.work_site_records()
        } if hasattr(self.state, "work_site_records") else set()
        linked_sites = len(after_sites - before_sites)
        if added:
            QMessageBox.information(
                self,
                "시간 환산 기준",
                f"기본 사업장 환산표 {added}개 행을 추가하고 저장했습니다.\n근무사업장 마스터 {linked_sites}개도 함께 연결했습니다.\n동기화 버튼을 누르면 다른 PC에도 반영됩니다.",
            )
        else:
            QMessageBox.information(self, "시간 환산 기준", "추가할 기본 환산표가 없습니다. 이미 등록된 상태입니다.\n근무사업장 검색 목록도 다시 확인했습니다.")

    def _collect_time_conversion_rows(self) -> list[dict]:
        if self.time_conversion_table is None:
            return []
        rows: list[dict] = []
        columns = self._time_conversion_columns()
        for row in range(self.time_conversion_table.rowCount()):
            payload: dict = {}
            for col, key in enumerate(columns):
                item = self.time_conversion_table.item(row, col)
                text = item.text().strip() if item else ""
                payload[key] = text
            if any(str(value or "").strip() for value in payload.values()):
                rows.append(payload)
        return rows

    def _load_time_conversion_rules(self):
        if self.time_conversion_table is None:
            return
        self.time_conversion_table.blockSignals(True)
        try:
            rows = self.state.site_time_conversion_rules() if hasattr(self.state, "site_time_conversion_rules") else []
            self.time_conversion_table.setRowCount(0)
            for row in rows:
                self._append_time_conversion_table_row(row)
        finally:
            self.time_conversion_table.blockSignals(False)

    def save_time_conversion_rules(self):
        before_sites = {
            (str(row.get("business_name", "") or "").strip(), str(row.get("name", "") or "").strip())
            for row in self.state.work_site_records()
        } if hasattr(self.state, "work_site_records") else set()
        rows = self._collect_time_conversion_rows()
        if hasattr(self.state, "update_site_time_conversion_rules"):
            self.state.update_site_time_conversion_rules(rows)
        self._refresh_work_site_selectors()
        self._reload_admin_business_combo()
        after_sites = {
            (str(row.get("business_name", "") or "").strip(), str(row.get("name", "") or "").strip())
            for row in self.state.work_site_records()
        } if hasattr(self.state, "work_site_records") else set()
        linked_sites = len(after_sites - before_sites)
        if linked_sites:
            QMessageBox.information(self, "시간 환산 기준", f"사업장별 시간 환산 기준을 저장했습니다.\n근무사업장 마스터 {linked_sites}개도 함께 연결했습니다.")
        else:
            QMessageBox.information(self, "시간 환산 기준", "사업장별 시간 환산 기준을 저장했습니다.")

    # ───────────── 탭 3: 현장별 급여 항목 ─────────────
    def _create_payroll_item_tab(self):
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        selector_panel = Panel("근무 사업장 선택", "")
        selector_panel.body_layout.addWidget(self._create_site_selector_row("근무 사업장"))
        layout.addWidget(selector_panel)

        preset_panel = Panel("급여항목 기본값", "공장별로 여러 항목 세트를 저장하고 선택 적용할 수 있습니다", icon_name="settings")
        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.setSpacing(6)
        preset_label = QLabel("항목 기본값")
        preset_label.setObjectName("FieldLabel")
        self.payroll_item_preset_combo = QComboBox()
        self.payroll_item_preset_combo.setMinimumHeight(30)
        self.payroll_item_preset_combo.setStyleSheet(self._combo_style())
        self._apply_compact_field_width(self.payroll_item_preset_combo, "large")
        self.payroll_item_preset_combo.currentIndexChanged.connect(self._on_payroll_item_preset_changed)
        new_item_preset_btn = QPushButton("새 항목세트 저장")
        new_item_preset_btn.setObjectName("PrimaryButton")
        new_item_preset_btn.clicked.connect(self._save_payroll_item_as_new_preset)
        copy_item_preset_btn = QPushButton("복사")
        copy_item_preset_btn.setObjectName("GhostButton")
        copy_item_preset_btn.clicked.connect(self._copy_payroll_item_preset)
        delete_item_preset_btn = QPushButton("삭제")
        delete_item_preset_btn.setObjectName("GhostButton")
        delete_item_preset_btn.clicked.connect(self._delete_payroll_item_preset)
        preset_row.addWidget(preset_label)
        preset_row.addWidget(self.payroll_item_preset_combo, 1)
        preset_row.addWidget(new_item_preset_btn)
        preset_row.addWidget(copy_item_preset_btn)
        preset_row.addWidget(delete_item_preset_btn)
        preset_panel.body_layout.addLayout(preset_row)
        layout.addWidget(preset_panel)

        action_panel = Panel("현장별 급여 항목", "", icon_name="settings")
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)
        add_btn = QPushButton("항목 추가")
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(self._add_payroll_item_row)
        del_btn = QPushButton("선택 항목 삭제")
        del_btn.setObjectName("GhostButton")
        del_btn.clicked.connect(self._remove_selected_payroll_item_row)
        save_btn = QPushButton("현재 현장 항목 저장")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self.save_payroll_item_settings)
        reset_btn = QPushButton("기본 항목 복원")
        reset_btn.setObjectName("GhostButton")
        reset_btn.clicked.connect(self.reset_payroll_item_settings)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch(1)
        action_panel.body_layout.addLayout(btn_row)
        layout.addWidget(action_panel)

        table_panel = Panel("항목 목록", "", icon_name="payroll")
        self.payroll_item_table = QTableWidget(0, 7)
        self.payroll_item_table.setHorizontalHeaderLabels(["사용", "구분", "항목명", "입력방식", "표시위치", "기본값", "순서"])
        self.payroll_item_table.verticalHeader().setVisible(False)
        self.payroll_item_table.verticalHeader().setDefaultSectionSize(34)
        self.payroll_item_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed | QTableWidget.SelectedClicked)
        install_resizable_table_columns(
            self.payroll_item_table,
            state=self.state,
            key="settings/payroll_item_table",
            default_widths=[58, 102, 180, 122, 112, 92, 66],
            min_widths=[48, 82, 112, 96, 88, 72, 52],
        )
        table_panel.body_layout.addWidget(self.payroll_item_table)
        layout.addWidget(table_panel, 1)
        return wrap


    # ───────────── 탭: 계정권한관리 ─────────────
    def _create_admin_tab(self):
        wrap = QWidget()
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        list_panel = Panel("로그인 계정 목록", "PC에서 생성한 담당자/관리자 로그인 계정과 권한을 보여줍니다.", icon_name="settings")
        list_top = QHBoxLayout()
        list_top.setContentsMargins(0, 0, 0, 0)
        list_top.setSpacing(6)
        refresh_btn = QPushButton("새로고침")
        refresh_btn.setObjectName("GhostButton")
        refresh_btn.clicked.connect(self._load_admin_table)
        list_top.addStretch(1)
        list_top.addWidget(refresh_btn)
        list_panel.body_layout.addLayout(list_top)

        self.admin_table = QTableWidget(0, 7)
        self.admin_table.setHorizontalHeaderLabels(["관리자명", "아이디", "권한", "연락처", "담당 사업자", "담당 근무사업장", "사용"])
        self.admin_table.verticalHeader().setVisible(False)
        self.admin_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.admin_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.admin_table.setSelectionMode(QTableWidget.SingleSelection)
        self.admin_table.itemSelectionChanged.connect(self._admin_table_selection_changed)
        install_resizable_table_columns(
            self.admin_table,
            state=self.state,
            key="settings/admin_table",
            default_widths=[110, 112, 88, 112, 150, 180, 62],
            min_widths=[82, 86, 70, 90, 104, 118, 50],
        )
        list_panel.body_layout.addWidget(self.admin_table, 1)
        layout.addWidget(list_panel, 11)

        detail_panel = Panel("계정 정보 / 권한 배정", "로그인 계정의 권한, 사용 여부, 담당 사업자와 근무사업장을 한 화면에서 관리합니다.", icon_name="settings")

        self.admin_name_edit = QLineEdit()
        self.admin_name_edit.setPlaceholderText("관리자 표시 이름")
        self.admin_username_edit = QLineEdit()
        self.admin_username_edit.setReadOnly(True)
        self.admin_phone_edit = QLineEdit()
        self.admin_phone_edit.setReadOnly(True)
        self.admin_role_edit = QComboBox()
        self.admin_role_edit.addItem("최고관리자", "super_admin")
        self.admin_role_edit.addItem("일반관리자", "manager")
        self.admin_role_edit.currentIndexChanged.connect(self._refresh_admin_assignment_summary_from_ui)
        self.admin_password_edit = QLineEdit()
        self.admin_password_edit.setReadOnly(True)
        self.admin_password_edit.setEchoMode(QLineEdit.Password)
        self.admin_created_at_edit = QLineEdit()
        self.admin_created_at_edit.setReadOnly(True)
        self.admin_updated_at_edit = QLineEdit()
        self.admin_updated_at_edit.setReadOnly(True)
        self.admin_active_check = QCheckBox("사용")
        self.admin_business_combo = QComboBox()
        self.admin_business_combo.setEditable(False)
        self.admin_business_combo.currentIndexChanged.connect(self._reload_admin_work_site_combo)
        self.admin_work_site_table = QTableWidget(0, 2)
        self.admin_work_site_table.setHorizontalHeaderLabels(["선택", "근무사업장"])
        self.admin_work_site_table.verticalHeader().setVisible(False)
        self.admin_work_site_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.admin_work_site_table.setAlternatingRowColors(True)
        self.admin_work_site_table.itemChanged.connect(self._refresh_admin_assignment_summary_from_ui)
        install_resizable_table_columns(
            self.admin_work_site_table,
            state=self.state,
            key="settings/admin_work_site_table",
            default_widths=[58, 210],
            min_widths=[48, 120],
        )
        self.admin_work_site_table.setFixedHeight(220)
        self.admin_note_edit = QTextEdit()
        self.admin_note_edit.hide()
        self.admin_assignment_summary_label = QLabel("관리자를 선택하면 담당자 정보와 배정 현황이 표시됩니다.")
        self.admin_assignment_summary_label.setObjectName("DetailMeta")
        self.admin_assignment_summary_label.setWordWrap(True)
        self.admin_assignment_summary_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.admin_assignment_summary_label.setFixedHeight(72)
        self.admin_assignment_summary_label.setStyleSheet("padding: 6px; border: 1px solid #d9dee8; border-radius: 8px; background: #fafbfd;")

        info_grid = QGridLayout()
        info_grid.setContentsMargins(0, 0, 0, 0)
        info_grid.setHorizontalSpacing(6)
        info_grid.setVerticalSpacing(6)
        info_grid.setColumnStretch(1, 1)
        info_grid.setColumnStretch(3, 1)

        def add_info_pair(row: int, left_label: str, left_widget: QWidget, right_label: str, right_widget: QWidget):
            lbl1 = QLabel(left_label)
            lbl2 = QLabel(right_label)
            lbl1.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            lbl2.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            info_grid.addWidget(lbl1, row, 0)
            info_grid.addWidget(left_widget, row, 1)
            info_grid.addWidget(lbl2, row, 2)
            info_grid.addWidget(right_widget, row, 3)

        add_info_pair(0, "관리자명", self.admin_name_edit, "아이디", self.admin_username_edit)
        add_info_pair(1, "연락처", self.admin_phone_edit, "권한", self.admin_role_edit)
        add_info_pair(2, "비밀번호", self.admin_password_edit, "사용 여부", self.admin_active_check)
        add_info_pair(3, "등록일", self.admin_created_at_edit, "수정일", self.admin_updated_at_edit)
        detail_panel.body_layout.addLayout(info_grid)

        business_row = QHBoxLayout()
        business_row.setContentsMargins(0, 0, 0, 0)
        business_row.setSpacing(6)
        business_label = QLabel("담당 사업자")
        business_label.setMinimumWidth(78)
        business_row.addWidget(business_label)
        business_row.addWidget(self.admin_business_combo, 1)
        detail_panel.body_layout.addLayout(business_row)

        work_site_title = QLabel("담당 근무사업장")
        work_site_title.setObjectName("DetailName")
        detail_panel.body_layout.addWidget(work_site_title)
        detail_panel.body_layout.addWidget(self.admin_work_site_table)

        summary_title = QLabel("배정 현황")
        summary_title.setObjectName("DetailName")
        detail_panel.body_layout.addWidget(summary_title)
        detail_panel.body_layout.addWidget(self.admin_assignment_summary_label)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)
        password_btn = QPushButton("비밀번호 변경")
        password_btn.setObjectName("GhostButton")
        password_btn.clicked.connect(self.change_admin_password)
        reset_password_btn = QPushButton("비밀번호 초기화")
        reset_password_btn.setObjectName("GhostButton")
        reset_password_btn.clicked.connect(self.reset_admin_password)
        delete_btn = QPushButton("삭제")
        delete_btn.setObjectName("GhostButton")
        delete_btn.clicked.connect(self.delete_admin_account)
        save_btn = QPushButton("정보 저장")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self.save_admin_assignment)
        btn_row.addWidget(password_btn)
        btn_row.addWidget(reset_password_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(save_btn)
        detail_panel.body_layout.addLayout(btn_row)

        guide = QLabel(
            "관리자 신규 등록은 근로자 등록 화면의 담당자등록에서 진행합니다. "
            "이 화면에서는 관리자명, 계정 권한, 비밀번호, 사용 여부, 담당 사업자와 근무사업장 배정을 처리합니다. "
            "최고관리자는 전체 권한이며, 일반관리자는 배정된 사업자+근무사업장 기준으로 서버/모바일 권한에 사용됩니다."
        )
        guide.setObjectName("DetailMeta")
        guide.setWordWrap(True)
        detail_panel.body_layout.addWidget(guide)
        layout.addWidget(detail_panel, 12)
        return wrap

    def _admin_site_pairs(self, account: dict) -> list[dict]:
        pairs: list[dict] = []
        raw_sites = account.get("work_sites") if isinstance(account, dict) else None
        fallback_business = str((account or {}).get("business", "") or "").strip()
        fallback_site = str((account or {}).get("work_site", "") or (account or {}).get("site", "") or "").strip()
        if isinstance(raw_sites, list):
            for item in raw_sites:
                if isinstance(item, dict):
                    business = str(item.get("business") or item.get("business_name") or fallback_business or "").strip()
                    site = str(item.get("work_site") or item.get("site") or item.get("name") or "").strip()
                else:
                    business = fallback_business
                    site = str(item or "").strip()
                if business and site and {"business": business, "work_site": site} not in pairs:
                    pairs.append({"business": business, "work_site": site})
        if not pairs and fallback_business and fallback_site:
            pairs.append({"business": fallback_business, "work_site": fallback_site})
        return pairs

    def _admin_site_display(self, account: dict) -> str:
        pairs = self._admin_site_pairs(account)
        names = [pair.get("work_site", "") for pair in pairs if pair.get("work_site")]
        if not names:
            return ""
        if len(names) == 1:
            return names[0]
        return f"{names[0]} 외 {len(names) - 1}개"

    def _manager_accounts(self) -> list[dict]:
        if hasattr(self.state, "manager_accounts"):
            try:
                rows = self.state.manager_accounts()
                return deepcopy(rows or [])
            except Exception:
                return []
        return []

    def _load_admin_table(self):
        if self.admin_table is None:
            return
        rows = self._manager_accounts()
        current_username = self._selected_admin_username
        self.admin_table.blockSignals(True)
        self.admin_table.setRowCount(len(rows))
        selected_row = -1
        for row_idx, row in enumerate(rows):
            values = [
                row.get("employee_name", ""),
                row.get("username", ""),
                self._admin_role_display(str(row.get("role", "manager") or "manager")),
                row.get("phone", ""),
                row.get("business", ""),
                self._admin_site_display(row),
                "사용" if row.get("active", True) else "중지",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                if col == 0:
                    item.setData(Qt.UserRole, deepcopy(row))
                self.admin_table.setItem(row_idx, col, item)
            if str(row.get("username", "") or "") == current_username:
                selected_row = row_idx
        self.admin_table.blockSignals(False)
        if selected_row >= 0:
            self.admin_table.selectRow(selected_row)
        elif rows:
            self.admin_table.selectRow(0)
        else:
            self._selected_admin_username = ""
            self._set_admin_detail({})

    def _selected_admin_account(self) -> dict | None:
        if self.admin_table is None:
            return None
        row = self.admin_table.currentRow()
        if row < 0:
            return None
        item = self.admin_table.item(row, 0)
        if item is None:
            return None
        return deepcopy(item.data(Qt.UserRole) or {})

    def _admin_table_selection_changed(self):
        account = self._selected_admin_account() or {}
        self._set_admin_detail(account)

    def _admin_role_display(self, role: str) -> str:
        role_key = str(role or "manager").strip().lower()
        if role_key in {"owner", "super", "super_admin", "admin", "최고관리자"}:
            return "최고관리자"
        return "일반관리자"

    def _admin_role_key(self, role: str) -> str:
        return "super_admin" if self._admin_role_display(role) == "최고관리자" else "manager"

    def _set_admin_role_value(self, role: str):
        if self.admin_role_edit is None:
            return
        role_key = self._admin_role_key(role)
        index = self.admin_role_edit.findData(role_key)
        self.admin_role_edit.setCurrentIndex(index if index >= 0 else 1)

    def _selected_admin_role(self) -> str:
        if self.admin_role_edit is None:
            return "manager"
        return str(self.admin_role_edit.currentData() or "manager")

    def _selected_admin_is_super(self) -> bool:
        return self._selected_admin_role() == "super_admin"

    def _admin_assignment_summary(self, account: dict) -> str:
        pairs = self._admin_site_pairs(account)
        if not pairs:
            return "미배정"
        lines = []
        for pair in pairs:
            business = str(pair.get("business", "") or "").strip()
            site = str(pair.get("work_site", "") or "").strip()
            if business and site:
                lines.append(f"- {business} / {site}")
            elif site:
                lines.append(f"- {site}")
        return "\n".join(lines) if lines else "미배정"

    def _set_admin_detail(self, account: dict):
        if not all([self.admin_name_edit, self.admin_username_edit, self.admin_phone_edit, self.admin_role_edit, self.admin_password_edit, self.admin_created_at_edit, self.admin_updated_at_edit, self.admin_active_check, self.admin_note_edit, self.admin_assignment_summary_label]):
            return
        username = str(account.get("username", "") or "")
        self._selected_admin_username = username
        self.admin_name_edit.setText(str(account.get("employee_name", "") or ""))
        self.admin_name_edit.setEnabled(bool(username))
        self.admin_username_edit.setText(username)
        self.admin_phone_edit.setText(str(account.get("phone", "") or ""))
        self._set_admin_role_value(str(account.get("role", "manager") or "manager"))
        self.admin_role_edit.setEnabled(bool(username))
        self.admin_password_edit.setText("********" if username else "")
        self.admin_created_at_edit.setText(str(account.get("created_at", "") or ""))
        self.admin_updated_at_edit.setText(str(account.get("updated_at", "") or ""))
        self.admin_active_check.setChecked(bool(account.get("active", True)) if username else False)
        self.admin_note_edit.setPlainText(str(account.get("note", "") or ""))
        self.admin_assignment_summary_label.setText(self._admin_assignment_summary(account) if username else "관리자를 선택하면 담당자 정보와 배정 현황이 표시됩니다.")
        self._reload_admin_business_combo(str(account.get("business", "") or ""))
        selected_sites = [pair.get("work_site", "") for pair in self._admin_site_pairs(account)]
        self._reload_admin_work_site_combo(selected_sites)
        self._refresh_admin_assignment_summary_from_ui()

    def _reload_admin_business_combo(self, current_text: str | None = None):
        if self.admin_business_combo is None:
            return
        if current_text is None:
            current_text = self.admin_business_combo.currentText()
        self.admin_business_combo.blockSignals(True)
        self.admin_business_combo.clear()
        self.admin_business_combo.addItem("선택 안 함", "")
        for row in self.state.business_master_records():
            name = str(row.get("name", "") or "").strip()
            if name:
                self.admin_business_combo.addItem(name, name)
        target = str(current_text or "").strip()
        index = self.admin_business_combo.findData(target)
        if index < 0 and target:
            self.admin_business_combo.addItem(target, target)
            index = self.admin_business_combo.findData(target)
        self.admin_business_combo.setCurrentIndex(index if index >= 0 else 0)
        self.admin_business_combo.blockSignals(False)
        self._reload_admin_work_site_combo()

    def _selected_admin_work_sites(self) -> list[str]:
        if self.admin_work_site_table is None:
            return []
        selected: list[str] = []
        for row in range(self.admin_work_site_table.rowCount()):
            check_item = self.admin_work_site_table.item(row, 0)
            name_item = self.admin_work_site_table.item(row, 1)
            if check_item is None or name_item is None:
                continue
            if check_item.checkState() == Qt.Checked:
                site_name = str(name_item.data(Qt.UserRole) or name_item.text() or "").strip()
                if site_name and site_name not in selected:
                    selected.append(site_name)
        return selected

    def _reload_admin_work_site_combo(self, current_text: str | list[str] | None = None):
        if self.admin_work_site_table is None or self.admin_business_combo is None:
            return
        if current_text is None:
            selected_sites = set(self._selected_admin_work_sites())
        elif isinstance(current_text, list):
            selected_sites = {str(item or "").strip() for item in current_text if str(item or "").strip()}
        else:
            selected_sites = {str(current_text or "").strip()} if str(current_text or "").strip() else set()
        selected_business = str(self.admin_business_combo.currentData() or "").strip()
        site_rows = self.state.work_site_records(selected_business) if selected_business else []
        self.admin_work_site_table.blockSignals(True)
        self.admin_work_site_table.setRowCount(len(site_rows))
        for row_idx, row in enumerate(site_rows):
            name = str(row.get("name", "") or "").strip()
            business_name = str(row.get("business_name", selected_business) or selected_business or "").strip()
            check_item = QTableWidgetItem("")
            check_item.setFlags((check_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled) & ~Qt.ItemIsEditable)
            check_item.setCheckState(Qt.Checked if name in selected_sites else Qt.Unchecked)
            check_item.setData(Qt.UserRole, {"business": business_name, "work_site": name})
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.UserRole, name)
            self.admin_work_site_table.setItem(row_idx, 0, check_item)
            self.admin_work_site_table.setItem(row_idx, 1, name_item)
        self.admin_work_site_table.blockSignals(False)
        self._refresh_admin_assignment_summary_from_ui()

    def _admin_assignment_summary_from_ui(self) -> str:
        if self.admin_business_combo is None or self.admin_work_site_table is None:
            return "미배정"
        if self._selected_admin_is_super():
            return "최고관리자: 전체 사업자 / 전체 근무사업장"
        business = str(self.admin_business_combo.currentData() or self.admin_business_combo.currentText() or "").strip()
        selected_sites = self._selected_admin_work_sites()
        if not business or not selected_sites:
            return "미배정"
        return "\n".join(f"- {business} / {site}" for site in selected_sites)

    def _refresh_admin_assignment_summary_from_ui(self):
        if self.admin_assignment_summary_label is None:
            return
        if not str(getattr(self, "_selected_admin_username", "") or "").strip():
            self.admin_assignment_summary_label.setText("관리자를 선택하면 담당자 정보와 배정 현황이 표시됩니다.")
            return
        self.admin_assignment_summary_label.setText(self._admin_assignment_summary_from_ui())

    def save_admin_assignment(self):
        account = self._selected_admin_account()
        if not account:
            QMessageBox.information(self, "계정권한관리", "관리자 목록에서 먼저 선택해 주세요.")
            return
        if self.admin_active_check is None or self.admin_business_combo is None or self.admin_work_site_table is None or self.admin_note_edit is None or self.admin_name_edit is None:
            return
        employee_name = str(self.admin_name_edit.text() or "").strip()
        if not employee_name:
            QMessageBox.warning(self, "계정권한관리", "관리자명을 입력해 주세요.")
            return
        business = str(self.admin_business_combo.currentData() or "").strip()
        work_sites = self._selected_admin_work_sites()
        active = self.admin_active_check.isChecked()
        role = self._selected_admin_role()
        if active and role != "super_admin" and (not business or not work_sites):
            QMessageBox.warning(self, "계정권한관리", "사용 중인 일반관리자는 담당 사업자와 근무사업장을 하나 이상 선택해 주세요.")
            return
        note = self.admin_note_edit.toPlainText().strip()
        username = str(account.get("username", "") or "").strip()
        try:
            if hasattr(self.state, "update_manager_account_assignment"):
                saved = self.state.update_manager_account_assignment(username, business, work_sites, active, note, role=role, employee_name=employee_name)
            else:
                payload = deepcopy(account)
                payload.update({"employee_name": employee_name, "business": business, "work_site": work_sites[0] if work_sites else "", "work_sites": [{"business": business, "work_site": site} for site in work_sites], "active": active, "note": note, "role": role})
                saved = self.state.add_or_update_manager_account(payload)
        except Exception as error:
            QMessageBox.warning(self, "계정권한관리", f"계정 권한을 저장하지 못했습니다.\n{error}")
            return
        self._selected_admin_username = str(saved.get("username", username) or username)
        self._load_admin_table()
        QMessageBox.information(self, "계정권한관리", "계정 정보와 권한 배정을 저장했습니다.")


    def _selected_admin_username_for_action(self) -> str:
        account = self._selected_admin_account() or {}
        return str(account.get("username", "") or "").strip()

    def change_admin_password(self):
        username = self._selected_admin_username_for_action()
        if not username:
            QMessageBox.information(self, "계정권한관리", "관리자 목록에서 먼저 선택해 주세요.")
            return
        new_password, ok = QInputDialog.getText(self, "비밀번호 변경", "새 비밀번호", QLineEdit.Password)
        if not ok:
            return
        new_password = str(new_password or "").strip()
        if not new_password:
            QMessageBox.warning(self, "비밀번호 변경", "새 비밀번호를 입력해 주세요.")
            return
        confirm_password, ok = QInputDialog.getText(self, "비밀번호 변경", "새 비밀번호 확인", QLineEdit.Password)
        if not ok:
            return
        if new_password != str(confirm_password or "").strip():
            QMessageBox.warning(self, "비밀번호 변경", "비밀번호 확인이 일치하지 않습니다.")
            return
        try:
            if hasattr(self.state, "change_manager_account_password"):
                saved = self.state.change_manager_account_password(username, new_password)
            else:
                account = self._selected_admin_account() or {}
                account["password"] = new_password
                saved = self.state.add_or_update_manager_account(account)
        except Exception as error:
            QMessageBox.warning(self, "비밀번호 변경", f"비밀번호를 변경하지 못했습니다.\n{error}")
            return
        self._selected_admin_username = str(saved.get("username", username) or username)
        self._load_admin_table()
        QMessageBox.information(self, "비밀번호 변경", "비밀번호를 변경했습니다.")

    def reset_admin_password(self):
        username = self._selected_admin_username_for_action()
        if not username:
            QMessageBox.information(self, "계정권한관리", "관리자 목록에서 먼저 선택해 주세요.")
            return
        new_password, ok = QInputDialog.getText(self, "비밀번호 초기화", "초기화할 새 비밀번호", QLineEdit.Password, "1234")
        if not ok:
            return
        new_password = str(new_password or "").strip()
        if not new_password:
            QMessageBox.warning(self, "비밀번호 초기화", "초기화할 비밀번호를 입력해 주세요.")
            return
        reply = QMessageBox.question(
            self,
            "비밀번호 초기화",
            f"선택한 관리자 계정의 비밀번호를 초기화합니다.\n\n아이디: {username}\n진행하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            if hasattr(self.state, "change_manager_account_password"):
                saved = self.state.change_manager_account_password(username, new_password)
            else:
                account = self._selected_admin_account() or {}
                account["password"] = new_password
                saved = self.state.add_or_update_manager_account(account)
        except Exception as error:
            QMessageBox.warning(self, "비밀번호 초기화", f"비밀번호를 초기화하지 못했습니다.\n{error}")
            return
        self._selected_admin_username = str(saved.get("username", username) or username)
        self._load_admin_table()
        QMessageBox.information(self, "비밀번호 초기화", "비밀번호를 초기화했습니다.")

    def delete_admin_account(self):
        account = self._selected_admin_account() or {}
        username = str(account.get("username", "") or "").strip()
        name = str(account.get("employee_name", "") or "").strip() or username
        if not username:
            QMessageBox.information(self, "계정권한관리", "관리자 목록에서 먼저 선택해 주세요.")
            return
        reply = QMessageBox.question(
            self,
            "관리자 삭제",
            f"선택한 관리자 계정과 배정 정보를 삭제합니다.\n\n관리자: {name}\n아이디: {username}\n\n근로자 원본 정보는 삭제되지 않습니다.\n삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            if hasattr(self.state, "delete_manager_account"):
                self.state.delete_manager_account(username)
            else:
                raise RuntimeError("관리자 삭제 기능을 찾을 수 없습니다.")
        except Exception as error:
            QMessageBox.warning(self, "관리자 삭제", f"관리자를 삭제하지 못했습니다.\n{error}")
            return
        self._selected_admin_username = ""
        self._load_admin_table()
        QMessageBox.information(self, "관리자 삭제", "관리자 계정과 배정 정보를 삭제했습니다. 근로자 정보는 유지됩니다.")



    # ───────────── 탭: 백업관리 ─────────────
    def _create_backup_tab(self):
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        backup_panel = Panel("백업 관리", "백업 위치와 백업/복구를 한 화면에서 관리합니다.", icon_name="settings")
        backup_info = QLabel("기본값은 WorkforceData\\backup 입니다. 위치를 바꾸면 새 백업부터 새 위치를 사용합니다.")
        backup_info.setObjectName("DetailMeta")
        backup_info.setWordWrap(True)
        backup_panel.body_layout.addWidget(backup_info)

        current_row = QHBoxLayout()
        current_label = QLabel("백업 위치")
        current_label.setObjectName("FieldLabel")
        self.backup_dir_edit = QLineEdit()
        self.backup_dir_edit.setMinimumHeight(30)
        self._apply_compact_field_width(self.backup_dir_edit, "path")
        current_row.addWidget(current_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        current_row.addWidget(self.backup_dir_edit, 0, Qt.AlignLeft | Qt.AlignVCenter)
        current_row.addStretch(1)
        backup_panel.body_layout.addLayout(current_row)

        default_row = QHBoxLayout()
        default_label = QLabel("기본 경로")
        default_label.setObjectName("FieldLabel")
        self.backup_default_dir_label = QLabel("")
        self.backup_default_dir_label.setObjectName("DetailMeta")
        self.backup_default_dir_label.setWordWrap(True)
        default_row.addWidget(default_label, 0, Qt.AlignLeft | Qt.AlignTop)
        default_row.addWidget(self.backup_default_dir_label, 0, Qt.AlignLeft | Qt.AlignTop)
        default_row.addStretch(1)
        backup_panel.body_layout.addLayout(default_row)

        button_row = QHBoxLayout()
        browse_btn = QPushButton("폴더 선택")
        browse_btn.setObjectName("GhostButton")
        browse_btn.clicked.connect(self.pick_backup_directory)
        default_btn = QPushButton("기본값 복원")
        default_btn.setObjectName("GhostButton")
        default_btn.clicked.connect(self.reset_backup_directory_to_default)
        open_btn = QPushButton("현재 폴더 열기")
        open_btn.setObjectName("GhostButton")
        open_btn.clicked.connect(self.open_backup_directory)
        save_btn = QPushButton("백업경로 저장")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self.save_backup_directory_settings)
        button_row.addWidget(browse_btn)
        button_row.addWidget(default_btn)
        button_row.addWidget(open_btn)
        button_row.addStretch(1)
        button_row.addWidget(save_btn)
        backup_panel.body_layout.addLayout(button_row)

        rule_label = QLabel("latest에는 최신 백업 1개, history에는 이전 백업을 보관합니다. 백업에는 DB, 설정, 첨부파일, 문서 원본이 포함됩니다.")
        rule_label.setObjectName("DetailMeta")
        rule_label.setWordWrap(True)
        backup_panel.body_layout.addWidget(rule_label)

        action_row = QHBoxLayout()
        backup_now_btn = QPushButton("지금 백업 만들기")
        backup_now_btn.setObjectName("PrimaryButton")
        backup_now_btn.clicked.connect(self.create_backup_now)
        restore_btn = QPushButton("복구하기")
        restore_btn.setObjectName("GhostButton")
        restore_btn.clicked.connect(self.restore_backup_from_selected_directory)
        action_row.addWidget(backup_now_btn)
        action_row.addWidget(restore_btn)
        action_row.addStretch(1)
        backup_panel.body_layout.addLayout(action_row)

        layout.addWidget(backup_panel)
        layout.addStretch(1)
        return wrap

    # ───────────── 탭 5: 기타설정 ─────────────
    def _create_misc_tab(self):
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        autosave_panel = Panel("자동저장/동기화 설정", "모든 데이터는 기본 10분마다 자동 저장·서버 전송을 시도하고, 급할 때는 상단 수동 동기화 버튼을 사용합니다.", icon_name="settings")
        autosave_wrap = QWidget()
        autosave_row = QHBoxLayout(autosave_wrap)
        autosave_row.setContentsMargins(0, 0, 0, 0)
        autosave_row.setSpacing(6)
        autosave_label = QLabel("자동저장 시간")
        autosave_label.setObjectName("FieldLabel")
        self.autosave_minutes_combo = QComboBox()
        self.autosave_minutes_combo.setMinimumHeight(30)
        self.autosave_minutes_combo.setEditable(True)
        self.autosave_minutes_combo.setStyleSheet(self._combo_style())
        self._apply_compact_field_width(self.autosave_minutes_combo, "small")
        for minutes in [5, 10, 30, 60, 120]:
            self.autosave_minutes_combo.addItem(f"{minutes}분", minutes)
        autosave_hint = QLabel("분 단위로 입력하거나 선택")
        autosave_hint.setObjectName("DetailMeta")
        autosave_save_btn = QPushButton("자동저장시간 저장")
        autosave_save_btn.setObjectName("GhostButton")
        autosave_save_btn.clicked.connect(self.save_autosave_settings)
        autosave_row.addWidget(autosave_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        autosave_row.addWidget(self.autosave_minutes_combo, 0, Qt.AlignLeft | Qt.AlignVCenter)
        autosave_row.addWidget(autosave_hint, 1)
        autosave_row.addWidget(autosave_save_btn, 0)
        autosave_panel.body_layout.addWidget(autosave_wrap)
        layout.addWidget(autosave_panel)

        server_api_panel = Panel("서버 연동 설정", "PC 배포본 실행 시 서버 설정 파일을 자동 생성하고, 수동 동기화 키를 저장합니다.", icon_name="settings")
        server_grid = QGridLayout()
        server_grid.setContentsMargins(0, 0, 0, 0)
        server_grid.setHorizontalSpacing(6)
        server_grid.setVerticalSpacing(6)

        self.server_base_url_edit = QLineEdit()
        self.server_base_url_edit.setMinimumHeight(30)
        self.server_base_url_edit.setPlaceholderText("https://sungjo2003.cafe24.com")
        self._apply_compact_field_width(self.server_base_url_edit, "path")

        self.server_sync_key_edit = QLineEdit()
        self.server_sync_key_edit.setMinimumHeight(30)
        self.server_sync_key_edit.setPlaceholderText("서버 .env의 PC_SYNC_KEY 값")
        self.server_sync_key_edit.setEchoMode(QLineEdit.Password)
        self._apply_compact_field_width(self.server_sync_key_edit, "path")

        self.server_timeout_edit = QLineEdit()
        self.server_timeout_edit.setMinimumHeight(30)
        self.server_timeout_edit.setPlaceholderText("5")
        self._apply_compact_field_width(self.server_timeout_edit, "small")

        server_grid.addWidget(QLabel("서버 주소"), 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        server_grid.addWidget(self.server_base_url_edit, 0, 1, Qt.AlignLeft | Qt.AlignVCenter)
        server_grid.addWidget(QLabel("동기화 키"), 1, 0, Qt.AlignLeft | Qt.AlignVCenter)
        server_grid.addWidget(self.server_sync_key_edit, 1, 1, Qt.AlignLeft | Qt.AlignVCenter)
        server_grid.addWidget(QLabel("대기 시간(초)"), 2, 0, Qt.AlignLeft | Qt.AlignVCenter)
        server_grid.addWidget(self.server_timeout_edit, 2, 1, Qt.AlignLeft | Qt.AlignVCenter)

        server_btn_row = QHBoxLayout()
        server_btn_row.setContentsMargins(0, 0, 0, 0)
        server_btn_row.setSpacing(6)
        save_server_btn = QPushButton("서버 설정 저장")
        save_server_btn.setObjectName("PrimaryButton")
        save_server_btn.clicked.connect(self.save_server_api_settings)
        server_btn_row.addWidget(save_server_btn)
        server_btn_row.addStretch(1)
        server_grid.addLayout(server_btn_row, 3, 0, 1, 2)

        self.server_status_label = QLabel("server_api.json은 실행 데이터 폴더에 자동 생성됩니다.")
        self.server_status_label.setObjectName("DetailMeta")
        self.server_status_label.setWordWrap(True)
        server_grid.addWidget(self.server_status_label, 4, 0, 1, 2)

        server_api_panel.body_layout.addLayout(server_grid)
        layout.addWidget(server_api_panel)

        holiday_panel = Panel("공휴일 자동 갱신", "공공데이터포털 인증키로 대한민국 공휴일을 받아와 근태관리와 급여관리에 같이 적용합니다.", icon_name="calendar")
        holiday_grid = QGridLayout()
        holiday_grid.setContentsMargins(0, 0, 0, 0)
        holiday_grid.setHorizontalSpacing(6)
        holiday_grid.setVerticalSpacing(6)

        self.holiday_api_enabled_check = QCheckBox("공휴일 자동 갱신 사용")
        self.holiday_api_enabled_check.setObjectName("FieldLabel")
        holiday_grid.addWidget(self.holiday_api_enabled_check, 0, 0, 1, 3)

        key_label = QLabel("인증키")
        key_label.setObjectName("FieldLabel")
        self.holiday_api_key_edit = QLineEdit()
        self.holiday_api_key_edit.setMinimumHeight(30)
        self.holiday_api_key_edit.setPlaceholderText("공공데이터포털 일반/인코딩 인증키를 붙여넣기")
        self.holiday_api_key_edit.setEchoMode(QLineEdit.Password)
        self._apply_compact_field_width(self.holiday_api_key_edit, "path")
        holiday_grid.addWidget(key_label, 1, 0, Qt.AlignLeft | Qt.AlignVCenter)
        holiday_grid.addWidget(self.holiday_api_key_edit, 1, 1, Qt.AlignLeft | Qt.AlignVCenter)

        save_holiday_btn = QPushButton("공휴일 설정 저장")
        save_holiday_btn.setObjectName("PrimaryButton")
        save_holiday_btn.clicked.connect(self.save_holiday_api_settings)
        sync_holiday_btn = QPushButton("지금 갱신")
        sync_holiday_btn.setObjectName("GhostButton")
        sync_holiday_btn.clicked.connect(self.sync_holiday_api_now)
        button_wrap = QWidget()
        button_layout = QHBoxLayout(button_wrap)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(6)
        button_layout.addWidget(save_holiday_btn)
        button_layout.addWidget(sync_holiday_btn)
        button_layout.addStretch(1)
        holiday_grid.addWidget(button_wrap, 1, 2, Qt.AlignLeft | Qt.AlignVCenter)

        api_link_label = QLabel(
            '<a href="https://www.data.go.kr/data/15012690/openapi.do">공공데이터포털 인증키 발급/활용신청 페이지 열기</a>'
        )
        api_link_label.setObjectName("DetailMeta")
        api_link_label.setOpenExternalLinks(True)
        api_link_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        api_link_label.setToolTip("한국천문연구원_특일 정보 API 페이지를 엽니다.")
        holiday_grid.addWidget(api_link_label, 2, 0, 1, 3)

        self.holiday_api_status_label = QLabel("인증키를 저장하면 올해와 다음해 공휴일을 자동으로 저장합니다.")
        self.holiday_api_status_label.setObjectName("DetailMeta")
        self.holiday_api_status_label.setWordWrap(True)
        holiday_grid.addWidget(self.holiday_api_status_label, 3, 0, 1, 3)
        holiday_panel.body_layout.addLayout(holiday_grid)
        layout.addWidget(holiday_panel)

        guide_panel = Panel("기타 안내", "기타 사용 기준을 간단히 확인합니다.", icon_name="settings")
        guide_text = QLabel(
            "- 현재 DB 위치: data/db/workforce.db\n"
            "- 백업 위치와 복구는 백업관리 화면에서 관리합니다.\n"
            "- 자동 동기화는 기본 10분 기준으로 동작합니다."
        )
        guide_text.setObjectName("DetailMeta")
        guide_text.setWordWrap(True)
        guide_panel.body_layout.addWidget(guide_text)
        layout.addWidget(guide_panel)

        version_panel = Panel("버전 정보", "프로그램 버전과 내부 저장구조 버전을 함께 표시합니다.", icon_name="settings")
        version_grid = QGridLayout()
        version_grid.setContentsMargins(0, 0, 0, 0)
        version_grid.setHorizontalSpacing(6)
        version_grid.setVerticalSpacing(6)
        version_program_label = QLabel("프로그램 버전")
        version_program_label.setObjectName("FieldLabel")
        version_program_value = QLabel(PROGRAM_VERSION)
        version_program_value.setObjectName("DetailMeta")
        version_storage_label = QLabel("저장구조 버전")
        version_storage_label.setObjectName("FieldLabel")
        version_storage_value = QLabel(str(STORAGE_VERSION))
        version_storage_value.setObjectName("DetailMeta")
        version_note = QLabel("화면 수정은 프로그램 버전으로, 저장 방식 변경은 저장구조 버전으로 구분합니다.")
        version_note.setObjectName("DetailMeta")
        version_note.setWordWrap(True)
        version_grid.addWidget(version_program_label, 0, 0)
        version_grid.addWidget(version_program_value, 0, 1)
        version_grid.addWidget(version_storage_label, 1, 0)
        version_grid.addWidget(version_storage_value, 1, 1)
        version_grid.addWidget(version_note, 2, 0, 1, 2)
        version_panel.body_layout.addLayout(version_grid)
        layout.addWidget(version_panel)
        layout.addStretch(1)
        return wrap

    def _create_vehicle_settings_hero(self):
        hero = QFrame()
        hero.setObjectName("VehicleSettingsHero")
        hero.setMinimumHeight(86)
        hero.setMaximumHeight(86)
        hero.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hero.setStyleSheet(
            "QFrame#VehicleSettingsHero {"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #EFF6FF, stop:1 #F8FAFC);"
            "border: 1px solid #BFDBFE;"
            "border-radius: 14px;"
            "}"
            "QLabel#VehicleSettingsBadge {"
            "color: #2563EB;"
            "font-size: 11px;"
            "font-weight: 900;"
            "letter-spacing: 0.4px;"
            "}"
            "QLabel#VehicleSettingsTitle {"
            "color: #0F172A;"
            "font-size: 20px;"
            "font-weight: 900;"
            "}"
            "QLabel#VehicleSettingsDesc {"
            "color: #475569;"
            "font-size: 12px;"
            "font-weight: 700;"
            "}"
        )

        row = QHBoxLayout(hero)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(6)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(6)

        badge = QLabel("차량관리 설정")
        badge.setObjectName("VehicleSettingsBadge")
        title = QLabel("차량 등록과 렌트카 기준 관리")
        title.setObjectName("VehicleSettingsTitle")
        desc = QLabel("차량 등록, 렌트카 계약 기준, 운전자, 주행거리 경고 기준을 이 화면에서 관리합니다.")
        desc.setObjectName("VehicleSettingsDesc")
        desc.setWordWrap(True)

        text_col.addWidget(badge)
        text_col.addWidget(title)
        text_col.addWidget(desc)
        text_col.addStretch(1)
        row.addLayout(text_col, 1)
        return hero

    # ───────────── 탭 4: 차량관리 설정 ─────────────
    def _create_vehicle_tab(self):
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        alert_panel = Panel("렌트카 경고 기준", "기본값: 남은 5000km / 계약 종료 30일", icon_name="vehicle")
        form = QGridLayout()
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(6)
        remain_label = QLabel("남은 km 경고 기준")
        remain_label.setObjectName("FieldLabel")
        days_label = QLabel("계약 종료 경고 기준 (일)")
        days_label.setObjectName("FieldLabel")
        self.vehicle_alert_remaining_edit = QLineEdit()
        self.vehicle_alert_remaining_edit.setMinimumHeight(30)
        self._apply_compact_field_width(self.vehicle_alert_remaining_edit, "small")
        self.vehicle_alert_days_edit = QLineEdit()
        self.vehicle_alert_days_edit.setMinimumHeight(30)
        self._apply_compact_field_width(self.vehicle_alert_days_edit, "small")
        form.addWidget(remain_label, 0, 0)
        form.addWidget(self.vehicle_alert_remaining_edit, 0, 1, Qt.AlignLeft)
        form.addWidget(days_label, 1, 0)
        form.addWidget(self.vehicle_alert_days_edit, 1, 1, Qt.AlignLeft)
        alert_panel.body_layout.addLayout(form)
        btn_row = QHBoxLayout()
        save_btn = QPushButton("차량 경고 기준 저장")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self.save_vehicle_alert_settings)
        btn_row.addWidget(save_btn)
        btn_row.addStretch(1)
        alert_panel.body_layout.addLayout(btn_row)
        layout.addWidget(alert_panel)

        sync_panel = Panel("차량 서버 연동 상태", "차량 데이터는 별도 체크 없이 기본 연동 대상입니다. 수동 동기화는 프로그램 상단 버튼을 함께 사용합니다.", icon_name="vehicle")
        sync_grid = QGridLayout()
        sync_grid.setHorizontalSpacing(6)
        sync_grid.setVerticalSpacing(6)

        self.vehicle_sync_base_url_label = QLabel("서버 주소: -")
        self.vehicle_sync_base_url_label.setObjectName("DetailMeta")
        self.vehicle_sync_count_label = QLabel("연동 대상: 차량 0대 / 운행 0건 / 주유 0건 / 기타비용 0건")
        self.vehicle_sync_count_label.setObjectName("DetailMeta")
        self.vehicle_sync_status_label = QLabel("상태: 기본 연동 대기")
        self.vehicle_sync_status_label.setObjectName("DetailMeta")
        self.vehicle_sync_status_label.setWordWrap(True)

        sync_grid.addWidget(QLabel("연동 방식"), 0, 0)
        default_sync_label = QLabel("기본 연동 · 10분 자동 동기화 · 상단 수동 동기화 버튼 공통 사용")
        default_sync_label.setObjectName("DetailMeta")
        default_sync_label.setWordWrap(True)
        sync_grid.addWidget(default_sync_label, 0, 1)
        sync_grid.addWidget(self.vehicle_sync_base_url_label, 1, 0, 1, 2)
        sync_grid.addWidget(self.vehicle_sync_count_label, 2, 0, 1, 2)
        sync_grid.addWidget(self.vehicle_sync_status_label, 3, 0, 1, 2)
        sync_panel.body_layout.addLayout(sync_grid)
        layout.addWidget(sync_panel)

        vehicle_panel = Panel("차량 기본정보", "차량 등록 유형: 자차 / 렌트카 · 차량 배치는 설정에서 관리", icon_name="vehicle")
        vehicle_btn_row = QHBoxLayout()
        vehicle_btn_row.setContentsMargins(0, 0, 0, 0)
        vehicle_btn_row.setSpacing(6)
        new_vehicle_btn = QPushButton("신규 등록")
        new_vehicle_btn.setObjectName("PrimaryButton")
        new_vehicle_btn.clicked.connect(self.open_vehicle_create_dialog)
        edit_vehicle_btn = QPushButton("선택 차량 수정")
        edit_vehicle_btn.setObjectName("GhostButton")
        edit_vehicle_btn.clicked.connect(self.open_vehicle_edit_dialog)
        delete_vehicle_btn = QPushButton("선택 차량 삭제")
        delete_vehicle_btn.setObjectName("DangerButton")
        delete_vehicle_btn.clicked.connect(self.delete_selected_vehicle)
        vehicle_btn_row.addWidget(new_vehicle_btn)
        vehicle_btn_row.addWidget(edit_vehicle_btn)
        vehicle_btn_row.addWidget(delete_vehicle_btn)
        vehicle_btn_row.addStretch(1)
        vehicle_panel.body_layout.addLayout(vehicle_btn_row)

        self.vehicle_table = QTableWidget(0, 8)
        self.vehicle_table.setHorizontalHeaderLabels(["차량명", "차량번호", "구분", "주 운전자", "사업자", "근무 사업장", "계약정보", "상태"])
        self.vehicle_table.verticalHeader().setVisible(False)
        self.vehicle_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.vehicle_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.vehicle_table.setSelectionMode(QTableWidget.SingleSelection)
        self.vehicle_table.itemSelectionChanged.connect(self._vehicle_table_selection_changed)
        install_resizable_table_columns(
            self.vehicle_table,
            state=self.state,
            key="settings/vehicle_table",
            default_widths=[130, 112, 76, 110, 120, 150, 112, 72],
            min_widths=[96, 92, 62, 86, 92, 104, 88, 60],
        )
        vehicle_panel.body_layout.addWidget(self.vehicle_table)
        layout.addWidget(vehicle_panel, 1)
        return wrap

    def _style_table_combo(self, combo: QComboBox):
        combo.setMinimumHeight(30)
        combo.setStyleSheet(self._combo_style())

    def _set_payroll_item_row(self, row_index: int, item: dict):
        enabled_item = QTableWidgetItem("")
        enabled_item.setFlags(enabled_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        enabled_item.setCheckState(Qt.Checked if item.get("enabled", True) else Qt.Unchecked)
        self.payroll_item_table.setItem(row_index, 0, enabled_item)

        group_combo = QComboBox()
        group_combo.addItems(list(GROUP_TEXT_TO_KEY.keys()))
        group_combo.setCurrentText(GROUP_KEY_TO_TEXT.get(str(item.get("group", "summary")), "요약"))
        self._style_table_combo(group_combo)
        self.payroll_item_table.setCellWidget(row_index, 1, group_combo)

        label_item = QTableWidgetItem(str(item.get("label", "")))
        label_item.setData(Qt.UserRole, str(item.get("key", "")))
        self.payroll_item_table.setItem(row_index, 2, label_item)

        mode_combo = QComboBox()
        mode_combo.addItems(list(MODE_TEXT_TO_KEY.keys()))
        mode_combo.setCurrentText(MODE_KEY_TO_TEXT.get(str(item.get("input_mode", "manual")), "수동입력"))
        self._style_table_combo(mode_combo)
        self.payroll_item_table.setCellWidget(row_index, 3, mode_combo)

        location_combo = QComboBox()
        location_combo.addItems(list(LOCATION_TEXT_TO_KEY.keys()))
        location_combo.setCurrentText(LOCATION_KEY_TO_TEXT.get(str(item.get("location", "both")), "둘다"))
        self._style_table_combo(location_combo)
        self.payroll_item_table.setCellWidget(row_index, 4, location_combo)

        default_item = QTableWidgetItem(str(item.get("default_value", 0)))
        order_item = QTableWidgetItem(str(item.get("order", row_index + 1)))
        self.payroll_item_table.setItem(row_index, 5, default_item)
        self.payroll_item_table.setItem(row_index, 6, order_item)
        self.payroll_item_table.setRowHeight(row_index, 34)

    def _load_payroll_item_settings(self):
        if not hasattr(self, "payroll_item_table"):
            return
        rows = self.state.get_payroll_detail_item_configs(self._current_site_name, self._current_business_name)
        self.payroll_item_table.setRowCount(len(rows))
        for row_index, item in enumerate(rows):
            self._set_payroll_item_row(row_index, item)

    def _make_internal_key(self, label: str, row_number: int, existing: str = "") -> str:
        if existing:
            return existing
        cleaned = "".join(ch for ch in str(label).strip().lower().replace(" ", "_") if ch.isalnum() or ch == "_")
        return cleaned or f"item_{row_number}"

    def _collect_payroll_item_rows(self) -> list[dict]:
        rows = []
        for row in range(self.payroll_item_table.rowCount()):
            enabled_item = self.payroll_item_table.item(row, 0)
            group_combo = self.payroll_item_table.cellWidget(row, 1)
            label_item = self.payroll_item_table.item(row, 2)
            mode_combo = self.payroll_item_table.cellWidget(row, 3)
            location_combo = self.payroll_item_table.cellWidget(row, 4)
            default_item = self.payroll_item_table.item(row, 5)
            order_item = self.payroll_item_table.item(row, 6)
            label = (label_item.text().strip() if label_item else "")
            if not label:
                continue
            existing_key = str(label_item.data(Qt.UserRole) or "") if label_item else ""
            key = self._make_internal_key(label, row + 1, existing_key)
            try:
                default_value = float((default_item.text() if default_item else "0").strip() or 0)
            except ValueError:
                raise ValueError(f"{row + 1}행 기본값은 숫자로 입력해 주세요.")
            try:
                order = int((order_item.text() if order_item else str(row + 1)).strip() or row + 1)
            except ValueError:
                raise ValueError(f"{row + 1}행 순서는 숫자로 입력해 주세요.")
            rows.append({
                "enabled": bool(enabled_item and enabled_item.checkState() == Qt.Checked),
                "group": GROUP_TEXT_TO_KEY.get(group_combo.currentText() if isinstance(group_combo, QComboBox) else "요약", "summary"),
                "label": label,
                "key": key,
                "input_mode": MODE_TEXT_TO_KEY.get(mode_combo.currentText() if isinstance(mode_combo, QComboBox) else "수동입력", "manual"),
                "location": LOCATION_TEXT_TO_KEY.get(location_combo.currentText() if isinstance(location_combo, QComboBox) else "둘다", "both"),
                "default_value": default_value,
                "order": order,
            })
        return rows

    def _add_payroll_item_row(self):
        row = self.payroll_item_table.rowCount()
        self.payroll_item_table.insertRow(row)
        self._set_payroll_item_row(row, {
            "enabled": True,
            "group": "allowance",
            "label": "새 항목",
            "key": f"item_{row + 1}",
            "input_mode": "manual",
            "location": "both",
            "default_value": 0,
            "order": row + 1,
        })

    def _remove_selected_payroll_item_row(self):
        row = self.payroll_item_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "급여 항목", "삭제할 행을 먼저 선택하세요.")
            return
        self.payroll_item_table.removeRow(row)

    def _prompt_preset_name(self, title: str, label: str, default_value: str = "") -> str:
        value, ok = QInputDialog.getText(self, title, label, text=default_value)
        return str(value or "").strip() if ok else ""

    def _current_payroll_settings_form_values(self) -> dict:
        settings: dict = {}
        wt = self._payroll_edits.get("work_type")
        settings["work_type"] = wt.currentText() if isinstance(wt, QComboBox) else "교대"
        pt = self._payroll_edits.get("pay_type")
        settings["pay_type"] = pt.currentText() if isinstance(pt, QComboBox) else "시급제"
        shift_group = self._payroll_edits.get("shift_start_group")
        settings["shift_start_group"] = shift_group.currentText() if isinstance(shift_group, QComboBox) else SHIFT_GROUP_OPTIONS[0]
        for key in ["day_hourly_rate", "night_hourly_rate", "absent_deduct", "unauthorized_absence_deduct", "late_deduct", "default_meal_deduct", "manual_severance"]:
            widget = self._payroll_edits[key]
            val = widget.text().strip().replace(",", "") if isinstance(widget, QLineEdit) else "0"
            if not val:
                settings[key] = 0
            elif val.lstrip("-").isdigit():
                settings[key] = int(val)
            else:
                raise ValueError(f"{PAYROLL_NUMBER_LABELS.get(key, key)} 항목은 숫자로 입력해 주세요.")
        for key in ["night_multiplier", "severance_multiplier", "attendance_base_hours", "attendance_over_hours", "attendance_night_hours"]:
            widget = self._payroll_edits[key]
            val = widget.text().strip() if isinstance(widget, QLineEdit) else "0"
            try:
                settings[key] = float(val or 0)
            except ValueError:
                raise ValueError(f"{PAYROLL_NUMBER_LABELS.get(key, key)} 항목은 소수점 숫자로 입력해 주세요.")
        for key in ["day_start", "day_end", "night_start", "night_end"]:
            widget = self._payroll_edits[key]
            settings[key] = widget.text().strip() if isinstance(widget, QLineEdit) else "00:00"
        method_combo = self._payroll_edits.get("severance_method")
        if isinstance(method_combo, QComboBox):
            settings["severance_method"] = method_combo.itemData(method_combo.currentIndex()) or "both"
        for key in ["hospital_payroll_treatment", "hospital_hours_mode", "late_payroll_treatment", "late_hours_mode", "early_leave_payroll_treatment", "early_leave_hours_mode"]:
            widget = self._payroll_edits.get(key)
            if isinstance(widget, QComboBox):
                settings[key] = widget.currentText().strip()
        for key in ["hospital_note", "late_note", "early_leave_note"]:
            widget = self._payroll_edits.get(key)
            settings[key] = widget.text().strip() if isinstance(widget, QLineEdit) else ""
        return settings

    def _open_payroll_preset_apply_dialog(self):
        names = self.state.list_payroll_setting_preset_names(None, None)
        if not names:
            QMessageBox.information(self, "기본값 불러오기", "불러올 기본값이 없습니다.")
            return
        if not self._current_site_name:
            QMessageBox.warning(self, "기본값 불러오기", "근무 사업장을 먼저 선택하세요.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("기본값 불러오기")
        dialog.resize(420, 170)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(PAGE_OUTER_SPACING)

        info = QLabel("설정창에서 저장한 기본값을 현재 공장 설정에 적용합니다.")
        info.setWordWrap(True)
        info.setObjectName("DetailMeta")
        layout.addWidget(info)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        label = QLabel("기본값")
        label.setObjectName("FieldLabel")
        label.setMinimumWidth(64)
        combo = QComboBox()
        combo.setMinimumHeight(30)
        combo.setStyleSheet(self._combo_style())
        self._apply_compact_field_width(combo, "large")
        active_name = self.state.get_active_payroll_setting_preset_name(None, None)
        for name in names:
            combo.addItem(name)
        idx = combo.findText(active_name)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        row.addWidget(label)
        row.addWidget(combo, 1)
        layout.addLayout(row)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        manage_btn = QPushButton("기본값 관리")
        manage_btn.setObjectName("GhostButton")
        cancel_btn = QPushButton("닫기")
        cancel_btn.setObjectName("GhostButton")
        apply_btn = QPushButton("선택 기본값 적용")
        apply_btn.setObjectName("PrimaryButton")
        button_row.addWidget(manage_btn)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(apply_btn)
        layout.addLayout(button_row)

        def _apply_selected():
            preset_name = combo.currentText().strip()
            if not preset_name:
                QMessageBox.information(dialog, "기본값 불러오기", "적용할 기본값을 먼저 선택하세요.")
                return
            if not self.state.apply_payroll_setting_preset_to_site(self._current_site_name, preset_name, self._current_business_name):
                QMessageBox.warning(dialog, "기본값 불러오기", "선택한 기본값을 적용하지 못했습니다.")
                return
            self.state.select_payroll_setting_preset(None, preset_name, None)
            self._load_site_settings()
            QMessageBox.information(dialog, "기본값 불러오기", f"'{preset_name}' 기본값을 현재 공장에 적용했습니다.")
            dialog.accept()

        def _open_manage():
            dialog.accept()
            self._open_payroll_preset_manage_dialog()

        apply_btn.clicked.connect(_apply_selected)
        cancel_btn.clicked.connect(dialog.reject)
        manage_btn.clicked.connect(_open_manage)
        dialog.exec()

    def _open_payroll_preset_manage_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("기본값 관리")
        dialog.resize(520, 230)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(PAGE_OUTER_SPACING)

        info = QLabel("여기서는 설정창용 기본값만 관리합니다. 현재 공장 저장은 현장별 급여기준 화면에서 따로 저장됩니다.")
        info.setWordWrap(True)
        info.setObjectName("DetailMeta")
        layout.addWidget(info)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)
        label = QLabel("기본값")
        label.setObjectName("FieldLabel")
        label.setMinimumWidth(64)
        combo = QComboBox()
        combo.setMinimumHeight(30)
        combo.setStyleSheet(self._combo_style())
        self._apply_compact_field_width(combo, "large")
        top_row.addWidget(label)
        top_row.addWidget(combo, 1)
        layout.addLayout(top_row)

        hint_label = QLabel("")
        hint_label.setWordWrap(True)
        hint_label.setObjectName("DetailMeta")
        layout.addWidget(hint_label)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)
        save_new_btn = QPushButton("현재 입력값 새 기본값 저장")
        save_new_btn.setObjectName("PrimaryButton")
        overwrite_btn = QPushButton("선택 기본값 덮어쓰기")
        overwrite_btn.setObjectName("GhostButton")
        row1.addWidget(save_new_btn)
        row1.addWidget(overwrite_btn)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)
        copy_btn = QPushButton("선택 기본값 복사")
        copy_btn.setObjectName("GhostButton")
        delete_btn = QPushButton("선택 기본값 삭제")
        delete_btn.setObjectName("GhostButton")
        close_btn = QPushButton("닫기")
        close_btn.setObjectName("GhostButton")
        row2.addWidget(copy_btn)
        row2.addWidget(delete_btn)
        row2.addStretch(1)
        row2.addWidget(close_btn)
        layout.addLayout(row2)

        def refresh_combo(select_name: str = ""):
            names = self.state.list_payroll_setting_preset_names(None, None)
            active_name = select_name or self.state.get_active_payroll_setting_preset_name(None, None)
            combo.blockSignals(True)
            combo.clear()
            for name in names:
                combo.addItem(name)
            idx = combo.findText(active_name)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)
            _refresh_hint()

        def _refresh_hint():
            current_name = combo.currentText().strip()
            count = combo.count()
            site_text = self._site_display_text({"business_name": self._current_business_name, "name": self._current_site_name}) if self._current_site_name else "선택 공장 없음"
            hint_label.setText(f"현재 선택 기본값: {current_name or '-'} · 저장된 기본값 {count}개 · 현재 화면 공장: {site_text}")

        def _save_new():
            default_name = combo.currentText().strip() or "기본값 1"
            preset_name = self._prompt_preset_name("기본값 관리", "새 기본값 이름", default_name)
            if not preset_name:
                return
            try:
                settings = self._current_payroll_settings_form_values()
            except ValueError as err:
                QMessageBox.warning(dialog, "기본값 관리", str(err))
                return
            self.state.save_payroll_setting_preset(None, preset_name, settings, None)
            refresh_combo(preset_name)
            QMessageBox.information(dialog, "기본값 관리", f"'{preset_name}' 기본값을 저장했습니다.")

        def _overwrite():
            preset_name = combo.currentText().strip()
            if not preset_name:
                QMessageBox.information(dialog, "기본값 관리", "덮어쓸 기본값을 먼저 선택하세요.")
                return
            answer = QMessageBox.question(dialog, "기본값 관리", f"'{preset_name}' 기본값을 현재 입력값으로 덮어쓸까요?")
            if answer != QMessageBox.Yes:
                return
            try:
                settings = self._current_payroll_settings_form_values()
            except ValueError as err:
                QMessageBox.warning(dialog, "기본값 관리", str(err))
                return
            self.state.save_payroll_setting_preset(None, preset_name, settings, None)
            refresh_combo(preset_name)
            QMessageBox.information(dialog, "기본값 관리", f"'{preset_name}' 기본값을 덮어썼습니다.")

        def _copy_selected():
            source_name = combo.currentText().strip()
            if not source_name:
                QMessageBox.information(dialog, "기본값 관리", "복사할 기본값을 먼저 선택하세요.")
                return
            new_name = self._prompt_preset_name("기본값 관리", "복사할 새 이름", f"{source_name} 복사")
            if not new_name:
                return
            if self.state.copy_payroll_setting_preset(None, source_name, new_name, None):
                refresh_combo(new_name)
                QMessageBox.information(dialog, "기본값 관리", f"'{new_name}' 기본값으로 복사했습니다.")

        def _delete_selected():
            preset_name = combo.currentText().strip()
            if not preset_name:
                return
            answer = QMessageBox.question(dialog, "기본값 관리", f"'{preset_name}' 기본값을 삭제할까요?")
            if answer != QMessageBox.Yes:
                return
            ok = self.state.delete_payroll_setting_preset(None, preset_name, None)
            if not ok:
                QMessageBox.information(dialog, "기본값 관리", "기본값은 최소 1개 이상 남아 있어야 합니다.")
                return
            refresh_combo()
            QMessageBox.information(dialog, "기본값 관리", "기본값을 삭제했습니다.")

        combo.currentIndexChanged.connect(_refresh_hint)
        save_new_btn.clicked.connect(_save_new)
        overwrite_btn.clicked.connect(_overwrite)
        copy_btn.clicked.connect(_copy_selected)
        delete_btn.clicked.connect(_delete_selected)
        close_btn.clicked.connect(dialog.accept)

        refresh_combo()
        dialog.exec()

    def _load_payroll_preset_names(self):
        if self.payroll_preset_combo is None:
            return
        self.payroll_preset_combo.blockSignals(True)
        self.payroll_preset_combo.clear()
        names = self.state.list_payroll_setting_preset_names(None, None)
        active_name = self.state.get_active_payroll_setting_preset_name(None, None)
        for name in names:
            self.payroll_preset_combo.addItem(name)
        index = self.payroll_preset_combo.findText(active_name)
        self.payroll_preset_combo.setCurrentIndex(index if index >= 0 else 0)
        self.payroll_preset_combo.blockSignals(False)

    def _on_payroll_preset_changed(self):
        if self.payroll_preset_combo is None:
            return
        name = self.payroll_preset_combo.currentText().strip()
        if not name:
            return
        self.state.select_payroll_setting_preset(None, name, None)

    def _save_payroll_settings_as_new_preset(self):
        preset_name = self._prompt_preset_name("급여기준 기본값", "새 기본값 이름", self.payroll_preset_combo.currentText().strip() if self.payroll_preset_combo else "")
        if not preset_name:
            return
        try:
            settings = self._current_payroll_settings_form_values()
        except ValueError as err:
            QMessageBox.warning(self, "급여 설정", str(err))
            return
        self.state.save_payroll_setting_preset(None, preset_name, settings, None)
        self._load_payroll_preset_names()
        QMessageBox.information(self, "급여 설정", f"'{preset_name}' 기본값을 추가했습니다.")

    def _apply_selected_payroll_preset_to_site(self):
        if self.payroll_preset_combo is None:
            return
        if not self._current_site_name:
            QMessageBox.warning(self, "급여 설정", "근무 사업장을 먼저 선택하세요.")
            return
        preset_name = self.payroll_preset_combo.currentText().strip()
        if not preset_name:
            QMessageBox.information(self, "급여 설정", "적용할 기본값을 먼저 선택하세요.")
            return
        if not self.state.apply_payroll_setting_preset_to_site(self._current_site_name, preset_name, self._current_business_name):
            QMessageBox.warning(self, "급여 설정", "선택한 기본값을 적용하지 못했습니다.")
            return
        self._load_site_settings()
        QMessageBox.information(self, "급여 설정", f"'{preset_name}' 기본값을 현재 현장에 적용했습니다.")

    def _copy_payroll_settings_preset(self):
        if self.payroll_preset_combo is None:
            return
        source_name = self.payroll_preset_combo.currentText().strip()
        new_name = self._prompt_preset_name("급여기준 기본값", "복사할 새 이름", f"{source_name} 복사")
        if not new_name:
            return
        if self.state.copy_payroll_setting_preset(None, source_name, new_name, None):
            self._load_payroll_preset_names()
            QMessageBox.information(self, "급여 설정", f"'{new_name}' 기본값으로 복사했습니다.")

    def _delete_payroll_settings_preset(self):
        if self.payroll_preset_combo is None:
            return
        preset_name = self.payroll_preset_combo.currentText().strip()
        if not preset_name:
            return
        ok = self.state.delete_payroll_setting_preset(None, preset_name, None)
        if not ok:
            QMessageBox.information(self, "급여 설정", "기본값은 최소 1개 이상 남아 있어야 합니다.")
            return
        self._load_payroll_preset_names()

    def _load_payroll_item_preset_names(self):
        if self.payroll_item_preset_combo is None or not self._current_site_name:
            return
        self.payroll_item_preset_combo.blockSignals(True)
        self.payroll_item_preset_combo.clear()
        names = self.state.list_payroll_item_preset_names(self._current_site_name, self._current_business_name)
        active_name = self.state.get_active_payroll_item_preset_name(self._current_site_name, self._current_business_name)
        for name in names:
            self.payroll_item_preset_combo.addItem(name)
        index = self.payroll_item_preset_combo.findText(active_name)
        self.payroll_item_preset_combo.setCurrentIndex(index if index >= 0 else 0)
        self.payroll_item_preset_combo.blockSignals(False)

    def _on_payroll_item_preset_changed(self):
        if self.payroll_item_preset_combo is None or not self._current_site_name:
            return
        name = self.payroll_item_preset_combo.currentText().strip()
        if not name:
            return
        self.state.select_payroll_item_preset(self._current_site_name, name, self._current_business_name)
        self._load_payroll_item_settings()

    def _save_payroll_item_as_new_preset(self):
        if not self._current_site_name:
            QMessageBox.warning(self, "급여 항목", "근무 사업장을 먼저 선택하세요.")
            return
        preset_name = self._prompt_preset_name("급여항목 기본값", "새 항목세트 이름", self.payroll_item_preset_combo.currentText().strip() if self.payroll_item_preset_combo else "")
        if not preset_name:
            return
        try:
            rows = self._collect_payroll_item_rows()
        except ValueError as err:
            QMessageBox.warning(self, "급여 항목", str(err))
            return
        self.state.save_payroll_item_preset(self._current_site_name, preset_name, rows, self._current_business_name)
        self._load_payroll_item_preset_names()
        QMessageBox.information(self, "급여 항목", f"'{preset_name}' 항목세트를 저장했습니다.")

    def _copy_payroll_item_preset(self):
        if self.payroll_item_preset_combo is None or not self._current_site_name:
            return
        source_name = self.payroll_item_preset_combo.currentText().strip()
        new_name = self._prompt_preset_name("급여항목 기본값", "복사할 새 항목세트 이름", f"{source_name} 복사")
        if not new_name:
            return
        if self.state.copy_payroll_item_preset(self._current_site_name, source_name, new_name, self._current_business_name):
            self._load_payroll_item_preset_names()
            QMessageBox.information(self, "급여 항목", f"'{new_name}' 항목세트로 복사했습니다.")

    def _delete_payroll_item_preset(self):
        if self.payroll_item_preset_combo is None or not self._current_site_name:
            return
        preset_name = self.payroll_item_preset_combo.currentText().strip()
        if not preset_name:
            return
        ok = self.state.delete_payroll_item_preset(self._current_site_name, preset_name, self._current_business_name)
        if not ok:
            QMessageBox.information(self, "급여 항목", "항목세트는 최소 1개 이상 남아 있어야 합니다.")
            return
        self._load_payroll_item_preset_names()
        self._load_payroll_item_settings()

    def _load_site_settings(self):
        settings = self.state.get_payroll_settings(self._current_site_name, self._current_business_name)
        wt = self._payroll_edits.get("work_type")
        if isinstance(wt, QComboBox):
            wt.setCurrentText(str(settings.get("work_type", "교대")))
        pt = self._payroll_edits.get("pay_type")
        if isinstance(pt, QComboBox):
            pt.setCurrentText(str(settings.get("pay_type", "시급제")))
        shift_group = self._payroll_edits.get("shift_start_group")
        if isinstance(shift_group, QComboBox):
            shift_group.setCurrentText(str(settings.get("shift_start_group", SHIFT_GROUP_OPTIONS[0])))
        for key, widget in self._payroll_edits.items():
            if isinstance(widget, QLineEdit):
                widget.setText(str(settings.get(key, "")))
        method_combo = self._payroll_edits.get("severance_method")
        if isinstance(method_combo, QComboBox):
            method_val = settings.get("severance_method", "both")
            for i in range(method_combo.count()):
                if method_combo.itemData(i) == method_val:
                    method_combo.setCurrentIndex(i)
                    break
        for key in ["hospital_payroll_treatment", "hospital_hours_mode", "late_payroll_treatment", "late_hours_mode", "early_leave_payroll_treatment", "early_leave_hours_mode"]:
            widget = self._payroll_edits.get(key)
            if isinstance(widget, QComboBox):
                current = str(settings.get(key, widget.currentText()))
                index = widget.findText(current)
                widget.setCurrentIndex(index if index >= 0 else 0)

    def save_payroll_item_settings(self):
        if not self._current_site_name:
            QMessageBox.warning(self, "급여 항목", "근무 사업장을 먼저 선택하세요.")
            return
        try:
            rows = self._collect_payroll_item_rows()
        except ValueError as err:
            QMessageBox.warning(self, "급여 항목", str(err))
            return
        self.state.set_payroll_detail_item_configs(rows, self._current_site_name, self._current_business_name)
        self._load_payroll_item_preset_names()
        QMessageBox.information(self, "급여 항목", f"'{self._site_display_text({'business_name': self._current_business_name, 'name': self._current_site_name})}' 항목 구성을 저장했습니다.")

    def reset_payroll_item_settings(self):
        from .state import DEFAULT_PAYROLL_DETAIL_ITEMS

        if not self._current_site_name:
            QMessageBox.warning(self, "급여 항목", "근무 사업장을 먼저 선택하세요.")
            return
        self.state.set_payroll_detail_item_configs(deepcopy(DEFAULT_PAYROLL_DETAIL_ITEMS), self._current_site_name, self._current_business_name)
        self._load_payroll_item_preset_names()
        self._load_payroll_item_settings()
        QMessageBox.information(self, "급여 항목", "기본 급여 항목으로 복원했습니다.")

    def _restore_default_payroll_settings(self):
        default_settings = self.state.default_payroll_settings()
        wt = self._payroll_edits.get("work_type")
        if isinstance(wt, QComboBox):
            wt.setCurrentText(str(default_settings.get("work_type", "교대")))
        pt = self._payroll_edits.get("pay_type")
        if isinstance(pt, QComboBox):
            pt.setCurrentText(str(default_settings.get("pay_type", "시급제")))
        shift_group = self._payroll_edits.get("shift_start_group")
        if isinstance(shift_group, QComboBox):
            shift_group.setCurrentText(str(default_settings.get("shift_start_group", SHIFT_GROUP_OPTIONS[0])))
        for key, widget in self._payroll_edits.items():
            if isinstance(widget, QLineEdit):
                widget.setText(str(default_settings.get(key, "")))
            elif isinstance(widget, QComboBox) and key != "severance_method":
                current = str(default_settings.get(key, widget.currentText()))
                index = widget.findText(current)
                widget.setCurrentIndex(index if index >= 0 else 0)

    def save_payroll_settings(self):
        if not self._current_site_name:
            QMessageBox.warning(self, "급여 설정", "저장할 근무 사업장을 먼저 선택하세요.")
            return
        try:
            settings = self._current_payroll_settings_form_values()
        except ValueError as err:
            QMessageBox.warning(self, "급여 설정", str(err))
            return
        self.state.update_payroll_settings(self._current_site_name, settings, self._current_business_name)
        self._load_payroll_preset_names()
        QMessageBox.information(self, "급여 설정", f"'{self._site_display_text({'business_name': self._current_business_name, 'name': self._current_site_name})}' 급여 기준을 저장했습니다.")

    def load_from_state(self):
        for key, edit in self.score_edits.items():
            edit.setText(str(self.state.score_settings[key]))
        grade_map = {name: minimum for minimum, name in self.state.rejoin_grades}
        for name, edit in self.grade_edits:
            edit.setText(str(grade_map.get(name, 0)))
        if self.autosave_minutes_combo is not None:
            autosave_value = self.state.autosave_minutes()
            idx = self.autosave_minutes_combo.findData(autosave_value)
            self.autosave_minutes_combo.blockSignals(True)
            if idx >= 0:
                self.autosave_minutes_combo.setCurrentIndex(idx)
            else:
                self.autosave_minutes_combo.setEditText(str(autosave_value))
            self.autosave_minutes_combo.blockSignals(False)
        if self.server_base_url_edit is not None and self.server_sync_key_edit is not None:
            settings = self.state.server_api_settings() if hasattr(self.state, "server_api_settings") else {}
            self.server_base_url_edit.blockSignals(True)
            self.server_sync_key_edit.blockSignals(True)
            if self.server_timeout_edit is not None:
                self.server_timeout_edit.blockSignals(True)
            self.server_base_url_edit.setText(str(settings.get("base_url", "") or ""))
            self.server_sync_key_edit.setText(str(settings.get("pc_sync_key", "") or ""))
            if self.server_timeout_edit is not None:
                self.server_timeout_edit.setText(str(int(settings.get("timeout_seconds", 5) or 5)))
                self.server_timeout_edit.blockSignals(False)
            self.server_base_url_edit.blockSignals(False)
            self.server_sync_key_edit.blockSignals(False)
            if self.server_status_label is not None:
                self.server_status_label.setText("서버 설정 파일이 자동 생성/저장되었습니다.")
        if self.holiday_api_enabled_check is not None and self.holiday_api_key_edit is not None:
            settings = self.state.holiday_api_settings() if hasattr(self.state, "holiday_api_settings") else {}
            self.holiday_api_enabled_check.blockSignals(True)
            self.holiday_api_key_edit.blockSignals(True)
            self.holiday_api_enabled_check.setChecked(bool(settings.get("enabled", False)))
            self.holiday_api_key_edit.setText(str(settings.get("service_key", "") or ""))
            self.holiday_api_enabled_check.blockSignals(False)
            self.holiday_api_key_edit.blockSignals(False)
            if self.holiday_api_status_label is not None:
                last_sync = str(settings.get("last_sync", "") or "").strip()
                last_error = str(settings.get("last_error", "") or "").strip()
                if last_error:
                    self.holiday_api_status_label.setText(f"마지막 오류: {last_error}")
                elif last_sync:
                    self.holiday_api_status_label.setText(f"마지막 공휴일 갱신: {last_sync}")
                else:
                    self.holiday_api_status_label.setText("인증키를 저장하면 올해와 다음해 공휴일을 자동으로 저장합니다.")
        if self.vehicle_alert_remaining_edit is not None and self.vehicle_alert_days_edit is not None:
            settings = self.state.vehicle_alert_settings()
            self.vehicle_alert_remaining_edit.setText(str(int(settings.get("remaining_km_threshold", 5000) or 5000)))
            self.vehicle_alert_days_edit.setText(str(int(settings.get("contract_days_threshold", 30) or 30)))
            self._refresh_vehicle_sync_panel()
            self._load_vehicle_table()
        if self.backup_dir_edit is not None:
            self.backup_dir_edit.setText(self.state.backup_root_path)
        if self.backup_default_dir_label is not None:
            self.backup_default_dir_label.setText(self.state.default_backup_root_path)
        self._load_time_conversion_rules()
        self._refresh_work_site_selectors()
        self._reload_admin_business_combo()
        self._load_admin_table()


    def _load_vehicle_table(self):
        if not hasattr(self, "vehicle_table"):
            return
        rows = self.state.vehicle_records()
        self.vehicle_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            contract_info = "무제한" if row.get("unlimited") else (f"{int(float(row.get('contract_total_limit_km', 0) or 0)):,}km" if row.get("vehicle_type") == "렌트카" else "-")
            values = [
                row.get("vehicle_name", ""),
                row.get("plate_number", ""),
                row.get("vehicle_type", ""),
                row.get("main_driver", ""),
                row.get("business_name", ""),
                row.get("work_site_name", ""),
                contract_info,
                row.get("status", ""),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setData(Qt.UserRole, deepcopy(row))
                self.vehicle_table.setItem(row_idx, col, item)
        if rows:
            restored = False
            for row_idx in range(self.vehicle_table.rowCount()):
                data = self.vehicle_table.item(row_idx, 0).data(Qt.UserRole) or {}
                if str(data.get("vehicle_id", "") or "") == self._selected_vehicle_id:
                    self.vehicle_table.selectRow(row_idx)
                    restored = True
                    break
            if not restored:
                self.vehicle_table.selectRow(0)
        else:
            self._selected_vehicle_id = ""

    def _vehicle_table_selection_changed(self):
        row = self.vehicle_table.currentRow()
        if row < 0:
            return
        data = self.vehicle_table.item(row, 0).data(Qt.UserRole) or {}
        self._selected_vehicle_id = str(data.get("vehicle_id", "") or "")

    def _selected_vehicle(self) -> dict | None:
        row = self.vehicle_table.currentRow()
        if row < 0:
            return None
        return deepcopy(self.vehicle_table.item(row, 0).data(Qt.UserRole) or {})

    def open_vehicle_create_dialog(self):
        dialog = VehicleRegistrationDialog(self.state, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.state.save_vehicle_record(dialog.vehicle_payload())
        except ValueError as error:
            QMessageBox.warning(self, "차량 등록", str(error))
            return
        self.load_from_state()
        QMessageBox.information(self, "차량 등록", "차량을 등록했습니다.")

    def open_vehicle_edit_dialog(self):
        vehicle = self._selected_vehicle()
        if not vehicle:
            QMessageBox.information(self, "차량 수정", "수정할 차량을 먼저 선택해 주세요.")
            return
        dialog = VehicleRegistrationDialog(self.state, vehicle=vehicle, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.state.save_vehicle_record(dialog.vehicle_payload())
        except ValueError as error:
            QMessageBox.warning(self, "차량 수정", str(error))
            return
        self._selected_vehicle_id = str(vehicle.get("vehicle_id", "") or "")
        self.load_from_state()
        QMessageBox.information(self, "차량 수정", "차량 정보를 수정했습니다.")

    def delete_selected_vehicle(self):
        vehicle = self._selected_vehicle()
        if not vehicle:
            QMessageBox.information(self, "차량 삭제", "삭제할 차량을 먼저 선택해 주세요.")
            return
        name = str(vehicle.get("vehicle_name", "") or "")
        if QMessageBox.question(self, "차량 삭제", f"{name} 차량을 삭제할까요?") != QMessageBox.Yes:
            return
        try:
            self.state.delete_vehicle_record(str(vehicle.get("vehicle_id", "") or ""))
        except ValueError as error:
            QMessageBox.warning(self, "차량 삭제", str(error))
            return
        self._selected_vehicle_id = ""
        self.load_from_state()

    def _refresh_vehicle_sync_panel(self):
        if self.vehicle_sync_base_url_label is None and self.vehicle_sync_count_label is None and self.vehicle_sync_status_label is None:
            return
        settings = self.state.vehicle_server_sync_settings() if hasattr(self.state, "vehicle_server_sync_settings") else {}
        server_settings = self.state.server_api_settings() if hasattr(self.state, "server_api_settings") else {}
        base_url = str(server_settings.get("base_url", "") or "").strip()
        if self.vehicle_sync_base_url_label is not None:
            self.vehicle_sync_base_url_label.setText(f"서버 주소: {base_url if base_url else '설정 필요'}")

        counts = self.state.vehicle_server_sync_counts() if hasattr(self.state, "vehicle_server_sync_counts") else {}
        if self.vehicle_sync_count_label is not None:
            self.vehicle_sync_count_label.setText(
                "연동 대상: "
                f"차량 {int(counts.get('vehicles', 0) or 0)}대 / "
                f"운행 {int(counts.get('run_logs', 0) or 0)}건 / "
                f"주유 {int(counts.get('fuel_logs', 0) or 0)}건 / "
                f"기타비용 {int(counts.get('cost_logs', 0) or 0)}건"
            )

        status = str(settings.get("last_status", "기본 연동 대기") or "기본 연동 대기")
        last_at = str(settings.get("last_at", "") or "").strip()
        last_error = str(settings.get("last_error", "") or "").strip()
        status_text = f"상태: {status}"
        if last_at:
            status_text += f" / 마지막 동기화: {last_at}"
        if last_error:
            status_text += f" / 오류: {last_error}"
        if self.vehicle_sync_status_label is not None:
            self.vehicle_sync_status_label.setText(status_text)


    def save_server_api_settings(self):
        if self.server_base_url_edit is None or self.server_sync_key_edit is None:
            return
        base_url = self.server_base_url_edit.text().strip() or "https://sungjo2003.cafe24.com"
        sync_key = self.server_sync_key_edit.text().strip()
        try:
            timeout_seconds = int((self.server_timeout_edit.text() if self.server_timeout_edit is not None else "5") or "5")
        except ValueError:
            QMessageBox.warning(self, "서버 연동 설정", "대기 시간은 숫자로 입력해 주세요.")
            return
        if not sync_key:
            QMessageBox.warning(self, "서버 연동 설정", "동기화 키를 입력해 주세요.")
            return
        if not hasattr(self.state, "save_server_api_settings"):
            return
        settings = self.state.save_server_api_settings(
            {
                "use_server": True,
                "base_url": base_url,
                "timeout_seconds": timeout_seconds,
                "health_path": "/api/health",
                "employees_path": "/api/employees",
                "pc_sync_key": sync_key,
            }
        )
        if self.server_status_label is not None:
            self.server_status_label.setText("서버 설정을 저장했습니다. 수동 동기화에 바로 사용됩니다.")
        self.load_from_state()
        QMessageBox.information(self, "서버 연동 설정", "서버 설정을 저장했습니다.")

    def save_vehicle_alert_settings(self):
        try:
            remain = self._read_int(self.vehicle_alert_remaining_edit, "남은 km 경고 기준")
            days = self._read_int(self.vehicle_alert_days_edit, "계약 종료 경고 기준")
        except ValueError as error:
            QMessageBox.warning(self, "차량관리 설정", str(error))
            return
        self.state.update_vehicle_alert_settings({"remaining_km_threshold": remain, "contract_days_threshold": days})
        QMessageBox.information(self, "차량관리 설정", "렌트카 경고 기준을 저장했습니다.")

    def save_server_mode_settings(self):
        QMessageBox.information(self, "기타설정", "동기화 관련 설정은 화면에서 제거되었습니다. 자동 동기화가 기본으로 동작하고, 필요하면 근로자 관리 화면의 동기화 버튼을 사용합니다.")

    def _handle_holiday_sync_status(self, message: str):
        if self.holiday_api_status_label is not None:
            self.holiday_api_status_label.setText(str(message or "공휴일 갱신 완료"))

    def save_holiday_api_settings(self):
        if self.holiday_api_enabled_check is None or self.holiday_api_key_edit is None:
            return
        enabled = self.holiday_api_enabled_check.isChecked()
        service_key = self.holiday_api_key_edit.text().strip()
        if enabled and not service_key:
            QMessageBox.warning(self, "공휴일 자동 갱신", "공공데이터포털 인증키를 입력해 주세요.")
            return
        if not hasattr(self.state, "save_holiday_api_settings"):
            return
        self.state.save_holiday_api_settings(enabled, service_key)
        if self.holiday_api_status_label is not None:
            self.holiday_api_status_label.setText("공휴일 설정을 저장했습니다. 갱신을 시작합니다." if enabled else "공휴일 자동 갱신을 껐습니다.")
        QMessageBox.information(self, "공휴일 자동 갱신", "공휴일 설정을 저장했습니다.")

    def sync_holiday_api_now(self):
        if not hasattr(self.state, "sync_holidays_async"):
            return
        settings = self.state.holiday_api_settings() if hasattr(self.state, "holiday_api_settings") else {}
        if not settings.get("enabled") or not str(settings.get("service_key", "") or "").strip():
            QMessageBox.warning(self, "공휴일 자동 갱신", "먼저 인증키를 입력하고 공휴일 설정을 저장해 주세요.")
            return
        started = self.state.sync_holidays_async(manual=True)
        if self.holiday_api_status_label is not None:
            self.holiday_api_status_label.setText("공휴일 정보를 갱신 중입니다.")
        if started:
            QMessageBox.information(self, "공휴일 자동 갱신", "공휴일 갱신을 시작했습니다.")

    def save_autosave_settings(self):
        if self.autosave_minutes_combo is None:
            return
        raw_text = self.autosave_minutes_combo.currentText().replace("분", "").strip()
        if not raw_text.isdigit():
            QMessageBox.warning(self, "기타설정", "자동저장 시간은 숫자로 입력해 주세요.")
            return
        saved = self.state.set_autosave_minutes(int(raw_text))
        self.load_from_state()
        QMessageBox.information(self, "기타설정", f"자동저장 시간을 {saved}분으로 저장했습니다.")

    def create_backup_now(self):
        try:
            self.state.backup_now(include_history=True)
        except Exception as error:
            QMessageBox.warning(self, "백업관리", f"백업을 만들지 못했습니다.\n{error}")
            return
        QMessageBox.information(self, "백업관리", "백업 압축파일을 만들었습니다. latest와 history에 저장되었습니다.")

    def restore_backup_from_selected_directory(self):
        start_dir = self.state.backup_history_path or self.state.backup_root_path
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "복구할 백업 압축파일 선택",
            start_dir,
            "백업 압축파일 (*.zip);;모든 파일 (*.*)",
        )
        if not selected:
            return
        if QMessageBox.question(
            self,
            "백업 복구",
            "선택한 백업으로 현재 데이터를 복구합니다.\n복구 전 현재 상태를 먼저 백업한 뒤 진행합니다.\n계속하시겠습니까?",
        ) != QMessageBox.Yes:
            return
        try:
            self.state.backup_now(include_history=True)
            self.state._storage.restore_from_backup(selected)
        except Exception as error:
            QMessageBox.warning(self, "백업 복구", f"복구하지 못했습니다.\n{error}")
            return
        QMessageBox.information(
            self,
            "백업 복구",
            "복구가 완료되었습니다.\n정확한 데이터 반영을 위해 프로그램을 종료한 뒤 다시 실행해 주세요.",
        )

    def pick_backup_directory(self):
        current_dir = self.backup_dir_edit.text().strip() if self.backup_dir_edit is not None else self.state.backup_root_path
        selected = QFileDialog.getExistingDirectory(self, "백업 폴더 선택", current_dir or self.state.default_backup_root_path)
        if selected and self.backup_dir_edit is not None:
            self.backup_dir_edit.setText(selected)

    def reset_backup_directory_to_default(self):
        if self.backup_dir_edit is not None:
            self.backup_dir_edit.setText(self.state.default_backup_root_path)

    def open_backup_directory(self):
        target = self.backup_dir_edit.text().strip() if self.backup_dir_edit is not None else self.state.backup_root_path
        if not target:
            target = self.state.default_backup_root_path
        Path(target).mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def save_backup_directory_settings(self):
        if self.backup_dir_edit is None:
            return
        raw_path = self.backup_dir_edit.text().strip() or self.state.default_backup_root_path
        try:
            saved_path = self.state.set_backup_root_path(raw_path)
        except OSError as error:
            QMessageBox.warning(self, "백업관리", f"백업 폴더를 저장하지 못했습니다.\n{error}")
            return
        self.load_from_state()
        QMessageBox.information(self, "백업관리", f"백업 폴더를 아래 위치로 저장했습니다.\n{saved_path}")

    def _read_int(self, edit: QLineEdit, field_name: str) -> int:
        text = edit.text().strip()
        if not text or not text.lstrip("-").isdigit():
            raise ValueError(f"{field_name}은 숫자로 입력해 주세요.")
        return int(text)

    def save_settings(self):
        try:
            score_settings = {key: self._read_int(edit, key) for key, edit in self.score_edits.items()}
            grade_rows = []
            for name, edit in self.grade_edits:
                grade_rows.append((self._read_int(edit, name), name))
        except ValueError as error:
            QMessageBox.warning(self, "설정", str(error))
            return
        grade_rows.sort(key=lambda item: item[0], reverse=True)
        self.state.update_score_settings(score_settings, grade_rows)
        QMessageBox.information(self, "설정", "점수 기준을 저장했습니다.")

    def reset_settings(self):
        self.state.reset_settings()
        QMessageBox.information(self, "설정", "기본 점수 기준으로 초기화했습니다.")
