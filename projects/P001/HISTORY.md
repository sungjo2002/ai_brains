# HISTORY

이 파일은 P001 프로젝트의 날짜별 작업 기록을 남긴다.

## 2026-05-20

- 저장소 구조를 여러 AI와 코딩 도구가 공통으로 사용할 수 있는 방식으로 정리했다.
- 루트 기준 파일을 `AGENTS.md`, `README.md`, `PROJECTS.md`, `RULES.md`, `CHANGELOG.md`로 정리했다.
- P001 프로젝트 폴더를 생성하고 현재 상태, 다음 작업, 규칙, 명령어, 테스트, 파일 지도, 결정 사항을 분리했다.
- 최신 기준은 PC `pc_33_common_refresh_after_save_fix.zip`, 서버 `server_13_employee_delete_tombstone_fix.zip`, 모바일 `mobile_18_home_worker_quick_info_memo_box.zip`로 정리했다.

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
