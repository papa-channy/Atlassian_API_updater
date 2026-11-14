# Search Quality Round 3 — 컨트롤러 세션 핸드오프 (2026-10-05)

> 이 문서는 **새 세션**이 계획 Task 9–17(컨트롤러 절차)을 바로 시작할 수 있게 쓴 것이다. 도구 구현(Task 1–8)과 리뷰는 끝났고 `main`에 병합돼 있다. 이전 세션(5edca2ca…)은 Round 2 hidden 평문을 본 적이 있어 AC-R3-08에 따라 Round 3의 생성자·검토자·워커·D 컨트롤러·일반 컨트롤러 역할을 맡을 수 없다 — 그래서 새 세션이 필요하다.

## 1. 현재 상태 (한 줄씩)

- `main` = **10473ad** (= 마지막 리뷰 통과 H′ 커밋). 푸시되지 않음(푸시는 사용자 지시 시에만).
- 스펙 **v1.23** `docs/superpowers/specs/2026-10-05-search-quality-round3-design.md` (binding). 계획 **v14** `docs/superpowers/plans/2026-10-05-search-quality-round3-implementation.md` (스펙의 논증; Task 9–17이 실행 절차).
- 전체 테스트 `python -m unittest discover -s tests -t .` → **530 OK**. `python tests/benchmarks/round3_simulation.py --phase H` → **ALL STEPS PASS**.
- 격자 실측(이 머신): 0.0547 s/점 × 23,328점 ≈ **21분** (`.superpowers/sdd/2026-10-05-search-quality-round3-implementation/grid_probe_r3.py`).
- SDD 원장(재구성본): `.superpowers/sdd/2026-10-05-search-quality-round3-implementation/progress.md` — 모든 판정·보류 minor·최종 리뷰 결과. 원본 브리프/리포트/리뷰 diff는 워크트리 삭제 때 유실됨(브리프는 `scripts/task-brief`로, 리뷰 diff는 git으로 재생성 가능).
- 메모리: `~/.claude/projects/-Users-chan-Developer-internal-Atlassian-API-updater/memory/search-quality-round3-design-status.md`.
- `~/.atlassian_api_updater/round3-cache`, `round3-work`는 **아직 없다** (Task 9 Step 1이 만든다). Round 2 보관본: `~/.atlassian_api_updater/archive/round2/{round2-cache,round2-work,sealed}`.

## 2. 먼저 읽을 것 (순서대로)

1. 이 문서.
2. 계획 **Global Constraints**(1–45행 부근)와 **Task 9–17** 전체. 스펙 **§5**(수명주기·AC-18b·actor 분리), **§8**(H′ 상태 모델), **§10**(AC 표).
3. 원장 `progress.md`의 Rulings 줄.

## 3. 절대 규칙 (세션 전체)

- 실제 Jira/Confluence API 호출 금지(카탈로그 새로고침 `python -m tools.atlassian_docs`는 공개 OpenAPI 문서 fetch — 계획 Task 9 Step 1이 허용하는 유일한 네트워크 단계). 자격증명 헤더 값은 어떤 출력에도 남기지 않는다.
- 봉인 평문 경로 `~/.atlassian_api_updater/sealed/round3-sealed.json`은 **어떤 서브에이전트에게도** 주지 않는다. hidden 질의 원문은 ledger·리포트·로그·대화에 쓰지 않는다(`query_sha256`만).
- 커밋 메시지 끝: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. 푸시·병합은 사용자 지시 시에만. bare `git stash` 금지.
- `TOOLING_FILES`(`tests/benchmarks/evaluator.py`의 목록)·`search.py`·`policy.py`는 `housekeeping_commit`(10473ad)부터 종료 커밋까지 불변(AC-05). 도구 결함이 나오면 스펙 §8 H′ 상태 모델을 따른다(post-S H′: fix → suite → `--phase H` → 새 리뷰어 범위 리뷰 findings 0 → `$W/housekeeping_commit` 이동 + `housekeeping_commit_moved` ledger(reviewer_actor_id, reviewed_base/head sha, review_output_sha256) → 같은 S로 artifact 재생성 → suite 재실행).
- 사용자 브리핑은 **한글**. 외부 검수는 끝났으니 ChatGPT 스레드는 hidden set 생성/검토 용도로만 쓴다(아래 §6).
- localhost HTTP 브리지는 권한 분류기가 거부했던 방식 — 재시도하지 않는다.

## 4. 시작 명령 (Task 9 Step 1 그대로)

```bash
cd /Users/chan/Developer/internal/Atlassian_API_updater && git status --porcelain --untracked-files=no   # 비어 있어야 함
git rev-parse HEAD        # 10473ad 여야 함 (다르면 멈추고 원인 확인; docs 커밋만 추가됐다면 10473ad를 수동으로 고정)
test ! -e ~/.atlassian_api_updater/round3-cache || { echo "S exists"; exit 1; }
mkdir -p ~/.atlassian_api_updater/round3-work
git rev-parse HEAD > ~/.atlassian_api_updater/round3-work/housekeeping_commit
echo '{"event": "initial_housekeeping_commit", "sha": "'"$(git rev-parse HEAD)"'", "actor_id": "<this chat/session id>", "session_id": "<uuid or not_available>"}' >> ~/.atlassian_api_updater/round3-work/controller-events.jsonl
python -m tools.atlassian_docs       # 라이브 캐시 1회 새로고침(네트워크)
python tests/benchmarks/round_seal.py catalog --round 3 --cache-dir "$(python -c 'from tools.atlassian_docs import storage; print(storage.CACHE_DIR)')" --out /tmp/live-gen.json --internal-out /tmp/live-internal.json
```

출력된 `registry_fingerprint`가 `f3c2e9d48aa85c96ca62cdd84ff700cc2714c888cf4148b3a91c604c45b47b62`이고 spec sha 3개가 Round 2 freeze 값과 같으면 보관된 S2를 `round3-cache`로 복사(계획 Task 9 Step 1 둘째 블록), 아니면 라이브 캐시를 S로 쓴다(계획 본문의 분기 그대로). 이후 `export ATLASSIAN_DOCS_ROUND3_CACHE=~/.atlassian_api_updater/round3-cache`.

그 다음은 계획 Task 9 Step 2(verb report·method-safety suffix 고정점) → Task 10(사전 re-gate, ChatGPT 없음) → Task 11(후보·R5/R6·AC-13 replay·**binding pre-T**·동결 텍스트·**Step 7 벤치 Round 2 stub 초기화 → freeze → commit T**) 순서다.

## 5. 실행 순서 요약과 게이트

```
S → 인벤토리(suffix만) → 사전(아카이브 re-gate) → 후보/R5/R6 → AC-13 replay
→ pre-T 체크포인트 (binding, AC-R3-01: seed ≥36/39, fixture 실패 [], regression raw ≥10/14 ∧ effective 14/14, equivalence_mismatches [])
→ T (벤치 hidden 섹션 [] 초기화 포함, freeze --reference-enc)
→ hidden 생성/검토 (ChatGPT, 12 기계 규칙, negative 4/4 actionable/abstained, 검토자 동사 용법 검사)
→ 검토 평문 삭제 → needle manifest + sha → seal --needle-manifest → 암호화 직전 스캔
→ [사용자] 암호화 + 평문 삭제 → 부재·암호문 검사 → B → B 직후 스캔
→ 워커 2단계 handshake(Phase 0 handshake-only, transport agent id 바인딩 → Phase 1 'run the brief procedure — …') → 튜닝(≈21분 격자) → --verify
→ C (tuning_accept ∧ canonical suite) → D (새 actor, 게이트 1회: held_out ≥15/16 ∧ negative 0 실패; 체크포인트 이벤트 후 Round 2 참조 세트 복호화·관찰·삭제 rm && test ! -e)
   | F (튜닝 실패) | X (abort)
→ 종료 직전/직후 스캔(allow: 카탈로그 스냅샷 디렉터리 + 분기별 목록) → readiness 렌더 → 종료 커밋 → Task 17 provenance 리뷰 → finishing-a-development-branch
```

## 6. ChatGPT 사용법 (hidden 생성/검토 전용)

- 생성·검토는 **Temporary chat, 개인화 끄기**(`temporary_chat_unpersonalized: true` ledger). 생성자 ≠ 검토자 ≠ 워커 ≠ D 컨트롤러(각 actor id ledger; 스펙 §5 세 체크포인트 `actor_separation_check_B/_worker/_D`).
- 파일 첨부: 세션 scratchpad에 복사한 뒤 숨겨진 `input[type=file]`(accept가 비어 있는 것) 을 JS로 보이게 하고 aria-label을 붙인 다음 `find` → `file_upload`. 보내기 버튼은 `find`로 ref를 얻어 클릭(첨부 업로드가 끝났는지 `form.innerText`로 확인). 응답 추출은 `document.body.innerText.lastIndexOf('ChatGPT 답변:')`.
- 생성 프롬프트는 `render_generation_input`으로 VERB_METHODS 블록을 렌더한 **그 텍스트**를 보내고 `rendered_generation_prompt_sha256`을 ledger. 검토자에게는 `annotate_for_review` 결과 + 카탈로그 JSONL 첨부. 응답은 `machine_check(round=3)` → `next_request` 상태기계대로만 재요청한다(계획 Task 12).
- 검토 입력 파일(`$W/plain/`)은 B 전에 삭제하고 해시만 남긴다(AC-18b).

## 7. 사용자 개입 지점 (미리 알려 둘 것)

1. T 전: 없음(모두 컨트롤러).
2. B 직전: 사용자가 `round3-sealed.json`을 암호화하고 평문을 삭제("암호화했어" 확인 후 부재·`.enc` sha 검사).
3. D: 게이트 체크포인트 이벤트 기록 **후** 사용자가 Round 2 참조 세트(`archive/round2/sealed/round2-sealed.json.enc`)를 `$W/reference-round2-plain.json`으로 복호화; diag `--reference` 1회 → 즉시 `rm && test ! -e`.
4. 종료 후: finishing-a-development-branch 메뉴(병합/푸시는 사용자 선택).

## 8. 알려진 함정

- `round_seal.py seal --round 3`는 벤치 `held_out`/`negative`가 비어 있지 않으면 **거부**한다 → Task 11 Step 7의 초기화(Round 2 봉인 stub → `[]`, `bench_hidden_sections_reset` ledger)를 빼먹지 말 것.
- seal에는 `--needle-manifest`가 필수이며 manifest 내용이 봉인 24 질의의 `needle_manifest()`와 정확히 같아야 한다(불일치/누락 exit 1). 스캔은 `--expect-sha256` 불일치 시 exit 2.
- 모든 스캔에 `--allow ~/.atlassian_api_updater/round3-cache --allow ~/.atlassian_api_updater/archive/round2/round2-cache`(카탈로그 스냅샷; 계획 v14 명령에 이미 포함). D 종료 후 스캔 allow는 `search_queries.json` + 봉인 평문 + 위 디렉터리뿐.
- T freeze 출력의 `hidden_generation_rules`는 `list(rs.HIDDEN_RULES_R3)`(12개, `ascii` 포함)와 정확히 같아야 한다.
- `--phase H`는 전체 suite를 6회 돌린다(약 1분). pre-T preflight(`--phase pre-T`)는 실제 S에서 20점 + baseline을 memoized/production 비교한다.
- `test_round3_policy_diff_is_limited_to_declared_kinds`는 `e16c073`이 없는 합성 트리에서만 skip된다 — 실제 저장소에서 skip되면 비정상.
- 워커 Phase 1 메시지는 `run the brief procedure — …` 접두 고정, 허용 응답은 브리프의 사전 정의 문구뿐. `tuning_accept := seed 39/39 ∧ regression_effective 14/14 ∧ fixture_positive 23/23 ∧ fixture_negative_raw 6/6`.
- 모든 이벤트는 `$W/controller-events.jsonl`/`attempts.jsonl`(저장소 밖)에 쓰고, readiness는 종료 커밋에서만 렌더(Task 16; outputs 본문 없이 sha/status만).

## 9. 이전 세션 판정 요약 (원장 참조)

Task 1 필드 위치·guard 내구화, Task 2 합계 식, Task 6 테스트 문구·ASCII 정규식, Task 7 Round 2 테스트 3건 조정, Task 8 합성 `apply_T` 4건, 최종 리뷰 C1(계획 v14)·I1~I3·잔여 1건(skip 조건). 보류 minor는 최종 리뷰어가 모두 "leave"로 분류. `tests/benchmarks/round2_simulation.py`는 역사 파일로 미수정.

## 10. 끝났을 때

종료 커밋(D/F/X) 후 Task 17: 메모리 파일 갱신(결과·sha), `round3-cache`/`round3-work`/`sealed/round3-sealed.json.enc`를 `~/.atlassian_api_updater/archive/round3/`로 보관, finishing-a-development-branch. D면 Phase 3 Discovery 게이트 통과 → Phase 3 설계로; F/X면 Round 4 brainstorming.
