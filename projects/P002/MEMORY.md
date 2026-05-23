# P002 기억 저장소 설계

## 목적

P002의 기억 저장소는 AI 직원들이 성조님의 업무 기준, 프로젝트 상태, 반복 작업 규칙, 작업 이력을 기억하고 다음 작업에 반영하도록 하는 장기 기억 구조다.

## 지식 창고와 기억 저장소의 차이

```text
지식 창고 = 회사 서류 보관함
기억 저장소 = AI 직원의 장기 기억
작업 기록 = 업무 일지
현재 상태 = 지금 책상 위에 펼쳐둔 자료
```

## 기억 저장소 4분류

### 1. 장기 기억

바뀌기 전까지 유지되는 고정 기준이다.

예시:
- 성조님은 한국어 답변을 선호한다.
- 설명은 요약 먼저 원한다.
- “기억해”는 AI 메모리에 저장한다는 뜻이다.
- “저장해”는 GitHub 저장소에 저장한다는 뜻이다.
- P001은 GitHub `projects/P001/` 문서를 우선한다.
- P002 기준 저장소는 `sungjo2002/ai_brains`다.
- P002 기준 문서는 `projects/P002/`에 저장한다.

### 2. 지식 문서 기억

회사와 프로젝트의 문서 자료를 의미 기반으로 검색하기 위한 기억이다.

예시:
- Cafe24 상품 등록 규칙
- SEO 제목 규칙
- P001 CURRENT.md / RULES.md / TASKS.md
- P002 CURRENT.md / RULES.md / ROADMAP.md
- 서버 명령어
- 상품 스펙
- 고객 응대 문구
- 인터넷 자료수집 Markdown 문서

### 3. 작업 이력

언제 무엇을 했는지 저장한다.

예시:
- P002 기준 문서 생성
- connect-ai 구조 확인
- Ollama 모델 다운로드 및 경로 설정
- 직원별 모델 자동 배정
- Markdown 지식창고 연결
- 인터넷 자료수집 기능 추가
- GitHub 문서 업데이트

### 4. 현재 상태

현재 진행 중인 프로젝트와 다음 작업을 저장한다.

예시:
- 현재 프로젝트: P002
- 현재 최신 생성본: 25_web_keyword_research_connect.zip
- 확인 완료: 24_knowledge_markdown_connect.zip
- 확인 전: 25_web_keyword_research_connect.zip
- 다음 작업: 25번 자료수집 기능 실제 확인

## 현재 확인된 Ollama 모델

```text
llama3.2-vision:latest   이미지 분석용
nomic-embed-text:latest   지식창고 검색용
qwen2.5-coder:3b          개발 AI / 코드용
llama3.2:3b               대표비서 / 빠른 분류용
gemma4:latest             쇼핑몰 / 마케팅 / 콘텐츠용
gemma4:e2b                CS / 기억 / 정산용
```

## 직원별 모델 기억

```text
대표비서 AI      → llama3.2:3b
쇼핑몰 AI        → gemma4:latest
CS AI            → gemma4:e2b
이미지 AI        → gemma4:latest
개발 AI          → qwen2.5-coder:3b
지식관리 AI      → gemma4:latest
기억관리 AI      → gemma4:e2b
정산 AI          → gemma4:e2b
자동화 AI        → llama3.2:3b
마케팅 AI        → gemma4:latest
콘텐츠 AI        → gemma4:latest
```

전용 모델:

```text
nomic-embed-text = 지식창고 검색용
llama3.2-vision:latest = 이미지 분석용
이미지 생성 = ComfyUI / Stable Diffusion에서 처리 예정
```

## 저장 방식 초안

처음에는 단순하게 시작한다.

```text
SQLite = 기억, 설정, 작업 이력
Markdown = 기준 문서와 지식 창고
GitHub = 백업과 기준 문서 저장
벡터 DB = 2차 이후 의미 검색용
```

## DB 테이블 초안

```text
memory_items
- id
- project_code
- memory_type
- title
- content
- source
- importance
- status
- created_at
- updated_at

command_history
- id
- project_code
- command_text
- selected_agent
- result_summary
- action_taken
- created_at

current_state
- project_code
- key
- value
- updated_at
```

## 기억 저장 원칙

- 중요한 기억은 사용자 승인 후 저장한다.
- 프로젝트별로 기억을 분리한다.
- P001 기억과 P002 기억을 섞지 않는다.
- 출처와 날짜를 함께 저장한다.
- 오래된 기준은 폐기하지 말고 `deprecated` 상태로 표시한다.
- 최신 기준과 오래된 기준이 충돌하면 최신 기준을 우선한다.

## P002 초기 기억

- P002는 1인 기업 AI 사무실 프로젝트다.
- P002 기준 저장소는 `sungjo2002/ai_brains`다.
- connect-ai는 프로그램 구조 참고 대상이다.
- Antigravity / VS Code / Cursor 안에서 사용하는 AI 작업자 구조를 참고한다.
- Ollama와 LM Studio는 로컬 AI 엔진이다.
- ComfyUI는 이미지 생성 엔진으로 2차 이후 연결한다.
- 1차 목표는 대시보드보다 지식창고/기억저장소/명령입력 기반이다.
- 24번은 지식창고 Markdown 연결 확인 완료다.
- 25번은 인터넷 키워드 자료수집 기능 추가본이며 아직 확인 전이다.
