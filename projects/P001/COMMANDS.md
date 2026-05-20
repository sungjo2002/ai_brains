# COMMANDS

이 파일은 P001 프로젝트의 실행, 검사, 적용 확인 명령어를 기록한다.

## PC 확인

```bash
run_app.bat
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

## Mobile 확인

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

권한 문제나 반영 이상이 있을 때만 권한 정리와 Nginx 재시작을 추가로 사용한다.

## 모바일 접속 기준

휴대폰 실제 실행 주소:

```text
https://sungjo2003.cafe24.com/mobile-live/
```

PC 브라우저에서 모바일 확인 주소:

```text
https://sungjo2003.cafe24.com/mobile-live/?v=번호
```
