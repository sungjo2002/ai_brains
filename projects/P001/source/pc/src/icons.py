from __future__ import annotations

from functools import lru_cache

from PySide6.QtGui import QPainter, QPixmap, QColor, QFont, QIcon
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtSvg import QSvgRenderer

# SVG Path Data for commonly used icons
ICON_PATHS = {
    "home": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>""",
    "registration": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="16" y1="11" x2="22" y2="11"/></svg>""",
    "business": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>""",
    "attendance": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>""",
    "settings": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>""",
    "passport": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><path d="M8 7h6"/><path d="M8 11h8"/></svg>""",
    "card": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>""",
    "empty": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M16 16s-1.5-2-4-2-4 2-4 2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>""",
    "check_plain": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5 10 17l9-10"/></svg>""",
    "clock_plain": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5l3.5 2"/></svg>""",
    "x_plain": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7l10 10M17 7 7 17"/></svg>""",
    "alert_plain": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 22 20H2L12 3Z"/><path d="M12 9v5"/><path d="M12 17h.01"/></svg>""",
    "exit_plain": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M10 5H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h4"/><path d="M14 8l4 4-4 4"/><path d="M8 12h10"/></svg>""",
    "medical_plain": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>""",
    "presence": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="currentColor"/><path d="m9 12 2 2 4-4" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>""",
    "absence": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="currentColor"/><path d="m15 9-6 6m0-6 6 6" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>""",
    "late": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="currentColor"/><path d="M12 7v5l3 2" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>""",
    "early": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="4" fill="currentColor"/><path d="M8 12h7m-3-3 3 3-3 3" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>""",
    "hospital": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="4" fill="currentColor"/><path d="M12 7v10M7 12h10" stroke="white" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>""",
    "warning": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" fill="currentColor"/><path d="M12 9v4m0 4h0" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>""",
    "unauthorized_absence": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill="currentColor"/><circle cx="12" cy="12" r="5" fill="white"/><path d="m14 10-4 4m0-4 4 4" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>""",
    "off": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>""",
    "search": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>""",
    "user": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>""",
    "vehicle": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 17h14l-1.2-5.2A2 2 0 0 0 15.85 10H8.15a2 2 0 0 0-1.95 1.8L5 17Z"/><path d="M7 10 8.5 6.8A2 2 0 0 1 10.3 5.6h3.4a2 2 0 0 1 1.8 1.2L17 10"/><circle cx="7.5" cy="17.5" r="1.5"/><circle cx="16.5" cy="17.5" r="1.5"/></svg>""",
    "payroll": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/><circle cx="12" cy="15" r="2"/><path d="M6 15h.01M18 15h.01"/></svg>""",
    "coin": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v2m0 8v2m-3.5-7H9a3 3 0 0 1 0 6H8m0-6h-.5"/></svg>""",
    "severance": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>""",
    "chart": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/><line x1="2" y1="20" x2="22" y2="20"/></svg>""",
}

@lru_cache(maxsize=128)
def get_svg_icon(name: str, color: str = "#000000", size: int = 24) -> QPixmap:
    svg_data = ICON_PATHS.get(name, ICON_PATHS["home"]).replace('currentColor', color)
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    renderer = QSvgRenderer(svg_data.encode('utf-8'))
    renderer.render(painter)
    painter.end()
    
    return pixmap

@lru_cache(maxsize=128)
def get_qicon(name: str, color: str = "#000000") -> QIcon:
    return QIcon(get_svg_icon(name, color, 64))

STATUS_ICON_MAP = {
    "출석": "presence",
    "지각": "late",
    "조퇴": "early",
    "병원": "hospital",
    "결근": "absence",
    "무단결근": "unauthorized_absence",
    "무단이탈": "unauthorized_absence",
    "휴무": "off",
}


# --- Sidebar menu icon set ---
from PySide6.QtGui import QPainterPath, QPen, QBrush

SIDEBAR_NAVY = QColor("#162554")
SIDEBAR_ORANGE = QColor("#FF6A1A")
SIDEBAR_BADGE = QColor("#F4F3FA")
SIDEBAR_ACTIVE_BADGE = QColor("#FFF8F2")


def _rounded_rect_path(x: float, y: float, w: float, h: float, r: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), r, r)
    return path


def _draw_sidebar_icon_shape(p: QPainter, name: str, rect: QRectF, active: bool):
    navy = SIDEBAR_NAVY
    orange = SIDEBAR_ORANGE
    cx = rect.center().x()
    cy = rect.center().y()
    w = rect.width()
    h = rect.height()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)

    if name == 'home':
        roof = QPainterPath()
        roof.moveTo(cx, rect.top() + h*0.12)
        roof.lineTo(rect.left() + w*0.18, rect.top() + h*0.42)
        roof.lineTo(rect.left() + w*0.28, rect.top() + h*0.42)
        roof.lineTo(rect.left() + w*0.28, rect.bottom() - h*0.12)
        roof.lineTo(rect.right() - w*0.28, rect.bottom() - h*0.12)
        roof.lineTo(rect.right() - w*0.28, rect.top() + h*0.42)
        roof.lineTo(rect.right() - w*0.18, rect.top() + h*0.42)
        roof.closeSubpath()
        p.setBrush(navy)
        p.drawPath(roof)
        door = QRectF(cx - w*0.09, rect.bottom() - h*0.36, w*0.18, h*0.24)
        p.setBrush(orange)
        p.drawRoundedRect(door, 4, 4)
        return

    if name == 'business':
        body = QRectF(rect.left()+w*0.14, rect.top()+h*0.28, w*0.72, h*0.48)
        p.setBrush(navy)
        p.drawRoundedRect(body, 8, 8)
        handle = QRectF(cx-w*0.16, rect.top()+h*0.14, w*0.32, h*0.18)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(navy, 3))
        p.drawRoundedRect(handle, 5, 5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#FFFFFF'))
        p.drawRect(body.left(), cy-1.2, body.width(), 2.4)
        latch = QRectF(cx-w*0.09, cy-h*0.02, w*0.18, h*0.16)
        p.setBrush(orange)
        p.drawRoundedRect(latch, 4, 4)
        p.setBrush(QColor('#FFFFFF'))
        inner = QRectF(cx-w*0.05, cy+h*0.01, w*0.10, h*0.08)
        p.drawRoundedRect(inner, 2, 2)
        return

    if name == 'user':
        p.setBrush(navy)
        p.drawEllipse(QRectF(cx-w*0.16, rect.top()+h*0.12, w*0.32, w*0.32))
        torso = QPainterPath()
        torso.moveTo(cx-w*0.26, rect.bottom()-h*0.18)
        torso.quadTo(cx-w*0.24, cy+h*0.02, cx, cy+h*0.02)
        torso.quadTo(cx+w*0.24, cy+h*0.02, cx+w*0.26, rect.bottom()-h*0.18)
        torso.lineTo(cx-w*0.26, rect.bottom()-h*0.18)
        torso.closeSubpath()
        p.drawPath(torso)
        tie = QPainterPath()
        tie.moveTo(cx, cy+h*0.02)
        tie.lineTo(cx-w*0.06, cy+h*0.14)
        tie.lineTo(cx, rect.bottom()-h*0.16)
        tie.lineTo(cx+w*0.06, cy+h*0.14)
        tie.closeSubpath()
        p.setBrush(orange)
        p.drawPath(tie)
        return

    if name == 'registration':
        _draw_sidebar_icon_shape(p, 'user', rect, active)
        badge = QRectF(rect.right()-w*0.34, rect.bottom()-h*0.34, w*0.28, h*0.28)
        p.setBrush(orange)
        p.drawEllipse(badge)
        p.setPen(QPen(QColor('white'), 3))
        p.drawLine(badge.center().x(), badge.top()+badge.height()*0.22, badge.center().x(), badge.bottom()-badge.height()*0.22)
        p.drawLine(badge.left()+badge.width()*0.22, badge.center().y(), badge.right()-badge.width()*0.22, badge.center().y())
        p.setPen(Qt.NoPen)
        return

    if name == 'attendance':
        body = QRectF(rect.left()+w*0.14, rect.top()+h*0.20, w*0.72, h*0.62)
        p.setBrush(QColor('#EDECF5'))
        p.drawRoundedRect(body, 8, 8)
        head = QRectF(body.left(), body.top(), body.width(), body.height()*0.28)
        p.setBrush(navy)
        p.drawRoundedRect(head, 8, 8)
        p.setBrush(QColor('#FFFFFF'))
        p.drawRoundedRect(QRectF(body.left()+w*0.15, body.top()+h*0.15, w*0.06, h*0.08), 2, 2)
        p.drawRoundedRect(QRectF(body.right()-w*0.21, body.top()+h*0.15, w*0.06, h*0.08), 2, 2)
        p.setBrush(navy)
        for ix in range(3):
            for iy in range(2):
                p.drawEllipse(QRectF(body.left()+w*(0.18+ix*0.16), body.top()+h*(0.40+iy*0.14), w*0.06, w*0.06))
        badge = QRectF(body.right()-w*0.24, body.bottom()-h*0.24, w*0.28, h*0.28)
        p.setBrush(orange)
        p.drawEllipse(badge)
        p.setPen(QPen(QColor('white'), 3))
        p.drawLine(badge.left()+badge.width()*0.24, badge.center().y(), badge.left()+badge.width()*0.43, badge.bottom()-badge.height()*0.28)
        p.drawLine(badge.left()+badge.width()*0.43, badge.bottom()-badge.height()*0.28, badge.right()-badge.width()*0.22, badge.top()+badge.height()*0.28)
        p.setPen(Qt.NoPen)
        return

    if name == 'payroll':
        wallet = QRectF(rect.left()+w*0.12, rect.top()+h*0.28, w*0.76, h*0.48)
        p.setBrush(navy)
        p.drawRoundedRect(wallet, 8, 8)
        flap = QRectF(wallet.left()+w*0.02, wallet.top()+h*0.02, wallet.width()*0.92, wallet.height()*0.22)
        p.setBrush(QColor('#F7F6FB'))
        p.drawRoundedRect(flap, 6, 6)
        badge = QRectF(wallet.right()-w*0.28, wallet.center().y()-w*0.11, w*0.22, w*0.22)
        p.setBrush(orange)
        p.drawEllipse(badge)
        p.setBrush(QColor('white'))
        p.drawEllipse(QRectF(badge.left()+w*0.04, badge.top()+w*0.04, badge.width()-w*0.08, badge.height()-w*0.08))
        return

    if name == 'vehicle':
        body = QPainterPath()
        body.moveTo(rect.left()+w*0.24, rect.bottom()-h*0.28)
        body.lineTo(rect.left()+w*0.20, rect.bottom()-h*0.10)
        body.lineTo(rect.left()+w*0.26, rect.bottom()-h*0.10)
        body.lineTo(rect.left()+w*0.30, rect.bottom()-h*0.20)
        body.lineTo(rect.right()-w*0.30, rect.bottom()-h*0.20)
        body.lineTo(rect.right()-w*0.26, rect.bottom()-h*0.10)
        body.lineTo(rect.right()-w*0.20, rect.bottom()-h*0.10)
        body.lineTo(rect.right()-w*0.24, rect.bottom()-h*0.28)
        body.lineTo(rect.right()-w*0.20, rect.top()+h*0.44)
        body.quadTo(cx, rect.top()+h*0.18, rect.left()+w*0.20, rect.top()+h*0.44)
        body.closeSubpath()
        p.setBrush(navy)
        p.drawPath(body)
        p.setBrush(QColor('#F7F6FB'))
        p.drawRoundedRect(QRectF(rect.left()+w*0.27, rect.top()+h*0.40, w*0.46, h*0.16), 5, 5)
        p.setBrush(orange)
        for x in (rect.left()+w*0.26, rect.right()-w*0.34):
            p.drawEllipse(QRectF(x, rect.bottom()-h*0.33, w*0.10, w*0.10))
        for x in (rect.left()+w*0.22, rect.right()-w*0.32):
            p.drawEllipse(QRectF(x, rect.bottom()-h*0.12, w*0.12, w*0.12))
        return

    if name == 'settings':
        import math
        outer = QPainterPath()
        cx2, cy2 = cx, cy
        r1, r2 = w*0.30, w*0.22
        for i in range(16):
            ang = math.pi/8 * i - math.pi/2
            r = r1 if i % 2 == 0 else r2
            x = cx2 + math.cos(ang) * r
            y = cy2 + math.sin(ang) * r
            if i == 0:
                outer.moveTo(x, y)
            else:
                outer.lineTo(x, y)
        outer.closeSubpath()
        p.setBrush(navy)
        p.drawPath(outer)
        p.setBrush(QColor('#FFFFFF'))
        p.drawEllipse(QRectF(cx-w*0.17, cy-h*0.17, w*0.34, w*0.34))
        p.setBrush(orange)
        p.drawEllipse(QRectF(cx-w*0.11, cy-h*0.11, w*0.22, w*0.22))
        return


@lru_cache(maxsize=64)
def get_sidebar_menu_icon(name: str, active: bool = False, size: int = 56) -> QIcon:
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    badge_margin = 3
    badge_rect = QRectF(badge_margin, badge_margin, size - badge_margin * 2, size - badge_margin * 2)
    p.setPen(Qt.NoPen)
    p.setBrush(SIDEBAR_ACTIVE_BADGE if active else SIDEBAR_BADGE)
    p.drawRoundedRect(badge_rect, 14, 14)
    inner_rect = QRectF(8, 8, size - 16, size - 16)
    _draw_sidebar_icon_shape(p, name, inner_rect, active)
    p.end()
    return QIcon(pixmap)
