# Search Quality Round 4 — Technical Specification

**문서 버전:** v1.1 (2026-10-09; v1.0 = brainstorming 초안, 사용자 결정 2026-10-09: "seed 레코드 감사(2번)를 짧게 한 뒤 같은 게이트·시스템 보강(1번)", 어휘 소스는 "공식 문서 제목 코퍼스(A) + 프롬프트 지시 병행", B(문서 근거 동일 제품 예외)는 조건부 예비안; v1.1 = ChatGPT 검수 1(P0 4/P1 5) 반영: 라운드 상태 모델(§9.1), 미도달 seed T 금지 게이트(§4.1), 실제 페이지 제목 수집·raw 번들(§5·§6.1), 소스 계약(§5.1), AC-R4-04…08)
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
| s-027 `show my starred searches` | 정상(starred = favourite, Jira UI 용어) | 'searches'→'search'가 `/…/search` 터미널 자원과 literal 일치; 정답에 닿으려면 **같은 제품의 자원 토큰 `search`→`filter` 동의어**가 필요한데 §6은 이를 허용하지 않음. `/filter/my`의 기능어 터미널은 부차적(제거해도 결과 불변) | **§6 하 알려진 미도달** — 레코드 유지; A 후에도 미도달이면 T를 열지 않고 §11 B를 별도 정정·검수 후 활성화(§4.1) |
| s-028 `publish a new project release` | 정상(release = version, Jira UI "Releases") | `release→version` 동의어가 두 번의 stateless 생성에서 나오지 않음(생성기는 release→deployment) | 어휘 소스(§6.1) |
| s-039 `browse pages inside this workspace` | 정상 | `workspace→space` 미생성(v1.25 교차 제품 예외로 자격은 있음; 생성기는 "team area"→space) | 어휘 소스(§6.1) |

프로브(HEAD 코드, 아카이브 Round 3 S): Round 3 사전(feedback→comment, iteration→sprint, time entry→worklog)으로 35/39; `release→version`·`workspace→space`를 더하면 **37/39**, fixture 23/23·6/6, regression 10/14·14/14. 기능어 터미널 제외와 `starred→favourite`는 s-027을 살리지 못했다(카탈로그에서 터미널이 기능어뿐인 op는 `/filter/my` 1개).

**독립성 선언:** 이 스펙을 쓴 세션(42e25099…)은 Round 3 컨트롤러였고 Round 2·3 hidden 평문을 본 적이 없다(Round 3 hidden set은 생성되지 않았다). 그래도 §5의 역할 규칙은 그대로다: Round 4 hidden 생성자·검토자·워커·D 컨트롤러는 각각 별도 stateless/fresh actor다.

## 1. 목표

- Discovery 게이트: 새 봉인 세트에서 held_out ≥ 15/16, negative 0 실패(Round 3 §4 대칭 판정식).
- 튜닝 전 최종 조건(AC-R3-01 상속): binding pre-T에서 seed ≥ 36/39, fixture positive 23/23 · negative raw 6/6, regression raw ≥ 10/14 · effective 14/14, 격자 평가기 동등성 불일치 0. 기대값 37/39(s-004는 격자 도달 가능, s-027은 A로 도달하지 못하면 §4.1에 따라 T 전에 B 정정이 필요).
- 결론의 범위는 Round 3과 같이 "actionable recommendation query의 Discovery 성능"이다.

## 2. 범위

**변경:** `tests/benchmarks/doc_titles.py`(신규: 사이트맵·페이지 제목 수집, raw 번들, 정규화, 렌더 보조; `TOOLING_FILES`에 추가), `tests/benchmarks/round_outcomes.json`(신규: 종결 라운드 기록, §9.1), `tests/benchmarks/concept_lexicon_check.py`(생성 입력 렌더러에 DOCUMENTATION TITLES 블록·둘째 첨부 파일), `tests/benchmarks/round4-lexicon-generation-prompt.md`(신규 동결 텍스트), `tests/benchmarks/round4-lexicon-review-prompt.md`(Round 3 판과 동일 내용, 파일명만), `tests/benchmarks/evaluator.py`(freeze 키 `doc_titles_snapshot_sha256`·`doc_titles_source_bundle_sha256`, round 4 키 집합, `pending_round` 종결 라운드 건너뜀, §9.1), `tests/benchmarks/round_seal.py`(round 4 freeze/seal/catalog 라운드 번호), `tests/benchmarks/round4_simulation.py`(Round 3 시뮬레이션의 round 4 판 + 합성 문서 제목 스냅샷), `tests/tune_search_ranking.py`(`ROUND = 4`, 로그 파일명), diag(`--round 4`), 스펙·계획·readiness.
**불변(byte-invariant):** Round 1·2·3 로그·freeze 항목·readiness 섹션·`round1-final.json`·`round2-*`·`round3-*`(Round 3 동결 텍스트 3종은 역사 파일), fixture 23/6, Phase 1 파일, `search.py`·`policy.py`·`search_ranking.json` **구조**(Round 3 H9에 고정된 `ordering_rules`·상수·격자 그대로; Round 4의 H는 스코어러를 건드리지 않는다), Round 3 회귀 참조 파일(AC-R3-02는 legacy 모드로 그대로 적용).
**제약된 변경:** `verb_methods`는 Round 3과 같은 prefix 불변(suffix는 T에만); `search_aliases.json`은 T에서 `lexicon-r4`(아카이브 Round 2 재게이트분 + Round 4 생성분의 합집합)만, B..C에서 `origin=round4`만; `concept_lexicon.json`은 Round 4 문서로 교체.
**하지 않음:** 스코어러·상수·격자 변경, seed 레코드 변경(r0는 불변, r1 레코드도 유지), 임계 변경, B(§11) 구현(조건부), 사용자·세션이 쓴 동의어 목록 병합.

## 3. 스코어러

변경 없음(Round 3 v1.25.1 §3 전부 상속: 상수 8개·격자·기준값 0·`ordering_rules` 3개·legacy 모드·식별자형 질의 예외). `evaluation_code_sha256_at_T`는 T에서 재동결된다.

## 4. 평가와 게이트

변경 없음(Round 3 §4 상속). hidden 생성 규칙 12개(`HIDDEN_RULES_R3` 목록을 `HIDDEN_RULES_R4`로 같은 내용·같은 순서로 노출), 분포, 섹션 교체 계약, needle manifest, 4회 스캔 체크포인트 모두 동일. Round 3 봉인 세트도 Round 3 freeze 항목도 없으므로(Round 3는 T 전에 종결, §9.1) `reference_set`은 **Round 2** 세트(아카이브 `round2-sealed.json.enc`, Round 2 freeze 항목의 봉인 sha와 같은 파일)를 가리키고, D 이후 참조 관찰(AC-R3-07)도 Round 2 세트로 1회 수행한다.

### 4.1 pre-T 체크포인트 추가 조건 — 미도달 seed 0건 (검수 1 P0-2)
AC-R3-01의 수치 조건(seed ≥36/39 등)에 더해 **T는 `known_unreachable_seed_count == 0`일 때만 허용**한다. 정의: pre-T 진단(`round4_simulation --phase pre-T`)이 실패 seed마다 `reachable_by_grid`(동결 격자의 어느 한 점에서 해당 seed가 정답이 되고 fixture 23/23·6/6 하드 제약이 유지되면 true; 격자 전수 평가는 memoized GridEvaluator)를 기록하고, `reachable_by_grid: false`인 실패 seed의 수가 `known_unreachable_seed_count`다. 0이 아니면 체크포인트는 "pre-T 미달(unreachable)"로 실패하며 T·hidden 생성을 시작하지 않는다. 이유: 최종 수용 조건 `tuning_accept`는 seed 39/39이므로 격자로 도달할 수 없는 seed를 남긴 채 T로 가면 F가 확정된다. 처리 순서: A(§6.1) → pre-T → 미도달 존재 → STOP → §11의 B를 **별도 스펙 정정(v1.x)·검수** 후 활성화 → 같은 S에서 pre-T 재실행. s-004는 프로브상 `path_unmatched_penalty` 격자점에서 정답이 되므로 reachable(검수 1 P1-2: 이 값은 상수 선택에 쓰지 않고 감사 결과의 반증 가능성만 높인다).

## 5. 절차 델타

- **S:** 새 스냅샷. Round 3 S(archive/round3/round3-cache, `a759181c…`)와 fingerprint·spec sha 3개가 같으면 복사(`s_reused_from_round3: true`), 아니면 라이브.
- **문서 제목 코퍼스 스냅샷 (신규, S 직후; 라운드에서 카탈로그 외 유일한 네트워크 단계):** `python -m tests.benchmarks.doc_titles acquire --out-dir $W/doc-title-sources` 가 §5.1의 `DOC_SOURCES` 3개 사이트맵을 받아 **raw bytes 그대로** `$W/doc-title-sources/<product>.sitemap.xml`에 저장하고, 각 `<loc>` 페이지를 1회 GET(간격 ≥0.25 s, 타임아웃 30 s, 재시도 없음)하여 `<product>.pages.jsonl`에 `{url, http_status, html_sha256, title_tag, h1}`(서버 렌더 `<title>`과 첫 `<h1>` 텍스트 **원문**, 정규화 없음; 실패 시 `http_status`만)을 기록한다. `acquisition-manifest.json` = `{fetched_at, sources:[{product, sitemap_url, sitemap_sha256, url_count, page_ok, page_failed}], pages_sha256}`. 이 디렉터리가 **immutable raw 번들**이다(sha = `doc_titles_source_bundle_sha256`, 번들 내 파일 sha 목록의 canonical sha). 이후 **모든** 파싱·렌더·H′ replay는 네트워크가 아니라 이 번들만 읽는다(검수 1 P0-4). 실패 페이지 비율이 5 %를 넘으면 acquire는 exit 1(부분 코퍼스로 진행하지 않음; 1회 수동 재시도 후에도 넘으면 중단·보고). 그다음 `python -m tests.benchmarks.doc_titles snapshot --sources $W/doc-title-sources --out $W/doc-titles-snapshot.json`이 번들에서 결정적으로 `{source_bundle_sha256, sources:[…], titles:[{product, url, title, tokens}]}`를 만든다: `title` = `h1`이 있으면 `h1`, 없으면 `title_tag`에서 ` | ` 뒤 접미(제품명·"Atlassian Support")를 제거한 앞부분, `tokens` = `norm_tokens(title)`(단수화·순서 유지·중복 제거). **선별·편집·추가 없음.** 두 sha를 ledger(`doc_titles_acquired`, `doc_titles_snapshot`)하고 freeze 키 `doc_titles_source_bundle_sha256`·`doc_titles_snapshot_sha256`으로 T에 고정, S와 함께 archive. 번들·스냅샷은 seed·hidden 텍스트를 담지 않고(AC-R4-01·05) T 이후 needle 스캔에서는 카탈로그 스냅샷 디렉터리와 같은 allow 지위다.

### 5.1 코퍼스 소스 계약 (검수 1 P1-5)
`doc_titles.DOC_SOURCES`(동결 상수, `tooling_code_sha256`에 포함):

| product | sitemap_url | allowed_loc_prefix |
|---|---|---|
| jira-software-cloud | https://support.atlassian.com/jira-cloud.xml | https://support.atlassian.com/jira-software-cloud/docs/ |
| confluence-cloud | https://support.atlassian.com/confluence-cloud.xml | https://support.atlassian.com/confluence-cloud/docs/ |
| jira-cloud-administration | https://support.atlassian.com/jira-cloud-administration.xml | https://support.atlassian.com/jira-cloud-administration/docs/ |

(2026-10-09 확인: 세 endpoint 모두 `urlset`, 각 1,088 / 919 / 428 URL; 페이지 `<h1>`은 서버 렌더.) `acquire`의 preflight는 소스마다 HTTP 2xx, XML root ∈ {urlset, sitemapindex}(sitemapindex면 하위 urlset을 재귀 1단계), 모든 `<loc>`의 host == support.atlassian.com, `allowed_loc_prefix`로 시작하지 않는 loc는 **버리고 개수를 manifest에 기록**, 남은 개수 > 0을 검증하며 하나라도 실패하면 exit 1. `product`는 표의 literal이다(URL에서 추론하지 않음).

- **사전 (Round 3 §5(b) 상속 + 코퍼스):** 아카이브 Round 2 raw/review(sha 고정) ∪ Round 4 생성 raw/review. 생성 입력(`round4-lexicon-generation-prompt.md`를 `render-generation-input --doc-titles $W/doc-titles-snapshot.json --attachment-out $W/doc-titles.txt`로 렌더; 이 코드 경로는 bench를 입력으로 받지 않는다(AC-R4-05))은 CONCEPTS(토큰·count·products·설명문 발췌)·**DOCUMENTATION TITLES**(§6.1)·VERBS 블록으로 구성되고, 둘째 첨부 파일 `doc-titles.txt`(전체 제목, 제품 접두)를 함께 보낸다. 렌더 결과 sha와 첨부 sha를 ledger·`concept_lexicon.json.components`에 기록. 검토자 프롬프트는 Round 3과 같다.
- 나머지(인벤토리 suffix-only, 후보·R5/R6, AC-13 replay, binding pre-T, T, hidden 생성·검토·봉인, B, 워커 2단계 handshake, C/D|F|X, 종료 스캔, readiness)는 Round 3 §5·계획 v16 Tasks 9–17/21의 round 4 판을 따른다.

## 6. 어휘 메커니즘 델타

### 6.1 DOCUMENTATION TITLES 블록 (생성 입력)
- 자원 토큰 `t`마다 `tokens`에 `t`를 포함하는 제목을 **(product, title) 사전순 최대 5개**: `t<TAB>product<TAB>title`. 0개면 `t<TAB>-`. 전체 목록은 첨부 `doc-titles.txt`(한 줄 `product<TAB>title`, (product, title) 사전순, 중복 제목 1회). 제목은 실제 페이지 `<h1>`(폴백 `<title>` 앞부분)이지 URL slug가 아니다(검수 1 P0-3: slug에는 구 용어가 남는다).
- 렌더는 결정적(입력 = 스냅샷 + 카탈로그 + 템플릿). `rendered_sha256`, `doc_titles_attachment_sha256` ledger.

### 6.2 생성 프롬프트(동결 텍스트) 추가 문장
Round 3 v1.24.2 프롬프트에 다음 한 단락을 추가하고 나머지는 유지한다(특정 동의어 예시 금지는 그대로):
> "DOCUMENTATION TITLES lists the current titles of the product's official help pages that mention each resource, and the attached file doc-titles.txt lists all of them. These titles show the words the product's user interface and its users use for each resource. Propose those words as synonyms. Include such a word even when it is itself a catalog term of a different product, if users of this product call this resource by it."

### 6.3 자격 규칙
변경 없음(v1.25.1 §6). 교차 제품 예외 덕에 코퍼스에서 나온 다른 제품 용어는 alias가 될 수 있고, 같은 제품의 자원 토큰(s-027의 `search→filter`)은 계속 거부된다(§11 B).

## 7. 도구 변경 요약

| 파일 | 변경 |
|---|---|
| `doc_titles.py` (신규) | `DOC_SOURCES`(§5.1), `preflight(source, sitemap_bytes) -> list[str]`, `parse_sitemap(bytes) -> list[url]`, `extract_title(html_bytes) -> (title_tag, h1)`(정규식/html.parser, JS 불요), `acquire(sources, out_dir, fetch=urllib)`(raw 번들 + manifest; `fetch` 주입으로 테스트는 네트워크 없음), `bundle_sha256(out_dir)`, `snapshot(out_dir) -> dict`(번들만 읽음, 결정적), `titles_for(snapshot, token) -> list`, `render_block(snapshot, concept_tokens) -> str`, `attachment_text(snapshot) -> str`; CLI `acquire`, `snapshot`, `render-check`. 어떤 함수도 bench/`search_queries.json` 경로·인자를 받지 않는다 |
| `concept_lexicon_check.py` | `render_lexicon_generation_input(template, internal, ranking_raw, doc_snapshot)`: 플레이스홀더 `<one line per concept: …>`·`<verb keys>`에 더해 `<one line per concept title: "<token>\t<product>\t<title words>">`; CLI `render-generation-input --doc-titles PATH --attachment-out PATH` |
| `evaluator.py` | `TOOLING_FILES` += `doc_titles.py`; round 4 freeze 키 집합 = round 3 키 집합 + `doc_titles_source_bundle_sha256` + `doc_titles_snapshot_sha256`; `PRE_FREEZE_NONVERB_STRUCTURE_SHA256[4]` = 현재 구조(변경 없음이므로 round 3 값과 같은 sha를 4에도 등록, 3은 역사로 유지); `load_round_outcomes()`·`closed_rounds()`; `pending_round`는 종결 라운드를 건너뜀(§9.1); `current_round`는 freeze 항목 중 최대 round(비연속 [1,2,4] 허용) |
| `round_seal.py` | `HIDDEN_RULES_R4 = HIDDEN_RULES_R3`; round 4 freeze는 `--doc-title-sources DIR --doc-titles PATH`를 받아 두 sha를 기록하고 스냅샷이 번들에서 재생성한 것과 byte-동일한지 검증; `freeze --round 4`는 round 3 항목 부재를 `round_outcomes.json`의 round 3 종결 기록으로 허용(없으면 REFUSED); seal/scan/reference-check의 round 4 이름 |
| `round4_simulation.py` | Round 3 시뮬레이션의 round 4 판: 합성 raw 번들(fixture 카탈로그 토큰으로 만든 가짜 사이트맵 XML + 페이지 20개, `fetch` 주입)에서 acquire→snapshot→render를 거쳐 T 입력으로 사용; `--phase pre-T`는 실패 seed별 `reachable_by_grid`와 `known_unreachable_seed_count`를 출력하고 0이 아니면 exit 1(§4.1); `--phase H` |
| `tune_search_ranking.py`, diag | `ROUND = 4`, 로그 `search-tuning-round4.jsonl`, `--round 4` |

## 8. 테스트 전략 델타

- `doc_titles`: preflight(host·prefix·root·count), 사이트맵 파싱(sitemapindex vs urlset), `extract_title`(h1 우선, `<title>` 접미 제거, 엔티티 디코드), acquire가 주입 `fetch`로 raw 번들·manifest를 쓰고 실패율 >5 %면 exit 1, `bundle_sha256` 결정성, snapshot이 번들만 읽음(네트워크 함수 호출 시 테스트 실패), title→tokens 정규화(단수화·순서), `titles_for` 상한 5·사전순, 첨부 텍스트 형식, 모듈에 bench 경로 상수·인자가 없음(AC-R4-05: `search_queries.json` 열기를 monkeypatch로 금지한 채 acquire→snapshot→render 전 과정 실행).
- 렌더러: 세 플레이스홀더 모두 치환, 미치환 시 ValueError, 입력 동일 → 바이트 동일.
- freeze·상태 모델: round 4 키 집합(= round 3 + 두 doc_titles 키), `commit_T` 없음, `PRE_FREEZE…[4]`; `round_outcomes.json` 스키마·`closed_rounds`; freeze [1,2] + outcomes {3} → `pending_round() == 4`; outcomes 없이 → 3(기존 동작 유지); `freeze --round 4`가 round 3 종결 기록 없이는 REFUSED; `current_round`가 [1,2,4]에서 4.
- 시뮬레이션 `--phase H` 통과(합성 raw 번들 포함); `--phase pre-T`는 실제 S에서 binding이며 `known_unreachable_seed_count` 게이트를 합성 상태로 테스트(격자 어느 점에서도 못 맞히는 seed 1건 → exit 1).
- 스코어러 불변(AC-R4-04): H13·H14 커밋 범위에서 `search.py`·`policy.py`·`search_ranking.json`의 `git diff --stat`이 비어 있음을 리뷰 패키지와 ledger에 기록(테스트가 아니라 체크포인트).
- 생성 입력 provenance: 렌더 결과에 seed 질의 문자열이 없음을 테스트(fixture bench 질의 vs 합성 스냅샷 렌더).

## 9. 상태 모델·readiness 델타

### 9.1 종결 라운드 기록과 라운드 번호 (검수 1 P0-1)
Round 3는 T에 이르지 못했으므로 `round_freeze.json`에 round 3 항목이 **없고, 만들지도 않는다**(가짜 T 금지). 대신 `tests/benchmarks/round_outcomes.json`(신규, 커밋)에 T 전에 종결된 라운드를 기록한다: `[{"round": 3, "outcome": "pre-T not reached", "decided": "2026-10-07", "decision_record": "docs/phase3-readiness.md#search-quality-round-3--decision-record-2026-10-07", "final_housekeeping_commit": "9bf823d", "last_checkpoint": {"seed": "35/39", "threshold": 36}}]`. 계약:
- `evaluator.closed_rounds()` = outcomes의 round 집합; `pending_round()` = `PRE_FREEZE_NONVERB_STRUCTURE_SHA256` 키 중 `current_round` 초과이면서 종결되지 않은 최소 round → freeze [1,2] + outcomes {3} + 키 {3,4} ⇒ **4**. outcomes 파일이 없으면 기존 동작(3)이다(Round 3 역사 테스트 불변).
- `round_freeze.json`은 비연속 round 목록 [1,2,4]를 허용한다. `current_round` = 최대 round 항목. `freeze --round N`은 N−1 항목이 없으면 outcomes에 N−1 종결 기록이 있을 때만 진행(없으면 REFUSED).
- 한 round는 freeze 항목과 outcomes 기록을 동시에 가질 수 없다(테스트). Round 4가 pre-T 미달로 종결되면 outcomes에 round 4를 추가한다.
- AC-R3-02의 회귀 참조(round 2 격리 스코어러)와 `reference_set`(Round 2 봉인)은 round 번호가 아니라 freeze 항목 2를 가리키므로 영향 없다.

Round 3 §9 상속. freeze 키 추가 `doc_titles_source_bundle_sha256`·`doc_titles_snapshot_sha256`; readiness에 `doc_titles_snapshot`(소스 3개·fetch 시각·URL/페이지 건수·실패 건수·번들 sha·스냅샷 sha), `round4_operational_snapshot`(S), `round2_regression_snapshot`(AC-R3-02 참조 그대로), `reference_set`(Round 2), 종료 분기 D|F|X 또는 "pre-T 미달"(Round 3와 같은 형식).

## 10. Acceptance Criteria (델타)

| ID | 분기 | 판정 | 검증 |
|---|---|---|---|
| AC-R4-01 | 공통 | 문서 제목 코퍼스 provenance: raw 번들(`doc-title-sources/`: 사이트맵 bytes, 페이지별 `<title>`/`<h1>` 원문, manifest)이 immutable이고 freeze `doc_titles_source_bundle_sha256`과 일치; 스냅샷은 번들에서만 결정적으로 재생성되어 freeze `doc_titles_snapshot_sha256`과 byte-동일(H′ replay는 번들 재파싱, 재fetch 금지); 소스 계약 §5.1 preflight 통과 기록; 스냅샷·렌더 결과·첨부에 seed/hidden 질의 문자열 없음 | 테스트(번들→스냅샷 결정성, preflight) + `freeze --round 4` 검증 + ledger + T 이후 스캔 allow 목록에 번들·스냅샷 경로 포함 |
| AC-R4-02 | T | 생성 입력은 카탈로그·코퍼스·동사 키에서만 유도되고 프롬프트에 특정 동의어 예시가 없다; 생성자·검토자는 Round 3 §5와 같이 stateless ChatGPT Temporary chat(개인화 off, 메모리 off)에서 각각 별도 실행; `rendered_sha256`·`doc_titles_attachment_sha256`·템플릿 sha ledger·`components` 기록 | 렌더 결정성 테스트 + ledger(생성·검토 세션 attestation) |
| AC-R4-04 | 공통 | 스코어러 불변: Round 4의 모든 H/H′ 커밋에서 `search.py`·`policy.py`·`search_ranking.json`의 스코어러·상수·격자·`ordering_rules` diff = 0; T에서 허용되는 `search_ranking.json` 변경은 `verb_methods` suffix와 `aliases` 추가(lexicon-r4)뿐, B..C는 `origin=round4` alias뿐 | H′마다 `git diff --stat <prev>..<H′> -- 세 파일` 공란 ledger + T 커밋 diff 검사 |
| AC-R4-05 | 공통 | no-benchmark-read: `doc_titles.py`와 생성 입력 렌더 코드 경로는 bench(`search_queries.json`)를 인자·경로·상수 어디서도 받지 않는다 | 테스트(bench 열기를 금지한 monkeypatch 아래 acquire→snapshot→render 전 과정 실행) + 코드 grep |
| AC-R4-06 | pre-T | T 선행 조건: `known_unreachable_seed_count == 0`(§4.1); 실패 seed마다 `reachable_by_grid` 기록 | `--phase pre-T` exit 코드 + ledger |
| AC-R4-07 | 공통 | 라운드 상태 모델(§9.1): round 3 freeze 항목 없음·가짜 T 없음, `round_outcomes.json`에 round 3 종결, `pending_round() == 4`, freeze [1,2,4] 허용 | 테스트 + `freeze --round 4` 가드 |
| AC-R4-08 | 공통 | 코퍼스 소스 계약(§5.1): `DOC_SOURCES` literal, preflight 실패 시 acquire exit 1, prefix 밖 loc 폐기 건수 manifest 기록 | 테스트 + manifest |
| AC-R4-03 | 공통 | s-027은 "§6 하 미도달(search→filter 불가)"로 readiness에 기록되고 레코드는 불변; pre-T 임계(≥36)는 그대로이되 미도달 seed가 남아 있으면 T를 열지 않는다(AC-R4-06) | readiness + bench sha |
| AC-R3-01..15, AC-18b(R3) | 상속 | 이름 치환으로 그대로 | — |

## 11. 위험과 완화

- 생성기가 코퍼스를 보고도 `workspace`/`release`를 내지 않을 수 있다(Confluence 문서는 "space"라고만 쓴다). 완화: 6.2의 지시문; 그래도 pre-T 미달이면 Round 3처럼 "pre-T 미달"로 종결하거나 어휘 소스를 다시 설계한다(임계·레코드는 불변).
- **B 예비안(조건부, §4.1의 STOP 뒤에만):** s-027처럼 같은 제품의 자원 토큰 동의어(`search→filter`)가 필요한 미도달 seed에 대해 "doc-evidenced same-product synonym" — 요건(검수 1 P1-3): (i) 동의어와 타깃 토큰이 **같은 제목**에 함께 나오는 것만으로는 부족하고, 코퍼스 제목에서 `<synonym> as a <target>` / `<target> (<synonym>)` 류의 **명시적 관계 구문**이거나 stateless 검토자가 동의어로 승인한 것, (ii) `source_product == target_product`, (iii) 고정 코퍼스 provenance(번들 sha), (iv) seed-regression 게이트·fixture 하드 제약 통과. 부작용(`search` alias가 모든 search 질의에 `filter`를 더함)이 크므로 별도 스펙 정정(v1.x)·검수 뒤에만 구현한다.
- 코퍼스 수집 실패/변경: 수집은 라운드 시작 시 1회(약 2,435 페이지, 간격 0.25 s → 10여 분), 실패율 >5 %면 중단·보고(수동 재시도 1회). 사이트맵·제목은 시간에 따라 바뀌므로 raw 번들을 보존하고 sha로 고정·archive한다. `extract_title` 자체의 결함은 번들에 원문 `<title>`/`<h1>`만 있으므로 정규화 단계까지만 replay 가능하다(HTML 전체는 보존하지 않음; 결함이 추출 단계면 새 S와 함께 재수집 — ledger에 `doc_titles_reacquired`).
- ChatGPT 사용량 창·비결정성: Round 3과 같음.
- s-004는 pre-T에서 실패한 채 T로 가며, 튜닝이 `path_unmatched_penalty`로 풀지 못하면 `tuning_accept`(39/39) 실패 → F. 이것은 Round 2·3과 같은 수용 조건이다.

## 12. 한 줄 정의

Round 4 = Round 3의 스코어러·게이트·봉인 절차를 그대로 두고, 어휘 소스에 seed와 무관한 공식 제품 문서 제목 코퍼스를 더해 pre-T 정책이 36/39를 넘게 한 뒤 새 hidden set으로 Discovery 게이트를 재시도하는 라운드.

## 13. 구현 계획 입력

- 도구 H′는 3개 커밋으로: H13 상태 모델(`round_outcomes.json`, `pending_round`·`current_round`·`freeze` 가드, round 4 freeze 키) ; H14 `doc_titles.py`(소스 계약·acquire·번들·snapshot·추출) + 렌더러 + 프롬프트 텍스트 + AC-R4-05 테스트; H15 `round4_simulation.py`(합성 번들, `reachable_by_grid`/`known_unreachable_seed_count` 게이트) + round 4 이름 치환(seal/tune/diag). 각각 TDD·canonical suite·`--phase H`·새 리뷰어 findings 0·AC-R4-04 diff 공란.
- 컨트롤러 절차는 Round 3 계획 v16의 Tasks 9–17·21 구조를 round 4 이름으로 재사용하고, Task 9 Step 1 직후 "문서 제목 코퍼스 수집·스냅샷" 단계를, pre-T 뒤에 "미도달 seed 0건" 게이트(§4.1)를 둔다.
- 모든 판단·결정은 ChatGPT 검수 스레드에서 논의해 확정한다(사용자 중단 지점은 작업 완료 보고뿐).
