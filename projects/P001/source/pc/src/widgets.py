from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal, QRectF, QDate, QPointF
from PySide6.QtGui import QColor, QFont, QIcon, QPalette, QPainter, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import QCalendarWidget, QDateEdit, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget, QSizePolicy
from .icons import get_qicon, get_svg_icon, get_sidebar_menu_icon
from .app_metadata import PROGRAM_VERSION


KOREAN_WEEKDAYS = {
    1: "월",
    2: "화",
    3: "수",
    4: "목",
    5: "금",
    6: "토",
    7: "일",
}

def format_korean_top_date(date: QDate | None = None) -> str:
    """상단 날짜를 2026-05-12 (화) 형식으로 표시합니다."""
    current = date if isinstance(date, QDate) and date.isValid() else QDate.currentDate()
    weekday = KOREAN_WEEKDAYS.get(current.dayOfWeek(), "")
    return f"{current.toString('yyyy-MM-dd')} ({weekday})"

# 공통 페이지 여백 기준
PAGE_OUTER_MARGINS = (6, 6, 6, 6)
PAGE_OUTER_SPACING = 6
PAGE_INNER_MARGINS = (6, 6, 6, 6)
PAGE_INNER_SPACING = 6

STATUS_BADGES = {
    "근무중": ("#ECFDF5", "#10B981"),
    "출근전": ("#FFFBEB", "#F59E0B"),
    "퇴근": ("#F9FAFB", "#6B7280"),
    "지각": ("#FFFBEB", "#F59E0B"),
    "병원": ("#F5F3FF", "#8B5CF6"),
    "결근": ("#FEF2F2", "#EF4444"),
    "무단결근": ("#FFF1F2", "#E11D48"),
    "무단이탈": ("#FFF7ED", "#F97316"),
    "휴무": ("#F9FAFB", "#6B7280"),
    "퇴사": ("#FEF2F2", "#EF4444"),
}

GRADE_BADGES = {
    "양호": ("#ECFDF3", "#027A48"),
    "주의": ("#FFF7E8", "#B54708"),
    "재검토": ("#FFF6ED", "#C4320A"),
    "비추천": ("#FFF1F3", "#C01048"),
}


CALENDAR_POPUP_STYLES = """
QCalendarWidget {
    background: #FFFFFF;
    color: #292524;
    border: 1px solid #D6D3D1;
    border-radius: 12px;
}
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background: #FFFFFF;
    color: #292524;
    border-bottom: 1px solid #E7E5E4;
    padding: 6px;
}
QCalendarWidget QToolButton {
    color: #292524;
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px;
    font-weight: 800;
}
QCalendarWidget QToolButton:hover {
    background: #F5F5F4;
}
QCalendarWidget QMenu {
    background: #FFFFFF;
    color: #292524;
    border: 1px solid #D6D3D1;
}
QCalendarWidget QSpinBox {
    background: #FFFFFF;
    color: #292524;
    border: 1px solid #D6D3D1;
    border-radius: 4px;
    padding: 6px 6px;
}
QCalendarWidget QAbstractItemView,
QCalendarWidget QTableView,
QCalendarWidget QTableWidget {
    background: #FFFFFF;
    alternate-background-color: #FFFFFF;
    color: #292524;
    selection-background-color: #DBEAFE;
    selection-color: #1D4ED8;
    outline: 0;
    border: none;
    gridline-color: #E7E5E4;
}
QCalendarWidget QAbstractItemView:enabled,
QCalendarWidget QTableView:enabled,
QCalendarWidget QTableWidget:enabled {
    background: #FFFFFF;
    color: #292524;
}
QCalendarWidget QAbstractItemView:disabled,
QCalendarWidget QTableView:disabled,
QCalendarWidget QTableWidget:disabled {
    background: #FFFFFF;
    color: #A8A29E;
}
"""


def style_date_edit_calendar(edit: QDateEdit | None) -> None:
    if edit is None:
        return
    try:
        edit.setCalendarPopup(True)
        calendar = edit.calendarWidget()
        if calendar is None:
            calendar = QCalendarWidget(edit)
            edit.setCalendarWidget(calendar)
        calendar.setAutoFillBackground(True)
        palette = calendar.palette()
        palette.setColor(QPalette.Window, QColor('#FFFFFF'))
        palette.setColor(QPalette.Base, QColor('#FFFFFF'))
        palette.setColor(QPalette.AlternateBase, QColor('#FFFFFF'))
        palette.setColor(QPalette.Button, QColor('#FFFFFF'))
        palette.setColor(QPalette.ButtonText, QColor('#292524'))
        palette.setColor(QPalette.Text, QColor('#292524'))
        palette.setColor(QPalette.WindowText, QColor('#292524'))
        palette.setColor(QPalette.Highlight, QColor('#DBEAFE'))
        palette.setColor(QPalette.HighlightedText, QColor('#1D4ED8'))
        calendar.setPalette(palette)
        calendar.setStyleSheet(CALENDAR_POPUP_STYLES)
        view = calendar.findChild(QWidget, 'qt_calendar_calendarview')
        if view is not None:
            view.setAutoFillBackground(True)
            view.setPalette(palette)
            view.setStyleSheet('background:#FFFFFF; color:#292524; selection-background-color:#DBEAFE; selection-color:#1D4ED8;')
    except Exception:
        pass


class SidebarButton(QPushButton):
    def __init__(self, text: str, active: bool = False, icon_name: str = "home"):
        super().__init__(text)
        self.icon_name = icon_name
        self.setObjectName("NavButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setChecked(active)
        self.setMinimumHeight(48)
        self.setIconSize(QSize(26, 26))
        self._refresh_icon()

    def setChecked(self, checked: bool):
        checked = bool(checked)
        if self.isChecked() == checked:
            return
        super().setChecked(checked)
        self._refresh_icon()

    def _refresh_icon(self):
        self.setIcon(get_sidebar_menu_icon(self.icon_name, self.isChecked(), 28))


class Panel(QFrame):
    def __init__(self, title: str, subtitle: str, icon_name: str | None = None):
        super().__init__()
        self.setObjectName("Panel")
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(0)

        self.header = PanelHeader(title, subtitle, icon_name=icon_name)
        
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#edf2f7;")

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(6, 6, 6, 6)
        self.body_layout.setSpacing(6)

        self.root.addWidget(self.header)
        self.root.addWidget(line)
        self.root.addWidget(self.body)


class BannerIllustration(QWidget):
    """상단 배너나 홈 요약영역에서 쓰는 가벼운 장식 일러스트"""

    def __init__(self, compact: bool = False):
        super().__init__()
        self.compact = compact
        self.setAttribute(Qt.WA_TranslucentBackground)
        if compact:
            self.setMinimumSize(128, 56)
            self.setMaximumHeight(64)
        else:
            self.setMinimumSize(180, 76)
            self.setMaximumHeight(88)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        w = float(rect.width())
        h = float(rect.height())
        left = float(rect.left())
        top = float(rect.top())

        def cx(v: float) -> float:
            return left + w * v

        def cy(v: float) -> float:
            return top + h * v

        # 배경 원형 포인트
        for x, y, r, alpha in [
            (0.14, 0.28, 0.14, 46),
            (0.60, 0.22, 0.11, 34),
            (0.82, 0.65, 0.16, 42),
        ]:
            c = QColor('#D9E8FF')
            c.setAlpha(alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(c))
            p.drawEllipse(QRectF(cx(x) - w * r / 2, cy(y) - h * r / 2, w * r, w * r))

        # 바닥선
        grid_pen = QPen(QColor('#DCE9FA'), 1.4)
        p.setPen(grid_pen)
        p.drawLine(cx(0.08), cy(0.82), cx(0.94), cy(0.82))

        # 왼쪽 그래프 카드
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#EEF4FF'))
        p.drawRoundedRect(QRectF(cx(0.06), cy(0.30), w * 0.22, h * 0.40), 10, 10)
        p.setBrush(QColor('#BFD7FF'))
        p.drawRoundedRect(QRectF(cx(0.10), cy(0.55), w * 0.03, h * 0.10), 3, 3)
        p.drawRoundedRect(QRectF(cx(0.15), cy(0.48), w * 0.03, h * 0.17), 3, 3)
        p.drawRoundedRect(QRectF(cx(0.20), cy(0.41), w * 0.03, h * 0.24), 3, 3)
        line_pen = QPen(QColor('#5B87E8'), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(line_pen)
        path = QPainterPath()
        path.moveTo(cx(0.10), cy(0.46))
        path.lineTo(cx(0.155), cy(0.41))
        path.lineTo(cx(0.21), cy(0.35))
        path.lineTo(cx(0.245), cy(0.29))
        p.drawPath(path)

        # 중앙 직원 캐릭터
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#CFE0FF'))
        p.drawRoundedRect(QRectF(cx(0.36), cy(0.40), w * 0.14, h * 0.28), 14, 14)
        p.setBrush(QColor('#8FB3F4'))
        p.drawEllipse(QRectF(cx(0.40), cy(0.23), w * 0.10, h * 0.18))
        p.setBrush(QColor('#4F7FE6'))
        p.drawRoundedRect(QRectF(cx(0.39), cy(0.22), w * 0.12, h * 0.07), 8, 8)
        p.drawRoundedRect(QRectF(cx(0.41), cy(0.18), w * 0.08, h * 0.04), 6, 6)
        p.setBrush(QColor('#5B87E8'))
        p.drawRoundedRect(QRectF(cx(0.385), cy(0.50), w * 0.09, h * 0.10), 8, 8)

        # 오른쪽 체크보드/작업 카드
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#EEF4FF'))
        p.drawRoundedRect(QRectF(cx(0.60), cy(0.24), w * 0.28, h * 0.46), 12, 12)
        board_pen = QPen(QColor('#9FC0F1'), 1.4)
        p.setPen(board_pen)
        p.drawRoundedRect(QRectF(cx(0.60), cy(0.24), w * 0.28, h * 0.46), 12, 12)
        p.setBrush(QColor('#5B87E8'))
        p.drawRoundedRect(QRectF(cx(0.64), cy(0.36), w * 0.03, h * 0.03), 3, 3)
        p.drawRoundedRect(QRectF(cx(0.64), cy(0.48), w * 0.03, h * 0.03), 3, 3)
        p.drawRoundedRect(QRectF(cx(0.64), cy(0.60), w * 0.03, h * 0.03), 3, 3)
        text_pen = QPen(QColor('#93A9CD'), 2.0, Qt.SolidLine, Qt.RoundCap)
        p.setPen(text_pen)
        p.drawLine(cx(0.69), cy(0.375), cx(0.83), cy(0.375))
        p.drawLine(cx(0.69), cy(0.495), cx(0.82), cy(0.495))
        p.drawLine(cx(0.69), cy(0.615), cx(0.78), cy(0.615))

        # 체크 표시
        p.setPen(QPen(QColor('#22C55E'), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        tick = QPainterPath()
        tick.moveTo(cx(0.86), cy(0.30))
        tick.lineTo(cx(0.89), cy(0.34))
        tick.lineTo(cx(0.94), cy(0.25))
        p.drawPath(tick)

        # 하단 연결 포인트
        p.setPen(QPen(QColor('#B7C9EA'), 1.2, Qt.DashLine, Qt.RoundCap))
        p.drawLine(cx(0.28), cy(0.82), cx(0.88), cy(0.82))
        for x in [0.28, 0.50, 0.74, 0.88]:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#BFD4F7'))
            p.drawEllipse(QRectF(cx(x) - 2.5, cy(0.82) - 2.5, 5, 5))

        p.end()


class InnerScrollFrame(QFrame):
    """고정 테두리 박스 안쪽에서만 내용이 스크롤되도록 감싸는 공통 프레임입니다."""

    def __init__(
        self,
        content: QWidget,
        *,
        margins: tuple[int, int, int, int] = (6, 6, 6, 6),
        min_content_height: int = 0,
        vertical_policy: Qt.ScrollBarPolicy = Qt.ScrollBarAsNeeded,
        horizontal_policy: Qt.ScrollBarPolicy = Qt.ScrollBarAlwaysOff,
    ):
        super().__init__()
        self.setObjectName("InnerScrollFrame")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*margins)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("InnerScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(horizontal_policy)
        self.scroll_area.setVerticalScrollBarPolicy(vertical_policy)
        self.scroll_area.viewport().setAutoFillBackground(False)

        if min_content_height > 0:
            content.setMinimumHeight(min_content_height)
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.scroll_area.setWidget(content)
        layout.addWidget(self.scroll_area, 1)


class StatCard(QFrame):
    clicked = Signal(str)

    def __init__(
        self,
        key: str,
        value: str,
        subtitle: str,
        accent_color: str,
        icon_name: str,
        filter_key: str | None = None,
        *,
        show_subtitle: bool = True,
        icon_background: bool = True,
        icon_size: int = 18,
        variant: str = "default",
    ):
        super().__init__()
        self.key = key
        self.filter_key = filter_key
        self.accent_color = accent_color
        self.icon_name = icon_name
        self.is_active = False
        self.variant = str(variant or "default")
        self._button_variants = {"home_summary", "employee_summary"}

        self.setObjectName("StatCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("active", False)
        self.setProperty("pressed", False)
        self.setProperty("variant", self.variant)
        self.setMouseTracking(True)
        if self.variant in self._button_variants:
            self._set_button_shadow("normal")

        layout = QVBoxLayout(self)
        if self.variant == "home_summary":
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(6)
            self.setMinimumHeight(96)
        else:
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.title_lbl = QLabel(key)
        self.title_lbl.setObjectName("HomeFilterCardTitle" if self.variant == "home_summary" else "StatTitle")
        header.addWidget(self.title_lbl)
        header.addStretch()

        icon_box_size = icon_size + 2 if self.variant == "home_summary" else max(28, icon_size + 12)
        self.icon_lbl = QLabel()
        self.icon_lbl.setObjectName("HomeFilterCardIcon" if self.variant == "home_summary" else "")
        self.icon_lbl.setFixedSize(icon_box_size, icon_box_size)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setPixmap(get_svg_icon(icon_name, accent_color, icon_size))
        if self.variant == "home_summary":
            self.icon_lbl.setStyleSheet("background: transparent; border: 0px; border-radius: 0px; padding: 0px; margin: 0px;")
        elif icon_background:
            radius = icon_box_size // 2
            self.icon_lbl.setStyleSheet(
                f"background: {accent_color}18; border: 1px solid {accent_color}2d; border-radius: {radius}px;"
            )
        else:
            self.icon_lbl.setStyleSheet("background: transparent; border: none;")
        header.addWidget(self.icon_lbl)
        layout.addLayout(header)

        self.value_lbl = QLabel(value)
        self.value_lbl.setObjectName("HomeFilterCardValue" if self.variant == "home_summary" else "StatValue")
        layout.addWidget(self.value_lbl)

        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setObjectName("HomeFilterCardSub" if self.variant == "home_summary" else "StatSub")
        self.sub_lbl.setVisible(show_subtitle and bool(subtitle))
        if self.sub_lbl.isVisible():
            layout.addWidget(self.sub_lbl)

    def set_value(self, value: str):
        self.value_lbl.setText(value)

    def _refresh_card_style(self):
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def _set_button_shadow(self, state: str):
        if self.variant not in self._button_variants:
            return
        effect = self.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            effect = QGraphicsDropShadowEffect(self)
            self.setGraphicsEffect(effect)
        settings = {
            "normal": (9, 0, 2, 24),
            "hover": (12, 0, 2, 34),
            "active": (10, 0, 2, 38),
            "pressed": (4, 0, 1, 18),
        }.get(state, (9, 0, 2, 24))
        blur, x_offset, y_offset, alpha = settings
        effect.setBlurRadius(blur)
        effect.setOffset(x_offset, y_offset)
        effect.setColor(QColor(15, 23, 42, alpha))

    def set_active(self, active: bool):
        active = bool(active)
        if self.is_active == active and self.property("active") == active:
            return
        self.is_active = active
        self.setProperty("active", active)
        self._refresh_card_style()
        self._set_button_shadow("active" if active else "normal")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setProperty("pressed", True)
            self._refresh_card_style()
            self._set_button_shadow("pressed")
            self.clicked.emit(self.key)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.property("pressed"):
            self.setProperty("pressed", False)
            self._refresh_card_style()
        state = "hover" if self.rect().contains(event.position().toPoint()) else "active" if self.is_active else "normal"
        self._set_button_shadow(state)
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        if not self.property("pressed"):
            self._set_button_shadow("hover")
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.property("pressed"):
            self.setProperty("pressed", False)
            self._refresh_card_style()
        self._set_button_shadow("active" if self.is_active else "normal")
        super().leaveEvent(event)


class MiniMetricCard(QFrame):
    def __init__(self, title: str, value: str, trend: str, icon_name: str | None = None):
        super().__init__()
        self.setObjectName("MiniMetricCard")
        self.setMinimumHeight(96)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header_layout = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setObjectName("MiniMetricTitle")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        self.icon_label = None
        if icon_name:
            self.icon_label = QLabel()
            self.icon_label.setPixmap(get_svg_icon(icon_name, "#64748b", 18))
            header_layout.addWidget(self.icon_label)
        layout.addLayout(header_layout)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("MiniMetricValue")
        layout.addWidget(self.value_label)

        self.trend_label = QLabel(trend)
        self.trend_label.setObjectName("MiniMetricSub")
        self.trend_label.setWordWrap(True)
        layout.addWidget(self.trend_label)

    def set_value(self, value: str):
        self.value_label.setText(value)

    def set_trend(self, trend: str):
        self.trend_label.setText(trend)


class ProgressBarRow(QWidget):
    def __init__(self, label: str, value: str, width: int, fill_name: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        title = QLabel(label)
        title.setObjectName("PanelNote")
        count = QLabel(value)
        count.setObjectName("PanelNote")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(count)
        track = QFrame()
        track.setObjectName("ProgressTrack")
        track.setFixedHeight(8)
        inner = QHBoxLayout(track)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)
        fill = QFrame()
        fill.setObjectName(fill_name)
        fill.setFixedWidth(width)
        inner.addWidget(fill)
        inner.addStretch()
        layout.addLayout(top)
        layout.addWidget(track)


class PanelHeader(QFrame):
    def __init__(self, title: str, subtitle: str, icon_name: str | None = None):
        super().__init__()
        self.setObjectName("PanelHeader")
        # 내용이 적은 패널에서 헤더가 세로로 늘어나 빈 공간을 만들지 않도록 고정합니다.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(6)
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("PanelTitle")
        self.note_lbl = QLabel(subtitle)
        self.note_lbl.setObjectName("PanelNote")
        self.note_lbl.setWordWrap(True)
        self.note_lbl.setVisible(bool(str(subtitle).strip()))
        text_layout.addWidget(self.title_lbl)
        text_layout.addWidget(self.note_lbl)

        layout.addLayout(text_layout, 1)
        layout.addStretch()

        if icon_name:
            self.icon_lbl = QLabel()
            self.icon_lbl.setAlignment(Qt.AlignCenter)
            self.icon_lbl.setFixedSize(40, 40)
            self.icon_lbl.setPixmap(get_sidebar_menu_icon(icon_name, False, 30).pixmap(QSize(30, 30)))
            layout.addWidget(self.icon_lbl, 0, Qt.AlignRight | Qt.AlignTop)


def make_splitter(orientation: Qt.Orientation, *widgets: QWidget) -> QSplitter:
    splitter = QSplitter(orientation)
    splitter.setChildrenCollapsible(False)
    splitter.setHandleWidth(6)
    splitter.setOpaqueResize(False)
    for widget in widgets:
        splitter.addWidget(widget)
    return splitter


def make_topbar(title: str, subtitle: str):
    wrap = QFrame()
    wrap.setObjectName("Topbar")
    layout = QHBoxLayout(wrap)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(6)

    left = QHBoxLayout()
    left.setContentsMargins(0, 0, 0, 0)
    left.setSpacing(6)

    title_lbl = QLabel(title)
    title_lbl.setObjectName("TopTitle")

    sub_lbl = QLabel(subtitle)
    sub_lbl.setObjectName("TopSub")
    sub_lbl.setWordWrap(False)

    left.addWidget(title_lbl, 0, Qt.AlignVCenter)
    left.addWidget(sub_lbl, 0, Qt.AlignVCenter)
    left.addStretch()

    layout.addLayout(left, 1)

    top_notice_label = QLabel("")
    top_notice_label.setObjectName("TopNoticeLabel")
    top_notice_label.setMinimumWidth(260)
    top_notice_label.setMaximumWidth(360)
    top_notice_label.setVisible(False)
    layout.addWidget(top_notice_label, 0, Qt.AlignVCenter)

    date_label = QLabel()
    date_label.setObjectName("TopDateLabel")
    date_label.setText(format_korean_top_date())
    layout.addWidget(date_label, 0, Qt.AlignVCenter)

    sync_btn = QPushButton("🔴 수동 동기화")
    sync_btn.setObjectName("TopSyncButton")
    sync_btn.setCursor(Qt.PointingHandCursor)
    sync_btn.setToolTip("서버와 PC 데이터를 자동 판단으로 맞춥니다.")
    layout.addWidget(sync_btn, 0, Qt.AlignVCenter)

    refresh_btn = QPushButton("새로고침")
    refresh_btn.setObjectName("TopRefreshButton")
    refresh_btn.setCursor(Qt.PointingHandCursor)
    layout.addWidget(refresh_btn, 0, Qt.AlignVCenter)
    return wrap

from PySide6.QtCore import Signal

class HomeStatCard(QFrame):
    clicked = Signal(str)

    def __init__(self, title: str, value: str, sub: str, theme: str = "blue", icon: str = "●", filter_key: str = ""):
        super().__init__()
        self.filter_key = filter_key
        self.setObjectName(f"HomeStatCard_{theme}")
        self.setMinimumSize(160, 110)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        icon_label = QLabel(icon)
        icon_label.setObjectName("HomeStatIcon")
        title_label = QLabel(title)
        title_label.setObjectName("HomeStatTitle")
        
        header.addWidget(icon_label)
        header.addWidget(title_label)
        header.addStretch()
        
        self.value_label = QLabel(value)
        self.value_label.setObjectName("HomeStatValue")
        
        self.sub_label = QLabel(sub)
        self.sub_label.setObjectName("HomeStatSub")
        
        layout.addLayout(header)
        layout.addStretch()
        layout.addWidget(self.value_label)
        layout.addWidget(self.sub_label)

    def set_value(self, value: str):
        self.value_label.setText(value)

    def set_active(self, active: bool):
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event):
        self.clicked.emit(self.filter_key)


class DonutChartWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._segments: list[tuple[str, float, str]] = []
        self._center_title = "0점"
        self._center_subtitle = "근태 점수"
        self._center_note = "등급 -"
        self._note_color = "#64748B"
        self._fallback_color = "#C9D3E5"
        self.setMinimumSize(210, 210)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_chart_data(
        self,
        segments: list[tuple[str, float, str]],
        center_title: str,
        center_subtitle: str = "근태 점수",
        center_note: str = "",
        note_color: str | None = None,
        fallback_color: str | None = None,
    ):
        self._segments = [(label, max(float(value), 0.0), color) for label, value, color in segments]
        self._center_title = center_title
        self._center_subtitle = center_subtitle
        self._center_note = center_note
        self._note_color = note_color or "#64748B"
        self._fallback_color = fallback_color or "#C9D3E5"
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        outer_margin = 14
        side = min(self.width(), self.height()) - outer_margin * 2
        side = max(side, 80)
        ring_rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        pen_width = max(14, int(side * 0.11))

        track_pen = QPen(QColor('#E7ECF5'), pen_width)
        painter.setPen(track_pen)
        painter.drawArc(ring_rect, 0, 360 * 16)

        total = sum(value for _, value, _ in self._segments if value > 0)
        start_angle = 90 * 16
        gap_angle = 4 * 16
        if total > 0:
            for _label, value, color in self._segments:
                if value <= 0:
                    continue
                span = int((value / total) * 360 * 16)
                span = max(span - gap_angle, 0)
                painter.setPen(QPen(QColor(color), pen_width, Qt.SolidLine, Qt.RoundCap))
                painter.drawArc(ring_rect, start_angle, -span)
                start_angle -= span + gap_angle
        else:
            painter.setPen(QPen(QColor(self._fallback_color), pen_width, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(ring_rect, start_angle, -360 * 16)

        inner_bg = ring_rect.adjusted(pen_width, pen_width, -pen_width, -pen_width)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#FFFFFF'))
        painter.drawEllipse(inner_bg)

        center_x = ring_rect.center().x()
        center_y = ring_rect.center().y()

        title_font = painter.font()
        title_font.setPointSize(18)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor('#0F172A'))
        title_rect = QRectF(center_x - 50, center_y - 24, 100, 28)
        painter.drawText(title_rect, Qt.AlignCenter, self._center_title)

        sub_font = painter.font()
        sub_font.setPointSize(9)
        sub_font.setBold(True)
        painter.setFont(sub_font)
        painter.setPen(QColor('#475569'))
        sub_rect = QRectF(center_x - 50, center_y + 6, 100, 16)
        painter.drawText(sub_rect, Qt.AlignCenter, self._center_subtitle)

        if self._center_note:
            note_font = painter.font()
            note_font.setPointSize(9)
            note_font.setBold(True)
            painter.setFont(note_font)
            painter.setPen(QColor(self._note_color))
            note_rect = QRectF(center_x - 50, center_y + 24, 100, 16)
            painter.drawText(note_rect, Qt.AlignCenter, self._center_note)


import math
from PySide6.QtGui import QPolygonF

class RadarChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments = []
        self._max_value = 5.0
        self.setMinimumSize(180, 180)

    def set_chart_data(
        self,
        segments: list[tuple[str, float, str]],
        max_value: float = 5,
    ):
        self._segments = [(label, max(float(value), 0.0), color) for label, value, color in segments]
        self._max_value = max(max([v for _, v, _ in self._segments] + [1]), max_value)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        outer_margin = 24
        side = min(self.width(), self.height()) - outer_margin * 2
        radius = side / 2
        center_x = self.width() / 2
        center_y = self.height() / 2

        axes_count = max(len(self._segments), 3)
        angle_step = 2 * math.pi / axes_count
        
        grid_levels = 4
        painter.setPen(QPen(QColor('#E2E8F0'), 1))
        for level in range(1, grid_levels + 1):
            r = radius * (level / grid_levels)
            polygon = QPolygonF()
            for i in range(axes_count):
                angle = i * angle_step - math.pi / 2
                polygon.append(QPointF(center_x + r * math.cos(angle), center_y + r * math.sin(angle)))
            painter.drawPolygon(polygon)

        for i in range(axes_count):
            angle = i * angle_step - math.pi / 2
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            painter.drawLine(QPointF(center_x, center_y), QPointF(x, y))

            if i < len(self._segments):
                label, _, color_hex = self._segments[i]
                label_radius = radius + 14
                lx = center_x + label_radius * math.cos(angle)
                ly = center_y + label_radius * math.sin(angle)
                painter.setPen(QColor(color_hex))
                font = painter.font()
                font.setPointSize(9)
                font.setBold(True)
                painter.setFont(font)
                # Adjust text alignment based on angle to avoid overlapping with axes
                align = Qt.AlignCenter
                rect = QRectF(lx - 20, ly - 10, 40, 20)
                painter.drawText(rect, align, label)

        data_polygon = QPolygonF()
        for i in range(axes_count):
            if i < len(self._segments):
                value = self._segments[i][1]
            else:
                value = 0
            angle = i * angle_step - math.pi / 2
            r = radius * (min(value, self._max_value) / self._max_value)
            data_polygon.append(QPointF(center_x + r * math.cos(angle), center_y + r * math.sin(angle)))

        fill_brush = QColor('#EF4444')
        fill_brush.setAlpha(50)
        painter.setBrush(fill_brush)
        painter.setPen(QPen(QColor('#DC2626'), 2))
        painter.drawPolygon(data_polygon)

        painter.setBrush(QColor('#FFFFFF'))
        painter.setPen(QPen(QColor('#DC2626'), 2))
        for point in data_polygon:
            painter.drawEllipse(point, 3, 3)
