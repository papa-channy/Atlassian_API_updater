# Atlassian API Docs Lightweight Sync

Jira Cloud / Confluence Cloud 공식 REST 문서 페이지에 인라인 임베드된 OpenAPI specification을 추출해, 버전과 무관한 고정 경로에 로컬로 캐싱하는 zero-dependency Python CLI.

AI 코딩 에이전트(Claude Code 등)가 Jira/Confluence 연동 코드를 작성하기 전에, 기억에 의존하거나 오래된 엔드포인트를 추측하는 대신 **항상 공식 최신 스펙**을 로컬 파일로 참조할 수 있게 하는 것이 목적이다.

> **문서 버전:** v1.2 · **상태:** 구현 완료, `main`에 머지·push됨 (2026-09-16)

---

## 왜 필요한가

Jira/Confluence의 API major version은 시간이 지나면 바뀐다(예: Jira Platform v3 → v4). 특정 버전이나 OpenAPI 파일 URL을 코드에 직접 박아두면, Atlassian이 버전을 올릴 때마다 동기화 로직 자체를 고쳐야 한다.

이 도구는 **API 버전이나 OpenAPI 다운로드 URL을 어디에도 하드코딩하지 않는다.** 대신 Atlassian이 제공하는, 버전과 무관한 안정적인 문서 진입점(discovery URL) 3개만 알고 있고, 실행할 때마다 그 페이지를 받아 현재 공식 스펙을 동적으로 추출한다.

## 빠른 사용법

```bash
# 저장소 루트에서 실행 (캐시 경로가 현재 작업 디렉터리 기준으로 정해짐)
python -m tools.atlassian_docs              # 기본 실행 — 24시간 TTL 내면 네트워크 접근 없음
python -m tools.atlassian_docs --force       # TTL 무시하고 즉시 재추출
python -m tools.atlassian_docs --status      # 캐시 상태만 조회 (항상 exit 0)
```

실행 후 `.atlassian-docs/`(gitignore 대상) 아래에 다음이 생긴다:

```text
.atlassian-docs/
├── jira-platform.json   # Jira Platform REST API OpenAPI spec
├── jira-software.json   # Jira Software / Agile API OpenAPI spec
├── confluence.json      # Confluence REST API OpenAPI spec
└── metadata.json        # 소스별 resolved URL, api_version, sha256, 타임스탬프 등
```

AI 에이전트가 이 도구를 어떻게 써야 하는지는 [`AGENTS.md`](./AGENTS.md)에 정리되어 있다 — Claude Code 같은 에이전트는 Jira/Confluence 관련 작업 전에 이 파일의 지시를 따라 자동으로 명령을 실행하도록 되어 있다.

## 동작 방식 (중요: 상시 자동화 아님)

**백그라운드 스케줄러나 데몬은 없다.** 사람이든 AI 에이전트든 명령을 직접 실행해야만 갱신이 일어난다.

- 마지막 성공 확인으로부터 **24시간 이내**면 `python -m tools.atlassian_docs`를 실행해도 네트워크 요청 자체를 하지 않고 기존 캐시를 그대로 쓴다.
- 24시간이 지났거나 `--force`를 주면, 그때 Atlassian 문서 페이지를 다시 받아 스펙을 재추출한다.
- 대상은 이 3개 소스뿐이다: `jira-platform`, `jira-software`, `confluence`.

즉 "실행될 때, 그리고 하루가 지났을 때"만 최신화되는 pull-on-demand 구조지, 상시 자동 동기화가 아니다. 상시 자동화(cron 등)는 현재 스펙 범위 밖이며 의도적으로 비목표로 뒀다.

## exit code

| exit | 의미 |
|---|---|
| `0` | 모든 소스 정상 사용 가능 |
| `1` | degraded — 일부 소스가 remote refresh에 실패했지만 기존 캐시로 fallback 가능 |
| `2` | unavailable — 일부 소스에 사용 가능한 캐시 자체가 없음 |

에이전트나 CI에서 이 exit code로 "Jira/Confluence 작업을 계속해도 되는지"를 판단할 수 있다.

## 핵심 설계 결정

- 페이지가 실제로는 React SPA라서, 문서 안에 `<a href="...">OpenAPI</a>` 같은 링크가 없다. 스펙 전체가 `<script>window.__DATA__ = {...}</script>` 안에 JSON으로 인라인 임베드되어 있다 — 이걸 직접 curl로 검증한 뒤 추출 방식을 전면 재설계했다.
- API version은 `resolved_documentation_url`의 URL path에서만 정규식으로 추출한다(`/rest/v3/` → `"v3"`). `info.version`이나 `paths` 키는 절대 신뢰하지 않는다 — Jira Software는 하나의 spec 안에 `/rest/agile/1.0/`과 `/rest/*/0.1/` 같은 서로 다른 버전 네임스페이스가 공존하기 때문에, `api_version: null`이 정상 상태로 허용된다.
- 실패 시 항상 fail-safe: HTTP 실패든 extraction 실패든, 기존에 잘 받아둔 캐시가 있으면 절대 지우지 않는다.
- 외부 패키지 의존성 0개 (`pip install` 불필요, 테스트도 `unittest` 표준 라이브러리만 사용).

## 현재 상태

- ✅ 스펙(v1.2) → 구현 계획(6개 TDD 태스크) → Subagent-Driven Development로 구현 → 태스크별 리뷰 6/6 통과 → 전체 브랜치 최종 리뷰 및 수정 → `main` 머지 및 `origin` push 완료.
- ✅ 오프라인 유닛 테스트 전부 통과 — Phase 1 67개 포함 전체 401개 (`python -m unittest discover -s tests -t .`; `python -S`로 선택 의존성 없이 실행하면 18개 skip). Phase 2에서 `intelligence/`(정규화·레지스트리·검색·요청 검증)와 `mcp/`(MCP 서버) 모듈이 추가되었다 (아래 Phase 2 절 참고).
- ✅ 실제 Atlassian 사이트 대상 live smoke test(`tests/live_smoke.py`, 수동 실행) 통과 — jira-platform `v3`, jira-software `(버전 없음)`, confluence `v2` 확인.

### 알려진 후속 과제 (머지는 막지 않음)

- `jira-software` 전용 오프라인 fixture 부재 — 현재 이 소스의 추출 검증은 live smoke test에만 의존.
- `sync.py`에서 소스당 캐시 파일을 최대 3번까지 중복으로 읽고 파싱함 — 성능엔 무해하지만 정리 여지 있음.
- `storage.py`의 atomic write가 `fsync`를 하지 않음 — 전원 손실 시에도 §22 self-heal 로직으로 다음 실행에서 복구는 되지만, 더 엄격하게 하려면 추가 가능.
- 초기 커밋 2개(`70ff33f`, `6fe0869`)의 `Co-Authored-By` 트레일러가 subject line에 바로 붙어 있어 일부 git 툴에서 정상 trailer로 인식되지 않을 수 있음(기능에는 영향 없음).

## 문서

| 문서 | 내용 |
|---|---|
| [`docs/superpowers/specs/2026-09-16-atlassian-docs-sync-design.md`](./docs/superpowers/specs/2026-09-16-atlassian-docs-sync-design.md) | 기술 스펙 v1.2 — 요구사항, 알고리즘, metadata 스키마, 40개 acceptance criteria |
| [`docs/superpowers/plans/2026-09-16-atlassian-docs-sync-implementation.md`](./docs/superpowers/plans/2026-09-16-atlassian-docs-sync-implementation.md) | 구현 계획 — 6개 태스크의 정확한 코드/테스트 명세 |
| [`AGENTS.md`](./AGENTS.md) | AI 에이전트용 사용 지침 (exit code, 캐시 경로 규칙 포함) |

## 코드 구조

```text
tools/atlassian_docs/
├── __main__.py     # CLI: 인자 파싱, 출력 포맷, exit code — sync 로직 없음
├── sources.py      # 3개 discovery URL만 (버전/CDN URL 없음)
├── extractor.py     # 순수 함수: HTML → OpenAPI dict (HTTP 모름)
├── sync.py          # orchestration: TTL, HTTP, 캐시/metadata self-heal, 버전 감지, 실패 정책
├── storage.py        # cache/metadata 파일 읽기/쓰기, atomic replace
├── intelligence/     # Phase 2: normalizer, gate, registry, search, schemas, inspect,
│                     #          request_template, request_check, provenance, lastgood, manager
└── mcp/              # Phase 2: MCP stdio 서버 (__main__, server, tools) — mcp SDK 필요

tests/               # unittest (오프라인, Phase 1 + tests/intelligence + tests/mcp) + live_smoke.py / live_mcp_smoke.py (수동, 네트워크 필요)
```

의존성 방향은 `__main__ → sync → {extractor, storage}` 한 방향으로 고정되어 있다.

---

## Phase 2: Atlassian OpenAPI Intelligence MCP

Phase 1이 OpenAPI spec을 로컬 파일로만 캐싱했다면, Phase 2는 그 캐시 위에 **MCP(Model Context Protocol) 서버**를 얹어 AI 코딩 에이전트가 파일을 직접 열어 읽는 대신 구조화된 tool 호출로 Jira/Confluence API를 조회·검색·검증할 수 있게 한다. 공식 `mcp` SDK 2.x(`MCPServer`, stdio transport)로 구현되어 있고, 실제 Jira/Confluence API를 호출하지 않으며(`execute_*` 없음), 서버 URL이나 자격증명도 생성하지 않는다 — 어디까지나 "무엇을 어떻게 호출해야 하는가"를 알려주는 조회 전용 계층이다.

> **문서 버전:** v2.1 · 스펙: [`docs/superpowers/specs/2026-09-28-atlassian-openapi-intelligence-mcp-design.md`](./docs/superpowers/specs/2026-09-28-atlassian-openapi-intelligence-mcp-design.md) · 구현 계획: [`docs/superpowers/plans/2026-09-28-atlassian-openapi-intelligence-mcp-implementation.md`](./docs/superpowers/plans/2026-09-28-atlassian-openapi-intelligence-mcp-implementation.md)

### 설치 및 실행

```bash
pip install -r requirements-mcp.txt   # mcp>=2.2,<3 — MCP 계층에만 필요
python -m tools.atlassian_docs.mcp    # stdio transport, 저장소 루트에서 실행
```

Phase 1과 마찬가지로 캐시 경로는 현재 작업 디렉터리 기준이므로 반드시 저장소 루트에서 실행한다. MCP SDK가 설치되어 있지 않으면 `tools.atlassian_docs.mcp`의 `ImportError`를 잡아 설치 안내와 함께 exit code 3으로 종료한다 — Phase 1 CLI와 `intelligence/` 계층은 SDK 없이도 그대로 동작한다.

Claude Code에 연결하려면 저장소 루트에서 project scope로 등록한다:

```bash
claude mcp add atlassian-openapi -- python -m tools.atlassian_docs.mcp
```

또는 저장소 루트의 project `.mcp.json`(이 저장소에 포함되어 있다)을 사용한다:

```json
{ "mcpServers": { "atlassian-openapi": { "command": "python", "args": ["-m", "tools.atlassian_docs.mcp"] } } }
```

Claude Code는 project-scoped 서버를 프로젝트 루트를 작업 디렉터리로 하여 시작하므로, 캐시 경로(`.atlassian-docs/`, 현재 작업 디렉터리 기준)가 올바르게 잡힌다.

### 7개 Tool

| tool | 역할 |
|---|---|
| `search_operations` | 자연어/키워드로 operation 검색 (source/method/tag/deprecated 필터, 결정적 순위) |
| `get_operation` | 특정 operation의 상세 정보 (기본은 example 제외, description 500자 절단) |
| `get_schema` | 특정 schema를 `max_depth`/`max_nodes` 한도로 펼쳐서 조회 |
| `build_request_template` | operation에 대한 요청 템플릿 생성 — `server: null`, Authorization/Cookie 값 없음, 누락된 required는 `missing_required`로 보고 |
| `check_request` | 요청 후보를 고정 규칙 세트로 검사 (`valid` 키 없음, `compatible` + `checked`/`not_checked`) |
| `get_api_status` | 소스별 provenance, refresh 상태, backoff 여부 조회 (`ensure_fresh` 트리거 안 함) |
| `refresh_api_docs` | 즉시 refresh 시도 (다른 refresh와 겹치면 `refresh_in_progress`) |

### Self-update 흐름

MCP 서버는 백그라운드 데몬 없이, 각 조회 tool 호출 시 `ensure_fresh()`를 거쳐 필요하면 스스로 최신화를 시도한다:

1. **sync** — Phase 1의 `sync.sync_all`을 통해서만 원격 스펙을 가져온다 (Phase 2는 직접 outbound HTTP를 하지 않는다).
2. **SHA 비교** — 캐시된 spec의 sha256이 바뀌었을 때만 재빌드를 시도한다.
3. **gate** — dialect(3.0.x/3.1.x만 지원), 구조적 유효성을 통과해야 한다. 통과 못 하면 이전 registry를 유지하고 `candidate` 진단만 기록한다.
4. **integrity** — normalize 결과가 자기 일관적인지 검사한다. 실패하면 마찬가지로 이전 registry를 유지한다.
5. **last-good** — 재빌드에 성공하면 last-good 스냅샷을 갱신한다. 프로세스가 재시작됐는데 현재 캐시가 실패하면 last-good에서 복구한다 (`served_from_last_good`).
6. **atomic swap** — 새 registry가 모든 단계를 통과한 뒤에만 원자적으로 active state를 교체한다. 실패한 refresh 이후에는 15분(900초) backoff가 적용되고, 같은 sha는 재검사하지 않는다.

### Degraded 동작

- 일부 source가 `stale`이어도 나머지 source는 정상 서비스되고, 결과의 `provenance`에 상태와 사유가 함께 표시된다.
- 일부 source가 `unavailable`이면 해당 source를 지정한 요청은 `source_unavailable` 오류를 반환하고, 검색 결과에서는 제외되지만 provenance에는 계속 나타난다.
- 시작 시 모든 source가 unavailable이면 1회 sync를 시도한 뒤에도 실패하면 프로세스가 exit code 2로 종료한다.
- `check_request.compatible`은 고정된 규칙 세트가 오류를 찾지 못했다는 뜻일 뿐, 실제 API가 요청을 수락한다는 보장은 아니다.

### 오프라인 테스트

```bash
python -m unittest discover -s tests -t .     # Phase 1 + Phase 2(.5) 전체, 네트워크 호출 없음 (sync는 fake 주입)
python tests/live_mcp_smoke.py                 # 수동, 네트워크 필요 — 실제 3개 source normalize 확인 (진단용, gate 아님)
```

`mcp` SDK가 설치되지 않은 환경에서는 `tests/mcp/test_server.py`가 skip되고, `jsonschema`(`requirements-validate.txt`)가
없으면 jsonschema 본문 검증 테스트가 skip된다. 나머지는 그대로 통과한다.

### Phase 2.5: Discovery hardening

설계: [spec v1.2](docs/superpowers/specs/2026-09-29-phase2.5-discovery-hardening-design.md) ·
구현 계획: [plan](docs/superpowers/plans/2026-09-30-phase2.5-discovery-hardening-implementation.md) ·
Phase 3 판정 기록: [docs/phase3-readiness.md](docs/phase3-readiness.md)

**식별자 정확 일치 + alias 확장 (`search_operations`)**

- 질의가 내부 공백 없는 operationId(대소문자 구분 우선, 그다음 대소문자 무시)이거나 canonical key
  (`jira-platform:GET:/rest/api/3/issue/{issueIdOrKey}`)이면 그 operation을 1위로 고정(pin)한다. 고정된 결과에는
  `match` 필드가 붙고 응답의 `exact_match`가 `true`다. `"get issue"`처럼 공백이 있는 질의는 고정하지 않는다.
- 질의 토큰은 `intelligence/data/search_aliases.json`의 alias(질의→스펙 방향)로 확장된다. 응답에서
  `query_tokens`(원 토큰), `alias_tokens`(alias로 추가된 토큰), `expanded_tokens`(합계)가 분리되어 나온다.
  alias 토큰은 감쇠 가중치를 받고, 전 토큰 일치 보너스는 원 토큰에만 적용된다.
- 응답에 `intelligence_fingerprint`(registry + alias·override 데이터 + 정책 버전의 해시)와 `intelligence_policy`(alias·override sha256과 `POLICY_VERSIONS`)가 포함된다.

**검색 질의 로그 (opt-in, 로컬 전용)**

- 환경변수 `ATLASSIAN_DOCS_SEARCH_LOG`가 `1`/`true`/`yes`일 때만 `.atlassian-docs/intelligence/search_log.jsonl`에
  질의·필터·토큰·상위 3개 결과(key, score)·fingerprint를 한 줄씩 기록한다. 기본은 비활성이며 비활성이면 파일을 만들지 않는다.
- 질의는 2,048자로 절단되고 제어문자는 정규화된다. 파일이 5 MiB에 이르면 `search_log.jsonl.prev`로 회전한다. 기록 실패(OSError)는 무시된다.
- 개인정보: 로그는 로컬 파일로만 남고 어디로도 전송되지 않는다. 질의에 비밀값을 넣지 말 것. Phase 3 판정의
  Runtime stability 축(§18)은 이 로그를 켠 상태의 실사용 기록을 전제로 한다.

**Operation quirks (스펙 밖 요청 요구사항)**

- `intelligence/data/operation_quirks.json`의 curated override와 description mining(advisory 전용)으로
  스펙에 없는 요구사항을 보강한다. 예: addAttachment의 `X-Atlassian-Token: no-check`.
- `build_request_template`의 헤더 항목: `declared_required`(스펙), `effective_required`(스펙 ∪ required quirk),
  `origins`, `effective_required_origins`, `enforcement`, `note`, 필요 시 `value`; 기존 `required`는 호환용으로 유지.
  `effective_required: true`이면 `missing_required`에 포함된다. 단, 호출자가 credential 헤더(`Authorization` 등)를
  넘기면 값은 버려지지만 "존재"로 간주되어 `missing_required`/`required` 오류에서 빠진다(없으면 여전히 missing).
- quirk 블록은 tool마다 다르다: `build_request_template.quirks = {applied, advisories, suppressed, request_hints}`,
  `check_request.quirks = {applied, suppressed, request_hints, notes}`. `request_hints.multipart_fields`가 있으면
  해당 필드가 없는 본문에 `multipart_field_missing` warning이 붙는다.

**본문 검증 (`check_request`, 선택적 jsonschema)**

```bash
pip install -r requirements-validate.txt   # jsonschema>=4.18,<5 (없어도 동작, 구조 검사로 fallback)
```

- `body_check`는 `"jsonschema"`(OAS 3.0 스키마를 draft-7로 변환해 전체 검증) 또는 `"structural"`(Phase 2 규칙)이다.
  jsonschema 경로는 **OAS 3.0 스펙에만** 적용된다.
- `"structural"`일 때 `body_check_reason`이 이유를 말한다: `oas31_not_supported`, `jsonschema_not_installed`,
  `schema_not_fully_resolvable`, `schema_transpile_failed`, `jsonschema_schema_error`, `jsonschema_runtime_error`,
  `no_body`, `no_body_schema`. 이 경우 본문은 완전히 검증된 것이 아니다.
- 응답에 `validation_engine`과 `validation_fingerprint`(intelligence fingerprint + engine·version·transpiler version의 해시)가 포함된다.
- 변환 규칙: `nullable`, boolean `exclusiveMinimum/Maximum`, `readOnly`(required에서 제거 후
  `readonly_property_present` warning), OAS 전용 키 제거, 그리고 `oneOf`는 `anyOf`로 취급한다(Atlassian union은
  가지가 겹치므로).
- 알려진 한계: `oneOf`의 배타성은 검사하지 않는다. `additionalProperties`/`not` 값 스키마 아래의 `readOnly`는
  (키는 제거되지만 경로를 기록하지 않으므로) 본문에서 검출하지 않고 경고도 내지 않는다.
  multipart 스키마가 `type: array`인 operation(예: addAttachment)은 dict 본문으로 jsonschema 경로를 통과할 수 없다
  (multipart hint는 dict 본문을 요구) — Phase 3 사전 과제로 보류. 오류 메시지는 제출값을 되풀이하지 않으므로 `anyOf`/`pattern` 실패는
  "violates <validator>" 같은 일반 문구로 나온다.

**MCP `check_request(..., body_present)`**

MCP SDK는 "body 생략"과 "JSON null"을 둘 다 `None`으로 전달하므로 `body_present`로 구분한다:
`false` → 본문 없음(`body`가 주어졌으면 무시하고 `body_ignored` warning), `true` → `body`를 그대로 사용
(`null`이면 명시적 JSON null), 생략 → Phase 2 동작.

**`get_api_status` 추가 필드**

`intelligence_fingerprint`, `intelligence_policy`, `capabilities.validation`(`validation_engine`과 동일),
`diagnostics.orphaned_override_keys`(registry에 없는 override key), `diagnostics.header_candidates`
(description에 언급됐지만 mining 허용 목록 밖인 `X-*` 헤더 `{key, header}`, 자동 적용 없음), `refresh.search_log_enabled`.

**기타**

- 스펙 gate에서 거부된 캐시만 있는 source는 메타데이터가 TTL 이내면 매 호출마다 다시 sync하지 않는다.
- 자격증명 헤더 값(정적·동적 apiKey 헤더)은 template/check 결과, 오류 메시지, 검색 로그, MCP `internal_error`에 나타나지 않는다.

**검색 품질 라운드 1 (search 정책 버전 3)**

설계: [Round 1 spec](docs/superpowers/specs/2026-09-30-search-quality-round1-design.md).
어휘 점수에 네 가지 구조 신호를 더한다: 질의 동사와 HTTP 메서드의 일치(`method_intent`), 질의가 언급하지 않은
경로 세그먼트 감점(`path_unmatched`, 상한 있음), 제품 단어 힌트(`product_hint` — `jira`/`confluence`/`wiki`/
`agile`/`board`/`sprint`/`backlog`/`epic`이 해당 source를 가산), 경로 마지막 리터럴 세그먼트를 질의가 온전히
언급할 때의 가산(`resource_match`, 터미널 리소스 일치). 각 결과의 `signals`가 네 값과 근거 토큰을 보여 주어 왜 그
순위인지 설명한다. 표(동사·noise·힌트)와 상수는 `intelligence/data/search_ranking.json`에 있고
`POLICY_VERSIONS["search"] == 3`, `intelligence_policy`에 `ranking_sha256`·`ranking_structure_sha256`이 붙는다.

상수는 손으로 고르지 않는다. `tests/tune_search_ranking.py --cache-dir <스냅샷>`이 `tuning_grid`의 모든 조합을
seed·regression_negative로 평가해 결정적 규칙으로 하나를 고르고 `constants`만 기록하며,
`tests/benchmarks/search-tuning-round1.jsonl`에 한 줄을 남긴다(`--dry-run`은 아무것도 쓰지 않는다).

벤치마크는 봉인 절차를 따른다: A(관찰된 집합을 seed로 강등) → T(표 freeze + 캐시 스냅샷) → B(새 held_out 16·
negative 8을 repo 밖 평문으로 두고 sha256·분포만 `round1_seal`에 봉인) → T2(v1.4 표 재동결) → 구현·튜닝 →
C(scorer·정책·평가기 freeze, `evaluation_code_sha256` 기록) → D(봉인 해제, 최종 평가 1회). 기록은
[docs/phase3-readiness.md](docs/phase3-readiness.md).

Round 1 결과: Discovery gate 실패 (held_out 4/16, negative 5/8) → Round 2 필요; 판정 기록은
[docs/phase3-readiness.md](docs/phase3-readiness.md#search-quality-round-1--decision-record-2026-09-30) 참고.

**검색 벤치마크 진단 (수동, 오프라인)**

```bash
python tests/diag_search_queries.py --sets seed,regression_negative --cache-dir ~/.atlassian_api_updater/round1-cache
python tests/diag_search_queries.py --bench <평문> --cache-dir <스냅샷> --json out.json   # 커밋 D 전용
```

`--cache-dir`는 스냅샷의 임시 복사본으로 `storage.CACHE_DIR`를 패치한다(기본은 `.atlassian-docs/`). 시작 시 registry
fingerprint·spec sha를 `round1_seal`과 비교해 다르면 경고하고, 그 상태에서 held_out/negative를 요청했거나 `--bench`가
주어졌으면 평가 없이 exit 2.
실패마다 top-5(key, score, signals)와 `git_commit`·fingerprint·`evaluation_code_sha256`·`sealed_sha256`을 보고한다.
벤치마크 파일은 수정하지 않는다.

봉인 도구는 `tests/benchmarks/round_seal.py`이며 모든 하위 명령이 `--round N`을 받는다(기본 1);
`freeze --round N --cache-dir S`는 `tests/benchmarks/round_freeze.json`에 라운드 동결 항목을 추가한다.

**검색 품질 라운드 2**

설계: [Round 2 spec](docs/superpowers/specs/2026-10-02-search-quality-round2-design.md). Round 1 게이트 실패
(held_out 4/16, negative 5/8) 이후 사전·후보 도구와 결정적 튜닝 파이프라인을 추가한다. 도구는
`tests/benchmarks/round_seal.py --round 2`(`freeze`/`verify-freeze` 포함), `tests/benchmarks/alias_candidates_tool.py`,
`tests/benchmarks/concept_lexicon_check.py prepare/finalize/merge`, 그리고 한-방향(one-way) 파이프라인인
`tests/tune_search_ranking.py`(상수·alias 패치를 커밋하는 `--adopt`, 결정성을 재확인하는 `--verify`)이다.
소스 스냅샷은 커밋 H 직후 한 번만 만들어 `$ATLASSIAN_DOCS_ROUND2_CACHE`(존재 시 거부)에 두고, T 이후 재스냅샷은
없다. 라운드는 세 종료 상태 중 하나로 끝난다: 성공(커밋 D), 튜닝 실패(커밋 F, 정책 파일은 B 상태로 유지), abort
(커밋 X, 튜닝 통과 후 전체 테스트 실패로 run이 거부된 경우). `tests/diag_search_queries.py --round N`이 해당
라운드의 `round{N}_seal`을 사용하고, 평문 hidden 레코드는 origin이 `held_out-r{N}`/`negative-r{N}`이어야 한다.
