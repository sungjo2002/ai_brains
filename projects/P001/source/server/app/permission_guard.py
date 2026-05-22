from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import AdminSiteAssignment, AdminUser, AdminVehicleAssignment
from .routes.mobile_auth import ROLE_SUPER, _get_token_from_header, _load_admin_by_token


def _text(value: Any) -> str:
    """권한 비교용 표시값을 안전하게 문자열로 정리한다.

    PC 스냅샷에는 근무사업장/차량 배정값이 문자열이 아니라
    {"business": "...", "work_site": "..."} 형태의 dict로 들어올 수 있다.
    dict를 그대로 str() 처리하면 "{'business': ...}" 같은 값이 되어
    일반관리자 범위 비교가 실패하므로 우선순위 필드만 뽑아 사용한다.
    """
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    if isinstance(value, dict):
        for key in (
            "name", "work_site", "site", "site_name", "work_site_name",
            "business", "business_name", "company", "company_name",
            "car", "vehicle_no", "plate_number", "vehicleNumber",
            "vehicle_id", "vehicle_name", "username", "login_id",
            "loginId", "display_name", "employee_name",
        ):
            text = _text(value.get(key))
            if text:
                return text
        return ""
    if isinstance(value, (list, tuple, set)):
        for item in value:
            text = _text(item)
            if text:
                return text
        return ""
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return " ".join(_text(value).split()).casefold()


@dataclass(frozen=True)
class PermissionContext:
    is_pc: bool = False
    admin: AdminUser | None = None
    is_super: bool = False
    businesses: frozenset[str] = frozenset()
    work_sites: frozenset[str] = frozenset()
    site_pairs: frozenset[tuple[str, str]] = frozenset()
    vehicles: frozenset[str] = frozenset()

    @property
    def is_mobile_manager(self) -> bool:
        return (not self.is_pc) and (self.admin is not None) and (not self.is_super)


def _load_assignments(db: Session, admin: AdminUser) -> PermissionContext:
    is_super = _text(admin.role) == ROLE_SUPER
    if is_super:
        return PermissionContext(is_pc=False, admin=admin, is_super=True)

    site_rows = db.execute(
        select(AdminSiteAssignment).where(AdminSiteAssignment.admin_id == admin.id)
    ).scalars().all()
    vehicle_rows = db.execute(
        select(AdminVehicleAssignment).where(AdminVehicleAssignment.admin_id == admin.id)
    ).scalars().all()

    return PermissionContext(
        is_pc=False,
        admin=admin,
        is_super=False,
        businesses=frozenset(_norm(row.business_name) for row in site_rows if _text(row.business_name)),
        work_sites=frozenset(_norm(row.work_site) for row in site_rows if _text(row.work_site)),
        site_pairs=frozenset(
            (_norm(row.business_name), _norm(row.work_site))
            for row in site_rows
            if _text(row.business_name) or _text(row.work_site)
        ),
        vehicles=frozenset(_norm(row.vehicle_no) for row in vehicle_rows if _text(row.vehicle_no)),
    )


def require_permission_context(
    db: Session,
    *,
    authorization: str | None = None,
    x_auth_token: str | None = None,
    x_pc_sync_key: str | None = None,
) -> PermissionContext:
    """PC 동기화 키 또는 모바일 로그인 토큰을 확인한다."""
    configured_key = _text(getattr(settings, "pc_sync_key", ""))
    request_key = _text(x_pc_sync_key)
    if configured_key and request_key and request_key == configured_key:
        return PermissionContext(is_pc=True, is_super=True)

    token = _get_token_from_header(authorization, x_auth_token)
    if token:
        admin = _load_admin_by_token(db, token)
        return _load_assignments(db, admin)

    raise HTTPException(status_code=401, detail="로그인이 필요합니다.")


def ensure_pc_or_super(context: PermissionContext) -> None:
    if context.is_pc or context.is_super:
        return
    raise HTTPException(status_code=403, detail="권한이 없습니다.")


def _scope_allowed(context: PermissionContext, business: Any = "", site: Any = "") -> bool:
    if context.is_pc or context.is_super:
        return True

    business_key = _norm(business)
    site_key = _norm(site)

    # 사업자와 사업장이 둘 다 있는 데이터는 한 쌍으로 검사한다.
    # 예: A사업자/1공장 담당자가 B사업자/1공장까지 보게 되는 것을 막는다.
    if business_key and site_key:
        if (business_key, site_key) in context.site_pairs:
            return True
        if (business_key, "") in context.site_pairs:
            return True
        if ("", site_key) in context.site_pairs:
            return True
        return False

    # 한쪽 값만 들어온 데이터는 기존 단일 범위 방식으로 방어한다.
    if business_key and business_key in context.businesses:
        return True
    if site_key and site_key in context.work_sites:
        return True
    return False


def ensure_site_allowed(context: PermissionContext, *, business: Any = "", site: Any = "") -> None:
    if _scope_allowed(context, business, site):
        return
    raise HTTPException(status_code=403, detail="담당 근무사업장 범위가 아닙니다.")


def _value_from_record(record: Any, *keys: str) -> Any:
    if isinstance(record, dict):
        for key in keys:
            if key in record and record.get(key) not in (None, ""):
                return record.get(key)
        raw = record.get("raw")
        if isinstance(raw, dict):
            for key in keys:
                if key in raw and raw.get(key) not in (None, ""):
                    return raw.get(key)
        return ""
    for key in keys:
        value = getattr(record, key, None)
        if value not in (None, ""):
            return value
    return ""


def employee_allowed(context: PermissionContext, employee: Any) -> bool:
    return _scope_allowed(
        context,
        _value_from_record(employee, "affiliated_business", "business", "business_name", "company", "company_name"),
        _value_from_record(employee, "work_site", "site", "site_name", "work_site_name", "worksite", "factory"),
    )


def filter_employees_for_context(context: PermissionContext, rows: Iterable[Any]) -> list[Any]:
    if context.is_pc or context.is_super:
        return list(rows)
    return [row for row in rows if employee_allowed(context, row)]


def attendance_record_allowed(context: PermissionContext, record: dict[str, Any]) -> bool:
    return _scope_allowed(context, record.get("business"), record.get("site"))


def ensure_attendance_record_allowed(context: PermissionContext, record: dict[str, Any]) -> None:
    if attendance_record_allowed(context, record):
        return
    raise HTTPException(status_code=403, detail={
        "status": "forbidden",
        "message": "담당 근무사업장 근태만 저장할 수 있습니다.",
    })


def _vehicle_values(vehicle: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    keys = (
        "vehicle_id", "vehicle_no", "plate_number", "vehicle_name", "car",
        "car_number", "number", "label",
    )
    for key in keys:
        value = _norm(vehicle.get(key))
        if value:
            values.add(value)
    raw = vehicle.get("raw")
    if isinstance(raw, dict):
        for key in keys:
            value = _norm(raw.get(key))
            if value:
                values.add(value)
    return values


def vehicle_allowed(context: PermissionContext, vehicle: dict[str, Any]) -> bool:
    if context.is_pc or context.is_super:
        return True
    if not context.vehicles:
        return False
    return bool(_vehicle_values(vehicle) & set(context.vehicles))


def ensure_vehicle_allowed(context: PermissionContext, vehicle: dict[str, Any]) -> None:
    if vehicle_allowed(context, vehicle):
        return
    raise HTTPException(status_code=403, detail="담당 차량만 조회/저장할 수 있습니다.")


def filter_vehicles_for_context(context: PermissionContext, vehicles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if context.is_pc or context.is_super:
        return list(vehicles)
    return [row for row in vehicles if vehicle_allowed(context, row)]


def vehicle_log_allowed(context: PermissionContext, log: Any, vehicle_by_id: dict[str, dict[str, Any]] | None = None) -> bool:
    if context.is_pc or context.is_super:
        return True
    if not context.vehicles:
        return False

    vehicle: dict[str, Any] = {}
    vehicle_id = _text(getattr(log, "vehicle_id", ""))
    if vehicle_by_id and vehicle_id:
        vehicle = vehicle_by_id.get(vehicle_id) or {}

    values = _vehicle_values(vehicle)
    for attr in ("vehicle_id", "car", "vehicle_no", "plate_number", "vehicle_name"):
        value = _norm(getattr(log, attr, ""))
        if value:
            values.add(value)
    return bool(values & set(context.vehicles))


def filter_vehicle_logs_for_context(
    context: PermissionContext,
    rows: Iterable[Any],
    vehicle_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[Any]:
    if context.is_pc or context.is_super:
        return list(rows)
    return [row for row in rows if vehicle_log_allowed(context, row, vehicle_by_id)]
