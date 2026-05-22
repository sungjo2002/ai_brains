from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AppSnapshot, VehicleCostLog, VehicleDeletedLog, VehicleFuelLog, VehicleRunLog
from ..permission_guard import (
    ensure_pc_or_super,
    ensure_vehicle_allowed,
    filter_vehicle_logs_for_context,
    filter_vehicles_for_context,
    require_permission_context,
)

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])

SERVER_TUPLE_MARKER = "__workforce_tuple__"
SERVER_DICT_ITEMS_MARKER = "__workforce_dict_items__"


def _decode_workforce_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode_workforce_value(item) for item in value]
    if isinstance(value, dict):
        if set(value.keys()) == {SERVER_TUPLE_MARKER}:
            return tuple(_decode_workforce_value(item) for item in value.get(SERVER_TUPLE_MARKER, []))
        if set(value.keys()) == {SERVER_DICT_ITEMS_MARKER}:
            decoded: dict[Any, Any] = {}
            for item in value.get(SERVER_DICT_ITEMS_MARKER, []):
                if not isinstance(item, list) or len(item) != 2:
                    continue
                decoded[_decode_workforce_value(item[0])] = _decode_workforce_value(item[1])
            return decoded
        return {str(key): _decode_workforce_value(item) for key, item in value.items()}
    return value


def _load_snapshot(db: Session) -> tuple[dict[str, Any], datetime | None]:
    row = db.get(AppSnapshot, "main")
    if not row:
        return {}, None
    try:
        payload = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    encoded_snapshot = payload.get("snapshot") if isinstance(payload, dict) else {}
    decoded = _decode_workforce_value(encoded_snapshot)
    if not isinstance(decoded, dict):
        decoded = {}
    return decoded, row.updated_at


def _safe_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value: Any, *, prefer: str | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    if isinstance(value, dict):
        prefer_keys = []
        if prefer == "business":
            prefer_keys = ["business", "business_name", "company", "company_name", "name"]
        elif prefer == "site":
            prefer_keys = ["work_site", "site", "site_name", "work_site_name", "name"]
        elif prefer == "vehicle":
            prefer_keys = ["car", "vehicle_no", "plate_number", "vehicleNumber", "vehicle_id", "vehicle_name", "name"]
        keys = prefer_keys + [
            "name", "work_site", "site", "site_name", "work_site_name",
            "business", "business_name", "company", "company_name",
            "car", "vehicle_no", "plate_number", "vehicleNumber",
            "vehicle_id", "vehicle_name", "main_driver", "driver_name",
            "manager_name",
        ]
        for key in keys:
            text = _text(value.get(key), prefer=prefer)
            if text:
                return text
        return ""
    if isinstance(value, (list, tuple, set)):
        for item in value:
            text = _text(item, prefer=prefer)
            if text:
                return text
        return ""
    return str(value or "").strip()


def _float(value: Any, default: float = 0) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return default


def _int_range(value: Any, default: int = 1, minimum: int = 1, maximum: int = 5) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _date_text(value: Any) -> str:
    text = _text(value)
    if text:
        return text[:10]
    return date.today().isoformat()


def _vehicle_label(row: dict[str, Any]) -> str:
    for key in ("plate_number", "vehicle_no", "car", "vehicle_name", "vehicle_id"):
        value = _text(row.get(key), prefer="vehicle")
        if value and value != "-":
            return value
    return ""


def _vehicle_identity_values(row: dict[str, Any]) -> set[str]:
    """같은 차량을 vehicle_id/차량명/번호 중 어떤 값으로 받아도 하나로 묶는다."""
    values: set[str] = set()
    keys = (
        "vehicle_id", "vehicle_name", "display_name", "name",
        "plate_number", "vehicle_no", "vehicleNumber", "car",
    )
    for source in (row, row.get("raw") if isinstance(row.get("raw"), dict) else {}):
        for key in keys:
            value = _text(source.get(key), prefer="vehicle")
            if value and value != "-":
                values.add(value.casefold())
    label = _vehicle_label(row)
    if label:
        values.add(label.casefold())
    return values


def _dedupe_vehicle_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """권한 필터 후 같은 차량이 여러 이름으로 섞여 내려가는 것을 막는다."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        identities = _vehicle_identity_values(row)
        if identities and identities & seen:
            continue
        result.append(row)
        seen.update(identities)
    return result


def _vehicle_to_mobile(row: dict[str, Any]) -> dict[str, Any] | None:
    car = _vehicle_label(row)
    if not car:
        return None
    return {
        "vehicle_id": _text(row.get("vehicle_id"), prefer="vehicle"),
        "vehicle_name": _text(row.get("vehicle_name"), prefer="vehicle"),
        "plate_number": _text(row.get("plate_number"), prefer="vehicle"),
        "car": car,
        "vehicle_type": _text(row.get("vehicle_type")),
        "business": _text(row.get("business_name") or row.get("business"), prefer="business"),
        "site": _text(row.get("work_site_name") or row.get("work_site") or row.get("site"), prefer="site"),
        "main_driver": _text(row.get("main_driver") or row.get("driver") or row.get("driver_name")),
        "status": _text(row.get("status")),
        "car_model": _text(row.get("car_model")),
        "contract_end": _text(row.get("contract_end")),
        "baseline_odometer": _float(row.get("baseline_odometer") or row.get("start_odometer") or row.get("initial_odometer")),
        "current_odometer": _float(row.get("current_odometer")),
        "raw": row,
    }


def _vehicle_maps(vehicles: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_label: dict[str, dict[str, Any]] = {}
    for row in vehicles:
        vehicle_id = _text(row.get("vehicle_id"))
        label = _vehicle_label(row)
        if vehicle_id:
            by_id[vehicle_id] = row
        if label:
            by_label[label] = row
    return by_id, by_label


def _resolve_vehicle(payload: dict[str, Any], vehicles: list[dict[str, Any]]) -> dict[str, Any]:
    by_id, by_label = _vehicle_maps(vehicles)
    vehicle_id = _text(payload.get("vehicle_id"))
    car = _text(payload.get("car") or payload.get("plate_number") or payload.get("vehicle_no"))
    vehicle = by_id.get(vehicle_id) if vehicle_id else None
    if not vehicle and car:
        vehicle = by_label.get(car)
    if vehicle:
        return vehicle
    if vehicle_id or car:
        # PC에서 차량 등록 직후 상세기록을 먼저 저장하는 경우,
        # 전체 차량 스냅샷 반영이 늦어도 기록 저장이 막히지 않도록
        # 요청값 안의 차량 정보를 임시 차량 정보로 사용합니다.
        return {
            "vehicle_id": vehicle_id,
            "vehicle_name": _text(payload.get("vehicle_name")) or car or vehicle_id,
            "plate_number": _text(payload.get("plate_number")) or car,
            "vehicle_no": _text(payload.get("vehicle_no")) or car,
            "business_name": _text(payload.get("business") or payload.get("business_name")),
            "business": _text(payload.get("business") or payload.get("business_name")),
            "work_site_name": _text(payload.get("site") or payload.get("work_site_name") or payload.get("work_site")),
            "work_site": _text(payload.get("site") or payload.get("work_site_name") or payload.get("work_site")),
            "site": _text(payload.get("site") or payload.get("work_site_name") or payload.get("work_site")),
            "baseline_odometer": _float(payload.get("baseline_odometer") or payload.get("start_odometer") or payload.get("initial_odometer")),
        }
    raise HTTPException(status_code=400, detail="차량 정보를 찾을 수 없습니다.")


def _run_log_to_mobile(row: VehicleRunLog | dict[str, Any], vehicle_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    data = row if isinstance(row, dict) else {
        "log_id": row.log_id,
        "vehicle_id": row.vehicle_id,
        "car": row.car,
        "business": row.business,
        "site": row.site,
        "log_date": row.log_date,
        "driver_name": row.driver_name,
        "end_odometer": row.end_odometer,
        "round_trips": row.round_trips,
        "note": row.note,
        "source": row.source,
        "updated_by": row.updated_by,
        "created_at": row.created_at.isoformat(timespec="seconds") if row.created_at else "",
        "updated_at": row.updated_at.isoformat(timespec="seconds") if row.updated_at else "",
    }
    vehicle_id = _text(data.get("vehicle_id"))
    vehicle = vehicle_by_id.get(vehicle_id, {})
    car = _text(data.get("car")) or (_vehicle_label(vehicle) if vehicle else vehicle_id)
    return {
        "log_id": _text(data.get("log_id")),
        "vehicle_id": vehicle_id,
        "car": car,
        "business": _text(data.get("business") or vehicle.get("business_name") or vehicle.get("business")),
        "site": _text(data.get("site") or vehicle.get("work_site_name") or vehicle.get("work_site") or vehicle.get("site")),
        "date": _text(data.get("log_date") or data.get("date")),
        "log_date": _text(data.get("log_date") or data.get("date")),
        "created_at": _text(data.get("created_at")),
        "updated_at": _text(data.get("updated_at")),
        "savedAt": _text(data.get("created_at") or data.get("updated_at") or data.get("log_date") or data.get("date")),
        "driver": _text(data.get("driver_name") or data.get("driver")),
        "driver_name": _text(data.get("driver_name") or data.get("driver")),
        "km": data.get("end_odometer") or data.get("km") or 0,
        "end_odometer": data.get("end_odometer") or data.get("km") or 0,
        "trip": data.get("round_trips") or data.get("trip") or "",
        "round_trips": data.get("round_trips") or data.get("trip") or "",
        "note": _text(data.get("note")),
        "source": _text(data.get("source") or "mobile"),
        "updated_by": _text(data.get("updated_by")),
        "raw": data,
    }


def _fuel_log_to_mobile(row: VehicleFuelLog, vehicle_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    vehicle = vehicle_by_id.get(_text(row.vehicle_id), {})
    return {
        "fuel_id": _text(row.fuel_id),
        "vehicle_id": _text(row.vehicle_id),
        "car": _text(row.car) or _vehicle_label(vehicle),
        "business": _text(row.business) or _text(vehicle.get("business_name") or vehicle.get("business")),
        "site": _text(row.site) or _text(vehicle.get("work_site_name") or vehicle.get("work_site") or vehicle.get("site")),
        "fuel_date": _text(row.fuel_date),
        "amount": row.amount or 0,
        "note": _text(row.note),
        "source": _text(row.source or "mobile"),
        "updated_by": _text(row.updated_by),
        "savedAt": row.updated_at.isoformat(timespec="seconds") if row.updated_at else _text(row.fuel_date),
    }


def _cost_log_to_mobile(row: VehicleCostLog, vehicle_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    vehicle = vehicle_by_id.get(_text(row.vehicle_id), {})
    return {
        "cost_id": _text(row.cost_id),
        "vehicle_id": _text(row.vehicle_id),
        "car": _text(row.car) or _vehicle_label(vehicle),
        "business": _text(row.business) or _text(vehicle.get("business_name") or vehicle.get("business")),
        "site": _text(row.site) or _text(vehicle.get("work_site_name") or vehicle.get("work_site") or vehicle.get("site")),
        "cost_date": _text(row.cost_date),
        "category": _text(row.category or "기타"),
        "amount": row.amount or 0,
        "description": _text(row.description),
        "note": _text(row.note),
        "source": _text(row.source or "mobile"),
        "updated_by": _text(row.updated_by),
        "savedAt": row.updated_at.isoformat(timespec="seconds") if row.updated_at else _text(row.cost_date),
    }


def _vehicle_payload_info(vehicle: dict[str, Any]) -> dict[str, Any]:
    return {
        "vehicle_id": _text(vehicle.get("vehicle_id")),
        "car": _vehicle_label(vehicle),
        "business": _text(vehicle.get("business_name") or vehicle.get("business")),
        "site": _text(vehicle.get("work_site_name") or vehicle.get("work_site") or vehicle.get("site")),
        "baseline_odometer": _float(vehicle.get("baseline_odometer") or vehicle.get("start_odometer") or vehicle.get("initial_odometer")),
    }


def _vehicle_baseline_odometer(vehicle: dict[str, Any]) -> float:
    return _float(vehicle.get("baseline_odometer") or vehicle.get("start_odometer") or vehicle.get("initial_odometer"))


def _run_log_order_key(row: VehicleRunLog, fallback_index: int = 0) -> tuple:
    created_at = row.created_at or row.updated_at or datetime.min
    return (_text(row.log_date), created_at, _text(row.log_id), fallback_index)


def _target_run_order_key(db: Session, vehicle_info: dict[str, str], log_date: str, exclude_log_id: str = "") -> tuple:
    target_date = _text(log_date) or "9999-12-31"
    target_id = _text(exclude_log_id)
    if target_id:
        current = db.get(VehicleRunLog, target_id)
        if current:
            key = _run_log_order_key(current)
            return (target_date, key[1], key[2], key[3])
    return (target_date, datetime.max, "~", 10**12)


def _latest_previous_run_odometer(db: Session, vehicle_info: dict[str, str], log_date: str, exclude_log_id: str = "") -> float:
    baseline = _vehicle_baseline_odometer({"baseline_odometer": vehicle_info.get("baseline_odometer", 0)})
    vehicle_id = _text(vehicle_info.get("vehicle_id"))
    car = _text(vehicle_info.get("car"))
    deleted_run_ids = _deleted_log_ids(db, "run")
    target_key = _target_run_order_key(db, vehicle_info, log_date, exclude_log_id)
    candidates: list[tuple[tuple, VehicleRunLog]] = []
    for idx, row in enumerate(db.query(VehicleRunLog).all()):
        row_log_id = _text(row.log_id)
        if row_log_id in deleted_run_ids:
            continue
        if exclude_log_id and row_log_id == _text(exclude_log_id):
            continue
        same_vehicle = (vehicle_id and _text(row.vehicle_id) == vehicle_id) or (car and _text(row.car) == car)
        if not same_vehicle:
            continue
        row_key = _run_log_order_key(row, idx)
        if row_key >= target_key:
            continue
        candidates.append((row_key, row))
    candidates.sort(key=lambda item: item[0])
    if not candidates:
        return baseline
    return _float(candidates[-1][1].end_odometer)


def _earliest_next_run_odometer(db: Session, vehicle_info: dict[str, str], log_date: str, exclude_log_id: str = "") -> float:
    vehicle_id = _text(vehicle_info.get("vehicle_id"))
    car = _text(vehicle_info.get("car"))
    deleted_run_ids = _deleted_log_ids(db, "run")
    target_key = _target_run_order_key(db, vehicle_info, log_date, exclude_log_id)
    candidates: list[tuple[tuple, VehicleRunLog]] = []
    for idx, row in enumerate(db.query(VehicleRunLog).all()):
        row_log_id = _text(row.log_id)
        if row_log_id in deleted_run_ids:
            continue
        if exclude_log_id and row_log_id == _text(exclude_log_id):
            continue
        same_vehicle = (vehicle_id and _text(row.vehicle_id) == vehicle_id) or (car and _text(row.car) == car)
        if not same_vehicle:
            continue
        row_key = _run_log_order_key(row, idx)
        if row_key <= target_key:
            continue
        candidates.append((row_key, row))
    candidates.sort(key=lambda item: item[0])
    if not candidates:
        return 0.0
    return _float(candidates[0][1].end_odometer)


def _ensure_vehicle_write_allowed(
    db: Session,
    payload: dict[str, Any] | None,
    authorization: str | None,
    x_auth_token: str | None,
    x_pc_sync_key: str | None,
):
    return require_permission_context(
        db,
        authorization=authorization,
        x_auth_token=x_auth_token,
        x_pc_sync_key=x_pc_sync_key,
    )


def _request_source(payload: dict[str, Any], default: str = "mobile") -> str:
    text = _text((payload or {}).get("source")) or default
    return text[:30]


def _request_user(payload: dict[str, Any], default: str = "mobile") -> str:
    return _text((payload or {}).get("updated_by") or (payload or {}).get("user") or (payload or {}).get("username") or default) or default


def _mobile_user(payload: dict[str, Any]) -> str:
    return _request_user(payload, "mobile")


def _deleted_log_ids(db: Session, log_type: str) -> set[str]:
    return {
        _text(row.log_id)
        for row in db.query(VehicleDeletedLog).filter(VehicleDeletedLog.log_type == log_type).all()
        if _text(row.log_id)
    }


def _deleted_log_payload(db: Session) -> dict[str, list[str]]:
    return {
        "run": sorted(_deleted_log_ids(db, "run")),
        "fuel": sorted(_deleted_log_ids(db, "fuel")),
        "cost": sorted(_deleted_log_ids(db, "cost")),
    }


def _clear_vehicle_delete_mark(db: Session, log_type: str, log_id: str) -> None:
    target = _text(log_id)
    if not target:
        return
    for row in db.query(VehicleDeletedLog).filter(
        VehicleDeletedLog.log_type == log_type,
        VehicleDeletedLog.log_id == target,
    ).all():
        db.delete(row)


def _mark_vehicle_log_deleted(db: Session, log_type: str, log_id: str, payload: dict[str, Any]) -> None:
    target = _text(log_id)
    if not target:
        raise HTTPException(status_code=400, detail="삭제할 기록 ID가 없습니다.")
    row = db.query(VehicleDeletedLog).filter(
        VehicleDeletedLog.log_type == log_type,
        VehicleDeletedLog.log_id == target,
    ).first()
    if row is None:
        row = VehicleDeletedLog(log_type=log_type, log_id=target)
    row.source = _request_source(payload, "pc")
    row.updated_by = _request_user(payload, "pc")
    row.deleted_at = datetime.now()
    db.add(row)


@router.get("")
def list_vehicle_snapshot(
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
    snapshot, updated_at = _load_snapshot(db)
    vehicles = _safe_list(snapshot.get("vehicles"))
    vehicle_by_id = {str(row.get("vehicle_id") or "").strip(): row for row in vehicles}
    allowed_vehicles = _dedupe_vehicle_rows(filter_vehicles_for_context(context, vehicles))
    mobile_vehicles = _dedupe_vehicle_rows([row for row in (_vehicle_to_mobile(item) for item in allowed_vehicles) if row])
    deleted_run_ids = _deleted_log_ids(db, "run")
    deleted_fuel_ids = _deleted_log_ids(db, "fuel")
    deleted_cost_ids = _deleted_log_ids(db, "cost")
    run_rows = [
        row for row in db.query(VehicleRunLog).order_by(VehicleRunLog.log_date.desc(), VehicleRunLog.updated_at.desc()).all()
        if _text(row.log_id) not in deleted_run_ids
    ]
    fuel_rows = [
        row for row in db.query(VehicleFuelLog).order_by(VehicleFuelLog.fuel_date.desc(), VehicleFuelLog.updated_at.desc()).all()
        if _text(row.fuel_id) not in deleted_fuel_ids
    ]
    cost_rows = [
        row for row in db.query(VehicleCostLog).order_by(VehicleCostLog.cost_date.desc(), VehicleCostLog.updated_at.desc()).all()
        if _text(row.cost_id) not in deleted_cost_ids
    ]
    run_rows = filter_vehicle_logs_for_context(context, run_rows, vehicle_by_id)
    fuel_rows = filter_vehicle_logs_for_context(context, fuel_rows, vehicle_by_id)
    cost_rows = filter_vehicle_logs_for_context(context, cost_rows, vehicle_by_id)
    deleted_payload = _deleted_log_payload(db)
    return {
        "ok": True,
        "source": "app_snapshot_and_mobile_logs",
        "updated_at": updated_at,
        "count": len(mobile_vehicles),
        "vehicles": mobile_vehicles,
        "run_logs": [_run_log_to_mobile(row, vehicle_by_id) for row in run_rows],
        "fuel_logs": [_fuel_log_to_mobile(row, vehicle_by_id) for row in fuel_rows],
        "cost_logs": [_cost_log_to_mobile(row, vehicle_by_id) for row in cost_rows],
        "deleted": deleted_payload,
        "deleted_log_ids": deleted_payload,
        "raw": {
            "vehicles": allowed_vehicles,
        },
    }


@router.get("/logs")
def list_vehicle_logs(
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
    snapshot, _ = _load_snapshot(db)
    vehicles = _safe_list(snapshot.get("vehicles"))
    vehicle_by_id = {str(row.get("vehicle_id") or "").strip(): row for row in vehicles}
    deleted_run_ids = _deleted_log_ids(db, "run")
    deleted_fuel_ids = _deleted_log_ids(db, "fuel")
    deleted_cost_ids = _deleted_log_ids(db, "cost")
    run_rows = [
        row for row in db.query(VehicleRunLog).order_by(VehicleRunLog.log_date.desc(), VehicleRunLog.updated_at.desc()).all()
        if _text(row.log_id) not in deleted_run_ids
    ]
    fuel_rows = [
        row for row in db.query(VehicleFuelLog).order_by(VehicleFuelLog.fuel_date.desc(), VehicleFuelLog.updated_at.desc()).all()
        if _text(row.fuel_id) not in deleted_fuel_ids
    ]
    cost_rows = [
        row for row in db.query(VehicleCostLog).order_by(VehicleCostLog.cost_date.desc(), VehicleCostLog.updated_at.desc()).all()
        if _text(row.cost_id) not in deleted_cost_ids
    ]
    run_rows = filter_vehicle_logs_for_context(context, run_rows, vehicle_by_id)
    fuel_rows = filter_vehicle_logs_for_context(context, fuel_rows, vehicle_by_id)
    cost_rows = filter_vehicle_logs_for_context(context, cost_rows, vehicle_by_id)
    deleted_payload = _deleted_log_payload(db)
    return {
        "ok": True,
        "run_logs": [_run_log_to_mobile(row, vehicle_by_id) for row in run_rows],
        "fuel_logs": [_fuel_log_to_mobile(row, vehicle_by_id) for row in fuel_rows],
        "cost_logs": [_cost_log_to_mobile(row, vehicle_by_id) for row in cost_rows],
        "deleted": deleted_payload,
        "deleted_log_ids": deleted_payload,
    }


@router.post("/run-logs")
def save_vehicle_run_log(
    payload: dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="요청 값이 올바르지 않습니다.")
    context = _ensure_vehicle_write_allowed(db, payload, authorization, x_auth_token, x_pc_sync_key)
    snapshot, _ = _load_snapshot(db)
    vehicles = _safe_list(snapshot.get("vehicles"))
    vehicle = _resolve_vehicle(payload, vehicles)
    ensure_vehicle_allowed(context, vehicle)
    info = _vehicle_payload_info(vehicle)
    log_id = _text(payload.get("log_id")) or f"mobile-run-{uuid4().hex[:16]}"
    row = db.get(VehicleRunLog, log_id) or VehicleRunLog(log_id=log_id)
    row.vehicle_id = info["vehicle_id"]
    row.car = info["car"]
    row.business = info["business"]
    row.site = info["site"]
    row.log_date = _date_text(payload.get("log_date") or payload.get("date"))
    row.driver_name = _text(payload.get("driver_name") or payload.get("driver"))
    end_odometer = _float(payload.get("end_odometer") or payload.get("km"))
    if end_odometer <= 0:
        raise HTTPException(status_code=400, detail="종료 계기판 km를 입력해 주세요.")

    request_source = _request_source(payload, "mobile")
    # PC 프로그램은 저장 전에 이미 화면/로컬 기준으로 계기판 순서를 검증합니다.
    # 서버 스냅샷/등록 순서 차이로 정상 PC 저장이 400으로 막히지 않도록
    # PC 요청은 서버 계기판 앞뒤 검증을 건너뛰고 저장만 담당합니다.
    # 모바일/외부 요청은 서버에서 기존 검증을 유지합니다.
    if not request_source.lower().startswith("pc"):
        previous_odometer = _latest_previous_run_odometer(db, info, row.log_date, exclude_log_id=log_id)
        if previous_odometer > 0 and end_odometer < previous_odometer:
            raise HTTPException(status_code=400, detail=f"종료 계기판 km가 이전 계기판 {int(previous_odometer):,}km보다 작습니다.")
        next_odometer = _earliest_next_run_odometer(db, info, row.log_date, exclude_log_id=log_id)
        if next_odometer > 0 and end_odometer > next_odometer:
            raise HTTPException(status_code=400, detail=f"종료 계기판 km가 다음 기록 {int(next_odometer):,}km보다 클 수 없습니다.")

    row.end_odometer = end_odometer
    row.round_trips = _int_range(payload.get("round_trips") or payload.get("trip"), default=1)
    row.note = _text(payload.get("note"))
    row.source = request_source
    row.updated_by = _request_user(payload, "mobile")
    _clear_vehicle_delete_mark(db, "run", log_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "message": "운행기록이 저장되었습니다.", "record": _run_log_to_mobile(row, {info["vehicle_id"]: vehicle})}


@router.post("/fuel-logs")
def save_vehicle_fuel_log(
    payload: dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="요청 값이 올바르지 않습니다.")
    context = _ensure_vehicle_write_allowed(db, payload, authorization, x_auth_token, x_pc_sync_key)
    snapshot, _ = _load_snapshot(db)
    vehicles = _safe_list(snapshot.get("vehicles"))
    vehicle = _resolve_vehicle(payload, vehicles)
    ensure_vehicle_allowed(context, vehicle)
    info = _vehicle_payload_info(vehicle)
    fuel_id = _text(payload.get("fuel_id")) or f"mobile-fuel-{uuid4().hex[:16]}"
    row = db.get(VehicleFuelLog, fuel_id) or VehicleFuelLog(fuel_id=fuel_id)
    row.vehicle_id = info["vehicle_id"]
    row.car = info["car"]
    row.business = info["business"]
    row.site = info["site"]
    row.fuel_date = _date_text(payload.get("fuel_date") or payload.get("date"))
    row.amount = _float(payload.get("amount"))
    row.note = _text(payload.get("note"))
    row.source = _request_source(payload, "mobile")
    row.updated_by = _request_user(payload, "mobile")
    _clear_vehicle_delete_mark(db, "fuel", fuel_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "message": "주유기록이 저장되었습니다.", "record": _fuel_log_to_mobile(row, {info["vehicle_id"]: vehicle})}


@router.post("/cost-logs")
def save_vehicle_cost_log(
    payload: dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="요청 값이 올바르지 않습니다.")
    context = _ensure_vehicle_write_allowed(db, payload, authorization, x_auth_token, x_pc_sync_key)
    snapshot, _ = _load_snapshot(db)
    vehicles = _safe_list(snapshot.get("vehicles"))
    vehicle = _resolve_vehicle(payload, vehicles)
    ensure_vehicle_allowed(context, vehicle)
    info = _vehicle_payload_info(vehicle)
    cost_id = _text(payload.get("cost_id")) or f"mobile-cost-{uuid4().hex[:16]}"
    row = db.get(VehicleCostLog, cost_id) or VehicleCostLog(cost_id=cost_id)
    row.vehicle_id = info["vehicle_id"]
    row.car = info["car"]
    row.business = info["business"]
    row.site = info["site"]
    row.cost_date = _date_text(payload.get("cost_date") or payload.get("date"))
    row.category = _text(payload.get("category")) or "기타"
    row.amount = _float(payload.get("amount"))
    row.description = _text(payload.get("description"))
    row.note = _text(payload.get("note"))
    row.source = _request_source(payload, "mobile")
    row.updated_by = _request_user(payload, "mobile")
    _clear_vehicle_delete_mark(db, "cost", cost_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "message": "기타비용이 저장되었습니다.", "record": _cost_log_to_mobile(row, {info["vehicle_id"]: vehicle})}


@router.delete("/run-logs/{log_id}")
def delete_vehicle_run_log(
    log_id: str,
    payload: dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
):
    payload = payload if isinstance(payload, dict) else {}
    context = _ensure_vehicle_write_allowed(db, payload, authorization, x_auth_token, x_pc_sync_key)
    ensure_pc_or_super(context)
    target = _text(log_id)
    if not target:
        raise HTTPException(status_code=400, detail="삭제할 운행기록 ID가 없습니다.")
    row = db.get(VehicleRunLog, target)
    if row is not None:
        db.delete(row)
    _mark_vehicle_log_deleted(db, "run", target, payload)
    db.commit()
    return {"ok": True, "message": "운행기록 삭제 상태가 저장되었습니다.", "log_id": target, "deleted": True}


@router.delete("/fuel-logs/{fuel_id}")
def delete_vehicle_fuel_log(
    fuel_id: str,
    payload: dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
):
    payload = payload if isinstance(payload, dict) else {}
    context = _ensure_vehicle_write_allowed(db, payload, authorization, x_auth_token, x_pc_sync_key)
    ensure_pc_or_super(context)
    target = _text(fuel_id)
    if not target:
        raise HTTPException(status_code=400, detail="삭제할 주유기록 ID가 없습니다.")
    row = db.get(VehicleFuelLog, target)
    if row is not None:
        db.delete(row)
    _mark_vehicle_log_deleted(db, "fuel", target, payload)
    db.commit()
    return {"ok": True, "message": "주유기록 삭제 상태가 저장되었습니다.", "fuel_id": target, "deleted": True}


@router.delete("/cost-logs/{cost_id}")
def delete_vehicle_cost_log(
    cost_id: str,
    payload: dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
):
    payload = payload if isinstance(payload, dict) else {}
    context = _ensure_vehicle_write_allowed(db, payload, authorization, x_auth_token, x_pc_sync_key)
    ensure_pc_or_super(context)
    target = _text(cost_id)
    if not target:
        raise HTTPException(status_code=400, detail="삭제할 기타비용 ID가 없습니다.")
    row = db.get(VehicleCostLog, target)
    if row is not None:
        db.delete(row)
    _mark_vehicle_log_deleted(db, "cost", target, payload)
    db.commit()
    return {"ok": True, "message": "기타비용 삭제 상태가 저장되었습니다.", "cost_id": target, "deleted": True}
