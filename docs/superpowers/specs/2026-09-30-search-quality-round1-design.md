# Search Quality Round 1 — Technical Specification

**문서 버전:** v1.3
**기준일:** 2026-09-30
**선행 구현:** Phase 2.5 Discovery Hardening (spec v1.2, `main` d63a2ca, 오프라인 테스트 328개)
**목적:** Phase 3 진입 조건의 Discovery 축(Phase 2.5 spec §18: held_out top-1 ≥ 90%, negative 실패 0)을 §7.3 승격 절차에 따라 **한 번의 iteration**으로, **독립적으로 증명 가능한** 방식으로 충족시킨다.
**설계 원칙:** Promote before you tune / Seal by hash, not by promise / Structure beats vocabulary / Every constant is policy data / Freeze then measure once / Explainable scores

---

## 0. 배경

### 0.1 1차 평가 결과 (2026-09-30, 실제 캐시, `tests/diag_search_queries.py`)

| 집합 | 결과 | 실패 질의 → 실제 1위 |
|---|---|---|
| seed | 7/9 | `update page content` → `PUT /pages/{page-id}/properties/{property-id}`; `get issue by key` → `GET /issue/{key}/properties` |
| held_out | 6/12 (오염 제외 4/12) | `change issue assignee` → `PUT /issuetypescheme/{id}`; `create a new confluence page in a space` → `GET /spaces/{id}/pages`; `run jql query` → `POST /jql/parse`; `add issue to sprint` → `GET /rest/software/1.0/sprint/{id}/issue`; `delete an attachment` → `confluence:DELETE:/attachments/{id}`; `get project by key` → `GET /projectvalidate/validProjectKey` |
| negative | 7/8 | `update issue summary` → `PUT /issuetypescheme/{id}` |

### 0.2 실패 원인 분류 (실제 캐시 probe; 한 질의가 여러 원인을 가질 수 있다)

| 원인 | 설명 | 해당 질의 |
|---|---|---|
| R1 하위 리소스 과잉 매칭 | 하위 리소스 경로가 기본 리소스와 같은 토큰을 모두 포함하고 추가 토큰으로 점수를 더 얻는다. | get issue by key, update page content, get project by key, change issue assignee, update issue summary |
| R2 HTTP 메서드 의도 미사용 | 질의 동사가 op 메서드와 대조되지 않는다. | add issue to sprint, delete an attachment, create a new confluence page in a space |
| R3 제품 힌트 미사용 | `jira`/`confluence` 토큰이 source 선택에 영향이 없다. | delete an attachment(모호), create … confluence page |
| R4 개념 어휘 부족 | `jql`↔`search`, `assignee`↔`assignIssue` 같은 operationId 어휘와의 연결이 없다. | run jql query, change issue assignee |

### 0.3 오염 기록

Phase 2.5 계획 단계에서 추가된 alias `change→update`, `post→add`, `attach→attachment`는 held_out 질의에서만 쓰였다(§7.3.1 위반). 더 근본적으로, 1차 평가에서 **모든** held_out/negative의 점수와 실패 원인 분석이 이미 관찰되었으므로, 기존 held_out/negative 전체가 더 이상 unseen이 아니다.

### 0.4 결정 이력

- 2026-09-30 사용자: 범위 = 순위 모델 + 데이터 + 승격; 새 held_out은 외부 생성기가 만들고 컨트롤러는 검색을 돌리지 않음; 접근안 A(구조 신호 3개) 채택.
- 2026-09-30 외부 검수 1차(v1.0→v1.1): 관찰된 집합 전부 gate 제외, 해시 봉인, clean-context 생성, 의미 검증, 자동 검사 규칙, target 중복 허용, vocabulary 테스트 격하, scorer freeze 커밋, PathToken 모델, 보수적 단수화, unigram 경로 토큰, 단일 합산 알고리즘, 동사 단위 메서드 집합, loader 계약, product 이중 계산 명시, 튜닝 자유도 봉인, alias는 R4만, competitor 픽스처, 진단에 git commit, AST AC, baseline 명시, fresh 평가 AC, end-to-end 점수 테스트, origin 카운팅 테스트, Round DoD와 gate 분리.
- 2026-09-30 외부 검수 2차(v1.1→v1.2): 커밋 순서 A→T→B→C→D 확정과 ancestor AC, OpenAPI/registry 스냅샷 봉인과 동일 스냅샷 평가, 평가기 코드 C에서 동결(`evaluation_code_sha256`), `ranking_structure_sha256`/`ranking_sha256` 분리, 단수화 예외 집합(`statuses`), `tokenize_unigrams`/`token_forms`/`expand_token_forms` 계약과 표현 고정, `failure_classes` 복수, grid 전수 평가와 결정적 선택 규칙, R4 alias 상한, `limit` 적용 위치, regression_negative 판정 정의, 규칙의 machine-check/reviewer-check 분리, 재요청 피드백 최소화, AC-04/11/15/16 자동 검증 범위와 attestation 분리, summary 연속 토큰 복사 금지 — 전부 반영.
- 2026-09-30 외부 검수 3차(v1.2→v1.3): AC-01을 구간 규칙(B..C에서만 가변 파일 변경)으로 재정의, `round1_seal` 최상위 영구 필드로 D에서 테스트 코드 무변경, joined token의 lexical 참여를 §6.6에 명시(구조 신호·all-match는 unigram만), alias `notes.origin`(phase2.5|round1)으로 AC-12 범위 한정, 스냅샷을 T 직후 생성하고 catalog도 그 스냅샷에서 추출, `evaluation_code_sha256` 알고리즘, 5-튜플 순서, ambiguous 분포 집계 기준 — 전부 반영. 검수자 판정: 이 4건 수정 시 구현 계획 진행 가능.

---

## 1. 목표

> 1차에서 관찰된 모든 평가 질의를 seed/regression으로 내리고, 구조 테이블을 먼저 잠근 뒤, 실패 원인을 모르는 clean context가 만든 새 held_out/negative를 **해시로 봉인**(평문과 당시 캐시 스냅샷은 repo 밖)하고, 어휘 스코어러에 메서드 의도·경로 특이도·제품 힌트를 정책 데이터로 더한 다음, 숫자만 격자 전수 평가로 결정적으로 고르고, scorer와 평가기를 얼린 커밋에서 봉인 집합을 **같은 스냅샷으로 한 번만** 측정한다.

## 2. 범위

### 2.1 포함
1. 벤치마크 재편: 관찰된 held_out 12 + negative 8 → `seed`/`regression_negative`. 새 `held_out` 16, 새 `negative` 8 생성·봉인.
2. `search_ranking.json`, 로더, `POLICY_VERSIONS["search"] = 3`, tokenizer 계약 3종과 보수적 단수화.
3. 세 구조 신호, 응답 `signals`.
4. alias/rule 보강(R4 전용, 상한 있음).
5. 커밋 A/T/B/C/D 절차, 스냅샷 봉인, grid 전수 튜닝 스크립트와 로그.
6. 진단 스크립트 확장, 무결성 테스트, readiness 2차 행, Phase 2.5 스펙 보정 한 줄(§11.2 `oneOf→anyOf`).

### 2.2 제외
검색 로그 기반 처리(Runtime 축), OAS 3.1 검증, Phase 3 실행 계층, 소스 우선순위 규칙, BM25/IDF, description 가중치 변경, 범용 영어 stemmer.

## 3. 설계 원칙

1. **Promote before you tune.** 관찰된 질의는 전부 튜닝 집합으로 내린다.
2. **Seal by hash, not by promise.** 봉인 집합의 평문과 그 시점의 캐시 스냅샷은 repo 밖에 있고, repo에는 canonical sha256·개수·분포·registry fingerprint·source별 spec sha만 있다.
3. **Structure beats vocabulary.** R1–R3은 구조 신호로만 고친다.
4. **Every constant is policy data.**
5. **Freeze then measure once.** 테이블(T) → scorer·정책·평가기(C) 순으로 얼리고, 봉인 집합은 C에서 B와 같은 스냅샷으로 한 번만 잰다.
6. **Explainable scores.**
7. **Automatic AC와 attestation을 구분한다.** repo만으로 증명 가능한 것은 테스트로, 아닌 것은 컨트롤러의 서명된 기록(readiness decision record)으로 남긴다.

## 4. 파일 구조

| 파일 | 변경 |
|---|---|
| `tests/benchmarks/search_queries.json` | `seed` 확장, `regression_negative` 신설, `held_out`/`negative` 봉인 메타데이터(§5.5) → 커밋 D에서 평문으로 교체 |
| `tests/benchmarks/evaluator.py` | 봉인 메타 인식, `regression_negative` 판정, 스키마 불변식 |
| `tests/benchmarks/test_evaluator.py` | §10.2 무결성 테스트 |
| `tests/benchmarks/search-tuning-round1.jsonl` | grid 전수 평가 로그(§8.3) |
| `tests/tune_search_ranking.py` | 신규: grid 전수 평가 + 결정적 선택 + 로그 기록(§8.2) |
| `tools/atlassian_docs/intelligence/data/search_ranking.json` | 신규 |
| `tools/atlassian_docs/intelligence/data/search_aliases.json` | R4 alias/rule + `notes` |
| `tools/atlassian_docs/intelligence/policy.py` | `RankingPolicy`, `ranking()`, `load_ranking`, `ranking_structure_sha256`, fingerprint 인자, `POLICY_VERSIONS["search"]=3` |
| `tools/atlassian_docs/intelligence/search.py` | `tokenize_unigrams`, `token_forms`, `expand_token_forms`, `PathToken`, `_structural_signals`, `_score`, 정렬·limit, `signals` |
| `tests/intelligence/test_search.py`, `test_policy.py` | §10.1 |
| `tests/fixtures/openapi/make_openapi_fixtures.py` + 생성물 | seed 정답 + competitor 경로 |
| `tests/diag_search_queries.py` | `--sets`, `--bench`, `--cache-dir`, 스냅샷 동일성 검사, provenance 출력 |
| `tests/test_layering.py` | AST(AC-05) |
| `docs/phase3-readiness.md` | 2차 행, decision record, attestation(§11) |
| `docs/superpowers/specs/2026-09-29-phase2.5-discovery-hardening-design.md` | §6 참조 한 줄, §11.2 규칙 5 |
| `README.md`, `AGENTS.md` | `signals`, 제품 힌트 |

불변(baseline `d63a2ca`, AC-09에서 정확히 이 목록으로 `git diff`): `tools/atlassian_docs/{__main__,sources,extractor,sync,storage}.py`, `tools/atlassian_docs/intelligence/{models,normalizer,registry,schemas,gate,lastgood,provenance,quirks,request_template,request_check,oas_schema,headers,search_log,manager}.py`, `tools/atlassian_docs/intelligence/data/operation_quirks.json`, `tools/atlassian_docs/mcp/`.

## 5. 벤치마크 재편과 봉인 (커밋 순서 A → T → B → C → D)

### 5.1 레코드 스키마 (Phase 2.5 §7.1 확장)
```json
{"id": "s-017", "query": "get project by key", "expected_top1_any": ["..."], "forbidden_top1": [],
 "origin": "held_out-r0", "failure_classes": ["R1"], "ambiguous": false}
```
- `id`: 집합 접두(`s-`, `h-`, `n-`, `rn-`)+3자리, 불변. `origin`: 처음 들어온 집합과 라운드(`seed-r0`, `held_out-r0`, `negative-r0`, `held_out-r1`, `negative-r1`). `failure_classes`: 1차 평가에서 실패한 seed에만, R1–R4의 부분집합(복수 허용; `change issue assignee`는 `["R1","R4"]`). `ambiguous`: 정보 필드.
- 스키마 불변식(evaluator가 검사): seed 레코드는 `expected_top1_any` 비어 있지 않음; `regression_negative`/`negative` 레코드는 `expected_top1_any == []`이고 `forbidden_top1` 비어 있지 않음.
- 판정: seed/held_out은 top-1 ∈ `expected_top1_any`이면 pass. `regression_negative`/`negative`는 top-1 ∉ `forbidden_top1`이면 pass(결과가 비어도 pass).

### 5.2 커밋 A — 관찰된 집합의 강등 (코드 변경 없음)
- `held_out` 12건 전부 → `seed`. `negative` 8건 중 `update issue summary` → `seed`(`expected_top1_any: ["jira-platform:PUT:/rest/api/3/issue/{issueIdOrKey}"]`), 나머지 7건 → `regression_negative`.
- `delete an attachment`: `ambiguous: true`, `expected_top1_any`에 Jira `DELETE /rest/api/3/attachment/{id}`와 Confluence `DELETE /attachments/{id}`.
- 결과: `seed` 22, `regression_negative` 7, `held_out`/`negative` 빈 리스트.

### 5.3 커밋 T — 구조 테이블 freeze (코드 변경 없음)
- `search_ranking.json`을 §6.2의 초기값으로 커밋. 이 커밋의 `ranking_structure_sha256`(§6.2)을 `tests/benchmarks/test_evaluator.py`의 상수로 함께 커밋한다. 이후 테이블 변경은 AC-13 위반이다.
- T가 B보다 앞서는 이유: hidden 집합을 만들기 전에 구조 테이블을 고정해, 테이블이 hidden 집합에 맞춰졌을 가능성을 원천 차단한다.
- **스냅샷 생성 시점은 T 직후**: 컨트롤러가 `.atlassian-docs/` 전체를 repo 밖 `$ATLASSIAN_DOCS_ROUND1_CACHE`(기본 `~/.atlassian_api_updater/round1-cache/`)로 복사하고, §5.4의 operation catalog는 **이 스냅샷에서** 추출한다. 생성·튜닝·최종 평가가 같은 universe를 쓴다.

### 5.4 새 집합 생성 (clean context)
- 생성기는 **이 스펙, 실패 목록, scorer/alias/ranking 정책을 모르는** 컨텍스트: 새 ChatGPT 대화(기존 스레드 금지) 또는 fresh subagent. 제공 정보는 (a) T 직후 스냅샷에서 추출한 operation catalog(canonical key, method, summary, tags; description 제외), (b) 아래 규칙뿐.
- 생성 프롬프트 전문과 결과 파일 sha256을 readiness decision record에 남긴다(attestation).
- **Machine-checkable 규칙**(§10.2 `hidden_set_rules` 테스트가 커밋 D에서 검사; 컨트롤러는 B 이전에 같은 함수를 평문에 대해 실행):
  1. 3–7 단어 영어. 질의 unigram 집합이 어떤 op의 operationId unigram 집합과 같으면 거부. 질의에 target op의 summary 또는 tags에서 **연속 content 토큰 2개 이상**(STOPWORDS 제외)을 그대로 복사한 구간이 있으면 거부.
  2. held_out 16: source 분포 jira-platform ≥ 6, jira-software ≥ 4, confluence ≥ 5. 메서드 분포 GET ≥ 4, POST ≥ 4, PUT ≥ 2, DELETE ≥ 2. 분포 집계는 레코드마다 `expected_top1_any[0]`의 source/method 기준(ambiguous 포함). 제품명(`jira`/`confluence`) 포함 ≥ 4, 미포함 ≥ 9.
  3. negative 8: `expected_top1_any == []`, `forbidden_top1` ≥ 1, 모든 키 실존.
  4. 중복 금지: 질의 문자열 또는 unigram 집합이 seed/regression 어느 것과도 같지 않다.
  5. 모든 expected/forbidden 키가 스냅샷 registry에 실존.
- **Reviewer-check 규칙**(컨트롤러 또는 별도 reviewer, scorer 미실행): 질의 ↔ expected op의 의미 대응(summary/description 기준), `ambiguous` 판정의 타당성, negative의 "유인 오답" 타당성, target 중복은 허용(같은 op에 대한 unseen phrasing은 정당한 테스트).
- 재요청: 거부 시 피드백은 "item N rejected; generate a replacement satisfying the original rules"만. 기존 질의·seed·점수·사유 상세를 전달하지 않는다. 재요청 횟수를 기록한다.

### 5.5 커밋 B — 해시·스냅샷 봉인
- 평문 `round1-sealed.json`(held_out 16 + negative 8)은 repo 밖 `$ATLASSIAN_DOCS_SEALED_BENCH`(기본 `~/.atlassian_api_updater/sealed/round1-sealed.json`)에. 스냅샷은 T 직후 만든 것을 그대로 쓴다(§5.3); 스냅샷은 비밀이 아니므로 구현·튜닝 서브에이전트에 그 경로를 알려도 된다. **봉인 평문 경로만** 알리지 않는다.
- `search_queries.json`의 `held_out`/`negative`:
  ```json
  "held_out": {"sealed": true, "round": 1, "count": 16, "sha256": "<canonical sha256 of record list>",
               "distribution": {"source": {...}, "method": {...}, "product_named": 4}}
  ```
  `negative`도 같은 형태이되 `distribution`은 `forbidden_top1[0]`(유인 오답)의 source/method 기준이다.
  최상위에 **영구 필드** `"round1_seal": {"held_out_sha256": "...", "negative_sha256": "...", "registry_fingerprint": "...", "spec_sha256": {"jira-platform": "...", "jira-software": "...", "confluence": "..."}}`를 둔다. 이 필드는 D 이후에도 남아 frozen evaluator가 평문의 canonical sha256과 비교하는 기준이 된다(테스트 코드에 상수를 넣지 않는다).
- canonical sha256: Phase 2.5 §10과 동일(`sort_keys`, `separators=(",",":")`, `ensure_ascii=False`, UTF-8), 레코드 리스트만 대상.
- 평가기는 `sealed: true`를 만나면 평가하지 않고 `{"sealed": true, "count": n}`을 보고한다.

### 5.6 구현·튜닝 (B 이후, C 이전)
- 코드·정책 숫자·R4 alias 변경은 전부 이 구간. seed/regression 측정은 **스냅샷**(`--cache-dir <round1-cache>`)에서 한다(§8.2). live 캐시 측정은 non-gating sanity로만 허용.

### 5.7 커밋 C — scorer·정책·평가기 freeze
- 내용 변경 없는 태그성 커밋. readiness에 "Round 1 frozen at <sha>"와 `evaluation_code_sha256`을 기록. 알고리즘: 네 파일(`tests/benchmarks/evaluator.py`, `tests/benchmarks/test_evaluator.py`, `tests/diag_search_queries.py`, `tests/tune_search_ranking.py`)을 경로 문자열 오름차순으로 정렬하고, 각 파일에 대해 `path.encode() + b"\0" + raw_bytes + b"\0"`를 이어 붙인 바이트열의 sha256 hex.
- C→D 사이 변경 허용 목록(whitelist): `tests/benchmarks/search_queries.json`(봉인 메타 → 평문 교체만), `docs/phase3-readiness.md`, `tests/benchmarks/round1-final.json`(결과). 그 외 파일 변경은 AC-02 위반.

### 5.8 커밋 D — 봉인 해제와 최종 평가
- 컨트롤러가 C 체크아웃에서 `python tests/diag_search_queries.py --bench <sealed> --cache-dir <round1-cache> --json tests/benchmarks/round1-final.json`을 실행. 스크립트는 시작 시 스냅샷의 registry fingerprint·spec sha가 `round1_seal`과 같은지 검사하고 다르면 평가하지 않고 exit 2.
- D에서는 `search_queries.json`의 `held_out`/`negative`만 평문 리스트로 교체한다(`round1_seal`은 그대로). **테스트 코드는 D에서 변경하지 않는다**(C에서 얼린 evaluator/테스트가 `round1_seal.*`과 계산 해시를 비교). 검사 항목: (a) 평문 canonical sha256 == `round1_seal.held_out_sha256`/`negative_sha256`, (b) `round1-final.json`의 `git_commit` == C, `evaluation_code_sha256` == C 기록값, `sealed_sha256` == `round1_seal` 값, `registry_fingerprint` == `round1_seal.registry_fingerprint`, (c) held_out/negative 모든 레코드 `origin`이 `held_out-r1`/`negative-r1`이고 r0 레코드 0개.
- gate 미달이어도 C를 수정하지 않는다. 재튜닝은 Round 2.
- "정확히 한 번 실행했다"는 repo로 증명할 수 없다. 자동 AC는 "커밋된 최종 결과 artifact가 정확히 하나이고 위 (b)를 만족"까지이고, 1회 실행은 컨트롤러 attestation(readiness decision record)으로 남긴다.

### 5.9 게이트
- Discovery gate: 봉인 held_out 16건 중 ≥ 15, 봉인 negative 8건 실패 0. `regression_negative`는 gate 제외(튜닝 중 7/7 요구).
- Round 1 DoD와 gate 판정은 별개(§11).

## 6. 순위 모델 (search 정책 버전 3)

### 6.1 토큰 계약 (세 함수, 한 가지 표현)
```
tokenize_unigrams(text) -> tuple[str, ...]
    camelCase 분리 → 소문자 → [^a-z0-9]+ 분할 → len ≥ 2, STOPWORDS 제외. 변형 없음, joined form 없음. 순서 유지, 중복 제거.
singular(t) -> str
    t in IRREGULAR → IRREGULAR[t]                      # {"statuses": "status"}  (실제 캐시 어휘에서 관찰된 것만)
    t in UNCHANGED → t                                 # {"series", "species", "news"}
    len(t) ≤ 3 → t
    t.endswith("ies") → t[:-3] + "y"                   # properties → property, queries → query
    t.endswith(("sses","shes","ches","xes")) → t[:-2]  # classes → class
    t.endswith(("ss","us","is")) → t                   # access, status, jsis
    t.endswith("s") → t[:-1]                           # issues → issue, databases → database
    else → t
token_forms(t) -> frozenset[str] = {t, singular(t)}
expand_token_forms(tokens) -> frozenset[str] = ∪ token_forms(t)
```
- 고정 테스트: `properties→property`, `queries→query`, `statuses→status`, `status→status`, `access→access`, `issues→issue`, `databases→database`, `schemes→scheme`, `boards→board`, `classes→class`, `series→series`, `news→news`.
- **표현 고정**: `QueryExpansion.base/direct/cond`는 **form-expanded** frozenset이다(`base = expand_token_forms(tokenize_unigrams(query))`, direct/cond도 alias/rule 토큰에 `expand_token_forms` 적용). 인덱스 필드 토큰도 form-expanded. 어휘 매칭은 form-expanded 집합끼리의 교집합 크기다(Phase 2.5와 같은 방식, 변형 규칙만 교체).
- all-match 판정: `bonus_tokens = tokenize_unigrams(query)`(raw). 조건은 `∀q ∈ bonus_tokens: token_forms(q) ∩ matched_base ≠ ∅`, 여기서 `matched_base`는 어떤 필드에서든 매칭된 base 토큰(form-expanded)의 합집합.
- joined form(Phase 2.5 §5의 `_query_tokens`, 예 `getissue`)은 `joined_query_forms(query) -> frozenset[str]`로 분리한다. **어휘 매칭에는 참여하고**(§6.6 `lexical_base`), 메서드 의도·경로 특이도·제품 힌트·all-match 판정에는 참여하지 않는다.

### 6.2 정책 데이터 `search_ranking.json`
```json
{
  "version": 1,
  "verb_methods": {
    "get": ["GET"], "fetch": ["GET"], "read": ["GET"], "list": ["GET"], "find": ["GET"], "search": ["GET"], "show": ["GET"],
    "create": ["POST"], "add": ["POST"], "post": ["POST"], "upload": ["POST"], "run": ["POST"], "submit": ["POST"], "assign": ["PUT"],
    "update": ["PUT"], "change": ["PUT"], "edit": ["PUT"], "set": ["PUT"], "rename": ["PUT"],
    "move": ["PUT", "POST"], "transition": ["PUT", "POST"],
    "delete": ["DELETE"], "remove": ["DELETE"]
  },
  "path_noise": ["rest", "api", "agile", "software", "wiki"],
  "product_hints": {
    "jira": ["jira-platform", "jira-software"],
    "confluence": ["confluence"], "wiki": ["confluence"],
    "agile": ["jira-software"], "board": ["jira-software"], "sprint": ["jira-software"],
    "backlog": ["jira-software"], "epic": ["jira-software"]
  },
  "tuning_grid": {
    "method_match_bonus": [1.0, 2.0, 3.0], "method_mismatch_penalty": [0.0, 1.0, 2.0, 3.0],
    "path_unmatched_penalty": [0.5, 1.0, 1.5, 2.0], "path_unmatched_cap": [2, 3, 4],
    "product_hint_bonus": [2.0, 3.0, 4.0]
  },
  "baseline": {
    "method_match_bonus": 2.0, "method_mismatch_penalty": 2.0,
    "path_unmatched_penalty": 1.0, "path_unmatched_cap": 3, "product_hint_bonus": 3.0
  },
  "constants": {
    "method_match_bonus": 2.0, "method_mismatch_penalty": 2.0,
    "path_unmatched_penalty": 1.0, "path_unmatched_cap": 3, "product_hint_bonus": 3.0
  }
}
```
- **두 해시**: `ranking_structure_sha256` = `{verb_methods, path_noise, product_hints, tuning_grid, baseline}`의 canonical sha256(커밋 T에서 freeze, AC-13). `baseline`은 §8.2의 "초기값"을 영구 고정한 것으로, 튜닝 중 `constants`가 바뀌어도 L1 거리 기준은 항상 `baseline`이다. `ranking_sha256` = 파일 전체(constants 포함)의 canonical sha256(fingerprint용).
- **Loader 계약**(`load_ranking` → `RankingPolicy`, 위반은 `ValueError`): `version` int ≥ 1; `verb_methods` 키 `^[a-z]+$`, 값 비어 있지 않은 리스트, 원소 ∈ {GET, POST, PUT, PATCH, DELETE}, 중복 금지; `path_noise` 원소 `^[a-z0-9]+$` 중복 금지; `product_hints` 키 `^[a-z]+$`, 값 비어 있지 않고 중복 없음, 원소 ∈ `sources.SOURCES`; `tuning_grid`·`baseline`·`constants` 키 집합이 모두 같은 5개, 각 값 리스트 비어 있지 않고 중복 없음; `constants`의 bonus/penalty는 finite float ≥ 0, `path_unmatched_cap`은 int ≥ 0(bool 거부), 각 값 ∈ 해당 grid; 미지 키 거부. 반환은 frozen dataclass(`tuple`/`frozenset`/`MappingProxyType`), `ranking()` lru_cache.

### 6.3 메서드 의도
- 입력 `verbs = tokenize_unigrams(query) ∩ verb_methods.keys()`(raw unigram 기준). `len(verbs)==0` → 0. `allowed = ∩ verb_methods[v]`; 공집합 → 0. `op.method ∈ allowed` → `+method_match_bonus`, 아니면 `−method_mismatch_penalty`.
- `signals.method_intent = {"value": float, "allowed": [sorted] | []}`.

### 6.4 경로 특이도
- 인덱스 빌드: `path_tokens: tuple[PathToken]`, `PathToken(origin: str, forms: frozenset[str])`. 경로의 `{…}`가 아닌 세그먼트를 `tokenize_unigrams`로 origin화 → 숫자만인 것과 `path_noise` 제거 → 중복 origin 제거(첫 등장만) → `forms = token_forms(origin)`.
  - 예: `/rest/api/3/issue/{issueIdOrKey}/properties` → `(("issue",{issue}), ("properties",{properties, property}))`.
- 검색: `unmatched = [pt for pt in path_tokens if pt.forms ∩ exp.all == ∅]`, `exp.all = base ∪ direct ∪ cond`.
- `penalty = min(len(unmatched), path_unmatched_cap) × path_unmatched_penalty`; origin당 최대 1회(AC-14).
- `signals.path_unmatched = {"value": −penalty, "tokens": [sorted origins]}`.

### 6.5 제품 힌트
- `hinted = ∪ product_hints[t] for t in tokenize_unigrams(query) if t in product_hints`. 비면 0. `op.source ∈ hinted` → `+product_hint_bonus`, 아니면 0.
- 힌트 토큰은 어휘 매칭에도 참여한다(**이중 계산 의도적**, 테스트로 고정).
- `signals.product_hint = {"value": float, "sources": [sorted]}`.

### 6.6 전체 알고리즘 (단일 정의)
```
filtered = [op for op in ops if passes(method, tag, source, include_deprecated)]   # Phase 2 필터
candidates = []
base = expand_token_forms(tokenize_unigrams(query))          # 구조 신호·all-match용 (unigram만)
lexical_base = base ∪ joined_query_forms(query)               # 어휘 매칭용 (Phase 2.5 동작 유지)
for op in filtered:
    lexical = Σ_field weight × (|lexical_base∩f| + ad·|direct∩f| + rd·|cond∩f|)
    if lexical == 0: continue
    if all_match(bonus_tokens, matched_base): lexical += ALL_MATCH_BONUS
    structural = method_intent + path_unmatched + product_hint
    clamped = max(lexical + structural, 0.0)
    final = clamped × (DEPRECATED_FACTOR if op.deprecated else 1.0)
    if final == 0.0: continue
    candidates.append((op, final, signals))
candidates.sort(key = (−final, op.deprecated, op.key))       # deprecated False 먼저, key 오름차순
pinned_ops = exact_matches(query, filtered)                   # Phase 2.5 §5, key 오름차순
pinned_score = (max(final of candidates whose op ∉ pinned_ops) if any else 0.0) + 1.0
results = [pinned entries (score = pinned_score, match set, signals all-zero)] + [c for c in candidates if c.op ∉ pinned_ops]
results = results[:limit]                                     # pinned도 limit 안에 포함; 초과 시 key 순 앞부터
exact_match = len(pinned_ops) > 0                             # limit로 잘려도 true
```

### 6.7 응답 필드
- 항목: `score`, `signals`, `match`(pinned만). exact 항목의 `signals`는 모두 0/빈 값.
- 최상위 `intelligence_policy`에 `ranking_sha256`, `ranking_structure_sha256`. 기존 필드 제거 없음.
- **fingerprint**: `intelligence_fingerprint = sha256(registry_fp \n aliases_sha256 \n overrides_sha256 \n ranking_sha256 \n POLICY_VERSIONS)`. 함수 **시그니처는 유지**(`intelligence_fingerprint(registry_fingerprint, aliases_sha256, overrides_sha256)`): `ranking().sha256`은 함수 내부에서 읽는다. 이유: 호출자 `request_template.py`, `request_check.py`, `mcp/tools.py`는 §4 불변 파일이고 도구 간 fingerprint 정의가 같아야 한다. `policy_block(aliases_sha256, overrides_sha256)`도 내부에서 `ranking_sha256`, `ranking_structure_sha256`을 추가한다. `POLICY_VERSIONS["search"] = 3`.

## 7. alias/rule 보강 (R4 전용, 상한 있음)

- 허용 조건: seed 레코드에 `"R4" ∈ failure_classes`이고, **구조 신호 적용 후에도** 그 질의가 실패한 상태일 것(튜닝 로그에 "추가 전 실패 → 추가 후 통과" 기록, §8.3).
- 상한: R4 seed 질의 하나당 direct alias 1개 **또는** conditional rule 1개. `notes`에 `seed_query_id`, `failure_classes`, `evidence`(operationId).
- 스키마: `search_aliases.json` 최상위 `notes: {"<alias-word | rule:<index>>": {"origin": "phase2.5" | "round1", "seed_query_id": null | "s-0xx", "failure_classes": [...], "evidence": "..."}}`. 기존 Phase 2.5 항목은 `origin: "phase2.5"`, `seed_query_id: null`, `failure_classes: []`, `evidence: "phase2.5 §6.1"`로 채우고 제거하지 않는다(grandfathered, regression 대상). Round 1에서 추가하는 항목은 `origin: "round1"`이며 §7의 허용 조건·상한을 적용받는다.
- `policy_vocabulary_provenance`(§10.2)는 단어 출처 검사일 뿐 봉인 증명이 아니다.

## 8. 튜닝 절차

### 8.1 자유도
- 테이블(`verb_methods`, `path_noise`, `product_hints`, `tuning_grid`, `baseline`)은 T에서 잠김. 튜닝 가능: `constants` 5개(각자 grid 안) + R4 alias/rule(§7 상한).

### 8.2 grid 전수 평가와 결정적 선택 (`tests/tune_search_ranking.py`)
- 스냅샷(`--cache-dir`)에서 grid의 모든 조합(초기 grid 기준 3×4×4×3×3 = 432)을 평가한다. 각 조합마다 seed 22건·regression 7건 pass 수를 계산한다.
- 선택 규칙(순서대로 tie-break, 결정적): (1) seed 22/22 AND regression 7/7인 조합만; (2) `baseline`(§6.2, 커밋 T에서 고정) 대비 L1 거리(각 축을 grid 인덱스 차이로) 최소; (3) `method_match_bonus + method_mismatch_penalty + path_unmatched_penalty + product_hint_bonus` 최소; (4) 5-튜플 `(method_match_bonus, method_mismatch_penalty, path_unmatched_penalty, path_unmatched_cap, product_hint_bonus)` 사전순 최소. (1)을 만족하는 조합이 없으면 seed pass 최대 → regression pass 최대 → (2)~(4)로 고르고 "seed 미달"을 로그에 남긴다(그 경우 §7의 R4 alias를 추가한 뒤 재실행).
- 스크립트는 선택된 조합을 `search_ranking.json`의 `constants`에 기록하고 로그를 남긴다. 사람이 숫자를 손으로 고르지 않는다.

### 8.3 튜닝 로그 `tests/benchmarks/search-tuning-round1.jsonl`
- 한 실행당 한 줄: `{"run_at", "git_commit", "registry_fingerprint", "alias_sha256", "ranking_structure_sha256", "grid_size", "passing_combos", "selected": {...5개}, "seed": "n/22", "regression_negative": "n/7", "adopted": bool, "note"}`. alias 변경 후 재실행은 `note`에 `alias:<word> for <seed_query_id> (before: fail, after: pass)`.
- 자동 AC(AC-15): `adopted: true`인 줄이 정확히 하나, 그 `selected` == 현재 `constants`, 모든 줄의 `selected`가 grid 안, `registry_fingerprint`가 `round1_seal.registry_fingerprint`와 같음. "모든 실험을 기록했다"는 attestation.

## 9. 진단 스크립트

- 옵션: `--sets <list>`(기본: 봉인되지 않은 집합 전부), `--bench <path>`(봉인 해제 평문; 지정 시 `held_out`/`negative`는 그 파일에서), `--cache-dir <dir>`(기본 `storage.CACHE_DIR`; 지정 시 `storage.CACHE_DIR`를 런타임에 그 경로로 패치 — Phase 1 코드는 수정하지 않음), `--json <out>`.
- 시작 시: 로드한 registry의 fingerprint와 source별 spec sha가 `search_queries.json`의 `round1_seal`과 같은지 검사. 다르면 `--sets`에 봉인 집합이 없을 때는 경고만, 있을 때는 exit 2.
- 출력: 집합별 정답률, 실패별 top-5(key, score, signals), `git_commit`, `registry_fingerprint`, `intelligence_fingerprint`, `ranking_sha256`, `ranking_structure_sha256`, `alias_sha256`, `evaluation_code_sha256`, `sealed_sha256`(`--bench` 시), source별 spec sha, `run_at`.
- 벤치마크 파일을 편집하지 않는다.

## 10. 테스트 전략

### 10.1 단위 (픽스처)
- 토큰 계약 3함수와 고정 케이스(§6.1); `QueryExpansion`이 form-expanded임; all-match 판정.
- 메서드 의도 5케이스; 경로 특이도(강등, cap, origin당 1회, 원형 매칭, noise·숫자 제외, 중복 세그먼트, unigram만); 제품 힌트(가산, 무힌트 불변, 타 소스 잔존, 이중 계산).
- end-to-end 합산: 합성 픽스처로 §6.6 전 단계를 **숫자**로 고정(음수→clamp→제외, deprecated, pinned score, 정렬 튜플, `limit`이 pinned를 자르는 경우, `exact_match` true 유지).
- `lexical == 0` 제외. Loader 계약 위반 전부 `ValueError`; 반환 불변; 두 해시 분리(constants 변경 시 `ranking_sha256`만 바뀜).
- fingerprint 민감/안정, `POLICY_VERSIONS["search"] == 3`, `signals` 형태.
- `TestSeedBenchmark`: seed 22/22, regression 7/7(픽스처). 픽스처 생성기에 정답 op와 §0.1의 각 실제 1위 competitor op 포함.
- AST(AC-05): `search.py`에 신호용 숫자 리터럴·테이블 리터럴 없음.

### 10.2 벤치마크 무결성 (`tests/benchmarks/test_evaluator.py`)
- `schema_invariants`: §5.1 불변식, `id` 유일·형식, `origin` 형식.
- `sealed_or_plain`: 봉인이면 `count`/`sha256` 형식이고 `sha256 == round1_seal.<set>_sha256`; 평문이면 canonical sha256 == `round1_seal.<set>_sha256`. 테스트 상수 없음.
- `no_query_reuse`: 문자열·unigram 집합 중복 없음(전 집합).
- `hidden_set_rules`: §5.4 machine-checkable 규칙(평문일 때만; 봉인 상태에서는 skip이 아니라 pass로 처리하고 이유를 출력).
- `policy_vocabulary_provenance`, `ranking_tables_frozen`(`ranking_structure_sha256` == T 상수), `constants_in_grid`, `alias_notes_r4_only`(`origin == "round1"` 항목만: `seed_query_id` 존재·seed에 실존, `"R4" ∈ failure_classes`, seed당 1개 상한; 모든 항목에 `notes` 존재), `tuning_log_adopted`(§8.3), `final_artifact`(D에서: 정확히 하나, `git_commit`/`evaluation_code_sha256`/`sealed_sha256` 일치, origin r1만).

### 10.3 최종 평가
- §5.8.

## 11. 상태 모델과 readiness 기록

- Round 1 DoD: AC-01..AC-16 자동 항목 통과 + attestation 항목 기록 + 커밋 D 존재. gate와 무관하게 "Round 1 completed".
- Discovery gate: `passed`/`failed`. 실패 시 "Round 1 completed, gate failed → Round 2".
- readiness 2차 행: 날짜, 커밋 A/T/B/C/D sha, `evaluation_code_sha256`, `round1_seal`(해시 2개, registry fingerprint, spec sha), fingerprints, `ranking_sha256`/`ranking_structure_sha256`/`alias_sha256`, seed 22·regression 7·held_out 16·negative 8 결과, gate 판정.
- Attestation(컨트롤러 서명 항목): 생성 프롬프트 sha256, 생성 결과 sha256, 재요청 횟수와 피드백 형식 준수, 최종 평가 1회 실행, 튜닝 로그 완전성, 서브에이전트에 봉인 경로 미노출.

## 12. Acceptance Criteria

자동(테스트/명령) 항목:

| ID | 기준 | 검증 |
|---|---|---|
| AC-01 | A < T < B < C < D (ancestor 관계 4회) **그리고** 가변 파일(`search.py`, `policy.py`, `search_aliases.json`, `search_ranking.json`의 `constants`)의 변경 커밋이 T..B와 C..D 구간에 없다(B..C 구간에서만 허용) | `git merge-base --is-ancestor` + `git log --name-only T..B`, `C..D` |
| AC-02 | C..D 변경 파일 ⊆ §5.7 whitelist | `git diff --name-only C D` |
| AC-03 | D의 held_out/negative canonical sha256 == `round1_seal.held_out_sha256`/`negative_sha256`; D는 테스트 코드를 변경하지 않음 | 테스트 + `git diff --name-only C D` |
| AC-04 | gate 집합 레코드의 `origin` ∈ {`held_out-r1`, `negative-r1`}, r0 레코드 0개 | 테스트 |
| AC-05 | 신호 상수·테이블이 `RankingPolicy` 밖 production Python에 없음 | AST 테스트 |
| AC-06 | seed 22/22(픽스처·스냅샷), regression 7/7 | 테스트 + 튜닝 로그 |
| AC-07 | §10.1 신호별·end-to-end 테스트 통과 | 테스트 |
| AC-08 | fingerprint 민감, `POLICY_VERSIONS["search"]==3`, `signals`·두 해시 노출 | 테스트 |
| AC-09 | `git diff d63a2ca -- <§4 불변 목록>` 비어 있음 | git diff |
| AC-10 | 최종 artifact에 §9 provenance 필드 전부 존재, `git_commit`==C, `evaluation_code_sha256`==C 기록, `sealed_sha256`==B, `registry_fingerprint`==`round1_seal.registry_fingerprint` | 테스트 |
| AC-11 | 커밋된 최종 artifact가 정확히 하나; D 이후 `search_ranking.json`/`search_aliases.json`/`search.py` 변경 커밋 없음(이 라운드 브랜치 내) | 테스트 + git log |
| AC-12 | 모든 alias/rule에 `notes`가 있고, `origin == "round1"`인 항목은 R4 seed 참조·seed당 1개 상한 준수 | 테스트 |
| AC-13 | `ranking_structure_sha256` == T 상수; `constants` ∈ grid | 테스트 |
| AC-14 | 경로 origin당 패널티 최대 1회 | 테스트 |
| AC-15 | 튜닝 로그 §8.3 자동 조건 | 테스트 |
| AC-16 | 전체 오프라인 테스트 통과, 새 의존성 없음 | unittest |

Attestation 항목(readiness decision record에 컨트롤러가 기록, 자동 검사는 필드 존재·sha 형식만): 생성 프롬프트/결과 sha256, 재요청 횟수, 최종 평가 1회 실행, 튜닝 로그 완전성, 봉인 경로 미노출.

## 13. 위험과 완화

- **seed 과적합**: 자유도는 grid 5개(전수 평가·결정적 선택) + R4 alias(상한). held_out 봉인이 검출.
- **생성기 편향(난이도)**: summary/tag 어휘로 만든 질의는 scorer 친화적일 수 있다. 완화: 연속 content 토큰 2개 복사 금지, reviewer 의미 검증. 남는 편향은 readiness에 명시.
- **`search` 동사 = GET**: Jira `POST /search/jql`도 정답. `expected_top1_any`에 둘 다. 테이블 변경은 Round 2.
- **upstream 변화**: 스냅샷 봉인으로 gate에서 분리. live 캐시 결과는 non-gating.
- **컨트롤러 누수**: 컨트롤러는 평문·스냅샷을 보지만 코드를 쓰지 않는다. 브리프는 스펙·seed·regression만 참조(리뷰 체크리스트).

## 14. 한 줄 정의

> 본 것은 전부 내리고, 테이블을 먼저 잠그고, 새 것은 캐시 스냅샷과 함께 해시로 봉인하고, 숫자는 격자 전수 평가로 기계가 고르고, 얼린 커밋에서 같은 스냅샷으로 한 번만 잰다.
