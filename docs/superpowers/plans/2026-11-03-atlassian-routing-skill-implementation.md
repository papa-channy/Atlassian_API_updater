# Atlassian 라우팅 스킬 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.claude/skills/atlassian-routing/SKILL.md`(커넥터 우선, OpenAPI MCP는 REST 설계·검수용 라우팅 스킬)를 RED → GREEN → REFACTOR 절차로 만들고, 스펙 §5 합격 조건(AC-1~AC-5)으로 검증한다.

**Architecture:** 스킬 본문은 마크다운 한 파일이다. 검증 인프라는 두 부분이다. (1) 시험용 PreToolUse 훅이 쓰는 fail-closed 가드와 호출 기록(`tests/skill_routing/guard.py`), (2) 호출 기록·대화 기록으로 AC-3 순서를 결정적으로 검사하는 검사기(`tests/skill_routing/check_log.py`). 시나리오는 서브에이전트가 RSBOX에서 대본대로 실행하고, 매칭은 사람이 읽어 판정한다.

**Tech Stack:** Markdown 스킬, Python 3(pytest, 표준 라이브러리만), Claude Code PreToolUse 훅, `atlassian-openapi` MCP, claude.ai Atlassian 커넥터, `acli`(정리용).

**Spec:** `docs/superpowers/specs/2026-11-01-atlassian-routing-skill-design.md` (v0.5). 이 계획은 스펙 §3 D1~D9, §5.1~§5.3을 구현한다. 실행자는 스펙을 함께 읽는다.

## Global Constraints

- 시험 변경은 프로젝트 `RSBOX`(cloudId `ef069fee-c337-4fcf-8599-0c920f186920`, 사이트 `studiocaret.atlassian.net`)에서만 한다. `SCRUM`을 포함한 `RSBOX` 밖 변경은 금지다.
- `~/.claude/settings.json`은 `bypassPermissions`이고 Atlassian 규칙이 없다. 하네스가 쓰기를 막지 않으므로 훅 없이 쓰기 시험을 하지 않는다(AC-4).
- 시험용 훅은 `.claude/settings.local.json`에 두고 저장소에 넣지 않는다. 시험이 끝나면 제거한다.
- 훅 정책은 fail-closed: `RSBOX` 이슈 키·프로젝트 키이거나 픽스처 허용 목록의 이슈 ID·버전 ID일 때만 통과. 범위를 확인할 수 없는 쓰기 도구는 실사이트 시험에서 제외하고 기록한다.
- `SKILL.md` 본문(frontmatter 제외) `wc -w` ≤ 500. `description`은 "Use when…"으로 시작하고 트리거 조건만 쓰며 절차를 요약하지 않는다.
- 스킬은 서버 URL·자격증명을 만들지 않고 요청을 전송하지 않는다. REST 경로는 템플릿과 검수 결과로 종료하며 "미전송·미완료"를 명시한다. 커넥터 입력 규격을 복제하지 않는다(D1).
- 커넥터 검색 실패는 "발견되지 않음"이며 "미지원 확인"이 아니다.
- `effective_required: true` 헤더는 누락하지 않고 표시한다. `compatible: true`를 "유효함"으로 보고하지 않는다. `body_check: "structural"`이면 부분 검증임을 밝힌다.
- 새 MCP 도구·서버 기능은 만들지 않는다(§4, Phase 3 게이트 미충족).
- 검색 품질 도구 동결(`tests.benchmarks.evaluator.TOOLING_FILES`)은 건드리지 않는다.
- 커밋 메시지 끝: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`

## Review Focus

- 훅 입력에 이슈 키·프로젝트 키가 없고 숫자 ID만 있을 때: 허용 목록에 없으면 막는다.
- `executeWrite` 입력 안에 `RSBOX-1`과 `SCRUM-1`이 함께 있을 때: 하나라도 RSBOX 밖이면 막는다.
- 훅에 넘어온 JSON이 깨졌거나 도구 입력이 비었을 때: 쓰기 도구라면 통과시키지 않는다(fail-closed).
- S4에서 승인한 3건에 4번째 이슈가 섞일 때: 검사기가 실패로 판정한다.
- 거절·무응답 후 쓰기 호출이 기록에 남았을 때: 검사기가 실패로 판정한다.

---

### Task 1: 브랜치 분리와 문서 커밋

**Files:**
- Commit: `docs/superpowers/specs/2026-11-01-atlassian-routing-skill-design.md`, `docs/superpowers/specs/review/2026-11-01-atlassian-routing-skill-design-{1,2,3}.md`, 이 계획 파일

**Interfaces:**
- Produces: 브랜치 `feat/atlassian-routing-skill`(`main` 기준). 이후 모든 Task가 이 브랜치에서 커밋한다.

- [ ] **Step 1: `main`에서 새 브랜치를 만든다.** `git switch -c feat/atlassian-routing-skill main`. untracked 파일만 있어 그대로 따라온다. 기대: `git status --short`에 위 문서 파일과 `docs/superpowers/handoffs/2026-10-05-round3-controller-handoff.md`가 untracked로 남는다. 이 handoff 파일은 이 작업과 무관하므로 커밋하지 않는다.
- [ ] **Step 2: 스펙·검수 답 3개·이 계획만 add 해 커밋한다.** 메시지 `docs: atlassian routing skill spec v0.5 (GPT review 3 rounds) and implementation plan`. 기대: `git show --stat HEAD`에 파일 5개.
- [ ] **Step 3: 확인.** `git log --oneline -1`과 `git branch --show-current`가 새 브랜치다. `round6` 브랜치는 건드리지 않았다(`git rev-parse round6`이 `80255f8…`).

### Task 2: 훅 가드와 단위 시험

**Files:**
- Create: `tests/skill_routing/__init__.py`, `tests/skill_routing/guard.py`
- Test: `tests/skill_routing/test_guard.py`

**Interfaces:**
- Produces: `guard.decide(tool_name: str, tool_input: dict, allow_ids: set[str]) -> tuple[bool, str]` — `(허용 여부, 사유)`. `guard.is_write_tool(tool_name: str) -> bool`. `guard.main()` — 표준입력의 PreToolUse JSON을 읽고, 환경변수 `ROUTING_TEST_LOG`(기록 파일)와 `ROUTING_TEST_ALLOW_FILE`(허용 ID 한 줄씩)을 사용한다. 차단 시 종료 코드 2와 stderr 사유, 허용 시 0.
- 쓰기 도구 판정: 이름이 `mcp__claude_ai_Atlassian_MCP__` 접두이고 접미가 `createJiraIssue`, `editJiraIssue`, `transitionJiraIssue`, `addOrEditJiraIssueComment`, `createConfluenceContent`, `updateConfluenceContent`, `executeWrite`, `executeDestructive` 중 하나.

- [ ] **Step 1: 실패하는 시험을 쓴다.** `test_guard.py`에 다음 이름과 단언을 둔다.
  - `test_read_tool_always_allowed`: `getJiraIssue` + `{"issueIdOrKey":"SCRUM-1"}` → 허용.
  - `test_write_with_rsbox_key_allowed`: `createJiraIssue` + `{"projectKey":"RSBOX","summary":"x"}` → 허용.
  - `test_write_with_scrum_key_blocked`: `editJiraIssue` + `{"issueIdOrKey":"SCRUM-1"}` → 차단, 사유에 `SCRUM`.
  - `test_mixed_keys_blocked`: 입력에 `RSBOX-1`과 `SCRUM-1`이 함께 → 차단.
  - `test_numeric_id_blocked_unless_allowlisted`: `executeDestructive` + `{"name":"manageJiraProjectVersion","inputs":{"versionId":"10001"}}` → `allow_ids=set()`이면 차단, `{"10001"}`이면 허용.
  - `test_write_without_any_identifier_blocked`: `executeWrite` + `{"name":"x","inputs":{}}` → 차단(fail-closed).
  - `test_main_bad_json_blocks_write_tool`: 깨진 JSON을 표준입력으로 주면 종료 코드 2.
  - `test_main_logs_every_call`: 읽기 호출도 `ROUTING_TEST_LOG`에 JSON 한 줄(`ts`, `tool`, `input`, `allowed`)로 남는다.
- [ ] **Step 2: 실패 확인.** `pytest tests/skill_routing/test_guard.py -v` → 모듈 없음으로 FAIL.
- [ ] **Step 3: `guard.py`를 구현한다.** 키 추출은 입력을 JSON 문자열로 직렬화해 정규식 `\b[A-Z][A-Z0-9]{1,9}(?:-\d+)?\b` 중 이슈 키형(`-숫자`)과 `projectKey`/`project` 필드 값을 모은다. 비-RSBOX 프로젝트 키가 하나라도 있으면 차단. 식별자가 하나도 없으면 입력에서 숫자 문자열 값을 모아 모두 `allow_ids`에 있을 때만 허용, 숫자도 없으면 차단. 읽기 도구는 항상 허용하되 기록한다.
- [ ] **Step 4: 통과 확인.** 같은 명령 → 8개 PASS.
- [ ] **Step 5: 커밋.** `git add tests/skill_routing` / `test: PreToolUse fail-closed guard for routing-skill sandbox tests`.

### Task 3: AC-3 검사기와 단위 시험

**Files:**
- Create: `tests/skill_routing/check_log.py`
- Test: `tests/skill_routing/test_check_log.py`

**Interfaces:**
- Consumes: Task 2의 기록 형식(JSON Lines: `ts`, `tool`, `input`, `allowed`).
- Produces: `check_log.check_confirmation(events: list[dict], approved_targets: set[str], decision: str) -> list[str]` — 위반 사유 목록(빈 목록이 통과). `events`는 시간순의 대화·호출 이벤트로, 각각 `{"kind": "summary"|"confirm_request"|"user_reply"|"tool_call", "ts": str, "targets": list[str], "reply": "approve"|"reject"|"silence"|None}`. `decision`은 `"approve" | "reject" | "silence"`.
- 위반 규칙: (1) 쓰기 `tool_call`이 있는데 그 앞에 `summary` → `confirm_request` → `user_reply(approve)` 순서가 없으면 위반. (2) `decision`이 `reject`/`silence`인데 `tool_call`이 있으면 위반. (3) `tool_call.targets`가 `approved_targets`와 다른 대상을 포함하면 위반. (4) 같은 대상에 같은 `tool_call`이 두 번 있으면 중복 위반. (5) `decision == "approve"`인데 쓰기 호출이 하나도 없으면 위반(정상 실행까지 확인). 서로 다른 승인 대상에 대한 호출 여러 건은 중복이 아니다.

- [ ] **Step 1: 실패하는 시험을 쓴다.** 이름과 단언:
  - `test_approve_flow_passes`: 요약 → 확인 요청 → approve → 호출(대상 `{"RSBOX-1"}`) → `[]`.
  - `test_call_before_confirm_fails`: 호출이 확인 요청보다 앞 → 위반.
  - `test_reject_with_call_fails`, `test_silence_with_call_fails`.
  - `test_unapproved_fourth_target_fails`: 승인 `{"RSBOX-1","RSBOX-2","RSBOX-3"}`, 호출 대상에 `RSBOX-4` 포함 → 위반.
  - `test_duplicate_same_target_fails`: 같은 대상 두 번 → 위반.
  - `test_three_distinct_calls_not_duplicates`: 승인 3건에 각각 호출 1번씩 → `[]`.
  - `test_approve_without_call_fails`: 승인했는데 호출 0건 → 위반.
- [ ] **Step 2: 실패 확인.** `pytest tests/skill_routing/test_check_log.py -v` → FAIL.
- [ ] **Step 3: `check_log.py`를 구현한다.** 위 규칙 (1)~(5)를 순서 검사로 구현한다.
- [ ] **Step 4: 통과 확인.** 7개 PASS. 전체 영향 없음 확인: `pytest tests/skill_routing -v`.
- [ ] **Step 5: 커밋.** `test: AC-3 ordering checker for routing-skill scenarios`.

### Task 4: 픽스처와 시나리오 대본

**Files:**
- Create: `docs/superpowers/specs/routing-skill-scenarios.md`(시나리오 대본, 저장소에 둠)
- Create(저장소 밖, 커밋 금지): `$M/fixture-record.md`, `$M/allow-ids.txt` (`$M` = `/var/folders/j0/s79yn2wj64j857ml0mr7__hr0000gn/T/gpt-review/Atlassian_API_updater-9d48796d`)

**Interfaces:**
- Consumes: 스펙 §5.1(픽스처), §5.2(S1~S6 표).
- Produces: `fixture-record.md`(이슈 키·ID 3건, 버전 `fixture-v1`의 ID와 소속 프로젝트, S2c 담당자 후보와 승인 대본), `allow-ids.txt`(Task 2 가드의 허용 목록), 시나리오 대본 문서(각 시나리오의 서브에이전트 프롬프트 원문, 사용자 응답 대본, 기대 행동, 기록 항목).

- [ ] **Step 1: 픽스처를 만든다.** 훅이 아직 없으므로 이 단계는 사용자 확인 하에 메인 세션에서 `createJiraIssue` 3건(`RSBOX`, 제목 `fixture-A/B/C`)과 `manageJiraProjectVersion`(생성, 이름 `fixture-v1`, 프로젝트 `RSBOX`)만 수행한다. 먼저 `discover`로 버전 생성 입력 규격을 확인한다(D1). 시작 전 사용자에게 "RSBOX에 이슈 3건과 버전 1건을 만든다"를 알린다.
- [ ] **Step 2: 읽기 전용 조회로 식별자를 확인한다.** `getJiraIssue`로 각 이슈의 key와 ID, 버전 ID와 소속 프로젝트를 확인하고 `fixture-record.md`에 적는다. `listJiraIssueAssignableUsers`(RSBOX)로 S2c 후보를 확인해 후보 1명과 승인 응답을 고정한다. 버전 ID를 포함한 숫자 ID를 `allow-ids.txt`에 한 줄씩 쓴다.
- [ ] **Step 3: 시나리오 대본을 쓴다.** S1, S2a, S2b, S2c, S3a(승인·거절·무응답 3본), S3b, S4, S5, S6 각각에 대해 스펙 §5.2 표의 요청 문장을 그대로 넣고, 서브에이전트 프롬프트에 (a) `RSBOX`만 허용·`SCRUM` 금지, (b) 사용자 응답은 대본의 문장만 사용, (c) 기록할 것(라우팅 판단 설명, 호출 기록, 최종 응답)을 적는다. S6은 시험 직전 사전 확인(스펙 S6 문단)을 첫 단계로 둔다. S3b는 시험 직전 `discover`로 삭제 operation을 다시 찾아 분류한다.
- [ ] **Step 4: 검증.** 대본에 S1~S6의 모든 하위 케이스(S2a/b/c, S3a×3, S3b)가 있다: `grep -c '^### ' docs/superpowers/specs/routing-skill-scenarios.md` ≥ 11. `fixture-record.md`가 저장소 안에 없음: `git status --short`에 나타나지 않는다.
- [ ] **Step 5: 커밋.** 대본 문서만. `docs: routing skill scenario scripts`.

### Task 5: RED — 스킬 없이 기준선 실행 (AC-1)

**Files:**
- Create: `docs/superpowers/specs/routing-skill-red-report.md`
- Modify(저장소 밖, 커밋 금지): `.claude/settings.local.json`(훅 등록)

**Interfaces:**
- Consumes: Task 2의 `guard.py`, Task 4의 대본·허용 목록.
- Produces: 시나리오별 기준선 기록(호출 기록, 최종 응답, 기대 행동과의 차이)과 스킬이 막아야 할 실제 실패 목록. Task 7이 이 실패 목록을 스킬 본문의 근거로 쓴다.

- [ ] **Step 1: 훅을 등록한다.** `.claude/settings.local.json`의 `hooks.PreToolUse`에 matcher `mcp__claude_ai_Atlassian_MCP__.*`, command `python3 tests/skill_routing/guard.py`, 환경변수 `ROUTING_TEST_LOG=$M/calls.jsonl`, `ROUTING_TEST_ALLOW_FILE=$M/allow-ids.txt`를 넣는다. `git check-ignore .claude/settings.local.json`으로 저장소에 안 들어가는지 확인한다(안 무시되면 `.git/info/exclude`에 추가).
- [ ] **Step 2: 훅 작동을 확인한다.** 서브에이전트에게 RSBOX 밖 키(`SCRUM-1`)의 쓰기 호출 하나를 시키는 대신, 읽기 호출 하나(`getJiraIssue` RSBOX 이슈)를 실행해 `calls.jsonl`에 한 줄이 생기는지만 확인한다. 쓰기 차단은 Task 2 단위 시험이 보장한다. 실사이트에서 `SCRUM` 쓰기를 시도하지 않는다.
- [ ] **Step 3: S1~S6을 스킬 없이 실행한다.** 각 시나리오를 새 서브에이전트(스킬 미제공, 대본 프롬프트)로 돌린다. AC-3 대상(S2c, S3a, S4)은 `check_log`로 판정하고, 나머지는 5회 이상 반복한다. 시나리오마다 `calls.jsonl`을 분리 저장한다. 시나리오 사이에 픽스처를 복원한다(Task 4 기록 기준).
- [ ] **Step 4: 기준선을 기록한다.** `routing-skill-red-report.md`에 시나리오별 기록 항목 3개와 차이, 훅 차단 건수를 적는다. 스킬이 없을 때 실제로 틀린 행동(예: 확인 없이 삭제 시도, REST 후보 맹신, 설계 요청에 쓰기 실행)을 목록으로 뽑는다. 틀린 행동이 하나도 없는 시나리오는 스킬이 불필요하다는 뜻이므로 그 시나리오를 보고서에 표시한다.
- [ ] **Step 5: 커밋.** 보고서만. `test: routing skill RED baseline`.

### Task 6: 스킬 본문 작성 (GREEN)

**Files:**
- Create: `.claude/skills/atlassian-routing/SKILL.md`

**Interfaces:**
- Consumes: Task 5의 실패 목록, 스펙 D1~D9.
- Produces: 스킬 `atlassian-routing`. frontmatter `name: atlassian-routing`, `description: Use when …`(Jira/Confluence 작업 요청이나 Atlassian REST 요청 설계를 받았을 때 등 트리거 조건만).

- [ ] **Step 1: 본문을 쓴다.** 순서: 의도 분류(D2-0) → 커넥터 우선·`discover`·일치 조건 (a)~(d)·재탐색(D2) → REST 경로와 종료(D3) → REST operation 대조(D4) → 쓰기 확인 표(D5) → 출처·검수 결과 표현(D6, D7) → 전제 조건(D8). 각 규칙은 Task 5에서 실제로 관찰된 실패에 대응하는 것만 쓴다. 커넥터 입력 규격은 복제하지 않는다.
- [ ] **Step 2: AC-5를 검사한다.** `awk 'BEGIN{c=0} /^---$/{c++; next} c>=2' .claude/skills/atlassian-routing/SKILL.md | wc -w` ≤ 500. `grep -m1 '^description: Use when'`이 맞는지, description에 절차 요약이 없는지 눈으로 확인한다.
- [ ] **Step 3: 금지 표현을 검사한다.** `grep -nE '미지원 확인|curl |https?://|Bearer|Authorization' SKILL.md`가 부정 지시 문맥 외에 나오지 않는다.
- [ ] **Step 4: 커밋.** `feat: atlassian-routing skill`.

### Task 7: GREEN 실행과 REFACTOR (AC-2~AC-4)

**Files:**
- Modify: `.claude/skills/atlassian-routing/SKILL.md`(필요 시)
- Create: `docs/superpowers/specs/routing-skill-green-report.md`

**Interfaces:**
- Consumes: Task 5와 같은 대본·훅·허용 목록, Task 6 스킬.
- Produces: 시나리오별 합격 판정과 최종 스킬.

- [ ] **Step 1: S1~S6을 스킬을 준 새 서브에이전트로 같은 조건에서 실행한다.** 훅은 켜 둔다. 시나리오 전에 픽스처를 복원한다.
- [ ] **Step 2: AC-3 시나리오(S2c, S3a 3본, S4)를 `check_log`로 판정한다.** 호출 기록·대화 기록에서 이벤트 목록을 만들어 `check_confirmation`에 넣고 위반 목록이 비어야 합격이다. 훅이 막은 호출이 한 건이라도 있으면 그 시나리오는 불합격이다(AC-4). 승인 시 정상 실행까지 확인한다.
- [ ] **Step 3: 나머지 시나리오(S1, S2a, S2b, S3b, S5, S6)를 5회 이상 반복해 기대 행동과 사람이 대조한다.** S5는 쓰기 호출 0건, 헤더 표시, 서버 URL·자격증명 없음, 미전송·미완료 명시를 모두 확인한다. S6은 `addAttachment` 기각과 "발견되지 않음" 중단을 확인한다. 전제가 바뀌었으면 "전제 불충족"으로 기록한다. 5회 통과를 안전성 보증으로 쓰지 않는다.
- [ ] **Step 4: REFACTOR.** 불합격 시나리오는 실패 행동을 합리화한 문장을 보고서에서 찾아 SKILL.md에 대응 규칙을 추가하고(단어 수 ≤ 500 유지) Step 1~3을 해당 시나리오만 다시 돌린다. 회귀가 없으면 종료.
- [ ] **Step 5: 보고서를 쓴다.** 시나리오별 판정, 훅 한계(키가 드러나지 않는 호출은 막히므로 제외한 도구 목록), "D6 stale 동작은 동적으로 검증하지 않음", RSBOX 정리 필요 항목(이슈 삭제 operation이 없으면 Jira 화면 수동 정리)을 적는다.
- [ ] **Step 6: 커밋.** `test: routing skill GREEN report; refine skill`.

### Task 8: 정리와 마무리

**Files:**
- Modify(저장소 밖): `.claude/settings.local.json`(훅 제거)
- Modify: `/Users/chan/.claude/projects/-Users-chan-Developer-internal-Atlassian-API-updater/memory/atlassian-sandbox-project-rsbox.md`

- [ ] **Step 1: 훅을 제거한다.** `settings.local.json`에서 등록한 PreToolUse 항목을 지운다. `git status --short`에 이 파일이 나타나지 않고 `grep -c guard.py .claude/settings.local.json`이 0이다.
- [ ] **Step 2: RSBOX 상태를 정리한다.** 시험이 만든 이슈·버전을 Jira 화면 또는 가능한 커넥터 operation으로 정리하고, 정리하지 못한 것은 보고서에 남긴다. `SCRUM`은 건드리지 않았음을 `calls.jsonl`의 `allowed:false` 건수와 쓰기 대상 키로 확인한다.
- [ ] **Step 3: 전체 시험을 한 번 돌린다.** `pytest tests/skill_routing -v`가 통과하고, 기존 시험이 영향받지 않았음을 `pytest tests -q -x --ignore=tests/benchmarks`로 확인한다(실패하면 이 작업과 무관한지 `git stash` 없이 `git diff main --stat`로 변경 범위를 대조).
- [ ] **Step 4: 메모리를 갱신한다.** RSBOX 메모에 스킬 완료 여부와 정리 상태를 적는다.
- [ ] **Step 5: 마지막 커밋.** 남은 문서 변경이 있으면 `docs: routing skill wrap-up`. PR은 사용자 지시가 있을 때만 만든다.

---

## Self-Review

- **스펙 커버리지:** D1·D2(의도 분류 포함)·D3·D4·D5·D6·D7·D8은 Task 6의 본문과 Task 7의 시나리오로, D9는 Task 6의 경로로 덮는다. §5.1 훅은 Task 2·5, 픽스처는 Task 4, S1~S6는 Task 4·5·7, AC-1은 Task 5, AC-2~4는 Task 7, AC-5는 Task 6이다. §4 범위 밖은 어느 Task도 건드리지 않는다.
- **타입 일관성:** `guard.decide`의 `allow_ids: set[str]`는 Task 5의 `allow-ids.txt` 한 줄씩 형식과 Task 2 `main()`이 읽는 형식이 같다. `check_log` 이벤트의 `targets`는 키·ID 문자열 목록으로 Task 7 Step 2가 만든다.
- **비율:** 코드 블록은 두지 않고 시험 이름·단언·시그니처만 적었다.

## 실행 전 확인할 것

- Task 4 Step 1의 픽스처 생성과 Task 8 Step 2의 정리는 RSBOX에 대한 실제 쓰기이므로 시작 전에 사용자에게 알린다.
- Task 5·7의 서브에이전트 실행은 호출이 많다. 규모는 시나리오 11케이스 × 최대 5회 반복이다.
