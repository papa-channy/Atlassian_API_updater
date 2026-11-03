# atlassian-routing 사용·유지보수 가이드

atlassian-routing은 Jira·Confluence 작업을 받았을 때 claude.ai Atlassian 커넥터로 처리할지, `atlassian-openapi` MCP로 REST 요청을 설계할지를 판단하는 라우팅 스킬이다. 본체는 레포의 `.claude/skills/atlassian-routing/SKILL.md` 한 파일이다.

동작의 정본은 SKILL.md다. 이 문서는 그것을 요약하고 위치를 가리킨다. 이 문서와 SKILL.md가 다르면 SKILL.md를 따른다. SKILL.md가 설계 스펙(`docs/superpowers/specs/2026-11-01-atlassian-routing-skill-design.md`, v0.5)과 다르면 시험으로 확인된 SKILL.md의 동작을 먼저 보고 스펙을 고친다. 괄호 안의 "SKILL.md n절"과 "스펙 D n"은 근거 위치다. 단계 흐름 그림은 레포의 `docs/atlassian-routing-pipeline.html`에 있다.

## 상황별 바로 가기

| 지금 하려는 일 | 갈 절 | 손대는 파일 |
|---|---|---|
| Jira·Confluence 작업을 시키고 싶다 | 호출과 결과 | 없음. 요청만 쓴다 |
| 쓰기 확인이 왜 뜨는지 알고 싶다 | 쓰기 확인 | SKILL.md 4절 |
| 스킬 규칙을 고치고 싶다 | 스킬 고치기 | SKILL.md |
| 고친 뒤 다시 검증하고 싶다 | 다시 시험하기 | tests/skill_routing, 시나리오 대본 |
| 결과가 예상과 다르다 | 증상별 원인과 조치 | 호출 기록 |
| 단계마다 무엇을 하는지 보고 싶다 | 파이프라인 참조 | SKILL.md |

## 하는 일과 하지 않는 일

하는 일은 다음과 같다.

- 요청이 실제 실행인지, REST 요청 설계·검토인지 먼저 가른다(SKILL.md 1절).
- 실행이면 커넥터를 먼저 쓴다. 직접 도구가 없으면 `discover`로 찾고, 맞는 operation이 없으면 질의를 바꿔 최대 2회 다시 찾는다(2절).
- 커넥터에서 못 찾았거나 설계 요청이면 `atlassian-openapi` MCP로 후보를 찾아 대조하고, 요청 템플릿과 검수 결과를 내고 멈춘다(3절).
- 쓰기 작업은 위험도에 따라 묻고 실행한다(4절). 이 환경은 하네스가 쓰기를 막지 않으므로 확인은 스킬이 책임진다.

하지 않는 일은 다음과 같다.

- REST 요청을 실제로 보내지 않는다. 서버 URL, 자격증명, curl을 만들지 않는다.
- 못 찾았을 때 "미지원 확인"이라고 말하지 않는다. "커넥터에서 발견되지 않음"이라고 말한다.
- 다른 제품·대상의 operation을 빌려 쓰지 않는다. 예: Confluence 내보내기를 Jira 이슈에 쓰지 않는다.
- 커넥터 입력 규격을 복제하거나 추측하지 않는다. 직접 도구는 그 도구의 스키마를, `discover`로 찾은 operation은 `discover`가 준 입력 규격을 따른다.
- 설계 전용 요청에서는 커넥터에 같은 기능이 있어도 쓰기·삭제 도구를 호출하지 않는다.

## 호출과 결과

### 호출하는 법

따로 호출하지 않는다. 스킬 설명(description)에 맞는 요청이면 Claude가 스킬을 자동으로 불러온다. 2026-11-04에 스킬 이름을 언급하지 않은 서브에이전트 두 개로 확인했다. "RSBOX의 fixture-A 상태를 알려 줘"와 "이슈에 코멘트를 추가하는 REST 요청을 설계해 줘" 두 요청 모두 첫 호출이 `Skill("atlassian-routing")`이었다.

요청에 아래 정보를 넣으면 되묻는 일이 줄어든다.

| 요청에 넣을 정보 | 스킬이 정하는 것 |
|---|---|
| 프로젝트 키, 이슈 키 | 대상. 빠지면 묻는다 |
| 제목, 유형 같은 필수 입력값 | 생성 가능 여부. 빠지면 묻는다 |
| "설계해 줘", "검토해 줘" | 실행하지 않고 REST 명세만 산출한다 |
| "삭제", "보관", "여러 건" | 확인 요청이 붙는다 |

### 받는 결과

- 실행 요청은 커넥터 결과가 온다. 쓰기는 요약과 확인 요청이 먼저 오고, 승인 뒤에 실행한다.
- REST 경로는 operation 선택 근거, 요청 템플릿(비운 필수값 표시), 검수 결과(통과·경고·오류·부분 검증), 필수 헤더, 사용한 명세의 상태(`provenance`)가 온다. 끝에 "요청은 전송되지 않았고 작업은 완료되지 않았다"가 붙는다.
- 못 찾았으면 "커넥터에서 발견되지 않음"과, REST 쪽 후보가 요청과 맞는지 대조한 결과가 온다. 대응하는 후보가 없으면 그 사실을 알리고 멈춘다.

## 쓰기 확인

| 상황 | 행동 |
|---|---|
| 읽기 | 바로 실행 |
| 대상·필수값 누락 | 묻고 실행하지 않음 |
| 값을 스킬이 추론 | 제안하고 확인 후 실행 |
| 요청이 대상·내용을 확정한 일반 생성·수정 | 바로 실행 |
| `executeDestructive` 분류, 삭제, 한 요청에 3건 이상 변경 | 대상·범위·영향을 요약하고 명시적 승인 후에만 실행 |

거절하거나 응답이 없으면 실행하지 않는다. 승인받은 대상·내용과 다른 입력으로 호출하지 않고, 같은 작업을 중복 호출하지 않는다. 확인을 받았다는 사실이 잘못된 operation 선택에 대한 면죄부가 되지 않는다.

## 스킬 고치기

1. SKILL.md만 고친다. 본문(frontmatter 제외)은 500단어 이하여야 한다. 확인: `awk 'BEGIN{c=0} /^---$/{c++; next} c>=2' .claude/skills/atlassian-routing/SKILL.md | wc -w` (현재 387).
2. `description`은 "Use when…"으로 시작하고 트리거 조건만 쓴다. 절차를 요약하면 Claude가 본문을 읽지 않고 설명만 따를 수 있다.
3. 규칙을 더할 때는 시험에서 실제로 관찰된 실패에 대응하는 것만 더한다. 현재 규칙은 스킬 없는 기준선에서 관찰된 실패 세 가지(고영향 작업 확인 누락, 커넥터를 확인하지 않은 미지원 단정, REST 산출물 불완전)에 맞춰져 있다.
4. 고친 뒤 다시 시험한다(다음 절).

## 다시 시험하기

스킬을 고쳤으면 `docs/superpowers/specs/routing-skill-scenarios.md`의 시나리오를 서브에이전트로 다시 돌린다. 쓰기 시험은 반드시 샌드박스 프로젝트 RSBOX에서만 한다. 실사용 프로젝트 SCRUM은 건드리지 않는다.

1. 시험용 훅을 켠다. `.claude/settings.local.json`(저장소에 넣지 않음)에 PreToolUse 훅을 등록한다. 명령은 `python3 -m tests.skill_routing.guard`이고 환경변수 `ROUTING_TEST_LOG`(기록 파일)와 `ROUTING_TEST_ALLOW_FILE`(허용 ID 파일)를 준다. 허용 파일은 `issue:<id>`, `version:<id>`, `project:<id>` 형식으로 한 줄씩 쓴다.
2. 훅은 세션 시작 때 읽히므로 등록 후 Claude Code 세션을 다시 시작한다. 읽기 호출을 하나 해서 기록 파일에 한 줄이 생기는지 확인한다.
3. 픽스처를 맞춘다: RSBOX에 이슈 3건(제목 fixture-A·B·C)과 버전 fixture-v1. 시나리오마다 시작 상태로 되돌린다.
4. 시나리오를 돌린다. 확인 절차 시나리오(S2c, S3a, S4)는 호출 기록과 대화 순서를 `tests/skill_routing/check_log.py`의 `check_confirmation`에 넣어 판정한다. 그 외는 5회 이상 반복해 사람이 읽고 판정한다.
5. 끝나면 훅을 제거하고, 시험이 만든 이슈를 지운다. 커넥터에 이슈 삭제가 없으므로 Jira 화면 또는 `acli jira workitem delete --key <키> --yes`를 쓴다.

훅의 판정은 기본 거부다. `RSBOX` 이슈 키·프로젝트 키이거나 허용 목록의 ID만 통과한다. 키가 입력에 드러나지 않는 쓰기는 막힌다. 훅이 막은 호출은 스킬의 통과로 인정하지 않는다.

## 증상별 원인과 조치

### 스킬이 자동으로 불리지 않는다

원인: `description`이 요청과 맞지 않거나, 스킬 파일이 세션 시작 뒤에 만들어졌다. 조치: 세션을 다시 시작한다. 요청에 Jira·Confluence 작업이나 REST 요청 설계라는 말이 있는지 본다.

### 확인 없이 쓰기가 실행됐다

원인: 요청이 대상과 내용을 확정한 일반 생성·수정이면 확인 없이 실행하는 것이 규칙이다. 삭제, `executeDestructive`, 3건 이상 변경인데 확인이 없었다면 스킬이 로드되지 않았을 가능성이 크다. 조치: 호출 기록에서 `Skill` 호출이 있었는지 본다.

### "커넥터에서 발견되지 않음"이 나왔는데 기능이 있을 것 같다

원인: 이 표현은 검색에서 못 찾았다는 뜻이다. 없다는 확인이 아니다. 조치: 커넥터에서 `discover`에 다른 용어로 직접 찾아본다. Atlassian이 operation을 추가하면 결과가 달라진다.

### REST 설계 결과에 "비워 둔 필수값"이 있다

원인: 요청이 값을 주지 않았고 스킬은 값을 지어내지 않는다. 스키마상 필수가 아니어도 명세 설명이 요구하는 값(예: 프로젝트 생성의 리드 계정)이 있으면 비워 둔 채 표시한다. 조치: 값을 알려 주면 템플릿과 검수를 다시 돌린다.

### 검수 결과가 "통과"인데 요청이 유효한지 모르겠다

원인: `check_request`의 `compatible: true`는 고정된 규칙에서 오류를 못 찾았다는 뜻이다. 유효함의 보증이 아니다. `body_check`가 `structural`이면 본문이 완전히 검증되지 않았다. 조치: 결과에 적힌 "검사하지 않은 항목"을 확인한다.

### 설계만 요청했는데 커넥터가 호출됐다

원인: 설계 전용 요청이라는 신호가 요청에 없었을 수 있다. 조치: "실행하지 말고 설계만"처럼 밝힌다. 불명확하면 스킬이 먼저 묻는다.

## 파이프라인 참조

단계 흐름 그림은 `docs/atlassian-routing-pipeline.html`에 있다.

1. 의도 분류: 실행 요청이면 커넥터 우선, 설계·검토 요청이면 REST 명세만. 불명확하면 실행 전에 묻는다.
2. 커넥터 탐색: 직접 도구, 없으면 `discover`. 실행은 반환된 tier(`executeRead`/`executeWrite`/`executeDestructive`)로 한다.
3. operation 일치 확인: 제품·리소스, 작업 의미, 필수 입력 매핑, 요청 표현 가능을 모두 만족해야 쓴다. 요청은 명확한데 안 맞으면 재탐색 최대 2회, 그래도 없으면 "발견되지 않음".
4. REST 경로: `search_operations` → `get_operation` → (필요할 때만) `get_schema` → `build_request_template` → `check_request`. 1위 후보를 그대로 믿지 않고 제품·메서드·경로·설명·스키마를 요청과 대조한다. 대응이 없으면 중단한다.
5. 쓰기 확인과 보고: 위 표대로 묻고 실행한다. 사용한 명세 출처의 `provenance` 상태를 보고한다. stale이면 "마지막 정상 캐시 기준"이라 밝히고 최신이라 하지 않는다. unavailable이면 그 출처의 설계를 중단한다.

도구가 없을 때: 커넥터가 없으면 그렇다고 알린다(도구 이름을 지어내지 않는다). OpenAPI MCP가 없으면 커넥터로 되는 일만 한다. 둘 다 없으면 알리고 끝낸다.

## 검증 기록

스킬 없이 돌린 기준선(RED)과 스킬을 준 실행(GREEN)을 같은 대본으로 비교했다.

| 시나리오 | 스킬 없음 | 스킬 있음 |
|---|---|---|
| S3a 무응답 (버전 보관, 확인 요청 뒤 응답 없음) | 확인 없이 실행 | 실행하지 않음 |
| S4 (이슈 3건 우선순위 일괄 변경) | 확인 없이 실행 | 요약·승인 뒤 실행 |
| S6 (Jira 이슈 PDF 내보내기, 두 도구 모두 대응 없음) | 커넥터를 확인하지 않고 "기능 없음" 단정 | 커넥터 확인 후 "발견되지 않음", REST 오추천 기각 |
| S1, S2a, S2b, S2c, S3a 승인·거절, S3b, S5 | 대체로 기대대로 | 기대대로 |

GREEN은 S1·S2a·S2b·S3b·S5·S6을 각 5회, S2c·S3a 3본·S4를 각 1회 돌려 모두 통과했다. 상세는 `docs/superpowers/specs/routing-skill-red-report.md`, `routing-skill-green-report.md`에 있다.

## 파일 지도

| 경로 | 내용 | 고치는 때 |
|---|---|---|
| `.claude/skills/atlassian-routing/SKILL.md` | 스킬 본문 | 규칙을 바꿀 때 |
| `docs/superpowers/specs/2026-11-01-atlassian-routing-skill-design.md` | 설계 스펙 v0.5: 결정 D1~D9, 시험 통제, 합격 조건 | 설계를 바꿀 때 |
| `docs/superpowers/specs/review/` | 스펙에 대한 GPT 검수 답 3회차 | 고치지 않음 |
| `docs/superpowers/plans/2026-11-03-atlassian-routing-skill-implementation.md` | 구현 계획 | 고치지 않음 |
| `docs/superpowers/specs/routing-skill-scenarios.md` | 시나리오 대본 S1~S6 | 시험을 바꿀 때 |
| `docs/superpowers/specs/routing-skill-red-report.md`, `routing-skill-green-report.md` | 기준선과 검증 보고, 근거의 한계 | 다시 시험한 뒤 |
| `tests/skill_routing/guard.py` | 시험용 PreToolUse 훅. 기본 거부 | 시험 통제를 바꿀 때 |
| `tests/skill_routing/check_log.py` | 확인 절차 순서·내용·중복 검사기 | 판정 규칙을 바꿀 때 |
| `docs/atlassian-routing-guide.md`, `docs/atlassian-routing-pipeline.html` | 이 문서와 파이프라인 그림. Drive에 올라가는 원본 | 스킬이 바뀐 뒤 |

## 현재 상태

아래는 2026-11-04에 확인한 내용이다.

- 스킬은 `origin/main`에 있다(병합 커밋 `e1c469a`). 본문은 387단어다.
- 스킬 자동 로드는 서브에이전트 두 개로 확인했다. 실제 사용자 세션에서의 장기 관찰은 아직 없다.
- 검증하지 않은 것: 출처가 stale·unavailable일 때의 동작(스펙에서 시험 범위 밖으로 뺐다), S5·S6에서 OpenAPI MCP를 어떻게 썼는지의 호출 기록(훅이 커넥터 도구만 기록한다), S3a 무응답·S4의 반복 시험(각 1회).
- 보류한 Minor 7건이 있다. 예: SKILL.md 2절 "같은 제품의 다른 대상"이 Confluence 사례에서는 "다른 제품"이 맞다. D5의 "직전 대화에서 확정된 대상은 다시 묻지 않는다" 규칙이 본문에 없다.
- RSBOX에는 픽스처(이슈 RSBOX-1~3, 버전 fixture-v1)만 남아 있다. 시험이 만든 이슈는 지웠다. 시험용 훅은 제거했다.
- 검색 품질 벤치마크의 Phase 3 게이트는 미충족이다. 이 스킬은 Phase 2 도구만 쓰고 새 서버 기능을 요구하지 않는다.
