# Search Quality Round 3 — Technical Specification

**문서 버전:** v1.0 (brainstorming 2026-10-05, 사용자 승인된 설계 섹션 1–6)
**기준일:** 2026-10-05
**선행 구현:** Round 2 (spec v1.14, 종료 커밋 F `770eb63`: 튜닝 실패, hidden set 미평가; `main` e16c073). 오프라인 테스트 476.
**상속:** 이 문서에 적지 않은 절차·AC·상태 모델은 **Round 2 스펙 v1.14를 그대로 상속**한다(§5 봉인 절차, §5.3 stateless 계약, §5.5 one-way 파이프라인·두 단계 채택, §8 alias_notes 스키마, §11 상태 모델, §12 AC 전부). 이 문서는 **델타**만 규정하며, 충돌 시 이 문서가 우선한다.
**목적:** Round 2가 증명한 구조적 실패 원인 4가지를 최소 변경으로 제거하고, Round 2 봉인 세트(미관찰)로 Discovery 게이트(held_out ≥ 15/16, negative 0 실패)를 재시도한다.
**설계 원칙:** Fix the mechanism, not the words / Every new number is a grid constant with 0 in its grid / Confidence is reported, not hidden / Same seal, same gate / The controller that saw plaintext never touches the next round after T

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

사전 시뮬레이션(스코어러를 임시 패치, 아카이브된 Round 2 S, B 상수): 막혀 있던 alias 8개를 풀면 33/39, 동사 순서 tie-break 0.5 + path-coverage 1.0을 더하면 35/39, `method_mismatch_penalty` 5까지 넓히면 36/39, fixture 23/23·6/6 무손상. 명사 negative 4건은 `confident` 규칙으로 통과(14/14). coverage 2.0 이상은 fixture와 s-029(정답이 더 얕은 경로)를 깨뜨린다. alias_damping 1.0은 손해.

## 1. 목표

- Discovery 게이트: Round 2 봉인 세트에서 held_out ≥ 15/16, negative 0 실패(negative 판정은 §4의 confident 규칙 포함).
- 튜닝 전 seed ≥ 36/39, regression negative 14/14, fixture 23/23·6/6을 H 시점 시뮬레이션으로 재현(AC-R3-01).

## 2. 범위

**변경:** `tools/atlassian_docs/intelligence/search.py`(신호 2개, `confident` 플래그), `data/search_ranking.json`(상수 2개, 격자, `verb_methods` 순서 의미), `tests/benchmarks/alias_candidates_tool.py`(타깃 제외 규칙), `tests/tune_search_ranking.py`(예산 2, 새 상수, fixture 캐시), `tests/benchmarks/evaluator.py`(negative 판정), `tests/benchmarks/round_seal.py`(재봉인 모드), diag(플래그 표시), 스펙·계획·readiness.
**유지(동결):** Round 1·2 로그·freeze 항목·readiness 섹션·`round1-final.json`; fixture 23/6(내용 불변, 하드 제약); Phase 1 파일; `policy.py`는 alias_notes origin `lexicon-r3`·`round3` 허용 외 변경 없음.
**해제:** Round 2의 "`search.py` 불변" 조항. 대신 `search.py` 변경은 H에서 끝나고 T에서 `evaluation_code_sha256_at_T`로 재동결된다(T 이후 불변은 그대로).
**하지 않음:** alias_damping 변경, 어휘 규칙(`when_all`) 자동 제안, 지시어(this/that) 신호, hidden set 신규 생성.

## 3. 스코어러 변경 (`search.py`, 모두 `search_ranking.json` 상수)

### 3.1 `method_order_bonus`
질의 unigram 중 **첫 번째로 등장하는** 동사 인벤토리 토큰 `v`의 행 `verb_methods[v]`는 **선호 순서** 리스트다. `entry.method == verb_methods[v][0]`이면 `+method_order_bonus`. 동사가 없으면 0. 기존 `method_intent`(교집합 기반 가감)는 그대로 유지되며 이 신호는 그 위에 더해진다. 격자 `[0, 0.5, 1.0]`, 기준값 0.5. signals에 `method_order: {"value", "verb", "preferred"}`를 기록한다.

### 3.2 `path_coverage_bonus`
`entry.path_tokens`(노이즈 제거된 리터럴 경로 토큰) 중 `forms ∩ exp.all ≠ ∅`인 토큰 수 `m`에 대해 `+path_coverage_bonus × m`. 격자 `[0, 0.5, 1.0]`, 기준값 0.5. signals에 `path_coverage: {"value", "matched": [...]}`.

### 3.3 `confident` 플래그 (점수 무관)
`intent_methods` := 질의 unigram 중 동사 인벤토리 토큰들의 허용 메서드 **교집합**(동사 없음 → ∅). `confident := bool(intent_methods)`. 응답 payload에 `confident: bool`, `intent_methods: [sorted]`를 추가한다. 정렬·점수에는 영향이 없다. MCP 응답 스키마 변경이므로 Phase 2 응답 테스트에 두 필드를 추가한다(provenance 블록은 불변).

### 3.4 격자와 상수 집합
`CONSTANT_KEYS`에 `method_order_bonus`, `path_coverage_bonus`를 추가(총 8). `method_mismatch_penalty` 격자를 `[0,1,2,3,4,5]`로 확장. 격자 크기 1728 × 9 × 2 = 31,104 지점. 격자 평가는 fixture 결과를 상수별로 한 번 계산해 캐시한다(결정적; 캐시는 run 내부 메모리에만).

### 3.5 회귀 보증
두 상수가 0이면 모든 op의 점수와 순서는 Round 2 B 정책과 **동일**해야 한다(AC-R3-02, 테스트로 고정). `confident`는 점수를 바꾸지 않으므로 Round 1·2 결과 재현에 영향이 없다.

## 4. 평가와 게이트

- **negative 판정(evaluator):** `pass := top1 ∉ forbidden_top1 or confident == false`. held_out 판정은 변경 없음(`top1 ∈ expected_top1_any`). `evaluate(records, search_fn)`의 `search_fn`은 `(ranked_keys, confident)`를 돌려주는 형태로 확장하되, Round 1 테스트(`TestRound1Invariants`, AC-17)는 기존 호출 형태로 계속 통과해야 한다(하위 호환 어댑터).
- **hidden set 재사용:** Round 2 암호문 `archive/round2/sealed/round2-sealed.json.enc`(sha `c1a3794b0ac7563bee0ccdcc61e0ecb43026d0f778ec4773ef2695459cca369b`)를 `~/.atlassian_api_updater/sealed/round3-sealed.json.enc`로 **복사**해 쓴다. B에서 `round_seal.py seal --round 3 --reuse-round 2`는 평문 없이 Round 2 freeze/bench의 봉인 해시(held_out `0f990f2f…`, negative `7750a202…`)와 분포를 `round3_seal`로 옮겨 적고 `hidden_set_origin: "round2"`, `hidden_enc_sha256`를 freeze 항목에 기록한다. 복호화는 D에서만, **새 세션의 컨트롤러**가 한다(§5).
- **D의 key 유효성:** 새 S에 없는 `expected_top1_any`/`forbidden_top1` key를 가진 레코드는 `invalid_key`로 표시하고 분모에서 제외하며 readiness에 id와 key를 기록한다. 유효 held_out이 15 미만이면 게이트는 **판정 불가(indeterminate)**로 기록하고 D 대신 종료 커밋 F′(평가 무효)로 끝난다.
- **fixture 하드 제약:** Round 2 v1.14 그대로(모든 후보 상수·alias는 23/23·6/6 통과).
- **게이트:** held_out ≥ 15/16(유효 분모), negative 실패 0.

## 5. 절차 델타 (Round 2 §5 상속)

- H: 도구+스코어러 변경 완료, 전체 브랜치 코드 리뷰, 시뮬레이션 재현(AC-R3-01) 후 `housekeeping_commit`.
- S: 새 스냅샷. fingerprint가 Round 2 S(`f3c2e9d4…`)와 같으면 아카이브 복사로 대체 가능(ledger에 `s_reused_from_round2`).
- 인벤토리: v1.14 §6 표를 **선호 순서 의미**로 상속(행 순서 변경 없음; 42개 다중 메서드 행의 첫 원소가 선호 메서드). method-safety(넓힘 전용)·fixture 호환 검사(좁힘 전용) 그대로. 순서 변경이 필요하면 같은 루프 안에서만 하고 ledger에 기록.
- 사전: **재생성 없음.** 아카이브의 `lexicon_raw.json`(sha `acc5cebe…`)·`lexicon_review.json`(sha `c5ba256f…`)을 입력으로 `prepare → finalize → lexicon-gate → merge --round 3`를 새 타깃 규칙으로 재실행한다. 추가분은 origin `lexicon-r3`. 입력 해시가 아카이브 ledger와 다르면 거부.
- 후보·R5/R6: §6의 제외 규칙으로 재생성. 워커 브리프는 예산 2를 반영한 Round 3 판으로 동결; hidden 생성·검토 프롬프트는 "Round 2 동결본 참조"로 freeze에 Round 2 sha를 그대로 적는다.
- T → B(재봉인) → 워커 디스패치 → C/D | F | X: Round 2와 동일. AC-18a-B/D/F/X는 `round3-sealed.json.enc` 기준.
- **세션 분리:** Round 2 평문을 추출 과정에서 본 컨트롤러 세션(2026-10-02/03 세션)은 Round 3의 T 이후 단계(워커 디스패치·D 복호화)를 수행하지 않는다. T까지는 허용(평문과 무관). ledger에 세션 식별자를 기록한다.
- **AC-18b 규칙(Round 2 교훈):** 레코드가 들어간 작업 파일은 만들지 않는다. Round 3는 생성·검토가 없으므로 D 이전에 평문이 디스크에 존재해서는 안 된다.

## 6. 어휘 메커니즘

- **타깃 제외 집합**(`expected_vocab`, `classify`, 사전 게이트 공통): `FUNCTION_WORDS ∪ path_noise ∪ ID_LIKE ∪ STOPWORDS ∪ {숫자}`. **동사 인벤토리 토큰과 product_hints 키는 제외하지 않는다.** 후보 ⇔ R6 동치 테스트 유지.
- **예산:** alias 총 ≤ 15, **seed당 ≤ 2**, alias당 타깃 1. 제안기는 seed(사전순)마다 후보 단어의 조합을 크기 1 → 2, 각 크기 안에서 사전순으로 시도하고, working 상태로 재평가해 통과하는 첫 조합을 채택한다(`resolved_by_prior_change` 그대로). validator는 seed당 2를 검사한다.
- 사전 재게이트: `feedback→comment`, `iteration→sprint` 류가 게이트를 통과하게 된다. `release→build`처럼 타깃이 seed의 expected_vocab에 없는 항목은 여전히 거부된다.

## 7. 도구 변경 요약

| 파일 | 변경 |
|---|---|
| `search.py` | §3.1–3.3 신호·플래그; `search_operations` payload에 `confident`, `intent_methods` |
| `search_ranking.json` | `constants`/`baseline`/`tuning_grid`에 두 상수 추가, mismatch 격자 확장; 버전 2 |
| `policy.py` | `CONSTANT_KEYS` 8개; `_check_alias_notes`에 `round3`/`lexicon-r3` 허용(regex는 이미 일반형) |
| `alias_candidates_tool.py` | 타깃 제외 규칙(§6) |
| `tune_search_ranking.py` | 예산 2 조합 제안기, 새 상수, fixture 캐시, `--round 3` |
| `evaluator.py` | negative 판정 §4, `search_fn` 어댑터, `round_freeze_hashes`에 `hidden_set_origin`/`hidden_enc_sha256` |
| `round_seal.py` | `seal --reuse-round 2`, D의 `invalid_key` 처리 |
| diag | `confident`·`intent_methods` 표시, held_out `invalid_key` 집계 |
| MCP 응답 테스트 | 두 필드 추가 |

## 8. 테스트 전략

- 신호 단위: 상수 0 → Round 2 B와 점수·순서 동일(AC-R3-02); `method_order_bonus`는 첫 동사의 첫 메서드에만; `path_coverage_bonus`는 매칭 수에 비례하고 노이즈 토큰은 세지 않음.
- `confident`: 동사 없음 → false·∅; 교집합 공집합 → false; 정상 → true와 정렬된 교집합.
- evaluator: negative 4건 유형(명사 나열, forbidden top-1, confident=false) 통과; held_out은 플래그 무관; Round 1 호출 형태 호환.
- 제안기: 조합 순서 결정성, seed당 2 초과 거부, 15 총량.
- 타깃 제외: `comment`/`sprint` 허용, `rest`/`api`/`id` 제외; 후보 ⇔ R6 동치.
- 사전 재게이트 재현: 아카이브 입력 → 결정적 동일 출력(해시 고정).
- 재봉인: `seal --reuse-round 2`가 평문 없이 Round 2 해시를 옮기고 origin을 기록; D의 `invalid_key` 분모 처리.
- 시뮬레이션 게이트(AC-R3-01): H 시점에 §0 수치 재현(seed ≥ 36/39, neg 14/14, fixture 무손상) — `round3_simulation.py`.
- Round 2 `round2_simulation.py`를 Round 3용으로 일반화해 T→B→C→D 시뮬레이션이 통과해야 `housekeeping_commit` 선언.

## 9. 상태 모델·readiness 델타

Round 2 §11 상속. 추가 필드: `hidden_set_origin`(round2), `hidden_enc_sha256`, `invalid_key_records`, `gate_denominator`, `controller_session_T_plus`(T 이후 세션 식별자), `indeterminate`(F′) 분기.

## 10. Acceptance Criteria (델타; 나머지는 v1.14 §12 상속)

| ID | 분기 | 판정 | 검증 |
|---|---|---|---|
| AC-R3-01 | 공통 | H 시점 시뮬레이션: seed ≥ 36/39, regression negative 14/14(confident 규칙 포함), fixture 23/23·6/6 | `round3_simulation.py --phase H` 출력 ledger |
| AC-R3-02 | 공통 | `method_order_bonus = path_coverage_bonus = 0`에서 Round 2 B 정책과 모든 seed·negative·fixture의 top-5 순서 동일 | 테스트 |
| AC-R3-03 | 공통 | `confident`는 점수를 바꾸지 않음(플래그 유무로 순서 불변) | 테스트 |
| AC-R3-04 | 공통 | 타깃 제외 집합에 동사·hint 미포함; 후보 ⇔ R6 동치 | 테스트 |
| AC-R3-05 | 공통 | 채택된 alias: seed당 ≤ 2, 총 ≤ 15, 타깃 1 | validator + 로그 테스트 |
| AC-R3-06 | 공통 | B의 `round3_seal` 해시 == Round 2 봉인 해시, `hidden_enc_sha256` == 복사된 암호문 sha, 평문 부재 | freeze + ledger |
| AC-R3-07 | D | `invalid_key` 레코드는 분모 제외·readiness 기록; 유효 held_out < 15 → F′ | diag + readiness |
| AC-R3-08 | T 이후 | 워커 디스패치·D는 Round 2 평문을 본 세션과 다른 세션에서 수행 | ledger 세션 id |
| AC-R3-09 | 공통 | negative 판정에 confident 규칙 적용, held_out 판정 불변 | evaluator 테스트 |
| AC-18b(R3) | B..종료 | D 이전 디스크에 레코드 평문 없음(작업 파일 포함) | 종료 시 디렉터리 스캔 ledger |

## 11. 위험과 완화

- coverage 보너스가 hidden의 "정답이 얕은 경로" 질의를 깨뜨릴 수 있음 → 격자에 0 포함, fixture 하드 제약.
- 명사 나열 held_out이 있으면 confident=false지만 held_out 판정은 top-1만 보므로 영향 없음.
- 격자 31,104점 × (seed 39 + neg 14 + fixture 29) → 계획 단계에서 실측; 10분을 넘으면 `method_order_bonus` 격자를 `[0, 0.5]`로 축소.
- Round 2 S와 새 S의 카탈로그 차이로 hidden key가 사라질 수 있음 → §4 `invalid_key` 규칙과 F′.
- s-027·s-028은 설계상 미해결일 수 있음(튜닝에 위임) → 게이트는 hidden 기준이므로 치명적이지 않음; Round 4 후보(규칙 자동 제안) 기록.

## 12. 한 줄 정의

Round 3 = Round 2의 봉인 절차와 hidden set을 그대로 두고, 어휘를 막던 네 가지 구조(동사·hint 타깃 제외, 예산 1, 메서드 동점, base/하위 자원)와 명사 negative를 격자 상수 두 개 + confident 플래그 + 제외 규칙 완화로 푸는 라운드.
