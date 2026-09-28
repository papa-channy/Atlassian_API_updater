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
- ✅ 오프라인 유닛 테스트 67개 전부 통과 (`python -m unittest discover -s tests -t .`).
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
└── storage.py        # cache/metadata 파일 읽기/쓰기, atomic replace

tests/               # unittest 67개 (오프라인) + live_smoke.py (수동, 네트워크 필요)
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

Claude Code에 연결하려면 (예: `.claude/settings.json` 또는 `claude mcp add`):

```json
{ "mcpServers": { "atlassian-openapi": { "command": "python", "args": ["-m", "tools.atlassian_docs.mcp"], "cwd": "<repo root>" } } }
```

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
python -m unittest discover -s tests -t .     # Phase 1 + Phase 2 전체, 네트워크 호출 없음 (sync는 fake 주입)
python tests/live_mcp_smoke.py                 # 수동, 네트워크 필요 — 실제 3개 source normalize 확인 (진단용, gate 아님)
```

`mcp` SDK가 설치되지 않은 환경에서는 `tests/mcp/test_server.py`가 skip되고 나머지는 그대로 통과한다.
