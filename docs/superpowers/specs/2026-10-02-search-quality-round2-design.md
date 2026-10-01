# Search Quality Round 2 — Technical Specification

**문서 버전:** v1.13 (v1.10 = 외부 검수 10회, 최종 판정 "구현 계획으로 진행 가능"; v1.11–v1.13 = 구현 계획 검수 중 추가·정합화된 abort 분기와 분기별 AC-19)
**기준일:** 2026-10-02
**선행 구현:** Search Quality Round 1 (spec v1.4, 게이트 실패: held_out 4/16, negative 5/8) + Round 2 pre-work (`main` 95b8de0: 관찰 집합 강등, 라운드 비의존 테스트, 로더 보정). 오프라인 테스트 405개.
**목적:** Round 1 절차(A→T→B→C→D)를 **어휘만 바꿔** 반복하고, 봉인된 새 held_out 16 / negative 8에서 Discovery 게이트(≥ 15/16, 0/8)를 충족한다.
**설계 원칙:** Vocabulary before structure / Inventories, not instances / Pre-register, then budget / Roles separated by what they have seen / Same seal, same gate / Round-independent tooling

---

## 0. 배경

### 0.1 Round 1 실패 분석 (artifact `tests/benchmarks/round1-final.json`; 해당 레코드는 지금 seed s-024..s-039 / regression rn-007..rn-014)

| 사실 | 수치 |
|---|---|
| held_out 실패 12건 중 질의에 동사 테이블 단어가 없는 것 | 9건 (`leave feedback`, `revise`×2, `publish`, `discard`, `rewrite`, `trash`, `browse`) |
| 동사가 있으나 오판 | `set up`(PUT 전용이라 createBoard POST 불일치) 1건 |
| 질의 개념어가 카탈로그 어휘(operationId·summary·tags·key)에 **전무** | `feedback`, `release`, `iteration`, `file/files`, `starred` (0회); `workspace`는 7회 있으나 다른 뜻(Linked Workspaces) |
| 정답 op의 어휘 | `comment` 82, `worklog` 23, `attachment` 50, `favourite` 3, `version` 47, `sprint` 35, `space` 87 |
| 터미널 리소스 보너스(+10)가 기본 리소스에 붙은 실패 | 15건 중 10건 — 대부분 위 어휘 단절의 결과 |
| 결과 없음 | `revise dates for this iteration` 1건 |
| negative 실패 3건 | 명사형 질의에서 유인 오답이 실제 1위 |

결론: Round 1 구조 신호는 R1을 해결했고(seed 23/23), Round 2 병목은 어휘 세 층이다: (1) 동사 커버리지, (2) 사용자 개념어 → 스펙 개념어(일반), (3) 특정 seed가 드러낸 개념어 단절(개별).

### 0.2 실패 클래스 추가 (T에서 기계적으로 부여, §5.2)

| 클래스 | 정의(기계적) |
|---|---|
| R5 동사 부재/오판 | 질의 unigram 중 `verb_methods` 키가 없거나, 교집합 허용 메서드가 **어느 정답 op(`expected_top1_any`)의 메서드도** 포함하지 않음(∃ 의미론: 하나라도 포함하면 R5 아님) |
| R6 개념어 단절 | 질의 unigram 중 하나 이상이 정답 op 어휘(§7.1 정의)·동사·기존 alias·제품 힌트·기능어 어디에도 없음 |

R1–R4 정의는 Round 1 그대로.

### 0.3 결정 이력

- 2026-10-01 사용자: 범위 = 어휘만(스코어러·게이트 무변경); 동사는 일반 영어 인벤토리, 개념 alias는 seed 근거만; 접근안 B(절차 반복 + alias 예산·사전 등록).
- 2026-10-02 외부 검수 1차(v1.0→v1.1): `commit_T` 자기참조 제거; 후보 추출을 전역 카탈로그 어휘가 아닌 **정답 op 어휘 기준**으로; T 전 seed 실현성 검사로 `leave feedback` 류의 도달 가능성 보장; alias 예산 우회 차단(1 alias = 1 타깃, 규칙은 후보어 + 문맥 1개 → 타깃 1개); hidden을 본 컨트롤러와 B..C 튜닝 주체의 역할 분리 명문화; 다의어 동사는 메서드 상위집합; 기능어 목록 최소화; 타깃에 summary 포함; R5/R6 기계 분류; Round 1 섹션 해시 AC; negative 규칙 machine/reviewer 분리 — 전부 반영. **사용자 결정**: 검수자 권고에 따라 **일반 개념 동의어 인벤토리(§7.0)**를 T 전에 clean context로 생성·동결(동사 인벤토리와 같은 위상).
- 2026-10-02 외부 검수 2차(v1.1→v1.2): notes 스키마를 라운드별로 분기(`candidate_word`는 round ≥ 2만 필수, Round 1 항목 그대로 로드되는 회귀 테스트); 사전 병합분의 동결 해시 `lexicon_aliases_sha256` 추가와 `concept_lexicon.json` 산출물 명시; 생성 단계는 **ChatGPT 임시 채팅(메모리·기록 없음)** 으로 고정("새 대화"는 독립성 보장이 아님); B..C 동안 봉인 평문을 **사용자 보유 passphrase로 암호화하고 평문 삭제**(worker 환경에서 읽을 수 없음을 물리적으로 보장), D에서 사용자가 복호화. P1 반영: 개념당 synonym ≤ 5 기계 강제(사전순 앞 5개), 정규화 후 카탈로그 비교, 폐기 항목에 `catalog_df`·개념 기록, `leave` → POST|DELETE 상위집합, `--verb-report`는 진단 전용, 타깃 어휘에서 path_noise·식별자형·제품 힌트 제거, worker 출력 sha·실행 횟수 기록, R5의 ∃ 의미론.
- 2026-10-02 외부 검수 3차(v1.2→v1.3): 임시 채팅은 **Unpersonalized** 선택 필수(Personalized 임시 채팅은 메모리·맞춤 지시를 사용함), 서버측 30일 보존은 인정하고 "완전 stateless 저장"이라 쓰지 않음; **worker 브리프를 T에서 동결**(`round2-worker-brief.md` 커밋, sha를 `round_freeze`에)하고 B..C의 alias 추가를 **사전 선언된 결정적 선택기**(`--propose-aliases`)로 바꿔 컨트롤러·worker의 선택 여지 제거, 다중 실행 시 첫 AC-valid 출력 채택; **사전–seed 호환 게이트**(seed에 등장하는 synonym은 `lexicon_targets ∩ allowed_targets ≠ ∅`일 때만 유지, 아니면 폐기해 seed 후보로 남김); P1: synonym 타깃 = 정확히 1, stateless 의미 검토자(binary reject만), 정규화 카탈로그 어휘 정의 고정, AC-18을 자동 체크포인트와 attestation으로 분리, "암호학적으로 접근 불가(선언된 위협 모델)" 표현, APFS 암호화 볼륨 대안 명시.
- 2026-10-02 외부 검수 4차(v1.3→v1.4): B..C 튜닝을 **단방향 파이프라인**으로 고정(상수는 B 시점 alias 상태에서 정확히 1회 선택 → alias는 그 상수에서 정확히 1회 제안 → 최종 검증; 재선택·재제안 금지, 최종 검증 실패면 튜닝 실패로 종료); 모든 튜닝 실행은 **B baseline을 명시적 입력**으로 삼고 worktree의 round2 상태를 읽지 않음(dirty 상태 거부); 사전의 의미 검토자도 §5.3과 **같은 stateless 실행 계약**; P1: `round_freeze` 예시 6개 필드, 사전 처리 순서 단일화(정규화 → 구조 검사 → stateless 의미 reject → 개념당 사전순 5개 → seed 호환 게이트 → 병합), §13 타깃 문구, 제안기의 working alias 상태 명시, `targets_by_seed`로 현재 seed의 타깃만 순회, AC-20(상수 1회·alias 1회 불변).
- 2026-10-02 외부 검수 5차(v1.4→v1.5): **소스 스냅샷 S를 H 직후, 모든 카탈로그 의존 pre-T 작업 전에 생성**하고 T 이후 재스냅샷 없음(한 라운드가 하나의 op universe만 사용); **hidden 의미 검토자도 §5.3 stateless 실행 계약**(입력: hidden 평문 + internal catalog + 규칙만; 컨트롤러는 디스패치·적용만); AC-20을 **run_id 기준**으로 재정의(run마다 상수 1회→alias 1회, 전체에서 adopted run 1개, 모든 AC-valid run의 baseline·output sha 동일); P1: 제안기는 각 seed 차례에 working 상태로 재평가해 이미 통과면 `resolved_by_prior_change`로 건너뜀, AC-13 범위를 결정적 단계로 한정, §7.0 생성 문장을 §5.3 계약으로 통일, `--feasibility`→`--method-safety`, §13 오염 표현 정정.
- 2026-10-02 외부 검수 6차(v1.5→v1.6): **hidden 생성 프롬프트와 hidden 의미 검토 프롬프트를 T에서 동결**(`round2-hidden-generation-prompt.md`, `round2-hidden-reviewer-prompt.md`, 해시 2개 추가 → `round_freeze` 8개) + 검토 실행 수명주기 고정(배치마다 첫 parseable/valid 출력 채택, valid 이후 의미 재실행 금지, transport/parse 실패만 동일 입력 재시도, 모든 attempt 기록, 재요청 항목도 같은 절차); 튜닝 결과 해시를 **`result_sha256`(final_constants + alias_patch canonical)** 과 `run_log_sha256`(run_id·진단 포함)으로 분리하고 AC-20·결정성 검증은 `result_sha256` 기준; P1: S의 `source_registry_fingerprint`·source별 `source_spec_sha256`을 `round_freeze` 항목에 저장, 영속 artifact 공통 provenance 스키마 `generated_from`, `baseline_sha256` 정의 고정.
- 2026-10-02 외부 검수 7차(v1.6→v1.7): pre-T 작업을 **의존 순서**로 고정(동사 인벤토리 → method-safety → 필요 시 수정·재실행 → `verb_inventory_sha256` **확정** → 개념 토큰 → 사전 생성·검사·의미 검토 → seed 게이트 → 후보 → 브리프/프롬프트 → T; 사전 검사의 "동사 키 아님" 규칙은 확정된 인벤토리 기준); **Round 2 도구 코드 전부를 H에서 완성하고 `tooling_code_sha256`으로 T에 동결**, T..D 동안 변경 금지, C는 T 동결값 재확인 마커(`evaluation_code_sha256 == tooling 부분집합 해시`); P1: 사전 생성에도 first-valid 수명주기, §4 예시에 `generated_from`, S 무결성 체크포인트(B..C 시작·D 직전), 튜닝 실패 시 의미 고정(adopted 0, C/D 생략, 봉인 유지).
- 2026-10-02 외부 검수 8차(v1.7→v1.8): §5.1의 stale 순서 문장 제거(의존 순서가 유일한 권위), T의 `verb_methods`는 확정 인벤토리; **튜닝 실패 후 hidden 재사용 규칙 폐기**(컨트롤러·검토자가 B 전에 평문을 봤으므로 다음 라운드에 재사용 불가 — 폐기하고 새로 생성); **AC를 공통 / 성공 분기 / 튜닝 실패 분기로 분리**(튜닝 실패도 검증 가능한 종료 상태); P1: 무결성 테스트 파일도 T..D 불변 목록에, `evaluation_code_sha256_at_T`를 `round_freeze`에 저장해 C는 단순 동등 검사, H′ 발생 시 최종 housekeeping 커밋을 readiness에 하나로 기록.
- 2026-10-02 외부 검수 9차(v1.8→v1.9): **AC 전면 재작성** — 모든 행이 분기표 없이 단독으로 참/거짓 판정되도록 분할(AC-01a/b, AC-05 "종료 커밋까지", AC-06a/b, AC-15a/b, AC-18a-B/18a-D, AC-20a/b); **튜닝 실패 종료 커밋 F** 정의(H → T → B → F; whitelist = 튜닝 로그 + readiness; 실패한 상수·alias는 정책 파일에 절대 적용되지 않음 — B 상태 유지); P1: H′ 후 pre-T artifact를 의존 DAG에 따라 재생성(S는 fingerprint 동일 시 재사용), §5.2 item 2를 "결과 확인"으로, §11 상태 모델에 실패 분기 필드 null/not_applicable.
- 2026-10-02 구현 계획 검수 6차 반영(v1.12→v1.13): AC-19를 분기별로 분리 — 성공: 적용된 round2 추가분 == 결정적 제안기 재실행 결과; 튜닝 실패: 적용 추가분 0, 제안기 최종 결과가 39/39·14/14 미달; abort: 적용 추가분 0(정책 == B), rejected run의 후보 `result_sha256` == 제안기 재실행 결과, 그 run의 `reject_evidence`(실패 테스트 id·출력 sha)가 로그에 존재. 브리프·프롬프트 동결 조건과 의미 검토 수명주기 조건은 공통 그대로.
- 2026-10-02 구현 계획 검수 4차 반영(v1.11→v1.12): abort 분기를 완전한 종료 분기로 승격 — 종료 커밋 := D | F | X; 절차 표기 H → T → B → (C → D | F | X); 도구 불변·`.enc` 체크포인트·attestation 문구를 세 종료 커밋 모두에 적용; AC-01d(abort 구간 규칙), AC-18a-X 행 추가; AC-07/AC-14/AC-16은 성공·튜닝 실패 분기에만 적용(abort의 원인이 바로 그 테스트 실패이므로), 새 공통 AC-23: T와 B 커밋 시점에 전체 오프라인 테스트 통과(ledger 기록); AC-22는 실패 테스트 이름·출력을 증거로 보존.
- 2026-10-02 구현 계획 검수 3차 반영(v1.10→v1.11): **abort 분기 추가** — 튜닝이 39/39·14/14를 만족했으나 정식 전체 테스트가 실패해 run이 `rejected`된 경우(도구·테스트 결함), 같은 라운드를 H′에서 재시작하지 않는다(컨트롤러·검토자가 이미 hidden 평문을 봤으므로). 종료 커밋 **X**(`docs/phase3-readiness.md`만 변경; 정책 파일은 B 상태; hidden 미평가; 암호문 보관; `reject_reason`·실패 테스트 출력 기록)로 Round 2를 소비하고 다음 시도는 새 hidden set의 Round 3이다. AC-22 추가, AC-18a-X 체크포인트, 상태 모델에 abort 분기.
- 2026-10-02 외부 검수 10차(v1.9→v1.10): **P0 없음 — "구현 계획으로 진행 가능"**. P1 문구 정리: AC-04는 B 봉인 과정의 체크포인트(F에서 평문 재독 금지), AC-19의 첫 AC-valid 채택은 "존재하면", 절차 표기를 H → T → B → (C → D | F)와 "종료 커밋까지"로 통일, §5.4 체크포인트에 F 반영, attestation의 평가 횟수를 분기별로, §10.3을 성공 분기 한정으로.

---

## 1. 목표

> 동사 인벤토리, 일반 개념 사전, seed 유래 alias 후보 목록을 **hidden set 생성 전에** 동결하고, B..C 구간에서는 후보 목록 안의 alias만 예산 내로(1 alias = 1 타깃) 추가하며, 상수는 grid 전수 재선택한 뒤, 얼린 커밋에서 봉인 집합을 한 번만 측정한다. 스코어러 코드와 게이트 정의는 바꾸지 않는다. hidden을 본 주체는 B..C의 정책 선택에 관여하지 않는다.

## 2. 범위

### 2.1 포함
1. `verb_methods` 인벤토리 교체(§6) + seed 메서드 안전성 검사.
2. 일반 개념 사전 `concept_lexicon.json`(§7.0) — clean-context 생성, 기계 검사, T 동결.
3. seed 유래 alias 후보 목록 `alias_candidates.json`(§7.1) — 결정적 생성, T 동결; R5/R6 기계 분류.
4. 봉인·진단·튜닝 도구의 라운드 일반화(§8); `policy.py`의 alias notes `origin` 허용값 확장(§8, 유일한 production 변경).
5. 새 hidden set 생성·봉인(§5), B..C 튜닝(상수 grid + 후보 alias), C/D, readiness Round 2 섹션.

### 2.2 제외
`search.py` 변경, `policy.py`의 notes-origin 규칙 외 변경, `POLICY_VERSIONS` bump, 게이트 수치·hidden set 크기 변경, 검색 로그 처리, 픽스처에 r1 정답 op 추가.

## 3. 설계 원칙

1. **Vocabulary before structure.** R5/R6은 어휘로 고친다; 구조 신호는 Round 1 그대로.
2. **Inventories, not instances.** 동사 인벤토리와 개념 사전은 특정 질의와 무관하게 만들어 T에서 통째로 동결한다.
3. **Pre-register, then budget.** seed 유래 alias는 T에서 동결된 후보 목록 안에서만, 1 alias = 1 타깃, 라운드당 ≤ 15, seed당 1개.
4. **Roles separated by what they have seen, and plaintext physically absent.** hidden 평문을 본 주체(seal/review controller)는 B 이후 정책 선택에 관여하지 않고, B..C 동안 평문은 어떤 에이전트도 읽을 수 없는 상태(사용자 보유 passphrase로 암호화, 평문 삭제)로 둔다(§5.6).
5. **Same seal, same gate.** 생성 규칙·봉인·평가 1회·게이트는 Round 1 §5/§5.9와 동일.
6. **Round-independent tooling.** 도구와 테스트는 `round_freeze.json`의 현재 라운드를 읽고 이전 라운드 artifact를 깨뜨리지 않는다.

## 4. 파일 구조

| 파일 | 변경 |
|---|---|
| `tools/atlassian_docs/intelligence/data/search_ranking.json` | T: `verb_methods` 교체; B..C: `constants`만 |
| `tools/atlassian_docs/intelligence/data/search_aliases.json` | T: 개념 사전 항목 병합(§7.0, `origin: "lexicon-r2"`); B..C: round2 alias/rule + notes |
| `tools/atlassian_docs/intelligence/data/alias_candidates.json` | 신규(T): §7.1 |
| `tools/atlassian_docs/intelligence/data/concept_lexicon.json` | 신규(T): §7.0 검사·정규화를 통과한 사전(`{"round": 2, "generated_from": {"registry_fingerprint", "spec_sha256", "inputs": {"verb_inventory": …, "aliases": …, "raw_generation": …, "semantic_review": …}, "tool_version"}, "prompt_sha256", "raw_sha256", "review_output_sha256", "lexicon": {...}, "rejected": {...}}`) |
| `tools/atlassian_docs/intelligence/policy.py` | T 전(housekeeping 커밋 H): notes `origin` 스키마를 라운드별로 분기(§8) — Round 1 항목은 그대로 로드 |
| `tests/benchmarks/round_freeze.json` | 리스트; round 2 항목 = `{"round": 2, "structure_sha256", "verb_inventory_sha256", "concept_lexicon_sha256", "lexicon_aliases_sha256", "alias_candidates_sha256", "worker_brief_sha256", "hidden_generation_prompt_sha256", "hidden_reviewer_prompt_sha256", "tooling_code_sha256", "evaluation_code_sha256_at_T", "source_registry_fingerprint", "source_spec_sha256": {"<source>": "…"}}` (**`commit_T` 없음** — T SHA는 readiness/B 메타에 기록; 해시 10개 + S 출처 2개 필드). `lexicon_aliases_sha256` = `search_aliases.json`에서 `notes[k].origin == "lexicon-r2"`인 alias와 notes 부분집합의 canonical sha256 — B..C에서 round2 항목이 추가돼도 사전 부분의 불변을 검증 |
| `tests/benchmarks/round_seal.py` | `round1_seal.py` 이름 변경 + `--round N` |
| `tests/benchmarks/round2-worker-brief.md` | 신규(T): B..C worker 브리프 전문(§5.2.7) |
| `tests/benchmarks/round2-hidden-generation-prompt.md`, `round2-hidden-reviewer-prompt.md` | 신규(T): hidden 생성 프롬프트 템플릿(generator catalog 삽입 자리만)과 의미 검토 프롬프트 전문(§5.2.7, §5.3) |
| `tests/benchmarks/alias_candidates_tool.py` | 신규: 후보 목록·R5/R6 분류·개념 토큰 목록 생성 |
| `tests/benchmarks/concept_lexicon_check.py` | 신규: 개념 사전 기계 검사·정규화 |
| `tests/tune_search_ranking.py` | `--alias-change` 후보·예산·형태 검사, 로그에 `round` |
| `tests/diag_search_queries.py` | seal 키·artifact 이름을 라운드에서 유도 |
| `tests/benchmarks/search_queries.json` | T: seed `failure_classes` 기계 분류 기록; B: 봉인 메타 + `round2_seal`; D: 평문 |
| `tests/benchmarks/round2-final.json`, `search-tuning-round2.jsonl` | D(성공 분기만) / B 이후 종료 커밋까지 |
| `tests/benchmarks/test_evaluator.py`, `tests/intelligence/test_policy.py`, `tests/intelligence/test_search.py`, `tests/test_diag_search_queries.py`, `tests/test_tune_search_ranking.py` | §10 |
| `docs/phase3-readiness.md` | Round 2 섹션 |
| `README.md`, `AGENTS.md` | 한 단락 |

불변(baseline `95b8de0`, AC-09): Round 1 spec §4 불변 목록 + `search.py`, `operation_quirks.json`, `tests/benchmarks/round1-final.json`, `search-tuning-round1.jsonl`, bench 안 `round1_seal` 객체, readiness의 Round 1 섹션(마커 `## Search Quality Round 1 — decision record` 부터 다음 `## ` 전까지의 canonical 텍스트 해시를 pre-work 상태에서 고정). `policy.py`는 커밋 H 이후 불변.

가변 구간 규칙(AC-01a/b): `search_aliases.json`(round2 항목)과 `search_ranking.json.constants`는 B..C에서만; `verb_methods`, `alias_candidates.json`, `concept_lexicon` 병합분, `failure_classes` 분류는 T에서만; `policy.py`는 H에서만.

## 5. 벤치마크 절차 (커밋 순서 H → T → B → (C → D | F | X); 종료 커밋 := D | F | X)

### 5.1 커밋 H (housekeeping, T 전) + 소스 스냅샷 S
`policy.py` notes-origin 규칙 확장(§4) + **Round 2 도구 코드 전부**(§8: `round_seal.py`, `alias_candidates_tool.py`, `concept_lexicon_check.py`, `tune_search_ranking.py`의 제안기·검증기·파이프라인, `diag_search_queries.py`, `evaluator.py`) + 테스트. 어휘·벤치마크 무변경. **H 이후 이 도구 파일들은 종료 커밋(D, F 또는 X)까지 변경 금지**(v1.7): 결정적 선택기·제안기·평가기의 코드가 hidden 생성 뒤에 바뀌면 "결정적"이 사후 조정 가능한 선택기가 되므로, T의 `round_freeze`에 `tooling_code_sha256`(도구 파일 목록의 canonical 연결 해시)을 기록하고 C의 `evaluation_code_sha256`은 그 부분집합(평가 경로 6개 파일)의 해시로서 T 값과 같아야 한다. pre-T 단계에서 도구 결함이 발견되면 **T 전에** 고치고 H′로 커밋한다(T 이후 발견 시 라운드 중단·재시작). readiness는 최종 housekeeping 커밋(H 또는 마지막 H′)을 `housekeeping_commit` 하나로 기록하고 AC-05는 그 커밋을 기준으로 한다. H′ 이후에는 영향받는 pre-T artifact를 의존 순서에 따라 재생성한다(도구가 바뀌면 verb-report부터 전부 재실행; S는 fingerprint·spec sha가 같으면 재사용). 무결성 테스트 파일(`tests/benchmarks/test_evaluator.py`, `tests/test_tune_search_ranking.py`, `tests/test_diag_search_queries.py`, `tests/intelligence/test_policy.py`)도 같은 불변 목록에 포함한다. `round_freeze`에는 `evaluation_code_sha256_at_T`(평가 경로 6개 파일의 T 시점 해시)도 저장해 C의 검증이 단순 동등 검사가 되게 한다.

**pre-T 의존 순서(v1.7, 고정)**: H → S → `--verb-report` → 동사 인벤토리 초안 → `--method-safety` → (위반 시 인벤토리 수정 → 재실행) → **`verb_inventory_sha256` 확정** → 개념 토큰 목록 → 사전 생성 → 기계 검사(확정 인벤토리 기준) → stateless 의미 검토 → 개념당 5개 절단 → seed 호환 게이트 → 사전 병합 → 후보 목록 → R5/R6 분류 → worker 브리프·프롬프트 → T. 인벤토리 확정 뒤에는 어떤 단계도 인벤토리를 바꾸지 않는다(바꾸면 사전부터 재실행).

**소스 스냅샷 S(v1.5)**: H 직후, 카탈로그에 의존하는 어떤 pre-T 작업(개념 토큰 목록, `--verb-report`, method-safety, 사전 게이트, 후보 목록)보다 **먼저** `~/.atlassian_api_updater/round2-cache/`(`$ATLASSIAN_DOCS_ROUND2_CACHE`; 존재 시 거부)를 만들고 registry fingerprint·spec sha를 readiness에 고정한다. 이후 모든 단계(pre-T 도구, hidden 생성용 generator catalog, B..C 튜닝, D 평가)는 S만 읽는다. **T 이후 재스냅샷은 없다.** 각 도구는 `generated_from.registry_fingerprint`를 기록하고, S의 fingerprint와 다르면 거부한다. 이후 모든 단계의 순서는 아래 **pre-T 의존 순서**(유일한 권위)를 따른다.

### 5.2 커밋 T (동결)
1. `search_ranking.json` `verb_methods` ← §6 인벤토리(**확정본** — method-safety는 이미 §5.1 순서에서 끝났다).
2. **메서드 안전성 검사 결과 확인**(검사 자체는 §5.1 순서에서 T 전에 끝났고 인벤토리는 확정본; T에는 그 결과 파일을 포함한다)(`alias_candidates_tool.py --method-safety`; 의미: 인벤토리가 seed에 잘못된 메서드 불일치 감산을 만들지 않는지): seed 39건 각각에 대해, 질의 unigram ∩ 인벤토리의 허용 메서드 교집합이 (a) 공집합(의도 0)이거나 (b) 정답 op 메서드를 포함해야 한다. 위반(허용 집합이 정답 메서드를 배제)이 있으면 그 동사를 상위집합으로 넓혀 재실행 — **이 조정은 사전 생성 전에 끝나고 `verb_inventory_sha256`로 확정된다.** 결과(통과 목록)는 readiness에 기록. 사전의 "동사 키 아님" 검사는 이 확정 인벤토리를 기준으로 한다.
3. **사전–seed 호환 게이트**(`alias_candidates_tool.py --lexicon-gate`, T 전): 사전 synonym `w`가 어떤 seed 질의의 unigram에 등장하면 `lexicon_targets(w) ∩ allowed_targets(w) ≠ ∅`(§7.1.6 정의, seed의 정답 op 어휘)일 때만 유지하고, 교집합이 비면 그 사전 항목을 폐기(`rejected[w].reason = "seed-incompatible"`)해 seed 유래 후보로 남긴다. seed만 사용하므로 독립성 훼손 없음; 사전 오생성이 seed 단어를 선점해 B..C에서 복구 불가능해지는 상황을 막는다.
4. 개념 사전 병합: `concept_lexicon.json` 항목을 `search_aliases.json.aliases`에 병합(`notes[word] = {"origin": "lexicon-r2", "seed_query_id": null, "failure_classes": [], "evidence": "concept lexicon r2"}`). 충돌(이미 있는 alias 키)은 기존 항목 우선, 사전 항목은 버림(기록).
5. `alias_candidates.json` 생성(§7.1) — 사전 병합 **후**에 실행(사전이 이미 잇는 토큰은 후보에서 자연히 빠진다).
6. seed `failure_classes` 기계 분류(R5/R6)를 bench에 기록(§0.2). 기존 R1–R4 표기는 유지하고 R5/R6를 추가.
7. **worker 브리프 동결**: `tests/benchmarks/round2-worker-brief.md`(B..C 튜닝 worker에게 전달할 브리프 전문 — 실행할 명령 순서, 허용 파일, 보고 형식만; seed 분석·힌트 없음)를 T에 커밋하고 sha를 `round_freeze.json`에 `worker_brief_sha256`으로 기록. B 이후 컨트롤러는 이 파일을 그대로 전달만 할 수 있다. 같은 커밋에 **hidden 생성 프롬프트 템플릿**과 **hidden 의미 검토 프롬프트**(§5.3)를 동결한다 — 컨트롤러는 Round 1 hidden을 본 상태이므로 B 전 프롬프트 표현 변경이 생성·검토 결과를 유도할 수 있어, 두 프롬프트의 문구는 T 이후 바꿀 수 없다(재요청 피드백은 §5.3의 고정 형식만).
8. `round_freeze.json` round 2 항목(해시 10개 — 8개 + `tooling_code_sha256` + `evaluation_code_sha256_at_T` — + S 출처: `source_registry_fingerprint`, source별 `source_spec_sha256`; §4).
9. T SHA와 S fingerprint(§5.1)를 readiness에 기록. 스냅샷은 §5.1의 S를 그대로 사용(재복사 없음).

### 5.3 생성 (stateless clean context, Round 1 §5.4 규칙)
- **생성기 실행 형태(v1.3, 사전 §7.0과 hidden 모두 동일)**: 1순위는 메모리 없는 stateless API 호출, 실무 2순위는 ChatGPT **임시 채팅 + Unpersonalized**. 임시 채팅은 시작 전 Personalized/Unpersonalized를 고를 수 있고 Personalized는 기존 메모리·맞춤 지시를 사용하므로 **Unpersonalized 선택이 필수**이며, 생성 전에 UI에서 그 상태를 확인하고 readiness에 `temporary_chat_unpersonalized: true`를 attestation한다. 일반 "새 대화"는 계정 메모리를 통해 과거 대화(Round 1 실패어 등)가 섞일 수 있으므로 금지. 임시 채팅은 채팅 기록에서 다시 열 수 없다(OpenAI가 안전 목적으로 최대 30일 사본을 보관할 수 있으므로 "완전 stateless 저장"은 아니지만 이 벤치마크의 누수 모델에는 영향 없음). 생성 결과는 컨트롤러가 즉시 추출해 sha256을 계산하고, 저장하지 않고 탭을 닫는다. readiness에 실행 형태를 기록.
- 생성기에는 generator catalog + 규칙만. Round 1 hidden 질의·seed·사전·실패 목록은 주지 않는다.
- negative 규칙 분리:
  - **machine**: 질의의 정규화 unigram 열이 어떤 op의 summary 또는 마지막 리터럴 세그먼트의 unigram 열과 **완전히 같으면** 거부(토큰 정규화 후 exact phrase).
  - **reviewer**: "이 질의에 정답 op가 존재하면 negative가 아니다"; 유인 오답이 실제로 오답인지.
- **hidden 의미 검토자(v1.5)**: §5.3 실행 계약과 동일하게 stateless API 또는 Unpersonalized 임시 채팅에서 실행한다. 입력은 hidden 평문 + internal catalog + 검토 규칙(§5.3 reviewer 규칙, 정답 op 존재 여부·유인 오답의 오답 여부)뿐이며 seed·alias·scorer·Round 1 실패·repo 접근 없음. 출력은 레코드별 accept/reject + 사유. 컨트롤러는 검토자를 디스패치하고 결과를 적용(재요청 피드백 구성)할 뿐 accept/reject를 직접 결정하지 않는다. **프롬프트는 T에서 동결된 `round2-hidden-reviewer-prompt.md` 전문 그대로**(생성 프롬프트도 `round2-hidden-generation-prompt.md` 템플릿 그대로). **실행 수명주기(v1.6)**: 후보 배치마다 첫 parseable/valid 출력을 채택하고, valid 출력 이후 의미 재실행은 금지; transport/API/parse 실패만 동일 입력·동일 프롬프트로 재시도; 모든 attempt의 입력/출력 sha256과 성공/실패 상태를 기록. 재요청으로 받은 대체 레코드도 같은 절차(기계 검사 → 같은 프롬프트의 검토)를 거친다. 재요청 피드백은 고정 형식("레코드 N 거부: <machine rule id 또는 reviewer 사유 코드>")만 허용.
- machine check 0 violation → reviewer check → 재요청은 최소 피드백.

### 5.4 커밋 B (봉인) + 평문 격리
`round_seal.py seal --round 2` → `round2_seal`(형식 Round 1과 동일). readiness에 T SHA, B SHA, 생성 프롬프트/결과 sha, 재요청 횟수 기록.

**평문 격리(v1.2)**: B 커밋 직후, 봉인 평문(`~/.atlassian_api_updater/sealed/round2-sealed.json`)을 **사용자가 자신의 터미널에서** 사용자만 아는 passphrase로 암호화하고 평문을 삭제한다(예: `openssl enc -aes-256-cbc -pbkdf2 -in round2-sealed.json -out round2-sealed.json.enc && rm round2-sealed.json`). 에이전트(컨트롤러·worker 모두)는 passphrase를 알지 못하며 세션에 입력하지 않는다. 컨트롤러는 `.enc` 존재와 평문 부재를 확인해 readiness에 기록한다(자동 체크포인트: B 직후와 종료 직전(D, F 또는 X)에 `.enc` 존재 ∧ 평문 부재 ∧ `.enc` sha256 동일; 그 사이 전체 기간은 컨트롤러 attestation. F와 X에서는 복호화하지 않는다). 이 격리의 의미는 "선언된 위협 모델(에이전트의 일반 파일 탐색·도구 읽기)에서 암호학적으로 접근 불가"이며, 포렌식 삭제나 같은 UID의 악성 프로세스 격리는 목표가 아니다. 더 명확한 경계를 원하면 macOS 암호화 APFS sparsebundle에 평문을 두고 B 직후 unmount, D에서 사용자가 mount하는 방식을 써도 된다(동등하게 허용). internal catalog(`round2-internal-catalog.json`)는 hidden 정보를 담지 않으므로 평문으로 두어도 된다. 생성이 임시 채팅에서 이루어졌으므로 브라우저 경로로도 평문에 닿을 수 없다. 같은 파일시스템·같은 계정에서 "경로를 알리지 않음"은 격리가 아니므로 이 단계는 필수다.

### 5.5 B..C (튜닝)
- 튜닝 주체(tuning worker)는 §5.6의 역할 규칙을 따른다.
- **동결된 절차만 실행(v1.3)**: worker는 T에서 동결된 `round2-worker-brief.md`의 명령 순서를 그대로 수행한다. 컨트롤러가 B 이후 worker에게 보낼 수 있는 메시지는 브리프 전문과 사전 정의 명령("브리프의 절차를 실행", "다시 실행")뿐이며 seed 분석·힌트·선택 지시는 금지.
- **단방향 파이프라인(v1.4)** — 전체가 하나의 순수 함수 `tune_round2(b_aliases, b_ranking, snapshot, frozen_candidates, seed, regression) -> (final_constants, alias_patch, log)`:
  1. `base_aliases` := B 시점의 alias 상태(`alias_candidates.json.generated_from.aliases_sha256`와 일치해야 하며, 불일치면 즉시 실패). `baseline_sha256` := sha256(canonical({`b_aliases_sha256`, `b_ranking_sha256`, `snapshot_registry_fingerprint`, `alias_candidates_sha256`, `seed_benchmark_sha256`, `regression_benchmark_sha256`})) — 함수 입력 전체의 동일성.
  2. `selected_constants` := `select_candidate(grid, base_aliases, seed, regression)` — grid 전수, **정확히 1회**.
  3. `alias_patch` := `propose_aliases(base_aliases, selected_constants, frozen_candidates, seed, regression)` — **정확히 1회**(§7.2).
  4. `final_config` := `selected_constants + alias_patch`; 최종 seed/regression 검증(39/39·14/14).
  5. **상수 재선택·alias 재제안 금지.** alias 제안은 상수 재선택을 유발하지 않는다. 최종 검증이 실패하면 그 run은 `tuning_failed: true`로 기록되고 `adopted` run은 0개이며 grid→alias 루프를 다시 돌리지 않는다. 이 경우 C/D 대신 **종료 커밋 F**를 만든다(H → T → B → F): F의 whitelist는 `search-tuning-round2.jsonl`과 `phase3-readiness.md`뿐이며, **실패한 `final_constants`·`alias_patch`는 정책 파일에 적용하지 않는다**(`search_ranking.json.constants`와 `search_aliases.json`은 B 상태 그대로; 순수 함수의 실패 결과는 로그에만 남는다). F에는 `tuning_failed: true`, `adopted` 0, 실패한 `result_sha256`, `.enc` sha256, 상태 "Round 2 tuning failed"가 기록된다. **봉인된 hidden set은 재사용하지 않는다**: 컨트롤러와 의미 검토자가 B 전에 평문을 봤으므로 다음 라운드의 정책·프롬프트·도구 결정에 그 기억이 섞일 수 있다. 암호문은 기록용으로 보관하되(`.enc` sha256을 readiness에), 다음 라운드는 새 hidden set을 생성한다.
  6. **입력은 항상 B baseline**: 실행은 worktree의 현재 `constants`·round2 alias를 읽지 않고 B 상태(파일 sha로 확인)에서 시작한다. worktree에 round2 변경이 이미 있으면 "dirty round2 state"로 거부하거나(기본) `--from-baseline`으로 B 상태를 복원해 실행한다. 따라서 재실행은 같은 함수의 같은 입력이며, 유효한 출력은 byte-identical해야 한다.
- worker도 컨트롤러도 상수·alias를 고르지 않는다. 각 alias 추가는 `--alias-change`로 기록·검증된다.
- **출력 선택 규칙**: worker 실행이 여러 번이면(예: 도구 오류로 재실행) **첫 번째 AC-valid 출력**(검증기 통과 + 테스트 통과)을 채택한다. 모든 실행이 B baseline에서 시작하므로 유효한 출력의 **canonical 튜닝 결과**는 byte-identical해야 하며, 다르면 그 자체가 결함으로 기록된다(채택 불가, 원인 조사 후 재실행). 해시는 둘로 분리한다: `result_sha256` = sha256(canonical({`final_constants`, `alias_patch`})) — 결정성 검증 대상; `run_log_sha256` = sha256(canonical(run_id·타임스탬프·진단을 포함한 전체 로그)) — provenance 기록용. 실행 횟수와 각 출력 sha를 readiness에 기록.

### 5.6 역할 분리 (v1.1, v1.3 보강)
| 역할 | 볼 수 있는 것 | 금지 |
|---|---|---|
| seal/review controller | hidden 평문(B 전·D만), internal catalog, 모든 repo 파일 | B 이후 alias 선택·상수 선택·튜닝 피드백 전달. 할 수 있는 것은 절차 명령(스크립트 실행 지시, 커밋, 리뷰 디스패치)뿐 |
| tuning worker (B..C 구현 서브에이전트) | seed/regression, 동결된 후보 목록·사전·인벤토리, 스냅샷, 튜닝 스크립트 | hidden 평문(B..C 동안 기계상 존재하지 않음 §5.4)·internal catalog 접근 |
| semantic reviewer (B 전, §5.3 stateless 계약으로 실행) | hidden 평문 + internal catalog + 규칙 | seed·alias·scorer·Round 1 실패·repo; 컨트롤러의 직접 판정 |
| 사용자 | passphrase | — |

attestation 항목: (1) "B..C 동안 봉인 평문은 튜닝 환경에서 읽을 수 없는 상태였다"(암호화 시각·`.enc` sha256·평문 부재 확인); (2) "hidden을 본 주체가 B..C의 alias/상수 선택에 관여하지 않았다"; 증거로 worker 브리프 sha256, worker 실행 횟수, 각 실행의 출력(패치) sha256을 readiness에 기록해 컨트롤러의 선별(cherry-picking) 여지를 줄인다.

### 5.7 C / D / 게이트
- C: 빈 커밋; `evaluation_code_sha256` 대상 6개 파일(기존 4 + `round_seal.py`, `alias_candidates_tool.py`; `concept_lexicon_check.py`는 T 전 도구라 제외). **C는 새 동결 시점이 아니라 T에서 얼린 도구가 그대로임을 재확인하는 마커**: C에서 계산한 값 == `round_freeze.evaluation_code_sha256_at_T`(단순 동등 검사), 다르면 D를 진행하지 않는다. S 무결성 체크포인트: B..C 시작 시와 D 직전에 실제 S의 registry fingerprint·spec sha == `round_freeze` 출처 필드를 assert.
- D: 사용자가 자신의 터미널에서 복호화(`openssl enc -d …`); 컨트롤러가 평문 sha256 == `round2_seal`임을 확인한 뒤 `diag --round 2 --bench <sealed> --cache-dir <round2-cache> --json tests/benchmarks/round2-final.json` 1회; unseal; readiness. whitelist = `search_queries.json`, `round2-final.json`, `phase3-readiness.md`.
- 게이트: held_out ≥ 15/16, negative 0/8. 보조 지표 `held_out_top3` 기록만.

## 6. 동사 인벤토리 (`verb_methods`, T 동결)

규칙: 한 동사는 한 메서드 집합; 질의 동사 여럿이면 교집합, 공집합이면 0(Round 1 §6.3). **다의어 원칙(v1.1)**: 오판은 무신호가 아니라 감산을 만들므로, 두 가지 이상의 메서드로 자연스럽게 읽히는 동사는 plausible methods의 **상위집합**을 쓴다. 메서드를 전혀 결정하지 않는 동사(`hand, give, put, take, bring, keep, manage, handle, work, do, use`)는 넣지 않는다. `leave`는 "leave feedback"(POST)과 "leave a workspace"(DELETE) 양쪽으로 읽히므로 상위집합 `["POST", "DELETE"]`로 넣는다(seed 예외가 아니라 다의어 원칙의 적용).

```json
"verb_methods": {
  "get": ["GET"], "fetch": ["GET"], "read": ["GET"], "list": ["GET"], "find": ["GET"], "show": ["GET"],
  "view": ["GET"], "browse": ["GET"], "look": ["GET"], "inspect": ["GET"], "retrieve": ["GET"],
  "display": ["GET"], "see": ["GET"], "lookup": ["GET"], "load": ["GET"], "download": ["GET"], "count": ["GET"],
  "describe": ["GET"],
  "search": ["GET", "POST"], "query": ["GET", "POST"], "check": ["GET", "POST"], "open": ["GET", "POST"],
  "export": ["GET", "POST"],
  "create": ["POST"], "add": ["POST"], "post": ["POST"], "upload": ["POST"], "run": ["POST"], "submit": ["POST"],
  "start": ["POST"], "make": ["POST"], "publish": ["POST"], "send": ["POST"], "register": ["POST"], "attach": ["POST"],
  "insert": ["POST"], "invite": ["POST"], "import": ["POST"], "trigger": ["POST"], "execute": ["POST"],
  "generate": ["POST"], "copy": ["POST"], "clone": ["POST"], "duplicate": ["POST"], "link": ["POST"], "share": ["POST"],
  "comment": ["POST"], "reply": ["POST"], "log": ["POST"], "record": ["POST"], "launch": ["POST"],
  "leave": ["POST", "DELETE"],
  "update": ["PUT", "POST"], "change": ["PUT", "POST"], "edit": ["PUT", "POST"], "set": ["PUT", "POST"],
  "rename": ["PUT", "POST"], "modify": ["PUT", "POST"], "revise": ["PUT", "POST"], "rewrite": ["PUT", "POST"],
  "replace": ["PUT", "POST"], "move": ["PUT", "POST"], "transition": ["PUT", "POST"], "assign": ["PUT", "POST"],
  "reassign": ["PUT", "POST"], "reorder": ["PUT", "POST"], "rank": ["PUT", "POST"], "archive": ["PUT", "POST"],
  "restore": ["PUT", "POST"], "enable": ["PUT", "POST"], "disable": ["PUT", "POST"], "close": ["PUT", "POST"],
  "reopen": ["PUT", "POST"], "resolve": ["PUT", "POST"], "approve": ["PUT", "POST"], "mark": ["PUT", "POST"],
  "pin": ["PUT", "POST"], "toggle": ["PUT", "POST"], "configure": ["PUT", "POST"], "adjust": ["PUT", "POST"],
  "correct": ["PUT", "POST"], "fix": ["PUT", "POST"], "promote": ["PUT", "POST"], "demote": ["PUT", "POST"],
  "unassign": ["PUT", "POST", "DELETE"], "unpin": ["PUT", "POST", "DELETE"], "unlink": ["PUT", "POST", "DELETE"],
  "cancel": ["PUT", "POST", "DELETE"], "clear": ["PUT", "POST", "DELETE"],
  "delete": ["DELETE"], "remove": ["DELETE"], "discard": ["DELETE"], "trash": ["DELETE"], "drop": ["DELETE"],
  "erase": ["DELETE"], "purge": ["DELETE"], "unwatch": ["DELETE"], "unsubscribe": ["DELETE"], "revoke": ["DELETE"],
  "detach": ["DELETE"], "destroy": ["DELETE"]
}
```

- v1.0 대비: `search/query/check/open/export` GET|POST; `unassign/unpin/unlink/cancel/clear` PUT|POST|DELETE; `kick` 제거(의미 불명확); `leave` POST|DELETE.
- **동결 전 진단**: `alias_candidates_tool.py --verb-report`가 각 동사에 대해 **카탈로그에서 그 동사가 operationId/summary에 나타나는 op들의 메서드 분포**를 출력한다(예: `check` → POST 3, GET 1). 토큰 출현은 동사 용법과 명사 용법(`record`, `comment`, `query`)을 구별하지 못하므로 이 보고서는 **진단 전용**이며 자동 확장 명령이 아니다: 분포가 인벤토리 밖의 메서드를 포함하는 동사는 "검토 대상"으로 표시하고, 컨트롤러가 동사 용법인지 판단해 넓힐지 결정한 뒤 readiness에 결정과 근거를 기록한다. 단 §5.2 메서드 안전성 검사 위반은 반드시 고친다. (hidden 무관, 카탈로그만 사용.)
- `path_noise`, `product_hints`, `tuning_grid`, `baseline`은 Round 1 T2 값 그대로.
- 굴절형(`rewrites`, `showing`)은 매칭되지 않는다 — 알려진 한계(§13).

## 7. 개념 어휘

### 7.0 일반 개념 사전 `concept_lexicon.json` (v1.1, T 전 생성·동결)
- **개념 토큰 목록**(기계 생성, `alias_candidates_tool.py --concept-tokens`): 카탈로그 전 op의 경로 리터럴 세그먼트 unigram(숫자·`path_noise` 제외) ∪ tags unigram, `singular` 정규화, 출현 수와 함께. 현재 스냅샷 기준 약 356개.
- **생성(§5.3 실행 계약: stateless API 우선, 또는 Unpersonalized 임시 채팅)**: 생성기에 **개념 토큰 목록(토큰, 출현 수, 소속 제품; S에서 계산)만** 주고, 각 개념에 대해 "일반 사용자가 대신 쓸 법한 영어 단어(단일 unigram, 동사 제외)"를 최대 5개 생성하게 한다. 출력: `{"<synonym>": ["<concept>", …]}`. 프롬프트에 seed·hidden·Round 1 실패·현 alias·동사 인벤토리를 주지 않는다. 프롬프트 sha256과 원본 결과 sha256(`raw_sha256`)을 `concept_lexicon.json`과 readiness에 기록. 수명주기는 hidden 생성과 같다: 첫 parseable/valid 출력 채택, valid 이후 재생성 금지, transport/parse 실패만 동일 프롬프트 재시도, 모든 attempt 기록(의미 검토도 동일).
- **기계 검사·정규화**(`concept_lexicon_check.py`, 순서 고정): (0) synonym과 타깃을 lowercase + `singular` canonical form으로 먼저 정규화하고 중복을 합친다; (a) synonym은 `^[a-z]+$`, STOPWORDS·기능어(§7.1 목록)·동사 인벤토리 키·제품 힌트 키가 아니고, **정규화된 카탈로그 어휘에 없는 단어**여야 한다 — 정규화 카탈로그 어휘 = 전 op의 operationId·경로 리터럴 세그먼트·tags·summary의 unigram을 `singular`로 정규화한 집합(§7.1의 `expected_vocab`과 같은 토큰화; `files`→`file`처럼 정규화 후 비교하므로 굴절형 우회 없음; 이미 있는 단어는 alias가 필요 없다); (b) 각 타깃은 개념 토큰 목록에 있어야 한다; (c) synonym 하나당 타깃 **정확히 1**(두 개념을 가리키는 synonym은 폐기 — 감쇠 0.5가 두 연결을 만들어 negative에 불리); (d) **개념당 synonym ≤ 5를 역방향으로 강제** — 초과 시 그 개념을 가리키는 synonym을 사전순으로 정렬해 앞 5개만 남긴다(결정적); (e) 기존 `search_aliases.json` 키와 충돌하면 사전 항목 폐기; (f) §5.2.3 사전–seed 호환 게이트.
- **stateless 의미 검토(T 전, 품질 필터)**: 사전순 절단은 품질 기준이 아니므로 절단 **전에** 의미 검토를 둔다. 검토자는 **§5.3과 완전히 같은 실행 계약**(stateless API 또는 Unpersonalized 임시 채팅)으로 실행한다 — "빈 컨텍스트 서브에이전트"는 현재 세션의 메모리·컨텍스트를 상속할 수 있으므로 불충분. 입력은 개념 토큰 + 생성된 synonym 목록만(seed·hidden·실패 목록 없음); 각 항목을 "일반 사용자의 동의어 표현인가"로 **binary reject만** 한다(추가·수정 금지). 실행 형태와 입력/출력 sha256을 readiness에 기록.
- **처리 순서(단일 정의)**: (0) 정규화 → (a)(b)(c)(e) 구조 검사 → stateless 의미 reject → (d) 개념당 사전순 5개 → (f) seed 호환 게이트 → 병합. (d)가 의미 검토 뒤에 오므로 앞 5개 중 reject된 자리를 6번째 이후의 좋은 synonym이 채운다. 위반 항목은 **삭제**(재요청 없음 — 인벤토리이므로 recall보다 결정성을 우선)하되 `rejected[synonym] = {"reason", "targets", "catalog_df"}`로 기록한다(카탈로그에 이미 있는 다의어 synonym은 Round 3 근거).
- 병합(§5.2.3)은 `aliases`에 넣고 `alias_damping`(0.5)을 그대로 적용한다. 스코어러 변경 없음.
- 전체 크기 상한 없음(개념당 ≤ 5 × 개념 수가 자연 상한). 동결 증거는 `concept_lexicon_sha256`(파일)과 `lexicon_aliases_sha256`(병합된 부분집합, §4) 두 해시.

### 7.1 seed 유래 후보 목록 `alias_candidates.json` (T 동결)
- 도구 `alias_candidates_tool.py --candidates`가 **결정적으로** 만든다(사전 병합 후):
  1. seed 레코드마다 질의 unigram(`tokenize_unigrams` 규칙).
  2. **정답 op 어휘** `expected_vocab(seed)` = 그 seed의 `expected_top1_any` op들의 operationId·path·tags·**summary** unigram(`singular` 적용) — 동사 인벤토리 키·기능어·`path_noise`·숫자/식별자형 토큰(`id`, `{...}` 파라미터명, 순수 숫자)·제품 힌트 키 제거(타깃은 개념어여야 한다).
  3. 후보 = 질의 unigram 중 `expected_vocab(seed)`에 없고, 동사 인벤토리·기존 alias(사전 포함)·제품 힌트·기능어 어디에도 없는 토큰(**전역 카탈로그 출현 여부는 제외 기준이 아니다** — v1.1; 전역 출현 수는 `catalog_df`로 기록만).
  4. 기능어(`FUNCTION_WORDS`, 최소화 v1.1): `{my, me, this, that, these, those, another, every, which, what, who, now, today, please, into, onto, brand, own, current, some, any, all, one, two, few, several, inside, up}` — 문법·지시 기능만. `dates, planning, entry, fresh, new, exist`는 후보에 남긴다(채택은 예산이 통제).
  5. 식별자형 토큰(어떤 op의 operationId 소문자와 동일) 제외.
  6. `targets_by_seed(word)[seed_id]` = `expected_vocab(seed)`(seed별로 저장); `allowed_targets(word)` = 그 합집합(검증용). 비어 있으면 등록만.
  7. 정렬·canonical sha256 → `round_freeze.json`.
- 파일(공통 provenance 스키마 — 영속되는 모든 pre-T artifact(`concept_lexicon.json`, method-safety 결과, `alias_candidates.json`)가 같은 `generated_from` 형식을 쓴다: `{"registry_fingerprint", "spec_sha256": {source: sha}, "inputs": {<입력 파일명>: sha256}, "tool_version"}`): `{"round": 2, "generated_from": {"registry_fingerprint", "spec_sha256", "inputs": {"bench": …, "aliases": …, "ranking": …}, "tool_version"}, "candidates": {"<word>": {"seed_ids": [...], "targets_by_seed": {"s-NNN": [...]}, "allowed_targets": [...], "catalog_df": n}}, "excluded": {"<word>": "<reason>"}}`.

### 7.2 B..C 추가 규칙 (v1.1 강화)
- **결정적 제안기 `--propose-aliases`(v1.3)**: 입력 = 선택된 상수, `alias_candidates.json`, 스냅샷 seed/regression 결과. 절차: `working_aliases`는 B 시점 alias에서 시작하고, 채택된 변경은 즉시 적용되며, 이후의 모든 시도는 그 working 상태에서 평가한다. seed를 id 오름차순으로 순회하되 **각 seed 차례 시작 시 working 상태로 재평가**해 이미 통과면 `resolved_by_prior_change`로 기록하고 건너뛴다; 각 seed에 대해 그 질의의 후보어를 사전순, **그 seed의 `targets_by_seed`** 를 사전순으로 순회하며(다른 seed 때문에 허용된 타깃은 시도하지 않음) (i) direct alias `word → [target]`를 시도, 그 seed가 통과하고 다른 seed/regression이 하나도 깨지지 않으면 채택; (ii) 전부 실패하면 conditional rule(`when_all = [word, ctx]`, ctx는 그 seed 질의의 나머지 unigram 사전순)을 같은 기준으로 시도; (iii) 그래도 없으면 그 seed는 미해결로 기록. 예산 15에 도달하면 중단. 제안기는 순수 함수이며 같은 입력에 같은 출력을 낸다(테스트).
- **direct alias**: `word → [target]` — 정확히 1개 타깃, `word ∈ candidates`, `target ∈ allowed_targets(word)`.
- **conditional rule**: `when_all = [word, ctx?]`(후보어 필수 + 문맥 토큰 최대 1개, 문맥 토큰은 해당 seed 질의의 unigram), `add = [target]` 정확히 1개, `target ∈ allowed_targets(word)`.
- 예산: 추가분(alias + rule) ≤ 15, seed당 1개. notes: `origin: "round2"`, `candidate_word`(필수), `seed_query_id`, `failure_classes ∋ "R6"`, `evidence`.
- 전제: 그 seed가 선택된 상수에서 실패 중이고 추가 후 통과(`alias_change` false→true). 사람·에이전트의 수동 alias 추가는 금지(제안기 출력만 허용, 검증기가 제안기 재실행 결과와 일치하는지 확인).
- 검증기 `validate_alias_change(before, after, candidates, budget)`(순수 함수)가 형태·후보·타깃·예산·seed당 1개·`candidate_word` 일치를 검사; 위반이면 로그 미기록, exit 1.
- 동사 alias 금지. 감쇠 불변. 사전(§7.0)·phase2.5·round1 항목 수정·삭제 금지.

## 8. 도구 일반화와 production 변경

- `round_seal.py --round N`: seal 키 `round{N}_seal`; `seal`은 해당 키가 있으면 거부. `round1_seal.py` 삭제, 테스트 import 변경.
- `diag_search_queries.py`: `round_freeze.json` 마지막 항목 또는 `--round N`으로 seal 키·artifact 이름 결정.
- `tune_search_ranking.py`: 로그 `search-tuning-round{N}.jsonl`, 라인에 `round`; `--alias-change` 검증기(§7.2).
- `alias_candidates_tool.py` 서브커맨드: `--concept-tokens`, `--verb-report`, `--method-safety`, `--candidates`, `--classify`(R5/R6를 bench에 기록, 결정적).
- `concept_lexicon_check.py`: §7.0 검사·정규화; 결과 파일과 폐기 목록 출력.
- `policy.py`(커밋 H, 유일한 production 변경) — notes `origin` 스키마를 **하위 호환**으로 분기:

  | origin | 필수 | 비고 |
  |---|---|---|
  | `phase2.5` | 기존 규칙(`seed_query_id: null`) | 불변 |
  | `round1` | `seed_query_id` + `failure_classes ∋ R4` + `evidence` | 기존 규칙 그대로, `candidate_word` 불필요 |
  | `round{N}`, N ≥ 2 | `seed_query_id`(`^s-\d{3}$`) + `candidate_word` + `failure_classes ∋ R6` + `evidence` | 신규 |
  | `lexicon-r{N}` | `seed_query_id: null`, `failure_classes: []`, `evidence` | 신규 |

  구현: origin을 정규식 `^(phase2\.5|round(\d+)|lexicon-r(\d+))$`로 받고 라운드 번호를 정수로 분기. 그 외 로더 로직 불변. **회귀 테스트**: H 직후 현재 `search_aliases.json`(phase2.5 + round1 항목)이 변경 없이 로드되고 `ranking_sha256`·alias sha가 95b8de0과 동일.
- `evaluation_code_sha256`: 6개 파일(§5.7).
- `round_freeze.json`: `[{"round": 1, "commit_T": "26005e4", "structure_sha256": …}, {"round": 2, "structure_sha256", "verb_inventory_sha256", "concept_lexicon_sha256", "lexicon_aliases_sha256", "alias_candidates_sha256", "worker_brief_sha256", "hidden_generation_prompt_sha256", "hidden_reviewer_prompt_sha256", "tooling_code_sha256", "evaluation_code_sha256_at_T", "source_registry_fingerprint", "source_spec_sha256": {…}}]` (round 1 항목의 `commit_T`는 역사 기록으로 유지).

## 9. 진단 출력 추가
`round2-final.json`: Round 1 필드 전부 + `round`, `held_out_top3`, `alias_sha256`, `alias_candidates_sha256`, `concept_lexicon_sha256`.

## 10. 테스트 전략

### 10.1 단위
- 동사 인벤토리 == 스펙 §6 블록(스펙 파일 파싱); 샘플 의도: `set up a jira planning board` → {PUT, POST}; `leave feedback on this jira ticket` → {POST, DELETE}; `discard this uploaded ticket file` → {DELETE}; `browse pages` → {GET}; `check access` → {GET, POST}; `revise`+`rewrite` → {PUT, POST}.
- 메서드 안전성 검사: seed 39건 전부 (a) 또는 (b) 충족(테스트로 고정; 인벤토리 변경 시 깨짐).
- pre-T 순서 검사: `concept_lexicon.json.generated_from.inputs.verb_inventory` == `round_freeze.verb_inventory_sha256`(인벤토리 확정 후 생성됐음을 기계적으로 보장).
- 개념 사전 검사기: 규칙 (0),(a)–(e) 각각 실패 케이스(굴절형 `files` 거부, 개념당 6개 → 사전순 5개, 타깃 3개 거부); 결정성(두 번 실행 동일); `rejected` 기록.
- `lexicon_aliases_sha256` 계산 함수: round2 alias 추가 전후 동일, 사전 항목 하나 변경 시 상이.
- 후보 도구: 결정성; **정답 op 어휘 기준** 제외(전역 출현 토큰 `workspace`가 후보로 남는 케이스를 고정); 기능어·식별자 제외; 타깃에 summary 포함, 동사 제거; R5/R6 분류 샘플.
- 검증기 `validate_alias_change`: 타깃 2개 거부, 후보 밖 단어 거부, 문맥 토큰 2개 거부, 예산 초과 거부, seed당 2개 거부, `candidate_word` 불일치 거부, 제안기 출력과 불일치 거부.
- 제안기 `--propose-aliases`: 결정성(두 번 동일), 순회 순서(id·사전순) 고정 케이스, working 상태 누적, 현재 seed의 타깃만 시도, 다른 seed를 깨는 alias 비채택, 예산 15 중단, 미해결 기록.
- 단방향 파이프라인: clean B 상태에서 두 번 실행 → `result_sha256` 동일·`run_log_sha256` 상이(두 run_id, 둘째는 adopted=false); 첫 출력이 적용된 worktree에서 실행 → "dirty round2 state" 거부(또는 `--from-baseline`으로 같은 출력); constants/round2 alias를 임의 변경한 상태 → baseline mismatch 실패; 재실행이 이전 출력을 입력으로 쓰지 않음; alias 제안 후 상수 재선택 경로 없음.
- 사전–seed 호환 게이트: 교집합 비면 폐기·후보로 복귀, 교집합 있으면 유지.
- `policy.py` notes-origin: `lexicon-r2`/`round2` 허용, `round9x` 형식 오류 거부, round2에 `candidate_word` 없으면 거부, round1 항목은 `candidate_word` 없이 통과, 현재 `search_aliases.json` 로드 회귀(§8).
- 라운드 일반화: `round_seal.py --round 2`가 `round1_seal`을 건드리지 않음; diag round 2 artifact 이름; Round 1 artifact 테스트 유지.

### 10.2 벤치마크 무결성 (`test_evaluator.py`)
- `TestSealIntegrity` 라운드 키 일반화.
- `alias_notes`: round2 항목 §7.2 전부; lexicon-r2 항목 형식.
- provenance: 동사 테이블 검사 제외; alias 단어는 (seed 토큰 ∪ 카탈로그 토큰 ∪ 개념 사전 키) 안; round2 alias는 후보×타깃 안; 예외 `{epic}`.
- `round_freeze.json` round 2: 10개 해시 == 현재 파일(`lexicon_aliases_sha256`는 부분집합 계산; 브리프·프롬프트 2개는 파일 해시; `tooling_code_sha256`는 §5.1 도구 파일 목록, `evaluation_code_sha256`는 그 부분집합); `source_registry_fingerprint` == 모든 pre-T artifact의 `generated_from.registry_fingerprint`.
- Round 1 불변: `round1-final.json`·`search-tuning-round1.jsonl` 파일 해시, `round1_seal` 객체 해시, readiness Round 1 섹션 텍스트 해시 == pre-work 상수.
- 최종 artifact(round 2) 내부 일관성.

### 10.3 seed 회귀
픽스처 r0 23/23·6/6 유지(공통). 스냅샷 seed 39/39, regression 14/14 — 튜닝 로그 adopted 라인(AC-06b, **성공 분기만**; 테스트는 종료 상태를 읽어 실패 분기면 `not_applicable`로 건너뛴다 — AC-16과 충돌하지 않도록).

## 11. 상태 모델과 readiness
Round 1 §11과 동일 + Round 2 섹션(성공 분기: 커밋 H/T/B/C/D; 실패 분기: H/T/B/F; abort 분기: H/T/B/X이며 C·D·복호화 시각·결과 행·`round2-final` 필드는 `null`/`not_applicable`로 명시): `housekeeping_commit`, 커밋 sha, 스냅샷 fingerprint, 생성 실행 형태(Unpersonalized 임시 채팅 attestation), 사전 생성 프롬프트/결과 sha, 폐기 항목 수, 동사 분포 보고서와 확장 결정, 메서드 안전성 검사 결과, hidden 생성 프롬프트/결과 sha, 재요청 횟수, 평문 암호화 시각·`.enc` sha256·복호화 시각, worker 브리프 sha·실행 횟수·출력 sha, 결과 행, 상태. attestation에 §5.6 항목 추가.

## 12. Acceptance Criteria

라운드는 세 종료 상태 중 하나로 끝난다: **성공**(H → T → B → C → D), **튜닝 실패**(H → T → B → F), 또는 **abort**(H → T → B → X: 튜닝은 통과했으나 정식 전체 테스트 실패로 run이 `rejected`된 경우). 각 AC 행은 분기표 없이 단독으로 판정 가능하도록 적용 분기를 행 안에 명시한다. "종료 커밋"은 성공 분기에서 D, 튜닝 실패 분기에서 F, abort 분기에서 X를 뜻한다.

| ID | 분기 | 기준 | 검증 |
|---|---|---|---|
| AC-01a | 공통 | 95b8de0 < `housekeeping_commit` < T < B; `verb_methods`·`alias_candidates.json`·사전 병합·`failure_classes`·브리프·프롬프트 변경은 T에만; `policy.py`와 §5.1 도구 변경은 H/H′에만 | git |
| AC-01b | 성공 | B < C < D; `search_aliases.json`(round2 항목)·`constants` 변경은 B..C에만 | git |
| AC-01c | 실패 | B < F; F가 종료 커밋이며 C·D 없음; B..F에서 `search_ranking.json`·`search_aliases.json` 변경 없음(B 상태 유지) | git |
| AC-01d | abort | B < X; X가 종료 커밋이며 C·D·F 없음; B..X에서 `search_ranking.json`·`search_aliases.json` 변경 없음(B 상태 유지; worker의 `--reject`가 복원) | git |
| AC-02 | 성공 | C..D 변경 파일 ⊆ {`search_queries.json`, `round2-final.json`, `phase3-readiness.md`} | git |
| AC-03 | 성공 | D 평문 sha256 == `round2_seal`; D에 테스트 코드 변경 없음 | 테스트 + git |
| AC-04 | 공통 | gate 집합 origin ∈ {`held_out-r2`, `negative-r2`}, r0/r1 레코드 0개 — **B 봉인 과정의 체크포인트**로 검사해 결과를 `round2_seal`/readiness에 기록한다(F에서 평문을 다시 읽어 검사하는 것은 금지; 성공 분기는 D unseal 후 테스트로 재확인) | 봉인 스크립트 + 테스트(성공 분기) |
| AC-05 | 공통 | `search.py` diff vs 95b8de0 비어 있음; `policy.py` diff는 notes-origin 규칙뿐; §5.1 도구·무결성 테스트 파일은 `housekeeping_commit` 이후 **종료 커밋까지** diff 비어 있음; `tooling_code_sha256` == 현재 파일 | git + 테스트 |
| AC-06a | 공통 | 픽스처 r0 23/23·6/6 | 테스트 |
| AC-06b | 성공 | adopted run의 스냅샷 seed 39/39, regression 14/14 | 로그 + 테스트 |
| AC-07 | 성공·실패 | §10.1 테스트 통과 | 테스트 |
| AC-08 | 공통 | `POLICY_VERSIONS["search"] == 3`; `round_freeze` round 2 해시 10개 == 현재 파일; S 출처 필드 == 모든 영속 artifact의 provenance | 테스트 |
| AC-09 | 공통 | §4 불변 목록 diff 비어 있음; Round 1 artifact·로그·seal·readiness 섹션 해시 불변 | 테스트 + git |
| AC-10 | 성공 | `round2-final.json` provenance 필드 + `round`, `held_out_top3` | 테스트 |
| AC-11 | 성공 | 최종 artifact 정확히 하나, `git_commit`==C(컨트롤러 D 검사), D 이후 가변 파일 변경 없음 | git |
| AC-12 | 공통 | round2 alias/rule 전부 §7.2(1 타깃, 후보 포함, 예산, seed당 1개, `candidate_word`); 실패 분기에서는 0개 | 테스트 |
| AC-13 | 공통 | `alias_candidates.json`·`concept_lexicon` 병합분·인벤토리가 T 이후 불변; 결정적 단계의 재실행 결과 동일(동결된 raw 생성 + 동결된 의미 검토 출력을 입력으로 한 정규화·게이트·후보 도구; LLM 호출 재실행 동일성은 요구하지 않음); 모든 영속 artifact의 `generated_from.registry_fingerprint` == `round_freeze.source_registry_fingerprint` | 테스트 + 도구 |
| AC-14 | 성공·실패 | 라운드 일반화 후 Round 1 테스트 통과 | 테스트 |
| AC-15a | 성공 | 튜닝 로그 round 2: `adopted: true` run 정확히 하나, 그 상수 == 파일, baseline == freeze | 테스트 |
| AC-15b | 실패 | 튜닝 로그 round 2: `adopted: true` run 0개, `tuning_failed: true` run ≥ 1, 파일 상수 == B 상태 | 테스트 |
| AC-16 | 성공·실패 | 전체 오프라인 테스트 통과, 새 의존성 없음 | unittest |
| AC-23 | 공통 | T 커밋과 B 커밋 시점에 전체 오프라인 테스트 통과(컨트롤러가 실행하고 ledger에 기록); 새 의존성 없음 | unittest + ledger |
| AC-17 | 공통 | H 직후 기존 `search_aliases.json`이 변경 없이 로드(round1 notes 하위 호환) | 테스트 |
| AC-18a-B | 공통 | B 직후 체크포인트: `.enc` 존재 ∧ 평문 부재 ∧ `.enc` sha256 기록 | 컨트롤러 스크립트 출력(readiness) |
| AC-18a-D | 성공 | D 직전 체크포인트: `.enc` sha256 == B 직후 값 ∧ 평문 부재; D 복호화 평문 sha256 == `round2_seal` | 컨트롤러 스크립트 출력(readiness) |
| AC-18a-F | 실패 | F 시점 체크포인트: `.enc` sha256 == B 직후 값 ∧ 평문 부재(복호화 없음) | 컨트롤러 스크립트 출력(readiness) |
| AC-18a-X | abort | X 시점 체크포인트: `.enc` 존재 ∧ 평문 부재 ∧ `.enc` sha256 == B 직후 값(복호화 없음) | 컨트롤러 스크립트 출력(readiness) |
| AC-18b | 공통 | attestation: B 이후 종료 커밋까지 평문 미복호화(성공 분기는 D에서만); 생성·검토는 Unpersonalized 임시 채팅(또는 stateless API) | readiness attestation |
| AC-19a | 공통 | `round2-worker-brief.md`·hidden 생성/검토 프롬프트가 T에 커밋되고 sha == `round_freeze`; AC-valid worker 출력이 존재하면 첫 번째만 채택; 의미 검토는 배치당 첫 valid 출력, valid 이후 재실행 없음(attempt 로그) | 테스트 + readiness |
| AC-19b | 성공 | 적용된 round2 alias 추가분 == 결정적 제안기 재실행 결과(`--verify`), 파일 상수 == adopted run | 테스트 + 도구 |
| AC-19c | 실패 | 적용 추가분 0; 튜닝 로그의 `failed` run이 제안기 최종 결과 39/39·14/14 미달을 기록 | 테스트 |
| AC-19d | abort | 적용 추가분 0(정책 == B); rejected run의 후보 `result_sha256` == 제안기 재실행 결과(`--verify`, abort 모드); 그 run에 `reject_evidence`(실패 테스트 id 목록·출력 sha256) 존재 | 테스트 + 도구 |
| AC-20a | 공통 | 튜닝 로그 round 2를 `run_id`로 묶었을 때: 각 run에 `constants_selected` 정확히 1개(입력 alias sha == B 시점 sha) → `aliases_proposed` 정확히 1개 순서, 이후 상수 변경 0; 모든 run의 `baseline_sha256` 동일; AC-valid run끼리 `result_sha256` 동일(`run_log_sha256`는 기록만) | 테스트 |
| AC-20b | 성공 | `adopted: true` run == 첫 AC-valid run(정확히 1개) | 테스트 |
| AC-22 | abort | X 변경 파일 ⊆ {`phase3-readiness.md`}(튜닝 로그의 `rejected` 라인은 worker 커밋에 이미 있음); 정책 파일 == B 상태; `round2-final.json` 없음; hidden 평가 0회; AC-18a-X 충족; readiness 상태 "Round 2 aborted"에 `reject_reason`·**실패한 테스트 이름과 출력**(증거 — 이 분기에서는 AC-07/14/16이 적용되지 않는다); 봉인 hidden set은 재사용하지 않음 | git + readiness |
| AC-21 | 실패 | F 변경 파일 ⊆ {`search-tuning-round2.jsonl`, `phase3-readiness.md`}; `round2-final.json` 없음; hidden 평가 artifact 없음; readiness 상태 "Round 2 tuning failed"에 실패 `result_sha256`·`.enc` sha256 기록; 봉인 hidden set은 재사용하지 않음(§5.5) | git + 테스트 + readiness |

Attestation(컨트롤러): 사전·hidden 생성 프롬프트/결과 sha와 실행 형태(임시 채팅), 재요청 횟수, hidden 평가 횟수(성공 분기 정확히 1회 / 튜닝 실패·abort 분기 0회), **B 이후 종료 커밋까지 봉인 평문이 튜닝 환경에서 읽을 수 없는 상태였음**, 튜닝 로그 완전성, **인벤토리·사전·후보 목록이 hidden 생성 전에 커밋됨(T < B)**, **hidden을 본 주체가 B..C 선택에 관여하지 않음(T 동결 브리프만 전달, alias는 결정적 제안기, 첫 AC-valid 출력 채택; 실행 횟수·출력 sha 첨부)**.

## 13. 위험과 완화

- **개념 사전 품질**: clean context가 엉뚱한 동의어를 만들 수 있다(예 `note→comment`는 좋지만 `card→issue`는 논란). 완화: 타깃 정확히 1, stateless 의미 검토, 카탈로그 어휘와 겹치는 단어 금지, alias 감쇠 0.5로 영향 제한. hidden 오염은 없음(생성에 hidden·seed 미제공); T의 seed 호환 게이트는 의도적으로 seed-informed한 학습 절차의 일부다.
- **인벤토리 과소/과다**: §6 다의어 원칙과 카탈로그 분포 보고서로 완화.
- **굴절형**: Round 3 후보.
- **후보 목록 seed 과적합**: 후보는 seed 유래지만 사전이 일반 커버리지를 맡는다. hidden의 새 동의어는 사전이 못 덮으면 실패 — 그것이 측정 대상.
- **negative 엄격화**: 규칙 추가로 0/8이 더 어려워짐. 게이트 유지.
- **역할 분리의 실무적 한계**: 컨트롤러(이 세션)는 봉인·검토·커밋을 수행하고 B 전에 평문을 본다. 완화: B..C 동안 평문은 사용자 passphrase 뒤에 있어 어떤 에이전트도 다시 읽을 수 없고, 모든 선택은 결정적 스크립트(상수)와 worker의 seed 분석(alias)으로만 이루어지며, 컨트롤러 브리프는 절차만 담는다(sha로 고정). 한계: 컨트롤러가 B 전에 본 기억은 지울 수 없다 — 그래서 B..C에서 컨트롤러가 전달할 수 있는 것은 T에서 동결된 브리프뿐이고, 선택(상수·alias·출력)은 모두 사전 선언된 결정적 규칙이 한다. 사용자 부담: B와 D에서 각각 한 번 터미널 명령.
- **일반 사전의 사각지대**: "카탈로그 어휘에 없는 단어만" 규칙은 `workspace→space`형(카탈로그에 다른 뜻으로 존재) 다의어를 일반 사전으로 못 잡는다. Round 2는 seed 후보(타깃 기준 제외)로만 이를 다루고, `rejected` 기록을 Round 3 근거로 남긴다.

## 14. 한 줄 정의

> 동사와 개념 동의어는 인벤토리로, seed가 드러낸 단절은 사전 등록된 후보로, 셋 다 봉인 전에 잠그고, 본 사람은 고르지 않으며, 같은 절차로 한 번만 잰다.
