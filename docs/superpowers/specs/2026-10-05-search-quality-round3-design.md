# Search Quality Round 3 — Technical Specification

**문서 버전:** v1.8 (v1.0 = brainstorming 2026-10-05, 사용자 승인 섹션 1–6; v1.1 = 외부 검수 1차 반영: P0 8건·P1 6건 — 새 hidden set, abstention 계약과 대칭 게이트, S 재사용 조건, AC-R3-02 참조 고정, 동사 순서 동결, 제안기 원자 액션 계약, freeze 불변, 보수적 tie-break, 타깃 자원 증거; v1.2 = 외부 검수 2차 반영: P0 4건·P1 6건 — hidden actionability 분포·검사 계약, verb_methods prefix 불변, fixture negative raw 6/6, recommended_operation, resource_vocab 정규화, 참조 생성 격리, 게이트 결과 해시 체크포인트, 역할 분리; v1.3 = 외부 검수 3차 반영: P0 4건·P1 6건 — 규칙명 정합(actionable·negative-distribution만), held_out expected-method 정합, negative 섹션 교체 계약·수명주기, recommended_operation 빈 결과 정의, negative 프롬프트 문구, actionable negative 강도 규칙, legacy 어댑터 기본값, B 정책 문구, 참조 평문 수명주기, 게이트 체크포인트 바인딩; v1.4 = 외부 검수 4차 반영: P0 3건·P1 6건 — 버전 라벨, policy.py 허용 diff 계약, AC-R3-01 pre-T 체크포인트, negative-method 기계 규칙, 생성 입력에 VERB_METHODS 블록, 섹션 교체 상태기계, generator≠reviewer actor, AC-R3-07 삭제 요건, 네 필드, 격자 축소 pre-T 한정; v1.5 = 외부 검수 5차 반영: P0 2건·P1 5건 — AC-R3-01 pre-T 단일화, Round 2 AC 치환표, negative-method 요약 정합, method_order_bonus의 intent 정합, AC-R3-13 분리, 런타임 측정 절차, freeze 키 집합; v1.6 = 외부 검수 6차 반영: P0 2건·P1 5건 — freeze 키 집합에서 commit_T 제거, §8 chronology 정정, 검토자 역할 축소, held_out 테스트 3분기, POLICY_VERSIONS 명시, 섹션 위반 처리 순서, resource_vocab 보장 문구; v1.7 = 외부 검수 7차 반영: P0 1건·P1 4건 — policy.py 허용 diff 세 종류 전 문서 통일, AC-01a 기준 커밋 e16c073, 생성 프롬프트 규칙 요약 정합, tuning_grid_sha256 정의, AC 참조 번호; v1.8 = 외부 검수 8차 반영: P0 4건·P1 4건 — §2를 불변/제약된 변경/변경으로 3분, AC-01a/b·AC-07·AC-08·AC-09 치환, provenance 도메인 분리, synthetic lifecycle F/X, 격자 환경 의존 주석)
**기준일:** 2026-10-05
**선행 구현:** Round 2 (spec v1.14, 종료 커밋 F `770eb63`: 튜닝 실패, hidden set 미평가; `main` e16c073). 오프라인 테스트 476.
**상속:** 이 문서에 적지 않은 절차·AC·상태 모델은 **Round 2 스펙 v1.14를 그대로 상속**한다(§5 봉인 절차 전부 — S, pre-T 순서, §5.3 stateless 생성·검토 계약, §5.4 봉인, §5.5 one-way 파이프라인·두 단계 채택, §5.6 워커 계약, abort X; §8 alias_notes 스키마; §11 상태 모델; §12 AC 전부). 이 문서는 **델타**만 규정하며, 충돌 시 이 문서가 우선한다.
**목적:** Round 2가 증명한 구조적 실패 원인 4가지를 최소 변경으로 제거하고, **새로 생성한** 봉인 hidden set에서 Discovery 게이트(held_out ≥ 15/16, negative 0 실패)를 재시도한다.
**설계 원칙:** Fix the mechanism, not the words / Every new number is a grid constant whose baseline is 0 / Abstain in the product, not in the evaluator / Same seal, same gate / Nothing the design session saw is a gate

---

## 0. 배경 — Round 2 실패의 원인

Round 2(어휘 전용)의 one-way 파이프라인은 최선 지점에서 seed 34/39, regression negative 10/14, 통과 조합 0개로 끝났다(F). 미해결 seed 5건(s-024, s-027, s-028, s-032, s-036)은 전부 R6으로 분류됐지만 원인은 어휘 부족이 아니라 **어휘를 쓸 수 없게 만드는 구조**였다.

| # | 원인 | 증거 |
|---|---|---|
| 1 | 개념 토큰이 동사 인벤토리에 먹힘 | `comment`, `post`가 §6 동사라 `expected_vocab`에서 제거 → feedback→comment가 후보·사전 게이트 양쪽에서 불가 (s-024) |
| 2 | 개념 토큰이 product_hints에 먹힘 | `sprint`, `board`, `backlog`, `epic`이 hint 키라 타깃 불가 → s-032의 허용 타깃 ∅ |
| 3 | seed당 alias 예산 1 | s-027은 starred→favourite **와** searches→filter가 동시에 필요 |
| 4 | base 자원 vs 하위 자원, 메서드 동점 | s-028: `project` 토큰이 POST /project에 resource_match를 줌; s-036: POST /blogposts와 PUT /blogposts/{id} 동점(19) → 정렬 순서로 패배 |

negative 측: B 정책에서 이미 10/14였고, 깨진 4건(rn-010/011/012/014)은 모두 **동사 없는 명사 나열** 질의가 금지 op와 정확히 일치하는 경우다. 어휘·상수로는 14/14가 원천적으로 불가능했다.

사전 시뮬레이션(스코어러 임시 패치, 아카이브된 Round 2 S, B 상수, seed·regression·fixture만 사용 — hidden 미사용): 막혀 있던 alias 8개를 풀면 33/39, 동사 순서 tie-break 0.5 + path-coverage 1.0을 더하면 35/39, `method_mismatch_penalty` 5까지 넓히면 36/39, fixture 23/23·6/6 무손상. coverage 2.0 이상은 fixture와 s-029(정답이 더 얕은 경로)를 깨뜨린다. alias_damping 1.0은 손해. 명사 negative 4건은 raw top-1로는 어떤 변형에서도 통과하지 못했다(10/14).

**독립성 선언:** Round 2 hidden 평문은 2026-10-02/03 컨트롤러 세션이 추출 과정에서 보았고, 이 스펙은 그 세션에서 작성됐다. 따라서 Round 2 봉인 세트는 Round 3의 **게이트로 쓰지 않는다**(§4). Round 3 게이트는 T 이후 §5.3 stateless 계약으로 새로 생성한 세트다.

## 1. 목표

- Discovery 게이트: 새 봉인 세트에서 held_out ≥ 15/16, negative 0 실패(§4의 대칭 판정식).
- 튜닝 전 최종 조건: **T 직전 pre-T 체크포인트**에서 seed ≥ 36/39, fixture positive 23/23 · fixture negative **raw** 6/6, regression negative raw ≥ 10/14 · effective(abstention 포함) 14/14를 재현하고 **raw/effective를 분리 기록**(AC-R3-01). H 시뮬레이션은 비구속 sanity check다.
- 이 라운드의 결론은 "전체 자연어 검색 품질"이 아니라 **"actionable recommendation query의 Discovery 성능"**이다(readiness에 명시).

## 2. 범위

**변경:** `tools/atlassian_docs/intelligence/search.py`(신호 2개, `method_intent_consistent`/`actionable` 필드), `data/search_ranking.json`(상수 2개, 격자, 버전 2), `tests/benchmarks/alias_candidates_tool.py`(타깃 자격 규칙), `tests/tune_search_ranking.py`(예산 2 원자 액션 제안기, 새 상수, 보수적 tie-break, fixture 캐시), `tests/benchmarks/evaluator.py`(대칭 판정식), `tests/benchmarks/round_seal.py`(생성 프롬프트 `actionable`·`negative-method`·`negative-distribution` 규칙, 섹션 교체 계약, Round 2 참조 세트 등록), diag, MCP 응답 테스트, 스펙·계획·readiness.
**불변(byte-invariant):** Round 1·2 로그·freeze 항목·readiness 섹션·`round1-final.json`·`round2-*` 산출물; fixture 23/6(내용 불변, 하드 제약); Phase 1 파일; Phase 2 core 모듈 중 §3이 명시하지 않은 파일.
**제약된 변경:** `verb_methods`는 행 집합 동일 + 각 행의 Round 2 리스트가 exact prefix(§3.1, AC-R3-12; suffix는 T에 커밋); `search_ranking.json`의 구조 변경(새 상수 키 기준값 0, 최종 `tuning_grid`, `method_mismatch_penalty` 격자, 버전 2)은 **T에 커밋**하고 T 이후 구조 불변, B..C에서는 선택된 상수 값과 `origin=round3` alias/rule만 변경; `policy.py`의 H 변경 허용 범위는 ① `CONSTANT_KEYS`에 `method_order_bonus`, `path_coverage_bonus` 추가, ② alias_notes origin `round3`·`lexicon-r3` 허용(regex는 이미 일반형), ③ `POLICY_VERSIONS["search"]` 3→4(응답 스키마 변경)로 한정하고 그 외 스키마·검증 의미는 Round 2와 동일하다(AC-R3-13a: H의 `policy.py` diff가 이 세 종류에 한정됨을 테스트).
**해제:** Round 2의 "`search.py` 불변" 조항. `search.py` 변경은 H에서 끝나고 T에서 `evaluation_code_sha256_at_T`로 재동결된다.
**하지 않음:** alias_damping 변경, 어휘 규칙(`when_all`) 자동 제안, 지시어 신호, `verb_methods` 기존 메서드의 삭제·재배열, Round 2 봉인 세트의 게이트 사용.

## 3. 스코어러 변경 (`search.py`, 모두 `search_ranking.json` 상수)

### 3.1 `method_order_bonus`
질의 unigram 중 **첫 번째로 등장하는** 동사 인벤토리 토큰 `v`에 대해 `preferred := verb_methods[v][0]`; `preferred ∈ intent_methods`(§3.3의 교집합)이고 `entry.method == preferred`이면 `+method_order_bonus`, 그 외(동사 없음, 교집합 공집합, preferred가 교집합 밖)에는 0 — 최종 메서드 의도 밖의 메서드를 보상하지 않는다(다중 동사 fixture 단위 테스트 필수). 기존 `method_intent` 신호는 그대로 유지된다. 격자 `[0, 0.5, 1.0]`, **기준값 0**. signals에 `method_order: {"value", "verb", "preferred"}`. **Round 2 prefix 불변(AC-R3-12):** verb 행 집합은 Round 2 T 산출물(`structure_sha256 8106c891…`)과 동일하고, 각 verb의 Round 2 메서드 리스트는 Round 3 리스트의 **exact prefix**다. 기존 메서드의 삭제·재배열 금지; method-safety가 새 메서드를 요구하면 **suffix에만**, 둘 이상이면 메서드 이름 사전순으로 추가한다. 따라서 `verb_methods[v][0]`은 Round 2와 항상 같다.

### 3.2 `path_coverage_bonus`
`matched := sorted({pt.origin for pt in entry.path_tokens if pt.forms ∩ exp.all ≠ ∅})`(리터럴 경로 토큰의 origin 기준 고유 집합; `forms`는 기존 singular/plural 형태 집합, 노이즈는 `path_tokens` 생성 시 이미 제외), `m := len(matched)`에 대해 `+path_coverage_bonus × m`. 격자 `[0, 0.5, 1.0]`, **기준값 0**. signals에 `path_coverage: {"value", "matched"}`.

### 3.3 메서드 의도 일관성과 abstention 계약 (점수 무관)
`intent_methods` := 질의 unigram 중 동사 인벤토리 토큰들의 허용 메서드 **교집합**(동사 없음 → ∅). `method_intent_consistent := bool(intent_methods)`. **`actionable := method_intent_consistent`.** 응답 payload에 `method_intent_consistent: bool`, `intent_methods: [sorted]`, `actionable: bool`, **`recommended_operation`**(`actionable == true AND len(results) > 0`이면 `results[0].key`, 그 외 `null`)을 추가한다. 의미 구분: `actionable=true, recommended_operation=null` = 의도는 명확하나 후보 없음; `actionable=false, recommended_operation=null` = 제품 abstention. 테스트 4사분면(actionable±, results 유무). `actionable == false`일 때 결과 배열은 **후보 목록**이며 소비자는 `results[0]`을 추천으로 해석해서는 안 된다(MCP 도구 설명·README·응답 스키마 테스트로 고정; 결과 배열 자체는 변경 없음). 정렬·점수에는 영향이 없다. Phase 2 응답 테스트에 네 필드를 추가한다(provenance 블록 불변).

### 3.4 격자·기준값·선택기
`CONSTANT_KEYS`에 두 상수 추가(총 8), 기준값은 둘 다 0 → 새 두 신호의 기여는 기준값에서 정확히 0이며, 고정된 Round 2 B aliases/ranking/inventory를 입력으로 쓰면 스코어러 출력은 AC-R3-02와 같이 Round 2와 동일하다(Round 3의 실제 B 정책에는 `lexicon-r3`·후보·suffix 변경이 들어갈 수 있으므로 "Round 3 B == Round 2 B"를 뜻하지 않는다). `method_mismatch_penalty` 격자를 `[0,1,2,3,4,5]`로 확장. 격자 1728 × 9 × 2 = 31,104 지점. **선택기 tie-break(보수성):** seed·regression·fixture 결과가 동일한 지점들 사이에서는 `(path_coverage_bonus, method_order_bonus)`가 작은 쪽을 우선하고, 그다음 Round 2의 기존 tie-break(기준값과의 L1 거리, 사전순)를 적용한다. **fixture 하드 제약(raw):** fixture positive 23건은 top-1 기준 23/23, fixture negative 6건은 **legacy raw 판정** `top1 ∉ forbidden_top1` 기준 6/6. `actionable`/effective 값은 진단으로만 기록하며 raw 판정을 대체하지 않는다(fixture는 제품 의미가 아니라 스코어러 회귀 가드). **fixture 캐시:** 상수 격자 단계에서만 `(상수 튜플, B alias sha)` 키로 캐시; 제안기의 각 시험 조합은 새 alias 상태에서 fixture를 재평가한다.

### 3.5 회귀 보증 (AC-R3-02)
**고정 참조** = {Round 2 `search.py` sha(커밋 29dba38 기준), B `search_ranking.json` sha, B `search_aliases.json` sha, Round 2 S의 registry fingerprint `f3c2e9d4…` + 소스별 spec sha 3개, 질의 집합 sha(seed 39 + regression 14 + fixture 29)}. 같은 Round 2 S와 같은 B 정책에서 Round 2 스코어러와 Round 3 스코어러(두 상수 0, 나머지 상수 B 값)를 실행하면 **전체 ranked key 순서와 각 score가 동일**해야 한다(top-5가 아니라 전체). 참조 파일 `tests/benchmarks/round3-regression-reference.json`은 **격리된 checkout**(`git worktree`로 Round 2 B 스코어러 커밋 29dba38 + 고정 B 정책 + Round 2 S 아카이브)에서 생성한다 — Round 3 working tree의 `search.py`로 생성하지 않는다. 파일에는 `reference_commit`, `search_py_sha256`, `ranking_sha256`, `aliases_sha256`, `registry_fingerprint`, 소스별 `spec_sha256`, `query_set_sha256`를 함께 기록하고 sha를 freeze에 넣는다.

## 4. 평가와 게이트

- **대칭 판정식(evaluator):** `held_out pass := top1 ∈ expected_top1_any AND actionable == true`; `negative pass := top1 ∉ forbidden_top1 OR actionable == false`. `search_fn`은 `(ranked_keys, actionable)`을 돌려주며, Round 1·2 호출 형태(ranked_keys만)는 어댑터가 `(ranked_keys, actionable=True)`로 해석해 계속 지원된다(과거 판정이 abstention으로 바뀌지 않음; Round 1 테스트 불변). readiness와 diag는 항상 `negative_raw_top1`(top1 ∉ forbidden만)과 `negative_effective`(판정식) 두 수치를 기록한다(AC-R3-11).
- **hidden set(게이트):** T 이후 Round 2 §5.3 계약(Temporary chat + Unpersonalized, 동결 프롬프트, 기계 검사, stateless 검토, 교체 계약, coverage manifest)으로 **새로 생성**한다. **actionability 계약(사전 등록, 기계 검사는 production과 동일한 `allowed_methods()` 헬퍼와 동결 인벤토리 사용):**
  - 규칙 `actionable`(held_out): ① 질의가 동결 동사 인벤토리 토큰을 1개 이상 포함하고, ② 발견된 모든 동사의 허용 메서드 교집합 `intent_methods`가 비어 있지 않으며(evaluator의 `actionable == true`와 동일), ③ `expected_top1_any` 중 최소 하나의 HTTP 메서드가 `intent_methods`에 속해야 한다(라벨과 동결 메서드 의도 표의 정합 — 스코어링 신호인 `verb_methods`와 구조적으로 충돌하는 레코드는 봉인되지 않는다). 프롬프트 문구: "Every held_out query must express a single actionable API intent using at least one action verb whose HTTP method matches the expected operation; if several recognized verbs occur, their allowed-method intersection must be non-empty." 위반은 `record h-00N rejected: actionable`. 테스트 3분기: 교집합 비공집합+expected 메서드 포함 → 통과; 교집합 비공집합+expected 메서드 전부 불일치 → 거부; 교집합 공집합 → 거부.
  - 규칙 `negative-distribution`: negative 8건 중 **정확히 4건은 actionable == true, 정확히 4건은 actionable == false**(같은 헬퍼로 판정). 프롬프트 문구: "Exactly 4 negative queries must be actionable under the frozen verb-method inventory (a recognized action verb is present and the allowed-method intersection is non-empty) and exactly 4 must be non-actionable; prefer no recognized verb for the non-actionable half — do not manufacture conflicting multi-verb phrasings merely to force abstention." **섹션 교체 계약(동결 프롬프트에 포함):** "If a later message starts with `negative distribution rejected` and lists all eight negative ids, reply ONLY with a JSON array of exactly eight replacement negative records, one per listed id, preserving those ids; together they must satisfy exactly 4 actionable / 4 non-actionable. Do not return held_out records or the outer object." 응답은 `validate_replacement_output(obj, 8 ids)` + 분포 검사를 통과해야 한다. **수명주기:** 개별 레코드 교체 뒤에도 4/4 분포를 재검사한다; 깨졌으면 개별 레코드를 임의로 고르지 않고 섹션 교체를 **정확히 1회** 수행하며, 새 8건은 기계 검사·의미 검토를 처음부터 다시 거친다. 섹션 교체를 이미 사용한 뒤 개별 교체로 다시 4/4가 깨지면 두 번째 섹션 교체는 하지 않고 즉시 생성 attempt 전체를 `invalid`로 기록하며, 새 attempt는 **새 stateless/Unpersonalized 호출**(기존 chat 이력 미승계)에서 동일 입력으로 시작한다(attempt 상한은 Round 2와 동일).
  - 규칙 `negative-method`(기계 규칙, actionable negative에만 적용): `methods(forbidden_top1) ∩ intent_methods ≠ ∅`(메서드만으로 밀려나는 쉬운 negative 방지). 위반은 `record n-00N rejected: negative-method`. 의미 검토자는 "정말 잘못된 operation인가"에만 집중한다.
  - **생성 입력의 동결 블록:** 생성 프롬프트에 기계 판독 가능한 `VERB_METHODS:` 블록(동결 `verb_methods` JSON, canonical sha == `verb_inventory_sha256`)을 포함해 generator가 recognized verb와 메서드 교집합을 정확히 알 수 있게 한다(§5.3 stateless 계약 유지; 블록은 템플릿의 자리표시자로 T에 동결).
  - **동결 규칙 목록(순서 고정, freeze `hidden_generation_rules`):** `schema, catalog, words, actionable, negative-method, operationId, summary/tags, negative-phrase, reuse, distribution, negative-distribution`. 레코드 단위 우선순위 `schema > catalog > words > actionable > negative-method > operationId > summary/tags > negative-phrase > reuse`; `distribution`(held_out 16 전체)·`negative-distribution`(negative 8 전체)은 섹션 단위이며, 둘이 동시에 위반되면 동결 규칙 순서대로 `distribution` 요청 → 전체 재검사 → `negative-distribution` 요청 → 전체 재검사로 처리한다(요청 병합·순서 선택 금지). 기존 `verb` 규칙은 존재하지 않는다.
  - 의미 검토자 프롬프트에 추가: 매칭된 동사가 문장에서 **행위 요청의 동사**로 쓰였는지 확인하고 명사적 용법만 있으면(`comment history`, `post details`) reject.
- **Round 2 봉인 세트(참조):** `archive/round2/sealed/round2-sealed.json.enc`(sha `c1a3794b…`)를 T freeze에 `reference_set: {"origin": "round2", "enc_sha256": …, "held_out_sha256": "0f990f2f…", "negative_sha256": "7750a202…"}`로 기록만 한다. **D에서 Round 3 게이트 판정이 끝나고** 게이트 체크포인트 이벤트 `{round3_gate_result_sha256(held_out·negative 결과와 pass/fail의 canonical sha), commit_C, round3_seal_sha256, evaluation_code_sha256, ranking_sha256, aliases_sha256}`를 controller ledger에 먼저 기록한 **뒤에만** D 컨트롤러가 1회 복호화해 `round3-final.json`의 `reference_round2` 블록(held_out/negative raw·effective, `invalid_key` 레코드 id·key 목록)에 관찰값으로 기록한다. 참조 세트를 본 뒤 Round 3 게이트를 재실행·재해석하지 않으며(ledger 순서가 증거), 그 actor는 이후 `reference-aware`로 표시한다. 참조 평문은 `reference_round2` 블록 계산 직후 삭제하고 평문 sha·복호화 시각·삭제 확인을 ledger에 기록하며, 종료 커밋 시점에 평문이 존재해서는 안 된다(AC-18b 스캔 범위에 포함). 게이트·튜닝·설계에 쓰지 않는다. 복호화 전 평가는 없으며, key 소실은 기록만 한다.
- **fixture 하드 제약:** Round 2 v1.14 그대로.
- **게이트:** held_out ≥ 15/16(전부 actionable 레코드); negative_actionable 4/4 **raw** 통과(`top1 ∉ forbidden_top1`); negative_abstained 4/4 effective 통과(raw 결과도 기록); 전체 negative 8/8 effective. 종료 분기는 Round 2와 같이 D | F | X뿐이다.

## 5. 절차 델타 (Round 2 §5 상속)

- H: 도구+스코어러 변경 완료, 전체 브랜치 코드 리뷰, 비구속 H sanity 시뮬레이션(`--phase H`), 회귀 참조 생성(AC-R3-02) 후 `housekeeping_commit`. AC-R3-01의 binding 실행은 아래 pre-T 체크포인트에서만 한다(`housekeeping_commit` < S < … < pre-T 체크포인트 < T).
- S: 새 스냅샷. Round 2 S 아카이브 복사는 `registry_fingerprint` **와** 소스별 `spec_sha256` 3개가 모두 Round 2 S와 동일할 때만 허용(ledger `s_reused_from_round2`); 하나라도 다르면 새 S.
- 인벤토리: v1.14 §6 표를 행 집합·순서 그대로 상속(§3.1 prefix 불변). method-safety는 suffix 추가만, fixture 호환 검사(좁힘)는 Round 2 그대로 — 단 좁힘이 prefix 불변과 충돌하면(기존 메서드 제거 필요) 절차를 멈추고 사용자 판단.
- 사전: **재생성 없음.** 아카이브 `lexicon_raw.json`(sha `acc5cebe…`)·`lexicon_review.json`(sha `c5ba256f…`)을 입력으로 `prepare → finalize → lexicon-gate → merge --round 3`를 §6 자격 규칙으로 재실행, 추가분은 origin `lexicon-r3`. 입력 해시가 아카이브 ledger와 다르면 거부.
- 후보·R5/R6: §6 규칙으로 재생성. **pre-T 체크포인트(AC-R3-01 binding):** 인벤토리 suffix 확정 → `lexicon-r3` 병합 → 후보·R5/R6까지 끝난 **T 직전의 정확한 정책 상태**에서 `round3_simulation.py --phase pre-T`를 실행해 seed ≥ 36/39, fixture positive 23/23 · negative raw 6/6, regression raw ≥ 10/14 · effective 14/14를 만족해야 T를 만들 수 있다; 입력 ranking/aliases/verb_inventory/S sha를 ledger에 기록한다(H 시뮬레이션은 개발 sanity check). 워커 브리프는 예산 2 판으로 동결. hidden 생성 프롬프트는 `actionable`·`negative-method`·`negative-distribution` 규칙(생성기에 사전 고지)과 섹션 교체 계약, `VERB_METHODS` 블록이 추가된 Round 3 판으로 동결(sha를 freeze에 기록); 검토 프롬프트는 동사 용법의 의미적 타당성(명사적 용법 reject)과 negative가 실제로 정답 없는 질의인지만 검토하도록 한 Round 3 판으로 동결 — `negative-method`는 기계 검사 전용이며 검토자는 재판정하지 않는다. **검토자 카탈로그 전달:** 카탈로그 JSON lines는 바이트 동일한 첨부 파일로 전달하고 프롬프트 본문의 `<internal catalog lines>`는 첨부 파일 지시문으로 치환한다(Round 2 deviation의 정식화; 프롬프트 템플릿 sha와 첨부 sha를 attempts에 기록).
- T → hidden 생성·검토 → B → 워커 디스패치 → C/D | F | X: Round 2와 동일. AC-18a-B/D/F/X는 `round3-sealed.json.enc` 기준.
- **AC-18b(Round 2 교훈):** 레코드를 담은 검토 입력 파일은 B 이전에 삭제하거나 암호화하고 해시만 남긴다. B 직후 작업 디렉터리 스캔을 ledger에 기록한다.
- **역할(각각 ledger에 세션/actor id 기록):** generator actor와 reviewer actor는 **서로 다른** stateless 호출(Round 2처럼 각각 새 Unpersonalized Temporary chat)이며 Round 3 평문 가시, 이후 튜닝 금지; tuning worker = 평문 비가시(Round 2·3 모두); D 게이트 컨트롤러 = 튜닝에 관여하지 않은 Round 3 평문 비가시 actor; D 이후 Round 2 참조 세트를 연 actor는 `reference-aware`로 표시. Round 2 평문에 노출된 세션(2026-10-02/03)은 Round 3의 hidden 생성·검토·워커·D 게이트를 맡지 않는다.

## 6. 어휘 메커니즘

- **타깃 자격(expected_vocab, classify, 사전 게이트 공통):** 제외 집합은 `FUNCTION_WORDS ∪ path_noise ∪ ID_LIKE ∪ STOPWORDS ∪ {숫자}`. 동사 인벤토리·product_hints 소속은 제외 사유가 **아니다**. 단, 타깃 토큰은 해당 seed의 expected op의 **자원 어휘** `resource_vocab(op) := norm_tokens(리터럴 경로 세그먼트 + 종단 세그먼트 + tags)`(후보 타깃도 같은 `norm_tokens` 정규화)에 최소 1회 나타나야 한다(summary·operationId만의 등장은 불충분) — 현재 동결 카탈로그에서 순수 행위 토큰(get/create/delete 등)이 자원 증거를 얻지 않음을 테스트로 보장한다(tag 텍스트에 행위어가 들어올 수 있으므로 규칙 자체의 절대 보장은 아니다). 실제 카탈로그 fixture로 `feedback→comment`(경로 `comment`), `iteration→sprint`(경로 `sprint`), `blog entry→post`(tag "Blog Post"의 `post`)가 허용됨을 테스트로 고정한다. 후보 ⇔ R6 동치 테스트 유지.
- **예산:** alias 총 ≤ 15, **seed당 ≤ 2**, alias당 타깃 1.
- **제안기 원자 액션 계약(결정적):** seed를 id 사전순으로 순회한다. 각 seed의 원자 액션 = `(candidate_word, target)`; 액션 목록은 튜플 사전순. 시험 순서: 크기 1 액션을 순서대로, 그다음 **서로 다른 candidate_word**를 가진 크기 2 조합을 튜플 사전순으로. 각 시험은 현재 working 스냅샷에서 시작하고 실패한 시험의 변경은 누적하지 않는다(원복). 통과하는 첫 조합만 working에 커밋한다. seed 진입 시 이미 통과면 `resolved_by_prior_change`. 채택된 원자 액션은 seed당 ≤ 2, 전체 ≤ 15. `--verify`는 같은 제안기를 B 상태에서 재실행해 패치·`result_sha256`이 정확히 일치해야 한다(AC-R3-10).
- 사전 재게이트: `feedback→comment`, `iteration→sprint` 류가 통과한다. `release→build`처럼 타깃이 seed의 자원 필드에 없는 항목은 계속 거부된다.

## 7. 도구 변경 요약

| 파일 | 변경 |
|---|---|
| `search.py` | §3.1–3.3 신호·필드; payload에 `method_intent_consistent`, `intent_methods`, `actionable`, `recommended_operation` |
| `search_ranking.json` | 두 상수(기준값 0)·격자 추가, mismatch 격자 확장; 버전 2; `verb_methods` prefix 불변 |
| `policy.py` | `CONSTANT_KEYS` 8개; alias_notes origin `round3`/`lexicon-r3`(regex 일반형); `POLICY_VERSIONS["search"]` 3→4 |
| `alias_candidates_tool.py` | 타깃 자격 규칙(§6) |
| `tune_search_ranking.py` | 원자 액션 제안기(예산 2), 새 상수, 보수적 tie-break, fixture 캐시 범위, `--round 3` |
| `evaluator.py` | 대칭 판정식, `search_fn` 어댑터, raw/effective, freeze 키 `reference_set`·`regression_reference_sha256`·`hidden_generation_prompt_sha256`(Round 3 판) |
| `round_seal.py` | 생성 프롬프트 `actionable`·`negative-method`·`negative-distribution` 규칙 기계 검사(production `allowed_methods()` 재사용)와 우선순위, 검토자 프롬프트 동사 용법 지시, 첨부 카탈로그 전달 기록, 게이트 결과 sha 체크포인트 후 Round 2 참조 세트 평가 |
| diag | 네 필드 표시, raw/effective 집계, `reference_round2` 블록 |
| MCP 응답 테스트 / README | 네 필드(`method_intent_consistent`, `intent_methods`, `actionable`, `recommended_operation`)와 abstention 계약; diag는 네 필드 모두 표시 |

## 8. 테스트 전략

- 회귀 보증(AC-R3-02): 고정 참조 파일과 전체 순위·점수 동일.
- 신호 단위: `method_order_bonus`는 첫 동사의 첫 메서드에만; `path_coverage_bonus`는 고유 매칭 수에 비례, 노이즈·중복 미계수.
- abstention: 동사 없음 → `actionable=false`·∅; 교집합 공집합 → false; 정상 → true와 정렬된 교집합; 점수·순서 불변(AC-R3-03).
- evaluator: 대칭 판정식 4사분면(held_out 정답+actionable, 정답+abstained=실패, negative 금지 top1+abstained=통과, 금지 top1+actionable=실패); raw/effective 분리; Round 1 호출 형태 호환.
- 제안기: 원자 액션 순서 결정성, 원복, seed당 2 초과 거부, 총량 15, `--verify` 정확 일치(AC-R3-10).
- 타깃 자격: `comment`/`sprint`/`post`(tag) 허용, `get`/`create` 거부(자원 어휘 미등장), `rest`/`api`/`id` 제외; 후보 ⇔ R6 동치.
- 사전 재게이트 재현: 아카이브 입력 → 결정적 동일 출력(해시 고정).
- hidden actionability 계약: `actionable` 규칙 3분기(교집합 비공집합 + expected 메서드 포함 → 통과; 교집합 비공집합 + expected 메서드 전부 불일치 → 거부; `create and delete` 교집합 공집합 → 거부), `negative-distribution` 4/4 정확 분포(3/5 거부, 섹션 교체 요청 문자열), 섹션 위반 처리 순서(distribution → 재검사 → negative-distribution → 재검사), 우선순위.
- fixture raw 하드 제약: negative fixture에 동사 없는 질의가 있어도 raw 판정으로만 통과/실패.
- `verb_methods` prefix 불변: Round 2 리스트가 exact prefix, suffix 추가 사전순, 재배열·삭제 거부.
- 응답 스키마: `recommended_operation` 4사분면(actionable±, results 유무).
- 섹션 교체 계약: `negative distribution rejected` 응답 검증(8 id, 분포 4/4), 섹션 교체 1회 수명주기, 두 번째 교체 금지 → attempt invalid 전환; `negative-method` 기계 규칙; 생성 입력 `VERB_METHODS` 블록 sha == `verb_inventory_sha256`.
- legacy 어댑터: ranked_keys만 돌려주는 search_fn은 actionable=True로 해석.
- 선택기 tie-break: 동일 결과에서 더 작은 보너스 쌍 우선.
- H sanity: `round3_simulation.py --phase H`(비구속). T→B→C→D, T→B→F, T→B→X 세 전이의 상태 로직은 fixture·mock artifact를 쓰는 **synthetic lifecycle 테스트**로 H에서 검증하며 실제 commit chronology와 무관하다(Round 2의 `round2_simulation.py`를 일반화). 실제 수명주기는 §5가 유일한 authority: `housekeeping_commit < S < … < AC-R3-01 pre-T < T < B < C < D`. AC-R3-01 binding: `round3_simulation.py --phase pre-T`, 통과 후에만 T 생성.
- `method_order_bonus` 다중 동사 테스트: 첫 동사의 preferred가 교집합 밖이면 0.

## 9. 상태 모델·readiness 델타

**Round 3 freeze 항목(`round_freeze.json`, round=3)의 canonical 키 집합:** Round 2 round=2 항목의 키 집합(`commit_T` **제외** — T commit sha는 파일 안에 넣을 수 없는 자기참조이므로 Round 2와 같이 T 생성 후 controller ledger·readiness에 기록하고 freeze 내용 해시와 함께 bind한다; 키 집합 테스트에 `"commit_T" not in freeze_for(3)` 포함)(`round`, `structure_sha256`, `verb_inventory_sha256`, `source_registry_fingerprint`, `source_spec_sha256`, `concept_lexicon_sha256`, `lexicon_aliases_sha256`, `alias_candidates_sha256`, `worker_brief_sha256`, `hidden_generation_prompt_sha256`, `hidden_reviewer_prompt_sha256`, `tooling_code_sha256`, `evaluation_code_sha256_at_T`) + Round 3 추가 키 `regression_reference_sha256`, `reference_set`{origin, enc_sha256, held_out_sha256, negative_sha256}, `hidden_generation_rules`(순서 목록), `tuning_grid_sha256`, `hidden_set_origin`. 키 집합은 테스트로 고정한다.

Round 2 §11 상속. 추가: `hidden_set_origin: "round3"`, `hidden_generation_rules`(§4의 동결 순서 목록), `negative_actionable`/`negative_abstained` 결과, `round3_gate_result_sha256`, `evaluation_domain: "actionable recommendation queries"`, 역할별 actor id, `negative_raw_top1`/`negative_effective`(seed·regression·hidden 각각), `reference_round2`(D 이후 관찰값: raw/effective, invalid_key 목록, enc sha), `regression_reference_sha256`, `tuning_grid_sha256`, `catalog_attachment_sha256`(검토 attempts). 종료 분기는 D | F | X.

## 10. Acceptance Criteria

### 10.1 Round 2 AC 치환표 (literal 상속하지 않는 행)

v1.14 §12의 다음 행은 Round 3에서 아래 문구로 **치환**한다. 표에 없는 Round 2 AC(AC-01c~d, AC-06a, AC-11, AC-13, AC-14, AC-16, AC-17, AC-23, AC-18a-B/D/F/X, AC-18b, AC-19a~d, AC-20a/b)는 `round2`→`round3`, `r2`→`r3`, `search-tuning-round2.jsonl`→`search-tuning-round3.jsonl`, `round2-worker-brief.md`→`round3-worker-brief.md`, `.enc`→`round3-sealed.json.enc`의 이름 치환만으로 그대로 적용한다.

| Round 2 AC | Round 3 치환 |
|---|---|
| AC-01a | `round3_start_commit == e16c073`; `e16c073 < housekeeping_commit < T < B`; `verb_methods`(suffix)·`alias_candidates.json`·사전 병합·`failure_classes`·브리프·프롬프트·**`search_ranking.json` 구조 변경(새 상수 키 기준값 0, 최종 `tuning_grid`, mismatch 격자, 버전 2)**은 T에만; `policy.py`·`search.py`·§5.1 도구 변경은 H/H′에만 |
| AC-01b | 성공: T < B < C < D; T에 동결된 상수 키·격자·스키마는 불변; B..C에서는 선택된 상수 **값**과 `origin=round3` alias/rule만 변경 |
| AC-07 | 성공·실패: §8에 정의된 **Round 3 unit/integrity suite** 통과(구현 계획이 테스트 모듈·명령 목록으로 구체화) |
| AC-02 | C..D 변경 파일 ⊆ {`search_queries.json`, `round3-final.json`, `phase3-readiness.md`} |
| AC-03 | D 평문 sha256 == `round3_seal`; D에 테스트 코드 변경 없음 |
| AC-04 | gate 집합 origin ∈ {`held_out-r3`, `negative-r3`}, 다른 round origin 0개(레코드 스키마: held_out `origin: "held_out-r3"`, negative `"negative-r3"`); B 봉인 체크포인트에서 검사 |
| AC-05 | `search.py` H 변경은 §3 범위만(T에서 `evaluation_code_sha256_at_T`로 재동결); `policy.py`는 §2의 세 종류(CONSTANT_KEYS 두 항목 추가, origin `round3`/`lexicon-r3` 허용, `POLICY_VERSIONS["search"]` 3→4)만; §5.1 도구·무결성 테스트 파일은 `housekeeping_commit` 이후 종료 커밋까지 diff 비어 있음; `tooling_code_sha256` == 현재 파일 |
| AC-06b | adopted run의 스냅샷 seed 39/39, regression **effective** 14/14(raw는 별도 기록) |
| AC-08 | `POLICY_VERSIONS["search"] == 4`(응답 스키마 변경으로 H에서 3→4 bump; Round 1·2 산출물 해시에는 영향 없음을 테스트); `round_freeze` round 3 항목의 모든 해시 == 현재 Round 3 artifact; Round 1·2 항목은 역사 artifact로 불변이며 현재 파일과 비교하지 않음; **provenance 도메인별 검사:** operational artifact(`lexicon-r3` 병합분·`alias_candidates.json`·method-safety·seal·tuning log·`round3-final.json`)의 `generated_from` == Round 3 S(`round3_operational_snapshot`), `round3-regression-reference.json`의 provenance == AC-R3-02에 고정된 Round 2 S(`round2_regression_snapshot`), `reference_set`의 provenance == Round 2 archive 메타데이터; readiness에 두 snapshot을 따로 표시 |
| AC-09 | §2 "불변" 목록 byte-invariant(Round 1·2 artifact·로그·seal·readiness 섹션, fixture, Phase 1); `verb_methods`는 AC-R3-12 prefix 불변; `policy.py`는 AC-R3-13a의 세 종류만; `search_ranking.json` 구조는 AC-01a/b의 T 커밋 규칙; 그 외 변경은 §2 "변경" 목록에 한정 |
| AC-10 | `round3-final.json` provenance 필드 + `round`, `held_out_top3`, raw/effective, `reference_round2` |
| AC-12 | round3 alias/rule 전부 §6·AC-R3-05 계약(1 타깃, 후보 포함, 총 ≤15, seed당 ≤2 원자 액션, `candidate_word`, 자원 어휘 자격 — 동사·hint 소속 타깃 허용); 실패·abort 분기에서는 0개 |
| AC-15a/b | 튜닝 로그 **round 3** 기준(adopted 정확히 1 / adopted 0 + `tuning_failed` ≥ 1, 파일 상수 == B) |
| AC-21 | F 변경 파일 ⊆ {`search-tuning-round3.jsonl`, `phase3-readiness.md`}; `round3-final.json` 없음; hidden 평가 artifact 없음; readiness "Round 3 tuning failed"에 실패 `result_sha256`·`.enc` sha256 기록; Round 3 봉인 세트는 재사용하지 않음 |
| AC-22 | X 변경 파일 ⊆ {`phase3-readiness.md`}; 정책 == B; `round3-final.json` 없음; hidden 평가 0회; AC-18a-X(round3); readiness "Round 3 aborted"에 `reject_reason`·실패 테스트 이름과 출력 |

### 10.2 Round 3 AC (델타)

| ID | 분기 | 판정 | 검증 |
|---|---|---|---|
| AC-R3-01 | 공통 | **pre-T 체크포인트**(T 직전 정확한 정책 상태): seed ≥ 36/39, fixture positive 23/23 · fixture negative raw 6/6, regression negative raw ≥ 10/14 · effective 14/14, 두 수치 분리 기록, 입력 sha ledger | `round3_simulation.py --phase pre-T` ledger(H 실행은 참고) |
| AC-R3-02 | 공통 | 고정 참조(Round 2 S + B 정책 + Round 2 scorer)에서 Round 3 scorer(새 상수 0)의 전체 ranked key 순서·score 동일 | `round3-regression-reference.json` 비교 테스트, sha freeze |
| AC-R3-03 | 공통 | `actionable`/`method_intent_consistent`는 점수·순서를 바꾸지 않음 | 테스트 |
| AC-R3-04 | 공통 | 타깃 자격: 동사·hint 소속은 제외 사유 아님, 자원 필드 등장 필수; 후보 ⇔ R6 동치 | 테스트 |
| AC-R3-05 | 공통 | 채택 alias: seed당 ≤ 2 원자 액션, 총 ≤ 15, 타깃 1 | validator + 로그 테스트 |
| AC-R3-06 | T | freeze에 `reference_set`(origin round2, enc·held_out·negative sha), Round 3 생성 프롬프트 sha, `regression_reference_sha256` 기록; B·D·종료에서 archive 암호문 sha == freeze 값 | freeze + ledger |
| AC-R3-07 | D | 게이트 체크포인트 이벤트 기록 **후** Round 2 참조 세트 1회 복호화, `reference_round2` 블록에 raw/effective·invalid_key 기록, 블록 계산 직후 평문 삭제(`plaintext_sha256`, `decrypt_at`, `deleted_at` ledger), 종료 커밋에 평문 부재, 게이트 재실행·재해석 없음 | ledger 순서 + round3-final + 스캔 |
| AC-R3-08 | T 이후 | §5 역할 분리: `generator ≠ reviewer ≠ worker ≠ D 컨트롤러` actor id가 모두 서로 다르고 각 제약을 만족(Round 2 평문 노출 세션 배제) | ledger |
| AC-R3-09 | 공통 | 대칭 판정식 적용; 봉인된 held_out 16건 전부 `actionable` 규칙(①②③) 통과, negative 정확히 4 actionable / 4 abstained, actionable negative 4건 모두 `negative-method` 통과; freeze의 `hidden_generation_rules`가 §4 목록과 동일; 게이트: held_out ≥15/16, negative_actionable 4/4 raw, negative_abstained 4/4 effective | evaluator·round_seal 테스트, 봉인 전 기계 검사 ledger |
| AC-R3-10 | 성공/abort | `--verify` 재실행이 원자 액션 제안기 결과(패치·result_sha256)와 정확히 일치 | 로그 + 테스트 |
| AC-R3-11 | 공통 | readiness·diag·round3-final에 `negative_raw_top1`과 `negative_effective` 동시 기록 | 렌더 테스트 |
| AC-R3-12 | 공통 | `verb_methods` prefix 불변: 행 집합 동일, 각 Round 2 리스트가 Round 3 리스트의 exact prefix, suffix 추가는 사전순 | 테스트 |
| AC-R3-13a | H | `policy.py`의 H diff가 §2의 세 종류(CONSTANT_KEYS 추가, origin 허용, POLICY_VERSIONS bump)에 한정 | diff 테스트 |
| AC-R3-13b | T 이후 | 최종 격자가 T에 동결: `tuning_grid_sha256 := sha256(canonical_json(search_ranking.json["tuning_grid"]))`(freeze·테스트·readiness가 같은 헬퍼 사용) == 현재 파일의 값, T 이후 격자 변경 0 | freeze + git |
| AC-18b(R3) | B..종료 | D 이전 디스크에 레코드 평문 없음(검토 입력 파일 포함); B 직후 스캔 ledger | ledger |

## 11. 위험과 완화

- coverage 보너스가 "정답이 얕은 경로" 질의를 깨뜨릴 수 있음 → 기준값 0, 보수적 tie-break, fixture 하드 제약.
- 동사 없는 held_out은 판정식상 실패 → `actionable` 규칙으로 사전 등록(evaluator와 같은 헬퍼). negative는 4/4 분포 고정으로 abstention이 게이트를 비우지 못하며, actionable negative 4건의 raw 통과가 raw 품질의 진짜 게이트다.
- 격자 31,104점 × (seed 39 + neg 14 + fixture 29) → 측정 절차: 같은 S·B aliases에서 전체 격자를 정확히 1회 실행한 wall-clock(도구 오류·timeout은 판정에 쓰지 않음)을 ledger에 기록하고, 10분 초과 시 `method_order_bonus` 격자를 `[0, 0.5]`로 축소. 격자 축소 여부는 **T 이전에만** 결정하고 T 이후 격자 변경은 금지하며, 최종 격자의 canonical sha(`tuning_grid_sha256`)를 freeze에 기록한다(AC-R3-13b). 계획 단계에서 실측해 격자를 미리 확정하는 것을 우선한다(동일 코드가 기계 부하에 따라 다른 격자를 고르는 환경 의존을 피하기 위해, 실측 기계·러너 조건을 ledger에 기록하고 가능하면 스펙에 최종 격자를 고정한다).
- 새 hidden 생성에는 ChatGPT 사용량이 필요(T 이후, 5시간 창 초기화 후).
- s-027·s-028은 설계상 미해결일 수 있음(튜닝에 위임). Round 4 후보: 어휘 규칙 자동 제안.

## 12. 한 줄 정의

Round 3 = Round 2의 봉인 절차를 그대로 두고, 어휘를 막던 네 가지 구조(동사·hint 타깃 제외, 예산 1, 메서드 동점, base/하위 자원)를 기준값 0인 격자 상수 두 개와 자격 규칙 완화·원자 액션 예산 2로 풀고, 동사 없는 질의는 제품이 abstain하고 게이트가 그 대칭을 요구하는 라운드.
