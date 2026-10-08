# Search Quality Round 4 — Technical Specification

**문서 버전:** v1.0 (2026-10-09, brainstorming; 사용자 결정 2026-10-09: "seed 레코드 감사(2번)를 짧게 한 뒤 같은 게이트·시스템 보강(1번)", 어휘 소스는 "공식 문서 제목 코퍼스(A) + 프롬프트 지시 병행", B(문서 근거 동일 제품 예외)는 조건부 예비안)
**기준일:** 2026-10-09
**선행:** Round 3 (spec v1.25.1 `0741e34`, plan v16; 종료 2026-10-07 "pre-T 미달": binding pre-T seed 31→33→35/39, T·B·hidden set 없음; `docs/phase3-readiness.md` Round 3 decision record). `main` = `237d2c9`.
**상속:** 이 문서에 적지 않은 것은 **Round 3 스펙 v1.25.1을 그대로 상속**한다(§3 스코어러 규칙·상수·격자·legacy 모드, §4 평가·게이트, §5 수명주기·역할·AC-18b·needle manifest·H′ 상태 모델, §6 어휘 메커니즘(자원 자격, 교차 제품 `in_catalog` 예외, 구문 규칙, `seed-regression` 게이트, 제안기 원자 액션), §7–§9, §10 AC 전부). 이름 치환: `round3`→`round4`, `-r3`→`-r4`, `lexicon-r3`→`lexicon-r4`, `round3_seal`→`round4_seal`, `round3-sealed.json.enc`→`round4-sealed.json.enc`, `search-tuning-round3.jsonl`→`search-tuning-round4.jsonl`, `round3-*.md`→`round4-*.md`, `POLICY_VERSIONS["search"]` 4 유지(응답 스키마 불변). 이 문서는 **델타**만 규정하며, 충돌 시 이 문서가 우선한다.
**목적:** Round 3가 남긴 어휘 소스 문제를 seed와 무관한 외부 근거(공식 제품 문서 제목)로 풀어 pre-T 체크포인트를 넘기고, 새 봉인 hidden set에서 Discovery 게이트(held_out ≥ 15/16, negative 0 실패)를 재시도한다.
**설계 원칙(상속 + 추가):** Fix the mechanism, not the words / Every new number is a grid constant whose baseline is 0 / Abstain in the product, not in the evaluator / Same seal, same gate / Nothing the design session saw is a gate / **Vocabulary comes from sources the seeds did not write** — 생성 입력에는 카탈로그·공식 문서 제목·동사 키만 들어가고 특정 동의어 예시는 들어가지 않는다.

---

## 0. 배경 — Round 3가 남긴 것

Round 3의 설계 확장(정렬 규칙 3개, 구문 규칙 사전, 교차 제품 예외, seed-regression 게이트)은 pre-T 정책을 31/39에서 35/39까지 올렸고 fixture·regression은 무손상이었다. 실패 4건을 2026-10-09 seed 감사(39건 전수, 카탈로그 경쟁 op 대조)로 분류했다:

| seed | 레코드 판정 | 원인 | Round 4 처리 |
|---|---|---|---|
| s-004 `transition issue status` | 정상(단일 이슈 전이; GET/POST 모두 타당) | 경쟁 `POST /bulk/issues/transition`의 summary "Bulk transition issue statuses"가 'status'와 일치(+5), `bulk` 미일치 −1 | 상수 영역(`path_unmatched_penalty` 격자) → 튜닝(B..C)에 위임 |
| s-027 `show my starred searches` | 정상(starred = favourite, Jira UI 용어) | 'searches'→'search'가 `/…/search` 터미널 자원과 literal 일치; 정답에 닿으려면 **같은 제품의 자원 토큰 `search`→`filter` 동의어**가 필요한데 §6은 이를 허용하지 않음. `/filter/my`의 기능어 터미널은 부차적(제거해도 결과 불변) | **§6 하 알려진 미도달** — 레코드 유지, 통과 기대에서 제외(§11 B 예비안) |
| s-028 `publish a new project release` | 정상(release = version, Jira UI "Releases") | `release→version` 동의어가 두 번의 stateless 생성에서 나오지 않음(생성기는 release→deployment) | 어휘 소스(§6.1) |
| s-039 `browse pages inside this workspace` | 정상 | `workspace→space` 미생성(v1.25 교차 제품 예외로 자격은 있음; 생성기는 "team area"→space) | 어휘 소스(§6.1) |

프로브(HEAD 코드, 아카이브 Round 3 S): Round 3 사전(feedback→comment, iteration→sprint, time entry→worklog)으로 35/39; `release→version`·`workspace→space`를 더하면 **37/39**, fixture 23/23·6/6, regression 10/14·14/14. 기능어 터미널 제외와 `starred→favourite`는 s-027을 살리지 못했다(카탈로그에서 터미널이 기능어뿐인 op는 `/filter/my` 1개).

**독립성 선언:** 이 스펙을 쓴 세션(42e25099…)은 Round 3 컨트롤러였고 Round 2·3 hidden 평문을 본 적이 없다(Round 3 hidden set은 생성되지 않았다). 그래도 §5의 역할 규칙은 그대로다: Round 4 hidden 생성자·검토자·워커·D 컨트롤러는 각각 별도 stateless/fresh actor다.

## 1. 목표

- Discovery 게이트: 새 봉인 세트에서 held_out ≥ 15/16, negative 0 실패(Round 3 §4 대칭 판정식).
- 튜닝 전 최종 조건(AC-R3-01 상속): binding pre-T에서 seed ≥ 36/39, fixture positive 23/23 · negative raw 6/6, regression raw ≥ 10/14 · effective 14/14, 격자 평가기 동등성 불일치 0. 기대값 37/39(s-004, s-027 제외).
- 결론의 범위는 Round 3과 같이 "actionable recommendation query의 Discovery 성능"이다.

## 2. 범위

**변경:** `tests/benchmarks/doc_titles.py`(신규: 사이트맵 스냅샷·정규화·렌더 보조; `TOOLING_FILES`에 추가), `tests/benchmarks/concept_lexicon_check.py`(생성 입력 렌더러에 DOCUMENTATION TITLES 블록·둘째 첨부 파일), `tests/benchmarks/round4-lexicon-generation-prompt.md`(신규 동결 텍스트), `tests/benchmarks/round4-lexicon-review-prompt.md`(Round 3 판과 동일 내용, 파일명만), `tests/benchmarks/evaluator.py`(freeze 키 `doc_titles_sha256`, round 4 키 집합), `tests/benchmarks/round_seal.py`(round 4 freeze/seal/catalog 라운드 번호), `tests/benchmarks/round4_simulation.py`(Round 3 시뮬레이션의 round 4 판 + 합성 문서 제목 스냅샷), `tests/tune_search_ranking.py`(`ROUND = 4`, 로그 파일명), diag(`--round 4`), 스펙·계획·readiness.
**불변(byte-invariant):** Round 1·2·3 로그·freeze 항목·readiness 섹션·`round1-final.json`·`round2-*`·`round3-*`(Round 3 동결 텍스트 3종은 역사 파일), fixture 23/6, Phase 1 파일, `search.py`·`policy.py`·`search_ranking.json` **구조**(Round 3 H9에 고정된 `ordering_rules`·상수·격자 그대로; Round 4의 H는 스코어러를 건드리지 않는다), Round 3 회귀 참조 파일(AC-R3-02는 legacy 모드로 그대로 적용).
**제약된 변경:** `verb_methods`는 Round 3과 같은 prefix 불변(suffix는 T에만); `search_aliases.json`은 T에서 `lexicon-r4`(아카이브 Round 2 재게이트분 + Round 4 생성분의 합집합)만, B..C에서 `origin=round4`만; `concept_lexicon.json`은 Round 4 문서로 교체.
**하지 않음:** 스코어러·상수·격자 변경, seed 레코드 변경(r0는 불변, r1 레코드도 유지), 임계 변경, B(§11) 구현(조건부), 사용자·세션이 쓴 동의어 목록 병합.

## 3. 스코어러

변경 없음(Round 3 v1.25.1 §3 전부 상속: 상수 8개·격자·기준값 0·`ordering_rules` 3개·legacy 모드·식별자형 질의 예외). `evaluation_code_sha256_at_T`는 T에서 재동결된다.

## 4. 평가와 게이트

변경 없음(Round 3 §4 상속). hidden 생성 규칙 12개(`HIDDEN_RULES_R3` 목록을 `HIDDEN_RULES_R4`로 같은 내용·같은 순서로 노출), 분포, 섹션 교체 계약, needle manifest, 4회 스캔 체크포인트 모두 동일. Round 3 봉인 세트가 없으므로 `reference_set`은 **Round 2** 세트(아카이브 `round2-sealed.json.enc`, Round 3 freeze와 같은 sha)를 다시 가리키고, D 이후 참조 관찰(AC-R3-07)도 Round 2 세트로 1회 수행한다.

## 5. 절차 델타

- **S:** 새 스냅샷. Round 3 S(archive/round3/round3-cache, `a759181c…`)와 fingerprint·spec sha 3개가 같으면 복사(`s_reused_from_round3: true`), 아니면 라이브.
- **문서 제목 코퍼스 스냅샷 (신규, S 직후, 네트워크 1회):** `python tests/benchmarks/doc_titles.py snapshot --out $W/doc-titles-snapshot.json`이 `https://support.atlassian.com/{jira-cloud,confluence-cloud,jira-cloud-administration}.xml` 3개를 가져와 `{fetched_at, sources:[{url, sha256, count}], titles:[{product, slug, tokens}]}`를 쓴다. `product` ∈ {jira-software-cloud, confluence-cloud, jira-cloud-administration}(URL 경로), `slug` = URL 마지막 세그먼트, `tokens` = `norm_tokens(slug.replace('-', ' '))`(단수화·순서 유지·중복 제거). **선별·편집·추가 없음.** 파일 sha를 ledger(`doc_titles_snapshot`)하고 freeze 키 `doc_titles_sha256`(파일 바이트 sha)로 T에 고정, S와 함께 archive. 스냅샷은 seed·hidden 텍스트를 담지 않는다(AC-R4-01; 생성 직후 needle 스캔 대상이 아니라 T 이후 스캔의 allow 디렉터리 — 카탈로그 스냅샷과 같은 지위).
- **사전 (Round 3 §5(b) 상속 + 코퍼스):** 아카이브 Round 2 raw/review(sha 고정) ∪ Round 4 생성 raw/review. 생성 입력(`round4-lexicon-generation-prompt.md`를 `render-generation-input --doc-titles $W/doc-titles-snapshot.json`으로 렌더)은 CONCEPTS(토큰·count·products·설명문 발췌)·**DOCUMENTATION TITLES**(§6.1)·VERBS 블록으로 구성되고, 둘째 첨부 파일 `doc-titles.txt`(전체 slug 단어열, 제품 접두)를 함께 보낸다. 렌더 결과 sha와 첨부 sha를 ledger·`concept_lexicon.json.components`에 기록. 검토자 프롬프트는 Round 3과 같다.
- 나머지(인벤토리 suffix-only, 후보·R5/R6, AC-13 replay, binding pre-T, T, hidden 생성·검토·봉인, B, 워커 2단계 handshake, C/D|F|X, 종료 스캔, readiness)는 Round 3 §5·계획 v16 Tasks 9–17/21의 round 4 판을 따른다.

## 6. 어휘 메커니즘 델타

### 6.1 DOCUMENTATION TITLES 블록 (생성 입력)
- 자원 토큰 `t`마다 `tokens`에 `t`를 포함하는 제목을 **slug 사전순 최대 5개**: `t<TAB>product<TAB>slug words`. 0개면 `t<TAB>-`. 전체 목록은 첨부 `doc-titles.txt`(한 줄 `product<TAB>slug words`, slug 사전순).
- 렌더는 결정적(입력 = 스냅샷 + 카탈로그 + 템플릿). `rendered_sha256`, `doc_titles_attachment_sha256` ledger.

### 6.2 생성 프롬프트(동결 텍스트) 추가 문장
Round 3 v1.24.2 프롬프트에 다음 한 단락을 추가하고 나머지는 유지한다(특정 동의어 예시 금지는 그대로):
> "DOCUMENTATION TITLES lists the titles of the product's official help pages that mention each resource, and the attached file doc-titles.txt lists all of them. These titles show the words the product's user interface and its users use for each resource. Propose those words as synonyms. Include such a word even when it is itself a catalog term of a different product, if users of this product call this resource by it."

### 6.3 자격 규칙
변경 없음(v1.25.1 §6). 교차 제품 예외 덕에 코퍼스에서 나온 다른 제품 용어는 alias가 될 수 있고, 같은 제품의 자원 토큰(s-027의 `search→filter`)은 계속 거부된다(§11 B).

## 7. 도구 변경 요약

| 파일 | 변경 |
|---|---|
| `doc_titles.py` (신규) | `fetch_sitemaps(urls) -> list[(url, bytes)]`(urllib, 타임아웃 30s, 재시도 없음), `parse_sitemap(bytes) -> list[url]`, `snapshot(urls, out)`(위 스키마, 정렬·결정적), `titles_for(snapshot, token) -> list`, `render_block(snapshot, concept_tokens) -> str`, `attachment_text(snapshot) -> str`; CLI `snapshot`, `render-check` |
| `concept_lexicon_check.py` | `render_lexicon_generation_input(template, internal, ranking_raw, doc_snapshot)`: 플레이스홀더 `<one line per concept: …>`·`<verb keys>`에 더해 `<one line per concept title: "<token>\t<product>\t<title words>">`; CLI `render-generation-input --doc-titles PATH --attachment-out PATH` |
| `evaluator.py` | `TOOLING_FILES` += `doc_titles.py`; round 4 freeze 키 집합 = round 3 키 집합 + `doc_titles_sha256`; `PRE_FREEZE_NONVERB_STRUCTURE_SHA256[4]` = 현재 구조(변경 없음이므로 round 3 값과 같은 sha를 4에도 등록) |
| `round_seal.py` | `HIDDEN_RULES_R4 = HIDDEN_RULES_R3`; round 4 freeze는 `--doc-titles` 입력의 sha를 기록; seal/scan/reference-check의 round 4 이름 |
| `round4_simulation.py` | Round 3 시뮬레이션의 round 4 판: 합성 문서 제목 스냅샷(fixture 카탈로그 토큰으로 만든 가짜 slug 20개)을 T 입력으로 사용, `--phase pre-T`/`--phase H` |
| `tune_search_ranking.py`, diag | `ROUND = 4`, 로그 `search-tuning-round4.jsonl`, `--round 4` |

## 8. 테스트 전략 델타

- `doc_titles`: 사이트맵 파싱(sitemapindex vs urlset), slug→tokens 정규화(하이픈·숫자·단수화), 결정적 정렬, 스냅샷 스키마, `titles_for` 상한 5·사전순, 첨부 텍스트 형식, 네트워크 없는 fixture 사이트맵 바이트로 테스트.
- 렌더러: 세 플레이스홀더 모두 치환, 미치환 시 ValueError, 입력 동일 → 바이트 동일.
- freeze: round 4 키 집합(= round 3 + `doc_titles_sha256`), `commit_T` 없음, `PRE_FREEZE…[4]`.
- 시뮬레이션 `--phase H` 6단계 통과(합성 스냅샷 포함); `--phase pre-T`는 실제 S에서 binding.
- 생성 입력 provenance: 렌더 결과에 seed 질의 문자열이 없음을 테스트(fixture bench 질의 vs 합성 스냅샷 렌더).

## 9. 상태 모델·readiness 델타

Round 3 §9 상속. freeze 키 추가 `doc_titles_sha256`; readiness에 `doc_titles_snapshot`(소스 URL 3개·fetch 시각·건수·sha), `round4_operational_snapshot`(S), `round2_regression_snapshot`(AC-R3-02 참조 그대로), `reference_set`(Round 2), 종료 분기 D|F|X 또는 "pre-T 미달"(Round 3와 같은 형식).

## 10. Acceptance Criteria (델타)

| ID | 분기 | 판정 | 검증 |
|---|---|---|---|
| AC-R4-01 | 공통 | 문서 제목 코퍼스 provenance: 스냅샷 파일에 소스 URL 3개·fetch 시각·소스별 sha·건수; `titles`는 소스 URL에서 결정적으로 유도(재파싱 시 동일); 스냅샷·렌더 결과·첨부에 seed/hidden 질의 문자열 없음; freeze `doc_titles_sha256` == 파일 sha | 테스트(파싱 결정성) + ledger + T 이후 스캔 allow 목록에 스냅샷 경로 포함 |
| AC-R4-02 | T | 생성 입력은 카탈로그·코퍼스·동사 키에서만 유도되고 프롬프트에 특정 동의어 예시가 없다; `rendered_sha256`·`doc_titles_attachment_sha256`·템플릿 sha ledger·`components` 기록 | 렌더 결정성 테스트 + ledger |
| AC-R4-03 | 공통 | s-027은 "§6 하 미도달"로 readiness에 기록되고 레코드는 불변; pre-T 임계(≥36)는 그대로 | readiness + bench sha |
| AC-R3-01..15, AC-18b(R3) | 상속 | 이름 치환으로 그대로 | — |

## 11. 위험과 완화

- 생성기가 코퍼스를 보고도 `workspace`/`release`를 내지 않을 수 있다(Confluence 문서는 "space"라고만 쓴다). 완화: 6.2의 지시문; 미달 시 **B 예비안** — 공식 문서 제목 하나에 동의어와 타깃 토큰이 함께 나오면(`save your search as a filter`) 같은 제품의 자원 토큰도 `in_catalog`를 면제하는 "doc-evidenced synonym". 부작용(`search` alias가 모든 search 질의에 `filter`를 더함)이 커서 seed-regression 게이트와 fixture 하드 제약을 통과해야만 하며, 구현은 별도 검수·스펙 정정(v1.x) 후에만 한다.
- 사이트맵 fetch 실패/변경: 스냅샷은 라운드 시작 시 1회, 실패 시 중단·보고(네트워크 재시도는 1회 수동). 사이트맵 내용은 시간에 따라 바뀌므로 sha로 고정하고 archive한다.
- ChatGPT 사용량 창·비결정성: Round 3과 같음.
- s-004는 pre-T에서 실패한 채 T로 가며, 튜닝이 `path_unmatched_penalty`로 풀지 못하면 `tuning_accept`(39/39) 실패 → F. 이것은 Round 2·3과 같은 수용 조건이다.

## 12. 한 줄 정의

Round 4 = Round 3의 스코어러·게이트·봉인 절차를 그대로 두고, 어휘 소스에 seed와 무관한 공식 제품 문서 제목 코퍼스를 더해 pre-T 정책이 36/39를 넘게 한 뒤 새 hidden set으로 Discovery 게이트를 재시도하는 라운드.

## 13. 구현 계획 입력

- 도구 H′는 2개 커밋으로: H13 `doc_titles.py` + 렌더러 + 프롬프트 텍스트 + freeze 키; H14 `round4_simulation.py` + round 4 이름 치환(seal/tune/diag). 각각 TDD·canonical suite·`--phase H`·새 리뷰어 findings 0.
- 컨트롤러 절차는 Round 3 계획 v16의 Tasks 9–17·21 구조를 round 4 이름으로 재사용하고, Task 9 Step 1 직후 "문서 제목 코퍼스 스냅샷" 단계를 둔다.
- 모든 판단·결정은 ChatGPT 검수 스레드에서 논의해 확정한다(사용자 중단 지점은 작업 완료 보고뿐).
