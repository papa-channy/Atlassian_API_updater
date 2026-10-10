# 보고서: 자원 근거 없는 질의의 `actionable: true` 오추천

**작성일:** 2026-10-11
**대상:** `search_operations`의 추천/기권 판정 (`search.py`, `POLICY_VERSIONS["search"] = 4`)
**성격:** 관찰·원인 분석만. 코드 변경 없음.

## 1. 관찰

MCP로 실제 호출(registry `e308a232…`, intelligence `f5687a36…`, 세 소스 모두 fresh).

| 질의 | total_matches | top-3 점수 | actionable | recommended_operation |
|---|---|---|---|---|
| `delete` | 142 | 15 / 15 / 15 | true | `confluence:DELETE:/space-roles/{id}` |
| `delete something` | 135 | 13 / 13 / 13 | true | `confluence:DELETE:/space-roles/{id}` |
| `delete xyzzy` | 135 | 13 / 13 / 13 | true | `confluence:DELETE:/space-roles/{id}` |

- 동사 외의 토큰(`something`, `xyzzy`)은 어떤 작업에도 근거가 없다. top-3 모두 `resource_match = 0`, `path_coverage.matched = []`.
- 1위는 점수 동점 후보 중 정렬 키 tie-break(사실상 key 사전순 — `confluence:` < `jira-platform:`)로 정해진다.
- 결과적으로 **DELETE 작업 중 임의의 하나가 "추천"으로 나간다.** 쓰기(파괴적) 메서드라 오추천 비용이 가장 큰 경우다.

대조: `create issue`, `get confluence page by id`는 각각 `resource_match = 10`인 정답이 1위로 나오며 정상.

## 2. 원인 — 판정 로직

`tools/atlassian_docs/intelligence/search.py:380-383`

```python
payload["method_intent_consistent"] = bool(allowed)
payload["intent_methods"] = sorted(allowed) if allowed else []
payload["actionable"] = payload["method_intent_consistent"]   # spec §3.3: the product abstains without a clear intent
payload["recommended_operation"] = shown[0]["key"] if payload["actionable"] and shown else None
```

- `actionable`은 **동사→메서드 교집합이 비어 있지 않은가** 하나만 본다 (Round 3 스펙 §3.3).
- 결과의 질(점수, 자원 일치, 1·2위 격차)은 판정에 전혀 들어가지 않는다. Round 3 AC-R3-03("actionable은 점수·순서를 바꾸지 않음")에 따라 의도적으로 분리된 설계다.
- 후보 진입 조건은 `lexical > 0`뿐이므로(`search.py` 후보 루프), 동사 `delete`가 operationId/summary에 들어 있는 것만으로 DELETE 작업 전체가 후보가 된다. 미지 토큰은 점수를 균일하게 낮출 뿐(15→13) 순위를 바꾸지 않는다.

## 3. Round 6 스펙(v1.3, 미구현)으로 해결되는가 — **아니오**

`docs/superpowers/specs/2026-10-11-search-quality-round6-design.md` §3.1–3.4는
`actionable := method_intent_consistent ∧ abstain_reason is None`으로 확장하고 세 규칙을 추가한다.

| 규칙 | 조건 | `delete something`에 적용? |
|---|---|---|
| R1 `uncovered_head_resource` (§3.2) | 쓰기 추천 + `head_info(q).concept`가 1위 작업 어휘·alias에 없음 | **미적용.** `head_info`는 단수형이 *카탈로그 개념어 집합*에 속하는 토큰만 고른다. `something`/`xyzzy`는 개념어가 아니므로 `head_info = None` → "R1·R3은 적용되지 않는다" |
| R2 `product_conflict` (§3.3) | 제품 힌트가 있고 1위 소스가 힌트와 불일치 | 미적용 (힌트 없음) |
| R3 단건/목록 동점 (§3.4) | 정렬 규칙일 뿐 기권 아님 | 해당 없음 |

즉 R1은 "알려진 자원을 말했는데 1위가 그 자원이 아닌" 경우만 잡고, **"알려진 자원을 하나도 말하지 않은" 경우는 설계상 빠져 있다.** 동사만 있는 질의(`delete`)도 같은 구멍으로 추천이 나간다.

## 4. 수정 방향 후보 (결정은 사용자/검수 스레드)

Round 6 §3 원칙(불리언 규칙, 수치 상수 추가 금지, H에서만 구조 변경)에 맞는 순서로 정리.

1. **R1 확장 — 개념어 없는 쓰기 질의 기권** (가장 작은 변경)
   쓰기 추천이고 `head_info(q) is None`이면 `abstain_reason = "no_head_resource"`(신규) 또는 기존 `uncovered_head_resource` 재사용.
   - 장점: 불리언, 상수 없음, 기존 `head_info` 재사용. 이번 사례(`delete`, `delete something`)를 정확히 잡는다.
   - 위험: operationId식 질의(`deleteSpaceRole`)는 exact_match 핀으로 별도 처리되므로 영향 없음. 단 개념어 정의(path literal ∪ tag 토큰)에 없는 정당한 자원명(예: summary에만 나오는 단어)을 쓴 쓰기 질의가 기권될 수 있다 → §3.5 scorer-rule counterexample(summary-as-query 코퍼스)로 손실을 측정해야 함.
2. **1위 근거 검사 — 1위가 질의의 비동사 토큰을 하나도 커버하지 않으면 기권**
   `top.signals.resource_match == 0 ∧ path_coverage.matched == []` 등. 불리언이지만 신호 값에 의존하므로 B..C 튜닝 constants와 상호작용 여부를 확인해야 함.
3. **동점 1위 기권** — 1위와 2위 점수가 정확히 같고 서로 다른 자원이면 기권.
   이번 사례는 잡지만, R3이 해소하려는 단건/목록 동점과 충돌 가능 → R3 적용 후 남은 동점에만 적용해야 함.

권장: **1번을 Round 6 H 범위에 포함**(스펙 개정 v1.4로 §3.2에 한 줄 추가 + AC-R6-02 테스트 케이스 추가: `"delete"`, `"delete xyzzy"` → `actionable=false`). 2·3번은 1번의 counterexample 손실이 기준을 넘을 때의 대안으로 보류.

## 5. 회귀 테스트로 고정할 질의 (제안)

| 질의 | 기대 |
|---|---|
| `delete` | actionable=false |
| `delete something` / `delete xyzzy` | actionable=false |
| `create` | actionable=false |
| `get something` | (R1이 GET 미적용 원칙이면) actionable=true 유지 — 정책 결정 필요 |
| `create issue` | actionable=true, `jira-platform:POST:/rest/api/3/issue` |

`get something`은 GET이라 R1·확장 모두 미적용 → 여전히 임의 GET 추천이 나간다. 읽기 오추천을 §4.1 정확도 지표로만 다룰지, 개념어 0개일 때는 GET도 기권할지 별도 결정이 필요하다.

## 6. 확인하지 않은 것

- 검색 로그(`ATLASSIAN_DOCS_SEARCH_LOG=1`)에서 실사용 질의 중 개념어 0개 사례의 빈도는 집계하지 않았다.
- 1번 수정의 실제 counterexample 손실은 측정하지 않았다(코드 미변경 원칙).

## 7. 후속 (2026-10-11)

사용자 결정: GET 포함 기권. Round 6 스펙 **v1.4**로 반영 — §3.2a R0 `no_resource_evidence`(1위 어휘가 내용 토큰을 하나도 덮지 않으면 전 메서드 기권; 이 보고서 §4의 2번 안). 설계 측정 결과 4번의 1번 안(개념어 0개 기권)은 v1.3 `head_info` 정의로는 summary 코퍼스 손실 11/647로 hard 계약 위반이었고, 그 원인인 제품 힌트 제외 결함도 §3.2에서 정정했다. 측정 상세는 스펙 §0.
