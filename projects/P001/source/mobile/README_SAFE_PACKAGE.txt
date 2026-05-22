모바일 수정본 안전 패키지 메모
- 모바일 근태 저장 실패 시 실패한 근태를 localStorage 재전송 대기열(attendanceRetryQueue)에 보관합니다.
- 같은 근로자+같은 날짜의 실패 근태는 대기열에 여러 개 쌓지 않고 마지막 상태만 남깁니다.
- 서버 연결 복구, 앱 실행/로그인, 수동 동기화 시 대기열을 자동 재전송합니다.
- 서버가 정상 저장하면 대기열에서 제거하고 월간 근태를 다시 조회합니다.
- 마감/권한/검증 오류처럼 다시 보내도 성공할 수 없는 오류는 대기열에서 제외합니다.
- 앱 버전을 v=82로 올리고 index.html/manifest.json/app.js 서비스워커 등록 버전을 맞췄습니다.

적용 확인 명령어
cd /root/apps/mobile_app
rm -rf /var/www/mobile_live/*
cp -r ./* /var/www/mobile_live/
chown -R www-data:www-data /var/www/mobile_live
find /var/www/mobile_live -type d -exec chmod 755 {} \;
find /var/www/mobile_live -type f -exec chmod 644 {} \;
systemctl restart nginx


[mobile_17_home_worker_phone_quick_info]
- 기준 파일: mobile_16_attendance_retry_queue_fix.zip
- 홈 화면 근로자 목록에서 이름/행을 누르면 간단 정보 팝업을 표시합니다.
- 팝업에는 전화번호, 근무사업장, 사업자, 근무형태, 현재상태, 국적, 성별, 메모를 표시합니다.
- 전화번호가 있으면 tel: 링크로 연결해 휴대폰에서 바로 전화 앱을 열 수 있습니다.
- 전화번호가 없으면 등록된 번호 없음으로 표시합니다.
- 앱 버전을 v=83으로 올리고 index.html/manifest.json/app.js 버전을 맞췄습니다.


[mobile_18_home_worker_quick_info_memo_box]
- 기준 파일: mobile_17_home_worker_phone_quick_info.zip
- 홈 화면 근로자 간단 정보 팝업에서 사업자 항목을 제거했습니다.
- 홈 화면 근로자 간단 정보 팝업에서 근무형태 항목을 제거했습니다.
- 메모는 항상 보이는 메모장 영역으로 표시합니다.
- 메모가 없으면 등록된 메모 없음으로 표시합니다.
- 전화번호 클릭 시 tel: 전화 연결 기능은 유지합니다.
- 앱 버전을 v=84로 올리고 index.html/manifest.json/app.js 버전을 맞췄습니다.

[mobile_19_remove_fallback_login]
- 기준 파일: mobile_18_home_worker_quick_info_memo_box.zip
- 모바일 로그인은 서버 /api/auth/login 또는 /api/login 응답만 사용하도록 정리했습니다.
- 로그인 실패 시 /api/employees/snapshot을 직접 읽어 관리자 계정을 찾던 fallback을 제거했습니다.
- admin/1234, manager/1234 같은 모바일 내장 기본 계정 fallback을 제거했습니다.
- 자동 로그인은 저장된 서버 토큰이 /api/auth/me 또는 /api/me에서 유효할 때만 복원합니다.
- 서버 토큰이 없거나 만료되면 저장된 예전 사용자 snapshot으로 화면에 들어가지 않고 로그인 화면에 머뭅니다.
- 앱 버전을 v=86으로 올리고 index.html/manifest.json/app.js/manifest/sw 버전을 맞췄습니다.


## mobile_20_remove_login_test_account_hint

- 로그인 화면의 테스트 계정 안내 표시를 제거했습니다.
- 서버 연결 실패 안내에서 임시 테스트 계정 문구를 제거했습니다.
- 앱 버전을 v=86으로 갱신했습니다.

## mobile_22_home_responsive_layout_fix

- 기준 파일: mobile_20_remove_login_test_account_hint.zip
- mobile_21에서 발생한 홈 화면 상단 밀림 문제를 피하기 위해 전체 CSS가 유지된 mobile_20 기준에서 다시 수정했습니다.
- 로그인/근태관리/근로자등록/차량관리/동기화 화면의 기본 흐름을 건드리지 않고, 로그인 후 공통 레이아웃을 flex 기준으로 정리했습니다.
- 홈 화면은 본문 영역 안에서 반응형으로 채우고, 근로자 목록 카드 내부에서만 스크롤되게 정리했습니다.
- 하단 메뉴는 화면 아래에 고정된 위치감을 유지하되, 본문 높이 계산에서 겹치지 않도록 흐름 안에 배치했습니다.
- 앱 버전을 v=92로 올리고 index.html/manifest.json/app.js/sw 버전을 맞췄습니다.


## mobile_26_restore_status_cards_original.zip

- `mobile_22_home_responsive_layout_fix.zip` 기준으로 상태 카드/아이콘/사용자 표시 영역을 복구했습니다.
- `mobile_23`~`mobile_25`에서 적용한 상태 카드 아이콘/배경/사용자 표시 변경은 제외했습니다.
- 홈 반응형 레이아웃 수정은 유지했습니다.
- 앱 버전을 v=92로 올렸습니다.
