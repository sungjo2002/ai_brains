from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QApplication,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from .app_metadata import APP_DISPLAY_NAME
from .styles import GLOBAL_STYLES


class LoginDialog(QDialog):
    """PC 프로그램 시작 전 최고관리자 로그인을 처리하는 창."""

    # 로그인 성공 직후 창을 바로 닫지 않고, 메인 홈 화면이 뒤에서 준비된 뒤 닫기 위한 신호.
    login_succeeded = Signal(dict)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._account: dict | None = None
        self._login_transition_started = False
        self._login_prefs = self.state.pc_login_preferences()
        self.setWindowTitle(f"{APP_DISPLAY_NAME} 로그인")
        self.setWindowIcon(QIcon(str(self._asset_path("app_icon.ico"))))
        self.setModal(True)
        self.setFixedSize(620, 326)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(GLOBAL_STYLES + self._dialog_styles())
        self._build_ui()
        self._load_saved_preferences()
        self.username_edit.setFocus()
        self.username_edit.selectAll()

    def logged_in_account(self) -> dict:
        return dict(self._account or {})

    def reject(self):
        if self._login_transition_started:
            return
        super().reject()

    def _asset_path(self, file_name: str) -> Path:
        return Path(__file__).resolve().parent.parent / "assets" / file_name

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("LoginCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        brand_panel = self._create_brand_panel()
        card_layout.addWidget(brand_panel, 0)

        form_panel = QFrame()
        form_panel.setObjectName("LoginFormPanel")
        form_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(22, 18, 22, 14)
        form_layout.setSpacing(5)

        title = QLabel("관리자 로그인")
        title.setObjectName("LoginMainTitle")
        title.setAlignment(Qt.AlignLeft)
        form_layout.addWidget(title)


        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("아이디를 입력해 주세요")
        self.username_edit.setMinimumHeight(30)
        self.username_edit.returnPressed.connect(self._try_login)
        form_layout.addWidget(self._labeled_field("아이디", self.username_edit))

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("비밀번호를 입력해 주세요")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setMinimumHeight(30)
        self.password_edit.returnPressed.connect(self._try_login)
        form_layout.addWidget(self._labeled_field("비밀번호", self.password_edit))

        option_row = QHBoxLayout()
        option_row.setContentsMargins(0, 0, 0, 0)
        option_row.setSpacing(12)

        self.remember_id_check = QCheckBox("아이디 저장")
        option_row.addWidget(self.remember_id_check)

        self.remember_password_check = QCheckBox("비밀번호 저장")
        self.remember_password_check.toggled.connect(self._sync_password_save_option)
        option_row.addWidget(self.remember_password_check)
        option_row.addStretch(1)
        form_layout.addLayout(option_row)

        form_layout.addSpacing(6)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)

        self.close_btn = QPushButton("닫기")
        self.close_btn.setObjectName("LoginGhostButton")
        self.close_btn.setMinimumHeight(32)
        self.close_btn.clicked.connect(self.reject)
        button_row.addWidget(self.close_btn, 1)

        self.login_btn = QPushButton("로그인")
        self.login_btn.setObjectName("LoginPrimaryButton")
        self.login_btn.setMinimumHeight(32)
        self.login_btn.setDefault(True)
        self.login_btn.clicked.connect(self._try_login)
        button_row.addWidget(self.login_btn, 1)

        form_layout.addLayout(button_row)
        self._build_status_bar(form_layout)
        form_layout.addStretch(1)

        card_layout.addWidget(form_panel, 1)
        outer.addWidget(card)

    def _build_status_bar(self, parent_layout: QVBoxLayout) -> None:
        self.status_bar = QFrame()
        self.status_bar.setObjectName("LoginStatusBar")
        self.status_bar.setFixedHeight(28)

        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(10, 0, 10, 0)
        status_layout.setSpacing(6)

        self.status_label = QLabel("로그인 정보를 입력하세요.")
        self.status_label.setObjectName("LoginStatusLabel")
        self.status_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        status_layout.addWidget(self.status_label, 1)

        parent_layout.addWidget(self.status_bar)

    def _set_status(self, message: str, *, busy: bool = False, error: bool = False) -> None:
        label = getattr(self, "status_label", None)
        bar = getattr(self, "status_bar", None)
        state = "error" if error else ("busy" if busy else "ready")
        if label is not None:
            label.setText(message)
            label.setProperty("state", state)
            label.style().unpolish(label)
            label.style().polish(label)
        if bar is not None:
            bar.setProperty("state", state)
            bar.style().unpolish(bar)
            bar.style().polish(bar)

    def set_transition_status(self, message: str, *, busy: bool = True) -> None:
        """로그인 성공 후 메인 화면 준비 상태를 로그인창 하단 상태바에 표시한다."""
        self._set_status(message, busy=busy)

    def _create_brand_panel(self) -> QFrame:
        brand_panel = QFrame()
        brand_panel.setObjectName("LoginBrandPanel")
        brand_panel.setFixedWidth(228)
        brand_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        brand_layout = QVBoxLayout(brand_panel)
        brand_layout.setContentsMargins(16, 16, 16, 16)
        brand_layout.setSpacing(6)
        brand_layout.addStretch(1)

        logo_label = QLabel()
        logo_label.setObjectName("LoginLogo")
        logo_label.setAlignment(Qt.AlignCenter)
        logo_pixmap = QPixmap(str(self._asset_path("app_icon_login.png")))
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(82, 82, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo_label.setText("인력365")
        brand_layout.addWidget(logo_label, 0, Qt.AlignCenter)

        name_label = QLabel(APP_DISPLAY_NAME)
        name_label.setObjectName("LoginBrandName")
        name_label.setAlignment(Qt.AlignCenter)
        brand_layout.addWidget(name_label)

        sub_label = QLabel("WORKFORCE MANAGER")
        sub_label.setObjectName("LoginBrandSub")
        sub_label.setAlignment(Qt.AlignCenter)
        brand_layout.addWidget(sub_label)

        divider = QFrame()
        divider.setObjectName("LoginBrandDivider")
        divider.setFixedSize(58, 1)
        brand_layout.addWidget(divider, 0, Qt.AlignCenter)

        tagline = QLabel("인력 · 근태 · 급여 · 차량 통합관리")
        tagline.setObjectName("LoginBrandTagline")
        tagline.setAlignment(Qt.AlignCenter)
        brand_layout.addWidget(tagline)
        brand_layout.addStretch(1)
        return brand_panel

    def _labeled_field(self, label_text: str, field: QLineEdit) -> QFrame:
        wrap = QFrame()
        wrap.setObjectName("LoginFieldWrap")
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(label_text)
        label.setObjectName("LoginFieldLabel")
        layout.addWidget(label)
        layout.addWidget(field)
        return wrap

    def _dialog_styles(self) -> str:
        return """
        QDialog {
            background: #F3F7FC;
        }
        QFrame#LoginCard {
            background: #FFFFFF;
            border: 1px solid #D9E2EC;
            border-radius: 18px;
        }
        QFrame#LoginBrandPanel {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2563EB, stop:0.48 #1D4ED8, stop:1 #0B3A91);
            border-top-left-radius: 18px;
            border-bottom-left-radius: 18px;
            border-top-right-radius: 0px;
            border-bottom-right-radius: 0px;
        }
        QLabel#LoginLogo {
            background: transparent;
            min-height: 84px;
        }
        QLabel#LoginBrandName {
            color: #FFFFFF;
            font-size: 21px;
            font-weight: 900;
        }
        QLabel#LoginBrandSub {
            color: rgba(219, 234, 254, 0.95);
            font-size: 10px;
            font-weight: 900;
            letter-spacing: 1.2px;
        }
        QFrame#LoginBrandDivider {
            background: rgba(219, 234, 254, 0.5);
            border: none;
        }
        QLabel#LoginBrandTagline {
            color: #F8FAFC;
            font-size: 10px;
            font-weight: 800;
        }
        QFrame#LoginFormPanel {
            background: #FFFFFF;
            border-top-right-radius: 18px;
            border-bottom-right-radius: 18px;
        }
        QLabel#LoginMainTitle {
            color: #0F172A;
            font-size: 24px;
            font-weight: 900;
        }
        QLabel#LoginFieldLabel {
            color: #334155;
            font-size: 12px;
            font-weight: 900;
        }
        QFrame#LoginFieldWrap {
            background: transparent;
            border: none;
        }
        QDialog QLineEdit {
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            padding: 0 10px;
            color: #0F172A;
            font-size: 12px;
            font-weight: 700;
        }
        QDialog QLineEdit:focus {
            border: 1px solid #2563EB;
            background: #FFFFFF;
        }
        QDialog QCheckBox {
            color: #334155;
            font-size: 12px;
            font-weight: 800;
            spacing: 6px;
        }
        QPushButton#LoginGhostButton {
            background: #FFFFFF;
            color: #0F172A;
            border: 1px solid #CBD5E1;
            border-radius: 9px;
            font-size: 12px;
            font-weight: 900;
        }
        QPushButton#LoginGhostButton:hover {
            background: #F8FAFC;
            border-color: #94A3B8;
        }
        QPushButton#LoginPrimaryButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2563EB, stop:1 #1D4ED8);
            color: #FFFFFF;
            border: 1px solid #1E40AF;
            border-radius: 9px;
            font-size: 12px;
            font-weight: 900;
        }
        QPushButton#LoginPrimaryButton:hover {
            background: #1D4ED8;
        }
        QPushButton#LoginPrimaryButton:disabled,
        QPushButton#LoginGhostButton:disabled {
            background: #E2E8F0;
            color: #64748B;
            border: 1px solid #CBD5E1;
        }
        QFrame#LoginStatusBar {
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
        }
        QFrame#LoginStatusBar[state="busy"] {
            background: #EFF6FF;
            border: 1px solid #BFDBFE;
        }
        QFrame#LoginStatusBar[state="error"] {
            background: #FEF2F2;
            border: 1px solid #FECACA;
        }
        QLabel#LoginStatusLabel {
            color: #64748B;
            font-size: 11px;
            font-weight: 800;
        }
        QLabel#LoginStatusLabel[state="busy"] {
            color: #1D4ED8;
        }
        QLabel#LoginStatusLabel[state="error"] {
            color: #B91C1C;
        }
        """

    def _load_saved_preferences(self) -> None:
        saved_username = str(self._login_prefs.get("saved_username", "") or "").strip()
        saved_password = str(self._login_prefs.get("saved_password", "") or "")

        if saved_username:
            self.username_edit.setText(saved_username)
        if saved_password:
            self.password_edit.setText(saved_password)

        self.remember_id_check.setChecked(bool(self._login_prefs.get("remember_id", False)))
        self.remember_password_check.setChecked(bool(self._login_prefs.get("remember_password", False)))
        self._sync_password_save_option(self.remember_password_check.isChecked())

        if saved_password:
            self.password_edit.setFocus()
            self.password_edit.selectAll()

    def _sync_password_save_option(self, checked: bool) -> None:
        if checked:
            self.remember_id_check.setChecked(True)

    def _save_preferences(self, username: str, password: str) -> None:
        self.state.set_pc_login_preferences(
            remember_id=self.remember_id_check.isChecked(),
            keep_logged_in=False,
            username=username,
            remember_password=self.remember_password_check.isChecked(),
            password=password,
        )

    def _try_login(self):
        if self._login_transition_started:
            return

        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()

        if hasattr(self, "login_btn"):
            self.login_btn.setText("확인 중...")
            self.login_btn.setEnabled(False)
        self._set_status("로그인 확인 중...", busy=True)
        try:
            account = self.state.authenticate_pc_admin(username, password)
        except Exception as error:
            if hasattr(self, "login_btn"):
                self.login_btn.setText("로그인")
                self.login_btn.setEnabled(True)
            self._set_status("아이디 또는 비밀번호를 확인하세요.", error=True)
            QMessageBox.warning(self, "로그인 실패", str(error))
            self.password_edit.selectAll()
            self.password_edit.setFocus()
            return

        self._save_preferences(username, password)
        self._account = account
        self._login_transition_started = True

        # 로그인창을 즉시 닫으면 메인창이 완성되기 전 바탕/흰 화면이 보일 수 있다.
        # 로그인창을 잠깐 유지한 상태로 메인 홈 화면을 뒤에서 준비하게 한다.
        self.username_edit.setEnabled(False)
        self.password_edit.setEnabled(False)
        if hasattr(self, "remember_id_check"):
            self.remember_id_check.setEnabled(False)
        if hasattr(self, "remember_password_check"):
            self.remember_password_check.setEnabled(False)
        if hasattr(self, "close_btn"):
            self.close_btn.setEnabled(False)
        if hasattr(self, "login_btn"):
            self.login_btn.setText("홈 화면 준비 중...")
            self.login_btn.setEnabled(False)

        self._set_status("홈 화면 준비 중...", busy=True)
        self.login_succeeded.emit(dict(account or {}))
