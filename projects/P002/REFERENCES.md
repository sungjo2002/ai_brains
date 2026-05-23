# P002 참고 자료

## connect-ai

주소:
https://github.com/wonseokjung/connect-ai.git

저장소 설명:
Antigravity / VS Code / Cursor에서 사용하는 1인 기업용 로컬 AI 작업 시스템 참고 소스.

P002에서 보는 의미:
- 개발 AI
- 지식 창고
- 기억 저장소
- GitHub 자동화
- Ollama / LM Studio 연결
- 파일 생성/수정
- 터미널 실행

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
- connect-ai를 그대로 복사하지 않는다.
- P002는 성조님 1인 기업 업무에 맞게 확장한다.
- 쇼핑몰, CS, 이미지 생성, Cafe24, ComfyUI, n8n은 별도 모듈로 추가한다.

## P002와 connect-ai 관계

```text
connect-ai
= 개발 AI + 지식창고 + GitHub 자동화 참고 모델

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
