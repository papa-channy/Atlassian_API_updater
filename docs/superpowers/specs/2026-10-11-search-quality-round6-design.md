# Search Quality Round 6 — Technical Specification

**문서 버전:** v1.0 (2026-10-11; 사용자 승인 섹션 1–4 기반 초안)
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

`actionable := method_intent_consistent ∧ abstain_reason is None`, `recommended_operation := shown[0].key if actionable else None`. payload에 `abstain_reason ∈ {None, "no_method_intent", "uncovered_head_resource", "product_conflict"}`를 추가한다(`no_method_intent`는 기존 `method_intent_consistent == false`에 해당). 결과 목록(`results`)과 순위는 기권과 무관하게 그대로 반환한다 — 에이전트는 목록을 계속 볼 수 있다.

### 3.2 R1 머리 명사 기권 (쓰기 추천만)

- 머리 명사 `head(q)`: 질의 정규화 토큰(`norm_tokens`, 단수화)에서 동사(`verb_methods` 키)·제품 힌트(`product_hints`)를 뺀 뒤, **카탈로그 개념어 집합**(path literal 토큰 ∪ tag 토큰, `path_noise` 제외 — Round 3부터의 `concept_tokens`와 같은 정의, 캐시 registry에서 계산)에 속하는 토큰 중 **마지막** 것. 없으면 R1은 적용되지 않는다.
- 1위 작업 `top`의 메서드가 POST·PUT·PATCH·DELETE이고, `head(q)`가 `top`의 어휘(operationId·path literal·summary·tag 토큰)에도, `head(q)`의 alias 타깃(직접 alias, 정책 파일)에도 없으면 `abstain_reason = "uncovered_head_resource"`.
- GET 추천에는 적용하지 않는다(설계 측정상 GET까지 적용하면 맞는 추천 손실이 커짐; 읽기 오추천은 §4.1 정확도 지표가 별도로 잡는다).

### 3.3 R2 제품 불일치 기권

질의 토큰에 제품 힌트가 있고(정책 `product_hints` → 소스 매핑, 상속), 그 힌트가 가리키는 소스 집합에 `top`의 소스가 없으면 `abstain_reason = "product_conflict"`. 모든 메서드에 적용한다.

### 3.4 R3 단건/목록 동점

정렬 키에서 최종 점수가 **정확히 같은** 두 후보가 같은 소스·같은 메서드이고 한쪽 path가 다른 쪽 path + `/{param}` 한 단계일 때: 질의의 머리 명사가 단수형으로 쓰였으면(원문 토큰이 단수화 전과 같음) 단건(`{param}`로 끝나는) 쪽을, 복수형이면 목록 쪽을 앞에 둔다. 점수가 다르면 작동하지 않는다(정렬 규칙 `ordering_rules`의 새 플래그 `singular_collection_tiebreak`, H 기본값 true).

### 3.5 채택 기준 (H, seed·regression만)

R1–R3은 H에서 **seed·regression·fixture에서만** 측정해 채택한다(hidden 미관찰). 채택 조건: (a) seed·regression 전체에서 쓰기 오추천 수가 늘지 않고, (b) 상속 counterexample 스위트에 R1–R3을 끈 정책 대비 켠 정책의 손실(이전에 맞던 추천이 기권 또는 오답으로 바뀜)을 기록, (c) 손실이 생기면 그 목록과 사유를 readiness와 검수 스레드에 보고하고 판정을 받는다. 규칙 정의는 이 스펙에 고정되며, H 이후 규칙 형태를 바꾸는 것은 스펙 개정이다.

## 4. 평가와 게이트

### 4.1 Discovery 게이트 (Phase 2.5 스펙 §18 Discovery 행 대체)

새 봉인 hidden set(held_out 16 + negative 8, 상속 생성·검토·봉인 절차)의 **단일 평가**로 판정한다.

| 지표 | 정의 | 기준 |
|---|---|---|
| 도달 | held_out 중 기대 작업이 결과 상위 3위 안에 있는 수 | ≥ 15/16 |
| 추천 정확도 | held_out에서 추천을 낸 경우 중 추천이 기대 작업인 비율 | ≥ 90% (추천 0건이면 0%) |
| 쓰기 안전 | held_out·negative에서 틀린 추천 중 메서드가 POST·PUT·PATCH·DELETE인 수 | = 0 |
| 기권 | negative 중 추천을 내지 않은 수 | ≥ 7/8 |

top-1 정답률·actionable 분할은 기록만 한다(게이트 아님). hidden negative 생성 규칙은 "카탈로그에 정답이 없는 질의"(상속)이고, 모든 hidden negative는 `no_answer: true`다.

### 4.2 튜닝 수용과 pre-T 게이트

KU registry는 Round 6에 이월하지 않는다(`KNOWN_UNREACHABLE[6] = ()`): 새 지표는 비율 기준이라 개별 seed 면제가 필요 없다.

학습 집합 `seed`(Round 5 39 + 승격 16)와 `regression_negative`(Round 5 14 + 승격 8, §4.3)에서:

- `seed_reach3 ≥ 90%` (기대 작업이 상위 3위 안),
- `seed_rec_precision ≥ 90%`,
- `write_safety_violations == 0` (seed·regression_negative 전체에서 틀린 쓰기 추천 0),
- `no_answer_abstention ≥ 87.5%` (`no_answer: true`인 regression 레코드 중 기권 비율),
- `forbidden_recommended == 0` (`forbidden_top1`이 추천되면 위반; `no_answer: false` 레코드 포함),
- regression raw·fixture 계약은 상속(`fixture_positive == 23/23`, `fixture_negative_raw == 6/6`),
- counterexample 스위트 상속(`counterexample_loss_at_selected == []`, `uncovered_proposer_keys == []`).

`tuning_accept`는 위 항목의 논리곱이다. pre-T 게이트는 같은 항목을 dry-run 결과에 적용하며, 위반은 blocker kind `metric_threshold`(지표 이름·값·기준)로 보고한다. 제안기 입력은 "도달하지 못한 seed"(상위 3위 밖)와 "틀린 추천을 낸 seed"다.

### 4.3 Round 5 hidden 승격과 라벨 이관 (§7.3)

- held_out-r5 16개 → `seed`로 승격, id `s-040`…`s-055`(원래 id 순서), `origin: "promoted-r5"`, 레코드 내용 불변.
- negative-r5 8개 → `regression_negative`로 승격, id `rn-015`…`rn-022`, `origin: "promoted-r5"`, `no_answer: true`.
- 기존 regression_negative 14개에 `no_answer` 라벨을 붙인다. 라벨은 **카탈로그 사실**(정답 작업이 존재하는가)로 정하며 엔진 결과를 보지 않는다: 각 레코드에 대해 stateless 검토(상속 Temporary chat, 카탈로그 첨부, 질의·`forbidden_top1`만 제시)로 "정답 작업이 있는가, 있으면 무엇인가"를 받는다. 정답이 있으면 `no_answer: false`와 `expected_top1_any`(검토 결과)를 기록하고, 정답이 없으면 `no_answer: true`. 라벨 이관은 H 산출물(T 이전 커밋)이며 원장에 검토 출력 sha를 남긴다.
- 승격·이관은 benchmark 파일의 **seed·regression 섹션만** 바꾼다. 이 변경은 Round 6 H 커밋에 속하며(T allowlist 밖), `search_queries.json` 구조 sha와 `regression_reference_sha256`은 새 값으로 기록된다.

## 5. 절차 델타

1. **pending round 등록:** H에서 `PRE_FREEZE_NONVERB_STRUCTURE_SHA256[6]`을 Round 6 H 구조로 등록하고 `pending_round() == 6`.
2. **실데이터 T 리허설(H 완료 조건):** H 최종 커밋에서, 실제 S와 실제 입력으로 저장소의 임시 복사본을 만들어 다음을 한 번 수행한다: 사전 해소(필요 시), candidates·classify·carry, freeze, 전체 스위트(T 상태), dry-run pre-T, 워커 handshake 형식 검사. 실패는 H′로 고친다. 결과는 `rehearsal_report`로 원장에 남긴다. 리허설은 hidden set을 만들지 않으며 봉인 이전이다.
3. **검수 상한:** 스펙·계획 검수는 P0 0건이면 통과(P1은 다음 버전에 반영, 재검수 없음). 스펙 검수는 4회를 목표 상한으로 하고, 넘으면 범위 축소 여부를 검수 스레드에서 판정받는다.
4. **hidden 전송 절차화:** 생성기·검토자 응답은 대화 API로 읽어 브라우저 해시와 대조한 청크로 옮긴다(Round 5 절차를 스크립트화). 숨김 텍스트는 원장에 해시로만 남는다.
5. 단일 평가·봉인·행위자 분리·검수 스레드 판정은 상속 그대로다.

## 6. Runtime stability와 검색 로그 (Phase 2.5 스펙 §8 개정)

- **등록(사용자 실행, Round 6 시작 시):** 사용자 범위 MCP 등록, 실행 위치는 저장소로 고정, `ATLASSIAN_DOCS_SEARCH_LOG=1`. 등록 시각을 원장 `runtime_stability_started`로 기록한다.
- **로그 확장(H):** `search_operations` 레코드에 `actionable`, `recommended_operation`, `abstain_reason`, `method_intent_consistent`를 추가한다. `get_operation`·`build_request_template` 호출은 별도 레코드 `{"ts", "kind": "selection", "tool", "key", "intelligence_fingerprint"}`로 같은 파일에 남긴다(인자 값·헤더는 기록하지 않음). 파일 권한·회전·OSError 무시는 상속.
- **판정:** 로그 기간이 7일 이상이고 `search_operations` 레코드가 100개 이상이면 Runtime stability 충족으로 readiness에 기록한다. 같은 기록에 로그 기반 참고 지표(추천 후 같은 세션에서 선택된 key와 추천의 일치율, 쓰기 추천 수)를 남긴다(게이트 아님).
- **실사용 질의:** 로그의 실패 질의는 §7.3대로 다음 라운드 seed 후보다. Round 6 봉인 평가에는 쓰지 않는다. 로그는 저장소 밖(캐시 디렉터리)에만 있으며 커밋하지 않는다.

## 7. 도구 변경 요약

- `tools/atlassian_docs/intelligence/search.py`: §3.1–3.4 (abstain_reason, R1–R3).
- `tools/atlassian_docs/intelligence/policy.py` / `data/search_ranking.json`: `ordering_rules.singular_collection_tiebreak`, 구조 sha 갱신, `POLICY_VERSIONS["search"] = 5`.
- `tools/atlassian_docs/intelligence/search_log.py`, `mcp/` 도구 계층: §6 로그 필드와 selection 레코드.
- `tests/benchmarks/evaluator.py`: §4.1·§4.2 지표 계산(`reach_at_k`, `rec_precision`, `write_safety_violations`, `no_answer_abstention`, `forbidden_recommended`), `KNOWN_UNREACHABLE[6] = ()`, `ROUND6_EXTRA_KEYS`, `TestSealIntegrity.test_hidden_plaintext_machine_rules`의 `verb_methods` 전달 수정(Round 5 교훈 3).
- `tests/tune_search_ranking.py`: `tuning_accept`·pre-T blocker·제안기 입력을 §4.2로.
- `tests/diag_search_queries.py`: 새 지표 출력과 `no_answer` 처리, 최종 산출물 `round6-final.json`.
- `tests/benchmarks/round6_simulation.py`: 상속 수명주기 + §5.2 리허설 모드(`--phase rehearsal`).
- benchmark: §4.3 승격·라벨 이관.

## 8. 테스트 전략 델타

- R1: 쓰기 추천 + 머리 명사 미반영 → 기권; 같은 경우 GET → 추천 유지; 머리 명사가 alias 타깃으로 반영되면 추천 유지; 개념어 없음 → 미적용.
- R2: 질의 "jira" + Confluence 1위 → 기권; 힌트 없음 → 미적용.
- R3: 정확한 동점 + 단수 머리 명사 → 단건 앞; 복수 → 목록 앞; 점수 차 → 순서 불변; 플래그 false → 상속 정렬과 바이트 동일.
- 결과 목록 불변: 기권해도 `results`의 순서·점수는 R1·R2 이전과 같다.
- 지표 함수: 손으로 만든 작은 결과 집합으로 각 지표 경계값(15/16, 90%, 0, 7/8) 검증.
- 라벨 이관: `no_answer` 필드 스키마 검사, 승격 id·origin 검사, 승격 레코드 내용이 Round 5 unseal 레코드와 바이트 동일(`ku_identity` 방식 projection 불필요 — 전체 동일).
- 로그: 새 필드와 selection 레코드, 인자 값 미기록, 권한 0600.
- 리허설: `round6_simulation --phase rehearsal`이 임시 복사본에서만 쓰기(작업 트리 불변) 테스트.

## 9. 상태 모델·readiness 델타

- readiness Round 6 기록: §4.1 네 지표(기준·결과), top-1(기록), §4.2 학습 지표, R1–R3 채택 측정(§3.5), 승격·라벨 이관 요약, 리허설 결과, Runtime stability 시작 시각과 판정 상태.
- Phase 2.5 스펙에 §18·§8 개정 각주를 추가한다(H 커밋, 문서만).

## 10. Acceptance Criteria (델타)

| AC | 기준 | 검증 |
|---|---|---|
| AC-R6-01 | payload `actionable`·`recommended_operation`·`abstain_reason`이 §3.1 계약대로; 기권해도 `results` 불변 | unit |
| AC-R6-02 | R1·R2·R3이 §3.2–3.4 정의대로 동작하고 R3 플래그 false에서 상속 정렬과 동일 | unit |
| AC-R6-03 | §3.5 채택 측정이 원장·readiness에 기록됨; 쓰기 오추천 수가 R1–R3 적용 전보다 늘지 않음 | ledger |
| AC-R6-04 | §4.1 지표 함수가 정의대로 계산되고 최종 산출물·readiness에 기준과 함께 기록됨 | unit + 산출물 |
| AC-R6-05 | §4.2 `tuning_accept`·pre-T blocker(`metric_threshold`)·제안기 입력이 정의대로; `KNOWN_UNREACHABLE[6] == ()` | unit |
| AC-R6-06 | §4.3 승격 id·origin·내용 동일, `no_answer` 라벨이 stateless 검토 출력 sha와 함께 원장에 있음 | unit + ledger |
| AC-R6-07 | §5.2 리허설이 H 최종 커밋에서 수행되고 실패 0으로 `rehearsal_report` 기록 | ledger |
| AC-R6-08 | §6 로그 필드·selection 레코드·권한; `runtime_stability_started` 기록 | unit + ledger |
| AC-R6-09 | T 이후 `search.py`·`policy.py`·`search_ranking.json` 구조가 `housekeeping_commit`과 동일(값 채택 경로 상속) | git diff |

## 11. 위험과 완화

- **규칙이 hidden에서 맞는 추천을 기권으로 바꿈(추천 정확도는 오르지만 도달·정확도 분모 감소):** 정확도 기준은 추천을 낸 경우만 세므로 기권은 정확도를 낮추지 않는다. 대신 추천 0건은 0%로 정의해 "전부 기권"으로 통과하는 길을 막는다.
- **머리 명사 정의가 영어 어순에 의존:** 짧은 명령형 질의(현 benchmark·실사용 형태)에서 마지막 개념어가 대상인 경우가 다수다. 예외는 §3.5 측정과 counterexample 스위트에 드러나고 판정 대상이 된다.
- **라벨 이관이 평가 맞추기로 변질:** 라벨은 엔진 결과를 보지 않는 stateless 검토가 카탈로그 사실로 정한다; 검토 입력에 엔진 출력이 없음을 원장에 기록한다.
- **실사용 로그 민감정보:** 저장소 밖 보관·커밋 금지·소유자 전용 권한.
- **s-004 같은 상속 쓰기 오추천이 pre-T에서 남음:** `write_safety_violations == 0`을 막는 blocker로 보고되며, 해결은 R1–R3 범위 안 또는 스펙 개정 판정으로만 한다.

## 12. 한 줄 정의

Round 6 = 실사용 기준 게이트(도달·추천 정확도·쓰기 안전·기권) + 추천/기권 규칙(R1 머리 명사, R2 제품 불일치, R3 단건/목록 동점) + Runtime stability 측정 개시 + 실데이터 T 리허설.

## 13. 구현 계획 입력

- H 순서 제안: H18 지표·라벨 스키마·evaluator(§4, §7) → H19 스코어러 R1–R3·payload(§3) → H20 로그·MCP(§6) → H21 승격·라벨 이관 도구와 round6_simulation·리허설(§4.3, §5.2) → whole-branch 리뷰 → 리허설 → 컨트롤러.
- 라벨 이관 검토(§4.3)와 R1–R3 채택 측정(§3.5)은 H 안의 컨트롤러 단계이며 검수 스레드 판정을 받는다.
