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
1. ZIP 압축 해제
2. 내부 구조와 핵심 파일 확인
3. Python/JavaScript 문법 검사
4. DB, 백업, 실제 설정, 운영 키 같은 위험 파일 제외
5. 수정이 필요한 경우 새 번호 ZIP 생성
6. 저장소에 올려도 되는 안전 파일만 정리
7. 서버 또는 모바일 적용용 콘솔 명령어 제공
```

번호 규칙은 아래 기준을 사용합니다.

```text
PC: pc_번호_영문설명.zip
server: server_번호_영문설명.zip
mobile: mobile_번호_영문설명.zip
```

모바일 수정본을 적용할 때는 기본적으로 `/root/apps/mobile_app`에 압축을 풀고 `/var/www/mobile_live`로 배포하는 명령어를 제공합니다.

서버 수정본을 적용할 때는 기본적으로 `/root/apps/green_api`에 압축을 풀고 py_compile 확인 후 `green_api` 서비스를 재시작하는 명령어를 제공합니다.

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
