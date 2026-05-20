# COMMANDS

이 파일은 P001 프로젝트의 실행, 검사, 적용 확인 명령어를 기록한다.

## 콘솔 명령어 기준

- 콘솔 명령어는 ZIP 압축을 푼 뒤 파일이 이미 작업 폴더에 들어간 상태를 기준으로 제공한다.
- 긴 압축 해제, 백업, 업로드 통합 명령어 방식은 사용하지 않는다.
- 한 줄씩 복사해서 입력할 수 있게 제공한다.
- 서버와 모바일 명령어를 섞지 않는다.
- 기본 명령어와 문제 있을 때만 쓰는 명령어를 분리한다.

## PC 확인

```bash
run_app.bat
```

## Server 위치

```text
/root/apps/green_api
```

## Server 확인

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

## Mobile 위치

```text
/root/apps/mobile_app
```

## Mobile 기본 확인

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
