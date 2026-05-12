# workforce README

이 파일은 인력관리 프로그램의 현재 작업 상태를 기록한다.

기준일: 2026-05-12

## 최신 상태

- PC 최신 수정본: pc_11_korean_weekday_date_label_fix.zip
- 서버 최신 수정본: server_10_attendance_clear_tombstone_fix(2).zip
- 모바일 최신 수정본: mobile_16_attendance_retry_queue_fix(2).zip
- PC 수정본 번호는 pc_69 이후 새 구간으로 다시 시작했으며 현재 새 구간 기준 pc_11까지 진행했다.
- 현재 PC 작업은 화면 안정화, 표 컬럼 사용성, 홈화면 세부 UI 정리 중심으로 진행 중이다.
- 깜빡임 문제는 일부 개선됐지만 완성된 홈 화면의 잔깜빡임은 보류 상태다.
- 모바일/서버는 근태 저장, 해제, 재전송, tombstone 처리 기준으로 안정화된 상태다.

## 번호 규칙

- PC 수정본은 새 구간 기준 pc_1부터 다시 시작했다.
- 다음 PC 수정본은 pc_12부터 이어간다.
- 모바일 수정본은 기존 번호를 유지한다.
- 서버 수정본은 기존 번호를 유지한다.
- 저장소 README/GitHub 저장은 사용자가 "저장해", "저장소에 저장해", "README 저장해"처럼 명확히 말할 때만 진행한다.
- 사용자가 "수정해"라고 하면 ZIP 파일만 수정/생성하고 저장소에는 자동 저장하지 않는다.

## 최신 파일 기준

### PC

1. pc_1_all_pages_column_resize_default_width_fix.zip
- 근태관리와 급여관리를 제외한 표 페이지의 컬럼 조절 기능과 기본 컬럼 폭 재계산을 진행했다.
- 공통 컬럼 조절 관리 파일 src/table_column_manager.py를 추가했다.
- 홈화면, 근로자 목록, 사업자 관리, 차량 관리, 환경설정 표 컬럼 조절을 적용했다.
- 기본 컬럼 폭을 헤더와 셀 글자 길이 기준으로 다시 계산하도록 했다.
- 조절한 컬럼 폭을 local_ui_settings와 QSettings에 같이 저장하도록 했다.

2. pc_2_home_kpi_icon_background_remove_fix.zip
- 홈화면 KPI/상태 카드 아이콘 뒤 원형/배지 배경 제거를 시도했다.
- 홈화면 카드 쪽 아이콘 표시 스타일만 수정했다.

3. pc_3_employee_summary_icon_background_remove_fix.zip
- 근로자 관리 상단 상태 요약 카드 아이콘 배경 제거를 진행했다.
- 원형 배경이 포함된 아이콘 대신 배경 없는 선형 아이콘으로 정리했다.

4. pc_4_selected_person_number_badge_hover_active_fix.zip
- 오른쪽 선택 인원 상세의 번호 배지를 QLabel에서 hover/click 효과가 가능한 버튼형 배지로 변경했다.
- 기본/마우스 올림/누름/선택 상태 색상 효과를 시도했다.

5. pc_5_selected_person_number_badge_hover_visible_fix.zip
- 번호 배지가 항상 선택 상태로 고정되어 hover/pressed 변화가 안 보이는 문제를 보강했다.
- 클릭 후 계속 진하게 고정되지 않게 수정했다.

6. pc_6_selected_person_number_badge_active_state_fix.zip
- 번호 배지의 active 상태를 다시 유지 가능하게 수정했다.
- 기본/hover/pressed/active 색상 차이를 더 키웠다.

7. pc_7_selected_person_number_badge_event_style_fix.zip
- QSS :hover/:pressed/:checked 방식 대신 전용 클래스와 마우스 이벤트로 직접 색상 변경을 시도했다.
- enterEvent, leaveEvent, mousePressEvent, mouseReleaseEvent에서 직접 setStyleSheet/update/repaint 처리했다.

8. pc_8_selected_person_detail_card_hover_active_fix.zip
- 번호 배지 단독 효과 대신 선택 인원 상세 카드 전체에 hover/active 효과를 적용하는 방식으로 변경했다.
- HomeSelectedDetailCard 전용 클래스를 추가하고 paintEvent로 카드 배경/테두리/왼쪽 세로선을 직접 그리도록 했다.

9. pc_9_selected_person_detail_color_stronger_fix.zip
- 선택 인원 상세 카드와 번호 배지의 강조 색상을 전체적으로 더 진하게 조정했다.
- 사용자가 올린 pc_9_selected_person_detail_color_stronger_fix(1).zip 확인 결과 pc_9 기반은 맞지만 __pycache__/.pyc가 포함되어 있었다.
- 추가로 상태 카드 쪽 파일인 employee_page.py, styles.py, widgets.py 변경도 포함되어 있었다.

10. pc_10_selected_person_detail_effect_remove_fix.zip
- 선택 인원 상세 카드 전체 hover/pressed/active 효과를 제거했다.
- 왼쪽 파란 세로선 효과와 paintEvent 방식, 자식 위젯 이벤트 감시를 제거했다.
- 0001 번호 배지를 단순 표시용 QLabel 배지로 되돌렸다.
- 번호 배지는 기본 연한 파란색 표시만 유지했다.
- 캐시 파일 제거 완료.

11. pc_11_korean_weekday_date_label_fix.zip
- 상단 날짜 표시를 영어 요일에서 한글 요일로 변경했다.
- 기존: 2026-05-12 (Tue)
- 변경: 2026-05-12 (화)
- 날짜 표시 공통 함수 format_korean_top_date()를 추가했다.
- 최초 상단바 생성 시와 새로고침/동기화 후 날짜 갱신 시에도 한글 요일을 유지하도록 했다.

### 모바일

- 최신 수정본: mobile_16_attendance_retry_queue_fix(2).zip
- 모바일 근태 저장 실패 시 자동 재전송 기능을 추가했다.
- 서버 연결 실패, 네트워크 끊김 등으로 저장 실패한 근태를 휴대폰 대기열에 보관한다.
- 앱 실행, 로그인, 수동 동기화, 연결 복구 시 자동 재전송한다.
- 같은 근로자 + 같은 날짜는 대기열에 여러 개 쌓지 않고 마지막 상태만 유지한다.
- 모바일 버전 v82 기준이다.
- 모바일 저장과 해제 모두 서버로 정상 전송 확인된 상태다.

### 서버

- 최신 수정본: server_10_attendance_clear_tombstone_fix(2).zip
- 모바일에서 근태를 해제할 때 서버가 기록을 DELETE 해버려 PC가 해제 신호를 받을 수 없던 문제를 수정했다.
- 해제 시 DELETE 대신 state='' 빈 상태 기록으로 저장한다.
- PC 수동 동기화 시 빈 상태 기록을 삭제 신호로 받아 PC 화면에서도 해당 근태 칸이 지워지는 흐름을 확인했다.

## 완료된 큰 흐름

- 배너 관련 문제 일부 개선 완료.
  - 홈 배너 빈 배지 박스 제거.
  - 배너 늦게 표시되는 느낌 개선.
  - 페이지별 배너 정상 표시 확인.
- 왼쪽 메뉴 클릭 시 흰 화면 깜빡임은 상당 부분 개선 완료.
- 로그인 후 홈 화면이 뜨기 전 빈 화면 깜빡임은 개선 완료.
- 로그인 화면 디자인 정리 완료.
  - 2번 시안 방향 적용.
  - 기존 프로그램 로고 사용.
  - 제목을 관리자 로그인으로 변경.
  - 설명 문구 삭제.
  - 전체 크기 축소.
  - 로고 크기 재조정.
- 급여관리 화면 보강 완료.
  - 우측 이중 스크롤 제거 보강.
  - 급여표 로딩 속도 개선.
  - 급여관리 전체 화면이 외부 스크롤처럼 움직이는 문제 보강.
- 홈화면 인원 목록에서 표시번호를 맨 앞으로 이동하고 제목을 번호로 변경 완료.
- 근로자 목록에서 이름, 영문이름 칸 폭이 너무 좁은 문제 1차 보강 완료.
- 모바일 저장/해제/재전송 흐름 정상 확인.
- 서버 근태 해제 tombstone 흐름 정상 확인.

## 현재 확인 필요

- pc_11 기준 실제 실행 확인 필요.
- 상단 날짜가 2026-05-12 (화) 형식으로 보이는지 확인한다.
- pc_10에서 선택 인원 상세 hover/active 효과가 제거되고 기본 표시로 돌아갔는지 확인한다.
- pc_1 이후 컬럼 조절 기능이 모든 적용 대상 페이지에서 정상인지 확인한다.
- 컬럼 조절 후 프로그램 재시작 시 저장값이 복원되는지 확인한다.
- 홈화면/근로자 관리/사업자 관리/차량 관리/환경설정 표 기본 칸 크기와 글자 가독성을 확인한다.
- 상태 카드 아이콘 배경 제거가 홈화면과 근로자 관리 모두에서 맞게 보이는지 확인한다.

## 다음 작업 후보

1. pc_11 실제 실행 확인 후 날짜 한글 요일 적용 여부 확인.
2. 선택 인원 상세 영역은 효과 제거 상태로 유지할지, 단순 배지 색만 조정할지 결정.
3. 컬럼 저장/복원이 실패하는 페이지가 있으면 해당 표의 저장 키와 초기 레이아웃 적용 순서를 다시 확인.
4. 표 기본 폭이 넓거나 좁은 페이지가 있으면 해당 표만 기본 폭 재조정.
5. 완성된 홈 화면에서 보이는 잔깜빡임은 다음 순서로 보류.
6. 시작/종료 속도 개선은 레이아웃/표 사용성 정리 후 진행.

## 적용/확인 명령어 기준

### PC 확인

run_app.bat

### 서버 적용/확인

cd /root/apps/green_api
python3 -m compileall -q app
systemctl restart green_api
systemctl status green_api --no-pager -l
curl -s http://127.0.0.1:8000/api/health

### 모바일 적용/확인

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

## 보류

- 완성된 홈 화면에서 보이는 잔깜빡임은 다음으로 보류.
- 시작/종료 속도 개선은 레이아웃/표 사용성 정리 후 진행.
- 모바일 고도화, 서버 동기화 고도화, OCR 고도화는 PC 1차 정리 후 진행.

## 오류/주의

- pc_64는 표 컬럼 자동 보정과 사용자 조절이 충돌하여 실패로 판단한다.
- pc_65는 홈화면 하단 스크롤과 현재 상태 컬럼 조절 불가 문제가 남아 있었다.
- pc_66은 여러 컬럼이 같이 움직이는 부작용이 있었다.
- pc_67은 재시작 후 컬럼 폭 저장 복원이 되지 않았다.
- pc_68은 저장은 시도했지만 초기 레이아웃 보정에 의해 저장값이 밀리는 문제가 있었다.
- pc_69도 사용자 확인 기준 재시작 후 저장값 복원이 되지 않았다.
- pc_1은 공통 컬럼 조절 방식으로 다시 정리한 첫 수정본이므로 실제 화면 확인이 필요하다.
- pc_4~pc_9의 선택 인원 상세 효과 시도는 실제 화면에서 체감이 약하거나 적용 위치가 불확실했다.
- pc_10에서 선택 인원 상세 효과를 제거하고 단순 표시 방식으로 되돌렸다.
- 표 컬럼 조절 수정 시 자동 폭 보정이 사용자의 마우스 조절 중 끼어들면 안 된다.
- 표 전체 폭은 화면 안에 고정해야 하며, 사용자가 조절하는 컬럼 경계만 움직여야 한다.
- 경계선은 보이게 하되 기존 표 색보다 진하면 안 된다.
- 기능 조건, 저장 조건, 동기화 조건, 계산 조건, 권한 조건은 건드리지 않는다.
- 근태관리와 급여관리는 전체 컬럼 조절 작업에서 제외했다.
- 저장소 기록보다 실제 업로드 파일과 사용자가 확인한 결과를 우선한다.
