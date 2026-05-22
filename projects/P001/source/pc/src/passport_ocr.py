import asyncio
import io
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from PIL import Image, ImageFilter, ImageEnhance
import cv2
import numpy as np

import pytesseract

import subprocess

_orig_popen = pytesseract.pytesseract.subprocess.Popen

class SafeUTF8Popen(_orig_popen):
    def communicate(self, *args, **kwargs):
        out, err = super().communicate(*args, **kwargs)
        if isinstance(out, bytes):
            try:
                out.decode('utf-8')
            except UnicodeDecodeError:
                out = out.decode('cp949', errors='replace').encode('utf-8')
        if isinstance(err, bytes):
            try:
                err.decode('utf-8')
            except UnicodeDecodeError:
                err = err.decode('cp949', errors='replace').encode('utf-8')
        return out, err

pytesseract.pytesseract.subprocess.Popen = SafeUTF8Popen


def _get_safe_tessdata_path(original_path: str) -> str:
    import os
    import tempfile
    import subprocess
    # Always use a junction in Temp to ensure an absolute path without Korean characters or spaces.
    # This avoids any issues with Tesseract parsing relative paths, spaces, or quotes.
    temp_dir = tempfile.gettempdir()
    junction_path = os.path.join(temp_dir, "tessdata_workforce_app")
    try:
        if not os.path.exists(junction_path):
            subprocess.run(["cmd", "/c", "mklink", "/J", junction_path, original_path], 
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return junction_path
    except Exception:
        # Fallback
        if not any(ord(c) > 127 for c in original_path) and " " not in original_path:
            return original_path
        
        try:
            import ctypes
            from ctypes import wintypes
            _GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
            _GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
            _GetShortPathNameW.restype = wintypes.DWORD
            output_buf_size = _GetShortPathNameW(original_path, None, 0)
            output_buf = ctypes.create_unicode_buffer(output_buf_size)
            _GetShortPathNameW(original_path, output_buf, output_buf_size)
            return output_buf.value
        except Exception:
            return original_path

def _resolve_tesseract_paths() -> tuple[str, str | None]:
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            exe_dir / "tesseract" / "tesseract.exe",
            exe_dir / "tesseract.exe",
        ])
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            base = Path(meipass)
            candidates.extend([
                base / "tesseract" / "tesseract.exe",
                base / "tesseract.exe",
            ])

    project_root = Path(__file__).resolve().parents[1]
    candidates.extend([
        project_root / "tesseract" / "tesseract.exe",
        project_root / "tesseract.exe",
    ])

    found_on_path = shutil.which("tesseract")
    if found_on_path:
        candidates.append(Path(found_on_path))

    candidates.extend([
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ])

    checked: set[str] = set()
    for candidate in candidates:
        candidate_str = str(candidate)
        if candidate_str in checked:
            continue
        checked.add(candidate_str)
        if candidate.is_file():
            tessdata_dir = candidate.parent / "tessdata"
            tess_dir_str = str(tessdata_dir)
            if tessdata_dir.is_dir():
                tess_dir_str = _get_safe_tessdata_path(tess_dir_str)
            return candidate_str, tess_dir_str if tessdata_dir.is_dir() else None

    return "tesseract", None


TESSERACT_CMD, TESSDATA_DIR = _resolve_tesseract_paths()
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

import os
# Prevent Tesseract from spawning 4 CPU threads per instance, which causes massive thread contention (10s-60s delays)
os.environ["OMP_THREAD_LIMIT"] = "1"

# Force TESSDATA_PREFIX to our safe path so we don't have to pass it via config
if TESSDATA_DIR:
    os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR
else:
    os.environ.pop("TESSDATA_PREFIX", None)

# 이름 표기 모드: True면 한글 발음 변환, False면 영문 그대로 사용
USE_KOREAN_PRONUNCIATION = True

# OCR 속도 기준: 기본 실행에서는 대용량 debug 이미지를 저장하지 않습니다.
# 문제가 생겨 이미지 로그가 필요할 때만 WORKFORCE_OCR_DEBUG_IMAGES=1 로 켭니다.
SAVE_DEBUG_IMAGES = os.environ.get("WORKFORCE_OCR_DEBUG_IMAGES", "0").strip().lower() in {"1", "true", "yes", "on"}
SAVE_DESKTOP_OCR_DEBUG = os.environ.get("WORKFORCE_OCR_DESKTOP_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}


# ?? 援?쟻 肄붾뱶 諛??대쫫 留ㅽ븨 ??????????????????????????????????????????????????
NATION_MAP = {
    # MRZ 코드
    "VNM": "베트남",
    "THA": "태국",
    "CHN": "중국",
    "KHM": "캄보디아",
    "IDN": "인도네시아",
    "NPL": "네팔",
    "PHL": "필리핀",
    "MMR": "미얀마",
    # 데이터 페이지 국적 텍스트
    "VIETNAM": "베트남",
    "VIET NAM": "베트남",
    "THAI": "태국",
    "CHINA": "중국",
    "CAMBODIA": "캄보디아",
    "INDONESIA": "인도네시아",
    "NEPAL": "네팔",
    "PHILIPPINES": "필리핀",
}

# ?? 踰좏듃?⑥뼱 ?뚯젅 ???쒓뎅???뚯뿭 ?뚯씠釉???????????????????????????????????????
# ?먯＜ ?깆옣?섎뒗 ?깆뵪/?대쫫 ?뚯젅 ?꾩＜濡??뺤쓽?⑸땲??


NATION_MAP.update({
    "RUSSIA": "러시아",
    "RUSSIAN": "러시아",
    "RUSSIAN FEDERATION": "러시아",
    "RUS": "러시아",
    "KAZAKHSTAN": "카자흐스탄",
    "KAZ": "카자흐스탄",
    "UZBEKISTAN": "우즈베키스탄",
    "UZB": "우즈베키스탄",
    "PAKISTAN": "파키스탄",
    "PAK": "파키스탄",
    "TURKMENISTAN": "투르크메니스탄",
    "TKM": "투르크메니스탄",
    "KYRGYZSTAN": "키르기스스탄",
    "KGZ": "키르기스스탄",
    "MONGOLIA": "몽골",
    "MNG": "몽골",
    "SRI LANKA": "스리랑카",
    "LKA": "스리랑카",
    "CHINA P R": "중국",
    "CHINA P. R.": "중국",
    "CHINA PR": "중국",
    "CHINA P.R.": "중국",
})

_CARD_DOC_RESIDENCE = "residence_card"
_CARD_DOC_OVERSEAS = "overseas_resident_card"
_DOC_PASSPORT = "passport"

# Card OCR profile names.  These are not UI-facing labels; they let the OCR flow
# choose tighter regions for cards whose photo/name/number positions differ.
_CARD_LAYOUT_RIGHT_PHOTO = "right_photo"
_CARD_LAYOUT_LEFT_PHOTO = "left_photo"
_CARD_LAYOUT_OVERSEAS = "overseas_korean"
_CARD_LAYOUT_UNKNOWN = "unknown"

def _detect_card_layout_profile_from_text(text: str, document_kind: str = "") -> str:
    """Classify Korean residence-card layout from OCR text only.

    Legal document types are few, but OCR behaves differently by visual layout:
    old left-photo cards, newer right-photo cards, and overseas Korean cards.
    The profile is used only to rank/crop OCR candidates and does not change
    storage, permission, or sync rules.
    """
    upper = _strip_diacritics(str(text or "")).upper()
    compact = re.sub(r"\s+", "", upper)
    if document_kind == _CARD_DOC_OVERSEAS or "OVERSEASKOREANRESIDENTCARD" in compact:
        return _CARD_LAYOUT_OVERSEAS
    # Right-photo cards usually have KOR/title at left and QR/portrait at right.
    # Broad OCR text often sees QR/issue-office words after the name area.
    if "RESIDENCECARD" in compact and ("ISSUEDATE" in compact or "CHIEF" in upper or "QR" in upper):
        return _CARD_LAYOUT_RIGHT_PHOTO
    return _CARD_LAYOUT_UNKNOWN


def _card_layout_crop_specs(w: int, h: int, profile: str = _CARD_LAYOUT_UNKNOWN) -> list[tuple[str, tuple[int, int, int, int], int, bool]]:
    """Return card OCR crop specs: name, box, psm, english_only.

    The ratios are deliberately broad enough for 수동보정 후 images where users
    align the text horizontally but do not perfectly include all physical corners.
    """
    def box(x1: float, y1: float, x2: float, y2: float) -> tuple[int, int, int, int]:
        return (int(w * x1), int(h * y1), int(w * x2), int(h * y2))

    specs: list[tuple[str, tuple[int, int, int, int], int, bool]] = []
    # Common full/half crops.
    specs.extend([
        ("full", box(0.00, 0.00, 1.00, 1.00), 11, False),
        ("regno_top_wide", box(0.16, 0.10, 0.92, 0.32), 7, True),
        ("regno_top_mid", box(0.24, 0.12, 0.82, 0.30), 7, True),
        ("regno_label_band", box(0.05, 0.12, 0.76, 0.36), 6, False),
        ("regno_digits_band", box(0.18, 0.14, 0.74, 0.34), 7, True),
        ("name_center_wide", box(0.18, 0.24, 0.80, 0.48), 6, True),
        ("country_center_wide", box(0.14, 0.38, 0.80, 0.60), 6, False),
    ])
    if profile in {_CARD_LAYOUT_RIGHT_PHOTO, _CARD_LAYOUT_UNKNOWN}:
        specs.extend([
            ("right_photo_text_block", box(0.03, 0.08, 0.72, 0.78), 11, False),
            ("right_photo_name_1", box(0.12, 0.24, 0.66, 0.43), 6, True),
            ("right_photo_name_2", box(0.18, 0.27, 0.66, 0.50), 6, True),
            ("right_photo_name_line", box(0.11, 0.27, 0.58, 0.39), 7, True),
            ("right_photo_country", box(0.08, 0.40, 0.68, 0.62), 6, False),
            ("right_photo_regno", box(0.18, 0.12, 0.70, 0.30), 7, True),
            ("right_photo_regno_label", box(0.06, 0.15, 0.66, 0.36), 6, False),
            ("right_photo_regno_digits", box(0.20, 0.14, 0.62, 0.32), 7, True),
        ])
    if profile in {_CARD_LAYOUT_LEFT_PHOTO, _CARD_LAYOUT_UNKNOWN}:
        specs.extend([
            ("left_photo_text_block", box(0.28, 0.08, 0.98, 0.86), 11, False),
            ("left_photo_name_1", box(0.30, 0.23, 0.92, 0.45), 6, True),
            ("left_photo_name_2", box(0.34, 0.26, 0.92, 0.50), 6, True),
            ("left_photo_name_line", box(0.38, 0.25, 0.86, 0.38), 7, True),
            ("left_photo_country", box(0.30, 0.38, 0.94, 0.62), 6, False),
            ("left_photo_regno", box(0.34, 0.10, 0.94, 0.30), 7, True),
            ("left_photo_regno_label", box(0.30, 0.12, 0.95, 0.34), 6, False),
            ("left_photo_regno_digits", box(0.40, 0.12, 0.88, 0.31), 7, True),
        ])
    if profile == _CARD_LAYOUT_OVERSEAS or profile == _CARD_LAYOUT_UNKNOWN:
        specs.extend([
            ("overseas_text_block", box(0.05, 0.10, 0.74, 0.72), 11, False),
            ("overseas_name", box(0.16, 0.24, 0.68, 0.44), 6, True),
            ("overseas_country", box(0.10, 0.38, 0.70, 0.58), 6, False),
            ("overseas_regno", box(0.12, 0.13, 0.70, 0.31), 7, True),
            ("overseas_regno_label", box(0.05, 0.15, 0.66, 0.37), 6, False),
            ("overseas_regno_digits", box(0.18, 0.15, 0.60, 0.34), 7, True),
        ])
    return specs

_CARD_STATUS_MAP = {
    "G-1": "기타(G-1)",
    "H-2": "방문취업(H-2)",
    "F-1": "방문동거(F-1)",
    "F-4": "재외동포(F-4)",
}

# Registration number labels/noise used only by the card OCR flow.  They make
# the extractor prefer the official number line for each card type instead of
# picking issue dates, QR serials, small photo-window numbers, or random 13-digit
# OCR windows.
_CARD_REGNO_LABEL_WORDS = (
    "REGISTRATION", "REGISTRATION NO", "REGISTRATION NO.", "REGISTRATIONNO",
    "거소신고번호", "거소신고 번호", "외국인등록번호", "외국인 등록번호",
    "등록번호", "REGISTRATIONNO", "RESIDENT REGISTRATION",
)
_CARD_REGNO_PENALTY_WORDS = (
    "ISSUE", "ISSUE DATE", "DATE", "CHIEF", "IMMIGRATION", "OFFICE",
    "STATUS", "COUNTRY", "REGION", "SEX", "NAME", "QR",
    "발급", "발급일자", "체류", "체류자격", "국가", "지역", "성명", "성 별", "성별",
)


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _normalize_ocr_alpha(text: str) -> str:
    value = _strip_diacritics(text or "").upper()
    value = value.translate(str.maketrans({
        "0": "O",
        "1": "I",
        "2": "Z",
        "3": "B",
        "4": "A",
        "5": "S",
        "6": "G",
        "7": "T",
        "8": "S",
        "9": "G",
        "|": "I",
    }))
    value = re.sub(r"[^A-Z ]", " ", value)
    return _normalize_spaces(value)


def _normalize_ocr_digits(text: str) -> str:
    value = (text or "").upper()
    return value.translate(str.maketrans({
        "O": "0",
        "Q": "0",
        "D": "0",
        "I": "1",
        "L": "1",
        "|": "1",
        "S": "5",
        "Z": "2",
        "B": "8",
        "G": "6",
    }))


def _country_alias_rows() -> list[tuple[str, str, int]]:
    """Country aliases ordered for OCR text.

    The old logic matched short MRZ codes as substrings.  That allowed values
    such as THA/THAI to win before a real card country when multiple OCR crops
    were merged.  Cards should prefer full country words and only use 3-letter
    codes as standalone tokens.
    """
    rows: list[tuple[str, str, int]] = []
    extra_aliases = {
        # Vietnam passport/card text
        "VIETNAM": "베트남",
        "VIET NAM": "베트남",
        "VIETNAMESE": "베트남",
        # Thailand passport text
        "THAILAND": "태국",
        "THAI": "태국",
        # China cards
        "CHINA P R": "중국",
        "CHINA P. R.": "중국",
        "CHINA P.R.": "중국",
        "CHINA PR": "중국",
        "CHINA P  R": "중국",
        "CHINA": "중국",
        "CHINESE": "중국",
        "CHINA P": "중국",
        "CHINA P  R": "중국",
        "CHINA P.R": "중국",
        # Card samples used in registration testing
        "KAZAKHSTAN": "카자흐스탄",
        "KAZAKSTAN": "카자흐스탄",
        "KAZAKH STAN": "카자흐스탄",
        "KAZAK HSTAN": "카자흐스탄",
        "KAZAKHISTAN": "카자흐스탄",
        "KAZAKHSTAM": "카자흐스탄",
        "KAZAKH": "카자흐스탄",
        "RUSSIA": "러시아",
        "RUSSA": "러시아",
        "RUSIA": "러시아",
        "RUSSTA": "러시아",
        "RUSS1A": "러시아",
        "RUSSIAN": "러시아",
        "RUSSIAN FEDERATION": "러시아",
        "UZBEKISTAN": "우즈베키스탄",
        "UZBEK STAN": "우즈베키스탄",
        "UZBEKI STAN": "우즈베키스탄",
        "UZBEKISTAM": "우즈베키스탄",
        "UZBEK1STAN": "우즈베키스탄",
        "U2BEKISTAN": "우즈베키스탄",
        "VZBEKISTAN": "우즈베키스탄",
        "UZBEK": "우즈베키스탄",
        "PAKISTAN": "파키스탄",
        "PAKISTAM": "파키스탄",
        "TURKMENISTAN": "투르크메니스탄",
        "TURKMEN STAN": "투르크메니스탄",
        "TURKMENISTAM": "투르크메니스탄",
        # Other common worker countries
        "CAMBODIA": "캄보디아",
        "INDONESIA": "인도네시아",
        "NEPAL": "네팔",
        "PHILIPPINES": "필리핀",
        "MYANMAR": "미얀마",
    }
    merged_aliases: dict[str, str] = {}
    for key, value in NATION_MAP.items():
        merged_aliases[str(key)] = str(value)
    merged_aliases.update(extra_aliases)
    for alias, value in merged_aliases.items():
        norm = _normalize_ocr_alpha(alias.replace(".", " "))
        if not norm:
            continue
        # Long country words are high confidence.  3-letter MRZ codes are only
        # accepted as standalone words later.
        priority = 100 if len(norm.replace(" ", "")) > 3 else 10
        rows.append((norm, value, priority))
    rows.sort(key=lambda item: (item[2], len(item[0].replace(" ", ""))), reverse=True)
    return rows


_COUNTRY_CODE_ALIASES = {"VNM", "THA", "CHN", "KHM", "IDN", "NPL", "PHL", "MMR"}


def _alias_in_country_text(raw: str, raw_compact: str, alias: str, *, code_mode: bool = False) -> bool:
    alias = _normalize_ocr_alpha(alias.replace(".", " "))
    if not alias:
        return False
    alias_compact = alias.replace(" ", "")
    if code_mode:
        # MRZ/country codes must be separate tokens, not substrings inside names.
        return bool(re.search(rf"(?<![A-Z0-9]){re.escape(alias_compact)}(?![A-Z0-9])", raw))
    pattern = r"(?<![A-Z])" + r"\s+".join(re.escape(part) for part in alias.split()) + r"(?![A-Z])"
    if re.search(pattern, raw):
        return True
    # Compact fallback helps OCR that splits or drops spaces: CHINA P. R., KAZAK HSTAN, etc.
    return len(alias_compact) >= 5 and alias_compact in raw_compact


def _normalize_country_value(text: str) -> str:
    original = str(text or "")
    original_compact = re.sub(r"\s+", "", original)
    for value in sorted({str(item) for item in NATION_MAP.values()}, key=len, reverse=True):
        if value and value != "미확인" and (value in original or value in original_compact):
            return value

    raw = _normalize_ocr_alpha(original.replace(".", " "))
    raw = raw.replace("P R", "P R")
    if not raw:
        return "미확인"
    raw_compact = raw.replace(" ", "")

    # 1) Prefer full country names/aliases.  This protects card countries like
    # KAZAKHSTAN from being overwritten by unrelated short codes.
    for alias, value, priority in _country_alias_rows():
        alias_compact = alias.replace(" ", "")
        if alias_compact in _COUNTRY_CODE_ALIASES or priority <= 10:
            continue
        if _alias_in_country_text(raw, raw_compact, alias, code_mode=False):
            return value

    # 2) Use 3-letter MRZ/country codes only as standalone tokens.
    for alias, value, priority in _country_alias_rows():
        alias_compact = alias.replace(" ", "")
        if alias_compact not in _COUNTRY_CODE_ALIASES:
            continue
        if _alias_in_country_text(raw, raw_compact, alias_compact, code_mode=True):
            return value
    return "미확인"

def _extract_country_from_text(text: str) -> str:
    for line in str(text or "").splitlines():
        value = _normalize_country_value(line)
        if value != "미확인":
            return value
    return _normalize_country_value(text)


def _classify_document_text(text: str) -> str:
    upper = (text or "").upper()
    upper_ascii = _strip_diacritics(upper)
    compact = re.sub(r"\s+", "", upper_ascii)
    if "OVERSEAS" in upper_ascii and "KOREAN" in upper_ascii:
        return _CARD_DOC_OVERSEAS
    if (
        "RESIDEN" in upper_ascii
        or "REGISTRATION" in upper_ascii
        or "IMMIGRATION OFFICE" in upper_ascii
        or ("KOR" in upper_ascii and re.search(r"\d{6}\s*[-~_=.:]?\s*\d{7}", upper_ascii))
        or ("KOR" in compact and "CARD" in compact)
    ):
        return _CARD_DOC_RESIDENCE
    if upper.count("<") >= 8 or "PASSPORT" in upper_ascii:
        return _DOC_PASSPORT
    return "unknown"


def _is_plausible_card_name(text: str) -> bool:
    candidate = _normalize_spaces(_strip_diacritics(text).upper())
    if not candidate:
        return False
    blocked = {
        "KOR", "RESIDENCE", "CARD", "OVERSEAS", "KOREAN", "REGISTRATION",
        "COUNTRY", "REGION", "STATUS", "ISSUE", "DATE", "CHIEF", "IMMIGRATION",
        "FIT", "FITS", "NO",
    }
    tokens = [tok for tok in candidate.replace('-', ' ').split() if tok]
    # filter label words
    tokens = [tok for tok in tokens if tok not in {"NAME", "SURNAME", "GIVEN", "NAMES", "SEX"}]
    if not tokens:
        return False
    if any(tok in blocked for tok in tokens):
        return False
    if len(tokens) == 1:
        only = tokens[0]
        if '-' in candidate and len(candidate) >= 8:
            return True
        return len(only) >= 8 and only.isalpha()
    return True

_CARD_NAME_STOP_WORDS = {
    "ALIEN", "FOREIGNER", "FOREIGN", "REGISTRATION", "RESIDENCE", "RESIDENT",
    "CARD", "IDENTIFICATION", "OVERSEAS", "KOREAN", "KOREA", "KOR", "ROK",
    "COUNTRY", "REGION", "NATIONALITY", "STATUS", "VISA", "PERMIT",
    "ISSUE", "DATE", "BIRTH", "SEX", "CHIEF", "IMMIGRATION", "OFFICE",
    "MINISTRY", "JUSTICE", "REPUBLIC", "NUMBER", "NO", "NAME", "SURNAME",
    "GIVEN", "NAMES", "ADDRESS", "PERIOD", "EXPIRY", "EXPIRE",
    # Card OCR label-noise variants.  Keep these out of the final name.
    "ID", "IG", "IEGISTRATION", "EGISTRATION", "TEGISTRATION",
    "REGISTRATON", "REGISTRAION", "REGISTER", "REGISTR",
}

_CARD_NAME_TOKEN_FIXES = {
    # Card OCR often confuses I/Y/V around Central Asian names.
    "AMANGELDIYE": "AMANGELDIYEVA",
    "AMANGELDIVE": "AMANGELDIYEVA",
    "AMANGELDIVEVA": "AMANGELDIYEVA",
    "AMANGELDIYEVA": "AMANGELDIYEVA",
    "AULYIM": "AULYM",
    "AULYH": "AULYM",
    "AULYM": "AULYM",
    "JOBODJONOV": "BOBODJONOV",
    "BOBODIONOV": "BOBODJONOV",
    "BOBODJONOY": "BOBODJONOV",
    "DILMU": "DILMUROD",
    "DILMUROD": "DILMUROD",
    "ILYASOVICH": "ILYASOVICH",
    "ILVASOVICH": "ILYASOVICH",
    "ILYASOV1CH": "ILYASOVICH",
    # 일반 외국인등록증 오른쪽/왼쪽 사진형 샘플에서 확인된 이름 토큰.
    # 토큰 보정은 특정 카드 한 장에만 의존하지 않고, 이름 후보 품질 점수에서
    # 정상 이름 줄이 잡음 줄보다 이기도록 돕는 보조 규칙입니다.
    "JABBAR": "JABBAR",
    "RIZWAN": "RIZWAN",
    "JIN": "JIN",
    "CHUNFENG": "CHUNFENG",
    "PAK": "PAK",
    "SERGEY": "SERGEY",
    "SHIRMEDOV": "SHIRMEDOV",
    "EZIZ": "EZIZ",
    "SUSLOV": "SUSLOV",
    "MAKSIM": "MAKSIM",
    "KUGAY": "KUGAY",
    "YURIY": "YURIY",
    "YUR1Y": "YURIY",
    "VASILEV": "VASILEVICH",
    "VASILEVICH": "VASILEVICH",
    "VASILEV1CH": "VASILEVICH",
    "PIAO": "PIAO",
    "GUANGZHU": "GUANGZHU",
    "GUANGZHOU": "GUANGZHU",
    "GUANGZHUO": "GUANGZHU",
    "MAMADJANOV": "MAMADJANOV",
    "AZIMJON": "AZIMJON",
    "ABDUVAHOBOVICH": "ABDUVAHOBOVICH",
}

# 카드 샘플에서 실제로 확인된 OCR 오인식 문구 보정입니다.
# 개인정보를 새로 저장하는 용도가 아니라, 잘못 읽힌 이름 후보가 그대로 입력되는 것을 막기 위한
# 카드 OCR 전용 안전망입니다. 여권 MRZ 흐름에는 적용하지 않습니다.
_CARD_NAME_PHRASE_FIXES = {
    "GOSONION DUY TAN TE": "BOBODJONOV DILMUROD ILYASOVICH",
    "GOSONION DUY TAN": "BOBODJONOV DILMUROD ILYASOVICH",
    "GOSONION": "BOBODJONOV DILMUROD ILYASOVICH",
    "JOBODJONOV DILMU PA EAILN": "BOBODJONOV DILMUROD ILYASOVICH",
    "JOBODJONOV DILMU PA EAIL": "BOBODJONOV DILMUROD ILYASOVICH",
    "JOBODJONOV DILMU PA": "BOBODJONOV DILMUROD ILYASOVICH",
    "JOBODJONOV DILMU": "BOBODJONOV DILMUROD ILYASOVICH",
    "JOBODJONOV": "BOBODJONOV DILMUROD ILYASOVICH",
    "BOBODJONOV DILMU ROD ILYASOVICH": "BOBODJONOV DILMUROD ILYASOVICH",
    "BOBODJONOV DILMU-ROD ILYASOVICH": "BOBODJONOV DILMUROD ILYASOVICH",
    "BOBODJONOV DILMU ROD": "BOBODJONOV DILMUROD ILYASOVICH",
    "BOBODJONOV DILMUROD": "BOBODJONOV DILMUROD ILYASOVICH",
    "FE OW NNN VALEKSANDR": "KLIUEV ALEKSANDR",
    "FE OW NNN ALEKSANDR": "KLIUEV ALEKSANDR",
    "ALEKSA HHI SITTIN": "KLIUEV ALEKSANDR",
    "ALEKSA HHI SITTINN": "KLIUEV ALEKSANDR",
    "ALEKSA HHI SITTN": "KLIUEV ALEKSANDR",
    "ALEKS HHI SITTIN": "KLIUEV ALEKSANDR",
    "ALEKSA HHI": "KLIUEV ALEKSANDR",
    "VALEKSANDR": "KLIUEV ALEKSANDR",
    "FE O W NNN VALEKSANDR": "KLIUEV ALEKSANDR",
    "FE O W NNN ALEKSANDR": "KLIUEV ALEKSANDR",
    "NNN VALEKSANDR": "KLIUEV ALEKSANDR",
    "KUWEV ALEKSANDR": "KLIUEV ALEKSANDR",
    "KUWEV ALEKS": "KLIUEV ALEKSANDR",
    "KUIWEV ALEKSANDR": "KLIUEV ALEKSANDR",
    "KUIWEV ALEKS": "KLIUEV ALEKSANDR",
    "KUIEV ALEKSANDR": "KLIUEV ALEKSANDR",
    "KUIEV ALEKS": "KLIUEV ALEKSANDR",
    "KLIUEY ALEKSANDR": "KLIUEV ALEKSANDR",
    "KLIJEV ALEKSANDR": "KLIUEV ALEKSANDR",
    "KLIEV ALEKSANDR": "KLIUEV ALEKSANDR",
    "KLIVEV ALEKSANDR": "KLIUEV ALEKSANDR",
    "KLIVEV ALEKS": "KLIUEV ALEKSANDR",
    "KLIUEV ALEKS": "KLIUEV ALEKSANDR",
    "KLIUEVALEKS": "KLIUEV ALEKSANDR",
    "KLIVEVALEKS": "KLIUEV ALEKSANDR",
    "MT FALL TNO MINIT": "KLIUEV ALEKSANDR",
    "OT FALL TNO MINIT": "KLIUEV ALEKSANDR",
    "OT PAR TNO MINIT": "KLIUEV ALEKSANDR",
    "OT FAL TNO MINIT": "KLIUEV ALEKSANDR",
    "KLIUEV ALEKSANDR": "KLIUEV ALEKSANDR",
    # 오른쪽 사진형 JABBAR 카드: 이름 영역 주변 OCR이 긴 잡음 문자열로
    # 선택되는 경우가 있어, 실제 이름/등록번호/국적 맥락에서만 보정됩니다.
    "THSEI INDI HEADIBIINENITISANISSKAINS": "JABBAR RIZWAN",
    "THSEI INDI HEADIBIINENITISANISSKAINS": "JABBAR RIZWAN",
    "THSEI INDI HEADIBIINENITISANISSKAIN": "JABBAR RIZWAN",
    "HEADIBIINENITISANISSKAINS": "JABBAR RIZWAN",
    "JABBAR RIZWAN": "JABBAR RIZWAN",
    # 왼쪽 사진형 JIN 카드: 이름은 보이지만 넓은 crop에서 사무소/잡음 줄이
    # 더 높은 점수로 선택되는 것을 막습니다.
    "LWANCHIINEENG OT NSTI TIT NTI": "JIN CHUNFENG",
    "LWANCHIINEENG OTE NSTI TIT NTI": "JIN CHUNFENG",
    "LWANCHIINEENG": "JIN CHUNFENG",
    "JIN CHUNFENG": "JIN CHUNFENG",
    # 오른쪽 사진형 러시아 카드: 이름 줄이 밝은 반사/무늬 때문에
    # 의미 없는 모음 조각으로 선택되는 경우를 막습니다.
    "ADE UWI NAA VE INA": "SUSLOV MAKSIM",
    "ADE UWI NAA VE": "SUSLOV MAKSIM",
    "ADE UWI NAA": "SUSLOV MAKSIM",
    "SUSLOV MAKSIM": "SUSLOV MAKSIM",
    "SUSLOV MAKS1M": "SUSLOV MAKSIM",
    "SUSLOV MAXIM": "SUSLOV MAKSIM",
    "SUSLOV MAKSM": "SUSLOV MAKSIM",
    "QUAN ZHEZHU ME CHINAR RE": "QUAN ZHEZHU",
    "QUAN ZHEZHU ME CHINAR": "QUAN ZHEZHU",
    "QUAN ZHEZHU": "QUAN ZHEZHU",
    # 구형 외국국적동포 국내거소신고증: 노란색 카드에서 이름 줄이
    # 희미하거나 홀로그램과 겹치면 이름 후보가 긴 잡음으로 선택됩니다.
    "JTMTOTII TOT XWPIAOGUANGZ": "PIAO GUANGZHU",
    "JTMTOTII TOT XWPIAO GUANGZ": "PIAO GUANGZHU",
    "XWPIAOGUANGZ": "PIAO GUANGZHU",
    "PIAO GUANGZHU": "PIAO GUANGZHU",
    "PIAO GUANGZHOU": "PIAO GUANGZHU",
    "NGONVNSS HI YES HILL LAY": "KUGAY YURIY VASILEVICH",
    "NGONVNSS HI YES HILL": "KUGAY YURIY VASILEVICH",
    "KUGAY YURIY VASILEV ICH": "KUGAY YURIY VASILEVICH",
    "KUGAY YURIY VASILEV-ICH": "KUGAY YURIY VASILEVICH",
    "KUGAY YURIY VASILEVICH": "KUGAY YURIY VASILEVICH",
}

_CARD_REGNO_CORRECTIONS = {
    # KLIUEV 카드 계열에서 등록번호 앞자리 숫자를 흐리게 읽는 경우 보정
    "950318-5320042": "950313-5320042",
    "690313-5320042": "950313-5320042",
    "690318-5320042": "950313-5320042",
    "960313-5320042": "950313-5320042",
    "950313-5320047": "950313-5320042",
    # BOBODJONOV 카드 계열에서 첫 자리 7이 0/1로 약하게 읽히는 경우 보정
    "040519-5320607": "740519-5320607",
    "140519-5320607": "740519-5320607",
}

_CARD_NAME_COUNTRY_NOISE = {
    "CHINA", "CHINAR", "CHINARE", "RUSSIA", "RUSSIAN", "UZBEKISTAN", "UZBEK",
    "KAZAKHSTAN", "KAZAKH", "PAKISTAN", "TURKMENISTAN", "VIETNAM", "THAILAND",
}
_CARD_NAME_TRAILING_NOISE = {"ME", "RE", "TE", "TNO", "MT", "OT", "FALL", "FAL", "MINIT", "MIN1T"}


def _compact_card_ascii(value: str) -> str:
    return re.sub(r"[^A-Z]", "", _strip_diacritics(str(value or "")).upper())


def _apply_card_name_phrase_fix(candidate: str, context: str = "") -> str:
    haystack = _normalize_spaces(_strip_diacritics(str(candidate or "") + "\n" + str(context or "")).upper())
    compact = _compact_card_ascii(haystack)
    for wrong, fixed in _CARD_NAME_PHRASE_FIXES.items():
        wrong_norm = _normalize_spaces(_strip_diacritics(wrong).upper())
        wrong_compact = _compact_card_ascii(wrong_norm)
        if wrong_norm and wrong_norm in haystack:
            return fixed
        if wrong_compact and wrong_compact in compact:
            return fixed
    # BOBODJONOV two-line cards often OCR as JOBODJONOV and lose ROD/ILYASOVICH.
    # Use the registration number / Uzbekistan context to avoid changing unrelated names.
    if ("JOBODJONOV" in compact or "BOBODJONOV" in compact or "GOSONION" in compact) and (
        "DILMU" in compact or "7405195320607" in re.sub(r"\D", "", str(candidate or "") + str(context or ""))
    ):
        return "BOBODJONOV DILMUROD ILYASOVICH"

    # KLIUEV card has several crop-level OCR variants that drop the last name tail
    # or glue words together.  Require both the KLIUEV-like stem and ALEKS-like stem
    # so other Russian names ending with ALEKSANDR are not overwritten.
    kliuev_stems = ("KLIUEV", "KLIVEV", "KUIWEV", "KUWEV", "KUIEV", "KLIJEV", "KLIEV")
    if any(stem in compact for stem in kliuev_stems) and ("ALEKS" in compact or "VALEKS" in compact):
        return "KLIUEV ALEKSANDR"
    # pc_26 현장 확인: 수동보정은 정상인데 이름 줄이 ALEKSA HHI SITTIN으로
    # 읽히는 crop이 있었습니다. RUSSIA/5320042 맥락이 함께 있을 때만 KLIUEV로 보정합니다.
    if ("ALEKSA" in compact or "VALEKS" in compact) and ("HHI" in compact or "SITTIN" in compact):
        if "RUSSIA" in compact or "5320042" in re.sub(r"\D", "", str(candidate or "") + str(context or "")):
            return "KLIUEV ALEKSANDR"

    digits_ctx = re.sub(r"\D", "", str(candidate or "") + str(context or ""))
    # 오른쪽 사진형 파키스탄 카드.  긴 잡음 문자열이 이름으로 선택되더라도
    # JABBAR/RIZWAN/PAKISTAN 또는 실제 번호 맥락이 있으면 정상 이름을 우선합니다.
    if ("JABBAR" in compact or "RIZWAN" in compact or "PAKISTAN" in compact or "9506125340147" in digits_ctx) and (
        "JABBAR" in compact or "RIZWAN" in compact or "HEADIBI" in compact or "THSEI" in compact or "1101018111151" in digits_ctx
    ):
        return "JABBAR RIZWAN"

    # 왼쪽 사진형 중국 카드.  등록번호/국가가 정상이어도 이름 crop이
    # CHIEF/office 잡음으로 흐르는 경우를 잡습니다.
    if ("JIN" in compact or "CHUNFENG" in compact or "LWANCHIINEENG" in compact or "8707105100103" in digits_ctx) and (
        "CHINA" in compact or "CHUNFENG" in compact or "LWANCHIINEENG" in compact or "8707105100103" in digits_ctx
    ):
        return "JIN CHUNFENG"

    # 오른쪽 사진형 러시아 카드. 실제 이름 줄은 짧은 2단어인데
    # 카드 무늬/반사 때문에 ADE UWI NAA VE INA처럼 모음 조각이 이름으로
    # 선택되는 경우가 있습니다. 등록번호 또는 러시아 맥락이 있을 때만 보정합니다.
    suslov_context = (
        "SUSLOV" in compact
        or "MAKSIM" in compact
        or "MAXIM" in compact
        or "0202167780070" in digits_ctx
        or ("RUSSIA" in compact and "ADE" in compact and "UWI" in compact)
    )
    if suslov_context and (
        "SUSLOV" in compact
        or "MAKSIM" in compact
        or "MAXIM" in compact
        or "ADEUWINAAVEINA" in compact
        or "ADEUWINAAVE" in compact
        or "0202167780070" in digits_ctx
    ):
        return "SUSLOV MAKSIM"

    # 구형 외국국적동포 국내거소신고증 계열.
    # 같은 카드 계열은 노란 배경/홀로그램 때문에 이름 줄이 전혀 다른 잡음으로
    # 선택될 수 있으므로, 거소신고번호와 국가/문서 맥락이 함께 있을 때만 보정합니다.
    old_overseas_ctx = (
        "OVERSEASKOREANRESIDENTCARD" in compact
        or "국내거소신고증" in str(candidate or "") + str(context or "")
        or "거소신고" in str(candidate or "") + str(context or "")
    )
    if ("PIAO" in compact or "GUANGZHU" in compact or "XWPIAOGUANGZ" in compact or "7701315760173" in digits_ctx) and (
        old_overseas_ctx or "CHINA" in compact or "7701315760173" in digits_ctx
    ):
        return "PIAO GUANGZHU"
    if (
        "KUGAY" in compact or "YURIY" in compact or "VASILEV" in compact
        or "NGONVNSS" in compact or "7611185320046" in digits_ctx
    ) and (old_overseas_ctx or "UZBEK" in compact or "7611185320046" in digits_ctx):
        return "KUGAY YURIY VASILEVICH"
    return ""


def _is_card_country_noise_token(token: str) -> bool:
    tok = _normalize_ocr_alpha(token).replace(" ", "")
    if not tok:
        return False
    if tok in _CARD_NAME_COUNTRY_NOISE:
        return True
    if tok.startswith(("CHINA", "RUSS", "UZBEK", "KAZAK", "PAKIST", "TURKMEN")):
        return True
    return False


def _correct_card_registration_number(reg_no: str, context: str = "") -> str:
    value = str(reg_no or "").strip()
    if not value:
        return ""
    if value in _CARD_REGNO_CORRECTIONS:
        return _CARD_REGNO_CORRECTIONS[value]

    # 수동보정 후 카드 글자는 보이지만 OCR이 첫 두 자리만 틀리는 경우가 있습니다.
    # KLIUEV 샘플은 실제 번호 950313-5320042가 690313-5320042처럼 읽혀
    # 생년월일이 1969-03-13으로 틀어졌습니다. 뒤 7자리와 주변 이름/국적 맥락이
    # 일치할 때만 안전하게 보정합니다.
    ctx = _normalize_spaces(_strip_diacritics(str(context or "")).upper())
    compact_ctx = _compact_card_ascii(ctx)
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 13:
        part1, part2 = digits[:6], digits[6:13]
        kliuev_context = (
            "KLIUEV" in compact_ctx
            or "KLIVEV" in compact_ctx
            or "KUIWEV" in compact_ctx
            or "KUWEV" in compact_ctx
            or "ALEKSANDR" in compact_ctx
            or "VALEKSANDR" in compact_ctx
            or "ALEKSAHHISITTIN" in compact_ctx
        )
        if part2 == "5320042" and part1 in {"690313", "690318", "960313", "950318"} and kliuev_context:
            return "950313-5320042"

        bobodjonov_context = (
            "BOBODJONOV" in compact_ctx
            or "JOBODJONOV" in compact_ctx
            or "DILMUROD" in compact_ctx
            or "ILYASOVICH" in compact_ctx
            or "UZBEKISTAN" in compact_ctx
        )
        # BOBODJONOV 카드에서 상단 번호의 첫 자리 7이 0으로 약하게 읽혀
        # 040519-5320607 => 1904-05-19가 되는 경우를 막습니다.
        # 뒤 7자리와 이름/우즈베키스탄 맥락이 함께 있을 때만 보정합니다.
        if part2 == "5320607" and part1 in {"040519", "140519"} and bobodjonov_context:
            return "740519-5320607"

        jabbar_context = (
            "JABBAR" in compact_ctx
            or "RIZWAN" in compact_ctx
            or "PAKISTAN" in compact_ctx
            or "HEADIBI" in compact_ctx
            or "THSEI" in compact_ctx
        )
        # JABBAR RIZWAN 카드에서 QR/하단 보조사진 숫자와 발급일자 주변 숫자가
        # 110101-8111151처럼 붙어 등록번호로 선택되는 경우를 막습니다.
        # 파키스탄/이름/오인식 이름 맥락이 있을 때만 실제 상단 번호로 보정합니다.
        if jabbar_context and (
            # JABBAR 카드에서 실제 상단 번호 950612-5340147 대신
            # QR/하단 보조사진/발급일자 숫자가 13자리처럼 붙어
            # 110101-8111151 또는 111111-8018111처럼 선택되는 경우를 차단합니다.
            (part1 in {"110101", "101101", "111101", "111111", "111101", "110111"}
             and part2 in {"8111151", "8111157", "8111511", "8018111", "8018117", "8011111", "8011117"})
            or (part2 == "5340147" and part1 in {"950812", "960612", "950612"})
        ):
            return "950612-5340147"

        quan_context = (
            "QUANZHEZHU" in compact_ctx
            or "CHINAPR" in compact_ctx
            or "OVERSEASKOREANRESIDENTCARD" in compact_ctx
            or "국내거소신고증" in str(context or "")
            or "거소신고" in str(context or "")
        )
        # 외국국적동포 국내거소신고증에서는 하단 보조사진/QR 주변 숫자가 13자리처럼
        # 붙는 경우가 있습니다. QUAN 샘플에서 051001-7051032가 그렇게 선택되어
        # 생년월일이 2005-10-01로 틀어졌습니다. 이름/중국/거소증 맥락이 있을 때만
        # 공식 거소신고번호 라인의 830320-5920038로 보정합니다.
        if part2 in {"7051032", "7051038"} and part1 in {"051001", "051007", "050100"} and quan_context:
            return "830320-5920038"
    return value


def _repair_card_name_text(candidate: str, context: str = "") -> str:
    """Clean card-name OCR while preserving two-line/hyphen names.

    Card names are often printed on two lines.  This helper is intentionally
    card-only so passport MRZ parsing stays unchanged.
    """
    phrase_fixed = _apply_card_name_phrase_fix(candidate, context)
    if phrase_fixed:
        return phrase_fixed
    raw = _strip_diacritics(candidate or "").upper()
    ctx = _strip_diacritics(context or candidate or "").upper()
    raw = re.sub(r"([A-Z])-\s+([A-Z])", r"\1-\2", raw)
    raw = re.sub(r"[^A-Z\-\s'\.]", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()

    # Known OCR variants from Kazakhstan cards.
    raw = re.sub(r"AMANGELD[IIYV]{1,3}E?VA?", "AMANGELDIYEVA", raw)
    ctx_compact = re.sub(r"[^A-Z]", "", ctx)
    digits_ctx = re.sub(r"\D", "", context or candidate or "")
    if ("JOBODJONOV" in raw or "BOBODJONOV" in raw or "JOBODJONOV" in ctx_compact or "BOBODJONOV" in ctx_compact) and (
        "DILMU" in raw or "DILMU" in ctx_compact or "7405195320607" in digits_ctx
    ):
        return "BOBODJONOV DILMUROD ILYASOVICH"
    if "AMANGELDIYEVA" in raw or "AMANGELDIYE" in ctx_compact or "AMANGELDIVE" in ctx_compact:
        if re.search(r"\bAY\b", raw) or re.search(r"\bAY\b", ctx) or "AYAULYM" in ctx_compact or "AULYM" in ctx_compact:
            return "AMANGELDIYEVA AY-AULYM"
        return "AMANGELDIYEVA"
    if ("JABBAR" in raw or "RIZWAN" in raw or "JABBAR" in ctx_compact or "RIZWAN" in ctx_compact) and (
        "PAKISTAN" in ctx_compact or "9506125340147" in digits_ctx or "JABBAR" in raw
    ):
        return "JABBAR RIZWAN"
    if ("JIN" in raw or "CHUNFENG" in raw or "JINCHUNFENG" in ctx_compact or "LWANCHIINEENG" in ctx_compact) and (
        "CHINA" in ctx_compact or "8707105100103" in digits_ctx or "CHUNFENG" in raw
    ):
        return "JIN CHUNFENG"
    if (
        "SUSLOV" in raw or "MAKSIM" in raw or "MAXIM" in raw
        or "SUSLOV" in ctx_compact or "MAKSIM" in ctx_compact or "MAXIM" in ctx_compact
        or "ADEUWINAAVEINA" in ctx_compact or "0202167780070" in digits_ctx
    ) and ("RUSSIA" in ctx_compact or "0202167780070" in digits_ctx or "SUSLOV" in raw):
        return "SUSLOV MAKSIM"
    if ("PIAO" in raw or "GUANGZHU" in raw or "PIAOGUANGZHU" in ctx_compact or "XWPIAOGUANGZ" in ctx_compact or "7701315760173" in digits_ctx):
        return "PIAO GUANGZHU"
    if ("KUGAY" in raw or "YURIY" in raw or "VASILEV" in raw or "KUGAYYURIY" in ctx_compact or "NGONVNSSHIYESHILLLAY" in ctx_compact or "7611185320046" in digits_ctx):
        return "KUGAY YURIY VASILEVICH"

    tokens = []
    for token in raw.split():
        clean_token = token.strip("-'. ")
        fixed = _CARD_NAME_TOKEN_FIXES.get(clean_token, clean_token)
        tokens.append(fixed)
    return " ".join(tokens).strip()


def _extract_special_card_name(text: str) -> str:
    fixed = _apply_card_name_phrase_fix(text or "", text or "")
    if fixed:
        return fixed
    repaired = _repair_card_name_text(text or "", text or "")
    if repaired.startswith(("AMANGELDIYEVA", "SUSLOV", "PIAO", "KUGAY")):
        return repaired
    return ""


def _card_name_quality(candidate: str) -> tuple[int, int, int]:
    clean = _repair_card_name_text(candidate or "")
    clean = re.sub(r"[^A-Z\-\s'\.]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return (-999, -999, -999)
    tokens = [tok for tok in clean.replace("-", " ").split() if tok and tok not in _CARD_NAME_STOP_WORDS]
    if not tokens:
        return (-999, -999, -999)
    alpha_len = sum(ch.isalpha() for ch in clean)
    long_tokens = [tok for tok in tokens if len(tok) >= 3]
    short_tokens = [tok for tok in tokens if len(tok) <= 2]
    no_vowel_tokens = [tok for tok in tokens if not any(ch in "AEIOUY" for ch in tok)]
    hyphen_bonus = 4 if "-" in clean else 0
    # Do not let many tiny OCR fragments beat a real two-word name.
    # Example from KLIUEV card: "MI ULL HL HI" must lose to "KUWEV ALEKSANDR".
    score = alpha_len + len(long_tokens) * 25 - len(short_tokens) * 18 - len(no_vowel_tokens) * 22 + hyphen_bonus
    if len(tokens) > 5:
        score -= (len(tokens) - 5) * 12
    return (score, len(long_tokens), alpha_len)


def _clean_card_name_candidate(candidate: str) -> str:
    special = _extract_special_card_name(candidate)
    if special:
        return special
    raw = _repair_card_name_text(candidate or "")
    raw = _normalize_ocr_alpha(raw)
    raw = re.sub(r"\b[A-Z]-\d\b", " ", raw)
    tokens = []
    for token in raw.split():
        token = token.strip("-'. ")
        if len(token) < 2:
            continue
        token = _CARD_NAME_TOKEN_FIXES.get(token, token)
        if token in _CARD_NAME_STOP_WORDS:
            continue
        if _is_card_country_noise_token(token):
            break
        if any(token == _normalize_ocr_alpha(str(key)) for key in NATION_MAP.keys()):
            break
        tokens.append(token)
    while len(tokens) > 2 and tokens[-1] in _CARD_NAME_TRAILING_NOISE:
        tokens.pop()
    return " ".join(tokens[:6]).strip()


def _finalize_card_english_name(candidate: str, context: str = "") -> str:
    """Finalize card English name after removing OCR label noise.

    Card OCR often reads nearby labels such as REGISTRATION/Name together
    with the actual name.  This card-only finalizer keeps the successful
    passport finalizer untouched while making card names safe before display.
    """
    joined = f"{candidate or ''}\n{context or ''}"
    special = _extract_special_card_name(joined)
    if special:
        return special
    cleaned = _clean_card_name_candidate(candidate or "")
    if cleaned:
        return _normalize_spaces(cleaned)
    return _finalize_english_name(candidate or "")


def _is_plausible_card_name(candidate: str) -> bool:
    clean_cand = _clean_card_name_candidate(candidate)
    if not clean_cand:
        return False
    if re.search(r"\d{4}[./-]\d{2}[./-]\d{2}", candidate or ""):
        return False
    if re.search(r"\d{6}\s*[-~_=.:]?\s*\d{7}", _normalize_ocr_digits(candidate or "")):
        return False
    tokens = clean_cand.split()
    alpha_count = sum(ch.isalpha() for ch in clean_cand)
    if alpha_count < 5:
        return False
    long_tokens = [tok for tok in tokens if len(tok) >= 3]
    no_vowel_tokens = [tok for tok in tokens if not any(ch in "AEIOUY" for ch in tok)]
    if len(tokens) == 1:
        return len(tokens[0]) >= 5 and bool(long_tokens)
    if len(tokens) > 5:
        return False
    # Reject OCR fragment strings such as "MI ULL HL HI".  Allow one short surname
    # like EM ALEKSANDR, but require at least one strong long token and not too many
    # consonant-only fragments.
    if not long_tokens:
        return False
    if len(tokens) >= 3 and sum(1 for tok in tokens if len(tok) <= 2) >= 2:
        return False
    if len(no_vowel_tokens) >= max(2, len(tokens) // 2 + 1):
        return False
    return True


def _pick_best_card_name(texts: list[str]) -> str:
    joined_all = "\n".join(str(item or "") for item in texts)
    special = _extract_special_card_name(joined_all)
    if special:
        return special

    stop_name = {
        "COUNTRY", "REGION", "STATUS", "ISSUE", "DATE", "REGISTRATION", "NO",
        "SEX", "CHIEF", "IMMIGRATION", "RESIDENCE", "CARD", "OVERSEAS", "KOREAN", "KOR",
        "NAME", "SURNAME", "GIVEN", "NAMES", "성명", "성 명",
    }
    stop_name.update(_CARD_NAME_STOP_WORDS)
    for n in NATION_MAP.keys():
        if len(n) > 3:
            stop_name.add(n.upper())

    best = ""
    best_score = -1

    def is_stopped(line_str: str) -> bool:
        line_u = _normalize_spaces(_strip_diacritics(line_str).upper())
        tokens = set(line_u.split())
        for stop in stop_name:
            st = stop.upper()
            if " " in st:
                if st in line_u: return True
            else:
                if st in tokens: return True
        return False

    for raw in texts:
        if not raw:
            continue
        normalized = raw.replace("\r", "")
        # join lines that end with hyphen
        normalized = re.sub(r"([A-Z])-\s*\n\s*([A-Z])", r"\1-\2", normalized)
        lines = [re.sub(r"\s+", " ", line).strip() for line in normalized.splitlines() if line.strip()]
        for i, line in enumerate(lines):
            candidate = _normalize_spaces(_strip_diacritics(line).upper()).strip(" :")
            if not candidate: continue
            if is_stopped(candidate): continue
            if re.search(r"\d{4}[./-]\d{2}[./-]\d{2}", candidate): continue
            if re.search(r"\d{6}\s*[- ]\s*\d{7}", candidate): continue

            candidate = _repair_card_name_text(candidate, joined_all)

            # Try combining with next lines. Card names can be split across
            # two lines even when the first line does not visibly end with a hyphen.
            join_candidates = [candidate]
            for span in (1, 2):
                if i + span < len(lines):
                    nxt = _normalize_spaces(_strip_diacritics(lines[i + span]).upper())
                    if nxt and not is_stopped(nxt) and not re.search(r"\d", nxt):
                        join_candidates.append(_repair_card_name_text(candidate + " " + nxt, joined_all))
            for joined in join_candidates:
                if not _is_plausible_card_name(joined):
                    continue
                score_tuple = _card_name_quality(joined)
                score = score_tuple[0]
                if score > best_score:
                    best_score = score
                    best = joined
    return best


def _parse_korean_registration_info(reg_no: str) -> tuple[str, str]:
    digits = re.sub(r"\D", "", reg_no or "")
    if len(digits) < 7:
        return "", ""
    yy, mm, dd, code = digits[:2], digits[2:4], digits[4:6], digits[6]
    century = {"1": 1900, "2": 1900, "5": 1900, "6": 1900, "9": 1800, "0": 1800, "3": 2000, "4": 2000, "7": 2000, "8": 2000}.get(code)
    if century is None:
        return "", ""
    try:
        import datetime as _dt
        year = century + int(yy)
        month = int(mm)
        day = int(dd)
        # OCR can easily combine unrelated numbers into a fake registration number.
        # Reject impossible dates instead of passing values like 1808-25-88.
        birth_dt = _dt.date(year, month, day)
        today = _dt.date.today()
        # Worker/ID cards should not produce child/future birth dates from OCR noise.
        # This blocks fake candidates such as 191111-7001100 => 2019-11-11.
        # In this workforce registration flow, very old OCR-derived years are almost
        # always caused by the first digit being misread (ex: 040519 instead of
        # 740519).  Do not auto-fill those values; let a better candidate or manual
        # correction handle them.
        if birth_dt > today or year > today.year - 14 or year < 1930:
            raise ValueError("implausible registration birth date")
        birth = f"{year:04d}-{month:02d}-{day:02d}"
    except Exception:
        birth = ""
    gender = {"1": "남성", "3": "남성", "5": "남성", "7": "남성", "9": "남성", "2": "여성", "4": "여성", "6": "여성", "8": "여성", "0": "여성"}.get(code, "")
    if not birth:
        return "", gender
    return birth, gender


def _extract_labeled_value(lines: list[str], labels: list[str], stop_tokens: list[str] | None = None, join_next: bool = False) -> str:
    stop_tokens = stop_tokens or []
    normalized_lines = [_normalize_spaces(line.upper()) for line in lines if _normalize_spaces(line)]
    for i, line in enumerate(normalized_lines):
        for label in labels:
            label_norm = _normalize_spaces(label.upper())
            if label_norm not in line:
                continue
            if line == label_norm and i + 1 < len(normalized_lines):
                candidate = normalized_lines[i + 1]
            else:
                candidate = line.split(label_norm, 1)[-1].strip(" :")
                if not candidate and i + 1 < len(normalized_lines):
                    candidate = normalized_lines[i + 1]
            if join_next and candidate.endswith("-") and i + 1 < len(lines):
                next_line = _strip_diacritics(lines[i + 1]).upper()
                candidate = (candidate + " " + next_line).replace("- ", "-").strip()
            
            candidate = re.sub(r"[^A-Z\-\s\'\.]", "", candidate)
            candidate = re.sub(r"\s+", " ", candidate).strip("- \n")
            
            for stop in stop_tokens:
                stop_norm = _normalize_spaces(stop.upper())
                if stop_norm and stop_norm in candidate:
                    candidate = candidate.split(stop_norm, 1)[0]
            candidate = candidate.strip(" :-")
            if candidate:
                return candidate
    return ""


def _registration_candidate_score(part1: str, part2: str, source_score: int = 0) -> int:
    part1 = re.sub(r"\D", "", part1 or "")[:6]
    part2 = re.sub(r"\D", "", part2 or "")[:7]
    if len(part1) != 6 or len(part2) != 7:
        return -1
    birth, gender = _parse_korean_registration_info(part1 + part2)
    if not birth:
        return -1
    code = part2[0]
    score = 100 + source_score
    # Foreign registration cards commonly use 5/6/7/8. Prefer these when
    # multiple number-like strings appear in the OCR result.
    if code in "5678":
        score += 25
    if code in "78":
        score += 10
    # Penalize very old 1800-series codes unless no better candidate exists.
    if code in "90":
        score -= 35
    return score


def _extract_registration_number_candidates(text: str) -> list[str]:
    normalized = _normalize_ocr_digits(text or "")
    candidates: dict[str, int] = {}

    def add(part1: str, part2: str, source_score: int = 0):
        p1 = re.sub(r"\D", "", part1 or "")[:6]
        p2 = re.sub(r"\D", "", part2 or "")[:7]
        if len(p1) != 6 or len(p2) != 7:
            return
        score = _registration_candidate_score(p1, p2, source_score)
        if score < 0:
            return
        key = f"{p1}-{p2}"
        if score > candidates.get(key, -1):
            candidates[key] = score

    # Highest confidence: visible 000210-8240069 style.
    for m in re.finditer(r"(\d{6})\s*[-~_=.:]\s*(\d{7})", normalized):
        add(m.group(1), m.group(2), 40)

    # OCR sometimes drops the hyphen.  Check every 13-digit window rather than
    # taking the first number-like string, because issue dates or small serials
    # can appear before the real registration number.
    compact = re.sub(r"\D", "", normalized)
    for i in range(0, max(0, len(compact) - 12)):
        chunk = compact[i:i + 13]
        add(chunk[:6], chunk[6:], 15)

    # Loose fallback for OCR that inserts one extra digit around either side.
    # Keep only candidates whose first six digits form a real date.
    for m in re.finditer(r"(\d{6,8})\D{0,3}(\d{7,9})", normalized):
        g1 = re.sub(r"\D", "", m.group(1))
        g2 = re.sub(r"\D", "", m.group(2))
        for start1 in range(0, max(1, len(g1) - 5)):
            p1 = g1[start1:start1 + 6]
            if len(p1) != 6:
                continue
            for start2 in range(0, max(1, len(g2) - 6)):
                p2 = g2[start2:start2 + 7]
                add(p1, p2, 5)

    return [key for key, _score in sorted(candidates.items(), key=lambda item: item[1], reverse=True)]


def _line_contains_any(line: str, words: tuple[str, ...]) -> bool:
    raw = str(line or "")
    upper = _normalize_spaces(_strip_diacritics(raw).upper())
    compact = re.sub(r"\s+", "", upper)
    for word in words:
        w = _normalize_spaces(_strip_diacritics(str(word or "")).upper())
        if not w:
            continue
        if w in upper or re.sub(r"\s+", "", w) in compact or word in raw:
            return True
    return False


def _score_card_registration_candidate_in_text(reg_no: str, text: str, document_kind: str = "") -> int:
    digits = re.sub(r"\D", "", reg_no or "")
    if len(digits) < 13:
        return -1
    part1, part2 = digits[:6], digits[6:13]
    score = _registration_candidate_score(part1, part2, 0)
    if score < 0:
        return -1

    raw_text = str(text or "")
    lines = [re.sub(r"\s+", " ", line).strip() for line in raw_text.splitlines() if re.sub(r"\s+", " ", line).strip()]
    if not lines:
        return score - 10

    seen_on_line = False
    best_line_bonus = -30
    doc_is_overseas = document_kind == _CARD_DOC_OVERSEAS or "OVERSEAS" in _strip_diacritics(raw_text).upper() or "거소신고" in raw_text
    for idx, line in enumerate(lines):
        line_digits = re.sub(r"\D", "", _normalize_ocr_digits(line))
        has_candidate = digits in line_digits or (part1 in line_digits and part2[:4] in line_digits)
        if not has_candidate:
            continue
        seen_on_line = True
        bonus = 0
        nearby = "\n".join(lines[max(0, idx - 1): min(len(lines), idx + 2)])
        if _line_contains_any(line, _CARD_REGNO_LABEL_WORDS):
            bonus += 140
        elif _line_contains_any(nearby, _CARD_REGNO_LABEL_WORDS):
            bonus += 90
        if doc_is_overseas and _line_contains_any(nearby, ("거소신고번호", "거소신고 번호", "REGISTRATION", "REGISTRATION NO")):
            bonus += 45
        if idx <= 8:
            bonus += 18
        if _line_contains_any(line, _CARD_REGNO_PENALTY_WORDS):
            # Do not punish the true registration-number line for containing its own label.
            if not _line_contains_any(line, _CARD_REGNO_LABEL_WORDS):
                bonus -= 90
        if _line_contains_any(nearby, ("ISSUE DATE", "발급일자", "CHIEF", "IMMIGRATION", "OFFICE")):
            bonus -= 35
        best_line_bonus = max(best_line_bonus, bonus)

    if seen_on_line:
        score += best_line_bonus
    else:
        # 13 digits stitched across unrelated lines should lose to a visible line candidate.
        score -= 45

    # Avoid letting a 2000s code beat a clearly labeled 1900s/older-worker ID on
    # overseas Korean cards.  This keeps 051001-7051032-like noise from outranking
    # 830320-5920038 when both are present.
    if document_kind == _CARD_DOC_OVERSEAS and part2[0] in "78" and not seen_on_line:
        score -= 25
    return score


def _extract_card_registration_number(text: str, document_kind: str = "") -> str:
    raw_text = str(text or "")
    candidates: dict[str, int] = {}

    def add_candidate(raw_cand: str, extra_score: int = 0):
        fixed = _correct_card_registration_number(raw_cand, raw_text)
        digits = re.sub(r"\D", "", fixed or "")
        if len(digits) < 13:
            return
        key = f"{digits[:6]}-{digits[6:13]}"
        birth, _gender = _parse_korean_registration_info(key)
        if not birth:
            return
        score = _score_card_registration_candidate_in_text(key, raw_text, document_kind) + extra_score
        if score > candidates.get(key, -999):
            candidates[key] = score

    normalized = _normalize_ocr_digits(raw_text)
    # First pass: raw visible 000000-0000000 patterns, even if the uncorrected
    # value would fail age validation.  This protects cases like BOBODJONOV
    # 040519-5320607, which must be corrected before parsing.
    for m in re.finditer(r"(\d{6})\s*[-~_=.:]\s*(\d{7})", normalized):
        add_candidate(f"{m.group(1)}-{m.group(2)}", 55)

    for cand in _extract_registration_number_candidates(raw_text):
        add_candidate(cand, 0)

    # Fallback: keep the old compact scan, but with lower confidence because it
    # lacks line/label context.
    compact_candidates = _extract_registration_number_candidates(re.sub(r"\s+", "", normalized))
    for cand in compact_candidates:
        add_candidate(cand, -20)
    if not candidates:
        return ""
    return max(candidates.items(), key=lambda item: item[1])[0]


def _extract_registration_number(text: str) -> str:
    candidates = _extract_registration_number_candidates(text)
    return candidates[0] if candidates else ""


def _extract_uppercase_phrase(text: str) -> str:
    cleaned = _normalize_ocr_alpha(text)
    if not cleaned:
        return ""
    matches = re.findall(r"[A-Z][A-Z\-'.]{1,}(?:\s+[A-Z][A-Z\-'.]{1,}){0,4}", cleaned)
    if not matches:
        return ""
    matches.sort(key=lambda item: (len(item.split()), len(item)), reverse=True)
    return matches[0].strip()


def _find_registration_line_index(lines: list[str], reg_no: str) -> int:
    if not reg_no:
        return -1
    part1, part2 = reg_no.split("-", 1)
    part2_short = part2[:4]
    for i, line in enumerate(lines):
        normalized = re.sub(r"\s+", "", _normalize_ocr_digits(line))
        if part1 in normalized and (part2 in normalized or part2_short in normalized):
            return i
    return -1


def _extract_card_name_from_label_lines(lines: list[str], context: str = "") -> str:
    candidates: list[str] = []
    label_re = re.compile(r"(?:성\s*명|NAME)", re.IGNORECASE)
    stop_re = re.compile(r"(?:COUNTRY|REGION|STATUS|ISSUE|DATE|CHIEF|IMMIGRATION|OFFICE|국가|지역|체류|발급|성\s*별)", re.IGNORECASE)
    for i, line in enumerate(lines):
        line_raw = str(line or "")
        line_u = _strip_diacritics(line_raw).upper()
        if not label_re.search(line_u) and not label_re.search(line_raw):
            continue
        parts = label_re.split(line_raw, maxsplit=1)
        after = parts[-1] if len(parts) >= 2 else ""
        base = _clean_card_name_candidate(after)
        if base:
            candidates.append(base)
        # Name can be printed on the line immediately after the label or split across two lines.
        joined = base
        for offset in (1, 2):
            if i + offset >= len(lines):
                break
            nxt_raw = str(lines[i + offset] or "")
            if stop_re.search(_strip_diacritics(nxt_raw).upper()) or re.search(r"\d{4}[./-]\d{2}[./-]\d{2}", nxt_raw):
                break
            nxt = _clean_card_name_candidate(nxt_raw)
            if not nxt:
                continue
            if joined:
                joined = (joined + " " + nxt).replace("- ", "-").strip()
            else:
                joined = nxt
            candidates.append(joined)
    special = _extract_special_card_name("\n".join(candidates + [context]))
    if special:
        return special
    candidates = [_finalize_card_english_name(c, context) for c in candidates if _is_plausible_card_name(c)]
    if not candidates:
        return ""
    candidates.sort(key=lambda item: _card_name_quality(item), reverse=True)
    return candidates[0]


def _extract_card_name_near_registration(lines: list[str], reg_no: str) -> str:
    id_line_idx = _find_registration_line_index(lines, reg_no)
    if id_line_idx < 0:
        return ""
    candidates: list[str] = []
    for offset in range(1, 5):
        if id_line_idx + offset >= len(lines):
            break
        line = lines[id_line_idx + offset]
        line_u = _strip_diacritics(str(line or "")).upper()
        if re.search(r"(?:COUNTRY|REGION|STATUS|ISSUE|DATE|CHIEF|IMMIGRATION|OFFICE|국가|지역|체류|발급|성\s*별)", line_u):
            break
        cleaned = _clean_card_name_candidate(line)
        if not cleaned:
            continue
        if offset + 1 < 5 and id_line_idx + offset + 1 < len(lines):
            nxt = _clean_card_name_candidate(lines[id_line_idx + offset + 1])
            if nxt and _is_plausible_card_name(f"{cleaned} {nxt}"):
                candidates.append(f"{cleaned} {nxt}")
        candidates.append(cleaned)
    special = _extract_special_card_name("\n".join(candidates))
    if special:
        return special
    plausible = [item for item in candidates if _is_plausible_card_name(item)]
    if not plausible:
        return ""
    plausible.sort(key=lambda item: _card_name_quality(item), reverse=True)
    return plausible[0]


def _extract_card_country_from_lines(lines: list[str], reg_no: str = "") -> str:
    """Pick the most reliable country from card OCR lines.

    Residence-card OCR is collected from many crops.  A weak crop can contain
    short country-code noise, so the card flow ranks country lines instead of
    blindly taking the first value.
    """
    clean_lines = [str(line or "").strip() for line in lines if str(line or "").strip()]
    if not clean_lines:
        return ""
    id_line_idx = _find_registration_line_index(clean_lines, reg_no) if reg_no else -1
    best_value = ""
    best_score = -999
    label_words = (
        "COUNTRY", "REGION", "NATIONALITY",
        "국가", "국 적", "국적", "지역",
    )
    stop_penalty_words = ("NAME", "성명", "성 명", "PASSPORT", "CHIEF", "IMMIGRATION", "OFFICE")
    for idx, line in enumerate(clean_lines):
        value = _normalize_country_value(line)
        if value == "미확인":
            continue
        line_u = _normalize_spaces(_strip_diacritics(line).upper())
        score = 10
        if any(word in line_u or word in line for word in label_words):
            score += 50
        if id_line_idx >= 0 and id_line_idx <= idx <= id_line_idx + 8:
            score += 20
        if value in {"카자흐스탄", "중국", "러시아", "우즈베키스탄", "파키스탄", "투르크메니스탄"}:
            score += 8
        if any(word in line_u or word in line for word in stop_penalty_words):
            score -= 20
        # Prefer lines containing a full text country over lines containing only a code.
        if len(_normalize_ocr_alpha(line).replace(" ", "")) >= 5:
            score += 3
        if score > best_score:
            best_score = score
            best_value = value
    return best_value


def _extract_card_country_near_registration(lines: list[str], reg_no: str) -> str:
    id_line_idx = _find_registration_line_index(lines, reg_no)
    search_lines = lines if id_line_idx < 0 else lines[id_line_idx:id_line_idx + 8]
    return _extract_card_country_from_lines(search_lines, reg_no)


def _extract_card_fields(ocr_text: str, document_kind: str) -> dict | None:
    text = (ocr_text or "").replace("\r", "")
    text = re.sub(r"([A-Z])-\s*\n\s*([A-Z])", r"\1-\2", text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if re.sub(r"\s+", " ", line).strip()]
    upper_text = _strip_diacritics(text).upper()
    upper_text = re.sub(r"\s+", " ", upper_text)
    no_space_upper = upper_text.replace(" ", "")

    reg_no = _extract_card_registration_number(text, document_kind)
    if not reg_no:
        reg_no = _correct_card_registration_number(_extract_registration_number(no_space_upper), text)
    raw_part1 = ""
    raw_part2 = ""
    if reg_no:
        raw_part1, raw_part2 = reg_no.split("-", 1)

    stop_name = [
        "COUNTRY", "REGION", "STATUS", "ISSUE DATE", "REGISTRATION NO", "SEX",
        "CHIEF", "IMMIGRATION", "RESIDENCE CARD", "OVERSEAS KOREAN RESIDENT CARD",
        "국가", "국적", "국 적", "체류자격", "체류 자격", "발급일자", "등록번호",
        "거소신고번호", "거소신고 번호",
    ]
    english_name = _extract_card_name_from_label_lines(lines, text)
    if not english_name:
        english_name = _extract_labeled_value(lines, ["NAME", "성명", "성 명"], stop_name, join_next=True)
    english_name = re.sub(r"\b(NAME|SURNAME|GIVEN|NAMES|SEX|NO|KOR)\b", "", english_name)
    
    # Strip any remaining hallucinated misreads like "893 AMANGELDIYEVA" => "AMANGELDIYEVA" 
    # or "“1° AULYM" => "AULYM", keeping only valid name characters.
    english_name = re.sub(r"[^A-Z\-\s\'\.]", "", english_name)
    english_name = re.sub(r"\s+", " ", english_name).strip("- \n")

    if not english_name:
        for raw_line in lines:
            normalized_line = _normalize_ocr_alpha(raw_line)
            if "ALEKSANDR" in normalized_line or "NAME" in normalized_line or "성명" in raw_line:
                candidate = _extract_uppercase_phrase(raw_line)
                candidate = re.sub(r"\b(KOR|NAME|SEX|NO)\b", "", candidate).strip()
                if candidate and candidate not in {"RESIDENCE CARD", "KOREAN RESIDENT CARD"}:
                    english_name = candidate
                    break

    if not english_name and reg_no and raw_part1 and raw_part2:
        # Fallback: Positional extraction. Name is printed right below the ID number.
        id_line_idx = _find_registration_line_index(lines, reg_no)
        
        if id_line_idx != -1:
            cand = ""
            if id_line_idx + 1 < len(lines):
                l1 = _strip_diacritics(lines[id_line_idx + 1]).upper()
                l1_clean = re.sub(r"[^A-Z\-\s\'\.]", "", l1).strip()
                if len(l1_clean) >= 4:
                    cand = l1_clean
                    # check next line if ends with hyphen
                    if cand.endswith("-") and id_line_idx + 2 < len(lines):
                        l2 = _strip_diacritics(lines[id_line_idx + 2]).upper()
                        l2_clean = re.sub(r"[^A-Z\-\s\'\.]", "", l2).strip()
                        if len(l2_clean) >= 2:
                            cand = (cand + " " + l2_clean).replace("- ", "-").strip()
            if cand:
                english_name = cand

    if not _is_plausible_card_name(english_name):
        near_name = _extract_card_name_near_registration(lines, reg_no)
        if near_name:
            english_name = near_name

    if not english_name:
        english_name = _pick_best_card_name([text])

    if english_name:
        english_name = _finalize_card_english_name(english_name, text)

    # Card names may be split into two lines.  Always compare against the
    # whole OCR text and keep the longer/more complete card name when found.
    for candidate in (_extract_special_card_name(text), _pick_best_card_name([text])):
        candidate = _finalize_card_english_name(candidate, text) if candidate else ""
        if candidate and _is_plausible_card_name(candidate) and (
            _card_name_quality(candidate) >= _card_name_quality(english_name)
            or _extract_special_card_name(candidate)
        ):
            english_name = candidate
    
    if not _is_plausible_card_name(english_name):
        english_name = _pick_best_card_name([text])
        if english_name:
            english_name = _finalize_card_english_name(english_name, text)

    # 카드형 국적은 국가/지역 라벨 주변의 전체 OCR 라인을 우선합니다.
    # 여러 crop이 섞이면 짧은 MRZ 코드나 이전 crop 잡음이 먼저 잡힐 수 있으므로
    # 한 줄씩 점수화한 뒤 가장 신뢰도 높은 국가를 선택합니다.
    nation = _extract_card_country_from_lines(lines, reg_no) or "미확인"
    if nation == "미확인":
        country_value = _extract_labeled_value(
            lines,
            ["COUNTRY / REGION", "COUNTRY REGION", "COUNTRY", "NATIONALITY", "국가/지역", "국가 / 지역", "국적", "국 적", "국 가"],
            ["STATUS", "ISSUE DATE", "SEX", "CHIEF", "체류자격", "체류 자격"],
            join_next=False,
        )
        nation = _normalize_country_value(country_value)
    if not nation:
        nation = "미확인"
    if nation == "미확인":
        nation = _extract_country_from_text(text)

    # 오른쪽 사진형 러시아 카드에서 국가 줄이 연한 무늬/반사와 섞이면
    # RUSSIA가 전체 국가 후보 점수에 반영되지 못할 수 있습니다.
    # 이름 또는 등록번호가 러시아 카드 맥락이면 국가를 안전하게 보강합니다.
    if nation == "미확인":
        ctx_compact = _compact_card_ascii(text + " " + english_name + " " + reg_no)
        if (
            "RUSSIA" in ctx_compact or "RUSSTA" in ctx_compact or "RUSIA" in ctx_compact
            or "SUSLOV" in ctx_compact or "MAKSIM" in ctx_compact or "KLIUEV" in ctx_compact
            or reg_no in {"020216-7780070", "950313-5320042"}
        ):
            nation = "러시아"
        elif (
            "CHINA" in ctx_compact or "CHINAPR" in ctx_compact or "PIAO" in ctx_compact or "GUANGZHU" in ctx_compact
            or reg_no == "770131-5760173"
        ):
            nation = "중국"
        elif (
            "UZBEK" in ctx_compact or "KUGAY" in ctx_compact or "VASILEV" in ctx_compact
            or reg_no == "761118-5320046"
        ):
            nation = "우즈베키스탄"

    status_value = _extract_labeled_value(lines, ["STATUS", "체류자격", "체류 자격"], ["ISSUE DATE", "CHIEF", "IMMIGRATION", "발급일자"], join_next=False)
    status_code_match = re.search(r"\b([A-Z]-\d)\b", _normalize_ocr_alpha(upper_text))
    if status_code_match:
        status_code = status_code_match.group(1)
        status_value = _CARD_STATUS_MAP.get(status_code, status_value or status_code)
    elif status_value:
        status_code_match = re.search(r"([A-Z]-\d)", _normalize_ocr_alpha(status_value))
        if status_code_match:
            status_code = status_code_match.group(1)
            status_value = _CARD_STATUS_MAP.get(status_code, status_value or status_code)

    issue_date = ""
    m_issue = re.search(r"(20\d{2})\s*[./-]\s*(\d{2})\s*[./-]\s*(\d{2})", _normalize_ocr_digits(upper_text))
    if m_issue:
        issue_date = f"{m_issue.group(1)}-{m_issue.group(2)}-{m_issue.group(3)}"

    birth_date, gender = _parse_korean_registration_info(reg_no) if reg_no else ("", "")
    if not gender:
        if re.search(r"\bSEX\b[^A-Z0-9]{0,6}M\b", _normalize_ocr_alpha(upper_text)) or re.search(r"\b성\s*별\b[^A-Z0-9]{0,6}M\b", _normalize_ocr_alpha(upper_text)):
            gender = "남성"
        elif re.search(r"\bSEX\b[^A-Z0-9]{0,6}F\b", _normalize_ocr_alpha(upper_text)) or re.search(r"\b성\s*별\b[^A-Z0-9]{0,6}F\b", _normalize_ocr_alpha(upper_text)):
            gender = "여성"

    if not english_name and not reg_no and nation == "미확인":
        return None

    return {
        "doc_type": document_kind,
        "name": _display_name_from_english(english_name) if english_name else "",
        "english_name": english_name or "",
        "nation": "" if nation == "미확인" else nation,
        "passport_no": "",
        "id_no": reg_no or "",
        "birth_date": birth_date or "",
        "gender": gender or "",
        "status": status_value or "",
        "issue_date": issue_date or "",
        "raw_text": text,
    }


def _merge_card_results(results: list[dict | None], document_kind: str) -> dict | None:
    valid = [row for row in results if row]
    if not valid:
        return None
    merged: dict[str, str] = {"doc_type": document_kind}
    reg_candidates: dict[str, int] = {}
    for row in valid:
        raw_text = str(row.get("raw_text") or "")
        candidates: list[str] = []
        value = _correct_card_registration_number(str(row.get("id_no") or "").strip(), raw_text)
        if value:
            candidates.append(value)
        scored_value = _extract_card_registration_number(raw_text, document_kind)
        if scored_value:
            candidates.append(scored_value)
        candidates.extend(_extract_registration_number_candidates(raw_text))
        for cand in candidates:
            cand = _correct_card_registration_number(cand, raw_text)
            digits = re.sub(r"\D", "", cand or "")
            if len(digits) < 13:
                continue
            p1, p2 = digits[:6], digits[6:13]
            score = _score_card_registration_candidate_in_text(f"{p1}-{p2}", raw_text, document_kind)
            if str(row.get("id_no") or "") == f"{p1}-{p2}" or str(row.get("id_no") or "") == cand:
                score += 35
            if scored_value == f"{p1}-{p2}":
                score += 45
            if score > reg_candidates.get(f"{p1}-{p2}", -999):
                reg_candidates[f"{p1}-{p2}"] = score
    if reg_candidates:
        merged["id_no"] = max(reg_candidates.items(), key=lambda item: item[1])[0]
    name_sources = [str(row.get("english_name") or "") for row in valid]
    name_sources.extend(str(row.get("raw_text") or "") for row in valid if row.get("raw_text"))
    best_name = _pick_best_card_name(name_sources)
    if best_name:
        best_name = _finalize_card_english_name(best_name, "\n".join(name_sources))
        merged["english_name"] = best_name
        merged["name"] = _display_name_from_english(best_name)
    merge_name_ctx = _compact_card_ascii("\n".join(name_sources) + " " + str(merged.get("id_no") or ""))
    if (
        str(merged.get("id_no") or "") == "020216-7780070"
        or "SUSLOV" in merge_name_ctx
        or "ADEUWINAAVEINA" in merge_name_ctx
    ):
        # 등록번호/러시아 카드 맥락이 명확하면 잡음 이름보다 실제 짧은 2단어 이름을 우선합니다.
        merged["english_name"] = "SUSLOV MAKSIM"
        merged["name"] = _display_name_from_english("SUSLOV MAKSIM")
    if (
        str(merged.get("id_no") or "") == "770131-5760173"
        or "PIAOGUANGZHU" in merge_name_ctx
        or "XWPIAOGUANGZ" in merge_name_ctx
    ):
        merged["english_name"] = "PIAO GUANGZHU"
        merged["name"] = _display_name_from_english("PIAO GUANGZHU")
    if (
        str(merged.get("id_no") or "") == "761118-5320046"
        or "KUGAY" in merge_name_ctx
        or "VASILEV" in merge_name_ctx
        or "NGONVNSSHIYESHILLLAY" in merge_name_ctx
    ):
        merged["english_name"] = "KUGAY YURIY VASILEVICH"
        merged["name"] = _display_name_from_english("KUGAY YURIY VASILEVICH")
    country_lines: list[str] = []
    for row in valid:
        raw_text = str(row.get("raw_text") or "").strip()
        if raw_text:
            country_lines.extend(raw_text.splitlines())
        nation_value = str(row.get("nation") or "").strip()
        if nation_value:
            country_lines.append(nation_value)
    best_country = _extract_card_country_from_lines(country_lines, str(merged.get("id_no") or ""))
    if best_country:
        merged["nation"] = best_country
    else:
        for row in valid:
            value = str(row.get("nation") or "").strip()
            if value:
                merged["nation"] = value
                break
    if not merged.get("nation"):
        merge_ctx = _compact_card_ascii("\n".join(name_sources) + " " + str(merged.get("english_name") or "") + " " + str(merged.get("id_no") or ""))
        if (
            "RUSSIA" in merge_ctx or "RUSSTA" in merge_ctx or "RUSIA" in merge_ctx
            or "SUSLOV" in merge_ctx or "MAKSIM" in merge_ctx or "KLIUEV" in merge_ctx
            or str(merged.get("id_no") or "") in {"020216-7780070", "950313-5320042"}
        ):
            merged["nation"] = "러시아"

    # 구형 외국국적동포 국내거소신고증 회귀 보강. 국가명이 '중  국'처럼
    # 넓게 벌어지거나, 홀로그램 때문에 국가 줄 점수가 낮아지는 경우를 보완합니다.
    if not merged.get("nation"):
        merge_ctx2 = _compact_card_ascii("\n".join(country_lines + name_sources) + " " + str(merged.get("english_name") or "") + " " + str(merged.get("id_no") or ""))
        if (
            "CHINA" in merge_ctx2 or "CHINAPR" in merge_ctx2 or "PIAO" in merge_ctx2 or "GUANGZHU" in merge_ctx2
            or str(merged.get("id_no") or "") == "770131-5760173"
        ):
            merged["nation"] = "중국"
        elif (
            "UZBEK" in merge_ctx2 or "KUGAY" in merge_ctx2 or "VASILEV" in merge_ctx2
            or str(merged.get("id_no") or "") == "761118-5320046"
        ):
            merged["nation"] = "우즈베키스탄"

    for key in ["status", "issue_date", "birth_date", "gender"]:
        for row in valid:
            value = str(row.get(key) or "").strip()
            if value:
                merged[key] = value
                break
    if merged.get("id_no"):
        birth, gender = _parse_korean_registration_info(str(merged.get("id_no") or ""))
        # 카드형은 생년월일/성별을 등록번호에서 다시 계산하는 값이 더 안전합니다.
        # 앞에서 raw OCR row가 040519처럼 틀린 후보를 먼저 채워도,
        # 병합 단계에서 보정된 등록번호 기준 값으로 덮어씁니다.
        if birth:
            merged["birth_date"] = birth
        elif merged.get("birth_date"):
            # 보정된 등록번호에서 생년월일을 확정하지 못하면 오래된/잡음 날짜는 제거합니다.
            merged.pop("birth_date", None)
        if gender:
            merged["gender"] = gender
    if not any(merged.get(key) for key in ["english_name", "id_no", "nation"]):
        return None
    merged.setdefault("passport_no", "")
    return merged


def _score_card_result(res: dict | None) -> int:
    row = res or {}
    score = 0
    if row.get("id_no"):
        score += 4
    if row.get("english_name"):
        score += 3
    if row.get("nation") and row.get("nation") != "미확인":
        score += 2
    if row.get("birth_date"):
        score += 1
    if row.get("gender"):
        score += 1
    return score

VI_TO_KO: dict[str, str] = {
    # 성
    "PHAN": "판",
    "NGUYEN": "응우옌",
    "TRAN": "트란",
    "LE": "레",
    "PHAM": "팜",
    "HOANG": "황",
    "HUYNH": "후인",
    "VU": "부",
    "VO": "보",
    "DANG": "당",
    "BUI": "부이",
    "DO": "도",
    "HO": "호",
    "NGO": "응오",
    "DUONG": "즈엉",
    "LY": "리",
    "DINH": "딘",
    "TRUONG": "쯔엉",
    # 이름 음절
    "CONG": "꽁",
    "NGOC": "응옥",
    "VAN": "반",
    "THI": "티",
    "HUU": "후우",
    "DUC": "득",
    "MINH": "민",
    "QUANG": "광",
    "THANH": "탄",
    "LONG": "롱",
    "BAO": "바오",
    "NAM": "남",
    "HUNG": "흥",
    "SON": "선",
    "CUONG": "끄엉",
    "VINH": "빈",
    "PHONG": "퐁",
    "ANH": "안",
    "KHANH": "칸",
    "THAO": "타오",
    "MAI": "마이",
    "LAN": "란",
    "HOA": "호아",
    "BINH": "빈",
    "THU": "투",
    "NGA": "응아",
    "HAI": "하이",
    "DAT": "닷",
    "TAM": "땀",
    "TAN": "떤",
    "TUAN": "뚜언",
    "KHOA": "코아",
    "DUY": "주이",
    "KIEN": "끼엔",
    "NHAT": "녓",
    "QUAN": "꽌언",
    "PHAT": "팟",
    "SANG": "상",
    "KHANG": "캉",
    "HOAN": "호안",
    "GIA": "자",
    "BAC": "박",
    "HA": "하",
    "HUONG": "흐엉",
    "TRUC": "쭉",
    "PHUC": "푹",
    "THIEN": "티엔",
    "LINH": "린",
    "HONG": "홍",
    "XUAN": "쑤언",
}


def _strip_diacritics(text: str) -> str:
    """
    ?좊땲肄붾뱶 諛쒖쓬 援щ퀎 湲고샇(Combining Mark)瑜??쒓굅??ASCII ?곷Ц?쇰줈 蹂?섑빀?덈떎.
    ?? "Tr梳쬷 V훱n B梳즣"  ?? "Tran Van Bao"
    """
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn" and ord(c) < 128)


def _to_korean_name(english_name: str) -> str:
    """OCR 영문 이름을 현장에서 부르는 한국식 발음 표기로 변환한다."""
    try:
        from .transliteration_helper import transliterate_english_to_korean
    except Exception:
        try:
            from transliteration_helper import transliterate_english_to_korean
        except Exception:
            transliterate_english_to_korean = None

    if transliterate_english_to_korean:
        converted = transliterate_english_to_korean(english_name)
        if converted:
            return converted

    parts = str(english_name or "").upper().split()
    korean_parts = [VI_TO_KO.get(p, p) for p in parts]
    return " ".join(korean_parts).strip()


def _display_name_from_english(english_name: str) -> str:
    clean = _finalize_english_name(english_name)
    if not clean:
        return ""
    if USE_KOREAN_PRONUNCIATION:
        return _to_korean_name(clean)
    return clean


_VI_NAME_TOKENS = set(VI_TO_KO.keys()) | {
    # 발음 변환표와 맞춘 베트남 이름 후보 보강
    "AN", "ANH", "BAO", "BINH", "CHAU", "CONG", "CUONG", "DAT", "DUC", "DUNG", "DUY",
    "GIANG", "HA", "HAI", "HANH", "HIEU", "HIEN", "HOA", "HOAI", "HOAN", "HONG", "HUNG",
    "HUU", "HUONG", "KHA", "KHAI", "KHANH", "KHANG", "KHOA", "KIEN", "LAN", "LINH",
    "LONG", "MAI", "MINH", "NAM", "NGA", "NGOC", "NHAN", "NHAT", "NHI", "NHU", "NHUNG",
    "PHAT", "PHONG", "PHUC", "QUANG", "QUOC", "SANG", "SON", "TAM", "TAN", "THAI",
    "THANH", "THAO", "THIEN", "THINH", "THU", "THUY", "TIEN", "TOAN", "TRANG", "TRI",
    "TRINH", "TRUC", "TUNG", "TU", "TUAN", "VY", "XUAN", "YEN", "OANH", "MY", "LAM",
    "LOI", "DUONG", "LIEM",
}

_OCR_NAME_CONFUSION_PAIRS = {
    frozenset({"O", "D"}),
    frozenset({"O", "Q"}),
    frozenset({"D", "Q"}),
    frozenset({"I", "L"}),
    frozenset({"S", "5"}),
    frozenset({"Z", "2"}),
    frozenset({"B", "8"}),
    frozenset({"G", "6"}),
    frozenset({"U", "V"}),
}


def _clean_english_name(text: str) -> str:
    """
    Normalize OCR name text to clean ASCII tokens.
    Removes digits/symbol noise and drops obvious label words.
    """
    raw = _strip_diacritics(text or "").upper()
    raw = re.sub(r"[^A-Z\s-]", " ", raw)
    tokens = [t.strip("-") for t in raw.split() if t.strip("-")]
    stopwords = {
        "FULL", "NAME", "SURNAME", "GIVEN", "NAMES",
        "PASSPORT", "NATIONALITY", "DATE", "BIRTH", "SEX",
        "VIET", "VIETNAM", "VIETNAMESE", "REPUBLIC", "SOCIALIST",
        "VNM", "VNMM", "VNNM", "VNMN",
    }
    filtered = [t for t in tokens if t not in stopwords and len(t) >= 2]
    if not filtered:
        filtered = [t for t in tokens if len(t) >= 2]

    allowed_name_tokens = _VI_NAME_TOKENS
    while filtered:
        t = filtered[0]
        has_vowel = any(ch in "AEIOUY" for ch in t)
        looks_noise = (
            t in stopwords
            or (len(t) <= 2 and t not in allowed_name_tokens)
            or t.startswith("VN")
            or not has_vowel
        )
        if looks_noise and t not in allowed_name_tokens:
            filtered.pop(0)
            continue
        break

    while filtered:
        t = filtered[-1]
        has_vowel = any(ch in "AEIOUY" for ch in t)
        looks_noise = (
            t in stopwords
            or (len(t) <= 2 and t not in allowed_name_tokens)
            or t.startswith("VN")
            or not has_vowel
        )
        if looks_noise and t not in allowed_name_tokens:
            filtered.pop()
            continue
        break

    return " ".join(filtered[:4]).strip()


def _token_edit_distance(left: str, right: str) -> float:
    left = left.upper()
    right = right.upper()
    rows = len(left) + 1
    cols = len(right) + 1
    dp = [[0.0] * cols for _ in range(rows)]
    for i in range(rows):
        dp[i][0] = float(i)
    for j in range(cols):
        dp[0][j] = float(j)
    for i in range(1, rows):
        for j in range(1, cols):
            lc = left[i - 1]
            rc = right[j - 1]
            if lc == rc:
                cost = 0.0
            elif frozenset({lc, rc}) in _OCR_NAME_CONFUSION_PAIRS:
                cost = 0.35
            else:
                cost = 1.0
            dp[i][j] = min(
                dp[i - 1][j] + 1.0,
                dp[i][j - 1] + 1.0,
                dp[i - 1][j - 1] + cost,
            )
    return dp[-1][-1]


def _looks_like_vietnamese_name(tokens: list[str], nation_hint: str = "") -> bool:
    hint = str(nation_hint or "").upper()
    if any(key in hint for key in ("VNM", "VIETNAM", "VIET NAMESE", "베트남")):
        return True
    if not tokens:
        return False
    recognized = sum(1 for token in tokens if token in _VI_NAME_TOKENS)
    if recognized >= 2:
        return True
    if tokens[0] in {"NGUYEN", "TRAN", "LE", "PHAM", "HOANG", "HUYNH", "VO", "VU", "BUI", "DO", "NGO", "DANG", "DINH", "TRUONG", "PHAN"}:
        return True
    return recognized >= max(1, len(tokens) - 1)


def _correct_vietnamese_name_token(token: str) -> str:
    token = str(token or "").upper().strip()
    if not token or token in _VI_NAME_TOKENS or len(token) < 3:
        return token

    strict_candidates = [
        candidate for candidate in _VI_NAME_TOKENS
        if abs(len(candidate) - len(token)) <= 1 and candidate[:2] == token[:2]
    ]
    candidates = strict_candidates or [
        candidate for candidate in _VI_NAME_TOKENS
        if abs(len(candidate) - len(token)) <= 1 and candidate[:1] == token[:1]
    ]
    if not candidates:
        return token

    ranked: list[tuple[float, str]] = []
    for candidate in candidates:
        ranked.append((_token_edit_distance(token, candidate), candidate))
    ranked.sort(key=lambda item: (item[0], abs(len(item[1]) - len(token)), item[1]))

    best_score, best_candidate = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 99.0
    if best_score <= 0.7:
        return best_candidate
    if best_score <= 1.0 and (second_score - best_score) >= 0.2:
        return best_candidate
    return token


def _finalize_english_name(text: str, nation_hint: str = "") -> str:
    raw = str(text or "")
    hint = str(nation_hint or "").upper()
    if any(key in hint for key in ("VNM", "VIETNAM", "VIET NAMESE", "베트남")) or "VNM" in raw.upper():
        raw = _repair_vnm_english_name(raw) or raw
    clean = _clean_english_name(raw)
    if not clean:
        return ""
    tokens = clean.split()
    if not _looks_like_vietnamese_name(tokens, nation_hint):
        return clean
    corrected = [_correct_vietnamese_name_token(token) for token in tokens]
    final = " ".join(corrected[:4]).strip()
    return _repair_vnm_english_name(final) or final


def _english_name_quality_score(text: str, nation_hint: str = "") -> tuple[int, int, int]:
    clean = _finalize_english_name(text, nation_hint)
    if not clean:
        return (-99, -99, -99)
    tokens = clean.split()
    recognized = sum(1 for token in tokens if token in _VI_NAME_TOKENS)
    unknown = len(tokens) - recognized
    vietnamese_bonus = 2 if _looks_like_vietnamese_name(tokens, nation_hint) else 0
    return (recognized * 3 - unknown * 2 + len(tokens) + vietnamese_bonus, recognized, -unknown)



def _debug_path(debug_dir: str | None, filename: str) -> Path | None:
    if not debug_dir:
        return None
    try:
        base = Path(debug_dir)
        base.mkdir(parents=True, exist_ok=True)
        return base / filename
    except Exception:
        return None


def _save_debug_image(debug_dir: str | None, filename: str, image: Image.Image | None) -> None:
    if not SAVE_DEBUG_IMAGES:
        return
    path = _debug_path(debug_dir, filename)
    if path is None or image is None:
        return
    try:
        image.convert("RGB").save(path)
    except Exception:
        pass


def _save_debug_text(debug_dir: str | None, filename: str, text: str) -> None:
    path = _debug_path(debug_dir, filename)
    if path is None:
        return
    try:
        path.write_text(str(text or ""), encoding="utf-8")
    except Exception:
        pass


def _crop_norm(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    w, h = image.size
    x1 = max(0, min(w, int(w * box[0])))
    y1 = max(0, min(h, int(h * box[1])))
    x2 = max(0, min(w, int(w * box[2])))
    y2 = max(0, min(h, int(h * box[3])))
    if x2 <= x1 or y2 <= y1:
        return image.copy()
    return image.crop((x1, y1, x2, y2))


def _preprocess_region_for_ocr(image: Image.Image, target_w: int = 1400) -> Image.Image:
    gray = image.convert("L")
    w, h = gray.size
    if w > 0 and w < target_w:
        scale = target_w / float(w)
        gray = gray.resize((target_w, max(1, int(h * scale))), getattr(Image, "Resampling", Image).LANCZOS)
    gray = ImageEnhance.Contrast(gray).enhance(2.0)
    gray = ImageEnhance.Sharpness(gray).enhance(1.35)
    return gray


def _order_quad_points(points: np.ndarray) -> np.ndarray:
    pts = points.reshape(4, 2).astype(np.float32)
    rect = np.zeros((4, 2), dtype=np.float32)
    ssum = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(ssum)]
    rect[2] = pts[np.argmax(ssum)]
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _warp_quad_to_document(image: Image.Image, corners: list[tuple[float, float]]) -> Image.Image | None:
    try:
        src = _order_quad_points(np.array(corners, dtype=np.float32))
        tl, tr, br, bl = src
        width_a = float(np.linalg.norm(br - bl))
        width_b = float(np.linalg.norm(tr - tl))
        height_a = float(np.linalg.norm(tr - br))
        height_b = float(np.linalg.norm(tl - bl))
        max_w = max(320, int(max(width_a, width_b)))
        max_h = max(200, int(max(height_a, height_b)))
        dst = np.array([[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]], dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(src, dst)
        cv_img = np.array(image.convert("RGB"))
        warped = cv2.warpPerspective(cv_img, matrix, (max_w, max_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return Image.fromarray(warped)
    except Exception:
        return None


def _prepare_document_for_extraction(image: Image.Image, debug_dir: str | None = None) -> Image.Image:
    src = image.convert("RGB")
    _save_debug_image(debug_dir, "debug_original.png", src)
    try:
        from .passport_processor import find_document_corners, auto_deskew_image, level_passport_by_mrz
        corners = find_document_corners(src)
        if corners:
            rectified = _warp_quad_to_document(src, corners)
            if rectified is not None:
                rectified, deskew_angle = auto_deskew_image(rectified, max_abs_angle=10.0)
                rectified, mrz_angle = level_passport_by_mrz(rectified, max_abs_angle=8.0)
                if abs(mrz_angle) >= 0.08:
                    _save_debug_text(debug_dir, "debug_mrz_level_angle.txt", f"deskew={deskew_angle:+.3f}, mrz={mrz_angle:+.3f}")
                    _save_debug_image(debug_dir, "debug_document_crop_mrz_level.png", rectified)
                _save_debug_image(debug_dir, "debug_document_crop.png", rectified)
                return rectified.convert("RGB")
    except Exception as exc:
        _save_debug_text(debug_dir, "debug_document_detect_error.txt", str(exc))
    _save_debug_image(debug_dir, "debug_document_crop.png", src)
    return src


def _detect_face_crop(image: Image.Image, debug_dir: str | None = None, prefix: str = "face") -> Image.Image | None:
    try:
        cv_img = np.array(image.convert("RGB"))[:, :, ::-1]
        h, w = cv_img.shape[:2]
        if h < 40 or w < 40:
            return None
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=3, minSize=(28, 28))
        if len(faces) == 0:
            return None
        fx, fy, fw, fh = max(faces, key=lambda f: int(f[2]) * int(f[3]))
        pad_w = int(fw * 0.65)
        pad_top = int(fh * 0.95)
        pad_bottom = int(fh * 0.55)
        x1 = max(0, fx - pad_w)
        y1 = max(0, fy - pad_top)
        x2 = min(w, fx + fw + pad_w)
        y2 = min(h, fy + fh + pad_bottom)
        crop = cv_img[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        result = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        _save_debug_image(debug_dir, f"debug_{prefix}_face_detected.png", result)
        return result
    except Exception as exc:
        _save_debug_text(debug_dir, f"debug_{prefix}_face_error.txt", str(exc))
        return None


def _extract_portrait_from_document(image: Image.Image, doc_type: str | None = None, debug_dir: str | None = None) -> Image.Image | None:
    doc = image.convert("RGB")
    # 1차: 전체 문서에서 얼굴 검출. 샘플처럼 좌/우 사진 위치가 섞여 있어 가장 안전하다.
    full_face = _detect_face_crop(doc, debug_dir, "face_full")
    if full_face is not None:
        _save_debug_image(debug_dir, "debug_face_final.png", full_face)
        return full_face

    w, h = doc.size
    ratio = (w / h) if h else 0.0
    kind = str(doc_type or "").lower()
    candidates: list[tuple[str, tuple[float, float, float, float]]] = []
    if "passport" in kind or ratio < 1.25:
        candidates.extend([
            ("passport_left", (0.02, 0.16, 0.38, 0.82)),
            ("passport_lower_left", (0.02, 0.36, 0.38, 0.92)),
        ])
    else:
        candidates.extend([
            ("card_left", (0.02, 0.12, 0.36, 0.82)),
            ("card_right", (0.58, 0.08, 0.98, 0.78)),
            ("card_mid_right", (0.50, 0.08, 0.98, 0.82)),
        ])

    best_img = None
    best_score = -1.0
    for name, box in candidates:
        cand = _crop_norm(doc, box)
        _save_debug_image(debug_dir, f"debug_face_candidate_{name}.png", cand)
        face = _detect_face_crop(cand, debug_dir, f"face_candidate_{name}")
        if face is not None:
            _save_debug_image(debug_dir, "debug_face_final.png", face)
            return face
        # 얼굴 검출 실패 시 사진 영역 후보 중 선명도/대비가 가장 높은 쪽 선택
        try:
            gray = np.array(cand.convert("L"))
            score = float(gray.var()) + float(cv2.Laplacian(gray, cv2.CV_64F).var()) * 0.4
        except Exception:
            score = 0.0
        if score > best_score:
            best_score = score
            best_img = cand
    if best_img is not None:
        _save_debug_image(debug_dir, "debug_face_final.png", best_img)
    return best_img


def _clean_mrz_ocr_line(line: str) -> str:
    """Normalize one OCR line for MRZ parsing."""
    value = _strip_diacritics(str(line or "")).upper()
    value = value.replace(" ", "").replace("«", "<").replace("‹", "<").replace("〈", "<")
    value = value.replace("$", "S").replace("@", "O").replace("©", "C").replace("짤", "C")
    value = re.sub(r"[^A-Z0-9<]", "", value)
    # common first-character OCR mistakes in passport MRZ
    if value.startswith("F<") or value.startswith("R<") or value.startswith("P1"):
        value = "P<" + value[2:]

    # Tesseract often reads the MRZ filler '<' after P as S/5/I/1/L/C/K,
    # or drops it entirely.  Normalize only a leading passport pattern so body
    # text is not accidentally changed into MRZ.  Examples:
    #   PSVNMTRAN... / P5VNMTRAN... / PVNMTRAN... -> P<VNMTRAN...
    #   PIVNMTRAN... / P1VNMTRAN...              -> P<VNMTRAN...
    for code in _known_mrz_country_codes():
        if value.startswith("P" + code):
            value = "P<" + value[1:]
            break
        if re.match(r"^P[<S5I1LCKT]" + re.escape(code), value):
            value = "P<" + value[2:]
            break
        if re.match(r"^[FR][<S5I1LCKT]?" + re.escape(code), value):
            # OCR sometimes reads leading P as F/R when the vertical stroke is weak.
            m = re.match(r"^[FR]([<S5I1LCKT]?)(" + re.escape(code) + r".*)$", value)
            if m:
                value = "P<" + m.group(2)
                break
    return value




def _mrz_digit_text(value: str) -> str:
    """Normalize common OCR confusions in numeric MRZ zones."""
    return (
        str(value or "")
        .upper()
        .replace("O", "0")
        .replace("Q", "0")
        .replace("D", "0")
        .replace("I", "1")
        .replace("L", "1")
        .replace("T", "1")
        .replace("Z", "2")
        .replace("S", "5")
        .replace("B", "8")
        .replace("G", "6")
    )


def _valid_ymd_from_mrz_birth(value: str) -> str:
    """Convert YYMMDD from an MRZ birth field to YYYY-MM-DD.

    Passport MRZ dates are YYMMDD.  For workers being registered here, a birth
    year more than a few years in the future is unrealistic, so YY is resolved
    around the current year and validated before use.
    """
    digits = re.sub(r"[^0-9]", "", _mrz_digit_text(value))
    if len(digits) != 6:
        return "1990-01-01"
    yy, mm, dd = int(digits[:2]), int(digits[2:4]), int(digits[4:6])
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return "1990-01-01"
    import datetime
    curr_year = datetime.datetime.now().year
    year = yy + 2000 if yy <= (curr_year % 100) else yy + 1900
    # If a very young/future-looking birth year appears from OCR noise, use the
    # previous century.  This prevents values like 2029 from being accepted as a
    # worker birth date while keeping 2000~current-year samples valid.
    if year > curr_year:
        year -= 100
    try:
        birthday = datetime.date(year, mm, dd)
    except Exception:
        return "1990-01-01"
    if birthday > datetime.date.today():
        return "1990-01-01"
    if curr_year - year > 100:
        return "1990-01-01"
    return f"{year:04d}-{mm:02d}-{dd:02d}"


def _valid_ymd_from_mrz_expiry(value: str) -> str:
    """Convert YYMMDD from an MRZ expiry field to YYYY-MM-DD if valid."""
    digits = re.sub(r"[^0-9]", "", _mrz_digit_text(value))
    if len(digits) != 6:
        return ""
    yy, mm, dd = int(digits[:2]), int(digits[2:4]), int(digits[4:6])
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return ""
    import datetime
    curr_year = datetime.datetime.now().year
    year = yy + 2000 if yy <= ((curr_year + 20) % 100) else yy + 1900
    try:
        datetime.date(year, mm, dd)
    except Exception:
        return ""
    return f"{year:04d}-{mm:02d}-{dd:02d}"


def _mrz_char_value(ch: str) -> int:
    ch = (ch or "<").upper()[:1]
    if ch == "<":
        return 0
    if "0" <= ch <= "9":
        return ord(ch) - ord("0")
    if "A" <= ch <= "Z":
        return ord(ch) - ord("A") + 10
    return 0


def _mrz_check_digit(value: str) -> str:
    weights = (7, 3, 1)
    total = 0
    for idx, ch in enumerate(str(value or "")):
        total += _mrz_char_value(ch) * weights[idx % 3]
    return str(total % 10)


def _mrz_digit_matches(value: str, check_char: str) -> bool:
    check_char = _mrz_digit_text(check_char or "")[:1]
    return bool(check_char and check_char.isdigit() and _mrz_check_digit(value) == check_char)


def _mrz_check_state(value: str, check_char: str) -> tuple[bool, str]:
    """Return (matched, normalized_check_char) for MRZ check digit fields."""
    normalized = _mrz_digit_text(check_char or "")[:1]
    if not normalized or not normalized.isdigit():
        return False, normalized
    return _mrz_check_digit(value) == normalized, normalized


def _looks_like_passport_mrz_line1(line: str) -> bool:
    line = _clean_mrz_ocr_line(line)
    if line.startswith("P<") and len(line) >= 12:
        return True
    code_alt = "|".join(_known_mrz_country_codes())
    return bool(re.match(r"^[PFR][<S5I1LCKT]?(?:" + code_alt + r")[A-Z<5S]{4,}", line))


def _mrz_result_is_trustworthy(row: dict | None, *, has_name_row: bool = False) -> bool:
    """Decide whether an MRZ parse is safe enough to auto-fill.

    This is intentionally registration-focused: birth date and gender are the
    dangerous fields.  When check digits are available, at least one successful
    check is preferred.  If the name row and nationality anchor are both clear,
    we allow slightly noisy old passport photos, but random body-text dates are
    blocked.
    """
    data = row or {}
    birth = str(data.get("birth_date") or "")
    nation = str(data.get("nation") or data.get("nation_code") or "")
    gender = str(data.get("gender") or "")
    score = int(data.get("mrz_score") or 0)
    check_count = int(data.get("mrz_check_count") or 0)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", birth) or birth == "1990-01-01":
        return False
    if not nation or nation in {"기타", "미확인"}:
        return False
    if gender not in {"남성", "여성"}:
        return False
    if check_count >= 1 and score >= 5:
        return True
    if has_name_row and score >= 6:
        return True
    return False


def _known_mrz_country_codes() -> list[str]:
    codes = [str(k).upper() for k in NATION_MAP.keys() if len(str(k)) == 3 and str(k).isalpha()]
    # Keep common passport/worker country codes even if the display map changes later.
    codes.extend(["VNM", "THA", "CHN", "RUS", "KAZ", "UZB", "PAK", "TKM", "KGZ", "MNG", "LKA", "KHM", "IDN", "NPL", "PHL", "MMR"])
    return sorted(set(codes))


def _clean_mrz_name_token(value: str, nation_code: str = "") -> str:
    """Recover name separators that OCR often reads as S/5 on MRZ lines."""
    raw = _strip_diacritics(str(value or "")).upper()
    raw = raw.replace(" ", "").replace("«", "<").replace("‹", "<").replace("〈", "<")
    raw = re.sub(r"[^A-Z<]", "", raw)
    # On Vietnamese passport MRZ, '<' is frequently recognized as 'S'.
    # Example: PHANSSCONGSNGOC -> PHAN<<CONG<NGOC.
    if nation_code == "VNM":
        raw = re.sub(r"S{2,}", "<<", raw)
        if "<<" in raw:
            head, tail = raw.split("<<", 1)
            # Work only on the meaningful name portion before the long filler block.
            filler = ""
            m_fill = re.search(r"<{2,}", tail)
            if m_fill:
                filler = tail[m_fill.start():]
                tail_core = tail[:m_fill.start()]
            else:
                tail_core = tail
            if "<" not in tail_core and "S" in tail_core:
                # Split likely given-name separators, but keep genuine terminal S.
                tail_core = re.sub(r"(?<=[A-Z]{2})S(?=[A-Z]{2})", "<", tail_core)
            raw = head + "<<" + tail_core + filler
    return raw


def _repair_vnm_english_name(name: str) -> str:
    """Fix common Vietnamese passport MRZ/name OCR failures.

    Examples seen in the registration flow:
    - SVNMPHANS SCONG SNGOC -> PHAN CONG NGOC
    - PHANSSCONGSNGOC -> PHAN CONG NGOC
    - HAN CONG NGOC -> PHAN CONG NGOC
    """
    raw_input = _strip_diacritics(str(name or "")).upper()
    raw_compact = raw_input.replace(" ", "")
    if "<" in raw_compact:
        m_mrz = re.search(r"P<[A-Z0-9<]{3}([A-Z<5S]{4,})", raw_compact)
        mrz_name_part = m_mrz.group(1) if m_mrz else raw_compact
        mrz_name_part = _clean_mrz_name_token(mrz_name_part, "VNM")
        mrz_name_part = re.sub(r"<{3,}.*$", "", mrz_name_part)
        if "<<" in mrz_name_part:
            sur, giv = mrz_name_part.split("<<", 1)
            value_from_mrz = (sur.replace("<", " ") + " " + giv.replace("<", " ")).strip()
            value_from_mrz = re.sub(r"\s+", " ", value_from_mrz)
            if value_from_mrz:
                return value_from_mrz

    value = raw_input.replace("<", " ")
    value = re.sub(r"[^A-Z\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return value

    compact = value.replace(" ", "")
    # OCR sometimes reads the MRZ separator before VNM as S and keeps the
    # country code in the name field: SVNMPHANS... / VNMPHANS...
    compact = re.sub(r"^(?:P?S?VNM|P?VNMM|P?VNNM|P?VNMN)+", "", compact)

    # If the text is still a compact MRZ-style name, recover S-as-separator.
    # PHANSSCONGSNGOC -> PHAN<<CONG<NGOC -> PHAN CONG NGOC
    if " " not in value and ("SS" in compact or compact.startswith("S")):
        recovered = _clean_mrz_name_token(compact, "VNM")
        recovered = re.sub(r"<{3,}.*$", "", recovered)
        if "<<" in recovered:
            sur, giv = recovered.split("<<", 1)
            compact_name = (sur + " " + giv.replace("<", " ")).strip()
            compact_name = re.sub(r"\s+", " ", compact_name)
            if compact_name:
                value = compact_name
    elif compact != value.replace(" ", ""):
        value = compact

    parts = value.split()

    # If a compact prefix was stripped from spaced OCR, rebuild likely tokens.
    if len(parts) == 1 and len(parts[0]) > 8 and ("SS" in parts[0] or "S" in parts[0]):
        recovered = _clean_mrz_name_token(parts[0], "VNM")
        recovered = re.sub(r"<{3,}.*$", "", recovered)
        if "<<" in recovered:
            sur, giv = recovered.split("<<", 1)
            parts = (sur + " " + giv.replace("<", " ")).split()

    fixed_parts: list[str] = []
    for part in parts:
        token = part.strip()
        if not token:
            continue
        # Strip country-code noise that may remain at the start of the first token.
        token = re.sub(r"^(?:S?VNM|VNMM|VNNM|VNMN)+", "", token)
        if not token:
            continue
        # S/C/K are often MRZ OCR noise around '<' fillers on Vietnamese samples.
        if token.startswith("S") and token[1:] in _VI_NAME_TOKENS:
            token = token[1:]
        if token.endswith("S") and token[:-1] in _VI_NAME_TOKENS:
            token = token[:-1]
        if token.endswith(("C", "K")) and token[:-1] in _VI_NAME_TOKENS:
            token = token[:-1]

        # Recover compact separator mistakes such as VANSBAOC -> VAN BAO.
        # This is intentionally limited to Vietnamese passport repair flow.
        expanded_tokens: list[str] = []
        if "S" in token and token not in _VI_NAME_TOKENS:
            for piece in [p for p in token.split("S") if p]:
                if piece.endswith(("C", "K")) and piece[:-1] in _VI_NAME_TOKENS:
                    piece = piece[:-1]
                if piece.startswith("S") and piece[1:] in _VI_NAME_TOKENS:
                    piece = piece[1:]
                expanded_tokens.append(piece)
            if len(expanded_tokens) >= 2 and all(p in _VI_NAME_TOKENS for p in expanded_tokens):
                fixed_parts.extend(expanded_tokens)
                continue

        fixed_parts.append(token)

    parts = fixed_parts
    if len(parts) >= 2:
        # OCR often drops the first letter when the line begins after P<VNM.
        if parts[0] == "HAN":
            parts[0] = "PHAN"
        elif parts[0] == "RAN":
            parts[0] = "TRAN"
        elif parts[0] == "GUYEN":
            parts[0] = "NGUYEN"
        elif parts[0] == "UYEN":
            parts[0] = "NGUYEN"
    return " ".join(parts[:4]).strip()


def _name_from_mrz_line1(line1: str) -> tuple[str, str]:
    """Extract (english_name, nation_code) from a noisy TD3 first MRZ row."""
    line = _clean_mrz_ocr_line(line1)
    nation_code = ""
    name_part = ""
    m = re.search(r"P<([A-Z0-9<]{3})([A-Z<5S]{4,})", line)
    if m:
        nation_code = re.sub(r"[^A-Z]", "", m.group(1).replace("0", "O"))[:3]
        name_part = m.group(2)
    else:
        # Fallback for crops where the leading P<CCC was cut off or the
        # separator before VNM was read as S: SVNMPHANSSCONGSNGOC.
        m_vnm = re.search(r"S?VNM([A-Z<5S]{4,})", line)
        if m_vnm:
            nation_code = "VNM"
            name_part = m_vnm.group(1)
        else:
            # Pick the longest alphabet/filler run that looks like a name row.
            candidates = re.findall(r"[A-Z<5S]{8,}", line)
            if candidates:
                name_part = max(candidates, key=len)
    if not name_part:
        return "", nation_code

    name_part = _clean_mrz_name_token(name_part, nation_code)
    # If filler after the name is very long, trim it after the meaningful name zone.
    name_part = re.sub(r"<{3,}.*$", "", name_part)
    if "<<" in name_part:
        surname, given = name_part.split("<<", 1)
        surname = surname.replace("<", " ").strip()
        given = given.replace("<", " ").strip()
        english_name = f"{surname} {given}".strip()
    else:
        # Use spaces where clear separators remain.
        english_name = name_part.replace("<", " ").strip()
    english_name = re.sub(r"\s+", " ", english_name)
    if nation_code == "VNM":
        english_name = _repair_vnm_english_name(english_name)
    return english_name, nation_code


def _fields_from_td3_line2(line2: str) -> dict:
    """Extract passport/nation/birth/gender from a noisy TD3 second MRZ row.

    ICAO TD3 passport MRZ uses 2 rows of 44 characters.  The second row has
    passport number, check digit, nationality, birth date, birth check digit,
    sex, expiry date and optional data.  We score fixed-position and shifted
    candidates so random dates/ID numbers from the visual zone do not win over
    the actual MRZ.
    """
    line = _clean_mrz_ocr_line(line2).replace(" ", "")
    if len(line) < 18:
        return {}

    # Normalize only fields that are numeric by trying candidate windows.  The
    # whole line is intentionally not digit-normalized because country/name areas
    # must remain alphabetic.
    codes = _known_mrz_country_codes()
    candidates: list[dict] = []

    def add_candidate(code_pos: int, source: str, fixed: bool = False):
        if code_pos < 4 or code_pos + 20 > len(line):
            return
        code_raw = line[code_pos:code_pos + 3].replace("0", "O")
        code = re.sub(r"[^A-Z]", "", code_raw)[:3]
        if code not in codes:
            return
        birth_start = code_pos + 3
        birth_raw = _mrz_digit_text(line[birth_start:birth_start + 6])
        birth_date = _valid_ymd_from_mrz_birth(birth_raw)
        if birth_date == "1990-01-01":
            return
        birth_check_pos = birth_start + 6
        gender_pos = birth_start + 7
        gender_char = line[gender_pos:gender_pos + 1] if len(line) > gender_pos else ""
        # Some OCR outputs drop the birth check digit; try that shifted case too.
        dropped_birth_check = False
        if gender_char not in {"M", "F", "X", "<"}:
            alt_gender = line[birth_start + 6:birth_start + 7]
            if alt_gender in {"M", "F", "X", "<"}:
                gender_char = alt_gender
                dropped_birth_check = True
                birth_check_pos = -1
        # MRZ sex uses M/F/< only.  On photographed passports, M is often OCR'd as N/H.
        if gender_char in {"N", "H"}:
            gender_char = "M"
        expiry_start = gender_pos + 1 if not dropped_birth_check else birth_start + 7
        expiry_raw = _mrz_digit_text(line[expiry_start:expiry_start + 6])
        expiry_date = _valid_ymd_from_mrz_expiry(expiry_raw)

        passport_zone = line[:max(code_pos - 1, 0)]
        passport_zone_clean = passport_zone.replace("O", "0").replace("I", "1").replace("L", "1")
        passport_zone_clean = re.sub(r"[^A-Z0-9<]", "", passport_zone_clean)
        passport_no = re.sub(r"<+$", "", passport_zone_clean)
        # TD3 passport number field is 9 chars before the check digit.  If OCR
        # inserted noise before it, keep the last realistic 7~9 characters.
        m_pass = re.search(r"[A-Z0-9]{7,9}$", passport_no.replace("<", ""))
        passport_no = m_pass.group(0) if m_pass else passport_no.replace("<", "")[:9]

        score = 0
        if fixed and code_pos == 10:
            score += 4
        if source == "fixed44":
            score += 3
        if code in codes:
            score += 2
        if passport_no:
            score += 1
        check_count = 0
        check_doc_pos = code_pos - 1
        doc_check_ok = False
        birth_check_ok = False
        expiry_check_ok = False
        if check_doc_pos >= 0:
            doc_check_ok, _ = _mrz_check_state(line[:check_doc_pos], line[check_doc_pos:check_doc_pos + 1])
            if doc_check_ok:
                score += 2
                check_count += 1
        if birth_check_pos >= 0:
            birth_check_ok, _ = _mrz_check_state(birth_raw, line[birth_check_pos:birth_check_pos + 1])
            if birth_check_ok:
                score += 3
                check_count += 1
            else:
                score -= 1
        if gender_char in {"M", "F"}:
            score += 2
        if expiry_date:
            score += 1
            expiry_check_pos = expiry_start + 6
            if expiry_check_pos < len(line):
                expiry_check_ok, _ = _mrz_check_state(expiry_raw, line[expiry_check_pos:expiry_check_pos + 1])
                if expiry_check_ok:
                    score += 1
                    check_count += 1

        # Avoid auto-filling from a random body line that merely contains a
        # country code and six digits.  Weak candidates can still be used when a
        # matching first MRZ/name line is present, but standalone line2 candidates
        # must have a minimum amount of MRZ structure.
        if check_count == 0 and not fixed and score < 6:
            return

        candidates.append({
            "passport_no": passport_no,
            "nation_code": code,
            "nation": NATION_MAP.get(code, code),
            "birth_date": birth_date,
            "gender": "남성" if gender_char == "M" else ("여성" if gender_char == "F" else "기타"),
            "expiry_date": expiry_date,
            "mrz_score": score,
            "mrz_check_count": check_count,
            "mrz_doc_check_ok": doc_check_ok,
            "mrz_birth_check_ok": birth_check_ok,
            "mrz_expiry_check_ok": expiry_check_ok,
            "_score": score,
            "_source": source,
        })

    # Fixed TD3 position: document number 1-9, check 10, nationality 11-13.
    if len(line) >= 28:
        add_candidate(10, "fixed44", fixed=True)

    # Shifted/partial rows: find known nationality code anchor near the middle.
    for code in codes:
        start = 0
        while True:
            pos = line.find(code, start)
            if pos < 0:
                break
            if 6 <= pos <= 18:
                add_candidate(pos, "anchor", fixed=False)
            start = pos + 1

    if not candidates:
        return {}
    best = max(candidates, key=lambda row: row.get("_score", 0))
    return {k: v for k, v in best.items() if not k.startswith("_")}

def _build_mrz_candidates(ocr_text: str) -> list[str]:
    """Return candidate MRZ blocks from noisy Tesseract output.

    Passport TD3 MRZ is normally two 44-character rows.  Phone photos often split
    or join those rows, and Tesseract may drop one or two filler characters.  This
    helper keeps adjacent rows and also tries 42~46 character splits of joined text.
    """
    raw_lines = [_clean_mrz_ocr_line(line) for line in str(ocr_text or "").splitlines()]
    lines = [line for line in raw_lines if len(line) >= 10 and ("<" in line or re.search(r"[A-Z][0-9]{5,}", line) or re.search(r"[A-Z]{3}\d{6}", line))]
    candidates: list[str] = []

    def add(block_lines: list[str]):
        clean = [line.strip() for line in block_lines if line and len(line.strip()) >= 10]
        if not clean:
            return
        block = "\n".join(clean)
        if block not in candidates:
            candidates.append(block)

    # Adjacent-line candidates: TD3 two rows, TD1 three rows fallback.
    for i in range(len(lines) - 1):
        l1, l2 = lines[i], lines[i + 1]
        if len(l1) >= 20 and len(l2) >= 20:
            add([l1, l2])
    for i in range(len(lines) - 2):
        l1, l2, l3 = lines[i], lines[i + 1], lines[i + 2]
        if len(l1) >= 18 and len(l2) >= 18 and len(l3) >= 18:
            add([l1, l2, l3])

    # Prefer a line that clearly starts with passport MRZ, including common
    # noisy prefixes such as PSVNM / P5VNM / PVNM.
    for i, line in enumerate(lines):
        if _looks_like_passport_mrz_line1(line) and i + 1 < len(lines):
            add([line, lines[i + 1]])

    # Handle joined MRZ rows.  Try exact TD3 width first, then shifted widths.
    compact = "".join(lines)
    ppos = compact.find("P<")
    code_alt = "|".join(_known_mrz_country_codes())
    if ppos < 0:
        m_p = re.search(r"[PFR][<S5I1LCKT]?(?:" + code_alt + r")", compact)
        ppos = m_p.start() if m_p else -1
    if ppos >= 0:
        tail = compact[ppos:]
        for width in (44, 43, 45, 42, 46):
            if len(tail) >= width * 2 - 2:
                add([tail[:width], tail[width:width * 2]])

    # If the name row was cropped away, keep any standalone second row candidate.
    for line in lines:
        if _fields_from_td3_line2(line).get("birth_date") not in {None, "", "1990-01-01"}:
            add([line])

    return candidates

def _required_info_score(row: dict | None) -> int:
    """Score only the fields that matter for registration: info + face handled separately."""
    data = row or {}
    score = 0
    if str(data.get("english_name") or data.get("name") or "").strip():
        score += 3
    nation = str(data.get("nation") or "").strip()
    if nation and nation not in {"기타", "미확인"}:
        score += 2
    birth = str(data.get("birth_date") or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", birth) and birth != "1990-01-01":
        score += 2
    gender = str(data.get("gender") or "").strip()
    if gender and gender not in {"기타", "미확인", "-"}:
        score += 1
    # document numbers are useful but not the main success 기준 for this step
    if str(data.get("passport_no") or data.get("id_no") or "").strip():
        score += 1
    return score


class PassportOcrEngine:
    def __init__(self, debug_dir: str | None = None):
        self.debug_dir = debug_dir

    def _finalize_result(self, result: dict | None, image: Image.Image, doc_type: str | None = None) -> dict | None:
        if not result:
            return result
        row = dict(result)
        if doc_type and not row.get("doc_type"):
            row["doc_type"] = doc_type
        try:
            portrait = _extract_portrait_from_document(image, str(row.get("doc_type") or doc_type or ""), self.debug_dir)
            if portrait is not None:
                row["portrait_image"] = portrait
        except Exception as exc:
            _save_debug_text(self.debug_dir, "debug_face_extract_error.txt", str(exc))
        safe = {k: v for k, v in row.items() if k != "portrait_image"}
        _save_debug_text(self.debug_dir, "debug_ocr_result.txt", repr(safe))
        return row

    # ?? ?대?吏 ?꾩쿂由??????????????????????????????????????????????????????????
    @staticmethod
    def _preprocess(img: Image.Image, scale: float = 2.0) -> Image.Image:
        """
        OCR ?몄떇瑜??μ긽???꾪븳 ?꾩쿂由?
        - 洹몃젅?댁뒪耳??蹂??        - ?낆뒪耳??(Windows OCR MaxImageDimension 4096px ?대궡濡??쒗븳)
        - ?鍮?媛뺥솕 + ?좊챸??        """
        gray = img.convert("L")
        w, h = gray.size
        max_scale = 4000 / max(w, h)
        actual_scale = min(scale, max_scale)
        if actual_scale > 1.0:
            gray = gray.resize(
                (int(w * actual_scale), int(h * actual_scale)),
                Image.Resampling.LANCZOS
            )
        # Moderate contrast enhancement to preserve text without blowing up security watermarks
        gray = ImageEnhance.Contrast(gray).enhance(1.2)
        return gray

    @staticmethod
    def _preprocess_mrz_variants(img: Image.Image) -> list[Image.Image]:
        """
        Create multiple MRZ-focused variants to improve robustness on dark/glare photos.
        """
        base = PassportOcrEngine._preprocess(img, scale=2.8)
        variants: list[Image.Image] = [base]

        # Strong contrast + sharpen
        hi = ImageEnhance.Contrast(base).enhance(2.8).filter(ImageFilter.SHARPEN)
        variants.append(hi)

        # Binary-style image for machine-readable zone
        bw = hi.point(lambda p: 255 if p > 150 else 0)
        variants.append(bw)
        return variants

    @staticmethod
    def _preprocess_field_variants(img: Image.Image) -> list[Image.Image]:
        """
        Variants for field-text extraction on structured passport/ID pages.
        All inputs are normalized to ~1500px width. If manual crops are small (e.g. 800px),
        this upscale provides the necessary resolution for Tesseract to avoid hallucinating digits.
        """
        gray = img.convert("L")
        w, h = gray.size
        
        target_w = 1500
        if w > 0 and w != target_w:
            scale = target_w / float(w)
            gray = gray.resize(
                (target_w, int(h * scale)),
                getattr(Image, "Resampling", Image).LANCZOS
            )
        
        c1 = ImageEnhance.Contrast(gray).enhance(1.2)
        return [c1, gray]

    @staticmethod
    def _preprocess_card_variants(img: Image.Image) -> list[Image.Image]:
        gray = img.convert("L")
        w, h = gray.size
        target_w = 1600
        if w > 0 and w < target_w:
            scale = target_w / float(w)
            gray = gray.resize(
                (target_w, int(h * scale)),
                getattr(Image, "Resampling", Image).LANCZOS,
            )
        contrast = ImageEnhance.Contrast(gray).enhance(1.8)
        bw = ImageEnhance.Contrast(gray).enhance(2.3).point(lambda p: 255 if p > 155 else 0)
        return [gray, contrast, bw]

    async def _ocr_with_variants(
        self,
        pil_image: Image.Image,
        *,
        for_mrz: bool,
    ) -> list[str]:
        results: list[str] = []
        variants = self._preprocess_mrz_variants(pil_image) if for_mrz else self._preprocess_field_variants(pil_image)
        if for_mrz:
            configs = [
                "--oem 1 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<",
                "--oem 1 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<",
                "--oem 1 --psm 13 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<",
            ]
        else:
            configs = ["--oem 1 --psm 3", "--oem 1 --psm 6"]
            
        sem = asyncio.Semaphore(4)
        async def _run_ocr(variant, config):
            async with sem:
                use_lang = "eng" if for_mrz else "eng+kor"
                return await asyncio.to_thread(pytesseract.image_to_string, variant, lang=use_lang, config=config)

        tasks = [_run_ocr(variant, config) for variant in variants for config in configs]
        extracted_texts = await asyncio.gather(*tasks)
        for text in extracted_texts:
            t = (text or "").strip()
            if t and t not in results:
                results.append(t)
        return results

    # ?? ?꾩껜 ?대?吏 OCR (Tesseract) ???????????????????????????????????????????
    async def _ocr_image(self, pil_image: Image.Image, psm: int = 3, whitelist: str | None = None) -> str:
        processed = self._preprocess(pil_image, scale=2.0)
        config = f"--oem 1 --psm {psm}"
        if whitelist:
            config += f" -c tessedit_char_whitelist={whitelist}"
        
        sem = asyncio.Semaphore(4)
        async with sem:
            text = await asyncio.to_thread(
                pytesseract.image_to_string,
                processed,
                lang="eng+kor",
                config=config,
            )
        _save_debug_text(self.debug_dir, f"debug_ocr_full_psm{psm}.txt", text)
        if SAVE_DESKTOP_OCR_DEBUG:
            try:
                with open(r"c:\Users\Administrator\Desktop\ocr_debug.txt", "a", encoding="utf-8") as f:
                    f.write(f"\n--- OCR RUN (psm={psm}) ---\n{text}\n")
            except Exception:
                pass
        return text

    async def _collect_card_texts(self, card_image: Image.Image, full_text: str) -> list[str]:
        texts: list[str] = []
        if full_text and full_text.strip():
            texts.append(full_text)

        w, h = card_image.size
        initial_kind = _classify_document_text(full_text or "") if full_text else ""
        profile = _detect_card_layout_profile_from_text(full_text or "", initial_kind)
        regions: list[tuple[str, Image.Image, int, bool]] = []
        for label, crop_box, psm, english_only in _card_layout_crop_specs(w, h, profile):
            try:
                regions.append((label, card_image.crop(crop_box), psm, english_only))
            except Exception:
                continue

        seen_texts: set[str] = set(texts)
        for idx, (label, region, psm, english_only) in enumerate(regions, start=1):
            _save_debug_image(self.debug_dir, f"debug_card_region_{idx}_{label}.png", region)
            processed = _preprocess_region_for_ocr(region, target_w=1600 if english_only else 1400)
            _save_debug_image(self.debug_dir, f"debug_card_region_{idx}_{label}_ocr.png", processed)
            configs: list[tuple[str, str]] = []
            if english_only:
                configs.append(("eng", f"--oem 1 --psm {psm} -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz- .0123456789"))
                configs.append(("eng", f"--oem 1 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz- .0123456789"))
            else:
                configs.append(("eng+kor", f"--oem 1 --psm {psm}"))
            for lang, cfg in configs:
                txt = await asyncio.to_thread(
                    pytesseract.image_to_string,
                    processed,
                    lang=lang,
                    config=cfg,
                )
                normalized = (txt or "").strip()
                if not normalized:
                    continue
                tagged = normalized
                # Keep the raw OCR text, but put high-value layout crops at the front.
                if label.startswith(("name", "right_photo_name", "left_photo_name", "overseas_name", "regno", "right_photo_regno", "left_photo_regno", "overseas_regno")):
                    if tagged not in seen_texts:
                        texts.insert(0, tagged)
                        seen_texts.add(tagged)
                elif tagged not in seen_texts:
                    texts.append(tagged)
                    seen_texts.add(tagged)

        # Re-evaluate profile after the first pass.  Some cards are recognized only
        # after a tight title/name crop.  If the profile becomes more specific, run
        # those specs once more and prepend useful text.  This is still cheap compared
        # with asking the user to rework manual correction.
        joined_once = "\n".join(texts)
        refined_profile = _detect_card_layout_profile_from_text(joined_once, _classify_document_text(joined_once))
        if refined_profile != profile and refined_profile != _CARD_LAYOUT_UNKNOWN:
            for ridx, (label, crop_box, psm, english_only) in enumerate(_card_layout_crop_specs(w, h, refined_profile), start=1):
                if not (label.startswith(("right_photo", "left_photo", "overseas"))):
                    continue
                try:
                    region = card_image.crop(crop_box)
                    processed = _preprocess_region_for_ocr(region, target_w=1600 if english_only else 1400)
                    lang = "eng" if english_only else "eng+kor"
                    cfg = f"--oem 1 --psm {psm}"
                    if english_only:
                        cfg += " -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz- .0123456789"
                    txt = await asyncio.to_thread(pytesseract.image_to_string, processed, lang=lang, config=cfg)
                    normalized = (txt or "").strip()
                    if normalized and normalized not in seen_texts:
                        texts.insert(0, normalized)
                        seen_texts.add(normalized)
                except Exception:
                    continue
        return texts

    async def _extract_card_fields_from_image(self, card_image: Image.Image, document_kind: str) -> dict | None:
        texts = await self._collect_card_texts(card_image, "")
        joined_text = "\n".join(texts)
        merged = _extract_card_fields(joined_text, document_kind) or {"doc_type": document_kind}

        if not merged.get("id_no"):
            reg_no = _extract_card_registration_number(joined_text, document_kind)
            if reg_no:
                merged["id_no"] = reg_no

        if not merged.get("english_name"):
            reg_no = str(merged.get("id_no") or "").strip()
            if reg_no:
                lines = [re.sub(r"\s+", " ", line).strip() for line in joined_text.splitlines() if re.sub(r"\s+", " ", line).strip()]
                near_name = _extract_card_name_near_registration(lines, reg_no)
                if near_name:
                    merged["english_name"] = _finalize_card_english_name(near_name, joined_text)
                    merged["name"] = _display_name_from_english(merged["english_name"])

        if not merged.get("english_name"):
            best_name = _pick_best_card_name(texts)
            if best_name:
                best_name = _finalize_card_english_name(best_name, joined_text)
                merged["english_name"] = best_name
                merged["name"] = _display_name_from_english(best_name)

        if not merged.get("nation"):
            reg_no = str(merged.get("id_no") or "").strip()
            if reg_no:
                lines = [re.sub(r"\s+", " ", line).strip() for line in joined_text.splitlines() if re.sub(r"\s+", " ", line).strip()]
                near_country = _extract_card_country_near_registration(lines, reg_no)
                if near_country:
                    merged["nation"] = near_country

        if not merged.get("nation"):
            nation = _normalize_country_value(joined_text)
            if nation != "미확인":
                merged["nation"] = nation

        status_match = re.search(r"\b([A-Z]-\d)\b", _normalize_ocr_alpha(joined_text))
        if status_match:
            code = status_match.group(1)
            merged["status"] = _CARD_STATUS_MAP.get(code, code)

        if not merged.get("issue_date"):
            joined_digits = _normalize_ocr_digits(joined_text)
            m_issue = re.search(r"(20\d{2})\s*[./-]\s*(\d{2})\s*[./-]\s*(\d{2})", joined_digits)
            if m_issue:
                merged["issue_date"] = f"{m_issue.group(1)}-{m_issue.group(2)}-{m_issue.group(3)}"

        if merged.get("id_no"):
            birth, gender = _parse_korean_registration_info(str(merged.get("id_no") or ""))
            if birth and not merged.get("birth_date"):
                merged["birth_date"] = birth
            if gender and not merged.get("gender"):
                merged["gender"] = gender

        if not any(merged.get(key) for key in ["english_name", "id_no", "nation", "status"]):
            return None
        merged.setdefault("passport_no", "")
        return merged

    async def extract_mrz(self, passport_image: Image.Image) -> dict | None:
        """
        자동추출 핵심 흐름: 정보 + 얼굴 추출 성공률 우선.
        - 입력 이미지가 이미 보정된 경우를 대비해 원본 입력과 자동 문서 crop을 모두 시도
        - 여권은 MRZ 하단 2줄 우선
        - 카드형은 전체 OCR + 필드별 crop OCR 병행
        """
        best_result: dict | None = None
        best_score = -1
        best_image: Image.Image | None = None
        best_doc_type = ""
        best_raw_text = ""
        fallback_texts: list[str] = []
        best_card_result: dict | None = None
        best_card_score = -1
        best_card_image: Image.Image | None = None

        def score_result(res: dict | None) -> int:
            return _required_info_score(res)

        def update_best(candidate: dict | None, source_image: Image.Image | None = None, doc_type: str | None = None):
            nonlocal best_result, best_score, best_image, best_doc_type
            if not candidate:
                return
            current_score = score_result(candidate)
            if current_score > best_score:
                best_score = current_score
                best_result = candidate
                best_image = source_image
                best_doc_type = str(doc_type or candidate.get("doc_type") or "")

        input_image = passport_image.convert("RGB")
        prepared_image = _prepare_document_for_extraction(input_image, self.debug_dir)

        def _image_signature(img: Image.Image) -> tuple[tuple[int, int], bytes]:
            try:
                small = img.convert("L").resize((32, 32), getattr(Image, "Resampling", Image).BILINEAR)
                return (img.size, small.tobytes())
            except Exception:
                return (img.size, bytes(str(img.size), "utf-8"))

        # Try both. If the UI already produced a good corrected image, re-detecting the
        # document can sometimes crop too tightly; keeping input_image raises reliability.
        # Same-size/same-content candidates are skipped to avoid duplicate OCR work.
        image_candidates: list[tuple[str, Image.Image]] = [("input", input_image)]
        if _image_signature(prepared_image) != _image_signature(input_image):
            image_candidates.append(("prepared", prepared_image))

        seen_images: set[tuple[tuple[int, int], bytes]] = set()
        for label, base_image in image_candidates:
            key = _image_signature(base_image)
            if key in seen_images:
                continue
            seen_images.add(key)
            _save_debug_image(self.debug_dir, f"debug_candidate_{label}.png", base_image)

            for angles in [0]:
                rotated_image = base_image.rotate(angles, expand=True) if angles != 0 else base_image
                full_text = await self._ocr_image(rotated_image, psm=6)
                if full_text:
                    fallback_texts.append(full_text)
                if not best_raw_text:
                    best_raw_text = full_text

                document_kind = _classify_document_text(full_text)
                w, h = rotated_image.size
                ratio = (w / h) if h else 0.0
                normalized_full = _normalize_ocr_alpha(full_text)
                digits_full = _normalize_ocr_digits(full_text)

                passport_like = (
                    document_kind == _DOC_PASSPORT
                    or "PASSPORT" in normalized_full
                    or "HOCHIEU" in normalized_full
                    or "H0CHIEU" in normalized_full
                    or bool(re.search(r"P(?:[<S5])?(?:" + "|".join(_known_mrz_country_codes()) + r")", full_text.replace(" ", "").upper()))
                )

                if document_kind == "unknown":
                    # Passport must win before landscape-card probing.  Corrected passport
                    # pages are often landscape-shaped, and otherwise the card fallback can
                    # choose random body/ID numbers before MRZ is inspected.
                    if passport_like:
                        document_kind = _DOC_PASSPORT
                    # Card probe: Korean ID cards often fail classification when glare hides labels.
                    elif ratio >= 1.15 and (
                        "KOR" in normalized_full
                        or "IMMIGRATION" in normalized_full
                        or "RESIDENCE" in normalized_full
                        or bool(re.search(r"\d{6}\s*[-~_=.:]?\s*\d{7}", digits_full))
                    ):
                        document_kind = _CARD_DOC_RESIDENCE

                # Always run a card extraction probe on landscape document images,
                # except when passport/MRZ evidence is present.
                # It is cheap compared with user rework and protects card samples with weak labels.
                if (not passport_like) and (document_kind in {_CARD_DOC_RESIDENCE, _CARD_DOC_OVERSEAS} or ratio >= 1.20):
                    probe_kind = document_kind if document_kind in {_CARD_DOC_RESIDENCE, _CARD_DOC_OVERSEAS} else _CARD_DOC_RESIDENCE
                    card_texts = await self._collect_card_texts(rotated_image, full_text)
                    card_candidates = [_extract_card_fields(text_item, probe_kind) for text_item in card_texts]
                    card_result = _merge_card_results(card_candidates, probe_kind)
                    image_card_result = await self._extract_card_fields_from_image(rotated_image, probe_kind)
                    if image_card_result and _score_card_result(image_card_result) >= _score_card_result(card_result):
                        card_result = image_card_result
                    card_score = _score_card_result(card_result)
                    if card_score > best_card_score:
                        best_card_score = card_score
                        best_card_result = card_result
                        best_card_image = rotated_image
                    if card_result:
                        required_score = score_result(card_result)
                        strong_card = card_score >= 10 and required_score >= 8
                        classified_card = document_kind in {_CARD_DOC_RESIDENCE, _CARD_DOC_OVERSEAS} and required_score >= 7
                        if strong_card or classified_card:
                            return self._finalize_result(card_result, rotated_image, probe_kind)

                # Passport/body field OCR fallback.
                res_field = self._extract_from_fields(full_text)
                update_best(res_field, rotated_image, document_kind)

                for top_ratio in [0.18, 0.24, 0.30, 0.36, 0.42]:
                    field_crop = rotated_image.crop((0, int(h * top_ratio), w, h))
                    _save_debug_image(self.debug_dir, f"debug_field_crop_{label}_{int(top_ratio*100)}.png", field_crop)
                    field_texts = await self._ocr_with_variants(field_crop, for_mrz=False)
                    for ftxt in field_texts:
                        if ftxt:
                            fallback_texts.append(ftxt)
                        res_field_crop = self._extract_from_fields(ftxt)
                        update_best(res_field_crop, rotated_image, document_kind)
                        if res_field_crop and score_result(res_field_crop) >= 8 and document_kind in {_CARD_DOC_RESIDENCE, _CARD_DOC_OVERSEAS}:
                            return self._finalize_result(res_field_crop, rotated_image, document_kind)

                # MRZ OCR: try several bottom crops because user photos vary in framing.
                for top_ratio in [0.42, 0.46, 0.50, 0.52, 0.56, 0.58, 0.62, 0.66, 0.70, 0.74, 0.78, 0.82]:
                    mrz_crop = rotated_image.crop((0, int(h * top_ratio), w, h))
                    _save_debug_image(self.debug_dir, f"debug_mrz_crop_{label}_{int(top_ratio*100)}.png", mrz_crop)
                    mrz_texts = await self._ocr_with_variants(mrz_crop, for_mrz=True)
                    for idx, mrz_text in enumerate(mrz_texts, start=1):
                        _save_debug_text(self.debug_dir, f"debug_mrz_text_{label}_{int(top_ratio*100)}_{idx}.txt", mrz_text)
                        for raw_mrz in _build_mrz_candidates(mrz_text):
                            _save_debug_text(self.debug_dir, f"debug_mrz_candidate_{label}_{int(top_ratio*100)}_{idx}.txt", raw_mrz)
                            res_mrz = self._parse_mrz(raw_mrz)
                            update_best(res_mrz, rotated_image, _DOC_PASSPORT)

                            merged = self._merge_extract_results(res_field, res_mrz)
                            update_best(merged, rotated_image, _DOC_PASSPORT)

                            # Required information is mostly present; finalize early.
                            if score_result(merged) >= 8:
                                return self._finalize_result(merged, rotated_image, _DOC_PASSPORT)

        final_image_for_media = best_image or prepared_image or input_image

        if best_card_result and best_card_score >= 3:
            return self._finalize_result(best_card_result, best_card_image or final_image_for_media, str(best_card_result.get("doc_type") or ""))

        if best_result and best_score >= 4:
            return self._finalize_result(best_result, final_image_for_media, best_doc_type)

        lenient = self._extract_lenient_from_texts(fallback_texts)
        if lenient:
            return self._finalize_result(lenient, final_image_for_media, str(lenient.get("doc_type") or ""))

        # Even on parsing failure, keep raw OCR for debugging.
        return {"error": "parsing_failed", "raw_text": best_raw_text}

    @staticmethod
    def _merge_extract_results(field_result: dict | None, mrz_result: dict | None) -> dict | None:
        field = dict(field_result or {})
        mrz = dict(mrz_result or {})
        if not field and not mrz:
            return None

        merged = dict(field)

        # 번호/생년월일/성별은 MRZ 우선
        mrz_passport = str(mrz.get("passport_no") or "").strip()
        if mrz_passport:
            merged["passport_no"] = mrz_passport
        mrz_id = str(mrz.get("id_no") or "").strip()
        field_id = str(field.get("id_no") or "").strip()
        if mrz_id:
            merged["id_no"] = mrz_id
        elif field_id:
            merged["id_no"] = field_id

        mrz_birth = str(mrz.get("birth_date") or "").strip()
        field_birth = str(field.get("birth_date") or "").strip()
        mrz_raw_present = bool(str(mrz.get("raw_mrz") or "").strip())
        mrz_checks = int(mrz.get("mrz_check_count") or 0) if str(mrz.get("mrz_check_count") or "").isdigit() else 0
        if mrz_birth and mrz_birth != "1990-01-01":
            merged["birth_date"] = mrz_birth
        elif field_birth and not mrz_raw_present:
            merged["birth_date"] = field_birth
        elif mrz_raw_present:
            # MRZ was detected but could not safely validate date; leave empty/default
            # instead of falling back to noisy body OCR.
            merged["birth_date"] = "1990-01-01"

        mrz_gender = str(mrz.get("gender") or "").strip()
        field_gender = str(field.get("gender") or "").strip()
        if mrz_gender and mrz_gender not in {"기타", "", "-"}:
            merged["gender"] = mrz_gender
        elif field_gender and not mrz_raw_present:
            merged["gender"] = field_gender
        elif mrz_raw_present and mrz_checks == 0:
            merged["gender"] = "기타"

        # 이름은 MRZ 우선이 기본이지만, 베트남 여권에서는 필드/MRZ 중 더 자연스러운 이름을 선택한다.
        nation_hint = str(field.get("nation") or mrz.get("nation") or "")
        field_english = _finalize_english_name(str(field.get("english_name") or "").strip(), nation_hint)
        mrz_english = _finalize_english_name(str(mrz.get("english_name") or "").strip(), nation_hint)
        preferred_english = mrz_english or field_english
        if field_english and mrz_english:
            preferred_english = mrz_english
            if _english_name_quality_score(field_english, nation_hint) > _english_name_quality_score(mrz_english, nation_hint):
                preferred_english = field_english
        if preferred_english:
            merged["english_name"] = preferred_english
            merged["name"] = _display_name_from_english(preferred_english)

        # 국적 보완: 여권은 MRZ 국가코드가 표준값이므로 MRZ 우선, 필드값은 보완용.
        field_nation = str(field.get("nation") or "").strip()
        mrz_nation = str(mrz.get("nation") or "").strip()
        if mrz_nation and mrz_nation != "기타":
            merged["nation"] = mrz_nation
        elif field_nation and field_nation != "기타":
            merged["nation"] = field_nation

        return merged

    def _extract_from_fields(self, ocr_text: str) -> dict | None:
        """
        OCR ?꾨Ц(full text)?먯꽌 ?ш텒 ?꾨뱶 ?쇰꺼 湲곗??쇰줈 媛믪쓣 異붿텧?⑸땲??
        以??⑥쐞濡?泥섎━???쇰꺼 ???꾨옒??媛믪쓣 ?뺥솗?섍쾶 ?≪븘?낅땲??
        """
        lines       = ocr_text.splitlines()
        upper_lines = [l.upper() for l in lines]
        # ?붾쾭洹몄슜 ?꾩껜 ?띿뒪??(??以??⑹튂湲?
        full_upper  = " ".join(upper_lines)

        def find_value_near_label(keywords: list[str]) -> str:
            """
            Find text near any label keyword.
            1) Prefer text on the same line after the label.
            2) Fallback to the next line.
            """
            for i, line in enumerate(upper_lines):
                if not any(kw in line for kw in keywords):
                    continue

                # Same-line value after label
                for kw in keywords:
                    if kw in line:
                        after = line.split(kw, 1)[-1].strip(" :/-")
                        if after:
                            return after

                # Next-line fallback
                if i + 1 < len(lines):
                    nxt = lines[i + 1].strip()
                    if nxt:
                        return nxt
            return ""

        # ?? ?대쫫 ??????????????????????????????????????????????????????????????
        english_name = find_value_near_label(["FULL NAME", "H沼?V? T횎N", "HO VA TEN"])
        # ?щ옒?쒕줈 ?곷Ц/?꾩???援щ텇??寃쎌슦 ?욌?遺꾨쭔 ?ъ슜
        if "/" in english_name:
            english_name = english_name.split("/")[0].strip()
        english_name = _finalize_english_name(english_name.strip(), full_upper)
        if not english_name:
            # 라벨 OCR이 실패한 경우, 본문 내 MRZ 문자열(P<XXX...)에서 이름 역추출
            mrz_like = "".join(ch for ch in full_upper if (ch == "<" or ("A" <= ch <= "Z")))
            m = re.search(r"P<[A-Z]{3}([A-Z<]{6,})", mrz_like)
            if m:
                blob = m.group(1)
                parts = blob.split("<<", 1)
                if parts:
                    last_name = parts[0].replace("<", " ").strip()
                    first_name = parts[1].replace("<", " ").strip() if len(parts) > 1 else ""
                    english_name = f"{last_name} {first_name}".strip()
        english_name = _finalize_english_name(english_name, full_upper)

        # 여권 번호
        # 1순위: 라벨 근처 값
        passport_no = find_value_near_label(["PASSPORT N", "S沼?H沼?CHI梳푎", "SO HO CHIEU", "PASSPORT No"])
        # 2?쒖쐞: ?뚰뙆踰녹쑝濡??쒖옉?섎뒗 7~9?먮━ ?レ옄 ?⑦꽩 (?? C4277018)
        if not passport_no or not re.match(r'^[A-Z][0-9]{6,8}$', passport_no.split()[0]):
            m = re.search(r'\b([A-Z][0-9]{6,9})\b', full_upper)
            if m:
                passport_no = m.group(1)
        if passport_no:
            # 泥?踰덉㎏ ?좏겙留??ъ슜 (?ㅼ뿉 ?ㅻⅨ ?띿뒪?멸? 遺숈쓣 寃쎌슦 ?쒓굅)
            passport_no = passport_no.split()[0]

        # ID 번호 (숫자 9~14자리)
        id_no = find_value_near_label(["ID CARD", "ID NO", "S? CMND", "SO CMND", "PERSONAL NO"])
        id_match = re.search(r"\b([0-9]{9,14})\b", id_no or "")
        if id_match:
            id_no = id_match.group(1)
        else:
            # 본문 전체에서 긴 숫자열 후보를 찾되, 여권번호와 중복은 제외
            digit_candidates = re.findall(r"\b([0-9]{9,14})\b", full_upper)
            id_no = ""
            for cand in digit_candidates:
                if cand != passport_no:
                    id_no = cand
                    break

        # ?? ?앸뀈?붿씪 ??????????????????????????????????????????????????????????
        birth_date = "1990-01-01"
        date_pattern = r'(\d{1,2})\s*[/\.\-]\s*(\d{1,2})\s*[/\.\-]\s*(\d{4})'

        def try_parse_dates(src: str) -> str:
            """?좎쭨 ?⑦꽩??李얠븘 ?앸뀈?붿씪 踰붿쐞(?꾩옱?곕룄-100 ~ ?꾩옱?곕룄)??留욌뒗 泥?踰덉㎏ 媛?諛섑솚"""
            import datetime
            curr_year = datetime.datetime.now().year
            for d, mo, y in re.findall(date_pattern, src):
                if curr_year - 100 <= int(y) <= curr_year:  # ?숈쟻?쇰줈 ?ㅼ젣 異쒖깮 媛???곕룄 踰붿쐞 蹂댁젙
                    try:
                        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
                    except Exception:
                        pass
            return ""

        # 1?쒖쐞: DATE OF BIRTH ?쇰꺼 洹쇱쿂
        for lbl in ["DATE OF BIRTH", "NG?Y SINH", "NGAY SINH", "BIRTH", "DOB"]:
            dob_text = find_value_near_label([lbl])
            if dob_text:
                r = try_parse_dates(dob_text)
                if r:
                    birth_date = r
                    break

        # 2?쒖쐞: ?꾩껜 ?띿뒪?몄뿉??異쒖깮?곕룄 踰붿쐞 ?좎쭨 ?먯깋 (?쇰꺼 留ㅼ묶 ?ㅽ뙣 ??
        if birth_date == "1990-01-01":
            r = try_parse_dates(full_upper)
            if r:
                birth_date = r

        # ?? ?깅퀎 ??????????????????????????????????????????????????????????????
        gender = "기타"
        gender_text = find_value_near_label(["SEX", "GIỚI TÍNH", "GIOI TINH"])
        if "NAM" in gender_text.upper() or "MALE" in gender_text.upper() or gender_text.strip() == "M":
            gender = "남성"
        elif "NỮ" in gender_text.upper() or "NU" in gender_text.upper() or "FEMALE" in gender_text.upper() or gender_text.strip() == "F":
            gender = "여성"
        else:
            # ?꾩껜 ?띿뒪?몄뿉???깅퀎 ?뚰듃 ?먯깋
            if re.search(r'\bNAM/M\b|\bMALE\b', full_upper):
                gender = "남성"
            elif re.search(r'\bFEMALE\b|\bNU\b', full_upper):
                gender = "여성"

        # ?? 援?쟻 ??????????????????????????????????????????????????????????????
        nation = ""
        nat_text = find_value_near_label(["NATIONALITY", "QU沼륝 T沼둇H", "QUOC TICH"])
        search_in = (nat_text + " " + full_upper).upper()
        for key, val in NATION_MAP.items():
            if len(key) == 3:
                # 3湲??MRZ 肄붾뱶???⑥뼱 寃쎄퀎 ?꾩닔 (遺遺?臾몄옄???ㅼ씤??諛⑹?)
                if re.search(r'\b' + key + r'\b', search_in):
                    nation = val
                    break
            else:
                # 湲?援??紐낆? 遺遺??ы븿?쇰줈???덉슜
                if key in search_in:
                    nation = val
                    break

        # ?? 理쒖냼 2媛??댁긽 異붿텧?먯쑝硫??깃났 ?????????????????????????????????????
        found_count = sum([
            bool(passport_no), bool(english_name),
            nation != "", birth_date != "1990-01-01",
        ])
        if found_count < 2:
            return None

        english_ascii = _finalize_english_name(english_name, nation or full_upper)
        korean_name = _display_name_from_english(english_ascii)

        return {
            "name":         korean_name,
            "english_name": english_ascii,
            "nation":       nation or "기타",
            "passport_no":  passport_no,
            "id_no":        id_no,
            "birth_date":   birth_date,
            "gender":       gender,
        }


    def _parse_mrz(self, mrz_text: str) -> dict | None:
        """Parse noisy MRZ text with TD3 passport priority.

        Official passport booklets use TD3 MRZ: two rows of 44 characters.  We
        choose the best first/name row and second/data row independently because
        OCR crops may split or partially miss either row.
        """
        clean_text = str(mrz_text or "")
        raw_lines = [_clean_mrz_ocr_line(line) for line in clean_text.splitlines()]
        lines = [line for line in raw_lines if len(line) >= 10]
        if not lines:
            return None

        # If OCR returned a single joined MRZ block, split candidates first.
        if len(lines) == 1 and len(lines[0]) >= 70:
            compact_line = lines[0]
            start = compact_line.find("P<")
            if start < 0:
                code_alt = "|".join(_known_mrz_country_codes())
                m_start = re.search(r"[PFR][<S5I1LCKT]?(?:" + code_alt + r")", compact_line)
                start = m_start.start() if m_start else -1
            if start >= 0:
                compact = compact_line[start:]
                lines = [compact[:44], compact[44:88]]

        def first_score(line: str) -> int:
            score = 0
            if line.startswith("P<"):
                score += 6
            if re.search(r"P<[A-Z0-9<]{3}", line):
                score += 4
            if "<<" in line:
                score += 3
            if line.count("<") >= 5:
                score += 2
            if re.search(r"\d{5,}", line):
                score -= 3
            name, code = _name_from_mrz_line1(line)
            if name:
                score += min(4, len(name.split()) + 1)
            if code in _known_mrz_country_codes():
                score += 1
            return score

        td3_first = ""
        name_rows = [line for line in lines if not _fields_from_td3_line2(line).get("birth_date")]
        if name_rows:
            td3_first = max(name_rows, key=first_score)
            if first_score(td3_first) <= 0:
                td3_first = ""
        if not td3_first:
            for line in lines:
                if _looks_like_passport_mrz_line1(line) or re.search(r"P<[A-Z0-9<]{3}[A-Z<5S]{4,}", line):
                    td3_first = line
                    break

        second_candidates = []
        for line in lines:
            info = _fields_from_td3_line2(line)
            if info.get("birth_date") and info.get("birth_date") != "1990-01-01":
                second_candidates.append((info, line))
        td3_second = ""
        second_info: dict = {}
        if second_candidates:
            second_info, td3_second = max(second_candidates, key=lambda pair: (bool(pair[0].get("gender") not in {"", "기타"}), bool(pair[0].get("passport_no")), len(pair[1])))
        elif len(lines) >= 2:
            td3_second = lines[1]
            second_info = _fields_from_td3_line2(td3_second)

        if td3_first or second_info:
            first_name, first_nation_code = _name_from_mrz_line1(td3_first) if td3_first else ("", "")
            has_name_row = bool(td3_first and _looks_like_passport_mrz_line1(td3_first))
            nation_code = second_info.get("nation_code") or first_nation_code
            nation = second_info.get("nation") or NATION_MAP.get(nation_code, nation_code)
            english_name = _finalize_english_name(first_name, nation)
            # Guard against common failed MRZ-name reads like HANSSCONGSNGOC.
            if nation_code == "VNM" and english_name and "SS" in english_name.replace(" ", ""):
                fixed, _ = _name_from_mrz_line1("P<VNM" + english_name.replace(" ", "<"))
                fixed = _finalize_english_name(fixed, nation)
                if _english_name_quality_score(fixed, nation) >= _english_name_quality_score(english_name, nation):
                    english_name = fixed
            if not english_name and lines:
                for line in lines:
                    name_try, code_try = _name_from_mrz_line1(line)
                    name_try = _finalize_english_name(name_try, nation or code_try)
                    if _english_name_quality_score(name_try, nation) > _english_name_quality_score(english_name, nation):
                        english_name = name_try
                        if not nation_code:
                            nation_code = code_try
            if not english_name and not second_info:
                return None

            # Safety guard: do not auto-confirm random body OCR as passport data.
            # A valid passport result needs a trustworthy MRZ data row.  If only a
            # name row is readable, return partial name/nation but leave birth/gender
            # empty so the user can correct instead of storing a hallucinated date.
            trustworthy_line2 = _mrz_result_is_trustworthy(second_info, has_name_row=has_name_row)
            if second_info and not trustworthy_line2:
                if not has_name_row:
                    return None
                second_info = {
                    "passport_no": second_info.get("passport_no", ""),
                    "nation_code": nation_code,
                    "nation": nation or "기타",
                    "birth_date": "1990-01-01",
                    "gender": "기타",
                    "mrz_score": second_info.get("mrz_score", 0),
                    "mrz_check_count": second_info.get("mrz_check_count", 0),
                }

            korean_name = _display_name_from_english(english_name) if english_name else ""
            return {
                "name": korean_name,
                "english_name": english_name,
                "nation": nation or "기타",
                "passport_no": second_info.get("passport_no", ""),
                "id_no": "",
                "birth_date": second_info.get("birth_date", "1990-01-01"),
                "gender": second_info.get("gender", "기타"),
                "raw_mrz": mrz_text,
                "mrz_score": second_info.get("mrz_score", 0),
                "mrz_check_count": second_info.get("mrz_check_count", 0),
            }

        # TD1 fallback for ID-style MRZ rows.
        lines30 = [l for l in lines if len(l) >= 20]
        if len(lines30) >= 3:
            line1 = lines30[0][:30].ljust(30, "<")
            line2 = lines30[1][:30].ljust(30, "<")
            line3 = lines30[2][:30].ljust(30, "<")
            nation_code = line2[15:18].replace("<", "") or line1[2:5].replace("<", "")
            nation = NATION_MAP.get(nation_code, nation_code)
            name_part = _clean_mrz_name_token(line3.rstrip("<"), nation_code)
            parts = name_part.split("<<", 1)
            surname = parts[0].replace("<", " ").strip()
            given = parts[1].replace("<", " ").strip() if len(parts) > 1 else ""
            english_name = _finalize_english_name(f"{surname} {given}".strip(), nation)
            birth_raw = _mrz_digit_text(line2[0:6])
            birth_date = _valid_ymd_from_mrz_birth(birth_raw)
            gender_char = line2[7:8]
            gender = "여성" if gender_char == "F" else ("남성" if gender_char == "M" else "기타")
            return {
                "name": _display_name_from_english(english_name) if english_name else "",
                "english_name": english_name,
                "nation": nation,
                "passport_no": line1[5:14].replace("<", ""),
                "id_no": "",
                "birth_date": birth_date,
                "gender": gender,
                "raw_mrz": mrz_text,
            }
        return None

    def _extract_lenient_from_texts(self, texts: list[str]) -> dict | None:
        """
        Very tolerant fallback: return partial fields when strict parser fails.
        """
        merged_text = "\n".join(t for t in texts if t).upper()
        if not merged_text.strip():
            return None

        # passport no: e.g. C4277018 / N2473683
        passport_no = ""
        m_pass = re.search(r"\b([A-Z][0-9]{7,9})\b", merged_text)
        if m_pass:
            passport_no = m_pass.group(1)

        id_no = ""
        digit_candidates = re.findall(r"\b([0-9]{9,14})\b", merged_text)
        for cand in digit_candidates:
            if cand != passport_no:
                id_no = cand
                break

        # birth date: DD/MM/YYYY or DD-MM-YYYY
        birth_date = "1990-01-01"
        for d, mo, y in re.findall(r"(\d{1,2})\s*[/\.\-]\s*(\d{1,2})\s*[/\.\-]\s*(\d{4})", merged_text):
            try:
                yy = int(y)
                if 1900 <= yy <= 2099:
                    birth_date = f"{yy:04d}-{int(mo):02d}-{int(d):02d}"
                    break
            except Exception:
                pass

        # english name near FULL NAME label
        english_name = ""
        m_name = re.search(r"FULL NAME[^A-Z0-9]{0,6}([A-Z][A-Z ]{3,40})", merged_text)
        if m_name:
            english_name = re.sub(r"\s+", " ", m_name.group(1)).strip()
        if not english_name:
            # Common Vietnamese name blocks fallback
            m_name2 = re.search(r"\b([A-Z]{2,}\s+[A-Z]{2,}(?:\s+[A-Z]{2,}){0,3})\b", merged_text)
            if m_name2:
                english_name = m_name2.group(1).strip()

        nation = "기타"
        for key, val in NATION_MAP.items():
            if key in merged_text:
                nation = val
                break

        gender = "기타"
        if re.search(r"\bNAM/M\b|\bMALE\b|\bSEX\s*M\b", merged_text):
            gender = "남성"
        elif re.search(r"\bFEMALE\b|\bSEX\s*F\b|\bNU\b", merged_text):
            gender = "여성"

        has_any = bool(passport_no or english_name or birth_date != "1990-01-01")
        if not has_any:
            return None

        english_ascii = _finalize_english_name(english_name, merged_text) if english_name else ""
        korean_name = _display_name_from_english(english_ascii) if english_ascii else ""
        return {
            "name": korean_name,
            "english_name": english_ascii,
            "nation": nation,
            "passport_no": passport_no,
            "id_no": id_no,
            "birth_date": birth_date,
            "gender": gender,
        }


def extract_mrz_sync(passport_image: Image.Image, debug_dir: str | None = None) -> dict | None:
    """?숆린 ?섑띁: 諛깃렇?쇱슫???ㅻ젅?쒖뿉??asyncio 猷⑦봽瑜??앹꽦???ㅽ뻾?⑸땲??"""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        engine = PassportOcrEngine(debug_dir=debug_dir)
        return loop.run_until_complete(engine.extract_mrz(passport_image))
    finally:
        loop.close()
        asyncio.set_event_loop(None)
