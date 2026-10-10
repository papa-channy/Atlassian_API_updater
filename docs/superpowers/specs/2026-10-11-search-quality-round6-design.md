# Search Quality Round 6 — Technical Specification

**문서 버전:** v1.5 (2026-10-11; v1.5 = 검수 4(**P0 0 / P1 4, 구현 계획으로 진행 가능**) P1 반영(재검수 없음, §5.3): 정확 작업 지목(canonical key·operationId 정확 일치)은 R0 근거로 인정, 일반어 진단 질의를 §8에 고정, 하위 절의 R1–R3 표기를 R0–R3로·게이트 "네 지표"를 "다섯 지표"로 정정, scorer-rule 결과 메타데이터 봉인; v1.4 = v1.4 = 사용자 지시 개정(검수 회차 아님): MCP 실사용 점검에서 `delete something`·`delete xyzzy`·`get something`이 근거 없는 임의 작업을 `actionable: true`로 추천함을 확인(`docs/superpowers/handoffs/2026-10-11-abstention-gap-report.md`) → **R0 근거 없음 기권(GET 포함 전 메서드)** 추가(§3.1·§3.2a), `head_info`의 제품 힌트 제외를 **제품 이름 토큰만** 제외로 정정(§3.2, `board`·`sprint`·`epic`·`backlog`가 R1·R3에서 무시되던 결함), §0 설계 측정 추가, scorer-rule counterexample·AC·테스트·로그 범위를 R0–R3으로 확장; v1.3 = 검수 3(P0 2/P1 5) 반영: 재라벨 후 active `forbidden_top1` ∩ `expected_top1_any` = ∅(충돌하는 기존 값은 `legacy_forbidden_top1`로 이동), 승격 negative 8개도 Round 6 S에서 재판정(재라벨 대상 22개), 승격 payload sha 선봉인 + `label_migration` 메타데이터, positive 기대 key의 Round 6 S 카탈로그 폐포 검사, `scorer_rule_ok`는 `eligible > 0` 필요, H 실행 순서 고정, Runtime 자격은 현재 채택 지문 기준(변경 시 재시작), selector 수용 풀에 `scorer_rule_ok` 포함; v1.2 = 검수 2(P0 4/P1 5) 반영: R1–R3 채택을 안전 비악화 + 지표 하한 계약으로, 제안기 입력·trial 개선을 모든 수용 위반 레코드로 일반화, scorer-rule counterexample을 H 채택·pre-T dry-run·B..C 최종 정책에 적용하고 `tuning_accept`에 포함, 손실 기준을 검수 판정으로 우회 불가한 hard 계약으로, fallback에 rp3, 손실 분모 = OFF 자기정답 추천 수, 코퍼스를 Round 6 S에 바인딩, 재라벨 출력 스키마 machine-check, selection 매칭을 결과 포함 검색 기준으로; v1.1 = 검수 1(P0 5/P1 5) 반영: 추천 커버리지 지표 추가, §4.2가 Round 5 §4.1–4.2의 KU·reachable·selector·제안기 trial·regression 수용 의미를 전부 대체, R1–R3 전용 scorer-rule counterexample, 승격 provenance와 promotion_identity, 답이 있는 regression 레코드의 positive 평가(`regression_positive`), Runtime stability 자격 구간, 세션 상관키, R3 단·복수 판정 단일화, 기권 사유 우선순위, 이중 독립 라벨 검토; 정수 분수 비교; v1.0 = 사용자 승인 섹션 1–4 기반 초안)
**기준일:** 2026-10-11
**선행:** Round 5 (spec v1.12, plan v8; 종료 2026-10-10, terminal branch **D**: pre-T reachable seed 36/36 통과, 튜닝 채택, 최종 단일 평가 held_out 14/16·negative 6/8로 Discovery 게이트 미충족; `docs/phase3-readiness.md` Round 5 decision record; PR #2 병합 `29f298f`).
**상속:** 이 문서에 적지 않은 것은 **Round 5 스펙 v1.12를 그대로 상속**한다(그 상속 체인으로 Round 4 v1.13·Round 3 v1.25.1 포함: 수명주기 H→T→B→C/D/F/X/X_preB, 역할·봉인·needle·AC-18b, 상태 모델, T allowlist 방식, source-precedence 사전 해소, 누적 provenance, counterexample 스위트, 워커 식별 판정). 이름 치환: `round5`→`round6`, `-r5`→`-r6`, `lexicon-r5`→`lexicon-r6`, `round5_seal`→`round6_seal`, `round5-*.md`→`round6-*.md`, `round5_simulation`→`round6_simulation`, `ROUND5_EXTRA_KEYS`→`ROUND6_EXTRA_KEYS`. 이 문서는 **델타**만 규정하며 충돌 시 이 문서가 우선한다.
**목적:** 실제 업무(Jira·Confluence 워크플로우 자동화)에서 에이전트가 이 MCP 검색으로 **맞는 작업을 찾고, 확신이 없으면 추천하지 않으며, 특히 잘못된 쓰기 작업을 추천하지 않도록** 한다. 이를 위해 Discovery 게이트를 실사용 기준으로 재정의하고(§4, Phase 2.5 스펙 §18 개정), Runtime stability 측정을 지금 시작하며(§6), 추천·기권 규칙을 스코어러에 넣는다(§3).
**설계 원칙(상속 + 추가):** 상속 원칙 전부 / **A wrong write is worse than no answer**(쓰기 작업 오추천은 기권보다 나쁘다) / **Measure what the agent sees**(에이전트가 받는 상위 목록과 추천을 잰다; top-1은 기록만) / **Rules are general**(규칙은 질의 id·benchmark를 모른다; 채택은 seed·regression 위 counterexample 측정으로) / **Rehearse on real data before T**(H에서 실데이터 리허설).

---

## 0. 배경 — Round 5 결과와 Round 6 설계 측정

Round 5 최종 평가 실패 4건(Round 5 스냅샷 registry `e308a232…`에서 재현):

| id | 엔진 동작 | 유형 |
|---|---|---|
| h-010 | 목록 `GET …/linkedWorkspaces`와 단건 `…/{workspaceId}`가 54.0 동점, 목록이 1위 | 단건/목록 동점 처리 |
| h-011 | 1위 점수 8.0, 기대 `GET /rest/api/3/myself`가 상위 4위 밖 | 어휘 |
| n-002 | 상위 리소스 `DELETE …/board/{boardId}` 42.0 1위, 질의의 "column" 미반영 | 기권 실패(쓰기) |
| n-004 | `DELETE confluence …/pages/{id}` 37.5가 Jira watcher 삭제 37.0을 근소하게 앞섬 | 기권 실패(쓰기) |

현재 추천 규칙: `actionable := method_intent_consistent`(질의에 동사가 있으면 1위를 추천). 결과가 질의의 대상까지 덮는지는 보지 않는다.

**설계 측정(새 지표, Round 5 스냅샷, Round 5 정책):**

| 집합 | top-1 | top-3 | 추천 정확 | 틀린 추천 | 그중 쓰기 |
|---|---|---|---|---|---|
| held_out-r5 (16) | 14 | 15 | 14/16 | 2 | 0 |
| seed (39) | 36 | 38 | 31/34 | 3 | 1 (s-004) |

| 집합 | 정답 없는 질의에 추천을 낸 수 | 그중 쓰기 |
|---|---|---|
| negative-r5 (8) | 4 | 4 (n-001 POST, n-002 DELETE, n-003 PUT, n-004 DELETE) |
| regression_negative (14) | 6 | 1 (rn-006 DELETE) |

Round 5에서 "통과"로 센 n-001·n-003도 실제로는 엉뚱한 쓰기 작업을 추천했다. 기존 negative 판정은 "금지된 작업이 1위가 아님"이었기 때문이다.

**기권 규칙 탐색(설계 측정, 채택 아님):**

| 후보 | 없앤 틀린 추천 | 잃은 맞는 추천 | 남은 틀린 쓰기 추천 |
|---|---|---|---|
| 카탈로그 개념어 하나라도 1위에서 빠지면 기권(전 메서드) | negative 3, seed 2 | held_out 5, seed 6 | s-004, rn-006, n-003 |
| 같은 규칙, 쓰기 추천만, 수식어 제외 | negative 3 | held_out 2, seed 3 | s-004, rn-006, n-003 |
| **머리 명사(질의의 마지막 개념어) 미반영 시 기권, 쓰기 추천만** | negative 3 | held_out 1 (h-012), seed 3 | s-004, rn-006, n-003 |

**v1.4 추가 측정 — 근거 없는 질의(R0, §3.2a; 설계 측정, 채택 아님):** registry `e308a232…`, Round 5 정책. 개념어가 하나도 없거나 처음 보는 단어만 있는 질의(`delete`, `delete something`, `delete xyzzy`, `get something`, `create`, `jira delete`)도 동사→메서드 교집합만 비어 있지 않으면 동점 후보 중 key 정렬상 첫 작업이 추천된다(예: `confluence:DELETE:/space-roles/{id}`, `jira-platform:GET:/rest/api/3/bulk/issues/fields`). v1.3의 R1은 `head_info = None`이면 적용되지 않아 이 경우를 잡지 못한다.

| 후보 | seed·held_out 잃은 맞는 추천 | 없앤 틀린 추천 | summary-as-query 코퍼스 손실 / eligible |
|---|---|---|---|
| 개념어 0개면 기권(v1.3 `head_info` 정의 그대로, 전 메서드) | seed 6 | — | 11 / 647 (쓰기 8) — `100×losses ≤ eligible` 위반 |
| 개념어 0개면 기권(제품 이름 제외 정정 + 직접 alias 반영) | 0 | held_out 1 (h-011, 읽기) | 4 / 647 |
| **1위 작업 어휘가 질의의 내용 토큰을 하나도 덮지 않으면 기권(§3.2a 채택안)** | **0** | **held_out 1 (h-011, 읽기), negative 1 (n-001, 쓰기 POST)** | **1 / 647** (`Add comment` — 두 토큰 모두 동사 키) |

첫 행의 손실은 대부분 `board`·`sprint`·`epic`·`backlog`처럼 **제품 힌트 키이면서 카탈로그 개념어인 토큰**을 v1.3 `head_info`가 힌트로 보고 버렸기 때문이다(§3.2 정정). 이 정정으로 `head_info`가 달라지는 학습 레코드는 5건이다: s-008·s-031·s-034는 None → `backlog`/`board`, s-016(`add issue to sprint`)은 `issue` → `sprint`, s-021(`move issue to backlog`)은 `issue` → `backlog`. s-016·s-021은 "마지막 개념어" 규칙상 목적지 명사가 머리 명사로 잡히는 경우로, R1 쓰기 기권에 미치는 영향은 §3.5 H 채택 측정의 손실 목록으로 확인한다.

남은 세 건의 원인: n-003은 질의가 "jira"를 명시했는데 Confluence 쓰기 작업 추천(제품 불일치), rn-006 "remove page"는 실제로 `DELETE /pages/{id}`가 정답인데 기존 regression negative 레코드가 "정답 없음"이 아니라 "금지 작업이 1위가 아님"으로 정의돼 있었다(§4.3 라벨 이관), s-004는 상속된 constants/ordering 문제(bulk 전환이 1위).

## 1. 목표

1. 새 Discovery 게이트(§4.1)를 새 봉인 hidden set의 단일 평가로 통과한다.
2. Runtime stability(§18) 측정을 Round 6 시작과 함께 개시하고, 로그로 실사용 지표를 함께 기록한다(§6).
3. 쓰기 작업 오추천 0을 상시 회귀 기준으로 고정한다(§4.2).

## 2. 범위

포함: Phase 2.5 스펙 §18 Discovery 행 개정(§4.1), §8 검색 로그 확장(§6), 스코어러 추천·기권·동점 규칙(§3), Round 5 hidden의 §7.3 승격과 negative 라벨 이관(§4.3), 실데이터 T 리허설과 검수 상한(§5).
제외: Template/validation 축, 새 문서 코퍼스 수집, top-1 게이트, Round 5 KU registry 이월(§4.2), 실사용 로그 질의의 이번 봉인 평가 사용.

## 3. 스코어러

Round 6은 **H에서만** `search.py`·`policy.py`·`search_ranking.json` 구조를 바꾼다. T 이후(B..C 포함) 스코어러 코드와 정책 구조는 H 최종 커밋(`housekeeping_commit`)과 바이트 동일하며, B..C 튜닝은 상속대로 `constants` 값과 alias만 고른다. 새 규칙은 수치 상수를 추가하지 않는다(불리언 규칙). `POLICY_VERSIONS["search"]`는 5로 올린다.

### 3.1 추천 판정 (payload 계약)

`actionable := method_intent_consistent ∧ abstain_reason is None`, `recommended_operation := shown[0].key if actionable else None`. payload에 `abstain_reason ∈ {None, "no_method_intent", "no_resource_evidence", "product_conflict", "uncovered_head_resource"}`를 추가한다(`no_method_intent`는 기존 `method_intent_consistent == false`에 해당; `no_resource_evidence`는 v1.4 R0). 여러 사유가 동시에 성립하면 우선순위 `no_method_intent > no_resource_evidence > product_conflict > uncovered_head_resource`로 하나만 기록한다(검수 1 P1-4; v1.4: 대상 자체가 없는 경우가 대상 불일치보다 앞선다). 결과 목록(`results`)과 순위는 기권과 무관하게 그대로 반환한다 — 에이전트는 목록을 계속 볼 수 있다.

### 3.2 R1 머리 명사 기권 (쓰기 추천만)

- 머리 명사 정보 `head_info(q) -> {concept, original_token, number}`를 **한 번에** 계산한다(검수 1 P1-3): 질의 원문 토큰을 순서대로 보며 각 토큰의 단수형(`singular`)을 만들고, 동사(`verb_methods` 키)와 **제품 이름 토큰**(`PRODUCT_NAME_TOKENS` := 소스 이름 `sources.SOURCES`를 `tokenize_unigrams`한 합집합 = 현재 `{confluence, jira, platform, software}`; v1.4 정정 — v1.3은 `product_hints` 키 전체를 뺐으나 그중 `board`·`sprint`·`epic`·`backlog`는 개념어다)을 뺀 뒤, 단수형이 **카탈로그 개념어 집합**(path literal 토큰 ∪ tag 토큰, `path_noise` 제외 — Round 3부터의 `concept_tokens`와 같은 정의, 캐시 registry에서 계산)에 속하는 토큰 중 **마지막** 것을 고른다. `concept`=단수형, `original_token`=원문 토큰, `number`= 원문이 단수형과 같으면 `singular`, 원문이 단수형+`s`/`es`이면 `plural`, 그 밖(불규칙·불변)은 `unknown`. 해당 토큰이 없으면 `head_info = None`이고 R1·R3은 적용되지 않는다.
- 1위 작업 `top`의 메서드가 POST·PUT·PATCH·DELETE이고, `head_info(q).concept`가 `top`의 어휘(operationId·path literal·summary·tag 토큰)에도, 그 concept의 alias 타깃(직접 alias, 정책 파일)에도 없으면 `abstain_reason = "uncovered_head_resource"`.
- GET 추천에는 적용하지 않는다(설계 측정상 GET까지 적용하면 맞는 추천 손실이 커짐; 읽기 오추천은 §4.1 정확도 지표가 별도로 잡는다). 근거가 **전혀 없는** GET 추천은 R0(§3.2a)가 막는다.

### 3.2a R0 근거 없음 기권 (전 메서드, v1.4)

- **내용 토큰** `content(q)` := `tokenize_unigrams(q)`에서 동사(`verb_methods` 키)와 `PRODUCT_NAME_TOKENS`(§3.2)를 뺀 토큰들(질의 순서). 개념어 여부는 보지 않는다 — 처음 보는 단어도 내용 토큰이다.
- **덮음:** 토큰 `t`가 1위 작업 `top`에 덮인다 := `token_forms(t) ∪ (t의 직접 alias 타깃들의 token_forms)`가 `top`의 어휘(R1과 같은 정의: operationId·path literal·summary·tag 토큰)와 교집합을 가진다.
- `content(q) = ∅`이거나, `content(q)`의 어떤 토큰도 `top`에 덮이지 않으면 `abstain_reason = "no_resource_evidence"`. **GET을 포함한 모든 메서드에 적용한다.**
- R1과의 관계: R0는 "1위가 질의의 무엇이든 하나라도 반영하는가"(약한 하한, 전 메서드), R1은 "1위가 질의의 대상(머리 명사)을 반영하는가"(강한 조건, 쓰기만)다. R0를 통과해도 R1에 걸릴 수 있다.
- 알려진 손실(§0 측정): 내용 토큰이 모두 동사 키인 질의(`add comment` — `comment`는 동사 키이자 개념어)는 기권한다. 동사 키 재정의는 이번 범위 밖이며, §3.5 측정의 손실 목록으로 보고한다.
- **정확 지목(검수 4 P1-1):** 질의가 canonical key 또는 operationId와 정확히 일치해 1위가 핀된 경우(`exact_match`이고 핀된 작업이 그 지목 대상), 그 지목 자체를 근거로 인정해 R0를 만족한 것으로 본다 — `addComment`처럼 토큰이 모두 동사 키여서 `content(q) = ∅`인 식별자 검색도 추천을 유지한다(AGENTS.md의 정확 식별자 검색 흐름). 그 밖의 경우(핀이 없거나 핀이 지목 대상이 아님)에는 일반 R0 규칙이 그대로 적용된다. 정확 지목은 R1·R2를 면제하지 않는다. §8 테스트로 고정한다.

### 3.3 R2 제품 불일치 기권

질의 토큰에 제품 힌트가 있고(정책 `product_hints` → 소스 매핑, 상속), 그 힌트가 가리키는 소스 집합에 `top`의 소스가 없으면 `abstain_reason = "product_conflict"`. 모든 메서드에 적용한다.

### 3.4 R3 단건/목록 동점

정렬 키에서 최종 점수가 **정확히 같은** 두 후보가 같은 소스·같은 메서드이고 한쪽 path가 다른 쪽 path + `/{param}` 한 단계일 때: `head_info(q).number == singular`이면 단건(`{param}`로 끝나는) 쪽을, `plural`이면 목록 쪽을 앞에 둔다. `unknown`이거나 `head_info`가 없으면 적용하지 않는다. 점수가 다르면 작동하지 않는다(정렬 규칙 `ordering_rules`의 새 플래그 `singular_collection_tiebreak`, H 기본값 true).

### 3.5 채택 기준과 scorer-rule counterexample

상속 counterexample 스위트는 alias/phrase 정책 diff만 관찰하므로 R0–R3(추천 판정·동점 정렬 변화)을 볼 수 없다(검수 1 P0-3). R0–R3은 별도의 **scorer-rule counterexample**로 검사한다. OFF = R0–R3 네 규칙 모두 끔, ON = 모두 켬; 개별 OFF 진단에 R0 포함.

- **코퍼스와 바인딩(검수 2 P1-3):** Round 6 S(컨트롤러가 H 채택 측정 **전에** 만드는 실제 스냅샷; §5.1)의 모든 작업에 대해 `summary`를 질의로 쓰는 summary-as-query 코퍼스(빈 summary 제외)를 결정적으로 생성한다. 코퍼스는 benchmark·seed·hidden id를 읽지 않는다. 메타데이터 `{registry_fingerprint, operation_count, corpus_sha256, generator_sha256}`를 H 측정 전에 원장에 고정하고, `registry_fingerprint == Round 6 S` 바인딩 검사를 H 채택·리허설·pre-T·B..C 모두에서 수행한다.
- **비교:** 같은 constants·같은 aliases에서 R0–R3을 모두 끈 정책(OFF)과 켠 정책(ON)으로 코퍼스를 평가한다. 각 질의의 자기 작업(summary의 원 작업)을 정답으로 본다.
- **손실:** OFF에서 "추천 = 자기 작업"이던 질의가 ON에서 기권 또는 다른 추천으로 바뀐 경우. `eligible` = OFF에서 추천이 자기 작업인 질의 수(검수 2 P1-2). 쓰기 손실과 읽기 손실을 나눠 기록한다.
- **hard 계약(검수 2 P0-4):** `scorer_rule_ok := eligible > 0 ∧ 100 × losses ≤ eligible`(검수 3 P1-2: 분모 0이면 실패). 이 기준을 넘으면 그 규칙 조합은 채택·수용될 수 없다. 개별 규칙 OFF 측정은 원인 진단과 "어떤 규칙을 끌지" 결정에만 쓰고, 최종 켜진 규칙 집합은 다시 조합 평가로 `scorer_rule_ok`를 만족해야 한다. 기준 자체를 바꾸는 것은 스펙 개정이며 검수 판정으로 예외를 줄 수 없다.
- **결과 메타데이터(검수 4 P1-4):** 모든 scorer-rule 결과는 `{registry_fingerprint, ranking_structure_sha256, verb_methods_sha256, aliases_sha256, constants, enabled_rules, corpus_sha256, losses, gains, eligible}`를 함께 기록한다.
- **적용 시점(검수 2 P0-3):** (1) H 채택: H 정책(Round 5 constants, H aliases)에서. (2) pre-T: production dry-run의 **선택 constants + 최종 working aliases**에서(OFF/ON 모두 같은 최종 constants·aliases). (3) B..C: 워커 실행의 최종 선택 정책에서 같은 방식으로. (2)·(3)의 결과는 `tuning_accept`의 항이다(§4.2).
- **H 채택 조건(검수 2 P0-1):** `scorer_rule_ok` ∧ ON에서 `wv_on ≤ wv_off` ∧ `fr_on ≤ fr_off` ∧ ON에서 §4.2 `accept(m)`의 지표 하한을 만족(Round 5 constants 기준). 개별 맞는 추천이 줄어드는 것은 하한을 지키는 한 허용된다(R1의 목적은 일부 추천을 기권으로 바꾸는 것이다). 모든 손실 목록(작업 key·사유)은 readiness와 검수 스레드에 보고한다.
- 규칙 정의는 이 스펙에 고정되며, H 이후 규칙 형태를 바꾸는 것은 스펙 개정이다.

## 4. 평가와 게이트

### 4.1 Discovery 게이트 (Phase 2.5 스펙 §18 Discovery 행 대체)

새 봉인 hidden set(held_out 16 + negative 8, 상속 생성·검토·봉인 절차)의 **단일 평가**로 판정한다.

| 지표 | 정의 | 기준 |
|---|---|---|
| 도달 | held_out 중 기대 작업이 결과 상위 3위 안에 있는 수 | ≥ 15/16 |
| 추천 커버리지 | held_out 중 추천을 낸 수 | ≥ 14/16 |
| 추천 정확도 | held_out에서 추천을 낸 경우 중 추천이 기대 작업인 비율 | `10 × correct ≥ 9 × recommended` (추천 0건이면 실패) |
| 쓰기 안전 | held_out·negative에서 틀린 추천 중 메서드가 POST·PUT·PATCH·DELETE인 수 | = 0 |
| 기권 | negative 중 추천을 내지 않은 수 | ≥ 7/8 |

모든 비율은 반올림 없이 정수 분수로 비교한다(검수 1 a). 커버리지 하한 때문에 "한두 건만 추천하고 나머지 기권"으로는 통과할 수 없다(검수 1 P0-1). top-1 정답률·actionable 분할은 기록만 한다(게이트 아님). hidden negative 생성 규칙은 "카탈로그에 정답이 없는 질의"(상속)이고, 모든 hidden negative는 `no_answer: true`다.

### 4.2 학습 지표, selector, 제안기, 수용 (Round 5 §4.1–4.2 대체)

**대체 범위(검수 1 P0-2):** 이 절은 Round 5 §4.1–4.2의 KU registry·reachable 계산·`select_candidate` 목적함수·제안기 trial 수용·regression effective/raw 수용 의미를 **전부 대체**한다. fixture 계약(`fixture_positive == 23/23`, `fixture_negative_raw == 6/6`, fixture 실패 격자점 사전 제외), alias counterexample 스위트(§8 상속), 수명주기·dry-run 계약만 상속한다. `KNOWN_UNREACHABLE[6] = ()`.

**학습 집합(§4.3 이후):** `seed`(Round 5 39 + 승격 16 = 55), `regression_positive`(기존 regression_negative 중 `no_answer: false`로 판정된 레코드), `regression_negative`(`no_answer: true`인 기존 레코드 + 승격 8).

**격자점 지표 벡터** `m(point)` (모두 정수):
- `wv` = seed·regression_positive·regression_negative 전체에서 틀린 쓰기 추천 수,
- `fr` = `forbidden_top1`이 추천된 레코드 수(전 집합),
- `sr3` = seed 중 기대 작업이 상위 3위 안인 수,
- `src` = seed 중 추천을 낸 수, `srk` = seed 중 추천이 기대 작업인 수,
- `rpk` = regression_positive 중 추천이 기대 작업인 수, `rp3` = regression_positive 중 상위 3위 안인 수,
- `nab` = regression_negative 중 기권 수.

**수용 조건** `accept(m)` := `wv == 0 ∧ fr == 0 ∧ 10·sr3 ≥ 9·|seed| ∧ 10·src ≥ 9·|seed| ∧ 10·srk ≥ 9·src ∧ rp3 == |regression_positive| ∧ rpk == |regression_positive| ∧ 8·nab ≥ 7·|regression_negative|`. `tuning_accept := accept(m(selected)) ∧ fixture 계약 ∧ alias counterexample(counterexample_loss_at_selected == [] ∧ uncovered_proposer_keys == []) ∧ scorer_rule_ok(selected constants, final aliases)(§3.5) ∧ validation_errors == []`.

**selector:** fixture 통과 격자점 중 `accept(m) ∧ scorer_rule_ok(point, 현재 working aliases)`인 점이 있으면 그중 Round 3 보수적 tie-break(상속)로 고른다(검수 3 P1-5). 제안기 이후 최종 aliases에서 `scorer_rule_ok`를 다시 검사하는 것은 그대로다. 없으면 다음 사전식 순서로 최선의 점을 고른 뒤 같은 tie-break: `(wv 최소, fr 최소, sr3 최대, srk 최대, src 최대, rp3 최대, rpk 최대, nab 최대)`. 이 순서에는 `accept`에 쓰이는 지표 구성요소가 정확히 한 번씩 나오며, 테스트가 이를 machine-check한다(검수 2 P1-1).

**제안기(검수 2 P0-2):** 입력 = **모든 수용 위반 레코드** — seed·regression_positive: 상위 3위 밖, 추천 없음(기권), 틀린 추천, 쓰기·금지 위반 중 하나; regression_negative: 추천을 냄, 또는 쓰기·금지 위반. trial alias의 **대상 개선**은 유형별로: positive 레코드는 상위 3위 진입 또는 추천이 기대 작업으로 바뀜, negative 레코드는 추천 → 기권, 안전 위반 레코드는 위반 추천이 사라짐. trial은 대상 개선 ∧ 전역 `wv`·`fr` 불증가 ∧ 나머지 지표(`sr3, src, srk, rp3, rpk, nab`) 불감소일 때만 채택한다. 원자 액션 예산은 상속.

**pre-T 게이트:** dry-run 결과에 `tuning_accept`를 적용하며, 실패는 blocker kind `metric_threshold`(항목 이름·값·기준)로 보고한다. regression raw/effective(Round 5의 14/14)는 기록만 한다.

### 4.3 Round 5 hidden 승격과 라벨 이관 (§7.3)

**순서(검수 3 P1-3):** Round 6 S 생성 → 승격 → 승격 payload sha 봉인 → 재라벨 → 학습 분할 sha 고정 → §3.5 H 채택 측정 → whole-branch 리뷰 → 리허설.

**승격:**
- held_out-r5 16개 → `seed`로 승격, id `s-040`…`s-055`(원래 id 순서), `origin: "promoted-r5"`.
- negative-r5 8개 → id `rn-015`…`rn-022`, `origin: "promoted-r5"`; 최종 섹션은 재라벨이 정한다.
- 승격 레코드는 `promoted_from = {round: 5, split, source_id, source_record_sha256}`를 갖는다. 승격 직후의 payload(`promotion_identity(r)` := `r`에서 `{id, origin, promoted_from}`과 재라벨 필드 `{no_answer, label_migration}`, 그리고 재라벨이 정한 경우의 `expected_top1_any`를 뺀 레코드)의 sha를 재라벨 **전에** 원장에 봉인하며, 이것이 원본(Round 5 unseal 레코드)에서 `{id, origin}`을 뺀 것과 같아야 한다(검수 1 P0-4, 검수 3 P0-2).

**재라벨 대상(검수 3 P0-2):** 기존 regression_negative 14개 **+ 승격 negative 8개 = 22개** 전부. Round 5에서 정답이 없던 질의도 Round 6 S에서는 정답 작업이 생겼을 수 있기 때문이다.

**재라벨 절차:** 라벨은 **카탈로그 사실**(Round 6 S에 정답 작업이 존재하는가)로 정하며 엔진 결과도 기존 `forbidden_top1`도 보지 않는다(검수 1 P1-5): stateless 검토자 **두 명**(서로 다른 Temporary chat, Round 6 S 카탈로그 첨부, **질의만** 제시)이 각각 `{answerable: bool, acceptable_keys: [...]}`를 낸다. 출력 스키마는 machine-check한다(검수 2 P1-4): `answerable == true ↔ acceptable_keys` 비어 있지 않음, `answerable == false ↔ acceptable_keys == []`, `acceptable_keys`는 정렬·중복 없음, 모든 key가 Round 6 S 카탈로그에 존재; 두 검토의 비교는 집합 기준; 다르면 세 번째 stateless 검토자(같은 입력·같은 스키마)가 판정한다.
- answerable → `regression_positive`, `expected_top1_any = acceptable_keys`, `no_answer: false`.
- not answerable → `regression_negative`, `no_answer: true`.
- 각 레코드에 `label_migration = {reviewers: [actor ids], review_output_sha256s, adjudicated: bool}`을 남긴다.

**금지 라벨 정합(검수 3 P0-1):** 재라벨 후 불변식 `active forbidden_top1 ∩ expected_top1_any == ∅`. 기존 `forbidden_top1` 중 `acceptable_keys`에 든 key는 `legacy_forbidden_top1`(provenance 전용, 지표 미사용)로 옮기고 active `forbidden_top1`에서 뺀다; acceptable 밖의 key만 active로 남는다. 검토자는 기존 forbidden을 보지 않았으므로 이것은 평가 맞추기가 아니라 독립 라벨 둘의 정합이다.

**카탈로그 폐포(검수 3 P1-1):** 모든 seed·regression_positive 레코드의 `expected_top1_any`를 Round 6 S 카탈로그와 교차한다. 사라진 key는 레코드에 `catalog_missing_keys`로 기록하고 active 목록에서 뺀다; active 기대 key가 하나도 남지 않는 레코드가 있으면 지표 실패로 흘리지 않고 **라벨/카탈로그 이관 문제로 STOP**(검수 스레드 판정).

**범위:** 승격·이관은 benchmark 파일의 seed·regression 섹션만 바꾸고 새 섹션 `regression_positive`를 추가한다. 이 변경은 Round 6 H 산출물(T 이전 커밋, T allowlist 밖)이며, `search_queries.json` 구조 sha와 `regression_reference_sha256`은 새 값으로 기록된다. 재라벨 검토 입력·출력 sha와 actor id는 원장에 남는다.

## 5. 절차 델타

1. **pending round 등록과 S 선행 생성:** H에서 `PRE_FREEZE_NONVERB_STRUCTURE_SHA256[6]`을 Round 6 H 구조로 등록하고 `pending_round() == 6`. Round 6 S(live fetch 1회, 상속 규칙)는 §4.3 순서의 맨 앞이다; 이후 승격·재라벨·H 채택 측정·리허설·pre-T·B..C·D는 같은 S를 쓴다.
2. **실데이터 T 리허설(H 완료 조건):** H 최종 커밋에서, 실제 S와 실제 입력으로 저장소의 임시 복사본을 만들어 다음을 한 번 수행한다: 사전 해소(필요 시), candidates·classify·carry, freeze, 전체 스위트(T 상태), dry-run pre-T, 워커 handshake 형식 검사. 실패는 H′로 고친다. 결과는 `rehearsal_report`로 원장에 남긴다. 리허설은 hidden set을 만들지 않으며 봉인 이전이다.
3. **검수 상한:** 스펙·계획 검수는 P0 0건이면 통과(P1은 다음 버전에 반영, 재검수 없음). 스펙 검수는 4회를 목표 상한으로 하고, 넘으면 범위 축소 여부를 검수 스레드에서 판정받는다.
4. **hidden 전송 절차화:** 생성기·검토자 응답은 대화 API로 읽어 브라우저 해시와 대조한 청크로 옮긴다(Round 5 절차를 스크립트화). 숨김 텍스트는 원장에 해시로만 남는다.
5. 단일 평가·봉인·행위자 분리·검수 스레드 판정은 상속 그대로다.

## 6. Runtime stability와 검색 로그 (Phase 2.5 스펙 §8 개정)

- **등록(사용자 실행, Round 6 시작 시):** 사용자 범위 MCP 등록, 실행 위치는 저장소로 고정, `ATLASSIAN_DOCS_SEARCH_LOG=1`. 등록 시각을 원장 `runtime_observation_started`로 기록한다(관찰 시작).
- **자격 구간(검수 1 P1-1, 검수 3 P1-4):** 자격은 **현재 채택된** `intelligence_fingerprint`에 묶인다. 지문이 바뀌면(H 최종, B..C 채택 등) 이전 관찰은 기록으로만 남고 `runtime_stability_qualifying_start`가 새 지문의 반영 시각으로 다시 시작하며, 7일·100회는 새 지문의 레코드로만 센다.
- **로그 확장(H):** `search_operations` 레코드에 `actionable`, `recommended_operation`, `abstain_reason`, `method_intent_consistent`를 추가한다. `get_operation`·`build_request_template` 호출은 별도 레코드 `{"ts", "kind": "selection", "tool", "key", "intelligence_fingerprint", "server_session_id", "call_seq"}`로 같은 파일에 남긴다(인자 값·헤더는 기록하지 않음). 모든 레코드는 `server_session_id`(MCP 서버 프로세스 시작 시 만든 무작위 uuid)와 `call_seq`(프로세스 내 증가 정수)를 가진다. 선택-추천 매칭은 같은 `server_session_id` 안에서 selection보다 앞선 `search_operations` 레코드 중 **결과 목록(로그의 상위 key)에 선택 key를 포함한 가장 최근 검색**으로 결정적으로 정하고, 그런 검색이 없으면 매칭하지 않는다(검수 2 P1-5). 이를 위해 검색 레코드의 `top`은 상위 10개 key를 담는다. 지표 이름은 "결과 포함 검색 기준 일치율"이다. 파일 권한·회전·OSError 무시는 상속.
- **판정:** 로그 기간이 7일 이상이고 `search_operations` 레코드가 100개 이상이면 Runtime stability 충족으로 readiness에 기록한다. 같은 기록에 로그 기반 참고 지표(추천 후 같은 세션에서 선택된 key와 추천의 일치율, 쓰기 추천 수)를 남긴다(게이트 아님).
- **실사용 질의:** 로그의 실패 질의는 §7.3대로 다음 라운드 seed 후보다. Round 6 봉인 평가에는 쓰지 않는다. 로그는 저장소 밖(캐시 디렉터리)에만 있으며 커밋하지 않는다.

## 7. 도구 변경 요약

- `tools/atlassian_docs/intelligence/search.py`: §3.1–3.4 (abstain_reason, R0–R3, `PRODUCT_NAME_TOKENS`, `content(q)`).
- `tools/atlassian_docs/intelligence/policy.py` / `data/search_ranking.json`: `ordering_rules.singular_collection_tiebreak`, 구조 sha 갱신, `POLICY_VERSIONS["search"] = 5`.
- `tools/atlassian_docs/intelligence/search_log.py`, `mcp/` 도구 계층: §6 로그 필드와 selection 레코드.
- `tests/benchmarks/evaluator.py`: §4.1·§4.2 지표 계산(`reach_at_k`, `rec_precision`, `write_safety_violations`, `no_answer_abstention`, `forbidden_recommended`), `KNOWN_UNREACHABLE[6] = ()`, `ROUND6_EXTRA_KEYS`, `TestSealIntegrity.test_hidden_plaintext_machine_rules`의 `verb_methods` 전달 수정(Round 5 교훈 3).
- `tests/tune_search_ranking.py`: `tuning_accept`·pre-T blocker·제안기 입력을 §4.2로.
- `tests/diag_search_queries.py`: 새 지표 출력과 `no_answer` 처리, 최종 산출물 `round6-final.json`.
- `tests/benchmarks/round6_simulation.py`: 상속 수명주기 + §5.2 리허설 모드(`--phase rehearsal`).
- benchmark: §4.3 승격·라벨 이관.

## 8. 테스트 전략 델타

- R0 일반어 진단(검수 4 P1-2, 게이트 아님): `delete id`, `get data`, `get user`의 기권/추천 결과를 기록 테스트로 고정하고 readiness에 남긴다(약한 하한의 알려진 한계; 실사용 로그에서 많으면 다음 라운드 confidence 규칙 후보).
- 정확 지목(검수 4 P1-1): `addComment`, `jira-platform:POST:/rest/api/3/issue/{issueIdOrKey}/comment` → 추천 유지(R0 근거로 인정); 정확 지목이 아닌 동사만 질의는 기권.
- R0(v1.4): `delete`·`delete something`·`delete xyzzy`·`create`·`jira delete` → 기권(`no_resource_evidence`); `get something` → 기권(GET에도 적용); `delete board`·`get myself`·`create issue` → 추천 유지; 내용 토큰이 alias 타깃으로만 덮여도 추천 유지; operationId·key 정확 일치 질의 → 추천 유지; `add comment` → 기권(알려진 손실 고정); R0 기권 시 `results` 불변.
- `PRODUCT_NAME_TOKENS`가 `sources.SOURCES`에서 파생되고 `board`·`sprint`·`epic`·`backlog`를 포함하지 않음; `head_info("remove this agile board").concept == "board"`, `head_info("filter owner jira").concept == "owner"`.
- R1: 쓰기 추천 + 머리 명사 미반영 → 기권; 같은 경우 GET → 추천 유지; 머리 명사가 alias 타깃으로 반영되면 추천 유지; 개념어 없음 → 미적용.
- R2: 질의 "jira" + Confluence 1위 → 기권; 힌트 없음 → 미적용.
- R3: 정확한 동점 + 단수 머리 명사 → 단건 앞; 복수 → 목록 앞; 점수 차 → 순서 불변; 플래그 false → 상속 정렬과 바이트 동일.
- 결과 목록 불변: 기권해도 `results`의 순서·점수는 R0·R1·R2 이전과 같다.
- 기권 사유 우선순위: `no_method_intent > no_resource_evidence > product_conflict > uncovered_head_resource`(동시 성립 조합 각각).
- 지표 함수: 손으로 만든 작은 결과 집합으로 각 지표 경계값(15/16, 90%, 0, 7/8) 검증.
- 라벨 이관: `no_answer` 필드 스키마, `regression_positive` 섹션 스키마, 승격 id·origin·`promoted_from` 검사, `promotion_identity` 동일성(§4.3).
- 지표·selector·제안기(§4.2): 손으로 만든 격자 결과에서 수용 풀·사전식 fallback·제안기 trial 거부(쓰기 위반 증가, 다른 지표 감소) 각각의 단위 테스트; 정수 분수 경계(14/16, 9/10, 7/8).
- scorer-rule counterexample(§3.5): 코퍼스 생성이 benchmark를 읽지 않음, 결정성(sha 고정), S 바인딩 불일치 시 실패, `eligible` 분모, OFF/ON이 같은 constants·aliases를 씀, `tuning_accept`가 `scorer_rule_ok` 거짓이면 거짓.
- 제안기 입력 일반화: regression_positive만 실패·regression_negative만 오추천·기권한 seed·안전 위반만 있는 경우 각각 입력에 포함되고 유형별 대상 개선이 판정됨.
- 재라벨 스키마 machine-check와 집합 기준 비교; `forbidden ∩ expected` 정합(legacy 이동); 카탈로그 폐포(누락 key 기록, 전부 누락 시 STOP); `scorer_rule_ok`의 `eligible == 0` 실패.
- `head_info`: 단수·복수·불규칙(unknown)·개념어 없음; 기권 사유 우선순위.
- 로그: 새 필드·selection 레코드·`server_session_id`·`call_seq`, 인자 값 미기록, 권한 0600; 자격 구간 계산(지문 필터).
- 리허설: `round6_simulation --phase rehearsal`이 임시 복사본에서만 쓰기(작업 트리 불변) 테스트.

## 9. 상태 모델·readiness 델타

- readiness Round 6 기록: §4.1 다섯 지표(기준·결과), top-1(기록), §4.2 학습 지표, R0–R3 채택 측정(§3.5), 승격·라벨 이관 요약, 리허설 결과, Runtime stability 시작 시각과 판정 상태.
- Phase 2.5 스펙에 §18·§8 개정 각주를 추가한다(H 커밋, 문서만).

## 10. Acceptance Criteria (델타)

| AC | 기준 | 검증 |
|---|---|---|
| AC-R6-01 | payload `actionable`·`recommended_operation`·`abstain_reason`이 §3.1 계약대로; 기권해도 `results` 불변 | unit |
| AC-R6-02 | R0·R1·R2·R3이 §3.2–3.4(§3.2a 포함) 정의대로 동작하고 R3 플래그 false에서 상속 정렬과 동일; §8 R0 질의 표와 `PRODUCT_NAME_TOKENS`·`head_info` 정정 케이스 통과 | unit |
| AC-R6-03 | §3.5 scorer-rule counterexample: 코퍼스 메타데이터 고정·S 바인딩, `100 × losses ≤ eligible`(hard), H 채택 조건(안전 비악화 + 지표 하한), pre-T·B..C 최종 정책 재검사가 `tuning_accept`에 포함, 손실 목록 보고 | unit + ledger |
| AC-R6-04 | §4.1 지표(도달·커버리지·정확도·쓰기 안전·기권) 함수가 정수 분수 비교로 계산되고 최종 산출물·readiness에 기준과 함께 기록됨 | unit + 산출물 |
| AC-R6-05 | §4.2가 Round 5 §4.1–4.2를 대체: 지표 벡터, `accept`, selector(수용 풀·사전식 fallback), 제안기 입력과 trial 수용, pre-T blocker(`metric_threshold`)가 정의대로; `KNOWN_UNREACHABLE[6] == ()` | unit |
| AC-R6-06 | §4.3: 실행 순서, 승격 id·origin·`promoted_from`·선봉인 `promotion_identity` 동일; 재라벨 22개가 이중 독립 검토(불일치 시 3자 판정)·스키마 검사와 함께 원장에 있음; answerable → `regression_positive`; `forbidden ∩ expected = ∅`(legacy 이동); 카탈로그 폐포 검사 | unit + ledger |
| AC-R6-07 | §5.2 리허설이 H 최종 커밋에서 수행되고 실패 0으로 `rehearsal_report` 기록 | ledger |
| AC-R6-08 | §6 로그 필드·selection 레코드·세션 상관키·권한; `runtime_observation_started`·`runtime_stability_qualifying_start` 기록, 자격 집계는 현재 채택 지문만(변경 시 재시작) | unit + ledger |
| AC-R6-09 | T 이후 `search.py`·`policy.py`·`search_ranking.json` 구조가 `housekeeping_commit`과 동일(값 채택 경로 상속) | git diff |

## 11. 위험과 완화

- **규칙이 hidden에서 맞는 추천을 기권으로 바꿈:** 추천 커버리지 하한(≥ 14/16, 학습 ≥ 90%)이 과잉 기권을 직접 막고, scorer-rule counterexample이 카탈로그 전체에서 손실을 잰다.
- **머리 명사 정의가 영어 어순에 의존:** 짧은 명령형 질의(현 benchmark·실사용 형태)에서 마지막 개념어가 대상인 경우가 다수다. 예외는 §3.5 측정과 counterexample 스위트에 드러나고 판정 대상이 된다.
- **라벨 이관이 평가 맞추기로 변질:** 라벨은 엔진 결과를 보지 않는 stateless 검토가 카탈로그 사실로 정한다; 검토 입력에 엔진 출력이 없음을 원장에 기록한다.
- **실사용 로그 민감정보:** 저장소 밖 보관·커밋 금지·소유자 전용 권한.
- **s-004 같은 상속 쓰기 오추천이 pre-T에서 남음:** `write_safety_violations == 0`을 막는 blocker로 보고되며, 해결은 R0–R3 범위 안 또는 스펙 개정 판정으로만 한다.

## 12. 한 줄 정의

Round 6 = 실사용 기준 게이트(도달·추천 정확도·쓰기 안전·기권) + 추천/기권 규칙(R0 근거 없음, R1 머리 명사, R2 제품 불일치, R3 단건/목록 동점) + Runtime stability 측정 개시 + 실데이터 T 리허설.

## 13. 구현 계획 입력

- H 순서 제안: H18 지표·라벨 스키마·evaluator(§4, §7) → H19 스코어러 R0–R3·payload(§3) → H20 로그·MCP(§6) → H21 승격·재라벨 도구와 round6_simulation·리허설(§4.3, §5.2) → [컨트롤러: S 생성 → 승격·재라벨 → 학습 분할 sha → §3.5 H 채택 측정] → whole-branch 리뷰 → 리허설 → 컨트롤러 T 이후.
- 라벨 이관 검토(§4.3)와 R0–R3 채택 측정(§3.5)은 H 안의 컨트롤러 단계이며 검수 스레드 판정을 받는다.
