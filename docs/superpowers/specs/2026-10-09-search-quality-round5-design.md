# Search Quality Round 5 — Technical Specification

**문서 버전:** v1.0 (2026-10-09; brainstorming 초안. 접근 결정은 검수 스레드 2의 두 판정에 따른다: 1차 "A 수정 후 채택 / B 좁게 수정 후 채택 / C 기각", 2차(비표적 counterexample 측정 후) "S2 채택 — union 정정 + §11 B만, 스코어러 무변경, known-unreachable 3개를 exact registry로 동결")
**기준일:** 2026-10-09
**선행:** Round 4 (spec v1.13 `6f99ae7`, plan v7; 종료 2026-10-09 "pre-T not reached": binding pre-T seed 35/39, dry-run tuning_accept false, T·B·hidden set 없음; `docs/phase3-readiness.md` Round 4 decision record; PR #1 병합 `56b4b0e`). Round 5는 Round 4 종결 커밋 `f745f80`에서 이미 **pending round**로 등록됐다(`PRE_FREEZE_NONVERB_STRUCTURE_SHA256[5]` = Round 4 H 구조, `pending_round() == 5`).
**상속:** 이 문서에 적지 않은 것은 **Round 4 스펙 v1.13을 그대로 상속**한다(그 상속 체인으로 Round 3 v1.25.1 포함: 스코어러·상수·격자·legacy 모드, 평가·게이트, 수명주기·역할·봉인·needle·AC-18b, 상태 모델 §9.1–§9.6, X_preB·recovery, T allowlist, 코퍼스 번들 계약). 이름 치환: `round4`→`round5`, `-r4`→`-r5`, `lexicon-r4`→`lexicon-r5`, `round4_seal`→`round5_seal`, `round4-sealed.json.enc`→`round5-sealed.json.enc`, `search-tuning-round4.jsonl`→`search-tuning-round5.jsonl`, `round4-*.md`→`round5-*.md`, `round4_simulation`→`round5_simulation`, `ROUND4_EXTRA_KEYS`→`ROUND5_EXTRA_KEYS`(§7), `POLICY_VERSIONS["search"]` 4 유지. 이 문서는 **델타**만 규정하며, 충돌 시 이 문서가 우선한다.
**목적:** Round 4가 드러낸 두 구조 결함(lexicon union의 first-wins, 같은 제품 문서 근거 동의어의 부재)을 seed와 무관한 규칙으로 고치고, 현재 메커니즘으로 표현할 수 없는 seed 3개를 **사전 동결된 known-unreachable(KU) registry**로 상태 모델에 정직하게 넣은 뒤, 새 봉인 hidden set에서 Discovery 게이트(held_out ≥ 15/16, negative 0 실패)를 재시도한다.
**설계 원칙(상속 + 추가):** Fix the mechanism, not the words / Every new number is a grid constant whose baseline is 0 / Abstain in the product, not in the evaluator / Same seal, same gate / Nothing the design session saw is a gate / Vocabulary comes from sources the seeds did not write / **A rule is admitted by counterexamples, not by seeds**(규칙은 그것이 건드리는 카탈로그 전체 slice에서 손실이 없어야 들어온다) / **What the system cannot express is declared before it is measured**(KU는 pre-T 전에 exact set으로 동결, 라운드 중 추가 금지).

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

조합 측정(근사): Round 4 first-wins 병합 결과에 alias `release→version`·`search→filter` 두 개만 더하면 seed 36/39(실패 = 정확히 {s-004, s-027, s-039}), regression raw 10 · eff 14, fixture 0. §6.1의 newest-accepted 해석 전체(다른 key의 선택 변화 포함)와 재검토 결과는 측정하지 않았다 — 그 효과는 pre-T와 §8 counterexample 스위트가 판정한다.

## 1. 목표

1. lexicon union을 **provenance-aware**로 바꾼다: 같은 key의 후보를 모두 보존하고, 각 후보를 동일한 수용 술어로 판정한 뒤, 고정된 provenance 우선순위로 하나를 고른다(§6.1).
2. Round 4 §11의 B를 **좁게 활성화**한다: 고정 코퍼스 제목의 명시적 관계 구문에서만 같은 제품 자원 토큰 동의어를 추출한다(§6.2).
3. **KU registry** `{s-004, s-027, s-039}`를 스펙(이 문서)과 코드에 exact set으로 동결하고, 수용 조건을 "reachable seed 전부 통과 ∧ 실패 집합 ⊆ registry"로 정의한다(§4).
4. 스코어러·상수·격자는 변경하지 않는다(§3). Discovery 게이트(hidden)는 Round 3/4와 같다.
5. 새 hidden set을 봉인하고 Round 4와 같은 수명주기(pre-T → T → hidden → B → worker → D)로 게이트를 시도한다.

## 2. 범위

**함:** union 해석 변경(도구), 문서 관계 동의어 추출기(도구), KU registry와 수용 조건 변경(도구·평가), 미검토 후보의 stateless 재검토 1회, round 5 이름 치환, 새 hidden set, readiness Round 5 섹션.

**하지 않음:** `search.py`·`policy.py`·`search_ranking.json` 변경(§3), 상수 격자 변경, 새 lexicon **생성**(Round 2 archive와 Round 4 생성 출력을 그대로 재사용, §5), 코퍼스 재수집(Round 4 epoch 1 번들 재사용, §5), seed·regression·fixture 레코드 변경(s-039 정답 집합 모호성은 별도의 독립 benchmark-audit 절차가 아니면 다루지 않음), 비율형 KU 규칙("KU ≤ 10%" 등), `my` 중립화·bulk-variant 규칙(기각, §0), 사용자·세션이 쓴 동의어 목록 병합.

## 3. 스코어러

변경 없음. `tools/atlassian_docs/intelligence/search.py`, `policy.py`, `data/search_ranking.json`(구조·격자·상수)은 Round 5 시작 커밋 `56b4b0e`와 바이트 동일해야 한다(AC-R5-05, Round 4 AC-R4-04 계승). 상수는 B..C 튜닝이 기존 격자에서 독립적으로 선택한다; 계획·스펙은 특정 격자점을 강제하지 않는다(설계 측정에서 본 `path_coverage_bonus` 값도 마찬가지).

## 4. 평가와 게이트

### 4.1 known-unreachable registry

`KNOWN_UNREACHABLE = {5: ("s-004", "s-027", "s-039")}` (`tests/benchmarks/evaluator.py`, 정렬된 tuple). 각 항목의 근거는 `tests/benchmarks/round5-known-unreachable.json`(커밋, T allowlist 밖의 H 산출물)에 기록한다: `{"round": 5, "seeds": [{"id", "query_sha256", "cause", "mechanisms_tried": [{"mechanism", "counterexample": {"slice", "hit_miss_before", "hit_miss_after", "losses": [...]}}], "official_source_check", "record_unchanged": true, "approved_by": "review thread 2 ruling 2026-10-09"}]}`. 질의 원문은 seed가 공개 레코드이므로 그대로 둘 수 있으나 파일은 id·sha·원인만으로도 충분해야 한다.

계약:
- registry는 **이 스펙 v1.x에 exact ID로 동결**되며 Round 5 동안 추가·삭제할 수 없다. 코드 상수와 이 문서의 집합이 같아야 한다(테스트가 스펙 본문에서 집합을 파싱해 비교).
- `reachable(seed) = seed ∖ registry`. registry의 seed가 우연히 통과해도 문제 없다(통과는 금지되지 않는다).
- registry는 freeze 키 `known_unreachable_seeds`(정렬 id 목록)와 `known_unreachable_registry_sha256`(근거 파일 sha)로 T에 고정된다.
- 실패 seed가 registry 밖에 하나라도 있으면 pre-T는 `STOP_FOR_AMENDMENT`(blocker kind `unreachable_seed`, Round 4 §4.1 의미 그대로). 그 seed를 registry에 넣는 것은 자동 허용되지 않으며 스펙 정정·검수가 필요하다.

### 4.2 수용 조건

- `tuning_accept := failed_seed_ids ⊆ registry ∧ regression_effective == 14/14 ∧ fixture_positive == 23/23 ∧ fixture_negative_raw == 6/6`. registry가 비면 Round 4 정의(seed 39/39)와 같다(테스트).
- `select_candidate`의 후보 풀 조건 `seed == SEED_TOTAL`은 `failed_seed_ids ⊆ registry`로 바뀐다(격자 결과에 실패 id 집합을 함께 보존). 우선순위 규칙(Round 3)은 그대로.
- pre-T 판정(AC-R3-01 계승): `failed ⊆ registry ∧ regression raw ≥ 10 ∧ effective 14 ∧ fixture 0`. 이때 seed 통과 수는 자동으로 ≥ 36이다.
- pre-T 게이트(Round 4 §4.1 계승): `pre_t_blockers == []`; `unreachable_seed` blocker는 **registry 밖** 실패만 센다. dry-run(write-free production pipeline) 계약은 그대로.
- readiness·워커 브리프·상태 문구는 "seed 36/36 reachable + KU 3/3"으로 쓴다; "36/39 통과"나 임계 하향으로 표현하지 않는다.
- Discovery 게이트(hidden held_out ≥ 15/16 actionable, negative 0 실패), regression 회귀 판정, AC-18 계열은 그대로다. hidden은 KU를 보상하는 점수풀이 아니다.

## 5. 절차 델타

- **S:** Round 4 규칙과 같다(라이브 fetch를 아카이브된 Round 4 S와 비교; 동일하면 재사용 `s_reused_from_round4: true`). 
- **코퍼스:** 새 수집 없음. Round 4 epoch 1 번들(`~/.atlassian_api_updater/archive/round4/round4-work/doc-title-sources/`, bundle `44f3378684201473…`, snapshot `2d3caa6e02e0a67c…`)을 읽기 전용으로 쓴다. 시작 시 `doc_titles.bundle_sha256`과 `snapshot` 재계산이 두 값과 일치해야 한다(불일치 → STOP). freeze의 doc-title 키는 이 값을 기록한다.
- **lexicon 입력(생성 없음):** raw 입력 = [Round 2 archive `lexicon_raw.json` (provenance rank 0), Round 4 `lexicon_raw_r4.json` (rank 1)]; 각 파일 sha를 시작 시 확인(Round 2 `acc5cebe…`, Round 4 `929e996e…`). 생성 입력·템플릿 sha도 components에 그대로 기록.
- **재검토(§6.3):** 기존 검토 판정이 없는 (key, targets) 후보만 Round 5 stateless 검토자 1회에 보낸다(Temporary chat, personalization off, 생성자·이전 검토자와 다른 actor, 바이트 검증, 실패 시 같은 입력으로 새 chat 1회 재시도).
- **문서 관계 후보(§6.2):** 스냅샷에서 결정적으로 추출, 별도 검토 없음(관계 구문 자체가 근거), 이후 gate는 공통.
- 그 밖의 수명주기(pre-T dry-run 게이트 → STOP/계속 → T → hidden 생성·검토·attempt-needle → 암호화(사용자) → B → worker → C/D|F|X|X_preB → readiness → archive)는 Round 4와 같다.

## 6. 어휘 메커니즘 델타

### 6.1 provenance-aware union (Round 4 판정 b, 2차 판정)

Round 3–4의 `union_docs`(같은 key는 첫 입력이 이김)를 다음으로 바꾼다.
1. **보존:** 각 raw 입력 i(provenance rank i, 오래된 것부터 0,1,…)의 각 key k에 대해 후보 `(k, targets, rank)`를 모두 보존한다. 같은 입력 안의 중복 key는 입력 파서가 이미 하나로 만든다.
2. **동일 술어:** 모든 후보는 같은 수용 술어 `accept(c) = structural_ok(c) ∧ review_ok(c) ∧ seed_gate_ok(c) ∧ seed_regression_ok(c)`로 판정된다. `structural_ok`·`seed_gate_ok`·`seed_regression_ok`는 Round 3/4 정의 그대로(후보 하나를 단독으로 판정). `review_ok`는 §6.3.
3. **해결:** key마다 수용된 후보 중 **rank가 가장 큰(가장 최근 provenance) 후보 하나**를 고른다. 수용된 후보가 없으면 key는 rejected(사유 = 각 후보의 사유 목록). 순서·결과는 seed 결과와 무관하게 입력 순서와 술어만으로 결정된다(결정성 테스트).
4. **기록:** `concept_lexicon.json`의 각 entry에 `provenance_rank`, rejected 항목에 후보별 사유를 기록; `components`에 `union_resolution: "newest-accepted"`와 입력 rank 목록.
5. 구문(phrase) key도 같은 규칙(정렬 토큰 집합이 canonical key, Round 3 v1.25 표시 규칙 유지).

### 6.2 문서 근거 같은 제품 동의어 (Round 4 §11 B의 좁은 활성화)

추출기 `doc_relations(snapshot)`(새 함수, `tests/benchmarks/doc_titles.py`):
- **패턴(동결):** 제목 전체를 소문자화한 뒤 (P1) `\b(?P<syn>[a-z][a-z-]*) as an? (?P<tgt>[a-z][a-z-]*)\b`, (P2) `\b(?P<tgt>[a-z][a-z-]*) \((?P<syn>[a-z][a-z-]*)\)`. 다른 패턴은 없다.
- **조건:** syn·tgt는 각각 단일 토큰(norm_tokens 한 개); syn ∉ 동사 인벤토리 key; syn·tgt ∉ 제품명 집합 {jira, confluence, atlassian}; tgt는 제목의 제품(source 매핑: `jira-software-cloud`·`jira-cloud-administration` → {jira-platform, jira-software}, `confluence-cloud` → {confluence})의 **카탈로그 자원 토큰**(경로 토큰); syn ≠ tgt.
- **결과:** 후보 `(syn, [tgt], origin "doc-relation", evidence = {product, url, title, pattern})`. Round 4 번들에서의 기대 결과는 정확히 `{"search": ["filter"]}`(P1 `Save your search as a filter`); 나머지 원시 일치(create→jira, calendar/android, confluence/premium feature, language/jql)는 조건에서 탈락한다(테스트가 실제 스냅샷 sha로 이 결과를 고정).
- **자격 예외:** 문서 관계 후보에 한해 Round 3 §6의 `in_catalog` 거부(같은 제품 카탈로그 토큰)를 면제한다. 그 밖의 gate(seed gate, seed-regression, fixture 하드 제약, 원자 액션 예산)는 공통으로 적용된다.
- **union 내 위치:** 문서 관계 후보는 provenance rank = (raw 입력 수)로 가장 최근 입력으로 취급된다(§6.1의 newest-accepted에 따라 같은 key의 생성 후보보다 우선). `review_ok`는 관계 구문으로 대체된다(검토 불필요).

### 6.3 검토 재사용과 Round 5 검토

- 검토 판정은 **(key, 정렬 targets) 쌍**에 묶인다. Round 2 archive 검토와 Round 4 검토(`lexicon_review_r4.json`)의 판정은, 그 검토 입력에 실제로 나타난 (key, targets) 쌍에 대해서만 재사용한다(검토 입력 파일에서 쌍을 복원; 입력 sha 확인).
- 판정이 없는 쌍(예: Round 4 생성의 `release→version` — Round 4 검토 입력은 first-wins union이라 `release→build`만 담았다)은 Round 5 검토 입력 `lexicon-review-input-r5.txt`(Round 4 검토 프롬프트와 바이트 동일한 템플릿, 쌍 목록만 다름)로 보낸다.
- `review_ok(c)` = 해당 쌍의 판정 true. 같은 쌍에 판정이 둘 이상이면(같은 쌍이 두 검토에 모두 나온 경우) 최신 검토를 쓴다.

## 7. 도구 변경 요약

- H16 (`concept_lexicon_check.py`, `alias_candidates_tool.py`): provenance-aware union(§6.1), 쌍 단위 검토 재사용과 미검토 쌍 렌더(§6.3), 후보별 gate 사유 기록, `finalize`/`merge`의 provenance 필드.
- H17 (`doc_titles.py`): `doc_relations(snapshot, catalog_tokens_by_source, verbs)` + CLI `relations`; `concept_lexicon_check`가 relations 파일을 추가 입력으로 받음(§6.2).
- H18 (`evaluator.py`, `tune_search_ranking.py`, `round5_simulation.py`, `round_seal.py`): `KNOWN_UNREACHABLE`, `reachable` 수용 조건(§4.2: `tuning_accept`, `select_candidate` 풀, pre-T verdict·blockers), freeze 키 `ROUND5_EXTRA_KEYS = ROUND4_EXTRA_KEYS + ("known_unreachable_seeds", "known_unreachable_registry_sha256", "lexicon_union_resolution")`, round 5 시뮬레이션(Round 4 시뮬레이션 복사 + 이름 치환 + KU 분기), `TOOLING_FILES`에 새 파일 추가(파일이 생기는 커밋에서).
- `search.py`, `policy.py`, `search_ranking.json` 무변경(§3).

## 8. 테스트 전략 델타

- union: (a) 앞 rank 거부 → 뒤 rank 수용 후보 선택, (b) 둘 다 수용 → 최신 rank, (c) 최신 거부 → 이전 수용, (d) 모두 거부 → rejected에 후보별 사유, (e) 입력 순서만 바꾸면 결과가 rank 규칙대로 바뀌고 seed 데이터는 결과에 영향 없음(seed-independence: seed 레코드를 바꿔도 술어가 같으면 해결 결과 동일).
- doc relations: 패턴·조건 단위 테스트, 실제 Round 4 스냅샷(sha 고정)에서 결과 exact `{"search": ["filter"]}`.
- KU: registry 상수 == 스펙 본문 집합; registry가 비면 수용 조건이 Round 4와 동일; registry 밖 실패 → blocker; registry 안 실패만 → blocker 없음; registry seed 통과 허용.
- **비표적 counterexample 스위트(pre-T 게이트의 일부):** Round 5 메커니즘이 새로 만든 entry(§6.1 해석 결과가 Round 4 first-wins 해석과 다른 key, 그리고 §6.2 entry)마다, summary 토큰에 그 key가 포함된 모든 카탈로그 operation에 대해 "summary를 질의로 넣었을 때 자기 자신이 top-1"을 pre-alias 정책과 post-alias 정책에서 비교한다. 손실(전에는 hit, 후에는 miss)이 하나라도 있으면 pre-T blocker `counterexample_loss`(STOP_FOR_AMENDMENT). 결과는 pre-T 이벤트에 slice별 hit/miss와 손실 목록으로 기록.
- AC-R5-05 diff 공란, 시뮬레이션 `--phase H`(T, B, D, F, X, XpreB2–5) 통과.

## 9. 상태 모델·readiness 델타

- Round 5는 이미 pending(§선행). freeze --round 5는 `pending_round() == 5`와 하위 round 완결성(1,2 frozen; 3,4 closed)을 확인한다(Round 4 가드 그대로).
- Round 5 시작 커밋 `round5_start_commit = 56b4b0e`.
- T allowlist(Round 4 §9.6) 이름 치환 + `tests/benchmarks/round5-known-unreachable.json`은 **T에서 바뀌면 안 되는** H 산출물이다(allowlist 밖; T diff에 나오면 REFUSED).
- readiness Round 5 섹션: Round 4 필드 + `known_unreachable` 표(각 seed의 원인·시도·counterexample·승인), `lexicon_union_resolution`, 문서 관계 entry 목록과 근거 제목, counterexample 스위트 결과.
- 종결 분기·X_preB·recovery 규칙은 Round 4 그대로(라운드 번호 치환).

## 10. Acceptance Criteria (델타)

| AC | 내용 |
|---|---|
| AC-R5-01 | union이 §6.1대로 동작한다(테스트 (a)–(e)); `concept_lexicon.json.components.union_resolution == "newest-accepted"`, entry별 `provenance_rank` 기록 |
| AC-R5-02 | 문서 관계 추출이 §6.2대로 결정적이며 Round 4 스냅샷에서 exact `{"search": ["filter"]}`; 해당 entry는 공통 gate를 통과해야 merge된다 |
| AC-R5-03 | KU registry == 스펙 집합 `{s-004, s-027, s-039}`; 근거 파일 필드 완비; freeze 키로 T에 고정; T에서 근거 파일 불변 |
| AC-R5-04 | 수용 조건(§4.2)이 `tuning_accept`·`select_candidate`·pre-T verdict·blockers에 일관 적용; registry 공집합에서 Round 4 동작과 동일 |
| AC-R5-05 | `search.py`, `policy.py`, `search_ranking.json` diff(56b4b0e..) 공란 |
| AC-R5-06 | 검토 재사용이 쌍 단위; 미검토 쌍만 Round 5 검토에 감; 검토자 actor ≠ 이전 생성자·검토자; 바이트 검증 ledger |
| AC-R5-07 | 생성 없음: raw 입력 sha가 Round 2·4 기록과 일치; 코퍼스 번들·스냅샷 sha 일치 |
| AC-R5-08 | 비표적 counterexample 스위트 손실 0(pre-T 게이트) |
| AC-R5-09 | pre-T 게이트 `pre_t_blockers == []`(registry 밖 미도달 0, tuning_accept, validation_errors 0, AC-R3-01, counterexample 손실 0) 후에만 T |
| (상속) | Round 4 AC-R4-01…10과 Round 3 AC 전부(이름 치환), Discovery 게이트 불변 |

## 11. 위험과 완화

- **union 정정의 광범위 효과:** newest-accepted는 release 외의 key에서도 Round 2 대신 Round 4 후보를 고를 수 있다. 완화: pre-T 전체 재평가와 §8 counterexample 스위트(Round 4 해석과 다른 모든 key 대상); 손실 시 STOP.
- **재검토 비결정성:** 검토자가 `release→version`을 거부하면 s-028이 다시 미도달 → registry 밖 실패 → STOP_FOR_AMENDMENT(자동 KU 추가 금지). 완화 없음(정직한 결과).
- **튜닝 단계의 변동:** dry-run이 다른 격자점을 고르거나 제안기가 alias를 추가해 reachable seed가 깨질 수 있다. 완화: Round 4 dry-run 게이트 그대로; 실패 시 STOP.
- **KU가 hidden 일반화를 가리는 위험:** KU 3개는 학습 세트의 표현 한계를 기록할 뿐 hidden 게이트를 바꾸지 않는다. hidden 생성 규칙·검토는 Round 4 그대로.
- **문서 관계 패턴의 협소함:** 2개 패턴만 쓴다; 결과가 1건뿐인 것이 정상이다. 패턴 확장은 Round 5 범위 밖.

## 12. 한 줄 정의

Round 5 = 스코어러를 그대로 두고, lexicon union의 first-wins와 같은 제품 문서 근거 동의어의 부재라는 두 구조 결함을 seed와 무관한 규칙으로 고친 뒤, 표현 불가능한 seed 3개를 사전 동결 registry로 선언하고 "reachable 36/36 + KU 3/3"에서 새 hidden set으로 Discovery 게이트를 재시도하는 라운드.

## 13. 구현 계획 입력

- 도구 H′: H16 union·검토 재사용, H17 문서 관계, H18 KU·수용 조건·freeze 키·round 5 시뮬레이션. 각각 TDD·canonical suite·`--phase H`·새 리뷰어 findings 0·AC-R5-05 diff 공란.
- 컨트롤러: Round 4 계획 v7 Tasks 4–12 구조를 round 5 이름으로 재사용하되 Task 4(코퍼스 수집) → 번들·스냅샷 sha 확인으로, Task 5(생성) → 쌍 단위 재검토 1회로 대체하고, Task 6 pre-T에 counterexample 스위트와 KU 판정을 넣는다.
- 모든 판단·결정은 검수 스레드 2에서 확정한다(사용자 중단은 작업 완료 보고뿐).
