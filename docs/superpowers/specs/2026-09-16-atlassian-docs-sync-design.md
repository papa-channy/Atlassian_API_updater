# Atlassian API Docs Lightweight Sync — Technical Specification

**문서 버전:** v1.2
**대상:** Jira Cloud / Confluence Cloud API Reference
**목적:** AI 코딩 에이전트 및 개발 환경에서 Atlassian 공식 API 스펙을 최소한의 구조로 항상 최신 상태에 가깝게 유지
**설계 원칙:** Lightweight / Official-first / Discovery-first / Cache-first / Version-agnostic / Zero-maintenance / Fail-safe

---

## 0. v1.2 개정 배경

v1.1은 "stable discovery URL → HTML 안의 `<a href="...">OpenAPI</a>` anchor → 별도 OpenAPI JSON URL 다운로드"라는 2단계 resolver를 가정했다. 실제 구현 착수 전 `curl -L`로 세 discovery URL을 직접 검증한 결과, 이 가정은 현재 Atlassian 문서 사이트 구조와 맞지 않았다.

**직접 관찰한 사실 (2026-09-16 기준):**

- `jira-platform`: `/cloud/jira/platform/rest/` → 302 redirect → `/rest/v3/`
- `confluence`: `/cloud/confluence/rest/` → 302 redirect → `/rest/v2/`
- `jira-software`: `/cloud/jira/software/rest/` → 200, redirect 없음 (URL에 버전 세그먼트 자체가 없음)
- 세 페이지 모두 `<div id="root">` React SPA이며, static HTML에는 `<a href="...">OpenAPI</a>` 같은 anchor가 전혀 없다.
- 대신 OpenAPI spec 전체가 `<script>window.__DATA__ = {...};</script>` 안에 JSON으로 완전히 인라인 임베드되어 있다. 임베드 위치는 제품마다 다르다 — Jira Platform/Software는 최상위 근처, Confluence와 Jira Software 둘 다 실제로는 `"schema"` 키 아래 중첩된 형태로 관찰됨 (Jira Platform만 최상위에 가까움).
- Jira Software의 임베드된 단일 spec은 `info.version: "1001.0.0"`(빌드 스냅샷 문자열)이며, 78개 path 아래 Agile(`/rest/agile/1.0/...`)과 Builds/Deployments(`/rest/*/0.1/...`) 등 서로 다른 버전 네임스페이스를 한 문서 안에서 함께 제공한다.

이 관찰을 반영해 resolver를 폐기하고 embedded-JSON extractor로 교체했으며, 그 과정에서 실패 시맨틱(`last_checked`)과 crash recovery(cache/metadata 불일치 처리) 규칙도 함께 명문화했다. v1.1 대비 변경/신설된 절은 본문에 표시했다.

**최종 검토(같은 날 추가 반영)에서 잡은 것들:** `sha256`이 "canonical JSON 직렬화 결과의 해시"인지 "cache 파일 bytes의 해시"인지가 §21(추출 시점)과 §22(복구 시점) 사이에서 모호하게 읽힐 수 있었다 — **canonical JSON 기준으로 통일**했고 atomic write 순서(cache 먼저, metadata 나중)도 명시했다(§22). CLI가 실패를 exit code로 어떻게 알릴지 정의가 없었다 — 0/1/2 3단계로 신설했다(§26). `api_version` 추출 정규식을 URL path로 한정했다(§15). `window.__DATA__` 할당이 페이지에 2개 이상이거나 0개면 fail closed로 처리하도록 명시했다(§8). 동시 실행/file locking은 v1.2 범위 밖으로 명시했다(§4).

---

## 1. 개요

Jira와 Confluence API를 사용하는 개발 작업에서는 endpoint, request/response schema, parameter, authentication scope뿐 아니라 API의 major version 자체도 변경될 수 있다. 특정 버전이나 OpenAPI 파일 URL을 코드/설정에 직접 고정하면, Atlassian이 새로운 major API로 이동할 때 synchronization 시스템 자체를 수정해야 한다.

본 시스템은 OpenAPI URL이나 API 버전을 직접 관리하지 않는다. 대신 Atlassian이 제공하는 안정적인 공식 REST 문서 진입점만 알고 있으며, 실행 시점에 해당 문서를 받아 그 안에 임베드된 현재 공식 OpenAPI specification을 추출한다.

## 2. 목표

> Atlassian의 안정적인 공식 REST 문서 진입점으로부터 현재 공식 OpenAPI specification을 동적으로 추출하고, 이를 로컬에 캐싱하여 AI Agent와 개발 환경이 최신 API definition을 참조할 수 있도록 한다.

시스템 특성:

- Atlassian 공식 문서만 사용한다.
- API major version을 configuration에 고정하지 않는다.
- OpenAPI CDN URL을 configuration에 고정하지 않는다. (v1.2: 애초에 별도 OpenAPI URL이 존재하지 않는다 — §7 참고)
- stable documentation URL만 고정한다.
- API version은 runtime metadata로 취급하며, 식별 불가능한 경우 `null`이 정상 상태다.
- 별도 데이터베이스/서버를 두지 않는다.
- 문서 HTML 전체를 저장하거나 크롤링하지 않는다.
- OpenAPI specification(추출된 dict)을 핵심 source of truth로 사용한다.
- 최신 여부 확인은 실행 시점에 수행하며, TTL 이내에는 network에 접근하지 않는다.
- AI Agent는 항상 동일한 local file path를 사용한다.
- 초기 구현은 하나의 경량 CLI 패키지 수준으로 유지한다.

## 3. 핵심 설계 결정

1. OpenAPI URL을 저장하지 않는다 — 애초에 별도 URL이 존재하지 않으므로 저장할 대상 자체가 없다.
2. API version을 configuration에 저장하지 않는다.
3. Stable Discovery URL만 저장한다.
4. **(v1.2)** "OpenAPI 링크를 anchor에서 찾아 별도로 다운로드"하는 2단계 대신, "discovery URL이 반환한 HTML 안에서 embedded JSON을 추출"하는 1단계로 처리한다. HTTP 요청이 하나 줄어들고, `html.parser` 의존성이 사라진다.

```text
Atlassian Stable Discovery URL
        │
        ▼
   GET + redirect follow
        │
        ▼
 Resolved Documentation HTML
        │
        ▼
   Extractor (embedded JSON)
        │
        ▼
   OpenAPI candidate (dict)
        │
        ▼
  Validate → Canonicalize → SHA-256 → Version tag
        │
        ▼
     Local Cache
```

## 4. 비목표

v1에서는 다음을 구현하지 않는다: 전체 문서 크롤링, 자체 documentation website, Elasticsearch/Vector DB/RAG, semantic diff, 변경사항 자동 요약, Slack/Email 알림, GitHub Actions 기반 정기 실행, Postman/SDK 동기화, endpoint별 Markdown 자동 생성, 과거 버전 snapshot 관리, 자체 API 서버, deprecated API 자동 migration, HTML 전체 archive, **여러 프로세스의 동시 실행 조율/file locking** (v1.2 신설 — atomic replace가 파일 손상은 막아 주므로, 실제 동시 실행 문제가 확인된 이후에 다룬다). 실제 필요성이 확인된 이후 단계적으로 추가한다.

## 5. 관리 대상 API

현재 버전을 configuration에 포함하지 않는다는 점이 핵심이다.

| 논리 식별자 | Stable Discovery URL | 캐시 파일 |
|---|---|---|
| `jira-platform` | `https://developer.atlassian.com/cloud/jira/platform/rest/` | `jira-platform.json` |
| `jira-software` | `https://developer.atlassian.com/cloud/jira/software/rest/` | `jira-software.json` |
| `confluence` | `https://developer.atlassian.com/cloud/confluence/rest/` | `confluence.json` |

Jira Platform과 Jira Software는 서로 다른 API family로 간주한다 (`/rest/api/3/issue/...` vs `/rest/agile/1.0/sprint/...`는 하나의 API가 아니다). 현재 API가 v3/v2/versionless이든 미래에 v4/v3로 바뀌든, logical source ID와 파일명은 유지한다.

## 6. Source Configuration

```python
SOURCES = {
    "jira-platform": {
        "discovery_url": "https://developer.atlassian.com/cloud/jira/platform/rest/"
    },
    "jira-software": {
        "discovery_url": "https://developer.atlassian.com/cloud/jira/software/rest/"
    },
    "confluence": {
        "discovery_url": "https://developer.atlassian.com/cloud/confluence/rest/"
    },
}
```

다음 값은 configuration에 저장하지 않는다: `v3`/`v2`/`v1` 같은 버전 문자열, OpenAPI CDN URL, revision 파라미터. `discovery_url` 세 개가 전부다 — sync 로직이 필요로 하는 다른 필드는 없다.

## 7. Extractor (v1.2: `resolver.py` → `extractor.py`로 개명)

v1.1의 Resolver는 "OpenAPI가 있는 위치(URL)를 찾는" 컴포넌트였다. v1.2의 Extractor는 "이미 받은 HTML 안에서 OpenAPI 객체 자체를 꺼내는" 컴포넌트다 — URL을 resolve하지 않으므로 이름을 바꾼다.

Extractor는 **순수 함수**이며 HTTP를 모른다. 입력은 HTML 문자열, 출력은 검증 전 OpenAPI 후보 dict다.

```python
def extract_embedded_data(html: str) -> object: ...
def find_openapi_candidates(data: object) -> list[dict]: ...
def extract_openapi_spec(html: str) -> dict:  # 위 둘을 조합, 정확히 1개 후보일 때만 성공
    ...
```

## 8. Extractor Algorithm

각 API source에 대해 다음을 수행한다 (HTTP는 `sync.py`가 담당):

1. Stable Discovery URL을 GET, redirect를 허용한다.
2. 최종 URL을 `resolved_documentation_url`로 기록한다.
3. 응답 HTML에서 정규식 `r"window\.__DATA__\s*=\s*"`로 마커 위치를 찾는다. 정확한 문자열이 아니라 정규식을 쓰는 이유는 Atlassian 빌드가 공백만 바꿔도 깨지지 않게 하기 위해서다.
4. 마커를 찾지 못하면 extraction failure. **(v1.2: 명확화)** HTML 안에 `window.__DATA__` 할당이 **정확히 하나가 아니면**(0개 또는 2개 이상) 그 자체로 extraction failure다 — "첫 번째 매치를 쓴다" 같은 관용은 두지 않는다. 현재 관찰된 세 페이지 모두 정확히 하나이며, 페이지 구조가 예상과 달라졌을 때 조용히 일부 데이터만 쓰는 것보다 fail closed가 이 설계의 철학(§38)과 일치한다.
5. 마커 뒤 위치부터 `json.JSONDecoder().raw_decode(html[pos:])`로 첫 JSON value만 파싱한다. 뒤에 `;`나 `</script>` 같은 JS 문법이 이어져도 `raw_decode`는 유효한 JSON이 끝나는 지점에서 멈추므로 문제없다. **`eval`, `exec`, JS parser는 절대 사용하지 않는다.**
6. 파싱된 트리를 순회하며 OpenAPI 후보를 찾는다. **재귀 대신 스택 기반 iterative DFS**를 사용한다 — 예상보다 깊은 JSON nesting에서도 Python recursion limit 문제가 생기지 않는다.

   ```python
   def is_openapi_candidate(node) -> bool:
       return (
           isinstance(node, dict)
           and isinstance(node.get("openapi"), str)
           and isinstance(node.get("info"), dict)
           and isinstance(node.get("paths"), dict)
       )

   def find_openapi_candidates(data) -> list[dict]:
       stack = [data]
       found = []
       while stack:
           node = stack.pop()
           if isinstance(node, dict):
               if is_openapi_candidate(node):
                   found.append(node)
               stack.extend(node.values())
           elif isinstance(node, list):
               stack.extend(node)
       return found
   ```

   `paths`가 빈 object라는 이유만으로 후보에서 제외하지 않는다 — 문법적으로 반드시 잘못된 specification은 아니기 때문이다.

7. 후보 개수로 판정한다:
   - **0개** → `ExtractionError` (extraction failure)
   - **1개** → 성공, 이 dict를 OpenAPI spec으로 사용
   - **2개 이상** → `AmbiguousExtractionError` (extraction failure) — "첫 번째 후보를 그냥 사용" 같은 heuristic은 넣지 않는다. 현재는 소스당 후보가 하나뿐임을 실제 페이지로 확인했지만, 미래에 Atlassian이 한 페이지에 여러 spec을 넣게 되면 조용히 잘못된 것을 고르는 대신 명시적으로 실패한다.

## 9. Extractor 구현 원칙

Python 표준 라이브러리만 사용한다: `re`, `json`, `urllib.request`, `urllib.parse`. **`html.parser`는 필요 없다** (anchor를 찾지 않으므로). BeautifulSoup, Playwright, Selenium 등은 사용하지 않는다.

## 10. Extraction 실패 처리

OpenAPI 후보를 정확히 하나 얻지 못한 경우(마커 없음, JSON decode 실패, candidate 0개, candidate 2개 이상), 기존 cache가 있다면 삭제하지 않는다.

```text
Extraction Failure
       ↓
Keep Existing Cache
       ↓
WARN 출력, last_checked는 갱신하지 않음 (§17)
```

기존 cache가 없는 최초 실행이라면 해당 source synchronization은 실패 처리한다. 다른 source의 synchronization은 계속 진행한다.

## 11. Documentation URL은 상태가 아니다

`resolved_documentation_url`은 metadata에 기록하지만 authoritative configuration으로 사용하지 않는다. 다음 실행에서 이 값을 곧바로 재사용하지 않고, TTL이 만료되었다면 discovery부터 다시 수행한다. TTL이 유효하면 애초에 discovery 자체를 수행하지 않는다.

## 12. 전체 아키텍처

```text
                  Atlassian Official Docs
                           │
                           ▼
                   Stable Discovery URL
                           │
                           ▼
                  GET + redirect follow
                           │
                           ▼
                 Resolved Documentation HTML
                           │
                           ▼
                       Extractor
              (window.__DATA__ → raw_decode
               → iterative candidate search)
                           │
                           ▼
                  OpenAPI candidate (dict)
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
          Validate    Canonicalize   Version tag
                           │
                           ▼
                       SHA-256
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
          unchanged                  changed
              │                         │
       metadata update           atomic cache replace
                                        │
                                        ▼
                                 metadata update
```

의존성 방향은 다음으로 고정한다: `__main__ → sync → {extractor, storage}`. `extractor`는 HTTP를 모르고, `storage`는 Atlassian을 모르고, `sync`만 orchestration을 안다. 반대 방향 의존성(`extractor → sync`, `storage → extractor` 등)은 만들지 않는다.

## 13. 디렉터리 구조

```text
project/
├── tools/
│   └── atlassian_docs/
│       ├── __main__.py      # CLI만 담당, sync 로직 없음
│       ├── sources.py       # discovery_url 3개
│       ├── extractor.py     # 순수 함수: HTML → OpenAPI dict
│       ├── sync.py          # orchestration: TTL, HTTP, validation, hash, version, 실패 정책
│       └── storage.py       # cache/metadata read/write, atomic replace
│
├── tests/
│   ├── fixtures/
│   │   ├── jira-platform-minimal.html      # 정상: 최상위 근처 임베드
│   │   ├── confluence-nested-minimal.html  # 정상: "schema" 키 아래 중첩
│   │   ├── marker-whitespace-variant.html  # 정상: 마커 공백 변형
│   │   ├── missing-data.html               # 실패: 마커 없음
│   │   ├── malformed-data.html             # 실패: JSON decode 불가
│   │   ├── no-openapi.html                 # 실패: candidate 0개
│   │   └── multiple-openapi.html           # 실패: candidate 2개 이상
│   ├── test_extractor.py
│   ├── test_sync.py
│   └── live_smoke.py        # 실제 Atlassian 접근, 기본 unittest 실행에는 포함 안 함
│
├── .atlassian-docs/          # gitignore 대상, ephemeral cache (§30)
│   ├── jira-platform.json
│   ├── jira-software.json
│   ├── confluence.json
│   └── metadata.json
│
└── AGENTS.md
```

cache filename에는 version을 넣지 않는다 (`jira-platform-v3.json` 같은 형태는 금지).

## 14. Version-Agnostic Cache

AI Agent가 참조하는 경로는 API major version에 영향을 받지 않는다. `.atlassian-docs/jira-platform.json`은 오늘 v3를 담고 있어도, 미래에 v4로 바뀌어도 항상 같은 경로다. Agent instruction은 변경할 필요가 없으며, 필요하면 `metadata.json`의 `api_version`을 확인한다.

## 15. API Version Detection (v1.2: 대폭 수정)

**v1.1/중간안에서 폐기한 방식:** OpenAPI `info.version`을 신뢰하거나, `paths`의 키를 스캔해서 버전 패턴을 추론하는 방식은 **사용하지 않는다**. Jira Software가 반례다 — 하나의 spec 안에 `/rest/agile/1.0/...`와 `/rest/*/0.1/...`처럼 서로 다른 버전 네임스페이스가 공존하므로, 이를 스캔해서 하나의 전역 `api_version`을 만들면 의미가 틀린 값을 자신 있게 기록하게 된다. 또한 `info.version`은 `"1001.0.0-SNAPSHOT-..."` 같은 빌드 문자열일 뿐 API major version이 아니다.

**최종 규칙:**

```text
resolved_documentation_url
        │
        ▼
  명시적 version segment 존재? (예: /rest/v3/, /rest/v2/)
        │
   ┌────┴────┐
  YES        NO
   │          │
   ▼          ▼
api_version  api_version
 = "v3"       = null
api_version_  api_version_
source =      source =
"documentation_url"  null
```

- `api_version == null`은 오류가 아니다. Sync는 정상적으로 성공한다 (Jira Software가 이 경우에 해당).
- OpenAPI 자체의 `info.version`은 필요하면 별도의 비authoritative 필드 `spec_info_version`으로만 기록한다. `api_version`과 `spec_info_version`을 같은 의미로 취급하지 않는다.
- Version detection 실패(=`null`)는 synchronization 실패 사유가 아니다. 핵심 조건은 버전 문자열이 아니라 OpenAPI specification이 정상인지 여부다.

**(v1.2: 추출 규칙 명확화)** 구현자가 서로 다르게 해석하지 않도록 추출 위치를 못 박는다:

- `api_version`은 `resolved_documentation_url`의 **URL path**에서만 추출한다. 전체 URL 문자열, `info.version`, `paths` 키, query string, HTML body 내용에서는 절대 추론하지 않는다.
- 추출 정규식은 `urllib.parse.urlparse(resolved_url).path`에 대해 `r"/rest/(v\d+)(?:/|$)"`를 적용한다.
  - `.../rest/v3/` → `"v3"`
  - `.../rest/v2/` → `"v2"`
  - `.../rest/` → `null`

## 16. Major Version Change Detection

이전 metadata의 `api_version`과 새 `api_version`이 **둘 다 non-null이고** 서로 다를 경우에만 major version 변경으로 표시한다 (`null → "v3"`처럼 처음 식별되는 경우는 변경 알림이 아니다).

```text
[VERSION] jira-platform: v3 -> v4
[UPDATED] jira-platform
```

major version 변경이라고 자동 update를 막지 않는다 — 이 시스템의 목적은 "latest official API reference" 유지이기 때문이다. 다만 일반적인 schema 변경보다 눈에 띄게 출력한다.

## 17. Cache 정책과 `last_checked` 시맨틱 (v1.2: 명문화)

기본 TTL은 24시간이다.

```text
refresh 실행 → metadata 확인 → now - last_checked < 24h ?
   YES → local cache 사용, network 접근 없음
   NO  → extraction부터 다시 수행
```

**`last_checked`의 의미를 정확히 고정한다:**

> `last_checked` = 마지막으로 **fetch + extraction + validation까지 전부 성공한** 시각.

다음 실패 케이스에서는 `last_checked`를 **갱신하지 않는다**: HTTP 실패, marker 없음, JSON decode 실패, candidate 0개, candidate 2개 이상, OpenAPI validation 실패. 이렇게 해야 실패한 확인 때문에 다음 24시간 동안 재시도가 봉쇄되는 문제를 피할 수 있다 — 실패 다음 실행에서는 TTL과 무관하게 다시 시도한다.

## 18. Metadata 구조 (v1.2: `resolved_openapi_url` 제거)

```json
{
  "jira-platform": {
    "resolved_documentation_url": "https://developer.atlassian.com/cloud/jira/platform/rest/v3/",
    "extraction_method": "embedded_window_data",
    "api_version": "v3",
    "api_version_source": "documentation_url",
    "spec_info_version": "3",
    "last_checked": "2026-09-16T05:00:00Z",
    "last_updated": "2026-09-16T05:00:00Z",
    "sha256": "..."
  },
  "jira-software": {
    "resolved_documentation_url": "https://developer.atlassian.com/cloud/jira/software/rest/",
    "extraction_method": "embedded_window_data",
    "api_version": null,
    "api_version_source": null,
    "spec_info_version": "1001.0.0",
    "last_checked": "2026-09-16T05:00:00Z",
    "last_updated": "2026-09-01T11:12:00Z",
    "sha256": "..."
  }
}
```

`discovery_url`은 `sources.py`에 이미 있으므로 metadata에 중복 저장하지 않는다.

## 19. Metadata Field 정의

- **`resolved_documentation_url`** — 마지막 성공한 extraction 시 확인된 실제 REST documentation URL (redirect 이후 최종 URL).
- **`extraction_method`** — 현재는 항상 `"embedded_window_data"`. 미래에 다른 추출 방식이 추가되면 구분자로 쓴다.
- **`api_version`** — `resolved_documentation_url`의 명시적 version segment에서만 얻은 값 (§15). 없으면 `null`.
- **`api_version_source`** — `api_version`을 어디서 얻었는지. 현재는 `"documentation_url"` 또는 `null`.
- **`spec_info_version`** — OpenAPI `info.version` 원본 값. 진단용이며 `api_version`과 혼동하지 않는다.
- **`last_checked`** — 마지막으로 fetch+extraction+validation까지 **성공**한 시각 (§17).
- **`last_updated`** — 실제 cached specification의 SHA-256이 변경된 시각.
- **`sha256`** — OpenAPI dict를 canonical JSON으로 직렬화한 결과의 SHA-256. **절대 raw file bytes의 해시가 아니다** — 불변식은 §22 참고.

## 20. 전체 Update Algorithm

```text
START
  │
  ▼
Read metadata
  │
  ▼
Cache exists AND canonicalize(parse(cache)) 기준 SHA-256 == metadata.sha256 ?
  (raw file bytes가 아니라 JSON parse → validate → canonical 직렬화를 거친 값으로 비교, §22)
  │
  ├─ NO (mismatch 또는 cache 없음) ──► cache를 stale로 취급
  │                                     TTL 게이트를 건너뛰고 곧장 extraction 시도로 진행
  │                                     (아래 "GET stable discovery URL"로 직행, TTL 체크 생략)
  │                                     extraction까지 실패해도 cache가 valid JSON+OpenAPI라면
  │                                     fallback으로 계속 사용 가능 (mismatch ≠ corrupt, §22)
  │
  YES (cache와 metadata가 일치)
  │
  ▼
now - last_checked < TTL(24h) AND NOT --force ?
  │
  YES → cache 사용, 종료
  │
  NO
  │
  ▼
GET stable discovery URL, redirect 허용
  │
  ▼
window.__DATA__ 마커 탐색 (regex)
  │
  ├─ 없음 → Extraction Failure → cache 유지 (last_checked 갱신 안 함)
  ▼
JSONDecoder.raw_decode()
  │
  ├─ 실패 → Extraction Failure → cache 유지
  ▼
Iterative tree search → candidates
  │
  ├─ 0개 또는 2개 이상 → Extraction Failure → cache 유지
  ▼
candidate 1개 확보 (OpenAPI dict)
  │
  ▼
OpenAPI validation (§21)
  │
  ├─ 실패 → cache 유지
  ▼
canonical JSON 직렬화 → SHA-256 계산
  │
  ▼
Version detection (§15)
  │
  ▼
last_checked = now (성공했으므로 갱신)
  │
  ▼
Compare canonical SHA-256 with metadata.sha256
  │
  ├─ SAME → metadata만 갱신 (last_checked, resolved_documentation_url, api_version 등). cache 파일은 다시 쓰지 않음.
  │
  └─ DIFFERENT → atomic cache replace (§22) → last_updated = now → metadata 갱신
```

## 21. OpenAPI Validation

Extractor의 candidate 판정(§8)이 최소 검증을 겸한다: `dict`이고 `openapi`가 `str`, `info`가 `dict`, `paths`가 `dict`여야 후보로 인정된다. `paths`가 빈 object여도 무효로 취급하지 않는다. 이 조건을 만족하는 후보가 정확히 하나가 아니면 validation 실패로 간주하고 cache를 교체하지 않는다.

## 22. Atomic Update와 Cache/Metadata 불일치 복구 (v1.2: 신설)

새 specification을 기존 cache 위에 즉시 쓰지 않는다: `jira-platform.json.tmp`에 먼저 쓰고, JSON/OpenAPI validation과 SHA-256 계산을 마친 뒤 atomic rename한다. metadata도 동일한 `.tmp → rename` 방식으로 별도로 쓴다. **쓰기 순서는 항상 cache 먼저, metadata 나중이다** — 이 순서라야 "cache=NEW, metadata=OLD" 상태만 발생할 수 있고, 이는 아래 복구 규칙으로 정상 회복된다. 반대 순서(metadata 먼저)를 쓰면 "metadata=NEW, cache=OLD"라는, sha256만으로는 구분할 수 없는 위험한 상태가 생길 수 있으므로 금지한다.

**주의:** cache 파일과 metadata 파일은 **두 개의 독립된 atomic write**이지 하나의 트랜잭션이 아니다. 따라서 "새 cache 저장 성공 → 프로세스 강제 종료 → metadata 쓰기 실패"가 발생하면 `실제 cache의 sha256 != metadata.sha256` 상태가 될 수 있다.

**`sha256`의 의미는 하나로 고정한다 (v1.2: 필수 불변식):**

> `metadata.sha256`은 **항상** "OpenAPI dict를 canonical JSON으로 직렬화한 결과"의 SHA-256이다 (§21의 `json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` 기준). Remote에서 새로 추출했을 때든, 로컬 cache를 검증할 때든 **동일한 canonicalization 함수**를 거친 값끼리만 비교한다. **cache 파일의 raw bytes를 직접 해싱한 값과는 절대 비교하지 않는다** — cache를 pretty-print로 저장하든 compact로 저장하든 canonical 표현이 같으면 같은 해시가 나와야 하기 때문이다.

**복구 규칙:** 매 실행 시작 시 다음 순서로 local cache의 실제 해시를 구해 metadata의 `sha256`과 비교한다: `cache 파일 읽기 → JSON parse → OpenAPI validation(§21) → canonical JSON 직렬화 → SHA-256`.

- 다르면 cache를 **stale**로 취급하고 extraction을 시도한다 (TTL과 무관하게).
- extraction까지 실패했는데 로컬 cache 자체는 (위 파이프라인을 통과하는) valid JSON + valid OpenAPI 구조라면, 그 cache를 fallback으로 계속 사용해도 된다.
- **mismatch ≠ corrupt**다 — sha256이 다르다고 cache를 삭제하거나 사용을 거부하지 않는다.

별도의 transaction 파일이나 lock DB는 두지 않는다. 여러 프로세스가 동시에 이 CLI를 실행하는 상황(concurrent execution / file locking)은 v1.2 범위 밖이다 — atomic replace가 파일이 반쪽짜리가 되는 것은 막아 주므로, 실제 필요성이 확인되면 이후 버전에서 다룬다.

## 23. Failure Policy

> 새 문서를 가져오지 못했다고 해서 마지막 정상 cache를 버리지 않는다.

실패 가능 지점: discovery HTTP 실패, redirect 문제, `window.__DATA__` 마커 미발견, JSON decode 실패, candidate 0개/2개 이상, OpenAPI validation 실패. 모든 경우 기존 정상 cache가 있다면 유지하고, 없다면 해당 source만 실패 처리하며 다른 source는 계속 진행한다.

## 24. CLI

```bash
python -m tools.atlassian_docs              # 기본 실행
python -m tools.atlassian_docs --force       # TTL 무시, extraction부터 재실행
python -m tools.atlassian_docs --status      # 캐시 상태 출력
```

`__main__.py`는 인터페이스만 담당한다:

```python
args = parse_args()
if args.status:
    show_status()
else:
    sync_all(force=args.force)
```

`--status` 출력 예:

```text
Jira Platform
  API version: v3
  Cached: yes
  Last checked: 2026-09-16 14:00
  Last updated: 2026-09-13 08:42

Jira Software
  API version: (unknown)
  Cached: yes
  Last checked: 2026-09-16 14:00
  Last updated: 2026-09-01 11:12
```

## 25. CLI 출력 정책

```text
[OK] jira-platform: cache valid (v3)
[UPDATED] confluence: specification changed
[VERSION] jira-platform: v3 -> v4
[UPDATED] jira-platform
[WARN] jira-software: OpenAPI extraction failed (0 candidates)
[WARN] jira-software: using existing cache
[ERROR] confluence: unable to extract OpenAPI specification (no existing cache)
```

## 26. CLI Exit Code (v1.2: 신설)

실패 정책(§23)은 무엇을 유지하고 무엇을 실패로 볼지 정의하지만, 그 결과를 CLI가 어떤 exit code로 알릴지는 정의하지 않았다. Claude Code 같은 agent가 이 도구를 호출할 때 exit code로 다음 작업을 판단해야 하므로 명확히 계약한다.

- **`exit 0`** — 모든 source가 사용 가능하다. TTL 이내라 cache를 그대로 썼거나, 시도한 remote refresh가 전부 성공했다.
- **`exit 1`** — degraded but usable. 하나 이상의 source에서 remote refresh가 실패했지만, 모든 source에 사용 가능한 fallback cache가 있다.
- **`exit 2`** — unavailable. 하나 이상의 source에 사용 가능한 cache 자체가 없다 (최초 실행에서 extraction 실패 등).

예: Jira Platform 성공, Jira Software 실패(기존 cache로 fallback), Confluence 성공 → `exit 1`. Jira Platform이 최초 실행인데 extraction 실패 → `exit 2` (다른 source가 전부 성공해도 하나라도 unavailable이면 2).

`--status`는 조회만 하므로 이 규칙과 무관하게 항상 `exit 0`이다 (파일을 읽을 수 없는 경우는 예외로 0이 아닌 코드를 반환해도 된다).

## 27. AI Agent 사용 방식

AI Agent는 `.atlassian-docs/` 내부 파일을 authoritative local API reference로 간주한다. Jira/Confluence 작업 전 `python -m tools.atlassian_docs`를 실행한 뒤 `jira-platform.json` / `jira-software.json` / `confluence.json`을 사용한다. 파일명에서 API version을 추측하지 않고, 필요하면 `metadata.json`의 `api_version`(null일 수 있음)을 확인한다.

## 28. Agent Instruction 예시

```text
## Atlassian APIs

Before implementing or modifying Jira or Confluence integrations, run:

    python -m tools.atlassian_docs

Use the OpenAPI specifications under .atlassian-docs/ as the primary
API reference. The cached files always represent the latest
successfully extracted official API specifications.

Do not assume API major versions from memory. Do not rely on
memorized Jira or Confluence endpoints when the local OpenAPI
specification provides the relevant information.

- jira-platform.json  → Jira Platform APIs
- jira-software.json  → Jira Software / Agile APIs
- confluence.json     → Confluence APIs

API versions may change over time without changing these local file
names. jira-software's api_version may legitimately be null/unknown —
this does not mean the cache is invalid.
```

## 29. Refresh 시점

별도의 background polling을 두지 않는다. AI Agent 작업 시작 시 `python -m tools.atlassian_docs`를 실행하고, TTL이 유효하면 cache를 그대로 사용하며, 만료되었으면 extraction을 수행한다.

## 30. Git 정책

`.atlassian-docs/`를 `.gitignore`에 포함한다 — cache는 ephemeral artifact다. repository에는 `tools/atlassian_docs/`와 `tests/`만 포함한다.

## 31. Dependencies

Python 표준 라이브러리만 사용한다: `urllib.request`, `urllib.parse`, `re`, `json`, `hashlib`, `pathlib`, `datetime`, `argparse`, `tempfile`, `os`, `dataclasses`, `unittest`, `unittest.mock`. **`html.parser`는 사용하지 않는다** (v1.1 대비 제거). `pip install` 없이 실행 가능한 것이 목표다.

테스트 프레임워크는 `unittest`(stdlib)를 기본으로 한다 — 본체가 zero runtime dependency인데 테스트 때문에 `pytest` 설치가 필요해지는 것은 원칙에 맞지 않는다. 이 도구가 이미 `pytest`를 표준으로 쓰는 상위 프로젝트에 편입되는 경우에만 예외적으로 `pytest`를 따른다.

## 32. 코드 규모

목표는 약 150~250 lines (extractor의 실패 케이스 처리와 iterative traversal이 추가되며 v1.1 목표치보다 다소 늘어남). 범위를 크게 넘어가면 구조를 재검토한다: source definitions, TTL, HTTP fetch, redirect, embedded JSON extraction, candidate search, JSON/OpenAPI validation, version detection, canonical hash, atomic replace, cache/metadata 불일치 복구, metadata, 기본 CLI.

## 33. 보안

공식 OpenAPI reference는 public resource를 대상으로 한다. 다음은 저장하지 않는다: Atlassian API Token, OAuth Access/Refresh Token, Account credential, Jira/Confluence user data, site-specific private content.

## 34. v1 구현 우선순위

**P0:** Stable discovery URL configuration, HTTP redirect follow, embedded JSON extractor (marker regex + raw_decode + iterative candidate search, 정확히 1개 assignment/1개 candidate 요구), 세 source 모두에 대한 extraction, local cache, 24h TTL, `last_checked` 성공시에만 갱신, metadata, canonical SHA-256 불변식(§22), version detection (URL path regex only, null 허용), 기존 cache fallback, atomic update(cache→metadata 순서), cache/metadata 불일치 복구, CLI exit code(§26).

**P1:** `--force`, `--status`, major version change 출력.

**P2:** source별 개별 refresh, configurable TTL, extraction 진단 로그.

## 35. Acceptance Criteria

- **AC-01** 최초 실행 시 `.atlassian-docs/` 디렉터리가 자동 생성된다.
- **AC-02** configuration(`sources.py`)에는 API version이 존재하지 않는다.
- **AC-03** configuration에는 direct OpenAPI CDN URL이 존재하지 않는다 (별도 URL 자체가 없음).
- **AC-04** 세 source 모두 stable discovery URL로부터 시작한다.
- **AC-05** Jira Platform의 문서 HTML에서 embedded OpenAPI spec을 extractor가 정확히 1개 추출한다.
- **AC-06** Jira Software의 문서 HTML에서 embedded OpenAPI spec을 extractor가 정확히 1개 추출한다.
- **AC-07** Confluence의 nested(`schema` 키 아래) embedded OpenAPI spec을 extractor가 정확히 1개 추출한다.
- **AC-08** `jira-platform.json` / `jira-software.json` / `confluence.json` cache가 생성된다.
- **AC-09** cache filename에는 API version이 포함되지 않는다.
- **AC-10** `metadata.json`에 `resolved_documentation_url`과 `extraction_method`를 기록한다 (`resolved_openapi_url`은 존재하지 않는다).
- **AC-11** 문서 URL에 명시적 version segment가 있으면 `api_version`을 기록하고, 없으면 `api_version: null`을 정상 상태로 기록한다 (예: jira-software).
- **AC-12** version detection 실패(`null`)여도 valid OpenAPI synchronization은 성공한다.
- **AC-13** 24시간 이내 재실행 시 network request 없이 cache를 사용한다.
- **AC-14** `--force` 사용 시 TTL을 무시하고 extraction부터 재실행한다.
- **AC-15** 추출된 spec의 canonical-JSON SHA-256이 동일하면 cache file을 다시 쓰지 않는다.
- **AC-16** canonical-JSON SHA-256이 변경되면 atomic replace가 수행된다.
- **AC-17** extraction 실패(마커 없음/decode 실패/candidate 0개) 시 기존 정상 cache를 유지한다.
- **AC-18** candidate가 2개 이상인 경우(ambiguous) 기존 정상 cache를 유지하고 첫 번째 후보를 임의로 선택하지 않는다.
- **AC-19** malformed JSON 응답이 기존 cache를 덮어쓰지 않는다.
- **AC-20** 이전 `api_version`과 새 `api_version`이 둘 다 non-null이고 서로 다른 경우 major version 변경을 출력한다.
- **AC-21** major version이 변경되더라도 local cache filename은 변경되지 않는다.
- **AC-22** 외부 Python package 없이 실행 가능하다 (`html.parser`도 사용하지 않음).
- **AC-23** 실패한 synchronization 시도는 `last_checked`를 갱신하지 않으며, 다음 실행에서 TTL과 무관하게 재시도된다.
- **AC-24** cache 파일을 `JSON parse → OpenAPI validation → canonical 직렬화 → SHA-256`한 값이 metadata의 `sha256`과 다르면 cache를 stale로 취급해 refresh를 시도하되, refresh도 실패하고 cache 자체는 (같은 파이프라인으로) valid하면 fallback으로 계속 사용한다. (v1.2: cache의 raw file bytes를 직접 해싱한 값과는 비교하지 않는다 — §22 불변식)
- **AC-25** `api_version`은 `resolved_documentation_url`의 URL path에서 `r"/rest/(v\d+)(?:/|$)"` 패턴으로만 추출한다. `info.version`, `paths` 키, query string에서는 추론하지 않는다.
- **AC-26** HTML 안에 `window.__DATA__` 할당이 정확히 하나가 아니면(0개 또는 2개 이상) extraction failure로 처리하며, 첫 번째 매치를 임의로 쓰지 않는다.
- **AC-27** CLI는 종료 시 `exit 0`(모든 source 사용 가능)/`exit 1`(하나 이상 degraded지만 전부 fallback으로 사용 가능)/`exit 2`(하나 이상 unavailable) 중 하나를 반환한다.
- **AC-28** cache와 metadata는 항상 cache를 먼저, metadata를 나중에 atomic replace한다 (반대 순서로 구현하지 않는다).

## 36. 예상 Major Version Migration

```text
현재: Stable URL → Jira Platform REST v3 → embedded OpenAPI v3 → jira-platform.json
향후: Stable URL → Jira Platform REST v4 → embedded OpenAPI v4 → jira-platform.json
```

변하지 않는 것: discovery URL, logical source ID, local cache filename, Agent instruction, CLI invocation, extractor 알고리즘(embedded JSON 위치가 바뀌지 않는 한).
변하는 것: `resolved_documentation_url`, `api_version`, OpenAPI 내용, SHA-256.

## 37. 확장 가능성

Phase 2 (Semantic Diff), Phase 3 (Atlassian Changelog 연동), Phase 4 (AI-friendly derived Markdown docs, OpenAPI 원본은 계속 authoritative), Phase 5 (Snapshot History) — 실제 필요성이 확인되면 추가한다. v1에서는 하지 않는다.

## 38. 핵심 설계 원칙

Official-first / Discovery-first / Version-agnostic / Stable interface / Cache-first / Fail-safe / Pull-on-demand / Minimal state / No infrastructure / **Thin extractor** (HTML 전체를 파싱하지 않고 embedded JSON에서 OpenAPI 후보를 찾는 데 필요한 최소한만 한다) / Expand only when necessary.

## 39. 최종 아키텍처

```text
sources.py ──(discovery_url ×3)──► sync.py
                                       │
                          GET + redirect follow
                                       │
                                       ▼
                            Documentation HTML
                                       │
                                       ▼
                                 extractor.py
                    (window.__DATA__ → raw_decode
                     → iterative candidate search)
                                       │
                                       ▼
                            OpenAPI dict (1 candidate)
                                       │
                    ┌──────────┬───────┴───────┬──────────┐
                    ▼          ▼               ▼          ▼
                validate   canonicalize   version tag   SHA-256
                                       │
                                       ▼
                                 storage.py
                                       │
                                       ▼
                              .atlassian-docs/
                    ├── jira-platform.json
                    ├── jira-software.json
                    ├── confluence.json
                    └── metadata.json
                                       │
                                       ▼
                              AI Coding Agent
```

## 40. v1.2 한 줄 정의

> `python -m tools.atlassian_docs`는 Atlassian의 version-independent 공식 REST 문서 진입점에서, 페이지에 인라인 임베드된 OpenAPI specification을 안전하게 추출하고, 버전 변화와 무관한 고정 경로에 실패-안전(fail-safe) 방식으로 캐싱하는 zero-infrastructure reference extractor다.
