from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Employee(Base):
    __tablename__ = "employees_api"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    nation: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    affiliated_business: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    work_site: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    work_type: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    pay_type: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    hire_date: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)




class EmployeeDeletedMarker(Base):
    __tablename__ = "employee_deleted_markers_api"

    employee_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(30), default="pc", nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

class AppSnapshot(Base):
    __tablename__ = "app_snapshots"

    snapshot_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), default="{}", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


# === mobile login api models start ===
class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="manager", nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class AdminSiteAssignment(Base):
    __tablename__ = "admin_site_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    business_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    work_site: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class AdminVehicleAssignment(Base):
    __tablename__ = "admin_vehicle_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    vehicle_no: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class AdminToken(Base):
    __tablename__ = "admin_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    admin_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
# === mobile login api models end ===


# === attendance month lock api models start ===
class AttendanceMonthLock(Base):
    __tablename__ = "attendance_month_locks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year_month: Mapped[str] = mapped_column(String(7), unique=True, index=True, nullable=False)
    locked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="pc", nullable=False)
    locked_by: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    unlocked_by: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
# === attendance month lock api models end ===


# === attendance save api models start ===
class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worker_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    worker_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    business: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    site: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    work_type: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    attendance_date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    year_month: Mapped[str] = mapped_column(String(7), index=True, nullable=False)
    state: Mapped[str] = mapped_column(String(50), default="empty", nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="mobile", nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    note: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
# === attendance save api models end ===



# === vehicle mobile log api models start ===
class VehicleRunLog(Base):
    __tablename__ = "vehicle_run_logs_api"

    log_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    car: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    business: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    site: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    log_date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    driver_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    end_odometer: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    round_trips: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="mobile", nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class VehicleFuelLog(Base):
    __tablename__ = "vehicle_fuel_logs_api"

    fuel_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    car: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    business: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    site: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    fuel_date: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="mobile", nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class VehicleCostLog(Base):
    __tablename__ = "vehicle_cost_logs_api"

    cost_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    car: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    business: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    site: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    cost_date: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="기타", nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="mobile", nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
# === vehicle mobile log api models end ===


# === vehicle detail log delete marker api models start ===
class VehicleDeletedLog(Base):
    __tablename__ = "vehicle_deleted_logs_api"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    log_type: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    log_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="pc", nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
# === vehicle detail log delete marker api models end ===
