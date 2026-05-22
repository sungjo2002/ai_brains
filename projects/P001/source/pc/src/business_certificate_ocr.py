
from __future__ import annotations

import os
import re
import asyncio
from typing import Callable

import winrt.windows.media.ocr as ocr
import winrt.windows.globalization as glob
import winrt.windows.graphics.imaging as imaging
import winrt.windows.storage as storage

def get_ocr_engine_status() -> tuple[bool, str]:
    if ocr.OcrEngine.is_language_supported(glob.Language("ko-KR")):
        return True, "자동 인식 준비됨 (Windows 내장)"
    return False, "Windows 한글 언어 팩이 확인되지 않으나 프로파일로 시도 가능합니다."

async def _extract_text_async(image_path: str) -> str:
    abs_path = os.path.abspath(image_path).replace('/', '\\')
    file = await storage.StorageFile.get_file_from_path_async(abs_path)
    stream = await file.open_async(storage.FileAccessMode.READ)
    decoder = await imaging.BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    
    lang = glob.Language("ko-KR")
    engine = ocr.OcrEngine.try_create_from_language(lang)
    if not engine:
        engine = ocr.OcrEngine.try_create_from_user_profile_languages()
        
    result = await engine.recognize_async(bitmap)
    
    all_words = []
    for line in result.lines:
        for word in line.words:
            rect = word.bounding_rect
            cy = rect.y + (rect.height / 2.0)
            all_words.append({
                "text": word.text,
                "x": rect.x,
                "y": rect.y,
                "cy": cy,
                "h": rect.height,
                "w": rect.width
            })
            
    if not all_words:
        return ""
        
    all_words.sort(key=lambda w: w["cy"])
    
    lines = []
    current_line = []
    
    for w in all_words:
        if not current_line:
            current_line.append(w)
            continue
            
        avg_cy = sum(cw["cy"] for cw in current_line) / len(current_line)
        avg_h = sum(cw["h"] for cw in current_line) / len(current_line)
        
        if abs(w["cy"] - avg_cy) < (avg_h * 0.6):
            current_line.append(w)
        else:
            lines.append(current_line)
            current_line = [w]
            
    if current_line:
        lines.append(current_line)
        
    text_lines = []
    for line_words in lines:
        line_words.sort(key=lambda w: w["x"])
        line_str = ""
        for i, w in enumerate(line_words):
            if i > 0:
                prev_w = line_words[i-1]
                gap = w["x"] - (prev_w["x"] + prev_w["w"])
                avg_h = (w["h"] + prev_w["h"]) / 2.0
                if gap > avg_h * 1.5:
                    line_str += "\t"
                else:
                    line_str += " "
            line_str += w["text"]
        text_lines.append(line_str)
        
    return "\n".join(text_lines)


_LABEL_FIXES: list[tuple[str, str]] = [
    (r"등\s*록\s*(?:번|변)\s*호", "등록번호"),
    (r"상\s*호(?:\s*\([^)]*\))?", "상호"),
    (r"법\s*인\s*명(?:\s*\([^)]*\))?", "법인명"),
    (r"단\s*체\s*명(?:\s*\([^)]*\))?", "단체명"),
    (r"성\s*명(?:\s*\([^)]*\))?", "성명"),
    (r"대\s*표\s*자(?:\s*\([^)]*\))?", "대표자"),
    (r"생\s*년\s*월\s*일", "생년월일"),
    (r"개\s*업\s*연\s*월\s*일", "개업연월일"),
    (r"업\s*태", "업태"),
    (r"종\s*목", "종목"),
    (r"사\s*업\s*장\s*소\s*재\s*지", "사업장소재지"),
    (r"사\s*업\s*의\s*종\s*류", "사업의종류"),
    (r"발\s*급\s*사\s*유", "발급사유"),
    (r"공\s*동\s*사\s*업\s*자", "공동사업자"),
    (r"사업자\s*단위\s*과세\s*적용사업자\s*여부", "사업자단위과세적용사업자여부"),
    (r"전자세금계산서\s*전용\s*전자우편주소", "전자세금계산서전용전자우편주소"),
]


def _normalize_text(text: str) -> str:
    normalized = text.replace("：", ":").replace("·", ".").replace("—", "-").replace("–", "-")
    normalized = normalized.replace("㈜", "(주)")
    normalized = re.sub(r"[ ]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    for pattern, replacement in _LABEL_FIXES:
        normalized = re.sub(pattern, replacement, normalized)
    return normalized


def _normalize_business_number(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return value.strip()


def _clean_value(value: str) -> str:
    value = value.strip(" :\n\t[]•.")
    value = re.sub(r"\s{2,}", " ", value)
    value = value.rstrip("[")
    return value.strip()




def _date_key(value: str) -> tuple[int, int, int]:
    match = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", value)
    if not match:
        return (0, 0, 0)
    return int(match.group(1)), int(match.group(2)), int(match.group(3))

def _format_date_parts(year: str, month: str, day: str) -> str:
    return f"{int(year):04d}년 {int(month):02d}월 {int(day):02d}일"


def _extract_dates(text: str) -> list[str]:
    matches = re.findall(r"((?:19|20)\d{2})[^\d\n]{1,10}(\d{1,2})[^\d\n]{1,10}(\d{1,2})", text)
    dates: list[str] = []
    for year, month, day in matches:
        try:
            month_int = int(month)
            day_int = int(day)
            if not (1 <= month_int <= 12 and 1 <= day_int <= 31):
                continue
            dates.append(_format_date_parts(year, month, day))
        except ValueError:
            continue
    unique: list[str] = []
    for value in dates:
        if value not in unique:
            unique.append(value)
    return unique

def _extract_first(patterns: list[str], text: str, *, flags: int = re.IGNORECASE | re.MULTILINE | re.DOTALL) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            value = match.group(1)
            return _clean_value(value)
    return ""


def _between(text: str, start_labels: list[str], end_labels: list[str]) -> str:
    start = -1
    start_end = -1
    for label in start_labels:
        match = re.search(label, text, re.IGNORECASE)
        if match:
            start = match.start()
            start_end = match.end()
            break
    if start_end < 0:
        return ""

    end = len(text)
    for label in end_labels:
        match = re.search(label, text[start_end:], re.IGNORECASE)
        if match:
            pos = start_end + match.start()
            if pos < end:
                end = pos
    return _clean_value(text[start_end:end])


def _split_business_type_block(block: str) -> tuple[str, str]:
    if not block:
        return "", ""

    # 전화번호/팩스 등 컨택 관련 불순물 일괄 제거
    block = re.sub(r"(?i)(?:tel|fax|email).*$", "", block, flags=re.MULTILINE|re.DOTALL)
    block = _normalize_text(block)
    
    lines = [_clean_value(line) for line in block.splitlines() if _clean_value(line)]
    if not lines:
        return "", ""

    business_types: list[str] = []
    business_items: list[str] = []

    for line in lines:
        line = re.sub(r"^사업의종류\s*:\s*", "", line)
        line = re.sub(r"^사업의종류\s+", "", line)
        
        if "업태" in line or "종목" in line:
            left_match = re.search(r"업태\]?\s*(.*?)\s*종목\]?\s*(.*)$", line)
            if left_match:
                business_types.append(left_match.group(1).strip())
                business_items.append(left_match.group(2).strip())
            else:
                if "종목" in line:
                    parts = re.split(r"종목\]?\s*", line)
                    if len(parts) > 1:
                        business_items.append(parts[1].strip())
                        if parts[0].replace("업태", "").strip():
                            business_types.append(parts[0].replace("업태", "").strip())
                else:
                    business_types.append(line.replace("업태", "").strip())
        else:
            if "\t" in line:
                parts = line.split("\t", 1)
                business_types.append(parts[0].strip())
                business_items.append(parts[1].strip())
            else:
                business_types.append(line.strip())

    def join_parts(parts: list[str]) -> str:
        values: list[str] = []
        for part in parts:
            if part and part not in values:
                values.append(part)
        return ", ".join(values)

    return join_parts(business_types), join_parts(business_items)


def _prepare_variants(image: Image.Image) -> list[Image.Image]:
    base = ImageOps.exif_transpose(image).convert("L")
    variants = [
        ImageOps.autocontrast(base),
        ImageOps.autocontrast(base).filter(ImageFilter.SHARPEN),
    ]

    resized = ImageOps.autocontrast(base).resize((base.width * 2, base.height * 2))
    variants.append(resized)

    threshold = ImageOps.autocontrast(base)
    threshold = threshold.point(lambda x: 255 if x > 170 else 0, mode="1").convert("L")
    variants.append(threshold)

    strong = ImageEnhance.Contrast(ImageOps.autocontrast(base)).enhance(1.8)
    variants.append(strong)

    return variants


def _score_result(text: str, result: dict) -> int:
    compact = re.sub(r"\s+", "", text)
    score = 0
    for token in ["등록번호", "상호", "성명", "개업연월일", "사업장소재지", "사업의종류"]:
        if token in compact:
            score += 1
    for field in ["business_number", "name", "representative_name", "opening_date", "address"]:
        if result.get(field):
            score += 2
    for field in ["business_type", "business_item", "issue_date"]:
        if result.get(field):
            score += 1
    return score


def _parse_from_text(text: str) -> dict:
    normalized = _normalize_text(text)

    number = _extract_first(
        [
            r"등록번호\s*:\s*([0-9OIl\- ]{10,})",
            r"등록번호\s*([0-9OIl\- ]{10,})",
            r"([0-9OIl]{3}\s*-\s*[0-9OIl]{2}\s*-\s*[0-9OIl]{5})",
        ],
        normalized,
    )
    number = number.replace("O", "0").replace("I", "1").replace("l", "1")
    number = _normalize_business_number(number)

    name = _extract_first(
        [
            r"(?:상\s*호|법\s*인\s*명|단\s*체\s*명)(?:\s*\([^)]*\))?\s*:\s*(.+?)(?:\n|성명|대\s*표|생년|$)",
            r"(?:상\s*호|법\s*인\s*명|단\s*체\s*명)(?:\s*\([^)]*\))?\s+(.+?)(?:\n|성명|대\s*표|생년|$)",
        ],
        normalized,
    )
    representative = _extract_first(
        [
            r"(?:성\s*명|대\s*표\s*자)(?:\s*\([^)]*\))?\s*[:\|.]?\s*([가-힣A-Za-z\s]+)(?:\n|생년|법인|$)",
            r"(?:성\s*명|명|대\s*표\s*자)[^\n]*?(?:[:\|.]?\s*)([가-힣]{2,5})(?:\s+생년월일|\n)",
            r"([가-힣]{2,5})\s+생년월일",
        ],
        normalized,
    )
    
    dates = _extract_dates(normalized)
    opening_date = _extract_first([
        r"개업연월일[^\d\n]*((?:19|20)\d{2}[^\d\n]{1,10}\d{1,2}[^\d\n]{1,10}\d{1,2})",
        r"개업일[^\d\n]*((?:19|20)\d{2}[^\d\n]{1,10}\d{1,2}[^\d\n]{1,10}\d{1,2})"
    ], normalized)
    
    if opening_date:
        opening_matches = _extract_dates(opening_date)
        opening_date = opening_matches[0] if opening_matches else opening_date
    elif dates:
        sorted_dates = sorted(dates, key=_date_key)
        opening_date = sorted_dates[1] if len(sorted_dates) > 1 else sorted_dates[0]

    address = _extract_first(
        [
            r"사업장소재지\s*:\s*(.+?)(?:\n|사업의종류|발급사유|$)",
            r"사업장소재지\s+(.+?)(?:\n|사업의종류|발급사유|$)",
        ],
        normalized,
    )
    issue_date = _extract_first([r"(\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일)\s*경"], normalized)
    if not issue_date and dates:
        opening_key = _date_key(opening_date) if opening_date else (0, 0, 0)
        candidates = [value for value in dates if _date_key(value) > opening_key]
        if candidates:
            issue_date = candidates[-1]

    business_type_block = _between(
        normalized,
        [r"사업의종류\s*:\s*", r"사업의종류\s+"],
        [r"(?i)tel", r"(?i)fax", r"(?i)email", r"발\s*급\s*사", r"공\s*동\s*사", r"사업자\s*단위"],
    )
    business_type, business_item = _split_business_type_block(business_type_block)
    
    email = _extract_first([r"(?i)e-?mai[lI\|1]\s*[:;]?\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"], normalized)

    # if not number and not name:
    #     raise RuntimeError("자동 인식에 실패했습니다. 더 선명한 등록증 이미지를 사용해 주세요.")
    return {
        "business_number": number,
        "name": name,
        "representative_name": representative,
        "opening_date": opening_date,
        "address": address,
        "business_type": business_type,
        "business_item": business_item,
        "issue_date": issue_date,
        "email": email,
        "raw_text": normalized.strip(),
    }


def _do_ocr_sync(image_path: str) -> str:
    return asyncio.run(_extract_text_async(image_path))

def extract_business_registration(image_path: str, progress_callback: Callable[[str], None] | None = None) -> dict:
    if not os.path.exists(image_path):
        raise RuntimeError("등록증 파일을 찾을 수 없습니다.")

    if progress_callback:
        progress_callback("Windows 내장 엔진으로 텍스트를 추출하고 있습니다.")

    try:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(1) as executor:
            text = executor.submit(_do_ocr_sync, image_path).result()
    except Exception as exc:
        raise RuntimeError(f"OCR 실행 중 오류가 발생했습니다: {exc}") from exc

    if progress_callback:
        progress_callback("추출된 텍스트를 분석하고 있습니다.")

    result = _parse_from_text(text)

    if not any(result.get(key) for key in ["business_number", "name", "address"]):
        raise RuntimeError("자동 인식에 실패했습니다. 더 선명한 등록증 이미지를 사용해 주세요.")

    if progress_callback:
        progress_callback("자동 인식이 완료되었습니다.")

    return result
