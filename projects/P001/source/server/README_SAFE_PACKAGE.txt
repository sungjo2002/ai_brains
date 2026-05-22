서버 수정본 안전 패키지 메모
- 모바일 근태 해제 요청(state empty/clear/delete/remove)은 삭제로 끝내지 않고 빈 상태 기록으로 저장합니다.
- PC가 서버 월간 근태를 가져올 때 빈 상태 기록을 해제 신호로 받아 PC 근태 칸을 삭제할 수 있습니다.
- 일반 근태 저장은 기존처럼 같은 근로자/날짜 기존 기록을 정리한 뒤 한 건만 저장합니다.
- bulk-save에서도 빈 상태 기록을 남겨 해제 동기화가 빠지지 않게 했습니다.
- .env와 .venv는 운영 서버 기존 파일을 유지하세요.
- 적용 확인 명령어는 아래 순서입니다.
cd /root/apps/green_api
python3 -m compileall -q app
systemctl restart green_api
systemctl status green_api --no-pager -l
curl -s http://127.0.0.1:8000/api/health

[server_11_snapshot_longtext_timeout_fix]
- 기준 파일: server_10_attendance_clear_tombstone_fix.zip
- PC 전체 스냅샷 저장소인 app_snapshots.payload_json을 MySQL LONGTEXT 기준으로 보강했습니다.
- 기존 운영 DB의 app_snapshots.payload_json 컬럼도 서비스 시작 시 LONGTEXT로 자동 보정하도록 했습니다.
- PC1에서 서버 전체 저장 후 PC2에서 서버 전체 불러오기를 할 때 급여/근태/차량 데이터가 많아도 일반 TEXT 용량 제한에 걸리지 않도록 했습니다.
- 근태 해제 tombstone 처리, 월마감, 권한, 차량 API 흐름은 기존 server_10 기준을 유지했습니다.
- 신분증/여권 원본 이미지와 신분증/여권 보정본 이미지는 서버 이미지 동기화 대상에 포함하지 않았습니다.
- 근로자 얼굴 사진 업로드/다운로드 API는 이번 수정 범위에 포함하지 않았습니다.

[server_12_snapshot_put_light_response]
- 기준 파일: server_11_snapshot_longtext_timeout_fix.zip
- 수정 목적: PC 전체 snapshot 저장 후 서버가 큰 payload를 다시 응답해 PC가 완료 문구까지 못 가는 문제 방지.
- 수정 내용:
  1) PUT /api/employees/snapshot 저장 성공 응답에서 전체 payload를 되돌려주지 않음.
  2) updated_at만으로 PC 저장 성공 처리가 가능하도록 응답을 가볍게 유지.
  3) GET /api/employees/snapshot은 PC2 복구를 위해 전체 payload 반환 유지.
  4) app_snapshots.payload_json LONGTEXT 보강 유지.
- 제외 유지: 근로자 얼굴 사진 파일, 신분증/여권 원본, 신분증/여권 보정본 이미지 동기화 제외.


[server_13_employee_delete_tombstone_fix]
- 기준 파일: server_12_snapshot_put_light_response.zip
- 수정 내용: 근로자 삭제 동기화 실패 보강. 삭제된 근로자가 서버 목록/snapshot에서 다시 살아나지 않도록 tombstone 처리와 실패 대기열 재시도 처리를 보강했습니다.
- 제외 유지: 근로자 얼굴 사진, 신분증/여권 원본, 신분증/여권 보정본 파일 동기화 제외.
- 확인 방법: PC1에서 근로자 삭제 후 동기화 실패 0건 확인, PC2 동기화 후 동일 근로자 삭제 상태 확인.

[server_14_snapshot_auth_lock]
- 기준 파일: server_13_employee_delete_tombstone_fix.zip
- 수정 내용: GET /api/employees/snapshot 조회에 권한 검사를 추가했습니다.
- PC 동기화 키(X-PC-Sync-Key) 또는 최고관리자 토큰이 있을 때만 전체 snapshot을 조회할 수 있습니다.
- 일반관리자 모바일 토큰과 로그인 없는 요청은 전체 snapshot 조회를 차단합니다.
- PUT /api/employees/snapshot 저장 권한, 근로자 삭제 tombstone, LONGTEXT 보강 흐름은 기존 server_13 기준을 유지했습니다.
- 확인 방법: 인증 없이 GET /api/employees/snapshot 호출 시 401, 일반관리자 토큰 호출 시 403, PC 동기화 키 또는 최고관리자 토큰 호출 시 200 확인.

[server_15_remove_default_admin_seed]
- 기준 파일: server_14_snapshot_auth_lock.zip
- 수정 내용: 서버 로그인 시 기본 관리자 계정을 자동 생성하던 로직을 비활성화했습니다.
- 목적: 프로그램 계정정보에 없는 manager 같은 기본 계정이 서버 DB에 다시 생기지 않게 막습니다.
- 기존 DB에 이미 남아 있는 manager 계정은 자동 삭제하지 않습니다. 운영자가 확인 후 직접 삭제합니다.
- PC 프로그램 계정정보/스냅샷에 있는 정상 관리자 계정 생성·갱신 흐름은 유지합니다.
- 확인 방법: manager 삭제 후 서버 재시작, manager가 다시 생기지 않는지 계정 목록 확인.
