from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QDate, QRect, QRectF, QPointF
from PySide6.QtGui import QCloseEvent, QGuiApplication, QIcon, QPixmap, QPainter, QPainterPath, QLinearGradient, QRadialGradient, QColor, QBrush, QPen, QPalette
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QDateEdit,
    QFrame,
    QGraphicsDropShadowEffect,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .home_page import HomePage
from .state import AppState
from .styles import GLOBAL_STYLES
from .widgets import SidebarButton, make_topbar, style_date_edit_calendar, BannerIllustration, format_korean_top_date
from .icons import get_svg_icon
from .app_metadata import APP_DISPLAY_NAME, PROGRAM_VERSION


PAGE_BACKGROUND_COLOR = "#F4F7FB"


class PageBannerFrame(QFrame):
    """스마트 반응형 이미지 렌더링으로 상단 배너를 그리는 프레임."""

    _pixmap_cache: dict[str, QPixmap] = {}

    def __init__(self):
        super().__init__()
        self.setMinimumSize(0, 0)
        self.setObjectName("HeroCard")
        self.setAttribute(Qt.WA_StyledBackground, False)
        # 둥근 배너는 직접 그리므로 OpaquePaintEvent를 켜면
        # 초기 표시/리사이즈 순간에 덜 칠해진 픽셀이 남아 깜빡일 수 있다.
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self._theme_key = "home"
        self._background_image_path = ""
        self._background_pixmap = QPixmap()
        self._scaled_pixmap = QPixmap()
        self._scaled_cache_key: tuple[str, int] | None = None

    @classmethod
    def preload_images(cls, image_paths) -> None:
        """첫 화면 표시 전에 배너 원본 이미지를 미리 읽어 초기 깜빡임을 줄입니다."""
        for image_path in image_paths or []:
            path_text = str(image_path or "").strip()
            if not path_text or path_text in cls._pixmap_cache:
                continue
            loaded = QPixmap(path_text)
            cls._pixmap_cache[path_text] = loaded if not loaded.isNull() else QPixmap()

    def set_theme(self, key: str) -> None:
        key = str(key or "home").strip() or "home"
        if self._theme_key == key:
            return
        self._theme_key = key
        self.update()

    def set_background_image(self, image_path: str) -> None:
        image_path = str(image_path or "").strip()
        if image_path == self._background_image_path and not self._background_pixmap.isNull():
            return
        self._background_image_path = image_path
        if not image_path:
            self._background_pixmap = QPixmap()
            self._scaled_pixmap = QPixmap()
            self._scaled_cache_key = None
            self.update()
            return
        cached = self._pixmap_cache.get(image_path)
        if cached is None:
            loaded = QPixmap(image_path)
            cached = loaded if not loaded.isNull() else QPixmap()
            self._pixmap_cache[image_path] = cached
        self._background_pixmap = cached
        self._scaled_pixmap = QPixmap()
        self._scaled_cache_key = None
        self.update()

    def paintEvent(self, event):
        radius = 16
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if rect.width() <= 1 or rect.height() <= 1:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        # 먼저 전체 사각 영역을 배경색으로 채워 둥근 모서리 바깥이
        # 이전 프레임/흰 배경으로 보이는 현상을 막는다.
        painter.fillRect(self.rect(), QColor("#F7FAFF"))

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.setClipPath(path)

        w = self.width()
        h = self.height()

        # 모든 페이지 테마를 차분한 파스텔 블루로 통일
        bg1, bg2 = ("#F0F6FF", "#E0EDFF")
        
        base = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
        base.setColorAt(0.00, QColor(bg1))
        base.setColorAt(1.00, QColor(bg2))
        painter.fillPath(path, QBrush(base))

        # 반응형 이미지 렌더링: 우측 45% 영역 차지, 같은 폭에서는 스케일 결과를 재사용
        if not self._background_pixmap.isNull() and w > 10 and h > 10:
            target_w = int(w * 0.45)
            cache_key = (self._background_image_path, target_w)
            if self._scaled_cache_key != cache_key or self._scaled_pixmap.isNull():
                self._scaled_pixmap = self._background_pixmap.scaledToWidth(target_w, Qt.SmoothTransformation)
                self._scaled_cache_key = cache_key
            scaled = self._scaled_pixmap
            target_x = max(0, w - target_w)
            target_y = (h - scaled.height()) / 2
            
            painter.drawPixmap(int(target_x), int(target_y), scaled)

            # 좌측 경계 심리스 페이드 (다크 톤으로 페이드)
            fade_start = max(0, target_x - 40)
            fade_end = target_x + 150
            fade = QLinearGradient(fade_start, 0, fade_end, 0)
            c_solid = QColor(bg1)
            c_transparent = QColor(bg1)
            c_transparent.setAlpha(0)
            
            fade.setColorAt(0.00, c_solid)
            fade.setColorAt(0.50, QColor(c_solid.red(), c_solid.green(), c_solid.blue(), 230))
            fade.setColorAt(1.00, c_transparent)
            painter.fillPath(path, QBrush(fade))

        # 텍스트 영역(좌측)의 가독성을 높이기 위한 기본 오버레이
        text_fade = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.top())
        text_fade.setColorAt(0.00, QColor(255, 255, 255, 240))
        text_fade.setColorAt(0.40, QColor(255, 255, 255, 120))
        text_fade.setColorAt(0.70, QColor(255, 255, 255, 0))
        painter.fillPath(path, QBrush(text_fade))

        # 프리미엄 상단 빛 반사 효과
        soft_light = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
        soft_light.setColorAt(0.00, QColor(255, 255, 255, 180))
        soft_light.setColorAt(0.15, QColor(255, 255, 255, 0))
        painter.fillPath(path, QBrush(soft_light))

        painter.setClipping(False)
        painter.setPen(QPen(QColor("#C8DBF4"), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)



class MainWindow(QMainWindow):
    def __init__(self, resource_path, state: AppState | None = None, login_account: dict | None = None):
        super().__init__()
        self.resource_path = resource_path
        self.state = state if state is not None else AppState()
        self.login_account = dict(login_account or {})
        self.nav_buttons: dict[str, SidebarButton] = {}
        self.topbars: dict[str, QWidget] = {}
        self.page_order = ["home", "business", "employee", "registration", "attendance", "payroll", "vehicle", "settings"]
        self.page_widgets: dict[str, QWidget] = {}
        # 각 메뉴 위치는 처음부터 고정된 host/scroll을 만들어 두고,
        # 메뉴 클릭 중 QStackedWidget remove/insert가 일어나지 않게 한다.
        # 이 구조가 왼쪽 메뉴 첫 클릭 시 본문이 흰색으로 비는 현상을 줄인다.
        self.page_hosts: dict[str, QWidget] = {}
        self.page_scrolls: dict[str, QWidget] = {}
        self._prewarm_page_queue: list[str] = []
        self._save_notice_timer = QTimer(self)
        self._save_notice_timer.setSingleShot(True)
        self._save_notice_timer.timeout.connect(self._hide_save_notice)
        self._sync_status_timer = QTimer(self)
        self._sync_status_timer.setInterval(900)
        self._sync_status_timer.timeout.connect(self._refresh_sync_button_state)
        self._active_page_key = ""
        self._last_banner_state: tuple[str, str, str, str, str] | None = None
        self._main_window_polished_once = False
        # 수동 동기화는 서버 저장/불러오기/화면 반영이 순차로 진행될 수 있어
        # 같은 버튼을 다시 누르지 못하게 UI 쪽에서도 보호한다.
        self._manual_sync_ui_locked = False
        # 데이터 변경 신호가 여러 화면으로 동시에 전달될 때 숨겨진/캐시된 화면도
        # 다음 진입 전에 최신 상태가 되도록 한 번에 묶어 새로고침합니다.
        self._pending_created_page_refresh_keys: set[str] = set()
        self._created_page_refresh_timer = QTimer(self)
        self._created_page_refresh_timer.setSingleShot(True)
        self._created_page_refresh_timer.setInterval(90)
        self._created_page_refresh_timer.timeout.connect(self._refresh_created_pages_after_state_change)

        self.setWindowTitle(f"{APP_DISPLAY_NAME} {PROGRAM_VERSION}")
        # 창을 가로/세로로 줄여도 본문 작업영역에서 스크롤로 처리되도록
        # 메인 창 최소 크기는 낮추고, 실제 화면 최소 폭은 PageScrollArea 안쪽에서 유지한다.
        self.setMinimumSize(960, 640)
        self._fit_initial_size_to_screen()
        self.setStyleSheet(GLOBAL_STYLES)

        icon_path = self.resource_path("assets", "app_icon.ico")
        self.setWindowIcon(QIcon(icon_path))

        self._build_ui()
        self._apply_calendar_theme()
        self._connect_common_refresh_signals()
        self.state.save_completed.connect(self._handle_save_completed)
        self.state.server_sync_status.connect(self._handle_server_sync_status)
        self.switch_page("home", force_refresh=True)
        self._prepare_initial_home_layout()
        QTimer.singleShot(80, self._polish_current_page_after_paint)
        self._refresh_sync_button_state()
        self._sync_status_timer.start()
        # 시작 직후 다른 페이지를 미리 만들면 홈 화면이 보인 뒤 한 번 더 레이아웃이 흔들릴 수 있다.
        # 첫 화면 안정성을 우선해 페이지는 실제 진입 시 생성한다.
        QTimer.singleShot(900, self._check_updates_on_startup)

    def _prepare_initial_home_layout(self):
        if hasattr(self, "home_page"):
            if hasattr(self.home_page, "_layout_status_cards"):
                self.home_page._layout_status_cards()
            if hasattr(self.home_page, "_adjust_splitter_sizes"):
                self.home_page._adjust_splitter_sizes()

    def _polish_current_page_after_paint(self):
        if not hasattr(self, "pages"):
            return
        index = self.pages.currentIndex()
        key = self.page_order[index] if 0 <= index < len(self.page_order) else "home"
        self._update_fixed_page_banner(key)
        if key == "home":
            self._prepare_initial_home_layout()
        if hasattr(self, "fixed_page_banner_card"):
            self.fixed_page_banner_card.update()

    def showEvent(self, event):
        super().showEvent(event)
        if self._main_window_polished_once:
            return
        self._main_window_polished_once = True
        QTimer.singleShot(120, self._polish_current_page_after_paint)

    def _get_page(self, key: str) -> QWidget | None:
        if key in self.page_widgets:
            return self.page_widgets[key]
        if key not in self.page_order:
            return None

        widget = self._create_page(key)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if key in ("payroll", "attendance"):
            # 급여관리/근태관리는 바깥 페이지 스크롤을 만들지 않고,
            # 화면 안에 고정한 뒤 표 영역 내부에서만 필요한 이동을 처리한다.
            widget.setMinimumWidth(0)
            widget.setMaximumWidth(16777215)
            widget.setProperty("disableOuterVerticalScroll", True)
            widget.setProperty("disableOuterHorizontalScroll", True)
        else:
            widget.setMinimumWidth(max(widget.minimumWidth(), 1120))
        self._apply_page_background(widget)

        host = self.page_hosts.get(key)
        if host is None:
            return None
        layout = host.layout()
        if layout is None:
            return None

        try:
            host.setUpdatesEnabled(False)
            # host 자체는 유지하고 내부 실제 페이지만 붙인다.
            # QStackedWidget의 widget 제거/삽입을 없애 메뉴 클릭 순간 흰 화면 노출을 줄인다.
            while layout.count():
                item = layout.takeAt(0)
                child = item.widget()
                if child is not None:
                    child.setParent(None)
                    child.deleteLater()
            layout.addWidget(widget)
        finally:
            host.setUpdatesEnabled(True)

        if key in ("payroll", "attendance"):
            widget.setMinimumWidth(0)
            widget.setMaximumWidth(16777215)
            widget.setProperty("disableOuterVerticalScroll", True)
            widget.setProperty("disableOuterHorizontalScroll", True)
            host.setMinimumWidth(0)
            host.setMaximumWidth(16777215)
            host.setProperty("fixedViewportPage", True)
            host.setProperty("disableOuterVerticalScroll", True)
            host.setProperty("disableOuterHorizontalScroll", True)

        self.page_widgets[key] = widget
        self._apply_calendar_theme(widget)
        self._normalize_page_control_metrics(widget)
        return widget

    def _create_page_host(self, key: str, page: QWidget | None = None) -> QWidget:
        host = QWidget()
        host.setObjectName(f"PageHost_{key}")
        if key in ("payroll", "attendance"):
            # 급여관리/근태관리는 표와 우측 상세 영역이 자체적으로 크기를 맞춘다.
            # 실제 PageScrollArea에는 PageHost가 들어가므로 외부 스크롤 비활성 속성을 host에도 직접 부여한다.
            host.setProperty("disableOuterVerticalScroll", True)
            host.setProperty("disableOuterHorizontalScroll", True)
            host.setMinimumWidth(0)
            host.setMaximumWidth(16777215)
        else:
            host.setMinimumWidth(1120)
        host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._apply_page_background(host)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if page is not None:
            if key in ("payroll", "attendance"):
                page.setMinimumWidth(0)
                page.setMaximumWidth(16777215)
                page.setProperty("disableOuterVerticalScroll", True)
                page.setProperty("disableOuterHorizontalScroll", True)
            else:
                page.setMinimumWidth(max(page.minimumWidth(), 1120))
            page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._apply_page_background(page)
            layout.addWidget(page)
        else:
            filler = QWidget()
            filler.setObjectName(f"PageWarmPlaceholder_{key}")
            filler.setMinimumWidth(0 if key in ("payroll", "attendance") else 1120)
            filler.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._apply_page_background(filler)
            layout.addWidget(filler)
        return host

    def _apply_page_background(self, widget: QWidget | None) -> None:
        if widget is None:
            return
        try:
            palette = widget.palette()
            color = QColor(PAGE_BACKGROUND_COLOR)
            palette.setColor(QPalette.Window, color)
            palette.setColor(QPalette.Base, color)
            widget.setPalette(palette)
            widget.setAutoFillBackground(True)
            widget.setAttribute(Qt.WA_StyledBackground, True)
        except Exception:
            pass

    def _current_content_page(self) -> QWidget | None:
        if not hasattr(self, "pages"):
            return None
        index = self.pages.currentIndex()
        key = self.page_order[index] if 0 <= index < len(self.page_order) else ""
        if key and key in self.page_widgets:
            return self.page_widgets[key]
        current = self.pages.currentWidget()
        if isinstance(current, QScrollArea):
            host = current.widget()
            if host is not None and host.layout() is not None and host.layout().count() > 0:
                child = host.layout().itemAt(0).widget()
                return child
        if current is not None and bool(current.property("fixedViewportPage")) and current.layout() is not None and current.layout().count() > 0:
            host = current.layout().itemAt(0).widget()
            if host is not None and host.layout() is not None and host.layout().count() > 0:
                child = host.layout().itemAt(0).widget()
                return child
            return host
        return current

    def _current_page_key(self) -> str:
        if not hasattr(self, "pages"):
            return ""
        index = self.pages.currentIndex()
        return self.page_order[index] if 0 <= index < len(self.page_order) else ""

    def _connect_common_refresh_signals(self) -> None:
        """저장/동기화 뒤 이미 생성된 다른 화면도 최신 상태로 맞춥니다.

        각 화면 내부의 저장·계산·권한 로직은 건드리지 않고, 화면 갱신 함수만
        짧게 지연 실행해 여러 신호가 연속으로 들어와도 한 번만 처리합니다.
        """
        signal_map = (
            (getattr(self.state, "employees_changed", None), {"home", "business", "employee", "registration", "attendance", "payroll", "vehicle", "settings"}),
            (getattr(self.state, "attendance_changed", None), {"home", "attendance", "payroll"}),
            (getattr(self.state, "records_changed", None), {"home", "attendance", "payroll"}),
            (getattr(self.state, "settings_changed", None), {"home", "business", "registration", "attendance", "payroll", "vehicle", "settings"}),
            (getattr(self.state, "payroll_changed", None), {"payroll", "settings"}),
            (getattr(self.state, "vehicles_changed", None), {"home", "vehicle", "settings"}),
            (getattr(self.state, "holidays_changed", None), {"attendance", "payroll", "settings"}),
        )
        for signal, target_keys in signal_map:
            if signal is None:
                continue
            try:
                signal.connect(lambda *args, keys=set(target_keys): self._schedule_created_pages_refresh(keys))
            except Exception:
                continue

    def _schedule_created_pages_refresh(self, keys: set[str] | list[str] | tuple[str, ...] | None = None) -> None:
        if not hasattr(self, "_pending_created_page_refresh_keys"):
            return
        if keys is None:
            self._pending_created_page_refresh_keys.update(self.page_order)
        else:
            self._pending_created_page_refresh_keys.update(str(key) for key in keys if str(key or "").strip())
        if hasattr(self, "_created_page_refresh_timer"):
            self._created_page_refresh_timer.start()

    def _refresh_one_created_page_from_state(self, key: str, page: QWidget) -> None:
        if key == "employee" and hasattr(page, "refresh_table"):
            page.refresh_table()
            return
        if key == "registration":
            if hasattr(page, "_refresh_company_options"):
                page._refresh_company_options()
            elif hasattr(page, "refresh_from_state"):
                page.refresh_from_state()
            return
        if key == "payroll" and hasattr(page, "refresh"):
            page.refresh(False)
            return
        if key == "settings" and hasattr(page, "load_from_state"):
            page.load_from_state()
            return
        if hasattr(page, "refresh_from_state"):
            page.refresh_from_state()
            return
        if hasattr(page, "refresh"):
            page.refresh()

    def _refresh_created_pages_after_state_change(self) -> None:
        if not hasattr(self, "page_widgets"):
            return
        target_keys = set(getattr(self, "_pending_created_page_refresh_keys", set()) or set())
        self._pending_created_page_refresh_keys.clear()
        if not target_keys:
            return

        # 현재 작업 중인 화면은 각 페이지가 이미 직접 받은 신호로 갱신합니다.
        # 여기서는 숨겨진/캐시된 화면만 갱신해 편집 중인 셀·입력칸을 흔들지 않습니다.
        current_key = self._current_page_key()
        for key in self.page_order:
            if key == current_key or key not in target_keys:
                continue
            page = self.page_widgets.get(key)
            if page is None:
                continue
            try:
                page.setUpdatesEnabled(False)
                self._refresh_one_created_page_from_state(key, page)
                self._normalize_page_control_metrics(page)
            except Exception:
                continue
            finally:
                try:
                    page.setUpdatesEnabled(True)
                    page.update()
                except Exception:
                    pass
        self._refresh_sync_button_state()

    def _prewarm_pages_after_startup(self) -> None:
        if not hasattr(self, "pages"):
            return
        # 첫 클릭 때 무거운 페이지 생성이 보이지 않도록 홈 표시 후 순차로 준비한다.
        # 한 번에 만들지 않고 나누어 시작 체감 속도 저하를 줄인다.
        self._prewarm_page_queue = [key for key in self.page_order if key != "home" and key not in self.page_widgets]
        self._prewarm_next_page()

    def _prewarm_next_page(self) -> None:
        if not getattr(self, "_prewarm_page_queue", None):
            return
        key = self._prewarm_page_queue.pop(0)
        try:
            if key not in self.page_widgets:
                pages_widget = getattr(self, "pages", None)
                if pages_widget is not None:
                    pages_widget.setUpdatesEnabled(False)
                self._get_page(key)
        except Exception:
            pass
        finally:
            pages_widget = getattr(self, "pages", None)
            if pages_widget is not None:
                pages_widget.setUpdatesEnabled(True)
        if self._prewarm_page_queue:
            QTimer.singleShot(180, self._prewarm_next_page)

    def _create_page(self, key: str) -> QWidget:
        if key == "business":
            from .business_page import BusinessPage

            self.business_page = BusinessPage(self.state)
            return self.business_page
        if key == "employee":
            from .employee_page import EmployeePage

            self.employee_page = EmployeePage(self.state)
            self.employee_page.request_registration.connect(self.open_registration_page)
            self.employee_page.request_document_edit.connect(self.open_registration_page_for_employee_document_edit)
            return self.employee_page
        if key == "registration":
            from .registration_page import RegistrationPage

            self.registration_page = RegistrationPage(self.state)
            self.registration_page.request_back.connect(lambda: self.switch_page("employee"))
            return self.registration_page
        if key == "attendance":
            from .attendance_page import AttendancePage

            self.attendance_page = AttendancePage(self.state)
            self.attendance_page.request_settings.connect(self.open_score_settings_page)
            self.attendance_page.request_payroll.connect(lambda: self.switch_page("payroll"))
            return self.attendance_page
        if key == "payroll":
            from .payroll_page import PayrollPage

            self.payroll_page = PayrollPage(self.state)
            self.payroll_page.request_settings.connect(self.open_payroll_settings_page)
            return self.payroll_page
        if key == "vehicle":
            from .vehicle_page import VehiclePage

            self.vehicle_page = VehiclePage(self.state)
            self.vehicle_page.request_settings.connect(self.open_vehicle_settings_page)
            return self.vehicle_page
        if key == "settings":
            from .settings_page import SettingsPage

            self.settings_page = SettingsPage(self.state)
            if hasattr(self.settings_page, "tabs"):
                self.settings_page.tabs.currentChanged.connect(self._handle_settings_tab_changed)
            return self.settings_page
        return QWidget()

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("AppRoot")
        self._apply_page_background(central)
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        shell = QFrame()
        shell.setObjectName("Shell")

        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        root.addWidget(shell)

        sidebar = self._create_sidebar()
        shell_layout.addWidget(sidebar)

        content_wrap = QWidget()
        content_wrap.setObjectName("ContentWrap")
        self._apply_page_background(content_wrap)
        self.content_wrap = content_wrap
        content_layout = QVBoxLayout(content_wrap)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        shell_layout.addWidget(content_wrap, 1)

        self.topbar_stack = QStackedWidget()
        self.topbar_stack.setFixedHeight(62)
        self.topbar_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        topbar_specs = {
            "home": ("홈", "현재 인력 운영 현황을 한눈에 확인"),
            "business": ("사업자 관리", "우리 회사 사업자 운영 현황"),
            "employee": ("근로자 관리", "목록 / 상세 / 수정 / 퇴사 / 삭제"),
            "registration": ("근로자 등록", "문서 업로드 · 보정 · 등록"),
            "attendance": ("근태 관리", "이벤트 등록 · 점수 반영 · 이력 조회"),
            "payroll": ("급여 관리", "근태 연동 자동 계산 · 퇴직금 현황"),
            "vehicle": ("차량관리", "월 기준 조회 · 운행기록 · 주유기록 · 렌트카 경고 확인"),
            "settings": ("설정", "근태 점수 기준 / 회사별 급여 기준 / 차량 배치"),
        }
        self.page_banner_specs = {
            "home": (
                "",
                "전체 인력 현황",
                "전체 인력의 현재 상태를 요약하여 보여줍니다.",
            ),
            "business": (
                "사업자 운영",
                "사업자 · 근무 사업장 관리",
                "사업자와 근무 사업장을 새로 등록하고, 선택한 항목을 바로 수정하거나 삭제할 수 있습니다.",
            ),
            "employee": (
                "WORKER MANAGEMENT",
                "근로자 관리",
                "목록 중심으로 근로자 현황을 보고, 선택한 인원을 오른쪽에서 바로 확인합니다.",
            ),
            "registration": (
                "사원 등록",
                "사원등록 작업화면",
                "원본 등록 후 보정 시작, 4점 조절, 자동 보정, 보정 적용 순서로 바로 작업할 수 있게 정리했습니다.",
            ),
            "attendance": (
                "ATTENDANCE MANAGEMENT",
                "근태 관리",
                "월 단위로 조회하고 근태 상태를 바로 입력하며 급여관리와 연결합니다.",
            ),
            "payroll": (
                "PAYROLL MANAGEMENT",
                "급여 관리",
                "근태관리 값은 불러오기 초안으로만 사용하고, 급여표에서 날짜별 숫자를 직접 수정합니다.",
            ),
            "vehicle": (
                "VEHICLE MANAGEMENT",
                "차량관리",
                "차량 목록, 월간 운행기록, 주유내역, 렌트카 경고 상태를 한 화면에서 확인합니다.",
            ),
            "settings": (
                "설정",
                "설정 관리",
                "근태, 급여, 차량, 기타 사용 기준을 관리합니다.",
            ),
        }
        self.page_banner_images = {
            "home": self.resource_path("assets", "banners", "home_banner.png"),
            "business": self.resource_path("assets", "banners", "business_banner.png"),
            "employee": self.resource_path("assets", "banners", "employee_banner.png"),
            "registration": self.resource_path("assets", "banners", "registration_banner.png"),
            "attendance": self.resource_path("assets", "banners", "attendance_banner.png"),
            "payroll": self.resource_path("assets", "banners", "payroll_banner.png"),
            "vehicle": self.resource_path("assets", "banners", "vehicle_banner.png"),
            "settings": self.resource_path("assets", "banners", "settings_banner.png"),
        }
        # 배너 이미지를 첫 화면 표시 전에 읽어 시작 직후 빈 배너/늦은 로딩 느낌을 줄인다.
        PageBannerFrame.preload_images(self.page_banner_images.values())
        self.settings_banner_specs = {
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
            "차량관리 설정": (
                "차량관리 설정",
                "차량 등록과 렌트카 기준 관리",
                "차량 등록, 렌트카 계약 기준, 운전자, 주행거리 경고 기준을 이 화면에서 관리합니다.",
            ),
            "기타설정": (
                "설정",
                "기타설정",
                "자동저장, 백업, 서버 연결, 공휴일 자동갱신 기준을 관리합니다.",
            ),
        }
        for key in self.page_order:
            title, subtitle = topbar_specs[key]
            bar = make_topbar(title, subtitle)
            sync_btn = bar.findChild(QPushButton, "TopSyncButton")
            if sync_btn is not None:
                sync_btn.clicked.connect(self._handle_manual_sync)
            refresh_btn = bar.findChild(QPushButton, "TopRefreshButton")
            if refresh_btn is not None:
                refresh_btn.clicked.connect(self._handle_topbar_refresh)
            self.topbars[key] = bar
            self.topbar_stack.addWidget(bar)
        content_layout.addWidget(self.topbar_stack)

        self.fixed_page_banner = self._create_fixed_page_banner()
        content_layout.addWidget(self.fixed_page_banner)

        self.pages = QStackedWidget()
        self.pages.setObjectName("PageStack")
        self.pages.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._apply_page_background(self.pages)
        self.home_page = HomePage(self.state)
        self.home_page.navigate_employee.connect(lambda: self.switch_page("employee"))
        self.home_page.navigate_registration.connect(self.open_registration_page)
        self.home_page.navigate_attendance.connect(lambda: self.switch_page("attendance"))
        self.home_page.navigate_settings.connect(self.open_score_settings_page)

        self.page_widgets["home"] = self.home_page
        for key in self.page_order:
            host = self._create_page_host(key, self.home_page if key == "home" else None)
            if key in ("payroll", "attendance"):
                page_container = self._create_page_fixed_view(host, key)
            else:
                page_container = self._create_page_scroll(host, key)
            self.page_hosts[key] = host
            self.page_scrolls[key] = page_container
            self.pages.addWidget(page_container)

        content_layout.addWidget(self.pages, 1)

        # 저장·동기화 안내 문구는 하단이 아니라 상단바에 표시한다.
        # 하단 라벨이 나타났다 사라지면서 본문 높이가 바뀌어 화면이 흔들리는 문제를 방지한다.
        self.save_notice_label = QLabel("")
        self.save_notice_label.setVisible(False)

    def _create_fixed_page_banner(self):
        wrap = QWidget()
        wrap.setObjectName("FixedPageBannerWrap")
        wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        banner = PageBannerFrame()
        banner.setFixedHeight(108)
        banner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.fixed_page_banner_card = banner

        # 프리미엄 Drop Shadow 효과
        shadow = QGraphicsDropShadowEffect(banner)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(180, 200, 225, 75))
        banner.setGraphicsEffect(shadow)

        row = QHBoxLayout(banner)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(6)

        texts_wrap = QFrame()
        texts_wrap.setObjectName("BannerTextOverlay")
        texts_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        texts = QVBoxLayout(texts_wrap)
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(6)

        self.fixed_page_banner_badge = QLabel("")
        self.fixed_page_banner_badge.setObjectName("HeroBadge")
        self.fixed_page_banner_badge.setVisible(False)
        self.fixed_page_banner_badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        self.fixed_page_banner_title = QLabel("")
        self.fixed_page_banner_title.setObjectName("HeroTitle")
        
        self.fixed_page_banner_desc = QLabel("")
        self.fixed_page_banner_desc.setObjectName("HeroDesc")
        self.fixed_page_banner_desc.setWordWrap(True)
        self.fixed_page_banner_desc.setMaximumWidth(620)

        texts.addStretch(1)
        texts.addWidget(self.fixed_page_banner_badge, 0, Qt.AlignLeft)
        texts.addWidget(self.fixed_page_banner_title)
        texts.addWidget(self.fixed_page_banner_desc)
        texts.addStretch(2)
        row.addWidget(texts_wrap, 1)

        layout.addWidget(banner)
        return wrap

    def _current_settings_banner_spec(self):
        if not hasattr(self, "settings_page") or not hasattr(self.settings_page, "tabs"):
            return self.page_banner_specs.get("settings", ("설정", "설정 관리", "프로그램 사용 기준을 관리합니다."))
        index = self.settings_page.tabs.currentIndex()
        tab_text = self.settings_page.tabs.tabText(index) if index >= 0 else "설정"
        return self.settings_banner_specs.get(tab_text, self.page_banner_specs["settings"])

    def _update_fixed_page_banner(self, key: str):
        if not hasattr(self, "fixed_page_banner_title"):
            return
        if key == "settings":
            badge, title, desc = self._current_settings_banner_spec()
        else:
            badge, title, desc = self.page_banner_specs.get(
                key,
                ("WORKFORCE", "업무 화면", "선택한 메뉴의 작업 내용을 관리합니다."),
            )
        image_key = key if key in getattr(self, "page_banner_images", {}) else "home"
        image_path = self.page_banner_images.get(image_key, "")
        banner_state = (str(key), str(badge), str(title), str(desc), str(image_path))
        if self._last_banner_state == banner_state:
            return
        self._last_banner_state = banner_state

        badge_text = str(badge or "").strip()
        badge_visible = bool(badge_text)
        if self.fixed_page_banner_badge.isVisible() != badge_visible:
            self.fixed_page_banner_badge.setVisible(badge_visible)
        if self.fixed_page_banner_badge.text() != badge_text:
            self.fixed_page_banner_badge.setText(badge_text)
        if self.fixed_page_banner_title.text() != title:
            self.fixed_page_banner_title.setText(title)
        if self.fixed_page_banner_desc.text() != desc:
            self.fixed_page_banner_desc.setText(desc)
        if hasattr(self, "fixed_page_banner_card"):
            self.fixed_page_banner_card.set_theme(key)
            self.fixed_page_banner_card.set_background_image(image_path)

    def _handle_settings_tab_changed(self, _index: int):
        if hasattr(self, "pages") and self.page_order[self.pages.currentIndex()] == "settings":
            self._update_fixed_page_banner("settings")

    def _login_role_display(self) -> str:
        role_key = str(self.login_account.get("role") or "super_admin").strip().lower()
        if role_key in {"owner", "super", "super_admin", "admin", "최고관리자"}:
            return "최고관리자"
        return "일반관리자"

    def _create_sidebar(self):
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(210)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        brand = QFrame()
        brand.setObjectName("BrandBox")
        brand.setFixedHeight(82)
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(6, 6, 6, 6)
        brand_layout.setSpacing(6)

        logo_label = QLabel()
        logo_label.setObjectName("BrandLogo")
        logo_label.setFixedSize(50, 50)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_pixmap = QPixmap(self.resource_path("assets", "app_icon.png"))
        if logo_pixmap.isNull():
            logo_pixmap = QPixmap(self.resource_path("assets", "app_icon.ico"))
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand_layout.addWidget(logo_label)

        divider = QFrame()
        divider.setObjectName("BrandDivider")
        divider.setFixedWidth(1)
        divider.setFrameShape(QFrame.VLine)
        brand_layout.addWidget(divider)

        brand_text_wrap = QWidget()
        brand_text_wrap.setObjectName("BrandTextWrap")
        brand_text_layout = QVBoxLayout(brand_text_wrap)
        brand_text_layout.setContentsMargins(0, 0, 0, 0)
        brand_text_layout.setSpacing(6)
        for text, obj_name in [
            ("스마트 인력 관리", "BrandSmall"),
            ("인력365", "BrandMain"),
            ("WORKFORCE MANAGER", "BrandSub"),
        ]:
            label = QLabel(text)
            label.setObjectName(obj_name)
            label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            brand_text_layout.addWidget(label)
        brand_layout.addWidget(brand_text_wrap, 1)
        layout.addWidget(brand)

        login_name = str(self.login_account.get("employee_name") or self.login_account.get("username") or "최고관리자")
        login_role = self._login_role_display()
        login_label = QLabel(f"로그인: {login_name} · {login_role}")
        login_label.setObjectName("BrandSub")
        login_label.setWordWrap(True)
        layout.addWidget(login_label)
        layout.addSpacing(6)

        nav_items = [
            ("home", "홈", "home"),
            ("business", "사업자 관리", "business"),
            ("employee", "근로자 관리", "user"),
            ("registration", "근로자 등록", "registration"),
            ("attendance", "근태 관리", "attendance"),
            ("payroll", "급여 관리", "payroll"),
            ("vehicle", "차량 관리", "vehicle"),
            ("settings", "설정", "settings"),
        ]
        for key, label, icon_name in nav_items:
            button = SidebarButton(label, False, icon_name)
            button.clicked.connect(lambda checked=False, k=key: self.switch_page(k))
            self.nav_buttons[key] = button
            layout.addWidget(button)

        layout.addStretch()
        return side

    def _fit_initial_size_to_screen(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1280, 760)
            return

        available = screen.availableGeometry()
        width = min(1366, max(960, int(available.width() * 0.94)))
        height = min(820, max(640, int(available.height() * 0.90)))
        width = min(width, max(available.width() - 24, 800))
        height = min(height, max(available.height() - 24, 560))

        self.resize(width, height)
        self.move(
            available.x() + max(0, (available.width() - width) // 2),
            available.y() + max(0, (available.height() - height) // 2),
        )

    def _normalize_page_control_metrics(self, root: QWidget | None = None) -> None:
        """페이지별로 남아 있는 개별 높이값을 공통 기준으로 보정합니다.

        기준: 여백은 각 페이지 공통값 6을 사용하고, 입력칸/선택칸/날짜칸/숫자칸/일반 버튼 높이는 30으로 맞춥니다.
        큰 배너, 표, 사진, 메모창 같은 본문 영역은 건드리지 않습니다.
        """
        root_widget = root if root is not None else self
        if isinstance(root_widget, QScrollArea) and root_widget.widget() is not None:
            root_widget = root_widget.widget()

        field_types = (QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox)
        for field_type in field_types:
            for widget in root_widget.findChildren(field_type):
                try:
                    widget.setMinimumHeight(30)
                    widget.setMaximumHeight(30)

                    # 입력칸 내부 글자가 아래쪽으로 붙어 보이지 않도록 세로 가운데 정렬만 보정한다.
                    # 기존 좌/우/가운데 정렬 의도는 유지한다.
                    if isinstance(widget, (QLineEdit, QDateEdit, QSpinBox, QDoubleSpinBox)):
                        current_align = widget.alignment()
                        horizontal_align = current_align & Qt.AlignHorizontal_Mask
                        if not horizontal_align:
                            horizontal_align = Qt.AlignLeft
                        widget.setAlignment(horizontal_align | Qt.AlignVCenter)
                        if isinstance(widget, QLineEdit):
                            widget.setTextMargins(0, 0, 0, 0)

                    if isinstance(widget, QComboBox) and widget.isEditable() and widget.lineEdit() is not None:
                        widget.lineEdit().setMinimumHeight(24)
                        widget.lineEdit().setMaximumHeight(24)
                        widget.lineEdit().setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        widget.lineEdit().setTextMargins(0, 0, 0, 0)
                except Exception:
                    continue

        excluded_button_names = {"NavButton", "PersonalToggleButton", "SyncButton"}
        for button in root_widget.findChildren(QPushButton):
            try:
                name = str(button.objectName() or "")
                if name in excluded_button_names:
                    continue
                button.setMinimumHeight(30)
                button.setMaximumHeight(30)
            except Exception:
                continue


    def _create_page_fixed_view(self, page: QWidget, key: str = "") -> QWidget:
        # 급여관리는 외부 QScrollArea를 사용하지 않는다.
        # 전체 화면은 현재 창 안에 고정하고, 움직임은 급여표 내부 스크롤과 우측 상세 내부 스크롤에만 맡긴다.
        page.setMinimumWidth(0)
        page.setMaximumWidth(16777215)
        page.setProperty("fixedViewportPage", True)
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._apply_page_background(page)

        wrapper = QFrame()
        wrapper.setObjectName(f"PageFixedViewport_{key}")
        wrapper.setMinimumWidth(0)
        wrapper.setMaximumWidth(16777215)
        wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        wrapper.setFrameShape(QFrame.NoFrame)
        wrapper.setProperty("fixedViewportPage", True)
        self._apply_page_background(wrapper)

        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(page)
        return wrapper

    def _create_page_scroll(self, page: QWidget, key: str = "") -> QScrollArea:
        # 왼쪽 메뉴와 상단바는 고정하고, 본문 작업영역만 필요 시 X/Y 스크롤로 처리한다.
        # 페이지 host는 처음부터 고정해 두어 메뉴 클릭 중 QStackedWidget 구조가 바뀌지 않게 한다.
        if key == "payroll" or page.objectName() == "PageHost_payroll":
            # 급여관리는 전체 페이지 폭을 창 안에 유지하고, 가로 이동은 급여표 내부 스크롤만 사용한다.
            page.setMinimumWidth(0)
            page.setProperty("disableOuterHorizontalScroll", True)
        else:
            page.setMinimumWidth(max(page.minimumWidth(), 1120))
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._apply_page_background(page)

        scroll = QScrollArea()
        scroll.setObjectName("PageScrollArea")
        scroll.setWidget(page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        disable_outer_horizontal = (
            key in ("payroll", "attendance")
            or page.objectName() in ("PageHost_payroll", "PageHost_attendance")
            or bool(page.property("disableOuterHorizontalScroll"))
        )
        if disable_outer_horizontal:
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        disable_outer_vertical = (
            key in ("payroll", "attendance")
            or page.objectName() in ("PageHost_payroll", "PageHost_attendance")
            or bool(page.property("disableOuterVerticalScroll"))
        )
        if disable_outer_vertical:
            # 급여관리처럼 내부 표/상세 패널이 자체 스크롤을 갖는 화면은
            # 바깥 PageScrollArea의 세로 스크롤을 확실히 끄어 우측 이중 스크롤을 막는다.
            # pc_53에서는 PayrollPage 속성만 보고 있어 PageHost_payroll 단계에서 적용되지 않았다.
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._apply_page_background(scroll)
        viewport = scroll.viewport()
        viewport.setObjectName("PageScrollViewport")
        viewport.setAutoFillBackground(True)
        palette = viewport.palette()
        color = QColor(PAGE_BACKGROUND_COLOR)
        palette.setColor(QPalette.Window, color)
        palette.setColor(QPalette.Base, color)
        viewport.setPalette(palette)
        scroll.setStyleSheet(
            "QScrollArea#PageScrollArea { background: #F4F7FB; border: none; }"
            "QWidget#PageScrollViewport { background: #F4F7FB; }"
        )
        return scroll

    def _refresh_topbar_meta(self, *, running: bool = False, pending: bool = False):
        for bar in self.topbars.values():
            date_label = bar.findChild(QLabel, "TopDateLabel")
            if date_label is not None:
                date_label.setText(format_korean_top_date())

            sync_btn = bar.findChild(QPushButton, "TopSyncButton")
            if sync_btn is not None:
                if running:
                    sync_btn.setText("🟢 동기화 중")
                    sync_btn.setEnabled(False)
                else:
                    sync_btn.setText("🔴 수동 동기화")
                    sync_btn.setEnabled(True)

    def _handle_topbar_refresh(self):
        current_page = self._current_content_page()
        try:
            if hasattr(current_page, "refresh_from_state"):
                current_page.refresh_from_state()
            self._refresh_topbar_meta()
            self._refresh_sync_button_state()
            self._show_save_notice("화면 새로고침")
        except Exception as error:
            QMessageBox.warning(self, "새로고침", f"화면 새로고침 중 문제가 발생했습니다.\n{error}")

    def _handle_server_snapshot_save(self):
        running = bool(getattr(self.state, "is_server_sync_running", lambda: False)())
        manual_running = bool(getattr(self.state, "is_manual_server_sync_running", lambda: False)())
        if running or manual_running or getattr(self, "_manual_sync_ui_locked", False):
            self._show_save_notice("동기화가 아직 진행 중입니다")
            self._refresh_sync_button_state()
            return
        self._manual_sync_ui_locked = True
        self._refresh_topbar_meta(running=True)
        self._show_save_notice("서버 전체 저장 시작")
        QTimer.singleShot(0, self._start_server_snapshot_save_now)

    def _start_server_snapshot_save_now(self):
        try:
            started = bool(getattr(self.state, "push_server_snapshot_now", lambda: False)())
        except Exception as error:
            self._manual_sync_ui_locked = False
            QMessageBox.warning(self, "서버저장", f"서버 전체 저장 중 문제가 발생했습니다.\n{error}")
            self._refresh_sync_button_state()
            return
        if not started:
            self._manual_sync_ui_locked = False
        self._refresh_sync_button_state()

    def _handle_server_snapshot_load(self):
        running = bool(getattr(self.state, "is_server_sync_running", lambda: False)())
        manual_running = bool(getattr(self.state, "is_manual_server_sync_running", lambda: False)())
        if running or manual_running or getattr(self, "_manual_sync_ui_locked", False):
            self._show_save_notice("동기화가 아직 진행 중입니다")
            self._refresh_sync_button_state()
            return
        self._manual_sync_ui_locked = True
        self._refresh_topbar_meta(running=True)
        self._show_save_notice("서버 전체 자료 불러오기 시작")
        QTimer.singleShot(0, self._start_server_snapshot_load_now)

    def _start_server_snapshot_load_now(self):
        try:
            started = bool(getattr(self.state, "pull_server_snapshot_now", lambda: False)())
        except Exception as error:
            self._manual_sync_ui_locked = False
            QMessageBox.warning(self, "서버불러오기", f"서버 전체 불러오기 중 문제가 발생했습니다.\n{error}")
            self._refresh_sync_button_state()
            return
        if not started:
            self._manual_sync_ui_locked = False
        self._refresh_sync_button_state()

    def _handle_manual_sync(self):
        running = bool(getattr(self.state, "is_server_sync_running", lambda: False)())
        manual_running = bool(getattr(self.state, "is_manual_server_sync_running", lambda: False)())
        if running or manual_running or getattr(self, "_manual_sync_ui_locked", False):
            self._show_save_notice("동기화가 아직 진행 중입니다")
            self._refresh_sync_button_state()
            return

        self._manual_sync_ui_locked = True
        if hasattr(self, "sync_button"):
            self.sync_button.setEnabled(False)
            self.sync_button.setText("동기화 중")
        if hasattr(self, "sync_state_label"):
            self.sync_state_label.setText("전체 데이터 동기화 중")
        if hasattr(self, "sync_hint_label"):
            self.sync_hint_label.setText("서버 동기화 완료까지 기다려 주세요")
        self._refresh_topbar_meta(running=True)
        self._show_save_notice("전체 동기화 시작")
        QTimer.singleShot(0, self._start_manual_sync_now)

    def _start_manual_sync_now(self):
        try:
            started = bool(self.state.sync_employees_now())
        except Exception as error:
            self._manual_sync_ui_locked = False
            QMessageBox.warning(self, "동기화", f"동기화 중 문제가 발생했습니다.\\n{error}")
            self._refresh_sync_button_state()
            return
        if not started:
            self._manual_sync_ui_locked = False
        self._refresh_sync_button_state()

    def _trigger_auto_sync(self):
        return

    @staticmethod
    def _compact_path(path_text: str, keep_segments: int = 3) -> str:
        text = str(path_text or "").strip()
        if not text:
            return ""
        normalized = text.replace("/", "\\")
        parts = [part for part in normalized.split("\\") if part]
        if len(parts) <= keep_segments:
            return normalized
        return "...\\" + "\\".join(parts[-keep_segments:])

    def _refresh_sync_button_state(self):
        pending_count = int(getattr(self.state, "pending_employee_sync_count", lambda: 0)())
        failed_count = int(getattr(self.state, "failed_employee_sync_count", lambda: 0)())
        running = bool(getattr(self.state, "is_server_sync_running", lambda: False)())
        manual_running = bool(getattr(self.state, "is_manual_server_sync_running", lambda: False)())

        if hasattr(self, "sync_button"):
            any_running = bool(manual_running or running or getattr(self, "_manual_sync_ui_locked", False))
            self.sync_button.setText("동기화 중" if any_running else "수동 동기화")
            self.sync_button.setEnabled(not any_running)

            if any_running:
                self.sync_state_label.setText("전체 데이터 동기화 중")
                self.sync_hint_label.setText("서버 동기화 완료까지 기다려 주세요")
            elif pending_count > 0:
                self.sync_state_label.setText(f"전송 대기 {pending_count}건")
                self.sync_hint_label.setText("클릭하면 대기 자료 다시 전송")
            elif failed_count > 0:
                self.sync_state_label.setText(f"전송 실패 {failed_count}건")
                self.sync_hint_label.setText("실패 자료는 PC 목록에 유지")
            elif running:
                self.sync_state_label.setText("서버 전체 상태 확인 중")
                self.sync_hint_label.setText("PC 자료 덮어쓰기 보호 중")
            else:
                self.sync_state_label.setText("수동 동기화 대기")
                self.sync_hint_label.setText("클릭하면 서버 저장/불러오기를 자동 판단")

            last_sync = str(getattr(self.state, "last_employee_sync_at", lambda: "")() or "").strip()
            sync_status = str(getattr(self.state, "last_employee_sync_status", lambda: "")() or "").strip()
            sync_error = str(getattr(self.state, "last_employee_sync_error", lambda: "")() or "").strip()
            if hasattr(self, "sync_meta_label"):
                last_text = last_sync if last_sync else "없음"
                status_text = sync_status if sync_status else "대기"
                self.sync_meta_label.setText(f"최근: {last_text}\n대기 {pending_count} · 실패 {failed_count}")
            if hasattr(self, "sync_error_label"):
                has_error = bool(sync_error)
                self.sync_error_label.setVisible(has_error)
                self.sync_error_label.setText(f"실패: {sync_error}" if has_error else "")
            if hasattr(self, "data_location_label"):
                data_root = str(getattr(self.state, "data_root_path", "") or "")
                db_path = str(getattr(self.state, "database_path", "") or "")
                display_root = Path(data_root).name if data_root else "WorkforceData"
                display_db = Path(db_path).name if db_path else "workforce.db"
                self.data_location_label.setText(f"저장: {display_root} · DB: {display_db}")
                tooltip = "\n".join(part for part in [data_root, db_path] if part)
                self.data_location_label.setToolTip(tooltip or display_db)

        if getattr(self, "_manual_sync_ui_locked", False) and not manual_running and not running:
            self._manual_sync_ui_locked = False
            if hasattr(self, "sync_button"):
                self.sync_button.setEnabled(True)
                self.sync_button.setText("수동 동기화")

        self._refresh_topbar_meta(
            running=manual_running or running or getattr(self, "_manual_sync_ui_locked", False),
            pending=pending_count > 0 or failed_count > 0,
        )

    def _handle_save_completed(self, reason: str):
        reason = str(reason or "").strip()
        if reason == "auto-save":
            self._show_save_notice("자동저장됨")
        elif reason in {"manual-save", "manual"}:
            self._show_save_notice("저장됨")
        # 저장 완료 시점에도 한 번 더 묶음 갱신을 예약해
        # 등록/수정/삭제 후 숨겨진 화면 목록이 늦게 따라오는 상황을 줄입니다.
        self._schedule_created_pages_refresh(set(self.page_order))

    def _handle_server_sync_status(self, message: str):
        text = str(message or "").strip()
        if text and any(marker in text for marker in ("실패", "오류", "지연")):
            self._show_save_notice(text)
        if text and any(marker in text for marker in ("완료", "반영", "확인", "변경 없음", "동기화")):
            self._schedule_created_pages_refresh(set(self.page_order))
        self._refresh_sync_button_state()
        QTimer.singleShot(120, self._refresh_sync_button_state)

    def _show_save_notice(self, message: str):
        text = str(message or "").strip()
        if hasattr(self, "save_notice_label"):
            self.save_notice_label.setText(text)
            self.save_notice_label.setVisible(False)

        for bar in self.topbars.values():
            notice = bar.findChild(QLabel, "TopNoticeLabel")
            if notice is not None:
                notice.setText(text)
                notice.setVisible(bool(text))

        self._save_notice_timer.start(2200)

    def _hide_save_notice(self):
        if hasattr(self, "save_notice_label"):
            self.save_notice_label.setVisible(False)
            self.save_notice_label.setText("")

        for bar in self.topbars.values():
            notice = bar.findChild(QLabel, "TopNoticeLabel")
            if notice is not None:
                notice.setVisible(False)
                notice.setText("")

    def _check_updates_on_startup(self):
        try:
            from .update_manager import UpdateManager

            manager = UpdateManager(self.state.get_storage_manager())
            manager.check_and_prompt(self)
        except Exception:
            return

    def open_registration_page(self):
        registration_page = self._get_page("registration")
        if registration_page is None:
            return
        self.registration_page.prepare_new_employee(self.state.next_employee_id())
        self.switch_page("registration")

    def open_registration_page_for_employee_document_edit(self, employee_id: int):
        registration_page = self._get_page("registration")
        if registration_page is None:
            return
        employee = self.state.get_employee_by_id(employee_id) if hasattr(self.state, "get_employee_by_id") else None
        if not employee:
            QMessageBox.warning(self, "사진/문서 수정", "수정할 근로자를 찾을 수 없습니다.")
            return
        if hasattr(self.registration_page, "prepare_employee_document_edit"):
            self.registration_page.prepare_employee_document_edit(employee)
            self.switch_page("registration")
        else:
            QMessageBox.warning(self, "사진/문서 수정", "사진/문서 수정 화면을 열 수 없습니다.")

    def open_settings_tab(self, tab_name: str):
        self.switch_page("settings")
        if hasattr(self.settings_page, "select_settings_tab"):
            self.settings_page.select_settings_tab(tab_name)
        self._update_fixed_page_banner("settings")
        current_widget = self.pages.currentWidget()
        if isinstance(current_widget, QScrollArea):
            current_widget.verticalScrollBar().setValue(0)

    def open_score_settings_page(self):
        self.open_settings_tab("근태 점수 기준")

    def open_payroll_settings_page(self):
        self.open_settings_tab("현장별 급여 기준")

    def open_payroll_item_settings_page(self):
        self.open_settings_tab("현장별 급여 항목")

    def open_vehicle_settings_page(self):
        self.open_settings_tab("차량관리 설정")

    def closeEvent(self, event: QCloseEvent):
        try:
            self.state.prepare_for_exit()
        except Exception as error:
            QMessageBox.warning(self, "종료", f"종료 전 저장 중 문제가 발생했습니다.\n{error}")
            event.ignore()
            return
        super().closeEvent(event)

    def _set_nav_checked(self, active_key: str) -> None:
        for name, button in self.nav_buttons.items():
            target = name == active_key
            if button.isChecked() == target:
                continue
            button.setChecked(target)

    def _settle_page_after_switch(self, key: str) -> None:
        if not hasattr(self, "pages"):
            return
        index = self.page_order.index(key) if key in self.page_order else -1
        if index < 0 or self.pages.currentIndex() != index:
            return
        if key == "home":
            self._prepare_initial_home_layout()
        current = self.pages.currentWidget()
        if current is not None:
            self._normalize_page_control_metrics(current)
        if hasattr(self, "fixed_page_banner_card"):
            self.fixed_page_banner_card.update()

    def switch_page(self, key: str, force_refresh: bool = False):
        if key not in self.page_order:
            return

        page_index = self.page_order.index(key)
        same_page = hasattr(self, "pages") and self.pages.currentIndex() == page_index

        if same_page and not force_refresh:
            update_root = getattr(self, "content_wrap", self)
            try:
                update_root.setUpdatesEnabled(False)
                if self.topbar_stack.currentIndex() != page_index:
                    self.topbar_stack.setCurrentIndex(page_index)
                self._update_fixed_page_banner(key)
                self._set_nav_checked(key)
            finally:
                update_root.setUpdatesEnabled(True)
                update_root.update()
            return

        update_root = getattr(self, "content_wrap", self)
        previous_key = self._active_page_key
        try:
            update_root.setUpdatesEnabled(False)
            page = self._get_page(key)
            if page is None:
                return
            try:
                page.setAutoFillBackground(True)
                page.setAttribute(Qt.WA_StyledBackground, True)
            except Exception:
                pass

            self._active_page_key = key
            self.setProperty("pageSwitching", True)
            if not same_page and self.pages.currentIndex() != page_index:
                self.pages.setCurrentIndex(page_index)
            if self.topbar_stack.currentIndex() != page_index:
                self.topbar_stack.setCurrentIndex(page_index)
            self._update_fixed_page_banner(key)
            self._set_nav_checked(key)
            is_settings = key == "settings"
            self.save_notice_label.setVisible(False if is_settings else self.save_notice_label.isVisible())
        finally:
            self.setProperty("pageSwitching", False)
            update_root.setUpdatesEnabled(True)
            update_root.update()

        if previous_key != key or force_refresh:
            QTimer.singleShot(80, lambda k=key: self._settle_page_after_switch(k))

    def _apply_calendar_theme(self, root: QWidget | None = None):
        root_widget = root if root is not None else self
        for edit in root_widget.findChildren(QDateEdit):
            if bool(edit.property("calendarThemeApplied")):
                continue
            style_date_edit_calendar(edit)
            edit.setProperty("calendarThemeApplied", True)
