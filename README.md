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

## 수정 실행 규칙

아래 표현은 분석, 계획, 정리 요청으로만 처리합니다.
실제 코드 수정, TXT 수정, ZIP 생성은 하지 않습니다.

```text
하자
할까
정리하자
차례대로 수정하자
순서대로 하자
어떨까
```

실제 수정은 사용자가 아래처럼 명확히 말했을 때만 진행합니다.

```text
수정해
적용해
파일 만들어줘
생성해
ZIP 만들어줘
```

실제 수정 전에는 먼저 `수정 대기`를 출력하고 아래 항목만 짧게 정리합니다.

```text
수정 대상
수정 이유
수정 범위
생성될 파일명
확인 방법
```

## 콘솔 명령어 제공 규칙

콘솔 명령어는 이 방식만 사용합니다.

```text
- ZIP 압축을 푼 뒤 파일이 이미 작업 폴더에 들어간 상태 기준
- 긴 압축 해제/백업/업로드 통합 명령어 방식 사용 안 함
- 한 줄씩 복사해서 입력할 수 있게 제공
- 서버와 모바일 명령어를 섞지 않음
- 기본 명령어와 문제 있을 때만 쓰는 명령어를 분리
```

## 서버 수정본 적용/확인 기본 명령어

서버 적용 위치:

```text
/root/apps/green_api
```

서버 명령어는 아래 순서로 고정합니다.
긴 `python3 -m py_compile app/...` 나열 대신 전체 검사 명령어를 사용합니다.

```bash
cd /root/apps/green_api
```

```bash
python3 -m compileall -q app
```

```bash
systemctl restart green_api
```

```bash
systemctl status green_api --no-pager -l
```

```bash
curl -s http://127.0.0.1:8000/api/health
```

## 모바일 앱 수정본 적용/확인 기본 명령어

모바일 앱 적용 위치:

```text
/root/apps/mobile_app
```

모바일 기본 적용은 보통 아래 4줄만 사용합니다.

```bash
cd /root/apps/mobile_app
```

```bash
node --check app.js
```

```bash
rm -rf /var/www/mobile_live/*
```

```bash
cp -r ./* /var/www/mobile_live/
```

권한 문제, 403, 반영 이상이 있을 때만 아래 명령어를 추가로 사용합니다.

```bash
chown -R www-data:www-data /var/www/mobile_live
```

```bash
find /var/www/mobile_live -type d -exec chmod 755 {} \;
```

```bash
find /var/www/mobile_live -type f -exec chmod 644 {} \;
```

Nginx 설정을 바꿨거나 반영이 이상할 때만 재시작합니다.

```bash
systemctl restart nginx
```

## 모바일 확인 주소 기준

휴대폰 실제 실행 주소:

```text
https://sungjo2003.cafe24.com/mobile-live/
```

PC 브라우저에서 모바일 수정본 확인 주소:

```text
https://sungjo2003.cafe24.com/mobile-live/?v=번호
```

여기서 `v=번호`는 캐시 회피와 새 파일 확인용입니다.
PC 확인은 PC 프로그램 확인이 아니라 PC 브라우저에서 모바일 웹을 확인하는 뜻입니다.

## PC 수정본 확인 기준

PC는 서버처럼 콘솔 적용이 아니라 실행 확인 기준으로 관리합니다.

```text
run_app.bat 실행
프로그램 로그인 확인
수정한 화면 확인
서버 동기화 확인
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

## 최근 정리 상태

현재 기준으로 저장소 README에는 아래 내용까지 반영되어 있어야 합니다.

```text
- 수정 실행 규칙: 하자/정리하자는 분석만, 수정해/적용해부터 실제 수정
- 서버 명령어: python3 -m compileall -q app 기준
- 모바일 명령어: 기본 4줄, 권한/Nginx는 문제 있을 때만
- 서버/모바일/PC 기준 분리
- 콘솔 명령어는 한 줄씩 간단히 제공
```
