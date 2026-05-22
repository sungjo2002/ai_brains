from __future__ import annotations

import re


def seed_monthly_records_from_events(
    monthly_records: dict[tuple[int, str], dict],
    attendance_events: list[dict],
    valid_statuses: list[str],
) -> bool:
    updated = False
    valid_status_set = {str(status).strip() for status in valid_statuses}
    for event in attendance_events:
        event_type = str(event.get("event_type") or "").strip()
        if event_type not in valid_status_set:
            continue
        try:
            employee_id = int(event.get("employee_id", 0) or 0)
        except (TypeError, ValueError):
            continue
        record_date = str(event.get("date") or "").strip()
        if employee_id <= 0 or not record_date:
            continue
        key = (employee_id, record_date)
        if key in monthly_records:
            continue
        monthly_records[key] = {
            "status": event_type,
            "memo": str(event.get("memo") or "").strip(),
        }
        updated = True
    return updated


def normalize_payroll_month_entry(entry: dict | None) -> dict:
    normalized = {
        "base": {},
        "over": {},
        "night": {},
        "cell_colors": {"base": {}, "over": {}, "night": {}},
        "imported_from_attendance": False,
    }
    for key in ("base", "over", "night"):
        source = entry.get(key, {}) if isinstance(entry, dict) else {}
        cleaned: dict[int, float] = {}
        if isinstance(source, dict):
            for day, value in source.items():
                try:
                    day_num = int(day)
                    amount = float(value or 0)
                except (TypeError, ValueError):
                    continue
                if day_num >= 1 and amount > 0:
                    cleaned[day_num] = amount
        normalized[key] = cleaned
    color_source = entry.get("cell_colors", {}) if isinstance(entry, dict) else {}
    if isinstance(color_source, dict):
        for key in ("base", "over", "night"):
            source = color_source.get(key, {}) or {}
            cleaned_colors: dict[int, str] = {}
            if isinstance(source, dict):
                for day, value in source.items():
                    try:
                        day_num = int(day)
                    except (TypeError, ValueError):
                        continue
                    color_text = str(value or "").strip()
                    if 1 <= day_num <= 31 and re.match(r"^#[0-9A-Fa-f]{6}$", color_text):
                        cleaned_colors[day_num] = color_text.upper()
            normalized["cell_colors"][key] = cleaned_colors
    normalized["imported_from_attendance"] = bool((entry or {}).get("imported_from_attendance"))
    return normalized
