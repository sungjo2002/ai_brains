# AGENTS.md

이 저장소는 여러 AI와 코딩 도구가 공통으로 사용하는 작업 저장소다.

특정 AI, 특정 프로그램, 특정 프로젝트 이름에 고정하지 않는다. 모든 작업은 프로젝트 ID 기준으로 관리한다.

## 시작 순서

새 대화, 새 AI, Codex, Cursor, Claude Code, Copilot 등 어떤 도구에서든 아래 순서로 확인한다.

```text
1. AGENTS.md를 읽는다.
2. PROJECTS.md에서 작업할 프로젝트 ID를 확인한다.
3. projects/Pxxx/META.md를 읽는다.
4. projects/Pxxx/CURRENT.md에서 최신 상태를 확인한다.
5. projects/Pxxx/TASKS.md에서 다음 작업을 확인한다.
6. projects/Pxxx/RULES.md에서 고정 규칙과 금지 조건을 확인한다.
7. projects/Pxxx/FILES.md에서 핵심 파일 위치를 확인한다.
8. projects/Pxxx/COMMANDS.md에서 실행/검사 명령어를 확인한다.
9. projects/Pxxx/TESTS.md 기준으로 확인한다.
```

## 기준 파일 원칙

- 최신 상태는 각 프로젝트의 `CURRENT.md` 하나만 기준으로 본다.
- 다음 작업은 각 프로젝트의 `TASKS.md` 하나만 기준으로 본다.
- 고정 규칙은 각 프로젝트의 `RULES.md`에 둔다.
- 전체 공통 규칙은 루트 `RULES.md`에 둔다.
- 날짜별 작업 기록은 각 프로젝트의 `HISTORY.md`에 둔다.
- 중요한 결정은 각 프로젝트의 `DECISIONS.md`에 둔다.
- 저장소 전체 변경 이력은 `CHANGELOG.md`에 둔다.

## 실제 수정 전 규칙

사용자가 실제 수정/생성을 요청하면 먼저 아래 형식으로 짧게 정리한다.

```text
수정 대기
- 수정 대상:
- 수정 이유:
- 수정 범위:
- 생성/수정 파일명:
- 확인 방법:
```

그 다음 실제 작업을 진행한다.

## 작업 저장 기준

- 작업 상태 변경은 해당 프로젝트의 `CURRENT.md`에 반영한다.
- 완료/진행/보류/오류는 해당 프로젝트의 `TASKS.md` 또는 `HISTORY.md`에 반영한다.
- 새로 확정된 고정 규칙은 해당 프로젝트의 `RULES.md`에 반영한다.
- 저장소 구조나 프로젝트 목록이 바뀌면 `PROJECTS.md`를 갱신한다.
- 의미 있는 저장/수정/정리 작업은 `CHANGELOG.md`에 기록한다.

## 보안 기준

이 저장소는 public 저장소로 취급한다.

아래 파일과 정보는 저장하지 않는다.

```text
.env
*.env
*.db
*.sqlite
*.sqlite3
API 키
토큰
서버 비밀번호
개인정보 원본 파일
운영 설정 파일
백업 데이터
```

## 코딩 작업 기준

- 실제 코드가 저장될 경우 `projects/Pxxx/source/` 아래에 둔다.
- ZIP 수정본이나 산출물은 `projects/Pxxx/packages/` 아래에 둔다.
- 오래된 기록과 이전 문서는 `projects/Pxxx/archive/` 아래에 둔다.
- 코드 수정 후에는 `COMMANDS.md`와 `TESTS.md` 기준으로 검사한다.

## 금지

- 기능 조건, 권한 조건, 저장 조건, 동기화 조건, 계산 조건은 임의로 바꾸지 않는다.
- 서버 방어 로직과 화면 숨김을 혼동하지 않는다.
- 최신 기준 파일이 여러 개로 갈라지게 만들지 않는다.
- 프로젝트 이름을 상위 폴더명에 직접 박지 않는다. 프로젝트명은 `META.md`와 `PROJECTS.md`에만 기록한다.
