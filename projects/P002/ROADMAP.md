# P002 로드맵

## 0단계: 기준 문서 생성

목표:
- P002 프로젝트 기준을 GitHub에 저장한다.

작업:
- CURRENT.md 생성
- IDEA.md 생성
- STRUCTURE.md 생성
- RULES.md 생성
- MEMORY.md 생성
- TOOLS.md 생성
- ROADMAP.md 생성
- REFERENCES.md 생성

상태:
- 진행 중

## 1단계: connect-ai 구조 분석

목표:
- connect-ai를 P002 참고 소스로 분석한다.

확인할 부분:
- Ollama 연결 코드
- LM Studio 연결 코드
- 모델 자동 감지 방식
- 명령 입력 처리 방식
- 파일 생성/수정 기능
- 터미널 실행 기능
- Markdown 지식창고 구조
- GitHub 자동 저장 구조

산출물:
- `projects/P002/ANALYSIS_connect_ai.md`

## 2단계: P002 역할 AI 정의

목표:
- 1차 AI 직원 역할을 정의한다.

1차 역할:
- 대표비서 AI
- 개발 AI
- 지식관리 AI

2차 역할:
- 쇼핑몰 AI
- CS AI
- 이미지 AI
- 서버관리 AI

산출물:
- `projects/P002/AGENTS.md`

## 3단계: 명령 입력기 설계

목표:
- 사용자가 자연어로 업무를 지시하는 입력 구조를 만든다.

기능:
- 자유 명령 입력
- 역할 선택
- 초안 생성
- 승인 요청
- 저장
- 실행 기록 저장

산출물:
- `projects/P002/COMMAND_INPUT.md`

## 4단계: 지식 창고 설계

목표:
- 회사 문서와 프로젝트 문서를 저장하고 검색하는 구조를 만든다.

초기 분류:
- company
- p001
- p002
- cafe24
- products
- cs
- server
- image_prompts

산출물:
- `projects/P002/KNOWLEDGE.md`

## 5단계: 기억 저장소 설계

목표:
- 장기 기억, 현재 상태, 작업 이력, 명령 이력을 저장하는 구조를 만든다.

초기 방식:
- SQLite
- Markdown
- GitHub 백업

산출물:
- `projects/P002/MEMORY_SCHEMA.md`

## 6단계: 로컬 실행 테스트

목표:
- Ollama 또는 LM Studio와 연결해 기본 명령을 실행한다.

테스트:
- 모델 목록 조회
- 간단한 명령 응답
- 지식 문서 읽기
- Markdown 파일 생성
- GitHub 저장

## 7단계: 업무 확장

목표:
- 1인 기업 업무 기능을 붙인다.

확장 후보:
- Cafe24 상품등록 초안
- 고객 문의 답변 초안
- 이미지 프롬프트 생성
- ComfyUI 이미지 생성 연결
- n8n 자동화
- 서버 로그 요약

## 8단계: 대시보드 UI

목표:
- 미래형 대시보드 시안을 실제 UI로 만든다.

화면:
- 대시보드
- 명령 입력기
- AI 직원
- 지식 창고
- 기억 저장소
- 작업 기록
- 설정

## 현재 최우선 작업

1. P002 기준 문서 생성 완료
2. connect-ai 소스 구조 분석 시작
3. AGENTS.md 작성
4. KNOWLEDGE.md 작성
5. MEMORY_SCHEMA.md 작성
