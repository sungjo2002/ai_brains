from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

API_URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
HOLIDAY_API_CONFIG_FILE = "holiday_api.json"
HOLIDAY_CACHE_FILE = "holidays.json"
DEFAULT_TIMEOUT_SECONDS = 8


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def default_holiday_api_settings() -> dict[str, Any]:
    current_year = datetime.now().year
    return {
        "enabled": False,
        "service_key": "",
        "last_sync": "",
        "last_error": "",
        "years": [current_year, current_year + 1],
        "api_url": API_URL,
    }


def _read_json(path: Path, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return dict(fallback or {})


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_holiday_api_settings(config_dir: str | Path) -> dict[str, Any]:
    path = Path(config_dir) / HOLIDAY_API_CONFIG_FILE
    settings = default_holiday_api_settings()
    loaded = _read_json(path, settings)
    settings.update(loaded)
    years = settings.get("years")
    if not isinstance(years, list) or not years:
        current_year = datetime.now().year
        settings["years"] = [current_year, current_year + 1]
    settings["enabled"] = bool(settings.get("enabled", False))
    settings["service_key"] = str(settings.get("service_key", "") or "").strip()
    settings["api_url"] = str(settings.get("api_url", "") or API_URL).strip() or API_URL
    if not path.exists():
        _write_json(path, settings)
    return settings


def save_holiday_api_settings(config_dir: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    settings = default_holiday_api_settings()
    settings.update(payload or {})
    settings["enabled"] = bool(settings.get("enabled", False))
    settings["service_key"] = str(settings.get("service_key", "") or "").strip()
    settings["api_url"] = str(settings.get("api_url", "") or API_URL).strip() or API_URL
    years: list[int] = []
    for value in settings.get("years", []) or []:
        try:
            year = int(value)
        except (TypeError, ValueError):
            continue
        if 1900 <= year <= 2100 and year not in years:
            years.append(year)
    if not years:
        current_year = datetime.now().year
        years = [current_year, current_year + 1]
    settings["years"] = years
    _write_json(Path(config_dir) / HOLIDAY_API_CONFIG_FILE, settings)
    return settings


def load_cached_holidays(config_dir: str | Path) -> dict[str, str]:
    path = Path(config_dir) / HOLIDAY_CACHE_FILE
    data = _read_json(path, {})
    raw = data.get("holidays", {}) if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for day_text, name in raw.items():
        key = str(day_text or "").strip()
        if len(key) == 10 and key[4] == "-" and key[7] == "-":
            result[key] = str(name or "휴일").strip() or "휴일"
    return result


def load_cached_holiday_map(config_dir: str | Path, year: int) -> dict[str, str]:
    prefix = f"{int(year):04d}-"
    return {day: name for day, name in load_cached_holidays(config_dir).items() if day.startswith(prefix)}


def _service_key_query(service_key: str) -> str:
    key = str(service_key or "").strip()
    # 공공데이터포털의 인코딩 인증키를 붙여넣은 경우 %2F 등이 이미 들어 있으므로 다시 인코딩하지 않는다.
    # 일반 인증키처럼 /, +, = 가 들어 있는 경우에는 주소용으로 인코딩한다.
    if "%" in key:
        return key
    return quote(key, safe="")


def _extract_items(xml_bytes: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(xml_bytes)
    err_msg = root.findtext(".//errMsg") or root.findtext(".//returnAuthMsg") or ""
    err_code = root.findtext(".//returnReasonCode") or root.findtext(".//returnCode") or ""
    if err_msg and "NORMAL" not in err_msg.upper():
        raise RuntimeError(f"공공데이터 응답 오류: {err_msg} {err_code}".strip())
    items: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        row = {
            "dateName": item.findtext("dateName") or "휴일",
            "locdate": item.findtext("locdate") or "",
            "isHoliday": item.findtext("isHoliday") or "",
        }
        items.append(row)
    return items


def fetch_rest_holidays(service_key: str, year: int, month: int, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, str]:
    key = _service_key_query(service_key)
    url = (
        f"{API_URL}?ServiceKey={key}"
        f"&solYear={int(year):04d}&solMonth={int(month):02d}&pageNo=1&numOfRows=100"
    )
    request = Request(url, headers={"User-Agent": "WorkforceHolidaySync/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            xml_bytes = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"공휴일 조회 실패: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"공휴일 조회 실패: 인터넷 연결 또는 주소 확인 필요 ({exc.reason})") from exc

    holidays: dict[str, str] = {}
    for row in _extract_items(xml_bytes):
        if str(row.get("isHoliday", "")).upper() != "Y":
            continue
        locdate = str(row.get("locdate", "") or "").strip()
        if len(locdate) != 8 or not locdate.isdigit():
            continue
        day = f"{locdate[:4]}-{locdate[4:6]}-{locdate[6:8]}"
        holidays[day] = str(row.get("dateName", "") or "휴일").strip() or "휴일"
    return holidays


def sync_holidays_from_api(config_dir: str | Path, years: list[int] | None = None) -> dict[str, Any]:
    config_path = Path(config_dir)
    settings = load_holiday_api_settings(config_path)
    if not settings.get("enabled"):
        return {"ok": False, "message": "공휴일 자동 갱신이 꺼져 있습니다.", "updated": 0}
    service_key = str(settings.get("service_key", "") or "").strip()
    if not service_key:
        return {"ok": False, "message": "공휴일 API 인증키가 비어 있습니다.", "updated": 0}

    target_years: list[int] = []
    for value in years or settings.get("years") or []:
        try:
            year = int(value)
        except (TypeError, ValueError):
            continue
        if 1900 <= year <= 2100 and year not in target_years:
            target_years.append(year)
    if not target_years:
        current_year = datetime.now().year
        target_years = [current_year, current_year + 1]

    cached_path = config_path / HOLIDAY_CACHE_FILE
    cached_payload = _read_json(cached_path, {"updated_at": "", "source": "", "years": [], "holidays": {}})
    current_holidays = cached_payload.get("holidays", {}) if isinstance(cached_payload.get("holidays"), dict) else {}
    merged = {str(k): str(v) for k, v in current_holidays.items()}

    updated_count = 0
    for year in target_years:
        for month in range(1, 13):
            month_holidays = fetch_rest_holidays(service_key, year, month)
            for day, name in month_holidays.items():
                if merged.get(day) != name:
                    updated_count += 1
                merged[day] = name

    payload = {
        "updated_at": _now_text(),
        "source": "data.go.kr 한국천문연구원 특일 정보",
        "years": target_years,
        "holidays": dict(sorted(merged.items())),
    }
    _write_json(cached_path, payload)

    settings["last_sync"] = payload["updated_at"]
    settings["last_error"] = ""
    settings["years"] = target_years
    save_holiday_api_settings(config_path, settings)
    return {"ok": True, "message": f"공휴일 {len(payload['holidays'])}건 저장 완료", "updated": updated_count, "years": target_years}


def mark_holiday_sync_error(config_dir: str | Path, error: str) -> None:
    settings = load_holiday_api_settings(config_dir)
    settings["last_error"] = str(error or "")
    save_holiday_api_settings(config_dir, settings)
