# Search Quality Round 2 — Technical Specification

**문서 버전:** v1.0
**기준일:** 2026-10-02
**선행 구현:** Search Quality Round 1 (spec v1.4, 게이트 실패: held_out 4/16, negative 5/8) + Round 2 pre-work (`main` 95b8de0: 관찰 집합 강등, 라운드 비의존 테스트, 로더 보정). 오프라인 테스트 405개.
**목적:** Round 1 절차(A→T→B→C→D)를 **어휘만 바꿔** 반복하고, 봉인된 새 held_out 16 / negative 8에서 Discovery 게이트(≥ 15/16, 0/8)를 충족한다.
**설계 원칙:** Vocabulary before structure / Inventory, not instances / Pre-register, then budget / Same seal, same gate / Round-independent tooling

---

## 0. 배경

### 0.1 Round 1 실패 분석 (artifact `tests/benchmarks/round1-final.json`, 지금은 seed s-024..s-039 / regression rn-007..rn-014)

| 사실 | 수치 |
|---|---|
| held_out 실패 12건 중 질의에 동사 테이블 단어가 없는 것 | 9건 (`leave feedback`, `revise`×2, `publish`, `discard`, `rewrite`, `trash`, `browse`, `browse`) |
| 동사가 있으나 오판 | `set up`(PUT 전용이라 createBoard POST 불일치) 1건 |
| 질의 개념어가 카탈로그 어휘(operationId·summary·tags·key)에 **전무** | `feedback`, `release`, `iteration`, `file/files`, `starred` (0회), `workspace`(7회, 다른 뜻) |
| 정답 op의 어휘 | `comment` 82, `worklog` 23, `attachment` 50, `favourite` 3, `version` 47, `sprint` 35, `space` 87 |
| 터미널 리소스 보너스(+10)가 기본 리소스에 붙은 실패 | 15건 중 10건 — 대부분 위 어휘 단절의 결과(`feedback→comment`가 이어지면 보너스가 `/issue/{k}/comment`로 이동) |
| 결과 없음 | `revise dates for this iteration` 1건 (어휘 히트 0) |
| negative 실패 3건 | 명사형 질의에서 유인 오답이 실제 1위 |

결론: Round 1 구조 신호는 R1(하위 리소스 과잉 매칭)을 해결했고(seed 23/23), Round 2 병목은 어휘 두 층이다. (1) 동사 테이블 커버리지, (2) 질의 개념어 → 스펙 어휘.

### 0.2 실패 클래스 추가

| 클래스 | 정의 | 해결 수단 |
|---|---|---|
| R5 동사 부재 | 질의의 unigram 중 `verb_methods` 키가 없거나, 있어도 허용 메서드가 정답 메서드를 포함하지 않음 | 동사 인벤토리(§6) — 커밋 T에서 동결 |
| R6 개념어 단절 | 질의의 unigram이 카탈로그 어휘·동사·기존 alias 어디에도 없음 | 사전 등록된 개념 alias(§7) — B..C에서 예산 내 추가 |

Round 1의 R1–R4 정의는 그대로다.

### 0.3 결정 이력

- 2026-10-01 사용자: 범위 = 어휘만(스코어러·게이트 무변경); 동사는 일반 영어 인벤토리, 개념 alias는 seed 근거만; 접근안 B(절차 반복 + alias 예산·사전 등록).

---

## 1. 목표

> 동사 인벤토리와 alias 후보 목록을 **hidden set 생성 전에** 동결하고, B..C 구간에서는 후보 목록 안의 alias만 예산 내로 추가하며, 상수는 grid 전수 재선택한 뒤, 얼린 커밋에서 봉인 집합을 한 번만 측정한다. 스코어러 코드와 게이트 정의는 바꾸지 않는다.

## 2. 범위

### 2.1 포함
1. `verb_methods` 인벤토리 교체(§6), `round_freeze.json` round 2 항목, 스냅샷 재복사.
2. `alias_candidates.json` 생성 도구와 동결(§7.1).
3. 봉인·진단·튜닝 도구의 라운드 일반화(§8).
4. 새 hidden set 생성·봉인(§5), B..C 튜닝(상수 grid + 후보 alias), C/D, readiness Round 2 섹션.

### 2.2 제외
`search.py`/`policy.py` 변경, `POLICY_VERSIONS` bump(스코어링 의미 불변), 게이트 수치·hidden set 크기 변경, 검색 로그 처리, 픽스처에 r1 정답 op 추가.

## 3. 설계 원칙

1. **Vocabulary before structure.** R5/R6은 어휘로 고친다; 구조 신호는 Round 1 그대로.
2. **Inventory, not instances.** 동사는 질의와 무관한 일반 인벤토리에서 오고 T에서 통째로 동결한다.
3. **Pre-register, then budget.** 개념 alias는 seed 39건에서 기계적으로 추출한 후보 목록(T에서 동결) 안에서만, 라운드당 ≤ 15, seed당 1개.
4. **Same seal, same gate.** 생성 규칙·봉인·평가 1회·게이트는 Round 1 spec §5/§5.9와 동일.
5. **Round-independent tooling.** 도구와 테스트는 `round_freeze.json`의 현재 라운드를 읽고, 이전 라운드 artifact를 깨뜨리지 않는다.

## 4. 파일 구조

| 파일 | 변경 |
|---|---|
| `tools/atlassian_docs/intelligence/data/search_ranking.json` | `verb_methods` 교체(T); `constants`만 B..C에서 변경 |
| `tools/atlassian_docs/intelligence/data/alias_candidates.json` | 신규(T): §7.1 |
| `tools/atlassian_docs/intelligence/data/search_aliases.json` | B..C: round2 alias/rule + notes |
| `tests/benchmarks/round_freeze.json` | 리스트로 확장; round 2 항목 |
| `tests/benchmarks/round_seal.py` | `round1_seal.py` 이름 변경 + `--round N`; 키 `round{N}_seal` |
| `tests/benchmarks/alias_candidates_tool.py` | 신규: 후보 목록 결정적 생성 |
| `tests/tune_search_ranking.py` | `--alias-change` 후보·예산 검사, 로그에 `round` |
| `tests/diag_search_queries.py` | seal 키·artifact 이름을 라운드에서 유도 |
| `tests/benchmarks/search_queries.json` | B: `held_out`/`negative` 봉인 메타 + `round2_seal`; D: 평문 |
| `tests/benchmarks/round2-final.json` | D |
| `tests/benchmarks/search-tuning-round2.jsonl` | 튜닝 로그(라운드별 파일) |
| `tests/benchmarks/test_evaluator.py`, `tests/intelligence/test_policy.py`, `tests/test_diag_search_queries.py`, `tests/test_tune_search_ranking.py` | §10 |
| `docs/phase3-readiness.md` | Round 2 섹션 |
| `README.md`, `AGENTS.md` | 동사 인벤토리·alias 후보 한 단락 |

불변(baseline `95b8de0`, AC-09): Round 1 spec §4의 불변 목록 전체 **+ `tools/atlassian_docs/intelligence/search.py`, `policy.py`**, `operation_quirks.json`, `tests/benchmarks/round1-final.json`, `search-tuning-round1.jsonl`, `round1_seal`(bench 안), `docs/phase3-readiness.md`의 Round 1 섹션.

가변 구간 규칙(AC-01): `search_aliases.json`과 `search_ranking.json`의 `constants`는 B..C에서만; `search_ranking.json`의 테이블과 `alias_candidates.json`은 T에서만.

## 5. 벤치마크 절차 (Round 1 spec §5 재사용, 차이만)

- **A**: 이미 완료(pre-work 95b8de0). seed 39(r0 23 + r1 16), regression 14(r0 6 + r1 8), hidden 비어 있음. 이번 라운드의 seed 실패에는 `failure_classes`에 R5/R6(필요 시 R1–R4)을 기록한다(튜닝 중 분류, alias 허용 판정용).
- **T**: `search_ranking.json` `verb_methods` 교체 + `alias_candidates.json` 커밋 + `round_freeze.json` round 2 항목(`commit_T`, `structure_sha256`, `alias_candidates_sha256`). **T 직후 스냅샷 재복사**(`$ATLASSIAN_DOCS_ROUND2_CACHE`, 기본 `~/.atlassian_api_updater/round2-cache/`; 존재하면 거부; fingerprint 기록). Round 1 스냅샷은 아카이브에 남긴다.
- **생성(clean context)**: Round 1 §5.4의 규칙 그대로 + 추가 규칙 (negative): 질의가 카탈로그 op의 summary 또는 마지막 경로 세그먼트를 **그대로 명사구로 옮긴 것**(예 `page history`, `label printer`처럼 결과적으로 정답이 존재하는 것)은 거부. reviewer-check 항목: "이 질의에 정답 op가 존재하면 negative가 아니다". 생성기에는 Round 1 hidden 질의도 제공하지 않는다(재사용은 machine check가 잡음 — seed 39건과 중복 금지는 자동).
- **B**: `round_seal.py seal --round 2` → `round2_seal` 키(형식은 `round1_seal`과 동일: 두 sha, 두 distribution, registry fingerprint, spec sha).
- **B..C**: §7.2 규칙으로 alias 추가, `tune_search_ranking.py` grid 전수 재실행(baseline은 Round 1 T2의 baseline 그대로 — 테이블 변경은 동사뿐이고 상수 grid·baseline은 유지).
- **C**: 빈 커밋; `evaluation_code_sha256` 대상 파일에 `tests/benchmarks/round_seal.py`, `tests/benchmarks/alias_candidates_tool.py`를 추가(6개 파일).
- **D**: `diag --bench <sealed> --cache-dir <round2-cache> --json tests/benchmarks/round2-final.json` 1회; unseal; readiness. C..D whitelist = `search_queries.json`, `round2-final.json`, `docs/phase3-readiness.md`.
- **게이트**: held_out ≥ 15/16, negative 0/8. artifact에 보조 지표 `held_out_top3`(top-3 안에 정답이 있는 비율)를 기록만 한다.

## 6. 동사 인벤토리 (`verb_methods`, 커밋 T에서 동결)

규칙: 한 동사는 한 메서드 집합에만; 질의에 동사가 여럿이면 교집합, 공집합이면 0(Round 1 §6.3 불변). 메서드를 결정하지 않는 동사(`leave, hand, give, put, take, bring, keep, draft, manage, handle, work, do, use`)는 **넣지 않는다**.

```json
"verb_methods": {
  "get": ["GET"], "fetch": ["GET"], "read": ["GET"], "list": ["GET"], "find": ["GET"], "search": ["GET"], "show": ["GET"],
  "view": ["GET"], "browse": ["GET"], "look": ["GET"], "check": ["GET"], "inspect": ["GET"], "retrieve": ["GET"],
  "display": ["GET"], "see": ["GET"], "query": ["GET"], "lookup": ["GET"], "open": ["GET"], "load": ["GET"],
  "download": ["GET"], "count": ["GET"], "describe": ["GET"], "export": ["GET"],
  "create": ["POST"], "add": ["POST"], "post": ["POST"], "upload": ["POST"], "run": ["POST"], "submit": ["POST"],
  "start": ["POST"], "make": ["POST"], "publish": ["POST"], "send": ["POST"], "register": ["POST"], "attach": ["POST"],
  "insert": ["POST"], "invite": ["POST"], "import": ["POST"], "trigger": ["POST"], "execute": ["POST"],
  "generate": ["POST"], "copy": ["POST"], "clone": ["POST"], "duplicate": ["POST"], "link": ["POST"], "share": ["POST"],
  "comment": ["POST"], "reply": ["POST"], "log": ["POST"], "record": ["POST"], "launch": ["POST"], "kick": ["POST"],
  "update": ["PUT", "POST"], "change": ["PUT", "POST"], "edit": ["PUT", "POST"], "set": ["PUT", "POST"],
  "rename": ["PUT", "POST"], "modify": ["PUT", "POST"], "revise": ["PUT", "POST"], "rewrite": ["PUT", "POST"],
  "replace": ["PUT", "POST"], "move": ["PUT", "POST"], "transition": ["PUT", "POST"], "assign": ["PUT", "POST"],
  "reassign": ["PUT", "POST"], "reorder": ["PUT", "POST"], "rank": ["PUT", "POST"], "archive": ["PUT", "POST"],
  "restore": ["PUT", "POST"], "enable": ["PUT", "POST"], "disable": ["PUT", "POST"], "close": ["PUT", "POST"],
  "reopen": ["PUT", "POST"], "resolve": ["PUT", "POST"], "approve": ["PUT", "POST"], "mark": ["PUT", "POST"],
  "pin": ["PUT", "POST"], "unpin": ["PUT", "POST"], "toggle": ["PUT", "POST"], "configure": ["PUT", "POST"],
  "adjust": ["PUT", "POST"], "correct": ["PUT", "POST"], "fix": ["PUT", "POST"], "promote": ["PUT", "POST"],
  "demote": ["PUT", "POST"],
  "delete": ["DELETE"], "remove": ["DELETE"], "discard": ["DELETE"], "trash": ["DELETE"], "drop": ["DELETE"],
  "erase": ["DELETE"], "clear": ["DELETE"], "purge": ["DELETE"], "unassign": ["DELETE"], "unlink": ["DELETE"],
  "unwatch": ["DELETE"], "unsubscribe": ["DELETE"], "revoke": ["DELETE"], "cancel": ["DELETE"], "detach": ["DELETE"],
  "destroy": ["DELETE"]
}
```

- Round 1 대비 변경: `update/change/edit/set/rename`과 `assign`이 PUT 전용 → PUT|POST(Atlassian이 갱신·배정에 POST를 섞어 씀; `set up … board`는 createBoard POST). `search`는 GET 유지(Round 1 §13).
- `verb_methods`의 키는 로더 규칙(`^[a-z]+$`, fullmatch) 그대로. `path_noise`, `product_hints`, `tuning_grid`, `baseline`은 Round 1 T2 값 그대로 — 바뀌는 것은 `verb_methods`뿐이므로 `ranking_structure_sha256`만 갱신된다.
- 토큰화 주의: 질의 unigram은 `token_forms` 적용 전 raw unigram으로 동사 판정(Round 1 §6.3). `rewrites`처럼 복수/3인칭형은 매칭되지 않는다 — 인벤토리에는 원형만 둔다(생성 규칙상 질의는 명령형·원형이 대부분이며, 이는 알려진 한계로 §13에 기록).

## 7. 개념 alias 정책

### 7.1 후보 목록 `alias_candidates.json` (커밋 T에서 동결)
- 생성 도구 `tests/benchmarks/alias_candidates_tool.py --cache-dir DIR --bench BENCH --ranking RANKING --aliases ALIASES --out OUT`가 **결정적으로** 만든다:
  1. seed 레코드마다 질의 unigram(`tokenize_unigrams` 동일 규칙: camelCase 분리, 소문자, len ≥ 2, STOPWORDS 제외).
  2. 제외: 카탈로그 어휘(operationId·summary·tags·key의 unigram, `singular` 적용 포함)에 있는 토큰; `verb_methods` 키; 기존 alias 키; `product_hints` 키; **기능어 목록** `FUNCTION_WORDS = {new, up, fresh, inside, exist, dates, planning, entry, another, every, which, my, me, one, now, today, please, into, onto, brand, own, current, this}`(스펙에 명시, 도구 상수); 식별자형 토큰(seed 질의 토큰이 어떤 op의 operationId 소문자와 같은 것 — `createissue`, `multipartfile`).
  3. 남은 토큰마다 `seed_ids`와 `allowed_targets` = 그 seed들의 `expected_top1_any` op들의 operationId·path·tags unigram(단수형)을 합친 집합. 타깃 집합이 비면 `allowed_targets: []`(등록만).
  4. 결정적 정렬(토큰 사전순, 리스트 정렬), canonical sha256을 `round_freeze.json`에 기록.
- 현재 seed 39건 기준 예상 후보(도구 실행 결과가 기준이며 이 목록은 설명용): `feedback → {comment, issue, add, …}`, `release → {version, create}`, `iteration → {sprint, update}`, `starred → {filter, favourite, get}`, `wiki → {blogpost, page, update, delete}`, `file → {attachment, delete}`, `files → {attachment, page, get}`, `uploaded → {attachment, delete}`, `attached → {attachment, page, get}`, `summary → {issue, edit}`.
- `allowed_targets`에 동사 토큰(`get`, `add`, …)이 섞여 들어오면 **동사 테이블 키는 타깃에서 제거**한다(alias는 개념어→개념어만).

### 7.2 B..C 추가 규칙
- 추가 가능: `candidates[word].allowed_targets ⊇ 선택 타깃`인 direct alias `word → [targets…]`, 또는 `when_all`·`add`가 모두 (후보 단어 ∪ 그 단어의 allowed_targets) 안에 있는 조건 규칙.
- 예산: 이번 라운드 추가분(alias + rule) ≤ 15, seed 1건당 1개(`notes.seed_query_id` 유일). notes: `origin: "round2"`, `seed_query_id`, `failure_classes ∋ "R6"`, `evidence`.
- 전제: 그 seed가 **선택된 상수에서 실패 중**이어야 하고, 추가 후 통과해야 한다(`alias_change` false→true 로그).
- 동사 alias 금지(동사는 §6). 감쇠 값 불변.
- `tune_search_ranking.py --alias-change`가 후보 포함·예산·seed당 1개를 검사해 위반이면 로그를 쓰지 않고 exit 1.

### 7.3 기존 alias
Round 1 `rules[3]`(`{jql}→…`)과 phase2.5 항목은 grandfathered. 삭제·수정 금지.

## 8. 도구 일반화

- `round_seal.py --round N`: seal 키 `round{N}_seal`; `seal`은 bench에 `round{N}_seal`이 이미 있으면 거부; `unseal`은 같은 키로 검증. `round1_seal.py`는 삭제하고 테스트 import를 바꾼다.
- `diag_search_queries.py`: `round_freeze.json`의 마지막 항목 `round`로 seal 키와 artifact 이름 결정; `--round N` 로 override 가능.
- `tune_search_ranking.py`: 로그 파일 `search-tuning-round{N}.jsonl`, 라인에 `round`; `--alias-change` 검사(§7.2).
- `evaluation_code_sha256`: 6개 파일(기존 4 + `round_seal.py`, `alias_candidates_tool.py`), 알고리즘 동일.
- `round_freeze.json`: `[{"round": 1, "commit_T": "26005e4", "structure_sha256": "6b3e…"}, {"round": 2, "commit_T": …, "structure_sha256": …, "alias_candidates_sha256": …}]`.

## 9. 진단 출력 추가
`round2-final.json`에 Round 1 필드 전부 + `round`, `held_out_top3`(정보), `alias_sha256`, `alias_candidates_sha256`.

## 10. 테스트 전략

### 10.1 단위
- 동사 인벤토리: `search_ranking.json`의 `verb_methods`가 스펙 §6 JSON 블록과 동일(스펙 파일 파싱); 메서드 의도 샘플: `set up a jira planning board` → allowed {POST, PUT}; `leave feedback on this jira ticket` → 의도 0 (`leave` 미등록, `feedback`은 동사 아님); `discard this uploaded ticket file` → DELETE; `browse pages` → GET; `revise`+`rewrite` 동시 → PUT|POST 교집합.
- 후보 도구: 같은 입력 → 같은 출력(두 번 실행 diff 없음); 기능어·식별자·카탈로그 토큰 제외 각각 테스트; 타깃에서 동사 제거.
- 튜닝 스크립트: `--alias-change`가 후보 밖 단어/타깃, 예산 초과, seed당 2개를 거부(순수 함수 `validate_alias_change(change, aliases_before, aliases_after, candidates, budget)` + 테스트).
- 라운드 일반화: `round_seal.py --round 2`가 `round2_seal`을 쓰고 `round1_seal`을 건드리지 않음; diag가 round 2 artifact 이름을 쓰고 round 1 artifact 테스트가 여전히 통과.

### 10.2 벤치마크 무결성 (`test_evaluator.py`)
- `TestSealIntegrity`를 라운드 키 일반화(`round{N}_seal` for N in freeze list).
- `alias_notes`: round2 항목이 §7.2 조건(후보 포함, 예산, seed당 1개, R6) 충족.
- provenance: 동사 테이블은 검사 제외(인벤토리 근거); alias 단어는 seed 토큰 ∪ 카탈로그 토큰(기존) **그리고** round2 alias는 후보×타깃 안; 예외 목록은 `{epic}`(제품 힌트).
- `round_freeze.json`: round 2 항목의 `structure_sha256` == 현재 파일, `alias_candidates_sha256` == 현재 파일.
- 최종 artifact(round 2): Round 1과 같은 내부 일관성 검사.

### 10.3 seed 회귀
픽스처: r0 23/23·6/6 유지. 스냅샷: seed 39/39, regression 14/14(튜닝 로그 `adopted` 라인으로 검증, AC-06).

## 11. 상태 모델과 readiness
Round 1 §11과 동일하되 Round 2 섹션. 게이트 통과 시 Discovery 축을 "충족(Round 2, 커밋 D sha)"으로 표시하고 Runtime stability 축은 별도임을 명시.

## 12. Acceptance Criteria

| ID | 기준 | 검증 |
|---|---|---|
| AC-01 | 95b8de0 < T < B < C < D; `search_aliases.json`·`search_ranking.json.constants` 변경 커밋은 B..C에만; `verb_methods`·`alias_candidates.json` 변경은 T에만 | git |
| AC-02 | C..D 변경 파일 ⊆ {`search_queries.json`, `round2-final.json`, `phase3-readiness.md`} | git |
| AC-03 | D의 평문 sha256 == `round2_seal`; D에 테스트 코드 변경 없음 | 테스트 + git |
| AC-04 | gate 집합 origin ∈ {`held_out-r2`, `negative-r2`}, r0/r1 레코드 0개 | 테스트 |
| AC-05 | `search.py`, `policy.py` diff vs 95b8de0 비어 있음(어휘 라운드) | git |
| AC-06 | 스냅샷 seed 39/39, regression 14/14(adopted 로그 라인); 픽스처 r0 23/23·6/6 | 테스트 + 로그 |
| AC-07 | §10.1 테스트 통과 | 테스트 |
| AC-08 | `POLICY_VERSIONS["search"] == 3` 유지; `ranking_structure_sha256` == round 2 T 값 | 테스트 |
| AC-09 | §4 불변 목록 diff vs 95b8de0 비어 있음; Round 1 artifact·로그·seal·readiness 섹션 불변 | git |
| AC-10 | `round2-final.json` provenance 필드 + `round`, `held_out_top3` | 테스트 |
| AC-11 | 최종 artifact 정확히 하나, `git_commit`==C(컨트롤러 D 검사), D 이후 가변 파일 변경 커밋 없음 | git |
| AC-12 | round2 alias/rule 전부 §7.2 조건·예산 충족; 동사 alias 없음 | 테스트 |
| AC-13 | `alias_candidates.json` sha == freeze; 도구 재실행 결과와 동일 | 테스트 + 도구 |
| AC-14 | 라운드 일반화 후 Round 1 artifact/seal 테스트가 여전히 통과 | 테스트 |
| AC-15 | 튜닝 로그 round 2: adopted 정확히 하나, 상수 == 파일, baseline == freeze | 테스트 |
| AC-16 | 전체 오프라인 테스트 통과, 새 의존성 없음 | unittest |

Attestation(컨트롤러): 생성 프롬프트/결과 sha, 재요청 횟수, 1회 평가, 봉인 경로 미노출, 튜닝 로그 완전성, **동사 인벤토리와 후보 목록이 hidden set 생성 전에 커밋됐음(T < B)**.

## 13. 위험과 완화

- **인벤토리 과소/과다**: hidden set의 동사가 인벤토리에 없으면 R5 재발. 완화: 인벤토리는 100개 안팎의 일반 API 동사. 반대로 다의어(`check`, `open`, `log`)가 잘못된 메서드를 가리킬 수 있다 → 교집합 규칙과 어휘 점수가 상쇄; readiness에 기록.
- **굴절형**: `rewrites`, `showing`은 매칭되지 않음. 완화: 생성 규칙이 명령형을 유도; Round 3 후보(동사 어간화).
- **후보 목록이 seed에 과적합**: 후보는 seed 토큰에서만 나오므로 hidden set의 새 개념어(예 `epic link`)는 못 잇는다. 이것이 Round 2가 측정하려는 일반화다; 실패하면 Round 3에서 "개념 사전 일반 인벤토리" 결정으로 넘어간다.
- **negative 약화**: 생성 규칙 추가로 negative가 더 어려워져 0/8 요구가 더 엄격해진다. 게이트는 유지한다.
- **컨트롤러 누수**: Round 1과 동일한 attestation. Round 1 hidden 질의는 이제 seed이므로 설계·튜닝에 쓰는 것이 정당하다.

## 14. 한 줄 정의

> 동사는 인벤토리로, 개념어는 사전 등록된 후보로, 둘 다 봉인 전에 잠그고, 같은 절차로 한 번만 잰다.
