from __future__ import annotations

import base64
from calendar import monthrange
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover
    Image = None
    ImageDraw = None
    ImageFont = None

COMMON_FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/malgun.ttf"),
    Path("C:/Windows/Fonts/malgunbd.ttf"),
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/mnt/data/HYKANM.TTF"),
]

SHEET_WIDTH = 1700
SHEET_HEIGHT = 1200


def _find_font_file() -> Path | None:
    for candidate in COMMON_FONT_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _safe_text(value: Any, fallback: str = "-") -> str:
    text = str(value or "").strip()
    return text or fallback


def _money(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    if abs(amount - int(amount)) < 1e-9:
        return f"{int(amount):,}원"
    return f"{amount:,.2f}".rstrip("0").rstrip(".") + "원"


def _hours(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    if abs(amount - int(amount)) < 1e-9:
        return f"{int(amount)}"
    return f"{amount:.2f}".rstrip("0").rstrip(".")


def _load_pil_font(size: int):
    if ImageFont is None:
        raise RuntimeError("Pillow 글꼴 기능을 사용할 수 없습니다.")
    font_path = _find_font_file()
    if font_path:
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except Exception:
            pass
    for name in ["malgun.ttf", "NanumGothic.ttf", "arial.ttf"]:
        try:
            return ImageFont.truetype(name, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _base_filename(month_key: str, employee_id: Any) -> str:
    month_part = str(month_key or "").replace("/", "-").replace(" ", "_")
    emp_part = str(employee_id or "employee").strip() or "employee"
    return f"payroll_slip_{month_part}_{emp_part}"


def _daily_rows(entry: dict, days_in_month: int) -> list[list[str]]:
    base_map = entry.get("base", {}) if isinstance(entry, dict) else {}
    over_map = entry.get("over", {}) if isinstance(entry, dict) else {}
    night_map = entry.get("night", {}) if isinstance(entry, dict) else {}
    rows = []
    for day in range(1, days_in_month + 1):
        base = float(base_map.get(day, 0) or 0)
        over = float(over_map.get(day, 0) or 0)
        night = float(night_map.get(day, 0) or 0)
        rows.append([
            f"{day:02d}",
            "" if base == 0 else _hours(base),
            "" if over == 0 else _hours(over),
            "" if night == 0 else _hours(night),
        ])
    return rows


def build_payroll_slip_payload(state, employee_id: int, month_key: str) -> dict:
    employee = state.get_employee_by_id(int(employee_id)) or {}
    detail = state.get_payroll_detail_payload(int(employee_id), month_key)
    entry = state.get_payroll_month_entry(int(employee_id), month_key)
    year, month = map(int, str(month_key).split("-"))
    days_in_month = monthrange(year, month)[1]
    summary_values = detail.get("summary_values", {})
    allowance_rows = [{"label": row.get("label", ""), "value": float(row.get("value", 0) or 0)} for row in detail.get("allowance", [])]
    deduction_rows = [{"label": row.get("label", ""), "value": float(row.get("value", 0) or 0)} for row in detail.get("deduction", [])]
    return {
        "employee_id": int(employee_id),
        "employee_name": _safe_text(employee.get("name")),
        "month_key": month_key,
        "display_title": "급여명세표",
        "days_in_month": days_in_month,
        "daily_rows": _daily_rows(entry, days_in_month),
        "allowance_rows": allowance_rows,
        "deduction_rows": deduction_rows,
        "summary_values": {
            "base_hours": float(summary_values.get("base_hours", 0) or 0),
            "over_hours": float(summary_values.get("over_hours", 0) or 0),
            "night_hours": float(summary_values.get("night_hours", 0) or 0),
            "total_hours": float(summary_values.get("total_hours", 0) or 0),
            "hourly_rate": float(summary_values.get("hourly_rate", 0) or 0),
            "base_amount": float(summary_values.get("base_amount", 0) or 0),
            "allowance_total": float(summary_values.get("allowance_total", 0) or 0),
            "gross_amount": float(summary_values.get("gross_amount", 0) or 0),
            "deduction_total": float(summary_values.get("deduction_total", 0) or 0),
            "net_amount": float(summary_values.get("net_amount", 0) or 0),
        },
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "default_filename": _base_filename(month_key, employee.get("id") or employee_id),
    }


def _draw_centered(draw, x1, x2, y, text, font, fill="#111827"):
    draw.text(((x1 + x2) / 2, y), str(text), font=font, fill=fill, anchor="ma")


def _draw_right(draw, x, y, text, font, fill="#111827"):
    draw.text((x, y), str(text), font=font, fill=fill, anchor="ra")


def _render_payroll_slip_image(payload: dict):
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow 라이브러리가 없어 명세표를 만들 수 없습니다.")

    image = Image.new("RGB", (SHEET_WIDTH, SHEET_HEIGHT), "white")
    draw = ImageDraw.Draw(image)

    title_font = _load_pil_font(40)
    name_font = _load_pil_font(30)
    section_font = _load_pil_font(22)
    header_font = _load_pil_font(18)
    body_font = _load_pil_font(16)
    small_font = _load_pil_font(14)
    strong_font = _load_pil_font(20)
    net_font = _load_pil_font(28)

    summary = payload.get("summary_values", {})
    allowance_rows = payload.get("allowance_rows", [])
    deduction_rows = payload.get("deduction_rows", [])

    margin_x = 34
    top = 24
    content_w = SHEET_WIDTH - margin_x * 2
    card_bg = "#F8FAFC"
    border = "#CBD5E1"
    title_color = "#0F172A"
    accent = "#0F766E"

    # title + name only
    _draw_centered(draw, margin_x, SHEET_WIDTH - margin_x, top + 4, payload.get("display_title", "급여명세표"), title_font, title_color)
    draw.rounded_rectangle((margin_x, top + 52, SHEET_WIDTH - margin_x, top + 102), radius=12, outline=border, width=2, fill=card_bg)
    draw.text((margin_x + 20, top + 66), f"성명  {payload.get('employee_name', '-')}", font=name_font, fill=title_color)

    y = top + 122

    def draw_day_block(block_rows: list[list[str]], block_title: str, y_pos: int) -> int:
        label_w = 58
        table_w = content_w
        cell_count = max(len(block_rows), 1)
        cell_w = (table_w - label_w) / cell_count
        row_h = 36
        section_h = row_h * 4 + 40
        draw.rounded_rectangle((margin_x, y_pos, margin_x + table_w, y_pos + section_h), radius=12, outline=border, width=2, fill="white")
        draw.text((margin_x + 14, y_pos + 10), block_title, font=section_font, fill=title_color)
        grid_top = y_pos + 40
        labels = ["날짜", "기본", "연장", "야간"]
        for ridx, label in enumerate(labels):
            y1 = grid_top + ridx * row_h
            y2 = y1 + row_h
            draw.rectangle((margin_x, y1, margin_x + label_w, y2), outline=border, width=1, fill=card_bg)
            _draw_centered(draw, margin_x, margin_x + label_w, y1 + 11, label, header_font, title_color)
            for cidx, row in enumerate(block_rows):
                x1 = margin_x + label_w + cidx * cell_w
                x2 = margin_x + label_w + (cidx + 1) * cell_w
                bg = "#FFF7ED" if ridx == 0 else "white"
                draw.rectangle((x1, y1, x2, y2), outline=border, width=1, fill=bg)
                value = row[0] if ridx == 0 else row[ridx]
                font = header_font if ridx == 0 else body_font
                fill = title_color if ridx == 0 else "#374151"
                _draw_centered(draw, x1, x2, y1 + 11, value, font, fill)
        return section_h

    daily_rows = payload.get("daily_rows", [])
    first_rows = daily_rows[:16]
    second_rows = daily_rows[16:]
    block_h = draw_day_block(first_rows, "1일 ~ 16일", y)
    y += block_h + 14
    if second_rows:
        y += draw_day_block(second_rows, "17일 ~ 31일", y) + 14

    # quick summary strip
    strip_h = 64
    strip_cells = [
        ("기본시간", _hours(summary.get("base_hours", 0)) + "H"),
        ("연장시간", _hours(summary.get("over_hours", 0)) + "H"),
        ("야간시간", _hours(summary.get("night_hours", 0)) + "H"),
        ("총시간", _hours(summary.get("total_hours", 0)) + "H"),
    ]
    gap = 10
    strip_w = (content_w - gap * 3) / 4
    for idx, (label, value) in enumerate(strip_cells):
        x1 = margin_x + idx * (strip_w + gap)
        x2 = x1 + strip_w
        draw.rounded_rectangle((x1, y, x2, y + strip_h), radius=12, outline=border, width=2, fill=card_bg)
        draw.text((x1 + 16, y + 12), label, font=small_font, fill="#475569")
        _draw_right(draw, x2 - 14, y + 14, value, strong_font, title_color)
    y += strip_h + 14

    # detail tables
    bottom_h = SHEET_HEIGHT - y - 104
    left_x1 = margin_x
    left_x2 = margin_x + (content_w - 12) / 2
    right_x1 = left_x2 + 12
    right_x2 = SHEET_WIDTH - margin_x
    table_y1 = y
    table_y2 = y + max(bottom_h, 220)

    def draw_money_table(x1: float, x2: float, title: str, rows: list[dict]):
        draw.rounded_rectangle((x1, table_y1, x2, table_y2), radius=12, outline=border, width=2, fill="white")
        draw.text((x1 + 12, table_y1 + 10), title, font=section_font, fill=title_color)
        inner_y = table_y1 + 44
        row_count = max(len(rows), 1)
        usable_h = table_y2 - inner_y - 10
        row_h = max(30, min(36, int(usable_h / row_count)))
        label_w = int((x2 - x1) * 0.63)
        for idx in range(row_count):
            row = rows[idx] if idx < len(rows) else {"label": "", "value": ""}
            y1 = inner_y + idx * row_h
            y2 = min(table_y2 - 10, y1 + row_h)
            draw.rectangle((x1 + 10, y1, x1 + 10 + label_w, y2), outline=border, width=1, fill=card_bg if idx % 2 == 0 else "white")
            draw.rectangle((x1 + 10 + label_w, y1, x2 - 10, y2), outline=border, width=1, fill="white")
            draw.text((x1 + 18, y1 + 8), _safe_text(row.get("label"), ""), font=body_font, fill=title_color)
            value = _money(row.get("value", 0)) if row.get("label") else ""
            _draw_right(draw, x2 - 18, y1 + 8, value, body_font, title_color)

    draw_money_table(left_x1, left_x2, "지급 항목", allowance_rows)
    draw_money_table(right_x1, right_x2, "공제 항목", deduction_rows)

    # bottom totals
    footer_y = SHEET_HEIGHT - 84
    draw.rounded_rectangle((margin_x, footer_y, SHEET_WIDTH - margin_x, SHEET_HEIGHT - 24), radius=14, outline=border, width=2, fill="#F8FAFC")
    draw.text((margin_x + 16, footer_y + 14), f"지급 합계  {_money(summary.get('gross_amount', 0))}", font=strong_font, fill=title_color)
    draw.text((margin_x + 500, footer_y + 14), f"공제 합계  {_money(summary.get('deduction_total', 0))}", font=strong_font, fill=title_color)
    _draw_right(draw, SHEET_WIDTH - margin_x - 20, footer_y + 10, f"실수령액  {_money(summary.get('net_amount', 0))}", net_font, accent)

    return image


def _render_payroll_slip_png_bytes(payload: dict) -> bytes:
    image = _render_payroll_slip_image(payload)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def build_payroll_slip_png_bytes(payload: dict) -> bytes:
    return _render_payroll_slip_png_bytes(payload)


def build_payroll_slip_html(payload: dict) -> str:
    png_bytes = build_payroll_slip_png_bytes(payload)
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return (
        "<html><head><meta charset='utf-8'></head>"
        "<body style='margin: 0; padding: 6px; background:#F3F4F6;'>"
        "<div style='text-align:center;'>"
        f"<img src='data:image/png;base64,{encoded}' style='width:100%; max-width:100%; height:auto; border:1px solid #D1D5DB; border-radius:12px; background:#fff;'/>"
        "</div></body></html>"
    )


def export_payroll_slip_image(payload: dict, output_path: str | Path, image_format: str = "PNG") -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image = _render_payroll_slip_image(payload)
    save_kwargs = {"format": image_format.upper()}
    if image_format.upper() in {"JPG", "JPEG"}:
        save_kwargs["quality"] = 85
        save_kwargs["optimize"] = True
    else:
        save_kwargs["optimize"] = True
    image.save(target, **save_kwargs)
    return target


