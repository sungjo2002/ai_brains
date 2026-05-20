# FILES

이 파일은 P001 프로젝트에서 코딩 도구가 우선 확인할 핵심 파일 위치를 기록한다.

## PC

- `src/main_window.py`: 메인 창, 화면 전환, 공통 새로고침, 데이터 변경 후 화면 갱신 흐름
- `src/table_column_manager.py`: 표 컬럼 조절 저장/복원
- `src/pages/employee_page.py`: 근로자 관리 화면
- `src/pages/vehicle_page.py`: 차량 관리 화면
- `src/pages/business_page.py`: 사업자/사업장 관리 화면

## Server

- `app/routes/employees.py`: 근로자 관련 API
- `app/routes/vehicles.py`: 차량 관련 API
- `app/routes/attendance_records.py`: 근태 관련 API
- `app/routes/attendance_month_lock.py`: 월마감 관련 API
- `app/routes/mobile_auth.py`: 모바일 인증 관련 API
- `app/permission_guard.py`: 권한 검사

## Mobile

- `index.html`: 모바일 화면 구조
- `app.js`: 모바일 주요 로직
- `styles.css`: 모바일 화면 스타일

## 주의

실제 파일 위치는 업로드된 최신 ZIP 또는 `source/` 폴더 기준으로 다시 확인한다.
저장소 기록보다 실제 파일 구조가 최신이면 실제 파일 구조를 우선한다.
