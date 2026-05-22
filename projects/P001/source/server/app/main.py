from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import text

from .db import Base, engine
from .routes.employees import router as employees_router
from .routes.health import router as health_router
from .routes.mobile_auth import router as mobile_auth_router
from .routes.attendance_month_lock import router as attendance_month_lock_router
from .routes.attendance_records import router as attendance_records_router
from .routes.vehicles import router as vehicles_router

app = FastAPI(title="Green API", version="0.1.0")

Base.metadata.create_all(bind=engine)


def _ensure_app_snapshot_payload_capacity() -> None:
    """PC 전체 snapshot은 급여/차량/근태를 포함해 일반 TEXT(64KB)를 넘을 수 있습니다.

    MySQL 운영 DB에서 기존 app_snapshots.payload_json 컬럼을 LONGTEXT로 보정해
    PC1 → 서버 → PC2 전체 복구가 중간에 실패하지 않도록 합니다.
    """
    if engine.dialect.name not in {"mysql", "mariadb"}:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE app_snapshots MODIFY COLUMN payload_json LONGTEXT NOT NULL"))


_ensure_app_snapshot_payload_capacity()

app.include_router(health_router)
app.include_router(employees_router)
app.include_router(mobile_auth_router)
app.include_router(attendance_month_lock_router)
app.include_router(attendance_records_router)
app.include_router(vehicles_router)


@app.get("/")
def root():
    return {"message": "green api ready"}
