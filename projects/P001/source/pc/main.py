from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from src.main_window import MainWindow
from src.state import AppState
from src.login_dialog import LoginDialog


APP_NAME = "Workforce PC Main"


def resource_path(*parts: str) -> str:
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base_dir = Path(__file__).resolve().parent
    return str(base_dir.joinpath(*parts))


def build_app() -> QApplication:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("OpenAI")

    icon_path = resource_path("assets", "app_icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    font = QFont("Malgun Gothic")
    font.setPointSize(10)
    app.setFont(font)
    return app


def main() -> int:
    app = build_app()

    # 로그인창이 닫히고 메인창이 표시되기 전 아주 짧은 순간에
    # Qt가 "마지막 창이 닫혔다"고 판단해 앱 종료를 예약하지 않도록 로그인 단계에서만 막는다.
    original_quit_on_last_window_closed = app.quitOnLastWindowClosed()
    app.setQuitOnLastWindowClosed(False)

    window_holder: dict[str, object] = {
        "original_quit_on_last_window_closed": original_quit_on_last_window_closed,
    }

    def prepare_login():
        # 로그인창이 뜨기 전 별도 시작 로딩화면을 띄우지 않는다.
        # 화면 전환 안내는 로그인 성공 후 LoginDialog 내부 상태바에서만 처리한다.
        state = AppState()
        state.ensure_default_super_admin_account()
        window_holder["state"] = state
        QTimer.singleShot(0, show_login_dialog)

    def show_login_dialog():
        state = window_holder.get("state")
        if state is None:
            app.quit()
            return

        # 자동 로그인으로 로그인 창을 건너뛰지 않도록 수정.
        # PC 프로그램은 실행할 때 항상 로그인 화면을 먼저 표시한다.
        dialog = LoginDialog(state)

        def handle_login_succeeded(account: dict):
            try:
                prepare_main_window(account, transition_dialog=dialog)
            except Exception as error:
                QMessageBox.critical(dialog, "실행 오류", f"홈 화면을 준비하는 중 문제가 발생했습니다.\n{error}")
                app.quit()

        dialog.login_succeeded.connect(handle_login_succeeded)
        result = dialog.exec()
        if result != QDialog.Accepted:
            try:
                state.prepare_for_exit()
            except Exception:
                pass
            app.quit()
            return

        # 로그인창이 완전히 닫힌 뒤 메인창을 표시한다.
        # 메인창 위에 로그인창 제목줄 조각이 다시 그려지는 현상을 줄이기 위해
        # 로그인창과 메인창을 동시에 겹쳐 표시하지 않는다.
        window = window_holder.get("window")
        if window is None:
            window = prepare_main_window(dialog.logged_in_account())
        show_main_window(window)

    def _set_login_status(dialog: LoginDialog | None, message: str, *, busy: bool = True) -> None:
        if dialog is None:
            return
        try:
            if hasattr(dialog, "set_transition_status"):
                dialog.set_transition_status(message, busy=busy)
            elif hasattr(dialog, "_set_status"):
                dialog._set_status(message, busy=busy)  # type: ignore[attr-defined]
        except Exception:
            pass

    def prepare_main_window(login_account: dict, transition_dialog: LoginDialog | None = None):
        state = window_holder.get("state")
        if state is None:
            app.quit()
            return None

        existing_window = window_holder.get("window")
        if existing_window is not None:
            return existing_window

        _set_login_status(transition_dialog, "홈 화면 구성 중...", busy=True)
        QApplication.processEvents()

        window = MainWindow(resource_path=resource_path, state=state, login_account=login_account)
        window.ensurePolished()
        window_holder["window"] = window

        _set_login_status(transition_dialog, "홈 화면 표시 준비 중...", busy=True)
        QApplication.processEvents()

        if transition_dialog is not None:
            # 로그인창을 숨기지 않고 그대로 둔 상태에서 준비 완료 후 테스트용 2초 대기 시간을 준 뒤 닫는다.
            # 로딩 시간이 2초로 늘어나더라도 창 잔상/조각 깜박임보다 안정적인 전환을 우선한다.
            QTimer.singleShot(2000, transition_dialog.accept)

        return window

    def show_main_window(window):
        if window is None:
            app.quit()
            return

        window.show()
        window.raise_()
        window.activateWindow()
        QApplication.processEvents()

        original_quit = window_holder.get("original_quit_on_last_window_closed")
        if isinstance(original_quit, bool):
            app.setQuitOnLastWindowClosed(original_quit)

    QTimer.singleShot(0, prepare_login)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
