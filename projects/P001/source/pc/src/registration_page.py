from __future__ import annotations

import shutil
import re
from datetime import datetime
from copy import deepcopy
from math import hypot
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageQt, ImageOps
from PySide6.QtCore import QDate, QPointF, QRectF, Qt, Signal, QTimer, QRegularExpression
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QFileDialog,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .state import STATUS_TYPES
from .background_workers import FunctionWorkerThread
from .passport_ocr import extract_mrz_sync
from .passport_processor import auto_deskew_image, level_passport_by_mrz, extract_main_portrait, extract_portrait_aligned, analyze_passport_correction_quality
from .app_metadata import get_default_data_root
from .widgets import Panel, InnerScrollFrame, PAGE_OUTER_MARGINS, PAGE_OUTER_SPACING
from .transliteration_helper import transliterate_english_to_korean


NATIONS: list[str] = []
GENDER_OPTIONS = ["", "남성", "여성"]
WORK_TYPES = ["주간", "야간", "교대"]
PAY_TYPES = ["월급제", "일급제", "시급제"]
BANK_OPTIONS = [
    "은행 선택",
    "국민은행",
    "신한은행",
    "우리은행",
    "하나은행",
    "농협은행",
    "기업은행",
    "SC제일은행",
    "씨티은행",
    "대구은행",
    "부산은행",
    "경남은행",
    "광주은행",
    "전북은행",
    "제주은행",
    "수협은행",
    "새마을금고",
    "신협",
    "우체국",
    "카카오뱅크",
    "케이뱅크",
    "토스뱅크",
    "직접입력",
]

# 근로자등록 화면은 고정 작업화면 + 스크롤 이동 기준입니다.
# 화면이 작아져도 카드/폼/입력칸 크기를 줄이지 않고, 넘치는 부분은 스크롤로 이동합니다.
# 화면이 넓을 때 남는 오른쪽 회색 공간은 사원등록 영역 안에서만 흡수합니다.
REGISTRATION_WORK_WIDTH = 840
REGISTRATION_FORM_WIDTH = 760
REGISTRATION_SPLITTER_HANDLE_WIDTH = 6
REGISTRATION_CONTENT_WIDTH = REGISTRATION_WORK_WIDTH + REGISTRATION_FORM_WIDTH + REGISTRATION_SPLITTER_HANDLE_WIDTH
REGISTRATION_PAGE_WIDTH = REGISTRATION_CONTENT_WIDTH + PAGE_OUTER_MARGINS[0] + PAGE_OUTER_MARGINS[2]
REGISTRATION_FIELD_ROW_HEIGHT = 60
REGISTRATION_FIELD_COLUMN_WIDTH = 240


def _parse_base_wage_input(raw_text) -> tuple[bool, float, str]:
    """기본급/급여금액 입력값을 검증합니다. 빈칸은 허용하고, 입력된 경우 숫자만 허용합니다."""
    text = str(raw_text or "").strip().replace(",", "")
    if not text:
        return True, 0.0, ""
    if text.startswith("-"):
        return False, 0.0, "기본급은 0 이상으로 입력해 주세요."
    if any(not ch.isdigit() for ch in text):
        return False, 0.0, "기본급은 숫자와 쉼표만 입력해 주세요."
    try:
        value = float(text)
    except ValueError:
        return False, 0.0, "기본급은 숫자만 입력해 주세요."
    if value < 0:
        return False, 0.0, "기본급은 0 이상으로 입력해 주세요."
    return True, value, ""


def normalize_employee_document_kind(doc_type: str | None) -> str:
    raw = str(doc_type or "").strip().lower()
    if raw in {"residence_card", "overseas_resident_card", "idcard", "id_card", "arc"}:
        return "idcard"
    if raw in {"passport", "pp"}:
        return "passport"
    return "document"


def infer_employee_document_kind(doc_type: str | None, extracted_passport_no: str | None = None, id_no: str | None = None) -> str:
    normalized = normalize_employee_document_kind(doc_type)
    if normalized != "document":
        return normalized
    if str(extracted_passport_no or "").strip():
        return "passport"
    if str(id_no or "").strip():
        return "idcard"
    return "document"

STATUS_TYPES = ["근무중", "출근", "퇴근", "지각", "퇴사"]

def extract_passport_portrait(image: Image.Image | None) -> Image.Image | None:
    if image is None:
        return None

    portrait = extract_main_portrait(image)
    if portrait is None:
        width, height = image.size
        left = int(width * 0.055)
        top = int(height * 0.18)
        right = int(width * 0.33)
        bottom = int(height * 0.69)
        if right - left < 40 or bottom - top < 40:
            return None
        portrait = image.crop((left, top, right, bottom))

    # 등록 페이지에서 잡은 사진 영역은 강제로 증명사진 비율로 바꾸지 않고
    # 원본 크기와 비율을 그대로 유지합니다.
    return portrait.convert("RGB").copy()


def save_passport_portrait(image: Image.Image | None, employee_id: int, state=None) -> str:
    portrait = extract_passport_portrait(image)
    if portrait is None:
        return ""
    if state is not None and hasattr(state, "get_employee_portrait_storage_path"):
        portrait_path, rel_path = state.get_employee_portrait_storage_path(employee_id, ".png")
    else:
        base_dir = get_default_data_root() / "files" / "employees" / str(employee_id) / "portrait"
        base_dir.mkdir(parents=True, exist_ok=True)
        portrait_path = base_dir / "worker_photo.png"
        rel_path = str(Path("files") / "employees" / str(employee_id) / "portrait" / "worker_photo.png")
    portrait_path.parent.mkdir(parents=True, exist_ok=True)
    portrait.save(portrait_path)
    return rel_path


def save_portrait_image(image: Image.Image | None, employee_id: int, state=None) -> str:
    if image is None:
        return ""
    # 수동 사진 등록에서 지정한 영역은 저장 단계에서 다시 자르거나
    # 220x280으로 변환하지 않습니다. 사용자가 등록한 크기/비율 그대로 저장합니다.
    portrait = image.convert("RGB").copy()
    if state is not None and hasattr(state, "get_employee_portrait_storage_path"):
        portrait_path, rel_path = state.get_employee_portrait_storage_path(employee_id, ".png")
    else:
        base_dir = get_default_data_root() / "files" / "employees" / str(employee_id) / "portrait"
        base_dir.mkdir(parents=True, exist_ok=True)
        portrait_path = base_dir / "worker_photo.png"
        rel_path = str(Path("files") / "employees" / str(employee_id) / "portrait" / "worker_photo.png")
    portrait_path.parent.mkdir(parents=True, exist_ok=True)
    portrait.save(portrait_path)
    return rel_path


def copy_original_document_file(source_path: str | None, employee_id: int, document_kind: str | None = None, state=None) -> str:
    raw = str(source_path or "").strip()
    if not raw:
        return ""
    src = Path(raw)
    if not src.exists() or not src.is_file():
        return ""
    kind = normalize_employee_document_kind(document_kind)
    suffix = src.suffix or ".png"
    if state is not None and hasattr(state, "get_employee_original_document_storage_path"):
        target_path, rel_path = state.get_employee_original_document_storage_path(employee_id, kind, suffix)
    else:
        base_dir = get_default_data_root() / "files" / "employees" / str(employee_id) / "documents" / "original"
        base_dir.mkdir(parents=True, exist_ok=True)
        target_path = base_dir / f"{kind}_original{suffix.lower()}"
        rel_path = str(Path("files") / "employees" / str(employee_id) / "documents" / "original" / target_path.name)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if target_path.exists() and target_path.resolve() == src.resolve():
            return rel_path
    except OSError:
        pass
    shutil.copy2(src, target_path)
    return rel_path


def save_corrected_document(image: Image.Image | None, employee_id: int, document_kind: str | None = None, state=None) -> str:
    if image is None:
        return ""
    kind = normalize_employee_document_kind(document_kind)
    if state is not None and hasattr(state, "get_employee_corrected_document_storage_path"):
        document_path, rel_path = state.get_employee_corrected_document_storage_path(employee_id, kind, ".png")
    else:
        base_dir = get_default_data_root() / "files" / "employees" / str(employee_id) / "documents" / "corrected"
        base_dir.mkdir(parents=True, exist_ok=True)
        document_path = base_dir / f"{kind}_corrected.png"
        rel_path = str(Path("files") / "employees" / str(employee_id) / "documents" / "corrected" / document_path.name)
    document_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(document_path)
    return rel_path


class DocumentCanvas(QWidget):
    status_changed = Signal(str)
    image_loaded = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("DocumentCanvas")
        self.setMinimumHeight(520)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.original_image: Image.Image | None = None
        self.current_image: Image.Image | None = None
        self.current_path: str = ""
        self.zoom = 1.0
        self.edit_mode = False
        self.handles: list[QPointF] = []  # internal order: tl, tr, br, bl in image coordinates
        self.active_handle: int | None = None
        self.image_rect = QRectF()
        self.handle_radius = 10.0
        self.handle_labels = ["1", "2", "4", "3"]  # display labels: 1=tl, 2=tr, 3=bl, 4=br
        self._cached_pixmap: QPixmap | None = None
        self.is_corrected = False
        
        # 초상화 크롭 변수
        self.portrait_mode = False
        self.portrait_rect_norm = QRectF(0.60, 0.10, 0.35, 0.70)
        self.portrait_active_edge: str | None = None
        self.portrait_click_offset = QPointF()

    def has_image(self) -> bool:
        return self.current_image is not None

    def load_image(self, path: str):
        image = Image.open(path).convert("RGB")
        self.original_image = image.copy()
        self.current_image = image
        self.current_path = path
        self.zoom = 1.0
        self.edit_mode = False
        self.portrait_mode = False
        self.portrait_active_edge = None
        self.is_corrected = False
        self._reset_handles()
        self._update_pixmap_cache()
        self.image_loaded.emit(path)
        self.status_changed.emit("원본 사진을 불러왔습니다. 보정 시작을 눌러 4개 모서리를 조절해 주세요.")
        self.update()

    def set_default_sample(self, path: str):
        if Path(path).exists():
            self.load_image(path)

    def _update_pixmap_cache(self):
        if self.current_image is None:
            self._cached_pixmap = None
            return
        qimage = ImageQt.ImageQt(self.current_image.convert("RGBA"))
        self._cached_pixmap = QPixmap.fromImage(qimage)

    def _reset_handles(self):
        if self.current_image is None:
            self.handles = []
            return
        width, height = self.current_image.size
        pad_w = max(14.0, width * 0.03)
        pad_h = max(14.0, height * 0.03)
        self.handles = [
            QPointF(pad_w, pad_h),
            QPointF(width - pad_w, pad_h),
            QPointF(width - pad_w, height - pad_h),
            QPointF(pad_w, height - pad_h),
        ]

    def _default_portrait_rect_norm(self) -> QRectF:
        if self.current_image is None:
            return QRectF(0.60, 0.10, 0.35, 0.70)
        width, height = self.current_image.size
        ratio = (width / height) if height else 0.0
        if 1.30 <= ratio <= 1.95:
            # 카드형 기본값은 우측 사진형 카드에 맞추되, 자동 후보가 있으면 begin_portrait_crop에서 교체됩니다.
            return QRectF(0.60, 0.10, 0.35, 0.70)
        # 여권 정보면 기본값: 좌측 얼굴사진 영역
        return QRectF(0.05, 0.18, 0.28, 0.51)

    def _normalized_portrait_rect(self, rect: QRectF | tuple | None = None) -> QRectF:
        if rect is None:
            rect = self.portrait_rect_norm if not self.portrait_rect_norm.isNull() else self._default_portrait_rect_norm()
        if not isinstance(rect, QRectF):
            try:
                rect = QRectF(float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
            except Exception:
                rect = self._default_portrait_rect_norm()

        rect = QRectF(rect).normalized()
        min_w = 0.04
        min_h = 0.06
        w = max(min_w, min(1.0, float(rect.width())))
        h = max(min_h, min(1.0, float(rect.height())))
        x = max(0.0, min(1.0 - w, float(rect.x())))
        y = max(0.0, min(1.0 - h, float(rect.y())))
        if x + w > 1.0:
            x = max(0.0, 1.0 - w)
        if y + h > 1.0:
            y = max(0.0, 1.0 - h)
        return QRectF(x, y, w, h)

    def _set_portrait_rect_norm(self, rect: QRectF | tuple | None):
        self.portrait_rect_norm = self._normalized_portrait_rect(rect)

    def _order_handles(self, points: list[QPointF]) -> list[QPointF]:
        """Ensure internal order is tl, tr, br, bl for stable perspective transform."""
        if len(points) != 4:
            return points
        sorted_by_y = sorted(points, key=lambda p: (p.y(), p.x()))
        top_two = sorted(sorted_by_y[:2], key=lambda p: p.x())
        bottom_two = sorted(sorted_by_y[2:], key=lambda p: p.x())
        tl, tr = top_two[0], top_two[1]
        bl, br = bottom_two[0], bottom_two[1]
        return [tl, tr, br, bl]

    def _display_label_for_handle_index(self, index: int) -> str:
        """Screen label mapping: 1=tl, 2=tr, 3=bl, 4=br while internal order stays tl,tr,br,bl."""
        return ["1", "2", "4", "3"][index] if 0 <= index < 4 else str(index + 1)

    def begin_correction(self):
        if self.current_image is None:
            self.status_changed.emit("먼저 원본 사진을 등록해 주세요.")
            return
        self.portrait_mode = False
        self.portrait_active_edge = None
        self.edit_mode = True
        
        try:
            from .passport_processor import find_document_corners
            corners = find_document_corners(self.current_image)
            if corners and len(corners) == 4:
                detected = [QPointF(x, y) for x, y in corners]
                self.handles = self._order_handles(detected)
                # Keep edit handles visible in correction mode.
                # User should explicitly click "보정적용" after fine-tuning.
                self.edit_mode = True
                self.status_changed.emit("자동으로 4점이 배치되었습니다. 1 좌상 · 2 우상 · 3 좌하 · 4 우하 순서로 확인한 뒤 보정적용을 눌러 주세요.")
            else:
                self._reset_handles()
                self.status_changed.emit("보정 모드입니다. 1 좌상 · 2 우상 · 3 좌하 · 4 우하 순서로 문서 모서리에 맞춘 뒤 보정적용을 눌러 주세요.")
        except Exception as e:
            print(f"Auto-crop error: {e}")
            self._reset_handles()
            self.status_changed.emit("보정 모드입니다. 1 좌상 · 2 우상 · 3 좌하 · 4 우하 순서로 4개 점을 드래그해 주세요.")
            
        self.update()

    def rotate_left(self):
        if self.current_image is None:
            return
        self.current_image = self.current_image.rotate(90, expand=True)
        self._reset_handles()
        self._update_pixmap_cache()
        self.status_changed.emit("이미지를 왼쪽으로 회전했습니다.")
        self.update()

    def rotate_right(self):
        if self.current_image is None:
            return
        self.current_image = self.current_image.rotate(-90, expand=True)
        self._reset_handles()
        self._update_pixmap_cache()
        self.status_changed.emit("이미지를 오른쪽으로 회전했습니다.")
        self.update()

    def zoom_in(self):
        if self.current_image is None:
            return
        self.zoom = min(3.0, self.zoom + 0.15)
        self.status_changed.emit(f"확대 배율 {self.zoom:.2f}x")
        self.update()

    def zoom_out(self):
        if self.current_image is None:
            return
        self.zoom = max(0.35, self.zoom - 0.15)
        self.status_changed.emit(f"축소 배율 {self.zoom:.2f}x")
        self.update()

    def reset_original(self):
        if self.original_image is None:
            return
        self.current_image = self.original_image.copy()
        self.zoom = 1.0
        self.edit_mode = False
        self.portrait_mode = False
        self.portrait_active_edge = None
        self.is_corrected = False
        self._reset_handles()
        self._update_pixmap_cache()
        self.status_changed.emit("원본 사진으로 복원했습니다.")
        self.update()

    def apply_correction(self) -> Image.Image | None:
        if self.current_image is None:
            self.status_changed.emit("보정할 원본 사진이 없습니다.")
            return None
        if len(self.handles) != 4:
            self.status_changed.emit("모서리 4개 점이 준비되지 않았습니다.")
            return None

        tl, tr, br, bl = self.handles
        width_top = hypot(tr.x() - tl.x(), tr.y() - tl.y())
        width_bottom = hypot(br.x() - bl.x(), br.y() - bl.y())
        height_left = hypot(bl.x() - tl.x(), bl.y() - tl.y())
        height_right = hypot(br.x() - tr.x(), br.y() - tr.y())
        target_w = max(220, int(max(width_top, width_bottom)))
        target_h = max(140, int(max(height_left, height_right)))

        try:
            quad = (
                tl.x(), tl.y(),
                bl.x(), bl.y(),
                br.x(), br.y(),
                tr.x(), tr.y(),
            )
            resample = getattr(Image, "Resampling", Image).BICUBIC
            corrected = self.current_image.transform((target_w, target_h), Image.Transform.QUAD, quad, resample)
            corrected, mrz_angle = level_passport_by_mrz(corrected, max_abs_angle=8.0)
            self.current_image = corrected
            self.zoom = 1.0
            self.edit_mode = False
            self.portrait_mode = False
            self.portrait_active_edge = None
            self.is_corrected = True
            self._reset_handles()
            self._update_pixmap_cache()
            if abs(locals().get("mrz_angle", 0.0)) >= 0.08:
                self.status_changed.emit(f"문서 보정을 적용했습니다. MRZ 기준으로 {mrz_angle:+.2f}° 추가 수평 보정했습니다.")
            else:
                self.status_changed.emit("문서 보정을 적용했습니다. 결과를 확인한 뒤 저장하거나 다시 보정할 수 있습니다.")
            self.update()
            return corrected
        except Exception as exc:
            self.status_changed.emit(f"보정 적용 중 오류: {exc}")
            return None

    def _enhance_corrected_document(self, image: Image.Image) -> Image.Image:
        enhanced = ImageOps.autocontrast(image.convert("RGB"), cutoff=1)
        enhanced = ImageEnhance.Contrast(enhanced).enhance(1.18)
        return enhanced

    def auto_correct_document(self) -> Image.Image | None:
        if self.current_image is None:
            self.status_changed.emit("자동 보정할 이미지가 없습니다.")
            return None

        try:
            if self.is_corrected and not self.edit_mode:
                corrected = self._enhance_corrected_document(self.current_image)
                rotated, angle = auto_deskew_image(corrected, max_abs_angle=15.0)
                rotated, mrz_angle = level_passport_by_mrz(rotated, max_abs_angle=8.0)
                angle += mrz_angle
                self.current_image = rotated
                self.zoom = 1.0
                self.portrait_mode = False
                self.portrait_active_edge = None
                self._reset_handles()
                self._update_pixmap_cache()
                if abs(angle) < 0.08:
                    self.status_changed.emit("자동 보정 완료: 대비를 보정했습니다.")
                else:
                    self.status_changed.emit(f"자동 보정 완료: 대비와 기울기 {angle:+.2f}도를 보정했습니다.")
                self.update()
                return rotated

            from .passport_processor import find_document_corners
            corners = find_document_corners(self.current_image)
            if corners and len(corners) == 4:
                self.handles = self._order_handles([QPointF(x, y) for x, y in corners])
                self.edit_mode = True
            elif len(self.handles) != 4:
                self._reset_handles()
                self.edit_mode = True
                self.status_changed.emit("자동으로 모서리를 찾지 못했습니다. 4개 점을 맞춘 뒤 보정적용을 눌러 주세요.")
                self.update()
                return None

            corrected = self.apply_correction()
            if corrected is None:
                return None

            corrected = self._enhance_corrected_document(corrected)
            rotated, angle = auto_deskew_image(corrected, max_abs_angle=15.0)
            rotated, mrz_angle = level_passport_by_mrz(rotated, max_abs_angle=8.0)
            angle += mrz_angle
            self.current_image = rotated
            self.zoom = 1.0
            self.edit_mode = False
            self.portrait_mode = False
            self.portrait_active_edge = None
            self.is_corrected = True
            self._reset_handles()
            self._update_pixmap_cache()
            if abs(angle) < 0.08:
                self.status_changed.emit("자동 보정 완료: 문서를 펴고 대비를 보정했습니다.")
            else:
                self.status_changed.emit(f"자동 보정 완료: 문서를 펴고 기울기 {angle:+.2f}도를 보정했습니다.")
            self.update()
            return rotated
        except Exception as exc:
            self._reset_handles()
            self.edit_mode = True
            self.status_changed.emit(f"자동 보정 실패: 4개 모서리를 직접 맞춘 뒤 보정적용을 눌러 주세요. ({exc})")
            self.update()
            return None

    def auto_deskew(self) -> Image.Image | None:
        if self.current_image is None:
            self.status_changed.emit("기울기 보정할 이미지가 없습니다.")
            return None
        if self.edit_mode:
            self.status_changed.emit("먼저 보정적용을 완료한 뒤 기울기를 눌러 주세요.")
            return None
        if not self.is_corrected:
            self.status_changed.emit("기울기는 보조 기능입니다. 보정 시작 → 보정적용 후 사용해 주세요.")
            return None

        try:
            rotated, angle = auto_deskew_image(self.current_image)
            rotated, mrz_angle = level_passport_by_mrz(rotated, max_abs_angle=8.0)
            angle += mrz_angle
            self.current_image = rotated
            self.zoom = 1.0
            self._reset_handles()
            self._update_pixmap_cache()
            if abs(angle) < 0.08:
                self.status_changed.emit("기울기 자동 보정: 추가 회전이 필요하지 않았습니다.")
            else:
                self.status_changed.emit(f"기울기 자동 보정 완료 ({angle:+.2f}°)")
            self.update()
            return rotated
        except Exception as exc:
            self.status_changed.emit(f"기울기 자동 보정 중 오류: {exc}")
            return None

    def begin_portrait_crop(self):
        if self.current_image is None:
            self.status_changed.emit("먼저 원본 사진을 등록해 주세요.")
            return

        self.portrait_mode = True
        self.edit_mode = False
        self.active_handle = None
        self.portrait_active_edge = None
        self.zoom = 1.0
        self._update_pixmap_cache()

        # 사진추출은 반자동 후보만 배치합니다. 저장용 확정은 ⑧ 사진확인에서만 처리합니다.
        try:
            from .passport_processor import estimate_portrait_rect
            norm = estimate_portrait_rect(self.current_image)
            self._set_portrait_rect_norm(norm or self._default_portrait_rect_norm())
            self.status_changed.emit("초록 박스를 얼굴사진에 맞춰 이동/크기조절한 뒤 ⑧ 사진확인을 눌러주세요.")
        except Exception as e:
            print("Portrait detection error:", e)
            self._set_portrait_rect_norm(self._default_portrait_rect_norm())
            self.status_changed.emit("얼굴 후보를 자동으로 찾지 못했습니다. 초록 박스를 사진 영역에 맞춘 뒤 ⑧ 사진확인을 눌러 주세요.")

        self.update()

    def _crop_portrait_from_current_rect(self, finish: bool = False) -> Image.Image | None:
        if self.current_image is None:
            return None

        w, h = self.current_image.size
        pr = self._normalized_portrait_rect(self.portrait_rect_norm)
        self.portrait_rect_norm = pr
        px = max(0, min(w - 1, int(round(pr.x() * w))))
        py = max(0, min(h - 1, int(round(pr.y() * h))))
        pw = max(1, min(w - px, int(round(pr.width() * w))))
        ph = max(1, min(h - py, int(round(pr.height() * h))))

        if pw < 20 or ph < 20:
            return None

        cropped = self.current_image.crop((px, py, px + pw, py + ph)).convert("RGB").copy()
        if finish:
            self.portrait_mode = False
            self.update()
        return cropped

    def preview_portrait_image(self) -> Image.Image | None:
        """Return the current portrait crop without leaving photo-adjust mode."""
        return self._crop_portrait_from_current_rect(finish=False)

    def get_portrait_image(self) -> Image.Image | None:
        if self.current_image is None or not self.portrait_mode:
            return None
        return self._crop_portrait_from_current_rect(finish=True)

    def _image_to_widget(self, point: QPointF) -> QPointF:
        if self.current_image is None or self.image_rect.width() <= 0 or self.image_rect.height() <= 0:
            return QPointF()
        width, height = self.current_image.size
        x = self.image_rect.left() + (point.x() / width) * self.image_rect.width()
        y = self.image_rect.top() + (point.y() / height) * self.image_rect.height()
        return QPointF(x, y)

    def _widget_to_image(self, point: QPointF) -> QPointF:
        if self.current_image is None or self.image_rect.width() <= 0 or self.image_rect.height() <= 0:
            return QPointF()
        width, height = self.current_image.size
        x = (point.x() - self.image_rect.left()) / self.image_rect.width() * width
        y = (point.y() - self.image_rect.top()) / self.image_rect.height() * height
        x = min(max(0.0, x), width)
        y = min(max(0.0, y), height)
        return QPointF(x, y)

    def _compute_image_rect(self) -> QRectF:
        if self.current_image is None:
            return QRectF()
        img_w, img_h = self.current_image.size
        avail_w = max(100.0, self.width() - 36.0)
        avail_h = max(100.0, self.height() - 36.0)
        scale = min(avail_w / img_w, avail_h / img_h) * self.zoom
        draw_w = img_w * scale
        draw_h = img_h * scale
        x = (self.width() - draw_w) / 2.0
        y = (self.height() - draw_h) / 2.0
        return QRectF(x, y, draw_w, draw_h)

    def _get_portrait_pixel_rect(self) -> QRectF:
        if self.image_rect.isEmpty():
            return QRectF()
        pr = self._normalized_portrait_rect(self.portrait_rect_norm)
        self.portrait_rect_norm = pr
        x = self.image_rect.x() + pr.x() * self.image_rect.width()
        y = self.image_rect.y() + pr.y() * self.image_rect.height()
        w = pr.width() * self.image_rect.width()
        h = pr.height() * self.image_rect.height()
        return QRectF(x, y, w, h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#eef3fb"))

        if self.current_image is None or self._cached_pixmap is None:
            painter.setPen(QColor("#7f90ab"))
            painter.drawText(self.rect(), Qt.AlignCenter, "원본 사진을 등록하면\n여기서 보정 작업 화면이 표시됩니다.")
            return

        self.image_rect = self._compute_image_rect()
        target = self.image_rect.toRect()
        painter.drawPixmap(target, self._cached_pixmap)

        # Desktop Crop Box Overlay
        if self.portrait_mode:
            prect = self._get_portrait_pixel_rect()
            
            # Dim the surrounding area
            dim = QColor(0, 0, 0, 140)
            painter.fillRect(QRectF(self.image_rect.left(), self.image_rect.top(), self.image_rect.width(), prect.top() - self.image_rect.top()), dim)
            painter.fillRect(QRectF(self.image_rect.left(), prect.bottom(), self.image_rect.width(), self.image_rect.bottom() - prect.bottom()), dim)
            painter.fillRect(QRectF(self.image_rect.left(), prect.top(), prect.left() - self.image_rect.left(), prect.height()), dim)
            painter.fillRect(QRectF(prect.right(), prect.top(), self.image_rect.right() - prect.right(), prect.height()), dim)
            
            # 2px border
            painter.setPen(QPen(QColor("#00ff66"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(prect)
            
            # Handle corners: 1=left top, 2=right top, 3=left bottom, 4=right bottom
            painter.setBrush(QColor("#00ff66"))
            s = 8
            crop_points = [
                (prect.left(), prect.top(), "1"),
                (prect.right(), prect.top(), "2"),
                (prect.left(), prect.bottom(), "3"),
                (prect.right(), prect.bottom(), "4"),
            ]
            for hx, hy, _label in crop_points:
                painter.drawRect(QRectF(hx - s/2, hy - s/2, s, s))

            number_font = QFont(painter.font())
            number_font.setBold(True)
            painter.setFont(number_font)
            for hx, hy, label in crop_points:
                badge_x = hx + 7
                badge_y = hy - 25
                if label in ("2", "4"):
                    badge_x = hx - 25
                if label in ("3", "4"):
                    badge_y = hy + 7
                badge_rect = QRectF(badge_x, badge_y, 18, 18)
                painter.setBrush(QColor("#00aa44"))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(badge_rect)
                painter.setPen(QColor("#ffffff"))
                painter.drawText(badge_rect, Qt.AlignCenter, label)
                painter.setBrush(QColor("#00ff66"))
                
        elif self.edit_mode and len(self.handles) == 4:
            pen = QPen(QColor("#2452d8"), 2)
            painter.setPen(pen)
            points = [self._image_to_widget(p) for p in self.handles]
            for i in range(4):
                painter.drawLine(points[i], points[(i + 1) % 4])

            number_font = QFont(painter.font())
            number_font.setPointSize(9)
            number_font.setBold(True)
            painter.setFont(number_font)

            for idx, point in enumerate(points):
                is_active = idx == self.active_handle
                painter.setBrush(QColor("#ffffff" if not is_active else "#d9e6ff"))
                painter.setPen(QPen(QColor("#2452d8"), 2))
                painter.drawEllipse(point, self.handle_radius, self.handle_radius)

                badge_rect = QRectF(
                    point.x() + self.handle_radius - 2,
                    point.y() - self.handle_radius - 14,
                    18,
                    18,
                )
                painter.setBrush(QColor("#2452d8" if not is_active else "#16389d"))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(badge_rect)
                painter.setPen(QColor("#ffffff"))
                painter.drawText(badge_rect, Qt.AlignCenter, self._display_label_for_handle_index(idx))

    def mousePressEvent(self, event):
        if self.current_image is None: return
        pos = QPointF(event.position())
        
        if self.portrait_mode:
            prect = self._get_portrait_pixel_rect()
            s = 15  # grip threshold
            if prect.adjusted(-s, -s, s, s).contains(pos) and not prect.adjusted(s, s, -s, -s).contains(pos):
                # Edge or corner detection
                dx1, dx2 = abs(pos.x() - prect.left()), abs(pos.x() - prect.right())
                dy1, dy2 = abs(pos.y() - prect.top()), abs(pos.y() - prect.bottom())
                edge = ""
                if dy1 < s: edge += "t"
                if dy2 < s: edge += "b"
                if dx1 < s: edge += "l"
                if dx2 < s: edge += "r"
                self.portrait_active_edge = edge if edge else None
            elif prect.contains(pos):
                self.portrait_active_edge = "center"
                self.portrait_click_offset = pos - prect.topLeft()
            return

        if not self.edit_mode: return
        for index, handle in enumerate(self.handles):
            widget_point = self._image_to_widget(handle)
            if hypot(widget_point.x() - pos.x(), widget_point.y() - pos.y()) <= self.handle_radius + 6:
                self.active_handle = index
                self.update()
                return

    def mouseMoveEvent(self, event):
        if self.current_image is None: return
        pos = QPointF(event.position())
        
        if self.portrait_mode and self.portrait_active_edge:
            if self.image_rect.width() <= 0 or self.image_rect.height() <= 0:
                return
            pr = self._normalized_portrait_rect(self.portrait_rect_norm)
            # Convert widget pos to normalized
            nx = (pos.x() - self.image_rect.x()) / self.image_rect.width()
            ny = (pos.y() - self.image_rect.y()) / self.image_rect.height()
            nx = max(0.0, min(1.0, nx))
            ny = max(0.0, min(1.0, ny))

            if self.portrait_active_edge == "center":
                cw = pr.width()
                ch = pr.height()
                nox = (pos.x() - self.portrait_click_offset.x() - self.image_rect.x()) / self.image_rect.width()
                noy = (pos.y() - self.portrait_click_offset.y() - self.image_rect.y()) / self.image_rect.height()
                nox = max(0.0, min(1.0 - cw, nox))
                noy = max(0.0, min(1.0 - ch, noy))
                self._set_portrait_rect_norm(QRectF(nox, noy, cw, ch))
            else:
                edge = self.portrait_active_edge
                if "t" in edge:
                    pr.setTop(min(ny, pr.bottom() - 0.06))
                if "b" in edge:
                    pr.setBottom(max(ny, pr.top() + 0.06))
                if "l" in edge:
                    pr.setLeft(min(nx, pr.right() - 0.04))
                if "r" in edge:
                    pr.setRight(max(nx, pr.left() + 0.04))
                self._set_portrait_rect_norm(pr)
            self.update()
            return
            
        if self.active_handle is None or not self.edit_mode: return
        mapped = self._widget_to_image(pos)
        self.handles[self.active_handle] = mapped
        self.update()

    def mouseReleaseEvent(self, event):
        self.active_handle = None
        self.portrait_active_edge = None
        self.update()


DocumentCorrectionCanvas = DocumentCanvas


class LockedSplitter(QSplitter):
    """분할선 드래그는 막고, 좌우/상하 영역 간격은 공통 기준 6px로 유지하는 스플리터."""

    GAP = 6

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setChildrenCollapsible(False)
        self.setHandleWidth(self.GAP)
        self.setStyleSheet("""
            QSplitter::handle {
                background: transparent;
                border: 0px;
                width: 6px;
                height: 6px;
            }
        """)

    def lock_handles(self):
        self.setHandleWidth(self.GAP)
        for idx in range(1, self.count()):
            handle = self.handle(idx)
            if handle is not None:
                handle.setEnabled(False)
                handle.setVisible(True)
                handle.setCursor(Qt.ArrowCursor)
                if self.orientation() == Qt.Horizontal:
                    handle.setFixedWidth(self.GAP)
                else:
                    handle.setFixedHeight(self.GAP)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.lock_handles)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.lock_handles)


class ManagerRegistrationDialog(QDialog):
    def __init__(self, parent=None, *, employee_id: int = 0, employee_name: str = "", phone: str = "", business: str = "", work_site: str = "", businesses: list[str] | None = None, work_sites: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("담당자 등록")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        note = QLabel("모바일 일반 관리자 계정만 등록합니다. 담당 사업자와 근무사업장 배정은 설정 > 관리자설정에서 관리합니다.")
        note.setObjectName("PanelNote")
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(6)

        self.employee_id = int(employee_id or 0)
        self.name_edit = QLineEdit(employee_name)
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.phone_edit = QLineEdit(phone)
        self.active_check = QCheckBox("사용")
        self.active_check.setChecked(True)
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("선택 입력")

        self.username_edit.setPlaceholderText("모바일 로그인 아이디")
        self.password_edit.setPlaceholderText("모바일 로그인 비밀번호")

        form.addRow("담당자명", self.name_edit)
        form.addRow("아이디", self.username_edit)
        form.addRow("비밀번호", self.password_edit)
        form.addRow("연락처", self.phone_edit)
        form.addRow("사용 여부", self.active_check)
        form.addRow("메모", self.note_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        cancel_btn = QPushButton("취소")
        save_btn = QPushButton("담당자 저장")
        cancel_btn.setObjectName("GhostButton")
        save_btn.setObjectName("PrimaryButton")
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(save_btn, QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def payload(self) -> dict:
        return {
            "employee_id": self.employee_id,
            "employee_name": self.name_edit.text().strip(),
            "username": self.username_edit.text().strip(),
            "password": self.password_edit.text().strip(),
            "phone": self.phone_edit.text().strip(),
            "active": self.active_check.isChecked(),
            "note": self.note_edit.text().strip(),
        }

class RegistrationPage(QWidget):
    request_back = Signal()
    employee_saved = Signal(dict)

    def __init__(self, state):
        super().__init__()
        self.state = state
        self._default_employee_id = 1001
        self.current_image_path = ""
        self._portrait_image: Image.Image | None = None
        self._main_splitter_initialized = False
        self._mrz_worker: FunctionWorkerThread | None = None
        self._name_edited_by_user = False
        self._last_doc_type = ""
        self._auto_name_for_save = ""
        self._company_manual_mode = False
        self._registration_mode = "new"
        self._editing_employee: dict | None = None
        self._loading_existing_media = False
        self._media_changed = False
        self._portrait_changed = False
        self._extract_progress_messages = [
            "자동 인식 준비 중",
            "빠른 인식 중",
            "보정 인식 중",
            "정밀 인식 중",
            "추가 보정 검사 중",
        ]
        self._extract_progress_index = 0
        self._extract_progress_timer = QTimer(self)
        self._extract_progress_timer.setInterval(850)
        self._extract_progress_timer.timeout.connect(self._advance_extract_progress_message)
        self._build_ui()
        self._refresh_company_options()
        self.prepare_new_employee(self.state.next_employee_id())
        self.state.employees_changed.connect(self._refresh_company_options)

    def _build_ui(self):
        # 화면 축소 시 내용이 먼저 압축되지 않도록 등록 작업화면 폭을 유지합니다.
        self.setMinimumWidth(REGISTRATION_PAGE_WIDTH)
        root = QVBoxLayout(self)
        root.setContentsMargins(*PAGE_OUTER_MARGINS)
        root.setSpacing(PAGE_OUTER_SPACING)
        # 바깥 큰 테두리는 제거하고, 작업 내용은 크기 유지 + 스크롤 이동 기준으로 처리합니다.

        compact_hero = QFrame()
        compact_hero.setObjectName("CompactHero")
        compact_hero.setFixedHeight(78)
        compact_layout = QHBoxLayout(compact_hero)
        compact_layout.setContentsMargins(6, 6, 6, 6)
        compact_layout.setSpacing(6)

        text_box = QVBoxLayout()
        text_box.setSpacing(6)
        badge = QLabel("사원 등록")
        badge.setObjectName("HeroBadge")
        title = QLabel("사원등록 작업화면")
        title.setObjectName("HeroTitle")
        sub = QLabel("① 원본등록 → ② 보정시작 → ③ 4점찾기 → ④ 보정적용 순서로 작업합니다.")
        sub.setObjectName("HeroDesc")
        sub.setWordWrap(True)
        text_box.addWidget(badge)
        text_box.addWidget(title)
        text_box.addWidget(sub)
        text_box.addStretch()
        compact_layout.addLayout(text_box, 1)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        for text in ["① 원본등록", "③ 4점찾기", "④ 보정적용"]:
            chip = QLabel(text)
            chip.setObjectName("HeroChip")
            chips.addWidget(chip)
        compact_layout.addLayout(chips)
        # 상단 고정 배너는 MainWindow에서 표시합니다.

        toolbar_panel = Panel("문서 보정 도구", "상단은 간단히, 작업영역은 넓게 사용합니다.", icon_name="settings")
        toolbar_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.open_btn = QPushButton("① 원본등록")
        self.open_btn.setObjectName("PrimaryButton")
        self.open_btn.clicked.connect(self.open_image)
        toolbar.addWidget(self.open_btn)

        self.correct_btn = QPushButton("② 보정시작")
        self.correct_btn.setObjectName("GhostButton")
        self.correct_btn.clicked.connect(self.begin_correction)
        toolbar.addWidget(self.correct_btn)


        self.auto_correct_btn = QPushButton("③ 4점찾기")
        self.auto_correct_btn.setObjectName("GhostButton")
        self.auto_correct_btn.clicked.connect(self.auto_correct)
        toolbar.addWidget(self.auto_correct_btn)

        for text, handler in [
            ("원본", self.reset_original),
        ]:
            button = QPushButton(text)
            button.setObjectName("GhostButton")
            button.clicked.connect(handler)
            toolbar.addWidget(button)

        apply_btn = QPushButton("④ 보정적용")
        apply_btn.setObjectName("PrimaryButton")
        apply_btn.clicked.connect(self.apply_correction)
        toolbar.addWidget(apply_btn)

        self.crop_portrait_btn = QPushButton("⑦ 사진추출")
        self.crop_portrait_btn.setObjectName("GhostButton")
        self.crop_portrait_btn.clicked.connect(self._begin_portrait_crop)
        toolbar.addWidget(self.crop_portrait_btn)

        self.apply_portrait_btn = QPushButton("⑧ 사진확인")
        self.apply_portrait_btn.setObjectName("PrimaryButton")
        self.apply_portrait_btn.clicked.connect(self._apply_portrait_crop)
        self.apply_portrait_btn.hide()
        toolbar.addWidget(self.apply_portrait_btn)

        toolbar.addStretch()

        go_list_btn = QPushButton("직원관리")
        go_list_btn.setObjectName("GhostButton")
        go_list_btn.clicked.connect(self.request_back.emit)
        toolbar.addWidget(go_list_btn)
        toolbar_panel.body_layout.addLayout(toolbar)

        info_card = QFrame()
        info_card.setObjectName("StatusRow")
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(6, 6, 6, 6)
        info_layout.setSpacing(6)
        self.file_label = QLabel("다음 등록 예정 번호: -")
        self.file_label.setObjectName("StatusText")
        self.preview_path = QLabel("파일을 등록하면 여기에 파일명이 표시됩니다.")
        self.preview_path.setObjectName("StatusText")
        self.preview_path.setWordWrap(True)
        self.status_label = QLabel("이미지 업로드 대기")
        self.status_label.setObjectName("StatusText")
        self.status_label.setWordWrap(True)
        info_layout.addWidget(self.file_label)
        info_layout.addWidget(self.preview_path)
        info_layout.addWidget(self.status_label)
        toolbar_panel.body_layout.addWidget(info_card)

        work_splitter = LockedSplitter(Qt.Horizontal)
        work_splitter.setChildrenCollapsible(False)
        work_splitter.setHandleWidth(6)

        origin_panel = Panel("원본 / 안내", "")
        self.origin_panel = origin_panel
        origin_panel.setMinimumWidth(210)
        origin_panel.setMaximumWidth(320)
        origin_panel.header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        origin_panel.body_layout.setContentsMargins(6, 6, 6, 6)
        origin_panel.body_layout.setSpacing(6)
        origin_panel.body_layout.setAlignment(Qt.AlignTop)
        self._origin_preview_ratio = 0.54

        guide_card = QFrame()
        guide_card.setObjectName("OriginGuideCard")
        guide_layout = QVBoxLayout(guide_card)
        guide_layout.setContentsMargins(6, 6, 6, 6)
        guide_layout.setSpacing(4)
        guide_title = QLabel("등록 전 확인")
        guide_title.setObjectName("OriginGuideTitle")
        guide = QLabel("1. 원본사진 등록\n2. 보정시작 또는 4점찾기\n3. 보정적용 후 결과 확인\n4. 오른쪽 자동추출 확인\n5. 사진추출 / 사진확인")
        guide.setWordWrap(True)
        guide.setObjectName("OriginGuideText")
        guide_layout.addWidget(guide_title)
        guide_layout.addWidget(guide)
        origin_panel.body_layout.addWidget(guide_card)

        self.left_portrait_preview = QLabel("추출된 사진")
        self.left_portrait_preview.setAlignment(Qt.AlignCenter)
        self.left_portrait_preview.setFixedSize(110, 132)
        self.left_portrait_preview.setStyleSheet("""
            QLabel {
                background: #F8FAFC;
                border: 2px solid #C9D6EA;
                border-radius: 10px;
                color: #7083A3;
                font-weight: bold;
            }
        """)
        origin_panel.body_layout.addWidget(self.left_portrait_preview, 0, Qt.AlignCenter)

        self.origin_preview = QLabel("원본 미리보기")
        self.origin_preview.setAlignment(Qt.AlignCenter)
        self.origin_preview.setMinimumWidth(190)
        self.origin_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.origin_preview.setStyleSheet("background:#F8FAFC; border:1px dashed #C9D6EA; border-radius:14px; color:#7083A3; font-size:12px; font-weight:700;")
        origin_panel.body_layout.addWidget(self.origin_preview)
        self._update_origin_preview_box_size()

        work_panel = Panel("문서 보정 작업영역", "4점 조절 / ③ 4점찾기 / ④ 보정적용")
        self.canvas = DocumentCorrectionCanvas()
        self.canvas.setMinimumHeight(300)
        self.canvas.status_changed.connect(self.status_label.setText)
        self.canvas.image_loaded.connect(self._on_image_loaded)
        work_panel.body_layout.addWidget(self.canvas)
        work_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        work_splitter.addWidget(origin_panel)
        work_splitter.addWidget(work_panel)
        work_splitter.setStretchFactor(0, 0)
        work_splitter.setStretchFactor(1, 1)
        work_splitter.setSizes([280, 600])
        QTimer.singleShot(0, work_splitter.lock_handles)

        form_panel = Panel("사원등록 기본 정보", "문서정보와 회사 입력 정보를 나누어 정리합니다.", icon_name="registration")
        form_panel.body_layout.setAlignment(Qt.AlignTop)

        self.business_combo = QComboBox()
        self.business_combo.setEditable(True)
        self.business_combo.currentTextChanged.connect(self._refresh_client_options)
        self.client_combo = QComboBox()
        self.client_combo.setEditable(True)
        self.name_edit = QLineEdit()
        self.name_edit.textEdited.connect(self._mark_name_edited)
        self.english_name_edit = QLineEdit()
        self.nation_combo = QComboBox()
        self.nation_combo.setEditable(True)
        self.nation_combo.setInsertPolicy(QComboBox.NoInsert)
        self.nation_combo.setPlaceholderText("국적 자동추출 또는 직접 입력")
        self.nation_combo.addItems(NATIONS)
        self._extracted_passport_no = ""
        self.id_number_edit = QLineEdit()
        self.birth_date_edit = QDateEdit()
        self.birth_date_edit.setCalendarPopup(True)
        self.birth_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.birth_date_edit.setMinimumDate(QDate(1900, 1, 1))
        self.birth_date_edit.setSpecialValueText("")
        self.gender_combo = QComboBox()
        self.gender_combo.addItems(GENDER_OPTIONS)
        self.phone_edit = QLineEdit()
        self.hire_date_edit = QDateEdit()
        self.hire_date_edit.setCalendarPopup(True)
        self.hire_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.hire_date_edit.setMinimumDate(QDate(1900, 1, 1))
        self.hire_date_edit.setSpecialValueText("")
        self.pay_type_combo = QComboBox()
        self.pay_type_combo.setEditable(True)
        self.pay_type_combo.addItems(PAY_TYPES)
        self.work_type_combo = QComboBox()
        self.work_type_combo.setEditable(True)
        self.work_type_combo.addItems(WORK_TYPES)
        self.base_wage_edit = QLineEdit()
        self.base_wage_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9,]*$"), self.base_wage_edit))
        self.base_wage_edit.setPlaceholderText("예: 2000000")
        self.bank_name_combo = QComboBox()
        self.bank_name_combo.setEditable(True)
        self.bank_name_combo.setInsertPolicy(QComboBox.NoInsert)
        self.bank_name_combo.addItems(BANK_OPTIONS)
        self.bank_name_combo.setCurrentText("은행 선택")
        if self.bank_name_combo.lineEdit() is not None:
            self.bank_name_combo.lineEdit().setPlaceholderText("은행 선택/입력")
        self.bank_account_edit = QLineEdit()
        self.bank_account_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9\-]*$"), self.bank_account_edit))
        self.bank_account_edit.setPlaceholderText("계좌번호 입력")
        self.bank_info_widget = QWidget()
        bank_info_layout = QHBoxLayout(self.bank_info_widget)
        bank_info_layout.setContentsMargins(0, 0, 0, 0)
        bank_info_layout.setSpacing(6)
        self.bank_name_combo.setFixedHeight(30)
        self.bank_name_combo.setMinimumWidth(110)
        self.bank_name_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.bank_account_edit.setFixedHeight(30)
        self.bank_account_edit.setMinimumWidth(180)
        self.bank_account_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bank_info_layout.addWidget(self.bank_name_combo, 0)
        bank_info_layout.addWidget(self.bank_account_edit, 1)
        self.bank_info_widget.setFixedHeight(30)
        self.bank_info_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.name_edit.setPlaceholderText("이름 입력")
        self.english_name_edit.setPlaceholderText("영문 이름 입력")
        self.id_number_edit.setPlaceholderText("예: 001234567890")
        self.nation_combo.lineEdit().setPlaceholderText("국적 자동추출 또는 직접 입력")
        self.phone_edit.setPlaceholderText("예: 010-1234-5678")

        form_intro = QFrame()
        form_intro.setMinimumWidth(REGISTRATION_FORM_WIDTH - 12)
        form_intro.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        form_intro.setObjectName("MiniMetricCard")
        intro_layout = QVBoxLayout(form_intro)
        intro_layout.setContentsMargins(6, 6, 6, 6)
        intro_layout.setSpacing(6)

        intro_text = QVBoxLayout()
        intro_text.setSpacing(6)
        intro_title = QLabel("자동추출로 여권 / 신분증 정보를 먼저 채워줍니다.")
        intro_title.setObjectName("StatBadge")
        intro_sub = QLabel("문서 정보가 먼저 채워지고, 아래에서 회사 정보를 이어서 입력하면 됩니다.")
        intro_sub.setObjectName("PanelNote")
        intro_sub.setWordWrap(True)
        intro_text.addWidget(intro_title)
        intro_text.addWidget(intro_sub)
        intro_layout.addLayout(intro_text)

        intro_right = QHBoxLayout()
        intro_right.setSpacing(6)
        self.extract_progress_label = QLabel("")
        self.extract_progress_label.setObjectName("PanelNote")
        self.extract_progress_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.extract_progress_label.setMinimumWidth(220)
        self.extract_progress_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.extract_progress_label.hide()
        intro_right.addWidget(self.extract_progress_label, 1)
        self.extract_status_badge = QLabel("자동 추출 대기")
        self.extract_status_badge.setObjectName("HeroChip")
        self.extract_status_badge.setAlignment(Qt.AlignCenter)
        self.extract_status_badge.setMinimumWidth(96)
        intro_right.addWidget(self.extract_status_badge)
        autoextract_btn = QPushButton("자동추출")
        autoextract_btn.setObjectName("PrimaryButton")
        autoextract_btn.setFixedHeight(30)
        autoextract_btn.clicked.connect(self.run_auto_extraction)
        intro_right.addWidget(autoextract_btn)
        intro_layout.addLayout(intro_right)
        form_panel.body_layout.addWidget(form_intro)

        document_card = QFrame()
        document_card.setMinimumWidth(REGISTRATION_FORM_WIDTH - 12)
        document_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        document_card.setObjectName("MiniMetricCard")
        document_layout = QVBoxLayout(document_card)
        document_layout.setContentsMargins(6, 6, 6, 6)
        document_layout.setSpacing(6)

        doc_header = QVBoxLayout()
        doc_header.setSpacing(6)
        doc_title_box = QVBoxLayout()
        doc_title_box.setSpacing(6)
        doc_title = QLabel("문서 자동추출 정보")
        doc_title.setObjectName("PanelTitle")
        doc_note = QLabel("여권 또는 ID 카드에서 자동으로 읽은 값입니다. 자동추출 후 먼저 확인해 주세요.")
        doc_note.setObjectName("PanelNote")
        doc_note.setWordWrap(True)
        doc_title_box.addWidget(doc_title)
        doc_title_box.addWidget(doc_note)
        doc_header.addLayout(doc_title_box)
        self.extract_status_note = QLabel("원본 등록 후 자동추출을 누르면 문서 정보 카드가 채워집니다.")
        self.extract_status_note.setObjectName("PanelNote")
        self.extract_status_note.setWordWrap(True)
        self.extract_status_note.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        doc_header.addWidget(self.extract_status_note)
        document_layout.addLayout(doc_header)

        document_grid = QGridLayout()
        document_grid.setHorizontalSpacing(6)
        document_grid.setVerticalSpacing(6)
        self.document_grid = document_grid
        self._document_field_boxes = []
        self._document_field_box_map = {}
        document_fields = [
            ("이름", self.name_edit),
            ("영문이름", self.english_name_edit),
            ("국적", self.nation_combo),
            ("생년월일", self.birth_date_edit),
            ("성별", self.gender_combo),
            ("계좌정보", self.bank_info_widget),
        ]
        for label, widget in document_fields:
            field_widget = QWidget()
            field_widget.setFixedHeight(REGISTRATION_FIELD_ROW_HEIGHT)
            field_widget.setMinimumHeight(REGISTRATION_FIELD_ROW_HEIGHT)
            field_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            field_box = QVBoxLayout(field_widget)
            field_box.setContentsMargins(0, 0, 0, 0)
            field_box.setSpacing(6)
            lbl = QLabel(label)
            lbl.setObjectName("FieldLabel")
            lbl.setFixedHeight(16)
            lbl.setMinimumHeight(16)
            field_box.addWidget(lbl)
            self._normalize_registration_input(widget)
            if label == "영문이름":
                h_layout = QHBoxLayout()
                h_layout.setSpacing(6)
                h_layout.setContentsMargins(0, 0, 0, 0)
                h_layout.addWidget(widget, 1)
                trans_btn = QPushButton("발음변환")
                trans_btn.setObjectName("SecondaryButton")
                trans_btn.setToolTip("영문이름을 현장에서 부르는 한국식 이름으로 변환합니다.")
                trans_btn.clicked.connect(self._translate_english_name)
                trans_btn.setFixedWidth(74)
                trans_btn.setFixedHeight(30)
                h_layout.addWidget(trans_btn)
                field_box.addLayout(h_layout)
            else:
                field_box.addWidget(widget)
            self._document_field_boxes.append(field_widget)
            self._document_field_box_map[label] = field_widget
            
        document_layout.addLayout(document_grid)
        
        form_panel.body_layout.addWidget(document_card)

        company_card = QFrame()
        company_card.setMinimumWidth(REGISTRATION_FORM_WIDTH - 12)
        company_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        company_card.setObjectName("MiniMetricCard")
        company_layout = QVBoxLayout(company_card)
        company_layout.setContentsMargins(6, 6, 6, 6)
        company_layout.setSpacing(6)

        company_header = QHBoxLayout()
        company_header.setSpacing(6)
        company_title_box = QVBoxLayout()
        company_title_box.setSpacing(6)
        company_title = QLabel("회사 입력 정보")
        company_title.setObjectName("PanelTitle")
        company_note = QLabel("문서에 없는 값은 아래에서 직접 입력합니다. 문서 정보와 함께 묶어서 관리됩니다.")
        company_note.setObjectName("PanelNote")
        company_note.setWordWrap(True)
        company_title_box.addWidget(company_title)
        company_title_box.addWidget(company_note)
        company_header.addLayout(company_title_box, 1)
        self.company_manual_check = QCheckBox("직접 입력 / 빈칸 허용")
        self.company_manual_check.setObjectName("CompanyManualCheck")
        self.company_manual_check.setToolTip("체크하면 회사 입력 정보 칸을 비워두거나 직접 입력할 수 있습니다.")
        self.company_manual_check.toggled.connect(self._toggle_company_manual_input)
        company_header.addWidget(self.company_manual_check, 0, Qt.AlignTop | Qt.AlignRight)
        company_layout.addLayout(company_header)

        company_grid = QGridLayout()
        company_grid.setHorizontalSpacing(6)
        company_grid.setVerticalSpacing(6)
        self.company_grid = company_grid
        self._company_field_boxes = []
        self._company_field_box_map = {}
        company_fields = [
            ("사업장", self.business_combo),
            ("근무 사업장", self.client_combo),
            ("연락처", self.phone_edit),
            ("입사일", self.hire_date_edit),
            ("급여형태", self.pay_type_combo),
            ("근무형태", self.work_type_combo),
            ("기본급", self.base_wage_edit),
        ]
        for label, widget in company_fields:
            field_widget = QWidget()
            field_widget.setFixedHeight(REGISTRATION_FIELD_ROW_HEIGHT)
            field_widget.setMinimumHeight(REGISTRATION_FIELD_ROW_HEIGHT)
            field_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            field_box = QVBoxLayout(field_widget)
            field_box.setContentsMargins(0, 0, 0, 0)
            field_box.setSpacing(6)
            lbl = QLabel(label)
            lbl.setObjectName("FieldLabel")
            lbl.setFixedHeight(16)
            lbl.setMinimumHeight(16)
            field_box.addWidget(lbl)
            self._normalize_registration_input(widget)
            field_box.addWidget(widget)
            self._company_field_boxes.append(field_widget)
            self._company_field_box_map[label] = field_widget
        company_layout.addLayout(company_grid)

        form_panel.body_layout.addWidget(company_card)

        form_buttons = QHBoxLayout()
        form_buttons.addStretch()
        self.save_btn = QPushButton("사원 저장")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.setFixedHeight(30)
        self.save_btn.clicked.connect(self.save_employee)
        manager_btn = QPushButton("담당자등록")
        manager_btn.setObjectName("GhostButton")
        manager_btn.setMinimumWidth(108)
        manager_btn.setFixedHeight(30)
        manager_btn.clicked.connect(self.open_manager_registration)
        form_buttons.addWidget(manager_btn)
        form_buttons.addWidget(self.save_btn)
        form_panel.body_layout.addLayout(form_buttons)

        main_splitter = LockedSplitter(Qt.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setHandleWidth(6)
        self.main_splitter = main_splitter
        
        left_wrap = QWidget()
        left_layout = QVBoxLayout(left_wrap)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(toolbar_panel)
        left_layout.addWidget(work_splitter, 1)
        
        self.form_panel = form_panel
        left_wrap.setFixedWidth(REGISTRATION_WORK_WIDTH)
        left_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        form_panel.setMinimumWidth(REGISTRATION_FORM_WIDTH)
        form_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        main_splitter.addWidget(left_wrap)
        main_splitter.addWidget(form_panel)
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setMinimumWidth(REGISTRATION_CONTENT_WIDTH)
        main_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_splitter.setSizes([REGISTRATION_WORK_WIDTH, REGISTRATION_FORM_WIDTH])
        QTimer.singleShot(0, main_splitter.lock_handles)
        
        scroll_frame = InnerScrollFrame(
            main_splitter,
            margins=(0, 0, 0, 0),
            min_content_height=740,
            # 근로자등록 내부 가로 스크롤은 만들지 않고, 바깥 PageScrollArea 가로 스크롤 1개만 사용한다.
            horizontal_policy=Qt.ScrollBarAlwaysOff,
        )
        scroll_frame.setObjectName("ScrollPageOuterFrame")
        root.addWidget(scroll_frame, 1)
        self._reflow_form_grids()

    def _normalize_registration_input(self, widget):
        common_height = 30
        widget.setFixedHeight(common_height)
        widget.setMinimumWidth(150)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if isinstance(widget, QLineEdit):
            widget.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            widget.setTextMargins(0, 0, 0, 0)
        if isinstance(widget, QComboBox) and widget.isEditable() and widget.lineEdit() is not None:
            widget.lineEdit().setFixedHeight(30)
            widget.lineEdit().setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            widget.lineEdit().setTextMargins(0, 0, 0, 0)
        if isinstance(widget, QDateEdit):
            widget.setObjectName("RegistrationDateEdit")
            widget.setMinimumWidth(150)
            widget.setFixedHeight(common_height)
            widget.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def _clear_grid_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            if child_layout is not None:
                child_layout.setParent(None)

    def _populate_grid_layout(self, layout, field_boxes, columns):
        self._clear_grid_layout(layout)
        row_count = max(1, (len(field_boxes) + max(1, columns) - 1) // max(1, columns))
        for idx, field_box in enumerate(field_boxes):
            row = idx // columns
            col = idx % columns
            if isinstance(field_box, QWidget):
                layout.addWidget(field_box, row, col)
            else:
                layout.addLayout(field_box, row, col)
            layout.setRowMinimumHeight(row, REGISTRATION_FIELD_ROW_HEIGHT)
            layout.setRowStretch(row, 0)
        for row in range(row_count, max(row_count + 1, 6)):
            layout.setRowMinimumHeight(row, 0)
            layout.setRowStretch(row, 0)
        for col in range(max(1, columns)):
            layout.setColumnMinimumWidth(col, REGISTRATION_FIELD_COLUMN_WIDTH)
            layout.setColumnStretch(col, 1)

    def _populate_document_grid_compact(self, available_width: int):
        layout = self.document_grid
        self._clear_grid_layout(layout)
        field_boxes = getattr(self, "_document_field_boxes", [])
        if not field_boxes:
            return

        # 폼은 크기 유지 기준입니다. 화면을 줄여도 2열 구조를 압축하지 않고 스크롤로 이동합니다.
        columns = 2
        self._populate_grid_layout(layout, field_boxes, columns)

    def _populate_company_grid_compact(self, available_width: int):
        layout = self.company_grid
        self._clear_grid_layout(layout)
        field_boxes = getattr(self, "_company_field_boxes", [])
        if not field_boxes:
            return

        # 회사 입력 정보도 2열 고정 구조를 유지하고, 부족한 폭은 스크롤로 처리합니다.
        columns = 2
        self._populate_grid_layout(layout, field_boxes, columns)

    def _reflow_form_grids(self):
        if not hasattr(self, "document_grid") or not hasattr(self, "company_grid"):
            return
        available_width = 0
        if hasattr(self, "form_panel"):
            available_width = self.form_panel.width()
        if available_width <= 0 and hasattr(self, "main_splitter") and len(self.main_splitter.sizes()) > 1:
            available_width = self.main_splitter.sizes()[1]
        self._populate_document_grid_compact(available_width)
        self._populate_company_grid_compact(available_width)

    def _refresh_company_options(self):
        if hasattr(self, "company_manual_check") and self.company_manual_check.isChecked():
            return
        current_business = self.business_combo.currentText().strip() if hasattr(self, "business_combo") else ""
        current_client = self.client_combo.currentText().strip() if hasattr(self, "client_combo") else ""

        business_names = [row["name"] for row in self.state.business_records()]

        self.business_combo.blockSignals(True)
        self.business_combo.clear()
        self.business_combo.addItems(business_names or ["No businesses"])
        if current_business:
            self.business_combo.setCurrentText(current_business)
        self.business_combo.blockSignals(False)

        self._refresh_client_options(current_client or None)

    def _refresh_client_options(self, preferred_client: str | None = None):
        if not hasattr(self, "client_combo"):
            return
        if hasattr(self, "company_manual_check") and self.company_manual_check.isChecked():
            return
        if hasattr(self, "business_combo"):
            selected_business = self.business_combo.currentText().strip()
        else:
            selected_business = ""
        current_client = preferred_client if preferred_client is not None else self.client_combo.currentText().strip()
        if selected_business:
            client_names = [row["name"] for row in self.state.work_site_records(selected_business)]
        else:
            client_names = [row["name"] for row in self.state.client_records()]

        self.client_combo.blockSignals(True)
        self.client_combo.clear()
        self.client_combo.addItems(client_names or ["No work sites"])
        if current_client and current_client in client_names:
            self.client_combo.setCurrentText(current_client)
        elif client_names:
            self.client_combo.setCurrentIndex(0)
        self.client_combo.blockSignals(False)

    def _set_combo_current_text(self, combo: QComboBox, text: str):
        if combo is None:
            return
        was_blocked = combo.blockSignals(True)
        if not combo.isEditable():
            combo.setEditable(True)
        combo.setCurrentText(str(text or ""))
        combo.blockSignals(was_blocked)

    def _clear_company_inputs_for_manual(self):
        if not hasattr(self, "business_combo"):
            return
        self._set_combo_current_text(self.business_combo, "")
        self._set_combo_current_text(self.client_combo, "")
        self.phone_edit.clear()
        self.hire_date_edit.setDate(self.hire_date_edit.minimumDate())
        self._set_combo_current_text(self.pay_type_combo, "")
        self._set_combo_current_text(self.work_type_combo, "")
        self.base_wage_edit.clear()

    def _toggle_company_manual_input(self, checked: bool):
        self._company_manual_mode = bool(checked)
        for combo in (self.business_combo, self.client_combo, self.pay_type_combo, self.work_type_combo):
            combo.setEditable(True)
            if combo.lineEdit() is not None:
                combo.lineEdit().setPlaceholderText("직접 입력 또는 빈칸")
        if checked:
            self._clear_company_inputs_for_manual()
        else:
            self._refresh_company_options()
            if self.hire_date_edit.date() == self.hire_date_edit.minimumDate():
                self.hire_date_edit.setDate(QDate.currentDate())
            if not self.pay_type_combo.currentText().strip():
                self.pay_type_combo.setCurrentText("시급제")
            if not self.work_type_combo.currentText().strip():
                self.work_type_combo.setCurrentText("교대")

    def _is_company_manual_input_enabled(self) -> bool:
        return bool(hasattr(self, "company_manual_check") and self.company_manual_check.isChecked())

    def prepare_new_employee(self, employee_id: int):
        self._registration_mode = "new"
        self._editing_employee = None
        self._loading_existing_media = False
        self._media_changed = False
        self._portrait_changed = False
        if hasattr(self, "save_btn"):
            self.save_btn.setText("사원 저장")
        self._default_employee_id = employee_id
        if self._is_company_manual_input_enabled():
            self._clear_company_inputs_for_manual()
        else:
            if self.business_combo.count():
                self.business_combo.setCurrentIndex(0)
            self._refresh_client_options()
        self.name_edit.clear()
        self._name_edited_by_user = False
        self._auto_name_for_save = ""
        self._last_doc_type = ""
        self.english_name_edit.clear()
        self.nation_combo.setCurrentText("")
        self._extracted_passport_no = ""
        self.id_number_edit.clear()
        self.birth_date_edit.setDate(self.birth_date_edit.minimumDate())
        self.gender_combo.setCurrentText("")
        self.phone_edit.clear()
        if hasattr(self, "bank_name_combo"):
            self.bank_name_combo.setCurrentText("은행 선택")
        if hasattr(self, "bank_account_edit"):
            self.bank_account_edit.clear()
        self.hire_date_edit.setDate(QDate.currentDate())
        self.base_wage_edit.clear()
        self.pay_type_combo.setCurrentText("시급제")
        self.work_type_combo.setCurrentText("교대")
        if self._is_company_manual_input_enabled():
            self._clear_company_inputs_for_manual()
        display_no = self.state.next_employee_display_number(employee_id) if hasattr(self.state, "next_employee_display_number") else f"{int(employee_id):04d}"
        self.file_label.setText(f"다음 등록 예정 번호: {display_no}")
        self.preview_path.setText("파일을 등록하면 여기에 파일명이 표시됩니다.")
        self.status_label.setText("이미지 업로드 대기")
        self.origin_preview.setPixmap(QPixmap())
        self.origin_preview.setText("원본 미리보기")
        self._portrait_image = None
        self._set_portrait_preview_image(None)
        self.current_image_path = ""
        self.extract_status_badge.setText("자동 추출 대기")
        self.extract_status_note.setText("원본 등록 후 자동추출을 누르면 문서 정보 카드가 채워집니다.")
        self._stop_extract_progress(clear_only=True)
        self.canvas.original_image = None
        self.canvas.current_image = None
        self.canvas.current_path = ""
        self.canvas.zoom = 1.0
        self.canvas.edit_mode = False
        self.canvas.portrait_mode = False
        self.canvas.portrait_active_edge = None
        self.canvas.is_corrected = False
        self.canvas.handles = []
        self.canvas._update_pixmap_cache()
        self.canvas.update()
        self.crop_portrait_btn.show()
        self.apply_portrait_btn.hide()

    def _existing_media_path(self, employee: dict, *keys: str) -> str:
        for key in keys:
            raw = str((employee or {}).get(key) or "").strip()
            if not raw:
                continue
            try:
                resolved = self.state.resolve_storage_file_path(raw) if hasattr(self.state, "resolve_storage_file_path") else raw
            except Exception:
                resolved = raw
            if resolved and Path(resolved).exists():
                return str(resolved)
        return ""

    def _load_existing_portrait_preview(self, employee: dict):
        path = self._existing_media_path(employee, "portrait_path")
        if not path:
            self._set_portrait_preview_image(None)
            return
        try:
            image = Image.open(path).convert("RGB")
            self._set_portrait_preview_image(image)
        except Exception:
            self._set_portrait_preview_image(None)

    def prepare_employee_document_edit(self, employee: dict):
        employee = deepcopy(employee or {})
        self._registration_mode = "document_edit"
        self._editing_employee = employee
        self._loading_existing_media = False
        self._media_changed = False
        self._portrait_changed = False
        self._default_employee_id = int(employee.get("id", 0) or 0)
        if hasattr(self, "save_btn"):
            self.save_btn.setText("사진/문서 저장")

        self._set_combo_current_text(self.business_combo, str(employee.get("affiliated_business") or employee.get("business") or ""))
        self._refresh_client_options()
        self._set_combo_current_text(self.client_combo, str(employee.get("work_site") or employee.get("client") or employee.get("company") or ""))
        self.name_edit.setText(str(employee.get("name") or ""))
        self.english_name_edit.setText(str(employee.get("english_name") or employee.get("name_english") or ""))
        self._name_edited_by_user = True
        self._auto_name_for_save = ""
        self._last_doc_type = str(employee.get("document_type") or "")
        self._extracted_passport_no = str(employee.get("passport_no") or "")

        nation = str(employee.get("nation") or "").strip()
        if nation and self.nation_combo.findText(nation) < 0:
            self.nation_combo.addItem(nation)
        self.nation_combo.setCurrentText(nation)
        self.id_number_edit.setText(str(employee.get("id_no") or ""))

        birth_text = str(employee.get("birth_date") or "").strip()
        birth_qdate = QDate.fromString(birth_text, "yyyy-MM-dd") if birth_text else QDate()
        self.birth_date_edit.setDate(birth_qdate if birth_qdate.isValid() else self.birth_date_edit.minimumDate())

        gender = str(employee.get("gender") or "").strip()
        if gender and self.gender_combo.findText(gender) < 0:
            self.gender_combo.addItem(gender)
        self.gender_combo.setCurrentText(gender)

        self.phone_edit.setText(str(employee.get("phone") or ""))
        if hasattr(self, "bank_name_combo"):
            bank_name = str(employee.get("bank_name") or employee.get("bank") or "").strip()
            self.bank_name_combo.setCurrentText(bank_name or "은행 선택")
        if hasattr(self, "bank_account_edit"):
            self.bank_account_edit.setText(str(employee.get("bank_account") or employee.get("account_number") or ""))
        hire_text = str(employee.get("hire_date") or "").strip()
        hire_qdate = QDate.fromString(hire_text, "yyyy-MM-dd") if hire_text else QDate()
        self.hire_date_edit.setDate(hire_qdate if hire_qdate.isValid() else self.hire_date_edit.minimumDate())
        self._set_combo_current_text(self.pay_type_combo, str(employee.get("pay_type") or "시급제"))
        self._set_combo_current_text(self.work_type_combo, str(employee.get("work_type") or "교대"))
        raw_wage = str(employee.get("base_wage") or "").strip()
        if raw_wage:
            try:
                wage = float(raw_wage)
                self.base_wage_edit.setText(f"{int(wage)}" if wage.is_integer() else str(wage))
            except Exception:
                self.base_wage_edit.setText(raw_wage)
        else:
            self.base_wage_edit.clear()

        display_no = self.state.employee_display_number(employee) if hasattr(self.state, "employee_display_number") else f"{int(self._default_employee_id):04d}"
        self.file_label.setText(f"사진/문서 수정 대상: {display_no}")
        self.preview_path.setText("기존 사진/문서를 불러왔습니다. 새 원본을 등록하거나 보정 후 저장하세요.")
        self.status_label.setText("사진/문서 수정 모드")
        self.extract_status_badge.setText("수정 모드")
        self.extract_status_note.setText("기존 여권/신분증 정보를 불러왔습니다. 필요한 경우 원본사진 등록 또는 자동추출을 다시 진행하세요.")
        self._stop_extract_progress(clear_only=True)

        self._portrait_image = None
        self._load_existing_portrait_preview(employee)

        self.current_image_path = ""
        self.canvas.original_image = None
        self.canvas.current_image = None
        self.canvas.current_path = ""
        self.canvas.zoom = 1.0
        self.canvas.edit_mode = False
        self.canvas.portrait_mode = False
        self.canvas.portrait_active_edge = None
        self.canvas.is_corrected = False
        self.canvas.handles = []
        self.canvas._update_pixmap_cache()
        self.canvas.update()

        existing_original = self._existing_media_path(employee, "original_document_path")
        existing_document = self._existing_media_path(employee, "document_path")
        load_path = existing_original or existing_document
        if load_path:
            try:
                self._loading_existing_media = True
                self.canvas.load_image(load_path)
                self.current_image_path = existing_original or load_path
                self._last_doc_type = str(employee.get("document_type") or self._last_doc_type or "")
                self._load_existing_portrait_preview(employee)
                self._media_changed = False
                self._portrait_changed = False
                self.preview_path.setText(load_path)
            finally:
                self._loading_existing_media = False
        else:
            self.origin_preview.setPixmap(QPixmap())
            self.origin_preview.setText("원본 미리보기")

        self.crop_portrait_btn.show()
        self.apply_portrait_btn.hide()

    def _on_image_loaded(self, path: str):
        self.current_image_path = path
        if not getattr(self, "_loading_existing_media", False):
            self._media_changed = True
            self._last_doc_type = ""
        name = Path(path).name
        self.file_label.setText(f"등록 파일: {name}")
        self.preview_path.setText(path)
        self._portrait_image = None
        self._update_origin_preview_from_current_image()
        self._update_portrait_preview_from_current_image()
        self.crop_portrait_btn.show()
        self.apply_portrait_btn.hide()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._main_splitter_initialized and hasattr(self, "main_splitter"):
            QTimer.singleShot(0, self._apply_initial_splitter_balance)

    def _apply_initial_splitter_balance(self):
        if self._main_splitter_initialized or not hasattr(self, "main_splitter"):
            return
        total_width = self.main_splitter.size().width()
        if total_width <= 0:
            return
        # 초기 표시 때도 절반 배분으로 다시 압축하지 않고, 고정 작업폭을 유지합니다.
        self.main_splitter.setSizes([REGISTRATION_WORK_WIDTH, REGISTRATION_FORM_WIDTH])
        self._main_splitter_initialized = True
        QTimer.singleShot(0, self._reflow_form_grids)
        QTimer.singleShot(0, self._update_origin_preview_box_size)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_form_grids()
        self._update_origin_preview_box_size()
        self._update_origin_preview_from_current_image()




    def _set_extract_progress_text(self, text: str = "", visible: bool | None = None):
        show = bool(text) if visible is None else visible
        self.extract_progress_label.setText(text)
        self.extract_progress_label.setVisible(show)

    def _start_extract_progress(self):
        self._extract_progress_index = 0
        self._set_extract_progress_text(self._extract_progress_messages[0], True)
        self._extract_progress_timer.start()

    def _advance_extract_progress_message(self):
        if self._mrz_worker is None or not self._mrz_worker.isRunning():
            self._extract_progress_timer.stop()
            return
        if self._extract_progress_index < len(self._extract_progress_messages) - 1:
            self._extract_progress_index += 1
        self._set_extract_progress_text(self._extract_progress_messages[self._extract_progress_index], True)

    def _stop_extract_progress(self, final_text: str = "", hold_ms: int = 0, clear_only: bool = False):
        self._extract_progress_timer.stop()
        if clear_only:
            self._set_extract_progress_text("", False)
            return
        if final_text:
            self._set_extract_progress_text(final_text, True)
            if hold_ms > 0:
                QTimer.singleShot(hold_ms, lambda: self._set_extract_progress_text("", False))
            return
        self._set_extract_progress_text("", False)

    def _estimate_document_kind(self, image: Image.Image | None) -> str:
        if image is None:
            return "unknown"
        width, height = image.size
        ratio = (width / height) if height else 0.0
        if ratio >= 1.18:
            return "card"
        return "document"

    def _build_ocr_input_image(self) -> Image.Image | None:
        source = getattr(self.canvas, "mrz_deskewed_image", None) or self.canvas.current_image
        if source is None:
            return None

        # Do NOT apply MedianFilter, Sharpness, or Scaling here, as it creates 
        # sub-pixel aliasing that destroys Tesseract's native parsing capabilities.
        image = source.convert("RGB")
        return image

    def _create_extract_debug_dir(self) -> str:
        base = Path.cwd() / "debug_extract"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = base / stamp
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def run_auto_extraction(self):
        if self.canvas.current_image is None:
            QMessageBox.information(self, "자동 추출", "먼저 원본 사진을 등록해 주세요.")
            return

        if self._mrz_worker is not None and self._mrz_worker.isRunning():
            return

        # 자동추출은 화면 상태를 바꾸지 않고 현재 이미지를 그대로 분석합니다.
        # 단, 사용자가 보정점 편집 중(edit_mode)이면 먼저 보정적용을 유도합니다.
        if self.canvas.edit_mode:
            QMessageBox.information(self, "자동 추출", "보정점을 조정 중입니다. 먼저 보정적용을 눌러 주세요.")
            return

        # 사용자가 원본 사진만 올리고 바로 '자동 추출'을 눌렀다면 눈에 보이게 보정해줍니다.
        if not getattr(self.canvas, "is_corrected", False):
            self.auto_correct(show_message=False)

        quality = self._analyze_correction_quality()
        self._set_quality_status(quality)
        ocr_input = self._build_ocr_input_image()
        if ocr_input is None:
            QMessageBox.information(self, "자동 추출", "OCR에 사용할 이미지를 준비하지 못했습니다.")
            return

        advisory_issues = [str(item) for item in quality.get("issues", [])]
        advisory_warnings = [str(item) for item in quality.get("warnings", [])]

        debug_dir = self._create_extract_debug_dir()
        self._current_extract_debug_dir = debug_dir

        self._set_mrz_busy(True)
        self._start_extract_progress()
        self.extract_status_badge.setText("추출 중...")
        if advisory_issues:
            self.extract_status_note.setText("보정 확인 필요: " + ", ".join(advisory_issues[:2]) + " / 그래도 현재 이미지로 인식합니다.")
        elif advisory_warnings:
            self.extract_status_note.setText("보정 참고: " + ", ".join(advisory_warnings[:2]) + " / 현재 이미지로 인식합니다.")
        else:
            self.extract_status_note.setText("보정 결과 이미지를 기준으로 자동 인식을 진행합니다.")
        self.status_label.setText(f"OCR 인식 진행 중... 입력 {ocr_input.size[0]}x{ocr_input.size[1]} / 디버그: {Path(debug_dir).name}")
        self._mrz_worker = FunctionWorkerThread(extract_mrz_sync, ocr_input.copy(), debug_dir)
        self._mrz_worker.result_ready.connect(self._handle_mrz_result)
        self._mrz_worker.error_occurred.connect(self._handle_mrz_error)
        self._mrz_worker.finished.connect(self._cleanup_mrz_worker)
        self._mrz_worker.start()

    def _set_mrz_busy(self, is_busy: bool):
        self.open_btn.setEnabled(not is_busy)
        self.correct_btn.setEnabled(not is_busy)
        if hasattr(self, "auto_correct_btn"):
            self.auto_correct_btn.setEnabled(not is_busy)

    def _build_mrz_review_issues(self, result: dict | None) -> tuple[list[str], list[str]]:
        data = result or {}
        critical_issues: list[str] = []
        warning_issues: list[str] = []
        name = str(data.get("name") or "").strip()
        english_name = str(data.get("english_name") or "").strip()
        passport_no = str(data.get("passport_no") or "").strip()
        id_no = str(data.get("id_no") or "").strip()
        birth_date = str(data.get("birth_date") or "").strip()
        gender = str(data.get("gender") or "").strip()
        doc_type = str(data.get("doc_type") or "")

        # pc_7 기준: 성공 판정은 문서번호보다 등록에 필요한 정보 + 얼굴을 우선한다.
        if not name and not english_name:
            critical_issues.append("이름 미추출")
        nation = str(data.get("nation") or "").strip()
        if not nation or nation in {"기타", "미확인", "-"}:
            critical_issues.append("국적 미추출")
        if not birth_date or not QDate.fromString(birth_date, "yyyy-MM-dd").isValid():
            critical_issues.append("생년월일 미추출")
        if gender in {"기타", "미확인", "", "-"}:
            critical_issues.append("성별 미추출")
        if data.get("_portrait_ok") is False:
            critical_issues.append("얼굴사진 미추출")
        if doc_type in {"residence_card", "overseas_resident_card"}:
            if not id_no:
                warning_issues.append("등록번호 확인 권장")
        else:
            if not passport_no:
                warning_issues.append("여권번호 확인 권장")
        return critical_issues, warning_issues

    def _handle_mrz_result(self, result: dict | None):
        if result:
            if "error" in result:
                QMessageBox.warning(
                    self,
                    "인식 실패",
                    "문자 인식은 되었지만 데이터 형식 분석에 실패했습니다.\n\n"
                    f"[OCR 원문]\n\n{result.get('raw_text', '')}"
                )
                self.extract_status_badge.setText("추출 실패")
                self.extract_status_note.setText("인식된 문자가 여권 형식과 맞지 않습니다.")
                self.status_label.setText("인식 실패: 형식 불일치")
                self._stop_extract_progress("형식 확인 필요", 1200)
                return

            # 자동추출 결과에 포함된 얼굴 사진을 우선 사용합니다.
            extracted_portrait = result.pop("portrait_image", None) if isinstance(result, dict) else None
            portrait_ok = False
            if extracted_portrait is not None:
                self._portrait_image = extracted_portrait
                self._portrait_changed = True
                self._set_portrait_preview_image(extracted_portrait)
                portrait_ok = True
            else:
                fallback_portrait = extract_main_portrait(self.canvas.current_image)
                if fallback_portrait is not None:
                    self._portrait_image = fallback_portrait
                    self._portrait_changed = True
                    self._set_portrait_preview_image(fallback_portrait)
                    portrait_ok = True
                else:
                    self._update_portrait_preview_from_current_image()
            if isinstance(result, dict):
                result["_portrait_ok"] = portrait_ok

            # 자동추출 필드 자동 입력
            doc_type = str(result.get("doc_type") or "")
            self._last_doc_type = doc_type
            extracted_name = str(result.get("name", result.get("english_name", "")) or "").strip()
            english_name = str(result.get("english_name", "") or "").strip()

            # OCR 원문 영문 이름은 영문이름칸에 보관하고,
            # 실제 이름칸은 현장에서 부르는 한국식 발음 이름으로 자동 입력한다.
            if not english_name and extracted_name and re.search(r"[A-Za-z]", extracted_name):
                english_name = extracted_name
            korean_name = transliterate_english_to_korean(english_name) if english_name else extracted_name
            display_name = korean_name or extracted_name or english_name

            self._name_edited_by_user = False
            self._auto_name_for_save = display_name
            self.name_edit.setText(display_name)
            self.english_name_edit.setText(english_name)
            nation_text = str(result.get("nation") or "").strip()
            if nation_text:
                if self.nation_combo.findText(nation_text) < 0:
                    self.nation_combo.addItem(nation_text)
                self.nation_combo.setCurrentText(nation_text)
            else:
                self.nation_combo.setCurrentText("")
            if doc_type in {"residence_card", "overseas_resident_card"}:
                self._extracted_passport_no = ""
            else:
                self._extracted_passport_no = str(result.get("passport_no") or "").strip()
            self.id_number_edit.setText(str(result.get("id_no", "") or ""))
            birth_text = str(result.get("birth_date") or "").strip()
            birth_qdate = QDate.fromString(birth_text, "yyyy-MM-dd") if birth_text else QDate()
            if birth_qdate.isValid():
                self.birth_date_edit.setDate(birth_qdate)
            else:
                self.birth_date_edit.setDate(self.birth_date_edit.minimumDate())
            gender_text = str(result.get("gender") or "").strip()
            if gender_text and self.gender_combo.findText(gender_text) < 0:
                self.gender_combo.addItem(gender_text)
            self.gender_combo.setCurrentText(gender_text)

            critical_issues, warning_issues = self._build_mrz_review_issues(result)
            if critical_issues:
                self.extract_status_badge.setText("수정 요망")
                self.extract_status_note.setText(f"자동추출 결과 확인이 필요합니다. ({', '.join(critical_issues)})")
                self._stop_extract_progress("결과 확인 필요", 1200)
            else:
                self.extract_status_badge.setText("추출 완료")
                extra_note = f" ({', '.join(warning_issues)})" if warning_issues else ""
                if doc_type in {"residence_card", "overseas_resident_card"}:
                    self.extract_status_note.setText(f"신분증 정보가 자동으로 입력되었습니다. 나머지 회사 정보를 직접 입력해 주세요.{extra_note}")
                else:
                    self.extract_status_note.setText(f"여권 정보가 자동으로 입력되었습니다. 나머지 회사 정보를 직접 입력해 주세요.{extra_note}")
                self._stop_extract_progress("추출 완료", 1200)
            status_name = self.name_edit.text().strip() or self.english_name_edit.text().strip()
            status_prefix = "수정 요망" if critical_issues else "추출 완료"
            doc_number = str(result.get("passport_no") or result.get("id_no") or "")
            self.status_label.setText(f"{status_prefix}: {status_name} / {doc_number} / 디버그: {Path(getattr(self, '_current_extract_debug_dir', '')).name}")
            return

        QMessageBox.warning(self, "추출 실패", "텍스트를 찾지 못했습니다. 보정 상태나 이미지 품질을 다시 확인해 주세요.")
        self.extract_status_badge.setText("추출 실패")
        self.extract_status_note.setText("자동 추출에 실패했습니다. 이미지 상태를 확인하거나 수동 입력으로 이어가 주세요.")
        self.status_label.setText("추출 실패: 텍스트 미검출")
        self._stop_extract_progress("재시도 필요", 1200)

    def _handle_mrz_error(self, message: str):
        QMessageBox.warning(self, "추출 실패", message)
        self.extract_status_badge.setText("추출 실패")
        self.extract_status_note.setText("자동 추출에 실패했습니다. 이미지 상태를 확인하거나 수동 입력으로 이어가 주세요.")
        self.status_label.setText("MRZ 인식 실패")
        self._stop_extract_progress("재시도 필요", 1200)

    def _mark_name_edited(self, _: str):
        self._name_edited_by_user = True

    def _cleanup_mrz_worker(self):
        self._extract_progress_timer.stop()
        self._set_mrz_busy(False)
        worker = self._mrz_worker
        self._mrz_worker = None
        if worker is not None:
            worker.deleteLater()

    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "원본 사진 선택",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self.canvas.load_image(path)

    def begin_correction(self):
        self.apply_portrait_btn.hide()
        self.crop_portrait_btn.show()
        self.canvas.begin_correction()

    def auto_correct(self, _checked: bool = False, show_message: bool = True):
        if self.canvas.current_image is None:
            QMessageBox.information(self, "자동 보정", "먼저 원본 사진을 등록해 주세요.")
            return

        corrected = self.canvas.auto_correct_document()
        if corrected is None:
            if show_message:
                QMessageBox.information(self, "자동 보정", "자동으로 문서 테두리를 찾지 못했습니다. 보정 시작으로 4개 점을 직접 맞춰 주세요.")
            return

        self._media_changed = True
        self._update_origin_preview_from_current_image()
        self._update_portrait_preview_from_current_image()
        self.status_label.setText("자동 보정 완료: 자동추출을 진행해 주세요.")

    def rotate_left(self):
        self.canvas.rotate_left()

    def rotate_right(self):
        self.canvas.rotate_right()

    def zoom_in(self):
        self.canvas.zoom_in()

    def zoom_out(self):
        self.canvas.zoom_out()

    def reset_original(self):
        self.canvas.reset_original()
        self._portrait_image = None
        self._update_origin_preview_from_current_image()
        self._update_portrait_preview_from_current_image()
        self.crop_portrait_btn.show()
        self.apply_portrait_btn.hide()

    def _analyze_correction_quality(self) -> dict:
        image = self.canvas.current_image
        if image is None:
            return {
                "grade": "none",
                "summary": "보정 분석 대상 이미지가 없습니다.",
                "issues": ["이미지가 등록되지 않았습니다."],
                "warnings": [],
                "width": 0,
                "height": 0,
                "aspect_ratio": 0.0,
            }

        width, height = image.size
        ratio = (width / height) if height else 0.0
        issues: list[str] = []
        warnings: list[str] = []

        # 수동 4점 기준: 종이 여백 전체보다 정보영역 + 얼굴사진 + MRZ 2줄이 중요합니다.
        # 따라서 가로/세로 비율은 참고만 하고, MRZ 존재/수평/잘림 여부를 더 강하게 봅니다.
        if width < 680 or height < 420:
            issues.append(f"해상도 낮음({width}x{height}) - 글자가 너무 작을 수 있습니다.")
        elif width < 860 or height < 520:
            warnings.append(f"해상도 주의({width}x{height}) - 가능하면 더 크게 촬영해 주세요.")

        if ratio < 1.08:
            issues.append(f"세로 비율 치우침({ratio:.2f}) - 여권 정보면 전체가 아니라 좁은 영역만 보정됐을 수 있습니다.")
        elif ratio > 2.20:
            warnings.append(f"가로 비율이 넓음({ratio:.2f}) - 종이 여백은 잘려도 되지만 정보영역이 잘리지 않았는지 확인해 주세요.")

        total_pixels = width * height
        if total_pixels < 650_000:
            issues.append("총 픽셀 수 부족 - MRZ 작은 글자 인식이 흔들릴 수 있습니다.")
        elif total_pixels < 950_000:
            warnings.append("총 픽셀 수 주의 - 글자가 흐리면 인식률이 떨어질 수 있습니다.")

        try:
            mrz_analysis = analyze_passport_correction_quality(image)
        except Exception as exc:
            mrz_analysis = {"issues": [], "warnings": [f"MRZ 품질 분석 실패: {exc}"], "mrz_present": False}

        mrz_issues = [str(item) for item in mrz_analysis.get("issues", [])]
        mrz_warnings = [str(item) for item in mrz_analysis.get("warnings", [])]
        issues.extend(mrz_issues)
        warnings.extend(mrz_warnings)

        if issues:
            grade = "risk"
            summary = f"보정 확인 필요 ({width}x{height}, 비율 {ratio:.2f})"
        elif warnings:
            grade = "warn"
            summary = f"보정 참고 ({width}x{height}, 비율 {ratio:.2f})"
        else:
            grade = "good"
            summary = f"보정 양호: 정보영역/MRZ 기준 통과 ({width}x{height}, 비율 {ratio:.2f})"

        return {
            "grade": grade,
            "summary": summary,
            "issues": issues,
            "warnings": warnings,
            "width": width,
            "height": height,
            "aspect_ratio": round(ratio, 4),
            "mrz_analysis": mrz_analysis,
        }

    def _set_quality_status(self, analysis: dict):
        summary = str(analysis.get("summary") or "").strip()
        issues = analysis.get("issues") if isinstance(analysis.get("issues"), list) else []
        warnings = analysis.get("warnings") if isinstance(analysis.get("warnings"), list) else []
        notes = [str(item) for item in issues] or [str(item) for item in warnings]
        if notes:
            self.status_label.setText(f"{summary} / {'; '.join(notes[:3])}")
        else:
            self.status_label.setText(summary)

    def _update_origin_preview_box_size(self):
        if not hasattr(self, "origin_preview"):
            return

        ratio = float(getattr(self, "_origin_preview_ratio", 0.65) or 0.65)
        ratio = max(0.35, min(ratio, 1.8))

        available_width = self.origin_preview.width()
        if available_width <= 0 and hasattr(self, "origin_panel"):
            available_width = max(210, self.origin_panel.width() - 28)
        available_width = max(210, available_width)

        desired_height = int(available_width * ratio)
        desired_height = max(110, min(desired_height, 220))
        self.origin_preview.setFixedHeight(desired_height)

    def _resize_portrait_preview_box(self, target: QLabel, image_size: tuple[int, int]):
        img_w, img_h = image_size
        if img_w <= 0 or img_h <= 0:
            return
        # 화면 공간 안에서는 줄여서 보여주되, 사용자가 등록한 사진 비율은 그대로 유지합니다.
        max_w, max_h = 170, 220
        min_w, min_h = 90, 110
        scale = min(max_w / img_w, max_h / img_h)
        if scale <= 0:
            return
        box_w = max(min_w, int(img_w * scale))
        box_h = max(min_h, int(img_h * scale))
        box_w = min(max_w, box_w)
        box_h = min(max_h, box_h)
        target.setFixedSize(box_w, box_h)

    def _set_portrait_preview_image(self, image: Image.Image | None):
        targets = []
        if hasattr(self, "portrait_preview"):
            targets.append(self.portrait_preview)
        if hasattr(self, "left_portrait_preview"):
            targets.append(self.left_portrait_preview)

        if image is None:
            for target in targets:
                target.setPixmap(QPixmap())
                target.setText("추출된 사진")
            return

        try:
            preview_image = image.convert("RGB")
            qimg = ImageQt.ImageQt(preview_image.convert("RGBA"))
            pixmap = QPixmap.fromImage(qimg)
            for target in targets:
                self._resize_portrait_preview_box(target, preview_image.size)
                target.setPixmap(pixmap.scaled(target.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                target.setText("")
        except Exception as exc:
            print(f"Portrait preview update error: {exc}")

    def _begin_portrait_crop(self):
        if self.canvas.current_image is None:
            QMessageBox.information(self, "사진추출", "먼저 원본 사진을 등록해 주세요.")
            return
        if self.canvas.edit_mode:
            QMessageBox.information(self, "사진추출", "보정점을 조정 중입니다. 먼저 ④ 보정적용을 눌러 주세요.")
            return

        self.canvas.begin_portrait_crop()

        portrait = None
        try:
            if hasattr(self.canvas, "preview_portrait_image"):
                portrait = self.canvas.preview_portrait_image()
        except Exception as exc:
            print(f"Portrait preview crop error: {exc}")
            portrait = None

        if portrait is None:
            try:
                portrait = extract_main_portrait(self.canvas.current_image)
                if portrait is None:
                    portrait = extract_passport_portrait(self.canvas.current_image)
            except Exception as exc:
                print(f"Auto portrait extract error: {exc}")
                portrait = None

        if portrait is not None:
            self._set_portrait_preview_image(portrait.convert("RGB").copy())
            self.crop_portrait_btn.hide()
            self.apply_portrait_btn.show()
            self.status_label.setText("사진추출 후보 표시: 초록 박스를 조절한 뒤 ⑧ 사진확인을 눌러야 저장용 얼굴사진으로 확정됩니다.")
            if hasattr(self, "extract_status_note"):
                self.extract_status_note.setText("얼굴사진 후보를 표시했습니다. 아직 저장용으로 확정되지 않았습니다.")
            return

        self.crop_portrait_btn.hide()
        self.apply_portrait_btn.show()
        self.status_label.setText("얼굴사진 후보를 자동으로 표시하지 못했습니다. 초록 박스를 사진 영역에 맞춘 뒤 ⑧ 사진확인을 눌러 주세요.")

    def _apply_portrait_crop(self):
        portrait = self.canvas.get_portrait_image()
        if portrait is None:
            QMessageBox.information(self, "사진확인", "사진 영역을 먼저 지정해 주세요.")
            return
        self._portrait_image = portrait.convert("RGB").copy()
        self._portrait_changed = True
        self._set_portrait_preview_image(self._portrait_image)
        self.apply_portrait_btn.hide()
        self.crop_portrait_btn.show()
        self.status_label.setText("사진확인 완료: 저장 시 이 얼굴사진이 등록됩니다.")
        if hasattr(self, "extract_status_note"):
            self.extract_status_note.setText("얼굴사진 확인이 완료되었습니다. 나머지 회사 정보를 확인한 뒤 저장하세요.")

    def _confirm_document_info(self):
        required = []
        if not self.name_edit.text().strip():
            required.append("이름")
        if not self.english_name_edit.text().strip():
            required.append("영문이름")
        if not self.nation_combo.currentText().strip():
            required.append("국적")
        if not self.birth_date_edit.date().isValid():
            required.append("생년월일")
        if not self.gender_combo.currentText().strip():
            required.append("성별")
        if required:
            self.extract_status_badge.setText("확인 필요")
            self.extract_status_note.setText("정보 확인 필요: " + ", ".join(required))
            self.status_label.setText("정보 확인 필요: " + ", ".join(required))
            return
        self.extract_status_badge.setText("정보 확인")
        self.extract_status_note.setText("필수 문서 정보가 확인되었습니다. 다음 단계로 ⑦ 사진추출을 진행하세요.")
        self.status_label.setText("정보 확인 완료: ⑦ 사진추출을 진행하세요.")

    def _translate_english_name(self):
        english_name = self.english_name_edit.text().strip()
        if not english_name:
            QMessageBox.information(self, "발음변환", "먼저 영문이름을 입력해 주세요.")
            return
        korean_name = transliterate_english_to_korean(english_name)
        if korean_name:
            self.name_edit.setText(korean_name)
            self._auto_name_for_save = korean_name
            self._name_edited_by_user = False
            self.status_label.setText(f"발음변환 완료: {korean_name}")
            if hasattr(self, "extract_status_note"):
                self.extract_status_note.setText("영문이름을 한국식 발음 이름으로 변환했습니다. 값 확인 후 저장하세요.")

    def _update_portrait_preview_from_current_image(self):
        if self._portrait_image is not None:
            self._set_portrait_preview_image(self._portrait_image)
            return
        if self.canvas.current_image is None:
            self._set_portrait_preview_image(None)
            return
        try:
            portrait = extract_main_portrait(self.canvas.current_image)
            if portrait is None:
                portrait = extract_passport_portrait(self.canvas.current_image)
            self._set_portrait_preview_image(portrait)
        except Exception as exc:
            print(f"Portrait preview update error: {exc}")

    def _update_origin_preview_from_current_image(self):
        image = self.canvas.current_image
        if image is None:
            self._origin_preview_ratio = 0.5
            self._update_origin_preview_box_size()
            if self.current_image_path and Path(self.current_image_path).exists():
                pixmap = QPixmap(self.current_image_path)
                if not pixmap.isNull():
                    self.origin_preview.setPixmap(
                        pixmap.scaled(self.origin_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
                    self.origin_preview.setText("")
                    return
            self.origin_preview.setPixmap(QPixmap())
            self.origin_preview.setText("원본 미리보기")
            return

        try:
            width, height = image.size
            if width > 0:
                self._origin_preview_ratio = height / width
            self._update_origin_preview_box_size()
            qimage = ImageQt.ImageQt(image.convert("RGBA"))
            pixmap = QPixmap.fromImage(qimage)
            if not pixmap.isNull():
                self.origin_preview.setPixmap(
                    pixmap.scaled(self.origin_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                self.origin_preview.setText("")
                return
        except Exception as exc:
            print(f"Origin preview update error: {exc}")

        self.origin_preview.setPixmap(QPixmap())
        self.origin_preview.setText("원본 미리보기")

    def apply_correction(self):
        if not self.canvas.edit_mode:
            QMessageBox.information(self, "보정 적용", "보정 시작 후 4점을 맞춘 다음 보정적용을 눌러 주세요.")
            return
        corrected = self.canvas.apply_correction()
        if corrected is None:
            return
        self._media_changed = True
        self._update_origin_preview_from_current_image()
        self._update_portrait_preview_from_current_image()
        analysis = self._analyze_correction_quality()
        self._set_quality_status(analysis)
        if analysis.get("grade") == "risk":
            issue_text = ", ".join(str(item) for item in (analysis.get("issues") or [])[:2])
            self.extract_status_note.setText(f"보정 확인 필요: {issue_text} / MRZ 2줄과 정보영역이 화면 안에 들어왔는지 확인해 주세요.")
        elif analysis.get("grade") == "warn":
            warn_text = ", ".join(str(item) for item in (analysis.get("warnings") or [])[:2])
            self.extract_status_note.setText(f"보정 참고: {warn_text} / 정상으로 보이면 자동추출을 진행하세요.")
        else:
            self.extract_status_note.setText("보정 양호: 정보영역과 MRZ 기준을 통과했습니다. 자동추출을 진행하세요.")

    def open_manager_registration(self):
        employee_name = self.name_edit.text().strip()
        if not employee_name:
            QMessageBox.warning(self, "담당자 등록", "담당자로 등록할 근로자 이름을 먼저 입력해 주세요.")
            return
        dialog = ManagerRegistrationDialog(
            self,
            employee_id=int(self._default_employee_id),
            employee_name=employee_name,
            phone=self.phone_edit.text().strip(),
        )
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.payload()
        if not payload.get("username"):
            QMessageBox.warning(self, "담당자 등록", "모바일 로그인 아이디를 입력해 주세요.")
            return
        if not payload.get("password"):
            QMessageBox.warning(self, "담당자 등록", "모바일 로그인 비밀번호를 입력해 주세요.")
            return
        try:
            if hasattr(self.state, "add_or_update_manager_account"):
                account = self.state.add_or_update_manager_account(payload)
            else:
                raise RuntimeError("담당자 저장 기능을 찾을 수 없습니다.")
        except Exception as error:
            QMessageBox.warning(self, "담당자 등록 실패", f"담당자 정보를 저장하지 못했습니다.\n\n상세: {error}")
            return
        active_text = "사용" if account.get("active", True) else "중지"
        QMessageBox.information(
            self,
            "담당자 등록",
            f"{account.get('employee_name', employee_name)} 담당자 계정이 저장되었습니다.\n"
            f"아이디: {account.get('username', '')}\n"
            f"상태: {active_text}\n"
            "담당 사업자와 근무사업장 배정은 설정 > 관리자설정에서 진행하세요.",
        )

    def save_employee(self):
        title_text = "근로자 수정" if getattr(self, "_registration_mode", "new") == "document_edit" else "근로자 등록"
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, title_text, "이름을 입력해 주세요.")
            return
        manual_company = self._is_company_manual_input_enabled()
        if (not manual_company) and not self.client_combo.currentText().strip():
            QMessageBox.warning(self, title_text, "근무 사업장을 선택해 주세요.")
            return
        if (not manual_company) and not self.business_combo.currentText().strip():
            QMessageBox.warning(self, title_text, "사업장을 선택해 주세요.")
            return

        valid_wage, base_wage, wage_message = _parse_base_wage_input(self.base_wage_edit.text())
        if not valid_wage:
            QMessageBox.warning(self, title_text, wage_message)
            return

        edit_mode = getattr(self, "_registration_mode", "new") == "document_edit" and bool(getattr(self, "_editing_employee", None))
        previous = deepcopy(self._editing_employee or {}) if edit_mode else {}
        media_changed = bool(getattr(self, "_media_changed", False) or getattr(self, "_portrait_changed", False))

        document_kind = infer_employee_document_kind(
            self._last_doc_type or previous.get("document_type"),
            self._extracted_passport_no,
            self.id_number_edit.text().strip(),
        )
        analysis = previous.get("document_correction_analysis", {}) if edit_mode and not media_changed else self._analyze_correction_quality()

        original_document_path = str(previous.get("original_document_path") or "").strip()
        saved_document_path = str(previous.get("document_path") or "").strip()
        portrait_path = str(previous.get("portrait_path") or "").strip()

        if (not edit_mode) or media_changed:
            try:
                original_document_path = copy_original_document_file(
                    self.current_image_path,
                    int(self._default_employee_id),
                    document_kind,
                    self.state,
                ) or original_document_path
                saved_document_path = save_corrected_document(
                    self.canvas.current_image,
                    int(self._default_employee_id),
                    document_kind,
                    self.state,
                ) or saved_document_path or original_document_path or self.current_image_path

                portrait_source = self._portrait_image if self._portrait_image is not None else self.canvas.current_image
                if self._portrait_image is not None:
                    portrait_path = save_portrait_image(portrait_source, int(self._default_employee_id), self.state) or portrait_path
                elif (not edit_mode) or getattr(self, "_media_changed", False):
                    portrait_path = save_passport_portrait(portrait_source, int(self._default_employee_id), self.state) or portrait_path
            except Exception as error:
                QMessageBox.critical(self, "파일 저장 실패", f"사진 파일을 저장하는 데 실패했습니다. 저장 공간이나 권한을 확인해 주세요.\n상세: {error}")
                return

        save_name = self.name_edit.text().strip()
        if (not self._name_edited_by_user) and self._auto_name_for_save.strip():
            # 자동추출 이름은 한국식 발음 이름을 저장 기준으로 사용한다.
            save_name = self._auto_name_for_save.strip()

        employee = deepcopy(previous) if edit_mode else {}
        employee.update({
            "id": int(self._default_employee_id),
            "name": save_name,
            "english_name": self.english_name_edit.text().strip(),
            "nation": self.nation_combo.currentText().strip(),
            "id_no": self.id_number_edit.text().strip(),
            "birth_date": "" if self.birth_date_edit.date() == self.birth_date_edit.minimumDate() else self.birth_date_edit.date().toString("yyyy-MM-dd"),
            "gender": self.gender_combo.currentText().strip(),
            "phone": self.phone_edit.text().strip(),
            "bank_name": ("" if not hasattr(self, "bank_name_combo") else ("" if self.bank_name_combo.currentText().strip() == "은행 선택" else self.bank_name_combo.currentText().strip())),
            "bank": ("" if not hasattr(self, "bank_name_combo") else ("" if self.bank_name_combo.currentText().strip() == "은행 선택" else self.bank_name_combo.currentText().strip())),
            "bank_account": self.bank_account_edit.text().strip() if hasattr(self, "bank_account_edit") else "",
            "account_number": self.bank_account_edit.text().strip() if hasattr(self, "bank_account_edit") else "",
            "hire_date": "" if (manual_company and self.hire_date_edit.date() == self.hire_date_edit.minimumDate()) else self.hire_date_edit.date().toString("yyyy-MM-dd"),
            "business": self.business_combo.currentText().strip(),
            "client": self.client_combo.currentText().strip(),
            "affiliated_business": self.business_combo.currentText().strip(),
            "company": self.client_combo.currentText().strip(),
            "work_site": self.client_combo.currentText().strip(),
            "department": self.client_combo.currentText().strip(),
            "work_type": self.work_type_combo.currentText(),
            "pay_type": self.pay_type_combo.currentText(),
            "base_wage": base_wage,
            "document_type": document_kind,
            "original_document_path": original_document_path,
            "document_path": saved_document_path or original_document_path or self.current_image_path,
            "portrait_path": portrait_path,
            "document_correction_analysis": analysis,
        })

        if not edit_mode:
            employee.update({
                "status": "출근전",
                "active": True,
            })

        try:
            if edit_mode:
                saved_employee = self.state.update_employee(int(self._default_employee_id), employee)
            else:
                saved_employee = self.state.add_employee(employee)
        except Exception as error:
            QMessageBox.warning(self, f"{title_text} 실패", f"근로자 정보를 시스템에 저장하는 동안 오류가 발생했습니다.\n\n상세: {error}")
            return

        self.employee_saved.emit(saved_employee)
        QMessageBox.information(self, title_text, f"{saved_employee.get('name', save_name)} 정보가 저장되었습니다.")
        if edit_mode:
            self.prepare_new_employee(self.state.next_employee_id())
            self.request_back.emit()
            return

        self.prepare_new_employee(self.state.next_employee_id())
        self.request_back.emit()

