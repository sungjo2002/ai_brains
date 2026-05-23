# P002 사용 도구

## 핵심 도구

### Antigravity / VS Code / Cursor

역할:
- P002 작업 공간
- AI 작업자 실행 환경
- 코드/문서 수정 공간

### connect-ai

역할:
- 참고 소스
- 로컬 AI 작업자 구조 분석 대상
- Ollama / LM Studio 연결 방식 참고
- 파일 생성/수정, 터미널 실행, GitHub 자동 저장 방식 참고

### Ollama

역할:
- 로컬 LLM 실행 엔진
- 업무 AI, 개발 AI, 지식관리 AI 실행 후보

용도:
- 문서 작성
- 코드 보조
- 명령 분석
- 지식 창고 질의응답

### LM Studio

역할:
- 로컬 모델 테스트
- OpenAI 호환 API 서버
- 모델 비교 및 실험

용도:
- Qwen, Llama, Gemma, Mistral 계열 테스트
- 이미지 분석 가능 모델 테스트
- connect-ai 연결 테스트

### ComfyUI

역할:
- 이미지 생성 엔진
- 2차 이후 연결

용도:
- 상품 썸네일 생성
- 상세페이지 배너 생성
- 이미지 생성 프롬프트 실행

### GitHub

역할:
- 기준 문서 저장
- 작업 이력 백업
- 코드 관리
- P001/P002 프로젝트 기준 저장소

현재 저장소:
- `sungjo2002/ai_brains`

### n8n

역할:
- 24시간 자동화 워크플로우
- 2차 이후 연결

용도:
- 메일 확인
- 정기 작업
- 알림 발송
- 외부 API 연결

## 향후 연결 도구

### Cafe24 API

용도:
- 상품 등록
- 상품 수정
- 상품 조회
- 쇼핑몰 자동화

주의:
- 실제 상품 등록/수정/삭제는 승인 후 실행한다.

### Gmail / Calendar

용도:
- 고객 문의 확인
- 일정 확인
- 업무 알림

### 서버 / VPS

용도:
- 24시간 백그라운드 실행
- API 서버
- 자동화 작업 실행
- 로그 확인

## 1차 연결 우선순위

1. GitHub
2. connect-ai 소스 분석
3. Ollama
4. LM Studio
5. Markdown 지식 창고
6. SQLite 기억 저장소

## 2차 연결 우선순위

1. ComfyUI
2. Cafe24 API
3. n8n
4. Gmail
5. 서버/VPS

## 도구별 판단

```text
Ollama / LM Studio = 글, 코드, 분석, 업무 지시 처리
ComfyUI = 이미지 생성
GitHub = 저장과 기준 문서 관리
n8n = 자동화 스케줄과 외부 연결
SQLite = 기억 저장소
Markdown = 지식 창고 원본 문서
```
