from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DISPLAY_NAME = "스마트인력관리365"
APP_SETTINGS_NAME = "Workforce PC Main"
PROGRAM_VERSION = "0.9.0.0.0"
STORAGE_VERSION = 2

PROGRAM_VENDOR = "GreenSystem"
DATA_ENV_VAR_NAME = "WORKFORCE_DATA_DIR"
DEFAULT_DATA_FOLDER_NAME = "WorkforceData"
DEFAULT_UPDATE_INFO_URL = ""
DEFAULT_SERVER_API_BASE_URL = "https://sungjo2003.cafe24.com"
# PC 배포본만 실행해도 서버 동기화 설정 파일이 자동 생성되도록 하는 기본 키입니다.
# 실제 운영에서는 서버 .env의 PC_SYNC_KEY와 같은 값이어야 합니다.
DEFAULT_SERVER_PC_SYNC_KEY = os.getenv("WORKFORCE_PC_SYNC_KEY", "green_sync_2026_key_0511")


def get_program_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_default_data_root(program_root: str | Path | None = None) -> Path:
    env_value = str(os.getenv(DATA_ENV_VAR_NAME, "") or "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()

    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return (base / PROGRAM_VENDOR / DEFAULT_DATA_FOLDER_NAME).resolve()

    return (Path.home() / f".{PROGRAM_VENDOR.lower()}" / DEFAULT_DATA_FOLDER_NAME.lower()).resolve()
