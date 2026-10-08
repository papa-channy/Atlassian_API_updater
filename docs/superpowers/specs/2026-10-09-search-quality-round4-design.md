# Search Quality Round 4 — Technical Specification

**문서 버전:** v1.4 (2026-10-09; v1.4 = ChatGPT 검수 4(P0 2/P1 4) 반영: 도달성 = 튜닝 파이프라인 dry-run(§4.1), pre-B 중단 X_preB(§9.4, AC-R4-09), STOP/종결 분리(§4.1·§9.1), epoch lineage·redirect·T 없는 종결 sha(§5·§9); v1.3 = ChatGPT 검수 3(P0 1/P1 5) 반영: H′ 두 경로·acquisition epoch(§9.3), proposer 궤적 기반 `reachable_by_alias`(§4.1), `round_outcomes_sha256`·pending_round 일치 가드(§9.1), HTML sha 정합성(§5), AC-R4-01 갱신; v1.2 = ChatGPT 검수 2(P0 3/P1 4) 반영: AC-01a 시작 커밋 치환(§9.2), 미도달 정의를 허용 튜닝 액션 공간 기준으로(§4.1), 페이지 raw HTML 보존(§5), AC-R4-01/04/08 정정; v1.0 = brainstorming 초안, 사용자 결정 2026-10-09: "seed 레코드 감사(2번)를 짧게 한 뒤 같은 게이트·시스템 보강(1번)", 어휘 소스는 "공식 문서 제목 코퍼스(A) + 프롬프트 지시 병행", B(문서 근거 동일 제품 예외)는 조건부 예비안; v1.1 = ChatGPT 검수 1(P0 4/P1 5) 반영: 라운드 상태 모델(§9.1), 미도달 seed T 금지 게이트(§4.1), 실제 페이지 제목 수집·raw 번들(§5·§6.1), 소스 계약(§5.1), AC-R4-04…08)
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

**변경:** `tests/benchmarks/doc_titles.py`(신규: 사이트맵·페이지 HTML 수집, raw 번들, 제목 추출·정규화, 렌더 보조; `TOOLING_FILES`에 추가), `tests/benchmarks/round_outcomes.json`(신규: 종결 라운드 기록, §9.1), `tests/benchmarks/concept_lexicon_check.py`(생성 입력 렌더러에 DOCUMENTATION TITLES 블록·둘째 첨부 파일), `tests/benchmarks/round4-lexicon-generation-prompt.md`(신규 동결 텍스트), `tests/benchmarks/round4-lexicon-review-prompt.md`(Round 3 판과 동일 내용, 파일명만), `tests/benchmarks/evaluator.py`(freeze 키 `doc_titles_snapshot_sha256`·`doc_titles_source_bundle_sha256`, round 4 키 집합, `pending_round` 종결 라운드 건너뜀, §9.1), `tests/benchmarks/round_seal.py`(round 4 freeze/seal/catalog 라운드 번호), `tests/benchmarks/round4_simulation.py`(Round 3 시뮬레이션의 round 4 판 + 합성 문서 제목 스냅샷), `tests/tune_search_ranking.py`(`ROUND = 4`, 로그 파일명), diag(`--round 4`), 스펙·계획·readiness.
**불변(byte-invariant):** Round 1·2·3 로그·freeze 항목·readiness 섹션·`round1-final.json`·`round2-*`·`round3-*`(Round 3 동결 텍스트 3종은 역사 파일), fixture 23/6, Phase 1 파일, `search.py`·`policy.py`·`search_ranking.json` **구조**(Round 3 H9에 고정된 `ordering_rules`·상수·격자 그대로; Round 4의 H는 스코어러를 건드리지 않는다), Round 3 회귀 참조 파일(AC-R3-02는 legacy 모드로 그대로 적용).
**제약된 변경:** `verb_methods`는 Round 3과 같은 prefix 불변(suffix는 T에만); `search_aliases.json`은 T에서 `lexicon-r4`(아카이브 Round 2 재게이트분 + Round 4 생성분의 합집합)만, B..C에서 `origin=round4`만; `concept_lexicon.json`은 Round 4 문서로 교체.
**하지 않음:** 스코어러·상수·격자 변경, seed 레코드 변경(r0는 불변, r1 레코드도 유지), 임계 변경, B(§11) 구현(조건부), 사용자·세션이 쓴 동의어 목록 병합.

## 3. 스코어러

변경 없음(Round 3 v1.25.1 §3 전부 상속: 상수 8개·격자·기준값 0·`ordering_rules` 3개·legacy 모드·식별자형 질의 예외). `evaluation_code_sha256_at_T`는 T에서 재동결된다.

## 4. 평가와 게이트

변경 없음(Round 3 §4 상속). hidden 생성 규칙 12개(`HIDDEN_RULES_R3` 목록을 `HIDDEN_RULES_R4`로 같은 내용·같은 순서로 노출), 분포, 섹션 교체 계약, needle manifest, 4회 스캔 체크포인트 모두 동일. Round 3 봉인 세트도 Round 3 freeze 항목도 없으므로(Round 3는 T 전에 종결, §9.1) `reference_set`은 **Round 2** 세트(아카이브 `round2-sealed.json.enc`, Round 2 freeze 항목의 봉인 sha와 같은 파일)를 가리키고, D 이후 참조 관찰(AC-R3-07)도 Round 2 세트로 1회 수행한다.

### 4.1 pre-T 체크포인트 추가 조건 — 미도달 seed 0건 (검수 1 P0-2)
AC-R3-01의 수치 조건(seed ≥36/39 등)에 더해 **T는 `known_unreachable_seed_count == 0`일 때만 허용**한다. 정의(검수 2 P0-2, 검수 4 P0-1): "미도달"은 **동결될 튜닝 파이프라인을 그대로 한 번 돌렸을 때 끝까지 남는 실패 seed**다. 튜닝(Round 3 §3·§6 상속)은 임의의 격자점을 고르는 시스템이 아니라 one-way다: B 상태(T 정책 + lexicon-r4) → 격자 전수 평가(memoized GridEvaluator) → `select_candidate` **정확히 1회** → 그 점에서 원자 alias 제안기 **정확히 1회**(전역 예산 `BUDGET = 15`, seed당 `PER_SEED = 2`; "budget-2"는 seed당 한도를 가리킨다) → `tuning_accept` 판정, 재선택·2차 제안 없음. 따라서 pre-T 진단(`round4_simulation --phase pre-T`)은 **이 파이프라인의 exact dry-run**을 쓰기 없이 수행한다: pre-T 정책을 B 상태로 간주하고 같은 코드 경로(`tune_search_ranking`의 격자 평가·선택·`propose_aliases`·`validate_alias_change`)를 그 라운드의 후보 집합(R5/R6, §6 자격 통과분)과 분류된 bench로 실행하되 파일을 쓰지 않고, dry-run 최종 상태에서 여전히 실패하는 seed의 집합이 `known_unreachable_seeds`, 그 수가 `known_unreachable_seed_count`다. 보조 진단으로 실패 seed마다 `reachable_by_grid`(어느 격자점에서든 정답+불변식)와 `dry_run_fixed`(dry-run이 고친 seed)를 기록하되 **T 게이트에는 dry-run 결과만 쓴다**. dry-run은 결정적이며 입력 sha(정책·후보·bench·격자)와 결과를 ledger한다. s-027: `search→filter`는 §6 자격 탈락이라 후보에 없고 dry-run에서도 남아 미도달; s-004: dry-run이 `path_unmatched_penalty` 점을 선택해 고치면 reachable.

상태 구분(검수 4 P1-1): 미도달 seed가 있으면 체크포인트는 `STOP_FOR_AMENDMENT`(라운드 **비종결**: ledger `checkpoint: pre-T`, `result: stop_for_amendment`, 미도달 seed id)로 멈추고 B(§11)를 별도 v1.x 정정·검수 후 같은 S에서 pre-T를 재실행한다. 라운드를 끝내는 `TERMINAL_PRE_T_NOT_REACHED`(§9.1의 outcomes 추가)는 사용자 결정으로만 전이하며, STOP 상태에서 outcomes를 추가하는 것은 금지(테스트: STOP ledger가 있고 사용자 종결 결정 ledger가 없으면 `round_outcomes` append 거부).

이유: 최종 수용 조건 `tuning_accept`는 seed 39/39이므로 파이프라인이 고칠 수 없는 seed를 남긴 채 T로 가면 F가 확정된다. 처리 순서: A(§6.1) → pre-T → 미도달 존재 → STOP_FOR_AMENDMENT → §11의 B를 **별도 스펙 정정(v1.x)·검수** 후 활성화 → 같은 S에서 pre-T 재실행. dry-run 결과는 상수 선택에 쓰지 않으며(B는 자체적으로 다시 돌린다) 감사 결과의 반증 가능성만 높인다(검수 1 P1-2).

## 5. 절차 델타

- **S:** 새 스냅샷. Round 3 S(archive/round3/round3-cache, `a759181c…`)와 fingerprint·spec sha 3개가 같으면 복사(`s_reused_from_round3: true`), 아니면 라이브.
- **문서 제목 코퍼스 스냅샷 (신규, S 직후; 라운드에서 카탈로그 외 유일한 네트워크 단계):** `python -m tests.benchmarks.doc_titles acquire --out-dir $W/doc-title-sources` 가 §5.1의 `DOC_SOURCES` 3개 사이트맵을 받아 **raw bytes 그대로** `$W/doc-title-sources/<product>.sitemap.xml`(sitemapindex이면 하위 urlset도 `<product>.child-<n>.sitemap.xml`로 모두 보존, 검수 2 P1-3)에 저장하고, 각 `<loc>` 페이지를 1회 GET(간격 ≥0.25 s, 타임아웃 30 s, 재시도 없음; redirect를 따르되 **최종 URL `final_url`을 기록하고 host == support.atlassian.com ∧ `allowed_loc_prefix` 재검증, 어긋나면 그 페이지는 `page_failed`로 분류하고 HTML을 저장하지 않음** — 검수 4 P1-3)하여 **응답 HTML 전체를 `pages/<html_sha256>.html.gz`로 보존**하고(검수 2 P0-3: 추출기 결함도 번들에서 완전 replay; 약 2,435 페이지, gzip 후 수십 MB, `$W` 전용·archive 포함·커밋 안 함) `<product>.pages.jsonl`에 `{url, final_url, http_status, html_sha256}`(실패 시 `html_sha256` 없음, `fail_reason`)을 기록한다. `acquisition-manifest.json` = `{fetched_at, sources:[{product, sitemap_url, sitemap_sha256, child_sitemaps:[{file, sha256}], loc_count, discarded_loc_count, url_count, page_ok, page_failed}], pages_sha256}`(검수 2 P1-2). `<title>`/`<h1>` 추출은 acquire가 아니라 `snapshot` 단계에서 번들의 HTML로부터 수행한다. 내용 주소 정합성(검수 3 P1-4): `snapshot`과 `freeze --round 4`는 모든 페이지에 대해 `sha256(gunzip(pages/<x>.html.gz)) == pages.jsonl.html_sha256 == x`를 검증하고 하나라도 어긋나면 exit 1. 이 디렉터리가 **immutable raw 번들**이다(sha = `doc_titles_source_bundle_sha256`, 번들 내 파일 sha 목록의 canonical sha). 이후 **bundle-preserving H′**(§9.3)의 추출·파싱·렌더·replay는 네트워크가 아니라 이 번들만 읽는다(검수 1 P0-4); 수집 단계 자체의 결함은 **acquisition-invalidating H′**(§9.3)로 새 epoch를 만든다. 실패 페이지 비율이 5 %를 넘으면 acquire는 exit 1(부분 코퍼스로 진행하지 않음; 1회 수동 재시도 후에도 넘으면 중단·보고). 그다음 `python -m tests.benchmarks.doc_titles snapshot --sources $W/doc-title-sources --out $W/doc-titles-snapshot.json`이 번들에서 결정적으로 `{source_bundle_sha256, sources:[…], titles:[{product, url, title, tokens}]}`를 만든다: `title` = 번들 HTML에서 `extract_title`로 얻은 첫 `<h1>` 원문(엔티티 디코드·공백 정규화), 없으면 `title_tag`에서 ` | ` 뒤 접미(제품명·"Atlassian Support")를 제거한 앞부분, `tokens` = `norm_tokens(title)`(단수화·순서 유지·중복 제거). **선별·편집·추가 없음.** 두 sha를 ledger(`doc_titles_acquired`, `doc_titles_snapshot`)하고 freeze 키 `doc_titles_source_bundle_sha256`·`doc_titles_snapshot_sha256`으로 T에 고정, S와 함께 archive. 번들·스냅샷은 seed·hidden 텍스트를 담지 않고(AC-R4-01·05) T 이후 needle 스캔에서는 카탈로그 스냅샷 디렉터리와 같은 allow 지위다.

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
| `doc_titles.py` (신규) | `DOC_SOURCES`(§5.1), `preflight(source, sitemap_bytes) -> list[str]`, `parse_sitemap(bytes) -> list[url]`, `extract_title(html_bytes) -> (title_tag, h1)`(정규식/html.parser, JS 불요), `acquire(sources, out_dir, fetch=urllib)`(raw 번들: 사이트맵·하위 사이트맵·페이지 HTML gzip + manifest; `fetch` 주입으로 테스트는 네트워크 없음), `bundle_sha256(out_dir)`(manifest·사이트맵·pages.jsonl·모든 HTML gzip의 sha 목록 canonical sha), `snapshot(out_dir) -> dict`(번들만 읽음, HTML에서 추출, 결정적), `titles_for(snapshot, token) -> list`, `render_block(snapshot, concept_tokens) -> str`, `attachment_text(snapshot) -> str`; CLI `acquire`, `snapshot`, `render-check`. 어떤 함수도 bench/`search_queries.json` 경로·인자를 받지 않는다 |
| `concept_lexicon_check.py` | `render_lexicon_generation_input(template, internal, ranking_raw, doc_snapshot)`: 플레이스홀더 `<one line per concept: …>`·`<verb keys>`에 더해 `<one line per concept title: "<token>\t<product>\t<title words>">`; CLI `render-generation-input --doc-titles PATH --attachment-out PATH` |
| `evaluator.py` | `TOOLING_FILES` += `doc_titles.py`; round 4 freeze 키 집합 = round 3 키 집합 + `doc_titles_source_bundle_sha256` + `doc_titles_snapshot_sha256` + `round_outcomes_sha256`; `PRE_FREEZE_NONVERB_STRUCTURE_SHA256[4]` = 현재 구조(변경 없음이므로 round 3 값과 같은 sha를 4에도 등록, 3은 역사로 유지); `load_round_outcomes()`·`closed_rounds()`; `pending_round`는 종결 라운드를 건너뜀(§9.1); `current_round`는 freeze 항목 중 최대 round(비연속 [1,2,4] 허용) |
| `round_seal.py` | `HIDDEN_RULES_R4 = HIDDEN_RULES_R3`; round 4 freeze는 `--doc-title-sources DIR --doc-titles PATH`를 받아 두 sha를 기록하고 스냅샷이 번들에서 재생성한 것과 byte-동일한지 검증; `freeze --round N`은 `N == pending_round(freeze, outcomes)`와 하위 round 단일 상태를 요구(§9.1; 아니면 REFUSED), `round_outcomes_sha256` 기록, 페이지 HTML sha 정합성 검증; seal/scan/reference-check의 round 4 이름 |
| `round4_simulation.py` | Round 3 시뮬레이션의 round 4 판: 합성 raw 번들(fixture 카탈로그 토큰으로 만든 가짜 사이트맵 XML + 페이지 20개, `fetch` 주입)에서 acquire→snapshot→render를 거쳐 T 입력으로 사용; `--phase pre-T`는 튜닝 파이프라인 dry-run(격자 전수 → 선택 1회 → 제안기 1회, 쓰기 없음)을 돌려 `known_unreachable_seeds`·`known_unreachable_seed_count`와 진단 `reachable_by_grid`·`dry_run_fixed`를 출력하고 0이 아니면 exit 1(§4.1); 합성 X_preB 수명주기; `--phase H` |
| `tune_search_ranking.py`, diag | `ROUND = 4`, 로그 `search-tuning-round4.jsonl`, `--round 4` |

## 8. 테스트 전략 델타

- `doc_titles`: preflight(host·prefix·root·count), 사이트맵 파싱(sitemapindex vs urlset), `extract_title`(h1 우선, `<title>` 접미 제거, 엔티티 디코드), acquire가 주입 `fetch`로 raw 번들·manifest를 쓰고 실패율 >5 %면 exit 1, `bundle_sha256` 결정성, snapshot이 번들만 읽음(네트워크 함수 호출 시 테스트 실패), title→tokens 정규화(단수화·순서), `titles_for` 상한 5·사전순, 첨부 텍스트 형식, 모듈에 bench 경로 상수·인자가 없음(AC-R4-05: `search_queries.json` 열기를 monkeypatch로 금지한 채 acquire→snapshot→render 전 과정 실행).
- 렌더러: 세 플레이스홀더 모두 치환, 미치환 시 ValueError, 입력 동일 → 바이트 동일.
- freeze·상태 모델: round 4 키 집합(= round 3 + 두 doc_titles 키 + `round_outcomes_sha256`), `commit_T` 없음, `PRE_FREEZE…[4]`; `round_outcomes.json` 스키마·`closed_rounds`; freeze [1,2] + outcomes {3} → `pending_round() == 4`; outcomes 없이 → 3(기존 동작 유지); `freeze --round 4`가 round 3 종결 기록 없이는 REFUSED, `--round 5`·freeze [1]+outcomes{3}에서 `--round 4`도 REFUSED; `current_round`가 [1,2,4]에서 4; 같은 round가 freeze와 outcomes에 동시에 있으면 로드 실패.
- H′ 두 경로(§9.3): 시뮬레이션 합성 상태에서 bundle-preserving replay가 번들 sha를 유지하고 스냅샷 sha만 바꾸는지, acquisition-invalidating이 새 epoch 디렉터리·새 번들 sha·파생물 폐기 ledger를 남기는지, T 이후 호출은 거부되는지.
- HTML 정합성: gzip 내용 sha ≠ 파일명/pages.jsonl이면 `snapshot`·freeze exit 1.
- 시뮬레이션 `--phase H` 통과(합성 raw 번들 포함); `--phase pre-T`는 실제 S에서 binding이며 `known_unreachable_seed_count` 게이트를 합성 상태로 테스트: dry-run이 격자 선택으로 고치는 seed, 제안기 alias로 고치는 seed, 어느 격자점에서는 맞지만 `select_candidate`가 고르지 않는 점이어서 dry-run 뒤에도 남는 seed(→ 미도달; `reachable_by_grid: true`이지만 게이트에 쓰이지 않음을 확인), 자격 탈락 alias만 있는 seed → exit 1; dry-run이 `tune_search_ranking`의 같은 함수(격자 평가·`select_candidate`·`propose_aliases`·`validate_alias_change`, BUDGET 15/PER_SEED 2)를 호출하고 파일을 쓰지 않음(쓰기 monkeypatch).
- 상태 전이: STOP_FOR_AMENDMENT 상태에서 outcomes append 거부; X_preB 합성 수명주기(T 뒤 B 없이 중단 → readiness·outcomes·invalidated_by, hidden 평가 0).
- 스코어러 불변(AC-R4-04): H13·H14 커밋 범위에서 `search.py`·`policy.py`·`search_ranking.json`의 `git diff --stat`이 비어 있음을 리뷰 패키지와 ledger에 기록(테스트가 아니라 체크포인트).
- 생성 입력 provenance: 렌더 결과에 seed 질의 문자열이 없음을 테스트(fixture bench 질의 vs 합성 스냅샷 렌더).

## 9. 상태 모델·readiness 델타

### 9.1 종결 라운드 기록과 라운드 번호 (검수 1 P0-1)
Round 3는 T에 이르지 못했으므로 `round_freeze.json`에 round 3 항목이 **없고, 만들지도 않는다**(가짜 T 금지). 대신 `tests/benchmarks/round_outcomes.json`(신규, 커밋)에 T 전에 종결된 라운드를 기록한다: `[{"round": 3, "outcome": "pre-T not reached", "decided": "2026-10-07", "decision_record": "docs/phase3-readiness.md#search-quality-round-3--decision-record-2026-10-07", "final_housekeeping_commit": "9bf823d", "last_checkpoint": {"seed": "35/39", "threshold": 36}}]`. 계약:
- `evaluator.closed_rounds()` = outcomes의 round 집합; `pending_round()` = `PRE_FREEZE_NONVERB_STRUCTURE_SHA256` 키 중 `current_round` 초과이면서 종결되지 않은 최소 round → freeze [1,2] + outcomes {3} + 키 {3,4} ⇒ **4**. outcomes 파일이 없으면 기존 동작(3)이다(Round 3 역사 테스트 불변).
- `round_freeze.json`은 비연속 round 목록 [1,2,4]를 허용한다. `current_round` = 최대 round 항목. `freeze --round N`은 `N == pending_round(freeze, outcomes)`이고 **N보다 작은 모든 round가 정확히 하나의 상태(freeze 항목 | 종결 기록)를 가질 때만** 진행(검수 3 P1-3: [1,2]+outcome{3} → 4 허용; 5·6 점프나 미해결 round 건너뜀은 REFUSED).
- `round_outcomes.json`은 freeze 순서의 의미를 바꾸는 무결성 상태이므로 Round 4 freeze 키에 `round_outcomes_sha256`을 추가하고 readiness·종료 provenance가 T 시점 sha와 exact equality를 확인한다(검수 3 P1-2). T 없는 종결(`TERMINAL_PRE_T_NOT_REACHED`)에서는 T sha가 없으므로 outcomes에 round 4를 append한 **직후** 파일 sha를 readiness에 `round_outcomes_sha256_after_append`로 기록하고, 종료 스캔이 그 값과 exact equality를 확인한다(검수 4 P1-4).
- 한 round는 freeze 항목과 outcomes 기록을 동시에 가질 수 없다(테스트; §9.4의 `aborted-pre-B`만 예외). Round 4가 `TERMINAL_PRE_T_NOT_REACHED`로 종결되면(사용자 결정, §4.1의 STOP과 구별) outcomes에 round 4를 추가한다.
- AC-R3-02의 회귀 참조(round 2 격리 스코어러)와 `reference_set`(Round 2 봉인)은 round 번호가 아니라 freeze 항목 2를 가리키므로 영향 없다.

### 9.3 Round 4 H′ 두 경로와 acquisition epoch (검수 3 P0-1)
Round 3 §5의 post-S H′ 상태 모델(fix → suite → `--phase H` → fresh review 0 → `housekeeping_commit` move → 같은 S에서 artifact 재생성)은 그대로 상속하되, 외부 코퍼스 때문에 결함의 **위치**에 따라 두 경로로 나눈다:
- **bundle-preserving H′** — 결함이 `snapshot`·`extract_title`·정규화·`titles_for`/렌더·evaluator·시뮬레이션에 있을 때. 기존 raw 번들을 그대로 쓰고(재fetch 금지), 같은 S에서 스냅샷·렌더·사전·후보·pre-T를 재생성한다. `doc_titles_source_bundle_sha256` 불변, `doc_titles_snapshot_sha256`은 바뀔 수 있다. ledger `h_prime_kind: bundle-preserving`.
- **acquisition-invalidating H′** — 결함이 `DOC_SOURCES`·preflight·`parse_sitemap`/하위 사이트맵 순회·prefix 필터·URL 열거·HTTP 수집에 있을 때(번들에 없는 페이지가 생기므로 같은 번들로 replay 불가). **T 이전에만 허용.** 기존 doc 번들과 그 파생물(스냅샷·렌더 입력·생성 raw/review·사전·후보·pre-T 결과)을 전부 폐기하고 `$W/doc-title-sources-epoch<k>/`에 **새 acquisition epoch**(새 `doc_titles_source_bundle_sha256`)를 만든 뒤 사전 생성부터 pre-T까지 재실행한다. **카탈로그 S는 유지**(Round 3의 same-S 원칙). ledger `h_prime_kind: acquisition-invalidating`, `doc_titles_epoch: k`, 폐기한 번들 sha. T 이후에 수집 결함이 발견되면 H′가 아니라 중단이다: B 이전이면 §9.4의 `X_preB`, B 이후면 Round 3 §5의 X.
- 두 경로 모두 fresh review 0 → `housekeeping_commit` move가 선행한다. 결함 위치가 두 영역에 걸치면 acquisition-invalidating으로 취급한다.

### 9.4 pre-B 중단 `X_preB` (검수 4 P0-2)
상속된 X는 `T < B < X`이고 AC-22가 정책 == B를 요구하므로 T와 B 사이(hidden 생성·검토·봉인 중 포함)에 코퍼스 무효화나 freeze 무효가 발견되면 쓸 종결 상태가 없다. Round 4는 **`X_preB`**를 둔다: `T < X_preB`, B 없음(정책 == T 상태), hidden 생성·평가 0회(이미 생성·봉인된 hidden set이 있으면 봉인 그대로 둔 채 미사용으로 기록, 평문 부재 검사), `round4-final.json` 없음, 변경 파일 ⊆ {`phase3-readiness.md`, `round_outcomes.json`}, readiness "Round 4 aborted before B"에 `reject_reason`(예: acquisition defect after T), 무효가 된 `doc_titles_source_bundle_sha256`·freeze 항목 sha·발견 커밋을 기록, `round_outcomes.json`에 `{"round": 4, "outcome": "aborted-pre-B", "invalidated_by": "X_preB"}` 추가(이 경우 freeze 항목 4가 이미 있으므로 §9.1의 동시 보유 금지는 `aborted-pre-B`에 한해 예외이며, 이후 `pending_round`는 4를 종결로 본다). B 이후에는 기존 `T < B < X`를 그대로 쓴다. AC-R4-09; 시뮬레이션에 합성 X_preB 수명주기 테스트.

### 9.2 Round 4 시작 커밋 (검수 2 P0-1)
Round 3 AC-01a(`round3_start_commit == e16c073`)는 이름 치환으로 상속하지 않고 **치환**한다: `round4_start_commit == 237d2c9`(Round 3 종결 기록 커밋 = 이 스펙 착수 시 main HEAD); `237d2c9 < initial_housekeeping_commit ≤ housekeeping_commit < T < B`(ancestry). H/H′에서 허용되는 diff의 authority는 §2·§13(도구·테스트·문서·`round_outcomes.json`·freeze 키·동결 텍스트만), T에서 허용되는 diff의 authority는 AC-R4-04다. 스펙·계획 문서 커밋은 start 이후 어느 시점이든 허용된다(Round 3 §9와 같음).

Round 3 §9 상속. freeze 키 추가 `doc_titles_source_bundle_sha256`·`doc_titles_snapshot_sha256`·`round_outcomes_sha256`; readiness에 `doc_titles_snapshot`(소스 3개·fetch 시각·URL/페이지 건수·실패 건수·번들 sha·스냅샷 sha·최종 `doc_titles_epoch`·`replaces_bundle_sha256[]`), `concept_lexicon.json.components`에 `doc_titles_snapshot_sha256`(검수 4 P1-2: 이전 epoch의 렌더·raw·review 재사용을 기계적으로 거부), `round4_operational_snapshot`(S), `round2_regression_snapshot`(AC-R3-02 참조 그대로), `reference_set`(Round 2), 종료 분기 D|F|X 또는 "pre-T 미달"(Round 3와 같은 형식).

## 10. Acceptance Criteria (델타)

| ID | 분기 | 판정 | 검증 |
|---|---|---|---|
| AC-R4-01 | 공통 | 문서 제목 코퍼스 provenance: raw 번들(`doc-title-sources/`: 사이트맵·하위 사이트맵 raw bytes, `pages.jsonl`, 페이지 응답 HTML 전체 gzip(내용 주소, sha 정합성 검증), acquisition manifest)이 epoch 안에서 immutable이고 freeze `doc_titles_source_bundle_sha256`과 일치; 스냅샷은 번들에서만 결정적으로 재생성되어 freeze `doc_titles_snapshot_sha256`과 byte-동일(bundle-preserving H′는 번들 재처리·재fetch 금지, acquisition-invalidating H′는 T 이전에만 새 epoch, §9.3); 소스 계약 §5.1 preflight 통과 기록; 번들·스냅샷·렌더 결과·첨부는 seed/hidden 질의에서 유도된 입력을 갖지 않는다(증명은 AC-R4-05의 코드 경로 부재; seed 질의 문자열과의 exact-string 일치 검사는 진단으로만 기록하고 게이트가 아니다 — 검수 2 P1-4) | 테스트(번들→스냅샷 결정성, preflight) + `freeze --round 4` 검증 + ledger + T 이후 스캔 allow 목록에 번들·스냅샷 경로 포함 |
| AC-R4-02 | T | 생성 입력은 카탈로그·코퍼스·동사 키에서만 유도되고 프롬프트에 특정 동의어 예시가 없다; 생성자·검토자는 Round 3 §5와 같이 stateless ChatGPT Temporary chat(개인화 off, 메모리 off)에서 각각 별도 실행; `rendered_sha256`·`doc_titles_attachment_sha256`·템플릿 sha ledger·`components` 기록 | 렌더 결정성 테스트 + ledger(생성·검토 세션 attestation) |
| AC-R4-04 | 공통 | 스코어러 불변: Round 4의 모든 H/H′ 커밋에서 `search.py`·`policy.py`·`search_ranking.json`의 스코어러·상수·격자·`ordering_rules` diff = 0; T에서 허용되는 변경: `search_ranking.json`은 `verb_methods` suffix만, `search_aliases.json`은 `lexicon-r4` 병합만; B..C는 `search_aliases.json`의 `origin=round4` alias만(검수 2 P1-1) | H′마다 `git diff --stat <prev>..<H′> -- 세 파일` 공란 ledger + T 커밋 diff 검사 |
| AC-R4-05 | 공통 | no-benchmark-read: `doc_titles.py`와 생성 입력 렌더 코드 경로는 bench(`search_queries.json`)를 인자·경로·상수 어디서도 받지 않는다 | 테스트(bench 열기를 금지한 monkeypatch 아래 acquire→snapshot→render 전 과정 실행) + 코드 grep |
| AC-R4-06 | pre-T | T 선행 조건: `known_unreachable_seed_count == 0`(§4.1, 튜닝 파이프라인 exact dry-run 기준, 쓰기 없음, 입력 sha·결과 ledger); 미도달 시 `STOP_FOR_AMENDMENT`(비종결); 보조 진단 `reachable_by_grid`·`dry_run_fixed` |
| AC-R4-09 | X_preB | T와 B 사이 중단(§9.4): 정책 == T, B 없음, hidden 평가 0, `round4-final.json` 없음, 변경 파일 ⊆ {readiness, `round_outcomes.json`}, 무효 sha·사유 기록, outcomes `aborted-pre-B`·`invalidated_by` | `--phase pre-T` exit 코드 + ledger |
| AC-R4-07 | 공통 | 라운드 상태 모델(§9.1·§9.2): round 3 freeze 항목 없음·가짜 T 없음, `round_outcomes.json`에 round 3 종결, `pending_round() == 4`, freeze [1,2,4] 허용, `freeze --round N`은 `N == pending_round` + 하위 round 단일 상태, freeze·readiness에 `round_outcomes_sha256`, `round4_start_commit == 237d2c9` ancestry | 테스트 + `freeze --round 4` 가드 |
| AC-R4-08 | 공통 | 코퍼스 소스 계약(§5.1): `DOC_SOURCES` literal, preflight 실패 시 acquire exit 1, prefix 밖 loc 폐기 건수 `discarded_loc_count` manifest 기록, 하위 사이트맵 bytes 보존·sha bind | 테스트 + manifest |
| AC-R4-03 | 공통 | s-027은 "§6 하 미도달(search→filter 불가)"로 readiness에 기록되고 레코드는 불변; pre-T 임계(≥36)는 그대로이되 미도달 seed가 남아 있으면 T를 열지 않는다(AC-R4-06) | readiness + bench sha |
| AC-R3-01..15, AC-18b(R3) | 상속 | 이름 치환으로 그대로(AC-01a는 §9.2로 치환, AC-22는 B 이후에만 적용되고 B 이전은 AC-R4-09) | — |

## 11. 위험과 완화

- 생성기가 코퍼스를 보고도 `workspace`/`release`를 내지 않을 수 있다(Confluence 문서는 "space"라고만 쓴다). 완화: 6.2의 지시문; 그래도 pre-T 미달이면 Round 3처럼 "pre-T 미달"로 종결하거나 어휘 소스를 다시 설계한다(임계·레코드는 불변).
- **B 예비안(조건부, §4.1의 STOP 뒤에만):** s-027처럼 같은 제품의 자원 토큰 동의어(`search→filter`)가 필요한 미도달 seed에 대해 "doc-evidenced same-product synonym" — 요건(검수 1 P1-3): (i) 동의어와 타깃 토큰이 **같은 제목**에 함께 나오는 것만으로는 부족하고, 코퍼스 제목에서 `<synonym> as a <target>` / `<target> (<synonym>)` 류의 **명시적 관계 구문**이거나 stateless 검토자가 동의어로 승인한 것, (ii) `source_product == target_product`, (iii) 고정 코퍼스 provenance(번들 sha), (iv) seed-regression 게이트·fixture 하드 제약 통과. 부작용(`search` alias가 모든 search 질의에 `filter`를 더함)이 크므로 별도 스펙 정정(v1.x)·검수 뒤에만 구현한다.
- 코퍼스 수집 실패/변경: 수집은 epoch당 1회(약 2,435 페이지, 간격 0.25 s → 10여 분, HTML gzip 수십 MB), 실패율 >5 %면 중단·보고(수동 재시도 1회). 사이트맵·제목은 시간에 따라 바뀌므로 raw HTML까지 번들로 보존하고 sha로 고정·archive한다; 추출·정규화·렌더 결함은 같은 번들에서 replay되고(bundle-preserving H′), 수집 단계 결함은 T 이전에만 새 epoch로 처리된다(§9.3).
- ChatGPT 사용량 창·비결정성: Round 3과 같음.
- s-004는 pre-T에서 실패한 채 T로 가며, 튜닝이 `path_unmatched_penalty`로 풀지 못하면 `tuning_accept`(39/39) 실패 → F. 이것은 Round 2·3과 같은 수용 조건이다.

## 12. 한 줄 정의

Round 4 = Round 3의 스코어러·게이트·봉인 절차를 그대로 두고, 어휘 소스에 seed와 무관한 공식 제품 문서 제목 코퍼스를 더해 pre-T 정책이 36/39를 넘게 한 뒤 새 hidden set으로 Discovery 게이트를 재시도하는 라운드.

## 13. 구현 계획 입력

- 도구 H′는 3개 커밋으로: H13 상태 모델(`round_outcomes.json`, `pending_round`·`current_round`·`freeze` 가드, round 4 freeze 키, `round_outcomes_sha256`) ; H14 `doc_titles.py`(소스 계약·acquire·번들·epoch·snapshot·추출·sha 정합성) + 렌더러 + 프롬프트 텍스트 + AC-R4-05 테스트; H15 `round4_simulation.py`(합성 번들, 튜닝 dry-run 게이트, X_preB 수명주기) + round 4 이름 치환(seal/tune/diag). 각각 TDD·canonical suite·`--phase H`·새 리뷰어 findings 0·AC-R4-04 diff 공란.
- 컨트롤러 절차는 Round 3 계획 v16의 Tasks 9–17·21 구조를 round 4 이름으로 재사용하고, Task 9 Step 1 직후 "문서 제목 코퍼스 수집·스냅샷" 단계를, pre-T 뒤에 "미도달 seed 0건" 게이트(§4.1, STOP_FOR_AMENDMENT)를 두며, T~B 사이의 중단은 X_preB(§9.4)로 처리한다.
- 모든 판단·결정은 ChatGPT 검수 스레드에서 논의해 확정한다(사용자 중단 지점은 작업 완료 보고뿐).
