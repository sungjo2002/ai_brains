# 인력관리 프로그램 작업 기록

기준일: 2026-05-12

## 1. 현재 최신 수정본

PC 최신 파일:
- pc_49_manual_sync_attendance_pull_fix.zip

모바일 최신 파일:
- mobile_16_attendance_retry_queue_fix.zip

서버 최신 파일:
- server_10_attendance_clear_tombstone_fix.zip

## 2. 이번 동기화 작업 완료 내용

### PC 완료

1. pc_48_sync_dirty_guard_fix.zip
- PC 동기화 상태값 저장 때문에 settings dirty가 다시 잡히던 문제 개선.
- 동기화 성공/실패 표시값 변경이 /api/employees/snapshot 반복 PUT으로 이어지지 않게 수정.
- 확인 결과, 서버 로그에서 PUT /api/employees/snapshot 반복이 멈춤.

2. pc_49_manual_sync_attendance_pull_fix.zip
- PC 상단 수동 동기화에 현재월 근태 서버 가져오기를 추가.
- 모바일에서 근태 저장 후 PC 상단 수동 동기화를 누르면 PC 근태 화면에 반영되도록 수정.
- 서버에서 가져온 근태를 PC 로컬에 반영하되, 다시 snapshot 반복 전송이 발생하지 않도록 server-sync 흐름으로 처리.

### 모바일 완료

1. mobile_15_attendance_save_dedupe_fix.zip
- 모바일 근태 저장 중복 요청 방지.
- 같은 근로자 + 같은 날짜 저장이 진행 중이면 추가 저장 차단.
- 같은 근로자 + 같은 날짜 + 같은 상태를 짧은 시간 안에 반복 저장하지 않도록 처리.
- 모바일 버전 v81 적용.
- service worker 등록을 APP_BUILD_VERSION 기준으로 통일.

2. mobile_16_attendance_retry_queue_fix.zip
- 모바일 근태 저장 실패 시 자동 재전송 기능 추가.
- 서버 연결 실패, 네트워크 끊김 등으로 저장 실패한 근태를 휴대폰 대기열에 보관.
- 앱 실행, 로그인, 수동 동기화, 연결 복구 시 자동 재전송.
- 같은 근로자 + 같은 날짜는 대기열에 여러 개 쌓지 않고 마지막 상태만 유지.
- 모바일 버전 v82 적용.
- 확인 결과, 모바일 저장과 해제 모두 서버로 정상 전송됨.

### 서버 완료

1. server_10_attendance_clear_tombstone_fix.zip
- 모바일에서 근태를 해제할 때 서버가 기록을 DELETE 해버려 PC가 해제 신호를 받을 수 없던 문제 수정.
- 해제 시 DELETE 대신 state='' 빈 상태 기록으로 저장.
- PC 수동 동기화 시 빈 상태 기록을 삭제 신호로 받아 PC 화면에서도 해당 근태 칸이 지워지는 흐름 확인.

## 3. 실제 확인 완료 결과

완료 확인:
- 모바일 v82 적용 정상.
- 모바일 근태 저장 -> 서버 POST /api/attendance/save 200 OK 확인.
- 모바일 근태 해제 -> 서버 POST /api/attendance/save 200 OK 확인.
- PC 상단 수동 동기화 -> GET /api/attendance/month 200 OK 확인.
- PC 화면에서 모바일 등록 근태 반영 정상.
- PC 화면에서 모바일 해제 근태 삭제 반영 정상.
- PC snapshot 반복 PUT 문제 개선 확인.

## 4. 서버 로그 확인 명령어

근태 저장/조회 확인:

journalctl -u green_api --since "3 minutes ago" --no-pager -l | grep -E "attendance/save|attendance/month"

PC snapshot 반복 확인:

journalctl -u green_api --since "10 minutes ago" --no-pager -l | grep "employees/snapshot"

전체 주요 동기화 확인:

journalctl -u green_api --since "5 minutes ago" --no-pager -l | grep -E "attendance/save|attendance/month|employees/snapshot|vehicles/logs|employees HTTP"

## 5. 서버 적용 기본 명령어

서버 수정본 적용 후 확인:

cd /root/apps/green_api
python3 -m compileall -q app
systemctl restart green_api
systemctl status green_api --no-pager -l
curl -s http://127.0.0.1:8000/api/health

주의:
- /root/apps/green_api 전체 삭제 금지.
- .env, .env.bak, .env.bak2, .venv 유지.
- app/ 교체와 필요한 파일만 적용.

## 6. 모바일 적용 기본 명령어

서버에는 node가 없으므로 node --check app.js는 서버에서 생략.

cd /root/apps/mobile_app
rm -rf /var/www/mobile_live/*
cp -r ./* /var/www/mobile_live/
chown -R www-data:www-data /var/www/mobile_live
find /var/www/mobile_live -type d -exec chmod 755 {} \;
find /var/www/mobile_live -type f -exec chmod 644 {} \;
systemctl restart nginx

모바일 실제 접속 주소:
- https://sungjo2003.cafe24.com/mobile-live/

PC 브라우저 모바일 확인 주소:
- https://sungjo2003.cafe24.com/mobile-live/?v=82

## 7. PC 확인 기준

PC 실행:
- run_app.bat 실행.

동기화 확인:
1. 모바일에서 근태 등록.
2. PC 상단 수동 동기화 클릭.
3. PC 월간 근태에 등록 내용 반영 확인.
4. 모바일에서 같은 근태 해제.
5. PC 상단 수동 동기화 클릭.
6. PC 월간 근태에서 해당 칸 삭제 확인.

## 8. 현재 남은 문제

현재 동기화 관련 큰 문제 없음.

완료 상태:
- 모바일 저장 정상.
- 모바일 해제 정상.
- 서버 저장/조회 정상.
- PC 수동 동기화 정상.
- PC 화면 반영 정상.
- 실패 저장 자동 재전송 정상.

다음 작업 후보:
1. 이번 완료 내역을 기준으로 불필요한 서버 README 파일 정리.
2. 오래된 서버 잔여 파일 보관 처리.
3. PC/모바일/서버 최신 파일 기준으로 다음 기능 수정 진행.

## 9. 주의할 점

- 실제 코드 수정은 사용자가 "수정해", "적용해", "파일 만들어줘", "ZIP 만들어줘"처럼 명확히 말했을 때만 진행.
- "하자", "할까", "다음은", "정리하자"는 우선 분석/계획으로 처리.
- 기능 조건, 권한 조건, 저장 조건, 동기화 조건, 계산 조건은 임의로 바꾸지 않음.
- 모바일 삭제 기능은 임의로 추가하지 않음.
- 권한 제한은 화면 숨김뿐 아니라 서버 API에서도 검사되어야 함.
