from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    AdminSiteAssignment,
    AdminToken,
    AdminUser,
    AdminVehicleAssignment,
    AppSnapshot,
)

router = APIRouter(prefix="/api", tags=["mobile-auth"])

TOKEN_DAYS = 30
ROLE_SUPER = "super_admin"
ROLE_MANAGER = "manager"


class LoginRequest(BaseModel):
    username: str | None = None
    password: str | None = None
    user_id: str | None = None
    userId: str | None = None
    login_id: str | None = None


def _now() -> datetime:
    return datetime.now()


def _server_time_payload() -> dict:
    now = _now()
    return {
        "status": "ok",
        "server_date": now.strftime("%Y-%m-%d"),
        "server_time": now.strftime("%H:%M:%S"),
        "server_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "server_ym": now.strftime("%Y-%m"),
    }


def _hash_password(password: str, salt: str | None = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    ).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def _verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash.startswith("pbkdf2_sha256$"):
        return secrets.compare_digest(password, stored_hash)
    try:
        _, salt, digest = stored_hash.split("$", 2)
    except ValueError:
        return False
    expected = _hash_password(password, salt).split("$", 2)[2]
    return secrets.compare_digest(expected, digest)


def _seed_default_admins(db: Session) -> None:
    """운영 서버에서는 기본 관리자 계정을 자동 생성하지 않는다.

    관리자 계정은 PC 프로그램의 계정정보/스냅샷을 기준으로만 생성·갱신한다.
    이 함수는 기존 호출부 호환을 위해 남겨두되 아무 작업도 하지 않는다.
    """
    return


def _issue_token(db: Session, admin: AdminUser) -> str:
    token = secrets.token_urlsafe(48)
    expires_at = _now() + timedelta(days=TOKEN_DAYS)
    db.add(AdminToken(
        token=token,
        admin_id=admin.id,
        expires_at=expires_at,
        is_active=1,
    ))
    admin.last_login_at = _now()
    db.commit()
    return token


def _get_token_from_header(authorization: str | None, x_auth_token: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    if x_auth_token:
        return x_auth_token.strip()
    return ""


def _load_admin_by_token(db: Session, token: str) -> AdminUser:
    if not token:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    token_row = db.execute(
        select(AdminToken).where(
            AdminToken.token == token,
            AdminToken.is_active == 1,
        )
    ).scalar_one_or_none()
    if not token_row or token_row.expires_at < _now():
        raise HTTPException(status_code=401, detail="로그인이 만료되었습니다.")

    admin = db.get(AdminUser, token_row.admin_id)
    if not admin or admin.is_active != 1:
        raise HTTPException(status_code=401, detail="사용할 수 없는 계정입니다.")
    return admin


def _admin_payload(db: Session, admin: AdminUser, token: str | None = None) -> dict:
    is_super = admin.role == ROLE_SUPER

    site_rows = [] if is_super else db.execute(
        select(AdminSiteAssignment).where(AdminSiteAssignment.admin_id == admin.id)
    ).scalars().all()
    vehicle_rows = [] if is_super else db.execute(
        select(AdminVehicleAssignment).where(AdminVehicleAssignment.admin_id == admin.id)
    ).scalars().all()

    businesses = sorted({row.business_name for row in site_rows if row.business_name})
    work_sites = sorted({row.work_site for row in site_rows if row.work_site})
    vehicles = sorted({row.vehicle_no for row in vehicle_rows if row.vehicle_no})

    payload = {
        "success": True,
        "token": token,
        "role": admin.role,
        "role_name": "최고 관리자" if is_super else "일반 관리자",
        "user": {
            "id": admin.id,
            "username": admin.username,
            "name": admin.display_name,
            "display_name": admin.display_name,
            "role": admin.role,
            "role_name": "최고 관리자" if is_super else "일반 관리자",
            "businesses": businesses,
            "work_sites": work_sites,
            "vehicles": vehicles,
            "cars": vehicles,
        },
        "permissions": {
            "is_super_admin": is_super,
            "can_view_all": is_super,
            "can_edit_attendance": True,
            "can_edit_closed_month": False,
            "can_manage_vehicle_logs": True,
            "can_simple_register_employee": True,
            "businesses": businesses,
            "work_sites": work_sites,
            "vehicles": vehicles,
            "cars": vehicles,
        },
        "assignments": {
            "businesses": businesses,
            "work_sites": work_sites,
            "vehicles": vehicles,
        },
        "userType": "super" if is_super else "manager",
        "allowedBusinesses": businesses,
        "allowedSites": work_sites,
        "allowedVehicles": vehicles,
        "businesses": businesses,
        "work_sites": work_sites,
        "vehicles": vehicles,
        "cars": vehicles,
        "server": _server_time_payload(),
    }
    if token is None:
        payload.pop("token", None)
    return payload



SERVER_TUPLE_MARKER = "__workforce_tuple__"
SERVER_DICT_ITEMS_MARKER = "__workforce_dict_items__"


def _decode_workforce_value(value):
    if isinstance(value, list):
        return [_decode_workforce_value(item) for item in value]
    if isinstance(value, dict):
        if set(value.keys()) == {SERVER_TUPLE_MARKER}:
            return tuple(_decode_workforce_value(item) for item in value.get(SERVER_TUPLE_MARKER, []))
        if set(value.keys()) == {SERVER_DICT_ITEMS_MARKER}:
            decoded = {}
            for item in value.get(SERVER_DICT_ITEMS_MARKER, []):
                if isinstance(item, list) and len(item) == 2:
                    decoded[_decode_workforce_value(item[0])] = _decode_workforce_value(item[1])
            return decoded
        return {str(key): _decode_workforce_value(item) for key, item in value.items()}
    return value


def _scope_text(value, *, prefer: str | None = None) -> str:
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
        elif prefer == "user":
            prefer_keys = ["username", "login_id", "loginId", "user_id", "userId", "id", "name", "display_name"]
        keys = prefer_keys + [
            "name", "work_site", "site", "site_name", "work_site_name",
            "business", "business_name", "company", "company_name",
            "car", "vehicle_no", "plate_number", "vehicleNumber",
            "vehicle_id", "vehicle_name", "username", "login_id",
            "loginId", "display_name", "employee_name",
        ]
        for key in keys:
            text = _scope_text(value.get(key))
            if text:
                return text
        return ""
    if isinstance(value, (list, tuple, set)):
        for item in value:
            text = _scope_text(item, prefer=prefer)
            if text:
                return text
        return ""
    return str(value or "").strip()


def _scope_list(*values, prefer: str | None = None) -> list[str]:
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            candidates = value
        elif isinstance(value, dict):
            candidates = [value]
        else:
            candidates = str(value).replace("|", ",").split(",")
        for item in candidates:
            text = _scope_text(item, prefer=prefer)
            if text and text not in result and text not in ("전체", "all", "ALL"):
                result.append(text)
    return result


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


def _manager_accounts_from_snapshot(db: Session) -> list[dict]:
    root = _snapshot_root(db)
    candidates = [
        root.get("manager_accounts"),
        root.get("managers"),
        root.get("admin_accounts"),
        root.get("admins"),
        root.get("users"),
    ]
    rows: list[dict] = []
    for candidate in candidates:
        if isinstance(candidate, list):
            rows.extend(item for item in candidate if isinstance(item, dict))
    return rows


def _snapshot_account_login_id(row: dict) -> str:
    return _scope_text(
        row.get("username")
        or row.get("login_id")
        or row.get("loginId")
        or row.get("user_id")
        or row.get("userId")
        or row.get("id")
    )


def _snapshot_account_password(row: dict) -> str:
    return str(row.get("password") or row.get("password_plain") or row.get("passcode") or "")


def _snapshot_account_is_active(row: dict) -> bool:
    return row.get("active") is not False and row.get("use") is not False and row.get("enabled") is not False


def _snapshot_account_is_super(row: dict) -> bool:
    role_text = _scope_text(row.get("role") or row.get("userType") or row.get("user_type")).lower()
    if role_text in ("super", "admin", "super_admin", "최고관리자", "최고 관리자"):
        return True
    return bool(row.get("is_super_admin") or row.get("can_view_all"))


def _snapshot_account_name(row: dict, fallback: str) -> str:
    return _scope_text(row.get("name") or row.get("display_name") or row.get("manager_name") or fallback)


def _snapshot_account_key(row: dict) -> str:
    return _snapshot_account_login_id(row).strip().casefold()


def _find_snapshot_manager_row(db: Session, username: str) -> dict | None:
    login_key = _scope_text(username).casefold()
    if not login_key:
        return None
    for row in _manager_accounts_from_snapshot(db):
        if not _snapshot_account_is_active(row):
            continue
        if _snapshot_account_key(row) == login_key:
            return row
    return None


def _vehicle_label_from_snapshot(row: dict) -> list[str]:
    values: list[str] = []
    for key in ("plate_number", "vehicle_no", "car", "vehicle_name", "vehicle_id"):
        value = _scope_text(row.get(key), prefer="vehicle")
        if value and value not in values:
            values.append(value)
    return values


def _vehicle_primary_label_from_snapshot(row: dict) -> str:
    """모바일 표시/권한 저장용 대표 차량명.
    vehicle_id까지 모두 권한값으로 저장하면 aaa/V003/aaa처럼 중복 표시될 수 있어
    실제 표시명 우선으로 한 차량당 하나만 저장한다.
    """
    for key in ("plate_number", "vehicle_no", "car", "vehicle_name", "vehicle_id"):
        value = _scope_text(row.get(key), prefer="vehicle")
        if value and value != "-":
            return value
    return ""


def _snapshot_vehicle_alias_map(db: Session) -> dict[str, str]:
    root = _snapshot_root(db)
    vehicles = root.get("vehicles")
    if not isinstance(vehicles, list):
        return {}
    alias_map: dict[str, str] = {}
    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            continue
        primary = _vehicle_primary_label_from_snapshot(vehicle)
        if not primary:
            continue
        for alias in _vehicle_label_from_snapshot(vehicle):
            if alias:
                alias_map[alias.casefold()] = primary
    return alias_map


def _canonical_vehicle_assignments(db: Session, vehicles: list[str]) -> list[str]:
    alias_map = _snapshot_vehicle_alias_map(db)
    result: list[str] = []
    seen: set[str] = set()
    for vehicle in vehicles:
        text = _scope_text(vehicle, prefer="vehicle")
        if not text:
            continue
        canonical = alias_map.get(text.casefold(), text)
        key = canonical.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(canonical)
    return result


def _snapshot_vehicles_for_manager(db: Session, row: dict) -> list[str]:
    """PC 스냅샷의 차량 기본정보에서 담당자/주 운전자 기준 차량을 보강한다."""
    root = _snapshot_root(db)
    vehicles = root.get("vehicles")
    if not isinstance(vehicles, list):
        return []

    account_names = {
        _scope_text(row.get("employee_name")),
        _scope_text(row.get("name")),
        _scope_text(row.get("display_name")),
        _scope_text(row.get("manager_name")),
        _snapshot_account_login_id(row),
    }
    account_keys = {name.casefold() for name in account_names if name}
    if not account_keys:
        return []

    result: list[str] = []
    person_keys = (
        "main_driver",
        "driver",
        "driver_name",
        "vehicle_manager",
        "manager",
        "manager_name",
        "assigned_manager",
        "assigned_person",
        "charge_person",
        "person_in_charge",
    )
    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            continue
        matched = False
        for key in person_keys:
            value = _scope_text(vehicle.get(key))
            if value and value.casefold() in account_keys:
                matched = True
                break
        if not matched:
            continue
        value = _vehicle_primary_label_from_snapshot(vehicle)
        if value and value not in result:
            result.append(value)
    return result


def _sync_snapshot_assignments(db: Session, admin: AdminUser, row: dict) -> None:
    for assignment in db.execute(
        select(AdminSiteAssignment).where(AdminSiteAssignment.admin_id == admin.id)
    ).scalars().all():
        db.delete(assignment)
    for assignment in db.execute(
        select(AdminVehicleAssignment).where(AdminVehicleAssignment.admin_id == admin.id)
    ).scalars().all():
        db.delete(assignment)

    if admin.role == ROLE_SUPER:
        return

    assignments = row.get("assignments") if isinstance(row.get("assignments"), dict) else {}
    businesses = _scope_list(
        row.get("businesses"),
        row.get("allowedBusinesses"),
        row.get("allowed_businesses"),
        row.get("business_names"),
        assignments.get("businesses"),
        prefer="business",
    )
    sites = _scope_list(
        row.get("sites"),
        row.get("allowedSites"),
        row.get("allowed_sites"),
        row.get("work_sites"),
        row.get("workSites"),
        assignments.get("work_sites"),
        assignments.get("sites"),
        prefer="site",
    )
    vehicles = _scope_list(
        row.get("cars"),
        row.get("vehicles"),
        row.get("allowedVehicles"),
        row.get("allowed_vehicles"),
        row.get("vehicle_no"),
        row.get("vehicle_nos"),
        assignments.get("vehicles"),
        prefer="vehicle",
    )
    vehicles = _scope_list(vehicles, _snapshot_vehicles_for_manager(db, row), prefer="vehicle")
    vehicles = _canonical_vehicle_assignments(db, vehicles)

    if sites:
        for site in sites:
            if businesses:
                for business in businesses:
                    db.add(AdminSiteAssignment(admin_id=admin.id, business_name=business, work_site=site))
            else:
                db.add(AdminSiteAssignment(admin_id=admin.id, business_name="", work_site=site))
    elif businesses:
        for business in businesses:
            db.add(AdminSiteAssignment(admin_id=admin.id, business_name=business, work_site=""))

    for vehicle in vehicles:
        db.add(AdminVehicleAssignment(admin_id=admin.id, vehicle_no=vehicle))


def _upsert_snapshot_manager_admin(db: Session, username: str, password: str, row: dict) -> AdminUser:
    account_id = _snapshot_account_login_id(row) or username
    admin = db.execute(select(AdminUser).where(AdminUser.username == account_id)).scalar_one_or_none()
    if admin is None:
        admin = AdminUser(
            username=account_id,
            password_hash=_hash_password(password),
            display_name=_snapshot_account_name(row, account_id),
            role=ROLE_SUPER if _snapshot_account_is_super(row) else ROLE_MANAGER,
            is_active=1,
        )
        db.add(admin)
        db.flush()
    else:
        if password:
            admin.password_hash = _hash_password(password)
        admin.display_name = _snapshot_account_name(row, account_id)
        admin.role = ROLE_SUPER if _snapshot_account_is_super(row) else ROLE_MANAGER
        admin.is_active = 1

    _sync_snapshot_assignments(db, admin, row)
    db.commit()
    db.refresh(admin)
    return admin


def _login_from_snapshot_manager(db: Session, username: str, password: str) -> AdminUser | None:
    row = _find_snapshot_manager_row(db, username)
    if row is None:
        return None
    saved_password = _snapshot_account_password(row)
    if saved_password != password:
        return None
    return _upsert_snapshot_manager_admin(db, username, password, row)



@router.get("/server-time")
def server_time() -> dict:
    return _server_time_payload()


@router.post("/auth/login")
@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    _seed_default_admins(db)

    username = (payload.username or payload.user_id or payload.userId or payload.login_id or "").strip()
    password = (payload.password or "").strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="아이디와 비밀번호를 입력하세요.")

    # PC 스냅샷 관리자 계정이 있으면 서버에 남아 있는 예전 기본 manager 계정보다
    # PC의 최신 비밀번호/담당범위를 우선한다.
    snapshot_row = _find_snapshot_manager_row(db, username)
    if snapshot_row is not None:
        saved_password = _snapshot_account_password(snapshot_row)
        if saved_password and saved_password != password:
            raise HTTPException(status_code=401, detail="아이디 또는 비밀번호를 확인하세요.")
        if saved_password:
            admin = _upsert_snapshot_manager_admin(db, username, password, snapshot_row)
        else:
            admin = db.execute(select(AdminUser).where(AdminUser.username == username)).scalar_one_or_none()
            if not admin or not _verify_password(password, admin.password_hash):
                raise HTTPException(status_code=401, detail="아이디 또는 비밀번호를 확인하세요.")
            _sync_snapshot_assignments(db, admin, snapshot_row)
            db.commit()
            db.refresh(admin)
    else:
        admin = db.execute(select(AdminUser).where(AdminUser.username == username)).scalar_one_or_none()
        if not admin or not _verify_password(password, admin.password_hash):
            raise HTTPException(status_code=401, detail="아이디 또는 비밀번호를 확인하세요.")

    if admin.is_active != 1:
        raise HTTPException(status_code=403, detail="사용이 중지된 계정입니다.")

    token = _issue_token(db, admin)
    return _admin_payload(db, admin, token)


@router.get("/auth/me")
@router.get("/me")
def me(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
) -> dict:
    token = _get_token_from_header(authorization, x_auth_token)
    admin = _load_admin_by_token(db, token)
    return _admin_payload(db, admin)


@router.post("/auth/logout")
def logout(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
) -> dict:
    token = _get_token_from_header(authorization, x_auth_token)
    if token:
        row = db.execute(select(AdminToken).where(AdminToken.token == token)).scalar_one_or_none()
        if row:
            row.is_active = 0
            db.commit()
    return {"success": True, "message": "로그아웃되었습니다."}
