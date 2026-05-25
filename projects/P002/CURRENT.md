# P002 현재 상태

최종 갱신: 2026-05-25

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
connect-ai는 직접 수정 대상이 아니며, P002 기능은 별도 생성본 기준으로 만든다.
P002 기준 문서와 작업 상태 저장은 sungjo2002/ai_brains/projects/P002/를 우선한다.
```

## 현재 목표

대표가 채팅창에 지시하면 대표비서 AI가 내용을 분석하고, AI 직원 10명 중 담당자를 자동 배정한 뒤 Ollama / LM Studio / 지식창고 / 기억저장소 / GitHub / 인터넷 자료수집 기능으로 업무를 처리하는 1인 기업용 AI 자동화 프로그램을 만든다.

## 현재 최신 생성본

```text
44_org_style_worker_monitoring.zip
```

## 확인 상태

```text
24_knowledge_markdown_connect.zip = 확인 완료
25_web_keyword_research_connect.zip = 기능 추가본, 이후 버전으로 계속 진행
32_asset_based_virtual_office.zip = 확인 완료
33_hidden_bridge_launcher.zip = 삭제 / 폐기
34_hidden_bridge_no_hide_folder.zip = 실행 실패
35_bat_hidden_bridge_no_vbs.zip = 실행 실패
36_stable_hidden_launcher_fix.zip = 실행 실패
37_minimized_bridge_stable.zip = 실행 방식 실험본, 이후 기준에서 제외
38_worker_monitoring_view.zip = AI 직원 모니터링 1차 적용
39_worker_monitoring_layout_fix.zip = 모니터링 화면 짤림 수정
40_menu_overlap_fix.zip = 하단 메뉴 숨김 처리 시도
41_top_menu_style_fix.zip = 상단 메뉴 모양 복구
42_remove_org_title_text.zip = 조직도 불필요 문구 제거
43_top_menu_left_align.zip = 상단 메뉴 왼쪽 정렬
44_org_style_worker_monitoring.zip = 최신 생성본, 사용자 최종 확인 전
```

## 현재까지 완료된 기능

```text
화면 UI 구성
대표 지시실 채팅창
채팅 입력창 하단 고정
AI 직원 조직도 기반 UI
직원별 AI 설정 화면
전체 자동 설정
Ollama 브릿지 연결
Ollama 모델 자동 감지
직원별 모델 자동 배정
Markdown 지식창고 검색
지식창고 검색 결과를 AI 프롬프트에 포함
인터넷 키워드 자료수집 기능 추가
검색 결과 Markdown 저장 기능 추가
자산 기반 가상사무실 시도
AI 직원 10명 실시간 모니터링 화면 적용
조직도 디자인 기반 AI 직원 모니터링으로 방향 정리
```

## 2026-05-25 작업 정리

### 가상사무실 검토

```text
26번 = 카드형 가상사무실 시도
28~31번 = Canvas 기반 사무실/캐릭터 이동 실험
32번 = 상세 사무실 배경 자산 + 캐릭터 스프라이트 자산 분리 방식 적용, 확인 완료
```

결론:

```text
캐릭터가 움직이는 가상사무실은 가능하지만, 실제 업무 모니터링에는 화면이 복잡해질 수 있다.
가상사무실보다 AI 직원 10명이 각각 어떻게 돌아가는지 보는 모니터링 화면이 더 실용적이다.
```

### 실행 방식 검토

```text
33번 = 브릿지 숨김 실행 + _system 숨김 처리 → 삭제 불편으로 폐기
34번 = _system 숨김 없이 VBS 숨김 실행 → 실행 실패
35번 = PowerShell 숨김 실행 → 따옴표/경로 문제로 실행 실패
36번 = PowerShell 스크립트 분리 → 실행 실패
37번 = 최소화 실행 안정화 시도 → 실행 방식 실험본으로 제외
```

결론:

```text
다음 생성본부터는 32번 방식처럼 밖에 P002_AI_Office_실행.bat 하나만 보이게 한다.
_system 폴더는 숨기지 않는다.
VBS / PowerShell 숨김 실행은 기본 사용하지 않는다.
실행 안정성을 우선한다.
```

### AI 직원 모니터링 방향

최종 방향:

```text
조직도 기능은 별도 메뉴로 두지 않는다.
조직도 디자인을 AI 직원 모니터링 화면으로 사용한다.
메뉴 이름은 AI 직원 모니터링 하나로 통합한다.
모델명 / 도구 / 공용자원 / 작업 연결도는 기본 화면에서 제거한다.
직원 카드에는 상태 / 현재 작업 / 진행률만 표시한다.
채팅 입력 시 담당 AI 카드가 분석중 → 검색중 → 작업중 → 완료 흐름으로 바뀐다.
```

44번 적용 내용:

```text
조직도 메뉴 제거
AI 직원 모니터링 메뉴 하나로 통합
기존 조직도 디자인을 모니터링 화면으로 사용
모델명 / 도구 / 공용자원 / 작업 연결도 제거
직원 카드에는 상태 / 현재 작업 / 진행률만 표시
채팅 입력 시 담당 AI 카드 상태 변경
상단 메뉴 왼쪽 정렬 유지
하단 메뉴 숨김 유지
밖에는 P002_AI_Office_실행.bat 하나만 유지
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

현재 선호 기준:

```text
밖에 보이는 파일 = P002_AI_Office_실행.bat 하나
내부 파일 = _system/ 안에 정리
_system 숨김 처리 = 하지 않음
VBS / PowerShell 숨김 실행 = 기본 사용 안 함
실행 안정성 = 최우선
```

기존 내부 실행 파일 기준:

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
1. 44_org_style_worker_monitoring.zip 실제 실행 확인
2. AI 직원 모니터링 메뉴가 하나만 남았는지 확인
3. 조직도 화면/AI 모니터링 화면 겹침이 사라졌는지 확인
4. 채팅 입력 시 담당 AI 카드 상태와 진행률이 바뀌는지 확인
5. 메뉴바 왼쪽 정렬과 하단 메뉴 숨김 상태 확인
6. 정상 확인되면 44번을 다음 기준본으로 확정
```