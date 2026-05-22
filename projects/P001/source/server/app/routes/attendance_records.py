from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from ..db import SessionLocal, engine

from ..permission_guard import (
    attendance_record_allowed,
    ensure_attendance_record_allowed,
    require_permission_context,
)

router = APIRouter(prefix="/api/attendance", tags=["attendance-records"])


def _permission_context_from_request(request: Request):
    with SessionLocal() as db:
        return require_permission_context(
            db,
            authorization=request.headers.get("authorization"),
            x_auth_token=request.headers.get("x-auth-token"),
            x_pc_sync_key=request.headers.get("x-pc-sync-key"),
        )



def _text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return data.get(key)
    return ""


def _deep_first(data: dict[str, Any], *keys: str) -> Any:
    value = _first(data, *keys)
    if value not in (None, ""):
        return value

    # 모바일에서 employee/worker/person/staff 내부 객체로 보내는 경우도 허용한다.
    for parent_key in ("employee", "worker", "person", "staff"):
        parent = data.get(parent_key)
        if isinstance(parent, dict):
            value = _first(parent, *keys)
            if value not in (None, ""):
                return value
    return ""


def _normalize_state(value: Any) -> str:
    raw = _text_value(value)
    key = raw.lower().replace(" ", "").replace("-", "_")
    mapping = {
        "present": "present",
        "attendance": "present",
        "attend": "present",
        "checkin": "present",
        "출석": "present",
        "정상": "present",

        "absent": "absent",
        "absence": "absent",
        "결근": "absent",

        "hospital": "hospital",
        "hospitalized": "hospital",
        "병원": "hospital",

        "late": "late",
        "지각": "late",

        "early": "early",
        "early_leave": "early",
        "leaveearly": "early",
        "조퇴": "early",

        "off": "off",
        "holiday": "off",
        "dayoff": "off",
        "휴무": "off",

        "unauthorized_absent": "unauthorized_absent",
        "unauthorizedabsence": "unauthorized_absent",
        "무단결근": "unauthorized_absent",

        "unauthorized_leave": "unauthorized_leave",
        "unauthorizedleave": "unauthorized_leave",
        "무단이탈": "unauthorized_leave",

        "clear": "",
        "delete": "",
        "remove": "",
        "none": "",
        "empty": "",
        "해제": "",
        "": "",
    }
    return mapping.get(key, raw)


def _display_state(value: str) -> str:
    mapping = {
        "present": "출석",
        "absent": "결근",
        "hospital": "병원",
        "late": "지각",
        "early": "조퇴",
        "off": "휴무",
        "unauthorized_absent": "무단결근",
        "unauthorized_leave": "무단이탈",
        "": "",
    }
    return mapping.get(value, value)


def _normalize_date(raw: Any) -> str:
    value = _text_value(raw)
    if not value:
        return ""
    if "T" in value:
        value = value.split("T", 1)[0]
    if " " in value:
        value = value.split(" ", 1)[0]
    value = value.replace(".", "-").replace("/", "-")
    parts = value.split("-")
    if len(parts) >= 3:
        y, m, d = parts[0], parts[1], parts[2]
        if len(m) == 1:
            m = "0" + m
        if len(d) == 1:
            d = "0" + d
        return f"{y}-{m}-{d}"
    return value


def _extract_record(data: dict[str, Any]) -> dict[str, str]:
    attendance_date = _normalize_date(_deep_first(
        data,
        "attendance_date", "date", "work_date", "target_date", "day", "selected_date"
    ))

    year_month = _text_value(_first(data, "year_month", "month", "target_month"))
    if not year_month and attendance_date and len(attendance_date) >= 7:
        year_month = attendance_date[:7]

    worker_id = _text_value(_deep_first(
        data,
        "worker_id", "workerId", "employee_id", "employeeId", "employee_no",
        "employeeNo", "staff_id", "staffId", "id", "code", "display_id"
    ))
    worker_name = _text_value(_deep_first(
        data,
        "worker_name", "workerName", "employee_name", "employeeName",
        "staff_name", "staffName", "name", "real_name"
    ))

    business = _text_value(_deep_first(
        data,
        "business", "business_name", "businessName", "affiliated_business",
        "affiliatedBusiness", "company", "company_name", "companyName"
    ))
    site = _text_value(_deep_first(
        data,
        "site", "site_name", "siteName", "work_site", "workSite",
        "workplace", "work_place", "factory", "factory_name"
    ))
    work_type = _text_value(_deep_first(
        data,
        "work_type", "workType", "shift_type", "shiftType",
        "work_shift", "workShift", "working_type"
    ))

    state = _normalize_state(_first(data, "state", "status", "attendance_state", "attendanceStatus", "value"))
    source = _text_value(_first(data, "source", "client", "from")) or "mobile"
    updated_by = _text_value(_first(data, "updated_by", "updatedBy", "user", "username", "admin_name")) or source
    note = _text_value(_first(data, "note", "memo", "remark"))

    missing = []
    if not worker_id:
        missing.append("worker_id/employee_id/id")
    if not worker_name:
        missing.append("worker_name/name")
    if not attendance_date:
        missing.append("date/attendance_date")
    if not year_month:
        missing.append("year_month")
    # state는 해제 처리 때문에 빈 값도 허용한다. 단, key 자체가 없으면 안내한다.
    if not any(k in data for k in ("state", "status", "attendance_state", "attendanceStatus", "value")):
        missing.append("state/status")

    if missing:
        raise HTTPException(status_code=400, detail={
            "status": "error",
            "message": "근태 저장값에 필요한 항목이 부족합니다.",
            "missing": missing,
            "received_keys": sorted(list(data.keys())),
        })

    return {
        "worker_id": worker_id,
        "worker_name": worker_name,
        "business": business,
        "site": site,
        "work_type": work_type,
        "date": attendance_date,
        "attendance_date": attendance_date,
        "year_month": year_month,
        "state": state,
        "source": source,
        "updated_by": updated_by,
        "note": note,
    }


_SCHEMA_READY = False


def _ensure_attendance_schema() -> None:
    """attendance_records 실제 테이블과 서버 코드 컬럼을 자동으로 맞춘다."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    create_sql = """
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            worker_id VARCHAR(100) NOT NULL DEFAULT '',
            worker_name VARCHAR(100) NOT NULL DEFAULT '',
            business VARCHAR(150) NOT NULL DEFAULT '',
            site VARCHAR(150) NOT NULL DEFAULT '',
            work_type VARCHAR(100) NOT NULL DEFAULT '',
            `date` VARCHAR(20) NOT NULL DEFAULT '',
            attendance_date VARCHAR(20) NOT NULL DEFAULT '',
            `year_month` VARCHAR(7) NOT NULL DEFAULT '',
            state VARCHAR(50) NOT NULL DEFAULT '',
            source VARCHAR(50) NOT NULL DEFAULT '',
            updated_by VARCHAR(100) NOT NULL DEFAULT '',
            note TEXT NULL,
            created_at DATETIME NULL,
            updated_at DATETIME NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """

    required_columns = [
        ("worker_id", "worker_id VARCHAR(100) NOT NULL DEFAULT ''"),
        ("worker_name", "worker_name VARCHAR(100) NOT NULL DEFAULT ''"),
        ("business", "business VARCHAR(150) NOT NULL DEFAULT ''"),
        ("site", "site VARCHAR(150) NOT NULL DEFAULT ''"),
        ("work_type", "work_type VARCHAR(100) NOT NULL DEFAULT ''"),
        ("date", "`date` VARCHAR(20) NOT NULL DEFAULT ''"),
        ("attendance_date", "attendance_date VARCHAR(20) NOT NULL DEFAULT ''"),
        ("year_month", "`year_month` VARCHAR(7) NOT NULL DEFAULT ''"),
        ("state", "state VARCHAR(50) NOT NULL DEFAULT ''"),
        ("source", "source VARCHAR(50) NOT NULL DEFAULT ''"),
        ("updated_by", "updated_by VARCHAR(100) NOT NULL DEFAULT ''"),
        ("note", "note TEXT NULL"),
        ("created_at", "created_at DATETIME NULL"),
        ("updated_at", "updated_at DATETIME NULL"),
    ]

    with engine.begin() as conn:
        conn.execute(text(create_sql))
        rows = conn.execute(text("SHOW COLUMNS FROM attendance_records")).mappings().all()
        existing = {str(row.get("Field", "")) for row in rows}

        for column_name, column_sql in required_columns:
            if column_name not in existing:
                conn.execute(text(f"ALTER TABLE attendance_records ADD COLUMN {column_sql}"))

        # 기존 데이터 보정: 날짜 컬럼이 둘 중 하나만 있는 경우 서로 채운다.
        conn.execute(text("""
            UPDATE attendance_records
            SET `date` = attendance_date
            WHERE (`date` IS NULL OR `date` = '')
              AND attendance_date IS NOT NULL
              AND attendance_date <> ''
        """))
        conn.execute(text("""
            UPDATE attendance_records
            SET attendance_date = `date`
            WHERE (attendance_date IS NULL OR attendance_date = '')
              AND `date` IS NOT NULL
              AND `date` <> ''
        """))
        conn.execute(text("""
            UPDATE attendance_records
            SET `year_month` = LEFT(COALESCE(NULLIF(attendance_date, ''), NULLIF(`date`, '')), 7)
            WHERE (`year_month` IS NULL OR `year_month` = '')
              AND COALESCE(NULLIF(attendance_date, ''), NULLIF(`date`, '')) IS NOT NULL
        """))

    _SCHEMA_READY = True


def _lock_status(year_month: str) -> dict[str, Any]:
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT `year_month`, locked
                FROM attendance_month_locks
                WHERE `year_month` = :year_month
                LIMIT 1
            """), {"year_month": year_month}).mappings().first()
    except Exception:
        row = None

    locked = False
    if row:
        value = row.get("locked")
        locked = value in (1, True, "1", "true", "TRUE", "True")

    return {
        "year_month": year_month,
        "locked": locked,
        "editable": not locked,
        "message": "이 월은 PC에서 마감되어 수정할 수 없습니다." if locked else "수정 가능",
    }


def _record_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    state = _text_value(data.get("state"))
    data["state_label"] = _display_state(state)
    if not data.get("attendance_date"):
        data["attendance_date"] = data.get("date", "")
    return data


def _db_error(message: str, exc: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail={
        "status": "error",
        "message": message,
        "error": str(exc),
    })


@router.get("/month")
def get_month_attendance(year_month: str, request: Request) -> dict[str, Any]:
    context = _permission_context_from_request(request)
    try:
        _ensure_attendance_schema()
    except Exception as exc:
        raise _db_error("근태 테이블 자동 보정 중 서버 오류가 발생했습니다.", exc)

    lock = _lock_status(year_month)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT
                    id,
                    worker_id,
                    worker_name,
                    business,
                    site,
                    work_type,
                    `date`,
                    attendance_date,
                    `year_month`,
                    state,
                    source,
                    updated_by,
                    note,
                    created_at,
                    updated_at
                FROM attendance_records
                WHERE `year_month` = :year_month
                ORDER BY `date`, worker_name, id
            """), {"year_month": year_month}).mappings().all()
    except Exception as exc:
        raise _db_error("근태 월간 조회 중 서버 오류가 발생했습니다.", exc)

    records = [
        _record_to_dict(r)
        for r in rows
        if attendance_record_allowed(context, _record_to_dict(r))
    ]
    return {
        "status": "ok",
        "year_month": year_month,
        "lock": lock,
        "records": records,
        "count": len(records),
    }


@router.get("/day")
def get_day_attendance(date: str, request: Request) -> dict[str, Any]:
    context = _permission_context_from_request(request)
    try:
        _ensure_attendance_schema()
    except Exception as exc:
        raise _db_error("근태 테이블 자동 보정 중 서버 오류가 발생했습니다.", exc)

    attendance_date = _normalize_date(date)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT
                    id,
                    worker_id,
                    worker_name,
                    business,
                    site,
                    work_type,
                    `date`,
                    attendance_date,
                    `year_month`,
                    state,
                    source,
                    updated_by,
                    note,
                    created_at,
                    updated_at
                FROM attendance_records
                WHERE `date` = :date OR attendance_date = :date
                ORDER BY worker_name, id
            """), {"date": attendance_date}).mappings().all()
    except Exception as exc:
        raise _db_error("근태 일자 조회 중 서버 오류가 발생했습니다.", exc)

    records = [
        _record_to_dict(r)
        for r in rows
        if attendance_record_allowed(context, _record_to_dict(r))
    ]
    return {
        "status": "ok",
        "date": attendance_date,
        "records": records,
        "count": len(records),
    }


@router.post("/save")
async def save_attendance(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail={
            "status": "error",
            "message": "JSON 형식으로 전송해야 합니다.",
        })

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail={
            "status": "error",
            "message": "근태 저장값은 객체 형식이어야 합니다.",
        })

    context = _permission_context_from_request(request)
    record = _extract_record(payload)
    ensure_attendance_record_allowed(context, record)
    try:
        _ensure_attendance_schema()
    except Exception as exc:
        raise _db_error("근태 테이블 자동 보정 중 서버 오류가 발생했습니다.", exc)

    lock = _lock_status(record["year_month"])
    if lock["locked"]:
        raise HTTPException(status_code=423, detail={
            "status": "locked",
            "message": lock["message"],
            "year_month": record["year_month"],
        })

    try:
        with engine.begin() as conn:
            # 같은 근로자/날짜 기록은 먼저 정리한 뒤 한 건만 남긴다.
            # state가 빈 값인 해제 요청도 삭제로 끝내지 않고 빈 상태 기록으로 남긴다.
            # 그래야 PC가 서버 월간 근태를 가져올 때 "해제된 칸"을 삭제 신호로 받을 수 있다.
            conn.execute(text("""
                DELETE FROM attendance_records
                WHERE worker_id = :worker_id
                  AND (`date` = :date OR attendance_date = :attendance_date)
            """), record)

            conn.execute(text("""
                INSERT INTO attendance_records (
                    worker_id,
                    worker_name,
                    business,
                    site,
                    work_type,
                    `date`,
                    attendance_date,
                    `year_month`,
                    state,
                    source,
                    updated_by,
                    note
                ) VALUES (
                    :worker_id,
                    :worker_name,
                    :business,
                    :site,
                    :work_type,
                    :date,
                    :attendance_date,
                    :year_month,
                    :state,
                    :source,
                    :updated_by,
                    :note
                )
            """), record)
    except Exception as exc:
        raise _db_error("근태 저장 중 서버 오류가 발생했습니다.", exc)

    action = "cleared" if record["state"] == "" else "saved"
    return {
        "status": "ok",
        "action": action,
        "message": "근태가 해제되었습니다." if action == "cleared" else "근태가 저장되었습니다.",
        "record": {
            **record,
            "state_label": _display_state(record["state"]),
        },
    }


@router.post("/bulk-save")
async def bulk_save_attendance(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail={
            "status": "error",
            "message": "JSON 형식으로 전송해야 합니다.",
        })

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("records") or payload.get("items") or payload.get("data") or []
    else:
        items = []

    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail={
            "status": "error",
            "message": "records/items/data는 목록이어야 합니다.",
        })

    context = _permission_context_from_request(request)

    try:
        _ensure_attendance_schema()
    except Exception as exc:
        raise _db_error("근태 테이블 자동 보정 중 서버 오류가 발생했습니다.", exc)

    saved = []
    failures = []

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            failures.append({"index": index, "message": "객체 형식이 아닙니다."})
            continue
        try:
            record = _extract_record(item)
            ensure_attendance_record_allowed(context, record)
            lock = _lock_status(record["year_month"])
            if lock["locked"]:
                failures.append({
                    "index": index,
                    "year_month": record["year_month"],
                    "message": lock["message"],
                })
                continue

            with engine.begin() as conn:
                # bulk 저장에서도 빈 상태 기록을 남겨 PC 삭제 동기화 신호로 사용한다.
                conn.execute(text("""
                    DELETE FROM attendance_records
                    WHERE worker_id = :worker_id
                      AND (`date` = :date OR attendance_date = :attendance_date)
                """), record)
                conn.execute(text("""
                    INSERT INTO attendance_records (
                        worker_id, worker_name, business, site, work_type,
                        `date`, attendance_date, `year_month`, state, source, updated_by, note
                    ) VALUES (
                        :worker_id, :worker_name, :business, :site, :work_type,
                        :date, :attendance_date, :year_month, :state, :source, :updated_by, :note
                    )
                """), record)
            saved.append(record)
        except HTTPException as exc:
            failures.append({"index": index, "detail": exc.detail})
        except Exception as exc:
            failures.append({"index": index, "message": str(exc)})

    return {
        "status": "ok" if not failures else "partial",
        "saved_count": len(saved),
        "failed_count": len(failures),
        "failures": failures,
    }
