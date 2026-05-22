from __future__ import annotations

from datetime import datetime
import json
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AppSnapshot, Employee, EmployeeDeletedMarker
from ..permission_guard import ensure_pc_or_super, ensure_site_allowed, filter_employees_for_context, require_permission_context
from ..schemas import AppSnapshotIn, AppSnapshotOut, EmployeeCreate, EmployeeOut, EmployeeUpdate

router = APIRouter(prefix="/api/employees", tags=["employees"])


def _normalize_duplicate_name(value: str | None) -> str:
    """이름 중복 비교용 정규화: 앞뒤 공백 제거, 내부 공백 제거, 대소문자 통일."""
    return re.sub(r"\s+", "", str(value or "").strip()).casefold()


def _normalize_duplicate_phone(value: str | None) -> str:
    """연락처 중복 비교용 정규화: 숫자만 남겨 하이픈/공백 차이를 무시."""
    return re.sub(r"\D+", "", str(value or ""))


def _find_same_name_phone_employee(db: Session, name: str, phone: str, exclude_id: int | None = None) -> Employee | None:
    target_name = _normalize_duplicate_name(name)
    target_phone = _normalize_duplicate_phone(phone)
    if not target_name or not target_phone:
        return None

    rows = db.execute(select(Employee.id, Employee.name, Employee.phone)).all()
    for employee_id, employee_name, employee_phone in rows:
        if exclude_id is not None and employee_id == exclude_id:
            continue
        if (
            _normalize_duplicate_name(employee_name) == target_name
            and _normalize_duplicate_phone(employee_phone) == target_phone
        ):
            return db.get(Employee, employee_id)
    return None


def _duplicate_employee_response(row: Employee) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "ok": False,
            "error": "duplicate_employee",
            "message": "이름과 연락처가 같은 근로자가 이미 등록되어 있어 등록할 수 없습니다.",
            "employee_id": row.id,
            "name": row.name,
            "phone": row.phone,
        },
    )

def _decode_workforce_value(value):
    if isinstance(value, list):
        return [_decode_workforce_value(item) for item in value]
    if isinstance(value, dict):
        if set(value.keys()) == {"__workforce_tuple__"}:
            return [_decode_workforce_value(item) for item in value.get("__workforce_tuple__", [])]
        if set(value.keys()) == {"__workforce_dict_items__"}:
            decoded = {}
            for item in value.get("__workforce_dict_items__", []):
                if isinstance(item, list) and len(item) == 2:
                    decoded[str(_decode_workforce_value(item[0]))] = _decode_workforce_value(item[1])
            return decoded
        return {str(key): _decode_workforce_value(item) for key, item in value.items()}
    return value


def _encode_workforce_value(value):
    if isinstance(value, tuple):
        return {"__workforce_tuple__": [_encode_workforce_value(item) for item in value]}
    if isinstance(value, list):
        return [_encode_workforce_value(item) for item in value]
    if isinstance(value, dict):
        return {
            "__workforce_dict_items__": [
                [_encode_workforce_value(key), _encode_workforce_value(item)]
                for key, item in value.items()
            ]
        }
    return value


def _safe_employee_id(value, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _snapshot_employee_id(row: dict, fallback: int = 0) -> int:
    if not isinstance(row, dict):
        return 0
    return _safe_employee_id(
        row.get("id") or row.get("employee_id") or row.get("worker_id") or row.get("employeeNumber"),
        fallback,
    )


def _snapshot_deleted_ids(root: dict | None) -> set[int]:
    if not isinstance(root, dict):
        return set()
    values = []
    for key in ("deleted_employee_ids", "employee_deleted_ids", "deleted_employees"):
        raw = root.get(key)
        if isinstance(raw, list):
            values.extend(raw)
    result: set[int] = set()
    for value in values:
        employee_id = _safe_employee_id(value, 0)
        if employee_id > 0:
            result.add(employee_id)
    return result


def _deleted_employee_ids(db: Session) -> set[int]:
    ids: set[int] = set()
    try:
        rows = db.execute(select(EmployeeDeletedMarker.employee_id)).all()
        for (employee_id,) in rows:
            employee_id = _safe_employee_id(employee_id, 0)
            if employee_id > 0:
                ids.add(employee_id)
    except Exception:
        pass
    ids.update(_snapshot_deleted_ids(_snapshot_root(db)))
    return ids


def _filter_deleted_employees_from_snapshot_payload(db: Session, payload: dict | None) -> dict:
    next_payload = dict(payload or {})
    deleted_ids = _deleted_employee_ids(db)
    if not deleted_ids:
        return next_payload
    root = _decode_workforce_value(next_payload.get("snapshot"))
    if not isinstance(root, dict):
        return next_payload
    rows = root.get("employees")
    if isinstance(rows, list):
        filtered_rows = []
        for index, row in enumerate(rows, start=1):
            employee_id = _snapshot_employee_id(row, index) if isinstance(row, dict) else 0
            if employee_id > 0 and employee_id in deleted_ids:
                continue
            filtered_rows.append(row)
        root["employees"] = filtered_rows
    existing_deleted = _snapshot_deleted_ids(root)
    root["deleted_employee_ids"] = sorted(existing_deleted | deleted_ids)
    next_payload["snapshot"] = _encode_workforce_value(root)
    return next_payload


def _mark_employee_deleted(db: Session, employee_id: int, *, source: str = "pc", updated_by: str = "") -> None:
    employee_id = _safe_employee_id(employee_id, 0)
    if employee_id <= 0:
        return
    row = db.get(EmployeeDeletedMarker, employee_id)
    now = datetime.utcnow()
    if row is None:
        row = EmployeeDeletedMarker(employee_id=employee_id, source=source, updated_by=updated_by, deleted_at=now)
        db.add(row)
    else:
        row.source = source or row.source or "pc"
        row.updated_by = updated_by or row.updated_by or ""
        row.deleted_at = now


def _remove_employee_from_snapshot(db: Session, employee_id: int) -> bool:
    employee_id = _safe_employee_id(employee_id, 0)
    if employee_id <= 0:
        return False
    row = db.get(AppSnapshot, "main")
    if row is None:
        payload = {"snapshot": _encode_workforce_value({"employees": [], "deleted_employee_ids": [employee_id]})}
        row = AppSnapshot(snapshot_key="main", payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")), updated_at=datetime.utcnow())
        db.add(row)
        return True
    try:
        payload = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    root = _decode_workforce_value(payload.get("snapshot"))
    if not isinstance(root, dict):
        root = {}
    changed = False
    rows = root.get("employees")
    if isinstance(rows, list):
        next_rows = []
        for index, item in enumerate(rows, start=1):
            item_id = _snapshot_employee_id(item, index) if isinstance(item, dict) else 0
            if item_id == employee_id:
                changed = True
                continue
            next_rows.append(item)
        root["employees"] = next_rows
    deleted_ids = _snapshot_deleted_ids(root)
    if employee_id not in deleted_ids:
        deleted_ids.add(employee_id)
        changed = True
    root["deleted_employee_ids"] = sorted(deleted_ids)
    payload["snapshot"] = _encode_workforce_value(root)
    row.payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    row.updated_at = datetime.utcnow()
    return changed


def _text_value(value, *keys: str) -> str:
    if value is None:
        return ""
    if keys and isinstance(value, dict):
        for key in keys:
            if key in value:
                text = _text_value(value.get(key))
                if text:
                    return text
        raw = value.get("raw")
        if isinstance(raw, dict):
            for key in keys:
                if key in raw:
                    text = _text_value(raw.get(key))
                    if text:
                        return text
    if isinstance(value, dict):
        for key in (
            "name", "employee_name", "worker_name", "korean_name",
            "work_site", "site", "site_name", "work_site_name",
            "business", "business_name", "affiliated_business",
            "phone", "nation", "nationality", "status",
        ):
            text = _text_value(value.get(key))
            if text:
                return text
        return ""
    if isinstance(value, (list, tuple, set)):
        for item in value:
            text = _text_value(item)
            if text:
                return text
        return ""
    return str(value or "").strip()


def _employee_to_dict(row: Employee) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "nation": row.nation,
        "affiliated_business": row.affiliated_business,
        "work_site": row.work_site,
        "work_type": row.work_type,
        "pay_type": row.pay_type,
        "status": row.status,
        "phone": row.phone,
        "hire_date": row.hire_date,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def _snapshot_root(db: Session) -> dict:
    row = db.get(AppSnapshot, "main")
    if not row:
        return {}
    try:
        payload = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        return {}
    root = payload.get("snapshot") if isinstance(payload, dict) else {}
    decoded = _decode_workforce_value(root)
    return decoded if isinstance(decoded, dict) else {}


def _snapshot_employee_rows(db: Session) -> list[dict]:
    root = _snapshot_root(db)
    rows = root.get("employees")
    if not isinstance(rows, list):
        return []
    deleted_ids = _deleted_employee_ids(db)
    result: list[dict] = []
    now_text = datetime.utcnow().isoformat()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        status = _text_value(row, "status", "employee_status", "state") or "근무중"
        if status == "퇴사" or row.get("active") is False or row.get("is_deleted") is True:
            continue
        name = _text_value(row, "name", "employee_name", "worker_name", "korean_name", "full_name")
        if not name:
            continue
        employee_id = _snapshot_employee_id(row, index)
        if employee_id in deleted_ids:
            continue
        result.append({
            "id": employee_id,
            "name": name,
            "nation": _text_value(row, "nation", "nationality", "country"),
            "affiliated_business": _text_value(row, "affiliated_business", "business", "business_name", "company", "company_name"),
            "work_site": _text_value(row, "work_site", "site", "site_name", "work_site_name", "worksite", "factory"),
            "work_type": _text_value(row, "work_type", "type", "workType", "shift", "work_shift", "work_time"),
            "pay_type": _text_value(row, "pay_type", "payType", "salary_type"),
            "status": status,
            "phone": _text_value(row, "phone", "contact", "mobile", "tel"),
            "hire_date": _text_value(row, "hire_date", "join_date", "start_date"),
            "note": _text_value(row, "note", "memo"),
            "created_at": now_text,
            "updated_at": now_text,
            "raw": row,
        })
    return result


def _dedupe_employee_rows(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for row in rows:
        key = str(row.get("id") or "").strip()
        if not key:
            key = f"{_normalize_duplicate_name(row.get('name'))}|{_normalize_duplicate_phone(row.get('phone'))}"
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(row)
    return result



@router.get("")
def list_employees(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
):
    context = require_permission_context(
        db,
        authorization=authorization,
        x_auth_token=x_auth_token,
        x_pc_sync_key=x_pc_sync_key,
    )
    deleted_ids = _deleted_employee_ids(db)
    api_rows = db.execute(select(Employee).order_by(Employee.id.desc())).scalars().all()
    rows = [_employee_to_dict(row) for row in api_rows if _safe_employee_id(row.id, 0) not in deleted_ids]
    rows.extend(_snapshot_employee_rows(db))
    rows = _dedupe_employee_rows(rows)
    return filter_employees_for_context(context, rows)


@router.get("/snapshot", response_model=AppSnapshotOut)
def get_app_snapshot(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
):
    context = require_permission_context(
        db,
        authorization=authorization,
        x_auth_token=x_auth_token,
        x_pc_sync_key=x_pc_sync_key,
    )
    # snapshot은 급여/근태/차량/관리자 계정까지 포함될 수 있는 전체 백업 데이터입니다.
    # 일반관리자 모바일 토큰으로는 전체 snapshot을 직접 내려주지 않고,
    # PC 동기화 키 또는 최고관리자 토큰일 때만 허용합니다.
    ensure_pc_or_super(context)

    row = db.get(AppSnapshot, "main")
    if not row:
        return {"snapshot_key": "main", "payload": {}, "updated_at": None}
    try:
        payload = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {"snapshot_key": row.snapshot_key, "payload": payload, "updated_at": row.updated_at}


@router.put("/snapshot", response_model=AppSnapshotOut)
def save_app_snapshot(
    payload: AppSnapshotIn,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
):
    context = require_permission_context(
        db,
        authorization=authorization,
        x_auth_token=x_auth_token,
        x_pc_sync_key=x_pc_sync_key,
    )
    ensure_pc_or_super(context)
    now = datetime.utcnow()
    filtered_payload = _filter_deleted_employees_from_snapshot_payload(db, payload.payload or {})
    payload_json = json.dumps(filtered_payload, ensure_ascii=False, separators=(",", ":"))
    row = db.get(AppSnapshot, "main")
    if row is None:
        row = AppSnapshot(snapshot_key="main", payload_json=payload_json, updated_at=now)
        db.add(row)
    else:
        row.payload_json = payload_json
        row.updated_at = now
    db.commit()
    db.refresh(row)
    # PC 전체 snapshot은 급여/차량/근태 전체 JSON이라 응답까지 그대로 돌려주면
    # PC가 업로드 후 큰 응답을 기다리다 timeout으로 완료 문구를 못 볼 수 있습니다.
    # 저장 성공 여부에는 updated_at만 필요하므로 PUT 응답은 가볍게 유지합니다.
    return {"snapshot_key": row.snapshot_key, "payload": {}, "updated_at": row.updated_at}


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
):
    context = require_permission_context(
        db,
        authorization=authorization,
        x_auth_token=x_auth_token,
        x_pc_sync_key=x_pc_sync_key,
    )
    row = db.get(Employee, employee_id)
    if not row:
        raise HTTPException(status_code=404, detail="employee not found")
    if row not in filter_employees_for_context(context, [row]):
        raise HTTPException(status_code=403, detail="담당 근로자 범위가 아닙니다.")
    return row


@router.post("", response_model=EmployeeOut)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
):
    context = require_permission_context(
        db,
        authorization=authorization,
        x_auth_token=x_auth_token,
        x_pc_sync_key=x_pc_sync_key,
    )
    ensure_site_allowed(
        context,
        business=payload.affiliated_business,
        site=payload.work_site,
    )
    requested_id = int(payload.id or 0) if payload.id is not None else 0
    if requested_id > 0 and db.get(EmployeeDeletedMarker, requested_id):
        raise HTTPException(status_code=410, detail="employee id was deleted")
    if requested_id > 0 and db.get(Employee, requested_id):
        raise HTTPException(status_code=409, detail="employee id already exists")

    duplicate_row = _find_same_name_phone_employee(db, payload.name, payload.phone)
    if duplicate_row is not None:
        return _duplicate_employee_response(duplicate_row)

    row_kwargs = {
        "name": payload.name,
        "nation": payload.nation,
        "affiliated_business": payload.affiliated_business,
        "work_site": payload.work_site,
        "work_type": payload.work_type,
        "pay_type": payload.pay_type,
        "status": payload.status,
        "phone": payload.phone,
        "hire_date": payload.hire_date,
        "note": payload.note,
    }
    now = datetime.utcnow()
    if hasattr(Employee, "created_at"):
        row_kwargs["created_at"] = now
    if hasattr(Employee, "updated_at"):
        row_kwargs["updated_at"] = now
    if requested_id > 0:
        row_kwargs["id"] = requested_id

    row = Employee(**row_kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
):
    context = require_permission_context(
        db,
        authorization=authorization,
        x_auth_token=x_auth_token,
        x_pc_sync_key=x_pc_sync_key,
    )
    ensure_pc_or_super(context)
    if db.get(EmployeeDeletedMarker, employee_id):
        raise HTTPException(status_code=410, detail="employee id was deleted")
    row = db.get(Employee, employee_id)
    if not row:
        raise HTTPException(status_code=404, detail="employee not found")

    update_data = payload.model_dump(exclude_unset=True)
    update_data.pop("id", None)

    next_name = update_data.get("name", row.name)
    next_phone = update_data.get("phone", row.phone)
    duplicate_row = _find_same_name_phone_employee(db, next_name, next_phone, exclude_id=row.id)
    if duplicate_row is not None:
        return _duplicate_employee_response(duplicate_row)

    for key, value in update_data.items():
        setattr(row, key, value)
    if hasattr(row, "updated_at"):
        row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{employee_id}")
def delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
):
    context = require_permission_context(
        db,
        authorization=authorization,
        x_auth_token=x_auth_token,
        x_pc_sync_key=x_pc_sync_key,
    )
    ensure_pc_or_super(context)
    row = db.get(Employee, employee_id)
    if row is not None:
        db.delete(row)
    _mark_employee_deleted(db, employee_id, source="pc", updated_by="pc")
    _remove_employee_from_snapshot(db, employee_id)
    db.commit()
    return {"ok": True, "id": employee_id, "deleted": True, "tombstone": True, "already_missing": row is None}
