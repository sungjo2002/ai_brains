from __future__ import annotations

from datetime import date, datetime
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AttendanceMonthLock
from ..permission_guard import ensure_pc_or_super, require_permission_context

router = APIRouter(prefix="/api/attendance", tags=["attendance-month-lock"])

YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class MonthLockRequest(BaseModel):
    year_month: str
    locked_by: str | None = None
    source: str | None = "pc"
    note: str | None = None


class MonthUnlockRequest(BaseModel):
    year_month: str
    unlocked_by: str | None = None
    source: str | None = "pc"
    note: str | None = None


def _now() -> datetime:
    return datetime.now()


def _validate_year_month(year_month: str) -> str:
    value = (year_month or "").strip()
    if not YEAR_MONTH_RE.match(value):
        raise HTTPException(status_code=400, detail="year_month 값은 YYYY-MM 형식이어야 합니다.")
    year, month = value.split("-")
    month_int = int(month)
    if month_int < 1 or month_int > 12:
        raise HTTPException(status_code=400, detail="월은 01부터 12 사이여야 합니다.")
    return value


def _editable_until(year_month: str) -> date:
    year, month = [int(x) for x in year_month.split("-")]
    if month == 12:
        return date(year + 1, 1, 10)
    return date(year, month + 1, 10)


def _load_lock(db: Session, year_month: str) -> AttendanceMonthLock | None:
    return db.execute(
        select(AttendanceMonthLock).where(AttendanceMonthLock.year_month == year_month)
    ).scalar_one_or_none()


def _permission_context(
    db: Session,
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


def _status_payload(db: Session, year_month: str) -> dict:
    ym = _validate_year_month(year_month)
    row = _load_lock(db, ym)
    now = _now()
    today = now.date()
    editable_until = _editable_until(ym)

    locked = bool(row and row.locked == 1)
    expired = today > editable_until
    editable = (not locked) and (not expired)

    if locked:
        message = "이 월은 PC에서 마감되어 수정할 수 없습니다."
        reason = "pc_locked"
    elif expired:
        message = "해당 월 근태 수정 가능 기간이 지났습니다."
        reason = "edit_period_expired"
    else:
        message = "수정 가능"
        reason = "editable"

    return {
        "status": "ok",
        "year_month": ym,
        "locked": locked,
        "editable": editable,
        "expired": expired,
        "reason": reason,
        "message": message,
        "editable_until": editable_until.strftime("%Y-%m-%d"),
        "server_date": today.strftime("%Y-%m-%d"),
        "server_time": now.strftime("%H:%M:%S"),
        "server_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "server_ym": now.strftime("%Y-%m"),
        "lock": None if not row else {
            "locked": bool(row.locked == 1),
            "source": row.source,
            "locked_by": row.locked_by,
            "locked_at": row.locked_at.strftime("%Y-%m-%d %H:%M:%S") if row.locked_at else None,
            "unlocked_by": row.unlocked_by,
            "unlocked_at": row.unlocked_at.strftime("%Y-%m-%d %H:%M:%S") if row.unlocked_at else None,
            "note": row.note,
        },
    }


@router.get("/month-lock-status")
def get_month_lock_status(
    year_month: str = Query(..., description="조회 월. 예: 2026-05"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
) -> dict:
    _permission_context(db, authorization, x_auth_token, x_pc_sync_key)
    return _status_payload(db, year_month)


@router.post("/month-lock-status")
def post_month_lock_status(
    payload: MonthLockRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
) -> dict:
    _permission_context(db, authorization, x_auth_token, x_pc_sync_key)
    return _status_payload(db, payload.year_month)


@router.post("/month-lock")
def lock_month(
    payload: MonthLockRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
) -> dict:
    context = _permission_context(db, authorization, x_auth_token, x_pc_sync_key)
    ensure_pc_or_super(context)
    ym = _validate_year_month(payload.year_month)
    row = _load_lock(db, ym)
    now = _now()

    if row is None:
        row = AttendanceMonthLock(
            year_month=ym,
            locked=1,
            source=(payload.source or "pc"),
            locked_by=(payload.locked_by or ""),
            locked_at=now,
            unlocked_by="",
            unlocked_at=None,
            note=(payload.note or ""),
        )
        db.add(row)
    else:
        row.locked = 1
        row.source = payload.source or row.source or "pc"
        row.locked_by = payload.locked_by or row.locked_by or ""
        row.locked_at = now
        row.unlocked_by = ""
        row.unlocked_at = None
        if payload.note is not None:
            row.note = payload.note

    db.commit()
    return _status_payload(db, ym)


@router.post("/month-unlock")
def unlock_month(
    payload: MonthUnlockRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    x_pc_sync_key: str | None = Header(default=None, alias="X-PC-Sync-Key"),
) -> dict:
    context = _permission_context(db, authorization, x_auth_token, x_pc_sync_key)
    ensure_pc_or_super(context)
    ym = _validate_year_month(payload.year_month)
    row = _load_lock(db, ym)
    now = _now()

    if row is None:
        row = AttendanceMonthLock(
            year_month=ym,
            locked=0,
            source=(payload.source or "pc"),
            locked_by="",
            locked_at=None,
            unlocked_by=(payload.unlocked_by or ""),
            unlocked_at=now,
            note=(payload.note or ""),
        )
        db.add(row)
    else:
        row.locked = 0
        row.source = payload.source or row.source or "pc"
        row.unlocked_by = payload.unlocked_by or row.unlocked_by or ""
        row.unlocked_at = now
        if payload.note is not None:
            row.note = payload.note

    db.commit()
    return _status_payload(db, ym)
