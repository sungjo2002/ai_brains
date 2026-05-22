from __future__ import annotations

import base64
import json
import os
import ssl
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .app_metadata import DEFAULT_SERVER_PC_SYNC_KEY


DEFAULT_PC_SYNC_KEY = DEFAULT_SERVER_PC_SYNC_KEY

_SSL_CONTEXT = None

def _https_context():
    """Use certifi CA bundle when available so packaged Windows PCs can verify HTTPS."""
    global _SSL_CONTEXT
    if _SSL_CONTEXT is not None:
        return _SSL_CONTEXT
    try:
        import certifi  # type: ignore
        cafile = certifi.where()
        if cafile and Path(cafile).exists():
            _SSL_CONTEXT = ssl.create_default_context(cafile=cafile)
            return _SSL_CONTEXT
    except Exception:
        pass
    _SSL_CONTEXT = ssl.create_default_context()
    return _SSL_CONTEXT

def _ssl_error_message(error: Exception) -> str:
    text = str(error or '').strip()
    if 'CERTIFICATE_VERIFY_FAILED' in text or 'certificate verify failed' in text.lower():
        return 'SSL 인증서 검증 실패: PC 인증서 묶음을 확인할 수 없습니다. certifi 보강본을 적용했는지 확인하세요.'
    return text


def _normalize_base_url(base_url: str) -> str:
    base = str(base_url or '').strip().rstrip('/')

    # 기존 PC에 저장된 설정이 http 주소인 경우, nginx의 https 리다이렉트 과정에서
    # POST 요청이 GET으로 바뀌어 405 오류가 날 수 있습니다.
    # 운영 서버는 HTTPS 기준으로 고정합니다.
    lowered = base.lower()
    if lowered.startswith('http://sungjo2003.cafe24.com'):
        base = 'https://' + base[len('http://'):]

    return base


def _join_url(base_url: str, path: str) -> str:
    base = _normalize_base_url(base_url)
    tail = str(path or '').strip()
    if not tail.startswith('/'):
        tail = '/' + tail

    # 설정창에서 base_url을 https://도메인/api 로 저장한 경우도 방어합니다.
    # API 경로가 /api/... 로 다시 붙으면 /api/api/... 가 되기 때문입니다.
    if base.lower().endswith('/api') and tail.lower().startswith('/api/'):
        tail = tail[4:]

    return f"{base}{tail}"


def _normalize_timeout(value: Any, fallback: int = 5) -> int:
    try:
        timeout = int(value or fallback)
    except (TypeError, ValueError):
        timeout = fallback
    return max(1, min(60, timeout))


def _server_headers(settings: dict[str, Any] | None = None) -> dict[str, str]:
    payload = settings if isinstance(settings, dict) else {}
    key = str(payload.get("pc_sync_key") or os.getenv("PC_SYNC_KEY", "") or DEFAULT_PC_SYNC_KEY).strip()
    headers = {
        "Accept": "application/json",
    }
    if key:
        headers["X-PC-Sync-Key"] = key
    return headers



def _snapshot_timeout(settings: dict[str, Any] | None = None) -> int:
    payload = settings if isinstance(settings, dict) else {}
    raw = payload.get("snapshot_timeout_seconds") or payload.get("timeout_seconds") or 30
    try:
        timeout = int(raw or 30)
    except (TypeError, ValueError):
        timeout = 30
    # PC 전체 snapshot은 급여/차량/근태 전체 JSON이라 기본 5초로는 실패할 수 있습니다.
    return max(30, min(60, timeout))

def _http_error_message(error: HTTPError) -> str:
    try:
        body = error.read().decode('utf-8', errors='replace').strip()
    except Exception:
        body = ''
    detail = f"HTTP {error.code} {getattr(error, 'reason', '')}".strip()
    if body:
        detail = f"{detail}: {body[:500]}"
    return detail


def fetch_json(url: str, timeout_seconds: int = 5, headers: dict[str, str] | None = None) -> Any:
    request = Request(url, headers=dict(headers or {}))
    try:
        with urlopen(request, timeout=_normalize_timeout(timeout_seconds), context=_https_context()) as response:
            raw = response.read().decode('utf-8')
        return json.loads(raw)
    except HTTPError as error:
        raise RuntimeError(_http_error_message(error)) from error
    except URLError as error:
        raise RuntimeError(_ssl_error_message(getattr(error, 'reason', error))) from error


def fetch_bytes(url: str, timeout_seconds: int = 5, headers: dict[str, str] | None = None) -> bytes:
    request = Request(url, headers=dict(headers or {}))
    try:
        with urlopen(request, timeout=_normalize_timeout(timeout_seconds), context=_https_context()) as response:
            return response.read()
    except HTTPError as error:
        raise RuntimeError(_http_error_message(error)) from error
    except URLError as error:
        raise RuntimeError(_ssl_error_message(getattr(error, 'reason', error))) from error


def send_json(url: str, method: str, payload: dict[str, Any], timeout_seconds: int = 5, headers: dict[str, str] | None = None) -> Any:
    data = json.dumps(payload or {}, ensure_ascii=False).encode('utf-8')
    normalized_method = str(method or 'POST').upper()
    request_headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }
    request_headers.update(dict(headers or {}))
    request = Request(
        url,
        data=data,
        headers=request_headers,
    )
    request.get_method = lambda: normalized_method
    try:
        with urlopen(request, timeout=_normalize_timeout(timeout_seconds), context=_https_context()) as response:
            raw = response.read().decode('utf-8')
        return json.loads(raw) if raw else {}
    except HTTPError as error:
        raise RuntimeError(_http_error_message(error)) from error
    except URLError as error:
        raise RuntimeError(_ssl_error_message(getattr(error, 'reason', error))) from error


def build_health_url(settings: dict[str, Any]) -> str:
    return _join_url(settings.get('base_url', ''), str(settings.get('health_path') or '/api/health'))


def build_employees_url(settings: dict[str, Any]) -> str:
    return _join_url(settings.get('base_url', ''), str(settings.get('employees_path') or '/api/employees'))


def build_snapshot_url(settings: dict[str, Any]) -> str:
    custom_path = str(settings.get('snapshot_path', '') or '').strip()
    if custom_path:
        return _join_url(settings.get('base_url', ''), custom_path)
    return f"{build_employees_url(settings).rstrip('/')}/snapshot"




def build_attendance_month_url(settings: dict[str, Any], year_month: str) -> str:
    query = urlencode({"year_month": str(year_month or "").strip()})
    return f"{_join_url(settings.get('base_url', ''), '/api/attendance/month')}?{query}"


def fetch_attendance_month_remote(settings: dict[str, Any], year_month: str) -> dict[str, Any]:
    response = fetch_json(
        build_attendance_month_url(settings, year_month),
        settings.get('timeout_seconds', 5),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}

def build_attendance_month_lock_status_url(settings: dict[str, Any], year_month: str) -> str:
    query = urlencode({"year_month": str(year_month or "").strip()})
    return f"{_join_url(settings.get('base_url', ''), '/api/attendance/month-lock-status')}?{query}"


def build_attendance_month_lock_url(settings: dict[str, Any]) -> str:
    return _join_url(settings.get('base_url', ''), '/api/attendance/month-lock')


def build_attendance_month_unlock_url(settings: dict[str, Any]) -> str:
    return _join_url(settings.get('base_url', ''), '/api/attendance/month-unlock')

def build_employee_media_url(settings: dict[str, Any], employee_id: int, media_kind: str) -> str:
    kind = str(media_kind or 'portrait').strip().lower() or 'portrait'
    return f"{build_employees_url(settings).rstrip('/')}/{int(employee_id)}/media/{kind}"


def check_health(settings: dict[str, Any]) -> bool:
    try:
        payload = fetch_json(build_health_url(settings), settings.get('timeout_seconds', 5), _server_headers(settings))
        return isinstance(payload, dict) and str(payload.get('status') or '').strip().lower() == 'ok'
    except Exception:
        return False


def fetch_employees(settings: dict[str, Any]) -> list[dict[str, Any]]:
    payload = fetch_json(build_employees_url(settings), settings.get('timeout_seconds', 5), _server_headers(settings))
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


def create_employee_remote(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    response = send_json(
        build_employees_url(settings),
        'POST',
        payload,
        _snapshot_timeout(settings),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def update_employee_remote(settings: dict[str, Any], employee_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    response = send_json(
        f"{build_employees_url(settings)}/{int(employee_id)}",
        'PUT',
        payload,
        settings.get('timeout_seconds', 5),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def delete_employee_remote(settings: dict[str, Any], employee_id: int) -> dict[str, Any]:
    response = send_json(
        f"{build_employees_url(settings)}/{int(employee_id)}",
        'DELETE',
        {},
        _snapshot_timeout(settings),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def fetch_app_snapshot(settings: dict[str, Any]) -> dict[str, Any]:
    response = fetch_json(build_snapshot_url(settings), _snapshot_timeout(settings), _server_headers(settings))
    return response if isinstance(response, dict) else {}


def push_app_snapshot(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    response = send_json(
        build_snapshot_url(settings),
        'PUT',
        payload,
        _snapshot_timeout(settings),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def upload_employee_media(settings: dict[str, Any], employee_id: int, media_kind: str, file_path: str) -> dict[str, Any]:
    from pathlib import Path

    path = Path(str(file_path or ''))
    if not path.exists() or not path.is_file():
        return {}
    response = send_json(
        build_employee_media_url(settings, employee_id, media_kind),
        'PUT',
        {
            'filename': path.name,
            'content_type': 'image/png' if path.suffix.lower() == '.png' else 'application/octet-stream',
            'data_base64': base64.b64encode(path.read_bytes()).decode('ascii'),
        },
        settings.get('timeout_seconds', 5),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def download_media_file(url: str, timeout_seconds: int = 5) -> bytes:
    return fetch_bytes(url, timeout_seconds)


def fetch_attendance_month_lock_status(settings: dict[str, Any], year_month: str) -> dict[str, Any]:
    response = fetch_json(
        build_attendance_month_lock_status_url(settings, year_month),
        settings.get('timeout_seconds', 5),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def close_attendance_month_remote(
    settings: dict[str, Any],
    year_month: str,
    *,
    locked_by: str = 'pc',
    source: str = 'pc',
    note: str = '',
) -> dict[str, Any]:
    response = send_json(
        build_attendance_month_lock_url(settings),
        'POST',
        {
            'year_month': str(year_month or '').strip(),
            'locked_by': str(locked_by or 'pc'),
            'source': str(source or 'pc'),
            'note': str(note or ''),
        },
        settings.get('timeout_seconds', 5),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def reopen_attendance_month_remote(
    settings: dict[str, Any],
    year_month: str,
    *,
    unlocked_by: str = 'pc',
    source: str = 'pc',
    note: str = '',
) -> dict[str, Any]:
    response = send_json(
        build_attendance_month_unlock_url(settings),
        'POST',
        {
            'year_month': str(year_month or '').strip(),
            'unlocked_by': str(unlocked_by or 'pc'),
            'source': str(source or 'pc'),
            'note': str(note or ''),
        },
        settings.get('timeout_seconds', 5),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def build_vehicle_logs_url(settings: dict[str, Any]) -> str:
    return _join_url(settings.get('base_url', ''), '/api/vehicles/logs')


def fetch_vehicle_logs_remote(settings: dict[str, Any]) -> dict[str, Any]:
    response = fetch_json(
        build_vehicle_logs_url(settings),
        settings.get('timeout_seconds', 5),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def build_vehicle_run_logs_url(settings: dict[str, Any]) -> str:
    return _join_url(settings.get('base_url', ''), '/api/vehicles/run-logs')


def build_vehicle_fuel_logs_url(settings: dict[str, Any]) -> str:
    return _join_url(settings.get('base_url', ''), '/api/vehicles/fuel-logs')


def build_vehicle_cost_logs_url(settings: dict[str, Any]) -> str:
    return _join_url(settings.get('base_url', ''), '/api/vehicles/cost-logs')


def save_vehicle_run_log_remote(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    response = send_json(
        build_vehicle_run_logs_url(settings),
        'POST',
        payload,
        settings.get('timeout_seconds', 5),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def save_vehicle_fuel_log_remote(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    response = send_json(
        build_vehicle_fuel_logs_url(settings),
        'POST',
        payload,
        settings.get('timeout_seconds', 5),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def save_vehicle_cost_log_remote(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    response = send_json(
        build_vehicle_cost_logs_url(settings),
        'POST',
        payload,
        settings.get('timeout_seconds', 5),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def delete_vehicle_run_log_remote(settings: dict[str, Any], log_id: str) -> dict[str, Any]:
    response = send_json(
        f"{build_vehicle_run_logs_url(settings).rstrip('/')}/{quote(str(log_id or '').strip(), safe='')}",
        'DELETE',
        {'source': 'pc', 'updated_by': 'pc'},
        settings.get('timeout_seconds', 5),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def delete_vehicle_fuel_log_remote(settings: dict[str, Any], fuel_id: str) -> dict[str, Any]:
    response = send_json(
        f"{build_vehicle_fuel_logs_url(settings).rstrip('/')}/{quote(str(fuel_id or '').strip(), safe='')}",
        'DELETE',
        {'source': 'pc', 'updated_by': 'pc'},
        settings.get('timeout_seconds', 5),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}


def delete_vehicle_cost_log_remote(settings: dict[str, Any], cost_id: str) -> dict[str, Any]:
    response = send_json(
        f"{build_vehicle_cost_logs_url(settings).rstrip('/')}/{quote(str(cost_id or '').strip(), safe='')}",
        'DELETE',
        {'source': 'pc', 'updated_by': 'pc'},
        settings.get('timeout_seconds', 5),
        _server_headers(settings),
    )
    return response if isinstance(response, dict) else {}
