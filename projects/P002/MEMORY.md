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
- connect-ai는 P002 프로그램 구조 참고 대상이며 직접 수정 대상이 아니다.

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
- 가상사무실 / AI 직원 모니터링 화면 실험 및 방향 정리

### 4. 현재 상태

현재 진행 중인 프로젝트와 다음 작업을 저장한다.

예시:
- 현재 프로젝트: P002
- 현재 최신 생성본: 44_org_style_worker_monitoring.zip
- 확인 완료: 24_knowledge_markdown_connect.zip, 32_asset_based_virtual_office.zip
- 확인 전: 44_org_style_worker_monitoring.zip
- 다음 작업: 44번 실제 실행 확인

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
- 많이 저장하는 것보다 잘 분류하고, 정확히 찾아오고, 최신 기준을 우선하며, 틀린 기억을 폐기하는 구조를 우선한다.
- 지식 창고와 기억 저장소가 쌓일수록 AI 직원의 업무 품질이 좋아지도록 만들되, 중복 자료와 오래된 자료가 답변에 섞이지 않게 관리한다.

## 지식 창고 / 기억 저장소 품질 향상 기준

P002는 자료를 많이 쌓는 것만 목표로 하지 않는다. 지식과 기억이 많아질수록 더 잘 작동하려면 다음 기준을 프로그램 구조에 반영한다.

```text
1. 중복 자료 정리
2. 오래된 자료 구분
3. 중요한 기억 우선순위 지정
4. 질문에 맞는 자료만 찾아오는 검색 구조
5. 최신 기준 우선 적용
6. 폐기된 기준은 deprecated 상태로 분리
7. 틀린 답변과 이상한 답변은 보정 기록으로 저장
8. 성조님의 피드백을 다음 답변 규칙에 반영
```

예시:

```text
성조님이 "영어 섞지 말고 한글로만 답해"라고 말하면 기억 저장소에 답변 규칙으로 저장한다.
성조님이 "날씨/가격/뉴스는 추측하지 말고 검색해"라고 말하면 최신정보 라우터 기준으로 저장한다.
성조님이 "상품 등록은 바로 하지 말고 초안만 만들어"라고 말하면 승인 필요 작업 기준에 반영한다.
```

답변 생성 흐름 기준:

```text
성조님 질문
→ 대표비서 AI가 질문 의도 분석
→ 기억 저장소에서 성조님 기준 확인
→ 지식 창고에서 관련 자료 검색
→ 현재 상태 문서 확인
→ 필요한 AI 직원 배정
→ 답변 생성
→ 새로 배운 기준은 기억 저장소에 저장
```

이 기준은 이후 P002 프로그램 개발, 기억 저장소, 지식 창고, 대화 품질 보정, 쇼핑몰 자동화 기능을 만들 때 참고한다.

## P002 초기 기억

- P002는 1인 기업 AI 사무실 프로젝트다.
- P002 기준 저장소는 `sungjo2002/ai_brains`다.
- connect-ai는 프로그램 구조 참고 대상이다.
- Antigravity / VS Code / Cursor 안에서 사용하는 AI 작업자 구조를 참고한다.
- Ollama와 LM Studio는 로컬 AI 엔진이다.
- ComfyUI는 이미지 생성 엔진으로 2차 이후 연결한다.
- 1차 목표는 대시보드보다 지식창고/기억저장소/명령입력 기반이다.
- 24번은 지식창고 Markdown 연결 확인 완료다.
- 25번은 인터넷 키워드 자료수집 기능 추가본이며 이후 버전으로 계속 진행했다.

## 2026-05-25 기억

### 실행 구조 기준

```text
다음 생성본부터는 32번 방식처럼 밖에 P002_AI_Office_실행.bat 하나만 보이게 한다.
_system 폴더는 숨기지 않는다.
VBS / PowerShell 숨김 실행은 기본 사용하지 않는다.
실행 안정성을 최우선으로 한다.
```

폐기/제외 기준:

```text
33_hidden_bridge_launcher.zip = _system 숨김 처리로 삭제 불편, 폐기
34_hidden_bridge_no_hide_folder.zip = 실행 실패
35_bat_hidden_bridge_no_vbs.zip = 실행 실패
36_stable_hidden_launcher_fix.zip = 실행 실패
37_minimized_bridge_stable.zip = 실행 방식 실험본, 기준 제외
```

### 가상사무실 방향 정리

```text
MP4 기준처럼 상세 사무실 + 움직이는 캐릭터 방식은 가능하다.
다만 P002 실제 사용 목적은 AI 직원 10명이 어떻게 돌아가는지 실시간으로 보는 것이 더 중요하다.
따라서 가상사무실보다 AI 직원 모니터링 화면을 우선한다.
```

확인/작업 이력:

```text
32_asset_based_virtual_office.zip = 상세 사무실 배경 자산 + 캐릭터 스프라이트 방식, 확인 완료
38_worker_monitoring_view.zip = AI 직원 10명 상태 카드형 모니터링 적용
39_worker_monitoring_layout_fix.zip = 화면 짤림 수정
40_menu_overlap_fix.zip = 하단 메뉴 숨김 시도
41_top_menu_style_fix.zip = 상단 메뉴 모양 복구
42_remove_org_title_text.zip = 조직도 불필요 문구 제거
43_top_menu_left_align.zip = 상단 메뉴 왼쪽 정렬
44_org_style_worker_monitoring.zip = 조직도 디자인을 AI 직원 모니터링으로 통합한 최신 생성본
```

### AI 직원 모니터링 최종 방향

```text
조직도 기능은 별도 메뉴로 두지 않는다.
조직도 디자인을 AI 직원 모니터링 화면으로 사용한다.
메뉴 이름은 AI 직원 모니터링 하나로 통합한다.
모델명 / 도구 / 공용자원 / 작업 연결도는 기본 화면에서 제거한다.
직원 카드에는 상태 / 현재 작업 / 진행률만 표시한다.
채팅 입력 시 담당 AI 카드가 분석중 → 검색중 → 작업중 → 완료 흐름으로 바뀐다.
```

44번 기준:

```text
조직도 메뉴 제거
AI 직원 모니터링 메뉴 하나로 통합
기존 조직도 디자인을 모니터링 화면으로 사용
모델명 / 도구 / 공용자원 / 작업 연결도 제거
직원 카드에는 상태 / 현재 작업 / 진행률만 표시
상단 메뉴 왼쪽 정렬 유지
하단 메뉴 숨김 유지
밖에는 P002_AI_Office_실행.bat 하나만 유지
```

## 다음 확인 작업

```text
1. 44_org_style_worker_monitoring.zip 실행 확인
2. AI 직원 모니터링 메뉴가 하나만 남았는지 확인
3. 기존 조직도 메뉴가 사라졌는지 확인
4. 조직도와 모니터링 화면 겹침이 없는지 확인
5. 채팅 입력 시 담당 AI 직원 카드 상태와 진행률이 바뀌는지 확인
6. 정상 확인되면 44번을 기준본으로 확정
```
