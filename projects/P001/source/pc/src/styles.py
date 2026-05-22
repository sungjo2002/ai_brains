GLOBAL_STYLES = """
/* Blue-gray UI palette applied in pc_32
   BG #F4F7FB / CARD #FFFFFF / SUBCARD #F8FAFC / BORDER #D9E2EC / INPUT #FBFCFE */
QWidget {
    background: transparent;
    color: #1E293B;
    font-family: 'Malgun Gothic', 'Segoe UI';
}
QLabel {
    background: transparent;
}
QMainWindow, QWidget#AppRoot {
    background: #F4F7FB;
}
QDialog, QMessageBox {
    background: #F4F7FB;
}
QFrame#Shell {
    background: transparent;
    border: none;
    border-radius: 0px;
}
QWidget#ContentWrap,
QStackedWidget#PageStack,
QScrollArea#PageScrollArea,
QScrollArea#PageScrollArea > QWidget,
QScrollArea#PageScrollArea > QWidget > QWidget {
    background: #F4F7FB;
}

/* ---------------- SIDEBAR ---------------- */
QFrame#Sidebar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #12346D, stop:0.52 #0D295C, stop:1 #081D43);
    border-radius: 0px;
    border-right: 1px solid #183B72;
}
QFrame#BrandBox {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #174D96, stop:0.55 #12376F, stop:1 #0A2657);
    border: 1px solid rgba(147, 197, 253, 0.22);
    border-radius: 16px;
}
QLabel#BrandLogo {
    background: transparent;
}
QFrame#BrandDivider {
    background: rgba(147, 197, 253, 0.32);
    border: none;
}
QWidget#BrandTextWrap {
    background: transparent;
}
QLabel#BrandSmall {
    color: #8DD3FF;
    font-size: 10px;
    font-weight: 900;
    letter-spacing: 0.6px;
}
QLabel#BrandMain {
    color: #FFFFFF;
    font-size: 24px;
    font-weight: 900;
}
QLabel#BrandSub {
    color: #93C5FD;
    font-size: 8px;
    font-weight: 900;
    letter-spacing: 1.2px;
}
QLabel#SidebarSection {
    color: rgba(219, 234, 254, 0.86);
    font-size: 10px;
    font-weight: 800;
}
QPushButton#NavButton {
    text-align: left;
    background: transparent;
    color: #DBEAFE;
    border: none;
    border-left: 4px solid transparent;
    border-radius: 4px;
    padding: 6px 6px 6px 6px;
    min-height: 48px;
    font-size: 14px;
    font-weight: 900;
}
QPushButton#NavButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255, 255, 255, 0.12), stop:1 transparent);
    color: #FFFFFF;
    border-left: 4px solid rgba(255, 255, 255, 0.5);
}
QPushButton#NavButton:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(96, 165, 250, 0.1), stop:1 transparent);
    color: #FFFFFF;
    border-left: 4px solid #60A5FA;
}
QPushButton#NavButton:disabled {
    color: rgba(255, 255, 255, 0.25);
}
QFrame#SidebarSyncWrap {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 14px;
}
QPushButton#SyncButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2A63E6, stop:1 #4285F4);
    color: #FFFFFF;
    border: 1px solid rgba(255,255,255,0.18);
    border-radius: 12px;
    padding: 6px 6px;
    font-size: 13px;
    font-weight: 900;
}
QPushButton#SyncButton:hover {
    background: #2458D4;
}
QPushButton#SyncButton:pressed {
    background: #1D4ED8;
}
QPushButton#SyncButton:disabled {
    background: rgba(59, 130, 246, 0.35);
    color: rgba(255, 255, 255, 0.65);
    border: 1px solid rgba(255, 255, 255, 0.12);
}
QLabel#SyncStateLabel {
    color: #F8FAFC;
    font-size: 11px;
    font-weight: 800;
}
QLabel#SyncHintLabel {
    color: rgba(219, 234, 254, 0.78);
    font-size: 10px;
    font-weight: 700;
}

/* ---------------- TOPBAR ---------------- */
QFrame#Topbar {
    background: #FFFFFF;
    border-top-right-radius: 20px;
    border-bottom: 1px solid #D9E2EC;
    min-height: 62px;
    max-height: 62px;
}
QLabel#TopTitle {
    color: #0F172A;
    font-size: 18px;
    font-weight: 900;
    padding-right: 6px;
}
QLabel#TopSub {
    color: #64748B;
    font-size: 14px;
    font-weight: 700;
}
QLabel#TopNoticeLabel {
    background: #ECFDF5;
    color: #047857;
    border: 1px solid #A7F3D0;
    border-radius: 8px;
    padding: 0 6px;
    min-height: 30px;
    max-height: 30px;
    font-size: 12px;
    font-weight: 900;
}

/* ---------------- HERO ---------------- */
QFrame#HeroCard, QFrame#CompactHero, QFrame#EmployeeHero {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FBFCFE, stop:0.60 #F3F8FF, stop:1 #EAF3FF);
    border: 1px solid #D9E2EC;
    border-radius: 14px;
}
QLabel#FixedBannerIconCircle {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #F5F9FF, stop:1 #E6F0FF);
    border: 1px solid #D1E2FA;
    border-radius: 21px;
}
QFrame#TopBannerArtWrap {
    background: transparent;
    border: none;
    border-radius: 0px;
}
QFrame#HomeOverviewBanner {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FBFCFE, stop:0.54 #F3F8FF, stop:1 #EAF3FF);
    border: 1px solid #D8E6F6;
    border-radius: 16px;
}
QLabel#BannerIconCircle {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #F5F9FF, stop:1 #E6F0FF);
    border: 1px solid #D0E1FA;
    border-radius: 27px;
}
QLabel#HomeOverviewBadge {
    color: #2563EB;
    font-size: 10px;
    font-weight: 900;
    letter-spacing: 1.2px;
}
QLabel#HomeOverviewTitle {
    color: #10233F;
    font-size: 18px;
    font-weight: 900;
}
QLabel#HomeOverviewDesc {
    color: #5A6C81;
    font-size: 12px;
    font-weight: 700;
}
QFrame#HomeOverviewArtWrap {
    background: rgba(255, 255, 255, 0.58);
    border: 1px solid #D9E6F6;
    border-radius: 14px;
}
QLabel#HeroTitle {
    color: #0A1931;
    font-size: 23px;
    font-weight: 900;
    letter-spacing: -0.6px;
}
QLabel#HeroDesc, QLabel#HeroSub {
    color: #4A5D75;
    font-size: 13px;
    font-weight: 700;
}
QLabel#HeroBadge {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #EAF2FF, stop:1 #DFECFF);
    color: #1D4ED8;
    border: 1px solid #C4D9F8;
    border-radius: 6px;
    padding: 6px 6px;
    font-size: 10px;
    font-weight: 900;
    letter-spacing: 1.2px;
}
QLabel#HeroChip {
    background: #FFFFFF;
    color: #1D4ED8;
    border: 1px solid #D8E5FA;
    border-radius: 15px;
    padding: 6px 6px;
    font-size: 12px;
    font-weight: 800;
}
QPushButton#HeroPillButton {
    background: #FFFFFF;
    color: #2957BE;
    border: 1px solid #D9E2EC;
    border-radius: 12px;
    padding: 6px 6px;
    font-size: 11px;
    font-weight: 800;
}
QPushButton#HeroPillButton:hover {
    background: #EEF4FF;
    border: 1px solid #AFC6EE;
    color: #1E40AF;
}

/* ---------------- PANELS & CARDS ---------------- */
QFrame#Panel {
    background: #FFFFFF;
    border: 1px solid #D9E2EC;
    border-radius: 14px;
}
QFrame#PanelHeader {
    background: transparent;
}
QLabel#PanelTitle, QLabel#SectionTitle {
    color: #0F172A;
    font-size: 14px;
    font-weight: 900;
}
QLabel#PanelNote, QLabel#PanelSubtitle, QLabel#SectionSub, QLabel#SectionHelp {
    color: #64748B;
    font-size: 12px;
    font-weight: 600;
}
QFrame#OriginGuideCard {
    background: #F8FAFC;
    border: 1px solid #D9E2EC;
    border-radius: 10px;
}
QLabel#OriginGuideTitle {
    color: #0F172A;
    font-size: 12px;
    font-weight: 900;
}
QLabel#OriginGuideText {
    color: #334155;
    font-size: 12px;
    font-weight: 600;
}
QFrame#StatCard, QFrame#MiniMetricCard {
    background: #FFFFFF;
    border: 1px solid #D9E2EC;
    border-radius: 14px;
}
QFrame#StatCard:hover {
    border: 1px solid #BFD1EA;
    background: #F8FAFC;
}
QFrame#StatCard[active="true"] {
    background: #EEF4FF;
    border: 1px solid #80A9E8;
}
QLabel#StatValue, QLabel#MiniMetricValue {
    color: #0F172A;
    font-size: 20px;
    font-weight: 900;
    padding-top: 6px;
}
QLabel#StatTitle, QLabel#MiniMetricTitle {
    color: #3F4E63;
    font-size: 12px;
    font-weight: 800;
}
QLabel#StatSub, QLabel#MiniMetricSub {
    color: #6B7B90;
    font-size: 11px;
    font-weight: 600;
}
QFrame#StatCard[variant="home_summary"],
QFrame#StatCard[variant="employee_summary"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #F1F7FF);
    border: 1px solid #C7D8ED;
    border-bottom: 2px solid #AFC5E0;
    border-radius: 12px;
}
QFrame#StatCard[variant="home_summary"]:hover,
QFrame#StatCard[variant="employee_summary"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #E7F1FF);
    border: 1px solid #91B8EA;
    border-bottom: 2px solid #6FA4E4;
}
QFrame#StatCard[variant="home_summary"][active="true"],
QFrame#StatCard[variant="employee_summary"][active="true"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F8FBFF, stop:1 #DDEBFF);
    border: 1px solid #7CAEEA;
    border-bottom: 2px solid #4F8DDA;
}
QFrame#StatCard[variant="home_summary"][active="true"]:hover,
QFrame#StatCard[variant="employee_summary"][active="true"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F3F8FF, stop:1 #D2E5FF);
    border: 1px solid #6FA4E4;
    border-bottom: 2px solid #3F7ED0;
}
QFrame#StatCard[variant="home_summary"][pressed="true"],
QFrame#StatCard[variant="employee_summary"][pressed="true"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #D8E9FF, stop:1 #F4F9FF);
    border: 1px solid #5B95DE;
    border-top: 2px solid #3F7ED0;
    border-bottom: 1px solid #9FC2EE;
}
QFrame#StatCard[variant="home_summary"][active="true"] QLabel#HomeFilterCardTitle,
QFrame#StatCard[variant="home_summary"][active="true"] QLabel#HomeFilterCardValue {
    color: #0F172A;
}
QFrame#StatCard[variant="home_summary"][pressed="true"] QLabel#HomeFilterCardTitle,
QFrame#StatCard[variant="home_summary"][pressed="true"] QLabel#HomeFilterCardValue {
    color: #0F172A;
}
QFrame#StatCard[variant="employee_summary"][pressed="true"] QLabel#StatTitle,
QFrame#StatCard[variant="employee_summary"][pressed="true"] QLabel#StatValue {
    color: #0B3B82;
}
QLabel#HomeFilterCardTitle {
    color: #42546A;
    font-size: 13px;
    font-weight: 800;
}
QLabel#HomeFilterCardValue {
    color: #0F172A;
    font-size: 24px;
    font-weight: 900;
    letter-spacing: -0.6px;
    padding-top: 6px;
}
QLabel#HomeFilterCardSub {
    color: #71839B;
    font-size: 11px;
    font-weight: 700;
}
QLabel#HomeFilterCardIcon {
    min-width: 24px;
    min-height: 24px;
    max-width: 24px;
    max-height: 24px;
    background: transparent;
    border: 0px;
    border-radius: 0px;
    padding: 0px;
    margin: 0px;
}
QLabel#StatusBadge {
    background: #F8FAFC;
    color: #334155;
    border: 1px solid #D9E2EC;
    border-radius: 12px;
    padding: 6px 6px;
    font-size: 12px;
    font-weight: 900;
}

/* ---------------- HOME STATUS CARDS ---------------- */
QFrame[objectName^="HomeStatCard_"] {
    border-radius: 16px;
    border: 2px solid transparent;
}
QFrame[objectName^="HomeStatCard_"][active="true"] {
    border: 2px solid #BFDBFE;
}
QFrame#HomeStatCard_blue { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #2563EB, stop:1 #1D4ED8); }
QFrame#HomeStatCard_green { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #10B981, stop:1 #047857); }
QFrame#HomeStatCard_red { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #F43F5E, stop:1 #BE123C); }
QFrame#HomeStatCard_purple { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #8B5CF6, stop:1 #6D28D9); }
QFrame#HomeStatCard_orange { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #F59E0B, stop:1 #D97706); }
QFrame#HomeStatCard_gray { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #64748B, stop:1 #334155); }
QLabel#HomeStatIcon { color: rgba(255, 255, 255, 0.92); font-size: 18px; }
QLabel#HomeStatTitle { color: rgba(255, 255, 255, 0.96); font-size: 13px; font-weight: 800; }
QLabel#HomeStatValue { color: #FFFFFF; font-size: 30px; font-weight: 900; letter-spacing: -1px; }
QLabel#HomeStatSub { color: rgba(255, 255, 255, 0.84); font-size: 11px; font-weight: 700; }


QFrame#DetailSummaryCard {
    background: transparent;
    border: none;
    border-radius: 0px;
}
QFrame#HomeSelectedDetailCard {
    background: transparent;
    border: none;
    border-radius: 0px;
}
QLabel#DetailAvatar {
    background: #EEF4FF;
    color: #3D66B5;
    border: 1px solid #D7E3F4;
    border-radius: 16px;
    font-size: 18px;
    font-weight: 900;
}
QLabel#DetailSummaryName {
    color: #10233E;
    font-size: 20px;
    font-weight: 900;
}
QLabel#HomeDetailNumberBadge {
    background: #EAF3FF;
    color: #1D4ED8;
    border: 1px solid #93C5FD;
    border-radius: 13px;
    padding: 6px 6px;
    font-size: 12px;
    font-weight: 900;
}
QLabel#HomeDetailMoreButton {
    color: #7B8BA0;
    font-size: 18px;
    font-weight: 900;
}
QLabel#DetailMeta {
    color: #43556E;
    font-size: 11px;
    font-weight: 800;
}
QLabel#FieldLabel, QLabel#HomeDetailKey {
    color: #5D6F86;
    font-size: 12px;
    font-weight: 800;
}
QLabel#HomeDetailValue {
    color: #1F344E;
    font-size: 12px;
    font-weight: 800;
}
QComboBox#PageSizeCombo {
    min-width: 82px;
}

QFrame#ScoreSummaryCard {
    background: transparent;
    border: none;
}
QFrame#ScoreValueBox {
    background: #FFFFFF;
    border: 1px solid #E1E8F2;
    border-radius: 12px;
}
QLabel#ScoreNumber {
    color: #0F172A;
    font-size: 24px;
    font-weight: 900;
}
QLabel#ScoreGrade {
    color: #10B981;
    font-size: 12px;
    font-weight: 900;
}
QLabel#ScorePeriod, QLabel#ScoreMeta {
    color: #64748B;
    font-size: 10px;
    font-weight: 600;
    line-height: 1.2;
}
QFrame#ScoreLegendRow {
    background: transparent;
    border: none;
    border-radius: 0px;
}
QLabel#ScoreLegendName {
    color: #334155;
    font-size: 12px;
    font-weight: 800;
}
QLabel#ScoreLegendValue {
    color: #0F172A;
    font-size: 12px;
    font-weight: 800;
    min-width: 32px;
    max-width: 32px;
}


/* ---------------- ATTENDANCE / PAYROLL COMMON ---------------- */
QLabel#FilterLabel {
    color: #475569;
    font-size: 11px;
    font-weight: 800;
    padding: 0 6px;
}
QPushButton#MonthChip {
    background: #FFFFFF;
    color: #334155;
    border: 1px solid #CBD5E1;
    border-radius: 10px;
    padding: 6px 6px;
    font-size: 12px;
    font-weight: 800;
}
QPushButton#MonthChip:hover {
    background: #F8FAFC;
    color: #1D4ED8;
    border: 1px solid #AFC6EE;
}
QPushButton#MonthChip:checked {
    background: #0F3F99;
    color: #FFFFFF;
    border: 1px solid #0D357F;
}
QPushButton#MonthChip:disabled {
    background: #F1F5F9;
    color: #94A3B8;
    border: 1px solid #E2E8F0;
}
QLabel#DetailName {
    color: #0F172A;
    font-size: 14px;
    font-weight: 900;
}
QLabel#DetailKey {
    color: #475569;
    font-size: 11px;
    font-weight: 800;
}
QLabel#DetailValue {
    color: #1E293B;
    font-size: 12px;
    font-weight: 700;
}

/* ---------------- BUTTONS ---------------- */
QPushButton#PrimaryButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #0F3F99);
    color: #FFFFFF;
    border: 1px solid #0D357F;
    border-radius: 8px;
    padding: 0 6px;
    min-height: 30px;
    max-height: 30px;
    font-size: 12px;
    font-weight: 800;
}
QPushButton#PrimaryButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2E6EF0, stop:1 #1247A8);
}
QPushButton#PrimaryButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #174AAE, stop:1 #0B2E6D);
}
QPushButton#PrimaryButton:disabled {
    background: #CBD5E1;
    color: #8A9BB5;
    border: 1px solid #CBD5E1;
}
QPushButton#GhostButton, QPushButton#IconActionButton {
    background: #FFFFFF;
    color: #334155;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 0 6px;
    min-height: 30px;
    max-height: 30px;
    font-size: 12px;
    font-weight: 700;
}
QPushButton#GhostButton:hover, QPushButton#IconActionButton:hover {
    background: #F4F9FF;
    color: #1D4ED8;
    border: 1px solid #AFC6EE;
}
QPushButton#GhostButton:pressed, QPushButton#IconActionButton:pressed {
    background: #EAF2FF;
    color: #1E40AF;
    border: 1px solid #9EB8E8;
}
QPushButton#DangerButton, QPushButton#WarnButton {
    background: #FEF2F2;
    color: #DC2626;
    border: 1px solid #FECACA;
    border-radius: 8px;
    padding: 0 6px;
    min-height: 30px;
    max-height: 30px;
    font-size: 12px;
    font-weight: 700;
}
QPushButton#PersonalToggleButton {
    background: #0F3F99;
    color: #FFFFFF;
    border: 1px solid #0D357F;
    border-radius: 8px;
    min-width: 18px;
    max-width: 18px;
    padding: 6px 0;
    font-size: 11px;
    font-weight: 900;
}
QPushButton#PersonalToggleButton:checked {
    background: #0B2E6D;
}

/* ---------------- INPUT FIELDS ---------------- */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {
    background: #FBFCFE;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 0px 6px;
    min-height: 30px;
    max-height: 30px;
    font-size: 12px;
    font-weight: 600;
}
QTextEdit, QPlainTextEdit {
    background: #FBFCFE;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 6px;
    font-size: 12px;
    font-weight: 600;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #2563EB;
    background: #FBFCFE;
}
QComboBox, QDateEdit {
    padding-right: 6px;
}
QComboBox::drop-down, QDateEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 15px;
    border-left: 1px solid #CBD5E1;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background: #F8FAFC;
}
QComboBox::down-arrow, QDateEdit::down-arrow {
    image: url(assets/combo_arrow_down.svg);
    width: 7px;
    height: 5px;
}
QComboBox QAbstractItemView {
    background: #FFFFFF;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    selection-background-color: #EEF4FF;
    selection-color: #1D4ED8;
    border-radius: 8px;
    padding: 6px;
}

/* ---------------- TABLES ---------------- */
QTableWidget, QTreeWidget, QListWidget {
    background: #FFFFFF;
    color: #1E293B;
    border: 1px solid #D9E2EC;
    border-radius: 12px;
    padding: 6px;
    gridline-color: #E5EDF5;
    font-size: 12px;
}
QHeaderView::section {
    background: #F8FAFC;
    color: #475569;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #E5EDF5;
    font-size: 13px;
    font-weight: 800;
}
QTableWidget::item, QTreeWidget::item, QListWidget::item {
    padding: 6px;
    border-bottom: 1px solid #E5EDF5;
}
QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {
    background: #EEF4FF;
    color: #1D4ED8;
}

/* ---------------- SCROLLBAR & SPLITTER ---------------- */

QFrame#InnerScrollFrame {
    background: #FFFFFF;
    border: 1px solid #D9E2EC;
    border-radius: 14px;
}

QFrame#ScrollPageOuterFrame {
    background: transparent;
    border: none;
    border-radius: 0px;
}
QScrollArea#InnerScrollArea {
    border: none;
    background: transparent;
}
QScrollArea#InnerScrollArea > QWidget > QWidget {
    background: transparent;
}

QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    width: 10px;
    background: transparent;
    margin: 6px 0 6px 0;
}
QScrollBar::handle:vertical {
    background: #CBD5E1;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}
QScrollBar:horizontal {
    height: 10px;
    background: transparent;
    margin: 0 6px 0 6px;
}
QScrollBar::handle:horizontal {
    background: #CBD5E1;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background: #94A3B8;
}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
    border: none;
}
QSplitter::handle:horizontal, QSplitter::handle:vertical {
    background: transparent;
    border: 0px;
}
QSplitter::handle:horizontal:hover, QSplitter::handle:vertical:hover {
    background: transparent;
    border: 0px;
}

/* ---------------- MENUS & CALENDAR ---------------- */
QMenu {
    background: #FFFFFF;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 6px 0;
}
QMenu::item {
    padding: 6px 6px;
    font-size: 12px;
    font-weight: 600;
}
QMenu::item:selected {
    background: #EEF4FF;
    color: #1D4ED8;
}
QCalendarWidget {
    background: #FFFFFF;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    border-radius: 12px;
}
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background: #FFFFFF;
    color: #1E293B;
    border-bottom: 1px solid #E5EDF5;
    padding: 6px;
}
QCalendarWidget QToolButton {
    color: #1E293B;
    background: transparent;
    border-radius: 6px;
    padding: 6px;
    font-weight: 800;
}
QCalendarWidget QToolButton:hover {
    background: #EEF4FF;
}
QCalendarWidget QSpinBox {
    background: #FFFFFF;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
}
QCalendarWidget QAbstractItemView,
QCalendarWidget QTableView,
QCalendarWidget QTableWidget {
    background: #FFFFFF;
    alternate-background-color: #FFFFFF;
    color: #1E293B;
    selection-background-color: #DBEAFE;
    selection-color: #1D4ED8;
    outline: 0;
    border: none;
    gridline-color: #E7EEF7;
}

/* ---------------- TABS, CHECKS ---------------- */
QTabWidget::pane {
    border: 1px solid #D9E2EC;
    border-radius: 12px;
    background: #FFFFFF;
}
QTabBar::tab {
    background: #F8FAFC;
    color: #475569;
    border: 1px solid #D9E2EC;
    padding: 6px 6px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    font-weight: 700;
    margin-right: 6px;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #1D4ED8;
    border-bottom-color: #FFFFFF;
}
QCheckBox, QRadioButton {
    color: #334155;
    font-size: 12px;
    font-weight: 600;
}

/* ---------------- DIALOG BUTTONS ---------------- */
QDialog QPushButton, QMessageBox QPushButton {
    background: #FFFFFF;
    color: #334155;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 0 6px;
    min-height: 30px;
    max-height: 30px;
    font-size: 12px;
    font-weight: 800;
    min-width: 86px;
}
QDialog QPushButton:hover, QMessageBox QPushButton:hover {
    background: #F8FAFC;
    border: 1px solid #AFC6EE;
    color: #1D4ED8;
}
QDateEdit#RegistrationDateEdit {
    min-height: 30px;
    max-height: 30px;
    padding: 0px 6px;
    margin: 0px;
}
QDateEdit#RegistrationDateEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 15px;
    border-left: 1px solid #CBD5E1;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background: #F8FAFC;
}
QDateEdit#RegistrationDateEdit::down-arrow {
    image: url(assets/combo_arrow_down.svg);
    width: 7px;
    height: 5px;
}
QLabel#TopDateLabel {
    background: #FFFFFF;
    border: 1px solid #D7E2F2;
    border-radius: 8px;
    padding: 0 6px;
    min-height: 30px;
    max-height: 30px;
    color: #1F3C88;
    font-size: 13px;
    font-weight: 800;
    min-width: 126px;
}
QPushButton#TopSyncButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1D4ED8);
    border: 1px solid #1D4ED8;
    border-radius: 8px;
    padding: 0 6px;
    min-height: 30px;
    max-height: 30px;
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 900;
    min-width: 104px;
}
QPushButton#TopSyncButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2E6EF0, stop:1 #1E40AF);
}
QPushButton#TopSyncButton:pressed {
    background: #1E40AF;
}
QPushButton#TopSyncButton:disabled {
    background: #CBD5E1;
    border: 1px solid #CBD5E1;
    color: #64748B;
}
QPushButton#TopRefreshButton {
    background: #FFFFFF;
    border: 1px solid #D7E2F2;
    border-radius: 8px;
    padding: 0 6px;
    min-height: 30px;
    max-height: 30px;
    color: #1F3C88;
    font-size: 13px;
    font-weight: 800;
}
QPushButton#TopRefreshButton:hover {
    background: #F8FAFC;
    border-color: #B7CAEA;
}
QPushButton#TopRefreshButton:pressed {
    background: #EEF4FF;
}



/* ---------------- HOME FILTER + TABLE MOCKUP ALIGN ---------------- */
QWidget#HomeFilterRow {
    background: transparent;
    border: none;
}
QLineEdit#HomeSearchField {
    background: #FBFCFE;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    border-radius: 9px;
    padding: 0 6px;
    font-size: 12px;
    font-weight: 700;
    min-height: 30px;
    max-height: 30px;
}
QLineEdit#HomeSearchField:focus {
    background: #FBFCFE;
    border: 1px solid #2563EB;
}
QComboBox#HomeFilterCombo {
    background: #FBFCFE;
    color: #24374F;
    border: 1px solid #CBD5E1;
    border-radius: 9px;
    padding: 0 6px 0 6px;
    font-size: 12px;
    font-weight: 700;
    min-height: 30px;
    max-height: 30px;
}
QComboBox#HomeFilterCombo:hover, QLineEdit#HomeSearchField:hover {
    border: 1px solid #BFD1EA;
}
QComboBox#HomeFilterCombo::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 15px;
    border-left: 1px solid #CBD5E1;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background: #F8FAFC;
}
QComboBox#HomeFilterCombo::down-arrow {
    image: url(assets/combo_arrow_down.svg);
    width: 7px;
    height: 5px;
}
QPushButton#HomeFilterResetButton {
    background: #FFFFFF;
    color: #35507A;
    border: 1px solid #D9E2EC;
    border-radius: 8px;
    padding: 0 6px;
    font-size: 12px;
    font-weight: 800;
    min-height: 30px;
    max-height: 30px;
}
QPushButton#HomeFilterResetButton:hover {
    background: #F8FAFC;
    border: 1px solid #BFD1EA;
    color: #1E40AF;
}
QTableWidget#HomeOverviewTable {
    background: #FFFFFF;
    alternate-background-color: #F8FAFC;
    color: #1E293B;
    border: 1px solid #D9E2EC;
    border-radius: 14px;
    padding: 0px;
    gridline-color: #E5EDF5;
    selection-background-color: #EEF4FF;
    selection-color: #1D4ED8;
}
QTableWidget#HomeOverviewTable QHeaderView::section {
    background: #F8FAFC;
    color: #4A607C;
    padding: 0 6px;
    border: none;
    border-bottom: 1px solid #E5EDF5;
    font-size: 13px;
    font-weight: 800;
    min-height: 40px;
}
QTableWidget#HomeOverviewTable::item {
    padding: 6px 6px;
    border-bottom: 1px solid #E5EDF5;
}
QTableWidget#HomeOverviewTable::item:selected {
    background: #EEF4FF;
    color: #1E40AF;
}

"""
