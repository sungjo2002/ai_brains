# P002 현재 상태

최종 갱신: 2026-05-23

## 프로젝트명

P002 1인 기업 AI 시스템

## 저장소 기준

```text
기준 저장소: sungjo2002/ai_brains
P002 기준 문서 위치: projects/P002/
현재 기준 파일: projects/P002/CURRENT.md
```

참고/소스 관련:

```text
connect-ai는 P002 프로그램 구조 참고 대상이다.
P002 기준 문서와 작업 상태 저장은 sungjo2002/ai_brains/projects/P002/를 우선한다.
```

## 현재 목표

대표가 채팅창에 지시하면 대표비서 AI가 내용을 분석하고, AI 직원 10명 중 담당자를 자동 배정한 뒤 Ollama / LM Studio / 지식창고 / 기억저장소 / GitHub / 인터넷 자료수집 기능으로 업무를 처리하는 1인 기업용 AI 자동화 프로그램을 만든다.

## 현재 최신 생성본

```text
25_web_keyword_research_connect.zip
```

## 확인 상태

```text
24_knowledge_markdown_connect.zip = 확인 완료
25_web_keyword_research_connect.zip = 아직 확인 전
```

## 현재까지 완료된 기능

```text
화면 UI 구성
대표 지시실 채팅창
채팅 입력창 하단 고정
AI 직원 조직도
직원별 AI 설정 화면
전체 자동 설정
Ollama 브릿지 연결
Ollama 모델 자동 감지
직원별 모델 자동 배정
Markdown 지식창고 검색
지식창고 검색 결과를 AI 프롬프트에 포함
인터넷 키워드 자료수집 기능 추가
검색 결과 Markdown 저장 기능 추가
```

## 현재 Ollama 모델 기준

성조님 PC에서 확인된 모델:

```text
llama3.2-vision:latest   이미지 분석용
nomic-embed-text:latest   지식창고 검색용
qwen2.5-coder:3b          개발 AI / 코드용
llama3.2:3b               대표비서 / 빠른 분류용
gemma4:latest             쇼핑몰 / 마케팅 / 콘텐츠용
gemma4:e2b                CS / 기억 / 정산용
```

## 직원별 모델 배정 기준

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
nomic-embed-text = 지식창고 검색용, 일반 채팅 답변용 아님
llama3.2-vision:latest = 이미지 분석용, 이미지 생성용 아님
이미지 생성 = ComfyUI / Stable Diffusion 단계에서 처리 예정
```

## 지식창고 구조

```text
knowledge/
  00_common/
  00_web_research/
  01_shopping/
  02_cs/
  03_image/
  04_dev/
  05_knowledge/
  06_memory/
  07_finance/
  08_automation/
  09_marketing/
  10_content/
```

## 실행 기준

```text
RUN.bat = 화면만 실행
RUN_AI_MODE.bat = AI 브릿지 + 실제 AI 모드 실행
START_BRIDGE.bat = 브릿지만 실행
CHECK_STATUS.bat = 상태 확인
OPEN_KNOWLEDGE_FOLDER.bat = 지식창고 폴더 열기
OPEN_WEB_RESEARCH_FOLDER.bat = 인터넷 자료 저장 폴더 열기
```

## 다음 우선 작업

```text
1. 25번 실제 실행 확인
2. 자료수집 화면에서 키워드 검색 정상 작동 확인
3. 특정 사이트 제한 검색 확인
4. 검색 결과 Markdown 저장 확인
5. 저장된 문서가 지식창고 검색에 포함되는지 확인
6. BAT 파일 구조 정리
```
