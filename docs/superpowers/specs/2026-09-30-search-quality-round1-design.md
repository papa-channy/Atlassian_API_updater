# Search Quality Round 1 — Technical Specification

**문서 버전:** v1.1
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

### 0.2 실패 원인 분류 (실제 캐시 probe)

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
- 2026-09-30 외부 검수 1차(v1.0→v1.1): 관찰된 집합 전부 gate 제외, 해시 봉인(평문 repo 밖), clean-context 생성, 의미 검증, 자동 검사 가능한 작성 규칙, target 중복 허용, vocabulary 테스트 격하, scorer freeze 커밋, 경로 토큰 origin/forms 모델, 보수적 단수화, unigram 경로 토큰, 전체 합산 알고리즘·정렬 튜플·exact 점수 기준, 동사 단위 메서드 집합, loader 계약, product 이중 계산 명시, 튜닝 자유도 봉인(테이블 freeze·숫자 grid·튜닝 로그), alias는 R4만, competitor 픽스처, 진단에 git commit, AST 기반 AC-05, baseline 명시, fresh 평가 AC, end-to-end 점수 테스트, origin 카운팅 테스트, Round DoD와 gate 분리 — 전부 반영.

---

## 1. 목표

> 1차에서 관찰된 모든 평가 질의를 seed/regression으로 내리고, 실패 원인을 모르는 clean context가 만든 새 held_out/negative를 **해시로 봉인**(평문은 repo 밖)한 뒤, 구조 테이블을 먼저 freeze하고 어휘 스코어러에 메서드 의도·경로 특이도·제품 힌트를 정책 데이터로 더한 다음, scorer를 freeze한 커밋에서 봉인 집합을 **한 번만** 측정한다. 상수는 fingerprint되는 정책 데이터이고 점수는 신호별로 설명된다.

## 2. 범위

### 2.1 포함
1. 벤치마크 재편: 관찰된 held_out 12 + negative 8 → `seed`(정답 있는 것)와 `regression_negative`(negative였던 것). 새 `held_out` 16, 새 `negative` 8 생성·봉인.
2. `search_ranking.json` 정책 데이터와 로더, `POLICY_VERSIONS["search"] = 3`, tokenizer 보수적 단수화.
3. 세 구조 신호, 응답 `signals`.
4. alias/rule 보강(R4에 한함, 근거 기록).
5. 튜닝 절차(테이블 freeze, 숫자 grid, 튜닝 로그), scorer freeze 커밋, 봉인 해제·최종 평가 커밋.
6. 진단 스크립트 확장, 봉인/무결성 테스트, readiness 2차 행, Phase 2.5 스펙 보정 한 줄(§11.2 `oneOf→anyOf`).

### 2.2 제외
검색 로그 기반 처리(Runtime 축), OAS 3.1 검증, Phase 3 실행 계층, 소스 우선순위 규칙, BM25/IDF, description 가중치 변경.

## 3. 설계 원칙

1. **Promote before you tune.** 관찰된 질의는 전부 튜닝 집합으로 내린다. 봉인 커밋이 코드·데이터 변경 커밋보다 git 이력상 앞선다.
2. **Seal by hash, not by promise.** 봉인 집합의 평문은 repo 밖 컨트롤러 전용 경로에 있고, repo에는 canonical sha256·개수·분포만 커밋된다. 구현자는 평문을 볼 수 없다.
3. **Structure beats vocabulary.** R1–R3은 구조 신호로만 고친다. alias/rule은 R4로 분류된 seed 실패에만 허용된다.
4. **Every constant is policy data.** 가산/감산/cap/테이블은 `search_ranking.json`에만 있다.
5. **Freeze then measure once.** 구조 테이블은 구현 전에 freeze, scorer/정책은 최종 평가 전에 freeze 커밋. 봉인 집합은 그 커밋에서 한 번만 측정하고 결과와 무관하게 수정하지 않는다.
6. **Explainable scores.** 결과마다 `signals`.

## 4. 파일 구조

| 파일 | 변경 |
|---|---|
| `tests/benchmarks/search_queries.json` | `seed` 확장, `regression_negative` 신설, `held_out`/`negative`는 봉인 메타데이터만(§5.4) → 최종 평가 커밋에서 평문으로 교체 |
| `tests/benchmarks/evaluator.py` | 봉인 메타 레코드 인식(`sealed: true`인 집합은 평가 대상에서 제외하고 상태만 보고) |
| `tests/benchmarks/test_evaluator.py` | 봉인 해시 무결성, 중복 금지, policy vocabulary provenance, 테이블 freeze 테스트 |
| `tests/benchmarks/search-tuning-round1.jsonl` | 튜닝 실험 로그(§8.3) |
| `tools/atlassian_docs/intelligence/data/search_ranking.json` | 신규 |
| `tools/atlassian_docs/intelligence/data/search_aliases.json` | R4 alias/rule + `notes` |
| `tools/atlassian_docs/intelligence/policy.py` | `RankingPolicy`, `ranking()`, `load_ranking`, fingerprint 인자, `POLICY_VERSIONS["search"]=3` |
| `tools/atlassian_docs/intelligence/search.py` | `token_forms`, `PathToken`, `_structural_signals`, `_score`, 정렬, `signals` |
| `tests/intelligence/test_search.py`, `test_policy.py` | §10 |
| `tests/fixtures/openapi/make_openapi_fixtures.py` + 생성물 | seed 정답 + 과거 1위 competitor 경로 |
| `tests/diag_search_queries.py` | `--sets`, `--bench <path>`, git commit·fingerprint·sha 출력 |
| `tests/test_layering.py` | AST: ranking 상수가 production 코드에 없음(AC-05) |
| `docs/phase3-readiness.md` | 2차 행, 상태 모델(§11) |
| `docs/superpowers/specs/2026-09-29-phase2.5-discovery-hardening-design.md` | §6 참조 한 줄, §11.2 규칙 5 |
| `README.md`, `AGENTS.md` | `signals`, 제품 힌트 |

불변(baseline `d63a2ca`, AC-09에서 정확히 이 목록으로 `git diff`): `tools/atlassian_docs/{__main__,sources,extractor,sync,storage}.py`, `tools/atlassian_docs/intelligence/{models,normalizer,registry,schemas,gate,lastgood,provenance,quirks,request_template,request_check,oas_schema,headers,search_log,manager}.py`, `tools/atlassian_docs/intelligence/data/operation_quirks.json`, `tools/atlassian_docs/mcp/`.

## 5. 벤치마크 재편과 봉인

### 5.1 레코드 스키마 (Phase 2.5 §7.1 확장)
```json
{"id": "s-017", "query": "get project by key", "expected_top1_any": ["..."], "forbidden_top1": [],
 "origin": "held_out-r0", "failure_class": "R1", "ambiguous": false}
```
- `id`는 집합 접두(`s-`, `h-`, `n-`, `rn-`)+3자리, 불변. `origin`은 처음 들어온 집합과 라운드(`seed-r0`, `held_out-r0`, `negative-r0`, `held_out-r1`, …). `failure_class`는 seed 실패에만(§7 alias 허용 판정용). `ambiguous`는 정보 필드(평가기는 무시).

### 5.2 커밋 A — 관찰된 집합의 강등
- `held_out` 12건 전부 → `seed`(정답 키 유지). `negative` 8건 중 `update issue summary`는 정답이 명확하므로 `seed`(`expected_top1_any: ["jira-platform:PUT:/rest/api/3/issue/{issueIdOrKey}"]`), 나머지 7건 → `regression_negative`(`forbidden_top1` 유지).
- `delete an attachment`는 `ambiguous: true`, `expected_top1_any`에 Jira `DELETE /rest/api/3/attachment/{id}`와 Confluence `DELETE /attachments/{id}` 둘 다.
- 결과: `seed` 22건(9+12+1), `regression_negative` 7건, `held_out`/`negative` 비어 있음. 이 커밋에는 코드 변경이 없다.

### 5.3 새 집합 생성 (clean context)
- 생성기는 **이 스펙, 실패 목록, 현재 scorer/alias/ranking 정책을 모르는** 별도 컨텍스트여야 한다: 새 ChatGPT 대화(기존 스레드 금지) 또는 컨텍스트가 비어 있는 fresh subagent. 제공 정보는 (a) operation catalog — 각 op의 canonical key, method, summary, tags(실제 캐시에서 추출, description 제외), (b) 아래 작성 규칙뿐이다.
- 생성 프롬프트 전문과 생성 결과 파일의 sha256을 `docs/phase3-readiness.md` decision record에 남긴다.
- 작성 규칙(생성기 전달, 전부 자동 검사 가능):
  1. 영어 자연어 3–7 단어. operationId·경로 조각·canonical key 문자열을 그대로 쓰지 않는다(질의 토큰 집합이 어떤 op의 operationId 토큰 집합과 완전히 같으면 거부).
  2. held_out 16건: source 분포 jira-platform ≥ 6, jira-software ≥ 4, confluence ≥ 5. 메서드 분포 GET ≥ 4, POST ≥ 4, PUT ≥ 2, DELETE ≥ 2. 제품명(`jira`/`confluence`) 포함 ≥ 4, 미포함 ≥ 9.
  3. negative 8건: 동사 없는 명사 질의 또는 흔한 오답 유인(예 `issue type`)이 있는 질의. `forbidden_top1`은 그 오답 키 1개 이상, `expected_top1_any`는 비움.
  4. 중복 금지(자동): 정규화 토큰 집합(§6.1 `token_forms` 적용 전 unigram)이 기존 seed/regression 질의 어느 것과도 완전히 같지 않다. 문자열 완전 일치 금지.
  5. **target 중복 허용**: 같은 canonical key를 seed와 held_out이 가리켜도 된다. 금지되는 것은 질의 문자열/토큰 집합 재사용이며, held_out은 unseen phrasing을 평가한다.
  6. `expected_top1_any`는 실제 존재하는 canonical key. 모호할 때만 2개 이상, `ambiguous: true`.
- 의미 검증: 컨트롤러 또는 별도 reviewer(scorer를 실행하지 않는 컨텍스트)가 각 질의 ↔ expected op의 대응을 **summary/description 기준으로** 확인한다. 키 존재만 확인하는 것은 불충분하다. 부적합 항목은 생성기에 재요청하고 그 횟수를 기록한다. 검증 중 `search_operations`는 호출하지 않는다.

### 5.4 커밋 B — 해시 봉인
- 평문 파일 `round1-sealed.json`(held_out 16 + negative 8, §5.1 스키마)은 repo 밖 컨트롤러 전용 경로(`$ATLASSIAN_DOCS_SEALED_BENCH`, 기본 `~/.atlassian_api_updater/sealed/round1-sealed.json`)에 둔다. 구현·튜닝 서브에이전트에는 이 경로를 알리지 않으며 워크트리 안에 복사하지 않는다.
- `search_queries.json`의 `held_out`/`negative`에는 메타데이터만 커밋한다:
  ```json
  "held_out": {"sealed": true, "round": 1, "count": 16, "sha256": "<canonical sha256 of the held_out record list>",
               "distribution": {"source": {...}, "method": {...}, "product_named": 4}}
  ```
  negative도 동일. `sha256`은 Phase 2.5 §10과 같은 canonical JSON(`sort_keys`, `separators=(",",":")`, `ensure_ascii=False`)의 UTF-8 sha256이며, 레코드 리스트만 대상으로 한다.
- 평가기는 `sealed: true` 집합을 만나면 평가하지 않고 `{"sealed": true, "count": n}`을 보고한다. 진단 스크립트는 `--bench <path>`로 봉인 해제 파일을 주입받을 때만 이를 평가한다.

### 5.5 커밋 C — scorer/정책 freeze
- 구현·튜닝 완료 후 코드·데이터 변경이 더 없음을 선언하는 태그성 커밋(내용 변경은 없고, `docs/phase3-readiness.md`에 "Round 1 frozen at <sha>" 한 줄). 이 커밋 이후 최종 평가까지 `tools/`, `tests/fixtures`, `data/` 변경은 금지된다(AC-02).

### 5.6 커밋 D — 봉인 해제와 최종 평가
- 컨트롤러가 커밋 C 체크아웃에서 `python tests/diag_search_queries.py --bench <sealed path> --json <out>`를 **한 번** 실행한다.
- 평문 레코드를 `search_queries.json`의 `held_out`/`negative`에 그대로 넣고(메타데이터 교체), 테스트가 커밋 B의 sha256과 평문의 canonical sha256이 일치함을 확인한다(AC-03). 결과 JSON과 readiness 2차 행을 함께 커밋한다. 이 커밋 이후 `held_out`/`negative`는 관찰된 집합이 되어 다음 라운드에서 §5.2와 같이 강등된다.
- 결과가 gate 미달이어도 커밋 C를 수정하지 않는다. 재튜닝은 Round 2다.

### 5.7 게이트
- Discovery gate: 봉인 held_out 16건 중 ≥ 15(93.75%), 봉인 negative 8건 실패 0. `regression_negative` 7건은 보고만 하고 gate에서 제외(단, seed와 함께 튜닝 중 확인한다).
- Round 1 완료(DoD)와 gate 판정은 별개다(§11).

## 6. 순위 모델 (search 정책 버전 3)

### 6.1 토큰 형태 (`token_forms`, tokenizer 변경)
- `tokenize`의 복수형 변형 규칙을 보수적 규칙으로 교체하고, 같은 함수를 어휘 매칭·질의 확장·경로 특이도에서 **하나만** 쓴다.
  ```
  forms(t):  t 자체 ∪ singular(t)
  singular(t): len(t) ≤ 3 → t
               t.endswith("ies") → t[:-3] + "y"        # properties → property
               t.endswith(("sses","shes","ches","xes")) → t[:-2]   # classes → class
               t.endswith(("ss","us","is")) → t         # status, analysis
               t.endswith("s") → t[:-1]                 # issues → issue
  ```
- 고정 테스트: `properties→property`, `status→status`, `issues→issue`, `schemes→scheme`, `boards→board`, `process→process`, `classes→class`.
- 경로 특이도용 토큰은 **unigram만** 사용한다(joined form, alias, 조건 규칙 토큰 제외).

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
  "product_hint_bonus": 3.0,
  "tuning_grid": {
    "method_match_bonus": [1.0, 2.0, 3.0], "method_mismatch_penalty": [0.0, 1.0, 2.0, 3.0],
    "path_unmatched_penalty": [0.5, 1.0, 1.5, 2.0], "path_unmatched_cap": [2, 3, 4],
    "product_hint_bonus": [2.0, 3.0, 4.0]
  }
}
```
- **Loader 계약**(`load_ranking` → `RankingPolicy`, 위반은 모두 `ValueError`): `version` int ≥ 1; `verb_methods` 키는 `^[a-z]+$`, 값은 비어 있지 않은 리스트로 원소 ∈ {GET, POST, PUT, PATCH, DELETE}, 중복 금지; `method_match_bonus`·`method_mismatch_penalty`·`path_unmatched_penalty`·`product_hint_bonus`는 finite float ≥ 0; `path_unmatched_cap`은 int ≥ 0(bool 거부); `path_noise` 원소는 `^[a-z0-9]+$` 중복 금지; `product_hints` 키 `^[a-z]+$`, 값은 비어 있지 않고 중복 없는 리스트로 원소 ∈ `sources.SOURCES`; `tuning_grid` 키는 위 5개 숫자 필드의 부분집합, 각 값 리스트는 비어 있지 않고 현재 값을 포함; 미지 키 거부. 반환값은 frozen dataclass, 컬렉션은 `tuple`/`frozenset`/`MappingProxyType`. `ranking()`은 lru_cache, `sha256`은 canonical JSON.
- **테이블 freeze**: `verb_methods`, `path_noise`, `product_hints`, `tuning_grid`는 구현 시작 전 커밋(커밋 B 직후, 커밋 T)에서 확정되며 이후 변경 금지(§8.1, AC-13). 숫자 5개만 grid 안에서 튜닝한다.

### 6.3 메서드 의도
- 입력은 `QueryExpansion.base`(alias 확장 전)만. `verbs = base ∩ verb_methods.keys()`.
- `len(verbs) == 0` → 0. `len(verbs) ≥ 1`이면 `allowed = ∩ verb_methods[v] for v in verbs`; 교집합이 비면 충돌 → 0. 비지 않으면 `op.method ∈ allowed` → `+method_match_bonus`, 아니면 `−method_mismatch_penalty`.
- `signals.method_intent = {"value": float, "allowed": [sorted methods] | []}`.

### 6.4 경로 특이도
- 인덱스 빌드 시 op마다 `path_tokens: tuple[PathToken]`을 계산한다. `PathToken(origin: str, forms: frozenset[str])`. 경로를 `/`로 나눈 세그먼트 중 `{…}`가 아닌 것을 unigram `tokenize`(camelCase 분리, 소문자, 길이 ≥ 2, STOPWORDS 제외, **변형 미포함**)하여 origin 목록을 만들고, 숫자만인 origin과 `path_noise`에 있는 origin을 제거한 뒤 `forms = token_forms(origin)`을 붙인다. 같은 origin이 경로에 두 번 나와도 한 번만 센다.
  - 예: `/rest/api/3/issue/{issueIdOrKey}/properties` → `(PathToken("issue",{issue}), PathToken("properties",{properties, property}))`.
- 검색 시 `unmatched = [pt for pt in path_tokens if pt.forms ∩ exp.all == ∅]`. 여기서 `exp.all`은 base ∪ direct ∪ cond(각각 `token_forms` 적용 후).
- `penalty = min(len(unmatched), path_unmatched_cap) × path_unmatched_penalty`. **origin 하나당 최대 1회**만 센다(AC-14 테스트).
- `signals.path_unmatched = {"value": −penalty, "tokens": [sorted origins]}`.

### 6.5 제품 힌트
- `hinted = ∪ product_hints[t] for t in base if t in product_hints`. 비어 있으면 0. `op.source ∈ hinted` → `+product_hint_bonus`, 아니면 0.
- 힌트 토큰은 어휘 매칭에도 그대로 참여한다. **이중 계산은 의도된 정책**이다(tag/description에 `jira`가 있으면 lexical 점수와 bonus를 함께 받는다). 단위 테스트로 고정한다.
- `signals.product_hint = {"value": float, "sources": [sorted hinted]}`.

### 6.6 전체 알고리즘 (단일 정의)
```
for op in filtered_ops:                      # method/tag/source/include_deprecated 필터 (Phase 2 그대로)
    lexical = Σ_field weight × (|base∩f| + ad·|direct∩f| + rd·|cond∩f|)
    if lexical == 0: continue                # 후보 아님 — 구조 신호 미적용
    if bonus_tokens ⊆ matched_base: lexical += ALL_MATCH_BONUS
    structural = method_intent + path_unmatched + product_hint
    clamped = max(lexical + structural, 0.0)
    final = clamped × (DEPRECATED_FACTOR if op.deprecated else 1.0)
    if final == 0.0: continue                # 최종 0점은 결과에서 제외
    candidates.append(op, final, signals)
sort key: (final desc, deprecated asc [False first], key asc)
exact = exact_matches(query, filtered_ops)   # Phase 2.5 §5, 필터 적용 후
pinned score = (max final among non-exact candidates, or 0.0) + 1.0   # deprecated factor 재적용 없음
results = pinned (key asc) + candidates without pinned keys
```
- `bonus_tokens`는 Phase 2.5와 같이 alias 없는 `tokenize(query)`, `matched_base`는 base 토큰 중 어떤 필드에든 매칭된 것.
- 동점 정렬 튜플은 위 한 줄이 전부다.

### 6.7 응답 필드
- 각 결과 항목: `score`(= final 또는 pinned score), `signals`(§6.3–6.5; exact 항목은 `{"method_intent": {"value": 0.0, "allowed": []}, "path_unmatched": {"value": 0.0, "tokens": []}, "product_hint": {"value": 0.0, "sources": []}}`), `match`(exact 항목만).
- 최상위 `intelligence_policy`에 `ranking_sha256`. 기존 필드 제거 없음.

## 7. alias/rule 보강 (R4 전용)

- alias/rule 추가는 `failure_class == "R4"`로 표시된 seed 실패에만 허용된다. 각 항목의 `notes`에 `seed_query_id`와 `failure_class=R4`, 근거 operationId를 적는다. R1–R3로 분류된 실패는 구조 신호로만 해결한다(AC-12).
- 스키마: `search_aliases.json`에 최상위 `notes: {"<alias-word or rule-index>": {"seed_query_id": "s-0xx", "failure_class": "R4", "evidence": "operationId …"}}`.
- 현재 R4 후보(구현 중 seed 결과로 확정): `run jql query` → `{jql}`→`search, searchforissuesusingjql` 규칙 또는 `jql→search` alias; `change issue assignee` → `{issue, assignee}`→`assignissue`.
- 어휘 출처 테스트(§10.2 `policy_vocabulary_provenance`)는 단어의 출처를 검사할 뿐 봉인 증명이 아니다.

## 8. 튜닝 절차

### 8.1 자유도 봉인
- 커밋 T(구현 시작 전): `search_ranking.json`의 테이블(`verb_methods`, `path_noise`, `product_hints`, `tuning_grid`)과 초기 숫자를 커밋. 이후 테이블은 변경 금지 — 테스트가 커밋 T의 테이블 canonical sha256을 상수로 갖고 현재 파일과 비교한다(AC-13).
- 튜닝 가능: 숫자 5개(각자 `tuning_grid` 안의 값만) + R4 alias/rule.

### 8.2 측정
- seed 22건 + regression_negative 7건에만. `python tests/diag_search_queries.py --sets seed,regression_negative`. 픽스처 테스트(`TestSeedBenchmark`)도 seed 22/22, regression 7/7이어야 한다.

### 8.3 튜닝 로그
- 모든 실험은 `tests/benchmarks/search-tuning-round1.jsonl`에 한 줄씩: `{"run_at", "git_commit", "constants": {...5개}, "alias_sha256", "seed": "n/22", "regression_negative": "n/7", "note"}`. 최종 채택 조합을 마지막 줄에 `"adopted": true`로 표시하고 그 값을 §6.2에 반영한다.

## 9. 진단 스크립트

- 옵션: `--sets <comma list>`(기본: 봉인되지 않은 집합 전부), `--bench <path>`(봉인 해제 평문 파일; 지정 시 그 파일의 `held_out`/`negative`를 사용), `--json <out>`.
- 출력(콘솔 + JSON): 집합별 정답률, 실패 질의별 top-5(key, score, signals), `git_commit`(`git rev-parse HEAD`, 실패 시 null), `registry_fingerprint`, `intelligence_fingerprint`, `ranking_sha256`, `alias_sha256`, source별 spec sha256, `run_at`.
- 벤치마크 파일을 편집하지 않고 exit 0.

## 10. 테스트 전략

### 10.1 단위 (픽스처)
- tokenizer `token_forms` 고정 케이스(§6.1).
- 메서드 의도: 일치/불일치/동사 없음/충돌(교집합 공집합)/`move`가 PUT·POST 모두 허용.
- 경로 특이도: 하위 리소스 강등, cap, origin당 최대 1회(변형 여러 개여도 1), 복수형 원형 매칭 시 미매칭 아님, `path_noise`·숫자 제외, 중복 세그먼트 1회, unigram만.
- 제품 힌트: 가산, 무힌트 불변, 타 소스 op 잔존, 이중 계산 명시 테스트.
- 전체 합산 end-to-end: 합성 픽스처 한 벌로 `lexical → all-match → structural → clamp → deprecated → exact pin`을 **숫자로** 고정. 음수 subtotal→clamp 0→결과 제외, deprecated factor, exact pin score(= max final + 1.0, factor 미재적용), 정렬 튜플(동점·deprecated·key) 각 최소 1케이스.
- `lexical == 0` op 결과 없음.
- Loader 계약(§6.2) 위반 케이스 전부 `ValueError`; 반환 불변.
- fingerprint: ranking 변경 민감, 안정, `POLICY_VERSIONS["search"] == 3`, `ranking_sha256` 노출.
- `signals` 형태(일반/exact).
- `TestSeedBenchmark`: seed 22/22, regression_negative 7/7. 픽스처 생성기에 정답 op와 **과거 1위 competitor op**(§0.1의 각 실제 1위)를 모두 포함.
- AST 테스트(AC-05): `search.py`에 `RankingPolicy` 밖의 가산/감산/cap 숫자 리터럴과 verb/hint/noise 테이블 리터럴이 없다.

### 10.2 벤치마크 무결성 (`tests/benchmarks/test_evaluator.py`)
- `sealed_hash_integrity`: 집합이 `sealed: true`이면 `count`·`sha256` 형식 검사; 평문이면 canonical sha256이 `docs/phase3-readiness.md` decision record의 커밋 B 해시와 같다(해시 상수는 커밋 B에서 테스트에 고정).
- `no_query_reuse`: 모든 집합 간 질의 문자열·정규화 토큰 집합 완전 일치 없음.
- `policy_vocabulary_provenance`: alias/rule 단어가 seed 질의 토큰 ∪ 캐시(또는 픽스처) operationId/경로 토큰에 있음. 봉인 증명이 아님을 docstring에 명시.
- `ranking_tables_frozen`: 테이블 canonical sha256 == 커밋 T 상수.
- `alias_notes_r4_only`: 모든 alias/rule에 `notes`가 있고 `failure_class == "R4"`, `seed_query_id`가 seed에 존재.

### 10.3 최종 평가
- 커밋 C 체크아웃에서 `--bench` 1회. 결과·해시 일치·readiness 행을 커밋 D로.

## 11. 상태 모델과 readiness 기록

- Round 1 DoD: AC-01..AC-16 충족 + 커밋 D 존재. gate 결과와 무관하게 "Round 1 completed".
- Discovery gate: `passed` / `failed` 를 별도로 기록. 실패 시 "Round 1 completed, gate failed → Round 2 필요". 이번 라운드에서 재튜닝 커밋은 없다.
- readiness 2차 행: 날짜, `git_commit`(커밋 C), registry/intelligence/validation fingerprint, `ranking_sha256`, `alias_sha256`, source별 sha, seed 22, regression_negative 7, sealed held_out 16, sealed negative 8 결과, gate 판정, 생성 프롬프트 sha256, 재요청 횟수, 커밋 A/T/B/C/D sha.

## 12. Acceptance Criteria

| ID | 기준 | 검증 |
|---|---|---|
| AC-01 | 커밋 A(강등), T(테이블 freeze), B(해시 봉인)가 `search.py`/`policy.py`/`search_ranking.json` 숫자/alias 변경 커밋보다 git 이력상 앞선다 | `git log` |
| AC-02 | 커밋 C 이후 커밋 D까지 `tools/`, `tests/fixtures/`, `intelligence/data/` 변경 없음 | `git diff C..D --stat` |
| AC-03 | 커밋 D의 held_out/negative 평문 canonical sha256 == 커밋 B 메타데이터 sha256 | 테스트 |
| AC-04 | 최종 gate 평가 집합의 모든 `id`가 `-r1` origin이고, r0 origin 질의는 하나도 없다 | 테스트 |
| AC-05 | 세 신호의 bonus/penalty/cap/테이블이 production Python에 없고 `RankingPolicy`에서만 공급된다 | AST 테스트 |
| AC-06 | seed 22/22 픽스처 + 실제 캐시, regression_negative 7/7 | 테스트 + 진단 |
| AC-07 | §10.1 신호별 테스트와 end-to-end 합산 테스트 통과 | 테스트 |
| AC-08 | `intelligence_fingerprint` ranking 민감, `POLICY_VERSIONS["search"]==3`, `signals`·`ranking_sha256` 노출 | 테스트 |
| AC-09 | `git diff d63a2ca -- <§4 불변 목록>` 비어 있음 | git diff |
| AC-10 | 진단 JSON에 `git_commit`, fingerprints, `ranking_sha256`, `alias_sha256`, spec sha, `run_at` | 실행 |
| AC-11 | 최종 평가는 커밋 C에서 1회 실행되고, gate 미달 시 재튜닝 커밋이 없다 | git log + readiness |
| AC-12 | 모든 alias/rule에 R4 `notes`; R1–R3 seed 실패에 대응하는 alias/rule 없음 | 테스트 + 리뷰 |
| AC-13 | 테이블 canonical sha256 == 커밋 T 상수; 숫자는 `tuning_grid` 안의 값 | 테스트 |
| AC-14 | 경로 origin 하나당 패널티 최대 1회 | 테스트 |
| AC-15 | 튜닝 로그가 존재하고 마지막 `adopted` 줄의 상수 == 현재 파일 | 테스트 |
| AC-16 | 전체 오프라인 테스트 통과, 새 의존성 없음, 생성 프롬프트 sha256과 재요청 횟수가 readiness에 기록 | unittest + 문서 |

## 13. 위험과 완화

- **seed 과적합**: 자유도는 grid 안의 숫자 5개 + R4 alias뿐(§8.1). held_out 봉인이 검출한다.
- **생성기 편향**: catalog summary만 보고 만든 질의가 summary 어휘에 치우칠 수 있다. 완화: 규칙 1(operationId 토큰 집합 일치 금지)과 reviewer의 의미 검증. 이 편향은 실사용 질의보다 쉬운 쪽이므로 gate가 관대해질 수 있음을 readiness에 명시한다.
- **`search` 동사 = GET**: Jira `POST /search/jql`도 정답이다. `expected_top1_any`에 둘 다 두고 어휘 점수로 경쟁시킨다. `verb_methods.search`를 바꾸는 것은 테이블 freeze 위반이므로 Round 2 항목이다.
- **컨트롤러 누수**: 컨트롤러는 평문을 보지만 코드를 쓰지 않는다. 컨트롤러가 구현자에게 전달하는 모든 브리프는 스펙·seed·regression만 참조한다(리뷰 체크리스트 항목).

## 14. 한 줄 정의

> 본 것은 전부 내리고, 새 것은 해시로 봉인하고, 테이블을 먼저 잠근 뒤 숫자만 격자 안에서 seed로 맞추고, 얼린 커밋에서 한 번만 잰다.
