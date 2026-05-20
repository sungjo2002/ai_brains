# HISTORY

이 파일은 P001 프로젝트의 날짜별 작업 기록을 남긴다.

## 2026-05-20

- 저장소 구조를 여러 AI와 코딩 도구가 공통으로 사용할 수 있는 방식으로 정리했다.
- 루트 기준 파일을 `AGENTS.md`, `README.md`, `PROJECTS.md`, `RULES.md`, `CHANGELOG.md`로 정리했다.
- P001 프로젝트 폴더를 생성하고 현재 상태, 다음 작업, 규칙, 명령어, 테스트, 파일 지도, 결정 사항을 분리했다.
- 최신 기준은 PC `pc_33_common_refresh_after_save_fix.zip`, 서버 `server_15_remove_default_admin_seed.zip`, 모바일 `mobile_26_restore_status_cards_original.zip`로 정리했다.

### server_14_snapshot_auth_lock.zip

- `GET /api/employees/snapshot` 조회를 로그인 전에는 볼 수 없도록 보강했다.
- 로그인 없이 snapshot 조회 시 `401`이 반환되는 것을 확인했다.
- 서버 상태는 `green_api active running`, `/api/health` 응답 정상으로 확인했다.

### server_15_remove_default_admin_seed.zip

- 서버 기본 관리자 계정 자동 생성 흐름을 비활성화했다.
- 삭제된 기본 계정이 서버 재시작 후 다시 생성되지 않도록 정리했다.
- 실제 확인 결과 `admin`, `test`, `test1`은 유지되고 삭제된 기본 계정 로그인은 `401`로 차단됐다.

### mobile_20_remove_login_test_account_hint.zip

- 로그인 화면에 보이던 테스트 계정 안내 문구를 제거했다.
- 모바일 앱 버전은 `v=86`으로 갱신했다.

### mobile_21_home_bottom_blank_space_fix.zip

- 홈 하단 빈공간 제거를 시도했다.
- 상단 영역이 크게 밀리는 문제가 있어 최신 기준에서 제외한다.

### mobile_22_home_responsive_layout_fix.zip

- 홈 화면을 반응형 구조로 다시 정리했다.
- 홈 상단 밀림과 하단 빈공간 문제를 함께 잡는 기준으로 수정했다.
- 모바일 앱 버전은 `v=88`로 갱신했다.

### mobile_23 ~ mobile_25

- 상태 카드 아이콘 배경, 카드 배경, 상단 사용자명 표시를 수정하려고 시도했다.
- 버튼 액션과 아이콘 표시가 깨지는 문제가 있어 해당 시도는 폐기한다.

### mobile_26_restore_status_cards_original.zip

- `mobile_22_home_responsive_layout_fix.zip` 기준으로 상태 카드 영역을 정상 동작 상태로 복구했다.
- 상태 카드, 아이콘, 버튼 액션은 원래 방식으로 복구했다.
- 홈 반응형 레이아웃 수정은 유지했다.
- 모바일 앱 버전은 `v=92` 기준이다.

### 콘솔 명령어 기준 보강

- 서버 수정본은 `/root/apps/green_api` 직접 업로드 기준으로 정리했다.
- 모바일 수정본은 `/root/apps/mobile_app` 직접 업로드 기준으로 정리했다.
- 모바일 라이브 반영 위치는 `/var/www/mobile_live` 기준이다.
- VPS에 `node` 명령어가 없으므로 모바일 적용 명령어에서 `node --check app.js`를 제외했다.
- 콘솔 명령어는 짧게, 필요한 최소 명령어만 제공하는 기준으로 정리했다.

## 2026-05-19

### 최신 기준 파일

- PC: `pc_33_common_refresh_after_save_fix.zip`
- Server: `server_13_employee_delete_tombstone_fix.zip`
- Mobile: `mobile_18_home_worker_quick_info_memo_box.zip`

### pc_29_employee_delete_safe_id_fix.zip

- 근로자 삭제 시 첫 번째는 실패하고 두 번째 삭제에서 반영되는 현상을 보강했다.
- 삭제 대상 ID 처리와 동기화 실패 대기열 처리 안정화를 목표로 했다.

### pc_30_shared_settings_sync_fix.zip

- 공용 설정값 동기화 대상을 보강했다.
- 서버 주소와 백업 폴더 위치는 계속 PC별 환경값으로 제외했다.

### pc_31_holiday_auto_sync_apply_fix.zip

- 공휴일 설정이 다른 PC로 동기화된 뒤 설정 화면과 공휴일 데이터 반영이 바로 이어지지 않는 문제를 보강했다.
- 동기화 후 설정 재적용, 자동갱신 실행 트리거, 캐시 초기화, 근태/급여 화면 반영을 목표로 했다.

### pc_32_worksite_business_select_fix.zip

- 사업장 신규 등록/수정 창에 소속 사업자 드롭다운을 추가했다.
- 신규 사업장 등록 시 어느 사업자 소속인지 선택할 수 있게 했다.
- 기존 사업장 수정 시 다른 사업자로 이동할 수 있게 했다.
- 왼쪽에서 선택한 사업자가 있으면 기본값으로 미리 선택되도록 했다.

### pc_33_common_refresh_after_save_fix.zip

- 사업자, 사업장, 근로자, 차량 등 등록/수정/삭제 또는 동기화 후 일부 화면 목록이 바로 갱신되지 않는 문제를 공통 새로고침 방식으로 보강했다.
- `src/main_window.py`에서 데이터 변경 신호를 감지하고 숨겨진 관련 화면들의 새로고침을 예약하는 방향으로 수정했다.
- 현재 작업 중인 화면은 직접 흔들지 않고, 숨겨진 화면 위주로 갱신하는 방향이다.
- 저장 조건, 권한 조건, 동기화 판단, 계산식, 서버 API 조건은 건드리지 않았다.

### server_11 ~ server_13

- PC에서 서버 전체 저장/불러오기 관련 문제를 확인했다.
- 다른 PC에서 서버 전체 불러오기 실패가 발생했다.
- 삭제 동기화에서 tombstone 방식 보강이 필요하다고 판단했다.
- 삭제한 근로자 목록이 다른 PC/모바일에 남거나 동기화 실패 건수로 표시되는 문제를 수정 대상으로 잡았다.
- 최종 서버 기준은 `server_13_employee_delete_tombstone_fix.zip`로 정리한다.
