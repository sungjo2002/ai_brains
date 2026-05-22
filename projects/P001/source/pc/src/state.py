from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from calendar import monthrange
import math
import re
import shutil
from urllib.error import HTTPError

from PySide6.QtCore import QObject, QTimer, Signal

from .database import DatabaseManager
from .state_batch_helpers import normalize_payroll_month_entry, seed_monthly_records_from_events
from .storage_manager import StorageManager
from .background_workers import FunctionWorkerThread
from .holiday_manager import (
    load_holiday_api_settings,
    save_holiday_api_settings,
    sync_holidays_from_api,
    mark_holiday_sync_error,
)
from .server_api import (
    check_health,
    close_attendance_month_remote,
    create_employee_remote,
    delete_employee_remote,
    download_media_file,
    fetch_app_snapshot,
    fetch_attendance_month_remote,
    fetch_employees,
    fetch_vehicle_logs_remote,
    delete_vehicle_cost_log_remote,
    delete_vehicle_fuel_log_remote,
    delete_vehicle_run_log_remote,
    push_app_snapshot,
    reopen_attendance_month_remote,
    save_vehicle_cost_log_remote,
    save_vehicle_fuel_log_remote,
    save_vehicle_run_log_remote,
    upload_employee_media,
    update_employee_remote,
)
from .app_metadata import APP_SETTINGS_NAME, STORAGE_VERSION
from .defaults import (
    ATTENDANCE_SCORE_SETTINGS,
    REJOIN_GRADES,
    VEHICLE_ALERT_SETTINGS,
)


def _clear_holiday_cache() -> None:
    from .attendance_page import clear_holiday_cache

    clear_holiday_cache()

STATUS_TYPES = ["근무중", "출근전", "퇴근", "지각", "병원", "결근", "무단결근", "무단이탈", "휴무", "퇴사"]


SERVER_ATTENDANCE_STATE_TO_STATUS = {
    "": "",
    "empty": "",
    "present": "출석",
    "workday_overtime": "출석",
    "special_work": "출석",
    "absent": "결근",
    "hospital": "병원",
    "late": "지각",
    "early": "조퇴",
    "off": "휴무",
    "unauthorized_absent": "무단결근",
    "unauthorized_leave": "무단이탈",
    "출석": "출석",
    "결근": "결근",
    "병원": "병원",
    "지각": "지각",
    "조퇴": "조퇴",
    "휴무": "휴무",
    "무단결근": "무단결근",
    "무단이탈": "무단이탈",
}


def _normalize_remote_attendance_text(value) -> str:
    return str(value or "").strip()


def _normalize_remote_attendance_key(value) -> str:
    # 서버/PC 값의 공백, 괄호, 구분기호 차이를 줄여 근로자 매칭 정확도를 높인다.
    text = _normalize_remote_attendance_text(value)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[\-_/\.\(\)\[\]{}]", "", text)
    return text.lower()


def _remote_attendance_state_to_status(value) -> str:
    text = _normalize_remote_attendance_text(value)
    return SERVER_ATTENDANCE_STATE_TO_STATUS.get(text, text)
EVENT_TYPES = ["무단결근", "무단이탈", "지각", "조퇴", "병원", "경고"]

MAX_VEHICLE_ODOMETER = 9_999_999
MAX_VEHICLE_FUEL_AMOUNT = 10_000_000
MAX_VEHICLE_COST_AMOUNT = 50_000_000
MAX_ANNUAL_LIMIT_KM = 1_000_000

DEFAULT_PAYROLL_PRESET_NAME = "기본값 1"
GLOBAL_PAYROLL_SETTING_PRESET_KEY = "__global_payroll_setting_presets__"
DEFAULT_AUTOSAVE_MINUTES = 10
MIN_AUTOSAVE_MINUTES = 1
MAX_AUTOSAVE_MINUTES = 720
MAX_SERVER_SYNC_RETRY = 3
SERVER_SNAPSHOT_PUSH_DELAY_MS = 2500
SERVER_SNAPSHOT_PULL_INTERVAL_MS = 10 * 60 * 1000
SERVER_SNAPSHOT_SKIP_PUSH_REASONS = {"initial-load", "server-sync", "server-snapshot-pull", "server-snapshot-push"}
SERVER_DICT_ITEMS_MARKER = "__workforce_dict_items__"
SERVER_TUPLE_MARKER = "__workforce_tuple__"

# 배포 전 테스트 자료 정리 기준
# 정확히 확인된 샘플/테스트 값만 제거해서 실제 운영 자료가 지워지지 않게 합니다.
TEST_BUSINESS_NAMES_TO_REMOVE = {"테스트사업자"}
TEST_WORK_SITE_NAMES_TO_REMOVE = {"테스트현장"}
TEST_EMPLOYEE_IDS_TO_REMOVE = {1777013596, 1777015713}
TEST_EMPLOYEE_NAMES_TO_REMOVE = {"wqr", "aa", "bbb", "11111"}
TEST_PAYROLL_SITE_KEYS_TO_REMOVE = {"테스트사업자::테스트현장", "B::S"}

DIRTY_SECTION_ALL = {"core_people", "attendance", "records", "payroll", "vehicles", "settings"}
DIRTY_SIGNAL_SECTION_MAP = {
    "employees": {"core_people", "attendance", "records", "payroll"},
    "attendance": {"attendance"},
    "settings": {"settings", "payroll", "vehicles"},
    "payroll": {"payroll"},
    "records": {"records"},
    "vehicles": {"vehicles"},
}

ATTENDANCE_STATUS_SCORE_RULES = {
    "출석": 0,
    "휴무": 0,
    "병원": -1,
    "지각": -1,
    "조퇴": -1,
    "결근": -3,
    "무단결근": -8,
    "무단이탈": -10,
}

DEFAULT_PAYROLL_DETAIL_ITEMS = [
    {"enabled": True, "group": "summary", "label": "총시간", "key": "total_hours", "input_mode": "readonly", "location": "both", "default_value": 0, "order": 1},
    {"enabled": True, "group": "summary", "label": "시급", "key": "hourly_rate", "input_mode": "manual", "location": "both", "default_value": 10320, "order": 2},
    {"enabled": True, "group": "summary", "label": "합계", "key": "base_amount", "input_mode": "readonly", "location": "both", "default_value": 0, "order": 3},
    {"enabled": True, "group": "summary", "label": "수당", "key": "allowance_total", "input_mode": "readonly", "location": "both", "default_value": 0, "order": 4},
    {"enabled": True, "group": "summary", "label": "총금액", "key": "gross_amount", "input_mode": "readonly", "location": "both", "default_value": 0, "order": 5},
    {"enabled": True, "group": "summary", "label": "공제", "key": "deduction_total", "input_mode": "readonly", "location": "both", "default_value": 0, "order": 6},
    {"enabled": True, "group": "summary", "label": "실수령액", "key": "net_amount", "input_mode": "readonly", "location": "both", "default_value": 0, "order": 7},
    {"enabled": True, "group": "allowance", "label": "연차수당", "key": "annual_allowance", "input_mode": "manual", "location": "both", "default_value": 0, "order": 10},
    {"enabled": True, "group": "allowance", "label": "유류대지원", "key": "fuel_support", "input_mode": "manual", "location": "both", "default_value": 0, "order": 11},
    {"enabled": True, "group": "deduction", "label": "국민연금", "key": "national_pension", "input_mode": "manual", "location": "both", "default_value": 0, "order": 20},
    {"enabled": True, "group": "deduction", "label": "건강보험", "key": "health_insurance", "input_mode": "manual", "location": "both", "default_value": 0, "order": 21},
    {"enabled": True, "group": "deduction", "label": "장기요양", "key": "long_term_care", "input_mode": "manual", "location": "both", "default_value": 0, "order": 22},
    {"enabled": True, "group": "deduction", "label": "고용보험", "key": "employment_insurance", "input_mode": "manual", "location": "both", "default_value": 0, "order": 23},
    {"enabled": True, "group": "deduction", "label": "갑근세", "key": "income_tax", "input_mode": "manual", "location": "both", "default_value": 0, "order": 24},
    {"enabled": True, "group": "deduction", "label": "주민세", "key": "resident_tax", "input_mode": "manual", "location": "both", "default_value": 0, "order": 25},
    {"enabled": True, "group": "deduction", "label": "식대공제", "key": "meal_deduction", "input_mode": "manual", "location": "both", "default_value": 31500, "order": 26},
]


def _normalize_payroll_detail_item(row: dict | None, fallback_order: int) -> dict:
    row = deepcopy(row or {})
    group = str(row.get("group", "summary") or "summary").strip() or "summary"
    if group not in {"summary", "allowance", "deduction"}:
        group = "summary"
    key = str(row.get("key", "") or "").strip()
    if not key:
        key = f"item_{fallback_order}"
    input_mode = str(row.get("input_mode", "manual") or "manual").strip() or "manual"
    if input_mode not in {"readonly", "manual"}:
        input_mode = "manual"
    location = str(row.get("location", "both") or "both").strip() or "both"
    if location not in {"detail", "slip", "both"}:
        location = "both"
    try:
        default_value = float(row.get("default_value", 0) or 0)
    except (TypeError, ValueError):
        default_value = 0.0
    try:
        order = int(row.get("order", fallback_order) or fallback_order)
    except (TypeError, ValueError):
        order = fallback_order
    label = str(row.get("label", key) or key).strip() or key
    return {
        "enabled": bool(row.get("enabled", True)),
        "group": group,
        "label": label,
        "key": key,
        "input_mode": input_mode,
        "location": location,
        "default_value": default_value,
        "order": order,
    }


def _grade_from_score(score: int, grades: list[tuple[int, str]]) -> str:
    for minimum, name in sorted(grades, key=lambda item: item[0], reverse=True):
        if score >= minimum:
            return name
    return grades[-1][1] if grades else "-"


def _normalize_business_name(value: str | None) -> str:
    name = str(value or "").strip()
    return name or "미지정 사업자"


def _normalize_work_site_name(value: str | None) -> str:
    name = str(value or "").strip()
    return name or "미지정 근무 사업장"


def _make_work_site_setting_key(work_site_name: str | None, business_name: str | None = None) -> str:
    site = _normalize_work_site_name(work_site_name)
    biz = _normalize_business_name(business_name) if business_name is not None else ""
    return f"{biz}::{site}" if biz else site


def _split_work_site_setting_key(key: str | None) -> tuple[str, str]:
    raw = str(key or "").strip()
    if "::" in raw:
        business_name, work_site_name = raw.split("::", 1)
        return _normalize_business_name(business_name), _normalize_work_site_name(work_site_name)
    return "", _normalize_work_site_name(raw)


def _global_payroll_setting_preset_scope_key() -> str:
    return GLOBAL_PAYROLL_SETTING_PRESET_KEY


def _normalize_site_time_conversion_rule(row: dict | None, fallback_order: int = 1) -> dict:
    row = row or {}

    def _text(key: str, default: str = "") -> str:
        return str(row.get(key, default) or "").strip()

    def _number(key: str) -> float:
        raw = row.get(key, "")
        if raw in (None, ""):
            return 0.0
        try:
            return float(str(raw).replace(",", "").strip() or 0)
        except (TypeError, ValueError):
            return 0.0

    business_name = _text("business_name")
    work_site_name = _text("work_site_name") or _text("site_name") or _text("site")
    area_name = _text("area_name") or _text("region") or _text("sub_site")
    conversion_type = _text("conversion_type", "시간대별") or "시간대별"
    day_type = _text("day_type")
    shift_type = _text("shift_type")
    value_type = _text("value_type", "실제시간") or "실제시간"
    return {
        "order": int(_number("order") or fallback_order),
        "business_name": business_name,
        "work_site_name": work_site_name,
        "area_name": area_name,
        "conversion_type": conversion_type,
        "day_type": day_type,
        "shift_type": shift_type,
        "start_time": _text("start_time"),
        "end_time": _text("end_time"),
        "day_number": _text("day_number"),
        "base_hours": _number("base_hours"),
        "over_hours": _number("over_hours"),
        "night_hours": _number("night_hours"),
        "special_hours": _number("special_hours"),
        "special_over_hours": _number("special_over_hours"),
        "holiday_special_hours": _number("holiday_special_hours"),
        "weekly_holiday_hours": _number("weekly_holiday_hours"),
        "value_type": value_type,
        "memo": _text("memo"),
    }


def _normalize_named_settings_presets(bundle: dict | None, default_payload: dict) -> dict:
    bundle = deepcopy(bundle or {})
    presets_raw = bundle.get("presets") if isinstance(bundle.get("presets"), dict) else {}
    presets: dict[str, dict] = {}
    for name, payload in presets_raw.items():
        preset_name = str(name or "").strip()
        if preset_name:
            presets[preset_name] = deepcopy(payload if isinstance(payload, dict) else default_payload)
    if not presets:
        presets[DEFAULT_PAYROLL_PRESET_NAME] = deepcopy(default_payload)
    active_name = str(bundle.get("active_preset", "") or "").strip()
    if active_name not in presets:
        active_name = next(iter(presets.keys()))
    return {"active_preset": active_name, "presets": presets}


def _normalize_named_item_presets(bundle: dict | None, default_rows: list[dict]) -> dict:
    bundle = deepcopy(bundle or {})
    presets_raw = bundle.get("presets") if isinstance(bundle.get("presets"), dict) else {}
    presets: dict[str, list[dict]] = {}
    for name, payload in presets_raw.items():
        preset_name = str(name or "").strip()
        if not preset_name:
            continue
        rows = payload if isinstance(payload, list) else default_rows
        presets[preset_name] = [_normalize_payroll_detail_item(row, idx + 1) for idx, row in enumerate(rows or default_rows)]
    if not presets:
        presets[DEFAULT_PAYROLL_PRESET_NAME] = [_normalize_payroll_detail_item(row, idx + 1) for idx, row in enumerate(default_rows)]
    active_name = str(bundle.get("active_preset", "") or "").strip()
    if active_name not in presets:
        active_name = next(iter(presets.keys()))
    return {"active_preset": active_name, "presets": presets}


def _clean_text(value) -> str:
    return str(value or "").strip()


def _normalize_date_string(value, fallback: str | None = None) -> str:
    raw = str(value or "").strip()
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
        except Exception:
            pass
    if fallback:
        try:
            return datetime.strptime(str(fallback), "%Y-%m-%d").date().isoformat()
        except Exception:
            pass
    return date.today().isoformat()


def _normalize_work_history(
    history: list[dict] | None,
    fallback_work_site: str,
    fallback_hire_date: str | None = None,
    fallback_status: str | None = None,
    fallback_business: str | None = None,
    fallback_work_type: str | None = None,
) -> list[dict]:
    default_start = _normalize_date_string(fallback_hire_date, date.today().isoformat())
    raw_entries = history if isinstance(history, list) else []
    entries: list[dict] = []

    for row in raw_entries:
        if not isinstance(row, dict):
            continue
        start_date = _normalize_date_string(row.get("start_date") or row.get("date") or default_start, default_start)
        raw_end_date = str(row.get("end_date") or "").strip()
        end_date = ""
        if raw_end_date:
            try:
                end_date = datetime.strptime(raw_end_date, "%Y-%m-%d").date().isoformat()
            except Exception:
                end_date = ""
        work_site = str(row.get("work_site") or row.get("site_name") or fallback_work_site or "-").strip() or "-"
        business = str(row.get("business") or row.get("affiliated_business") or fallback_business or "").strip()
        work_type = str(row.get("work_type") or fallback_work_type or "").strip()
        status = str(row.get("status") or fallback_status or "근무중").strip() or "근무중"
        reason = str(row.get("reason") or row.get("status_reason") or "").strip()
        note = str(row.get("note") or row.get("memo") or "").strip()
        entries.append({
            "start_date": start_date,
            "end_date": end_date,
            "business": business,
            "work_site": work_site,
            "work_type": work_type,
            "status": status,
            "reason": reason,
            "note": note,
            "active": not bool(end_date),
        })

    if not entries:
        entries.append({
            "start_date": default_start,
            "end_date": "" if str(fallback_status or "").strip() != "퇴사" else default_start,
            "business": str(fallback_business or "").strip(),
            "work_site": str(fallback_work_site or "-").strip() or "-",
            "work_type": str(fallback_work_type or "").strip(),
            "status": str(fallback_status or "근무중").strip() or "근무중",
            "reason": "",
            "note": "",
            "active": str(fallback_status or "").strip() != "퇴사",
        })

    entries.sort(key=lambda row: (row.get("start_date") or "", row.get("end_date") or "9999-12-31"))
    for idx, row in enumerate(entries):
        row["active"] = not bool(row.get("end_date")) and idx == len(entries) - 1
    return entries


def _encode_server_value(value):
    if isinstance(value, tuple):
        return {SERVER_TUPLE_MARKER: [_encode_server_value(item) for item in value]}
    if isinstance(value, list):
        return [_encode_server_value(item) for item in value]
    if isinstance(value, dict):
        return {
            SERVER_DICT_ITEMS_MARKER: [
                [_encode_server_value(key), _encode_server_value(item)]
                for key, item in value.items()
            ]
        }
    return value


def _decode_server_value(value):
    if isinstance(value, list):
        return [_decode_server_value(item) for item in value]
    if isinstance(value, dict):
        if set(value.keys()) == {SERVER_TUPLE_MARKER}:
            return tuple(_decode_server_value(item) for item in value.get(SERVER_TUPLE_MARKER, []))
        if set(value.keys()) == {SERVER_DICT_ITEMS_MARKER}:
            decoded: dict = {}
            for item in value.get(SERVER_DICT_ITEMS_MARKER, []):
                if not isinstance(item, list) or len(item) != 2:
                    continue
                decoded[_decode_server_value(item[0])] = _decode_server_value(item[1])
            return decoded
        return {str(key): _decode_server_value(item) for key, item in value.items()}
    return value


def build_business_original_form(record: dict | None) -> dict:
    record = deepcopy(record or {})
    return {
        "name": _normalize_business_name(record.get("name")),
        "business_number": _clean_text(record.get("business_number")),
        "representative_name": _clean_text(record.get("representative_name")),
        "manager_name": _clean_text(record.get("manager_name")),
        "phone": _clean_text(record.get("phone")),
        "email": _clean_text(record.get("email")),
        "address": _clean_text(record.get("address")),
        "opening_date": _clean_text(record.get("opening_date")),
        "business_type": _clean_text(record.get("business_type")),
        "business_item": _clean_text(record.get("business_item")),
        "issue_date": _clean_text(record.get("issue_date")),
        "active": bool(record.get("active", True)),
        "note": _clean_text(record.get("note")),
        "certificate_path": _clean_text(record.get("certificate_path")),
    }


def build_work_site_original_form(record: dict | None) -> dict:
    record = deepcopy(record or {})
    return {
        "business_name": _normalize_business_name(record.get("business_name") or record.get("affiliated_business")),
        "name": _normalize_work_site_name(record.get("name") or record.get("work_site") or record.get("company")),
        "business_number": _clean_text(record.get("business_number")),
        "representative_name": _clean_text(record.get("representative_name")),
        "manager_name": _clean_text(record.get("manager_name")),
        "phone": _clean_text(record.get("phone")),
        "email": _clean_text(record.get("email")),
        "address": _clean_text(record.get("address")),
        "opening_date": _clean_text(record.get("opening_date")),
        "business_type": _clean_text(record.get("business_type")),
        "business_item": _clean_text(record.get("business_item")),
        "issue_date": _clean_text(record.get("issue_date")),
        "site_code": _clean_text(record.get("site_code")),
        "default_work_type": _clean_text(record.get("default_work_type")),
        "active": bool(record.get("active", True)),
        "note": _clean_text(record.get("note")),
        "certificate_path": _clean_text(record.get("certificate_path")),
    }


def normalize_business_record(record: dict | None) -> dict:
    record = deepcopy(record or {})
    original_form = build_business_original_form(record)
    parsed = deepcopy(record.get("ocr_parsed_data", {})) if isinstance(record.get("ocr_parsed_data"), dict) else {}
    return {
        "business_id": _clean_text(record.get("business_id")),
        "record_type": "business",
        "name": original_form["name"],
        "business_number": original_form["business_number"],
        "representative_name": original_form["representative_name"],
        "manager_name": original_form["manager_name"],
        "phone": original_form["phone"],
        "email": original_form["email"],
        "address": original_form["address"],
        "opening_date": original_form["opening_date"],
        "business_type": original_form["business_type"],
        "business_item": original_form["business_item"],
        "issue_date": original_form["issue_date"],
        "active": original_form["active"],
        "note": original_form["note"],
        "certificate_path": original_form["certificate_path"],
        "ocr_raw_text": _clean_text(record.get("ocr_raw_text")),
        "ocr_parsed_data": parsed,
        "original_form": original_form,
    }



def normalize_work_site_record(record: dict | None) -> dict:
    record = deepcopy(record or {})
    original_form = build_work_site_original_form(record)
    parsed = deepcopy(record.get("ocr_parsed_data", {})) if isinstance(record.get("ocr_parsed_data"), dict) else {}
    return {
        "work_site_id": _clean_text(record.get("work_site_id")),
        "record_type": "work_site",
        "parent_business_id": _clean_text(record.get("parent_business_id")),
        "business_name": original_form["business_name"],
        "name": original_form["name"],
        "business_number": original_form["business_number"],
        "representative_name": original_form["representative_name"],
        "manager_name": original_form["manager_name"],
        "phone": original_form["phone"],
        "email": original_form["email"],
        "address": original_form["address"],
        "opening_date": original_form["opening_date"],
        "business_type": original_form["business_type"],
        "business_item": original_form["business_item"],
        "issue_date": original_form["issue_date"],
        "site_code": original_form.get("site_code", ""),
        "default_work_type": original_form.get("default_work_type", ""),
        "active": original_form["active"],
        "note": original_form["note"],
        "certificate_path": original_form["certificate_path"],
        "ocr_raw_text": _clean_text(record.get("ocr_raw_text")),
        "ocr_parsed_data": parsed,
        "original_form": original_form,
    }


def normalize_employee(
    employee: dict,
    score_settings: dict[str, int] | None = None,
    rejoin_grades: list[tuple[int, str]] | None = None,
) -> dict:
    score_settings = score_settings or deepcopy(ATTENDANCE_SCORE_SETTINGS)
    rejoin_grades = rejoin_grades or deepcopy(REJOIN_GRADES)

    normalized = deepcopy(employee)
    status = str(normalized.get("status", "출근전")).strip() or "출근전"
    if status not in STATUS_TYPES:
        status = "출근전"

    normalized["id"] = int(normalized.get("id", 0) or 0)
    normalized["name"] = str(normalized.get("name", "")).strip()
    normalized["english_name"] = str(normalized.get("english_name") or normalized.get("name_english") or "").strip()
    normalized["nation"] = str(normalized.get("nation", "대한민국")).strip() or "대한민국"
    normalized["id_no"] = str(normalized.get("id_no") or normalized.get("id_number") or "").strip()
    normalized["id_number"] = normalized["id_no"]
    normalized["affiliated_business"] = _normalize_business_name(normalized.get("affiliated_business") or normalized.get("business"))
    normalized["company"] = (
        str(normalized.get("company") or normalized.get("client") or "미지정 근무 사업장").strip()
        or "미지정 근무 사업장"
    )
    normalized["department"] = str(normalized.get("department") or "").strip()
    normalized["work_site"] = (
        str(normalized.get("work_site") or normalized.get("site_name") or normalized["company"]).strip()
        or normalized["company"]
    )
    if not normalized["department"]:
        normalized["department"] = normalized["work_site"]

    normalized["work_type"] = str(normalized.get("work_type", "교대")).strip() or "교대"
    normalized["pay_type"] = str(normalized.get("pay_type", "시급제")).strip() or "시급제"
    normalized["base_wage"] = float(normalized.get("base_wage", 0) or 0)
    pay_effective_date = str(normalized.get("pay_effective_date") or normalized.get("pay_type_effective_date") or normalized.get("hire_date") or date.today().isoformat()).strip()
    try:
        pay_effective_date = datetime.strptime(pay_effective_date, "%Y-%m-%d").date().isoformat()
    except Exception:
        pay_effective_date = date.today().isoformat()
    normalized["pay_effective_date"] = pay_effective_date
    normalized["pay_type_history"] = _normalize_pay_type_history(
        normalized.get("pay_type_history"),
        normalized["pay_type"],
        normalized["base_wage"],
        pay_effective_date,
    )
    if normalized["pay_type_history"]:
        latest_entry = normalized["pay_type_history"][-1]
        normalized["pay_type"] = str(latest_entry.get("pay_type") or normalized["pay_type"]).strip() or normalized["pay_type"]
        try:
            normalized["base_wage"] = float(latest_entry.get("base_wage", normalized["base_wage"]) or 0)
        except (TypeError, ValueError):
            normalized["base_wage"] = float(normalized.get("base_wage", 0) or 0)
        normalized["pay_effective_date"] = str(latest_entry.get("effective_date") or pay_effective_date)
    normalized["work_history"] = _normalize_work_history(
        normalized.get("work_history"),
        normalized["work_site"],
        normalized.get("hire_date") or date.today().isoformat(),
        status,
        normalized.get("affiliated_business"),
        normalized.get("work_type"),
    )
    normalized["resign_reason"] = str(normalized.get("resign_reason", "")).strip()
    normalized["resign_note"] = str(normalized.get("resign_note", "")).strip()
    if status == "퇴사" and not normalized["resign_reason"] and normalized["work_history"]:
        latest_history = normalized["work_history"][-1]
        normalized["resign_reason"] = str(latest_history.get("reason") or "").strip()
        normalized["resign_note"] = str(latest_history.get("note") or "").strip()

    normalized["status"] = status
    normalized["active"] = bool(normalized.get("active", status != "퇴사")) and status != "퇴사"
    normalized["workday"] = str(normalized.get("workday", "근무일")).strip() or "근무일"
    normalized["scheduled_start"] = str(normalized.get("scheduled_start", "08:00")).strip() or "08:00"
    normalized["actual_start"] = str(normalized.get("actual_start", "-")).strip() or "-"
    normalized["scheduled_end"] = str(normalized.get("scheduled_end", "18:00")).strip() or "18:00"
    normalized["actual_end"] = str(normalized.get("actual_end", "-")).strip() or "-"
    normalized["late_status"] = str(normalized.get("late_status", "없음")).strip() or "없음"
    normalized["hospital_status"] = str(normalized.get("hospital_status", "없음")).strip() or "없음"
    normalized["absence_status"] = str(normalized.get("absence_status", "없음")).strip() or "없음"
    normalized["note"] = str(normalized.get("note", "")).strip()

    normalized["hire_date"] = str(normalized.get("hire_date", "")).strip()
    bank_name = str(normalized.get("bank_name") or normalized.get("bank") or "").strip()
    if bank_name == "은행 선택":
        bank_name = ""
    normalized["bank_name"] = bank_name
    normalized["bank"] = bank_name
    bank_account = str(normalized.get("bank_account") or normalized.get("account_number") or "").strip()
    normalized["bank_account"] = bank_account
    normalized["account_number"] = bank_account
    normalized["attendance_score"] = int(normalized.get("attendance_score", score_settings["base_score"]) or score_settings["base_score"])
    normalized["unauthorized_absence"] = int(normalized.get("unauthorized_absence", 0) or 0)
    normalized["unauthorized_leave"] = int(normalized.get("unauthorized_leave", 0) or 0)
    normalized["late_count"] = int(normalized.get("late_count", 0) or 0)
    normalized["early_leave_count"] = int(normalized.get("early_leave_count", 0) or 0)
    normalized["warning_count"] = int(normalized.get("warning_count", 0) or 0)
    normalized["rejoin_grade"] = _grade_from_score(normalized["attendance_score"], rejoin_grades)
    return normalized


def _normalize_pay_type_history(history: list[dict] | None, fallback_pay_type: str, fallback_base_wage: float, fallback_date: str | None = None) -> list[dict]:
    entries: list[dict] = []
    default_date = str(fallback_date or date.today().isoformat()).strip()
    try:
        default_date = datetime.strptime(default_date, "%Y-%m-%d").date().isoformat()
    except Exception:
        default_date = date.today().isoformat()

    raw_entries = history if isinstance(history, list) else []
    for row in raw_entries:
        if not isinstance(row, dict):
            continue
        raw_date = str(row.get("effective_date") or row.get("date") or default_date).strip()
        try:
            effective_date = datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
        except Exception:
            continue
        pay_type = str(row.get("pay_type") or fallback_pay_type or "시급제").strip() or "시급제"
        try:
            base_wage = float(row.get("base_wage", fallback_base_wage) or 0)
        except (TypeError, ValueError):
            base_wage = float(fallback_base_wage or 0)
        entries.append({
            "effective_date": effective_date,
            "pay_type": pay_type,
            "base_wage": base_wage,
        })

    if not entries:
        entries.append({
            "effective_date": default_date,
            "pay_type": str(fallback_pay_type or "시급제").strip() or "시급제",
            "base_wage": float(fallback_base_wage or 0),
        })

    deduped: dict[str, dict] = {}
    for row in entries:
        deduped[row["effective_date"]] = row
    return [deduped[key] for key in sorted(deduped.keys())]


def _pay_terms_for_date(employee: dict | None, target_date: str | date | None) -> dict:
    employee = employee or {}
    if target_date is None:
        target = date.today()
    else:
        try:
            target = target_date if isinstance(target_date, date) else datetime.strptime(str(target_date), "%Y-%m-%d").date()
        except Exception:
            target = date.today()
    history = _normalize_pay_type_history(
        employee.get("pay_type_history"),
        str(employee.get("pay_type") or "시급제").strip() or "시급제",
        float(employee.get("base_wage", 0) or 0),
        str(employee.get("pay_effective_date") or employee.get("hire_date") or target.isoformat()),
    )
    selected = history[0]
    for row in history:
        try:
            effective_date = datetime.strptime(str(row.get("effective_date") or ""), "%Y-%m-%d").date()
        except Exception:
            continue
        if effective_date <= target:
            selected = row
        else:
            break
    return {
        "pay_type": str(selected.get("pay_type") or employee.get("pay_type") or "시급제").strip() or "시급제",
        "base_wage": float(selected.get("base_wage", employee.get("base_wage", 0)) or 0),
        "effective_date": str(selected.get("effective_date") or target.isoformat()),
    }



class AppState(QObject):
    employees_changed = Signal()
    attendance_changed = Signal()
    settings_changed = Signal()
    payroll_changed = Signal()
    records_changed = Signal()  # 월별 근태 기록이 변경될 때 emit
    vehicles_changed = Signal()
    holidays_changed = Signal(str)
    save_completed = Signal(str)
    server_sync_status = Signal(str)

    def __init__(self):
        super().__init__()
        self._default_score_settings = deepcopy(ATTENDANCE_SCORE_SETTINGS)
        self._default_rejoin_grades = deepcopy(REJOIN_GRADES)
        self._score_settings = deepcopy(ATTENDANCE_SCORE_SETTINGS)
        self._rejoin_grades = deepcopy(REJOIN_GRADES)
        self._employees: list[dict] = []
        self._businesses: list[dict] = []
        self._work_sites: list[dict] = []
        self._manager_accounts: list[dict] = []
        self._attendance_events: list[dict] = []
        self._payroll_settings_by_site: dict[str, dict] = {}
        self._payroll_setting_presets_by_site: dict[str, dict] = {}
        self._site_time_conversion_rules: list[dict] = []
        # 월별 근태 기록: {(employee_id, "yyyy-MM-dd"): {"status": str, "base": float, "over": float, "night": float, "memo": str}}
        self._monthly_records: dict[tuple[int, str], dict] = {}
        # 월별 급여 입력표 초안/수정본: {(employee_id, "yyyy-MM"): {"base": {day: hours}, "over": {...}, "night": {...}}}
        self._payroll_month_inputs: dict[tuple[int, str], dict] = {}
        # PC에서 마감한 월 정보입니다. 모바일 근태 수정 잠금 기준으로 서버 스냅샷에 함께 보냅니다.
        self._attendance_month_locks: dict[str, dict] = {}
        self._payroll_active_month: str | None = None
        # 개인별 월 급여 추가수당 및 공제액 (엑셀처럼 수기 수정 가능하도록 저장)
        # 키: (employee_id, "yyyy-MM") -> 값: dict (national_pension, health_insurance, meals_deduct, etc.)
        self._individual_payroll_adjustments: dict[tuple[int, str], dict] = {}
        self._payroll_detail_items_by_site: dict[str, list[dict]] = {}
        self._payroll_item_presets_by_site: dict[str, dict] = {}
        self._vehicles: list[dict] = []
        self._vehicle_run_logs: list[dict] = []
        self._vehicle_fuel_logs: list[dict] = []
        self._vehicle_cost_logs: list[dict] = []
        self._vehicle_alert_settings = deepcopy(VEHICLE_ALERT_SETTINGS)
        self._storage = StorageManager()
        self._storage.ensure_structure()
        self._storage.restore_latest_if_needed()
        self._app_settings = self._storage.load_app_settings(
            {
                "app_name": APP_SETTINGS_NAME,
                "storage_version": STORAGE_VERSION,
                "created_at": "",
                "last_backup_at": "",
                "autosave_minutes": DEFAULT_AUTOSAVE_MINUTES,
                "backup_dir": self._storage.backup_setting_value(),
                "vehicle_server_sync_enabled": True,
                "vehicle_server_sync_last_status": "기본 연동 대기",
                "vehicle_server_sync_last_at": "",
                "vehicle_server_sync_last_error": "",
            }
        )
        # 현재 정책: 전체 데이터는 10분 자동 저장·서버 전송을 기본값으로 사용합니다.
        current_autosave_raw = self._app_settings.get("autosave_minutes", DEFAULT_AUTOSAVE_MINUTES)
        self._autosave_minutes = self._sanitize_autosave_minutes(current_autosave_raw)
        if int(self._autosave_minutes or 0) == 30:
            self._autosave_minutes = DEFAULT_AUTOSAVE_MINUTES
        self._app_settings["storage_version"] = STORAGE_VERSION
        self._app_settings["app_name"] = APP_SETTINGS_NAME
        self._app_settings["autosave_minutes"] = self._autosave_minutes
        self._app_settings["backup_dir"] = self._storage.backup_setting_value()
        self._app_settings["vehicle_server_sync_enabled"] = True
        self._app_settings.setdefault("vehicle_server_sync_last_status", "기본 연동 대기")
        self._app_settings.setdefault("vehicle_server_sync_last_at", "")
        self._app_settings.setdefault("vehicle_server_sync_last_error", "")
        self._storage.save_app_settings(self._app_settings)
        self._db_is_saving = False
        self._is_preparing_exit = False
        self._dirty_sections: set[str] = set(DIRTY_SECTION_ALL)
        self._db = DatabaseManager(root_dir=self._storage.root_dir, data_dir=self._storage.data_dir, db_path=self._storage.db_path)
        self._db.initialize()
        loaded_snapshot = self._db.load_snapshot()
        self._db_is_loading = False
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(self._autosave_interval_ms())
        self._autosave_timer.timeout.connect(self._save_database_snapshot)
        self._pending_employee_sync: list[dict] = self._normalize_pending_employee_sync(self._app_settings.get("pending_employee_sync", []))
        self._server_sync_worker: FunctionWorkerThread | None = None
        self._active_server_sync_entry: dict | None = None
        self._server_refresh_worker: FunctionWorkerThread | None = None
        self._manual_sync_requested = False
        self._server_sync_timer = QTimer(self)
        self._server_sync_timer.setSingleShot(True)
        self._server_sync_timer.timeout.connect(self._start_employee_server_sync)
        self._server_snapshot_push_timer = QTimer(self)
        self._server_snapshot_push_timer.setSingleShot(True)
        self._server_snapshot_push_timer.timeout.connect(self._start_server_snapshot_push)
        self._server_snapshot_pull_timer = QTimer(self)
        self._server_snapshot_pull_timer.setInterval(SERVER_SNAPSHOT_PULL_INTERVAL_MS)
        self._server_snapshot_pull_timer.timeout.connect(self._start_server_snapshot_pull)
        self._server_snapshot_push_worker: FunctionWorkerThread | None = None
        self._server_snapshot_pull_worker: FunctionWorkerThread | None = None
        self._vehicle_log_pull_worker: FunctionWorkerThread | None = None
        self._holiday_sync_worker: FunctionWorkerThread | None = None
        self._server_snapshot_applying = False
        self._last_server_snapshot_updated_at = str(self._app_settings.get("last_server_snapshot_updated_at", "") or "")
        self._last_server_sync_notice = ""
        self._suppress_server_sync_notice = False
        self._settings_dirty_emit_suppressed = False
        if loaded_snapshot:
            self._apply_database_snapshot(loaded_snapshot)
        removed_test_seed_data = self._remove_known_test_seed_data()
        migrated_employee_media = self._stabilize_employee_media_paths()
        seeded_records = self._seed_monthly_records_from_events()
        if loaded_snapshot is None or seeded_records or removed_test_seed_data:
            self._dirty_sections = set(DIRTY_SECTION_ALL)
            reason = "test-data-cleanup" if removed_test_seed_data else "initial-load"
            self._save_database_snapshot(force_full=True, sync_latest_backup=False, backup_reason=reason)
        elif migrated_employee_media:
            self._dirty_sections.update({"core_people"})
            self._save_database_snapshot(force_full=False, sync_latest_backup=False, backup_reason="employee-media-migration")
        current_server_settings = self._storage.load_server_api_settings({})
        if not bool(current_server_settings.get("use_server", True)):
            current_server_settings["use_server"] = True
            self._storage.save_server_api_settings(current_server_settings)
        self._save_pending_employee_sync()
        self._bind_database_autosave()
        self._server_snapshot_pull_timer.start()
        QTimer.singleShot(2500, self._start_server_snapshot_pull)
        QTimer.singleShot(3600, self.sync_holidays_async)

    def get_local_ui_setting(self, key: str, default=None):
        settings = self._app_settings.get("local_ui_settings", {})
        if not isinstance(settings, dict):
            return default
        return deepcopy(settings.get(str(key), default))

    def set_local_ui_setting(self, key: str, value) -> None:
        settings = self._app_settings.get("local_ui_settings", {})
        if not isinstance(settings, dict):
            settings = {}
        settings[str(key)] = deepcopy(value)
        self._app_settings["local_ui_settings"] = settings
        self._storage.save_app_settings(self._app_settings)

    def holiday_api_settings(self) -> dict:
        self._storage.ensure_structure()
        return load_holiday_api_settings(self._storage.config_dir)

    def save_holiday_api_settings(self, enabled: bool, service_key: str) -> dict:
        self._storage.ensure_structure()
        settings = self.holiday_api_settings()
        settings["enabled"] = bool(enabled)
        settings["service_key"] = str(service_key or "").strip()
        current_year = datetime.now().year
        settings["years"] = sorted(set(int(y) for y in (settings.get("years") or [current_year, current_year + 1]) if str(y).isdigit()))
        if current_year not in settings["years"]:
            settings["years"].append(current_year)
        if current_year + 1 not in settings["years"]:
            settings["years"].append(current_year + 1)
        settings["years"] = sorted(set(settings["years"]))
        saved = save_holiday_api_settings(self._storage.config_dir, settings)
        # 공휴일 자동갱신 인증키는 PC 환경값이 아니라 회사 운영 공용 설정입니다.
        # 저장 즉시 서버 snapshot 대상(settings)으로 표시해 다른 PC에도 동기화되게 합니다.
        self._dirty_sections.add("settings")
        self._schedule_database_snapshot()
        self._schedule_server_snapshot_push(1200)
        self.settings_changed.emit()
        if saved.get("enabled") and saved.get("service_key"):
            self.sync_holidays_async(manual=True)
        return saved

    def sync_holidays_async(self, manual: bool = False) -> bool:
        self._storage.ensure_structure()
        settings = self.holiday_api_settings()
        if not settings.get("enabled") or not str(settings.get("service_key", "") or "").strip():
            if manual:
                self.holidays_changed.emit("공휴일 API 인증키가 비어 있습니다.")
            return False
        if self._holiday_sync_worker is not None and self._holiday_sync_worker.isRunning():
            if manual:
                self.holidays_changed.emit("공휴일 갱신이 이미 진행 중입니다.")
            return False
        current_year = datetime.now().year
        years = sorted(set([current_year, current_year + 1] + [int(y) for y in settings.get("years", []) if str(y).isdigit()]))
        self._holiday_sync_worker = FunctionWorkerThread(sync_holidays_from_api, self._storage.config_dir, years)
        self._holiday_sync_worker.result_ready.connect(self._handle_holiday_sync_result)
        self._holiday_sync_worker.error_occurred.connect(self._handle_holiday_sync_error)
        self._holiday_sync_worker.start()
        return True

    def _finish_holiday_worker(self):
        worker = self._holiday_sync_worker
        self._holiday_sync_worker = None
        if worker is not None:
            worker.deleteLater()

    def _handle_holiday_sync_result(self, result):
        _clear_holiday_cache()
        message = str((result or {}).get("message") or "공휴일 갱신 완료")
        self._finish_holiday_worker()
        self.holidays_changed.emit(message)

    def _handle_holiday_sync_error(self, error: str):
        message = str(error or "공휴일 갱신 실패")
        mark_holiday_sync_error(self._storage.config_dir, message)
        _clear_holiday_cache()
        self._finish_holiday_worker()
        self.holidays_changed.emit(f"공휴일 갱신 실패: {message}")

    @property
    def database_path(self) -> str:
        return str(self._db.db_path)

    @property
    def data_root_path(self) -> str:
        return str(self._storage.data_dir)

    def last_employee_sync_at(self) -> str:
        return str(self._app_settings.get("last_employee_sync_at", "") or "")

    def last_employee_sync_error(self) -> str:
        error_text = str(self._app_settings.get("last_employee_sync_error", "") or "").strip()
        if error_text:
            return error_text
        for row in self._pending_employee_sync:
            row_error = str((row or {}).get("last_error") or "").strip()
            if row_error:
                return row_error
        return ""

    def last_employee_sync_status(self) -> str:
        return str(self._last_server_sync_notice or self._app_settings.get("last_employee_sync_status", "") or "")


    @property
    def backup_root_path(self) -> str:
        return str(self._storage.backup_root)

    @property
    def default_backup_root_path(self) -> str:
        return str(self._storage.default_backup_root)

    @property
    def backup_latest_path(self) -> str:
        return str(self._storage.backup_latest_dir)

    @property
    def backup_history_path(self) -> str:
        return str(self._storage.backup_history_dir)

    @property
    def export_root_path(self) -> str:
        self._storage.ensure_structure()
        return str(self._storage.export_dir)

    def export_subdir_path(self, name: str) -> str:
        self._storage.ensure_structure()
        folder_name = str(name or "export").strip() or "export"
        target = self._storage.export_dir / folder_name
        target.mkdir(parents=True, exist_ok=True)
        return str(target)

    def _sanitize_autosave_minutes(self, minutes: int | str | None) -> int:
        try:
            value = int(minutes or DEFAULT_AUTOSAVE_MINUTES)
        except (TypeError, ValueError):
            value = DEFAULT_AUTOSAVE_MINUTES
        return max(MIN_AUTOSAVE_MINUTES, min(MAX_AUTOSAVE_MINUTES, value))

    def _autosave_interval_ms(self) -> int:
        return self._sanitize_autosave_minutes(self._autosave_minutes) * 60 * 1000

    def autosave_minutes(self) -> int:
        return self._sanitize_autosave_minutes(self._autosave_minutes)

    def set_autosave_minutes(self, minutes: int | str | None) -> int:
        value = self._sanitize_autosave_minutes(minutes)
        self._autosave_minutes = value
        self._autosave_timer.setInterval(self._autosave_interval_ms())
        self._app_settings["autosave_minutes"] = value
        self._storage.save_app_settings(self._app_settings)
        self.settings_changed.emit()
        return value


    def backup_dir_setting(self) -> str:
        return str(self._app_settings.get("backup_dir", self._storage.backup_setting_value()) or self._storage.backup_setting_value())

    def set_backup_root_path(self, backup_dir_value: str | None) -> str:
        target = self._storage.set_backup_root(backup_dir_value)
        self._app_settings["backup_dir"] = self._storage.backup_setting_value()
        self._storage.save_app_settings(self._app_settings)
        self.settings_changed.emit()
        return str(target)

    def save_now(self, include_latest_backup: bool = False) -> None:
        self._save_database_snapshot(sync_latest_backup=include_latest_backup, backup_reason="manual-save")

    def _bind_database_autosave(self):
        self.employees_changed.connect(lambda: self._mark_dirty_and_schedule("employees"))
        self.attendance_changed.connect(lambda: self._mark_dirty_and_schedule("attendance"))
        self.settings_changed.connect(lambda: None if getattr(self, "_settings_dirty_emit_suppressed", False) else self._mark_dirty_and_schedule("settings"))
        self.payroll_changed.connect(lambda: self._mark_dirty_and_schedule("payroll"))
        self.records_changed.connect(lambda: self._mark_dirty_and_schedule("records"))
        self.vehicles_changed.connect(lambda: self._mark_dirty_and_schedule("vehicles"))

    def _mark_dirty_and_schedule(self, signal_name: str):
        self._dirty_sections.update(DIRTY_SIGNAL_SECTION_MAP.get(signal_name, set(DIRTY_SECTION_ALL)))
        self._schedule_database_snapshot()

    def _emit_settings_changed_without_dirty(self):
        """동기화 상태 표시만 갱신할 때 settings dirty 표시를 만들지 않습니다."""
        self._settings_dirty_emit_suppressed = True
        try:
            self.settings_changed.emit()
        finally:
            self._settings_dirty_emit_suppressed = False

    def _schedule_database_snapshot(self):
        if getattr(self, "_db_is_loading", False) or getattr(self, "_is_preparing_exit", False):
            return
        if not self._dirty_sections:
            return
        self._autosave_timer.start()

    def _schedule_server_snapshot_push(self, delay_ms: int = SERVER_SNAPSHOT_PUSH_DELAY_MS):
        if getattr(self, "_db_is_loading", False) or getattr(self, "_is_preparing_exit", False):
            return
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "")).strip():
            return
        if self._server_snapshot_push_worker is not None and self._server_snapshot_push_worker.isRunning():
            return
        self._server_snapshot_push_timer.start(max(500, int(delay_ms or SERVER_SNAPSHOT_PUSH_DELAY_MS)))

    def _push_server_snapshot_payload(self, settings: dict, payload: dict) -> dict:
        return push_app_snapshot(settings, {"payload": payload})

    def _upload_employee_portrait_to_server(self, employee: dict) -> dict:
        payload = deepcopy(employee or {})
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "")).strip():
            return payload
        try:
            employee_id = int(payload.get("id", 0) or 0)
        except (TypeError, ValueError):
            employee_id = 0
        if employee_id <= 0:
            return payload
        local_path = self.resolve_storage_file_path(payload.get("portrait_path"))
        if not local_path:
            return payload
        src = Path(local_path)
        if not src.exists() or not src.is_file():
            return payload
        try:
            response = upload_employee_media(settings, employee_id, "portrait", str(src))
        except Exception as exc:
            self._emit_server_sync_notice(f"얼굴 사진 서버 저장 실패: {exc}")
            return payload
        url = str(response.get("url") or response.get("media_url") or "").strip() if isinstance(response, dict) else ""
        if url:
            payload["portrait_server_url"] = url
        return payload

    def _download_missing_employee_portraits(self) -> bool:
        changed = False
        settings = self.server_api_settings()
        timeout = settings.get("timeout_seconds", 5)
        for row in self._employees:
            url = str(row.get("portrait_server_url") or "").strip()
            if not url.lower().startswith(("http://", "https://")):
                continue
            try:
                employee_id = int(row.get("id", 0) or 0)
            except (TypeError, ValueError):
                employee_id = 0
            if employee_id <= 0:
                continue
            current_path = self.resolve_storage_file_path(row.get("portrait_path"))
            if current_path and Path(current_path).exists():
                continue
            try:
                target_path, rel = self.get_employee_portrait_storage_path(employee_id, ".png")
                data = download_media_file(url, timeout)
                if not data:
                    continue
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(data)
                row["portrait_path"] = rel
                changed = True
            except Exception:
                continue
        return changed

    def _start_server_snapshot_push(self):
        if getattr(self, "_db_is_loading", False) or getattr(self, "_server_snapshot_applying", False):
            return
        if self._server_snapshot_push_worker is not None and self._server_snapshot_push_worker.isRunning():
            return
        if self._dirty_sections:
            self._save_database_snapshot(sync_latest_backup=False, backup_reason="server-snapshot-push")
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "")).strip():
            return
        payload = self._build_server_snapshot_payload()
        self._server_snapshot_push_worker = FunctionWorkerThread(self._push_server_snapshot_payload, deepcopy(settings), payload)
        self._server_snapshot_push_worker.result_ready.connect(self._handle_server_snapshot_push_success)
        self._server_snapshot_push_worker.error_occurred.connect(self._handle_server_snapshot_push_error)
        self._server_snapshot_push_worker.finished.connect(self._cleanup_server_snapshot_push_worker)
        self._server_snapshot_push_worker.start()

    def _handle_server_snapshot_push_success(self, response: dict):
        payload = response.get("payload") if isinstance(response, dict) else {}
        updated_at = str(response.get("updated_at") or (payload or {}).get("updated_at") or "").strip() if isinstance(response, dict) else ""
        now_text = datetime.now().isoformat(timespec="seconds")
        if updated_at:
            self._last_server_snapshot_updated_at = updated_at
            self._app_settings["last_server_snapshot_updated_at"] = updated_at
        self._app_settings["vehicle_server_sync_enabled"] = True
        self._app_settings["vehicle_server_sync_last_status"] = "차량 상세기록 포함 서버 전체 저장 완료"
        self._app_settings["vehicle_server_sync_last_error"] = ""
        self._app_settings["vehicle_server_sync_last_at"] = updated_at or now_text
        self._save_sync_status_metadata(status="서버 전체 저장 완료", success=True)
        self._storage.save_app_settings(self._app_settings)
        self._emit_settings_changed_without_dirty()
        self._emit_server_sync_notice("서버 전체 저장 완료")

    def _handle_server_snapshot_push_error(self, message: str):
        error_text = str(message or "").strip()
        self._app_settings["vehicle_server_sync_enabled"] = True
        self._app_settings["vehicle_server_sync_last_status"] = "차량 상세기록 포함 서버 전체 저장 실패"
        self._app_settings["vehicle_server_sync_last_error"] = error_text
        self._app_settings["vehicle_server_sync_last_at"] = datetime.now().isoformat(timespec="seconds")
        self._save_sync_status_metadata(status="서버 전체 저장 실패", error=error_text)
        self._storage.save_app_settings(self._app_settings)
        self._emit_settings_changed_without_dirty()
        self._emit_server_sync_notice(f"서버 전체 저장 실패: {error_text or message}")

    def _cleanup_server_snapshot_push_worker(self):
        worker = self._server_snapshot_push_worker
        self._server_snapshot_push_worker = None
        if worker is not None:
            worker.deleteLater()
        if not self.is_server_sync_running():
            self._manual_sync_requested = False
            self._suppress_server_sync_notice = False
            self._emit_server_sync_notice("동기화 대기")

    def _fetch_server_snapshot_payload(self, settings: dict) -> dict:
        return fetch_app_snapshot(settings)

    def _start_server_employee_refresh_after_snapshot_pull(self, notice: str = "서버 근로자 목록 확인 중") -> bool:
        """수동 동기화 중 snapshot 확인 뒤 서버 근로자 목록을 즉시 다시 확인합니다.

        모바일 근로자 등록은 /api/employees 목록에는 바로 들어오지만,
        전체 snapshot에는 아직 반영되지 않았을 수 있습니다.
        그래서 snapshot 변경 여부와 상관없이 수동 동기화에서는 서버 근로자 목록을
        추가 확인해 홈/근로자관리/근태관리 화면이 즉시 갱신되게 합니다.
        """
        if not self._manual_sync_requested or self._suppress_server_sync_notice:
            return False
        if self._server_refresh_worker is not None and self._server_refresh_worker.isRunning():
            return True
        self._emit_server_sync_notice(str(notice or "서버 근로자 목록 확인 중"))
        self._start_server_refresh()
        return self._server_refresh_worker is not None

    def _start_server_snapshot_pull(self, *, force: bool = False) -> bool:
        # PC 자료 보호: 자동 주기 실행은 기존처럼 막고, 사용자가 누른 수동 동기화에서만
        # 서버 전체 스냅샷을 PC에 적용할 수 있게 합니다.
        if not force and not bool(self._app_settings.get("allow_server_snapshot_pull", False)):
            self._start_vehicle_log_pull(silent=True)
            return False
        if getattr(self, "_db_is_loading", False) or getattr(self, "_is_preparing_exit", False):
            return False
        if self._dirty_sections:
            if force and not self._suppress_server_sync_notice:
                self._emit_server_sync_notice("PC 변경사항 저장 후 서버 전체 불러오기 가능")
            return False
        if self._server_snapshot_applying:
            return False
        if self._server_snapshot_push_worker is not None and self._server_snapshot_push_worker.isRunning():
            return False
        if self._server_snapshot_pull_worker is not None and self._server_snapshot_pull_worker.isRunning():
            return False
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "")).strip():
            return False
        self._server_snapshot_pull_worker = FunctionWorkerThread(self._fetch_server_snapshot_payload, deepcopy(settings))
        self._server_snapshot_pull_worker.result_ready.connect(self._handle_server_snapshot_pull_success)
        self._server_snapshot_pull_worker.error_occurred.connect(self._handle_server_snapshot_pull_error)
        self._server_snapshot_pull_worker.finished.connect(self._cleanup_server_snapshot_pull_worker)
        self._server_snapshot_pull_worker.start()
        return True

    def _handle_server_snapshot_pull_success(self, response: dict):
        if not isinstance(response, dict):
            return
        payload = response.get("payload") if isinstance(response.get("payload"), dict) else {}
        snapshot, payload_updated_at = self._decode_server_snapshot_payload(payload)
        updated_at = str(response.get("updated_at") or payload_updated_at or "").strip()
        if not snapshot:
            self._save_sync_status_metadata(status="서버 전체 자료 없음", error="")
            if self._start_server_employee_refresh_after_snapshot_pull("서버 전체 자료 없음 · 근로자 목록 확인 중"):
                return
            attendance_summary = self._manual_attendance_sync_summary(
                self._pull_current_attendance_month_for_manual_sync()
            ) if self._manual_sync_requested and not self._suppress_server_sync_notice else ""
            suffix = f" · {attendance_summary}" if attendance_summary else ""
            self._emit_server_sync_notice(f"서버 전체 자료 없음 · 자료가 있는 PC에서 동기화를 먼저 눌러 주세요{suffix}")
            return
        if updated_at and self._last_server_snapshot_updated_at and updated_at <= self._last_server_snapshot_updated_at:
            # timestamp가 같아도 PC별 설정 파일에는 공휴일 인증키가 아직 반영되지 않은 경우가 있다.
            # 수동 동기화 때는 서버 snapshot의 공용 설정을 한 번 더 적용해서 PC2가 바로 사용할 수 있게 한다.
            shared_changed = self._apply_shared_settings_snapshot(snapshot.get("shared_settings") or {})
            if shared_changed:
                self._save_database_snapshot(sync_latest_backup=False, backup_reason="server-snapshot-pull", force_full=True)
            if self._start_server_employee_refresh_after_snapshot_pull("서버 전체 자료 변경 없음 · 근로자 목록 확인 중"):
                return
            attendance_summary = self._manual_attendance_sync_summary(
                self._pull_current_attendance_month_for_manual_sync()
            ) if self._manual_sync_requested and not self._suppress_server_sync_notice else ""
            holiday_suffix = "공휴일 설정 반영" if shared_changed else ""
            parts = [part for part in (holiday_suffix, attendance_summary) if part]
            if parts:
                self._save_sync_status_metadata(success=True)
                self._emit_server_sync_notice("서버 전체 자료 변경 없음 · " + " · ".join(parts))
            else:
                self._emit_server_sync_notice("서버 전체 자료 변경 없음")
            return

        self._server_snapshot_applying = True
        try:
            try:
                self._db_is_loading = True
                self._apply_database_snapshot(snapshot)
                self._dirty_sections = set(DIRTY_SECTION_ALL)
            finally:
                self._db_is_loading = False
            self._save_database_snapshot(sync_latest_backup=False, backup_reason="server-snapshot-pull", force_full=True)
            if updated_at:
                self._last_server_snapshot_updated_at = updated_at
                self._app_settings["last_server_snapshot_updated_at"] = updated_at
                self._storage.save_app_settings(self._app_settings)
            try:
                self._db_is_loading = True
                self.employees_changed.emit()
                self.attendance_changed.emit()
                self.records_changed.emit()
                self.payroll_changed.emit()
                self.vehicles_changed.emit()
                self.settings_changed.emit()
            finally:
                self._db_is_loading = False
            if self._start_server_employee_refresh_after_snapshot_pull("서버 전체 자료 반영 완료 · 근로자 목록 확인 중"):
                self._save_sync_status_metadata(success=True)
                return
            attendance_summary = ""
            if self._manual_sync_requested and not self._suppress_server_sync_notice:
                attendance_result = self._pull_current_attendance_month_for_manual_sync()
                attendance_summary = self._manual_attendance_sync_summary(attendance_result)
            suffix = f" · {attendance_summary}" if attendance_summary else ""
            self._save_sync_status_metadata(success=True)
            self._emit_server_sync_notice(f"서버 전체 자료 반영 완료{suffix}")
        finally:
            self._server_snapshot_applying = False

    def _handle_server_snapshot_pull_error(self, message: str):
        text = str(message or "").strip()
        if self._manual_sync_requested and not self._suppress_server_sync_notice:
            if text and "404" not in text and "422" not in text:
                self._save_sync_status_metadata(status="서버 전체 불러오기 실패", error=text)
                if self._start_server_employee_refresh_after_snapshot_pull(f"서버 전체 불러오기 실패 · 근로자 목록 확인 중"):
                    return
            else:
                if self._start_server_employee_refresh_after_snapshot_pull("서버 근로자 목록 확인 중"):
                    return
        attendance_summary = ""
        if self._manual_sync_requested and not self._suppress_server_sync_notice:
            attendance_summary = self._manual_attendance_sync_summary(self._pull_current_attendance_month_for_manual_sync())
        if text and "404" not in text and "422" not in text:
            self._save_sync_status_metadata(status="서버 전체 불러오기 실패", error=text)
            suffix = f" · {attendance_summary}" if attendance_summary else ""
            self._emit_server_sync_notice(f"서버 전체 불러오기 실패: {text}{suffix}")
        elif attendance_summary:
            self._save_sync_status_metadata(success=True)
            self._emit_server_sync_notice(attendance_summary)

    def _cleanup_server_snapshot_pull_worker(self):
        worker = self._server_snapshot_pull_worker
        self._server_snapshot_pull_worker = None
        if worker is not None:
            worker.deleteLater()
        if not self.is_server_sync_running():
            self._manual_sync_requested = False
            self._suppress_server_sync_notice = False


    def _fetch_vehicle_log_rows_remote(self, settings: dict) -> dict:
        return fetch_vehicle_logs_remote(settings)

    def _vehicle_detail_log_server_settings(self) -> dict | None:
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "") or "").strip():
            return None
        return settings

    @staticmethod
    def _vehicle_log_source_label(value: str | None, default: str = "모바일") -> str:
        text = str(value or "").strip()
        if not text:
            return default
        lowered = text.lower()
        if lowered in {"pc", "pc수동"} or text.startswith("PC"):
            return text if text.startswith("PC") else "PC"
        if lowered == "mobile" or text == "모바일":
            return "모바일"
        return text

    def _sync_vehicle_detail_log_save_remote(self, log_kind: str, payload: dict) -> None:
        settings = self._vehicle_detail_log_server_settings()
        if not settings:
            return
        funcs = {
            "run": save_vehicle_run_log_remote,
            "fuel": save_vehicle_fuel_log_remote,
            "cost": save_vehicle_cost_log_remote,
        }
        func = funcs.get(str(log_kind or "").strip())
        if func is None:
            return
        remote_payload = deepcopy(payload or {})
        remote_payload["source"] = str(remote_payload.get("source") or "pc").strip() or "pc"
        remote_payload["updated_by"] = "pc"
        vehicle_id = str(remote_payload.get("vehicle_id") or "").strip()
        vehicle = self.get_vehicle_by_id(vehicle_id) if vehicle_id else None
        if vehicle:
            vehicle_name = str(vehicle.get("vehicle_name") or "").strip()
            plate_number = str(vehicle.get("plate_number") or vehicle.get("vehicle_no") or "").strip()
            car_label = plate_number or vehicle_name or vehicle_id
            if not str(remote_payload.get("vehicle_name") or "").strip():
                remote_payload["vehicle_name"] = vehicle_name
            if not str(remote_payload.get("plate_number") or "").strip():
                remote_payload["plate_number"] = plate_number
            if not str(remote_payload.get("car") or "").strip():
                remote_payload["car"] = car_label
            if not str(remote_payload.get("business") or "").strip():
                remote_payload["business"] = str(vehicle.get("business_name") or vehicle.get("business") or "").strip()
            if not str(remote_payload.get("site") or "").strip():
                remote_payload["site"] = str(vehicle.get("work_site_name") or vehicle.get("work_site") or vehicle.get("site") or "").strip()
            if not str(remote_payload.get("baseline_odometer") or "").strip():
                remote_payload["baseline_odometer"] = vehicle.get("baseline_odometer") or vehicle.get("start_odometer") or vehicle.get("initial_odometer") or 0
        try:
            response = func(settings, remote_payload)
            if isinstance(response, dict) and response.get("ok") is False:
                raise RuntimeError(str(response.get("message") or response.get("detail") or "서버 저장 실패"))
        except Exception as error:
            self.mark_vehicle_server_sync_status("PC 차량기록 서버 저장 실패", str(error))
            raise ValueError(f"서버 차량기록 저장 실패: {error}") from error
        else:
            self.mark_vehicle_server_sync_status("PC 차량기록 서버 저장 완료", "")

    def _sync_vehicle_detail_log_delete_remote(self, log_kind: str, log_id: str) -> None:
        settings = self._vehicle_detail_log_server_settings()
        if not settings:
            return
        funcs = {
            "run": delete_vehicle_run_log_remote,
            "fuel": delete_vehicle_fuel_log_remote,
            "cost": delete_vehicle_cost_log_remote,
        }
        func = funcs.get(str(log_kind or "").strip())
        if func is None:
            return
        try:
            response = func(settings, str(log_id or "").strip())
            if isinstance(response, dict) and response.get("ok") is False:
                raise RuntimeError(str(response.get("message") or response.get("detail") or "서버 삭제 실패"))
        except Exception as error:
            self.mark_vehicle_server_sync_status("PC 차량기록 서버 삭제 실패", str(error))
            raise ValueError(f"서버 차량기록 삭제 실패: {error}") from error
        else:
            self.mark_vehicle_server_sync_status("PC 차량기록 서버 삭제 완료", "")

    def _start_vehicle_log_pull(self, silent: bool = True) -> None:
        if self._vehicle_log_pull_worker is not None and self._vehicle_log_pull_worker.isRunning():
            return
        now = datetime.now()
        last_text = str(self._app_settings.get("vehicle_server_sync_last_at", "") or "").strip()
        if last_text:
            try:
                last_dt = datetime.fromisoformat(last_text)
                if (now - last_dt).total_seconds() < 5:
                    if not silent:
                        self._emit_server_sync_notice("차량기록 최근 확인됨")
                    return
            except Exception:
                pass
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "")).strip():
            return
        self._vehicle_log_pull_worker = FunctionWorkerThread(self._fetch_vehicle_log_rows_remote, deepcopy(settings))
        self._vehicle_log_pull_worker.result_ready.connect(lambda payload: self._handle_vehicle_log_pull_success(payload, silent=silent))
        self._vehicle_log_pull_worker.error_occurred.connect(lambda message: self._handle_vehicle_log_pull_error(message, silent=silent))
        self._vehicle_log_pull_worker.finished.connect(self._cleanup_vehicle_log_pull_worker)
        self._vehicle_log_pull_worker.start()

    @staticmethod
    def _vehicle_log_float(value, default: float = 0.0) -> float:
        try:
            return max(0.0, float(value or 0))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _vehicle_log_int(value, default: int = 1) -> int:
        try:
            parsed = int(value or default)
        except (TypeError, ValueError):
            parsed = default
        return max(1, min(5, parsed))

    def _normalize_remote_run_log(self, row: dict) -> dict | None:
        if not isinstance(row, dict):
            return None
        log_id = str(row.get("log_id") or "").strip()
        vehicle_id = str(row.get("vehicle_id") or "").strip()
        if not log_id or not vehicle_id:
            return None
        if not self.get_vehicle_by_id(vehicle_id):
            return None
        target_date = str(row.get("date") or row.get("log_date") or "").strip()[:10]
        if not target_date:
            return None
        return {
            "log_id": log_id,
            "date": target_date,
            "vehicle_id": vehicle_id,
            "driver_name": str(row.get("driver_name") or row.get("driver") or "").strip(),
            "end_odometer": self._vehicle_log_float(row.get("end_odometer") if row.get("end_odometer") is not None else row.get("km")),
            "round_trips": self._vehicle_log_int(row.get("round_trips") if row.get("round_trips") is not None else row.get("trip")),
            "note": str(row.get("note") or "").strip(),
            "source": self._vehicle_log_source_label(row.get("source"), "모바일"),
            "saved_at": str(row.get("created_at") or row.get("savedAt") or row.get("updated_at") or row.get("saved_at") or "").strip(),
        }

    def _normalize_remote_fuel_log(self, row: dict) -> dict | None:
        if not isinstance(row, dict):
            return None
        fuel_id = str(row.get("fuel_id") or "").strip()
        vehicle_id = str(row.get("vehicle_id") or "").strip()
        if not fuel_id or not vehicle_id:
            return None
        if not self.get_vehicle_by_id(vehicle_id):
            return None
        fuel_date = str(row.get("fuel_date") or row.get("date") or "").strip()
        if not fuel_date:
            return None
        return {
            "fuel_id": fuel_id,
            "fuel_date": fuel_date,
            "vehicle_id": vehicle_id,
            "amount": self._vehicle_log_float(row.get("amount")),
            "note": str(row.get("note") or "").strip(),
            "source": self._vehicle_log_source_label(row.get("source"), "모바일"),
        }

    def _normalize_remote_cost_log(self, row: dict) -> dict | None:
        if not isinstance(row, dict):
            return None
        cost_id = str(row.get("cost_id") or "").strip()
        vehicle_id = str(row.get("vehicle_id") or "").strip()
        if not cost_id or not vehicle_id:
            return None
        if not self.get_vehicle_by_id(vehicle_id):
            return None
        cost_date = str(row.get("cost_date") or row.get("date") or "").strip()
        if not cost_date:
            return None
        return {
            "cost_id": cost_id,
            "cost_date": cost_date,
            "vehicle_id": vehicle_id,
            "category": str(row.get("category") or "기타").strip() or "기타",
            "amount": self._vehicle_log_float(row.get("amount")),
            "description": str(row.get("description") or "").strip(),
            "note": str(row.get("note") or "").strip(),
            "source": self._vehicle_log_source_label(row.get("source"), "모바일"),
        }

    @staticmethod
    def _merge_vehicle_log_rows(current: list[dict], incoming: list[dict], id_key: str) -> tuple[list[dict], int]:
        merged = [deepcopy(row) for row in current if isinstance(row, dict)]
        index = {str(row.get(id_key) or "").strip(): idx for idx, row in enumerate(merged) if str(row.get(id_key) or "").strip()}
        changed = 0
        for row in incoming:
            key = str(row.get(id_key) or "").strip()
            if not key:
                continue
            if key in index:
                if merged[index[key]] != row:
                    merged[index[key]] = deepcopy(row)
                    changed += 1
            else:
                index[key] = len(merged)
                merged.append(deepcopy(row))
                changed += 1
        return merged, changed

    @staticmethod
    def _vehicle_deleted_id_texts(value) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, dict):
            values = value.values()
        elif isinstance(value, (list, tuple, set)):
            values = value
        else:
            values = str(value or "").replace(";", ",").split(",")
        return {str(item or "").strip() for item in values if str(item or "").strip()}

    @classmethod
    def _vehicle_deleted_log_ids_from_payload(cls, payload: dict) -> dict[str, set[str]]:
        result = {"run": set(), "fuel": set(), "cost": set()}
        if not isinstance(payload, dict):
            return result
        grouped_sources = []
        for key in ("deleted", "deleted_log_ids", "deleted_ids"):
            value = payload.get(key)
            if isinstance(value, dict):
                grouped_sources.append(value)
        for source in grouped_sources:
            result["run"].update(cls._vehicle_deleted_id_texts(source.get("run") or source.get("run_logs") or source.get("run_log_ids")))
            result["fuel"].update(cls._vehicle_deleted_id_texts(source.get("fuel") or source.get("fuel_logs") or source.get("fuel_log_ids")))
            result["cost"].update(cls._vehicle_deleted_id_texts(source.get("cost") or source.get("cost_logs") or source.get("cost_log_ids")))
        result["run"].update(cls._vehicle_deleted_id_texts(payload.get("deleted_run_ids") or payload.get("run_deleted_ids")))
        result["fuel"].update(cls._vehicle_deleted_id_texts(payload.get("deleted_fuel_ids") or payload.get("fuel_deleted_ids")))
        result["cost"].update(cls._vehicle_deleted_id_texts(payload.get("deleted_cost_ids") or payload.get("cost_deleted_ids")))
        return result

    @staticmethod
    def _remove_vehicle_deleted_log_rows(current: list[dict], deleted_ids: set[str], id_key: str) -> tuple[list[dict], int]:
        if not deleted_ids:
            return [deepcopy(row) for row in current if isinstance(row, dict)], 0
        kept = []
        removed = 0
        for row in current:
            if not isinstance(row, dict):
                continue
            key = str(row.get(id_key) or "").strip()
            if key and key in deleted_ids:
                removed += 1
                continue
            kept.append(deepcopy(row))
        return kept, removed

    def _handle_vehicle_log_pull_success(self, payload: dict, *, silent: bool = True) -> None:
        if not isinstance(payload, dict):
            return
        run_rows = [row for row in (self._normalize_remote_run_log(row) for row in payload.get("run_logs", []) or []) if row]
        fuel_rows = [row for row in (self._normalize_remote_fuel_log(row) for row in payload.get("fuel_logs", []) or []) if row]
        cost_rows = [row for row in (self._normalize_remote_cost_log(row) for row in payload.get("cost_logs", []) or []) if row]
        deleted_ids = self._vehicle_deleted_log_ids_from_payload(payload)
        new_run, run_changed = self._merge_vehicle_log_rows(self._vehicle_run_logs, run_rows, "log_id")
        new_fuel, fuel_changed = self._merge_vehicle_log_rows(self._vehicle_fuel_logs, fuel_rows, "fuel_id")
        new_cost, cost_changed = self._merge_vehicle_log_rows(self._vehicle_cost_logs, cost_rows, "cost_id")
        new_run, run_removed = self._remove_vehicle_deleted_log_rows(new_run, deleted_ids.get("run", set()), "log_id")
        new_fuel, fuel_removed = self._remove_vehicle_deleted_log_rows(new_fuel, deleted_ids.get("fuel", set()), "fuel_id")
        new_cost, cost_removed = self._remove_vehicle_deleted_log_rows(new_cost, deleted_ids.get("cost", set()), "cost_id")
        changed = run_changed + fuel_changed + cost_changed + run_removed + fuel_removed + cost_removed
        removed = run_removed + fuel_removed + cost_removed
        now_text = datetime.now().isoformat(timespec="seconds")
        self._app_settings["vehicle_server_sync_enabled"] = True
        self._app_settings["vehicle_server_sync_last_at"] = now_text
        self._app_settings["vehicle_server_sync_last_error"] = ""
        if changed:
            self._vehicle_run_logs = new_run
            self._vehicle_fuel_logs = new_fuel
            self._vehicle_cost_logs = new_cost
            if removed:
                status_text = f"차량기록 {changed}건 동기화, 삭제 {removed}건 반영"
            else:
                status_text = f"차량기록 {changed}건 반영"
            self._app_settings["vehicle_server_sync_last_status"] = status_text
            self._storage.save_app_settings(self._app_settings)
            self.vehicles_changed.emit()
            self._save_database_snapshot(sync_latest_backup=False, backup_reason="vehicle-mobile-log-sync")
            if not silent:
                self._emit_server_sync_notice(status_text)
        else:
            self._app_settings["vehicle_server_sync_last_status"] = "차량기록 확인 완료"
            self._storage.save_app_settings(self._app_settings)
            self._emit_settings_changed_without_dirty()
            if not silent:
                self._emit_server_sync_notice("차량기록 확인 완료")

    def _handle_vehicle_log_pull_error(self, message: str, *, silent: bool = True) -> None:
        text = str(message or "차량기록 불러오기 실패").strip() or "차량기록 불러오기 실패"
        self._app_settings["vehicle_server_sync_enabled"] = True
        self._app_settings["vehicle_server_sync_last_status"] = "모바일 차량기록 불러오기 실패"
        self._app_settings["vehicle_server_sync_last_error"] = text
        self._app_settings["vehicle_server_sync_last_at"] = datetime.now().isoformat(timespec="seconds")
        self._storage.save_app_settings(self._app_settings)
        self._emit_settings_changed_without_dirty()
        if not silent:
            self._emit_server_sync_notice(text)

    def _cleanup_vehicle_log_pull_worker(self) -> None:
        worker = self._vehicle_log_pull_worker
        self._vehicle_log_pull_worker = None
        if worker is not None:
            worker.deleteLater()
        if not self.is_server_sync_running():
            self._manual_sync_requested = False
            self._suppress_server_sync_notice = False
            self._emit_server_sync_notice("동기화 대기")


    def _sanitize_employee_reference_snapshot(self, snapshot: dict[str, dict | list]) -> dict[str, dict | list]:
        employee_rows = snapshot.get("employees", self._employees)
        valid_employee_ids: set[int] = set()
        for row in employee_rows or []:
            try:
                employee_id = int((row or {}).get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id > 0:
                valid_employee_ids.add(employee_id)

        def _keep_employee_keyed_rows(source: dict) -> dict:
            cleaned: dict = {}
            for key, value in (source or {}).items():
                employee_key = None
                if isinstance(key, tuple) and key:
                    employee_key = key[0]
                else:
                    employee_key = key
                try:
                    employee_id = int(employee_key or 0)
                except (TypeError, ValueError):
                    continue
                if employee_id in valid_employee_ids:
                    cleaned[key] = deepcopy(value)
            return cleaned

        if "monthly_records" in snapshot:
            snapshot["monthly_records"] = _keep_employee_keyed_rows(snapshot.get("monthly_records", {}))
        if "payroll_month_inputs" in snapshot:
            snapshot["payroll_month_inputs"] = _keep_employee_keyed_rows(snapshot.get("payroll_month_inputs", {}))
        if "payroll_adjustments" in snapshot:
            snapshot["payroll_adjustments"] = _keep_employee_keyed_rows(snapshot.get("payroll_adjustments", {}))
        return snapshot

    def _build_shared_settings_snapshot(self) -> dict:
        """PC별 환경값을 제외한 회사 운영 공용 설정만 snapshot에 포함합니다."""
        shared: dict[str, dict] = {}
        try:
            holiday_settings = load_holiday_api_settings(self._storage.config_dir)
        except Exception:
            holiday_settings = {}
        if isinstance(holiday_settings, dict):
            service_key = str(holiday_settings.get("service_key", "") or "").strip()
            # 빈 인증키만 있는 PC가 서버의 기존 인증키를 덮어쓰지 않게,
            # 인증키가 있거나 자동갱신을 켠 경우에만 공유 설정으로 올립니다.
            if service_key or bool(holiday_settings.get("enabled", False)):
                shared["holiday_api"] = {
                    "enabled": bool(holiday_settings.get("enabled", False)),
                    "service_key": service_key,
                    "years": deepcopy(holiday_settings.get("years") or []),
                    "api_url": str(holiday_settings.get("api_url") or "").strip(),
                    "last_sync": str(holiday_settings.get("last_sync") or ""),
                    "last_error": str(holiday_settings.get("last_error") or ""),
                }
        return shared

    def _apply_shared_settings_snapshot(self, shared_settings: dict | None) -> bool:
        """서버 snapshot의 회사 공용 설정을 이 PC에 반영합니다.

        서버 주소, 백업 폴더, 창 위치 같은 PC별 환경값은 여기서 다루지 않습니다.
        공휴일 자동갱신 인증키처럼 회사 공용 설정이 동기화되면 저장만 하지 않고
        즉시 설정 화면과 공휴일 캐시 갱신까지 이어지도록 처리합니다.
        """
        if not isinstance(shared_settings, dict):
            return False
        changed = False
        should_run_holiday_sync = False
        holiday_payload = shared_settings.get("holiday_api")
        if isinstance(holiday_payload, dict):
            current = self.holiday_api_settings()
            incoming_key = str(holiday_payload.get("service_key", "") or "").strip()
            current_key = str(current.get("service_key", "") or "").strip()
            # 빈 서버 값이 이미 입력된 PC 인증키를 지우지 않도록 보호합니다.
            should_apply = bool(incoming_key) or not current_key
            if should_apply:
                merged = dict(current)
                for key in ("enabled", "service_key", "years", "api_url", "last_sync", "last_error"):
                    if key in holiday_payload:
                        merged[key] = deepcopy(holiday_payload.get(key))
                saved = save_holiday_api_settings(self._storage.config_dir, merged)
                holiday_changed = saved != current
                changed = changed or holiday_changed
                if holiday_changed:
                    _clear_holiday_cache()
                    self.settings_changed.emit()
                    self.holidays_changed.emit("공휴일 자동갱신 설정을 서버 동기화로 반영했습니다.")
                if saved.get("enabled") and str(saved.get("service_key", "") or "").strip():
                    # PC2가 인증키를 받은 직후에도 '지금 갱신'을 따로 누르지 않게 한다.
                    # 워커 중복 실행은 sync_holidays_async 내부에서 차단된다.
                    should_run_holiday_sync = True
        if should_run_holiday_sync:
            QTimer.singleShot(1200, lambda: self.sync_holidays_async(manual=True))
        return changed

    def _build_database_snapshot(self, sections: set[str] | None = None) -> dict:
        sections = set(sections or DIRTY_SECTION_ALL)
        snapshot: dict[str, dict | list] = {}
        if "core_people" in sections:
            snapshot["businesses"] = deepcopy(self._businesses)
            snapshot["work_sites"] = deepcopy(self._work_sites)
            snapshot["employees"] = deepcopy(self._employees)
            snapshot["manager_accounts"] = deepcopy(self._manager_accounts)
        if "attendance" in sections:
            snapshot["attendance_events"] = deepcopy(self._attendance_events)
        if "settings" in sections:
            snapshot["score_settings"] = deepcopy(self._score_settings)
            snapshot["rejoin_grades"] = deepcopy(self._rejoin_grades)
            snapshot["shared_settings"] = self._build_shared_settings_snapshot()
        if "records" in sections:
            snapshot["monthly_records"] = deepcopy(self._monthly_records)
        if "payroll" in sections:
            snapshot["payroll_site_settings"] = deepcopy(self._payroll_settings_by_site)
            snapshot["payroll_setting_presets"] = deepcopy(self._payroll_setting_presets_by_site)
            snapshot["site_time_conversion_rules"] = deepcopy(self._site_time_conversion_rules)
            snapshot["payroll_detail_items"] = deepcopy(self._payroll_detail_items_by_site)
            snapshot["payroll_item_presets"] = deepcopy(self._payroll_item_presets_by_site)
            snapshot["payroll_month_inputs"] = deepcopy(self._payroll_month_inputs)
            snapshot["payroll_adjustments"] = deepcopy(self._individual_payroll_adjustments)
            snapshot["attendance_month_locks"] = deepcopy(self._attendance_month_locks)
        if "vehicles" in sections:
            snapshot["vehicles"] = deepcopy(self._vehicles)
            snapshot["vehicle_run_logs"] = deepcopy(self._vehicle_run_logs)
            snapshot["vehicle_fuel_logs"] = deepcopy(self._vehicle_fuel_logs)
            snapshot["vehicle_cost_logs"] = deepcopy(self._vehicle_cost_logs)
            snapshot["vehicle_alert_settings"] = deepcopy(self._vehicle_alert_settings)
        snapshot = self._sanitize_employee_reference_snapshot(snapshot)
        return snapshot

    def _build_server_snapshot_payload(self) -> dict:
        snapshot = self._build_database_snapshot(set(DIRTY_SECTION_ALL))
        return {
            "app_name": APP_SETTINGS_NAME,
            "storage_version": STORAGE_VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "snapshot": _encode_server_value(snapshot),
        }

    def _decode_server_snapshot_payload(self, payload: dict | None) -> tuple[dict, str]:
        if not isinstance(payload, dict):
            return {}, ""
        updated_at = str(payload.get("updated_at") or "").strip()
        encoded_snapshot = payload.get("snapshot")
        decoded = _decode_server_value(encoded_snapshot)
        return (decoded if isinstance(decoded, dict) else {}), updated_at

    def _apply_database_snapshot(self, snapshot: dict):
        score_settings = deepcopy(snapshot.get("score_settings") or self._default_score_settings)
        rejoin_grades = deepcopy(snapshot.get("rejoin_grades") or self._default_rejoin_grades)
        self._score_settings = score_settings
        self._rejoin_grades = rejoin_grades
        employees = snapshot.get("employees") or []
        self._employees = [normalize_employee(row, self._score_settings, self._rejoin_grades) for row in employees]
        self._manager_accounts = self._normalize_manager_accounts(snapshot.get("manager_accounts") or [])
        self._download_missing_employee_portraits()
        business_rows = snapshot.get("businesses")
        work_site_rows = snapshot.get("work_sites")
        attendance_rows = snapshot.get("attendance_events")
        self._businesses = [self._attach_business_defaults(row) for row in (business_rows if business_rows is not None else self._build_default_businesses())]
        self._businesses.sort(key=lambda row: row["name"])
        self._work_sites = [self._attach_work_site_defaults(row) for row in (work_site_rows if work_site_rows is not None else self._build_default_work_sites())]
        self._work_sites.sort(key=lambda row: (row["business_name"], row["name"]))
        self._attendance_events = deepcopy(attendance_rows if attendance_rows is not None else self._build_default_events())
        self._monthly_records = deepcopy(snapshot.get("monthly_records") or {})
        self._payroll_settings_by_site = deepcopy(snapshot.get("payroll_site_settings") or {})
        self._payroll_setting_presets_by_site = deepcopy(snapshot.get("payroll_setting_presets") or {})
        raw_time_rules = snapshot.get("site_time_conversion_rules") or snapshot.get("time_conversion_rules") or []
        self._site_time_conversion_rules = [
            _normalize_site_time_conversion_rule(row, idx + 1)
            for idx, row in enumerate(raw_time_rules if isinstance(raw_time_rules, list) else [])
        ]
        self.ensure_work_sites_from_time_conversion_rules(self._site_time_conversion_rules, emit=False)
        self._payroll_detail_items_by_site = deepcopy(snapshot.get("payroll_detail_items") or {})
        self._payroll_item_presets_by_site = deepcopy(snapshot.get("payroll_item_presets") or {})
        self._repair_payroll_preset_collections()
        self._payroll_month_inputs = deepcopy(snapshot.get("payroll_month_inputs") or {})
        self._attendance_month_locks = self._normalize_attendance_month_locks(snapshot.get("attendance_month_locks") or {})
        self._individual_payroll_adjustments = deepcopy(snapshot.get("payroll_adjustments") or {})
        vehicle_rows = snapshot.get("vehicles")
        vehicle_run_rows = snapshot.get("vehicle_run_logs")
        vehicle_fuel_rows = snapshot.get("vehicle_fuel_logs")
        vehicle_cost_rows = snapshot.get("vehicle_cost_logs")
        self._vehicles = deepcopy(vehicle_rows if vehicle_rows is not None else [])
        self._repair_vehicle_location_fields()
        self._vehicle_run_logs = deepcopy(vehicle_run_rows if vehicle_run_rows is not None else [])
        self._vehicle_fuel_logs = deepcopy(vehicle_fuel_rows if vehicle_fuel_rows is not None else [])
        self._vehicle_cost_logs = deepcopy(vehicle_cost_rows if vehicle_cost_rows is not None else [])
        self._vehicle_alert_settings = deepcopy(snapshot.get("vehicle_alert_settings") or VEHICLE_ALERT_SETTINGS)
        self._apply_shared_settings_snapshot(snapshot.get("shared_settings") or {})
        self._payroll_active_month = None

    def _save_database_snapshot(self, *, sync_latest_backup: bool = False, backup_reason: str = "auto-save", force_full: bool = False):
        if getattr(self, "_db_is_loading", False) or getattr(self, "_db_is_saving", False):
            return
        pending_sections = set(DIRTY_SECTION_ALL) if force_full else set(self._dirty_sections)
        should_push_server_snapshot = bool(pending_sections) and str(backup_reason or "") not in SERVER_SNAPSHOT_SKIP_PUSH_REASONS
        self._db_is_saving = True
        self._autosave_timer.stop()
        try:
            if pending_sections:
                self._db.save_snapshot(self._build_database_snapshot(pending_sections), sections=pending_sections)
                self._dirty_sections.difference_update(pending_sections)
            if sync_latest_backup:
                self._storage.sync_latest_backup(include_files=False, include_settings=True, reason=backup_reason)
        finally:
            self._db_is_saving = False
        self.save_completed.emit(str(backup_reason or ""))
        if should_push_server_snapshot:
            self._schedule_server_snapshot_push()

    def backup_now(self, include_history: bool = True):
        self._autosave_timer.stop()
        self._save_database_snapshot(sync_latest_backup=False, backup_reason="manual", force_full=not bool(self._dirty_sections))
        self._storage.sync_latest_backup(include_files=True, include_settings=True, reason="manual")
        if include_history:
            self._storage.create_history_backup(reason="manual", include_files=True, include_settings=True)

    def prepare_for_exit(self):
        if getattr(self, "_is_preparing_exit", False):
            return
        self._is_preparing_exit = True
        self._autosave_timer.stop()
        try:
            self._save_database_snapshot(sync_latest_backup=False, backup_reason="shutdown", force_full=not bool(self._dirty_sections))
            self._attempt_shutdown_server_sync()
            self._storage.sync_latest_backup(include_files=True, include_settings=True, reason="shutdown")
            self._storage.create_history_backup(reason="shutdown", include_files=True, include_settings=True)
        except Exception:
            self._is_preparing_exit = False
            raise

    def _attempt_shutdown_server_sync(self) -> None:
        """프로그램 종료 직전 전체 스냅샷을 한 번 서버에 전송합니다.

        실패해도 로컬 자료와 백업은 유지되며, 다음 실행 또는 다음 자동 동기화 때 다시 전송됩니다.
        """
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "") or "").strip():
            return
        try:
            payload = self._build_server_snapshot_payload()
            self._push_server_snapshot_payload(deepcopy(settings), payload)
            now_text = datetime.now().isoformat(timespec="seconds")
            self._app_settings["last_employee_sync_status"] = "종료 시 차량 상세기록 포함 서버 저장 완료"
            self._app_settings["last_employee_sync_error"] = ""
            self._app_settings["last_employee_sync_at"] = now_text
            self._app_settings["vehicle_server_sync_enabled"] = True
            self._app_settings["vehicle_server_sync_last_status"] = "종료 시 차량 상세기록 포함 서버 저장 완료"
            self._app_settings["vehicle_server_sync_last_error"] = ""
            self._app_settings["vehicle_server_sync_last_at"] = now_text
            self._storage.save_app_settings(self._app_settings)
        except Exception as exc:
            now_text = datetime.now().isoformat(timespec="seconds")
            error_text = str(exc or "").strip()
            self._app_settings["last_employee_sync_error"] = f"종료 시 차량 상세기록 서버 저장 실패: {error_text}"
            self._app_settings["vehicle_server_sync_enabled"] = True
            self._app_settings["vehicle_server_sync_last_status"] = "종료 시 차량 상세기록 서버 저장 실패"
            self._app_settings["vehicle_server_sync_last_error"] = error_text
            self._app_settings["vehicle_server_sync_last_at"] = now_text
            self._storage.save_app_settings(self._app_settings)

    def _remove_known_test_seed_data(self) -> bool:
        """압축 배포본에 섞인 테스트 자료를 안전하게 정리합니다."""
        removed_employee_ids: set[int] = set()
        changed = False

        def _employee_is_test(row: dict) -> bool:
            try:
                employee_id = int((row or {}).get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            name = str((row or {}).get("name") or "").strip()
            return employee_id in TEST_EMPLOYEE_IDS_TO_REMOVE or name in TEST_EMPLOYEE_NAMES_TO_REMOVE

        kept_employees: list[dict] = []
        for row in self._employees:
            if _employee_is_test(row):
                try:
                    removed_employee_ids.add(int(row.get("id", 0) or 0))
                except (TypeError, ValueError, AttributeError):
                    pass
                changed = True
            else:
                kept_employees.append(row)
        self._employees = kept_employees

        if removed_employee_ids:
            self._attendance_events = [row for row in self._attendance_events if self._pending_entry_employee_id(row) not in removed_employee_ids]
            self._monthly_records = {key: value for key, value in self._monthly_records.items() if int(key[0]) not in removed_employee_ids}
            self._payroll_month_inputs = {key: value for key, value in self._payroll_month_inputs.items() if int(key[0]) not in removed_employee_ids}
            self._individual_payroll_adjustments = {key: value for key, value in self._individual_payroll_adjustments.items() if int(key[0]) not in removed_employee_ids}
            self._pending_employee_sync = [row for row in self._pending_employee_sync if self._pending_entry_employee_id(row) not in removed_employee_ids]
            for employee_id in removed_employee_ids:
                try:
                    target_dir = self._storage.employee_files_dir / str(employee_id)
                    if target_dir.exists():
                        shutil.rmtree(target_dir)
                except Exception:
                    pass

        before_business_count = len(self._businesses)
        self._businesses = [row for row in self._businesses if str((row or {}).get("name") or "").strip() not in TEST_BUSINESS_NAMES_TO_REMOVE]
        changed = changed or len(self._businesses) != before_business_count

        before_site_count = len(self._work_sites)
        self._work_sites = [
            row for row in self._work_sites
            if str((row or {}).get("business_name") or "").strip() not in TEST_BUSINESS_NAMES_TO_REMOVE
            and str((row or {}).get("name") or "").strip() not in TEST_WORK_SITE_NAMES_TO_REMOVE
        ]
        changed = changed or len(self._work_sites) != before_site_count

        for target in [
            self._payroll_settings_by_site,
            self._payroll_setting_presets_by_site,
            self._payroll_detail_items_by_site,
            self._payroll_item_presets_by_site,
        ]:
            for key in list(target.keys()):
                if key in TEST_PAYROLL_SITE_KEYS_TO_REMOVE or str(key).startswith("테스트사업자::"):
                    target.pop(key, None)
                    changed = True

        if changed:
            self._save_pending_employee_sync()
            self._dirty_sections.update(DIRTY_SECTION_ALL)
        return changed

    def _seed_monthly_records_from_events(self) -> bool:
        return seed_monthly_records_from_events(
            self._monthly_records,
            self._attendance_events,
            STATUS_TYPES,
        )

    def _default_payroll_settings(self) -> dict:
        return {
            "work_type": "교대",
            "pay_type": "시급제",
            "day_hourly_rate": 10320,  # 엑셀 기준
            "night_hourly_rate": 15480, # 1.5배
            "night_multiplier": 1.5,
            "day_start": "08:00",
            "day_end": "17:00",
            "night_start": "22:00",
            "night_end": "06:00",
            "shift_start_group": "주간",
            "attendance_base_hours": 8.0,
            "attendance_over_hours": 0.0,
            "attendance_night_hours": 8.0,
            "late_deduct": 0,
            "absent_deduct": 0,
            "unauthorized_absence_deduct": 0,
            "severance_method": "both",
            "severance_multiplier": 1.0,
            "default_meal_deduct": 31500, # 엑셀 식대 기본값 예시
            "hospital_payroll_treatment": "결근",
            "hospital_hours_mode": "0시간",
            "hospital_note": "",
            "late_payroll_treatment": "근무",
            "late_hours_mode": "기본시간 적용",
            "late_note": "",
            "early_leave_payroll_treatment": "근무",
            "early_leave_hours_mode": "기본시간 적용",
            "early_leave_note": "",
        }

    # ──────────── 개인별 월 급여 세금/수당/공제 (오버라이드) ────────────
    def default_payroll_settings(self) -> dict:
        return deepcopy(self._default_payroll_settings())

    def get_individual_adjustment(self, employee_id: int, month_str: str) -> dict:
        """month_str format: 'yyyy-MM', returns dict with tax and custom deduct amounts."""
        return deepcopy(self._individual_payroll_adjustments.get((employee_id, month_str), {}))

    def set_individual_adjustment(self, employee_id: int, month_str: str, data: dict):
        self._individual_payroll_adjustments[(employee_id, month_str)] = deepcopy(data)
        self.payroll_changed.emit()

    def get_payroll_detail_item_configs(self, work_site_name: str | None = None, business_name: str | None = None) -> list[dict]:
        key, _bundle = self._ensure_payroll_item_bundle(work_site_name, business_name)
        source = self._payroll_detail_items_by_site.get(key) or [_normalize_payroll_detail_item(row, idx + 1) for idx, row in enumerate(DEFAULT_PAYROLL_DETAIL_ITEMS)]
        return [deepcopy(row) for row in sorted(source, key=lambda item: (int(item.get("order", 0)), str(item.get("label", ""))))]

    def set_payroll_detail_item_configs(self, rows: list[dict], work_site_name: str | None = None, business_name: str | None = None):
        self._consume_legacy_payroll_site_key(work_site_name, business_name)
        key, bundle = self._ensure_payroll_item_bundle(work_site_name, business_name)
        cleaned: list[dict] = []
        used_keys: set[str] = set()
        for idx, row in enumerate(rows or [], start=1):
            normalized = _normalize_payroll_detail_item(row, idx)
            key = normalized["key"]
            if key in used_keys:
                suffix = 2
                new_key = f"{key}_{suffix}"
                while new_key in used_keys:
                    suffix += 1
                    new_key = f"{key}_{suffix}"
                normalized["key"] = new_key
            used_keys.add(normalized["key"])
            cleaned.append(normalized)
        if not cleaned:
            cleaned = [_normalize_payroll_detail_item(row, idx + 1) for idx, row in enumerate(DEFAULT_PAYROLL_DETAIL_ITEMS)]
        if key:
            self._payroll_detail_items_by_site[key] = cleaned
            active_name = str(bundle.get("active_preset", DEFAULT_PAYROLL_PRESET_NAME))
            bundle.setdefault("presets", {})[active_name] = deepcopy(cleaned)
            self._payroll_item_presets_by_site[key] = bundle
        self.settings_changed.emit()
        self.payroll_changed.emit()

    def _move_payroll_site_settings(
        self,
        old_work_site_name: str | None,
        old_business_name: str | None,
        new_work_site_name: str | None,
        new_business_name: str | None,
    ) -> bool:
        old_key = _make_work_site_setting_key(old_work_site_name, old_business_name)
        new_key = _make_work_site_setting_key(new_work_site_name, new_business_name)
        if not old_key or old_key == new_key:
            return False

        changed = False
        if old_key in self._payroll_setting_presets_by_site:
            if new_key not in self._payroll_setting_presets_by_site:
                self._payroll_setting_presets_by_site[new_key] = deepcopy(self._payroll_setting_presets_by_site[old_key])
            del self._payroll_setting_presets_by_site[old_key]
            changed = True
        if old_key in self._payroll_item_presets_by_site:
            if new_key not in self._payroll_item_presets_by_site:
                self._payroll_item_presets_by_site[new_key] = deepcopy(self._payroll_item_presets_by_site[old_key])
            del self._payroll_item_presets_by_site[old_key]
            changed = True
        if old_key in self._payroll_settings_by_site:
            if new_key not in self._payroll_settings_by_site:
                self._payroll_settings_by_site[new_key] = deepcopy(self._payroll_settings_by_site[old_key])
            del self._payroll_settings_by_site[old_key]
            changed = True

        if old_key in self._payroll_detail_items_by_site:
            if new_key not in self._payroll_detail_items_by_site:
                self._payroll_detail_items_by_site[new_key] = deepcopy(self._payroll_detail_items_by_site[old_key])
            del self._payroll_detail_items_by_site[old_key]
            changed = True

        old_site = _normalize_work_site_name(old_work_site_name)
        old_business = _normalize_business_name(old_business_name) if old_business_name is not None else ""
        new_site = _normalize_work_site_name(new_work_site_name)
        new_business = _normalize_business_name(new_business_name) if new_business_name is not None else ""
        for row in self._site_time_conversion_rules:
            row_site = _normalize_work_site_name(row.get("work_site_name"))
            row_business = _normalize_business_name(row.get("business_name")) if str(row.get("business_name", "") or "").strip() else ""
            if row_site == old_site and (not old_business or row_business == old_business):
                row["work_site_name"] = new_site
                if new_business:
                    row["business_name"] = new_business
                changed = True

        return changed

    def _move_payroll_business_settings(self, old_business_name: str | None, new_business_name: str | None) -> bool:
        old_name = _normalize_business_name(old_business_name)
        new_name = _normalize_business_name(new_business_name)
        if old_name == new_name:
            return False

        changed = False
        keys = set(self._payroll_settings_by_site.keys()) | set(self._payroll_detail_items_by_site.keys()) | set(self._payroll_setting_presets_by_site.keys()) | set(self._payroll_item_presets_by_site.keys())
        for key in sorted(keys):
            business_name, work_site_name = _split_work_site_setting_key(key)
            if business_name == old_name:
                changed = self._move_payroll_site_settings(work_site_name, old_name, work_site_name, new_name) or changed
        return changed

    def _consume_legacy_payroll_site_key(self, work_site_name: str | None, business_name: str | None = None) -> bool:
        legacy_key = _make_work_site_setting_key(work_site_name)
        new_key = _make_work_site_setting_key(work_site_name, business_name)
        if not legacy_key or legacy_key == new_key:
            return False

        changed = False
        if legacy_key in self._payroll_setting_presets_by_site:
            if new_key not in self._payroll_setting_presets_by_site:
                self._payroll_setting_presets_by_site[new_key] = deepcopy(self._payroll_setting_presets_by_site[legacy_key])
            del self._payroll_setting_presets_by_site[legacy_key]
            changed = True
        if legacy_key in self._payroll_item_presets_by_site:
            if new_key not in self._payroll_item_presets_by_site:
                self._payroll_item_presets_by_site[new_key] = deepcopy(self._payroll_item_presets_by_site[legacy_key])
            del self._payroll_item_presets_by_site[legacy_key]
            changed = True
        if legacy_key in self._payroll_settings_by_site:
            if new_key not in self._payroll_settings_by_site:
                self._payroll_settings_by_site[new_key] = deepcopy(self._payroll_settings_by_site[legacy_key])
            del self._payroll_settings_by_site[legacy_key]
            changed = True

        if legacy_key in self._payroll_detail_items_by_site:
            if new_key not in self._payroll_detail_items_by_site:
                self._payroll_detail_items_by_site[new_key] = deepcopy(self._payroll_detail_items_by_site[legacy_key])
            del self._payroll_detail_items_by_site[legacy_key]
            changed = True

        return changed

    def get_payroll_detail_payload(self, employee_id: int, month_str: str) -> dict:
        employee_id = int(employee_id)
        month_key = str(month_str).strip()
        entry = self.get_payroll_month_entry(employee_id, month_key)
        employee = self.get_employee_by_id(employee_id) or {}
        payroll_settings = self.get_employee_payroll_settings(employee)
        adjustments = self.get_individual_adjustment(employee_id, month_key)
        configs = self.get_employee_payroll_detail_item_configs(employee)

        def _sum_hours(name: str) -> float:
            return sum(float(entry.get(name, {}).get(day, 0) or 0) for day in range(1, 32))

        base_hours = _sum_hours("base")
        over_hours = _sum_hours("over")
        night_hours = _sum_hours("night")
        total_hours = base_hours + over_hours + night_hours
        year, month = map(int, month_key.split("-"))
        days_in_month = monthrange(year, month)[1]
        try:
            default_hourly_rate = float(adjustments.get("hourly_rate", payroll_settings.get("day_hourly_rate", 10320)) or 0)
        except (TypeError, ValueError):
            default_hourly_rate = 0.0
        hourly_rate = default_hourly_rate

        base_amount = 0.0
        active_monthly_segments: set[tuple[str, float]] = set()
        for day in range(1, days_in_month + 1):
            target_date = date(year, month, day)
            pay_terms = self.get_employee_pay_terms_for_date(employee_id, target_date)
            pay_type = str(pay_terms.get("pay_type") or employee.get("pay_type") or "시급제").strip() or "시급제"
            configured_amount = float(pay_terms.get("base_wage", 0) or 0)
            day_base = float(entry.get("base", {}).get(day, 0) or 0)
            day_over = float(entry.get("over", {}).get(day, 0) or 0)
            day_night = float(entry.get("night", {}).get(day, 0) or 0)
            day_total_hours = day_base + day_over + day_night
            daily_hourly_rate = configured_amount if pay_type == "시급제" and configured_amount > 0 else default_hourly_rate
            if pay_type == "시급제":
                base_amount += day_total_hours * daily_hourly_rate
                hourly_rate = daily_hourly_rate
            elif pay_type == "일급제":
                if day_total_hours > 0:
                    day_rate = configured_amount if configured_amount > 0 else daily_hourly_rate * max(float(payroll_settings.get("attendance_base_hours", 8.0) or 8.0), 1.0)
                    base_amount += day_rate
            else:
                monthly_salary = configured_amount
                if monthly_salary > 0:
                    active_monthly_segments.add((str(pay_terms.get("effective_date") or target_date.isoformat()), monthly_salary))

        for effective_date, monthly_salary in active_monthly_segments:
            try:
                start_date = datetime.strptime(effective_date, "%Y-%m-%d").date()
            except Exception:
                start_date = date(year, month, 1)
            segment_start = max(start_date, date(year, month, 1))
            segment_end = date(year, month, days_in_month)
            history = _normalize_pay_type_history(
                employee.get("pay_type_history"),
                employee.get("pay_type"),
                employee.get("base_wage", 0),
                employee.get("pay_effective_date") or employee.get("hire_date") or date.today().isoformat(),
            )
            next_dates = []
            for row in history:
                try:
                    next_date = datetime.strptime(str(row.get("effective_date") or ""), "%Y-%m-%d").date()
                except Exception:
                    continue
                if next_date > segment_start:
                    next_dates.append(next_date)
            if next_dates:
                segment_end = min(segment_end, min(next_dates) - timedelta(days=1))
            covered_days = max(0, (segment_end - segment_start).days + 1)
            if covered_days > 0:
                base_amount += monthly_salary * (covered_days / max(days_in_month, 1))

        allowance_total = 0.0
        deduction_total = 0.0
        manual_values: dict[str, float] = {}
        for row in configs:
            if row.get("group") == "summary":
                continue
            key = str(row.get("key", "") or "").strip()
            try:
                value = float(adjustments.get(key, row.get("default_value", 0)) or 0)
            except (TypeError, ValueError):
                value = 0.0
            manual_values[key] = value
            if row.get("group") == "allowance" and row.get("enabled", True):
                allowance_total += value
            elif row.get("group") == "deduction" and row.get("enabled", True):
                deduction_total += value

        gross_amount = base_amount + allowance_total
        net_amount = gross_amount - deduction_total
        summary_values = {
            "base_hours": base_hours,
            "over_hours": over_hours,
            "night_hours": night_hours,
            "total_hours": total_hours,
            "hourly_rate": hourly_rate,
            "base_amount": base_amount,
            "allowance_total": allowance_total,
            "gross_amount": gross_amount,
            "deduction_total": deduction_total,
            "net_amount": net_amount,
        }
        summary_rows = []
        allowance_rows = []
        deduction_rows = []
        for row in configs:
            if not row.get("enabled", True):
                continue
            key = row.get("key")
            value = summary_values.get(key, manual_values.get(key, row.get("default_value", 0)))
            payload_row = {**row, "value": float(value or 0)}
            if row.get("group") == "summary":
                summary_rows.append(payload_row)
            elif row.get("group") == "allowance":
                allowance_rows.append(payload_row)
            elif row.get("group") == "deduction":
                deduction_rows.append(payload_row)
        return {
            "summary": summary_rows,
            "allowance": allowance_rows,
            "deduction": deduction_rows,
            "summary_values": summary_values,
            "adjustments": adjustments,
            "effective_pay_type": self.get_employee_effective_pay_type(employee, date(year, month, 1)),
            "effective_work_type": self.get_employee_effective_work_type(employee),
            "payroll_settings": deepcopy(payroll_settings),
        }

    def _normalize_manager_accounts(self, rows) -> list[dict]:
        normalized_rows: list[dict] = []
        seen_usernames: set[str] = set()
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            username = str(row.get("username") or "").strip()
            if not username or username in seen_usernames:
                continue
            seen_usernames.add(username)
            try:
                employee_id = self._pending_entry_employee_id(row)
            except (TypeError, ValueError):
                employee_id = 0
            fallback_business = str(row.get("business") or "").strip()
            fallback_site = str(row.get("work_site") or row.get("site") or "").strip()
            work_sites: list[dict] = []
            raw_sites = row.get("work_sites")
            if isinstance(raw_sites, list):
                for item in raw_sites:
                    if isinstance(item, dict):
                        business = str(item.get("business") or item.get("business_name") or fallback_business or "").strip()
                        site = str(item.get("work_site") or item.get("site") or item.get("name") or "").strip()
                    else:
                        business = fallback_business
                        site = str(item or "").strip()
                    pair = {"business": business, "work_site": site}
                    if business and site and pair not in work_sites:
                        work_sites.append(pair)
            if not work_sites and fallback_business and fallback_site:
                work_sites.append({"business": fallback_business, "work_site": fallback_site})
            primary_business = work_sites[0]["business"] if work_sites else fallback_business
            primary_site = work_sites[0]["work_site"] if work_sites else fallback_site
            normalized_rows.append({
                "employee_id": employee_id,
                "employee_name": str(row.get("employee_name") or row.get("name") or "").strip(),
                "username": username,
                "password": str(row.get("password") or "").strip(),
                "role": str(row.get("role") or "manager").strip() or "manager",
                "active": bool(row.get("active", True)),
                "business": primary_business,
                "work_site": primary_site,
                "work_sites": work_sites,
                "phone": str(row.get("phone") or "").strip(),
                "note": str(row.get("note") or "").strip(),
                "created_at": str(row.get("created_at") or "").strip(),
                "updated_at": str(row.get("updated_at") or "").strip(),
            })
        normalized_rows.sort(key=lambda row: (row.get("business", ""), row.get("work_site", ""), row.get("employee_name", ""), row.get("username", "")))
        return normalized_rows

    def manager_accounts(self) -> list[dict]:
        return deepcopy(self._manager_accounts)


    @staticmethod
    def _is_super_admin_role(role: str | None) -> bool:
        role_key = str(role or "").strip().lower()
        return role_key in {"owner", "super", "super_admin", "admin", "최고관리자"}

    def _normalize_manager_role(self, role: str | None) -> str:
        return "super_admin" if self._is_super_admin_role(role) else "manager"

    def _active_super_admin_count(self, exclude_username: str = "") -> int:
        exclude_key = str(exclude_username or "").strip().lower()
        count = 0
        for account in self._manager_accounts:
            username = str(account.get("username") or "").strip().lower()
            if exclude_key and username == exclude_key:
                continue
            if bool(account.get("active", True)) and self._is_super_admin_role(account.get("role")):
                count += 1
        return count

    def ensure_default_super_admin_account(self) -> dict:
        """PC 최초 로그인용 최고관리자 계정을 보장합니다."""
        now_text = datetime.now().isoformat(timespec="seconds")
        for account in self._manager_accounts:
            if bool(account.get("active", True)) and self._is_super_admin_role(account.get("role")):
                return deepcopy(account)

        admin_index = -1
        for index, account in enumerate(self._manager_accounts):
            if str(account.get("username") or "").strip().lower() == "admin":
                admin_index = index
                break

        if admin_index >= 0:
            account = deepcopy(self._manager_accounts[admin_index])
            account["employee_name"] = str(account.get("employee_name") or "최고관리자").strip() or "최고관리자"
            account["username"] = str(account.get("username") or "admin").strip() or "admin"
            account["password"] = str(account.get("password") or "1234").strip() or "1234"
            account["role"] = "super_admin"
            account["active"] = True
            account["updated_at"] = now_text
            if not str(account.get("created_at") or "").strip():
                account["created_at"] = now_text
            self._manager_accounts[admin_index] = self._normalize_manager_accounts([account])[0]
            result = deepcopy(self._manager_accounts[admin_index])
        else:
            result = self._normalize_manager_accounts([{
                "employee_id": 0,
                "employee_name": "최고관리자",
                "username": "admin",
                "password": "1234",
                "role": "super_admin",
                "active": True,
                "business": "",
                "work_site": "",
                "work_sites": [],
                "phone": "",
                "note": "PC 최초 로그인용 기본 최고관리자 계정입니다.",
                "created_at": now_text,
                "updated_at": now_text,
            }])[0]
            self._manager_accounts.append(result)

        self._manager_accounts = self._normalize_manager_accounts(self._manager_accounts)
        self._dirty_sections.update({"core_people"})
        self._save_database_snapshot(sync_latest_backup=False, backup_reason="login-bootstrap")
        self.settings_changed.emit()
        return deepcopy(result)

    def authenticate_pc_admin(self, username: str, password: str) -> dict:
        """PC 로그인은 현재 최고관리자 계정만 허용합니다."""
        username = str(username or "").strip()
        password = str(password or "").strip()
        if not username:
            raise ValueError("아이디를 입력해 주세요.")
        if not password:
            raise ValueError("비밀번호를 입력해 주세요.")
        for account in self._manager_accounts:
            account_username = str(account.get("username") or "").strip()
            if account_username.lower() != username.lower():
                continue
            if not bool(account.get("active", True)):
                raise ValueError("사용 중지된 계정입니다.")
            if not self._is_super_admin_role(account.get("role")):
                raise ValueError("PC 프로그램은 현재 최고관리자 계정만 로그인할 수 있습니다.")
            if str(account.get("password") or "").strip() != password:
                raise ValueError("비밀번호가 맞지 않습니다.")
            result = deepcopy(account)
            result["role"] = "super_admin"
            return result
        raise ValueError("등록된 최고관리자 계정을 찾을 수 없습니다.")

    def pc_login_preferences(self) -> dict:
        keep_logged_in = bool(self._app_settings.get("pc_login_keep_logged_in", False))
        remember_password = bool(self._app_settings.get("pc_login_remember_password", False))
        remember_id = bool(self._app_settings.get("pc_login_remember_id", False)) or keep_logged_in or remember_password
        saved_password = str(self._app_settings.get("pc_login_saved_password", "") or "")
        return {
            "remember_id": remember_id,
            "remember_password": remember_password,
            "keep_logged_in": keep_logged_in,
            "saved_username": str(self._app_settings.get("pc_login_saved_username", "") or "").strip(),
            "saved_password": saved_password if remember_password else "",
        }

    def set_pc_login_preferences(
        self,
        *,
        remember_id: bool,
        keep_logged_in: bool,
        username: str,
        remember_password: bool = False,
        password: str = "",
    ) -> None:
        username = str(username or "").strip()
        password = str(password or "")
        keep_logged_in = bool(keep_logged_in)
        remember_password = bool(remember_password)
        remember_id = bool(remember_id) or keep_logged_in or remember_password

        self._app_settings["pc_login_remember_id"] = remember_id
        self._app_settings["pc_login_keep_logged_in"] = keep_logged_in
        self._app_settings["pc_login_remember_password"] = remember_password
        self._app_settings["pc_login_saved_username"] = username if (remember_id or keep_logged_in or remember_password) else ""
        self._app_settings["pc_login_saved_password"] = password if remember_password else ""
        self._storage.save_app_settings(self._app_settings)

    def auto_login_pc_admin(self) -> dict | None:
        prefs = self.pc_login_preferences()
        if not bool(prefs.get("keep_logged_in", False)):
            return None
        saved_username = str(prefs.get("saved_username", "") or "").strip()
        if not saved_username:
            return None
        for account in self._manager_accounts:
            account_username = str(account.get("username") or "").strip()
            if account_username.lower() != saved_username.lower():
                continue
            if not bool(account.get("active", True)):
                return None
            if not self._is_super_admin_role(account.get("role")):
                return None
            result = deepcopy(account)
            result["role"] = "super_admin"
            return result
        return None

    def _manager_site_pairs(self, account: dict) -> list[dict]:
        pairs: list[dict] = []
        fallback_business = str((account or {}).get("business", "") or "").strip()
        fallback_site = str((account or {}).get("work_site", "") or (account or {}).get("site", "") or "").strip()
        raw_sites = (account or {}).get("work_sites")
        if isinstance(raw_sites, list):
            for item in raw_sites:
                if isinstance(item, dict):
                    business = str(item.get("business") or item.get("business_name") or fallback_business or "").strip()
                    site = str(item.get("work_site") or item.get("site") or item.get("name") or "").strip()
                else:
                    business = fallback_business
                    site = str(item or "").strip()
                pair = {"business": business, "work_site": site}
                if business and site and pair not in pairs:
                    pairs.append(pair)
        if not pairs and fallback_business and fallback_site:
            pairs.append({"business": fallback_business, "work_site": fallback_site})
        return pairs

    def _manager_names_for_site(self, business_name: str, work_site_name: str) -> list[str]:
        business_key = _normalize_business_name(business_name)
        site_key = _normalize_work_site_name(work_site_name)
        names: list[str] = []
        for account in self._manager_accounts:
            if not account.get("active", True):
                continue
            for pair in self._manager_site_pairs(account):
                if (
                    _normalize_business_name(pair.get("business")) == business_key
                    and _normalize_work_site_name(pair.get("work_site")) == site_key
                ):
                    name = _clean_text(account.get("employee_name"))
                    if name and name not in names:
                        names.append(name)
        return names

    def _manager_display_for_site(self, business_name: str, work_site_name: str) -> str:
        names = self._manager_names_for_site(business_name, work_site_name)
        if not names:
            return ""
        if len(names) == 1:
            return names[0]
        return f"{names[0]} 외 {len(names) - 1}명"

    def _set_work_site_manager_name(self, business_name: str, work_site_name: str, manager_name: str) -> bool:
        business_name = _normalize_business_name(business_name)
        work_site_name = _normalize_work_site_name(work_site_name)
        manager_name = _clean_text(manager_name)
        if not business_name or not work_site_name:
            return False
        for index, row in enumerate(self._work_sites):
            if row.get("business_name") == business_name and row.get("name") == work_site_name:
                updated_row = deepcopy(row)
                current_names = [name.strip() for name in str(updated_row.get("manager_name") or "").split(",") if name.strip()]
                if manager_name and manager_name not in current_names:
                    current_names.append(manager_name)
                display_name = current_names[0] if len(current_names) == 1 else f"{current_names[0]} 외 {len(current_names) - 1}명" if current_names else ""
                updated_row["manager_name"] = display_name
                original_form = deepcopy(updated_row.get("original_form") or {})
                original_form["manager_name"] = display_name
                updated_row["original_form"] = original_form
                self._work_sites[index] = updated_row
                return True
        return False

    def _clear_work_site_manager_name(self, business_name: str, work_site_name: str, manager_name: str) -> bool:
        business_name = _normalize_business_name(business_name)
        work_site_name = _normalize_work_site_name(work_site_name)
        manager_name = _clean_text(manager_name)
        if not business_name or not work_site_name or not manager_name:
            return False
        for index, row in enumerate(self._work_sites):
            if row.get("business_name") == business_name and row.get("name") == work_site_name:
                updated_row = deepcopy(row)
                updated_row["manager_name"] = self._manager_display_for_site(business_name, work_site_name)
                original_form = deepcopy(updated_row.get("original_form") or {})
                original_form["manager_name"] = updated_row["manager_name"]
                updated_row["original_form"] = original_form
                self._work_sites[index] = updated_row
                return True
        return False

    def add_or_update_manager_account(self, payload: dict) -> dict:
        payload = dict(payload or {})
        username = str(payload.get("username") or "").strip()
        if not username:
            raise ValueError("로그인 아이디를 입력해 주세요.")
        password = str(payload.get("password") or "").strip()
        if not password:
            raise ValueError("비밀번호를 입력해 주세요.")
        employee_name = str(payload.get("employee_name") or payload.get("name") or "").strip()
        if not employee_name:
            raise ValueError("담당자명을 입력해 주세요.")
        now_text = datetime.now().isoformat(timespec="seconds")
        try:
            employee_id = int(payload.get("employee_id", 0) or 0)
        except (TypeError, ValueError):
            employee_id = 0

        previous_account: dict | None = None
        for row in self._manager_accounts:
            if str(row.get("username") or "").strip() == username:
                previous_account = deepcopy(row)
                break

        assignment_keys = {"business", "work_site", "site", "work_sites"}
        has_assignment_payload = any(key in payload for key in assignment_keys)
        if has_assignment_payload:
            raw_work_sites = payload.get("work_sites")
            if not raw_work_sites:
                business = str(payload.get("business") or "").strip()
                site = str(payload.get("work_site") or payload.get("site") or "").strip()
                raw_work_sites = [{"business": business, "work_site": site}] if business and site else []
            business_value = str(payload.get("business") or "").strip()
            work_site_value = str(payload.get("work_site") or payload.get("site") or "").strip()
        else:
            raw_work_sites = deepcopy((previous_account or {}).get("work_sites") or [])
            business_value = str((previous_account or {}).get("business") or "").strip()
            work_site_value = str((previous_account or {}).get("work_site") or (previous_account or {}).get("site") or "").strip()

        role_value = payload.get("role")
        if role_value is None and previous_account:
            role_value = previous_account.get("role")

        account = {
            "employee_id": employee_id,
            "employee_name": employee_name,
            "username": username,
            "password": password,
            "role": self._normalize_manager_role(role_value),
            "active": bool(payload.get("active", True)),
            "business": business_value,
            "work_site": work_site_value,
            "work_sites": raw_work_sites,
            "phone": str(payload.get("phone") or "").strip(),
            "note": str(payload.get("note") or "").strip(),
            "created_at": now_text,
            "updated_at": now_text,
        }
        account = self._normalize_manager_accounts([account])[0]
        if previous_account and self._is_super_admin_role(previous_account.get("role")):
            if (not self._is_super_admin_role(account.get("role")) or not bool(account.get("active", True))) and self._active_super_admin_count(username) <= 0:
                raise ValueError("최고관리자 계정은 최소 1개 이상 사용 상태로 남아 있어야 합니다.")
        updated = False
        for index, row in enumerate(self._manager_accounts):
            if str(row.get("username") or "").strip() == username:
                existing_created_at = str(row.get("created_at") or "").strip() or now_text
                account["created_at"] = existing_created_at
                self._manager_accounts[index] = account
                updated = True
                break
        if not updated:
            self._manager_accounts.append(account)
        previous_pairs = self._manager_site_pairs(previous_account or {})
        new_pairs = self._manager_site_pairs(account)
        previous_name = str((previous_account or {}).get("employee_name") or account.get("employee_name") or "").strip()
        for pair in previous_pairs:
            if pair not in new_pairs or previous_name != account.get("employee_name") or not account.get("active", True):
                self._clear_work_site_manager_name(pair.get("business", ""), pair.get("work_site", ""), previous_name)
        if account.get("active", True):
            for pair in new_pairs:
                self._set_work_site_manager_name(pair.get("business", ""), pair.get("work_site", ""), account.get("employee_name", ""))

        self._manager_accounts = self._normalize_manager_accounts(self._manager_accounts)
        self._work_sites.sort(key=lambda row: (row["business_name"], row["name"]))
        self._dirty_sections.update({"core_people"})
        self._mark_dirty_and_schedule("employees")
        self.employees_changed.emit()
        self.settings_changed.emit()
        return deepcopy(account)

    def update_manager_account_assignment(self, username: str, business: str, work_site: str | list[str], active: bool, note: str = "", role: str | None = None, employee_name: str | None = None) -> dict:
        username = str(username or "").strip()
        if not username:
            raise ValueError("관리자 아이디를 찾을 수 없습니다.")
        now_text = datetime.now().isoformat(timespec="seconds")
        target_index = -1
        previous_account: dict | None = None
        for index, row in enumerate(self._manager_accounts):
            if str(row.get("username") or "").strip() == username:
                target_index = index
                previous_account = deepcopy(row)
                break
        if target_index < 0 or not previous_account:
            raise ValueError("관리자 계정을 찾을 수 없습니다.")

        if isinstance(work_site, list):
            selected_sites = [str(site or "").strip() for site in work_site if str(site or "").strip()]
        else:
            selected_sites = [str(work_site or "").strip()] if str(work_site or "").strip() else []
        work_site_pairs = [{"business": str(business or "").strip(), "work_site": site} for site in selected_sites if str(business or "").strip() and site]

        updated_account = deepcopy(previous_account)
        if employee_name is not None:
            clean_name = str(employee_name or "").strip()
            if not clean_name:
                raise ValueError("관리자명을 입력해 주세요.")
            updated_account["employee_name"] = clean_name
        updated_account["business"] = str(business or "").strip()
        updated_account["work_site"] = selected_sites[0] if selected_sites else ""
        updated_account["work_sites"] = work_site_pairs
        updated_account["active"] = bool(active)
        updated_account["note"] = str(note or "").strip()
        if role is not None:
            updated_account["role"] = self._normalize_manager_role(role)
        updated_account["updated_at"] = now_text
        updated_account = self._normalize_manager_accounts([updated_account])[0]
        if self._is_super_admin_role(previous_account.get("role")):
            if (not self._is_super_admin_role(updated_account.get("role")) or not bool(updated_account.get("active", True))) and self._active_super_admin_count(username) <= 0:
                raise ValueError("최고관리자 계정은 최소 1개 이상 사용 상태로 남아 있어야 합니다.")
        self._manager_accounts[target_index] = updated_account

        previous_pairs = self._manager_site_pairs(previous_account)
        new_pairs = self._manager_site_pairs(updated_account)
        previous_name = str(previous_account.get("employee_name") or "").strip()
        new_name = str(updated_account.get("employee_name") or "").strip()
        for pair in previous_pairs:
            if pair not in new_pairs or previous_name != new_name or not updated_account.get("active", True):
                self._clear_work_site_manager_name(pair.get("business", ""), pair.get("work_site", ""), previous_name)
        if updated_account.get("active", True):
            for pair in new_pairs:
                self._set_work_site_manager_name(pair.get("business", ""), pair.get("work_site", ""), new_name)

        self._manager_accounts = self._normalize_manager_accounts(self._manager_accounts)
        self._work_sites.sort(key=lambda row: (row["business_name"], row["name"]))
        self._dirty_sections.update({"core_people"})
        self._mark_dirty_and_schedule("employees")
        self.employees_changed.emit()
        self.settings_changed.emit()
        return deepcopy(updated_account)


    def delete_manager_account(self, username: str) -> bool:
        username = str(username or "").strip()
        if not username:
            raise ValueError("삭제할 관리자 아이디를 찾을 수 없습니다.")
        target_index = -1
        previous_account: dict | None = None
        for index, row in enumerate(self._manager_accounts):
            if str(row.get("username") or "").strip() == username:
                target_index = index
                previous_account = deepcopy(row)
                break
        if target_index < 0 or not previous_account:
            raise ValueError("관리자 계정을 찾을 수 없습니다.")
        if self._is_super_admin_role(previous_account.get("role")) and self._active_super_admin_count(username) <= 0:
            raise ValueError("최고관리자 계정은 최소 1개 이상 남아 있어야 합니다.")

        previous_pairs = self._manager_site_pairs(previous_account)
        del self._manager_accounts[target_index]
        self._manager_accounts = self._normalize_manager_accounts(self._manager_accounts)

        for pair in previous_pairs:
            business = pair.get("business", "")
            site = pair.get("work_site", "")
            for index, row in enumerate(self._work_sites):
                if _normalize_business_name(row.get("business_name")) == _normalize_business_name(business) and _normalize_work_site_name(row.get("name")) == _normalize_work_site_name(site):
                    updated_row = deepcopy(row)
                    updated_row["manager_name"] = self._manager_display_for_site(business, site)
                    original_form = deepcopy(updated_row.get("original_form") or {})
                    original_form["manager_name"] = updated_row["manager_name"]
                    updated_row["original_form"] = original_form
                    self._work_sites[index] = updated_row
                    break

        self._work_sites.sort(key=lambda row: (row["business_name"], row["name"]))
        self._dirty_sections.update({"core_people"})
        self._mark_dirty_and_schedule("employees")
        self.employees_changed.emit()
        self.settings_changed.emit()
        return True

    def change_manager_account_password(self, username: str, new_password: str) -> dict:
        username = str(username or "").strip()
        new_password = str(new_password or "").strip()
        if not username:
            raise ValueError("관리자 아이디를 찾을 수 없습니다.")
        if not new_password:
            raise ValueError("새 비밀번호를 입력해 주세요.")
        now_text = datetime.now().isoformat(timespec="seconds")
        for index, row in enumerate(self._manager_accounts):
            if str(row.get("username") or "").strip() == username:
                updated = deepcopy(row)
                updated["password"] = new_password
                updated["updated_at"] = now_text
                self._manager_accounts[index] = self._normalize_manager_accounts([updated])[0]
                self._dirty_sections.update({"core_people"})
                self._mark_dirty_and_schedule("employees")
                self.settings_changed.emit()
                return deepcopy(self._manager_accounts[index])
        raise ValueError("관리자 계정을 찾을 수 없습니다.")

    def _display_employees(self) -> list[dict]:
        return self._merge_pending_employee_rows(self._employees)

    @property
    def employees(self) -> list[dict]:
        return self._display_employees()

    def employee_display_number(self, employee_or_id) -> str:
        """화면에 보여줄 사원 표시번호입니다.

        실제 저장/동기화용 내부 고유번호는 그대로 두고,
        사용자가 보는 사원 번호만 0001 형식으로 통일합니다.
        사업자번호, 차량번호, 여권번호 등 다른 번호에는 적용하지 않습니다.
        """
        raw_id = employee_or_id
        if isinstance(employee_or_id, dict):
            raw_id = employee_or_id.get("id", 0)
        try:
            target_id = int(raw_id or 0)
        except (TypeError, ValueError):
            target_id = 0

        seen: set[int] = set()
        ordered_ids: list[int] = []
        for row in self._display_employees():
            try:
                employee_id = int((row or {}).get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id > 0 and employee_id not in seen:
                seen.add(employee_id)
                ordered_ids.append(employee_id)

        if target_id > 0:
            if target_id not in seen:
                ordered_ids.append(target_id)
            try:
                index = ordered_ids.index(target_id) + 1
                return f"{index:04d}"
            except ValueError:
                pass
        return "0000"

    def next_employee_display_number(self, employee_id: int | None = None) -> str:
        if employee_id is not None:
            return self.employee_display_number(employee_id)
        return f"{len(self._display_employees()) + 1:04d}"

    def server_api_settings(self) -> dict:
        self._storage.ensure_structure()
        return self._storage.load_server_api_settings({})

    def save_server_api_settings(self, payload: dict) -> dict:
        self._storage.ensure_structure()
        normalized_payload = dict(payload or {})
        normalized_payload["use_server"] = True
        self._storage.save_server_api_settings(normalized_payload)
        settings = self._storage.load_server_api_settings({})
        settings["use_server"] = True
        self._storage.save_server_api_settings(settings)
        self.settings_changed.emit()
        self._start_server_refresh()
        return settings


    @staticmethod
    def _safe_employee_id(value, default: int = 0) -> int:
        try:
            return int(value or default)
        except (TypeError, ValueError, AttributeError):
            return int(default or 0)

    def _pending_entry_employee_id(self, entry: dict | None) -> int:
        if not isinstance(entry, dict):
            return 0
        return self._safe_employee_id(entry.get("employee_id", 0), 0)

    def _is_sync_entry_blocked(self, entry: dict | None) -> bool:
        try:
            retry_count = int((entry or {}).get("retry_count", 0) or 0)
        except (TypeError, ValueError, AttributeError):
            retry_count = 0
        return retry_count >= MAX_SERVER_SYNC_RETRY

    def _pending_employee_sync_active_count(self) -> int:
        return sum(1 for row in self._pending_employee_sync if not self._is_sync_entry_blocked(row))

    def _pending_employee_sync_failed_count(self) -> int:
        return sum(1 for row in self._pending_employee_sync if self._is_sync_entry_blocked(row))

    def pending_employee_sync_count(self) -> int:
        return self._pending_employee_sync_active_count()

    def failed_employee_sync_count(self) -> int:
        return self._pending_employee_sync_failed_count()

    def is_server_mode_enabled(self) -> bool:
        settings = self.server_api_settings()
        return bool(str(settings.get("base_url", "")).strip())

    def is_server_sync_running(self) -> bool:
        worker_running = self._server_sync_worker is not None and self._server_sync_worker.isRunning()
        refresh_running = self._server_refresh_worker is not None and self._server_refresh_worker.isRunning()
        snapshot_push_running = self._server_snapshot_push_worker is not None and self._server_snapshot_push_worker.isRunning()
        snapshot_pull_running = self._server_snapshot_pull_worker is not None and self._server_snapshot_pull_worker.isRunning()
        vehicle_log_pull_running = self._vehicle_log_pull_worker is not None and self._vehicle_log_pull_worker.isRunning()
        return bool(worker_running or refresh_running or snapshot_push_running or snapshot_pull_running or vehicle_log_pull_running)

    def is_manual_server_sync_running(self) -> bool:
        return bool(self._manual_sync_requested and self.is_server_sync_running())

    def push_server_snapshot_now(self, silent: bool = False) -> bool:
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "")).strip():
            if not silent:
                self._emit_server_sync_notice("서버 주소 확인 필요")
            return False
        if self.is_server_sync_running() or getattr(self, "_server_snapshot_applying", False):
            if not silent:
                self._manual_sync_requested = True
                self._emit_server_sync_notice("동기화가 아직 진행 중입니다")
            return False
        self._suppress_server_sync_notice = bool(silent)
        self._manual_sync_requested = not bool(silent)
        if not silent:
            self._emit_server_sync_notice("서버 전체 저장 시작")
        self._start_server_snapshot_push()
        return True

    def pull_server_snapshot_now(self, silent: bool = False) -> bool:
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "")).strip():
            if not silent:
                self._emit_server_sync_notice("서버 주소 확인 필요")
            return False
        if self.is_server_sync_running() or getattr(self, "_server_snapshot_applying", False):
            if not silent:
                self._manual_sync_requested = True
                self._emit_server_sync_notice("동기화가 아직 진행 중입니다")
            return False
        if self._dirty_sections:
            if not silent:
                self._emit_server_sync_notice("PC 변경사항이 있습니다 · 동기화를 다시 눌러 서버 저장하세요")
            return False
        self._suppress_server_sync_notice = bool(silent)
        self._manual_sync_requested = not bool(silent)
        if not silent:
            self._emit_server_sync_notice("서버 전체 자료 불러오기 시작")
        if self._start_server_snapshot_pull(force=True):
            return True
        if not silent:
            self._emit_server_sync_notice("서버 전체 불러오기 시작 실패")
        return False

    def _local_snapshot_has_core_data(self) -> bool:
        try:
            if len(self._employees or []) > 0:
                return True
            if len(self._vehicles or []) > 0:
                return True
            if len(self._businesses or []) > 0:
                return True
            if len(self._work_sites or []) > 0:
                return True
            if len(self._monthly_records or {}) > 0:
                return True
            if len(self._payroll_month_inputs or {}) > 0:
                return True
            if len(self._attendance_month_locks or {}) > 0:
                return True
        except Exception:
            return False
        return False

    def sync_employees_now(self, silent: bool = False) -> bool:
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "")).strip():
            if not silent:
                self._emit_server_sync_notice("서버 주소 확인 필요")
            return False
        if self.is_server_sync_running() or getattr(self, "_server_snapshot_applying", False):
            if not silent:
                self._manual_sync_requested = True
                self._emit_server_sync_notice("동기화가 아직 진행 중입니다")
            return False
        self._suppress_server_sync_notice = bool(silent)
        self._manual_sync_requested = not bool(silent)
        pending_count = self._pending_employee_sync_active_count()
        failed_count = self._pending_employee_sync_failed_count()
        if not silent and pending_count <= 0 and failed_count > 0:
            for row in self._pending_employee_sync:
                if self._is_sync_entry_blocked(row):
                    row["retry_count"] = 0
                    row["last_error"] = ""
            self._save_pending_employee_sync()
            pending_count = self._pending_employee_sync_active_count()
            failed_count = self._pending_employee_sync_failed_count()
        if pending_count > 0:
            if not silent:
                self._emit_server_sync_notice(f"동기화 시작 · 대기 {pending_count}건")
            self._schedule_employee_server_sync(100)
            if self._server_sync_worker is None or not self._server_sync_worker.isRunning():
                self._start_employee_server_sync()
            return True

        if not silent:
            # 사용자는 기존처럼 동기화 버튼 하나만 누릅니다.
            # 내부에서는 PC 자료 보호를 위해 자동 판단합니다.
            # 1) 변경사항이 있으면 이 PC 자료를 서버 전체 스냅샷으로 저장합니다.
            # 2) 빈 PC 또는 이미 서버 스냅샷 기준을 가진 PC는 서버 전체 자료를 불러옵니다.
            # 3) 기존 자료는 있지만 아직 서버 스냅샷 기준 시간이 없는 대표 PC는 최초 1회 서버 저장을 우선합니다.
            if self._dirty_sections:
                self._emit_server_sync_notice("PC 변경사항 서버 전체 저장 시작")
                self._start_server_snapshot_push()
                self._start_vehicle_log_pull(silent=False)
                return True
            local_has_core_data = self._local_snapshot_has_core_data()
            if local_has_core_data and not str(self._last_server_snapshot_updated_at or "").strip():
                self._emit_server_sync_notice("이 PC 자료 서버 전체 저장 시작")
                self._start_server_snapshot_push()
                self._start_vehicle_log_pull(silent=False)
                return True
            self._emit_server_sync_notice("서버 전체 자료 불러오기 시작")
            if self._start_server_snapshot_pull(force=True):
                return True
            if failed_count > 0:
                self._emit_server_sync_notice(f"전송 실패 {failed_count}건 · 서버 목록 동기화 시작")
            else:
                self._emit_server_sync_notice("서버 목록 동기화 시작")

        self._start_server_refresh()
        return True

    def _server_row_to_employee(self, row: dict, base_employee: dict | None = None) -> dict:
        mapped = deepcopy(base_employee or {})
        mapped.update({
            "id": int(row.get("id", 0) or 0),
            "name": str(row.get("name") or mapped.get("name") or "").strip(),
            "nation": str(row.get("nation") or mapped.get("nation") or "대한민국").strip() or "대한민국",
            "affiliated_business": str(row.get("affiliated_business") or mapped.get("affiliated_business") or "").strip(),
            "business": str(row.get("affiliated_business") or mapped.get("business") or mapped.get("affiliated_business") or "").strip(),
            "company": str(row.get("work_site") or mapped.get("company") or "").strip(),
            "client": str(row.get("work_site") or mapped.get("client") or mapped.get("company") or "").strip(),
            "work_site": str(row.get("work_site") or mapped.get("work_site") or "").strip(),
            "department": str(row.get("work_site") or mapped.get("department") or mapped.get("work_site") or "").strip(),
            "work_type": str(row.get("work_type") or mapped.get("work_type") or "교대").strip() or "교대",
            "pay_type": str(row.get("pay_type") or mapped.get("pay_type") or "시급제").strip() or "시급제",
            "status": str(row.get("status") or mapped.get("status") or "출근전").strip() or "출근전",
            "phone": str(row.get("phone") or mapped.get("phone") or "").strip(),
            "hire_date": str(row.get("hire_date") or mapped.get("hire_date") or "").strip(),
            "note": str(row.get("note") or mapped.get("note") or "").strip(),
            "active": str(row.get("status") or mapped.get("status") or "").strip() != "퇴사",
        })
        pay_type = str(mapped.get("pay_type") or "시급제").strip()
        if pay_type in {"월급", "월급제"}:
            mapped["pay_type"] = "월급제"
        elif pay_type in {"시급", "시급제"}:
            mapped["pay_type"] = "시급제"
        elif pay_type in {"일급", "일급제"}:
            mapped["pay_type"] = "일급제"
        return normalize_employee(mapped, self._score_settings, self._rejoin_grades)

    def _employee_to_server_payload(self, employee: dict, *, include_id: bool = False) -> dict:
        pay_type = str(employee.get("pay_type") or "시급제").strip() or "시급제"
        if pay_type in {"월급", "월급제"}:
            pay_type = "월급제"
        elif pay_type in {"시급", "시급제"}:
            pay_type = "시급제"
        elif pay_type in {"일급", "일급제"}:
            pay_type = "일급제"
        payload = {
            "name": str(employee.get("name") or "").strip(),
            "nation": str(employee.get("nation") or "대한민국").strip() or "대한민국",
            "affiliated_business": str(employee.get("affiliated_business") or employee.get("business") or "").strip(),
            "work_site": str(employee.get("work_site") or employee.get("company") or employee.get("client") or "").strip(),
            "work_type": str(employee.get("work_type") or "교대").strip() or "교대",
            "pay_type": pay_type,
            "status": str(employee.get("status") or "출근전").strip() or "출근전",
            "phone": str(employee.get("phone") or "").strip(),
            "hire_date": str(employee.get("hire_date") or "").strip(),
            "note": str(employee.get("note") or "").strip(),
        }
        if include_id:
            payload["id"] = int(employee.get("id", 0) or 0)
        return payload

    def _normalize_pending_employee_sync(self, rows: list | None) -> list[dict]:
        normalized_rows: list[dict] = []
        if not isinstance(rows, list):
            return normalized_rows
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                employee_id = self._pending_entry_employee_id(row)
            except (TypeError, ValueError):
                continue
            if employee_id <= 0:
                continue
            mode = str(row.get("mode") or "update").strip().lower()
            if mode not in {"create", "update", "delete"}:
                mode = "update"
            payload = deepcopy(row.get("payload") or {}) if isinstance(row.get("payload"), dict) else {}
            local_employee = deepcopy(row.get("local_employee") or {}) if isinstance(row.get("local_employee"), dict) else {}
            sync_token = str(row.get("sync_token") or f"{employee_id}-{datetime.now().timestamp()}").strip()
            created_at = str(row.get("created_at") or datetime.now().isoformat(timespec="seconds")).strip()
            last_error = str(row.get("last_error") or "").strip()
            try:
                retry_count = int(row.get("retry_count", 0) or 0)
            except (TypeError, ValueError):
                retry_count = 0
            normalized_rows.append({
                "employee_id": employee_id,
                "mode": mode,
                "payload": payload,
                "local_employee": local_employee,
                "sync_token": sync_token,
                "created_at": created_at,
                "last_error": last_error,
                "retry_count": max(0, retry_count),
            })
        return normalized_rows

    def _save_pending_employee_sync(self) -> None:
        self._app_settings["pending_employee_sync"] = deepcopy(self._pending_employee_sync)
        self._storage.save_app_settings(self._app_settings)

    def _save_sync_status_metadata(self, *, status: str | None = None, error: str | None = None, success: bool = False) -> None:
        if status is not None:
            self._app_settings["last_employee_sync_status"] = str(status or "").strip()
        if error is not None:
            self._app_settings["last_employee_sync_error"] = str(error or "").strip()
        if success:
            self._app_settings["last_employee_sync_at"] = datetime.now().isoformat(timespec="seconds")
            self._app_settings["last_employee_sync_error"] = ""
        self._storage.save_app_settings(self._app_settings)

    def _emit_server_sync_notice(self, message: str) -> None:
        text = str(message or "").strip()
        if not text or text == self._last_server_sync_notice:
            return
        self._last_server_sync_notice = text
        self._app_settings["last_employee_sync_status"] = text
        self._storage.save_app_settings(self._app_settings)
        if self._suppress_server_sync_notice:
            return
        self.server_sync_status.emit(text)

    def _employee_identity_signature(self, employee: dict | None) -> str:
        row = employee or {}
        parts = [
            str(row.get("name") or "").strip(),
            str(row.get("nation") or "").strip(),
            str(row.get("affiliated_business") or row.get("business") or "").strip(),
            str(row.get("work_site") or row.get("company") or row.get("client") or "").strip(),
            str(row.get("work_type") or "").strip(),
            str(row.get("phone") or "").strip(),
            str(row.get("hire_date") or "").strip(),
        ]
        return "|".join(part.casefold() for part in parts)

    def _next_available_employee_id_from_set(self, extra_used_ids: set[int] | None = None) -> int:
        used_ids: set[int] = set(extra_used_ids or set())
        for row in self._employees:
            try:
                employee_id = int((row or {}).get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id > 0:
                used_ids.add(employee_id)
        for row in self._pending_employee_sync:
            try:
                employee_id = self._pending_entry_employee_id(row)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id > 0:
                used_ids.add(employee_id)
        candidate = max(used_ids | {1000}) + 1
        while candidate in used_ids:
            candidate += 1
        return candidate

    def _reassign_employee_id_everywhere(self, old_employee_id: int, new_employee_id: int) -> bool:
        try:
            old_id = int(old_employee_id or 0)
            new_id = int(new_employee_id or 0)
        except (TypeError, ValueError):
            return False
        if old_id <= 0 or new_id <= 0 or old_id == new_id:
            return False

        changed = False
        for row in self._employees:
            try:
                employee_id = int((row or {}).get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id == old_id:
                row["id"] = new_id
                changed = True

        for row in self._attendance_events:
            try:
                employee_id = self._pending_entry_employee_id(row)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id == old_id:
                row["employee_id"] = new_id
                changed = True

        rebuilt_monthly_records: dict[tuple[int, str], dict] = {}
        for (employee_id, record_date), payload in self._monthly_records.items():
            target_id = new_id if int(employee_id) == old_id else int(employee_id)
            if target_id != int(employee_id):
                changed = True
            rebuilt_monthly_records[(target_id, record_date)] = payload
        self._monthly_records = rebuilt_monthly_records

        rebuilt_payroll_inputs: dict[tuple[int, str], dict] = {}
        for (employee_id, month_key), payload in self._payroll_month_inputs.items():
            target_id = new_id if int(employee_id) == old_id else int(employee_id)
            if target_id != int(employee_id):
                changed = True
            rebuilt_payroll_inputs[(target_id, month_key)] = payload
        self._payroll_month_inputs = rebuilt_payroll_inputs

        rebuilt_adjustments: dict[tuple[int, str], dict] = {}
        for (employee_id, month_key), payload in self._individual_payroll_adjustments.items():
            target_id = new_id if int(employee_id) == old_id else int(employee_id)
            if target_id != int(employee_id):
                changed = True
            rebuilt_adjustments[(target_id, month_key)] = payload
        self._individual_payroll_adjustments = rebuilt_adjustments

        for entry in self._pending_employee_sync:
            try:
                pending_id = self._pending_entry_employee_id(entry)
            except (TypeError, ValueError, AttributeError):
                pending_id = 0
            if pending_id != old_id:
                continue
            entry["employee_id"] = new_id
            if isinstance(entry.get("payload"), dict):
                entry["payload"]["id"] = new_id
            if isinstance(entry.get("local_employee"), dict):
                entry["local_employee"]["id"] = new_id
            changed = True

        if changed:
            self._employees.sort(key=lambda row: int(row.get("id", 0) or 0))
            self._dirty_sections.update({"core_people", "attendance", "records", "payroll"})
            self._save_pending_employee_sync()
        return changed

    def _reconcile_pending_create_conflicts(self, server_rows: list[dict]) -> bool:
        if not self._pending_employee_sync:
            return False
        server_by_id: dict[int, dict] = {}
        for row in server_rows:
            try:
                employee_id = int((row or {}).get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id > 0:
                server_by_id[employee_id] = deepcopy(row)
        if not server_by_id:
            return False

        changed = False
        reserved_ids: set[int] = set(server_by_id.keys())
        pending_snapshot = list(self._pending_employee_sync)
        for entry in pending_snapshot:
            if str(entry.get("mode") or "").strip().lower() != "create":
                continue
            try:
                employee_id = self._pending_entry_employee_id(entry)
            except (TypeError, ValueError):
                employee_id = 0
            if employee_id <= 0:
                continue
            server_row = server_by_id.get(employee_id)
            if not server_row:
                reserved_ids.add(employee_id)
                continue

            local_employee = deepcopy(entry.get("local_employee") or self.get_employee_by_id(employee_id) or {})
            if not local_employee:
                reserved_ids.add(employee_id)
                continue

            local_signature = self._employee_identity_signature(local_employee)
            server_signature = self._employee_identity_signature(server_row)
            if local_signature and local_signature == server_signature:
                pending_index = next((i for i, row in enumerate(self._pending_employee_sync) if self._pending_entry_employee_id(row) == employee_id), -1)
                if pending_index >= 0:
                    self._pending_employee_sync.pop(pending_index)
                    changed = True
                merged = self._server_row_to_employee(server_row, local_employee)
                for index, row in enumerate(self._employees):
                    if int(row.get("id", 0) or 0) == employee_id:
                        self._employees[index] = merged
                        break
                else:
                    self._employees.append(merged)
                reserved_ids.add(employee_id)
                continue

            new_id = self._next_available_employee_id_from_set(reserved_ids)
            if self._reassign_employee_id_everywhere(employee_id, new_id):
                changed = True
            reserved_ids.add(new_id)

        if changed:
            self._employees.sort(key=lambda row: int(row.get("id", 0) or 0))
            self._save_pending_employee_sync()
        return changed

    def _pending_employee_delete_ids(self) -> set[int]:
        deleted_ids: set[int] = set()
        for entry in self._pending_employee_sync:
            if str((entry or {}).get("mode") or "").strip().lower() != "delete":
                continue
            try:
                employee_id = self._pending_entry_employee_id(entry)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id > 0:
                deleted_ids.add(employee_id)
        return deleted_ids

    def _purge_employee_related_local_data(self, employee_ids: set[int], *, remove_files: bool = False) -> None:
        clean_ids = {self._safe_employee_id(employee_id, 0) for employee_id in (employee_ids or set()) if self._safe_employee_id(employee_id, 0) > 0}
        if not clean_ids:
            return
        self._employees = [row for row in self._employees if self._safe_employee_id((row or {}).get("id", 0), 0) not in clean_ids]
        self._attendance_events = [row for row in self._attendance_events if self._pending_entry_employee_id(row) not in clean_ids]
        self._monthly_records = {key: value for key, value in self._monthly_records.items() if self._safe_employee_id(key[0] if key else 0, 0) not in clean_ids}
        self._payroll_month_inputs = {key: value for key, value in self._payroll_month_inputs.items() if self._safe_employee_id(key[0] if key else 0, 0) not in clean_ids}
        self._individual_payroll_adjustments = {key: value for key, value in self._individual_payroll_adjustments.items() if self._safe_employee_id(key[0] if key else 0, 0) not in clean_ids}
        self._pending_employee_sync = [row for row in self._pending_employee_sync if self._pending_entry_employee_id(row) not in clean_ids]
        if remove_files:
            for employee_id in clean_ids:
                try:
                    shutil.rmtree(self._storage.employee_files_dir / str(employee_id), ignore_errors=True)
                except Exception:
                    pass

    def _merge_pending_employee_rows(self, employees: list[dict]) -> list[dict]:
        merged_by_id: dict[int, dict] = {}
        for row in employees or []:
            try:
                employee_id = int((row or {}).get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id <= 0:
                continue
            merged_by_id[employee_id] = deepcopy(row)

        for entry in self._pending_employee_sync:
            mode = str((entry or {}).get("mode") or "").strip().lower()
            try:
                employee_id = self._pending_entry_employee_id(entry)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id <= 0:
                continue
            if mode == "delete":
                merged_by_id.pop(employee_id, None)
                continue
            if mode not in {"create", "update"}:
                continue
            local_employee = deepcopy((entry or {}).get("local_employee") or {})
            if not isinstance(local_employee, dict) or not local_employee:
                continue
            local_employee["id"] = employee_id
            merged_by_id[employee_id] = normalize_employee(local_employee, self._score_settings, self._rejoin_grades)

        return sorted(merged_by_id.values(), key=lambda item: int(item.get("id", 0) or 0))

    def _queue_employee_server_sync(self, mode: str, employee: dict) -> None:
        raw_mode = str(mode or "update").strip().lower()
        normalized_mode = raw_mode if raw_mode in {"create", "update", "delete"} else "update"
        normalized_employee = normalize_employee(employee, self._score_settings, self._rejoin_grades)
        employee_id = int(normalized_employee.get("id", 0) or 0)
        if employee_id <= 0:
            return
        sync_token = f"{employee_id}-{datetime.now().timestamp()}"
        include_id = normalized_mode in {"create", "update"}
        payload = {} if normalized_mode == "delete" else self._employee_to_server_payload(normalized_employee, include_id=include_id)
        existing_index = next((i for i, row in enumerate(self._pending_employee_sync) if self._pending_entry_employee_id(row) == employee_id), -1)
        queued_row = {
            "employee_id": employee_id,
            "mode": normalized_mode,
            "payload": payload,
            "local_employee": normalized_employee,
            "sync_token": sync_token,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "last_error": "",
            "retry_count": 0,
        }
        if existing_index >= 0:
            existing = deepcopy(self._pending_employee_sync[existing_index])
            queued_row["created_at"] = str(existing.get("created_at") or queued_row["created_at"])
            self._pending_employee_sync[existing_index] = queued_row
        else:
            self._pending_employee_sync.append(queued_row)
        self._save_pending_employee_sync()
        self._emit_server_sync_notice(f"서버 전송 대기 {len(self._pending_employee_sync)}건")
        self._schedule_employee_server_sync(300)

    def _schedule_employee_server_sync(self, delay_ms: int = 1500) -> None:
        if self._pending_employee_sync_active_count() <= 0:
            return
        if self._server_sync_worker is not None and self._server_sync_worker.isRunning():
            return
        interval = max(400, int(delay_ms or 0))
        self._server_sync_timer.start(interval)

    @staticmethod
    def _runtime_http_status_code(error: Exception) -> int:
        text = str(error or "")
        match = re.search(r"HTTP\s+(\d{3})", text)
        if not match:
            return 0
        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            return 0

    def _sync_single_employee_entry(self, settings: dict, entry: dict) -> dict:
        payload = deepcopy(entry.get("payload") or {})
        employee_id = self._pending_entry_employee_id(entry)
        mode = str(entry.get("mode") or "update").strip().lower()
        if mode == "delete":
            try:
                response = delete_employee_remote(settings, employee_id)
                used_mode = "delete"
            except HTTPError as exc:
                status_code = int(getattr(exc, "code", 0) or 0)
                if status_code in {404, 410}:
                    response = {"id": employee_id, "deleted": True, "already_missing": True}
                    used_mode = "delete"
                else:
                    raise
            except RuntimeError as exc:
                status_code = self._runtime_http_status_code(exc)
                if status_code in {404, 410}:
                    response = {"id": employee_id, "deleted": True, "already_missing": True}
                    used_mode = "delete"
                else:
                    raise
        elif mode == "create":
            create_payload = deepcopy(payload)
            try:
                response = create_employee_remote(settings, create_payload)
                used_mode = "create"
            except HTTPError as exc:
                status_code = int(getattr(exc, "code", 0) or 0)
                if status_code == 410:
                    response = {"id": employee_id, "deleted": True, "already_missing": True}
                    used_mode = "delete"
                elif status_code in {404, 409, 500}:
                    response = update_employee_remote(settings, employee_id, payload)
                    used_mode = "update"
                else:
                    raise
            except RuntimeError as exc:
                status_code = self._runtime_http_status_code(exc)
                if status_code == 410:
                    response = {"id": employee_id, "deleted": True, "already_missing": True}
                    used_mode = "delete"
                else:
                    raise
        else:
            try:
                response = update_employee_remote(settings, employee_id, payload)
                used_mode = "update"
            except HTTPError as exc:
                status_code = int(getattr(exc, "code", 0) or 0)
                if status_code == 410:
                    response = {"id": employee_id, "deleted": True, "already_missing": True}
                    used_mode = "delete"
                elif status_code == 404:
                    response = create_employee_remote(settings, payload)
                    used_mode = "create"
                else:
                    raise
            except RuntimeError as exc:
                status_code = self._runtime_http_status_code(exc)
                if status_code == 410:
                    response = {"id": employee_id, "deleted": True, "already_missing": True}
                    used_mode = "delete"
                else:
                    raise
        if not isinstance(response, dict):
            response = {}
        return {
            "employee_id": employee_id,
            "sync_token": str(entry.get("sync_token") or ""),
            "mode": used_mode,
            "response": response,
        }

    def _start_employee_server_sync(self) -> None:
        if self._server_sync_worker is not None and self._server_sync_worker.isRunning():
            return
        active_entry = next((row for row in self._pending_employee_sync if not self._is_sync_entry_blocked(row)), None)
        if active_entry is None:
            self._start_server_refresh()
            return
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "")).strip():
            return
        self._active_server_sync_entry = deepcopy(active_entry)
        self._server_sync_worker = FunctionWorkerThread(self._sync_single_employee_entry, settings, deepcopy(self._active_server_sync_entry))
        self._server_sync_worker.result_ready.connect(self._handle_employee_sync_success)
        self._server_sync_worker.error_occurred.connect(self._handle_employee_sync_error)
        self._server_sync_worker.finished.connect(self._cleanup_employee_sync_worker)
        self._server_sync_worker.start()

    def _handle_employee_sync_success(self, result: dict) -> None:
        current_entry = deepcopy(self._active_server_sync_entry or {})
        employee_id = int(result.get("employee_id", current_entry.get("employee_id", 0)) or 0)
        sync_token = str(result.get("sync_token") or current_entry.get("sync_token") or "")
        result_mode = str(result.get("mode") or current_entry.get("mode") or "update").strip().lower()
        server_row = result.get("response") if isinstance(result.get("response"), dict) else {}
        current_index = next((i for i, row in enumerate(self._pending_employee_sync) if self._pending_entry_employee_id(row) == employee_id), -1)
        if current_index >= 0:
            live_entry = self._pending_employee_sync[current_index]
            if str(live_entry.get("sync_token") or "") == sync_token:
                self._pending_employee_sync.pop(current_index)
            else:
                if str(live_entry.get("mode") or "") == "create":
                    live_entry["mode"] = "update"
                live_entry["last_error"] = ""
                live_entry["retry_count"] = 0
        if result_mode == "delete":
            self._employees = [row for row in self._employees if self._safe_employee_id((row or {}).get("id", 0), 0) != employee_id]
            self._attendance_events = [row for row in self._attendance_events if self._pending_entry_employee_id(row) != employee_id]
            self._monthly_records = {key: value for key, value in self._monthly_records.items() if self._safe_employee_id(key[0] if key else 0, 0) != employee_id}
            self._payroll_month_inputs = {key: value for key, value in self._payroll_month_inputs.items() if self._safe_employee_id(key[0] if key else 0, 0) != employee_id}
            self._individual_payroll_adjustments = {key: value for key, value in self._individual_payroll_adjustments.items() if self._safe_employee_id(key[0] if key else 0, 0) != employee_id}
            self._dirty_sections.update({"core_people", "attendance", "records", "payroll"})
            self.employees_changed.emit()
            self.attendance_changed.emit()
        elif server_row:
            try:
                server_employee_id = int(server_row.get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                server_employee_id = 0
            if server_employee_id > 0 and server_employee_id != employee_id:
                conflicting = self.get_employee_by_id(server_employee_id)
                local_base = self.get_employee_by_id(employee_id) or deepcopy(current_entry.get("local_employee") or {})
                if conflicting is None or self._employee_identity_signature(conflicting) == self._employee_identity_signature(local_base):
                    if self._reassign_employee_id_everywhere(employee_id, server_employee_id):
                        employee_id = server_employee_id
            existing = self.get_employee_by_id(employee_id) or deepcopy(current_entry.get("local_employee") or {})
            merged = self._server_row_to_employee(server_row, existing)
            for index, row in enumerate(self._employees):
                if int(row.get("id", 0) or 0) == employee_id:
                    self._employees[index] = merged
                    break
            else:
                self._employees.append(merged)
                self._employees.sort(key=lambda row: int(row.get("id", 0) or 0))
            self._dirty_sections.update({"core_people", "attendance", "records", "payroll"})
            self.employees_changed.emit()
        self._save_pending_employee_sync()
        active_count = self._pending_employee_sync_active_count()
        failed_count = self._pending_employee_sync_failed_count()
        if active_count > 0:
            self._emit_server_sync_notice(f"서버 전송 대기 {active_count}건")
            self._schedule_employee_server_sync(400)
        else:
            if failed_count > 0:
                self._emit_server_sync_notice(f"서버 반영 완료 · 실패 {failed_count}건 제외 · 목록 새로고침 중")
            else:
                self._emit_server_sync_notice("서버 반영 완료 · 목록 새로고침 중")
            self._start_server_refresh()

    def _handle_employee_sync_error(self, message: str) -> None:
        current_entry = deepcopy(self._active_server_sync_entry or {})
        employee_id = self._pending_entry_employee_id(current_entry)
        sync_token = str(current_entry.get("sync_token") or "")
        error_text = str(message or "서버 전송 실패").strip() or "서버 전송 실패"
        for row in self._pending_employee_sync:
            if self._pending_entry_employee_id(row) != employee_id:
                continue
            if str(row.get("sync_token") or "") != sync_token:
                continue
            row["last_error"] = error_text
            row["retry_count"] = int(row.get("retry_count", 0) or 0) + 1
            break
        self._save_pending_employee_sync()
        active_count = self._pending_employee_sync_active_count()
        failed_count = self._pending_employee_sync_failed_count()
        if failed_count > 0:
            self._save_sync_status_metadata(error=f"전송 실패 {failed_count}건 · {error_text}")
            self._emit_server_sync_notice(f"전송 실패 {failed_count}건 · PC 자료 유지")
        elif active_count > 0:
            self._save_sync_status_metadata(error=f"서버 연결 지연 · {error_text}")
            self._emit_server_sync_notice(f"서버 연결 지연 · 대기 {active_count}건 · PC 자료 유지")
        else:
            self._save_sync_status_metadata(error=error_text)
        self._start_server_refresh()

    def _cleanup_employee_sync_worker(self) -> None:
        worker = self._server_sync_worker
        self._server_sync_worker = None
        self._active_server_sync_entry = None
        if worker is not None:
            worker.deleteLater()
        if self._pending_employee_sync_active_count() > 0:
            self._schedule_employee_server_sync(400)
            return
        if self._server_refresh_worker is None:
            self._suppress_server_sync_notice = False

    def _apply_server_employee_rows(self, rows: list[dict], emit_signal: bool = False, remove_missing: bool = False) -> bool:
        self._reconcile_pending_create_conflicts(rows)

        pending_delete_ids = self._pending_employee_delete_ids()
        pending_upsert_ids: set[int] = set()
        for entry in self._pending_employee_sync:
            mode = str((entry or {}).get("mode") or "").strip().lower()
            if mode not in {"create", "update"}:
                continue
            try:
                employee_id = self._pending_entry_employee_id(entry)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id > 0:
                pending_upsert_ids.add(employee_id)

        # PC 자료 보호: 서버 목록을 기준으로 PC 목록을 통째로 갈아끼우지 않습니다.
        # 다만 수동 동기화에서 서버에 이미 삭제된 근로자는 다른 PC에서도 삭제되도록
        # remove_missing=True일 때만 서버 목록 누락분을 삭제 반영합니다.
        merged_by_id: dict[int, dict] = {}
        for row in self._employees:
            try:
                employee_id = int((row or {}).get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id > 0 and employee_id not in pending_delete_ids:
                merged_by_id[employee_id] = deepcopy(row)

        server_ids: set[int] = set()
        for row in rows or []:
            try:
                employee_id = int((row or {}).get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id <= 0:
                continue
            server_ids.add(employee_id)
            # 삭제 대기 중인 근로자는 서버 목록에 아직 남아 있어도 다시 병합하지 않습니다.
            # 이 처리가 없으면 첫 번째 삭제 직후 서버 refresh가 삭제한 근로자를 되살립니다.
            if employee_id in pending_delete_ids:
                continue
            local_base = merged_by_id.get(employee_id)
            merged_by_id[employee_id] = self._server_row_to_employee(row, local_base)

        removed_ids: set[int] = set()
        if remove_missing and server_ids:
            for employee_id in list(merged_by_id.keys()):
                if employee_id in pending_upsert_ids or employee_id in pending_delete_ids:
                    continue
                if employee_id not in server_ids:
                    removed_ids.add(employee_id)
                    merged_by_id.pop(employee_id, None)

        self._employees = self._merge_pending_employee_rows(list(merged_by_id.values()))
        if removed_ids:
            self._attendance_events = [row for row in self._attendance_events if self._pending_entry_employee_id(row) not in removed_ids]
            self._monthly_records = {key: value for key, value in self._monthly_records.items() if int(key[0]) not in removed_ids}
            self._payroll_month_inputs = {key: value for key, value in self._payroll_month_inputs.items() if int(key[0]) not in removed_ids}
            self._individual_payroll_adjustments = {key: value for key, value in self._individual_payroll_adjustments.items() if int(key[0]) not in removed_ids}
        self._dirty_sections.update({"core_people", "attendance", "records", "payroll"})
        if emit_signal:
            self.employees_changed.emit()
            if removed_ids:
                self.attendance_changed.emit()
                self.records_changed.emit()
                self.payroll_changed.emit()
        return True

    def _fetch_server_employee_rows(self, settings: dict) -> list[dict]:
        rows = fetch_employees(settings)
        return [row for row in rows if isinstance(row, dict)]

    def _start_server_refresh(self) -> None:
        if self._server_refresh_worker is not None and self._server_refresh_worker.isRunning():
            return
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "")).strip():
            self._manual_sync_requested = False
            if not self._suppress_server_sync_notice:
                self._emit_server_sync_notice("서버 주소 확인 필요")
            return
        self._server_refresh_worker = FunctionWorkerThread(self._fetch_server_employee_rows, deepcopy(settings))
        self._server_refresh_worker.result_ready.connect(self._handle_server_refresh_success)
        self._server_refresh_worker.error_occurred.connect(self._handle_server_refresh_error)
        self._server_refresh_worker.finished.connect(self._cleanup_server_refresh_worker)
        self._server_refresh_worker.start()

    def _handle_server_refresh_success(self, rows: list[dict]) -> None:
        row_list = rows if isinstance(rows, list) else []
        # 수동 동기화에서는 다른 PC에서 삭제한 근로자도 즉시 반영합니다.
        # 단, 이 PC에 전송 대기/실패 건이 있으면 로컬 작업 보호를 위해 삭제 반영을 보류합니다.
        remove_missing = bool(
            self._manual_sync_requested
            and self._pending_employee_sync_active_count() <= 0
            and self._pending_employee_sync_failed_count() <= 0
        )
        self._apply_server_employee_rows(row_list, emit_signal=True, remove_missing=remove_missing)
        self._save_database_snapshot(sync_latest_backup=False, backup_reason="server-sync")
        attendance_summary = ""
        if self._manual_sync_requested and not self._suppress_server_sync_notice:
            attendance_result = self._pull_current_attendance_month_for_manual_sync()
            attendance_summary = self._manual_attendance_sync_summary(attendance_result)
        count = len(self._employees)
        active_count = self._pending_employee_sync_active_count()
        failed_count = self._pending_employee_sync_failed_count()
        suffix = f" · {attendance_summary}" if attendance_summary else ""
        if failed_count > 0:
            self._save_sync_status_metadata(error=f"전송 실패 {failed_count}건")
            self._emit_server_sync_notice(f"동기화 완료 · 서버 {count}명 / 실패 {failed_count}건{suffix}")
        elif active_count > 0:
            self._save_sync_status_metadata(error=f"전송 대기 {active_count}건")
            self._emit_server_sync_notice(f"동기화 완료 · 서버 {count}명 / 대기 {active_count}건{suffix}")
        else:
            self._save_sync_status_metadata(success=True)
            self._emit_server_sync_notice(f"동기화 완료 · 서버 {count}명{suffix}")
        self._manual_sync_requested = False
        self._suppress_server_sync_notice = False

    def _handle_server_refresh_error(self, message: str) -> None:
        text = str(message or "서버 목록 동기화 실패").strip() or "서버 목록 동기화 실패"
        active_count = self._pending_employee_sync_active_count()
        failed_count = self._pending_employee_sync_failed_count()
        if failed_count > 0:
            self._save_sync_status_metadata(error=f"서버 연결 지연 · 실패 {failed_count}건")
            self._emit_server_sync_notice(f"서버 연결 지연 · 실패 {failed_count}건")
        elif active_count > 0:
            self._save_sync_status_metadata(error=f"서버 연결 지연 · 대기 {active_count}건 · PC 자료 유지")
            self._emit_server_sync_notice(f"서버 연결 지연 · 대기 {active_count}건 · PC 자료 유지")
        else:
            self._save_sync_status_metadata(error=text)
            self._emit_server_sync_notice(text)
        self._manual_sync_requested = False
        self._suppress_server_sync_notice = False

    def _cleanup_server_refresh_worker(self) -> None:
        worker = self._server_refresh_worker
        self._server_refresh_worker = None
        if worker is not None:
            worker.deleteLater()
        if not self.is_server_sync_running():
            self._manual_sync_requested = False
            self._suppress_server_sync_notice = False
            self._emit_server_sync_notice("동기화 대기")

    def refresh_employees_from_server(self, emit_signal: bool = False) -> bool:
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "")).strip():
            return False
        rows = self._fetch_server_employee_rows(settings)
        self._apply_server_employee_rows(rows, emit_signal=emit_signal)
        return True

    @property
    def attendance_events(self) -> list[dict]:
        return self._attendance_events

    @property
    def score_settings(self) -> dict[str, int]:
        return self._score_settings

    @property
    def rejoin_grades(self) -> list[tuple[int, str]]:
        return self._rejoin_grades


    def _next_business_id(self) -> str:
        businesses = getattr(self, "_businesses", [])
        numbers = [int(str(row.get("business_id", "")).replace("B", "") or 0) for row in businesses]
        return f"B{(max(numbers) + 1 if numbers else 1):04d}"

    def _next_work_site_id(self) -> str:
        work_sites = getattr(self, "_work_sites", [])
        numbers = [int(str(row.get("work_site_id", "")).replace("W", "") or 0) for row in work_sites]
        return f"W{(max(numbers) + 1 if numbers else 1):04d}"

    def _attach_business_defaults(self, record: dict) -> dict:
        normalized = normalize_business_record(record)
        if not normalized.get("business_id"):
            normalized["business_id"] = self._next_business_id()
        normalized["original_form"] = build_business_original_form({**normalized.get("original_form", {}), **(record or {})})
        return normalized

    def _attach_work_site_defaults(self, record: dict) -> dict:
        normalized = normalize_work_site_record(record)
        if not normalized.get("work_site_id"):
            normalized["work_site_id"] = self._next_work_site_id()
        business_name = normalized.get("business_name", "")
        business = self.get_business(business_name)
        normalized["parent_business_id"] = business.get("business_id", "") if business else normalized.get("parent_business_id", "")
        normalized["original_form"] = build_work_site_original_form({**normalized.get("original_form", {}), **(record or {}), "business_name": business_name})
        return normalized

    def _build_default_businesses(self) -> list[dict]:
        businesses: dict[str, dict] = {}
        for employee in self._employees:
            name = _normalize_business_name(employee.get("affiliated_business"))
            if not name:
                continue
            if name not in businesses:
                businesses[name] = self._attach_business_defaults({"name": name, "active": employee.get("status") != "퇴사"})
        return sorted(businesses.values(), key=lambda row: row["name"])

    def _build_default_work_sites(self) -> list[dict]:
        work_sites: dict[tuple[str, str], dict] = {}
        for employee in self._employees:
            business_name = _normalize_business_name(employee.get("affiliated_business"))
            site_name = _normalize_work_site_name(employee.get("work_site") or employee.get("company"))
            if not business_name or not site_name:
                continue
            key = (business_name, site_name)
            if key not in work_sites:
                work_sites[key] = self._attach_work_site_defaults({
                    "business_name": business_name,
                    "name": site_name,
                    "active": employee.get("status") != "퇴사",
                })
        return sorted(work_sites.values(), key=lambda row: (row["business_name"], row["name"]))

    def _ensure_business_exists(self, business_name: str):
        name = _normalize_business_name(business_name)
        if any(row["name"] == name for row in self._businesses):
            return
        self._businesses.append(self._attach_business_defaults({"name": name}))
        self._businesses.sort(key=lambda row: row["name"])

    def _ensure_work_site_exists(self, business_name: str, work_site_name: str):
        business_name = _normalize_business_name(business_name)
        work_site_name = _normalize_work_site_name(work_site_name)
        if any(row["business_name"] == business_name and row["name"] == work_site_name for row in self._work_sites):
            return
        self._work_sites.append(self._attach_work_site_defaults({
            "business_name": business_name,
            "name": work_site_name,
        }))
        self._work_sites.sort(key=lambda row: (row["business_name"], row["name"]))

    def ensure_work_sites_from_time_conversion_rules(self, rows: list[dict] | None = None, emit: bool = True) -> int:
        """사업장별 시간 환산 기준에 나온 사업장을 근무사업장 마스터에도 연결한다.

        환산 기준표는 설정 데이터이고, 근무사업장 검색은 별도의 마스터 목록을 본다.
        기본 환산표를 불러오거나 동기화로 환산표를 받은 뒤에도 검색 목록에 바로 보이도록
        누락된 사업장만 보강한다. 사업자명이 비어 있으면 기존에 같은 사업장명이 있는지 먼저
        확인하고, 없을 때만 `미지정 사업자` 아래에 추가한다.
        """
        source_rows = rows if rows is not None else self._site_time_conversion_rules
        before_count = len(self._work_sites)
        changed = False
        for idx, row in enumerate(source_rows or []):
            normalized = _normalize_site_time_conversion_rule(row, idx + 1)
            site_name = _normalize_work_site_name(normalized.get("work_site_name"))
            raw_site = str(normalized.get("work_site_name", "") or "").strip()
            if not raw_site:
                continue
            business_name = str(normalized.get("business_name", "") or "").strip()
            if business_name:
                before_businesses = len(self._businesses)
                before_sites = len(self._work_sites)
                self._ensure_work_site_exists(business_name, site_name)
                changed = changed or len(self._businesses) != before_businesses or len(self._work_sites) != before_sites
                continue

            # 환산표에 사업자명이 없을 때는 같은 사업장명이 이미 등록되어 있으면 그대로 연결된 것으로 본다.
            # 이렇게 해야 실제 사업자 아래에 이미 등록된 사업장을 `미지정 사업자`로 중복 생성하지 않는다.
            if any(_normalize_work_site_name(existing.get("name")) == site_name for existing in self._work_sites):
                continue
            before_businesses = len(self._businesses)
            before_sites = len(self._work_sites)
            self._ensure_work_site_exists("미지정 사업자", site_name)
            changed = changed or len(self._businesses) != before_businesses or len(self._work_sites) != before_sites

        if changed:
            self._businesses.sort(key=lambda row: row["name"])
            self._work_sites.sort(key=lambda row: (row["business_name"], row["name"]))
            if emit:
                self.employees_changed.emit()
        return max(0, len(self._work_sites) - before_count)

    def _business_usage_stats(self) -> dict[str, dict]:
        stats: dict[str, dict] = {}
        for employee in self._employees:
            key = _normalize_business_name(employee["affiliated_business"])
            record = stats.setdefault(
                key,
                {
                    "employee_count": 0,
                    "active_count": 0,
                    "company_names": set(),
                    "site_names": set(),
                    "nations": set(),
                },
            )
            record["employee_count"] += 1
            if employee.get("active", True):
                record["active_count"] += 1
            record["company_names"].add(employee["company"])
            record["site_names"].add(employee["work_site"])
            record["nations"].add(employee["nation"])
        return stats

    def _work_site_usage_stats(self) -> dict[tuple[str, str], dict]:
        stats: dict[tuple[str, str], dict] = {}
        for employee in self._employees:
            business_name = _normalize_business_name(employee["affiliated_business"])
            site_name = _normalize_work_site_name(employee.get("work_site") or employee.get("company"))
            key = (business_name, site_name)
            record = stats.setdefault(
                key,
                {
                    "employee_count": 0,
                    "active_count": 0,
                    "nations": set(),
                },
            )
            record["employee_count"] += 1
            if employee.get("active", True):
                record["active_count"] += 1
            record["nations"].add(employee["nation"])
        return stats

    def _build_default_events(self) -> list[dict]:
        return []

    def next_employee_id(self) -> int:
        base = int(datetime.now().timestamp())
        used_ids: set[int] = set()
        for row in self._employees:
            try:
                employee_id = int((row or {}).get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                continue
            if base <= employee_id < base + 10:
                used_ids.add(employee_id)
        for row in self._pending_employee_sync:
            try:
                employee_id = self._pending_entry_employee_id(row)
            except (TypeError, ValueError, AttributeError):
                continue
            if base <= employee_id < base + 10:
                used_ids.add(employee_id)
        
        candidate = base
        while candidate in used_ids:
            candidate += 1
        return candidate

    def get_employee_by_id(self, employee_id: int) -> dict | None:
        target_id = self._safe_employee_id(employee_id, 0)
        if target_id <= 0:
            return None
        for employee in self._employees:
            row_id = self._safe_employee_id((employee or {}).get("id", 0), 0)
            if row_id == target_id:
                return employee
        return None

    def get_employee_pay_terms_for_date(self, employee_id: int, target_date: str | date | None) -> dict:
        employee = self.get_employee_by_id(employee_id) or {}
        terms = _pay_terms_for_date(employee, target_date)
        settings = self.get_employee_payroll_settings(employee)
        # 개인별 설정에서 체크된 급여형태가 있으면 개인값을 우선 적용하고,
        # 체크되어 있지 않으면 현재 근무사업장의 공장 기본 급여형태를 적용합니다.
        # 급여금액은 별도 개인 급여금액/이력 기준을 유지합니다.
        effective_pay_type = str(settings.get("pay_type") or terms.get("pay_type") or "시급제").strip() or "시급제"
        terms["pay_type"] = effective_pay_type
        return terms

    def get_employee_effective_work_type(self, employee: dict | int | None) -> str:
        settings = self.get_employee_payroll_settings(employee)
        return str(settings.get("work_type") or "교대").strip() or "교대"

    def get_employee_effective_pay_type(self, employee: dict | int | None, target_date: str | date | None = None) -> str:
        if isinstance(employee, int):
            return str(self.get_employee_pay_terms_for_date(int(employee), target_date).get("pay_type") or "시급제").strip() or "시급제"
        employee = employee or {}
        terms = _pay_terms_for_date(employee, target_date)
        settings = self.get_employee_payroll_settings(employee)
        return str(settings.get("pay_type") or terms.get("pay_type") or "시급제").strip() or "시급제"

    def _append_pay_type_history(self, employee: dict, effective_date: str | None = None) -> dict:
        source = deepcopy(employee or {})
        history = _normalize_pay_type_history(
            source.get("pay_type_history"),
            str(source.get("pay_type") or "시급제").strip() or "시급제",
            float(source.get("base_wage", 0) or 0),
            effective_date or str(source.get("pay_effective_date") or source.get("hire_date") or date.today().isoformat()),
        )
        target_date = str(effective_date or source.get("pay_effective_date") or source.get("hire_date") or date.today().isoformat()).strip()
        try:
            target_date = datetime.strptime(target_date, "%Y-%m-%d").date().isoformat()
        except Exception:
            target_date = date.today().isoformat()
        entry = {
            "effective_date": target_date,
            "pay_type": str(source.get("pay_type") or "시급제").strip() or "시급제",
            "base_wage": float(source.get("base_wage", 0) or 0),
        }
        replaced = False
        for idx, row in enumerate(history):
            if str(row.get("effective_date") or "") == target_date:
                history[idx] = entry
                replaced = True
                break
        if not replaced:
            history.append(entry)
        history = _normalize_pay_type_history(history, entry["pay_type"], entry["base_wage"], target_date)
        source["pay_type_history"] = history
        source["pay_effective_date"] = target_date
        latest = history[-1]
        source["pay_type"] = latest["pay_type"]
        source["base_wage"] = float(latest.get("base_wage", 0) or 0)
        return source

    def _today_string(self) -> str:
        return date.today().isoformat()

    def _append_work_history_entry(
        self,
        employee: dict,
        *,
        start_date: str | None = None,
        end_date: str = "",
        work_site: str | None = None,
        business: str | None = None,
        work_type: str | None = None,
        status: str | None = None,
        reason: str = "",
        note: str = "",
    ) -> dict:
        source = deepcopy(employee or {})
        history = _normalize_work_history(
            source.get("work_history"),
            str(source.get("work_site") or work_site or "-").strip() or "-",
            source.get("hire_date") or start_date or self._today_string(),
            source.get("status") or status or "근무중",
            source.get("affiliated_business") or business,
            source.get("work_type") or work_type,
        )
        history.append({
            "start_date": _normalize_date_string(start_date or self._today_string(), self._today_string()),
            "end_date": _normalize_date_string(end_date, self._today_string()) if str(end_date or "").strip() else "",
            "business": str(business or source.get("affiliated_business") or "").strip(),
            "work_site": str(work_site or source.get("work_site") or "-").strip() or "-",
            "work_type": str(work_type or source.get("work_type") or "").strip(),
            "status": str(status or source.get("status") or "근무중").strip() or "근무중",
            "reason": str(reason or "").strip(),
            "note": str(note or "").strip(),
            "active": not bool(str(end_date or "").strip()),
        })
        source["work_history"] = _normalize_work_history(
            history,
            str(source.get("work_site") or work_site or "-").strip() or "-",
            source.get("hire_date") or start_date or self._today_string(),
            source.get("status") or status or "근무중",
            source.get("affiliated_business") or business,
            source.get("work_type") or work_type,
        )
        return source

    def _close_active_work_history(
        self,
        employee: dict,
        *,
        end_date: str | None = None,
        status: str | None = None,
        reason: str = "",
        note: str = "",
    ) -> dict:
        source = deepcopy(employee or {})
        history = _normalize_work_history(
            source.get("work_history"),
            str(source.get("work_site") or "-").strip() or "-",
            source.get("hire_date") or self._today_string(),
            source.get("status") or status or "근무중",
            source.get("affiliated_business"),
            source.get("work_type"),
        )
        target_end = _normalize_date_string(end_date or self._today_string(), self._today_string())
        for row in reversed(history):
            if not row.get("end_date"):
                row["end_date"] = target_end
                row["active"] = False
                if status:
                    row["status"] = str(status).strip() or row.get("status") or "근무중"
                if reason:
                    row["reason"] = str(reason).strip()
                if note:
                    row["note"] = str(note).strip()
                break
        source["work_history"] = _normalize_work_history(
            history,
            str(source.get("work_site") or "-").strip() or "-",
            source.get("hire_date") or self._today_string(),
            source.get("status") or status or "근무중",
            source.get("affiliated_business"),
            source.get("work_type"),
        )
        return source

    def _ensure_current_work_history(self, employee: dict) -> dict:
        source = deepcopy(employee or {})
        history = _normalize_work_history(
            source.get("work_history"),
            str(source.get("work_site") or "-").strip() or "-",
            source.get("hire_date") or self._today_string(),
            source.get("status") or "근무중",
            source.get("affiliated_business"),
            source.get("work_type"),
        )
        if str(source.get("status") or "").strip() == "퇴사":
            source["work_history"] = history
            return source
        active_index = next((idx for idx in range(len(history) - 1, -1, -1) if not history[idx].get("end_date")), -1)
        if active_index < 0:
            source["work_history"] = history
            source = self._append_work_history_entry(
                source,
                start_date=source.get("hire_date") or self._today_string(),
                business=source.get("affiliated_business"),
                work_site=source.get("work_site"),
                work_type=source.get("work_type"),
                status=source.get("status") or "근무중",
            )
            return source
        history[active_index]["business"] = str(source.get("affiliated_business") or history[active_index].get("business") or "").strip()
        history[active_index]["work_site"] = str(source.get("work_site") or history[active_index].get("work_site") or "-").strip() or "-"
        history[active_index]["work_type"] = str(source.get("work_type") or history[active_index].get("work_type") or "").strip()
        history[active_index]["status"] = str(source.get("status") or history[active_index].get("status") or "근무중").strip() or "근무중"
        history[active_index]["active"] = True
        source["work_history"] = history
        return source

    def _apply_resignation_score(self, employee: dict, reason: str) -> dict:
        source = deepcopy(employee or {})
        reason_text = str(reason or "").strip()
        score_delta = 0
        if "무단결근" in reason_text:
            source["unauthorized_absence"] = int(source.get("unauthorized_absence", 0) or 0) + 1
            score_delta = int(self._score_settings.get("unauthorized_absence", 0) or 0)
        elif "무단이탈" in reason_text:
            source["unauthorized_leave"] = int(source.get("unauthorized_leave", 0) or 0) + 1
            score_delta = int(self._score_settings.get("unauthorized_leave", 0) or 0)
        if score_delta:
            source["attendance_score"] = int(source.get("attendance_score", 0) or 0) + score_delta
            source["rejoin_grade"] = _grade_from_score(int(source.get("attendance_score", 0) or 0), self._rejoin_grades)
        return source

    def _finalize_resignation(self, employee: dict, *, reason: str = "일반 퇴사", note: str = "", end_date: str | None = None) -> dict:
        source = deepcopy(employee or {})
        source = self._ensure_current_work_history(source)
        target_end = _normalize_date_string(end_date or source.get("actual_end") or self._today_string(), self._today_string())
        source["status"] = "퇴사"
        source["active"] = False
        source["actual_end"] = target_end
        source["resign_reason"] = str(reason or "일반 퇴사").strip() or "일반 퇴사"
        source["resign_note"] = str(note or "").strip()
        source = self._close_active_work_history(
            source,
            end_date=target_end,
            status="퇴사",
            reason=source["resign_reason"],
            note=source["resign_note"],
        )
        source = self._apply_resignation_score(source, source["resign_reason"])
        source["rejoin_grade"] = _grade_from_score(int(source.get("attendance_score", 0) or 0), self._rejoin_grades)
        return source

    def add_employee(self, employee: dict) -> dict:
        normalized = normalize_employee(employee, self._score_settings, self._rejoin_grades)
        normalized = self._ensure_current_work_history(normalized)
        if str(normalized.get("status") or "").strip() == "퇴사":
            normalized = self._finalize_resignation(
                normalized,
                reason=str(normalized.get("resign_reason") or "일반 퇴사").strip() or "일반 퇴사",
                note=str(normalized.get("resign_note") or "").strip(),
                end_date=str(normalized.get("actual_end") or "").strip() or None,
            )
        normalized = self._stabilize_employee_media_payload(normalized)
        normalized = self._append_pay_type_history(normalized, normalized.get("pay_effective_date"))
        if any(int(row["id"]) == int(normalized["id"]) for row in self._employees):
            raise ValueError("이미 사용 중인 사번입니다.")
        normalized = self._upload_employee_portrait_to_server(normalized)
        self._ensure_business_exists(normalized["affiliated_business"])
        self._ensure_work_site_exists(normalized["affiliated_business"], normalized["work_site"])
        self._employees.append(normalized)
        self._employees.sort(key=lambda row: int(row["id"]))
        settings = self.server_api_settings()
        if str(settings.get("base_url", "")).strip():
            self._queue_employee_server_sync("create", normalized)
        self.employees_changed.emit()
        self.attendance_changed.emit()
        return normalized

    def update_employee(self, employee_id: int, employee: dict) -> dict:
        previous = self.get_employee_by_id(employee_id) or {}
        incoming = deepcopy(employee or {})
        requested_pay_type = str(incoming.get("pay_type") or "").strip()
        requested_has_base_wage = "base_wage" in incoming
        try:
            requested_base_wage = float(incoming.get("base_wage", previous.get("base_wage", 0)) or 0)
        except (TypeError, ValueError):
            requested_base_wage = float(previous.get("base_wage", 0) or 0)
        requested_pay_date = str(
            incoming.get("pay_change_date")
            or incoming.get("pay_effective_date")
            or previous.get("pay_effective_date")
            or date.today().isoformat()
        ).strip()
        merged = deepcopy(previous)
        merged.update(incoming)
        normalized = normalize_employee(merged, self._score_settings, self._rejoin_grades)
        normalized["work_history"] = deepcopy(previous.get("work_history") or normalized.get("work_history"))

        previous_status = str(previous.get("status") or "").strip()
        new_status = str(normalized.get("status") or "").strip()
        previous_business = str(previous.get("affiliated_business") or "").strip()
        new_business = str(normalized.get("affiliated_business") or "").strip()
        previous_site = str(previous.get("work_site") or "").strip()
        new_site = str(normalized.get("work_site") or "").strip()
        previous_work_type = str(previous.get("work_type") or "").strip()
        new_work_type = str(normalized.get("work_type") or "").strip()
        move_start_date = _normalize_date_string((employee or {}).get("work_site_move_date"), self._today_string())
        try:
            move_end_date = (datetime.strptime(move_start_date, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()
        except Exception:
            move_end_date = self._today_string()

        if previous_status == "퇴사" and new_status != "퇴사":
            normalized = self._append_work_history_entry(
                normalized,
                start_date=move_start_date,
                business=normalized.get("affiliated_business"),
                work_site=normalized.get("work_site"),
                work_type=normalized.get("work_type"),
                status=new_status or "근무중",
                reason="재입사",
            )
            normalized["resign_reason"] = ""
            normalized["resign_note"] = ""
        elif previous_status != "퇴사" and new_status == "퇴사":
            normalized = self._finalize_resignation(
                normalized,
                reason=str((employee or {}).get("resign_reason") or normalized.get("resign_reason") or "일반 퇴사").strip() or "일반 퇴사",
                note=str((employee or {}).get("resign_note") or normalized.get("resign_note") or "").strip(),
                end_date=str((employee or {}).get("actual_end") or normalized.get("actual_end") or "").strip() or None,
            )
        elif new_status != "퇴사" and (
            (previous_business and new_business and previous_business != new_business)
            or (previous_site and new_site and previous_site != new_site)
            or (previous_work_type and new_work_type and previous_work_type != new_work_type)
        ):
            change_note_parts = []
            if previous_business != new_business:
                change_note_parts.append(f"사업자 {previous_business or '-'} → {new_business or '-'}")
            if previous_site != new_site:
                change_note_parts.append(f"근무사업장 {previous_site or '-'} → {new_site or '-'}")
            if previous_work_type != new_work_type:
                change_note_parts.append(f"근무형태 {previous_work_type or '-'} → {new_work_type or '-'}")
            normalized = self._close_active_work_history(
                normalized,
                end_date=move_end_date,
                status="이동",
                reason="근무정보 변경",
                note=" / ".join(change_note_parts),
            )
            normalized = self._append_work_history_entry(
                normalized,
                start_date=move_start_date,
                business=new_business,
                work_site=new_site,
                work_type=new_work_type,
                status=new_status or "근무중",
            )
        else:
            normalized = self._ensure_current_work_history(normalized)

        normalized = normalize_employee(normalized, self._score_settings, self._rejoin_grades)
        # 기존 급여 이력이 있는 근로자는 normalize 과정에서 가장 최근 이력이
        # 화면에서 방금 선택한 급여형태/급여금액을 덮어쓸 수 있습니다.
        # 저장 버튼에서 넘어온 값은 이 시점에 다시 반영한 뒤 변경 이력으로 기록합니다.
        if requested_pay_type:
            normalized["pay_type"] = requested_pay_type
        if requested_has_base_wage:
            normalized["base_wage"] = requested_base_wage
        effective_date = _normalize_date_string(requested_pay_date, date.today().isoformat())
        normalized["pay_effective_date"] = effective_date
        normalized = self._stabilize_employee_media_payload(normalized)
        normalized = self._upload_employee_portrait_to_server(normalized)
        pay_type_changed = str(previous.get("pay_type") or "") != str(normalized.get("pay_type") or "")
        base_wage_changed = float(previous.get("base_wage", 0) or 0) != float(normalized.get("base_wage", 0) or 0)
        if pay_type_changed or base_wage_changed:
            normalized = self._append_pay_type_history(normalized, effective_date)
        else:
            normalized["pay_type_history"] = _normalize_pay_type_history(
                previous.get("pay_type_history") or normalized.get("pay_type_history"),
                normalized.get("pay_type"),
                normalized.get("base_wage", 0),
                normalized.get("pay_effective_date") or normalized.get("hire_date") or effective_date,
            )
            if normalized["pay_type_history"]:
                latest = normalized["pay_type_history"][-1]
                normalized["pay_effective_date"] = str(latest.get("effective_date") or effective_date)
        self._ensure_business_exists(normalized["affiliated_business"])
        self._ensure_work_site_exists(normalized["affiliated_business"], normalized["work_site"])
        updated = False
        for index, row in enumerate(self._employees):
            if int(row["id"]) == int(employee_id):
                self._employees[index] = normalized
                updated = True
                break
        if not updated:
            existing_pending = next((row for row in self._pending_employee_sync if self._pending_entry_employee_id(row) == int(employee_id)), None)
            if existing_pending is not None:
                existing_pending["local_employee"] = deepcopy(normalized)
                existing_pending["payload"] = self._employee_to_server_payload(normalized, include_id=True)
                existing_pending["mode"] = "create" if str(existing_pending.get("mode") or "").strip().lower() == "create" else "update"
                existing_pending["last_error"] = ""
                existing_pending["retry_count"] = 0
                self._save_pending_employee_sync()
                updated = True
            else:
                raise ValueError("근로자를 찾을 수 없습니다.")
        settings = self.server_api_settings()
        if str(settings.get("base_url", "")).strip():
            self._queue_employee_server_sync("update", normalized)
        self.employees_changed.emit()
        self.attendance_changed.emit()
        return normalized


    def delete_employee_work_history_entry(self, employee_id: int, history_index: int) -> dict:
        target = self.get_employee_by_id(employee_id)
        if target is None:
            raise ValueError("근로자를 찾을 수 없습니다.")

        normalized = deepcopy(target)
        history = _normalize_work_history(
            normalized.get("work_history"),
            str(normalized.get("work_site") or "-").strip() or "-",
            normalized.get("hire_date") or self._today_string(),
            normalized.get("status") or "근무중",
            normalized.get("affiliated_business"),
            normalized.get("work_type"),
        )
        try:
            target_index = int(history_index)
        except (TypeError, ValueError):
            raise ValueError("삭제할 근무이력 위치가 올바르지 않습니다.")
        if target_index < 0 or target_index >= len(history):
            raise ValueError("삭제할 근무이력을 찾을 수 없습니다.")
        if len(history) <= 1:
            raise ValueError("기본 근무이력은 삭제할 수 없습니다.")

        row = history[target_index]
        if bool(row.get("active")) or not str(row.get("end_date") or "").strip():
            raise ValueError("현재 적용 중인 근무이력은 삭제할 수 없습니다.")

        del history[target_index]
        normalized["work_history"] = _normalize_work_history(
            history,
            str(normalized.get("work_site") or "-").strip() or "-",
            normalized.get("hire_date") or self._today_string(),
            normalized.get("status") or "근무중",
            normalized.get("affiliated_business"),
            normalized.get("work_type"),
        )
        if str(normalized.get("status") or "").strip() != "퇴사":
            normalized = self._ensure_current_work_history(normalized)

        normalized = normalize_employee(normalized, self._score_settings, self._rejoin_grades)

        updated = False
        for index, employee in enumerate(self._employees):
            if int(employee.get("id", 0) or 0) == int(employee_id):
                self._employees[index] = normalized
                updated = True
                break
        if not updated:
            raise ValueError("근로자를 찾을 수 없습니다.")

        settings = self.server_api_settings()
        if str(settings.get("base_url", "")).strip():
            self._queue_employee_server_sync("update", normalized)
        self.employees_changed.emit()
        self.attendance_changed.emit()
        return deepcopy(normalized)

    def resign_employee(self, employee_id: int, reason: str = "일반 퇴사", note: str = "", end_date: str | None = None):
        employee = self.get_employee_by_id(employee_id)
        if employee is None:
            raise ValueError("근로자를 찾을 수 없습니다.")
        return self.update_employee(
            employee_id,
            {
                "status": "퇴사",
                "active": False,
                "actual_end": employee.get("actual_end", "-") or "-",
                "resign_reason": str(reason or "일반 퇴사").strip() or "일반 퇴사",
                "resign_note": str(note or "").strip(),
                "actual_end": str(end_date or employee.get("actual_end") or "").strip() or self._today_string(),
            },
        )

    def delete_employee(self, employee_id: int):
        requested_id = self._safe_employee_id(employee_id, 0)
        target = self.get_employee_by_id(requested_id)
        if target is None:
            raise ValueError("근로자를 찾을 수 없습니다.")
        target_id = self._safe_employee_id(target.get("id", requested_id), requested_id)
        if target_id <= 0:
            raise ValueError("근로자 ID가 올바르지 않아 삭제할 수 없습니다.")
        # 예전 실패 대기열에 숫자가 아닌 employee_id가 남아 있으면 삭제 처리 중 int 변환 오류가 납니다.
        # 삭제 전에는 잘못된 대기열 행을 먼저 정리합니다.
        self._pending_employee_sync = [row for row in self._pending_employee_sync if self._pending_entry_employee_id(row) > 0]
        existing_pending = next((deepcopy(row) for row in self._pending_employee_sync if self._pending_entry_employee_id(row) == target_id), None)
        existing_pending_mode = str((existing_pending or {}).get("mode") or "").strip().lower()
        # 먼저 로컬 목록과 관련 자료를 즉시 제거합니다.
        # 이후 서버 목록 refresh가 먼저 들어와도 pending delete 가드가 재추가를 막습니다.
        self._purge_employee_related_local_data({target_id}, remove_files=True)
        self._save_pending_employee_sync()

        settings = self.server_api_settings()
        if str(settings.get("base_url", "")).strip() and existing_pending_mode != "create":
            self._queue_employee_server_sync("delete", target)
        else:
            if self._pending_employee_sync:
                self._emit_server_sync_notice(f"서버 전송 대기 {len(self._pending_employee_sync)}건")
            else:
                self._emit_server_sync_notice("대기 목록 정리 완료")

        self._dirty_sections.update({"core_people", "attendance", "records", "payroll"})
        self.employees_changed.emit()
        self.attendance_changed.emit()

    def business_master_records(self) -> list[dict]:
        self._businesses.sort(key=lambda row: row["name"])
        return [deepcopy(row) for row in self._businesses]

    def get_business(self, business_name: str) -> dict | None:
        name = _normalize_business_name(business_name)
        for business in self._businesses:
            if business["name"] == name:
                return deepcopy(business)
        return None

    def add_business(self, business: dict) -> dict:
        normalized = self._attach_business_defaults(business)
        if any(row["name"] == normalized["name"] for row in self._businesses):
            raise ValueError("이미 등록된 사업자명입니다.")
        self._businesses.append(normalized)
        self._businesses.sort(key=lambda row: row["name"])
        self.employees_changed.emit()
        return deepcopy(normalized)

    def update_business(self, original_name: str, business: dict) -> dict:
        original_name = _normalize_business_name(original_name)
        existing = self.get_business(original_name)
        normalized = self._attach_business_defaults({**(existing or {}), **(business or {})})
        if existing:
            normalized["business_id"] = existing.get("business_id", normalized.get("business_id", ""))
        for row in self._businesses:
            if row["name"] == normalized["name"] and row["name"] != original_name:
                raise ValueError("이미 등록된 사업자명입니다.")
        for index, row in enumerate(self._businesses):
            if row["name"] == original_name:
                self._businesses[index] = normalized
                payroll_changed = False
                if normalized["name"] != original_name:
                    for employee in self._employees:
                        if _normalize_business_name(employee["affiliated_business"]) == original_name:
                            employee["affiliated_business"] = normalized["name"]
                    for work_site in self._work_sites:
                        if _normalize_business_name(work_site["business_name"]) == original_name:
                            work_site["business_name"] = normalized["name"]
                            work_site["original_form"]["business_name"] = normalized["name"]
                    payroll_changed = self._move_payroll_business_settings(original_name, normalized["name"])
                self._work_sites.sort(key=lambda row: (row["business_name"], row["name"]))
                self.employees_changed.emit()
                self.attendance_changed.emit()
                if payroll_changed:
                    self.payroll_changed.emit()
                return deepcopy(normalized)
        raise ValueError("사업자를 찾을 수 없습니다.")

    def delete_business(self, business_name: str):
        name = _normalize_business_name(business_name)
        linked_employee_count = sum(1 for employee in self._employees if _normalize_business_name(employee["affiliated_business"]) == name)
        if linked_employee_count:
            raise ValueError("연결된 근로자가 있어 삭제할 수 없습니다.")
        linked_work_site_count = sum(1 for row in self._work_sites if _normalize_business_name(row["business_name"]) == name)
        if linked_work_site_count:
            raise ValueError("연결된 근무 사업장이 있어 먼저 정리해야 합니다.")
        before = len(self._businesses)
        self._businesses = [row for row in self._businesses if row["name"] != name]
        if len(self._businesses) == before:
            raise ValueError("사업자를 찾을 수 없습니다.")
        self.employees_changed.emit()

    def get_work_site(self, business_name: str, work_site_name: str) -> dict | None:
        business_name = _normalize_business_name(business_name)
        work_site_name = _normalize_work_site_name(work_site_name)
        for row in self._work_sites:
            if row["business_name"] == business_name and row["name"] == work_site_name:
                return deepcopy(row)
        return None

    def work_site_records(self, business_name: str | None = None) -> list[dict]:
        usage = self._work_site_usage_stats()
        known_keys = {(row["business_name"], row["name"]) for row in self._work_sites}
        known_keys |= set(usage.keys())
        rows: list[dict] = []
        filter_business = _normalize_business_name(business_name) if business_name else None
        for key in sorted(known_keys, key=lambda item: (item[0], item[1])):
            business_key, site_key = key
            if filter_business and business_key != filter_business:
                continue
            master = self.get_work_site(business_key, site_key) or normalize_work_site_record({
                "business_name": business_key,
                "name": site_key,
            })
            manager_display = self._manager_display_for_site(business_key, site_key)
            if manager_display:
                master["manager_name"] = manager_display
            elif not _clean_text(master.get("manager_name")):
                master["manager_name"] = ""
            stat = usage.get(key, {})
            rows.append({
                **master,
                "employee_count": stat.get("employee_count", 0),
                "active_count": stat.get("active_count", 0),
                "nation_count": len(stat.get("nations", set())),
                "status_text": "운영중" if master.get("active", True) else "중지",
            })
        return rows

    def add_work_site(self, business_name: str, work_site: dict) -> dict:
        self._ensure_business_exists(business_name)
        normalized = self._attach_work_site_defaults({**(work_site or {}), "business_name": business_name})
        if any(row["business_name"] == normalized["business_name"] and row["name"] == normalized["name"] for row in self._work_sites):
            raise ValueError("같은 사업자 아래에 이미 등록된 근무 사업장명입니다.")
        self._work_sites.append(normalized)
        self._work_sites.sort(key=lambda row: (row["business_name"], row["name"]))
        self.employees_changed.emit()
        return deepcopy(normalized)

    def update_work_site(self, business_name: str, original_name: str, work_site: dict) -> dict:
        business_name = _normalize_business_name(business_name)
        original_name = _normalize_work_site_name(original_name)
        new_business_name = _normalize_business_name(work_site.get("business_name", business_name))
        self._ensure_business_exists(new_business_name)
        
        existing = self.get_work_site(business_name, original_name)
        normalized = self._attach_work_site_defaults({**(existing or {}), **(work_site or {}), "business_name": new_business_name})
        if existing:
            normalized["work_site_id"] = existing.get("work_site_id", normalized.get("work_site_id", ""))
            
        for row in self._work_sites:
            if row["business_name"] == new_business_name and row["name"] == normalized["name"] and not (row["business_name"] == business_name and row["name"] == original_name):
                # 이미 동일한 이름의 사업장이 해당 사업자 아래에 있음 (충돌) -> 에러 대신 자동 병합(Merge) 및 이관 처리
                for employee in self._employees:
                    if (
                        _normalize_business_name(employee["affiliated_business"]) == business_name
                        and _normalize_work_site_name(employee.get("work_site") or employee.get("company")) == original_name
                    ):
                        employee["work_site"] = normalized["name"]
                        employee["company"] = normalized["name"]
                        employee["department"] = normalized["name"]
                        employee["affiliated_business"] = new_business_name
                payroll_changed = self._move_payroll_site_settings(
                    original_name,
                    business_name,
                    normalized["name"],
                    new_business_name,
                )
                # 이전 사업장(껍데기) 리스트에서 제거
                self._work_sites = [
                    x for x in self._work_sites 
                    if not (x["business_name"] == business_name and x["name"] == original_name)
                ]
                self.employees_changed.emit()
                self.attendance_changed.emit()
                if payroll_changed:
                    self.payroll_changed.emit()
                return deepcopy(row)
                
        for index, row in enumerate(self._work_sites):
            if row["business_name"] == business_name and row["name"] == original_name:
                self._work_sites[index] = normalized
                payroll_changed = False
                if normalized["name"] != original_name or new_business_name != business_name:
                    for employee in self._employees:
                        if (
                            _normalize_business_name(employee["affiliated_business"]) == business_name
                            and _normalize_work_site_name(employee.get("work_site") or employee.get("company")) == original_name
                        ):
                            employee["work_site"] = normalized["name"]
                            employee["company"] = normalized["name"]
                            employee["department"] = normalized["name"]
                            if new_business_name != business_name:
                                employee["affiliated_business"] = new_business_name
                    payroll_changed = self._move_payroll_site_settings(
                        original_name,
                        business_name,
                        normalized["name"],
                        new_business_name,
                    )
                self._work_sites.sort(key=lambda row: (row["business_name"], row["name"]))
                self.employees_changed.emit()
                self.attendance_changed.emit()
                if payroll_changed:
                    self.payroll_changed.emit()
                return deepcopy(normalized)
        raise ValueError("근무 사업장을 찾을 수 없습니다.")

    def delete_work_site(self, business_name: str, work_site_name: str):
        business_name = _normalize_business_name(business_name)
        work_site_name = _normalize_work_site_name(work_site_name)
        linked_count = sum(
            1
            for employee in self._employees
            if _normalize_business_name(employee["affiliated_business"]) == business_name
            and _normalize_work_site_name(employee.get("work_site") or employee.get("company")) == work_site_name
        )
        if linked_count:
            raise ValueError("배치된 근로자가 있어 삭제할 수 없습니다.")
        before = len(self._work_sites)
        self._work_sites = [
            row for row in self._work_sites
            if not (row["business_name"] == business_name and row["name"] == work_site_name)
        ]
        if len(self._work_sites) == before:
            raise ValueError("근무 사업장을 찾을 수 없습니다.")
        self.employees_changed.emit()

    def _impact_value(self, event_type: str) -> int:
        mapping = {
            "무단결근": self._score_settings["unauthorized_absence"],
            "무단이탈": self._score_settings["unauthorized_leave"],
            "지각": self._score_settings["late"],
            "조퇴": self._score_settings["early_leave"],
            "경고": self._score_settings["warning"],
            "병원": 0,
        }
        return mapping.get(event_type, 0)

    def _impact_text(self, event_type: str) -> str:
        value = self._impact_value(event_type)
        if value == 0:
            return "점수 영향 없음"
        return f"점수 {value}"

    def add_attendance_event(
        self,
        employee_id: int,
        event_type: str,
        date: str,
        time: str,
        process_status: str,
        memo: str,
    ) -> dict:
        employee = self.get_employee_by_id(employee_id)
        if employee is None:
            raise ValueError("근로자를 찾을 수 없습니다.")
        event_type = event_type.strip()
        if event_type not in EVENT_TYPES:
            raise ValueError("지원하지 않는 이벤트입니다.")

        impact_value = self._impact_value(event_type)
        employee["attendance_score"] = max(0, employee.get("attendance_score", self._score_settings["base_score"]) + impact_value)

        if event_type == "무단결근":
            employee["unauthorized_absence"] += 1
            employee["status"] = "무단결근"
            employee["absence_status"] = "무단결근"
            employee["actual_start"] = "-"
        elif event_type == "무단이탈":
            employee["unauthorized_leave"] += 1
            employee["status"] = "무단이탈"
        elif event_type == "지각":
            employee["late_count"] += 1
            employee["status"] = "지각"
            employee["late_status"] = "지각"
        elif event_type == "조퇴":
            employee["early_leave_count"] += 1
            employee["actual_end"] = time or employee.get("actual_end", "-")
            if employee["status"] not in ("퇴사", "무단결근", "무단이탈"):
                employee["status"] = "퇴근"
        elif event_type == "병원":
            employee["hospital_status"] = "병원"
            employee["status"] = "병원"
        elif event_type == "경고":
            employee["warning_count"] += 1

        employee["rejoin_grade"] = _grade_from_score(employee["attendance_score"], self._rejoin_grades)
        employee["note"] = memo.strip() or employee.get("note", "")

        event = {
            "date": date.strip(),
            "time": time.strip(),
            "employee_id": int(employee["id"]),
            "employee_name": employee["name"],
            "event_type": event_type,
            "business": employee["affiliated_business"],
            "work_site": employee["work_site"],
            "impact": self._impact_text(event_type),
            "process_status": process_status.strip() or "확인대기",
            "memo": memo.strip() or "-",
        }
        self._attendance_events.insert(0, event)
        self.employees_changed.emit()
        self.attendance_changed.emit()
        return event

    def update_score_settings(
        self,
        score_settings: dict[str, int],
        rejoin_grades: list[tuple[int, str]],
    ):
        self._score_settings = deepcopy(score_settings)
        self._rejoin_grades = sorted(deepcopy(rejoin_grades), key=lambda item: item[0], reverse=True)
        for employee in self._employees:
            employee["rejoin_grade"] = _grade_from_score(int(employee.get("attendance_score", 0)), self._rejoin_grades)
        self.settings_changed.emit()
        self.employees_changed.emit()
        self.attendance_changed.emit()

    def reset_settings(self):
        self.update_score_settings(self._default_score_settings, self._default_rejoin_grades)

    def business_records(self) -> list[dict]:
        stats = self._business_usage_stats()
        known_names = {row["name"] for row in self._businesses}
        known_names |= {row["business_name"] for row in self._work_sites}
        rows: list[dict] = []
        for name in sorted(known_names | set(stats.keys())):
            master = self.get_business(name) or normalize_business_record({"name": name})
            stat = stats.get(name, {})
            work_site_count = sum(1 for row in self._work_sites if row["business_name"] == name)
            if not work_site_count:
                work_site_count = len(stat.get("site_names", set()))
            rows.append({
                **master,
                "employee_count": stat.get("employee_count", 0),
                "active_count": stat.get("active_count", 0),
                "client_count": work_site_count,
                "work_site_count": work_site_count,
                "site_count": len(stat.get("site_names", set())),
                "nation_count": len(stat.get("nations", set())),
            })
        return rows

    def _repair_payroll_preset_collections(self):
        site_keys = set(self._payroll_settings_by_site.keys()) | {
            key for key in self._payroll_setting_presets_by_site.keys()
            if key != _global_payroll_setting_preset_scope_key()
        }
        for key in sorted(site_keys):
            active_settings = deepcopy(self._payroll_settings_by_site.get(key) or self._default_payroll_settings())
            bundle = self._payroll_setting_presets_by_site.get(key)
            if not isinstance(bundle, dict) or "presets" not in bundle:
                bundle = {"active_preset": DEFAULT_PAYROLL_PRESET_NAME, "presets": {DEFAULT_PAYROLL_PRESET_NAME: active_settings}}
            bundle = _normalize_named_settings_presets(bundle, active_settings)
            self._payroll_setting_presets_by_site[key] = bundle
            self._payroll_settings_by_site[key] = deepcopy(bundle["presets"][bundle["active_preset"]])

        self._ensure_global_payroll_setting_preset_bundle()

        item_keys = set(self._payroll_detail_items_by_site.keys()) | set(self._payroll_item_presets_by_site.keys())
        default_rows = [_normalize_payroll_detail_item(row, idx + 1) for idx, row in enumerate(DEFAULT_PAYROLL_DETAIL_ITEMS)]
        for key in sorted(item_keys):
            active_rows = deepcopy(self._payroll_detail_items_by_site.get(key) or default_rows)
            bundle = self._payroll_item_presets_by_site.get(key)
            if not isinstance(bundle, dict) or "presets" not in bundle:
                bundle = {"active_preset": DEFAULT_PAYROLL_PRESET_NAME, "presets": {DEFAULT_PAYROLL_PRESET_NAME: active_rows}}
            bundle = _normalize_named_item_presets(bundle, active_rows)
            self._payroll_item_presets_by_site[key] = bundle
            self._payroll_detail_items_by_site[key] = deepcopy(bundle["presets"][bundle["active_preset"]])

    def _ensure_payroll_setting_bundle(self, work_site_name: str | None, business_name: str | None = None) -> tuple[str, dict]:
        self._consume_legacy_payroll_site_key(work_site_name, business_name)
        key = _make_work_site_setting_key(work_site_name, business_name)
        active_settings = deepcopy(self._payroll_settings_by_site.get(key) or self._default_payroll_settings())
        bundle = self._payroll_setting_presets_by_site.get(key)
        if not isinstance(bundle, dict) or "presets" not in bundle:
            bundle = {"active_preset": DEFAULT_PAYROLL_PRESET_NAME, "presets": {DEFAULT_PAYROLL_PRESET_NAME: active_settings}}
        bundle = _normalize_named_settings_presets(bundle, active_settings)
        self._payroll_setting_presets_by_site[key] = bundle
        self._payroll_settings_by_site[key] = deepcopy(bundle["presets"][bundle["active_preset"]])
        return key, bundle

    def _ensure_global_payroll_setting_preset_bundle(self) -> dict:
        key = _global_payroll_setting_preset_scope_key()
        default_settings = self._default_payroll_settings()
        bundle = self._payroll_setting_presets_by_site.get(key)
        if not isinstance(bundle, dict) or "presets" not in bundle:
            bundle = {"active_preset": DEFAULT_PAYROLL_PRESET_NAME, "presets": {DEFAULT_PAYROLL_PRESET_NAME: deepcopy(default_settings)}}
        bundle = _normalize_named_settings_presets(bundle, default_settings)
        self._payroll_setting_presets_by_site[key] = bundle
        return bundle

    def _ensure_payroll_item_bundle(self, work_site_name: str | None, business_name: str | None = None) -> tuple[str, dict]:
        self._consume_legacy_payroll_site_key(work_site_name, business_name)
        key = _make_work_site_setting_key(work_site_name, business_name)
        default_rows = [_normalize_payroll_detail_item(row, idx + 1) for idx, row in enumerate(DEFAULT_PAYROLL_DETAIL_ITEMS)]
        active_rows = deepcopy(self._payroll_detail_items_by_site.get(key) or default_rows)
        bundle = self._payroll_item_presets_by_site.get(key)
        if not isinstance(bundle, dict) or "presets" not in bundle:
            bundle = {"active_preset": DEFAULT_PAYROLL_PRESET_NAME, "presets": {DEFAULT_PAYROLL_PRESET_NAME: active_rows}}
        bundle = _normalize_named_item_presets(bundle, active_rows)
        self._payroll_item_presets_by_site[key] = bundle
        self._payroll_detail_items_by_site[key] = deepcopy(bundle["presets"][bundle["active_preset"]])
        return key, bundle

    def list_payroll_setting_preset_names(self, work_site_name: str | None = None, business_name: str | None = None) -> list[str]:
        bundle = self._ensure_global_payroll_setting_preset_bundle()
        return list(bundle.get("presets", {}).keys())

    def get_active_payroll_setting_preset_name(self, work_site_name: str | None = None, business_name: str | None = None) -> str:
        bundle = self._ensure_global_payroll_setting_preset_bundle()
        return str(bundle.get("active_preset", DEFAULT_PAYROLL_PRESET_NAME))

    def get_payroll_setting_preset(self, preset_name: str) -> dict:
        bundle = self._ensure_global_payroll_setting_preset_bundle()
        preset = str(preset_name or "").strip()
        payload = bundle.get("presets", {}).get(preset)
        return deepcopy(payload if isinstance(payload, dict) else self._default_payroll_settings())

    def select_payroll_setting_preset(self, work_site_name: str | None, preset_name: str, business_name: str | None = None) -> bool:
        bundle = self._ensure_global_payroll_setting_preset_bundle()
        preset = str(preset_name or "").strip()
        if preset not in bundle.get("presets", {}):
            return False
        bundle["active_preset"] = preset
        self._payroll_setting_presets_by_site[_global_payroll_setting_preset_scope_key()] = bundle
        self.settings_changed.emit()
        self.payroll_changed.emit()
        return True

    def save_payroll_setting_preset(self, work_site_name: str | None, preset_name: str, settings: dict, business_name: str | None = None):
        bundle = self._ensure_global_payroll_setting_preset_bundle()
        preset = str(preset_name or "").strip() or DEFAULT_PAYROLL_PRESET_NAME
        bundle.setdefault("presets", {})[preset] = deepcopy(settings)
        bundle["active_preset"] = preset
        self._payroll_setting_presets_by_site[_global_payroll_setting_preset_scope_key()] = bundle
        self.settings_changed.emit()
        self.payroll_changed.emit()

    def delete_payroll_setting_preset(self, work_site_name: str | None, preset_name: str, business_name: str | None = None) -> bool:
        bundle = self._ensure_global_payroll_setting_preset_bundle()
        preset = str(preset_name or "").strip()
        presets = bundle.get("presets", {})
        if preset not in presets or len(presets) <= 1:
            return False
        del presets[preset]
        if bundle.get("active_preset") == preset:
            bundle["active_preset"] = next(iter(presets.keys()))
        self._payroll_setting_presets_by_site[_global_payroll_setting_preset_scope_key()] = bundle
        self.settings_changed.emit()
        self.payroll_changed.emit()
        return True

    def copy_payroll_setting_preset(self, work_site_name: str | None, source_preset_name: str, new_preset_name: str, business_name: str | None = None) -> bool:
        bundle = self._ensure_global_payroll_setting_preset_bundle()
        source = str(source_preset_name or "").strip()
        target = str(new_preset_name or "").strip()
        if not source or not target or source not in bundle.get("presets", {}):
            return False
        bundle.setdefault("presets", {})[target] = deepcopy(bundle["presets"][source])
        bundle["active_preset"] = target
        self._payroll_setting_presets_by_site[_global_payroll_setting_preset_scope_key()] = bundle
        self.settings_changed.emit()
        self.payroll_changed.emit()
        return True

    def apply_payroll_setting_preset_to_site(self, work_site_name: str | None, preset_name: str, business_name: str | None = None) -> bool:
        site = str(work_site_name or "").strip()
        if not site:
            return False
        settings = self.get_payroll_setting_preset(preset_name)
        self.update_payroll_settings(site, settings, business_name)
        return True

    def list_payroll_item_preset_names(self, work_site_name: str | None, business_name: str | None = None) -> list[str]:
        _key, bundle = self._ensure_payroll_item_bundle(work_site_name, business_name)
        return list(bundle.get("presets", {}).keys())

    def get_active_payroll_item_preset_name(self, work_site_name: str | None, business_name: str | None = None) -> str:
        _key, bundle = self._ensure_payroll_item_bundle(work_site_name, business_name)
        return str(bundle.get("active_preset", DEFAULT_PAYROLL_PRESET_NAME))

    def select_payroll_item_preset(self, work_site_name: str | None, preset_name: str, business_name: str | None = None) -> bool:
        key, bundle = self._ensure_payroll_item_bundle(work_site_name, business_name)
        preset = str(preset_name or "").strip()
        if preset not in bundle.get("presets", {}):
            return False
        bundle["active_preset"] = preset
        self._payroll_item_presets_by_site[key] = bundle
        self._payroll_detail_items_by_site[key] = deepcopy(bundle["presets"][preset])
        self.settings_changed.emit()
        self.payroll_changed.emit()
        return True

    def save_payroll_item_preset(self, work_site_name: str | None, preset_name: str, rows: list[dict], business_name: str | None = None):
        key, bundle = self._ensure_payroll_item_bundle(work_site_name, business_name)
        preset = str(preset_name or "").strip() or DEFAULT_PAYROLL_PRESET_NAME
        cleaned = [_normalize_payroll_detail_item(row, idx + 1) for idx, row in enumerate(rows or [])]
        if not cleaned:
            cleaned = [_normalize_payroll_detail_item(row, idx + 1) for idx, row in enumerate(DEFAULT_PAYROLL_DETAIL_ITEMS)]
        bundle.setdefault("presets", {})[preset] = deepcopy(cleaned)
        bundle["active_preset"] = preset
        self._payroll_item_presets_by_site[key] = bundle
        self._payroll_detail_items_by_site[key] = deepcopy(cleaned)
        self.settings_changed.emit()
        self.payroll_changed.emit()

    def delete_payroll_item_preset(self, work_site_name: str | None, preset_name: str, business_name: str | None = None) -> bool:
        key, bundle = self._ensure_payroll_item_bundle(work_site_name, business_name)
        preset = str(preset_name or "").strip()
        presets = bundle.get("presets", {})
        if preset not in presets or len(presets) <= 1:
            return False
        del presets[preset]
        if bundle.get("active_preset") == preset:
            bundle["active_preset"] = next(iter(presets.keys()))
        self._payroll_item_presets_by_site[key] = bundle
        self._payroll_detail_items_by_site[key] = deepcopy(presets[bundle["active_preset"]])
        self.settings_changed.emit()
        self.payroll_changed.emit()
        return True

    def copy_payroll_item_preset(self, work_site_name: str | None, source_preset_name: str, new_preset_name: str, business_name: str | None = None) -> bool:
        key, bundle = self._ensure_payroll_item_bundle(work_site_name, business_name)
        source = str(source_preset_name or "").strip()
        target = str(new_preset_name or "").strip()
        if not source or not target or source not in bundle.get("presets", {}):
            return False
        bundle.setdefault("presets", {})[target] = deepcopy(bundle["presets"][source])
        bundle["active_preset"] = target
        self._payroll_item_presets_by_site[key] = bundle
        self._payroll_detail_items_by_site[key] = deepcopy(bundle["presets"][target])
        self.settings_changed.emit()
        self.payroll_changed.emit()
        return True

    def client_records(self) -> list[dict]:
        rows = []
        for record in self.work_site_records():
            rows.append({
                "name": record["name"],
                "business_name": record["business_name"],
                "employee_count": record["employee_count"],
                "active_count": record["active_count"],
                "business_count": 1,
                "site_count": 1,
                "nation_count": record["nation_count"],
                "status_text": record["status_text"],
            })
        return rows

    def site_time_conversion_rules(self, work_site_name: str | None = None, business_name: str | None = None) -> list[dict]:
        rows = [deepcopy(row) for row in self._site_time_conversion_rules]
        site = str(work_site_name or "").strip()
        biz = str(business_name or "").strip()
        if site:
            rows = [row for row in rows if str(row.get("work_site_name", "") or "").strip() == site]
        if biz:
            rows = [row for row in rows if str(row.get("business_name", "") or "").strip() == biz]
        return rows

    def update_site_time_conversion_rules(self, rows: list[dict]):
        cleaned: list[dict] = []
        for idx, row in enumerate(rows or []):
            normalized = _normalize_site_time_conversion_rule(row, idx + 1)
            has_key_text = any(str(normalized.get(key, "") or "").strip() for key in [
                "business_name",
                "work_site_name",
                "area_name",
                "conversion_type",
                "day_type",
                "shift_type",
                "start_time",
                "end_time",
                "day_number",
                "memo",
            ])
            has_numbers = any(float(normalized.get(key, 0) or 0) != 0 for key in [
                "base_hours",
                "over_hours",
                "night_hours",
                "special_hours",
                "special_over_hours",
                "holiday_special_hours",
                "weekly_holiday_hours",
            ])
            if has_key_text or has_numbers:
                normalized["order"] = len(cleaned) + 1
                cleaned.append(normalized)
        self._site_time_conversion_rules = cleaned
        self.ensure_work_sites_from_time_conversion_rules(cleaned)
        self._dirty_sections.update({"settings", "core_people"})
        self.payroll_changed.emit()
        self.settings_changed.emit()

    def add_site_time_conversion_rule(self, row: dict):
        rules = self.site_time_conversion_rules()
        rules.append(_normalize_site_time_conversion_rule(row, len(rules) + 1))
        self.update_site_time_conversion_rules(rules)

    def get_payroll_settings(self, work_site_name: str, business_name: str | None = None) -> dict:
        from copy import deepcopy
        key, _bundle = self._ensure_payroll_setting_bundle(work_site_name, business_name)
        return deepcopy(self._payroll_settings_by_site.get(key, self._default_payroll_settings()))

    def get_employee_payroll_settings(self, employee: dict | int | None) -> dict:
        if isinstance(employee, int):
            employee = self.get_employee_by_id(employee) or {}
        employee = employee or {}
        site_name = str(employee.get("work_site") or employee.get("company") or "").strip()
        business_name = str(employee.get("affiliated_business") or "").strip() or None
        settings = self.get_payroll_settings(site_name, business_name)
        if not bool(employee.get("individual_payroll_enabled", False)):
            return settings
        overrides = employee.get("individual_payroll_field_overrides") or {}
        for key, raw in overrides.items():
            if isinstance(raw, dict):
                if not bool(raw.get("enabled", False)):
                    continue
                value = raw.get("value")
            else:
                if raw in (None, ""):
                    continue
                value = raw
            if value in (None, ""):
                continue
            settings[str(key)] = deepcopy(value)
        return settings

    def get_employee_payroll_detail_item_configs(self, employee: dict | int | None) -> list[dict]:
        if isinstance(employee, int):
            employee = self.get_employee_by_id(employee) or {}
        employee = employee or {}
        site_name = str(employee.get("work_site") or employee.get("company") or "").strip()
        business_name = str(employee.get("affiliated_business") or "").strip() or None
        rows = self.get_payroll_detail_item_configs(site_name, business_name)
        if not bool(employee.get("individual_payroll_enabled", False)):
            return rows
        overrides = employee.get("individual_payroll_item_overrides") or {}
        result: list[dict] = []
        for row in rows:
            copied = deepcopy(row)
            raw = overrides.get(str(copied.get("key", "")))
            enabled = False
            value = None
            if isinstance(raw, dict):
                enabled = bool(raw.get("enabled", False))
                value = raw.get("value")
            elif raw not in (None, ""):
                enabled = True
                value = raw
            if enabled and value not in (None, ""):
                try:
                    copied["default_value"] = float(value)
                except (TypeError, ValueError):
                    copied["default_value"] = copied.get("default_value", 0)
            result.append(copied)
        return result

    def get_employee_attendance_defaults(self, employee: dict | int | None) -> dict[str, float]:
        if isinstance(employee, int):
            employee = self.get_employee_by_id(employee) or {}
        settings = self.get_employee_payroll_settings(employee)

        def _to_float(key: str, default: float) -> float:
            try:
                return float(settings.get(key, default) or default)
            except (TypeError, ValueError):
                return float(default)

        return {
            "base": _to_float("attendance_base_hours", 8.0),
            "over": _to_float("attendance_over_hours", 0.0),
            "night": _to_float("attendance_night_hours", 8.0),
        }

    def update_payroll_settings(self, work_site_name: str, settings: dict, business_name: str | None = None):
        from copy import deepcopy
        key, bundle = self._ensure_payroll_setting_bundle(work_site_name, business_name)
        active_name = str(bundle.get("active_preset", DEFAULT_PAYROLL_PRESET_NAME))
        bundle.setdefault("presets", {})[active_name] = deepcopy(settings)
        self._payroll_setting_presets_by_site[key] = bundle
        self._payroll_settings_by_site[key] = deepcopy(settings)
        self.payroll_changed.emit()
        self.settings_changed.emit()

    def all_payroll_settings(self) -> dict[str, dict]:
        from copy import deepcopy
        result = {}
        for work_site in self.work_site_records():
            key = _make_work_site_setting_key(work_site.get("name"), work_site.get("business_name"))
            label = f"{work_site.get('business_name', '')} / {work_site.get('name', '')}".strip(" /")
            result[label] = deepcopy(self._payroll_settings_by_site.get(key, self._default_payroll_settings()))
        return result

    def _shift_cycle_days(self, cycle_value: str | None) -> int:
        return 7

    def get_site_attendance_defaults(self, work_site_name: str | None, business_name: str | None = None) -> dict[str, float]:
        settings = self.get_payroll_settings(work_site_name or "", business_name)

        def _to_float(key: str, default: float) -> float:
            try:
                return float(settings.get(key, default) or default)
            except (TypeError, ValueError):
                return float(default)

        return {
            "base": _to_float("attendance_base_hours", 8.0),
            "over": _to_float("attendance_over_hours", 0.0),
            "night": _to_float("attendance_night_hours", 8.0),
        }

    def get_default_attendance_hours(self, employee: dict | None, target_date: str | date | None, status: str = "출석") -> tuple[float, float, float]:
        employee = employee or {}
        if status not in ("출석", "지각", "조퇴", "병원"):
            return 0.0, 0.0, 0.0

        defaults = self.get_employee_attendance_defaults(employee)
        base = float(defaults.get("base", 8.0) or 0.0)
        over = float(defaults.get("over", 0.0) or 0.0)
        night_default = float(defaults.get("night", 8.0) or 0.0)

        work_type = self.get_employee_effective_work_type(employee)
        effective_group = "주간"
        if work_type == "야간":
            effective_group = "야간"
        elif work_type == "교대":
            effective_group = self.get_effective_shift_group(employee, target_date)

        night = night_default if effective_group == "야간" else 0.0
        return round(base, 2), round(over, 2), round(night, 2)

    def get_attendance_score_summary(self, employee_id: int, start_date: str | date, end_date: str | date) -> dict:
        try:
            start = start_date if isinstance(start_date, date) else datetime.strptime(str(start_date), "%Y-%m-%d").date()
            end = end_date if isinstance(end_date, date) else datetime.strptime(str(end_date), "%Y-%m-%d").date()
        except Exception as err:
            raise ValueError("조회 날짜 형식이 올바르지 않습니다.") from err

        if end < start:
            start, end = end, start

        employee = self.get_employee_by_id(int(employee_id)) or {}
        deductions = {
            "출석": 0,
            "휴무": 0,
            "병원": 0,
            "지각": int(self._score_settings.get("late", 0) or 0),
            "조퇴": int(self._score_settings.get("early_leave", 0) or 0),
            "결근": 0,
            "무단결근": int(self._score_settings.get("unauthorized_absence", 0) or 0),
            "무단이탈": int(self._score_settings.get("unauthorized_leave", 0) or 0),
        }
        counts = {key: 0 for key in deductions.keys()}
        score_delta = 0
        record_count = 0

        current = start
        while current <= end:
            record = self._monthly_records.get((int(employee_id), current.isoformat()), {})
            status = str(record.get("status", "") or "").strip()
            if status in deductions:
                counts[status] += 1
                score_delta += int(deductions[status])
                record_count += 1
            current += timedelta(days=1)

        base_score = int(self._score_settings.get("base_score", 100) or 100)
        score = max(0, base_score + score_delta)
        return {
            "employee_id": int(employee_id),
            "employee_name": employee.get("name", ""),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "base_score": base_score,
            "score": score,
            "grade": _grade_from_score(score, self._rejoin_grades),
            "record_count": record_count,
            "counts": counts,
            "deductions": deepcopy(deductions),
        }

    def get_weekly_paid_sunday_hours(self, employee_id: int, sunday_date: str | date | None) -> tuple[float, float, float]:
        """월~금이 모두 출석/지각/조퇴인 주의 일요일 기본시간을 공장 설정값으로 반환한다."""
        if sunday_date is None:
            return 0.0, 0.0, 0.0
        try:
            target = sunday_date if isinstance(sunday_date, date) else datetime.strptime(str(sunday_date), "%Y-%m-%d").date()
        except Exception:
            return 0.0, 0.0, 0.0
        if target.weekday() != 6:
            return 0.0, 0.0, 0.0

        employee = self.get_employee_by_id(int(employee_id)) or {}
        if not employee:
            return 0.0, 0.0, 0.0

        qualifying_statuses = {"출석", "지각", "조퇴"}
        for offset in range(6, 1, -1):
            weekday = target - timedelta(days=offset)
            record = self._monthly_records.get((int(employee_id), weekday.isoformat()), {})
            status = str(record.get("status", "") or "").strip()
            if status not in qualifying_statuses:
                return 0.0, 0.0, 0.0

        base, _over, _night = self.get_default_attendance_hours(employee, target, "출석")
        return round(base, 2), 0.0, 0.0

    def get_effective_shift_group(self, employee: dict | None, target_date: str | date | None) -> str:
        employee = employee or {}
        work_type = self.get_employee_effective_work_type(employee)
        if work_type == "야간":
            return "야간"
        if work_type != "교대":
            return "주간"

        settings = self.get_employee_payroll_settings(employee)
        start_group = str(settings.get("shift_start_group", "주간") or "주간").strip() or "주간"
        try:
            if isinstance(target_date, date):
                current_date = target_date
            else:
                current_date = datetime.strptime(str(target_date), "%Y-%m-%d").date()
        except Exception:
            return start_group

        # 교대는 별도 기준일 입력 없이 월요일~일요일을 1주 단위로 계산한다.
        # 2000-01-03은 월요일이며, 이 날짜부터 7일 단위로 주간/야간을 번갈아 적용한다.
        reference_monday = date(2000, 1, 3)
        week_index = (current_date - reference_monday).days // 7
        if week_index % 2 == 0:
            return start_group
        return "야간" if start_group == "주간" else "주간"


    # ──────────── 월별 근태 기록 (공유) ────────────

    def _remote_attendance_employee_lookup(self) -> tuple[
        dict[str, int],
        dict[tuple[str, str, str], int],
        dict[tuple[str, str], int],
        dict[str, int],
    ]:
        by_id: dict[str, int] = {}
        by_signature: dict[tuple[str, str, str], int] = {}
        by_name_site: dict[tuple[str, str], int] = {}
        by_name_only_candidates: dict[str, list[int]] = {}

        def _add_id(value, employee_id: int) -> None:
            raw = _normalize_remote_attendance_text(value)
            compact = _normalize_remote_attendance_key(value)
            for key in {raw, compact}:
                if key:
                    by_id[key] = employee_id
            try:
                numeric = str(int(raw))
            except (TypeError, ValueError):
                numeric = ""
            if numeric:
                by_id[numeric] = employee_id

        for employee in self._employees:
            try:
                employee_id = int((employee or {}).get("id", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                employee_id = 0
            if employee_id <= 0:
                continue

            _add_id(employee_id, employee_id)
            for key_name in ("server_id", "server_employee_id", "remote_id", "employee_id", "worker_id"):
                if (employee or {}).get(key_name) not in (None, ""):
                    _add_id((employee or {}).get(key_name), employee_id)
            try:
                display_no = str(self.employee_display_number(employee_id) or "").strip()
            except Exception:
                display_no = ""
            if display_no:
                _add_id(display_no, employee_id)

            name = _normalize_remote_attendance_key((employee or {}).get("name"))
            business = _normalize_remote_attendance_key((employee or {}).get("affiliated_business") or (employee or {}).get("business"))
            site = _normalize_remote_attendance_key((employee or {}).get("work_site") or (employee or {}).get("company") or (employee or {}).get("client"))
            signature = (name, business, site)
            if name and signature not in by_signature:
                by_signature[signature] = employee_id
            name_site = (name, site)
            if name and site and name_site not in by_name_site:
                by_name_site[name_site] = employee_id
            if name:
                by_name_only_candidates.setdefault(name, []).append(employee_id)

        by_name_only = {
            name: candidates[0]
            for name, candidates in by_name_only_candidates.items()
            if len(set(candidates)) == 1
        }
        return by_id, by_signature, by_name_site, by_name_only

    def _resolve_remote_attendance_employee_id(
        self,
        row: dict,
        by_id: dict[str, int],
        by_signature: dict[tuple[str, str, str], int],
        by_name_site: dict[tuple[str, str], int] | None = None,
        by_name_only: dict[str, int] | None = None,
    ) -> int:
        by_name_site = by_name_site or {}
        by_name_only = by_name_only or {}
        worker_id_raw = _normalize_remote_attendance_text((row or {}).get("worker_id") or (row or {}).get("employee_id"))
        worker_id_compact = _normalize_remote_attendance_key(worker_id_raw)
        for key in (worker_id_raw, worker_id_compact):
            if key and key in by_id:
                return by_id[key]
        try:
            numeric_worker_id = str(int(worker_id_raw))
        except (TypeError, ValueError):
            numeric_worker_id = ""
        if numeric_worker_id and numeric_worker_id in by_id:
            return by_id[numeric_worker_id]

        name = _normalize_remote_attendance_key((row or {}).get("worker_name") or (row or {}).get("name"))
        business = _normalize_remote_attendance_key((row or {}).get("business") or (row or {}).get("affiliated_business"))
        site = _normalize_remote_attendance_key((row or {}).get("site") or (row or {}).get("work_site"))
        signature = (name, business, site)
        if signature in by_signature:
            return int(by_signature.get(signature, 0) or 0)
        name_site = (name, site)
        if name_site in by_name_site:
            return int(by_name_site.get(name_site, 0) or 0)
        if name in by_name_only:
            return int(by_name_only.get(name, 0) or 0)
        return 0

    def _remote_attendance_skip_detail(self, row: dict, reason: str) -> dict:
        return {
            "reason": reason,
            "worker_id": _normalize_remote_attendance_text((row or {}).get("worker_id") or (row or {}).get("employee_id")),
            "worker_name": _normalize_remote_attendance_text((row or {}).get("worker_name") or (row or {}).get("name")),
            "business": _normalize_remote_attendance_text((row or {}).get("business") or (row or {}).get("affiliated_business")),
            "site": _normalize_remote_attendance_text((row or {}).get("site") or (row or {}).get("work_site")),
            "date": _normalize_remote_attendance_text((row or {}).get("attendance_date") or (row or {}).get("date")),
            "state": _normalize_remote_attendance_text((row or {}).get("state")),
            "source": _normalize_remote_attendance_text((row or {}).get("source")),
            "updated_by": _normalize_remote_attendance_text((row or {}).get("updated_by")),
        }

    def pull_attendance_month_from_server(self, month_str: str) -> dict:
        month_key = str(month_str or "").strip()
        if not re.match(r"^\d{4}-\d{2}$", month_key):
            return {"status": "skipped", "message": "조회 월 형식이 올바르지 않습니다.", "count": 0, "changed": False}

        settings = self.server_api_settings()
        if not str(settings.get("base_url", "")).strip():
            return {"status": "skipped", "message": "서버 주소가 설정되지 않았습니다.", "count": 0, "changed": False}

        response = fetch_attendance_month_remote(settings, month_key)
        rows = response.get("records") if isinstance(response, dict) else []
        if not isinstance(rows, list):
            rows = []

        by_id, by_signature, by_name_site, by_name_only = self._remote_attendance_employee_lookup()
        updates: dict[tuple[int, str], dict] = {}
        removals: list[tuple[int, str]] = []
        applied_count = 0
        skipped_count = 0
        skipped_details: list[dict] = []
        applied_keys: list[tuple[int, str]] = []

        for row in rows:
            if not isinstance(row, dict):
                skipped_count += 1
                if len(skipped_details) < 10:
                    skipped_details.append({"reason": "잘못된 서버 근태 형식"})
                continue
            source = _normalize_remote_attendance_key(row.get("source"))
            updated_by = _normalize_remote_attendance_key(row.get("updated_by"))
            if source == "test" or updated_by == "servertest":
                skipped_count += 1
                if len(skipped_details) < 10:
                    skipped_details.append(self._remote_attendance_skip_detail(row, "테스트 데이터 제외"))
                continue
            record_date = _normalize_remote_attendance_text(row.get("attendance_date") or row.get("date"))
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", record_date) or record_date[:7] != month_key:
                skipped_count += 1
                if len(skipped_details) < 10:
                    skipped_details.append(self._remote_attendance_skip_detail(row, "조회 월과 날짜 불일치"))
                continue
            employee_id = self._resolve_remote_attendance_employee_id(row, by_id, by_signature, by_name_site, by_name_only)
            if employee_id <= 0:
                skipped_count += 1
                if len(skipped_details) < 10:
                    skipped_details.append(self._remote_attendance_skip_detail(row, "PC 근로자 매칭 실패"))
                continue

            status = _remote_attendance_state_to_status(row.get("state"))
            target_key = (employee_id, record_date)
            applied_keys.append(target_key)
            if not status:
                removals.append(target_key)
                applied_count += 1
                continue

            employee = self.get_employee_by_id(employee_id) or {}
            base, over, night = self.get_default_attendance_hours(employee, record_date, status)
            updates[target_key] = {
                "status": status,
                "base": float(base or 0),
                "over": float(over or 0),
                "night": float(night or 0),
                "memo": _normalize_remote_attendance_text(row.get("note")),
            }
            applied_count += 1

        before = dict(self._monthly_records)
        self.set_monthly_records_bulk(updates, remove_keys=removals)
        changed = before != self._monthly_records
        if changed:
            # 서버 근태를 PC 로컬 저장소에 반영하되, 다시 서버 snapshot PUT으로 되돌려 보내지 않습니다.
            self._save_database_snapshot(sync_latest_backup=False, backup_reason="server-sync")

        return {
            "status": "ok",
            "year_month": month_key,
            "count": applied_count,
            "skipped": skipped_count,
            "changed": changed,
            "server_count": len(rows),
            "skipped_details": skipped_details,
            "applied_keys": applied_keys,
            "lock": response.get("lock") if isinstance(response, dict) else {},
        }

    def _manual_attendance_month_keys(self) -> list[str]:
        today = date.today()
        months: list[str] = []
        for year, month in (
            (today.year if today.month > 1 else today.year - 1, today.month - 1 if today.month > 1 else 12),
            (today.year, today.month),
            (today.year if today.month < 12 else today.year + 1, today.month + 1 if today.month < 12 else 1),
        ):
            key = f"{year:04d}-{month:02d}"
            if key not in months:
                months.append(key)
        return months

    def _pull_current_attendance_month_for_manual_sync(self) -> dict:
        month_keys = self._manual_attendance_month_keys()
        results: list[dict] = []
        total_count = 0
        total_skipped = 0
        total_server_count = 0
        changed = False
        errors: list[str] = []

        for month_key in month_keys:
            try:
                result = self.pull_attendance_month_from_server(month_key)
            except Exception as error:
                errors.append(f"{month_key}: {str(error or '근태 동기화 실패')}")
                continue
            if not isinstance(result, dict):
                errors.append(f"{month_key}: 근태 동기화 응답 형식 오류")
                continue
            result.setdefault("year_month", month_key)
            results.append(result)
            status = str(result.get("status") or "").lower()
            if status == "ok":
                total_count += int(result.get("count", 0) or 0)
                total_skipped += int(result.get("skipped", 0) or 0)
                total_server_count += int(result.get("server_count", 0) or 0)
                changed = changed or bool(result.get("changed", False))
            elif status == "error":
                errors.append(f"{month_key}: {str(result.get('message') or result.get('error') or '근태 동기화 실패')}")

        if results:
            return {
                "status": "ok",
                "year_month": month_keys[1] if len(month_keys) > 1 else month_keys[0],
                "months": month_keys,
                "count": total_count,
                "skipped": total_skipped,
                "server_count": total_server_count,
                "changed": changed,
                "results": results,
                "errors": errors,
            }
        return {
            "status": "error",
            "year_month": month_keys[1] if len(month_keys) > 1 else (month_keys[0] if month_keys else ""),
            "months": month_keys,
            "message": "; ".join(errors) if errors else "근태 동기화 실패",
            "count": 0,
            "changed": False,
        }

    def _manual_attendance_sync_summary(self, result: dict | None) -> str:
        if not isinstance(result, dict):
            return ""
        status = str(result.get("status") or "").lower()
        month_key = str(result.get("year_month") or "").strip()
        if status == "ok":
            count = int(result.get("count", 0) or 0)
            skipped = int(result.get("skipped", 0) or 0)
            changed = bool(result.get("changed", False))
            suffix = "반영" if changed else "확인"
            months = [str(value or "").strip() for value in (result.get("months") or []) if str(value or "").strip()]
            if len(months) >= 2:
                month_label = f"{months[0]}~{months[-1]}"
            else:
                month_label = month_key
            if skipped > 0:
                return f"근태 {month_label} {count}건 {suffix} / 제외 {skipped}건"
            return f"근태 {month_label} {count}건 {suffix}"
        if status == "skipped":
            message = str(result.get("message") or "근태 동기화 건너뜀").strip()
            return message
        message = str(result.get("message") or result.get("error") or "근태 동기화 실패").strip()
        return message

    def get_monthly_record(self, employee_id: int, date: str) -> dict:
        return dict(self._monthly_records.get((employee_id, date), {}))

    def set_monthly_record(self, employee_id: int, date: str, data: dict):
        self._monthly_records[(employee_id, date)] = dict(data)
        self.records_changed.emit()

    def set_monthly_records_bulk(
        self,
        records: dict[tuple[int, str], dict],
        *,
        remove_keys: list[tuple[int, str]] | None = None,
    ) -> None:
        changed = False
        for key, payload in (records or {}).items():
            employee_id = int(key[0])
            record_date = str(key[1]).strip()
            normalized = dict(payload or {})
            target_key = (employee_id, record_date)
            if self._monthly_records.get(target_key) != normalized:
                self._monthly_records[target_key] = normalized
                changed = True

        for key in remove_keys or []:
            employee_id = int(key[0])
            record_date = str(key[1]).strip()
            target_key = (employee_id, record_date)
            if target_key in self._monthly_records:
                self._monthly_records.pop(target_key, None)
                changed = True

        if changed:
            self.records_changed.emit()

    def delete_monthly_record(self, employee_id: int, date: str):
        self._monthly_records.pop((employee_id, date), None)
        self.records_changed.emit()

    def sync_monthly_records(self, records: dict):
        """attendance_page 내부 dict 를 AppState 에 통째로 동기화."""
        self._monthly_records = dict(records)
        self.records_changed.emit()

    @property
    def monthly_records(self) -> dict:
        return self._monthly_records

    # ──────────── 월별 급여 입력표 (수동 수정용) ────────────
    def _empty_payroll_month_entry(self) -> dict:
        return {
            "base": {},
            "over": {},
            "night": {},
            "cell_colors": {"base": {}, "over": {}, "night": {}},
            "imported_from_attendance": False,
        }

    def _normalize_payroll_month_entry_payload(self, entry: dict | None) -> dict:
        return normalize_payroll_month_entry(entry)

    def get_payroll_month_entry(self, employee_id: int, month_str: str) -> dict:
        return deepcopy(self._payroll_month_inputs.get((int(employee_id), month_str), self._empty_payroll_month_entry()))

    def has_payroll_month_entry(self, employee_id: int, month_str: str) -> bool:
        entry = self._payroll_month_inputs.get((int(employee_id), month_str), {})
        if not entry:
            return False
        return any(bool(entry.get(key)) for key in ("base", "over", "night"))

    def set_payroll_active_month(self, month_str: str | None):
        self._payroll_active_month = str(month_str).strip() if month_str else None
        self.payroll_changed.emit()

    def get_payroll_active_month(self) -> str | None:
        return self._payroll_active_month

    def _normalize_attendance_month_locks(self, source: dict | None) -> dict[str, dict]:
        normalized: dict[str, dict] = {}
        if not isinstance(source, dict):
            return normalized
        for raw_key, raw_payload in source.items():
            month_key = str(raw_key or "").strip()
            if not re.match(r"^\d{4}-\d{2}$", month_key):
                if isinstance(raw_payload, dict):
                    month_key = str(raw_payload.get("month_key") or raw_payload.get("year_month") or "").strip()
            if not re.match(r"^\d{4}-\d{2}$", month_key):
                continue
            payload = raw_payload if isinstance(raw_payload, dict) else {}
            locked = bool(payload.get("locked", payload.get("closed", True)))
            normalized[month_key] = {
                "month_key": month_key,
                "locked": locked,
                "locked_at": str(payload.get("locked_at") or payload.get("closed_at") or ""),
                "locked_by": str(payload.get("locked_by") or payload.get("closed_by") or "PC 급여관리"),
                "reopened_at": str(payload.get("reopened_at") or payload.get("cancelled_at") or payload.get("canceled_at") or ""),
                "reopened_by": str(payload.get("reopened_by") or payload.get("cancelled_by") or payload.get("canceled_by") or ""),
                "source": str(payload.get("source") or "PC 급여관리"),
                "memo": str(payload.get("memo") or ""),
            }
        return normalized

    def get_attendance_month_lock(self, month_str: str) -> dict | None:
        month_key = str(month_str or "").strip()
        payload = self._attendance_month_locks.get(month_key)
        return deepcopy(payload) if payload else None

    def is_attendance_month_locked(self, month_str: str) -> bool:
        payload = self.get_attendance_month_lock(month_str)
        return bool(payload and payload.get("locked"))

    def _sync_attendance_month_lock_remote(self, mode: str, month_key: str, payload: dict) -> dict:
        settings = self.server_api_settings()
        if not str(settings.get("base_url", "")).strip():
            return {"ok": False, "skipped": True, "message": "서버 주소가 설정되지 않았습니다."}
        try:
            if mode == "lock":
                response = close_attendance_month_remote(
                    settings,
                    month_key,
                    locked_by=str(payload.get("locked_by") or "PC 급여관리"),
                    source="pc",
                    note=str(payload.get("memo") or ""),
                )
                success_message = "월 마감 서버 반영 완료"
            else:
                response = reopen_attendance_month_remote(
                    settings,
                    month_key,
                    unlocked_by=str(payload.get("reopened_by") or "PC 급여관리"),
                    source="pc",
                    note=str(payload.get("memo") or ""),
                )
                success_message = "마감 취소 서버 반영 완료"
            ok = isinstance(response, dict) and str(response.get("status") or "").strip().lower() == "ok"
            return {
                "ok": ok,
                "message": success_message if ok else "서버 응답을 확인해야 합니다.",
                "response": response if isinstance(response, dict) else {},
                "synced_at": datetime.now().isoformat(timespec="seconds") if ok else "",
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc), "response": {}, "synced_at": ""}

    def close_attendance_month(self, month_str: str, *, locked_by: str = "PC 급여관리", memo: str = "") -> dict:
        month_key = str(month_str or "").strip()
        if not re.match(r"^\d{4}-\d{2}$", month_key):
            raise ValueError("month_str 형식은 yyyy-MM 이어야 합니다.")
        payload = {
            "month_key": month_key,
            "locked": True,
            "locked_at": datetime.now().isoformat(timespec="seconds"),
            "locked_by": str(locked_by or "PC 급여관리"),
            "source": "PC 급여관리",
            "memo": str(memo or ""),
        }
        sync_result = self._sync_attendance_month_lock_remote("lock", month_key, payload)
        payload["server_synced"] = bool(sync_result.get("ok"))
        payload["server_synced_at"] = str(sync_result.get("synced_at") or "")
        payload["server_sync_message"] = str(sync_result.get("message") or "")
        payload["server_sync_response"] = sync_result.get("response") if isinstance(sync_result.get("response"), dict) else {}
        self._attendance_month_locks[month_key] = payload
        self._dirty_sections.add("payroll")
        self.payroll_changed.emit()
        if payload["server_synced"]:
            self._emit_server_sync_notice(f"{month_key} 월 마감 서버 반영 완료")
        else:
            self._emit_server_sync_notice(f"{month_key} 월 마감 서버 반영 실패 · PC 자료 유지")
        return deepcopy(payload)

    def reopen_attendance_month(self, month_str: str, *, reopened_by: str = "PC 급여관리", memo: str = "") -> dict:
        month_key = str(month_str or "").strip()
        if not re.match(r"^\d{4}-\d{2}$", month_key):
            raise ValueError("month_str 형식은 yyyy-MM 이어야 합니다.")
        previous = self._attendance_month_locks.get(month_key) or {}
        payload = {
            "month_key": month_key,
            "locked": False,
            "locked_at": str(previous.get("locked_at") or ""),
            "locked_by": str(previous.get("locked_by") or "PC 급여관리"),
            "reopened_at": datetime.now().isoformat(timespec="seconds"),
            "reopened_by": str(reopened_by or "PC 급여관리"),
            "source": "PC 급여관리",
            "memo": str(memo or ""),
        }
        sync_result = self._sync_attendance_month_lock_remote("unlock", month_key, payload)
        payload["server_synced"] = bool(sync_result.get("ok"))
        payload["server_synced_at"] = str(sync_result.get("synced_at") or "")
        payload["server_sync_message"] = str(sync_result.get("message") or "")
        payload["server_sync_response"] = sync_result.get("response") if isinstance(sync_result.get("response"), dict) else {}
        self._attendance_month_locks[month_key] = payload
        self._dirty_sections.add("payroll")
        self.payroll_changed.emit()
        if payload["server_synced"]:
            self._emit_server_sync_notice(f"{month_key} 마감 취소 서버 반영 완료")
        else:
            self._emit_server_sync_notice(f"{month_key} 마감 취소 서버 반영 실패 · PC 자료 유지")
        return deepcopy(payload)

    def set_payroll_month_entry(self, employee_id: int, month_str: str, entry: dict):
        normalized = self._normalize_payroll_month_entry_payload(entry)
        self._payroll_month_inputs[(int(employee_id), month_str)] = normalized
        self._dirty_sections.add("payroll")
        self.payroll_changed.emit()

    def set_payroll_month_entries_bulk(self, month_str: str, entries_by_employee: dict[int, dict]) -> None:
        changed = False
        normalized_month = str(month_str).strip()
        for employee_id, entry in (entries_by_employee or {}).items():
            key = (int(employee_id), normalized_month)
            normalized = self._normalize_payroll_month_entry_payload(entry)
            if self._payroll_month_inputs.get(key) != normalized:
                self._payroll_month_inputs[key] = normalized
                changed = True
        if changed:
            self._dirty_sections.add("payroll")
            self.payroll_changed.emit()

    def _payroll_category_key(self, category: str) -> str:
        key_map = {
            "기본": "base",
            "연장": "over",
            "심야": "night",
            "base": "base",
            "over": "over",
            "night": "night",
        }
        return key_map.get(str(category).strip(), "base")

    def set_payroll_cell(self, employee_id: int, month_str: str, category: str, day: int, value: float):
        category_key = self._payroll_category_key(category)
        day_num = int(day)
        amount = float(value or 0)
        entry = deepcopy(self._payroll_month_inputs.get((int(employee_id), month_str), self._empty_payroll_month_entry()))
        entry = self._normalize_payroll_month_entry_payload(entry)
        if amount > 0:
            entry[category_key][day_num] = amount
        else:
            entry[category_key].pop(day_num, None)
        self._payroll_month_inputs[(int(employee_id), month_str)] = entry
        self._dirty_sections.add("payroll")
        self.payroll_changed.emit()

    def set_payroll_cell_color(self, employee_id: int, month_str: str, category: str, day: int, color_hex: str | None):
        category_key = self._payroll_category_key(category)
        day_num = int(day)
        entry = deepcopy(self._payroll_month_inputs.get((int(employee_id), month_str), self._empty_payroll_month_entry()))
        entry = self._normalize_payroll_month_entry_payload(entry)
        colors = entry.setdefault("cell_colors", {"base": {}, "over": {}, "night": {}})
        target = colors.setdefault(category_key, {})
        color_text = str(color_hex or "").strip().upper()
        if re.match(r"^#[0-9A-F]{6}$", color_text):
            target[day_num] = color_text
        else:
            target.pop(day_num, None)
        self._payroll_month_inputs[(int(employee_id), month_str)] = entry
        self._dirty_sections.add("payroll")
        self.payroll_changed.emit()

    def set_payroll_cell_colors_bulk(self, month_str: str, color_changes: list[tuple[int, str, int, str | None]]) -> None:
        normalized_month = str(month_str).strip()
        changed = False
        for employee_id, category, day, color_hex in color_changes or []:
            category_key = self._payroll_category_key(category)
            day_num = int(day)
            key = (int(employee_id), normalized_month)
            entry = deepcopy(self._payroll_month_inputs.get(key, self._empty_payroll_month_entry()))
            entry = self._normalize_payroll_month_entry_payload(entry)
            colors = entry.setdefault("cell_colors", {"base": {}, "over": {}, "night": {}})
            target = colors.setdefault(category_key, {})
            before = dict(target)
            color_text = str(color_hex or "").strip().upper()
            if re.match(r"^#[0-9A-F]{6}$", color_text):
                target[day_num] = color_text
            else:
                target.pop(day_num, None)
            if before != target or self._payroll_month_inputs.get(key) != entry:
                self._payroll_month_inputs[key] = entry
                changed = True
        if changed:
            self._dirty_sections.add("payroll")
            self.payroll_changed.emit()

    def import_payroll_month_from_attendance(self, month_str: str, employee_ids: list[int] | None = None, overwrite: bool = False):
        month_str = str(month_str).strip()
        if not re.match(r"^\d{4}-\d{2}$", month_str):
            raise ValueError("month_str 형식은 yyyy-MM 이어야 합니다.")
        year, month = map(int, month_str.split("-"))
        from calendar import monthrange
        last_day = monthrange(year, month)[1]
        target_ids = [int(emp_id) for emp_id in employee_ids] if employee_ids else [int(row["id"]) for row in self._employees if row.get("status") != "퇴사"]
        work_statuses = {"출석", "지각", "조퇴"}

        for employee_id in target_ids:
            entry = self._empty_payroll_month_entry() if overwrite else deepcopy(self._payroll_month_inputs.get((employee_id, month_str), self._empty_payroll_month_entry()))
            for day in range(1, last_day + 1):
                date_key = f"{month_str}-{day:02d}"
                record = self._monthly_records.get((employee_id, date_key), {})
                try:
                    base = float(record.get("base", 0) or 0)
                    over = float(record.get("over", 0) or 0)
                    night = float(record.get("night", 0) or 0)
                except (TypeError, ValueError):
                    base, over, night = 0.0, 0.0, 0.0
                status = str(record.get("status", "") or "").strip()
                employee = self.get_employee_by_id(employee_id) or {}
                if base <= 0 and over <= 0 and night <= 0 and status in work_statuses:
                    base, over, night = self.get_default_attendance_hours(employee, date_key, status)
                elif base <= 0 and over <= 0 and night <= 0 and status in {"", "휴무"}:
                    sunday_base, sunday_over, sunday_night = self.get_weekly_paid_sunday_hours(employee_id, date_key)
                    if sunday_base > 0 or sunday_over > 0 or sunday_night > 0:
                        base, over, night = sunday_base, sunday_over, sunday_night

                for category_key, amount in (("base", base), ("over", over), ("night", night)):
                    existing = float(entry.get(category_key, {}).get(day, 0) or 0)
                    if overwrite:
                        if amount > 0:
                            entry[category_key][day] = amount
                        else:
                            entry[category_key].pop(day, None)
                    else:
                        if existing <= 0 and amount > 0:
                            entry[category_key][day] = amount
            entry["imported_from_attendance"] = True
            self._payroll_month_inputs[(employee_id, month_str)] = entry

        self._payroll_active_month = month_str
        self.payroll_changed.emit()



    # ──────────── 차량관리 ────────────
    def vehicle_records(self) -> list[dict]:
        self._repair_vehicle_location_fields()
        return [deepcopy(row) for row in self._vehicles]

    def get_vehicle_by_id(self, vehicle_id: str) -> dict | None:
        target = str(vehicle_id or "").strip()
        for row in self._vehicles:
            if str(row.get("vehicle_id", "")).strip() == target:
                return deepcopy(row)
        return None

    def vehicle_alert_settings(self) -> dict:
        return deepcopy(self._vehicle_alert_settings)

    def update_vehicle_alert_settings(self, settings: dict):
        merged = deepcopy(self._vehicle_alert_settings)
        merged["remaining_km_threshold"] = max(0, int(settings.get("remaining_km_threshold", merged.get("remaining_km_threshold", 5000)) or 0))
        merged["contract_days_threshold"] = max(0, int(settings.get("contract_days_threshold", merged.get("contract_days_threshold", 30)) or 0))
        self._vehicle_alert_settings = merged
        self.settings_changed.emit()
        self.vehicles_changed.emit()

    def vehicle_server_sync_settings(self) -> dict:
        """차량관리 서버 연동 상태입니다.

        차량 데이터는 별도 사용 체크 없이 기본 연동 대상입니다.
        상단 수동 동기화와 10분 자동 동기화 흐름에 함께 포함됩니다.
        """
        return {
            "enabled": True,
            "last_status": str(self._app_settings.get("vehicle_server_sync_last_status", "기본 연동 대기") or "기본 연동 대기"),
            "last_at": str(self._app_settings.get("vehicle_server_sync_last_at", "") or ""),
            "last_error": str(self._app_settings.get("vehicle_server_sync_last_error", "") or ""),
        }

    def save_vehicle_server_sync_settings(self, enabled: bool = True) -> dict:
        # 이전 버전 호환용입니다. 이제 차량 연동은 끄지 않고 기본 연동 상태로 유지합니다.
        self._app_settings["vehicle_server_sync_enabled"] = True
        self._app_settings["vehicle_server_sync_last_status"] = "기본 연동 적용"
        self._app_settings["vehicle_server_sync_last_error"] = ""
        self._app_settings["vehicle_server_sync_last_at"] = datetime.now().isoformat(timespec="seconds")
        self._storage.save_app_settings(self._app_settings)
        self._emit_settings_changed_without_dirty()
        return self.vehicle_server_sync_settings()

    def mark_vehicle_server_sync_status(self, status: str, error: str = "") -> dict:
        self._app_settings["vehicle_server_sync_last_status"] = str(status or "").strip()
        self._app_settings["vehicle_server_sync_last_error"] = str(error or "").strip()
        self._app_settings["vehicle_server_sync_last_at"] = datetime.now().isoformat(timespec="seconds")
        self._storage.save_app_settings(self._app_settings)
        self._emit_settings_changed_without_dirty()
        return self.vehicle_server_sync_settings()

    def vehicle_server_sync_counts(self) -> dict:
        return {
            "vehicles": len(self._vehicles),
            "run_logs": len(self._vehicle_run_logs),
            "fuel_logs": len(self._vehicle_fuel_logs),
            "cost_logs": len(self._vehicle_cost_logs),
        }


    def _next_vehicle_id(self) -> str:
        numbers = []
        for row in self._vehicles:
            raw = str(row.get("vehicle_id", "") or "").strip()
            digits = re.sub(r"\D", "", raw)
            if digits:
                numbers.append(int(digits))
        return f"V{(max(numbers) + 1 if numbers else 1):03d}"

    def _estimate_contract_total_limit_km(self, annual_limit_km: float, contract_start: str | None, contract_end: str | None) -> int:
        annual_limit_km = float(annual_limit_km or 0)
        if annual_limit_km <= 0:
            return 0
        start = self._parse_date(contract_start)
        end = self._parse_date(contract_end)
        if not start or not end or end < start:
            return int(annual_limit_km)
        months = (end.year - start.year) * 12 + (end.month - start.month)
        # 계약 종료일이 시작일과 같은 일자인 경우는 정확히 만 n개월로 본다.
        # 예: 2024-11-05 ~ 2026-11-05 = 24개월 = 2년
        # 같은 일자를 포함 계산하면 25개월로 잡혀 3년(60,000km)으로 과대 계산된다.
        if end.day > start.day:
            months += 1
        contract_years = max(1, math.ceil(max(1, months) / 12))
        return int(annual_limit_km * contract_years)

    def estimate_contract_total_limit_km(self, annual_limit_km: float, contract_start: str | None, contract_end: str | None) -> int:
        return self._estimate_contract_total_limit_km(annual_limit_km, contract_start, contract_end)


    def _normalize_storage_suffix(self, suffix: str | None, default: str = ".png") -> str:
        ext = str(suffix or default).strip() or default
        if not ext.startswith("."):
            ext = f".{ext}"
        return ext.lower()

    def get_employee_portrait_storage_path(self, employee_id: int | str, suffix: str | None = ".png") -> tuple[Path, str]:
        self._storage.ensure_structure()
        target_path = self._storage.employee_portrait_path(employee_id, self._normalize_storage_suffix(suffix, ".png"))
        rel = target_path.relative_to(self._storage.data_dir).as_posix()
        return target_path, rel

    def get_employee_document_storage_path(self, employee_id: int | str, suffix: str | None = ".png") -> tuple[Path, str]:
        self._storage.ensure_structure()
        target_path = self._storage.employee_document_path(employee_id, self._normalize_storage_suffix(suffix, ".png"))
        rel = target_path.relative_to(self._storage.data_dir).as_posix()
        return target_path, rel

    def get_employee_original_document_storage_path(
        self,
        employee_id: int | str,
        document_kind: str | None = None,
        suffix: str | None = None,
    ) -> tuple[Path, str]:
        self._storage.ensure_structure()
        target_path = self._storage.employee_original_document_path(
            employee_id,
            document_kind,
            self._normalize_storage_suffix(suffix, ".png"),
        )
        rel = target_path.relative_to(self._storage.data_dir).as_posix()
        return target_path, rel

    def get_employee_corrected_document_storage_path(
        self,
        employee_id: int | str,
        document_kind: str | None = None,
        suffix: str | None = None,
    ) -> tuple[Path, str]:
        self._storage.ensure_structure()
        target_path = self._storage.employee_corrected_document_path(
            employee_id,
            document_kind,
            self._normalize_storage_suffix(suffix, ".png"),
        )
        rel = target_path.relative_to(self._storage.data_dir).as_posix()
        return target_path, rel

    def _infer_employee_document_kind_for_media(self, document_kind: str | None, *path_values: str | None) -> str:
        raw = str(document_kind or "").strip().lower()
        if raw in {"passport", "pp"}:
            return "passport"
        if raw in {"idcard", "id_card", "residence_card", "overseas_resident_card", "arc"}:
            return "idcard"
        for path_value in path_values:
            name = Path(str(path_value or "").replace("\\", "/")).name.lower()
            if "passport" in name:
                return "passport"
            if any(token in name for token in ("idcard", "id_card", "residence_card", "arc")):
                return "idcard"
        return "document"

    def _canonicalize_employee_media_path(
        self,
        employee_id: int | str,
        path_value: str | None,
        kind: str,
        document_kind: str | None = None,
    ) -> str:
        raw = str(path_value or "").strip()
        if not raw:
            return ""
        resolved = self.resolve_storage_file_path(raw)
        src = Path(resolved)
        if not src.exists() or not src.is_file():
            return raw
        if kind == "portrait":
            target_path, rel = self.get_employee_portrait_storage_path(employee_id, src.suffix or ".png")
        elif kind == "document":
            target_path, rel = self.get_employee_corrected_document_storage_path(
                employee_id,
                document_kind,
                src.suffix or ".png",
            )
        else:
            target_path, rel = self.get_employee_document_storage_path(employee_id, src.suffix or ".png")
        try:
            if target_path.exists() and target_path.resolve() == src.resolve():
                return rel
        except OSError:
            pass
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target_path)
        return rel

    def _stabilize_employee_media_payload(self, employee: dict) -> dict:
        payload = deepcopy(employee or {})
        employee_id = payload.get("id", 0)
        document_kind = self._infer_employee_document_kind_for_media(
            payload.get("document_type"),
            payload.get("document_path"),
            payload.get("original_document_path"),
        )
        payload["portrait_path"] = self._canonicalize_employee_media_path(
            employee_id,
            payload.get("portrait_path"),
            "portrait",
        )
        payload["document_path"] = self._canonicalize_employee_media_path(
            employee_id,
            payload.get("document_path"),
            "document",
            document_kind,
        )
        raw_original = str(payload.get("original_document_path") or "").strip()
        if raw_original:
            resolved = self.resolve_storage_file_path(raw_original)
            src = Path(resolved)
            if src.exists() and src.is_file():
                target_path, rel = self.get_employee_original_document_storage_path(employee_id, document_kind, src.suffix or ".png")
                try:
                    same_file = target_path.exists() and target_path.resolve() == src.resolve()
                except OSError:
                    same_file = False
                if not same_file:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, target_path)
                payload["original_document_path"] = rel
        return payload

    def _stabilize_employee_media_paths(self) -> bool:
        changed = False
        updated_rows: list[dict] = []
        for row in self._employees:
            updated = self._stabilize_employee_media_payload(row)
            if updated.get("portrait_path", "") != str(row.get("portrait_path", "") or ""):
                changed = True
            if updated.get("document_path", "") != str(row.get("document_path", "") or ""):
                changed = True
            if updated.get("original_document_path", "") != str(row.get("original_document_path", "") or ""):
                changed = True
            updated_rows.append(updated)
        if changed:
            self._employees = updated_rows
        return changed

    def get_storage_manager(self):
        return self._storage

    def resolve_storage_file_path(self, path: str | None) -> str:
        raw = str(path or "").strip()
        if not raw:
            return ""
        candidate = Path(raw)
        candidates: list[Path] = []
        normalized_raw = raw.replace("\\", "/").strip()
        if candidate.is_absolute():
            candidates.append(candidate)
        else:
            candidates.extend([
                self._storage.root_dir / candidate,
                self._storage.data_dir / candidate,
                self._storage.files_dir / candidate,
                self._storage.employee_files_dir / candidate,
                self._storage.legacy_storage_dir / candidate,
            ])

        marker_specs = [
            ("data/files/", self._storage.data_dir),
            ("files/", self._storage.data_dir),
            ("data/storage/", self._storage.data_dir),
            ("storage/", self._storage.data_dir),
        ]
        lowered = normalized_raw.lower()
        for marker, base_dir in marker_specs:
            idx = lowered.find(marker)
            if idx >= 0:
                suffix = normalized_raw[idx + len(marker):].lstrip("/")
                if suffix:
                    candidates.append(base_dir / Path(marker.rstrip("/")).name / Path(suffix) if marker in {"files/", "storage/"} else base_dir / Path(suffix))

        basename = Path(normalized_raw).name
        if basename.startswith("employee_") and basename.endswith("_portrait.png"):
            candidates.append(self._storage.legacy_employee_portraits_dir / basename)
        if basename.startswith("employee_") and basename.endswith("_document.png"):
            candidates.append(self._storage.legacy_employee_documents_dir / basename)

        seen: set[str] = set()
        deduped: list[Path] = []
        for item in candidates:
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        for item in deduped:
            try:
                if item.exists():
                    return str(item.resolve())
            except OSError:
                continue
        return raw

    def _parse_non_negative_float(self, value, field_name: str, *, max_value: float | None = None) -> float:
        try:
            number = float(value or 0)
        except (TypeError, ValueError):
            raise ValueError(f"{field_name}는 숫자로 입력해 주세요.")
        if number < 0:
            raise ValueError(f"{field_name}는 0 이상만 입력할 수 있습니다.")
        if max_value is not None and number > max_value:
            raise ValueError(f"{field_name}가 너무 큽니다.")
        return number

    def _parse_int_range(self, value, field_name: str, minimum: int, maximum: int) -> int:
        try:
            number = int(value or 0)
        except (TypeError, ValueError):
            raise ValueError(f"{field_name}는 숫자로 입력해 주세요.")
        if number < minimum or number > maximum:
            raise ValueError(f"{field_name}는 {minimum}~{maximum} 사이만 입력할 수 있습니다.")
        return number
    def _vehicle_compare_key(self, value) -> str:
        return re.sub(r"[\s\-_/·.,]+", "", str(value or "").strip()).lower()

    def _find_vehicle_business_master(self, business_name: str | None = None, business_id: str | None = None) -> dict | None:
        target_id = str(business_id or "").strip()
        target_key = self._vehicle_compare_key(business_name)
        if target_id:
            for row in self._businesses:
                if str(row.get("business_id", "") or "").strip() == target_id:
                    return deepcopy(row)
        if target_key:
            for row in self._businesses:
                if self._vehicle_compare_key(row.get("name")) == target_key:
                    return deepcopy(row)
        return None

    def _find_vehicle_work_site_master(self, business_name: str | None = None, work_site_name: str | None = None, work_site_id: str | None = None) -> dict | None:
        target_id = str(work_site_id or "").strip()
        business_key = self._vehicle_compare_key(business_name)
        site_key = self._vehicle_compare_key(work_site_name)
        if target_id:
            candidates = [row for row in self._work_sites if str(row.get("work_site_id", "") or "").strip() == target_id]
            if business_key:
                for row in candidates:
                    if self._vehicle_compare_key(row.get("business_name")) == business_key:
                        return deepcopy(row)
            if candidates:
                return deepcopy(candidates[0])
        if site_key:
            candidates = [row for row in self._work_sites if self._vehicle_compare_key(row.get("name")) == site_key]
            if business_key:
                for row in candidates:
                    if self._vehicle_compare_key(row.get("business_name")) == business_key:
                        return deepcopy(row)
            if len(candidates) == 1:
                return deepcopy(candidates[0])
        return None

    def _normalize_vehicle_location_payload(self, data: dict, existing: dict | None = None) -> dict:
        merged = {**deepcopy(existing or {}), **deepcopy(data or {})}
        business_id = str(merged.get("business_id", "") or "").strip()
        business_name = str(merged.get("business_name", "") or merged.get("business", "") or merged.get("company", "") or merged.get("company_name", "") or "").strip()
        work_site_id = str(merged.get("work_site_id", "") or "").strip()
        work_site_name = str(merged.get("work_site_name", "") or merged.get("work_site", "") or merged.get("site", "") or merged.get("site_name", "") or merged.get("factory", "") or "").strip()

        business = self._find_vehicle_business_master(business_name, business_id)
        if business:
            business_id = str(business.get("business_id", "") or business_id).strip()
            business_name = str(business.get("name", "") or business_name).strip()

        work_site = self._find_vehicle_work_site_master(business_name, work_site_name, work_site_id)
        if work_site:
            work_site_id = str(work_site.get("work_site_id", "") or work_site_id).strip()
            work_site_name = str(work_site.get("name", "") or work_site_name).strip()
            site_business_name = str(work_site.get("business_name", "") or "").strip()
            parent_business_id = str(work_site.get("parent_business_id", "") or "").strip()
            if site_business_name:
                business_name = site_business_name
            if parent_business_id:
                business_id = parent_business_id
            business = self._find_vehicle_business_master(business_name, business_id) or business
            if business:
                business_id = str(business.get("business_id", "") or business_id).strip()
                business_name = str(business.get("name", "") or business_name).strip()

        merged["business_id"] = business_id
        merged["business_name"] = business_name
        merged["business"] = business_name
        merged["company"] = business_name
        merged["company_name"] = business_name
        merged["work_site_id"] = work_site_id
        merged["work_site_name"] = work_site_name
        merged["work_site"] = work_site_name
        merged["site"] = work_site_name
        merged["site_name"] = work_site_name
        merged["factory"] = work_site_name
        return merged

    def _repair_vehicle_location_fields(self) -> bool:
        changed = False
        repaired: list[dict] = []
        for row in self._vehicles:
            if not isinstance(row, dict):
                continue
            normalized = self._normalize_vehicle_location_payload(row)
            if normalized != row:
                changed = True
            repaired.append(normalized)
        if changed:
            self._vehicles = repaired
            self._dirty_sections.update({"vehicles"})
        return changed
    def _copy_vehicle_contract_document(self, vehicle_id: str, source_path: str | None) -> str:
        raw = self.resolve_storage_file_path(source_path)
        if not raw:
            return ""
        src = Path(raw)
        if not src.exists() or not src.is_file():
            return ""
        self._storage.ensure_structure()
        target_dir = self._storage.vehicle_files_dir / str(vehicle_id).strip() / "contracts"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"rental_contract{src.suffix.lower()}"
        if target_path.exists() and target_path.resolve() == src.resolve():
            rel = target_path.relative_to(self._storage.data_dir)
            return rel.as_posix()
        shutil.copy2(src, target_path)
        rel = target_path.relative_to(self._storage.data_dir)
        return rel.as_posix()

    def _copy_vehicle_attachment_document(self, vehicle_id: str, source_path: str | None) -> str:
        raw = self.resolve_storage_file_path(source_path)
        if not raw:
            return ""
        src = Path(raw)
        if not src.exists() or not src.is_file():
            return ""
        self._storage.ensure_structure()
        target_dir = self._storage.vehicle_files_dir / str(vehicle_id).strip() / "attachments"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"attachment{src.suffix.lower()}"
        if target_path.exists() and target_path.resolve() == src.resolve():
            rel = target_path.relative_to(self._storage.data_dir)
            return rel.as_posix()
        shutil.copy2(src, target_path)
        rel = target_path.relative_to(self._storage.data_dir)
        return rel.as_posix()

    def save_vehicle_record(self, data: dict) -> dict:
        vehicle_id = str(data.get("vehicle_id", "") or "").strip() or self._next_vehicle_id()
        existing = self.get_vehicle_by_id(vehicle_id) or {}
        vehicle_type = "렌트카" if str(data.get("vehicle_type", existing.get("vehicle_type", "자차")) or "자차").strip() == "렌트카" else "자차"
        unlimited = bool(data.get("unlimited", existing.get("unlimited", False))) if vehicle_type == "렌트카" else False
        annual_limit_km = self._parse_non_negative_float(
            data.get("annual_limit_km", existing.get("annual_limit_km", 0)),
            "연간 허용 km",
            max_value=MAX_ANNUAL_LIMIT_KM,
        )
        baseline_odometer = self._parse_non_negative_float(
            data.get("baseline_odometer", existing.get("baseline_odometer", 0)),
            "시작 계기판 km",
            max_value=MAX_VEHICLE_ODOMETER,
        )

        contract_start = str(data.get("contract_start", existing.get("contract_start", "")) or "").strip()
        contract_end = str(data.get("contract_end", existing.get("contract_end", "")) or "").strip()
        contract_document_path = str(existing.get("contract_document_path", "") or "").strip()
        source_path = str(data.get("contract_document_source", "") or "").strip()
        if source_path:
            contract_document_path = self._copy_vehicle_contract_document(vehicle_id, source_path)
        attachment_document_path = str(existing.get("attachment_document_path", "") or "").strip()
        attachment_source_path = str(data.get("attachment_document_source", "") or "").strip()
        if attachment_source_path:
            attachment_document_path = self._copy_vehicle_attachment_document(vehicle_id, attachment_source_path)

        contract_total_limit_km = 0 if unlimited or vehicle_type != "렌트카" else self._estimate_contract_total_limit_km(annual_limit_km, contract_start, contract_end)

        location_payload = self._normalize_vehicle_location_payload(data, existing)

        payload = {
            "vehicle_id": vehicle_id,
            "vehicle_type": vehicle_type,
            "vehicle_name": str(data.get("vehicle_name", existing.get("vehicle_name", "")) or "").strip(),
            "plate_number": str(data.get("plate_number", existing.get("plate_number", "")) or "").strip(),
            "car_model": str(data.get("car_model", existing.get("car_model", "")) or "").strip(),
            "business_id": str(location_payload.get("business_id", "") or "").strip(),
            "business_name": str(location_payload.get("business_name", existing.get("business_name", "")) or "").strip(),
            "business": str(location_payload.get("business", location_payload.get("business_name", "")) or "").strip(),
            "company": str(location_payload.get("company", location_payload.get("business_name", "")) or "").strip(),
            "company_name": str(location_payload.get("company_name", location_payload.get("business_name", "")) or "").strip(),
            "work_site_id": str(location_payload.get("work_site_id", "") or "").strip(),
            "work_site_name": str(location_payload.get("work_site_name", existing.get("work_site_name", "")) or "").strip(),
            "work_site": str(location_payload.get("work_site", location_payload.get("work_site_name", "")) or "").strip(),
            "site": str(location_payload.get("site", location_payload.get("work_site_name", "")) or "").strip(),
            "site_name": str(location_payload.get("site_name", location_payload.get("work_site_name", "")) or "").strip(),
            "factory": str(location_payload.get("factory", location_payload.get("work_site_name", "")) or "").strip(),
            "main_driver": str(data.get("main_driver", existing.get("main_driver", "")) or "").strip(),
            "status": str(data.get("status", existing.get("status", "운행중")) or "운행중").strip(),
            "rental_company": str(data.get("rental_company", existing.get("rental_company", "")) or "").strip() if vehicle_type == "렌트카" else "",
            "contract_start": contract_start if vehicle_type == "렌트카" else "",
            "contract_end": contract_end if vehicle_type == "렌트카" else "",
            "annual_limit_km": int(annual_limit_km if vehicle_type == "렌트카" else 0),
            "contract_total_limit_km": int(contract_total_limit_km if vehicle_type == "렌트카" else 0),
            "unlimited": unlimited if vehicle_type == "렌트카" else False,
            "baseline_odometer": baseline_odometer,
            "note": str(data.get("note", existing.get("note", "")) or "").strip(),
            "attachment_document_path": attachment_document_path,
            "contract_document_path": contract_document_path if vehicle_type == "렌트카" else "",
        }

        if not payload["vehicle_name"]:
            raise ValueError("차량명을 입력해 주세요.")
        if not payload["plate_number"]:
            raise ValueError("차량번호를 입력해 주세요.")
        if vehicle_type == "렌트카" and not unlimited:
            start_date = self._parse_date(contract_start)
            end_date = self._parse_date(contract_end)
            if not start_date or not end_date:
                raise ValueError("렌트카는 계약 시작일과 종료일을 확인해 주세요.")
            if end_date < start_date:
                raise ValueError("계약 종료일은 시작일보다 빠를 수 없습니다.")

        updated = False
        for idx, row in enumerate(self._vehicles):
            if str(row.get("vehicle_id", "") or "").strip() == vehicle_id:
                self._vehicles[idx] = payload
                updated = True
                break
        if not updated:
            self._vehicles.append(payload)
        self.vehicles_changed.emit()
        return deepcopy(payload)

    def delete_vehicle_record(self, vehicle_id: str):
        target = str(vehicle_id or "").strip()
        if not target:
            return
        if any(str(row.get("vehicle_id", "") or "").strip() == target for row in self._vehicle_run_logs):
            raise ValueError("운행기록이 있는 차량은 삭제할 수 없습니다.")
        if any(str(row.get("vehicle_id", "") or "").strip() == target for row in self._vehicle_fuel_logs):
            raise ValueError("주유기록이 있는 차량은 삭제할 수 없습니다.")
        if any(str(row.get("vehicle_id", "") or "").strip() == target for row in self._vehicle_cost_logs):
            raise ValueError("기타비용 기록이 있는 차량은 삭제할 수 없습니다.")
        self._vehicles = [row for row in self._vehicles if str(row.get("vehicle_id", "") or "").strip() != target]
        self.vehicles_changed.emit()

    def _next_vehicle_run_log_id(self) -> str:
        numbers: list[int] = []
        for row in self._vehicle_run_logs:
            raw = str(row.get("log_id", "") or "").strip()
            match = re.fullmatch(r"VR(\d+)", raw)
            if match:
                numbers.append(int(match.group(1)))
        return f"VR{(max(numbers) + 1 if numbers else 1):03d}"

    def _next_vehicle_fuel_log_id(self) -> str:
        numbers: list[int] = []
        for row in self._vehicle_fuel_logs:
            raw = str(row.get("fuel_id", "") or "").strip()
            match = re.fullmatch(r"VF(\d+)", raw)
            if match:
                numbers.append(int(match.group(1)))
        return f"VF{(max(numbers) + 1 if numbers else 1):03d}"

    def _next_vehicle_cost_log_id(self) -> str:
        numbers: list[int] = []
        for row in self._vehicle_cost_logs:
            raw = str(row.get("cost_id", "") or "").strip()
            match = re.fullmatch(r"VC(\d+)", raw)
            if match:
                numbers.append(int(match.group(1)))
        return f"VC{(max(numbers) + 1 if numbers else 1):03d}"

    def _parse_date(self, value: str | None) -> date | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        return None

    def _parse_datetime(self, value: str | None) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        normalized = raw.replace("T", " ").replace("Z", "")
        if "+" in normalized:
            normalized = normalized.split("+", 1)[0].strip()
        if "." in normalized:
            normalized = normalized.split(".", 1)[0].strip()
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue
        return None

    def _vehicle_run_order_key(self, row: dict, fallback_index: int = 0) -> tuple:
        log_date = self._parse_date(row.get("date") or row.get("log_date")) or date.min
        saved_at = self._parse_datetime(row.get("saved_at") or row.get("savedAt") or row.get("updated_at"))
        if saved_at is None:
            saved_at = datetime.min
        return (log_date, saved_at, str(row.get("log_id", "") or ""), fallback_index)

    def _vehicle_run_target_order_key(self, vehicle_id: str, target_date: str | None, exclude_log_id: str | None = None) -> tuple:
        target_vehicle_id = str(vehicle_id or "").strip()
        exclude_id = str(exclude_log_id or "").strip()
        parsed_target = self._parse_date(target_date) or date.max
        if exclude_id:
            for idx, row in enumerate(self._vehicle_run_logs):
                if not isinstance(row, dict):
                    continue
                if str(row.get("vehicle_id", "") or "").strip() != target_vehicle_id:
                    continue
                if str(row.get("log_id", "") or "").strip() == exclude_id:
                    existing_key = self._vehicle_run_order_key(row, idx)
                    return (parsed_target, existing_key[1], existing_key[2], existing_key[3])
        return (parsed_target, datetime.max, "~", 10**12)

    def _annotated_vehicle_run_logs(self) -> list[dict]:
        annotated: list[dict] = []
        baseline_by_vehicle = {str(v.get("vehicle_id")): float(v.get("baseline_odometer", 0) or 0) for v in self._vehicles}
        grouped: dict[str, list[dict]] = {}
        for row in self._vehicle_run_logs:
            grouped.setdefault(str(row.get("vehicle_id", "")).strip(), []).append(deepcopy(row))
        for vehicle_id, rows in grouped.items():
            rows.sort(key=lambda item: self._vehicle_run_order_key(item))
            prev_end = float(baseline_by_vehicle.get(vehicle_id, 0) or 0)
            for row in rows:
                try:
                    end_odometer = float(row.get("end_odometer", 0) or 0)
                except (TypeError, ValueError):
                    end_odometer = prev_end
                run_km = max(0.0, end_odometer - prev_end)
                annotated.append({
                    **row,
                    "prev_odometer": prev_end,
                    "run_km": run_km,
                })
                prev_end = end_odometer
        annotated.sort(key=lambda item: (str(item.get("vehicle_id", "") or ""), self._vehicle_run_order_key(item)))
        return annotated

    def _vehicle_current_odometer(self, vehicle_id: str) -> float:
        vehicle = self.get_vehicle_by_id(vehicle_id) or {}
        baseline = float(vehicle.get("baseline_odometer", 0) or 0)
        current = baseline
        for row in self._annotated_vehicle_run_logs():
            if str(row.get("vehicle_id", "")).strip() == str(vehicle_id).strip():
                current = float(row.get("end_odometer", current) or current)
        return current

    def _vehicle_total_used_km(self, vehicle_id: str) -> float:
        vehicle = self.get_vehicle_by_id(vehicle_id) or {}
        baseline = float(vehicle.get("baseline_odometer", 0) or 0)
        return max(0.0, self._vehicle_current_odometer(vehicle_id) - baseline)

    def _vehicle_alert_status(self, vehicle: dict) -> tuple[str, str, int | None, float | None]:
        if not vehicle:
            return "정상", "정상", None, None
        settings = self._vehicle_alert_settings
        remain_threshold = int(settings.get("remaining_km_threshold", 5000) or 0)
        day_threshold = int(settings.get("contract_days_threshold", 30) or 0)
        today = date.today()

        days_left: int | None = None
        end_date = self._parse_date(vehicle.get("contract_end"))
        if end_date:
            days_left = (end_date - today).days

        remaining_km: float | None = None
        over_limit = False
        km_warning = False
        if str(vehicle.get("vehicle_type", "")) == "렌트카" and not bool(vehicle.get("unlimited")):
            total_limit = float(vehicle.get("contract_total_limit_km", 0) or 0)
            if total_limit > 0:
                remaining_km = total_limit - self._vehicle_total_used_km(vehicle.get("vehicle_id", ""))
                over_limit = remaining_km < 0
                km_warning = remaining_km <= remain_threshold

        contract_warning = days_left is not None and days_left <= day_threshold
        if over_limit:
            return "초과", "km 초과", days_left, remaining_km
        if contract_warning and km_warning:
            return "계약임박", "km·기한 임박", days_left, remaining_km
        if contract_warning:
            return "계약임박", "계약 종료 임박", days_left, remaining_km
        if km_warning:
            return "km임박", "남은 km 임박", days_left, remaining_km
        if str(vehicle.get("vehicle_type", "")) == "렌트카" and bool(vehicle.get("unlimited")):
            return "무제한", "무제한 계약", days_left, remaining_km
        return "정상", "정상", days_left, remaining_km

    def vehicle_main_driver_candidates(self, business_name: str | None = None, work_site_name: str | None = None) -> list[str]:
        target_business = _normalize_business_name(business_name) if str(business_name or "").strip() else ""
        target_site = _normalize_work_site_name(work_site_name) if str(work_site_name or "").strip() else ""
        seen: set[str] = set()
        ordered: list[str] = []

        def display_name(account: dict) -> str:
            return str(account.get("employee_name") or account.get("username") or "").strip()

        def add_account(account: dict):
            if not bool(account.get("active", True)):
                return
            name = display_name(account)
            if not name or name in seen:
                return
            seen.add(name)
            ordered.append(name)

        # 1순위: 선택한 사업자 + 근무사업장에 배정된 담당자
        if target_business and target_site:
            for account in self._manager_accounts:
                for pair in self._manager_site_pairs(account):
                    if (
                        _normalize_business_name(pair.get("business")) == target_business
                        and _normalize_work_site_name(pair.get("work_site")) == target_site
                    ):
                        add_account(account)
                        break

        # 2순위: 선택한 사업자에 배정된 담당자
        if target_business:
            for account in self._manager_accounts:
                for pair in self._manager_site_pairs(account):
                    if _normalize_business_name(pair.get("business")) == target_business:
                        add_account(account)
                        break

        # 3순위: 활성 관리자/담당자 전체
        for account in self._manager_accounts:
            add_account(account)
        return ordered

    def vehicle_driver_candidates(self, business_name: str | None = None) -> list[str]:
        target_business = str(business_name or "").strip()
        vehicle_business_map = {str(row.get("vehicle_id", "")).strip(): str(row.get("business_name", "")).strip() for row in self._vehicles}
        seen: set[str] = set()
        ordered: list[str] = []

        def add_name(value: str | None):
            name = str(value or "").strip()
            if not name or name in seen:
                return
            seen.add(name)
            ordered.append(name)

        if target_business:
            for row in self.business_master_records():
                if str(row.get("name", "") or "").strip() == target_business:
                    add_name(row.get("manager_name"))
            for row in self._vehicles:
                if str(row.get("business_name", "") or "").strip() == target_business:
                    add_name(row.get("main_driver"))
            for row in self._vehicle_run_logs:
                if vehicle_business_map.get(str(row.get("vehicle_id", "")).strip(), "") == target_business:
                    add_name(row.get("driver_name"))

        for row in self.business_master_records():
            add_name(row.get("manager_name"))
        for row in self._vehicles:
            add_name(row.get("main_driver"))
        for row in self._vehicle_run_logs:
            add_name(row.get("driver_name"))
        return ordered

    def vehicle_summary_rows(self, year: int, month: int, vehicle_type: str = "전체", vehicle_id: str | None = None, driver_filter: str | None = None) -> list[dict]:
        target_id = str(vehicle_id or "").strip()
        type_filter = str(vehicle_type or "전체").strip()
        driver_filter = str(driver_filter or "").strip().lower()
        run_rows = self._annotated_vehicle_run_logs()
        fuel_rows = [deepcopy(row) for row in self._vehicle_fuel_logs]
        cost_rows = [deepcopy(row) for row in self._vehicle_cost_logs]
        rows: list[dict] = []
        for vehicle in self._vehicles:
            vid = str(vehicle.get("vehicle_id", "")).strip()
            if target_id and vid != target_id:
                continue
            if type_filter and type_filter != "전체" and str(vehicle.get("vehicle_type", "")).strip() != type_filter:
                continue
            if driver_filter and driver_filter not in str(vehicle.get("main_driver", "")).lower():
                matched = any(driver_filter in str(log.get("driver_name", "")).lower() for log in run_rows if str(log.get("vehicle_id", "")).strip() == vid)
                if not matched:
                    continue
            month_logs = [row for row in run_rows if str(row.get("vehicle_id", "")).strip() == vid and (self._parse_date(row.get("date")) or date.min).year == int(year) and (self._parse_date(row.get("date")) or date.min).month == int(month)]
            month_fuels = [row for row in fuel_rows if str(row.get("vehicle_id", "")).strip() == vid and (self._parse_datetime(row.get("fuel_date")) or datetime.min).year == int(year) and (self._parse_datetime(row.get("fuel_date")) or datetime.min).month == int(month)]
            month_costs = [row for row in cost_rows if str(row.get("vehicle_id", "")).strip() == vid and (self._parse_datetime(row.get("cost_date")) or datetime.min).year == int(year) and (self._parse_datetime(row.get("cost_date")) or datetime.min).month == int(month)]
            monthly_km = sum(float(row.get("run_km", 0) or 0) for row in month_logs)
            fuel_total = sum(float(row.get("amount", 0) or 0) for row in month_fuels)
            cost_total = sum(float(row.get("amount", 0) or 0) for row in month_costs)
            latest_fuel = max((row.get("fuel_date", "") for row in month_fuels), default="")
            status_text, status_note, days_left, remaining_km = self._vehicle_alert_status(vehicle)
            total_used_km = self._vehicle_total_used_km(vid)
            current_odometer = self._vehicle_current_odometer(vid)
            rows.append({
                **deepcopy(vehicle),
                "monthly_km": round(monthly_km, 1),
                "fuel_total": int(fuel_total),
                "cost_total": int(cost_total),
                "recent_fuel_date": latest_fuel,
                "total_used_km": round(total_used_km, 1),
                "current_odometer": round(current_odometer, 1),
                "status_text": status_text,
                "status_note": status_note,
                "days_left": days_left,
                "remaining_km": None if remaining_km is None else round(remaining_km, 1),
                "monthly_run_count": len(month_logs),
                "monthly_fuel_count": len(month_fuels),
                "monthly_cost_count": len(month_costs),
            })
        rows.sort(key=lambda item: (0 if item.get("vehicle_type") == "렌트카" else 1, str(item.get("vehicle_name", ""))))
        return rows

    def vehicle_run_log_rows(self, year: int, month: int, vehicle_id: str | None = None, driver_filter: str | None = None) -> list[dict]:
        target_id = str(vehicle_id or "").strip()
        driver_filter = str(driver_filter or "").strip().lower()
        rows = []
        vehicle_map = {str(row.get("vehicle_id", "")).strip(): row for row in self._vehicles}
        for row in self._annotated_vehicle_run_logs():
            parsed = self._parse_date(row.get("date"))
            if not parsed or parsed.year != int(year) or parsed.month != int(month):
                continue
            vid = str(row.get("vehicle_id", "")).strip()
            if target_id and vid != target_id:
                continue
            if driver_filter and driver_filter not in str(row.get("driver_name", "")).lower():
                continue
            vehicle = vehicle_map.get(vid, {})
            rows.append({
                **deepcopy(row),
                "vehicle_name": vehicle.get("vehicle_name", vid),
                "vehicle_type": vehicle.get("vehicle_type", ""),
                "plate_number": vehicle.get("plate_number", ""),
            })
        rows.sort(key=lambda item: (item.get("date", ""), item.get("vehicle_name", ""), item.get("log_id", "")), reverse=True)
        return rows

    def vehicle_fuel_log_rows(self, year: int, month: int, vehicle_id: str | None = None) -> list[dict]:
        target_id = str(vehicle_id or "").strip()
        rows = []
        vehicle_map = {str(row.get("vehicle_id", "")).strip(): row for row in self._vehicles}
        for row in self._vehicle_fuel_logs:
            parsed = self._parse_datetime(row.get("fuel_date"))
            if not parsed or parsed.year != int(year) or parsed.month != int(month):
                continue
            vid = str(row.get("vehicle_id", "")).strip()
            if target_id and vid != target_id:
                continue
            vehicle = vehicle_map.get(vid, {})
            rows.append({
                **deepcopy(row),
                "vehicle_name": vehicle.get("vehicle_name", vid),
                "vehicle_type": vehicle.get("vehicle_type", ""),
                "plate_number": vehicle.get("plate_number", ""),
            })
        rows.sort(key=lambda item: (item.get("fuel_date", ""), item.get("vehicle_name", ""), item.get("fuel_id", "")), reverse=True)
        return rows


    def vehicle_cost_log_rows(self, year: int, month: int, vehicle_id: str | None = None) -> list[dict]:
        target_id = str(vehicle_id or "").strip()
        rows = []
        vehicle_map = {str(row.get("vehicle_id", "")).strip(): row for row in self._vehicles}
        for row in self._vehicle_cost_logs:
            parsed = self._parse_datetime(row.get("cost_date"))
            if not parsed or parsed.year != int(year) or parsed.month != int(month):
                continue
            vid = str(row.get("vehicle_id", "")).strip()
            if target_id and vid != target_id:
                continue
            vehicle = vehicle_map.get(vid, {})
            rows.append({
                **deepcopy(row),
                "vehicle_name": vehicle.get("vehicle_name", vid),
                "vehicle_type": vehicle.get("vehicle_type", ""),
                "plate_number": vehicle.get("plate_number", ""),
            })
        rows.sort(key=lambda item: (item.get("cost_date", ""), item.get("vehicle_name", ""), item.get("cost_id", "")), reverse=True)
        return rows


    def latest_vehicle_odometer(self, vehicle_id: str) -> float:
        return self._vehicle_current_odometer(vehicle_id)

    def previous_vehicle_odometer_before(self, vehicle_id: str, target_date: str | None = None, exclude_log_id: str | None = None) -> float:
        vehicle = self.get_vehicle_by_id(vehicle_id) or {}
        baseline = float(vehicle.get("baseline_odometer", 0) or 0)
        target_vehicle_id = str(vehicle_id or "").strip()
        exclude_id = str(exclude_log_id or "").strip()
        target_key = self._vehicle_run_target_order_key(target_vehicle_id, target_date, exclude_id)
        candidates: list[tuple[tuple, dict]] = []
        for idx, row in enumerate(self._vehicle_run_logs):
            if not isinstance(row, dict):
                continue
            if str(row.get("vehicle_id", "") or "").strip() != target_vehicle_id:
                continue
            log_id = str(row.get("log_id", "") or "").strip()
            if exclude_id and log_id == exclude_id:
                continue
            row_key = self._vehicle_run_order_key(row, idx)
            if row_key >= target_key:
                continue
            candidates.append((row_key, row))
        candidates.sort(key=lambda item: item[0])
        if not candidates:
            return baseline
        try:
            return float(candidates[-1][1].get("end_odometer", baseline) or baseline)
        except (TypeError, ValueError):
            return baseline

    def next_vehicle_odometer_after(self, vehicle_id: str, target_date: str | None = None, exclude_log_id: str | None = None) -> float:
        target_vehicle_id = str(vehicle_id or "").strip()
        exclude_id = str(exclude_log_id or "").strip()
        target_key = self._vehicle_run_target_order_key(target_vehicle_id, target_date, exclude_id)
        candidates: list[tuple[tuple, dict]] = []
        for idx, row in enumerate(self._vehicle_run_logs):
            if not isinstance(row, dict):
                continue
            if str(row.get("vehicle_id", "") or "").strip() != target_vehicle_id:
                continue
            log_id = str(row.get("log_id", "") or "").strip()
            if exclude_id and log_id == exclude_id:
                continue
            row_key = self._vehicle_run_order_key(row, idx)
            if row_key <= target_key:
                continue
            candidates.append((row_key, row))
        candidates.sort(key=lambda item: item[0])
        if not candidates:
            return 0.0
        try:
            return float(candidates[0][1].get("end_odometer", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def save_vehicle_run_log(self, data: dict) -> dict:
        vehicle_id = str(data.get("vehicle_id", "") or "").strip()
        if not vehicle_id:
            raise ValueError("차량을 선택해 주세요.")
        if not self.get_vehicle_by_id(vehicle_id):
            raise ValueError("선택한 차량을 찾을 수 없습니다.")
        target_date = str(data.get("date", "") or "").strip()
        if not self._parse_date(target_date):
            raise ValueError("운행일을 확인해 주세요.")
        log_id = str(data.get("log_id", "") or "").strip() or self._next_vehicle_run_log_id()
        end_odometer = self._parse_non_negative_float(
            data.get("end_odometer", 0),
            "종료 계기판 km",
            max_value=MAX_VEHICLE_ODOMETER,
        )
        previous_odometer = self.previous_vehicle_odometer_before(vehicle_id, target_date, exclude_log_id=log_id)
        if end_odometer < previous_odometer:
            raise ValueError(f"종료 계기판 km는 이전 기록({int(previous_odometer):,} km)보다 작을 수 없습니다.")
        next_odometer = self.next_vehicle_odometer_after(vehicle_id, target_date, exclude_log_id=log_id)
        if next_odometer > 0 and end_odometer > next_odometer:
            raise ValueError(f"종료 계기판 km는 다음 기록({int(next_odometer):,} km)보다 클 수 없습니다.")
        payload = {
            "log_id": log_id,
            "date": target_date,
            "vehicle_id": vehicle_id,
            "driver_name": str(data.get("driver_name", "") or "").strip(),
            "end_odometer": end_odometer,
            "round_trips": self._parse_int_range(data.get("round_trips", 1), "왕복 횟수", 1, 5),
            "note": str(data.get("note", "") or "").strip(),
            "source": str(data.get("source", "PC") or "PC").strip() or "PC",
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._sync_vehicle_detail_log_save_remote("run", payload)
        updated = False
        for idx, row in enumerate(self._vehicle_run_logs):
            if str(row.get("log_id", "")).strip() == payload["log_id"]:
                self._vehicle_run_logs[idx] = payload
                updated = True
                break
        if not updated:
            self._vehicle_run_logs.append(payload)
        self.vehicles_changed.emit()
        return deepcopy(payload)

    def delete_vehicle_run_log(self, log_id: str):
        target = str(log_id or "").strip()
        if not target:
            return
        self._sync_vehicle_detail_log_delete_remote("run", target)
        self._vehicle_run_logs = [row for row in self._vehicle_run_logs if str(row.get("log_id", "")).strip() != target]
        self.vehicles_changed.emit()

    def save_vehicle_fuel_log(self, data: dict) -> dict:
        vehicle_id = str(data.get("vehicle_id", "") or "").strip()
        if not vehicle_id:
            raise ValueError("차량을 선택해 주세요.")
        if not self.get_vehicle_by_id(vehicle_id):
            raise ValueError("선택한 차량을 찾을 수 없습니다.")
        fuel_date = str(data.get("fuel_date", "") or "").strip()
        if not self._parse_datetime(fuel_date):
            raise ValueError("주유 날짜를 확인해 주세요.")
        payload = {
            "fuel_id": str(data.get("fuel_id", "") or "").strip() or self._next_vehicle_fuel_log_id(),
            "fuel_date": fuel_date,
            "vehicle_id": vehicle_id,
            "amount": self._parse_non_negative_float(
                data.get("amount", 0),
                "주유비",
                max_value=MAX_VEHICLE_FUEL_AMOUNT,
            ),
            "note": str(data.get("note", "") or "").strip(),
            "source": str(data.get("source", "PC") or "PC").strip() or "PC",
        }
        self._sync_vehicle_detail_log_save_remote("fuel", payload)
        updated = False
        for idx, row in enumerate(self._vehicle_fuel_logs):
            if str(row.get("fuel_id", "")).strip() == payload["fuel_id"]:
                self._vehicle_fuel_logs[idx] = payload
                updated = True
                break
        if not updated:
            self._vehicle_fuel_logs.append(payload)
        self.vehicles_changed.emit()
        return deepcopy(payload)

    def delete_vehicle_fuel_log(self, fuel_id: str):
        target = str(fuel_id or "").strip()
        if not target:
            return
        self._sync_vehicle_detail_log_delete_remote("fuel", target)
        self._vehicle_fuel_logs = [row for row in self._vehicle_fuel_logs if str(row.get("fuel_id", "")).strip() != target]
        self.vehicles_changed.emit()

    def save_vehicle_cost_log(self, data: dict) -> dict:
        vehicle_id = str(data.get("vehicle_id", "") or "").strip()
        if not vehicle_id:
            raise ValueError("차량을 선택해 주세요.")
        if not self.get_vehicle_by_id(vehicle_id):
            raise ValueError("선택한 차량을 찾을 수 없습니다.")
        cost_date = str(data.get("cost_date", "") or "").strip()
        if not self._parse_datetime(cost_date):
            raise ValueError("비용 날짜를 확인해 주세요.")
        category = str(data.get("category", "") or "").strip() or "기타"
        payload = {
            "cost_id": str(data.get("cost_id", "") or "").strip() or self._next_vehicle_cost_log_id(),
            "cost_date": cost_date,
            "vehicle_id": vehicle_id,
            "category": category,
            "amount": self._parse_non_negative_float(
                data.get("amount", 0),
                "기타비용",
                max_value=MAX_VEHICLE_COST_AMOUNT,
            ),
            "description": str(data.get("description", "") or "").strip(),
            "note": str(data.get("note", "") or "").strip(),
            "source": str(data.get("source", "PC수동") or "PC수동").strip() or "PC수동",
        }
        self._sync_vehicle_detail_log_save_remote("cost", payload)
        updated = False
        for idx, row in enumerate(self._vehicle_cost_logs):
            if str(row.get("cost_id", "")).strip() == payload["cost_id"]:
                self._vehicle_cost_logs[idx] = payload
                updated = True
                break
        if not updated:
            self._vehicle_cost_logs.append(payload)
        self.vehicles_changed.emit()
        return deepcopy(payload)

    def delete_vehicle_cost_log(self, cost_id: str):
        target = str(cost_id or "").strip()
        if not target:
            return
        self._sync_vehicle_detail_log_delete_remote("cost", target)
        self._vehicle_cost_logs = [row for row in self._vehicle_cost_logs if str(row.get("cost_id", "")).strip() != target]
        self.vehicles_changed.emit()
