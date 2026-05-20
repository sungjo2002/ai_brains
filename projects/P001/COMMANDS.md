# COMMANDS

이 파일은 P001 프로젝트의 실행, 검사, 적용 확인 명령어를 기록한다.

## 콘솔 명령어 제공 원칙

- 서버 파일 또는 모바일 파일을 수정해 새 ZIP을 만들었으면 답변 마지막에 반드시 적용용 콘솔 명령어를 함께 제공한다.
- 콘솔 명령어는 사용자가 PC에서 ZIP 압축을 풀고, 압축 해제된 폴더를 VPS 작업 폴더에 이미 업로드한 상태를 기준으로 제공한다.
- VPS 콘솔 명령어에는 `unzip` 명령어를 넣지 않는다.
- 긴 압축 해제, 백업, 업로드 통합 명령어 방식은 사용하지 않는다.
- 한 줄씩 복사해서 입력할 수 있게 제공한다.
- 서버와 모바일 명령어를 섞지 않는다.
- 기본 적용 명령어와 문제 있을 때만 쓰는 추가 명령어를 분리한다.
- 수정 파일명과 작업 폴더명은 최신 번호 기준으로 맞춘다.

## 작업 폴더 기준

서버 수정본 업로드 위치 예시:

```text
/root/apps/server_번호_수정명/
```

모바일 수정본 업로드 위치 예시:

```text
/root/apps/mobile_번호_수정명/
```

운영 서버 위치:

```text
/root/apps/green_api
```

모바일 라이브 위치:

```text
/var/www/mobile_live
```

모바일 작업 위치:

```text
/root/apps/mobile_app
```

## Server 수정 후 기본 적용 형식

서버 수정본은 압축 해제된 폴더가 `/root/apps/server_번호_수정명/`에 업로드된 상태를 기준으로 한다.

```bash
cd /root/apps
```

```bash
cp -r /root/apps/server_번호_수정명/* /root/apps/green_api/
```

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

## Mobile 수정 후 기본 적용 형식

모바일 수정본은 압축 해제된 폴더가 `/root/apps/mobile_번호_수정명/`에 업로드된 상태를 기준으로 한다.

```bash
cd /root/apps/mobile_번호_수정명
```

```bash
node --check app.js
```

```bash
rm -rf /root/apps/mobile_app/*
```

```bash
cp -r /root/apps/mobile_번호_수정명/* /root/apps/mobile_app/
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

현재 서버 14 적용 폴더 예시:

```text
/root/apps/server_14_snapshot_auth_lock/
```

현재 모바일 19 적용 폴더 예시:

```text
/root/apps/mobile_19_remove_fallback_login/
```

현재 모바일 확인 주소 예시:

```text
https://sungjo2003.cafe24.com/mobile-live/?v=85
```
