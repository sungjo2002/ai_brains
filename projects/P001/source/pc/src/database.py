from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from .app_metadata import get_default_data_root, get_program_root


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return deepcopy(default)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return deepcopy(default)




DB_SECTION_DEPENDENCIES = {
    "core_people": {"records", "payroll"},
}

DB_SECTION_SNAPSHOT_KEYS = {
    "core_people": ("businesses", "work_sites", "employees", "manager_accounts"),
    "attendance": ("attendance_events",),
    "records": ("monthly_records",),
    "payroll": (
        "payroll_site_settings",
        "payroll_setting_presets",
        "payroll_detail_items",
        "payroll_item_presets",
        "payroll_month_inputs",
        "payroll_adjustments",
        "attendance_month_locks",
    ),
    "vehicles": ("vehicles", "vehicle_run_logs", "vehicle_fuel_logs", "vehicle_cost_logs", "vehicle_alert_settings"),
    "settings": ("score_settings", "rejoin_grades"),
}

DB_SECTION_TABLES = {
    "core_people": ("work_sites", "employees", "businesses"),
    "attendance": ("attendance_events",),
    "records": ("attendance_daily_records",),
    "payroll": ("payroll_site_settings", "payroll_site_items", "payroll_cell_colors", "payroll_month_inputs", "payroll_adjustments"),
    "vehicles": ("vehicle_assignments", "vehicle_run_logs", "vehicle_fuel_logs", "vehicle_cost_logs", "vehicles", "vehicle_alert_settings"),
}

DB_SECTION_SETTING_KEYS = {
    "core_people": ("manager_accounts",),
    "payroll": ("payroll_setting_presets", "payroll_item_presets", "attendance_month_locks"),
    "settings": ("score_settings", "rejoin_grades"),
}

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS app_meta (
    meta_key TEXT PRIMARY KEY,
    meta_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS businesses (
    business_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    business_number TEXT DEFAULT '',
    representative_name TEXT DEFAULT '',
    manager_name TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    email TEXT DEFAULT '',
    address TEXT DEFAULT '',
    opening_date TEXT DEFAULT '',
    business_type TEXT DEFAULT '',
    business_item TEXT DEFAULT '',
    issue_date TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    note TEXT DEFAULT '',
    certificate_path TEXT DEFAULT '',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_sites (
    work_site_id TEXT PRIMARY KEY,
    business_id TEXT,
    business_name TEXT NOT NULL,
    name TEXT NOT NULL,
    address TEXT DEFAULT '',
    manager_name TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    note TEXT DEFAULT '',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(business_name, name),
    FOREIGN KEY (business_id) REFERENCES businesses(business_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    nation TEXT DEFAULT '',
    affiliated_business TEXT DEFAULT '',
    company TEXT DEFAULT '',
    work_site TEXT DEFAULT '',
    department TEXT DEFAULT '',
    work_type TEXT DEFAULT '',
    pay_type TEXT DEFAULT '',
    status TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    attendance_score INTEGER NOT NULL DEFAULT 0,
    rejoin_grade TEXT DEFAULT '',
    hire_date TEXT DEFAULT '',
    note TEXT DEFAULT '',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attendance_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date TEXT NOT NULL,
    employee_id INTEGER,
    employee_name TEXT DEFAULT '',
    event_type TEXT DEFAULT '',
    business_name TEXT DEFAULT '',
    work_site_name TEXT DEFAULT '',
    impact TEXT DEFAULT '',
    process_status TEXT DEFAULT '',
    memo TEXT DEFAULT '',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attendance_daily_records (
    employee_id INTEGER NOT NULL,
    record_date TEXT NOT NULL,
    status TEXT DEFAULT '',
    base_hours REAL NOT NULL DEFAULT 0,
    over_hours REAL NOT NULL DEFAULT 0,
    night_hours REAL NOT NULL DEFAULT 0,
    memo TEXT DEFAULT '',
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (employee_id, record_date),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS payroll_site_settings (
    site_key TEXT PRIMARY KEY,
    business_name TEXT DEFAULT '',
    work_site_name TEXT DEFAULT '',
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payroll_site_items (
    site_key TEXT NOT NULL,
    item_key TEXT NOT NULL,
    item_order INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (site_key, item_key)
);

CREATE TABLE IF NOT EXISTS payroll_month_inputs (
    employee_id INTEGER NOT NULL,
    month_key TEXT NOT NULL,
    day_no INTEGER NOT NULL,
    base_hours REAL NOT NULL DEFAULT 0,
    over_hours REAL NOT NULL DEFAULT 0,
    night_hours REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (employee_id, month_key, day_no),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS payroll_cell_colors (
    employee_id INTEGER NOT NULL,
    month_key TEXT NOT NULL,
    category_key TEXT NOT NULL,
    day_no INTEGER NOT NULL,
    color_hex TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (employee_id, month_key, category_key, day_no),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS payroll_adjustments (
    employee_id INTEGER NOT NULL,
    month_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (employee_id, month_key),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id TEXT PRIMARY KEY,
    vehicle_type TEXT NOT NULL,
    vehicle_name TEXT NOT NULL,
    plate_number TEXT DEFAULT '',
    car_model TEXT DEFAULT '',
    business_name TEXT DEFAULT '',
    work_site_name TEXT DEFAULT '',
    main_driver TEXT DEFAULT '',
    status TEXT DEFAULT '',
    rental_company TEXT DEFAULT '',
    contract_start TEXT DEFAULT '',
    contract_end TEXT DEFAULT '',
    annual_limit_km INTEGER NOT NULL DEFAULT 0,
    contract_total_limit_km INTEGER NOT NULL DEFAULT 0,
    unlimited INTEGER NOT NULL DEFAULT 0,
    baseline_odometer INTEGER NOT NULL DEFAULT 0,
    note TEXT DEFAULT '',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vehicle_assignments (
    assignment_id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    business_name TEXT DEFAULT '',
    work_site_name TEXT DEFAULT '',
    main_driver TEXT DEFAULT '',
    start_date TEXT DEFAULT '',
    end_date TEXT DEFAULT '',
    status TEXT DEFAULT '',
    note TEXT DEFAULT '',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vehicle_run_logs (
    log_id TEXT PRIMARY KEY,
    log_date TEXT NOT NULL,
    vehicle_id TEXT NOT NULL,
    driver_name TEXT DEFAULT '',
    end_odometer INTEGER NOT NULL DEFAULT 0,
    round_trips INTEGER NOT NULL DEFAULT 0,
    note TEXT DEFAULT '',
    source TEXT DEFAULT 'PC',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vehicle_fuel_logs (
    fuel_id TEXT PRIMARY KEY,
    fuel_date TEXT NOT NULL,
    vehicle_id TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    note TEXT DEFAULT '',
    source TEXT DEFAULT 'PC',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vehicle_cost_logs (
    cost_id TEXT PRIMARY KEY,
    cost_date TEXT NOT NULL,
    vehicle_id TEXT NOT NULL,
    category TEXT DEFAULT '',
    amount REAL NOT NULL DEFAULT 0,
    description TEXT DEFAULT '',
    note TEXT DEFAULT '',
    source TEXT DEFAULT 'PC수동',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vehicle_alert_settings (
    settings_id INTEGER PRIMARY KEY CHECK (settings_id = 1),
    remaining_km_threshold INTEGER NOT NULL DEFAULT 5000,
    contract_days_threshold INTEGER NOT NULL DEFAULT 30,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_files (
    document_id TEXT PRIMARY KEY,
    owner_type TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    document_type TEXT DEFAULT '',
    file_path TEXT NOT NULL,
    original_name TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class DatabaseManager:
    def __init__(
        self,
        root_dir: str | Path | None = None,
        db_name: str = "workforce.db",
        data_dir: str | Path | None = None,
        db_path: str | Path | None = None,
    ):
        self.root_dir = Path(root_dir).resolve() if root_dir is not None else get_program_root().resolve()
        if db_path is not None:
            self.db_path = Path(db_path).expanduser().resolve()
            self.db_dir = self.db_path.parent
            self.data_dir = Path(data_dir).expanduser().resolve() if data_dir is not None else self.db_dir.parent
        else:
            self.data_dir = (
                Path(data_dir).expanduser().resolve()
                if data_dir is not None
                else get_default_data_root(self.root_dir)
            )
            self.db_dir = self.data_dir / "db"
            self.db_path = self.db_dir / db_name
        self.legacy_db_path = self.root_dir / "data" / db_name

    def connect(self) -> sqlite3.Connection:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        if self.legacy_db_path.exists() and not self.db_path.exists():
            shutil.move(str(self.legacy_db_path), str(self.db_path))
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            self._migrate_existing_schema(conn)
            now = _utc_now_iso()
            conn.execute(
                """
                INSERT INTO app_meta (meta_key, meta_value, updated_at)
                VALUES ('schema_version', ?, ?)
                ON CONFLICT(meta_key) DO UPDATE SET
                    meta_value=excluded.meta_value,
                    updated_at=excluded.updated_at
                """,
                ("1", now),
            )

    def _migrate_existing_schema(self, conn: sqlite3.Connection) -> None:
        business_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(businesses)")}
        if "email" not in business_columns:
            conn.execute("ALTER TABLE businesses ADD COLUMN email TEXT DEFAULT ''")

    def has_seed_data(self) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM employees").fetchone()
            return bool(row and int(row["count"] or 0) > 0)

    def load_snapshot(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            employee_count = conn.execute("SELECT COUNT(*) AS count FROM employees").fetchone()
            has_any = bool(employee_count and int(employee_count["count"] or 0) > 0)
            if not has_any:
                vehicle_count = conn.execute("SELECT COUNT(*) AS count FROM vehicles").fetchone()
                has_any = bool(vehicle_count and int(vehicle_count["count"] or 0) > 0)
            if not has_any:
                business_count = conn.execute("SELECT COUNT(*) AS count FROM businesses").fetchone()
                has_any = bool(business_count and int(business_count["count"] or 0) > 0)
            if not has_any:
                work_site_count = conn.execute("SELECT COUNT(*) AS count FROM work_sites").fetchone()
                has_any = bool(work_site_count and int(work_site_count["count"] or 0) > 0)
            if not has_any:
                return None

            businesses = [
                _json_loads(row["payload_json"], {})
                for row in conn.execute("SELECT payload_json FROM businesses ORDER BY name")
            ]
            work_sites = [
                _json_loads(row["payload_json"], {})
                for row in conn.execute("SELECT payload_json FROM work_sites ORDER BY business_name, name")
            ]
            employees = [
                _json_loads(row["payload_json"], {})
                for row in conn.execute("SELECT payload_json FROM employees ORDER BY employee_id")
            ]
            attendance_events = [
                _json_loads(row["payload_json"], {})
                for row in conn.execute("SELECT payload_json FROM attendance_events ORDER BY event_date, event_id")
            ]
            vehicles = [
                _json_loads(row["payload_json"], {})
                for row in conn.execute("SELECT payload_json FROM vehicles ORDER BY vehicle_name, vehicle_id")
            ]
            vehicle_run_logs = [
                _json_loads(row["payload_json"], {})
                for row in conn.execute("SELECT payload_json FROM vehicle_run_logs ORDER BY log_date, log_id")
            ]
            vehicle_fuel_logs = [
                _json_loads(row["payload_json"], {})
                for row in conn.execute("SELECT payload_json FROM vehicle_fuel_logs ORDER BY fuel_date, fuel_id")
            ]
            vehicle_cost_logs = [
                _json_loads(row["payload_json"], {})
                for row in conn.execute("SELECT payload_json FROM vehicle_cost_logs ORDER BY cost_date, cost_id")
            ]

            score_settings = self._load_setting(conn, "score_settings", {})
            rejoin_grades = self._load_setting(conn, "rejoin_grades", [])
            manager_accounts = self._load_setting(conn, "manager_accounts", [])
            vehicle_alert_settings = self._load_vehicle_alert_settings(conn)
            monthly_records = self._load_monthly_records(conn)
            payroll_site_settings = self._load_payroll_site_settings(conn)
            payroll_detail_items = self._load_payroll_site_items(conn)
            payroll_month_inputs = self._load_payroll_month_inputs(conn)
            payroll_adjustments = self._load_payroll_adjustments(conn)
            payroll_setting_presets = self._load_setting(conn, "payroll_setting_presets", {})
            payroll_item_presets = self._load_setting(conn, "payroll_item_presets", {})
            attendance_month_locks = self._load_setting(conn, "attendance_month_locks", {})

            return {
                "businesses": businesses,
                "work_sites": work_sites,
                "employees": employees,
                "manager_accounts": manager_accounts,
                "attendance_events": attendance_events,
                "vehicles": vehicles,
                "vehicle_run_logs": vehicle_run_logs,
                "vehicle_fuel_logs": vehicle_fuel_logs,
                "vehicle_cost_logs": vehicle_cost_logs,
                "score_settings": score_settings,
                "rejoin_grades": rejoin_grades,
                "monthly_records": monthly_records,
                "payroll_site_settings": payroll_site_settings,
                "payroll_detail_items": payroll_detail_items,
                "payroll_month_inputs": payroll_month_inputs,
                "payroll_adjustments": payroll_adjustments,
                "payroll_setting_presets": payroll_setting_presets,
                "payroll_item_presets": payroll_item_presets,
                "attendance_month_locks": attendance_month_locks,
                "vehicle_alert_settings": vehicle_alert_settings,
            }

    def save_snapshot(self, snapshot: dict[str, Any], sections: set[str] | None = None) -> None:
        now = _utc_now_iso()
        normalized_sections = self._normalize_sections(sections)
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            with conn:
                self._clear_snapshot_sections(conn, normalized_sections)
                self._save_snapshot_sections(conn, snapshot, now, normalized_sections)
                conn.execute(
                    """
                    INSERT INTO app_meta (meta_key, meta_value, updated_at)
                    VALUES ('last_snapshot_at', ?, ?)
                    ON CONFLICT(meta_key) DO UPDATE SET
                        meta_value=excluded.meta_value,
                        updated_at=excluded.updated_at
                    """,
                    (now, now),
                )

    def _normalize_sections(self, sections: set[str] | None) -> set[str]:
        if not sections:
            return set(DB_SECTION_SNAPSHOT_KEYS.keys())
        normalized = {str(section or "").strip() for section in sections if str(section or "").strip()}
        expanded = set(normalized)
        stack = list(normalized)
        while stack:
            section = stack.pop()
            for dependency in DB_SECTION_DEPENDENCIES.get(section, set()):
                if dependency not in expanded:
                    expanded.add(dependency)
                    stack.append(dependency)
        return expanded or set(DB_SECTION_SNAPSHOT_KEYS.keys())

    def _clear_snapshot_sections(self, conn: sqlite3.Connection, sections: set[str]) -> None:
        seen_tables: set[str] = set()
        for section in sections:
            for table in DB_SECTION_TABLES.get(section, ()):
                if table in seen_tables:
                    continue
                conn.execute(f"DELETE FROM {table}")
                seen_tables.add(table)
        setting_keys: list[str] = []
        for section in sections:
            setting_keys.extend(DB_SECTION_SETTING_KEYS.get(section, ()))
        if setting_keys:
            placeholders = ",".join("?" for _ in setting_keys)
            conn.execute(f"DELETE FROM app_settings WHERE setting_key IN ({placeholders})", tuple(setting_keys))

    def _save_snapshot_sections(self, conn: sqlite3.Connection, snapshot: dict[str, Any], now: str, sections: set[str]) -> None:
        if "settings" in sections:
            self._save_setting(conn, "score_settings", snapshot.get("score_settings", {}), now)
            self._save_setting(conn, "rejoin_grades", snapshot.get("rejoin_grades", []), now)
        if "core_people" in sections:
            self._save_businesses(conn, snapshot.get("businesses", []), now)
            self._save_work_sites(conn, snapshot.get("work_sites", []), now)
            self._save_employees(conn, snapshot.get("employees", []), now)
            self._save_setting(conn, "manager_accounts", snapshot.get("manager_accounts", []), now)
        if "attendance" in sections:
            self._save_attendance_events(conn, snapshot.get("attendance_events", []), now)
        if "records" in sections:
            self._save_monthly_records(conn, snapshot.get("monthly_records", {}), now)
        if "payroll" in sections:
            self._save_payroll_site_settings(conn, snapshot.get("payroll_site_settings", {}), now)
            self._save_payroll_site_items(conn, snapshot.get("payroll_detail_items", {}), now)
            self._save_payroll_month_inputs(conn, snapshot.get("payroll_month_inputs", {}), now)
            self._save_payroll_adjustments(conn, snapshot.get("payroll_adjustments", {}), now)
            self._save_setting(conn, "payroll_setting_presets", snapshot.get("payroll_setting_presets", {}), now)
            self._save_setting(conn, "payroll_item_presets", snapshot.get("payroll_item_presets", {}), now)
            self._save_setting(conn, "attendance_month_locks", snapshot.get("attendance_month_locks", {}), now)
        if "vehicles" in sections:
            self._save_vehicles(conn, snapshot.get("vehicles", []), now)
            self._save_vehicle_run_logs(conn, snapshot.get("vehicle_run_logs", []), now)
            self._save_vehicle_fuel_logs(conn, snapshot.get("vehicle_fuel_logs", []), now)
            self._save_vehicle_cost_logs(conn, snapshot.get("vehicle_cost_logs", []), now)
            self._save_vehicle_alert_settings(conn, snapshot.get("vehicle_alert_settings", {}), now)

    def _save_setting(self, conn: sqlite3.Connection, key: str, value: Any, now: str) -> None:
        conn.execute(
            """
            INSERT INTO app_settings (setting_key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
                value_json=excluded.value_json,
                updated_at=excluded.updated_at
            """,
            (key, _json_dumps(value), now),
        )

    def _load_setting(self, conn: sqlite3.Connection, key: str, default: Any) -> Any:
        row = conn.execute(
            "SELECT value_json FROM app_settings WHERE setting_key = ?",
            (key,),
        ).fetchone()
        if not row:
            return deepcopy(default)
        return _json_loads(row["value_json"], default)

    def _save_businesses(self, conn: sqlite3.Connection, rows: list[dict], now: str) -> None:
        for row in rows:
            payload = deepcopy(row)
            conn.execute(
                """
                INSERT INTO businesses (
                    business_id, name, business_number, representative_name, manager_name,
                    phone, email, address, opening_date, business_type, business_item,
                    issue_date, active, note, certificate_path, payload_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.get("business_id", "") or ""),
                    str(payload.get("name", "") or ""),
                    str(payload.get("business_number", "") or ""),
                    str(payload.get("representative_name", "") or ""),
                    str(payload.get("manager_name", "") or ""),
                    str(payload.get("phone", "") or ""),
                    str(payload.get("email", "") or ""),
                    str(payload.get("address", "") or ""),
                    str(payload.get("opening_date", "") or ""),
                    str(payload.get("business_type", "") or ""),
                    str(payload.get("business_item", "") or ""),
                    str(payload.get("issue_date", "") or ""),
                    1 if payload.get("active", True) else 0,
                    str(payload.get("note", "") or ""),
                    str(payload.get("certificate_path", "") or ""),
                    _json_dumps(payload),
                    now,
                    now,
                ),
            )

    def _save_work_sites(self, conn: sqlite3.Connection, rows: list[dict], now: str) -> None:
        for row in rows:
            payload = deepcopy(row)
            conn.execute(
                """
                INSERT INTO work_sites (
                    work_site_id, business_id, business_name, name, address,
                    manager_name, phone, active, note, payload_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.get("work_site_id", "") or ""),
                    str(payload.get("parent_business_id", "") or "") or None,
                    str(payload.get("business_name", "") or ""),
                    str(payload.get("name", "") or ""),
                    str(payload.get("address", "") or ""),
                    str(payload.get("manager_name", "") or ""),
                    str(payload.get("phone", "") or ""),
                    1 if payload.get("active", True) else 0,
                    str(payload.get("note", "") or ""),
                    _json_dumps(payload),
                    now,
                    now,
                ),
            )

    def _save_employees(self, conn: sqlite3.Connection, rows: list[dict], now: str) -> None:
        for row in rows:
            payload = deepcopy(row)
            conn.execute(
                """
                INSERT INTO employees (
                    employee_id, name, nation, affiliated_business, company,
                    work_site, department, work_type, pay_type, status,
                    active, attendance_score, rejoin_grade, hire_date, note,
                    payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(payload.get("id", 0) or 0),
                    str(payload.get("name", "") or ""),
                    str(payload.get("nation", "") or ""),
                    str(payload.get("affiliated_business", "") or ""),
                    str(payload.get("company", "") or ""),
                    str(payload.get("work_site", "") or ""),
                    str(payload.get("department", "") or ""),
                    str(payload.get("work_type", "") or ""),
                    str(payload.get("pay_type", "") or ""),
                    str(payload.get("status", "") or ""),
                    1 if payload.get("active", True) else 0,
                    int(payload.get("attendance_score", 0) or 0),
                    str(payload.get("rejoin_grade", "") or ""),
                    str(payload.get("hire_date", "") or ""),
                    str(payload.get("note", "") or ""),
                    _json_dumps(payload),
                    now,
                    now,
                ),
            )

    def _save_attendance_events(self, conn: sqlite3.Connection, rows: list[dict], now: str) -> None:
        for row in rows:
            payload = deepcopy(row)
            conn.execute(
                """
                INSERT INTO attendance_events (
                    event_date, employee_id, employee_name, event_type,
                    business_name, work_site_name, impact, process_status,
                    memo, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.get("date", "") or ""),
                    int(payload.get("employee_id", 0) or 0) or None,
                    str(payload.get("employee_name", "") or ""),
                    str(payload.get("event_type", "") or ""),
                    str(payload.get("business", "") or ""),
                    str(payload.get("work_site", "") or ""),
                    str(payload.get("impact", "") or ""),
                    str(payload.get("process_status", "") or ""),
                    str(payload.get("memo", "") or ""),
                    _json_dumps(payload),
                    now,
                    now,
                ),
            )

    def _save_monthly_records(self, conn: sqlite3.Connection, rows: dict[tuple[int, str], dict], now: str) -> None:
        for (employee_id, record_date), payload in rows.items():
            row = deepcopy(payload)
            conn.execute(
                """
                INSERT INTO attendance_daily_records (
                    employee_id, record_date, status, base_hours, over_hours,
                    night_hours, memo, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(employee_id),
                    str(record_date),
                    str(row.get("status", "") or ""),
                    float(row.get("base", 0) or 0),
                    float(row.get("over", 0) or 0),
                    float(row.get("night", 0) or 0),
                    str(row.get("memo", "") or ""),
                    _json_dumps(row),
                    now,
                ),
            )

    def _load_monthly_records(self, conn: sqlite3.Connection) -> dict[tuple[int, str], dict]:
        records: dict[tuple[int, str], dict] = {}
        for row in conn.execute(
            "SELECT employee_id, record_date, payload_json FROM attendance_daily_records"
        ):
            key = (int(row["employee_id"]), str(row["record_date"]))
            records[key] = _json_loads(row["payload_json"], {})
        return records

    def _save_payroll_site_settings(self, conn: sqlite3.Connection, rows: dict[str, dict], now: str) -> None:
        for site_key, payload in rows.items():
            business_name = ""
            work_site_name = str(site_key)
            if "::" in str(site_key):
                business_name, work_site_name = str(site_key).split("::", 1)
            conn.execute(
                """
                INSERT INTO payroll_site_settings (
                    site_key, business_name, work_site_name, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (str(site_key), business_name, work_site_name, _json_dumps(deepcopy(payload)), now),
            )

    def _load_payroll_site_settings(self, conn: sqlite3.Connection) -> dict[str, dict]:
        rows: dict[str, dict] = {}
        for row in conn.execute("SELECT site_key, payload_json FROM payroll_site_settings"):
            rows[str(row["site_key"])] = _json_loads(row["payload_json"], {})
        return rows

    def _save_payroll_site_items(self, conn: sqlite3.Connection, rows: dict[str, list[dict]], now: str) -> None:
        for site_key, items in rows.items():
            for order, payload in enumerate(items or [], start=1):
                item_key = str(payload.get("key", f"item_{order}") or f"item_{order}")
                conn.execute(
                    """
                    INSERT INTO payroll_site_items (
                        site_key, item_key, item_order, payload_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(site_key), item_key, int(payload.get("order", order) or order), _json_dumps(deepcopy(payload)), now),
                )

    def _load_payroll_site_items(self, conn: sqlite3.Connection) -> dict[str, list[dict]]:
        rows: dict[str, list[dict]] = {}
        for row in conn.execute(
            "SELECT site_key, payload_json FROM payroll_site_items ORDER BY site_key, item_order, item_key"
        ):
            rows.setdefault(str(row["site_key"]), []).append(_json_loads(row["payload_json"], {}))
        return rows

    def _save_payroll_month_inputs(self, conn: sqlite3.Connection, rows: dict[tuple[int, str], dict], now: str) -> None:
        for (employee_id, month_key), payload in rows.items():
            base_map = payload.get("base", {}) or {}
            over_map = payload.get("over", {}) or {}
            night_map = payload.get("night", {}) or {}
            color_map = payload.get("cell_colors", {}) or {}
            day_keys = set(base_map.keys()) | set(over_map.keys()) | set(night_map.keys())
            for day_key in sorted(day_keys, key=lambda item: int(item)):
                day_no = int(day_key)
                conn.execute(
                    """
                    INSERT INTO payroll_month_inputs (
                        employee_id, month_key, day_no, base_hours, over_hours, night_hours, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(employee_id),
                        str(month_key),
                        day_no,
                        float(base_map.get(day_no, base_map.get(str(day_no), 0)) or 0),
                        float(over_map.get(day_no, over_map.get(str(day_no), 0)) or 0),
                        float(night_map.get(day_no, night_map.get(str(day_no), 0)) or 0),
                        now,
                    ),
                )
            for category_key, category_colors in color_map.items():
                if category_key not in {"base", "over", "night"} or not isinstance(category_colors, dict):
                    continue
                for day_key, color_hex in category_colors.items():
                    try:
                        day_no = int(day_key)
                    except (TypeError, ValueError):
                        continue
                    color_text = str(color_hex or "").strip().upper()
                    if not re.match(r"^#[0-9A-F]{6}$", color_text):
                        continue
                    conn.execute(
                        """
                        INSERT INTO payroll_cell_colors (
                            employee_id, month_key, category_key, day_no, color_hex, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (int(employee_id), str(month_key), str(category_key), day_no, color_text, now),
                    )

    def _load_payroll_month_inputs(self, conn: sqlite3.Connection) -> dict[tuple[int, str], dict]:
        rows: dict[tuple[int, str], dict] = {}
        for row in conn.execute(
            "SELECT employee_id, month_key, day_no, base_hours, over_hours, night_hours FROM payroll_month_inputs"
        ):
            key = (int(row["employee_id"]), str(row["month_key"]))
            entry = rows.setdefault(key, {"base": {}, "over": {}, "night": {}, "cell_colors": {"base": {}, "over": {}, "night": {}}})
            day_no = int(row["day_no"])
            entry["base"][day_no] = float(row["base_hours"] or 0)
            entry["over"][day_no] = float(row["over_hours"] or 0)
            entry["night"][day_no] = float(row["night_hours"] or 0)
        try:
            color_rows = conn.execute(
                "SELECT employee_id, month_key, category_key, day_no, color_hex FROM payroll_cell_colors"
            )
        except sqlite3.OperationalError:
            color_rows = []
        for row in color_rows:
            key = (int(row["employee_id"]), str(row["month_key"]))
            entry = rows.setdefault(key, {"base": {}, "over": {}, "night": {}, "cell_colors": {"base": {}, "over": {}, "night": {}}})
            category_key = str(row["category_key"] or "")
            if category_key not in {"base", "over", "night"}:
                continue
            entry.setdefault("cell_colors", {"base": {}, "over": {}, "night": {}}).setdefault(category_key, {})[int(row["day_no"])] = str(row["color_hex"] or "").upper()
        return rows

    def _save_payroll_adjustments(self, conn: sqlite3.Connection, rows: dict[tuple[int, str], dict], now: str) -> None:
        for (employee_id, month_key), payload in rows.items():
            conn.execute(
                """
                INSERT INTO payroll_adjustments (
                    employee_id, month_key, payload_json, updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (int(employee_id), str(month_key), _json_dumps(deepcopy(payload)), now),
            )

    def _load_payroll_adjustments(self, conn: sqlite3.Connection) -> dict[tuple[int, str], dict]:
        rows: dict[tuple[int, str], dict] = {}
        for row in conn.execute("SELECT employee_id, month_key, payload_json FROM payroll_adjustments"):
            rows[(int(row["employee_id"]), str(row["month_key"]))] = _json_loads(row["payload_json"], {})
        return rows

    def _save_vehicles(self, conn: sqlite3.Connection, rows: list[dict], now: str) -> None:
        for payload in rows:
            row = deepcopy(payload)
            conn.execute(
                """
                INSERT INTO vehicles (
                    vehicle_id, vehicle_type, vehicle_name, plate_number, car_model,
                    business_name, work_site_name, main_driver, status, rental_company,
                    contract_start, contract_end, annual_limit_km, contract_total_limit_km,
                    unlimited, baseline_odometer, note, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(row.get("vehicle_id", "") or ""),
                    str(row.get("vehicle_type", "") or ""),
                    str(row.get("vehicle_name", "") or ""),
                    str(row.get("plate_number", "") or ""),
                    str(row.get("car_model", "") or ""),
                    str(row.get("business_name", "") or ""),
                    str(row.get("work_site_name", "") or ""),
                    str(row.get("main_driver", "") or ""),
                    str(row.get("status", "") or ""),
                    str(row.get("rental_company", "") or ""),
                    str(row.get("contract_start", "") or ""),
                    str(row.get("contract_end", "") or ""),
                    int(row.get("annual_limit_km", 0) or 0),
                    int(row.get("contract_total_limit_km", 0) or 0),
                    1 if row.get("unlimited", False) else 0,
                    int(row.get("baseline_odometer", 0) or 0),
                    str(row.get("note", "") or ""),
                    _json_dumps(row),
                    now,
                    now,
                ),
            )

    def _save_vehicle_run_logs(self, conn: sqlite3.Connection, rows: list[dict], now: str) -> None:
        for payload in rows:
            row = deepcopy(payload)
            conn.execute(
                """
                INSERT INTO vehicle_run_logs (
                    log_id, log_date, vehicle_id, driver_name, end_odometer,
                    round_trips, note, source, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(row.get("log_id", "") or ""),
                    str(row.get("date", "") or ""),
                    str(row.get("vehicle_id", "") or ""),
                    str(row.get("driver_name", "") or ""),
                    int(row.get("end_odometer", 0) or 0),
                    int(row.get("round_trips", 0) or 0),
                    str(row.get("note", "") or ""),
                    str(row.get("source", "PC") or "PC"),
                    _json_dumps(row),
                    now,
                    now,
                ),
            )

    def _save_vehicle_fuel_logs(self, conn: sqlite3.Connection, rows: list[dict], now: str) -> None:
        for payload in rows:
            row = deepcopy(payload)
            conn.execute(
                """
                INSERT INTO vehicle_fuel_logs (
                    fuel_id, fuel_date, vehicle_id, amount, note,
                    source, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(row.get("fuel_id", "") or ""),
                    str(row.get("fuel_date", "") or ""),
                    str(row.get("vehicle_id", "") or ""),
                    float(row.get("amount", 0) or 0),
                    str(row.get("note", "") or ""),
                    str(row.get("source", "PC") or "PC"),
                    _json_dumps(row),
                    now,
                    now,
                ),
            )

    def _save_vehicle_cost_logs(self, conn: sqlite3.Connection, rows: list[dict], now: str) -> None:
        for payload in rows:
            row = deepcopy(payload)
            conn.execute(
                """
                INSERT INTO vehicle_cost_logs (
                    cost_id, cost_date, vehicle_id, category, amount,
                    description, note, source, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(row.get("cost_id", "") or ""),
                    str(row.get("cost_date", "") or ""),
                    str(row.get("vehicle_id", "") or ""),
                    str(row.get("category", "") or ""),
                    float(row.get("amount", 0) or 0),
                    str(row.get("description", "") or ""),
                    str(row.get("note", "") or ""),
                    str(row.get("source", "PC수동") or "PC수동"),
                    _json_dumps(row),
                    now,
                    now,
                ),
            )

    def _save_vehicle_alert_settings(self, conn: sqlite3.Connection, payload: dict, now: str) -> None:
        row = deepcopy(payload or {})
        conn.execute(
            """
            INSERT INTO vehicle_alert_settings (
                settings_id, remaining_km_threshold, contract_days_threshold, updated_at
            ) VALUES (1, ?, ?, ?)
            ON CONFLICT(settings_id) DO UPDATE SET
                remaining_km_threshold=excluded.remaining_km_threshold,
                contract_days_threshold=excluded.contract_days_threshold,
                updated_at=excluded.updated_at
            """,
            (
                int(row.get("remaining_km_threshold", 5000) or 5000),
                int(row.get("contract_days_threshold", 30) or 30),
                now,
            ),
        )

    def _load_vehicle_alert_settings(self, conn: sqlite3.Connection) -> dict[str, int]:
        row = conn.execute(
            "SELECT remaining_km_threshold, contract_days_threshold FROM vehicle_alert_settings WHERE settings_id = 1"
        ).fetchone()
        if not row:
            return {"remaining_km_threshold": 5000, "contract_days_threshold": 30}
        return {
            "remaining_km_threshold": int(row["remaining_km_threshold"] or 5000),
            "contract_days_threshold": int(row["contract_days_threshold"] or 30),
        }
