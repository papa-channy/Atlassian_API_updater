# Search Quality Round 1 — Technical Specification

**문서 버전:** v1.0
**기준일:** 2026-09-30
**선행 구현:** Phase 2.5 Discovery Hardening (spec v1.2, `main` d63a2ca, 오프라인 테스트 328개)
**목적:** Phase 3 진입 조건의 Discovery 축(§18 of Phase 2.5 spec: 동결 held_out top-1 ≥ 90%, negative 실패 0)을 §7.3 승격 절차에 따라 **한 번의 iteration**으로 충족시킨다.
**설계 원칙:** Promote before you tune / Structure beats vocabulary / Every constant is policy data / Explainable scores / Held-out is sealed until the last run

---

## 0. 배경

### 0.1 1차 평가 결과 (2026-09-30, 실제 캐시, `tests/diag_search_queries.py`)

| 집합 | 결과 | 실패 질의 → 실제 1위 |
|---|---|---|
| seed | 7/9 | `update page content` → `PUT /pages/{page-id}/properties/{property-id}`; `get issue by key` → `GET /issue/{key}/properties` |
| held_out | 6/12 (오염 제외 4/12) | `change issue assignee` → `PUT /issuetypescheme/{id}`; `create a new confluence page in a space` → `GET /spaces/{id}/pages`; `run jql query` → `POST /jql/parse`; `add issue to sprint` → `GET /rest/software/1.0/sprint/{id}/issue`; `delete an attachment` → `confluence:DELETE:/attachments/{id}`; `get project by key` → `GET /projectvalidate/validProjectKey` |
| negative | 7/8 | `update issue summary` → `PUT /issuetypescheme/{id}` |

### 0.2 실패 원인 분류 (실제 캐시 probe)

| 원인 | 설명 | 해당 질의 |
|---|---|---|
| R1 하위 리소스 과잉 매칭 | 경로 토큰이 많은 하위 리소스가 기본 리소스와 같은 토큰을 모두 포함하고 추가 토큰으로 점수를 더 얻는다. 짧은 경로에 대한 보상이 없다. | get issue by key, update page content, get project by key, change issue assignee, update issue summary |
| R2 HTTP 메서드 의도 미사용 | 질의 동사(add/delete/create)가 op 메서드와 대조되지 않는다. | add issue to sprint, delete an attachment, create a new confluence page in a space |
| R3 제품 힌트 미사용 | `jira`/`confluence` 토큰이 source 선택에 영향이 없다. | delete an attachment(모호), create … confluence page |
| R4 개념 어휘 부족 | `jql`↔`search`, `assignee`↔`assignIssue` 같은 operationId 어휘와의 연결이 없다. | run jql query, change issue assignee |

### 0.3 오염 기록

Phase 2.5 계획 단계에서 추가된 alias `change→update`, `post→add`, `attach→attachment`는 held_out 질의에서만 쓰였다(§7.3.1 위반). 해당 held_out 3건(`attach a file to a jira ticket`, `post a comment on an issue`, `change issue assignee`)은 소진(consumed) 처리되어 이번 라운드에서 seed로 승격된다.

### 0.4 결정 이력

- 2026-09-30 사용자: 범위 = 순위 모델 + 데이터 + 승격; 새 held_out은 ChatGPT가 생성하고 컨트롤러는 키 존재만 검증; 접근안 A(구조 신호 3개 추가) 채택.

---

## 1. 목표

> 실패한 held_out/negative 질의를 seed로 승격하고 새 unseen held_out을 **코드 변경 전에** 봉인한 뒤, 어휘 스코어러에 메서드 의도·경로 특이도·제품 힌트 세 구조 신호를 정책 데이터로 추가하고 seed 어휘만으로 alias/rule을 보강하여, 봉인된 held_out에서 top-1 ≥ 90%, negative 실패 0을 달성한다. 상수는 전부 fingerprint되는 정책 데이터이고, 점수는 항목별 신호로 설명된다.

## 2. 범위

### 2.1 포함
1. 벤치마크 승격: 실패 held_out 6 + negative 1 + 소진 3 → seed (9 → 18, 중복 1건 제외). 새 held_out 12건, 새 negative 2건(8건 유지) 봉인.
2. `search_ranking.json` 정책 데이터와 로더, `POLICY_VERSIONS["search"] = 3`.
3. 스코어러에 세 구조 신호 추가, 응답에 `signals` 필드.
4. alias/rule 보강(seed 어휘 근거를 `notes`로 기록).
5. 진단 스크립트 `--sets`, `signals` 출력; 봉인 검증 테스트.
6. `docs/phase3-readiness.md` 2차 평가 행; Phase 2.5 스펙 §6·§11.2 참조/보정 한 줄.

### 2.2 제외
- 검색 로그 기반 실패 질의 처리(Runtime stability 축), OAS 3.1 검증, Phase 3 실행 계층, 소스 우선순위 규칙, BM25/IDF류 정규화, 설명문(description) 가중치 변경.

## 3. 설계 원칙

1. **Promote before you tune.** 승격 커밋과 새 held_out 커밋이 스코어러·데이터 변경보다 먼저 있어야 한다(git 이력으로 증명, AC-02).
2. **Structure beats vocabulary.** 실패 원인 R1–R3은 데이터가 아니라 구조 신호로 고친다. alias는 R4에만 쓴다.
3. **Every constant is policy data.** 가산/감산 값과 표는 `search_ranking.json`에 있고 sha256이 `intelligence_fingerprint`에 들어간다.
4. **Explainable scores.** 결과마다 `signals`로 세 신호의 기여를 보여 준다.
5. **Held-out is sealed.** 구현·튜닝 중 held_out/negative는 실행하지 않는다. 최종 1회만 진단 스크립트로 측정하고 결과와 관계없이 이번 라운드에서 다시 고치지 않는다.

## 4. 파일 구조

| 파일 | 변경 |
|---|---|
| `tests/benchmarks/search_queries.json` | 승격 + 새 held_out/negative (두 커밋, 코드 변경 전) |
| `tests/benchmarks/test_evaluator.py` | 봉인 검증 테스트 2개 추가 |
| `tools/atlassian_docs/intelligence/data/search_ranking.json` | 신규: 신호 상수·표 |
| `tools/atlassian_docs/intelligence/data/search_aliases.json` | alias/rule 보강 + `notes` |
| `tools/atlassian_docs/intelligence/policy.py` | `RankingPolicy`, `ranking()`, `load_ranking`, fingerprint 인자 추가, `POLICY_VERSIONS["search"]=3` |
| `tools/atlassian_docs/intelligence/search.py` | `_structural_signals`, `_score` 확장, `signals` 응답 |
| `tests/intelligence/test_search.py`, `test_policy.py` | 신호·로더·fingerprint 테스트 |
| `tests/fixtures/openapi/make_openapi_fixtures.py` + 생성물 | seed 19건 커버 경로 추가 |
| `tests/diag_search_queries.py` | `--sets`, `signals`/`ranking_sha256` 출력 |
| `docs/phase3-readiness.md` | 2차 평가 행 |
| `docs/superpowers/specs/2026-09-29-phase2.5-discovery-hardening-design.md` | §6 참조 한 줄, §11.2 `oneOf→anyOf` 규칙 5 추가 |
| `README.md`, `AGENTS.md` | `signals`, 제품 힌트 사용법 한 단락 |

불변: Phase 1 파일, Phase 2 동결 모듈(models, normalizer, registry, schemas, gate, lastgood, provenance), `quirks.py`, `request_*.py`, `oas_schema.py`, `manager.py`, `mcp/`.

## 5. 벤치마크 승격과 봉인 (§7.3 적용)

### 5.1 승격 커밋 (커밋 A)
- held_out에서 seed로: `change issue assignee`, `create a new confluence page in a space`, `run jql query`, `add issue to sprint`, `delete an attachment`, `get project by key`, 소진 3건 `attach a file to a jira ticket`, `post a comment on an issue`(`change issue assignee`는 위와 중복).
- negative에서 seed로: `update issue summary` → `expected_top1_any: ["jira-platform:PUT:/rest/api/3/issue/{issueIdOrKey}"]`, `forbidden_top1` 제거.
- `delete an attachment`는 모호 질의로 표기: `expected_top1_any`에 `jira-platform:DELETE:/rest/api/3/attachment/{id}`와 `confluence:DELETE:/attachments/{id}` 둘 다, 레코드에 `"ambiguous": true`. 이유: 어휘·메서드가 동일하고 제품 힌트가 없어 어느 쪽도 오답이 아니다. 평가기는 `ambiguous`를 무시한다(정보 필드).
- 결과: seed 18건(중복 제거), held_out 4건(통과분만 잔존), negative 7건.

### 5.2 새 held_out/negative 커밋 (커밋 B)
- ChatGPT 생성(작성 규칙은 §5.3), 컨트롤러는 각 `expected_top1_any` 키가 실제 캐시에 존재하는지만 `Registry.get_operation`으로 확인하고 **검색을 실행하지 않는다**.
- held_out에 12건 추가 → 16건. negative에 2건 추가 → 9건. (seed와 held_out 어느 쪽에도 없는 질의여야 한다.)
- 봉인 검증 테스트(§10.2)가 이 커밋에 함께 들어간다.

### 5.3 새 질의 작성 규칙 (ChatGPT에 전달)
1. 자연어 3–7단어, 영어. operationId나 경로 조각을 그대로 쓰지 않는다.
2. 제품 분포: jira-platform ≥ 5, jira-software ≥ 3, confluence ≥ 4.
3. 메서드 분포: GET/POST/PUT|DELETE 각 ≥ 3.
4. 기존 seed·held_out·negative 질의와 (동사, 명사) 조합이 겹치지 않는다. 제품명(`jira`, `confluence`)을 넣은 질의 ≥ 3, 넣지 않은 질의 ≥ 6.
5. `expected_top1_any`는 실제 존재하는 canonical key. 모호할 때만 2개 이상.
6. negative 2건: 동사 없이 명사만이거나 흔한 오답 유인(예: `issue type`)이 있는 질의, `forbidden_top1`은 그 오답 키.

### 5.4 게이트
새 held_out 16건 중 ≥ 15(93.75%)이면서 negative 9건 실패 0. 미달 시 §7.3.3에 따라 다음 라운드로 넘기고 이번 라운드에서 재튜닝하지 않는다.

## 6. 순위 모델 (search 정책 버전 3)

### 6.1 정책 데이터 `search_ranking.json`
```json
{
  "version": 1,
  "method_intent": {
    "GET":    ["get", "fetch", "read", "list", "find", "search", "show"],
    "POST":   ["create", "add", "post", "upload", "run", "submit", "assign"],
    "PUT":    ["update", "change", "edit", "set", "rename", "move", "transition"],
    "DELETE": ["delete", "remove"]
  },
  "method_intent_extra": {"PUT": ["POST"]},
  "method_match_bonus": 2.0,
  "method_mismatch_penalty": 2.0,
  "path_noise": ["rest", "api", "agile", "software", "wiki"],
  "path_unmatched_penalty": 1.0,
  "path_unmatched_cap": 3,
  "product_hints": {
    "jira": ["jira-platform", "jira-software"],
    "confluence": ["confluence"], "wiki": ["confluence"],
    "agile": ["jira-software"], "board": ["jira-software"], "sprint": ["jira-software"],
    "backlog": ["jira-software"], "epic": ["jira-software"]
  },
  "product_hint_bonus": 3.0
}
```
- 로더 검증: 모든 숫자는 `float(x) >= 0`; 메서드 키는 `{GET, POST, PUT, PATCH, DELETE}`; 소스 이름은 `sources.SOURCES` 안; 동사는 소문자 `[a-z]+`; 한 동사가 두 메서드에 들어가면 `ValueError`. 잘못된 형태는 모두 `ValueError`. `ranking()`은 lru_cache frozen dataclass `RankingPolicy(…, sha256)`; 반환 구조는 불변 타입(tuple/frozenset/Mapping proxy)이다.
- 값은 초기값이다. 튜닝 규칙은 §6.6.

### 6.2 메서드 의도
- 입력은 `QueryExpansion.base`(alias 확장 전)만. `intents = {m for m, verbs in method_intent.items() if base ∩ verbs}`.
- `len(intents) == 1`일 때만 적용. 허용 메서드 집합 = `{m} ∪ method_intent_extra.get(m, [])`. op.method ∈ 허용 → `+method_match_bonus`; 아니면 `−method_mismatch_penalty`.
- `len(intents) ∈ {0, ≥2}` → 0. `signals.method_intent`에는 적용값(+2.0/−2.0/0.0)과 판정 메서드(`"GET"`/`null`)를 기록한다.

### 6.3 경로 특이도
- 인덱스 빌드 시 op마다 `path_literal_tokens`를 계산: 경로를 `/`로 나눈 세그먼트 중 `{…}`가 아닌 것만 `tokenize`(복수형 변형 포함)하고, 숫자만인 토큰과 `path_noise`를 제거한다. 예: `/rest/api/3/issue/{issueIdOrKey}/properties` → `{issue, properties, propertie}`.
- 검색 시 `unmatched = {t ∈ path_literal_tokens : t ∉ exp.all ∧ singular(t) ∉ exp.all}` — 복수형 변형은 원형이 매칭되면 매칭된 것으로 본다(집합 정의: 변형이 아닌 원 토큰 기준으로 센다).
- `penalty = min(len(unmatched_origin_tokens), path_unmatched_cap) × path_unmatched_penalty`, 점수에서 감산. `signals.path_unmatched`에 `−penalty`와 미매칭 토큰 목록(정렬)을 기록한다.
- 점수가 음수가 되면 0으로 고정한다(결과에서 제외하지 않는다).

### 6.4 제품 힌트
- `hinted = ∪ product_hints[t] for t in base if t in product_hints`. 비어 있으면 0.
- `op.source ∈ hinted` → `+product_hint_bonus`; 아니면 0(감산 없음, 필터 아님). 힌트 토큰은 어휘 매칭에도 그대로 참여한다(`jira`가 tag/description에 있으면 그 점수도 붙는다).
- `signals.product_hint`에 적용값과 `hinted` 소스 목록을 기록한다.

### 6.5 합산 순서와 exact match
```
lexical = Σ weight × (|base∩f| + ad·|direct∩f| + rd·|cond∩f|)      # Phase 2.5 §6.3
lexical += ALL_MATCH_BONUS if applicable
structural = method_intent + path_unmatched + product_hint            # §6.2–6.4
score = max(lexical + structural, 0) × (DEPRECATED_FACTOR if deprecated else 1)
```
- `lexical == 0`인 op에는 구조 신호를 적용하지 않는다(후보가 아니다). 즉 어휘 매칭이 하나도 없는 op는 여전히 결과에 없다.
- exact match(§5 of 2.5)는 그대로 먼저 적용된다. 고정된 항목의 점수는 "필터된 (lexical+structural) 최대값 + 1"이다.
- 동점 정렬은 기존과 같이 canonical key 오름차순.

### 6.6 상수 튜닝 규칙
- 튜닝은 seed(18건)에만 한다. 진단 스크립트 `--sets seed`로 측정한다. held_out/negative는 구현 완료 후 최종 1회만 실행한다.
- 변경한 값은 `search_ranking.json`에만 있고, 최종값을 이 스펙 §6.1에 반영한다. 코드에 숫자를 두지 않는다.
- seed는 픽스처(오프라인)와 실제 캐시 양쪽에서 18/18이어야 한다.

### 6.7 응답 필드
- 각 결과 항목에 `signals: {"method_intent": {"value": float, "method": str|null}, "path_unmatched": {"value": float, "tokens": [..]}, "product_hint": {"value": float, "sources": [..]}}`. exact 고정 항목은 `signals`가 모두 0/빈 값이고 `match` 필드가 있다.
- 응답 최상위 `intelligence_policy`에 `ranking_sha256` 추가. 기존 필드 제거 없음.

## 7. alias/rule 보강

- 작성 근거는 seed 18건의 토큰과 실제 캐시의 operationId/경로 토큰뿐이다. 각 항목에 `notes`(근거 질의 또는 operationId 한 줄)를 둔다. 스키마: `aliases` 값은 그대로 문자열 배열, `notes`는 별도 최상위 객체 `{"<alias or rule-id>": "<근거>"}`.
- 후보(구현 중 seed 결과를 보고 확정): `jql → search` alias 또는 `{run, jql}`/`{jql, query}` → `searchforissuesusingjql, search` 규칙; `{issue, assignee}` → `assignissue`; `{project, key}` → `getproject`; `{add, sprint}` → `movetosprint`(실제 operationId 확인 후).
- 오염 방지: alias/rule에 등장하는 모든 단어는 §10.2 봉인 검증 테스트가 seed 토큰 ∪ 실제 캐시 토큰에 있음을 확인한다.

## 8. fingerprint

- `intelligence_fingerprint = sha256(registry_fp, aliases.sha256, overrides.sha256, ranking.sha256, POLICY_VERSIONS)` — canonical JSON, 기존 함수에 인자 추가(키워드 인자, 기본값 없음).
- `POLICY_VERSIONS["search"] = 3`. `validation_fingerprint`는 자동 반영.
- `get_api_status.intelligence_policy`에 `ranking_sha256` 추가.

## 9. 진단 스크립트

- `--sets seed[,held_out,negative]` (기본 전체). `--json`에 실패 질의별 top-5(key, score, signals)와 `ranking_sha256`, `alias_sha256` 포함.
- 스크립트는 벤치마크 파일을 편집하지 않고 exit 0.

## 10. 테스트 전략

### 10.1 단위 (픽스처)
- 메서드 의도: 일치 가산, 불일치 감산, 동사 없음/충돌 시 0, `PUT` 의도가 `POST` op를 허용.
- 경로 특이도: 하위 리소스가 기본 리소스 아래로 내려감; cap 적용; 복수형 원형 매칭이 미매칭으로 세지 않음; `path_noise` 제외.
- 제품 힌트: 힌트 있는 질의에서 소스 가산; 힌트 없는 질의는 점수 불변; 힌트가 있어도 다른 소스 op가 결과에서 사라지지 않음.
- `lexical == 0`인 op는 신호가 있어도 결과에 없음. 점수 하한 0. exact 고정 점수 규칙 유지.
- 로더: 잘못된 형태·중복 동사·미지 소스·음수 값 → `ValueError`; 반환값 불변.
- fingerprint: ranking 변경에 민감, 같은 입력에 안정. `POLICY_VERSIONS["search"] == 3`.
- `signals` 필드 형태와 exact 항목의 0 값.
- seed 18건 픽스처 통과(`TestSeedBenchmark`). 픽스처 생성기에 필요한 경로 추가·재생성(assignee, comment, search/jql, sprint/{id}/issue, project/{key}, attachment/{id}, spaces, attachments).

### 10.2 봉인 검증 (`tests/benchmarks/test_evaluator.py`)
- held_out/negative 질의 문자열이 seed에 없다.
- `search_aliases.json`·`search_ranking.json`의 모든 alias 단어·rule 토큰·동사·힌트 토큰이 seed 질의 토큰 ∪ (실제 캐시가 있으면) operationId/경로 토큰에 존재한다. 실제 캐시가 없으면 픽스처 토큰으로 대신하고 skip 사유를 남기지 않는다(픽스처만으로도 검사 가능한 부분은 검사).

### 10.3 최종 평가
- `python tests/diag_search_queries.py --json <out>` 실제 캐시 1회. 결과를 `docs/phase3-readiness.md` 2차 행에 기록.

## 11. Acceptance Criteria

| ID | 기준 | 검증 |
|---|---|---|
| AC-01 | 승격 커밋 A와 봉인 커밋 B가 스코어러·정책 데이터 변경 커밋보다 git 이력상 앞선다 | `git log` |
| AC-02 | 커밋 B 이후 held_out/negative 레코드는 최종 평가 커밋까지 변경되지 않는다 | `git log -p` |
| AC-03 | seed 18/18 픽스처 통과, 실제 캐시 18/18 | 테스트 + 진단 |
| AC-04 | 세 신호가 각각 §10.1 테스트로 검증된다 | 테스트 |
| AC-05 | 모든 상수가 `search_ranking.json`에 있고 코드에 숫자 리터럴이 없다(0과 1 제외) | grep + 리뷰 |
| AC-06 | `intelligence_fingerprint`가 ranking 변경에 민감하고 `POLICY_VERSIONS["search"]==3` | 테스트 |
| AC-07 | 결과 항목에 `signals`, `intelligence_policy.ranking_sha256` | 테스트 |
| AC-08 | 봉인 검증 테스트 2개 통과 | 테스트 |
| AC-09 | Phase 1·Phase 2 동결 모듈·2.5 모듈(§4 불변 목록) diff 없음 | git diff |
| AC-10 | 최종 진단 1회 결과가 readiness 2차 행에 fingerprint·sha·실행일과 함께 기록 | 문서 |
| AC-11 | 게이트(§5.4) 판정이 문서에 명시되고, 미달 시 재튜닝 커밋이 없다 | git log |
| AC-12 | 전체 오프라인 테스트 통과, 새 의존성 없음 | unittest |

## 12. 위험과 완화

- **seed 과적합**: 상수 3개와 alias 추가는 18건에 맞춰진다. 완화: 구조 신호는 원인(R1–R3)에 직접 대응하는 형태로 제한하고, held_out 봉인으로 검출한다.
- **메서드 의도 오판**: `search`가 GET 의도인데 Jira `POST /search/jql`도 정답. 완화: `expected_top1_any`에 둘 다 있고, `search` 동사는 GET에만 두되 POST 검색 op는 어휘 점수로 경쟁한다. 결과가 나쁘면 `method_intent_extra`에 `GET: [POST]`를 두지 않고 seed 단위로 판단한다.
- **제품 힌트 과보상**: `board`·`sprint`가 jira-software 힌트이면서 어휘이기도 하다. 완화: 가산만 있고 감산이 없어 다른 소스 정답이 사라지지 않는다.

## 13. 한 줄 정의

> 실패를 seed로 올리고 새 held_out을 먼저 봉인한 뒤, 메서드 의도·경로 특이도·제품 힌트를 정책 데이터로 더해 설명 가능한 점수로 순위를 매기고, 봉인된 집합에서 한 번만 판정한다.
