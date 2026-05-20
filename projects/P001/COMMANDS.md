# COMMANDS

이 파일은 P001 프로젝트의 실행, 검사, 적용 확인 명령어를 기록한다.

## 콘솔 명령어 제공 원칙

- 서버 파일 또는 모바일 파일을 수정해 새 ZIP을 만들었으면 답변 마지막에 반드시 적용용 콘솔 명령어를 함께 제공한다.
- 콘솔 명령어는 무조건 짧게 제공한다.
- 한 번에 필요한 최소 명령어만 제공하고, 설명은 명령어 위아래로 길게 붙이지 않는다.
- 긴 한 줄 Python 명령어는 사용하지 않는다.
- 긴 heredoc 스크립트는 사용자가 먼저 요청했을 때만 제공한다.
- DB 확인이나 DB 수정이 필요하면 긴 명령어 대신 Python 대화형 모드에서 짧은 줄을 여러 번 입력하는 방식으로 제공한다.
- 여러 줄 스크립트는 사용자가 요청했을 때만 제공한다.
- 콘솔 명령어는 사용자가 PC에서 ZIP 압축을 풀고, 압축 해제된 파일을 실제 VPS 작업 폴더에 이미 업로드한 상태를 기준으로 제공한다.
- VPS 콘솔 명령어에는 `unzip` 명령어를 넣지 않는다.
- 중간 적용 폴더 예시인 `/root/apps/server_번호_수정명/`, `/root/apps/mobile_번호_수정명/` 기준 명령어를 사용하지 않는다.
- 긴 압축 해제, 백업, 업로드 통합 명령어 방식은 사용하지 않는다.
- 한 줄씩 복사해서 입력할 수 있게 제공한다.
- 서버와 모바일 명령어를 섞지 않는다.
- 기본 적용 명령어와 문제 있을 때만 쓰는 추가 명령어를 분리한다.

## 실제 VPS 폴더 기준

서버 API 실제 위치:

```text
/root/apps/green_api
```

모바일 작업 폴더 실제 위치:

```text
/root/apps/mobile_app
```

모바일 라이브 실제 위치:

```text
/var/www/mobile_live
```

구버전 또는 별도 앱 가능성 있는 위치:

```text
/root/apps/green_app
```

## 업로드 기준

서버 수정본은 PC에서 ZIP 압축을 푼 뒤, 압축 해제된 서버 파일들을 아래 위치에 직접 업로드한다.

```text
/root/apps/green_api
```

모바일 수정본은 PC에서 ZIP 압축을 푼 뒤, 압축 해제된 모바일 파일들을 아래 위치에 직접 업로드한다.

```text
/root/apps/mobile_app
```

업로드 후 VPS 콘솔에서는 복사 명령어를 최소화하고, 검사와 재시작 또는 라이브 반영만 진행한다.

## Server 수정 후 기본 적용 형식

서버 수정본이 `/root/apps/green_api/`에 이미 업로드된 상태를 기준으로 한다.

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

## Server 추가 확인

서버 API 외부 확인이 필요할 때만 사용한다.

```bash
curl -i https://sungjo2003.cafe24.com/api/employees/snapshot
```

## Mobile 수정 후 기본 적용 형식

모바일 수정본이 `/root/apps/mobile_app/`에 이미 업로드된 상태를 기준으로 한다.

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
cp -r /root/apps/mobile_app/* /var/www/mobile_live/
```

## Mobile 권한 문제 또는 반영 이상 시 추가

```bash
chown -R www-data:www-data /var/www/mobile_live
```

```bash
find /var/www/mobile_live -type d -exec chmod 755 {} \;
```

```bash
find /var/www/mobile_live -type f -exec chmod 644 {} \;
```

Nginx 설정을 바꿨거나 반영이 이상할 때만 재시작한다.

```bash
systemctl restart nginx
```

## PC 확인

```bash
run_app.bat
```

## 모바일 접속 기준

휴대폰 실제 실행 주소:

```text
https://sungjo2003.cafe24.com/mobile-live/
```

PC 브라우저에서 모바일 확인 주소:

```text
https://sungjo2003.cafe24.com/mobile-live/?v=번호
```

`v=번호`는 캐시 회피와 새 파일 확인용이다.
PC 확인은 PC 프로그램 확인이 아니라 PC 브라우저에서 모바일 웹을 확인하는 뜻이다.

## 현재 버전 예시

현재 서버 실제 업로드 위치:

```text
/root/apps/green_api
```

현재 모바일 실제 업로드 위치:

```text
/root/apps/mobile_app
```

현재 모바일 확인 주소 예시:

```text
https://sungjo2003.cafe24.com/mobile-live/?v=85
```
