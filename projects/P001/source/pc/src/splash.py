from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget


class StartupSplash(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setObjectName("StartupSplash")
        self.setFixedSize(420, 240)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("StartupSplashCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(6, 6, 6, 6)
        card_layout.setSpacing(6)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(6)

        icon_badge = QLabel("인력")
        icon_badge.setObjectName("StartupSplashBadge")
        icon_badge.setAlignment(Qt.AlignCenter)
        icon_badge.setFixedSize(52, 52)
        badge_row.addWidget(icon_badge, 0, Qt.AlignLeft | Qt.AlignVCenter)

        title_wrap = QVBoxLayout()
        title_wrap.setContentsMargins(0, 0, 0, 0)
        title_wrap.setSpacing(6)

        brand_small = QLabel("WORKFORCE OPERATIONS")
        brand_small.setObjectName("StartupSplashSmall")
        title_wrap.addWidget(brand_small)

        title = QLabel("프로그램 불러오는 중")
        title.setObjectName("StartupSplashTitle")
        title_wrap.addWidget(title)

        subtitle = QLabel("근로자 · 근태 · 급여 · 차량 데이터를 준비하고 있습니다.")
        subtitle.setObjectName("StartupSplashSubtitle")
        subtitle.setWordWrap(True)
        title_wrap.addWidget(subtitle)

        badge_row.addLayout(title_wrap, 1)
        card_layout.addLayout(badge_row)

        self.status_label = QLabel("잠시만 기다려주세요")
        self.status_label.setObjectName("StartupSplashStatus")
        card_layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)
        self.progress.setObjectName("StartupSplashProgress")
        card_layout.addWidget(self.progress)

        tip = QLabel("초기 실행 시에는 로딩이 조금 더 길 수 있습니다.")
        tip.setObjectName("StartupSplashTip")
        tip.setWordWrap(True)
        card_layout.addWidget(tip)

        card_layout.addStretch(1)
        root.addWidget(card)

        self._dot_step = 0
        self._progress_value = 0
        self._progress_target = 10
        self._base_status = "잠시만 기다려주세요"
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate_text)
        self._timer.start(45)

        self.setStyleSheet(
            """
            QWidget#StartupSplash { background: rgba(0, 0, 0, 24); }
            QFrame#StartupSplashCard {
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 22px;
            }
            QLabel#StartupSplashBadge {
                background: #EFF6FF;
                color: #1E3A8A;
                border: 1px solid #BFDBFE;
                border-radius: 16px;
                font-size: 15px;
                font-weight: 900;
            }
            QLabel#StartupSplashSmall {
                color: #64748B;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 1.4px;
            }
            QLabel#StartupSplashTitle {
                color: #0F172A;
                font-size: 22px;
                font-weight: 900;
            }
            QLabel#StartupSplashSubtitle {
                color: #475569;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#StartupSplashStatus {
                color: #1E293B;
                font-size: 13px;
                font-weight: 800;
                padding-top: 6px;
            }
            QLabel#StartupSplashTip {
                color: #94A3B8;
                font-size: 11px;
                font-weight: 600;
                padding-top: 6px;
            }
            QProgressBar#StartupSplashProgress {
                background: #F1F5F9;
                border: 1px solid #E2E8F0;
                border-radius: 5px;
            }
            QProgressBar#StartupSplashProgress::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #93C5FD, stop:0.55 #3B82F6, stop:1 #2563EB);
                border-radius: 5px;
            }
            """
        )

    def _animate_text(self):
        self._dot_step = (self._dot_step + 1) % 4
        self.status_label.setText(self._base_status + "." * self._dot_step)
        if self._progress_value < self._progress_target:
            self._progress_value = min(self._progress_target, self._progress_value + 2)
        elif self._progress_value > self._progress_target:
            self._progress_value = max(self._progress_target, self._progress_value - 1)
        self.progress.setValue(self._progress_value)

    def set_status(self, text: str, progress: int | None = None):
        self._base_status = str(text or "").strip() or "잠시만 기다려주세요"
        if progress is not None:
            self.set_progress_target(progress)
        self._animate_text()

    def set_progress_target(self, value: int):
        self._progress_target = max(0, min(100, int(value)))

    def center_on_screen(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geometry = screen.availableGeometry()
        self.move(
            geometry.center().x() - self.width() // 2,
            geometry.center().y() - self.height() // 2,
        )

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
