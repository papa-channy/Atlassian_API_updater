# Search Quality Round 5 — Technical Specification

**문서 버전:** v1.8 (2026-10-09; **검수 8 판정 P0 0 / P1 3 "구현 계획으로 진행 가능"**; v1.8 = 그 P1 3건 반영: §1·§7 문구를 §3 계약과 일치, counterexample 4분류의 분할 불변식(§8), `base_tuning_accept`와 최종 `tuning_accept` 이름 분리(§4.2); v1.7 = 검수 7(P0 1/P1 3) 반영: `counterexample_tokens` 투영 함수(§8), `static_policy_sha256` 스키마(§7), uncovered_static 진단 완비 구조 검증(§8), old→absent provenance 규칙(§8); v1.6 = 검수 6(P0 2/P1 3) 반영: static·proposer 중첩 시 proposer 우선 분류(§8), §8 KU 테스트를 두 동등성 계약과 일치, 설계 원칙 문구, §8 `changed_keys`를 canonical map으로, uncovered_static 진단 결정적 직렬화; v1.5 = 검수 5(P0 2/P1 3) 반영 + zero-slice 재판정(검수 스레드 2: '모든 zero-slice fail-closed' P0 철회, C+A 수정 채택 — 측정상 바뀔 수 있는 key 상한 475개 중 383개, 그리고 `release` 자체가 summary slice 0): counterexample key 4분류(§8), KU 의미 동등과 전체 파이프라인 동등 분리(§4.2), canonical policy map(§4.2), `counterexample_result` 필드(§7), 상태 문구 분리(§4.2); v1.4 = 검수 4(P0 2/P1 3) 반영: selector는 상속된 fixture-admissible 입력에서 reachable seed·regression만으로 선택(빈 registry exact 동등, §4.2), 최종 counterexample 대상 = Round 4 기준 정책과 최종 working 정책의 대칭차(제안기 alias 포함, §4.2·§8), `PipelineResult.counterexample_result`(§7), §6.2 gate 문구, 승인 근거 pre-T machine-check(§4.1); v1.3 = 검수 3(P0 1/P1 4) 반영: selector fallback도 reachable 성능만(§4.2), 해석 이름 `source-precedence`(§6.1), KU `record_sha256` = 전체 seed 레코드(§4.1), 승인 해시의 바이트 계약·archive authority(§4.1), 채택 constants에서 counterexample 재검사를 tuning_accept 조건으로(§4.2·§8); v1.2 = 검수 2(P0 2/P1 4) 반영: 제안기 입력에서 KU 제외(§4.2), counterexample 대상 = Round 4·Round 5 정책 map의 대칭차(§8), §2 문구 정합, counterexample ranking = prospective-T ranking(§8), KU 레코드 machine-check(§4.1), KU 승인 provenance 해시(§4.1); v1.1 = 검수 1(P0 3/P1 5) 반영: union 해석에서 seed 제거·후행 gate·fallback 금지(§6.1), `search_ranking.json` 불변식과 튜닝 계약 정합(§3), 실제 코퍼스 exact 결과를 portable 단위 테스트와 컨트롤러 binding check로 분리(§6.2·§8), source identity rank(§6.1), 과거 판정 충돌 시 재검토(§6.3), counterexample 기준 고정(§8), full sha 바인딩(§5), Round 5 T allowlist exact(§9); v1.0 = brainstorming 초안. 접근 결정은 검수 스레드 2의 두 판정에 따른다: 1차 "A 수정 후 채택 / B 좁게 수정 후 채택 / C 기각", 2차(비표적 counterexample 측정 후) "S2 채택 — union 정정 + §11 B만, 스코어러 무변경, known-unreachable 3개를 exact registry로 동결")
**기준일:** 2026-10-09
**선행:** Round 4 (spec v1.13 `6f99ae7`, plan v7; 종료 2026-10-09 "pre-T not reached": binding pre-T seed 35/39, dry-run tuning_accept false, T·B·hidden set 없음; `docs/phase3-readiness.md` Round 4 decision record; PR #1 병합 `56b4b0e`). Round 5는 Round 4 종결 커밋 `f745f80`에서 이미 **pending round**로 등록됐다(`PRE_FREEZE_NONVERB_STRUCTURE_SHA256[5]` = Round 4 H 구조, `pending_round() == 5`).
**상속:** 이 문서에 적지 않은 것은 **Round 4 스펙 v1.13을 그대로 상속**한다(그 상속 체인으로 Round 3 v1.25.1 포함: 스코어러·상수·격자·legacy 모드, 평가·게이트, 수명주기·역할·봉인·needle·AC-18b, 상태 모델 §9.1–§9.6, X_preB·recovery, T allowlist, 코퍼스 번들 계약). 이름 치환: `round4`→`round5`, `-r4`→`-r5`, `lexicon-r4`→`lexicon-r5`, `round4_seal`→`round5_seal`, `round4-sealed.json.enc`→`round5-sealed.json.enc`, `search-tuning-round4.jsonl`→`search-tuning-round5.jsonl`, `round4-*.md`→`round5-*.md`, `round4_simulation`→`round5_simulation`, `ROUND4_EXTRA_KEYS`→`ROUND5_EXTRA_KEYS`(§7), `POLICY_VERSIONS["search"]` 4 유지. 이 문서는 **델타**만 규정하며, 충돌 시 이 문서가 우선한다.
**목적:** Round 4가 드러낸 두 구조 결함(lexicon union의 first-wins, 같은 제품 문서 근거 동의어의 부재)을 seed와 무관한 규칙으로 고치고, 현재 메커니즘으로 표현할 수 없는 seed 3개를 **사전 동결된 known-unreachable(KU) registry**로 상태 모델에 정직하게 넣은 뒤, 새 봉인 hidden set에서 Discovery 게이트(held_out ≥ 15/16, negative 0 실패)를 재시도한다.
**설계 원칙(상속 + 추가):** Fix the mechanism, not the words / Every new number is a grid constant whose baseline is 0 / Abstain in the product, not in the evaluator / Same seal, same gate / Nothing the design session saw is a gate / Vocabulary comes from sources the seeds did not write / **A rule is admitted by counterexamples where observable, otherwise by independent source provenance; seed-driven proposals require observable counterexample coverage**(관찰 가능한 slice에서는 손실 0으로, 관찰 불가한 source-grounded 어휘는 독립 출처와 진단 기록으로 들어오며, seed 실패에서 나온 제안은 반드시 관찰 가능한 counterexample을 가져야 한다) / **What the system cannot express is declared before it is measured**(KU는 pre-T 전에 exact set으로 동결, 라운드 중 추가 금지).

---

## 0. 배경 — Round 4가 남긴 것과 Round 5 설계 측정

Round 4 pre-T(2026-10-08T22:00Z): seed 35/39, regression raw 10/14 · effective 14/14, fixture 0, dry-run tuning_accept false. 미도달 s-004·s-027·s-028·s-039(Round 3 최종과 동일).

설계 세션은 throwaway 프로브(아카이브된 Round 4 S `d69b9ca6…`, Round 4 pre-T 정책 = lexicon-r4 병합 상태, production `search_operations` 경로, 버려지는 worktree)로 원인과 해법을 측정했다. 프로브 코드는 저장소에 들어가지 않는다.

| seed | 원인 | 측정한 일반 해법 | 비표적 counterexample(summary-as-query, §8) | 판정 |
|---|---|---|---|---|
| s-028 `publish a new project release` | Round 4 생성기가 `release→version`을 냈으나 union first-wins가 Round 2 archive의 `release→build`를 택했고 그것이 seed gate에서 거부됨 | provenance-aware union(§6.1) | alias 1개, 부작용 0 | **해결 대상** |
| s-027 `show my starred searches` | `search→filter`(같은 제품 자원 토큰)가 §6에서 불허; 허용해도 `my`가 `/filter/my` 터미널과 literal 일치 | §11 B(`Save your search as a filter`) + 질의 `my` 중립화 + 격자 `path_coverage_bonus` | `search→filter`: search slice 55개 on/off 동일(손실 0). `my` 중립화: my/bulk slice 41개에서 35/6 → 13/28 hit/miss, `Get my filters` 붕괴 | `search→filter`는 채택(§6.2), `my` 규칙 기각 → **KU** |
| s-004 `transition issue status` | `POST /bulk/issues/transition` summary가 질의 3단어 전부 포함(all-match) 46 vs 정답 42 | bulk-variant 강등 v1(모든 bulk 세그먼트) / v2(비터미널 bulk 세그먼트) | v1: 대량 손실. v2: 35/6 → 33/8(명확한 손실 1 `Get issue panel pin status for projects`, 모호 1) | 기각 → **KU** |
| s-039 `browse pages inside this workspace` | `workspace→space` 근거 없음: 문서 제목 1,359개 중 workspace 0회, Confluence API 설명의 workspace는 사이트 전체 의미, jira-software는 DevOps workspace | 일반 복합어 분해(카탈로그 토큰이라 미적용, 벤치 영향 0) / stateless 생성 재시도(생성 결과만으로는 채택 근거 아님) | — | **KU** |

조합 측정(근사): Round 4 first-wins 병합 결과에 alias `release→version`·`search→filter` 두 개만 더하면 seed 36/39(실패 = 정확히 {s-004, s-027, s-039}), regression raw 10 · eff 14, fixture 0. §6.1의 source-precedence 해석 전체(다른 key의 선택 변화 포함)와 재검토 결과는 측정하지 않았다 — 그 효과는 pre-T와 §8 counterexample 스위트가 판정한다.

## 1. 목표

1. lexicon union을 **provenance-aware**로 바꾼다: 같은 key의 후보를 모두 보존하고, 각 후보를 동일한 수용 술어로 판정한 뒤, 고정된 provenance 우선순위로 하나를 고른다(§6.1).
2. Round 4 §11의 B를 **좁게 활성화**한다: 고정 코퍼스 제목의 명시적 관계 구문에서만 같은 제품 자원 토큰 동의어를 추출한다(§6.2).
3. **KU registry** `{s-004, s-027, s-039}`를 스펙(이 문서)과 코드에 exact set으로 동결하고, 수용 조건을 "reachable seed 전부 통과 ∧ 실패 집합 ⊆ registry"로 정의한다(§4).
4. 새 스코어러 로직·상수 key·격자 변경은 없다. 기존 상수 **값**의 B..C 채택과 상속된 `verb_methods` suffix만 §3대로 허용한다. Discovery 게이트(hidden)는 Round 3/4와 같다.
5. 새 hidden set을 봉인하고 Round 4와 같은 수명주기(pre-T → T → hidden → B → worker → D)로 게이트를 시도한다.

## 2. 범위

**함:** union 해석 변경(도구), 문서 관계 동의어 추출기(도구), KU registry와 수용 조건 변경(도구·평가), 미검토 후보의 stateless 재검토 1회, round 5 이름 치환, 새 hidden set, readiness Round 5 섹션.

**하지 않음:** `search.py`·`policy.py` 변경, `search_ranking.json`의 새 구조·격자·상수 key 변경(상속된 `verb_methods` suffix와 B..C 상수 **값** 채택만 §3에 따라 허용), 상수 격자 변경, 새 lexicon **생성**(Round 2 archive와 Round 4 생성 출력을 그대로 재사용, §5), 코퍼스 재수집(Round 4 epoch 1 번들 재사용, §5), seed·regression·fixture 레코드 변경(s-039 정답 집합 모호성은 별도의 독립 benchmark-audit 절차가 아니면 다루지 않음), 비율형 KU 규칙("KU ≤ 10%" 등), `my` 중립화·bulk-variant 규칙(기각, §0), 사용자·세션이 쓴 동의어 목록 병합.

## 3. 스코어러

스코어러 코드와 정책 구조는 바뀌지 않는다. 불변식(AC-R5-05, Round 4 AC-R4-04 계승·정밀화):
- `tools/atlassian_docs/intelligence/search.py`, `policy.py`: Round 5 시작 커밋 `56b4b0e`와 바이트 동일(라운드 끝까지).
- `tools/atlassian_docs/intelligence/data/search_ranking.json`: `version`, `path_noise`, `product_hints`, `tuning_grid`, `baseline`, `ordering_rules`는 `56b4b0e`와 동일(라운드 끝까지). `verb_methods`는 상속된 prefix 불변식(T에서 정렬된 suffix 추가만; Round 5에서는 인벤토리 불변이 예상). `constants`는 **값만** 상속된 B..C 채택 경로(`--adopt`, 워커 커밋)에서 바뀔 수 있고, 그 전(H, pre-T, T, hidden, B)에는 `56b4b0e`와 동일하다. 상수 종류(key 집합)는 불변.
- 상수 값은 B..C 튜닝이 기존 격자 전체에서 상속된 `select_candidate`로 독립적으로 고른다. 계획·스펙은 특정 격자점을 강제하지 않는다(설계 측정에서 본 `path_coverage_bonus` 값 포함).

## 4. 평가와 게이트

### 4.1 known-unreachable registry

`KNOWN_UNREACHABLE = {5: ("s-004", "s-027", "s-039")}` (`tests/benchmarks/evaluator.py`, 정렬된 tuple). 각 항목의 근거는 `tests/benchmarks/round5-known-unreachable.json`(커밋, T allowlist 밖의 H 산출물)에 기록한다: `{"round": 5, "approval": {"rulings": [{"thread": "review thread 2", "date": "2026-10-09", "summary", "review_output_sha256"}, …], "user_decision": {"date": "2026-10-09", "words": "좋아 Round 5 진행해보자", "event_sha256"}}, "seeds": [{"id", "record_sha256", "query_sha256", "cause", "mechanisms_tried": [{"mechanism", "counterexample": {"slice", "hit_miss_before", "hit_miss_after", "losses": [...]}}], "official_source_check"}]}`. `review_output_sha256 = sha256(아카이브된 판정 원문 파일의 exact UTF-8 바이트)` — 판정 원문은 검수 스레드 답변 텍스트를 가공 없이(헤더 없음, 끝 개행 하나) `$W/rulings/<date>-<n>.md`로 저장한다; `event_sha256 = canonical_sha256({"role": "user", "timestamp", "exact_text"})`이며 원문 이벤트는 `$W/controller-events.jsonl`에 있다. 두 원문 파일은 Round 5 archive authority(종료 archive 목록)에 반드시 포함된다(검수 3 P1-3). 근거 파일 전체 sha가 freeze 키 `known_unreachable_registry_sha256`이므로 승인 provenance도 T에 고정된다(검수 2 P1-4). 질의 원문은 seed가 공개 레코드이므로 그대로 둘 수 있으나 파일은 id·sha·원인만으로도 충분해야 한다.

계약:
- registry는 **이 스펙 v1.x에 exact ID로 동결**되며 Round 5 동안 추가·삭제할 수 없다. 코드 상수와 이 문서의 집합이 같아야 한다(테스트가 스펙 본문에서 집합을 파싱해 비교).
- **승인 근거 machine-check(검수 4 P1-3):** pre-T에서 각 `review_output_sha256` == 실제 `$W/rulings/*.md` 바이트 sha, `event_sha256` == 해당 controller 이벤트의 canonical sha, 참조된 모든 근거 파일 존재를 확인한다; 하나라도 없거나 불일치하면 STOP.
- **레코드 machine-check(검수 2 P1-3):** 각 KU id에 대해 `query_sha256 == sha256(현재 seed query)`, `record_sha256 == canonical_sha256(현재 seed 레코드 전체)`(검수 3 P1-2; `query_sha256`은 사람이 확인하기 쉬운 보조 필드)이고, 그 레코드가 `56b4b0e`의 `tests/benchmarks/search_queries.json`과 같아야 한다. H 테스트와 pre-T 이벤트가 둘 다 확인한다; 불일치 → STOP(같은 id라도 레코드가 바뀌면 면제되지 않는다). "record_unchanged"는 선언이 아니라 이 검사 결과로만 기록된다.
- `reachable(seed) = seed ∖ registry`. registry의 seed가 우연히 통과해도 문제 없다(통과는 금지되지 않는다).
- registry는 freeze 키 `known_unreachable_seeds`(정렬 id 목록)와 `known_unreachable_registry_sha256`(근거 파일 sha)로 T에 고정된다.
- 실패 seed가 registry 밖에 하나라도 있으면 pre-T는 `STOP_FOR_AMENDMENT`(blocker kind `unreachable_seed`, Round 4 §4.1 의미 그대로). 그 seed를 registry에 넣는 것은 자동 허용되지 않으며 스펙 정정·검수가 필요하다.

### 4.2 수용 조건

- `base_tuning_accept := failed_seed_ids ⊆ registry ∧ regression_effective == 14/14 ∧ fixture_positive == 23/23 ∧ fixture_negative_raw == 6/6 ∧ counterexample_loss_at_selected == [] ∧ uncovered_proposer_keys == []`(§8 분류); `PipelineResult.tuning_accept := base_tuning_accept ∧ validation_errors == []`(상속된 `accept = tuning_accept(...) and not errors`와 같은 의미를 이름으로 고정; 검수 8 P1-3). 이하 `tuning_accept`는 이 최종 값을 뜻한다. 마지막 항은 §8의 counterexample 스위트를 **선택된 constants**에서 최종 정책 전체에 대해 다시 돌린 결과다(검수 3 P1-4, 검수 4 P0-2): 대상 `final_changed_keys = { k | canonical_policy_map(round4_reference_policy).get(k) != canonical_policy_map(final_working_policy).get(k) }` — `canonical_policy_map`은 alias와 phrase rule을 같은 비교 공간으로 바꾼다: `("alias", key) → 정렬 targets`, `("phrase", 정렬 토큰 튜플) → 정렬 add targets`(검수 5 P1-1; `changed_keys`도 같은 map으로 계산) — `round4_reference_policy` = `round4_static_policy`(§8, alias와 phrase rule 모두), `final_working_policy` = 제안기 적용 후 최종 alias 정책; 따라서 lexicon 해석 변화, doc_relation, 그리고 **제안기가 B..C(또는 dry-run)에서 추가·변경한 alias**까지 포함한다. pre/post 모두 선택된 constants를 쓴다. 테스트: lexicon `changed_keys`에 없는 key를 제안기가 추가 → `final_changed_keys`에 포함 → 그 key의 summary-as-query 손실이 있으면 `tuning_accept` false. 동등성은 둘로 나뉜다(검수 5 P0-2): (i) **KU 의미 동등** — registry가 비면 `reachable_failed == failed`, `actionable_failed == failed`, selector의 seed/regression 순서, KU 관련 수용 항이 Round 4와 같다(항상 성립, 테스트); (ii) **전체 파이프라인 동등** — registry가 비고 `final_changed_keys`가 비면 `tuning_accept`가 Round 4 정의(seed 39/39)와 exact 동등하다(테스트).
- **selector(검수 3 P0-1):** 격자 결과마다 실패 id 집합을 보존하고 `reachable_failed = failed − registry`, `reachable_passed = reachable_total − |reachable_failed|`를 계산한다. selector의 입력은 상속 그대로 **fixture-admissible 격자점**(상속된 `run_pipeline`이 `fixture_fn`으로 fixture 실패 점을 먼저 제외; selector 자체는 fixture를 보지 않는다)이다(검수 4 P0-1). (1) 수용 풀 = `reachable_failed == ∅ ∧ regression_effective == total`인 점; 풀이 있으면 KU 통과 수는 무시하고 Round 3 보수적 tie-break만 적용한다. (2) 풀이 없으면 `(reachable_passed, regression_effective_passed)`를 최대화하는 점들 → Round 3 보수적 tie-break. KU 통과 수는 어느 단계에서도 순위에 들어가지 않는다. registry가 비면 `reachable_passed == seed_passed`이므로 Round 3/4 selector와 exact 동등. 테스트: reachable 성능이 같고 KU 통과 수만 다른 두 점 → 선택 동일; reachable 성능이 높은 점이 KU 통과 수가 적어도 우선; 빈 registry → 기존 selector와 모든 fixture에서 동일.
- **제안기 입력(검수 2 P0-1):** `actionable_failed_seed_ids = failed_seed_ids − registry`. 상속된 제안기(`propose_aliases`, 원자 액션 예산)는 actionable 실패만 입력으로 받는다: KU 실패만 있으면 제안기는 KU를 보지 않으며 제안은 빈 패치(no-op)일 수 있다; KU와 non-KU가 섞이면 non-KU id만 받는다; 최종적으로 non-KU 실패가 남으면 `unreachable_seed` blocker. registry가 비면 Round 4 파이프라인(제안 입력·결과)과 exact 동등(테스트 3종: KU만 실패 → 제안 입력에 KU id 없음; 혼합 → 입력 == non-KU id; 빈 registry → Round 4와 동일).
- pre-T 판정(AC-R3-01 계승): `failed ⊆ registry ∧ regression raw ≥ 10 ∧ effective 14 ∧ fixture 0`. 이때 seed 통과 수는 자동으로 ≥ 36이다.
- pre-T 게이트(Round 4 §4.1 계승): `pre_t_blockers == []`; `unreachable_seed` blocker는 **registry 밖** 실패만 센다. dry-run(write-free production pipeline) 계약은 그대로.
- readiness·워커 브리프·상태 문구는 registry 승인 상태와 실제 결과를 분리해 쓴다(검수 5 P1-3): `reachable seed: 36/36`, `KU registry: 3/3 validated`, `KU observed: pass X / fail 3−X`. "36/39 통과"나 임계 하향으로 표현하지 않는다.
- Discovery 게이트(hidden held_out ≥ 15/16 actionable, negative 0 실패), regression 회귀 판정, AC-18 계열은 그대로다. hidden은 KU를 보상하는 점수풀이 아니다.

## 5. 절차 델타

- **S:** Round 4 규칙과 같다(라이브 fetch를 아카이브된 Round 4 S와 비교; 동일하면 재사용 `s_reused_from_round4: true`). 
- **코퍼스:** 새 수집 없음. Round 4 epoch 1 번들(`~/.atlassian_api_updater/archive/round4/round4-work/doc-title-sources/`)을 읽기 전용으로 쓴다. 시작 시(컨트롤러 binding check) `doc_titles.bundle_sha256` 재계산 == `44f3378684201473d6267dd6f0296bb8babf904dc120320d594ed569d9de14fe`, 번들에서 다시 만든 스냅샷 파일 sha == `2d3caa6e02e0a67c523940add30e083cac415564302deb7e51a832ead50e6453`(불일치 → STOP). 두 값은 Round 4 readiness(`docs/phase3-readiness.md` Round 4 decision record, 커밋 `3445a11`)의 `doc_titles_snapshot` 행과 같다. freeze의 doc-title 키는 이 값을 기록한다.
- **lexicon 입력(생성 없음):** source identity로 고정된 입력(§6.1)과 full sha(시작 시 확인, 불일치 → STOP):

| source id | rank | 파일 | sha256 |
|---|---|---|---|
| `round2_archive` raw | 0 | `archive/round2/round2-work/lexicon_raw.json` | `acc5cebeafc5c48236a9de5d685b888fb2a83532340405556d77b801468a6872` |
| `round2_archive` review | — | `…/lexicon_review.json` | `c5ba256f8acd082febe06724d6646bff631e136dc437f4fa1528286117bd62f4` |
| `round2_archive` review input | — | `…/lexicon-review-input.txt` | `17efa0b87647cf89357fffe3c2aaf2f0effb24539ce1c44b399a0a574eb3a484` |
| `round2_archive` generation input | — | `…/lexicon-generation-input.txt` | `9125fa8444453762076cdb5c6791f166f46a15579fd016bfcbb8cd4412bd857e` |
| `round4_generation` raw | 1 | `archive/round4/round4-work/lexicon_raw_r4.json` | `929e996ea4b69286811f24de9c379b6143b07f127705558d1abc633329d18105` |
| `round4_generation` review | — | `…/lexicon_review_r4.json` | `308e115be3d944bd0f36108255a03bd14edc1a06b5f9182a9c5042aad35e325b` |
| `round4_generation` review input | — | `…/lexicon-review-input-r4.txt` | `8da851f5f00830428d15f6f722d3ca102ea33f1c3ef083cb52143660f50edd27` |
| `round4_generation` generation input | — | `…/lexicon-generation-input-r4.txt` | `6bfacc2589ab2a715391a299f9106d680689038b879752a0d216504845bbd9c1` |
| `doc_relation` | 2 | 스냅샷에서 추출(§6.2) | 스냅샷 sha 위 |

생성 입력·템플릿 sha는 components에 그대로 기록한다.
- **재검토(§6.3):** 기존 검토 판정이 없는 (key, targets) 후보만 Round 5 stateless 검토자 1회에 보낸다(Temporary chat, personalization off, 생성자·이전 검토자와 다른 actor, 바이트 검증, 실패 시 같은 입력으로 새 chat 1회 재시도).
- **문서 관계 후보(§6.2):** 스냅샷에서 결정적으로 추출, 별도 검토 없음(관계 구문 자체가 근거), 이후 gate는 공통.
- 그 밖의 수명주기(pre-T dry-run 게이트 → STOP/계속 → T → hidden 생성·검토·attempt-needle → 암호화(사용자) → B → worker → C/D|F|X|X_preB → readiness → archive)는 Round 4와 같다.

## 6. 어휘 메커니즘 델타

### 6.1 provenance-aware union (Round 4 판정 b, 2차 판정, 검수 1 P0-1·P1-1)

Round 3–4의 `union_docs`(같은 key는 첫 입력이 이김)를 다음으로 바꾼다. **해석(resolution)은 seed·regression·fixture를 읽지 않는다.**
1. **source identity rank(고정):** `round2_archive` = 0, `round4_generation` = 1, `doc_relation` = 2. rank는 입력의 source id 메타데이터에서 오며 CLI 인자 순서와 무관하다(입력 나열 순서를 바꿔도 결과 동일).
2. **보존:** 각 source의 각 key k에 대해 후보 `(k, 정렬 targets, rank)`를 모두 보존한다.
3. **자격(seed 무관):** `eligible(c) = structural_ok(c) ∧ review_ok(c)`. `structural_ok`는 Round 3/4 구조 단계 정의(동사·제품명·카탈로그·자격 규칙; §6.2 후보의 `in_catalog` 면제 포함)를 후보 하나에 적용한 것이고, `review_ok`는 §6.3. 둘 다 benchmark 파일을 읽지 않는다(테스트: 해석 함수에 benchmark 경로가 전달되지 않음).
4. **해석:** key마다 eligible 후보 중 **source precedence(rank)가 가장 높은 후보 하나**를 고른다. eligible 후보가 없으면 key는 rejected(후보별 사유 목록).
5. **후행 gate(상속, 대체 없음):** 해석된 lexicon 전체에 상속된 lexicon gate(`seed-incompatible`, `seed-regression`)를 적용한다. gate는 해석된 entry를 **제거만** 할 수 있고, 같은 key의 다른(오래된) 후보로 **대체하지 않는다**(fallback 금지). 제거로 reachable seed가 실패하면 그것은 pre-T(§4)·counterexample(§8)에서 드러나며 STOP_FOR_AMENDMENT다.
6. **기록:** `concept_lexicon.json`의 각 entry에 `source`·`provenance_rank`, rejected 항목에 후보별 사유, gate 제거 항목에 `gate_reason`; `components`에 `union_resolution: "source-precedence"`와 source 표(§5).
7. 구문(phrase) key도 같은 규칙(정렬 토큰 집합이 canonical key, Round 3 v1.25 표시 규칙 유지).

### 6.2 문서 근거 같은 제품 동의어 (Round 4 §11 B의 좁은 활성화)

추출기 `doc_relations(snapshot)`(새 함수, `tests/benchmarks/doc_titles.py`):
- **패턴(동결):** 제목 전체를 소문자화한 뒤 (P1) `\b(?P<syn>[a-z][a-z-]*) as an? (?P<tgt>[a-z][a-z-]*)\b`, (P2) `\b(?P<tgt>[a-z][a-z-]*) \((?P<syn>[a-z][a-z-]*)\)`. 다른 패턴은 없다.
- **조건:** syn·tgt는 각각 단일 토큰(norm_tokens 한 개); syn ∉ 동사 인벤토리 key; syn·tgt ∉ 제품명 집합 {jira, confluence, atlassian}; tgt는 제목의 제품(source 매핑: `jira-software-cloud`·`jira-cloud-administration` → {jira-platform, jira-software}, `confluence-cloud` → {confluence})의 **카탈로그 자원 토큰**(경로 토큰); syn ≠ tgt.
- **결과:** 후보 `(syn, [tgt], source "doc_relation", evidence = {product, url, title, pattern})`. Round 4 번들에서의 기대 결과는 정확히 `{"search": ["filter"]}`(P1 `Save your search as a filter`); 나머지 원시 일치(create→jira, calendar/android, confluence/premium feature, language/jql)는 조건에서 탈락한다. 이 exact 결과는 **컨트롤러 binding check**(실제 아카이브 스냅샷, §5의 sha 확인 뒤 `doc_relations(snapshot) == {"search": ["filter"]}`, 아니면 STOP_FOR_AMENDMENT, 결과·sha ledger)로 검증하고, 알고리즘은 저장소에 커밋된 축소 fixture로 portable 단위 테스트한다(§8; 검수 1 P0-3).
- **자격 예외:** 문서 관계 후보에 한해 Round 3 §6의 `in_catalog` 거부(같은 제품 카탈로그 토큰)를 면제한다. 해석 뒤에는 다른 entry와 똑같이 후행 gate(`seed-incompatible`, `seed-regression`)를 거치고, 이후 전체 정책은 상속된 fixture·튜닝 수용 조건을 거친다. 제안기 원자 액션 예산은 doc-relation 추출 자체에는 적용되지 않는다(검수 4 P1-2).
- **union 내 위치:** 문서 관계 후보는 source `doc_relation`(rank 2)이다(§6.1에 따라 같은 key의 생성 후보보다 우선). `review_ok`는 관계 구문으로 대체된다(검토 불필요).

### 6.3 검토 재사용과 Round 5 검토

- 검토 판정은 **(key, 정렬 targets) 쌍**에 묶인다. Round 2 archive 검토와 Round 4 검토(`lexicon_review_r4.json`)의 판정은, 그 검토 입력에 실제로 나타난 (key, targets) 쌍에 대해서만 재사용한다(검토 입력 파일에서 쌍을 복원; 입력 sha 확인).
- 판정이 없는 쌍(예: Round 4 생성의 `release→version` — Round 4 검토 입력은 first-wins union이라 `release→build`만 담았다)은 Round 5 검토 입력 `$W/lexicon-review-input-r5.txt`(아래 템플릿, 쌍 목록만 다름)로 보낸다.
- `review_ok(c)` = 해당 쌍의 판정 true. 같은 쌍에 과거 판정이 둘 이상이고 **모두 같으면** 재사용, **서로 다르면** unresolved로 보고 Round 5 검토에 보낸다(검수 1 P1-2). Round 5 검토가 실패·불가(두 번의 시도 모두 무효)이면 STOP_FOR_AMENDMENT.
- Round 5 검토 템플릿은 저장소에 이미 커밋된 `tests/benchmarks/round4-lexicon-review-prompt.md`를 바이트 그대로 쓴다(새 프롬프트 파일 없음).

## 7. 도구 변경 요약

- H16 (`concept_lexicon_check.py`, `alias_candidates_tool.py`): provenance-aware union(§6.1), 쌍 단위 검토 재사용과 미검토 쌍 렌더(§6.3), 후보별 gate 사유 기록, `finalize`/`merge`의 provenance 필드.
- H17 (`doc_titles.py`): `doc_relations(snapshot, catalog_tokens_by_source, verbs)` + CLI `relations`; `concept_lexicon_check`가 relations 파일을 추가 입력으로 받음(§6.2).
- H18 (`evaluator.py`, `tune_search_ranking.py`, `round5_simulation.py`, `round_seal.py`): `KNOWN_UNREACHABLE`, `reachable` 수용 조건(§4.2: `tuning_accept`, `select_candidate` 풀·fallback, 제안기 입력, pre-T verdict·blockers), counterexample 스위트(`changed_keys`, `final_changed_keys`)와 `PipelineResult.counterexample_result = {"scope": "final_policy", "scope_keys", "classes": {"covered_static", "uncovered_static", "covered_proposer", "uncovered_proposer"}, "losses", "per_key_counts", "uncovered_static_diagnostics", "pre_policy_sha256", "static_policy_sha256", "post_policy_sha256", "selected_constants"}`(pipeline_result_sha256에 포함; 검수 4 P1-1·검수 5 P1-2), freeze 키 `ROUND5_EXTRA_KEYS = ROUND4_EXTRA_KEYS + ("known_unreachable_seeds", "known_unreachable_registry_sha256", "lexicon_union_resolution")`, round 5 시뮬레이션(Round 4 시뮬레이션 복사 + 이름 치환 + KU 분기), `TOOLING_FILES`에 새 파일 추가(파일이 생기는 커밋에서).
- `search.py`·`policy.py` 무변경; `search_ranking.json`은 새 구조·상수 key·격자 변경 없음(상수 값 채택과 `verb_methods` suffix만 §3대로).

## 8. 테스트 전략 델타

- union: (a) 낮은 rank 부적격 → 높은 rank 적격 후보, (b) 둘 다 적격 → 높은 rank, (c) 높은 rank 부적격(구조·검토) → 낮은 rank 적격, (d) 모두 부적격 → rejected에 후보별 사유, (e) 입력 나열 순서를 바꿔도 결과 동일(rank는 source id에서), (f) **seed-independence:** benchmark seed 레코드를 임의로 바꿔도 해석 결과 `(key, targets, rank)` 집합이 동일, (g) 후행 gate가 entry를 제거해도 같은 key의 다른 후보로 대체되지 않음.
- doc relations: 저장소에 커밋된 축소 fixture(`tests/fixtures/doc_titles/relations-snapshot.json`; P1·P2 일치, 동사 syn, 제품명, 비카탈로그 tgt, 다른 제품 tgt, 다단어, syn == tgt 사례 포함)로 패턴·조건·결정성·`in_catalog` 면제 범위를 portable 단위 테스트한다. 실제 아카이브 스냅샷의 exact 결과는 컨트롤러 binding check(§6.2)이며 canonical suite에 들어가지 않는다.
- KU: registry 상수 == 스펙 본문 집합; `registry == ∅` → reachable·actionable·selector·KU 수용 항이 Round 4와 동일(§4.2 (i)); `registry == ∅ ∧ final_changed_keys == ∅` → 전체 `tuning_accept`가 Round 4와 동일(§4.2 (ii)); registry 밖 실패 → blocker; registry 안 실패만 → blocker 없음; registry seed 통과 허용.
- **비표적 counterexample 스위트(pre-T 게이트의 일부, 검수 1 P1-3):** 대상 key = `changed_keys = diff(canonical_policy_map(round4_static_policy), canonical_policy_map(round5_static_policy))` — `round4_static_policy` = Round 4 first-wins 해석(같은 raw·검토 입력, Round 3/4 `union_docs`) 후 후행 gate를 거쳐 병합한 alias 정책(= §4.2의 `round4_reference_policy`), `round5_static_policy` = Round 5 해석(§6.1, doc_relation 포함) 후 후행 gate를 거쳐 병합한, **제안기 적용 직전** 정책; `diff`는 두 map에서 값이 다른(한쪽에만 있는 것 포함) canonical key 집합. 대칭차이므로 old→new targets, old→absent(새 후보가 선택됐다가 gate에서 제거되고 fallback이 없어 key가 사라진 경우), absent→new, 구문 key 변화가 모두 포함된다(검수 2 P0-2; 회귀 테스트: 새 후보 선택 → gate 제거 → Round 4에는 있던 key가 Round 5에서 사라짐 → 그 key가 대상에 포함). **토큰 투영(검수 7 P0-1):** `counterexample_tokens(canonical_key)`: `("alias", key) → (key,)`, `("phrase", token_tuple) → token_tuple`; tag(`"alias"`/`"phrase"`)는 어휘 토큰이 아니며 어떤 coverage 계산에도 들어가지 않는다. slice·operationId/path 진단·문서 제목 진단은 모두 이 함수의 결과만 쓴다(테스트 3종: `("alias","search") → ("search",)`, `("phrase",("issue","type")) → ("issue","type")`, tag가 coverage 토큰에 포함되지 않음). slice(key) = summary의 norm 토큰 집합이 `counterexample_tokens(key)`의 모든 토큰을 포함하는 카탈로그 operation 전부. pre/post는 같은 S와 같은 **prospective-T ranking**(constants = `56b4b0e` 값, `verb_methods` = 검증된 prospective-T suffix 상태, 나머지 구조 `56b4b0e`)을 쓰고, 두 정책의 유일한 차이는 lexicon 해석이다(검수 2 P1-2): pre = `round4_static_policy`, post = `round5_static_policy`. 손실 = pre에서 "summary를 질의로 넣으면 그 operation이 top-1"이었는데 post에서 아닌 operation. **분류 우선순위(검수 6 P0-1):** `static_changed_keys = diff(round4_static_policy, round5_static_policy)`, `proposer_changed_keys = diff(round5_static_policy, final_working_policy)`, `final_changed_keys = diff(round4_static_policy, final_working_policy)`(모두 canonical map). k ∈ `final_changed_keys`의 출처 = `proposer` if k ∈ `proposer_changed_keys` else `static` — 제안기가 최종 값에 영향을 줬으면 제안기 우선(seed 기반 변화가 static 출처 뒤에 숨어 uncovered_static으로 빠지는 경로 차단). 테스트: static이 key 변경 → 제안기가 같은 key 재변경 → slice 0 → uncovered_proposer → `tuning_accept` false. `PipelineResult.counterexample_result`에 `static_policy_sha256`도 기록.

**key 분류(재판정):** 수용 slice는 summary-as-query 그대로이며, operationId·path 토큰 coverage는 진단으로만 기록한다(그 토큰이 slice를 넓혀도 summary 질의에 key가 없으면 alias가 발동하지 않으므로 수용 근거가 될 수 없다).

| 분류 | 출처 | slice > 0 | slice = 0 |
|---|---|---|---|
| covered_static | `round2_archive`, `round4_generation`, `doc_relation` 해석 변화 | 손실 0 필수(손실 → STOP / `tuning_accept` false) | — |
| uncovered_static | 같음 | — | 비차단. 대신 readiness 진단 필수(결정적 직렬화, 검수 6 P1-3): key, source·provenance, `summary_slice_size = 0`, operationId·path coverage(`doc_titles.norm_tokens`와 같은 정규화로 key 토큰 전부를 포함하는 operation key 사전순), 문서 제목 진단(스냅샷 normalized tokens가 key 토큰 전부를 포함하는 행을 `(product, url, title)` 사전순, url 중복 1회; 각 제목을 질의로 넣어 pre/post top-1을 기록하고 바뀐 행만 `{title, url, pre_top1, post_top1}`으로 나열; 라벨 없음, gate 아님) |
| covered_proposer | B..C(또는 dry-run) 제안기가 추가·변경한 alias | 손실 0 필수 | — |
| uncovered_proposer | 같음 | — | 차단: `counterexample_uncovered_proposer` → `tuning_accept` false(제안기 alias는 seed 실패에서 생겼으므로 counterexample조차 없으면 채택 근거가 seed 개선뿐) |

손실이 하나라도 있으면 pre-T blocker `counterexample_loss`(STOP_FOR_AMENDMENT). pre-T 이벤트에 key별 분류·slice 크기·pre/post hit 수·손실 목록·uncovered_static 진단을 기록.

**분할 불변식(검수 8 P1-2):** `covered_static ∪ uncovered_static ∪ covered_proposer ∪ uncovered_proposer == scope_keys`이고 네 집합은 서로소다; 위반 시 `validation_errors`에 `counterexample_classification_invalid`(→ `tuning_accept` false; 구현 버그로 proposer key가 어느 분류에도 들어가지 않아 fail-closed를 우회하는 경로 차단).

**진단 완비 검증(검수 7 P1-2):** `set(diagnostic_keys) == set(uncovered_static_keys)`이고 각 행의 필수 필드(key, source/provenance, summary_slice_size, opid_path_coverage, title_rows, changed_title_rows)가 있어야 한다; 아니면 `validation_errors`에 `counterexample_diagnostic_incomplete`(→ `tuning_accept` false, pre-T blocker `alias_validation_error`). uncovered_static은 의미상 비차단이지만 감사 증거 누락만은 차단한다.

**provenance 규칙(검수 7 P1-3):** old→new·absent→new = Round 5에서 선택된 entry의 `source`·`provenance_rank`; old→absent = Round 5에서 선택됐다가 후행 gate로 제거된 후보의 provenance + `gate_reason`; eligible 후보가 없어 absent가 된 경우 = `source: null`과 `rejected_candidates: [{source, provenance_rank, reasons}]` 배열. pre-T의 이 lexicon-only 검사(`changed_keys`, baseline constants)와 별도로, 튜닝이 선택한 constants에서 `final_changed_keys`(§4.2) 전체를 다시 검사해 `tuning_accept`의 마지막 항으로 쓴다(pre-T dry-run에서도 같은 경로로 계산; B..C에서 손실 → F).
- AC-R5-05 diff 공란, 시뮬레이션 `--phase H`(T, B, D, F, X, XpreB2–5) 통과.

## 9. 상태 모델·readiness 델타

- Round 5는 이미 pending(§선행). freeze --round 5는 `pending_round() == 5`와 하위 round 완결성(1,2 frozen; 3,4 closed)을 확인한다(Round 4 가드 그대로).
- Round 5 시작 커밋 `round5_start_commit = 56b4b0e`.
- **T allowlist(exact, 검수 1 P1-5):** {`…/data/search_ranking.json`(`verb_methods` suffix만), `…/data/search_aliases.json`(`lexicon-r5` 병합만), `…/data/concept_lexicon.json`, `…/data/alias_candidates.json`, `tests/benchmarks/round_freeze.json`(round 5 항목 append만), `tests/benchmarks/search_queries.json`(분류·regression 메타만, hidden 섹션 `[]`), `tests/benchmarks/round5-worker-brief.md`, `tests/benchmarks/round5-hidden-generation-prompt.md`, `tests/benchmarks/round5-hidden-reviewer-prompt.md`, `tests/benchmarks/round5-method-safety.json`}. lexicon 생성·검토 프롬프트 파일은 없다(생성 없음, 검토는 커밋된 Round 4 템플릿 재사용). `tests/benchmarks/round5-known-unreachable.json`과 doc-relation fixture는 H 산출물로 T에서 바뀌면 REFUSED. 나머지 체크포인트(post-T `t_policy_files` 재확인 등)는 Round 4 §9.6 그대로.
- readiness Round 5 섹션: Round 4 필드 + `known_unreachable` 표(각 seed의 원인·시도·counterexample·승인), `lexicon_union_resolution`, 문서 관계 entry 목록과 근거 제목, counterexample 스위트 결과.
- 종결 분기·X_preB·recovery 규칙은 Round 4 그대로(라운드 번호 치환).

## 10. Acceptance Criteria (델타)

| AC | 내용 |
|---|---|
| AC-R5-01 | union이 §6.1대로 동작한다(테스트 (a)–(g), 해석은 benchmark를 읽지 않음); `components.union_resolution == "source-precedence"`, entry별 `source`·`provenance_rank` 기록 |
| AC-R5-02a | 문서 관계 추출 알고리즘이 커밋된 fixture로 portable 단위 테스트를 통과한다 |
| AC-R5-02b | 컨트롤러 binding check: §5 sha 확인 뒤 실제 스냅샷에서 exact `{"search": ["filter"]}`(아니면 STOP), ledger 기록; 해당 entry는 후행 gate를 통과해야 merge된다 |
| AC-R5-03 | KU registry == 스펙 집합 `{s-004, s-027, s-039}`; 근거 파일 필드 완비(승인 provenance 해시 포함); 레코드 machine-check 통과(§4.1); freeze 키로 T에 고정; T에서 근거 파일 불변 |
| AC-R5-04 | KU 의미가 수용(`failed ⊆ registry`)·제안기 입력(actionable 실패만)·selector(reachable 성능만, fallback 포함)·pre-T verdict·blockers에 일관 적용; registry 공집합에서 **KU 관련 동작**이 Round 4와 동일(§4.2 (i)); 전체 동등은 registry와 `final_changed_keys`가 모두 빌 때만(§4.2 (ii)) |
| AC-R5-05 | §3 불변식: `search.py`·`policy.py` diff(56b4b0e..) 공란; `search_ranking.json`은 `constants` 값(B..C 채택 커밋에서만)과 `verb_methods` suffix(T에서만) 외 diff 공란 |
| AC-R5-06 | 검토 재사용이 쌍 단위; 미검토 쌍만 Round 5 검토에 감; 검토자 actor ≠ 이전 생성자·검토자; 바이트 검증 ledger |
| AC-R5-07 | 생성 없음: §5 표의 full sha가 모두 일치; 코퍼스 번들·스냅샷 sha 일치 |
| AC-R5-08 | 비표적 counterexample 스위트(대상 = canonical 정책 map 대칭차, prospective-T ranking): covered key 손실 0(pre-T 게이트·선택 constants의 `tuning_accept`), uncovered_proposer 0, uncovered_static은 진단 기록 완비 |
| AC-R5-09 | pre-T 게이트 `pre_t_blockers == []`(registry 밖 미도달 0, tuning_accept, validation_errors 0, AC-R3-01, counterexample 손실 0) 후에만 T |
| (상속) | Round 4 AC-R4-01…10과 Round 3 AC 전부(이름 치환), Discovery 게이트 불변 |

## 11. 위험과 완화

- **union 정정의 광범위 효과:** source-precedence은 release 외의 key에서도 Round 2 대신 Round 4 후보를 고를 수 있다. 완화: pre-T 전체 재평가와 §8 counterexample 스위트(Round 4 해석과 다른 모든 key 대상); 손실 시 STOP.
- **재검토 비결정성:** 검토자가 `release→version`을 거부하면 s-028이 다시 미도달 → registry 밖 실패 → STOP_FOR_AMENDMENT(자동 KU 추가 금지). 완화 없음(정직한 결과).
- **튜닝 단계의 변동:** dry-run이 다른 격자점을 고르거나 제안기가 alias를 추가해 reachable seed가 깨질 수 있다. 완화: Round 4 dry-run 게이트 그대로; 실패 시 STOP.
- **KU가 hidden 일반화를 가리는 위험:** KU 3개는 학습 세트의 표현 한계를 기록할 뿐 hidden 게이트를 바꾸지 않는다. hidden 생성 규칙·검토는 Round 4 그대로.
- **문서 관계 패턴의 협소함:** 2개 패턴만 쓴다; 결과가 1건뿐인 것이 정상이다. 패턴 확장은 Round 5 범위 밖.

## 12. 한 줄 정의

Round 5 = 스코어러를 그대로 두고, lexicon union의 first-wins와 같은 제품 문서 근거 동의어의 부재라는 두 구조 결함을 seed와 무관한 규칙으로 고친 뒤, 표현 불가능한 seed 3개를 사전 동결 registry로 선언하고 "reachable seed 36/36, KU registry 3/3 validated" 조건에서 새 hidden set으로 Discovery 게이트를 재시도하는 라운드.

## 13. 구현 계획 입력

- 도구 H′: H16 union·검토 재사용, H17 문서 관계, H18 KU·수용 조건·freeze 키·round 5 시뮬레이션. 각각 TDD·canonical suite·`--phase H`·새 리뷰어 findings 0·AC-R5-05 diff 공란.
- 컨트롤러: Round 4 계획 v7 Tasks 4–12 구조를 round 5 이름으로 재사용하되 Task 4(코퍼스 수집) → 번들·스냅샷 sha 확인으로, Task 5(생성) → 쌍 단위 재검토 1회로 대체하고, Task 6 pre-T에 counterexample 스위트와 KU 판정을 넣는다.
- 모든 판단·결정은 검수 스레드 2에서 확정한다(사용자 중단은 작업 완료 보고뿐).
