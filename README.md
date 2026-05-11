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
