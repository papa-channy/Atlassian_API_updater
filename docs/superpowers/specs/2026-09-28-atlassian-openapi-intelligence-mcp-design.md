# Atlassian OpenAPI Intelligence MCP — Phase 2 Technical Specification

**문서 버전:** v2.0
**기준일:** 2026-09-28
**선행 구현:** Atlassian API Docs Lightweight Sync v1.2 (`tools/atlassian_docs/`, `main` 머지 완료, 오프라인 테스트 67개 통과)
**목적:** Phase 1이 캐싱한 공식 Jira/Confluence OpenAPI를 정규화된 지식 계층으로 바꾸고, AI 코딩 에이전트가 MCP를 통해 검색·해석·요청 구조 생성·구조 검사를 할 수 있게 한다.
**설계 원칙:** Registry-first / Fixed small tool surface / Cache-first startup / Provenance everywhere / Gate before swap / Fail-safe / No execution

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
- `securitySchemes`는 `OAuth2`/`basicAuth`(Jira), `basicAuth`/`oAuthDefinitions`(Confluence)로 이름이 제품마다 다르다. security 정보는 정규화하되 해석은 하지 않는다.
- Atlassian 확장 필드 `x-atlassian-oauth2-scopes`, `x-experimental`, `x-changes`, `x-atlassian-connect-scope`, `x-atlassian-data-security-policy`, `x-atlassian-narrative`, `x-showInExample`가 존재한다. **`x-atlassian-oauth2-scopes`와 `x-experimental` 두 개만 보존**하고 나머지는 무시한다(§7.5).
- 응답의 `example` 문자열이 수 KB에 이른다. **기본 출력에서 example은 제거**한다(§14.2).
- 현재 모든 operation에 고유한 `operationId`가 있지만, 이는 Atlassian 스펙 품질에 의존하는 사실이므로 canonical key는 `operationId`에 두지 않는다(§9.1).

### 0.3 외부 검토에서 채택한 수정사항

Phase 2 초안(v1.0 계획)에 대한 검토 의견 중 다음을 전부 채택했다.

| # | 변경 | 근거 |
|---|---|---|
| 1 | `validate_request` → `check_request` (structural check) | 풀 JSON Schema/OpenAPI validator를 직접 구현하면 범위가 폭발한다. 결과도 `valid` 대신 `compatible`로 표현 |
| 2 | `build_request` → `build_request_template` | site URL·Authorization을 만들지 않음을 이름에서 드러낸다 |
| 3 | Raw OpenAPI Resource P0 제외 | 거대한 원본을 Agent context에 넣는 것은 intelligence layer의 목적과 반대 |
| 4 | 모든 intelligence 응답에 provenance 포함 | Agent가 `get_api_status`를 따로 부르지 않아도 stale 여부를 알아야 한다 |
| 5 | Compatibility Gate + Registry Integrity Check 후 atomic swap | valid JSON이지만 우리가 해석 못 하는 dialect가 조용히 registry를 망가뜨리는 것을 막는다 |
| 6 | Cache-first startup, lazy refresh | MCP handshake가 Atlassian 네트워크 응답에 묶이면 안 된다 |
| 7 | `refresh_api_docs`는 TTL 존중, `--force`는 CLI 전용 | Agent가 매번 강제 다운로드할 이유가 없다 |
| 8 | `operationId → [canonical_key, ...]` | 중복 operationId 가능성을 배제하지 않는다 |
| 9 | "자연어 검색" 대신 "weighted lexical search" | 기대치를 정확히 표현 |
| 10 | schema name을 search index에 포함 | 비용 거의 없음, 정확한 type 이름 검색 지원 |
| 11 | 출력 크기 제한(depth/nodes/description 길이) | Agent context 절약이 이 MCP의 핵심 품질 |

### 0.4 MCP 구현 방식 결정

**공식 `mcp` Python SDK(2.x, FastMCP)를 사용한다.** 사용자 결정(2026-09-28). SDK 의존은 `tools/atlassian_docs/mcp/` 패키지에만 존재하고, `intelligence/`와 Phase 1 core는 stdlib만 사용한다(§20).

---

## 1. 목표

> Phase 1이 유지하는 현재 공식 OpenAPI 캐시를 정규화된 immutable registry로 변환하고, 고정된 소수의 MCP tool로 operation 검색·상세 조회·schema 해석·request template 생성·구조 검사를 제공한다. OpenAPI가 바뀌면 소스 코드 수정 없이 registry가 안전하게 재생성된다.

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

### 2.1 포함

- Phase 1 sync core 재사용 (수정 없음)
- OpenAPI 3.0.x / 3.1.x normalization → domain model
- Operation Registry / Schema Registry, local `$ref` recursive resolution
- Weighted lexical operation search (source/method/tag/deprecated 필터)
- operation 상세 조회, schema 조회
- request template 생성, structural request check
- 모든 응답에 provenance
- Compatibility Gate, Registry Integrity Check, atomic swap
- Cache-first MCP startup, TTL 기반 lazy refresh, 재시도 backoff
- 7개 고정 MCP tool
- MCP Resources (operation/schema template, **P1**)
- degraded / unavailable mode
- fixture 기반 오프라인 테스트, SDK in-memory MCP 통합 테스트, 수동 live smoke

### 2.2 제외 (Phase 3 이후)

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
3. **Registry는 immutable이다.** 갱신은 새 registry를 만들어 교체하는 방식만 허용한다.
4. **Gate before swap.** 새 스펙은 호환성 검사와 무결성 검사를 통과해야만 active가 된다.
5. **Cache-first.** MCP 가용성과 remote freshness를 분리한다.
6. **Provenance everywhere.** 모든 intelligence 응답은 어떤 source, 어떤 sha, 어떤 freshness 상태에서 나왔는지 말한다.
7. **Compact by default.** description 길이, schema depth, node 수, example 제거를 기본으로 하고 확장은 opt-in이다.
8. **하드코딩 금지.** API 버전, endpoint 목록, schema 이름, tool 별 endpoint 매핑을 소스 코드에 넣지 않는다.
9. **Phase 1 zero-dependency 보존.** SDK 의존은 `mcp/` 패키지 안에서만 끝난다.

## 4. 아키텍처와 의존 방향

```text
                    MCP Adapter  (tools/atlassian_docs/mcp/)      ← mcp SDK 허용
                         │
                         ▼
               Intelligence Layer  (tools/atlassian_docs/intelligence/)  ← stdlib only
       ┌───────────┬─────────┼──────────┬───────────┐
       ▼           ▼         ▼          ▼           ▼
    search     inspect    schemas   request     check
       └───────────┴─────────┼──────────┴───────────┘
                             ▼
                     RegistryManager  (freshness, gate, swap)
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
│   ├── manager.py         RegistryManager: load, freshness, refresh, swap
│   ├── provenance.py      SourceProvenance 계산
│   ├── search.py          tokenizer, index, weighted search
│   ├── inspect.py         get_operation / get_schema 출력 조립 (compact 정책)
│   ├── request_template.py
│   └── request_check.py
│
└── mcp/
    ├── __init__.py
    ├── __main__.py        python -m tools.atlassian_docs.mcp
    ├── server.py          FastMCP 인스턴스 생성, tool/resource 등록만
    ├── tools.py           tool 핸들러 (SDK 무관 순수 함수 + 얇은 SDK 바인딩)
    └── resources.py       P1 resources

tests/
├── (Phase 1 테스트 유지)
├── intelligence/
│   ├── test_models.py
│   ├── test_normalizer.py
│   ├── test_schemas.py
│   ├── test_registry.py
│   ├── test_gate.py
│   ├── test_manager.py
│   ├── test_search.py
│   ├── test_inspect.py
│   ├── test_request_template.py
│   └── test_request_check.py
├── mcp/
│   ├── test_tools.py      SDK 없이 핸들러 로직 검증
│   └── test_server.py     SDK in-memory client 통합 (SDK 미설치 시 skip)
├── test_layering.py       import 방향 규칙
├── fixtures/openapi/
│   ├── jira-platform-openapi.json      실제 스펙에서 축약 (10~15 ops)
│   ├── jira-software-openapi.json      실제 스펙에서 축약 (path-level params 포함)
│   ├── confluence-openapi.json         실제 스펙에서 축약 (requestBodies component 포함)
│   ├── edge-cases-openapi.json         합성: cycle, missing ref, external ref, allOf/oneOf, operationId 없음, path-level override
│   └── make_openapi_fixtures.py        캐시에서 축약 fixture를 결정적으로 생성하는 수동 스크립트
└── live_mcp_smoke.py      수동, 네트워크 필요

requirements-mcp.txt       mcp>=2.2,<3   (MCP 계층 전용 optional dependency)
```

## 6. Domain Model (`models.py`)

모든 모델은 `@dataclass(frozen=True)`이며 컬렉션은 `tuple`을 쓴다. JSON 직렬화는 `to_dict()`로 제공한다. raw schema 조각(`schema`, `request_body.content[*].schema`, `responses[*].content[*].schema`)은 **원본 dict 그대로 보존**하며 `$ref`를 풀지 않는다.

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
class SecurityRequirement:
    scheme: str            # securitySchemes 키 이름 그대로
    scopes: tuple[str, ...]

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
    security: tuple[SecurityRequirement, ...]
    deprecated: bool
    experimental: bool                    # x-experimental
    oauth2_scopes: tuple[str, ...]        # x-atlassian-oauth2-scopes (없으면 빈 tuple)
```

`SourceRegistry`, `Registry`, `SourceProvenance`는 §9, §12에서 정의한다.

## 7. Normalizer (`normalizer.py`)

```python
def normalize_openapi(source_name: str, spec: dict) -> SourceRegistry
```

### 7.1 처리 대상

`paths`, `components.schemas`, `components.parameters`, `components.requestBodies`, `components.responses`, `components.securitySchemes`, 최상위 `security`, `tags`, `openapi`, `info.title`.

### 7.2 Path 순회

허용 HTTP method: `get post put patch delete head options trace`. path item의 다른 키(`parameters`, `summary`, `description`, `servers`, `$ref`, `x-*`)는 operation으로 취급하지 않는다. path item 자체가 `$ref`인 경우는 unsupported로 기록하고 해당 path를 건너뛴다(관찰되지 않음).

### 7.3 Parameter 병합 규칙

1. path-level `parameters`를 먼저 수집한다. `$ref`인 항목은 `components.parameters`에서 해석한다.
2. operation-level `parameters`를 수집한다. 동일하게 `$ref` 해석.
3. `(name, location)`을 키로 하여 **operation-level이 path-level을 override**한다.
4. 결과 순서: path-level 순서 유지 → 신규 operation-level 항목을 뒤에 추가.
5. `location == "path"`인 parameter는 OpenAPI 규칙상 `required: true`로 강제한다.

### 7.4 requestBody / responses

- `requestBody`가 `$ref`이면 `components.requestBodies`에서 해석한다(Confluence에서 24개 사용).
- `responses[*]`가 `$ref`이면 `components.responses`에서 해석한다.
- 각 media type의 `schema`는 raw dict로 보존, `example`/`examples`는 **normalizer 단계에서 버린다**(Registry에 실리지 않음).

### 7.5 Security와 확장 필드

- operation-level `security`가 있으면 그것을, 없으면 최상위 `security`를 사용한다. `security: []`는 "인증 없음"으로 빈 tuple.
- `x-atlassian-oauth2-scopes`: 문자열 배열이면 `oauth2_scopes`로 보존. 다른 형태면 무시.
- `x-experimental`: truthy면 `experimental=True`.
- 그 외 `x-*`는 무시한다.

### 7.6 결정성

같은 spec dict 입력에 대해 operation 순서·내용·fingerprint가 동일해야 한다. paths와 methods는 spec 내 등장 순서를 따르되, 정렬이 필요한 곳(`tags`, `schema names` 목록)은 명시적으로 정렬한다.

### 7.7 실패 정책

normalizer는 개별 operation 처리 중 예외를 만나면 그 operation을 건너뛰고 `SourceRegistry.warnings`에 `{"kind": "operation_skipped", "path":..., "method":..., "reason":...}`를 기록한다. spec 전체가 처리 불가능한 구조(`paths`가 dict가 아님 등)이면 `NormalizationError`를 발생시키며, 이는 gate(§10)에서 incompatible로 처리된다.

## 8. Schema Registry와 `$ref` 해석 (`schemas.py`)

### 8.1 Lookup

```python
registry.get_schema(source: str, name: str) -> dict | None   # raw, $ref 유지
```

### 8.2 지원 범위

지원: `#/components/schemas/{name}`, `#/components/parameters/{name}`, `#/components/requestBodies/{name}`, `#/components/responses/{name}`.
미지원: `http(s)://...`, `file://...`, `other.json#/...`, `#/paths/...`. 미지원 ref는 오류가 아니라 `{"$ref": "<원문>", "_unresolved": "external"}`로 남긴다. 존재하지 않는 local ref는 `{"$ref": "<원문>", "_unresolved": "missing"}`.

### 8.3 Recursive resolution

```python
def resolve(node: dict, source_registry, *, max_depth: int = 2, max_nodes: int = 200) -> ResolvedSchema
```

- `$ref`를 만나면 대상 schema를 inline으로 치환하고 `depth += 1`.
- 현재 해석 경로(stack)에 이미 있는 ref를 다시 만나면 `{"$ref": ..., "_cycle": true}`로 멈춘다.
- `depth > max_depth`이면 `{"$ref": ..., "_truncated": "depth"}`.
- 치환한 총 node 수가 `max_nodes`를 넘으면 이후 ref는 `{"$ref": ..., "_truncated": "nodes"}`.
- `allOf`/`oneOf`/`anyOf`/`items`/`properties`/`additionalProperties`(dict인 경우)/`not` 안으로 재귀한다. 이 키워드들은 **구조를 바꾸지 않고 그대로 유지**한다(allOf를 merge하지 않는다 — merge는 `request_check.py`의 책임).
- `ResolvedSchema`는 `schema: dict`, `truncated: bool`, `unresolved: tuple[str, ...]`, `cycles: tuple[str, ...]`, `node_count: int`를 갖는다.

기본값 `max_depth=2`, 허용 최대 `8`; `max_nodes` 기본 `200`, 허용 최대 `2000`.

## 9. Operation Registry (`registry.py`)

### 9.1 Canonical key와 alias

```text
key = f"{source}:{METHOD}:{path}"      예) jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments
```

- `operation_id → tuple[key, ...]` alias 맵을 유지한다. 길이가 1이 아니면 조회 API는 `ambiguous` 결과를 돌려주고 canonical key 사용을 요구한다.
- key는 source 안에서 유일해야 한다(OpenAPI 상 `paths` 키와 method 조합은 본질적으로 유일). 중복 발견은 integrity 실패(§10.2).

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
    schemas: Mapping[str, dict]          # components.schemas raw
    parameters: Mapping[str, dict]
    request_bodies: Mapping[str, dict]
    responses: Mapping[str, dict]
    security_schemes: Mapping[str, dict]
    tags: tuple[str, ...]
    spec_sha256: str                     # storage.sha256_of_spec(spec) — Phase 1 metadata.sha256과 동일 정의
    warnings: tuple[dict, ...]
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

`fingerprint = sha256("\n".join(f"{name}:{sources[name].spec_sha256 if loaded else '-'}" for name in sorted(sources.SOURCES)))`.

조회 API: `get_operation(key)`, `find_by_operation_id(source|None, operation_id)`, `list_operations(source=None, method=None, tag=None, include_deprecated=True)`, `list_sources()`, `list_tags(source)`, `get_schema(source, name)`.

### 9.4 메모리 상주와 재사용

Registry는 프로세스 메모리에 상주한다. 재빌드 시 **sha가 바뀌지 않은 source의 `SourceRegistry` 객체는 재사용**하고, 바뀐 source만 normalize한다. 942 operations 전체 normalize도 1초 미만이어야 하며(AC-33), 이 최적화는 정확성 조건이 아니라 편의 조건이다.

## 10. Compatibility Gate와 Integrity Check (`gate.py`)

### 10.1 Compatibility Gate (source 단위, normalize 전)

| 검사 | 통과 조건 | 실패 시 |
|---|---|---|
| dialect | `spec["openapi"]`가 문자열이고 `3.0.` 또는 `3.1.`로 시작 | `incompatible_dialect` |
| structure | `extractor.is_openapi_candidate(spec)` 참 | `invalid_structure` |
| paths | `paths`에 허용 method를 가진 operation이 1개 이상 | `no_operations` |

실패한 source는 **이전 `SourceRegistry`를 유지**하고 `SourceProvenance.status = "stale"`, `reason = <실패 코드>`로 표시한다. 이전 registry가 없으면 `unavailable`. `openapi: "4.x"` 같은 미래 dialect는 자동 대응 대상이 아니다 — Atlassian API 버전 변화(v3→v4)와 OpenAPI 명세 포맷 변화는 다른 문제다.

### 10.2 Integrity Check (source 단위, normalize 후)

| 검사 | 조건 | 실패 시 |
|---|---|---|
| operations | `len(operations) > 0` | `empty_registry` |
| unique keys | key 중복 없음 | `duplicate_keys` |
| exceptions | normalize가 `NormalizationError`를 던지지 않음 | `normalization_failed` |
| schema access | `components.schemas`가 dict (없으면 빈 dict) | `invalid_components` |

실패 시 처리는 10.1과 같다.

### 10.3 Anomaly Warning (차단하지 않음)

이전 registry 대비 operation 수가 50% 이상 감소하면 `SourceProvenance.warnings`에 `{"kind": "operation_count_drop", "previous": N, "current": M}`을 남긴다. major migration일 수 있으므로 swap은 진행한다.

## 11. RegistryManager와 Self-Update (`manager.py`)

### 11.1 상태

```python
class RegistryManager:
    current: Registry | None                 # atomic attribute assignment으로만 교체
    provenance: Mapping[str, SourceProvenance]
    last_refresh_attempt: str | None         # ISO UTC
    last_refresh_result: dict | None
    _lock: threading.Lock                    # refresh 직렬화
```

### 11.2 Startup (cache-first)

```text
START
  ├─ storage.read_metadata(), 각 source storage.read_cache_spec()
  ├─ 유효 캐시가 있는 source → gate → normalize → integrity → SourceRegistry
  ├─ 유효 캐시가 하나도 없음 → 이 경우에만 startup에서 sync.sync_all() 1회 시도 후 재시도
  ├─ 그래도 모두 unavailable → RegistryUnavailableError (MCP 프로세스 종료, exit 2)
  └─ 하나 이상 로드됨 → Registry 조립 → READY   (네트워크 없음)
```

TTL이 만료되어 있어도 startup은 네트워크에 가지 않는다. freshness는 `stale`로 표시되고 첫 intelligence 요청에서 갱신을 시도한다.

### 11.3 `ensure_fresh()` — 요청 시 lazy refresh

`search_operations`, `get_operation`, `get_schema`, `build_request_template`, `check_request` 처리 직전에 호출한다. `get_api_status`는 호출하지 않는다(순수 조회).

```text
ensure_fresh():
  if no source is TTL-expired: return
  if last_refresh_attempt within MIN_RETRY_INTERVAL (기본 15분): return   # 실패 반복 방지
  with _lock (non-blocking; 이미 다른 요청이 갱신 중이면 그냥 현재 registry 사용):
      results = sync.sync_all(force=False)          # Phase 1 그대로. TTL 존중.
      last_refresh_attempt = now; last_refresh_result = results 요약
      rebuild_if_changed()
```

`MIN_RETRY_INTERVAL`이 필요한 이유: Phase 1은 refresh 실패 시 `last_checked`를 갱신하지 않으므로, 이 backoff가 없으면 오프라인 상태에서 매 요청마다 네트워크 타임아웃을 기다리게 된다.

### 11.4 `rebuild_if_changed()`

```text
metadata = storage.read_metadata()
for source in SOURCES:
    spec = storage.read_cache_spec(source)
    if spec is None or not gate.compatible(spec): mark stale/unavailable; keep previous SourceRegistry
    elif sha256_of_spec(spec) == current.sources[source].spec_sha256: reuse
    else: candidate = normalize(...); integrity(candidate) → 성공 시 채택, 실패 시 previous 유지 + stale
new = Registry(assembled)
if new.fingerprint != current.fingerprint: self.current = new      # atomic swap
recompute provenance
```

어느 시점에도 `current`가 `None`으로 돌아가지 않는다. 요청 처리 코드는 `registry = manager.current`를 한 번 읽어 그 스냅샷으로 끝까지 처리한다.

### 11.5 `refresh(force_retry=True)` — `refresh_api_docs` tool

`ensure_fresh()`와 같지만 `MIN_RETRY_INTERVAL`을 무시한다. Phase 1 TTL은 여전히 존중한다(`sync_all(force=False)`). 결과: per-source sync status, `registry_rebuilt: bool`, `fingerprint_before`, `fingerprint_after`.

### 11.6 동시성

MCP SDK는 asyncio 위에서 tool을 동시에 실행할 수 있다. `sync.sync_all()`은 blocking I/O이므로 MCP 계층은 `asyncio.to_thread`로 감싼다. Manager 내부는 `threading.Lock`으로 refresh를 직렬화하고, `current` 교체는 단일 attribute 대입이므로 reader는 lock 없이 스냅샷을 읽는다. 여러 MCP 프로세스가 동시에 같은 `.atlassian-docs/`를 갱신하는 경우의 file locking은 Phase 1과 동일하게 범위 밖이다(Phase 1 atomic replace 덕분에 깨진 파일은 생기지 않는다).

## 12. Provenance (`provenance.py`)

```python
@dataclass(frozen=True)
class SourceProvenance:
    source: str
    status: str                      # "fresh" | "stale" | "unavailable"
    reason: str | None               # stale/unavailable 사유: "ttl_expired" | "refresh_failed" | "incompatible_dialect" | ... | "no_cache"
    api_version: str | None          # metadata.api_version (jira-software는 null 정상)
    spec_sha256: str | None
    openapi_version: str | None
    resolved_documentation_url: str | None
    last_checked: str | None
    last_updated: str | None
    operation_count: int
    schema_count: int
    warnings: tuple[dict, ...]
```

상태 정의:

| status | 조건 |
|---|---|
| `fresh` | 유효 캐시가 로드됨 **and** 캐시 sha == metadata.sha256 **and** `last_checked`가 TTL(24h) 이내 |
| `stale` | 유효 캐시(또는 이전 registry)가 서비스 중이지만 TTL 만료, 최근 refresh 실패, metadata 불일치, gate/integrity 실패 중 하나 |
| `unavailable` | 서비스할 registry가 없음 |

모든 intelligence 응답(§14)은 `"provenance": {source: SourceProvenance.to_dict()}`를 관련 source에 대해 포함하고, 최상위에 `"registry_fingerprint"`를 포함한다.

## 13. Weighted Lexical Search (`search.py`)

### 13.1 Tokenizer

1. camelCase 경계 분리(`addAttachment` → `add Attachment`)
2. lowercase
3. `[^a-z0-9]+`로 split (snake/kebab/path 구분자 포함, `{issueIdOrKey}` → `issue id or key`)
4. 길이 1 토큰 제거
5. 영어 기능어 stopword 제거: `a an the to of for in on at and or with by from is are be this that`
6. 단순 복수형 정규화: 길이 > 3이고 `s`로 끝나면 마지막 `s` 제거 (`issues`→`issue`, `attachments`→`attachment`)

### 13.2 Index 필드와 가중치

| 필드 | 가중치 | 비고 |
|---|---|---|
| operation_id | 5 | |
| summary | 4 | |
| tags | 3 | |
| path | 3 | path parameter 이름 포함 |
| schema names | 2 | request/response media type schema의 `$ref` 마지막 세그먼트, inline이면 없음 |
| method | 1 | `post`, `get` 등 |
| description | 1 | 처음 1,000자만 index |

각 operation은 필드별 token **set**을 registry build 시 미리 계산한다(`SearchIndex`).

### 13.3 Scoring

```text
score(op) = Σ_{t ∈ query_tokens} Σ_{f ∈ fields} weight(f) · [t ∈ tokens(op, f)]
          + 2 · [모든 query token이 어느 필드에서든 1회 이상 매칭]
score(op) *= 0.7  if op.deprecated
```

score가 0인 operation은 결과에서 제외한다. 정렬: score 내림차순 → `deprecated=False` 우선 → source 이름 오름차순 → key 오름차순. 결정적이어야 한다(AC-10).

### 13.4 인터페이스

```python
def search_operations(registry, query: str, *, source=None, method=None, tag=None,
                      include_deprecated=True, limit=10) -> SearchResult
```

`limit` 기본 10, 최대 50. 결과 항목: `key, source, operation_id, method, path, summary, tags, deprecated, experimental, score`. 빈 query 또는 토큰이 전부 제거된 query는 `{"error": "empty_query"}`.

### 13.5 검색 품질 고정 테스트

fixture 기반으로 다음 순위를 테스트로 고정한다.

- `"upload attachment to issue"` → 1위가 jira-platform `addAttachment`
- `"sprint board backlog"` → 상위 3개가 전부 jira-software
- `"create confluence page"` → 상위 1개가 confluence `POST .../pages`
- `"IssueCreateMetadata"` (정확한 schema 이름) → 해당 schema를 참조하는 operation이 1위
- `source="confluence"` 필터 시 jira 결과 0개

## 14. Intelligence API (`inspect.py`) — 출력 정책

### 14.1 공통

모든 함수는 JSON 직렬화 가능한 dict를 반환하고 `provenance`, `registry_fingerprint`를 포함한다. 조회 실패는 예외가 아니라 `{"error": {"code": ..., "message": ...}}`로 반환한다. 코드: `operation_not_found`, `ambiguous_operation_id`(후보 key 목록 포함), `schema_not_found`, `source_unavailable`, `empty_query`, `invalid_argument`.

### 14.2 `get_operation(key | (source, operation_id), *, include_description=False, include_responses=False, resolve_schema_depth=0)`

기본(compact) 출력:

```json
{
  "key": "jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/attachments",
  "source": "jira-platform", "operation_id": "addAttachment",
  "method": "POST", "path": "/rest/api/3/issue/{issueIdOrKey}/attachments",
  "summary": "Add attachment",
  "description": "Adds one or more attachments to an issue. ... (처음 500자, 잘리면 description_truncated: true)",
  "tags": ["Issue attachments"], "deprecated": false, "experimental": false,
  "oauth2_scopes": ["write:jira-work"],
  "parameters": [{"name": "issueIdOrKey", "in": "path", "required": true, "schema": {"type": "string"}}],
  "request_body": {"required": true, "content": [{"content_type": "multipart/form-data", "schema": {"type": "array", "items": {"$ref": "#/components/schemas/MultipartFile"}}}]},
  "responses": [{"status": "200", "content_types": ["application/json"]}, {"status": "403"}, {"status": "404"}, {"status": "413"}],
  "security": [{"scheme": "OAuth2", "scopes": ["write:jira-work"]}, {"scheme": "basicAuth", "scopes": []}],
  "provenance": {...}, "registry_fingerprint": "..."
}
```

- `include_description=True`: description 전체.
- `include_responses=True`: 각 response의 description과 media type schema(`$ref` 유지) 포함.
- example은 normalizer 단계에서 버려지므로(§7.4) 어떤 옵션으로도 반환되지 않는다.
- `resolve_schema_depth > 0`: parameter/request/response schema를 §8 규칙으로 inline 해석(최대 8).

### 14.3 `get_schema(source, name, *, max_depth=2, max_nodes=200)`

`{"source", "name", "schema": <resolved>, "truncated", "unresolved", "cycles", "node_count", "provenance", "registry_fingerprint"}`.

## 15. Request Template Builder (`request_template.py`)

```python
def build_request_template(registry, key: str, values: dict | None = None) -> dict
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
  "content_types": ["multipart/form-data"],
  "selected_content_type": "multipart/form-data",
  "body_schema": {"type": "array", "items": {"$ref": "#/components/schemas/MultipartFile"}},
  "body": null,
  "body_required": true,
  "security": [...], "oauth2_scopes": [...],
  "server": null,
  "missing_required": ["body"],
  "notes": ["server URL and Authorization are out of scope for Phase 2"],
  "provenance": {...}, "registry_fingerprint": "..."
}
```

규칙:

- `path`는 모든 path parameter 값이 주어졌을 때만 채우고, 아니면 `null`. 값은 `urllib.parse.quote(str(v), safe="")`로 인코딩.
- `query`/`headers`는 spec에 선언된 parameter를 이름별로 나열하고 `values`에서 온 값을 `value`에 채운다. spec에 없는 값은 `unknown_parameters`에 나열한다(버리지 않음).
- `selected_content_type`: `values.content_type`가 선언된 것 중 하나면 그것, 아니면 첫 번째 선언 content type.
- `server`는 항상 `null`. `Authorization`, `Cookie` header 값은 절대 생성하지 않는다.
- `missing_required`: 값이 없는 required path/query/header parameter 이름과, `body_required`인데 body가 없으면 `"body"`.

## 16. Structural Request Check (`request_check.py`)

```python
def check_request(registry, key: str, *, path_params=None, query=None, headers=None,
                  body=None, content_type=None) -> dict
```

출력:

```json
{
  "compatible": false,
  "errors":   [{"location": "path.issueIdOrKey", "rule": "required", "message": "required path parameter is missing"}],
  "warnings": [{"location": "query.foo", "rule": "unknown_parameter", "message": "not declared in the specification"}],
  "checked":     ["required_parameters", "parameter_types", "parameter_enums", "body_required", "content_type", "body_required_properties", "body_property_types", "body_property_enums"],
  "not_checked": ["oneOf/anyOf branches", "pattern", "format", "min/max", "nested objects beyond depth 2", "additionalProperties"],
  "provenance": {...}, "registry_fingerprint": "..."
}
```

규칙 목록(이것이 전부다 — 여기 없는 것은 검사하지 않으며 `not_checked`에 명시한다):

| rule | 대상 | 결과 |
|---|---|---|
| `required` | required path/query/header parameter 누락 | error |
| `type` | parameter 값의 primitive type(`string`,`integer`,`number`,`boolean`,`array`) 불일치. query/header는 문자열 → 선언 type으로 coercion 가능하면 통과(`"5"`→integer OK) | error |
| `enum` | parameter 값이 enum 밖 | error |
| `unknown_parameter` | spec에 없는 query/header | warning |
| `body_required` | `request_body.required`인데 body 없음 | error |
| `content_type` | 주어진 content_type이 선언되지 않음 | error |
| `body_required_properties` | body schema(depth ≤ 2로 `$ref` 해석, `allOf`는 `required`/`properties`를 합집합으로 merge)의 top-level `required` 누락 | error |
| `body_property_type` | top-level property primitive type 불일치 (`nullable: true`이면 `null` 허용) | error |
| `body_property_enum` | top-level property enum 위반 | error |
| `body_unknown_property` | `additionalProperties: false`가 명시된 경우에만 미선언 property | warning |
| `not_checked` | body schema가 `oneOf`/`anyOf`이거나 depth 2 안에서 해석 불가 | warning `structure_not_checked` |

`compatible = len(errors) == 0`. 이 값은 "우리가 검사한 규칙에서 오류가 없음"을 뜻하며 OpenAPI 전체 규칙 만족을 뜻하지 않는다 — tool description에 이 문장을 그대로 넣는다.

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
| `get_operation` | `key?` 또는 (`source?`, `operation_id?`), `include_description?`, `include_responses?`, `resolve_schema_depth?=0` | §14.2 | 예 |
| `get_schema` | `source`, `name`, `max_depth?=2`, `max_nodes?=200` | §14.3 | 예 |
| `build_request_template` | `key`, `values?` | §15 | 예 |
| `check_request` | `key`, `path_params?`, `query?`, `headers?`, `body?`, `content_type?` | §16 | 예 |
| `get_api_status` | 없음 | §17.3 | 아니오 |
| `refresh_api_docs` | 없음 | §11.5 | (자체 refresh) |

tool description은 provenance 해석법("status가 stale이면 결과는 마지막 정상 스펙 기준"), `compatible`의 의미, 실제 호출을 하지 않는다는 사실을 포함한다. 입력 스키마는 SDK가 type hint에서 생성한다.

### 17.3 `get_api_status` 출력

```json
{
  "registry_fingerprint": "...", "built_at": "...",
  "sources": { "jira-platform": {<SourceProvenance>}, "jira-software": {...}, "confluence": {...} },
  "refresh": { "ttl_seconds": 86400, "min_retry_interval_seconds": 900,
               "last_refresh_attempt": "...", "last_refresh_result": {...} },
  "execution": "disabled"
}
```

### 17.4 오류 계약

intelligence 함수가 돌려준 `{"error": ...}`는 tool 결과로 그대로 전달하고 MCP `isError=true`로 표시한다. 예상치 못한 예외는 `{"error": {"code": "internal_error", "message": str(exc)}}`로 변환하며 서버 프로세스는 죽지 않는다.

### 17.5 크기 제한

tool 결과 직렬화 크기가 200 KB를 넘으면 결과 대신 `{"error": {"code": "result_too_large", "message": "...reduce limit / max_depth / max_nodes"}}`를 반환한다.

## 18. MCP Resources (P1)

P0 완료 후 추가한다. raw OpenAPI 전체 resource는 만들지 않는다.

```text
atlassian://operation/{source}/{operation_id}     → get_operation compact 출력 (ambiguous면 후보 목록)
atlassian://schema/{source}/{name}                → get_schema(max_depth=2)
```

`resources/list`는 template 두 개만 노출하고 개별 operation을 열거하지 않는다(942개 열거는 context 낭비).

## 19. Degraded / Unavailable

| 상황 | MCP 동작 |
|---|---|
| 일부 source stale | 정상 서비스, 해당 source provenance `stale` + reason |
| 일부 source unavailable | 나머지 source로 정상 서비스. 해당 source 지정 요청은 `source_unavailable` 오류. 검색 결과에서 자연히 제외 |
| 모든 source unavailable (startup) | §11.2에 따라 1회 sync 시도 후에도 없으면 프로세스 종료 exit 2 |
| refresh 실패 (runtime) | 이전 registry 유지, provenance `stale/refresh_failed`, 15분 backoff |
| gate/integrity 실패 (runtime) | 이전 registry 유지, provenance `stale/<code>` |
| metadata.json 손상 | provenance의 metadata 필드 `null`, 캐시 파일이 유효하면 registry는 로드(Phase 1 self-heal이 다음 sync에서 복구) |

## 20. Dependencies와 패키징

- Phase 1 core, `intelligence/`, 모든 `tests/intelligence/*`: **stdlib only** (Python ≥ 3.10; 개발 환경 3.11).
- `mcp/`, `tests/mcp/test_server.py`: `mcp>=2.2,<3` (`requirements-mcp.txt`).
- `pyproject.toml`/`pip install -e .`는 도입하지 않는다 — 최상위 패키지 이름이 `tools`라 site-packages에 설치하는 것이 부적절하고, Phase 1이 이미 "저장소 루트에서 `python -m`" 규약을 쓰고 있다.
- `tests/mcp/test_server.py`는 `unittest.skipUnless(importlib.util.find_spec("mcp"))`로 SDK 미설치 환경에서 skip한다. 기본 `python -m unittest discover -s tests -t .`는 SDK 없이도 실패 없이 끝나야 한다.

## 21. 테스트 전략

### 21.1 Fixture

`tests/fixtures/openapi/make_openapi_fixtures.py`가 `.atlassian-docs/*.json`에서 지정된 path 목록만 추출하고, 참조되는 components를 transitive closure로 포함해 결정적으로(`sort_keys=True`) 저장한다. 생성물은 커밋한다. 포함 조건:

- jira-platform: `POST /rest/api/3/issue`, `POST .../issue/{issueIdOrKey}/attachments`, `GET .../issue/{issueIdOrKey}`, `GET .../issue/createmeta` 계열(`IssueCreateMetadata` 참조), `GET /rest/api/3/search/jql`, deprecated operation 1개 이상, `allOf` 사용 schema 1개 이상
- jira-software: path-level `parameters`가 있는 `/rest/builds/0.1/bulk` 등, sprint/board/backlog operation 3개 이상, `/rest/agile/1.0/`과 `/rest/*/0.1/` 네임스페이스 혼재 (Phase 1의 알려진 후속 과제였던 jira-software fixture 부재를 여기서 해소)
- confluence: `POST /pages`, `GET /pages/{id}`, cursor pagination parameter가 있는 list operation, `$ref` requestBody 사용 operation
- edge-cases(합성): 순환 `$ref`, missing ref, external ref, `oneOf`/`anyOf`, operationId 없는 operation, operation-level이 path-level을 override하는 parameter, `openapi: "3.1.0"` 항목; 별도 파일 `unsupported-dialect-openapi.json`(`openapi: "4.0.0"`)

### 21.2 Unit

normalizer, schemas, registry, gate, manager(storage/sync를 monkeypatch한 fake), search 순위, inspect compact 정책, request_template, request_check 규칙별.

### 21.3 Integration

- fixture 캐시 디렉터리를 `tempfile`에 만들고 `storage.CACHE_DIR`를 patch → `RegistryManager` startup → intelligence 함수 → 기대 출력.
- self-update: 캐시 파일과 metadata sha를 바꾼 뒤 `refresh()` → fingerprint 변경, 새 operation 검색 가능. gate 실패 스펙으로 교체 → 이전 registry 유지 + `stale`.
- `tests/mcp/test_server.py`: SDK in-memory client로 7개 tool `tools/list`와 각 1회 호출.

### 21.4 Layering test

`tests/test_layering.py`: `ast`로 각 모듈의 import를 읽어 §4 금지 방향을 검사한다. `tools/atlassian_docs/intelligence/**`와 Phase 1 모듈은 `mcp` 패키지를 import하지 않는다.

### 21.5 Live smoke (수동)

`python tests/live_mcp_smoke.py`: 실제 sync → RegistryManager → `search_operations("upload attachment to issue")` 1위가 jira-platform attachment operation → `get_operation` → `build_request_template`. 네트워크 필요, 기본 suite에 포함하지 않음, Atlassian API 호출 없음.

## 22. Milestones

| Milestone | 포함 | 완료 조건 |
|---|---|---|
| **2A Intelligence Core** | models, normalizer, schemas, registry, gate, fixtures, layering test | fixture 3종 + edge-cases normalize, `$ref` 해석, gate 동작. Python 라이브러리로 단독 사용 가능 |
| **2B Request Intelligence** | search, provenance, inspect, request_template, request_check | §13.5 순위 테스트 통과, §15/§16 규칙 테스트 통과 |
| **2C Self-Update** | manager (startup, ensure_fresh, refresh, swap, backoff) | §21.3 self-update 통합 테스트 통과 |
| **2D MCP Exposure** | mcp/server, tools, resources(P1), requirements-mcp.txt, AGENTS.md/README 갱신, live_mcp_smoke | 7 tool in-memory 통합 테스트 통과, Claude Code에서 실제 사용 확인 |

순서를 바꾸지 않는다. 특히 MCP를 먼저 만들면 이후 로직 테스트가 프로토콜에 얽힌다. 2C를 2D 앞에 둔 이유는 manager가 SDK 없이 테스트 가능해야 하기 때문이다.

## 23. Acceptance Criteria

| # | 조건 |
|---|---|
| AC-01 | Phase 1 테스트 67개가 그대로 통과한다 |
| AC-02 | Phase 1 모듈 5개의 diff가 0이다 |
| AC-03 | Phase 1 core와 `intelligence/`는 stdlib 외 import가 없다 (layering test) |
| AC-04 | 3개 실제 source 캐시를 모두 normalize할 수 있다 (live smoke) |
| AC-05 | 모든 operation에 `{source}:{METHOD}:{path}` key가 생성되고 source 안에서 유일하다 |
| AC-06 | operationId 없는 operation도 registry에 포함된다 |
| AC-07 | 중복 operationId는 `ambiguous_operation_id`로 응답한다 |
| AC-08 | path-level parameter가 operation-level에 의해 `(name, in)` 기준 override된다 |
| AC-09 | local `$ref` 4종을 해석하고, 순환·missing·external ref가 예외 없이 marker로 표시된다 |
| AC-10 | 동일 query·registry에 대해 검색 결과 순서가 결정적이다 |
| AC-11 | §13.5의 순위 테스트 5개가 통과한다 |
| AC-12 | source/method/tag/include_deprecated 필터가 동작한다 |
| AC-13 | `get_operation` 기본 출력에 example이 없고 description이 500자로 잘린다 |
| AC-14 | `get_schema`가 `max_depth`/`max_nodes`를 지키고 `truncated`를 보고한다 |
| AC-15 | `build_request_template`가 `server: null`을 반환하고 Authorization 값을 생성하지 않는다 |
| AC-16 | `build_request_template`가 required 누락을 `missing_required`로 보고한다 |
| AC-17 | `check_request`가 §16의 규칙 전부를 검출하고 `not_checked`를 명시한다 |
| AC-18 | `check_request` 출력에 `valid` 키가 없다 |
| AC-19 | 모든 intelligence 응답에 `provenance`와 `registry_fingerprint`가 있다 |
| AC-20 | `openapi: "4.0.0"` 스펙은 gate에서 거부되고 이전 registry가 유지된다 |
| AC-21 | integrity 실패 시 이전 registry가 유지되고 provenance가 `stale`이다 |
| AC-22 | spec sha 변경 후 `refresh()`에서 registry가 재빌드되고 fingerprint가 바뀐다 |
| AC-23 | sha 미변경 source의 `SourceRegistry` 객체가 재사용된다 |
| AC-24 | refresh 실패 후 15분 안의 요청은 네트워크를 시도하지 않는다 |
| AC-25 | startup은 캐시가 하나라도 있으면 네트워크에 가지 않는다 |
| AC-26 | 캐시가 전혀 없을 때만 startup에서 sync를 1회 시도하고, 실패 시 exit 2 |
| AC-27 | 한 source unavailable 상태에서 나머지 source가 정상 서비스된다 |
| AC-28 | MCP `tools/list`가 정확히 7개를 반환한다 |
| AC-29 | 7개 tool 각각이 in-memory client 통합 테스트에서 성공 응답을 반환한다 |
| AC-30 | tool 결과 200 KB 초과 시 `result_too_large`를 반환한다 |
| AC-31 | SDK 미설치 환경에서 기본 테스트 suite가 skip만 있고 실패 없이 끝난다 |
| AC-32 | 오프라인에서 전체 suite가 통과한다 (네트워크 mock 없이 호출 자체가 없음) |
| AC-33 | 실제 3개 캐시 전체 normalize + index build가 1초 이내다 (live smoke에서 측정) |
| AC-34 | 저장소 어디에도 `urllib`/`http` 호출로 `atlassian.net`에 요청하는 코드가 없다 (Phase 1의 `developer.atlassian.com` 문서 fetch 제외) |
| AC-35 | API 버전·endpoint·schema 이름이 소스 코드에 하드코딩되지 않는다 (fixture와 테스트 기대값 제외) |
| AC-36 | live smoke에서 `"upload attachment to issue"` 1위가 jira-platform attachment operation이다 |

## 24. Phase 2에서 하지 않는 것 (재확인)

개발 중 다음 요구가 나오더라도 이번 Phase에 넣지 않는다: 실제 실행(`execute_*`), OAuth/토큰, site URL 입력, endpoint별 tool, embedding, synonym dictionary, changelog 분석, OpenAPI→Markdown 전체 변환, 다른 벤더 OpenAPI. Phase 3 진입 조건은 registry self-update 안정성, request template의 실제 API 형태 일치, MCP interface 고정이다.

## 25. 한 줄 정의

> Phase 2는 Atlassian 공식 OpenAPI surface를 자동 추종하는 API Intelligence MCP다 — Atlassian 공식 문서 전체를 이해하는 시스템도, Jira/Confluence를 실행하는 시스템도 아니다.
