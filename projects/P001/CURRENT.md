# CURRENT

기준일: 2026-05-20

## 최신 기준 파일

- PC: `pc_33_common_refresh_after_save_fix.zip`
- Server: `server_15_remove_default_admin_seed.zip`
- Mobile: `mobile_26_restore_status_cards_original.zip`

## 다음 번호

- PC: `pc_34`
- Server: `server_16`
- Mobile: `mobile_27`

## 현재 핵심 상태

- 서버 기준으로 PC와 모바일 데이터를 동기화하는 구조를 유지한다.
- 사용자는 동기화 버튼을 기존처럼 하나만 사용한다.
- 내부 저장, 불러오기, 병합, 삭제 반영은 자동 처리하되 사용자 화면에는 복잡한 버튼을 늘리지 않는다.
- PC ↔ 모바일 동기화는 테스트 완료 기준으로 본다.
- PC ↔ PC 서버 백업/복구 동기화 테스트는 아직 별도 확인이 필요하다.
- 실제 VPS 반영 여부는 콘솔 적용 후 확인한다.

## 최신 PC 작업 내용

### pc_33_common_refresh_after_save_fix.zip

- 저장, 삭제, 동기화 후 이미 생성된 화면 목록이 오래된 상태로 남는 문제를 공통 새로고침 방식으로 보강했다.
- 현재 작업 중인 화면은 직접 흔들지 않고, 숨겨진 화면 위주로 갱신하는 방향이다.
- 저장 조건, 권한 조건, 동기화 판단, 계산식, 서버 API 조건은 건드리지 않았다.

## 최신 서버 작업 내용

### server_15_remove_default_admin_seed.zip

- `server_14_snapshot_auth_lock.zip`를 기준으로 만든 서버 보강 수정본이다.
- 서버의 기본 관리자 계정 자동 생성 흐름을 비활성화했다.
- 삭제된 기본 계정이 서버 재시작 후 다시 생기지 않도록 막는 것이 목적이다.
- 실제 확인 결과 서버는 정상 실행 중이고, 삭제된 기본 계정 로그인은 `401`로 차단되는 상태다.

## 최신 모바일 작업 내용

### mobile_26_restore_status_cards_original.zip

- `mobile_22_home_responsive_layout_fix.zip` 기준으로 상태 카드 영역을 정상 동작 상태로 복구한 수정본이다.
- `mobile_23`, `mobile_24`, `mobile_25`에서 시도한 상태 카드 아이콘/배경/상단 사용자 표시 수정은 버튼 액션과 아이콘 표시 문제로 폐기한다.
- 상태 카드/아이콘/버튼 액션은 원래 방식으로 복구한다.
- 홈 반응형 레이아웃 수정은 유지한다.
- 모바일 앱 버전은 `v=92` 기준이다.

## 모바일 중간 수정 기록 요약

- `mobile_20_remove_login_test_account_hint.zip`: 로그인 화면 테스트 계정 안내 문구 제거, `v=86`.
- `mobile_21_home_bottom_blank_space_fix.zip`: 홈 하단 빈공간 수정 시도, 상단 밀림 문제가 있어 폐기.
- `mobile_22_home_responsive_layout_fix.zip`: 홈 반응형 레이아웃 기준 수정, `v=88`.
- `mobile_23_status_icon_and_admin_name_fix.zip`: 상태 아이콘/사용자명 수정 시도, 실제 화면 반영 부족으로 폐기.
- `mobile_24_status_icon_real_class_and_user_name_fix.zip`: 실제 클래스 기준 재수정 시도, 권한명 표시와 아이콘 문제로 폐기.
- `mobile_25_status_card_background_fix.zip`: 상태 카드 배경 수정 시도, 버튼 액션과 아이콘 표시 문제로 폐기.
- `mobile_26_restore_status_cards_original.zip`: 상태 카드 영역을 정상 동작 기준으로 복구한 최신 기준.

## 업로드/적용 방식 기준

- 사용자는 ZIP을 PC에서 먼저 압축 해제한 뒤 파일을 실제 VPS 작업 폴더에 직접 업로드하는 방식을 사용한다.
- 서버 수정본은 `/root/apps/green_api/`에 직접 업로드한다.
- 모바일 수정본은 `/root/apps/mobile_app/`에 직접 업로드한다.
- VPS 콘솔 명령어는 압축 해제가 이미 끝나 있고, 파일이 실제 작업 폴더에 업로드된 상태를 기준으로 제공한다.
- 서버 실제 운영 위치는 `/root/apps/green_api`다.
- 모바일 작업 위치는 `/root/apps/mobile_app`다.
- 모바일 실제 서비스 위치는 `/var/www/mobile_live`다.
- `/root/apps/green_app`은 구버전 또는 별도 앱 가능성 위치로 보고, 현재 서버 API 작업 기준에서 제외한다.
- VPS에 `node` 명령어가 없으므로 모바일 적용 명령어에는 `node --check app.js`를 포함하지 않는다.

## 이미지 동기화 기준

서버 사진 동기화 보강에서 제외할 대상은 다음으로 확정했다.

- 신분증 원본 이미지
- 여권 원본 이미지
- 신분증 보정본 이미지
- 여권 보정본 이미지

근로자 얼굴 사진은 위 제외 대상과 별도이며, 실제 구현 상태는 최신 코드 기준으로 확인이 필요하다.

## PC별 환경값과 공용 업무 설정값 구분

### 동기화 제외 유지

- 서버 주소
- 백업 폴더 위치
- 창 크기/위치
- 로컬 캐시
- 로컬 실패 대기열
- PC별 실행 환경
- PC별 인증서/실행 파일 관련 설정

### 동기화 대상

- 사업자 설정
- 근무사업장 설정
- 근로자
- 근태
- 차량
- 급여
- 월마감
- 관리자/권한
- 공휴일 자동갱신 설정
- 공휴일 자동갱신 인증키
- 회사 운영 공용 설정값
