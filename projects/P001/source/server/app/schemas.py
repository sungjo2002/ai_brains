from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EmployeeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    nation: str = Field(default="", max_length=50)
    affiliated_business: str = Field(default="", max_length=100)
    work_site: str = Field(default="", max_length=100)
    work_type: str = Field(default="", max_length=50)
    pay_type: str = Field(default="", max_length=50)
    status: str = Field(default="", max_length=30)
    phone: str = Field(default="", max_length=50)
    hire_date: str = Field(default="", max_length=20)
    note: str = Field(default="", max_length=2000)


class EmployeeCreate(EmployeeBase):
    id: int | None = Field(default=None, ge=1)


class EmployeeUpdate(BaseModel):
    id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    nation: str | None = Field(default=None, max_length=50)
    affiliated_business: str | None = Field(default=None, max_length=100)
    work_site: str | None = Field(default=None, max_length=100)
    work_type: str | None = Field(default=None, max_length=50)
    pay_type: str | None = Field(default=None, max_length=50)
    status: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=50)
    hire_date: str | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=2000)


class EmployeeOut(EmployeeBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AppSnapshotIn(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class AppSnapshotOut(BaseModel):
    snapshot_key: str = "main"
    payload: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None
