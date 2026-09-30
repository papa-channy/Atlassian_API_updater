# Phase 3 진입 재판정 기록 (readiness)

기준: [Phase 2.5 spec v1.2 §18](superpowers/specs/2026-09-29-phase2.5-discovery-hardening-design.md#18-phase-3-진입-재판정-기준-분리-docsphase3-readinessmd에-기록).
이 문서는 평가 결과를 **기록만** 한다. 벤치마크(`tests/benchmarks/search_queries.json`)의 held_out/negative와
`intelligence/data/search_aliases.json`은 동결 상태이며, 실패 질의의 반영은 §7.3 승격 절차(별도의 후속 변경)로만 한다.

## 판정 요약 (2026-09-30, 1차)

| 축 | 기준 (§18) | 1차 결과 | 판정 |
|---|---|---|---|
| Discovery | held_out top-1 ≥ 90%, negative 실패 0 (실제 캐시) | held_out 6/12 보고 (오염 제외 4/12, 아래 "held_out 오염" 참고), negative 7/8 (실패 1), seed 7/9 | **미충족** |
| Template/validation | createIssue·createPage 픽스처가 jsonschema 경로에서 통과 + 중첩 negative 검출; addAttachment는 required header + multipart hint + content type | createIssue/createPage 통과·negative 검출 OK; addAttachment header/hint OK (본문 모양 이슈, 아래 참고) | 부분 충족 |
| Runtime stability | `search_operations` ≥ 100회 AND ≥ 7일, 검색 로그 활성 | not started | 미시작 |
| Self-update | 시뮬레이션 통합 테스트 존재 | 존재 (`tests/intelligence/test_manager.py`: last-good fallback, reject→accept→reject, swap) | 충족 |

결론: **Phase 3 진입 불가** (Discovery 미충족, Runtime stability 미시작).

## 평가 기록

| 실행일 (UTC) | registry_fingerprint | intelligence_fingerprint | validation_fingerprint | seed | held_out | negative | Runtime stability |
|---|---|---|---|---|---|---|---|
| 2026-09-30T02:47:06Z | `a13ba026ab6b…a793f` | `03ceaedd8732…cb6b4` | `e612a6ceec69…d5066` (jsonschema 4.26.0, transpiler v1) | 7/9 | 6/12 | 7/8 | not started |

전체 값:

- `registry_fingerprint`: `a13ba026ab6b6a3f19845a3aaa694a1e98427220fdbdc74bb711c316730a793f`
- `intelligence_fingerprint`: `03ceaedd8732e03d92f24613f760ec2bf6b9f33947bd78e427105c6ad72cb6b4`
- `validation_fingerprint`: `e612a6ceec69d809646df04effa70bd5d52d11f0ab13bcbdcb55a3d7f2ed5066`
  (`check_request` 1회, `validation_engine = {"engine": "jsonschema", "version": "4.26.0", "oas_transpiler_version": 1, "oas31_strong_validation": false}`)
- source별 spec sha256:
  - jira-platform `2aa6ef12fca713d5b7fc10042e458439ccb3e20eab5d86fd82323f56783f7ab1`
  - jira-software `cb7e24b331ad9b31944fa9a588f70d4ea60d74d1dfb52d39a59770230b79207a`
  - confluence `e4de6c1134a19d8717a309dbb7285a525ae31a9e3c733d046e9e144741f6e313`

재현: `python tests/diag_search_queries.py [--json out.json]` (오프라인, 네트워크 호출 없음, sync는 가짜 `sync_all`로 대체).

### Discovery 실패 질의 (1차, 동결 — 수정하지 않음)

| 집합 | 질의 | 실제 top-1 | 기대 top-1 |
|---|---|---|---|
| seed | `update page content` | `confluence:PUT:/pages/{page-id}/properties/{property-id}` | `confluence:PUT:/pages/{id}` |
| seed | `get issue by key` | `jira-platform:GET:/rest/api/3/issue/{issueIdOrKey}/properties` | `jira-platform:GET:/rest/api/3/issue/{issueIdOrKey}` |
| held_out | `change issue assignee` | `jira-platform:PUT:/rest/api/3/issuetypescheme/{issueTypeSchemeId}` | `jira-platform:PUT:/rest/api/3/issue/{issueIdOrKey}/assignee` |
| held_out | `create a new confluence page in a space` | `confluence:GET:/spaces/{id}/pages` | `confluence:POST:/pages` |
| held_out | `run jql query` | `jira-platform:POST:/rest/api/3/jql/parse` | `GET` 또는 `POST /rest/api/3/search/jql` |
| held_out | `add issue to sprint` | `jira-software:GET:/rest/software/1.0/sprint/{sprintId}/issue` | `jira-software:POST:/rest/agile/1.0/sprint/{sprintId}/issue` |
| held_out | `delete an attachment` | `confluence:DELETE:/attachments/{id}` | `jira-platform:DELETE:/rest/api/3/attachment/{id}` |
| held_out | `get project by key` | `jira-platform:GET:/rest/api/3/projectvalidate/validProjectKey` | `jira-platform:GET:/rest/api/3/project/{projectIdOrKey}` |
| negative | `update issue summary` | `jira-platform:PUT:/rest/api/3/issuetypescheme/{issueTypeSchemeId}` | `jira-platform:PUT:/rest/api/3/issue/{issueIdOrKey}` (금지: `confluence:PUT:/pages/{id}`) |

관찰: seed는 9개 fixture 위 unit test(AC-05)에서는 통과하지만 실제 캐시 942 operations에서는 7/9다.
공통 패턴은 (1) 하위 리소스(`/properties`, `/issuetypescheme`)가 짧은 기본 리소스를 이기는 것,
(2) HTTP 동사 의도(`add`/`create`→POST, `change`/`update`→PUT)가 약하게 반영되는 것, (3) product 힌트
(`confluence`, jira 기본값) 부재다. 다음 단계는 §7.3 승격 절차(실패 질의를 seed로 승격 → alias/점수 조정 →
새 held_out 동결 → 재평가)이며 이 Phase에서는 하지 않는다.

### held_out 오염 공개 (최종 리뷰 I1)

alias `change`→`update`, `post`→`add`, `attach`→`attachment`는 spec §6.1 seed 목록 밖에서 계획 단계에 추가되었고,
이 세 단어는 **seed 질의에는 나오지 않고 held_out 질의에서만** 쓰인다 (`change issue assignee`,
`post a comment on an issue`, `attach a file to a jira ticket`). §7.3.1(alias 작성은 seed와 operationId 어휘만 참고)을
어긴 것이다. 실제 캐시 probe 결과 held_out 통과 6개 중 2개가 이 alias에 의존한다:

- `attach a file to a jira ticket` → alias 있으면 `…/attachments`, 없으면 `POST /expression/evaluate`
- `post a comment on an issue` → alias 있으면 `…/comment`, 없으면 `confluence:GET:/blogposts/{id}/footer-comments`

따라서 **held_out은 6/12로 보고하되, 오염을 제외한 수치는 4/12**다. 판정(미충족)은 바뀌지 않는다.
벤치마크와 alias 파일은 동결 상태이므로 여기서는 기록만 한다.

**소진(consumed) 처리:** 위 세 held_out 질의는 다음 §7.3 승격 라운드에서 held_out으로 재사용하지 않는다.
그 라운드에서 seed로 승격하고, 새로 본 적 없는 held_out 질의 3개로 대체한다. 이후 계획 템플릿에는
"동결 전에 alias 키를 held_out 어휘와 대조한다"는 체크 항목을 둔다.

### Template/validation 상세 (실제 캐시, `check_request`, jsonschema 4.26.0)

| 픽스처 | 결과 |
|---|---|
| `create_issue.json` | `body_check: "jsonschema"`, errors 0; `negative_body` → `body.transition.id` `schema:type` 검출 |
| `create_page.json` | `body_check: "jsonschema"`, errors 0; `negative_body` → `body.title` `schema:type` 검출 |
| `add_attachment.json` | `X-Atlassian-Token` 누락 시 `header.X-Atlassian-Token` `required`(origin `quirk:override`) error; 헤더 제공 시 해당 error 없음; `quirks.request_hints.multipart_fields = [file]`; `file` 필드 없는 본문 → `multipart_field_missing` warning |

addAttachment 주의: 실제 스펙의 multipart request schema가 `type: array`라서 `{"file": ...}` 형태 dict 본문을
jsonschema 경로로 넘기면 `body` `schema:type` ("expected type array") error가 난다. 본문 없이 호출하면
`body_required` error가 난다. §18의 addAttachment 기준(required header + multipart hint + content type)은 충족하지만,
multipart 본문을 JSON 스키마로 검증하는 방식은 Phase 3 전에 다시 볼 항목이다.

**알려진 한계 / Phase 3 사전 과제 (최종 리뷰 I4, 보류 판정):** multipart operation의 스키마가 `type: array`이면
(예: addAttachment) dict 본문으로는 jsonschema 본문 경로를 통과할 수 없고, array 본문은 multipart hint 검사를 건너뛴다.
즉 어떤 본문도 두 검사를 동시에 통과하지 못해 `compatible`이 항상 `false`다. 이번 Phase에서는 코드를 바꾸지 않는다.
Phase 3 전에 form 계열 media type(`multipart/*`, `application/x-www-form-urlencoded`)의 본문 검증 방식을 정한다.

## Spec amendment (v1.2, 미출시이므로 transpiler version은 1 유지)

- §11.2 transpiler rule 5: `oneOf` → `anyOf`로 변환한다. Atlassian의 union 스키마는 가지가 서로 겹쳐서
  `oneOf`의 "정확히 하나" 의미로는 유효한 payload도 거부되기 때문이다. `oas_transpiler_version`은 1 그대로 둔다.
- 알려진 한계: `additionalProperties`/`not` 값 스키마 아래의 `readOnly`는 본문에서 검출하지 않는다 (키는 제거하고
  하위 스키마도 변환하지만 경로를 기록하지 않으므로 `readonly_property_present` 경고도 나오지 않는다). 스키마 오류
  메시지는 제출값을 되풀이하지 않으므로 `anyOf`/`pattern` 실패는 "violates <validator>" 식의 일반 문구로 나온다.

## Search Quality Round 1 — decision record (2026-09-30)

스펙: `docs/superpowers/specs/2026-09-30-search-quality-round1-design.md` v1.4. 절차 A→T→B→T2→C→D (T2: v1.4 재동결, 커밋 B 이후 C 이전).

| 항목 | 값 |
|---|---|
| 커밋 A (강등) | `d15f760` — seed 23 (관찰된 held_out 12 + negative 중 정답 있는 2 포함), regression_negative 6 |
| 커밋 T (테이블 freeze) | `b3c2ba5` — `ranking_structure_sha256 = 8bcd33bb905e3d4946218f05d0edcebe9df6c30060d9de567e88157c820dcf9f` |
| 스냅샷 | T 직후 `$ATLASSIAN_DOCS_ROUND1_CACHE`로 복사; registry_fingerprint `a13ba026ab6b6a3f19845a3aaa694a1e98427220fdbdc74bb711c316730a793f`; spec sha jira-platform `2aa6ef12…`, jira-software `cb7e24b3…`, confluence `e4de6c11…` |
| 생성 프롬프트 sha256 | `14a03d3337ec6b272aa2690327b1cf6e0d7d7c1aaf3e034faa2b42167615d482` (clean context: 새 ChatGPT 대화, generator catalog + 규칙만 제공; seed·실패·정책 미제공) |
| 생성 결과(평문) sha256 | `e6cf5c9c5f9acbaa13b22ff3983c130d4bc27f96e0c1e4b1d433fd4bd002f68f` (repo 밖 보관) |
| 재요청 | 3회 (semantic reviewer 거부 h-008, n-004; 분포 위반 h-008) — 피드백은 "item N rejected; generate a replacement satisfying the original rules"만 |
| 커밋 B (봉인) | `b0cfee2a4866b8e64598f75201152ab658266b50` — held_out 16 sha256 `606535e1…`, negative 8 sha256 `17313dda…` (`round1_seal` 참조) |
| 커밋 T2 (v1.4 재동결) | `26005e4` — `ranking_structure_sha256 = 6b3e79ca4d184b16793fc7fc6c7003733bd2081e35d951af21703c2c407a4de2` (`resource_match_bonus` 추가) |
| 커밋 C (freeze) | `d862e011aaf9711b585201479e886264ed197e52` |
| `evaluation_code_sha256` (C) | `48381df69f6f37cb5f4c43ff4951c41671c26e2793e25b2147dd737a6b7cee88` (`tests/benchmarks/evaluator.py::evaluation_code_sha256`, spec §5.7) |
| 커밋 D (봉인 해제·최종 평가) | `ff173120d53de0faa0a17ba188b56903b3a25283` |

Attestation(컨트롤러): 봉인 평문 경로는 어떤 구현·튜닝 서브에이전트에도 전달하지 않았다. machine check 0 violation. 의미 검증은 seed 파일과 scorer를 보지 않은 별도 reviewer가 수행.

### Round 1 상태 모델 (spec v1.4 §11)

- **Round 1 DoD**: AC-01..AC-16 자동 항목 통과 + 아래 attestation 기록 + 커밋 D 존재 → "Round 1 completed"
  (gate 결과와 무관). 상태: **completed** (커밋 D `ff173120d…`; attestation은 아래 "Attestation (컨트롤러)" 참고).
- **Discovery gate** (spec §5.9): 봉인 held_out 16건 중 ≥ 15 통과, 봉인 negative 8건 실패 0
  (`regression_negative`는 gate 제외). 판정: **failed** (held_out 4/16, negative 5/8) → "Round 1 completed, gate failed → Round 2".
  상세는 아래 "Round 1 2차 평가 (커밋 D…)" 참고.

#### 평가 기록 2차 행 (최종 평가, `tests/benchmarks/round1-final.json`)

값은 아래 "Round 1 2차 평가 (커밋 D, 2026-09-30T12:50:39Z…)" 표와 동일하다 (날짜, 커밋 A/T/B/T2/C/D,
`evaluation_code_sha256`, `round1_seal`, registry/intelligence fingerprint, ranking/ranking_structure/alias sha,
seed 23/23, regression_negative 6/6, held_out 4/16, negative 5/8, gate failed) — 중복 기입에 의한 불일치를 피하기 위해
그 섹션을 단일 출처로 삼는다.

#### Attestation (컨트롤러 서명 항목)

- 생성 프롬프트 sha256 / 생성 결과 sha256: 위 decision record 표.
- 재요청 횟수와 피드백 형식 준수: 위 decision record 표.
- 최종 평가 1회 실행 / 튜닝 로그 완전성 / 서브에이전트에 봉인 평문 경로 미노출: 아래 "Round 1 2차 평가 (커밋 D…)" 섹션의
  "Attestation (컨트롤러)"에 기록 (커밋 C 체크아웃, 스냅샷 캐시로 정확히 1회 실행·재튜닝 없음; 튜닝 로그는 모든 실행을 기록;
  봉인 평문 경로는 서브에이전트에 미노출).

### Round 1 2차 평가 (커밋 D, 2026-09-30T12:50:39Z, 커밋 C 체크아웃, 스냅샷 캐시, 단 1회)

| 항목 | 값 |
|---|---|
| git_commit (C) | `d862e011aaf9711b585201479e886264ed197e52` |
| registry_fingerprint | `a13ba026ab6b6a3f19845a3aaa694a1e98427220fdbdc74bb711c316730a793f` (= round1_seal) |
| intelligence_fingerprint | `f3c071c4d952f9144eb0cdbfdad5072b042c528a29c625b1289b4f85516adbe0` |
| ranking_sha256 / ranking_structure_sha256 | `e70cacb5…eda7df` / `6b3e79ca…4de2` (T2) |
| alias_sha256 | `c430e961…55be3` |
| evaluation_code_sha256 | `48381df6…cee88` (= C 기록) |
| sealed_sha256 | held_out `606535e1…`, negative `17313dda…` (= round1_seal) |
| seed / regression_negative | 23/23 / 6/6 |
| **held_out (봉인)** | **4/16** (기준 ≥ 15) |
| **negative (봉인)** | **5/8** (기준 실패 0) |
| **Discovery gate** | **failed** |
| Round 1 DoD | completed (AC 자동 항목 통과, 커밋 D 존재; 아래 attestation) |
| 상태 | **Round 1 completed, gate failed → Round 2 필요** |

결과 artifact: `tests/benchmarks/round1-final.json`. 이번 라운드에서 재튜닝 커밋은 없다(§5.8).

#### held_out/negative 실패 목록 (이제 관찰된 집합 — 다음 라운드에서 §5.2와 같이 강등)

| id | 질의 | 실제 top-1 | 기대/금지 |
|---|---|---|---|
| h-001 | leave feedback on this jira ticket | POST /rest/api/3/issue | POST …/issue/{k}/comment |
| h-003 | revise project configuration details | GET …/project/{k}/roledetails | PUT …/project/{k} |
| h-004 | show my starred searches | GET …/workflows/search | GET …/filter/favourite |
| h-005 | publish a new project release | GET …/project/{k} | POST …/version |
| h-006 | discard this uploaded ticket file | GET …/issue/{k} | DELETE …/attachment/{id} |
| h-007 | show time entries for ticket | GET …/issue/{k} | GET …/issue/{k}/worklog |
| h-008 | set up a jira planning board | PUT …/board/{id}/properties/{key} | POST …/board |
| h-009 | revise dates for this iteration | (결과 없음) | PUT …/sprint/{id} |
| h-013 | rewrite this wiki blog entry | GET /blogposts | PUT /blogposts/{id} |
| h-014 | trash this confluence wiki page | GET /pages | DELETE /pages/{id} |
| h-015 | show files attached to this page | GET /pages | GET /pages/{id}/attachments |
| h-016 | browse pages inside this workspace | GET /pages | GET /spaces/{id}/pages |
| n-004 | confluence label printer | GET /labels (금지) | — |
| n-006 | site access emails | POST /user/access/check-access-by-email (금지) | — |
| n-008 | filter owner jira | PUT …/filter/{id}/owner (금지) | — |

#### 원인 분류 (Round 2 입력; 튜닝 근거가 아니라 기록)

- **R5 동사 어휘 부재**: `leave feedback`, `revise`, `discard`, `rewrite`, `trash`, `publish`, `browse`, `set up`이 `verb_methods`에 없어 메서드 의도가 0이고, 같은 리소스의 GET/POST/PUT/DELETE가 동점(h-001, h-005, h-006, h-013, h-014).
- **R6 하위 리소스 개념어 부재**: `feedback→comment`, `time entries→worklog`, `files attached→attachments`, `starred→favourite`, `release→version`, `iteration→sprint`, `workspace→space`, `uploaded file→attachment`가 어휘로 연결되지 않아 터미널 리소스 보너스가 **기본 리소스**(`issue`, `pages`)에 붙는다(h-001, h-006, h-007, h-015, h-016). 터미널 리소스 보너스는 R1을 고쳤지만 질의가 하위 리소스를 다른 단어로 부를 때는 역효과다.
- **R7 완전 무매칭**: h-009는 어휘 히트가 0이라 결과가 없다.
- **negative**: 명사만 있는 질의에서 유인 오답이 실제로 1위로 온다(n-004, n-006, n-008) — 구조 신호는 명사형 질의를 구별하지 못한다.
- **schema-name 순위 하락**: 질의 `IssueCreateMetadata`에서 deprecated된 createmeta op가 2위에서 4위로 밀렸다.
  `issue` 토큰을 포함한 질의에서 `/issue` 하위 경로들이 resource-match 보너스(+10)를 받기 때문이다. `test_exact_schema_name`은
  고정 상수에 pinned되어 있다. Round 2는 joined-form/schema-name 질의를 구조 신호에서 면제할지 결정해야 한다.
- **resource-match 보너스 쏠림**: 실패한 top-1 15건 중 10건이 `resource_match = +10`을 받았다.
- **Round 2 carry-forward (테스트)**: `TestFinalArtifact`(test_evaluator.py:253-277)는 `evaluation_code_sha256`을 HEAD
  트리와 비교하고 평문 r1 섹션 존재를 요구하며, `RANKING_STRUCTURE_SHA256`(test_evaluator.py:80)은 하드코딩된 값이고,
  diag default-sets 테스트(`tests/test_diag_search_queries.py`)는 번들 벤치가 평문이라고 가정한다. Round 2는 이 값들을
  커밋 C 기준 해시와 비교하도록 바꾸고, 재봉인 전에 테스트를 상태 독립적으로 만들어야 한다.

#### Attestation (컨트롤러)

- 최종 평가는 커밋 C 체크아웃에서 스냅샷 캐시로 정확히 1회 실행했고, 결과와 무관하게 재튜닝하지 않았다.
- 봉인 평문 경로(`$ATLASSIAN_DOCS_SEALED_BENCH`)는 어떤 구현·튜닝 서브에이전트에도 전달하지 않았다. 스냅샷 경로는 공유했다.
- 생성 프롬프트 sha256 `14a03d33…`, 평문 sha256 `e6cf5c9c…`, 재요청 3회(피드백은 "item N rejected; generate a replacement satisfying the original rules"만).
- 튜닝 로그(`tests/benchmarks/search-tuning-round1.jsonl`)의 모든 실행이 기록되어 있다(dry-run 1회는 초기 스크립트 결함으로 기록됨; 이후 dry-run은 기록하지 않음). 채택된(adopted) 튜닝 로그 라인(4번째 줄, git_commit `d876188`)은 `bench_sha256`/`dirty` 필드가 추가되기 전(`26aced2`) 기록이며, 그 실행 당시 s-008 벤치마크 수정이 아직 커밋되지 않은 트리에서 돌았다(이후 `34948d8`에서 상수와 함께 커밋됨).
- 의미 검증(semantic review)은 내부 카탈로그만 제공받은 새 reviewer 서브에이전트가 수행했고, 컨트롤러는 그 검증 단계와 커밋 D 시점 모두에서 봉인 평문을 열람했다.
- **v1.4 설계 변경(터미널 리소스 보너스, 커밋 T2)은 봉인 이후에 이루어졌다.** 유도 근거는 seed 실패 s-005/s-006/s-019/s-022/s-011의 top-5 분석뿐이며, 봉인 집합의 어떤 질의도 설계나 튜닝에 사용하지 않았다. 다만 컨트롤러는 의미 검증 단계와 D 시점에 평문을 열람했으므로 독립성 근거는 "절차상" 수준이다.

#### 커밋 D 직후 발견된 테스트 결함

`tests/test_diag_search_queries.py::test_default_sets_skip_sealed_sections`는 번들 벤치마크 파일이 봉인 상태라고 가정해 D 이후 실패한다(테스트 자체가 파일 상태에 의존). C..D whitelist상 D에서는 테스트 코드를 고칠 수 없으므로, D 다음 커밋에서 임시 봉인 벤치를 만들어 검사하도록 고친다.
