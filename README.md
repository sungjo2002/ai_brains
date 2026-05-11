# ai_brains

개인 작업 저장소입니다.

## workforce 프로젝트 기준

현재 인력관리 프로그램은 PC, server, mobile 세 영역으로 나눠 관리합니다.

```text
workforce/
  pc/
  server/
  mobile/
  docs/
```

## 저장소 작업 규칙

사용자가 PC, server, mobile ZIP 파일을 올리면 아래 순서로 처리합니다.

```text
1. ZIP 내부 구조와 핵심 파일 확인
2. Python/JavaScript 문법 검사
3. DB, 백업, 실제 설정, 운영 키 같은 위험 파일 제외
4. 수정이 필요한 경우 새 번호 ZIP 생성
5. 저장소에 올려도 되는 안전 파일만 정리
6. 서버 또는 모바일 적용용 콘솔 명령어 제공
```

번호 규칙은 아래 기준을 사용합니다.

```text
PC: pc_번호_영문설명.zip
server: server_번호_영문설명.zip
mobile: mobile_번호_영문설명.zip
```

## 콘솔 명령어 제공 규칙

콘솔 명령어는 이 방식만 사용합니다.

```text
- ZIP 압축을 푼 뒤 파일이 이미 작업 폴더에 들어간 상태 기준
- 긴 압축 해제/백업/업로드 통합 명령어 방식 사용 안 함
- 한 줄씩 복사해서 입력할 수 있게 제공
- 모바일은 /root/apps/mobile_app 기준
- 서버는 /root/apps/green_api 기준
```

모바일 수정본 적용 명령어 기본 형식:

```bash
cd /root/apps/mobile_app
rm -rf /var/www/mobile_live/*
cp -r ./* /var/www/mobile_live/
chown -R www-data:www-data /var/www/mobile_live
find /var/www/mobile_live -type d -exec chmod 755 {} \;
find /var/www/mobile_live -type f -exec chmod 644 {} \;
systemctl restart nginx
systemctl status nginx --no-pager -l
```

서버 수정본 적용 명령어 기본 형식:

```bash
cd /root/apps/green_api
python3 -m py_compile app/permission_guard.py
python3 -m py_compile app/routes/mobile_auth.py
python3 -m py_compile app/routes/employees.py
python3 -m py_compile app/routes/vehicles.py
python3 -m py_compile app/routes/attendance_records.py
python3 -m py_compile app/routes/attendance_month_lock.py
systemctl restart green_api
systemctl status green_api --no-pager -l
curl -s http://127.0.0.1:8000/api/health
```

## 중요 보안 기준

이 저장소는 public 저장소이므로 아래 파일은 올리지 않습니다.

```text
*.db
*.sqlite
.env
data/backup/
data/config/app_settings.json
data/config/server_api.json
data/config/update_settings.json
__pycache__/
*.pyc
```

실제 운영 키는 코드에 직접 넣지 않고 PC 설정 파일 또는 서버 `.env`에서만 관리합니다.
