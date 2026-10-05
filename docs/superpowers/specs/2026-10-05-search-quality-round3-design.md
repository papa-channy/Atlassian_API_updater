# Search Quality Round 3 — Technical Specification

**문서 버전:** v1.1 (v1.0 = brainstorming 2026-10-05, 사용자 승인 섹션 1–6; v1.1 = 외부 검수 1차 반영: P0 8건·P1 6건 — 새 hidden set, abstention 계약과 대칭 게이트, S 재사용 조건, AC-R3-02 참조 고정, 동사 순서 동결, 제안기 원자 액션 계약, freeze 불변, 보수적 tie-break, 타깃 자원 증거)
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
- 튜닝 전 seed ≥ 36/39, fixture 23/23·6/6, regression negative raw ≥ 10/14 · effective(abstention 포함) 14/14를 H 시점 시뮬레이션으로 재현하고 **raw/effective를 분리 기록**(AC-R3-01).

## 2. 범위

**변경:** `tools/atlassian_docs/intelligence/search.py`(신호 2개, `method_intent_consistent`/`actionable` 필드), `data/search_ranking.json`(상수 2개, 격자, 버전 2), `tests/benchmarks/alias_candidates_tool.py`(타깃 자격 규칙), `tests/tune_search_ranking.py`(예산 2 원자 액션 제안기, 새 상수, 보수적 tie-break, fixture 캐시), `tests/benchmarks/evaluator.py`(대칭 판정식), `tests/benchmarks/round_seal.py`(생성 프롬프트 `verb` 규칙, Round 2 참조 세트 등록), diag, MCP 응답 테스트, 스펙·계획·readiness.
**유지(동결):** Round 1·2 로그·freeze 항목·readiness 섹션·`round1-final.json`; fixture 23/6(내용 불변, 하드 제약); Phase 1 파일; `verb_methods`의 **행 집합과 각 행의 리스트 순서**(Round 2 T 산출물과 byte 동일); `policy.py`는 alias_notes origin `lexicon-r3`·`round3` 외 변경 없음.
**해제:** Round 2의 "`search.py` 불변" 조항. `search.py` 변경은 H에서 끝나고 T에서 `evaluation_code_sha256_at_T`로 재동결된다.
**하지 않음:** alias_damping 변경, 어휘 규칙(`when_all`) 자동 제안, 지시어 신호, `verb_methods` 재배열, Round 2 봉인 세트의 게이트 사용.

## 3. 스코어러 변경 (`search.py`, 모두 `search_ranking.json` 상수)

### 3.1 `method_order_bonus`
질의 unigram 중 **첫 번째로 등장하는** 동사 인벤토리 토큰 `v`에 대해 `entry.method == verb_methods[v][0]`이면 `+method_order_bonus`. 동사가 없으면 0. 기존 `method_intent` 신호는 그대로 유지된다. 격자 `[0, 0.5, 1.0]`, **기준값 0**. signals에 `method_order: {"value", "verb", "preferred"}`. `verb_methods`의 리스트 순서는 Round 2 T 산출물(`structure_sha256 8106c891…`의 `verb_methods`)과 byte 동일하게 고정하며 Round 3에서 재배열하지 않는다(AC-R3-12). method-safety(넓힘)는 **리스트 끝에 추가**만 허용한다.

### 3.2 `path_coverage_bonus`
`m := |set(entry.path_tokens 원형 토큰) ∩ exp.all 매칭 토큰|`(고유 토큰 기준, 노이즈 제외)에 대해 `+path_coverage_bonus × m`. 격자 `[0, 0.5, 1.0]`, **기준값 0**. signals에 `path_coverage: {"value", "matched": sorted([...])}`.

### 3.3 메서드 의도 일관성과 abstention 계약 (점수 무관)
`intent_methods` := 질의 unigram 중 동사 인벤토리 토큰들의 허용 메서드 **교집합**(동사 없음 → ∅). `method_intent_consistent := bool(intent_methods)`. **`actionable := method_intent_consistent`.** 응답 payload에 `method_intent_consistent: bool`, `intent_methods: [sorted]`, `actionable: bool`을 추가하고, `actionable == false`일 때 결과는 **후보 목록**이지 추천이 아니다(MCP 도구 설명과 README에 명시; 결과 배열 자체는 변경 없음). 정렬·점수에는 영향이 없다. Phase 2 응답 테스트에 세 필드를 추가한다(provenance 블록 불변).

### 3.4 격자·기준값·선택기
`CONSTANT_KEYS`에 두 상수 추가(총 8), 기준값은 둘 다 0 → **B 정책은 Round 2 B와 점수·순서가 동일**하다. `method_mismatch_penalty` 격자를 `[0,1,2,3,4,5]`로 확장. 격자 1728 × 9 × 2 = 31,104 지점. **선택기 tie-break(보수성):** seed·regression·fixture 결과가 동일한 지점들 사이에서는 `(path_coverage_bonus, method_order_bonus)`가 작은 쪽을 우선하고, 그다음 Round 2의 기존 tie-break(기준값과의 L1 거리, 사전순)를 적용한다. **fixture 캐시:** 상수 격자 단계에서만 `(상수 튜플, B alias sha)` 키로 캐시; 제안기의 각 시험 조합은 새 alias 상태에서 fixture를 재평가한다.

### 3.5 회귀 보증 (AC-R3-02)
**고정 참조** = {Round 2 `search.py` sha(커밋 29dba38 기준), B `search_ranking.json` sha, B `search_aliases.json` sha, Round 2 S의 registry fingerprint `f3c2e9d4…` + 소스별 spec sha 3개, 질의 집합 sha(seed 39 + regression 14 + fixture 29)}. 같은 Round 2 S와 같은 B 정책에서 Round 2 스코어러와 Round 3 스코어러(두 상수 0, 나머지 상수 B 값)를 실행하면 **전체 ranked key 순서와 각 score가 동일**해야 한다(top-5가 아니라 전체). 테스트는 Round 2 스코어러 출력을 H에서 한 번 생성해 `tests/benchmarks/round3-regression-reference.json`(sha를 freeze에 기록)으로 고정하고 비교한다.

## 4. 평가와 게이트

- **대칭 판정식(evaluator):** `held_out pass := top1 ∈ expected_top1_any AND actionable == true`; `negative pass := top1 ∉ forbidden_top1 OR actionable == false`. `search_fn`은 `(ranked_keys, actionable)`을 돌려주며, Round 1·2 호출 형태(ranked_keys만)는 어댑터로 계속 지원된다(Round 1 테스트 불변). readiness와 diag는 항상 `negative_raw_top1`(top1 ∉ forbidden만)과 `negative_effective`(판정식) 두 수치를 기록한다(AC-R3-11).
- **hidden set(게이트):** T 이후 Round 2 §5.3 계약(Temporary chat + Unpersonalized, 동결 프롬프트, 기계 검사, stateless 검토, 교체 계약, coverage manifest)으로 **새로 생성**한다. 생성 프롬프트에 규칙 `verb`를 추가한다: "every held_out query contains an action verb (what the user wants done)"; 기계 검사는 `query unigram ∩ 동결 동사 인벤토리 ≠ ∅`로 판정하고 위반은 `record h-00N rejected: verb`로 교체 요청한다(우선순위 `schema > catalog > words > verb > operationId > summary/tags > negative-phrase > reuse`). negative에는 `verb` 규칙을 적용하지 않는다(동사 없는 negative는 abstention으로 통과할 수 있고, 동사 있는 negative는 raw로 통과해야 한다).
- **Round 2 봉인 세트(참조):** `archive/round2/sealed/round2-sealed.json.enc`(sha `c1a3794b…`)를 T freeze에 `reference_set: {"origin": "round2", "enc_sha256": …, "held_out_sha256": "0f990f2f…", "negative_sha256": "7750a202…"}`로 기록만 한다. **D에서 Round 3 게이트 판정이 끝난 뒤** 같은 컨트롤러가 1회 복호화해 `round3-final.json`의 `reference_round2` 블록(held_out/negative raw·effective, `invalid_key` 레코드 id·key 목록)에 관찰값으로 기록한다. 게이트·튜닝·설계에 쓰지 않는다. 복호화 전 평가는 없으며, key 소실은 기록만 한다.
- **fixture 하드 제약:** Round 2 v1.14 그대로.
- **게이트:** held_out ≥ 15/16, negative 실패 0 (판정식은 위). 종료 분기는 Round 2와 같이 D | F | X뿐이다.

## 5. 절차 델타 (Round 2 §5 상속)

- H: 도구+스코어러 변경 완료, 전체 브랜치 코드 리뷰, 시뮬레이션 재현(AC-R3-01), 회귀 참조 생성(AC-R3-02) 후 `housekeeping_commit`.
- S: 새 스냅샷. Round 2 S 아카이브 복사는 `registry_fingerprint` **와** 소스별 `spec_sha256` 3개가 모두 Round 2 S와 동일할 때만 허용(ledger `s_reused_from_round2`); 하나라도 다르면 새 S.
- 인벤토리: v1.14 §6 표를 행 집합·순서 그대로 상속. method-safety는 리스트 끝 추가만, fixture 호환 검사(좁힘)는 Round 2 그대로. 재배열 금지.
- 사전: **재생성 없음.** 아카이브 `lexicon_raw.json`(sha `acc5cebe…`)·`lexicon_review.json`(sha `c5ba256f…`)을 입력으로 `prepare → finalize → lexicon-gate → merge --round 3`를 §6 자격 규칙으로 재실행, 추가분은 origin `lexicon-r3`. 입력 해시가 아카이브 ledger와 다르면 거부.
- 후보·R5/R6: §6 규칙으로 재생성. 워커 브리프는 예산 2 판으로 동결. hidden 생성 프롬프트는 `verb` 규칙이 추가된 Round 3 판으로 동결(sha를 freeze에 기록); 검토 프롬프트는 Round 2 판 그대로. **검토자 카탈로그 전달:** 카탈로그 JSON lines는 바이트 동일한 첨부 파일로 전달하고 프롬프트 본문의 `<internal catalog lines>`는 첨부 파일 지시문으로 치환한다(Round 2 deviation의 정식화; 프롬프트 템플릿 sha와 첨부 sha를 attempts에 기록).
- T → hidden 생성·검토 → B → 워커 디스패치 → C/D | F | X: Round 2와 동일. AC-18a-B/D/F/X는 `round3-sealed.json.enc` 기준.
- **AC-18b(Round 2 교훈):** 레코드를 담은 검토 입력 파일은 B 이전에 삭제하거나 암호화하고 해시만 남긴다. B 직후 작업 디렉터리 스캔을 ledger에 기록한다.
- **세션:** Round 2 평문에 노출된 세션은 Round 3 D의 Round 2 참조 세트 복호화를 맡아도 되지만, Round 3 hidden 생성·검토·워커·D 게이트 판정은 노출되지 않은 세션이 맡는다(생성·검토는 stateless 계약상 어느 세션이든 평문을 보게 되므로, 그 세션은 이후 튜닝에 관여하지 않는다 — Round 2와 동일).

## 6. 어휘 메커니즘

- **타깃 자격(expected_vocab, classify, 사전 게이트 공통):** 제외 집합은 `FUNCTION_WORDS ∪ path_noise ∪ ID_LIKE ∪ STOPWORDS ∪ {숫자}`. 동사 인벤토리·product_hints 소속은 제외 사유가 **아니다**. 단, 타깃 토큰은 해당 seed의 expected op의 **자원 필드**(리터럴 경로 토큰, 종단 토큰, tag)에 최소 1회 나타나야 한다(summary·operationId만의 등장은 불충분) — 순수 행위 토큰(get/create/delete 등)이 타깃이 되는 것을 막는다. 후보 ⇔ R6 동치 테스트 유지.
- **예산:** alias 총 ≤ 15, **seed당 ≤ 2**, alias당 타깃 1.
- **제안기 원자 액션 계약(결정적):** seed를 id 사전순으로 순회한다. 각 seed의 원자 액션 = `(candidate_word, target)`; 액션 목록은 튜플 사전순. 시험 순서: 크기 1 액션을 순서대로, 그다음 **서로 다른 candidate_word**를 가진 크기 2 조합을 튜플 사전순으로. 각 시험은 현재 working 스냅샷에서 시작하고 실패한 시험의 변경은 누적하지 않는다(원복). 통과하는 첫 조합만 working에 커밋한다. seed 진입 시 이미 통과면 `resolved_by_prior_change`. 채택된 원자 액션은 seed당 ≤ 2, 전체 ≤ 15. `--verify`는 같은 제안기를 B 상태에서 재실행해 패치·`result_sha256`이 정확히 일치해야 한다(AC-R3-10).
- 사전 재게이트: `feedback→comment`, `iteration→sprint` 류가 통과한다. `release→build`처럼 타깃이 seed의 자원 필드에 없는 항목은 계속 거부된다.

## 7. 도구 변경 요약

| 파일 | 변경 |
|---|---|
| `search.py` | §3.1–3.3 신호·필드; payload에 `method_intent_consistent`, `intent_methods`, `actionable` |
| `search_ranking.json` | 두 상수(기준값 0)·격자 추가, mismatch 격자 확장; 버전 2; `verb_methods` byte 불변 |
| `policy.py` | `CONSTANT_KEYS` 8개; alias_notes origin `round3`/`lexicon-r3`(regex 일반형) |
| `alias_candidates_tool.py` | 타깃 자격 규칙(§6) |
| `tune_search_ranking.py` | 원자 액션 제안기(예산 2), 새 상수, 보수적 tie-break, fixture 캐시 범위, `--round 3` |
| `evaluator.py` | 대칭 판정식, `search_fn` 어댑터, raw/effective, freeze 키 `reference_set`·`regression_reference_sha256`·`hidden_generation_prompt_sha256`(Round 3 판) |
| `round_seal.py` | 생성 프롬프트 `verb` 규칙 기계 검사와 우선순위, 첨부 카탈로그 전달 기록, Round 2 참조 세트 D 이후 평가 |
| diag | 세 필드 표시, raw/effective 집계, `reference_round2` 블록 |
| MCP 응답 테스트 / README | 세 필드와 abstention 계약 |

## 8. 테스트 전략

- 회귀 보증(AC-R3-02): 고정 참조 파일과 전체 순위·점수 동일.
- 신호 단위: `method_order_bonus`는 첫 동사의 첫 메서드에만; `path_coverage_bonus`는 고유 매칭 수에 비례, 노이즈·중복 미계수.
- abstention: 동사 없음 → `actionable=false`·∅; 교집합 공집합 → false; 정상 → true와 정렬된 교집합; 점수·순서 불변(AC-R3-03).
- evaluator: 대칭 판정식 4사분면(held_out 정답+actionable, 정답+abstained=실패, negative 금지 top1+abstained=통과, 금지 top1+actionable=실패); raw/effective 분리; Round 1 호출 형태 호환.
- 제안기: 원자 액션 순서 결정성, 원복, seed당 2 초과 거부, 총량 15, `--verify` 정확 일치(AC-R3-10).
- 타깃 자격: `comment`/`sprint` 허용(자원 필드 등장), `get`/`create` 거부(자원 필드 미등장), `rest`/`api`/`id` 제외; 후보 ⇔ R6 동치.
- 사전 재게이트 재현: 아카이브 입력 → 결정적 동일 출력(해시 고정).
- 생성 프롬프트 `verb` 규칙: 기계 검사·우선순위·교체 요청 문자열 테스트.
- 선택기 tie-break: 동일 결과에서 더 작은 보너스 쌍 우선.
- 시뮬레이션 게이트(AC-R3-01, `round3_simulation.py --phase H`) 및 T→B→C→D 시뮬레이션 통과 후 `housekeeping_commit`.

## 9. 상태 모델·readiness 델타

Round 2 §11 상속. 추가: `hidden_set_origin: "round3"`, `hidden_generation_rules: [..., "verb"]`, `negative_raw_top1`/`negative_effective`(seed·regression·hidden 각각), `reference_round2`(D 이후 관찰값: raw/effective, invalid_key 목록, enc sha), `regression_reference_sha256`, `catalog_attachment_sha256`(검토 attempts). 종료 분기는 D | F | X.

## 10. Acceptance Criteria (델타; 나머지는 v1.14 §12 상속)

| ID | 분기 | 판정 | 검증 |
|---|---|---|---|
| AC-R3-01 | 공통 | H 시뮬레이션: seed ≥ 36/39, fixture 23/23·6/6, regression negative raw ≥ 10/14 · effective 14/14, 두 수치 분리 기록 | `round3_simulation.py --phase H` ledger |
| AC-R3-02 | 공통 | 고정 참조(Round 2 S + B 정책 + Round 2 scorer)에서 Round 3 scorer(새 상수 0)의 전체 ranked key 순서·score 동일 | `round3-regression-reference.json` 비교 테스트, sha freeze |
| AC-R3-03 | 공통 | `actionable`/`method_intent_consistent`는 점수·순서를 바꾸지 않음 | 테스트 |
| AC-R3-04 | 공통 | 타깃 자격: 동사·hint 소속은 제외 사유 아님, 자원 필드 등장 필수; 후보 ⇔ R6 동치 | 테스트 |
| AC-R3-05 | 공통 | 채택 alias: seed당 ≤ 2 원자 액션, 총 ≤ 15, 타깃 1 | validator + 로그 테스트 |
| AC-R3-06 | T | freeze에 `reference_set`(origin round2, enc·held_out·negative sha), Round 3 생성 프롬프트 sha, `regression_reference_sha256` 기록; B·D·종료에서 archive 암호문 sha == freeze 값 | freeze + ledger |
| AC-R3-07 | D | Round 2 참조 세트는 게이트 판정 **후** 1회 복호화, `reference_round2` 블록에 raw/effective·invalid_key 기록, 게이트에 미사용 | ledger 순서 + round3-final |
| AC-R3-08 | T 이후 | hidden 생성·검토·워커·D 게이트는 Round 2 평문 비노출 세션이 수행(ledger 세션 id) | ledger |
| AC-R3-09 | 공통 | 대칭 판정식 적용: held_out은 `actionable` 필수, negative는 abstained 통과; held_out 생성 규칙 `verb` 기계 검사 통과 | evaluator·round_seal 테스트, 봉인 전 기계 검사 ledger |
| AC-R3-10 | 성공/abort | `--verify` 재실행이 원자 액션 제안기 결과(패치·result_sha256)와 정확히 일치 | 로그 + 테스트 |
| AC-R3-11 | 공통 | readiness·diag·round3-final에 `negative_raw_top1`과 `negative_effective` 동시 기록 | 렌더 테스트 |
| AC-R3-12 | 공통 | `verb_methods` 행 집합·리스트 순서가 Round 2 T 산출물과 byte 동일(method-safety 추가분은 끝에만) | 테스트 |
| AC-18b(R3) | B..종료 | D 이전 디스크에 레코드 평문 없음(검토 입력 파일 포함); B 직후 스캔 ledger | ledger |

## 11. 위험과 완화

- coverage 보너스가 "정답이 얕은 경로" 질의를 깨뜨릴 수 있음 → 기준값 0, 보수적 tie-break, fixture 하드 제약.
- 동사 없는 held_out은 판정식상 실패 → 생성 규칙 `verb`로 사전 등록(기계 검사). 동사 있는 negative가 금지 op를 1위로 내면 실패 — 이것이 raw 품질의 진짜 게이트다.
- 격자 31,104점 × (seed 39 + neg 14 + fixture 29) → 계획 단계에서 실측; 10분 초과 시 `method_order_bonus` 격자를 `[0, 0.5]`로 축소.
- 새 hidden 생성에는 ChatGPT 사용량이 필요(T 이후, 5시간 창 초기화 후).
- s-027·s-028은 설계상 미해결일 수 있음(튜닝에 위임). Round 4 후보: 어휘 규칙 자동 제안.

## 12. 한 줄 정의

Round 3 = Round 2의 봉인 절차를 그대로 두고, 어휘를 막던 네 가지 구조(동사·hint 타깃 제외, 예산 1, 메서드 동점, base/하위 자원)를 기준값 0인 격자 상수 두 개와 자격 규칙 완화·원자 액션 예산 2로 풀고, 동사 없는 질의는 제품이 abstain하고 게이트가 그 대칭을 요구하는 라운드.
