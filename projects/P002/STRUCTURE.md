# P002 구조

## 전체 구조

```text
Antigravity / VS Code / Cursor
= 작업 공간 / IDE / AI 사무실 실행 공간

connect-ai
= 로컬 AI 작업자 참고 소스

Ollama
= 로컬 업무 AI 엔진

LM Studio
= 로컬 모델 테스트 및 OpenAI 호환 서버

ComfyUI
= 이미지 생성 엔진, 2차 이후 연결

GitHub
= 기준 문서, 작업 기록, 코드 저장소

지식 창고
= 회사 문서/프로젝트 문서/상품 자료 저장소

기억 저장소
= 장기 기억, 현재 상태, 작업 이력 저장소
```

## 프로그램 구성

```text
P002_1인기업_AI_사무실
├─ 명령 입력기
├─ AI 직원
│  ├─ 대표비서 AI
│  ├─ 개발 AI
│  ├─ 지식관리 AI
│  ├─ 쇼핑몰 AI
│  ├─ CS AI
│  └─ 이미지 AI
├─ 지식 창고
├─ 기억 저장소
├─ 작업 기록
├─ 승인 시스템
└─ 외부 연결
   ├─ Ollama
   ├─ LM Studio
   ├─ GitHub
   ├─ Cafe24
   ├─ ComfyUI
   ├─ n8n
   └─ Gmail / Calendar
```

## 폴더 구조 초안

```text
projects/P002/
├─ CURRENT.md
├─ IDEA.md
├─ STRUCTURE.md
├─ RULES.md
├─ MEMORY.md
├─ TOOLS.md
├─ ROADMAP.md
├─ REFERENCES.md
└─ modules/
   ├─ ollama/
   ├─ lmstudio/
   ├─ knowledge/
   ├─ memory/
   ├─ github/
   ├─ cafe24/
   ├─ comfyui/
   └─ automation/
```

## 저장소 분리 기준

- P001: 인력관리 / 근태 / 급여 시스템
- P002: 1인 기업 AI 사무실 / AI 자동화 시스템

P001과 P002는 서로 다른 프로젝트로 관리한다.
P002에서 P001 문서를 읽을 수는 있지만, P001 기준을 임의로 수정하지 않는다.

## 실행 방식 초안

1. 사용자가 명령 입력
2. 역할 AI 선택
3. 지식 창고 검색
4. 기억 저장소에서 사용자 기준 확인
5. Ollama 또는 LM Studio에 요청
6. 결과 생성
7. 승인 필요 여부 판단
8. 저장 또는 실행
9. GitHub에 기록
