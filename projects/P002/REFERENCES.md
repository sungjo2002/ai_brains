# P002 참고 자료

## connect-ai

### 실제 사용 저장소

주소:
https://github.com/sungjo2002/connect-ai.git

의미:
성조님이 현재 Antigravity에서 실제로 사용 중인 connect-ai 프로그램 저장소다.
P002에서 connect-ai를 분석하거나 수정할 때는 이 저장소를 1차 기준으로 본다.

### 원본/참고 저장소

주소:
https://github.com/wonseokjung/connect-ai.git

의미:
connect-ai의 원본 또는 참고 저장소로 본다.
성조님 실제 작업 기준은 `sungjo2002/connect-ai`를 우선한다.

## 저장소 설명

Antigravity / VS Code / Cursor에서 사용하는 1인 기업용 로컬 AI 작업 시스템 참고 소스다.
Ollama / LM Studio와 연결해 로컬 AI 작업자처럼 사용한다.

P002에서 보는 의미:
- 개발 AI
- 지식 창고
- 기억 저장소
- GitHub 자동화
- Ollama / LM Studio 연결
- 파일 생성/수정
- 터미널 실행
- Antigravity 작업 보조

참고할 부분:
1. Ollama 연결 방식
2. LM Studio 연결 방식
3. 모델 자동 감지 방식
4. 명령 입력 처리 구조
5. 파일 생성/수정 기능
6. Markdown 위키/지식창고 구조
7. GitHub 자동 저장 구조
8. Antigravity / VS Code / Cursor 확장 구조

주의할 점:
- P002 분석 기준은 성조님 실제 사용 저장소 `sungjo2002/connect-ai`를 우선한다.
- 원본 `wonseokjung/connect-ai`는 비교/참고용으로만 본다.
- connect-ai를 그대로 복사하지 않는다.
- P002는 성조님 1인 기업 업무에 맞게 확장한다.
- 쇼핑몰, CS, 이미지 생성, Cafe24, ComfyUI, n8n은 별도 모듈로 추가한다.

## P002와 connect-ai 관계

```text
sungjo2002/connect-ai
= 성조님이 실제 Antigravity에서 쓰는 로컬 AI 작업자

wonseokjung/connect-ai
= 원본/참고 저장소

P002
= 쇼핑몰 + 개발 + 이미지 + 고객응대 + 서버관리 + 지식창고 + 기억저장소를 묶은 1인 기업 AI 사무실
```

## 미래형 대시보드 시안

대화에서 생성한 디자인 방향:
- 미래형 다크 대시보드
- 명령 입력기 중심
- AI 직원 패널
- 지식 창고
- 기억 저장소
- 최근 작업 기록
- 자동화 흐름
- Ollama / LM Studio / 서버 상태 표시

추후 실제 UI 설계 문서:
- `projects/P002/UI_DASHBOARD.md`

## 관련 프로젝트

### P001

설명:
인력관리 / 근태 / 급여 시스템

관계:
P002는 P001 문서를 읽고 개발/관리 보조를 할 수 있지만, P001 기준은 `projects/P001/` 문서를 우선한다.

### P002

설명:
1인 기업 AI 사무실 / AI 자동화 시스템

관계:
현재 새로 시작한 프로젝트이며, 모든 기준 문서는 `projects/P002/`에 저장한다.
