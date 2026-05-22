from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .app_metadata import (
    APP_SETTINGS_NAME,
    PROGRAM_VERSION,
    STORAGE_VERSION,
    DEFAULT_UPDATE_INFO_URL,
    DEFAULT_SERVER_API_BASE_URL,
    DEFAULT_SERVER_PC_SYNC_KEY,
    get_default_data_root,
    get_program_root,
)


def _utc_now_compact() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")


class StorageManager:
    def __init__(
        self,
        root_dir: str | Path | None = None,
        db_name: str = "workforce.db",
        data_root_dir: str | Path | None = None,
    ):
        self.root_dir = Path(root_dir).resolve() if root_dir is not None else get_program_root().resolve()
        self.data_dir = (
            Path(data_root_dir).expanduser().resolve()
            if data_root_dir is not None
            else get_default_data_root(self.root_dir)
        )

        self.legacy_data_dir = self.root_dir / "data"

        self.db_dir = self.data_dir / "db"
        self.db_path = self.db_dir / db_name
        self.legacy_db_path = self.legacy_data_dir / db_name

        self.files_dir = self.data_dir / "files"
        self.business_files_dir = self.files_dir / "businesses"
        self.employee_files_dir = self.files_dir / "employees"
        self.vehicle_files_dir = self.files_dir / "vehicles"

        # 예전 storage 구조는 프로그램 폴더가 아니라 실제 데이터 루트(WorkforceData) 안에서만 유지합니다.
        # 프로그램 폴더 안 data/storage는 읽기/마이그레이션 대상일 뿐, 새로 만들지 않습니다.
        self.program_legacy_storage_dir = self.legacy_data_dir / "storage"
        self.legacy_storage_dir = self.data_dir / "storage"
        self.legacy_employee_portraits_dir = self.legacy_storage_dir / "portraits"
        self.legacy_employee_documents_dir = self.legacy_storage_dir / "documents"

        self.config_dir = self.data_dir / "config"
        self.settings_dir = self.config_dir
        self.legacy_settings_dir = self.legacy_data_dir / "settings"
        self.app_settings_path = self.config_dir / "app_settings.json"
        self.update_settings_path = self.config_dir / "update_settings.json"
        self.server_api_settings_path = self.config_dir / "server_api.json"

        self.cache_dir = self.data_dir / "cache"
        self.export_dir = self.data_dir / "export"
        self.logs_dir = self.data_dir / "logs"
        self.temp_dir = self.data_dir / "temp"
        self.sample_dir = self.data_dir / "sample"
        self.sample_disabled_dir = self.sample_dir / "disabled"

        self.default_backup_root = self.data_dir / "backup"
        existing_app_settings = self._load_existing_app_settings()
        self._configure_backup_paths(existing_app_settings.get("backup_dir", ""))

        self.legacy_backup_root = self.root_dir / "BACKUP"
        self.legacy_logs_dir = self.root_dir / "logs"
        self.legacy_temp_dir = self.root_dir / "temp"

    def _load_existing_app_settings(self) -> dict[str, Any]:
        candidates = [
            self.app_settings_path,
            self.legacy_data_dir / "config" / "app_settings.json",
            self.legacy_data_dir / "settings" / "app_settings.json",
        ]
        for path in candidates:
            if not path.exists():
                continue
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
        return {}

    def _configure_backup_paths(self, backup_dir_value: str | Path | None) -> None:
        backup_root = self._resolve_backup_root(backup_dir_value)
        self.backup_root = backup_root
        self.backup_latest_dir = self.backup_root / "latest"
        self.backup_latest_zip_path = self.backup_latest_dir / "workforce_backup_latest.zip"
        # 예전 폴더형 백업과의 호환을 위해 경로 속성은 유지합니다.
        self.backup_latest_files_dir = self.backup_latest_dir / "files"
        self.backup_latest_storage_dir = self.backup_latest_dir / "storage"
        self.backup_latest_settings_dir = self.backup_latest_dir / "config"
        self.backup_history_dir = self.backup_root / "history"

    def _resolve_backup_root(self, backup_dir_value: str | Path | None) -> Path:
        raw_value = str(backup_dir_value or "").strip()
        if not raw_value:
            return self.default_backup_root

        path = Path(raw_value).expanduser()
        if path.is_absolute():
            return path.resolve()

        normalized = raw_value.replace("\\", "/").strip()
        # 예전 버전에서 저장된 data/backup 값은 프로그램 폴더가 아니라
        # 실제 사용자 데이터 루트인 WorkforceData 아래로 보정합니다.
        if normalized == "data" or normalized.startswith("data/"):
            suffix = normalized[5:] if normalized.startswith("data/") else ""
            return (self.data_dir / suffix).resolve()

        data_candidate = (self.data_dir / normalized).resolve()
        root_candidate = (self.root_dir / normalized).resolve()
        if root_candidate.exists() and not data_candidate.exists():
            return root_candidate
        return data_candidate

    def backup_setting_value(self) -> str:
        try:
            relative = self.backup_root.resolve().relative_to(self.data_dir.resolve())
            return relative.as_posix()
        except ValueError:
            try:
                relative = self.backup_root.resolve().relative_to(self.root_dir.resolve())
                return relative.as_posix()
            except ValueError:
                return str(self.backup_root)

    def set_backup_root(self, backup_dir_value: str | Path | None) -> Path:
        self._configure_backup_paths(backup_dir_value)
        self.ensure_structure()
        payload = self.load_app_settings(
            {
                "app_name": APP_SETTINGS_NAME,
                "storage_version": STORAGE_VERSION,
                "created_at": _utc_now_compact(),
                "last_backup_at": "",
            }
        )
        payload["backup_dir"] = self.backup_setting_value()
        self.save_app_settings(payload)
        return self.backup_root

    def ensure_structure(self) -> None:
        self._migrate_legacy_layout()

        for folder in [
            self.data_dir,
            self.db_dir,
            self.files_dir,
            self.business_files_dir,
            self.employee_files_dir,
            self.vehicle_files_dir,
            self.legacy_storage_dir,
            self.legacy_employee_portraits_dir,
            self.legacy_employee_documents_dir,
            self.config_dir,
            self.cache_dir,
            self.export_dir,
            self.logs_dir,
            self.temp_dir,
            self.sample_dir,
            self.sample_disabled_dir,
            self.backup_latest_dir,
            self.backup_history_dir,
        ]:
            folder.mkdir(parents=True, exist_ok=True)

        self._write_text_if_missing(
            self.data_dir / "README_DATA.txt",
            "현재 실제 사용 중인 데이터 폴더입니다.\n"
            "- db/workforce.db: 핵심 DB\n"
            "- files/: 실제 첨부/문서 저장 폴더\n"
            "- config/: 프로그램 설정\n"
            "- backup/: 최신/이력 백업\n"
            "- export/: 내보내기 파일\n"
            "- logs/: 실행 로그\n"
            "- temp/: 임시 작업 폴더\n"
            "- sample/: 수동 참고용 샘플(자동 불러오기 없음)\n"
            "- storage/: 예전 경로 호환용 폴더(신규 저장은 files 기준)\n",
        )
        self._write_text_if_missing(
            self.backup_root / "README_BACKUP.txt",
            "backup 폴더는 다른 PC로 옮겨 복구할 수 있는 백업 세트입니다.\n"
            "- latest/: 최신 복구본\n"
            "- history/: 날짜별 백업본\n",
        )
        self._write_text_if_missing(
            self.sample_dir / "README_SAMPLE.txt",
            "sample 폴더는 수동 참고용 샘플 전용입니다.\n"
            "프로그램 시작 시 자동으로 불러오지 않습니다.\n",
        )
        # 이 안내 파일은 실행 PC 계정에 따라 경로가 달라지므로 항상 최신 경로로 다시 씁니다.
        # 프로그램 폴더가 읽기 전용이어도 실행이 중단되지 않도록 실제 데이터 루트에 저장합니다.
        self._safe_write_text(
            self.data_dir / "DATA_FOLDER_INFO.txt",
            "이 프로그램의 실제 데이터 폴더는 프로그램 폴더 밖에 따로 저장됩니다.\n"
            "저장 루트 이름은 항상 WorkforceData로 통일합니다.\n"
            f"현재 데이터 폴더: {self.data_dir}\n"
            f"현재 DB 파일: {self.db_path}\n"
            f"기본 백업 폴더: {self.default_backup_root}\n",
        )
        if not self.app_settings_path.exists():
            self.save_app_settings(
                {
                    "app_name": APP_SETTINGS_NAME,
                    "storage_version": STORAGE_VERSION,
                    "created_at": _utc_now_compact(),
                    "last_backup_at": "",
                    "backup_dir": self.backup_setting_value(),
                }
            )

        if not self.update_settings_path.exists():
            self.save_update_settings(
                {
                    "enabled": False,
                    "auto_check_on_start": False,
                    "current_version": PROGRAM_VERSION,
                    "update_info_url": "",
                    "skip_version": "",
                    "last_checked_at": "",
                    "check_timeout_seconds": 3,
                }
            )

        if not self.server_api_settings_path.exists():
            self.save_server_api_settings(
                {
                    "use_server": True,
                    "base_url": DEFAULT_SERVER_API_BASE_URL,
                    "timeout_seconds": 5,
                    "health_path": "/api/health",
                    "employees_path": "/api/employees",
                    "pc_sync_key": DEFAULT_SERVER_PC_SYNC_KEY,
                }
            )

    def _merge_legacy_path(self, src: Path, dst: Path) -> None:
        if not src.exists():
            return
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return
        if src.is_file():
            return
        dst.mkdir(parents=True, exist_ok=True)
        for child in list(src.iterdir()):
            target = dst / child.name
            if child.is_dir():
                self._merge_legacy_path(child, target)
            else:
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(child), str(target))
        try:
            src.rmdir()
        except OSError:
            pass

    def _migrate_legacy_layout(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

        legacy_map = [
            (self.legacy_data_dir / "db", self.db_dir),
            (self.legacy_db_path, self.db_path),
            (self.legacy_data_dir / "files", self.files_dir),
            (self.program_legacy_storage_dir, self.legacy_storage_dir),
            (self.legacy_data_dir / "config", self.config_dir),
            (self.legacy_settings_dir, self.config_dir),
            (self.legacy_data_dir / "cache", self.cache_dir),
            (self.legacy_data_dir / "export", self.export_dir),
            (self.legacy_data_dir / "logs", self.logs_dir),
            (self.legacy_data_dir / "temp", self.temp_dir),
            (self.legacy_data_dir / "sample", self.sample_dir),
            (self.legacy_data_dir / "backup", self.default_backup_root),
        ]
        for src, dst in legacy_map:
            self._merge_legacy_path(src, dst)

        if self.legacy_backup_root.exists() and not self.backup_root.exists():
            self.backup_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(self.legacy_backup_root), str(self.backup_root))

        default_backup_root = self.default_backup_root
        if default_backup_root != self.backup_root and default_backup_root.exists() and not self.backup_root.exists():
            self.backup_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(default_backup_root), str(self.backup_root))

        if self.legacy_logs_dir.exists() and not self.logs_dir.exists():
            shutil.move(str(self.legacy_logs_dir), str(self.logs_dir))

        if self.legacy_temp_dir.exists() and not self.temp_dir.exists():
            shutil.move(str(self.legacy_temp_dir), str(self.temp_dir))

        legacy_latest_settings = self.backup_latest_dir / "settings"
        if legacy_latest_settings.exists() and not self.backup_latest_settings_dir.exists():
            shutil.move(str(legacy_latest_settings), str(self.backup_latest_settings_dir))

        if self.backup_history_dir.exists():
            for child in self.backup_history_dir.iterdir():
                if not child.is_dir():
                    continue
                old_settings = child / "settings"
                new_config = child / "config"
                if old_settings.exists() and not new_config.exists():
                    shutil.move(str(old_settings), str(new_config))

    def load_app_settings(self, default: dict[str, Any] | None = None) -> dict[str, Any]:
        default = dict(default or {})
        if not self.app_settings_path.exists():
            return default
        try:
            return json.loads(self.app_settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def save_app_settings(self, payload: dict[str, Any]) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        normalized = dict(payload or {})
        normalized["app_name"] = APP_SETTINGS_NAME
        normalized["program_version"] = PROGRAM_VERSION
        normalized["storage_version"] = STORAGE_VERSION
        self.app_settings_path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


    def load_update_settings(self, default: dict[str, Any] | None = None) -> dict[str, Any]:
        default_payload = {
            "enabled": False,
            "auto_check_on_start": False,
            "current_version": PROGRAM_VERSION,
            "update_info_url": "",
            "skip_version": "",
            "last_checked_at": "",
            "check_timeout_seconds": 3,
        }
        if default:
            default_payload.update(default)
        if not self.update_settings_path.exists():
            return dict(default_payload)
        try:
            payload = json.loads(self.update_settings_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return dict(default_payload)
            merged = dict(default_payload)
            merged.update(payload)
            base_url = str(merged.get("base_url") or DEFAULT_SERVER_API_BASE_URL).strip().rstrip("/") or DEFAULT_SERVER_API_BASE_URL
            if base_url.lower().startswith("http://sungjo2003.cafe24.com"):
                base_url = "https://" + base_url[len("http://"):]
            merged["base_url"] = base_url
            return merged
        except (OSError, json.JSONDecodeError):
            return dict(default_payload)

    def save_update_settings(self, payload: dict[str, Any]) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        normalized = self.load_update_settings({})
        normalized.update(dict(payload or {}))
        normalized["current_version"] = PROGRAM_VERSION
        normalized["update_info_url"] = str(normalized.get("update_info_url") or "").strip()
        try:
            normalized["check_timeout_seconds"] = max(1, min(15, int(normalized.get("check_timeout_seconds", 3) or 3)))
        except (TypeError, ValueError):
            normalized["check_timeout_seconds"] = 3
        self.update_settings_path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )



    def _default_server_api_settings(self, default: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "use_server": True,
            "base_url": DEFAULT_SERVER_API_BASE_URL,
            "timeout_seconds": 5,
            "health_path": "/api/health",
            "employees_path": "/api/employees",
            "pc_sync_key": DEFAULT_SERVER_PC_SYNC_KEY,
        }
        if default:
            payload.update(default)
        return payload

    def _normalize_server_api_settings(self, payload: dict[str, Any] | None, default: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = self._default_server_api_settings(default)
        if isinstance(payload, dict):
            normalized.update(payload)
        normalized["use_server"] = True
        normalized["base_url"] = str(normalized.get("base_url") or DEFAULT_SERVER_API_BASE_URL).strip().rstrip("/") or DEFAULT_SERVER_API_BASE_URL
        if normalized["base_url"].lower().startswith("http://sungjo2003.cafe24.com"):
            normalized["base_url"] = "https://" + normalized["base_url"][len("http://"):]
        normalized["health_path"] = str(normalized.get("health_path") or "/api/health").strip() or "/api/health"
        normalized["employees_path"] = str(normalized.get("employees_path") or "/api/employees").strip() or "/api/employees"
        normalized["pc_sync_key"] = str(normalized.get("pc_sync_key") or DEFAULT_SERVER_PC_SYNC_KEY or "").strip()
        try:
            normalized["timeout_seconds"] = max(1, min(30, int(normalized.get("timeout_seconds", 5) or 5)))
        except (TypeError, ValueError):
            normalized["timeout_seconds"] = 5
        return normalized

    def _write_server_api_settings_file(self, payload: dict[str, Any]) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.server_api_settings_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_server_api_settings(self, default: dict[str, Any] | None = None) -> dict[str, Any]:
        default_payload = self._default_server_api_settings(default)
        if not self.server_api_settings_path.exists():
            normalized = self._normalize_server_api_settings(default_payload)
            self._write_server_api_settings_file(normalized)
            return normalized
        try:
            payload = json.loads(self.server_api_settings_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                normalized = self._normalize_server_api_settings(default_payload)
                self._write_server_api_settings_file(normalized)
                return normalized
            normalized = self._normalize_server_api_settings(payload, default_payload)
            # 기존 파일에 pc_sync_key가 비어 있었던 PC도 실행만 하면 자동 복구되게 저장합니다.
            if normalized != payload:
                self._write_server_api_settings_file(normalized)
            return normalized
        except (OSError, json.JSONDecodeError):
            normalized = self._normalize_server_api_settings(default_payload)
            try:
                self._write_server_api_settings_file(normalized)
            except OSError:
                pass
            return normalized

    def save_server_api_settings(self, payload: dict[str, Any]) -> None:
        normalized = self._normalize_server_api_settings(payload)
        self._write_server_api_settings_file(normalized)


    def restore_latest_if_needed(self) -> bool:
        if self.db_path.exists():
            return False
        if self.backup_latest_zip_path.exists():
            self.restore_from_backup(self.backup_latest_zip_path)
            return True
        legacy_latest_db = self.backup_latest_dir / self.db_path.name
        if legacy_latest_db.exists():
            self.restore_from_backup(self.backup_latest_dir)
            return True
        return False

    def sync_latest_backup(self, *, include_files: bool = False, include_settings: bool = True, reason: str = "auto") -> Path:
        """최신 백업을 압축파일 1개로 갱신합니다.

        백업 압축파일에는 복구에 필요한 db/config/storage/files가 포함됩니다.
        종료 단계에서 백업 파일이 사용 중이어도 프로그램 종료가 막히지 않도록
        백업 오류는 기록만 남기고 반환합니다.
        """
        self.ensure_structure()
        try:
            self._create_backup_zip(self.backup_latest_zip_path, reason=reason)
            self._update_last_backup_setting()
            self._clear_backup_error()
        except OSError as exc:
            self._record_backup_error(reason, [f"최신 백업 압축파일 저장 실패: {exc}"])
        return self.backup_latest_zip_path

    def create_history_backup(self, *, reason: str = "manual", include_files: bool = True, include_settings: bool = True) -> Path:
        self.ensure_structure()
        stamp = _utc_now_compact()
        target_zip = self.backup_history_dir / f"workforce_backup_{stamp}.zip"
        try:
            self._create_backup_zip(target_zip, reason=reason, stamp=stamp)
            self._update_last_backup_setting(stamp)
            self._clear_backup_error()
            self._cleanup_history_backups(days=30)
        except OSError as exc:
            self._record_backup_error(reason, [f"이력 백업 압축파일 저장 실패: {exc}"])
        return target_zip

    def restore_from_backup(self, backup_source: str | Path) -> None:
        backup_path = Path(backup_source)
        if backup_path.is_file() and backup_path.suffix.lower() == ".zip":
            with tempfile.TemporaryDirectory(prefix="workforce_restore_") as tmp_dir:
                tmp_path = Path(tmp_dir)
                with zipfile.ZipFile(backup_path, "r") as zf:
                    zf.extractall(tmp_path)
                self._restore_from_backup_folder(tmp_path)
            return
        self._restore_from_backup_folder(backup_path)

    def _restore_from_backup_folder(self, backup_path: Path) -> None:
        db_source = backup_path / "db" / self.db_path.name
        legacy_db_source = backup_path / self.db_path.name
        if not db_source.exists() and legacy_db_source.exists():
            db_source = legacy_db_source
        if not db_source.exists():
            raise FileNotFoundError(f"백업 DB를 찾을 수 없습니다: {backup_path}")
        self.ensure_structure()
        self.db_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_source, self.db_path)

        files_source = backup_path / "files"
        storage_source = backup_path / "storage"
        config_source = backup_path / "config"
        settings_source = backup_path / "settings"
        if files_source.exists():
            self._replace_tree(files_source, self.files_dir)
        if storage_source.exists():
            self._replace_tree(storage_source, self.legacy_storage_dir)
        if config_source.exists():
            self._replace_tree(config_source, self.config_dir)
        elif settings_source.exists():
            self._replace_tree(settings_source, self.config_dir)

    def _create_backup_zip(self, target_zip: Path, *, reason: str, stamp: str | None = None) -> Path:
        target_zip.parent.mkdir(parents=True, exist_ok=True)
        tmp_zip = target_zip.with_name(f".{target_zip.stem}.tmp{target_zip.suffix}")
        self._safe_unlink(tmp_zip)
        backup_stamp = stamp or _utc_now_compact()
        manifest = self._backup_manifest_payload(reason=reason, stamp=backup_stamp)
        try:
            with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                if self.db_path.exists():
                    zf.write(self.db_path, f"db/{self.db_path.name}")
                self._write_tree_to_zip(zf, self.config_dir, "config")
                self._write_tree_to_zip(zf, self.legacy_storage_dir, "storage")
                self._write_tree_to_zip(zf, self.files_dir, "files")
                zf.writestr("backup_info.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            if not self.db_path.exists():
                raise FileNotFoundError(f"백업할 DB를 찾을 수 없습니다: {self.db_path}")
            self._make_writable(tmp_zip)
            if target_zip.exists():
                self._make_writable(target_zip)
            tmp_zip.replace(target_zip)
        except Exception:
            self._safe_unlink(tmp_zip)
            raise
        return target_zip

    def _write_tree_to_zip(self, zf: zipfile.ZipFile, src: Path, arc_root: str) -> None:
        if not src.exists():
            return
        for file_path in src.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, f"{arc_root}/{file_path.relative_to(src).as_posix()}")

    def _backup_manifest_payload(self, *, reason: str, stamp: str) -> dict[str, Any]:
        return {
            "created_at": stamp,
            "reason": reason,
            "program_version": PROGRAM_VERSION,
            "storage_version": STORAGE_VERSION,
            "data_dir": str(self.data_dir),
            "includes": {
                "db": self.db_path.exists(),
                "config": self.config_dir.exists(),
                "storage": self.legacy_storage_dir.exists(),
                "files": self.files_dir.exists(),
            },
        }

    def _cleanup_history_backups(self, *, days: int = 30) -> None:
        if days <= 0 or not self.backup_history_dir.exists():
            return
        cutoff = datetime.utcnow() - timedelta(days=days)
        for path in self.backup_history_dir.iterdir():
            if not path.is_file() or path.suffix.lower() != ".zip":
                continue
            try:
                modified_at = datetime.utcfromtimestamp(path.stat().st_mtime)
            except OSError:
                continue
            if modified_at < cutoff:
                self._safe_unlink(path)

    def employee_record_dir(self, employee_id: int | str) -> Path:
        employee_key = str(employee_id).strip() or "unknown"
        target_dir = self.employee_files_dir / employee_key
        target_dir.mkdir(parents=True, exist_ok=True)
        for folder in [
            target_dir / "documents" / "original",
            target_dir / "documents" / "corrected",
            target_dir / "documents" / "preview",
            target_dir / "portrait",
            target_dir / "ocr",
        ]:
            folder.mkdir(parents=True, exist_ok=True)
        return target_dir

    def _normalize_document_kind(self, document_kind: str | None) -> str:
        raw = str(document_kind or "").strip().lower()
        if raw in {"passport", "pp"}:
            return "passport"
        if raw in {"idcard", "id_card", "residence_card", "overseas_resident_card", "arc"}:
            return "idcard"
        return "document"

    def employee_portrait_path(self, employee_id: int | str, suffix: str = ".png") -> Path:
        ext = str(suffix or ".png").strip() or ".png"
        if not ext.startswith("."):
            ext = f".{ext}"
        return self.employee_record_dir(employee_id) / "portrait" / f"worker_photo{ext.lower()}"

    def employee_original_document_path(self, employee_id: int | str, document_kind: str | None = None, suffix: str = ".png") -> Path:
        ext = str(suffix or ".png").strip() or ".png"
        if not ext.startswith("."):
            ext = f".{ext}"
        base_name = self._normalize_document_kind(document_kind)
        return self.employee_record_dir(employee_id) / "documents" / "original" / f"{base_name}_original{ext.lower()}"

    def employee_corrected_document_path(self, employee_id: int | str, document_kind: str | None = None, suffix: str = ".png") -> Path:
        ext = str(suffix or ".png").strip() or ".png"
        if not ext.startswith("."):
            ext = f".{ext}"
        base_name = self._normalize_document_kind(document_kind)
        return self.employee_record_dir(employee_id) / "documents" / "corrected" / f"{base_name}_corrected{ext.lower()}"

    def employee_document_path(self, employee_id: int | str, suffix: str = ".png") -> Path:
        return self.employee_corrected_document_path(employee_id, "document", suffix)

    def _replace_tree(self, src: Path, dst: Path) -> None:
        if dst.exists():
            self._remove_tree(dst)
        if src.exists():
            shutil.copytree(src, dst)
        else:
            dst.mkdir(parents=True, exist_ok=True)

    def _make_writable(self, path: Path) -> None:
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass

    def _remove_tree(self, path: Path) -> None:
        def onerror(func, failing_path, _exc_info):
            try:
                os.chmod(failing_path, stat.S_IWRITE | stat.S_IREAD)
                func(failing_path)
            except OSError:
                raise

        shutil.rmtree(path, onerror=onerror)

    def _safe_unlink(self, path: Path) -> None:
        try:
            if path.exists():
                self._make_writable(path)
                path.unlink()
        except OSError:
            pass

    def _safe_replace_file(self, src: Path, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(f".{dst.name}.tmp")
        self._safe_unlink(tmp)
        shutil.copy2(src, tmp)
        self._make_writable(tmp)
        if dst.exists():
            self._make_writable(dst)
        try:
            tmp.replace(dst)
        except PermissionError:
            self._safe_unlink(dst)
            try:
                tmp.replace(dst)
            except PermissionError as exc:
                fallback = dst.with_name(f"{dst.stem}_{_utc_now_compact()}{dst.suffix}")
                try:
                    tmp.replace(fallback)
                finally:
                    self._safe_unlink(tmp)
                raise PermissionError(f"{dst} 파일이 사용 중이어서 {fallback.name} 이름으로 백업했습니다.") from exc
        finally:
            self._safe_unlink(tmp)

    def _record_backup_error(self, reason: str, errors: list[str]) -> None:
        message = "\n".join(errors)
        payload = {
            "created_at": _utc_now_compact(),
            "reason": reason,
            "message": message,
            "backup_root": str(self.backup_root),
        }
        self._safe_write_text(
            self.backup_root / "LAST_BACKUP_ERROR.txt",
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def _clear_backup_error(self) -> None:
        self._safe_unlink(self.backup_root / "LAST_BACKUP_ERROR.txt")

    def _write_backup_manifest(self, target_dir: Path, *, reason: str) -> None:
        payload = {
            "created_at": _utc_now_compact(),
            "reason": reason,
            "db_file": self.db_path.name,
            "includes": {
                "files": (target_dir / "files").exists(),
                "storage": (target_dir / "storage").exists(),
                "config": (target_dir / "config").exists() or (target_dir / "settings").exists(),
            },
        }
        (target_dir / "backup_info.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _update_last_backup_setting(self, stamp: str | None = None) -> None:
        payload = self.load_app_settings(
            {
                "app_name": APP_SETTINGS_NAME,
                "storage_version": STORAGE_VERSION,
                "created_at": _utc_now_compact(),
                "last_backup_at": "",
                "backup_dir": self.backup_setting_value(),
            }
        )
        payload["last_backup_at"] = stamp or _utc_now_compact()
        self.save_app_settings(payload)

    def _write_text_if_missing(self, path: Path, text: str) -> None:
        if not path.exists():
            self._safe_write_text(path, text)

    def _safe_write_text(self, path: Path, text: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError:
            # 안내/README 파일 작성 실패는 실행을 막을 정도의 오류가 아닙니다.
            return
