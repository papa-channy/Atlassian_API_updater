# Atlassian OpenAPI Intelligence MCP — Phase 2 Technical Specification

**문서 버전:** v2.1
**기준일:** 2026-09-28
**선행 구현:** Atlassian API Docs Lightweight Sync v1.2 (`tools/atlassian_docs/`, Phase 1 완료 commit `ffbdd42`, 오프라인 테스트 67개 통과)
**목적:** Phase 1이 캐싱한 공식 Jira/Confluence OpenAPI를 정규화된 지식 계층으로 바꾸고, AI 코딩 에이전트가 MCP를 통해 검색·해석·요청 구조 생성·구조 검사를 할 수 있게 한다.
**설계 원칙:** Registry-first / Fixed small tool surface / Cache-first startup / Provenance everywhere / Gate before swap / Durable last-known-good / Fail-safe / No execution

---

## 0. 배경과 선행 결정

### 0.1 Phase 1이 끝낸 것

```text
Atlassian Official Docs → embedded window.__DATA__ 추출 → .atlassian-docs/{source}.json + metadata.json
```

Phase 1 core(`sources.py`, `extractor.py`, `sync.py`, `storage.py`, `__main__.py`)는 stdlib만 사용하고, 의존 방향은 `__main__ → sync → {extractor, storage}`로 고정되어 있다. Phase 2는 이 core를 **수정하지 않고** 소비만 한다.

### 0.2 2026-09-28 실제 스펙 프로파일 (설계 근거)

| source | openapi | paths | operations | operationId 없음 | 중복 operationId | path-level parameters | deprecated | components.schemas | 기타 components | 크기 |
|---|---|---|---|---|---|---|---|---|---|---|
| jira-platform | 3.0.1 | 423 | 619 | 0 | 0 | 0 | 29 | 975 | – | 3.5 MB |
| jira-software | 3.0.1 | 78 | 105 | 0 | 0 | 27 paths | 8 | 66 | – | 1.1 MB |
| confluence | 3.0.3 | 151 | 218 | 0 | 0 | 0 | 1 | 142 | requestBodies 24 | 0.9 MB |

관찰된 사실과 설계에 미치는 영향:

- 합계 942 operations / 1,183 schemas. **선형 lexical search로 충분**하며 SQLite·embedding·외부 검색엔진은 필요 없다.
- `$ref`는 전부 `#/components/...` 형태의 local ref. 외부 ref는 관찰되지 않았지만 §8에서 graceful하게 처리한다.
- jira-software는 path-level `parameters`를 실제로 사용한다. **`(name, in)` 기준 operation-level override 병합 규칙이 필수**다(§7.3).
- Confluence `servers`는 `https://{your-domain}/wiki/api/v2` 처럼 tenant 변수를 포함한다. Phase 2는 **서버 URL을 만들지 않는다**(§15).
- `securitySchemes`는 `OAuth2`/`basicAuth`(Jira), `basicAuth`/`oAuthDefinitions`(Confluence)로 이름이 제품마다 다르다. security 정보는 OR/AND 구조 그대로 보존하되 해석은 하지 않는다(§6).
- Atlassian 확장 필드 `x-atlassian-oauth2-scopes`, `x-experimental`, `x-changes`, `x-atlassian-connect-scope`, `x-atlassian-data-security-policy`, `x-atlassian-narrative`, `x-showInExample`가 존재한다. **`x-atlassian-oauth2-scopes`와 `x-experimental` 두 개만 보존**하고 나머지는 무시한다(§7.5).
- 응답의 `example` 문자열이 수 KB에 이른다. **normalizer 단계에서 example을 버린다**(§7.4).
- 현재 모든 operation에 고유한 `operationId`가 있지만, 이는 Atlassian 스펙 품질에 의존하는 사실이므로 canonical key는 `operationId`에 두지 않는다(§9.1).
- Phase 1 `extractor.is_openapi_candidate()`는 `openapi`가 문자열인지만 검사한다(코드로 확인, 2026-09-28). 따라서 OpenAPI 3.1은 Phase 1 sync를 통과해 캐시되며, dialect 필터는 Phase 2 gate(§10.1)가 담당한다. Phase 1 수정은 필요 없다.

### 0.3 외부 검토에서 채택한 수정사항 (1차, 계획 v1.0 → 스펙 v2.0)

| # | 변경 | 근거 |
|---|---|---|
| 1 | `validate_request` → `check_request` (structural check) | 풀 JSON Schema/OpenAPI validator를 직접 구현하면 범위가 폭발한다. 결과도 `valid` 대신 `compatible`로 표현 |
| 2 | `build_request` → `build_request_template` | site URL·Authorization을 만들지 않음을 이름에서 드러낸다 |
| 3 | Raw OpenAPI Resource 제외, operation/schema Resource는 P1 | 거대한 원본을 Agent context에 넣는 것은 intelligence layer의 목적과 반대 |
| 4 | 모든 intelligence 응답에 provenance 포함 | Agent가 `get_api_status`를 따로 부르지 않아도 stale 여부를 알아야 한다 |
| 5 | Compatibility Gate + Registry Integrity Check 후 atomic swap | valid JSON이지만 우리가 해석 못 하는 dialect가 조용히 registry를 망가뜨리는 것을 막는다 |
| 6 | Cache-first startup, lazy refresh | MCP handshake가 Atlassian 네트워크 응답에 묶이면 안 된다 |
| 7 | `refresh_api_docs`는 TTL 존중, `--force`는 CLI 전용 | Agent가 매번 강제 다운로드할 이유가 없다 |
| 8 | `operationId → [canonical_key, ...]` | 중복 operationId 가능성을 배제하지 않는다 |
| 9 | "자연어 검색" 대신 "weighted lexical search" | 기대치를 정확히 표현 |
| 10 | schema name을 search index에 포함 | 비용 거의 없음, 정확한 type 이름 검색 지원 |
| 11 | 출력 크기 제한(depth/nodes/description 길이) | Agent context 절약이 이 MCP의 핵심 품질 |

### 0.4 외부 검토에서 채택한 수정사항 (2차, 스펙 v2.0 → v2.1)

2026-09-28 v2.0 검수에서 나온 24개 지적을 전부 반영했다. 구조는 유지하고 상태 모델·영속성·계약의 엄밀성을 고쳤다.

| # | 변경 | 절 |
|---|---|---|
| 1 | "immutable"을 **logically immutable**로 정의: ingress 이후 mutate 금지, egress는 deep copy | §3, §9.5 |
| 2 | **Durable last-known-good**: gate+integrity를 통과한 raw spec을 `.atlassian-docs/intelligence/`에 영속화, 재시작 후에도 마지막 정상 registry 복구 | §11.3 |
| 3 | `current`+`provenance` 분리 상태 → **`ActiveState` 단일 immutable snapshot** 하나로 교체 | §11.1 |
| 4 | provenance는 항상 **active registry 기준**. 관찰된 캐시(`observed_cache_sha256`)와 실패한 candidate 진단을 분리 | §12 |
| 5 | `needs_refresh(source)` 명시 정의 (unavailable source 포함) | §11.4 |
| 6 | rebuild가 `current`에 없던 source를 신규 build하는 분기 명시 (부분 unavailable → runtime 복구) | §11.6 |
| 7 | backoff는 **실패 후에만**, monotonic clock, clock injectable | §11.4 |
| 8 | Manager는 완전 동기, `asyncio.to_thread`는 MCP handler 책임으로 고정 | §11.8 |
| 9 | lock busy 시 `ensure_fresh`는 현재 state 사용, `refresh_api_docs`는 `refresh_in_progress` 반환 | §11.5, §11.7 |
| 10 | stemming 제거 → **plural variant 추가**, query token dedupe, acronym/digit 경계 규칙, tokenizer fixture | §13.1 |
| 11 | schema-name index는 raw schema tree의 **모든 local `$ref`**를 bounded traversal로 수집 | §13.2 |
| 12 | `check_request` 계약 확정: `_MISSING` sentinel, root body type, coercion 허용값, bool≠int, header case-insensitive, content_type ambiguous, cookie unsupported | §16 |
| 13 | `additionalProperties: false` 위반은 **error** | §16 |
| 14 | allOf 동일 property 충돌 시 해당 property 검사 생략 + `conflicting_allof_property` | §16 |
| 15 | `SecurityAlternative`로 OpenAPI security의 OR/AND 구조 보존 | §6 |
| 16 | `build_request_template`: 잘못된 content_type은 조용히 대체하지 않고 `invalid_content_type`; `unknown_parameters` 출력 필드 명시; path substitution은 primitive만 | §15 |
| 17 | `normalization_partial` 품질 신호, `x-experimental`은 bool `True`만 인정, `x-atlassian-oauth2-scopes`는 실제 관찰된 객체 배열 형태로 파싱 | §7.5, §7.7, §12 |
| 18 | OpenAPI 3.1 지원과 Phase 1 candidate check 충돌 여부 코드로 확인 → 충돌 없음 | §0.2 |
| 19 | `get_operation` 옵션명을 동작대로 `include_full_description`, `include_response_schemas`로 변경 | §14.2 |
| 20 | MCP Resources는 **Phase 2 P0 DoD에서 제외**, P1 optional enhancement로 일관되게 표기 | §2, §18, §22 |
| 21 | AC-33 벤치마크로 강등, AC-36 fixture 고정/live는 diagnostic, AC-04 dialect 조건부, AC-34 layering test로 검증 | §23 |
| 22 | AC-02 baseline commit `ffbdd42` 명시, AC-23은 구현 노트로 강등 | §9.4, §23 |
| 23 | search provenance는 scope 안 **모든 configured source** 포함 (결과 유무 무관) | §13.4 |
| 24 | 200 KB 제한을 UTF-8 JSON byte 수로 정의 | §17.5 |

### 0.5 MCP 구현 방식 결정

**공식 `mcp` Python SDK(2.x, FastMCP)를 사용한다.** 사용자 결정(2026-09-28). SDK 의존은 `tools/atlassian_docs/mcp/` 패키지에만 존재하고, `intelligence/`와 Phase 1 core는 stdlib만 사용한다(§20).

---

## 1. 목표

> Phase 1이 유지하는 현재 공식 OpenAPI 캐시를 정규화된 logically-immutable registry로 변환하고, 고정된 소수의 MCP tool로 operation 검색·상세 조회·schema 해석·request template 생성·구조 검사를 제공한다. OpenAPI가 바뀌면 소스 코드 수정 없이 registry가 안전하게 재생성되고, 새 스펙을 이해하지 못하면 재시작 후에도 마지막 정상 상태를 계속 서비스한다.

기대 사용 흐름:

```text
사용자: "Jira issue에 파일 첨부 기능 구현해줘"
Agent:  search_operations(query="upload attachment to issue")
MCP:    jira-platform  POST /rest/api/3/issue/{issueIdOrKey}/attachments  (addAttachment)
Agent:  get_operation(key=...) → get_schema(source, "MultipartFile") → build_request_template(key=...)
Agent:  현재 공식 스펙을 근거로 구현 코드 작성
```

실제 Atlassian 서버로 요청은 보내지 않는다.

## 2. 범위

### 2.1 포함 (Phase 2 P0 — Definition of Done)

- Phase 1 sync core 재사용 (수정 없음)
- OpenAPI 3.0.x / 3.1.x normalization → domain model
- Operation Registry / Schema Registry, local `$ref` recursive resolution
- Weighted lexical operation search (source/method/tag/deprecated 필터)
- operation 상세 조회, schema 조회
- request template 생성, structural request check
- 모든 응답에 provenance (active registry 기준)
- Compatibility Gate, Registry Integrity Check, atomic `ActiveState` swap
- Durable last-known-good snapshot
- Cache-first MCP startup, TTL 기반 lazy refresh, 실패 backoff
- 7개 고정 MCP tool
- degraded / unavailable mode
- fixture 기반 오프라인 테스트, SDK in-memory MCP 통합 테스트, 수동 live smoke

### 2.2 P1 (P0 완료 후 선택적 확장, Phase 2 DoD에 포함되지 않음)

- MCP Resources: `atlassian://operation/...`, `atlassian://schema/...` template (§18)

### 2.3 제외 (Phase 3 이후)

- 실제 Jira/Confluence API 호출, site URL 생성, Authorization header 생성
- OAuth, API token, credential storage, permission, rate limit, retry, pagination 자동 수행
- 풀 JSON Schema validator 구현 (필요 시 Phase 3에서 기존 validator 의존성 도입)
- Vector DB, embedding, LLM 기반 검색, synonym dictionary
- endpoint별 MCP tool 자동 생성
- raw OpenAPI 전체 Resource
- Changelog / auth guide / ADF / pagination guide 등 OpenAPI 밖의 문서 (Phase 2.5 후보)
- MCP source code 자동 수정 — "self-updating"은 registry 재생성을 의미한다(§11)
- 백그라운드 스케줄러 / 데몬
- 외부(`http://`, `file://`) `$ref` 해석
- GitHub/Slack/Notion 등 다른 OpenAPI source

## 3. 핵심 설계 원칙

1. **OpenAPI operation은 data이고 MCP tool이 아니다.** tool 개수는 endpoint 수와 무관하게 7개로 고정한다.
2. **Registry가 유일한 중간 계층이다.** MCP는 원본 JSON을 직접 읽지 않는다.
3. **Registry는 logically immutable이다.** 생성(ingress) 이후 내부 데이터를 변경하는 코드는 존재하지 않으며, public API가 내부 dict를 반환할 때는 항상 deep copy한다(egress copy). Python 수준의 recursive freeze는 하지 않는다. 갱신은 새 `ActiveState`를 만들어 교체하는 방식만 허용한다.
4. **Gate before swap.** 새 스펙은 호환성 검사와 무결성 검사를 통과해야만 active가 되고, 통과한 스펙만 last-known-good로 영속화된다.
5. **Cache-first.** MCP 가용성과 remote freshness를 분리한다.
6. **Provenance everywhere, active 기준.** 모든 intelligence 응답은 실제로 그 응답을 만든 active registry가 어떤 source, 어떤 sha, 어떤 freshness 상태인지 말한다.
7. **Compact by default.** description 길이, schema depth, node 수, example 제거를 기본으로 하고 확장은 opt-in이다.
8. **하드코딩 금지.** API 버전, endpoint 목록, schema 이름, tool 별 endpoint 매핑을 소스 코드에 넣지 않는다.
9. **Phase 1 zero-dependency 보존.** SDK 의존은 `mcp/` 패키지 안에서만 끝난다.
10. **Phase 2 모듈은 직접 outbound HTTP를 하지 않는다.** remote refresh는 오직 `sync.sync_all()`을 통해서만 일어난다.

## 4. 아키텍처와 의존 방향

```text
                    MCP Adapter  (tools/atlassian_docs/mcp/)      ← mcp SDK 허용
                         │  await asyncio.to_thread(...)
                         ▼
               Intelligence Layer  (tools/atlassian_docs/intelligence/)  ← stdlib only, 완전 동기
       ┌───────────┬─────────┼──────────┬───────────┐
       ▼           ▼         ▼          ▼           ▼
    search     inspect    schemas   request     check
       └───────────┴─────────┼──────────┴───────────┘
                             ▼
                     RegistryManager  (ActiveState, freshness, gate, swap, last-good)
                             │
                             ▼
                  Phase 1 Sync Core  (sync.sync_all, storage.read_*)  ← 수정 없음
                     ┌───────┴───────┐
                     ▼               ▼
                 extractor        storage
```

허용되는 import:

```text
mcp.*          → intelligence.*
intelligence.* → sync, storage, extractor.is_openapi_candidate, sources.SOURCES
```

금지되는 import:

```text
sync / storage / extractor / sources → intelligence, mcp
intelligence → mcp
intelligence, mcp → urllib.request, http.client, socket   (직접 HTTP 금지)
```

이 규칙은 테스트로 고정한다(§21.4).

## 5. 디렉터리 구조

```text
tools/atlassian_docs/
├── __main__.py            (Phase 1, 변경 없음)
├── sources.py             (Phase 1, 변경 없음)
├── extractor.py           (Phase 1, 변경 없음)
├── sync.py                (Phase 1, 변경 없음)
├── storage.py             (Phase 1, 변경 없음)
│
├── intelligence/
│   ├── __init__.py        공개 API re-export
│   ├── models.py          frozen dataclass domain model
│   ├── normalizer.py      raw OpenAPI dict → SourceRegistry
│   ├── schemas.py         $ref resolver (depth/node 제한, cycle 처리)
│   ├── registry.py        SourceRegistry, Registry(합성), fingerprint
│   ├── gate.py            compatibility gate + integrity check
│   ├── lastgood.py        last-known-good snapshot 읽기/쓰기 (atomic replace)
│   ├── manager.py         RegistryManager: ActiveState, startup, ensure_fresh, refresh, swap
│   ├── provenance.py      SourceProvenance 계산
│   ├── search.py          tokenizer, index, weighted search
│   ├── inspect.py         get_operation / get_schema 출력 조립 (compact 정책)
│   ├── request_template.py
│   └── request_check.py
│
└── mcp/
    ├── __init__.py
    ├── __main__.py        python -m tools.atlassian_docs.mcp
    ├── server.py          FastMCP 인스턴스 생성, tool 등록만
    ├── tools.py           tool 핸들러 (SDK 무관 순수 함수 + 얇은 SDK 바인딩)
    └── resources.py       P1 (P0에서는 생성하지 않음)

tests/
├── (Phase 1 테스트 유지)
├── intelligence/
│   ├── test_models.py
│   ├── test_normalizer.py
│   ├── test_schemas.py
│   ├── test_registry.py
│   ├── test_gate.py
│   ├── test_lastgood.py
│   ├── test_manager.py
│   ├── test_provenance.py
│   ├── test_search.py
│   ├── test_inspect.py
│   ├── test_request_template.py
│   └── test_request_check.py
├── mcp/
│   ├── test_tools.py      SDK 없이 핸들러 로직 검증
│   └── test_server.py     SDK in-memory client 통합 (SDK 미설치 시 skip)
├── test_layering.py       import 방향 규칙 + 직접 HTTP 금지
├── fixtures/openapi/
│   ├── jira-platform-openapi.json      실제 스펙에서 축약 (10~15 ops)
│   ├── jira-software-openapi.json      실제 스펙에서 축약 (path-level params 포함)
│   ├── confluence-openapi.json         실제 스펙에서 축약 (requestBodies component 포함)
│   ├── edge-cases-openapi.json         합성 (§21.1)
│   ├── unsupported-dialect-openapi.json  openapi: "4.0.0"
│   └── make_openapi_fixtures.py        캐시에서 축약 fixture를 결정적으로 생성하는 수동 스크립트
└── live_mcp_smoke.py      수동, 네트워크 필요

requirements-mcp.txt       mcp>=2.2,<3   (MCP 계층 전용 optional dependency)

.atlassian-docs/                       (gitignore, Phase 1 소유)
└── intelligence/                      (Phase 2 소유, §11.3)
    ├── jira-platform.last-good.json
    ├── jira-software.last-good.json
    └── confluence.last-good.json
```

## 6. Domain Model (`models.py`)

모든 모델은 `@dataclass(frozen=True)`이며 컬렉션은 `tuple`을 쓴다. JSON 직렬화는 `to_dict()`로 제공한다. raw schema 조각(`schema`, `request_body.content[*].schema`, `responses[*].content[*].schema`)은 **원본 dict 그대로 보존**하며 `$ref`를 풀지 않는다. 이 dict들은 registry 내부 소유이며 §9.5의 egress copy 규칙을 따른다.

```python
@dataclass(frozen=True)
class Parameter:
    name: str
    location: str          # "path" | "query" | "header" | "cookie"
    required: bool
    description: str | None
    schema: dict | None    # raw, $ref 유지
    deprecated: bool

@dataclass(frozen=True)
class MediaType:
    content_type: str      # "application/json", "multipart/form-data", ...
    schema: dict | None    # raw, $ref 유지

@dataclass(frozen=True)
class RequestBody:
    required: bool
    description: str | None
    content: tuple[MediaType, ...]

@dataclass(frozen=True)
class Response:
    status: str            # "200", "4XX", "default"
    description: str | None
    content: tuple[MediaType, ...]

@dataclass(frozen=True)
class SecurityRequirement:      # 하나의 scheme + 그 scope
    scheme: str            # securitySchemes 키 이름 그대로
    scopes: tuple[str, ...]

@dataclass(frozen=True)
class SecurityAlternative:      # OpenAPI security 배열의 원소 하나. 내부 requirements는 AND
    requirements: tuple[SecurityRequirement, ...]

@dataclass(frozen=True)
class Operation:
    source: str
    key: str               # "{source}:{METHOD}:{path}"
    operation_id: str | None
    method: str            # 대문자
    path: str
    summary: str | None
    description: str | None
    tags: tuple[str, ...]
    parameters: tuple[Parameter, ...]     # path-level + operation-level 병합 결과
    request_body: RequestBody | None
    responses: tuple[Response, ...]
    security: tuple[SecurityAlternative, ...]   # 바깥 tuple = OR, 안쪽 = AND. OpenAPI 구조 그대로
    deprecated: bool
    experimental: bool                    # x-experimental
    oauth2_scopes: tuple[str, ...]        # x-atlassian-oauth2-scopes (없으면 빈 tuple)
```

`security: []`(인증 없음)는 빈 tuple. `security` 필드 부재는 최상위 `security`를 상속한다(§7.5).

`SourceRegistry`, `Registry`, `ActiveState`, `SourceProvenance`는 §9, §11, §12에서 정의한다.

## 7. Normalizer (`normalizer.py`)

```python
def normalize_openapi(source_name: str, spec: dict) -> SourceRegistry
```

### 7.1 처리 대상

`paths`, `components.schemas`, `components.parameters`, `components.requestBodies`, `components.responses`, `components.securitySchemes`, 최상위 `security`, `tags`, `openapi`, `info.title`.

### 7.2 Path 순회

허용 HTTP method: `get post put patch delete head options trace`. path item의 다른 키(`parameters`, `summary`, `description`, `servers`, `$ref`, `x-*`)는 operation으로 취급하지 않는다. path item 자체가 `$ref`인 경우는 `warnings`에 `path_item_ref_unsupported`로 기록하고 해당 path를 건너뛴다(관찰되지 않음).

### 7.3 Parameter 병합 규칙

1. path-level `parameters`를 먼저 수집한다. `$ref`인 항목은 `components.parameters`에서 해석한다.
2. operation-level `parameters`를 수집한다. 동일하게 `$ref` 해석.
3. `(name, location)`을 키로 하여 **operation-level이 path-level을 override**한다.
4. 결과 순서: path-level 순서 유지 → 신규 operation-level 항목을 뒤에 추가.
5. `location == "path"`인 parameter는 OpenAPI 규칙상 `required: true`로 강제한다.

### 7.4 requestBody / responses

- `requestBody`가 `$ref`이면 `components.requestBodies`에서 해석한다(Confluence에서 24개 사용).
- `responses[*]`가 `$ref`이면 `components.responses`에서 해석한다.
- 각 media type의 `schema`는 raw dict로 보존, `example`/`examples`는 **normalizer 단계에서 버린다**(Registry에 실리지 않음). schema 안의 `example` 키도 제거한다.

### 7.5 Security와 확장 필드

- operation에 `security` 키가 있으면 그것을, 없으면 최상위 `security`를 사용한다. `security: []`는 "인증 없음"으로 빈 tuple.
- 각 원소 `{"OAuth2": ["write:jira-work"], "basicAuth": []}`는 `SecurityAlternative(requirements=(SecurityRequirement("OAuth2", ...), SecurityRequirement("basicAuth", ())))`로 변환한다. 원소 순서와 내부 키 순서를 보존한다.
- `x-atlassian-oauth2-scopes`: 실제 형태는 `[{"scheme": "OAuth2", "scopes": [...], "state": "Current"|"Beta"}, ...]`(2026-09-28 관찰)이다. 각 원소의 `scopes` 문자열 배열을 등장 순서대로 합치고 중복을 제거해 `oauth2_scopes`로 보존한다. 문자열 배열이 직접 오면 그대로 보존한다. 그 외 형태는 무시하고 `warnings`에 `oauth2_scopes_shape_ignored`를 남긴다.
- `x-experimental`: **값이 bool `True`일 때만** `experimental=True`. 문자열 `"true"`, 숫자 등은 `False`로 취급하고 `warnings`에 `experimental_value_ignored`를 남긴다.
- 그 외 `x-*`는 무시한다.

### 7.6 결정성

같은 spec dict 입력에 대해 operation 순서·내용·fingerprint가 동일해야 한다. paths와 methods는 spec 내 등장 순서를 따르되, 정렬이 필요한 곳(`tags`, `schema names` 목록)은 명시적으로 정렬한다.

### 7.7 실패 정책

normalizer는 개별 operation 처리 중 예외를 만나면 그 operation을 건너뛰고 `SourceRegistry.warnings`에 `{"kind": "operation_skipped", "path":..., "method":..., "reason":...}`를 기록한다. skip이 하나라도 있으면 `SourceRegistry.normalization_partial = True`이며, 이 값은 provenance warnings로 전달된다(§12). spec 전체가 처리 불가능한 구조(`paths`가 dict가 아님 등)이면 `NormalizationError`를 발생시키며, 이는 integrity check(§10.2)에서 `normalization_failed`로 처리된다.

## 8. Schema Registry와 `$ref` 해석 (`schemas.py`)

### 8.1 Lookup

```python
registry.get_schema(source: str, name: str) -> dict | None   # raw, $ref 유지, deep copy 반환
```

### 8.2 지원 범위

지원: `#/components/schemas/{name}`, `#/components/parameters/{name}`, `#/components/requestBodies/{name}`, `#/components/responses/{name}`.
미지원: `http(s)://...`, `file://...`, `other.json#/...`, `#/paths/...`. 미지원 ref는 오류가 아니라 `{"$ref": "<원문>", "_unresolved": "external"}`로 남긴다. 존재하지 않는 local ref는 `{"$ref": "<원문>", "_unresolved": "missing"}`.

### 8.3 Recursive resolution

```python
def resolve(node: dict, source_registry, *, max_depth: int = 2, max_nodes: int = 200) -> ResolvedSchema
```

- 입력 `node`를 변경하지 않는다. 결과는 새로 만든 dict다.
- `$ref`를 만나면 대상 schema를 inline으로 치환하고 `depth += 1`.
- 현재 해석 경로(stack)에 이미 있는 ref를 다시 만나면 `{"$ref": ..., "_cycle": true}`로 멈춘다.
- `depth > max_depth`이면 `{"$ref": ..., "_truncated": "depth"}`.
- 치환한 총 node 수가 `max_nodes`를 넘으면 이후 ref는 `{"$ref": ..., "_truncated": "nodes"}`.
- `allOf`/`oneOf`/`anyOf`/`items`/`properties`/`additionalProperties`(dict인 경우)/`not` 안으로 재귀한다. 이 키워드들은 **구조를 바꾸지 않고 그대로 유지**한다(allOf를 merge하지 않는다 — merge는 `request_check.py`의 책임).
- `ResolvedSchema`는 `schema: dict`, `truncated: bool`, `unresolved: tuple[str, ...]`, `cycles: tuple[str, ...]`, `node_count: int`를 갖는다.

기본값 `max_depth=2`, 허용 최대 `8`; `max_nodes` 기본 `200`, 허용 최대 `2000`. 범위 밖 값은 `invalid_argument`.

## 9. Operation Registry (`registry.py`)

### 9.1 Canonical key와 alias

```text
key = f"{source}:{METHOD}:{path}"      예) jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments
```

- `operation_id → tuple[key, ...]` alias 맵을 유지한다. 길이가 1이 아니면 조회 API는 `ambiguous_operation_id`를 돌려주고 canonical key 사용을 요구한다.
- key는 source 안에서 유일해야 한다. 중복 발견은 integrity 실패(§10.2).

### 9.2 SourceRegistry

```python
@dataclass(frozen=True)
class SourceRegistry:
    source: str
    openapi_version: str                 # "3.0.1"
    title: str | None
    operations: tuple[Operation, ...]
    operations_by_key: Mapping[str, Operation]
    keys_by_operation_id: Mapping[str, tuple[str, ...]]
    schemas: Mapping[str, dict]          # components.schemas raw (내부 소유)
    parameters: Mapping[str, dict]
    request_bodies: Mapping[str, dict]
    responses: Mapping[str, dict]
    security_schemes: Mapping[str, dict]
    tags: tuple[str, ...]
    spec_sha256: str                     # storage.sha256_of_spec(spec) — Phase 1 metadata.sha256과 동일 정의
    warnings: tuple[dict, ...]
    normalization_partial: bool
    search_index: SearchIndex            # §13, build 시 미리 계산
```

### 9.3 Registry (합성)

```python
@dataclass(frozen=True)
class Registry:
    sources: Mapping[str, SourceRegistry]     # 로드에 성공한 source만
    fingerprint: str
    built_at: str                             # ISO UTC
```

`fingerprint = sha256("\n".join(f"{name}:{sources[name].spec_sha256 if name in sources else '-'}" for name in sorted(sources.SOURCES)))`.

조회 API: `get_operation(key)`, `find_by_operation_id(source|None, operation_id)`, `list_operations(source=None, method=None, tag=None, include_deprecated=True)`, `list_sources()`, `list_tags(source)`, `get_schema(source, name)`.

### 9.4 메모리 상주와 재사용 (구현 노트, AC 아님)

Registry는 프로세스 메모리에 상주한다. 재빌드 시 sha가 바뀌지 않은 source의 `SourceRegistry` 객체를 재사용하고 바뀐 source만 normalize하는 것을 권장한다. 이는 편의 최적화이며 정확성 조건이 아니다. 942 operations 전체 normalize + index build는 개발 환경 기준 1초 미만을 목표로 하되(벤치마크), hard AC로 두지 않는다.

### 9.5 Logical immutability 규칙

- ingress: normalize 시 spec dict에서 필요한 조각을 `copy.deepcopy`해 registry에 넣는다. 원본 spec dict는 이후 참조하지 않는다.
- 내부: registry 생성 후 내부 dict/tuple을 변경하는 코드는 존재하지 않는다.
- egress: `get_schema`, `get_operation(...).to_dict()`, `resolve()` 등 public API가 반환하는 dict는 항상 내부 객체와 별개(deep copy 또는 새로 조립)여야 한다. 테스트: 반환값을 변경한 뒤 다시 조회했을 때 원래 값이어야 한다(AC-24).

## 10. Compatibility Gate와 Integrity Check (`gate.py`)

### 10.1 Compatibility Gate (source 단위, normalize 전)

| 검사 | 통과 조건 | 실패 코드 |
|---|---|---|
| dialect | `spec["openapi"]`가 문자열이고 `3.0.` 또는 `3.1.`로 시작 | `incompatible_dialect` |
| structure | `extractor.is_openapi_candidate(spec)` 참 | `invalid_structure` |
| paths | `paths`에 허용 method를 가진 operation이 1개 이상 | `no_operations` |

`openapi: "4.x"` 같은 미래 dialect는 자동 대응 대상이 아니다 — Atlassian API 버전 변화(v3→v4)와 OpenAPI 명세 포맷 변화는 다른 문제다.

### 10.2 Integrity Check (source 단위, normalize 후)

| 검사 | 조건 | 실패 코드 |
|---|---|---|
| operations | `len(operations) > 0` | `empty_registry` |
| unique keys | key 중복 없음 | `duplicate_keys` |
| exceptions | normalize가 `NormalizationError`를 던지지 않음 | `normalization_failed` |
| schema access | `components.schemas`가 dict (없으면 빈 dict) | `invalid_components` |

### 10.3 실패 시 처리

gate 또는 integrity 실패 시 해당 source의 candidate는 폐기하고, `ActiveState`에는 이전 `SourceRegistry`(메모리 또는 last-known-good에서 로드된 것)를 유지한다. provenance는 `status="stale"`, `reason=<실패 코드>`, `candidate` 진단 필드에 실패한 캐시의 sha와 코드를 기록한다(§12). 이전 registry가 없으면 `unavailable`. **실패한 candidate는 last-known-good에 기록되지 않는다.**

### 10.4 Anomaly Warning (차단하지 않음)

이전 active `SourceRegistry` 대비 operation 수가 50% 이상 감소하면 `SourceProvenance.warnings`에 `{"kind": "operation_count_drop", "previous": N, "current": M}`을 남긴다. `normalization_partial=True`이면 `{"kind": "normalization_partial", "skipped": K}`를 남긴다. 둘 다 swap은 진행한다.

## 11. RegistryManager와 Self-Update (`manager.py`)

### 11.1 상태 모델 — `ActiveState` 단일 snapshot

```python
@dataclass(frozen=True)
class ActiveState:
    registry: Registry
    provenance: Mapping[str, SourceProvenance]     # configured source 3개 전부 (unavailable 포함)
    refresh: RefreshStatus                         # last_attempt_at, last_result, in_progress 등 외부 표시용

class RegistryManager:
    _active: ActiveState                 # 단일 attribute 대입으로만 교체
    _lock: threading.Lock                # refresh 직렬화
    _last_failed_refresh_mono: float | None   # time.monotonic() 기준, 실패 시에만 갱신
    _clock: Callable[[], float]          # 기본 time.monotonic, 테스트에서 주입
    _now: Callable[[], datetime]         # 기본 UTC now, 테스트에서 주입

    @property
    def active(self) -> ActiveState: ...
```

요청 처리 코드는 `state = manager.active`를 **정확히 한 번** 읽고 그 snapshot으로 끝까지 처리한다. registry와 provenance는 같은 snapshot에서 나오므로 항상 일관된다. 어느 시점에도 `_active`가 "registry 없음" 상태로 돌아가지 않는다.

### 11.2 Startup (cache-first)

```text
START
  ├─ 각 source에 대해:
  │     spec = storage.read_cache_spec(source)          # Phase 1 현재 캐시
  │     candidate = gate → normalize → integrity
  │     성공 → SourceRegistry 채택, last-good에 없거나 sha가 다르면 last-good 갱신
  │     실패/없음 → last-good 읽기 → gate → normalize → integrity
  │         성공 → 채택 (provenance stale, reason = 현재 캐시 실패 코드 또는 no_cache)
  │         실패/없음 → unavailable
  ├─ 채택된 source가 0개이고 현재 캐시·last-good 모두 없음 → 이 경우에만 sync.sync_all() 1회 시도 후 위 절차 재실행
  ├─ 그래도 0개 → RegistryUnavailableError (MCP 프로세스 종료, exit 2)
  └─ 1개 이상 → ActiveState 조립 → READY
```

TTL이 만료되어 있어도 startup은 네트워크에 가지 않는다(캐시·last-good이 하나라도 있는 한). freshness는 `stale/ttl_expired`로 표시되고 첫 intelligence 요청에서 갱신을 시도한다.

### 11.3 Durable last-known-good (`lastgood.py`)

Phase 1은 새 스펙을 받으면 캐시 파일을 즉시 교체하므로, gate/integrity에 실패한 새 스펙이 들어오면 이전 정상 스펙은 디스크에서 사라진다. 프로세스 재시작 시 안전망이 없어지는 것을 막기 위해 Phase 2가 별도 snapshot을 유지한다.

- 위치: `.atlassian-docs/intelligence/{source}.last-good.json` (raw spec 전체, Phase 1 캐시와 같은 직렬화 형식).
- 기록 시점: gate → normalize → integrity를 **모두 통과한 raw spec**만, 그리고 기존 last-good의 sha와 다를 때만. `storage._atomic_write_text`와 동일한 방식(tempfile + `os.replace`)으로 쓰되 Phase 1 private 함수를 import하지 않고 `lastgood.py`에 동일 로직을 둔다.
- 읽기 시점: startup과 rebuild에서 현재 캐시가 실패했을 때만.
- 실패 정책: last-good 쓰기 실패(OSError)는 swap을 막지 않는다. provenance warnings에 `last_good_write_failed`를 남긴다.
- last-good 파일도 gate/integrity를 다시 통과해야 사용된다(손상 방지).

### 11.4 `needs_refresh(source)`와 backoff

```text
needs_refresh(source) = True if any of:
    - source가 unavailable (캐시 없음)
    - source의 last_checked가 없거나 TTL(24h) 초과        # Phase 1 metadata 기준
    - source의 캐시 sha != metadata.sha256                # metadata 불일치

backoff_active = _last_failed_refresh_mono is not None
                 and clock() - _last_failed_refresh_mono < MIN_RETRY_INTERVAL (기본 900초)
```

- backoff는 **실패한 refresh 이후에만** 적용된다. 성공한 refresh는 backoff를 걸지 않는다(TTL이 다음 네트워크 접근을 막는다).
- "실패"의 정의: `sync.sync_all()`이 예외를 던졌거나, 결과 중 하나라도 `warn_fallback`/`error_unavailable`인 경우.
- 시간 측정은 `time.monotonic()` 기반이며 시스템 시계 변경에 영향받지 않는다. 외부 표시용 `last_refresh_attempt_at`(ISO UTC)은 별도로 기록한다.
- gate/integrity 실패는 backoff 대상이 아니다. 같은 캐시 sha에 대해 gate/integrity를 반복 실행하지 않도록 `_last_rejected_sha[source]`를 기억하고, sha가 같으면 재검사를 건너뛴다.

### 11.5 `ensure_fresh()` — 요청 시 lazy refresh

`search_operations`, `get_operation`, `get_schema`, `build_request_template`, `check_request` 처리 직전에 호출한다. `get_api_status`는 호출하지 않는다.

```text
ensure_fresh() -> None:
  if not any(needs_refresh(s) for s in SOURCES): return
  if backoff_active: return
  if not _lock.acquire(blocking=False): return          # 다른 refresh 진행 중 → 현재 active 사용
  try:
      _run_refresh()
  finally:
      _lock.release()
```

`ensure_fresh`는 실패해도 예외를 던지지 않는다. 결과는 provenance에 반영된다.

### 11.6 `_run_refresh()` — sync → rebuild → swap

```text
_run_refresh():
  attempt_at = now()
  try:
      results = sync.sync_all(force=False)              # Phase 1 그대로. TTL 존중.
      failed = any(r.status in ("warn_fallback", "error_unavailable") for r in results)
  except Exception as exc:
      results, failed = [], True
  if failed: _last_failed_refresh_mono = clock()

  previous = _active
  new_sources = {}
  for source in SOURCES:
      prev_sr = previous.registry.sources.get(source)   # None일 수 있음 (startup 때 unavailable이었던 source)
      spec = storage.read_cache_spec(source)
      if spec is None:
          if prev_sr is not None: new_sources[source] = prev_sr        # 이전 유지
          continue
      sha = sha256_of_spec(spec)
      if prev_sr is not None and sha == prev_sr.spec_sha256:
          new_sources[source] = prev_sr; continue                       # 변경 없음 → 재사용
      if sha == _last_rejected_sha.get(source):
          if prev_sr is not None: new_sources[source] = prev_sr
          continue                                                      # 이미 거부한 candidate
      candidate = gate → normalize → integrity
      if candidate ok:
          new_sources[source] = candidate; lastgood.write(source, spec)
      else:
          _last_rejected_sha[source] = sha
          if prev_sr is not None: new_sources[source] = prev_sr         # 이전 유지
          # prev_sr이 None이면 unavailable 유지

  registry = Registry(new_sources, fingerprint, built_at)
  provenance = compute_provenance(registry, metadata, results, rejected=...)
  _active = ActiveState(registry, provenance, refresh_status)           # 단일 대입 = atomic swap
```

`prev_sr is None`인 source가 정상 fetch되면 이 경로에서 신규 build되어 unavailable → 사용 가능으로 복구된다(AC-27).

### 11.7 `refresh()` — `refresh_api_docs` tool

```text
refresh() -> dict:
  if not _lock.acquire(blocking=False): return {"status": "refresh_in_progress"}
  try:
      before = _active.registry.fingerprint
      _run_refresh()                       # backoff 무시. Phase 1 TTL은 여전히 존중 (sync_all(force=False))
      after = _active.registry.fingerprint
      return {"status": "completed", "registry_rebuilt": before != after,
              "fingerprint_before": before, "fingerprint_after": after,
              "sources": {source: sync status ...}}
  finally: _lock.release()
```

### 11.8 동시성과 실행 모델

- `RegistryManager`와 intelligence 함수는 **완전 동기**다. Python 라이브러리로 쓸 때는 그대로 호출한다.
- MCP tool handler는 `await asyncio.to_thread(manager.ensure_fresh)` 와 `await asyncio.to_thread(manager.refresh)`로 감싼다. intelligence 함수 자체(search 등)는 CPU-bound이고 짧으므로 handler에서 직접 호출해도 되지만, 일관성을 위해 전체 tool 본문을 하나의 `to_thread`로 감싸는 것을 권장한다.
- `_active` 교체는 단일 attribute 대입이므로 reader는 lock 없이 snapshot을 읽는다.
- 여러 MCP 프로세스가 동시에 같은 `.atlassian-docs/`를 갱신하는 경우의 file locking은 Phase 1과 동일하게 범위 밖이다. Phase 1 캐시와 Phase 2 last-good 모두 atomic replace로 쓰므로 깨진 파일은 생기지 않는다.

## 12. Provenance (`provenance.py`)

```python
@dataclass(frozen=True)
class SourceProvenance:
    source: str
    status: str                      # "fresh" | "stale" | "unavailable"
    reason: str | None               # "ttl_expired" | "refresh_failed" | "metadata_mismatch" |
                                     # "incompatible_dialect" | "invalid_structure" | "no_operations" |
                                     # "empty_registry" | "duplicate_keys" | "normalization_failed" |
                                     # "invalid_components" | "no_cache" | "served_from_last_good"
    # ---- active registry 기준 (실제로 응답을 만든 스펙) ----
    active_spec_sha256: str | None
    active_openapi_version: str | None
    active_api_version: str | None   # active sha와 metadata.sha256이 같을 때만 metadata.api_version, 아니면 None
    operation_count: int
    schema_count: int
    # ---- Phase 1 metadata / 관찰된 캐시 ----
    observed_cache_sha256: str | None        # 현재 .atlassian-docs/{source}.json의 sha
    metadata_sha256: str | None
    resolved_documentation_url: str | None
    last_checked: str | None
    last_updated: str | None
    # ---- 진단 ----
    candidate: dict | None           # 거부된 candidate: {"sha256": ..., "rejected_reason": ...} 또는 None
    warnings: tuple[dict, ...]       # operation_count_drop, normalization_partial, last_good_write_failed ...
```

상태 정의:

| status | 조건 |
|---|---|
| `fresh` | active registry가 현재 캐시에서 빌드됨 **and** `active_spec_sha256 == metadata_sha256` **and** `last_checked`가 TTL 이내 **and** 최근 refresh 실패 없음 |
| `stale` | active registry가 서비스 중이지만 다음 중 하나: TTL 만료, 최근 refresh 실패, metadata 불일치, gate/integrity 실패로 이전 registry 유지, last-good에서 로드됨 |
| `unavailable` | 서비스할 registry가 없음 |

원칙: **provenance의 `active_*` 필드는 반드시 실제 응답을 생성한 registry를 설명한다.** 거부된 새 스펙의 정보는 `candidate`에만 나타난다.

모든 intelligence 응답(§14)은 `"provenance": {source: SourceProvenance.to_dict()}`와 최상위 `"registry_fingerprint"`를 포함한다. 포함 범위:

- `search_operations`: 검색 scope의 **모든 configured source** (source 필터 없음 → 3개 전부, 있음 → 그 source). 결과가 0개여도 포함한다. Agent가 "결과가 없다"와 "그 source를 검색할 수 없었다"를 구분하기 위해서다.
- `get_operation`, `get_schema`, `build_request_template`, `check_request`: 해당 operation/schema의 source.
- `get_api_status`: 3개 전부.

## 13. Weighted Lexical Search (`search.py`)

검색은 **영어 ASCII lexical search**다. tool description에 이 사실을 명시한다.

### 13.1 Tokenizer

```python
def tokenize(text: str) -> frozenset[str]
```

1. 경계 분리: 소문자→대문자 경계(`addAttachment` → `add Attachment`), 연속 대문자 뒤 소문자 경계(`JQLQuery` → `JQL Query`), 문자→숫자 경계는 분리하지 않는다(`OAuth2` → `oauth2` 하나).
2. lowercase
3. `[^a-z0-9]+`로 split (snake/kebab/path 구분자 포함, `{issueIdOrKey}` → `issue id or key`)
4. 길이 1 토큰 제거
5. 영어 기능어 stopword 제거: `a an the to of for in on at and or with by from is are be this that`
6. **plural variant 추가** (stemming 대신): 길이 > 3이고 `s`로 끝나는 토큰은 원형을 유지한 채 마지막 `s`를 뗀 형태를 **추가**한다. 단 `ss`, `us`, `is`로 끝나는 토큰은 variant를 만들지 않는다. 예: `attachments` → `{attachments, attachment}`, `issues` → `{issues, issue}`, `status` → `{status}`, `process` → `{process}`, `analysis` → `{analysis}`, `statuses` → `{statuses, statuse}` (variant가 무의미해도 원형이 남으므로 검색은 훼손되지 않는다).
7. 결과는 set (중복 제거). query와 index 모두 같은 함수를 쓴다.
8. **query에 한해** 공백으로 나뉜 각 단어의 소문자·영숫자 결합형(길이 > 3)을 토큰에 추가한다(`IssueCreateMetadata` → `issuecreatemetadata`). index의 schema name 정확형(§13.2)과 매칭되게 하기 위해서다.

tokenizer fixture 테스트에 다음을 포함한다: `issueIdOrKey`, `IssueCreateMetadata`, `OAuth2`, `JQL`, `statuses`, `status`, `process`, `create_issue`, `/rest/api/3/issue/{issueIdOrKey}/attachments`.

### 13.2 Index 필드와 가중치

| 필드 | 가중치 | 비고 |
|---|---|---|
| operation_id | 5 | |
| summary | 4 | |
| tags | 3 | |
| path | 3 | path parameter 이름 포함 |
| schema names | 2 | request/response media type raw schema tree에서 **모든 local `$ref`**의 마지막 세그먼트. `items`, `properties`, `additionalProperties`, `allOf`/`oneOf`/`anyOf`, `not`을 depth ≤ 6으로 순회. resolve하지 않음 |
| method | 1 | `post`, `get` 등 |
| description | 1 | 처음 1,000자만 index |

각 operation은 필드별 token set을 registry build 시 미리 계산한다(`SearchIndex`).

### 13.3 Scoring

```text
score(op) = Σ_{t ∈ query_tokens} Σ_{f ∈ fields} weight(f) · [t ∈ tokens(op, f)]
          + 2 · [모든 query token이 어느 필드에서든 1회 이상 매칭]
score(op) *= 0.7  if op.deprecated
```

score가 0인 operation은 결과에서 제외한다. 정렬: score 내림차순 → `deprecated=False` 우선 → source 이름 오름차순 → key 오름차순. 결정적이어야 한다(AC-10).

### 13.4 인터페이스

```python
def search_operations(state, query: str, *, source=None, method=None, tag=None,
                      include_deprecated=True, limit=10) -> dict
```

`limit` 기본 10, 최대 50(초과 시 `invalid_argument`). 결과 항목: `key, source, operation_id, method, path, summary, tags, deprecated, experimental, score`. 빈 query 또는 토큰이 전부 제거된 query는 `{"error": {"code": "empty_query", ...}}`. `source`가 configured source가 아니면 `invalid_argument`, configured지만 unavailable이면 결과 0개 + provenance `unavailable`(오류 아님). provenance 포함 범위는 §12.

### 13.5 검색 품질 고정 테스트 (fixture 기준)

- `"upload attachment to issue"` → 1위가 jira-platform `addAttachment`
- `"sprint board backlog"` → 상위 3개가 전부 jira-software
- `"create confluence page"` → 상위 1개가 confluence `POST .../pages`
- `"MultipartFile"` (정확한 schema 이름) → 해당 schema를 참조하는 `addAttachment`가 1위
- `"IssueCreateMetadata"` → `GET .../issue/createmeta`가 상위 2개 안 (실제 스펙에서 deprecated라 ×0.7 페널티를 받으므로 1위를 고정하지 않는다)
- `source="confluence"` 필터 시 jira 결과 0개
- `"issue attachments"`와 `"issue attachment"`가 같은 1위를 반환 (plural variant)

## 14. Intelligence API (`inspect.py`) — 출력 정책

### 14.1 공통

모든 함수는 `state: ActiveState`를 첫 인자로 받고 JSON 직렬화 가능한 dict를 반환하며 `provenance`, `registry_fingerprint`를 포함한다. 조회 실패는 예외가 아니라 `{"error": {"code": ..., "message": ...}}`로 반환한다. 코드: `operation_not_found`, `ambiguous_operation_id`(후보 key 목록 포함), `schema_not_found`, `source_unavailable`, `empty_query`, `invalid_argument`. 반환 dict는 registry 내부 객체를 공유하지 않는다(§9.5).

### 14.2 `get_operation(state, key=None, source=None, operation_id=None, *, include_full_description=False, include_response_schemas=False, resolve_schema_depth=0)`

`key`가 주어지면 그것을 쓰고, 아니면 `(source, operation_id)`로 alias 조회한다(`source=None`이면 모든 source에서 찾되 후보가 2개 이상이면 `ambiguous_operation_id`).

기본(compact) 출력:

```json
{
  "key": "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments",
  "source": "jira-platform", "operation_id": "addAttachment",
  "method": "POST", "path": "/rest/api/3/issue/{issueIdOrKey}/attachments",
  "summary": "Add attachment",
  "description": "Adds one or more attachments to an issue. ...",
  "description_truncated": true,
  "tags": ["Issue attachments"], "deprecated": false, "experimental": false,
  "oauth2_scopes": ["write:jira-work"],
  "parameters": [{"name": "issueIdOrKey", "in": "path", "required": true, "schema": {"type": "string"}}],
  "request_body": {"required": true, "content": [{"content_type": "multipart/form-data", "schema": {"type": "array", "items": {"$ref": "#/components/schemas/MultipartFile"}}}]},
  "responses": [{"status": "200", "content_types": ["application/json"]}, {"status": "403", "content_types": []}, {"status": "404", "content_types": []}, {"status": "413", "content_types": []}],
  "security": [[{"scheme": "OAuth2", "scopes": ["write:jira-work"]}], [{"scheme": "basicAuth", "scopes": []}]],
  "provenance": {...}, "registry_fingerprint": "..."
}
```

- 기본: description은 처음 500자, 잘리면 `description_truncated: true`. responses는 status와 content type 목록만.
- `include_full_description=True`: description 전체, `description_truncated: false`.
- `include_response_schemas=True`: 각 response에 `description`과 `content: [{content_type, schema}]`(`$ref` 유지) 추가.
- `resolve_schema_depth > 0` (최대 8): parameter/request/response schema를 §8 규칙으로 inline 해석.
- example은 normalizer 단계에서 버려지므로(§7.4) 어떤 옵션으로도 반환되지 않는다.
- `security`는 OR 배열의 AND 배열로 그대로 직렬화한다.

### 14.3 `get_schema(state, source, name, *, max_depth=2, max_nodes=200)`

`{"source", "name", "schema": <resolved>, "truncated", "unresolved", "cycles", "node_count", "provenance", "registry_fingerprint"}`.

## 15. Request Template Builder (`request_template.py`)

```python
def build_request_template(state, key: str, values: dict | None = None) -> dict
```

`values = {"path_params": {...}, "query": {...}, "headers": {...}, "body": <any>, "content_type": "..."}` (전부 선택).

출력:

```json
{
  "key": "...", "method": "POST",
  "path_template": "/rest/api/3/issue/{issueIdOrKey}/attachments",
  "path": "/rest/api/3/issue/ABC-123/attachments",
  "path_params": {"issueIdOrKey": {"required": true, "schema": {"type": "string"}, "value": "ABC-123"}},
  "query": {},
  "headers": {},
  "unknown_parameters": {"query": [], "headers": [], "path_params": []},
  "content_types": ["multipart/form-data"],
  "selected_content_type": "multipart/form-data",
  "body_schema": {"type": "array", "items": {"$ref": "#/components/schemas/MultipartFile"}},
  "body": null,
  "body_required": true,
  "security": [[...]], "oauth2_scopes": [...],
  "server": null,
  "missing_required": ["body"],
  "notes": ["server URL and Authorization are out of scope for Phase 2"],
  "provenance": {...}, "registry_fingerprint": "..."
}
```

규칙:

- `path`는 모든 path parameter 값이 주어졌을 때만 채우고, 아니면 `null`. 값은 primitive(str/int/float/bool)만 허용하고 `urllib.parse.quote(str(v), safe="")`로 인코딩한다. dict/list 값은 `invalid_argument`.
- `query`/`headers`는 spec에 선언된 parameter를 이름별로 나열하고 `values`에서 온 값을 `value`에 채운다. header 이름 매칭은 case-insensitive. spec에 없는 값은 `unknown_parameters`에 나열한다(버리지 않음).
- `selected_content_type`:
  - `values.content_type`이 주어졌고 선언된 것 중 하나 → 그것.
  - 주어졌지만 선언되지 않음 → `selected_content_type: null`, `body_schema: null`, `errors: [{"rule": "invalid_content_type", ...}]`. **조용히 다른 값으로 바꾸지 않는다.**
  - 생략됨 → 선언된 content type이 1개면 그것, 2개 이상이면 첫 번째를 선택하고 `notes`에 `content_type_defaulted`를 남긴다.
- `server`는 항상 `null`. `Authorization`, `Cookie` header 값은 절대 생성하지 않는다. `values.headers`에 `authorization`/`cookie`(case-insensitive)가 오면 값을 출력에 넣지 않고 `notes`에 `credential_header_dropped`를 남긴다.
- `missing_required`: 값이 없는 required path/query/header parameter 이름과, `body_required`인데 body가 없으면 `"body"`.
- cookie parameter는 template에 `cookies: {...}` 항목으로 나열만 하고 값은 채우지 않는다.

## 16. Structural Request Check (`request_check.py`)

```python
_MISSING = object()
def check_request(state, key: str, *, path_params=None, query=None, headers=None,
                  body=_MISSING, content_type=None) -> dict
```

`body=_MISSING`은 "body 미제공", `body=None`은 "명시적 JSON null"이다. MCP 바인딩에서는 tool 입력에 `body` 키가 없으면 `_MISSING`, `"body": null`이면 `None`으로 매핑한다.

출력:

```json
{
  "compatible": false,
  "errors":   [{"location": "path.issueIdOrKey", "rule": "required", "message": "required path parameter is missing"}],
  "warnings": [{"location": "query.foo", "rule": "unknown_parameter", "message": "not declared in the specification"}],
  "checked":     ["required", "type", "enum", "body_required", "content_type", "body_root_type", "body_required_properties", "body_property_type", "body_property_enum", "body_unknown_property"],
  "not_checked": ["oneOf/anyOf", "pattern", "format", "minimum/maximum", "minLength/maxLength", "nested objects beyond depth 2", "cookie parameters", "conflicting allOf properties"],
  "provenance": {...}, "registry_fingerprint": "..."
}
```

### 16.1 값 해석 규칙 (고정)

| 선언 type | 허용 값 (body / path) | 허용 값 (query / header 문자열 coercion) |
|---|---|---|
| `string` | `str` | 모든 문자열 |
| `integer` | `int` **and not** `bool` | `^-?\d+$` |
| `number` | `int` 또는 `float`, **not** `bool` | `float()` 파싱 가능 |
| `boolean` | `bool` | 정확히 `"true"` 또는 `"false"` (소문자) |
| `array` | `list` | 문자열에서 자동 split하지 않음. `list`만 허용 |
| `object` | `dict` | 검사하지 않음 (`not_checked`) |
| type 없음 | 검사하지 않음 | 검사하지 않음 |

- `nullable: true`(3.0) 또는 `type`에 `"null"` 포함(3.1)이면 `None` 허용.
- header 이름 비교는 case-insensitive.
- query/header 값이 문자열이 아니면(예: int) body 규칙으로 검사한다.

### 16.2 규칙 목록 (이것이 전부다 — 여기 없는 것은 검사하지 않으며 `not_checked`에 명시한다)

| rule | 대상 | 결과 |
|---|---|---|
| `required` | required path/query/header parameter 누락 | error |
| `type` | parameter 값 type 불일치 (§16.1) | error |
| `enum` | parameter 값이 enum 밖 | error |
| `unknown_parameter` | spec에 없는 query/header | warning |
| `body_required` | `request_body.required`인데 body가 `_MISSING` | error |
| `content_type` | 주어진 content_type이 선언되지 않음 | error (body schema 검사 생략) |
| `content_type_ambiguous` | content_type 미지정이고 선언된 것이 2개 이상 | warning (body schema 검사 생략, `structure_not_checked`) |
| `body_root_type` | body가 있고 schema에 root `type`이 있을 때 root 값 type 불일치 (§16.1) | error |
| `body_required_properties` | root가 object일 때 top-level `required` 누락 | error |
| `body_property_type` | top-level property type 불일치 | error |
| `body_property_enum` | top-level property enum 위반 | error |
| `body_unknown_property` | `additionalProperties: false`가 명시된 object에 미선언 property | **error** |
| `structure_not_checked` | body schema가 `oneOf`/`anyOf`이거나, depth 2 안에서 `$ref` 해석 불가(`_unresolved`/`_truncated`), 또는 content type ambiguous | warning |
| `conflicting_allof_property` | allOf 병합 시 같은 property에 서로 다른 schema | warning (그 property의 type/enum 검사 생략) |
| `cookie_not_checked` | operation에 cookie parameter가 있음 | warning (Phase 2는 cookie를 검사하지 않음) |

- body schema 준비: §8 `resolve(max_depth=2, max_nodes=200)` → `allOf`가 있으면 `required`는 합집합, `properties`는 이름별로 모으되 동일 이름에 non-identical schema가 2개 이상이면 그 property를 `conflicting_allof_property`로 표시.
- `compatible = len(errors) == 0`. 이 값은 "우리가 검사한 규칙에서 오류가 없음"을 뜻하며 OpenAPI 전체 규칙 만족을 뜻하지 않는다 — tool description에 이 문장을 그대로 넣는다. 출력에 `valid` 키는 존재하지 않는다.

## 17. MCP Server (`mcp/`)

### 17.1 실행

```bash
pip install -r requirements-mcp.txt          # mcp>=2.2,<3 — MCP 계층에만 필요
python -m tools.atlassian_docs.mcp           # stdio transport, 저장소 루트에서 실행
```

Phase 1과 같이 캐시 경로는 현재 작업 디렉터리 기준이다. `tools.atlassian_docs.mcp`를 SDK 없이 import하면 `ImportError`를 잡아 "pip install -r requirements-mcp.txt" 안내와 함께 exit 3으로 종료한다. Phase 1 CLI와 `intelligence/`는 SDK 없이 그대로 동작한다.

Claude Code 설정 예:

```json
{ "mcpServers": { "atlassian-openapi": { "command": "python", "args": ["-m", "tools.atlassian_docs.mcp"], "cwd": "<repo root>" } } }
```

### 17.2 Tools (7개, 고정)

| tool | 입력 | 동작 | ensure_fresh |
|---|---|---|---|
| `search_operations` | `query`(필수), `source?`, `method?`, `tag?`, `include_deprecated?=true`, `limit?=10` | §13 | 예 |
| `get_operation` | `key?` 또는 (`source?`, `operation_id?`), `include_full_description?=false`, `include_response_schemas?=false`, `resolve_schema_depth?=0` | §14.2 | 예 |
| `get_schema` | `source`, `name`, `max_depth?=2`, `max_nodes?=200` | §14.3 | 예 |
| `build_request_template` | `key`, `values?` | §15 | 예 |
| `check_request` | `key`, `path_params?`, `query?`, `headers?`, `body?`, `content_type?` | §16 | 예 |
| `get_api_status` | 없음 | §17.3 | 아니오 |
| `refresh_api_docs` | 없음 | §11.7 | (자체 refresh) |

각 handler는 `await asyncio.to_thread(tools.<name>, manager, **args)` 형태로 동기 함수를 호출한다. `tools.<name>`은 `manager.ensure_fresh()` → `state = manager.active` → intelligence 함수 순으로 실행하는 SDK 무관 순수 함수다.

tool description은 provenance 해석법("status가 stale이면 결과는 마지막 정상 스펙 기준, `active_*` 필드가 실제 사용된 스펙"), `compatible`의 의미, 검색이 영어 ASCII lexical이라는 점, 실제 호출을 하지 않는다는 사실을 포함한다. 입력 스키마는 SDK가 type hint에서 생성한다.

### 17.3 `get_api_status` 출력

```json
{
  "registry_fingerprint": "...", "built_at": "...",
  "sources": { "jira-platform": {<SourceProvenance>}, "jira-software": {...}, "confluence": {...} },
  "refresh": { "ttl_seconds": 86400, "min_retry_interval_seconds": 900,
               "backoff_active": false,
               "last_refresh_attempt_at": "...", "last_refresh_result": {...}, "in_progress": false },
  "execution": "disabled"
}
```

### 17.4 오류 계약

intelligence 함수가 돌려준 `{"error": ...}`는 tool 결과로 그대로 전달하고 MCP `isError=true`로 표시한다. 예상치 못한 예외는 `{"error": {"code": "internal_error", "message": str(exc)}}`로 변환하며 서버 프로세스는 죽지 않는다.

### 17.5 크기 제한

SDK 바인딩 직전 intelligence payload를 `json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")`로 직렬화한 **byte 수가 200 × 1024를 넘으면** 결과 대신 `{"error": {"code": "result_too_large", "message": "...reduce limit / max_depth / max_nodes / resolve_schema_depth"}}`를 반환한다.

## 18. MCP Resources (P1 — Phase 2 DoD 아님)

P0 완료 후 선택적으로 추가한다. raw OpenAPI 전체 resource는 만들지 않는다. Acceptance Criteria에 포함되지 않으며, 추가 시 별도 AC를 작성한다.

```text
atlassian://operation/{source}/{operation_id}     → get_operation compact 출력 (ambiguous면 후보 목록)
atlassian://schema/{source}/{name}                → get_schema(max_depth=2)
```

`resources/list`는 template 두 개만 노출하고 개별 operation을 열거하지 않는다.

## 19. Degraded / Unavailable

| 상황 | MCP 동작 |
|---|---|
| 일부 source stale | 정상 서비스, 해당 source provenance `stale` + reason |
| 일부 source unavailable | 나머지 source로 정상 서비스. 해당 source 지정 요청은 `source_unavailable` 오류. 검색 결과에서 제외되지만 provenance에는 `unavailable`로 포함 |
| 모든 source unavailable (startup) | §11.2에 따라 1회 sync 시도 후에도 없으면 프로세스 종료 exit 2 |
| refresh 실패 (runtime) | 이전 ActiveState의 source registry 유지, provenance `stale/refresh_failed`, 15분 backoff |
| gate/integrity 실패 (runtime) | 이전 registry 유지, provenance `stale/<code>`, `candidate` 진단, 같은 sha는 재검사 안 함 |
| gate/integrity 실패 후 프로세스 재시작 | 현재 캐시 실패 → last-good에서 로드, provenance `stale/served_from_last_good` |
| metadata.json 손상 | provenance의 metadata 필드 `null`, status `stale/metadata_mismatch`, 캐시 파일이 유효하면 registry는 로드(Phase 1 self-heal이 다음 sync에서 복구) |
| unavailable source가 runtime refresh로 복구 | §11.6 경로로 신규 build되어 사용 가능 |

## 20. Dependencies와 패키징

- Phase 1 core, `intelligence/`, 모든 `tests/intelligence/*`: **stdlib only** (Python ≥ 3.10; 개발 환경 3.11).
- `mcp/`, `tests/mcp/test_server.py`: `mcp>=2.2,<3` (`requirements-mcp.txt`).
- `pyproject.toml`/`pip install -e .`는 도입하지 않는다 — 최상위 패키지 이름이 `tools`라 site-packages에 설치하는 것이 부적절하고, Phase 1이 이미 "저장소 루트에서 `python -m`" 규약을 쓰고 있다.
- `tests/mcp/test_server.py`는 `unittest.skipUnless(importlib.util.find_spec("mcp"))`로 SDK 미설치 환경에서 skip한다. 기본 `python -m unittest discover -s tests -t .`는 SDK 없이도 실패 없이 끝나야 한다.

## 21. 테스트 전략

### 21.1 Fixture

`tests/fixtures/openapi/make_openapi_fixtures.py`가 `.atlassian-docs/*.json`에서 지정된 path 목록만 추출하고, 참조되는 components를 transitive closure로 포함해 결정적으로(`sort_keys=True`) 저장한다. 생성물은 커밋한다. 포함 조건:

- jira-platform: `POST /rest/api/3/issue`, `POST .../issue/{issueIdOrKey}/attachments`, `GET .../issue/{issueIdOrKey}`, `GET .../issue/createmeta` 계열(`IssueCreateMetadata` 참조), `GET /rest/api/3/search/jql`, deprecated operation 1개 이상, `allOf` 사용 schema 1개 이상, `additionalProperties: false` schema 1개 이상(없으면 edge-cases에 합성)
- jira-software: path-level `parameters`가 있는 `/rest/builds/0.1/bulk` 등, sprint/board/backlog operation 3개 이상, `/rest/agile/1.0/`과 `/rest/*/0.1/` 네임스페이스 혼재 (Phase 1의 알려진 후속 과제였던 jira-software fixture 부재를 여기서 해소)
- confluence: `POST /pages`, `GET /pages/{id}`, cursor pagination parameter가 있는 list operation, `$ref` requestBody 사용 operation
- edge-cases(합성): 순환 `$ref`, missing ref, external ref, `oneOf`/`anyOf`, operationId 없는 operation, 중복 operationId 2개, operation-level이 path-level을 override하는 parameter, cookie parameter, 두 개의 request content type, allOf 충돌 property, `x-experimental: "true"`(문자열), security OR/AND 혼합, `openapi: "3.1.0"`
- `unsupported-dialect-openapi.json`: `openapi: "4.0.0"`

### 21.2 Unit

normalizer, schemas, registry(egress copy 포함), gate, lastgood, manager(storage/sync를 fake로 주입, clock 주입), provenance 상태 전이, search 순위·tokenizer, inspect compact 정책, request_template, request_check 규칙별.

### 21.3 Integration

- fixture 캐시 디렉터리를 `tempfile`에 만들고 `storage.CACHE_DIR`를 patch → `RegistryManager` startup → intelligence 함수 → 기대 출력.
- self-update: 캐시 파일과 metadata sha를 바꾼 뒤 `refresh()` → fingerprint 변경, 새 operation 검색 가능, last-good 갱신.
- gate 실패: 캐시를 `unsupported-dialect`로 교체 → `refresh()` → 이전 registry 유지 + `stale/incompatible_dialect` + `candidate` 진단 → **새 Manager 인스턴스로 startup** → last-good에서 로드, `stale/served_from_last_good`.
- 부분 unavailable → runtime 복구: 한 source 캐시 없이 startup → 캐시 추가 → `refresh()` → 해당 source 사용 가능.
- backoff: sync를 실패하도록 주입 → `ensure_fresh()` 두 번째 호출이 sync를 부르지 않음 → clock을 900초 진행 → 다시 부름. 성공 후에는 backoff 없음.
- provenance/registry 일관성: refresh 도중 캡처한 `state`의 registry fingerprint와 provenance가 서로 일치.
- `tests/mcp/test_server.py`: SDK in-memory client로 7개 tool `tools/list`와 각 1회 호출, `body` 생략 vs `null` 매핑 확인.

### 21.4 Layering test

`tests/test_layering.py`: `ast`로 각 모듈의 import를 읽어 §4 금지 방향을 검사한다. `tools/atlassian_docs/intelligence/**`와 `mcp/**`는 `urllib.request`, `http.client`, `socket`을 import하지 않는다(직접 HTTP 금지). Phase 1 모듈과 `intelligence/`는 `mcp` 패키지를 import하지 않는다.

### 21.5 Live smoke (수동, diagnostic)

`python tests/live_mcp_smoke.py`: 실제 sync → RegistryManager → 3개 source normalize 성공 여부와 소요 시간 출력 → `search_operations("upload attachment to issue")` 상위 5개 출력 → 1위 `get_operation` → `build_request_template`. 네트워크 필요, 기본 suite에 포함하지 않음, Atlassian API 호출 없음. 순위와 시간은 진단 출력이며 pass/fail 조건이 아니다(단, normalize 자체가 지원 dialect에서 실패하면 fail).

## 22. Milestones

| Milestone | 포함 | 완료 조건 |
|---|---|---|
| **2A Intelligence Core** | models, normalizer, schemas, registry(egress copy), gate, fixtures, layering test | fixture 3종 + edge-cases normalize, `$ref` 해석, gate 동작. Python 라이브러리로 단독 사용 가능 |
| **2B Request Intelligence** | search, provenance, inspect, request_template, request_check | §13.5 순위 테스트 통과, §15/§16 규칙 테스트 통과 |
| **2C Self-Update** | lastgood, manager (ActiveState, startup, needs_refresh, backoff, ensure_fresh, refresh, swap) | §21.3 통합 테스트 전부 통과 |
| **2D MCP Exposure** | mcp/server, tools, requirements-mcp.txt, AGENTS.md/README 갱신, live_mcp_smoke | 7 tool in-memory 통합 테스트 통과, Claude Code에서 실제 사용 확인 |
| (P1) Resources | mcp/resources | Phase 2 DoD 아님 |

순서를 바꾸지 않는다. 특히 MCP를 먼저 만들면 이후 로직 테스트가 프로토콜에 얽힌다. 2C를 2D 앞에 둔 이유는 manager가 SDK 없이 테스트 가능해야 하기 때문이다.

## 23. Acceptance Criteria

| # | 조건 | 검증 방법 |
|---|---|---|
| AC-01 | Phase 1 테스트 67개가 그대로 통과한다 | unittest |
| AC-02 | `git diff ffbdd42 -- tools/atlassian_docs/{__main__,sources,extractor,sync,storage}.py`가 비어 있다 | git |
| AC-03 | Phase 1 core와 `intelligence/`는 stdlib 외 import가 없고, `intelligence/`·`mcp/`는 직접 HTTP 모듈을 import하지 않는다 | layering test |
| AC-04 | 지원 dialect(3.0.x/3.1.x) fixture는 normalize에 성공하고, 미지원 dialect는 gate에서 graceful하게 거부된다 | unit |
| AC-05 | 모든 operation에 `{source}:{METHOD}:{path}` key가 생성되고 source 안에서 유일하다 | unit |
| AC-06 | operationId 없는 operation도 registry에 포함된다 | unit (edge-cases) |
| AC-07 | 중복 operationId는 `ambiguous_operation_id`로 응답한다 | unit (edge-cases) |
| AC-08 | path-level parameter가 operation-level에 의해 `(name, in)` 기준 override된다 | unit |
| AC-09 | local `$ref` 4종을 해석하고, 순환·missing·external ref가 예외 없이 marker로 표시된다 | unit |
| AC-10 | 동일 query·state에 대해 검색 결과 순서가 결정적이다 | unit (반복 실행) |
| AC-11 | §13.5의 순위 테스트 6개가 통과한다 | unit (fixture) |
| AC-12 | source/method/tag/include_deprecated 필터가 동작한다 | unit |
| AC-13 | `get_operation` 기본 출력에 example이 없고 description이 500자로 잘리며 `description_truncated`가 표시된다 | unit |
| AC-14 | `get_schema`가 `max_depth`/`max_nodes`를 지키고 `truncated`를 보고한다 | unit |
| AC-15 | `build_request_template`가 `server: null`을 반환하고 Authorization/Cookie 값을 생성하지 않으며, 입력에 온 credential header 값을 출력에 넣지 않는다 | unit |
| AC-16 | `build_request_template`가 required 누락을 `missing_required`로, 미선언 값을 `unknown_parameters`로, 잘못된 content_type을 `invalid_content_type`으로 보고한다 | unit |
| AC-17 | `check_request`가 §16.2의 규칙 전부를 검출하고 `checked`/`not_checked`를 명시한다 | unit (규칙별) |
| AC-18 | `check_request` 출력에 `valid` 키가 없고, `additionalProperties: false` 위반은 error다 | unit |
| AC-19 | 모든 intelligence 응답에 `provenance`와 `registry_fingerprint`가 있으며, search provenance는 scope 안 모든 configured source를 포함한다 | unit |
| AC-20 | `openapi: "4.0.0"` 스펙은 gate에서 거부되고 이전 registry가 유지되며 `candidate` 진단이 기록된다 | integration |
| AC-21 | integrity 실패 시 이전 registry가 유지되고 provenance가 `stale`이며 `active_spec_sha256`은 이전 스펙을 가리킨다 | integration |
| AC-22 | spec sha 변경 후 `refresh()`에서 registry가 재빌드되고 fingerprint가 바뀌며 last-good이 갱신된다 | integration |
| AC-23 | gate 실패 후 새 Manager로 startup하면 last-good에서 이전 registry가 복구되고 `served_from_last_good`이 표시된다 | integration |
| AC-24 | public API 반환값을 변경해도 registry 내부 상태가 바뀌지 않는다 (egress copy) | unit |
| AC-25 | 실패한 refresh 이후 900초 안의 `ensure_fresh()`는 sync를 호출하지 않고, 성공한 refresh 이후에는 backoff가 없다 | unit (clock 주입) |
| AC-26 | startup은 캐시나 last-good이 하나라도 있으면 sync를 호출하지 않는다 | unit (sync fake) |
| AC-27 | 캐시·last-good이 전혀 없을 때만 startup에서 sync를 1회 시도하고, 실패 시 `RegistryUnavailableError` | unit |
| AC-28 | 한 source unavailable 상태에서 나머지 source가 정상 서비스되고, 그 source가 이후 refresh로 복구된다 | integration |
| AC-29 | refresh 도중 캡처한 `ActiveState`의 registry와 provenance가 서로 일치한다 | integration |
| AC-30 | MCP `tools/list`가 정확히 7개를 반환한다 | mcp integration |
| AC-31 | 7개 tool 각각이 in-memory client 통합 테스트에서 성공 응답을 반환한다 | mcp integration |
| AC-32 | tool 결과 UTF-8 JSON byte가 200 KiB 초과 시 `result_too_large`를 반환한다 | unit |
| AC-33 | SDK 미설치 환경에서 기본 테스트 suite가 skip만 있고 실패 없이 끝난다 | CI |
| AC-34 | 오프라인에서 전체 suite가 통과한다 (네트워크 호출 자체가 없음: sync는 fake 주입) | CI |
| AC-35 | Phase 2 모듈은 직접 outbound HTTP를 하지 않고, remote refresh는 오직 `sync.sync_all` 호출을 통해서만 일어난다 | layering test |
| AC-36 | API 버전·endpoint·schema 이름이 소스 코드에 하드코딩되지 않는다 (fixture와 테스트 기대값 제외) | 리뷰 |
| AC-37 | `refresh_api_docs`가 다른 refresh와 겹치면 `refresh_in_progress`를 반환한다 | unit |
| AC-38 | `x-experimental`은 bool `True`만 인정하고 문자열 `"true"`는 무시된다 | unit (edge-cases) |
| AC-39 | live smoke에서 3개 실제 source가 모두 normalize된다 (검색 순위·시간은 진단 출력) | 수동 |

벤치마크 목표(AC 아님): 실제 3개 캐시 전체 normalize + index build 1초 미만(개발 환경).

## 24. Phase 2에서 하지 않는 것 (재확인)

개발 중 다음 요구가 나오더라도 이번 Phase에 넣지 않는다: 실제 실행(`execute_*`), OAuth/토큰, site URL 입력, endpoint별 tool, embedding, synonym dictionary, changelog 분석, OpenAPI→Markdown 전체 변환, 다른 벤더 OpenAPI, 풀 JSON Schema validator. Phase 3 진입 조건은 registry self-update 안정성, request template의 실제 API 형태 일치, MCP interface 고정이다.

## 25. 한 줄 정의

> Phase 2는 Atlassian 공식 OpenAPI surface를 자동 추종하고, 이해하지 못하는 변경 앞에서는 마지막 정상 상태를 끝까지 지키는 API Intelligence MCP다 — Atlassian 공식 문서 전체를 이해하는 시스템도, Jira/Confluence를 실행하는 시스템도 아니다.
