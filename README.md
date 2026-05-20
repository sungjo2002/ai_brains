# ai_brains

여러 AI와 코딩 도구가 공통으로 사용하는 작업 저장소입니다.

이 저장소는 특정 프로젝트 하나만 위한 공간이 아니라, 여러 작업을 프로젝트 ID 기준으로 관리합니다.

## 처음 확인할 파일

```text
AGENTS.md
PROJECTS.md
RULES.md
CHANGELOG.md
```

## 작업 시작 순서

```text
1. AGENTS.md 확인
2. PROJECTS.md에서 프로젝트 ID 확인
3. projects/Pxxx/META.md 확인
4. projects/Pxxx/CURRENT.md에서 최신 상태 확인
5. projects/Pxxx/TASKS.md에서 다음 작업 확인
6. projects/Pxxx/RULES.md에서 프로젝트 고정 규칙 확인
7. projects/Pxxx/FILES.md에서 핵심 파일 위치 확인
8. projects/Pxxx/COMMANDS.md에서 실행/검사 명령어 확인
9. projects/Pxxx/TESTS.md 기준으로 확인
```

## 저장소 구조

```text
ai_brains/
├─ AGENTS.md
├─ README.md
├─ PROJECTS.md
├─ RULES.md
├─ CHANGELOG.md
├─ projects/
│  ├─ P001/
│  │  ├─ META.md
│  │  ├─ CURRENT.md
│  │  ├─ TASKS.md
│  │  ├─ RULES.md
│  │  ├─ COMMANDS.md
│  │  ├─ TESTS.md
│  │  ├─ FILES.md
│  │  ├─ DECISIONS.md
│  │  ├─ HISTORY.md
│  │  ├─ source/
│  │  ├─ packages/
│  │  └─ archive/
│  ├─ P002/
│  └─ P003/
└─ templates/
```

## 핵심 원칙

- 상위 폴더에는 특정 프로젝트명을 쓰지 않는다.
- 프로젝트는 `P001`, `P002`처럼 번호로 관리한다.
- 프로젝트 이름은 `PROJECTS.md`와 각 프로젝트의 `META.md` 안에만 기록한다.
- 최신 상태는 각 프로젝트의 `CURRENT.md` 하나만 기준으로 본다.
- 다음 작업은 각 프로젝트의 `TASKS.md` 하나만 기준으로 본다.
- 코딩 작업에 필요한 명령어는 `COMMANDS.md`에 둔다.
- 핵심 파일 위치는 `FILES.md`에 둔다.
- 확인 절차는 `TESTS.md`에 둔다.

## 보안 원칙

운영 설정, 인증 정보, 데이터베이스, 개인정보 파일, 백업 데이터는 저장하지 않는다.
