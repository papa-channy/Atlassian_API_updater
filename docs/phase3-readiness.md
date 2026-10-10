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

### Round 2 pre-work (2026-09-30)

- **관찰된 숨김 집합 강등** (`902b447`): `held_out` h-001..h-016 → `seed` s-024..s-039, `negative` n-001..n-008 → `regression_negative` rn-007..rn-014 (순서 유지, origin `held_out-r1`/`negative-r1` 유지). `held_out`/`negative`는 `[]`, `round1_seal`은 변경 없음. seed 39 / regression_negative 14. 픽스처 평가(`TestSeedBenchmark`)는 r0 origin 레코드만(23/23, 6/6) 대상으로 하고, r1 레코드의 키는 `ATLASSIAN_DOCS_ROUND1_CACHE`가 `round1_seal`과 지문이 같은 스냅샷을 가리킬 때만 실제 레지스트리에서 검사한다(아니면 스키마만 검사하고 사유 출력).
- **라운드 독립 테스트** (`8f5078c`): `TestFinalArtifact`(`round1_seal`과의 내부 일관성만 검사; 현재 트리의 평가 코드 해시 비교와 평문 r1 섹션 요구는 D 전용이므로 제거), `RANKING_STRUCTURE_SHA256` → `tests/benchmarks/round_freeze.json`(`test_evaluator`·`test_policy`가 파일을 읽음), 정책 어휘 출처 검사(seed 단어는 all seed records (r0+r1)에서; 예외 목록은 `{"epic","find","read","rename"}`로 축소), 튜너 총계 테스트(번들 벤치 길이와 비교), `tests/test_diag_search_queries.py`(r0 레코드로 자체 벤치를 만들고 평문/봉인 숨김 섹션도 자체 생성 — 위 "커밋 D 직후 발견된 테스트 결함" 해소).
- **policy 로더 수정** (`8ef0faf`): `verb_methods`/`product_hints`/`path_noise`/`tuning_grid`의 잘못된 원소(비문자열, 중첩 리스트)는 `TypeError`가 아니라 `ValueError`; 키 정규식은 `fullmatch`(`"get\n"` 거부); 상수 키 오류 메시지는 `len(CONSTANT_KEYS)`(6)에서 파생.
- **저장소 밖 Round 1 파일 보관**: `~/.atlassian_api_updater/archive/round1/`에 봉인 평문(`sealed/round1-sealed.json`), 내부 카탈로그(`sealed/round1-internal-catalog.json`), 생성 프롬프트(`sealed/round1-generation-prompt.txt`), 캐시 스냅샷(`round1-cache/`). Round 2는 새 숨김 집합으로 A→T→B→C→D를 다시 수행한다.

## Search Quality Round 2 — decision record (2026-10-03)

**Outcome: F — tuning failed (spec v1.14 §5.5 / AC-21).** The one-way pipeline found no constants × alias combination that passes the snapshot seed set (39/39) and the regression negatives (14/14); the policy files stay at B, the hidden set was never evaluated or decrypted. Status: **Round 2 tuning failed** (Round 2 completed, Discovery gate not attempted) → Round 3 with a new hidden set.

### Provenance

| item | value |
|---|---|
| housekeeping_commit | 2edad7b (branch `round2`, H1..H7 + H′ wave; whole-branch code review before S) |
| spec | v1.14; plan v10.1 |
| S (source snapshot) | `~/.atlassian_api_updater/round2-cache/`, registry_fingerprint `f3c2e9d48aa85c96ca62cdd84ff700cc2714c888cf4148b3a91c604c45b47b62`, 943 operations |
| spec_sha256 | confluence `b3d010b6438677d8…`; jira-platform `3d0edfb02ff91873…`; jira-software `cb7e24b331ad9b31…` |
| verb inventory | spec §6 verbatim, 101 verbs (Round 1: 23); REVIEW lines replace, share, transition, trash, unwatch, update → no-widen; fixture-compatibility check OK; `verb_inventory_sha256` `d66317db7a6a3d047f30197791eefdb93448747b913544da7545136f91dbffc0` |
| method-safety | 1 pass, 0 violations, artifact sha `0a8de4fe9182d1a2a70150d8e87e3f2b4af69e7f7e037c15421e390b05654778` |
| lexicon template / generation input | `a5b7808fe6f3ac4da99f81173ac7ac8deae8c22d02f2854ac5c8c201617a577d` / `9125fa8444453762076cdb5c6791f166f46a15579fd016bfcbb8cd4412bd857e` (286 concept tokens) |
| lexicon raw / review input / review output | `acc5cebeafc5c48236a9de5d685b888fb2a83532340405556d77b801468a6872` (584 synonyms, 1 attempt) / `17efa0b87647cf89357fffe3c2aaf2f0effb24539ce1c44b399a0a574eb3a484` / `c5ba256f8acd082febe06724d6646bff631e136dc437f4fa1528286117bd62f4` (1 attempt) |
| lexicon counts | structural kept 524 / rejected 57 {'in_catalog': 42, 'verb': 11, 'function_word': 2, 'id_like': 1, 'alias_conflict': 1}; semantic rejected 56; seed gate rejected ['feedback', 'fresh', 'iteration', 'new', 'release', 'summary']; merged 462 `lexicon-r2` aliases, skipped [] |
| concept_lexicon.json / aliases sha | `352b5921201d97de55e75ddbcbe6e048650168b89fcfa3d4c2939e442dd4e3df` / lexicon_aliases `6eb9d7b6ca9f90a8984fb0d4c11aede406a9d3f350df4e977171c910c2c74c29` |
| candidates / R5 / R6 | 22 candidates (51 excluded), seeds with R5: 5, with R6: 18; alias_candidates sha `2e4aa64bb5a74b6b120b7ed737f9cdc577e8116bd810f7b785b2c4ce23bd7ef6` |
| AC-13 replay | ok (lexicon, merge, candidates, classification reproduced from committed inputs) |
| T | `29dba388fe5c9521a7a91ce68ee8f152ed94ffca` — suite OK (exit 0, output sha `59f073a97f126d90…`) |
| structure / tooling / evaluation shas at T | `8106c8918b8271957f157fafcb1efdf83e0d7e14a17723afbeb8d0f00660c49b` / `5accdeaa15699d1e884e903172627efdb3e324a1393381e6cbf571ae3aebbdd6` / `974c0e54d2d7b7d9c097cc38abcdb9b21285cb8ec8b14f307940d689555d77a6` |
| hidden generation | input `3c702962513e834c80220d03e4dc1c83cd633b5e96a89a9a2161ccacc79e7ba0`; attempt 1 output `4b868ca87ead72ae369df502b46487fbf105ada25be6e6141617afe096f5b7be` status valid; machine check 0 violations; re-requests: 0 machine, 1 reviewer |
| hidden review | attempt 2: message `50b413e156e3abf99f096fb18dde6b81b569de7ee02b9b545d984c6eaeedf104` + catalog `b22de253515c88ac40f1c7672f36c3bdd4b9dc2f050080601565bc05ed51b282` (attached JSON lines, see deviation) → output `5a30746ae26a5b93575a817225c795251debd63450d65b09ec31c54c6af3312f` (23 accept, reject h-009); attempt 3 replacement h-009 (rule `reviewer`) output `86fe08b95bf35bee6173be47c179704e1f38840e6eed2a7576bf4c570dfc2b99` valid, machine check 0; attempt 4 review of h-009 → accept (`5a863a15977a99850fd720f7f92c165b91155612b14b0a9ca0bf469dba26454b`) |
| coverage manifest | `ffa9d7ae3dfe7d424cdf85020b06c41bc66a2534a4a663349f98d8b03761b2b2`, verify_coverage [] |
| temporary_chat_unpersonalized | true (generation + both reviews; UI-state screenshots in round2-work/) |
| B | `4fc5fe7c676a81c96aa3b3c34c72fa10461413fb` — sealed held_out `0f990f2fc134cd41eca2061931c65cfdd4bc21819051f9ae8538c0258aaf3540`, negative `7750a2020923bcf8ddfa22e79f2c071001db9942194c3215cc03c60f363dde76`; suite OK (exit 0) |
| .enc sha at B / at F | `c1a3794b0ac7563bee0ccdcc61e0ecb43026d0f778ec4773ef2695459cca369b` / `c1a3794b0ac7563bee0ccdcc61e0ecb43026d0f778ec4773ef2695459cca369b` (equal: True; plaintext absent; passphrase held by the user only) |
| worker brief | `15be63e6fc7e1cf4e054f330c40a37b8581f92046f6143d3efb0aefdcb9c0fcf` (== freeze); runs: 1; replies: run the brief procedure |
| tuning run | run_id `8127f83d-97d0-4eab-890c-fd7c55a18c63`, status `failed`, seed 34/39, regression_negative 10/14, passing_combos 0, result_sha256 `f8743eda516e06d83d1b9658b7b9c8dc1155fac90cd95d77e16cabbe64c46329`, commit `15653ebcb591ec22addd6e60c624080479c3c906` (log only) |
| C / D / decryption / round2-final / held_out result | not_applicable (tuning failure) |
| policy at F | aliases canonical `20d94582413d6587ab2c68fa1c67552ea10fbbe931c1a77eb34a71e4dff55918`, ranking canonical `3648e860a0ef8739d92bd1d88e305f46f7cbefb0dbc01230d95eaf6fbae8d555` — identical to B (worker commit touched only the log) |
| terminal_commit | self (F; sha recorded in the ledger and the provenance report after the commit) |

### Deviations ledgered

- The hidden reviewer input materialized to 701,725 chars (catalog descriptions 462 KB), beyond a ChatGPT message; the frozen prompt and the records were sent inline and the catalog as an attached JSON-lines file with identical bytes (event `hidden_review_input_split`).
- AC-13 replay restores the pre-classification bench for the lexicon stage (plan v10.1).
- The ChatGPT personalization toggle had to be switched to "개인화되지 않음" by the user; it persisted across the Temporary chats used.

### State model

| field | value |
|---|---|
| branch | F |
| adopted_runs | 0 |
| rejected_runs | 0 |
| failed_runs | 1 |
| hidden_evaluated | false |
| ciphertext_retained | true |
| round3_required | true |

### Attestation (spec §12)

- AC-01a/b/c: H..T..B..F commits touch only the allowed files; no policy change after B. AC-05: tooling diff H..F empty, `tooling_code_sha256` unchanged. AC-18a-B/F: ciphertext sha unchanged, no plaintext. AC-21: tuning failure ends the round at B policy. AC-23: suite green at T and B (ledgered). AC-07/14/16: apply on branch F and pass (no evaluation ran; no policy or evaluator change after B; ciphertext retained). **AC-18b: FAIL** — the post-terminal provenance review found that four working files under `~/.atlassian_api_updater/round2-work/` (the hidden-review inputs, the replacement output and the replacement-review message) held the hidden records in plaintext from before B through F, readable by the worker's account; they were never handed to the worker and the tuning run depends only on the B inputs and the frozen tooling (unchanged H..F), so the F result is unaffected, but the spec's claim that the plaintext was unreadable during tuning does not hold for Round 2. Remediation: the four files were deleted after F (`ac18b_finding_remediated` event, shas ledgered); Round 3 rule: review inputs that embed the records must be deleted or encrypted before B. Controller evidence: `~/.atlassian_api_updater/round2-work/{controller-events,attempts}.jsonl`.

## Search Quality Round 3 — decision record (2026-10-07)

**Outcome: closed before T — the binding pre-T checkpoint (AC-R3-01, seed ≥ 36/39) was not reached.** No T, B, hidden set, tuning run or gate evaluation exists for Round 3; the Round 2 reference set was never decrypted. Status: **Round 3 pre-T not reached** (Discovery gate not attempted) → Round 4 brainstorming. Spec v1.25.1 (`0741e34`), plan v16. Evaluation domain: actionable recommendation queries.

| item | value |
|---|---|
| round3_start_commit | `e16c073` |
| initial_housekeeping_commit | `10473ad` (H′ of the Task 8 review) |
| housekeeping_commit (final) | `9bf823d` (design-extension H′ series, below) |
| controller_actor_id / session | `42e25099-9d61-4b2a-b9f5-db24bf29e3ba` (fresh session, never saw Round 2 plaintext) |
| round3_operational_snapshot (S) | live fetch 2026-10-05, `s_reused_from_round2: false`, registry `a759181ca5511d5ccd6115461e6c22b62cc96627cdea6af7e6741c8b77d07a49`, confluence `b3d010b6438677d8…`, jira-platform `e1f7bdb40cb38c15…` (changed vs Round 2), jira-software `cb7e24b331ad9b31…`, 943 ops |
| round2_regression_snapshot | `29dba38`, `f3c2e9d4…` (AC-R3-02 reference `tests/benchmarks/round3-regression-reference.json`, compared in legacy ordering mode) |
| verb inventory | unchanged (`d66317db…`), method-safety 39 rows / 0 violations, prefix ok, 26 REVIEW verbs no-widen |
| lexicon | stage (a) archive re-gate (feedback→comment, iteration→sprint) + stage (b) Round 3 stateless generation ×2 (see attempts); last union: 239 kept (21 words, 218 phrase rules), seed gate rejected fresh/new/release/summary, seed-regression rejected 0 — **left uncommitted and discarded at close** (copies: `round3-work/final-uncommitted/`) |
| T / B / C / D / F / X | none |
| hidden set, needle manifest, ciphertext | none (AC-18 scans not applicable) |
| reference_round2 | not decrypted |

### Design-extension H′ series (spec §8, §15; each reviewed by a fresh reviewer, findings 0 after fixes)

| pointer move | reason | review |
|---|---|---|
| 10473ad → dca5b9c | post-S H prime: concept_lexicon_check.validate_review required exact key equality, refusing the… | findings 0 |
| dca5b9c → c1d91d7 | design-extension H prime (spec v1.24/v1.24.1): H9 37187cb ordering_rules (intent tier, preferre… | findings 0 |
| c1d91d7 → e4084ab | design-extension H prime (spec v1.24.2): H10 51a6420 lexicon phrase rules/union/renderer/prompt… | findings 0 |
| e4084ab → 15047bf | design-extension H prime H11 15047bf: synthetic T merges a lexicon-r3 phrase rule (final housek… | findings 0 |
| 15047bf → 9bf823d | design-extension H prime (spec v1.25/v1.25.1): H12 5c609d9 natural-order phrase keys, in_catalo… | findings 0 |

Commits: H9 `37187cb` + H9′ `c1d91d7` (ordering_rules: intent tier, preferred-method tie-break, terminal-alias full weight; legacy mode; identifier-query exemption), H10 `51a6420` + H10′ `e4084ab` (lexicon phrase→`when_all` rules, union inputs, grounded generation-input renderer, Round 3 lexicon prompts), H11 `15047bf` (simulation), H12 `5c609d9` + H12′ `9bf823d` (natural-order phrase keys, `in_catalog` cross-product exception, `seed-regression` gate). Clean-worktree canonical suite at `9bf823d`: 555 OK; `--phase H` ALL STEPS PASS. In the pre-T window the working-tree suite showed exactly the 3 freeze-dependent tests (expected until T).

### Binding pre-T checkpoints (`round3_simulation --phase pre-T`, real S)

| at | seed | regression raw · effective | fixture failing | equivalence mismatches | verdict |
|---|---|---|---|---|---|
| 2026-10-05T13:31:19Z | 31/39 | 10/14 · 14/14 | [] | [] | fail |
| 2026-10-07T02:22:02Z | 33/39 | 10/14 · 14/14 | [] | [] | fail |
| 2026-10-07T02:23:46Z | 33/39 | 10/14 · 14/14 | [] | [] | fail |
| 2026-10-07T03:28:59Z | 35/39 | 10/14 · 14/14 | [] | [] | fail |

Rules-only diagnostic (scratch, after H9): 34/39. Final failing seeds: s-004 (intent-tier side effect; constants domain), s-027 (literal `my` terminal match), s-028 (`release→version` never generated), s-039 (`workspace→space` never generated). Root finding (spec §0/§15 v1.24): the v1.23 figure 36/39 was a post-tuning simulation value; the pre-T policy ranks like the Round 2 baseline (31/39) by AC-R3-02.

### Lexicon generation / review attempts (ChatGPT Temporary chat, personalization off; inputs attached byte-exact, outputs checksum-verified)

| stage | actor_id | input sha | output sha | transport/parse/valid |
|---|---|---|---|---|
| lexicon-generation-r3 (run 1) | `6ac5a8b6-35a8-83e8-b910-8a8d19f0ade1` | a8fb621a851b… | 957133966913… | ok/ok/ok |
| lexicon-review-r3 (run 1) | `6ac5aa98-6124-83ec-bde5-1fd3b34108d6` | 8b3b867784db… | 43c7af333763… | ok/ok/ok |
| lexicon-generation-r3 (run 2) | `6ac5b8f8-a488-83ec-8f52-d4ec497992e8` | a8fb621a851b… | b34f81d88774… | ok/ok/ok |
| lexicon-review-r3 (run 2) | `6ac5ba74-c698-83ec-aaaa-33baedfe75b1` | d3a09ea2561a… | 18227e1d81ed… | ok/ok/ok |

Generator ≠ reviewer in both runs (`actor_separation_check_lexicon`). No hidden records were ever created, so no plaintext hygiene step applied.

### Evidence

`~/.atlassian_api_updater/round3-work/controller-events.jsonl` sha256 `c07e586d39dd3e27d519c3be14dab3637f00fe678902de747a37e80e91e9ec5b`, `attempts.jsonl` `a1fdd809cdb2cbbd629d57b2bbb8b386f3e0e1906330005bd53d6b4ead074c76`; review reports `h9-review.md` `d3dbf6229c9bfcbb…`, `h9b-review.md` `40fd039eb0433832…`, `h10-review.md` `10d6728c467e0f00…`, `h10b-review.md` `8c0c5d5db0ee1c59…`, `h11-review.md` `06352eca52aa547e…`, `h12-review.md` `38f3ea1878e7ef27…`, `h12b-review.md` `ca2d14d3a0458cae…`. Archived with S under `~/.atlassian_api_updater/archive/round3/`.

### Attestation (spec v1.25.1 §10)

- AC-01a: `e16c073 < 10473ad ≤ 9bf823d`; no T. AC-05/AC-R3-13a: `TOOLING_FILES`, `search.py`, `policy.py` changed only in the reviewed H′ commits; `policy.py` diff limited to the six declared kinds (test). AC-R3-02: legacy-mode equivalence with the Round 2 reference holds (suite). AC-R3-12: verb inventory unchanged. AC-R3-13b: grid unchanged. AC-R3-14: ordering rules flag-gated, structure committed at H. AC-R3-15: stateless generation/review with actor separation, union provenance, replay ok (run 2).
- Not attempted (no T): AC-01b, AC-02–04, AC-06b, AC-07, AC-08 freeze comparison, AC-10–12, AC-15, AC-19–23, AC-R3-01 (failed: 31 → 33 → 35 of 39), AC-R3-06–11, AC-18b(R3).
- Branch: none of D/F/X (`adopted_runs 0`, `failed_runs 0`, `rejected_runs 0`, `hidden_evaluated false`, `ciphertext_retained n/a`).

### Lessons for Round 4

1. Thresholds must be stated for the policy state they are measured on (pre-tuning vs post-tuning).
2. A stateless reviewer judges what it sees: canonical identity (sorted token sets) and display (natural order) must be separated.
3. Vocabulary-eligibility gates need a ranking-effect check (`seed-regression`), not only vocabulary membership.
4. The generator avoids catalog tokens, so cross-product synonyms (`workspace→space`) need an explicit allowance in the prompt or a different source.
5. Residual structural cases: literal determiner terminals (`/filter/my`), the intent-tier side effect on multi-op expected sets (s-004).

## Search Quality Round 4 — decision record (2026-10-09)

**Outcome: closed before T — the binding pre-T gate (spec v1.13 §4.1: AC-R3-01 seed ≥ 36/39 ∧ `pre_t_blockers == []`) was not reached.** Terminal branch `pre-T-not-reached` (user decision 2026-10-09 after the review-thread ruling). No T, B, hidden set, tuning run or gate evaluation exists for Round 4; the Round 2 reference set was never decrypted. Next: **Round 5** (registered as the pending round at closure). Spec v1.13 (`6f99ae7`), plan v7.

| item | value |
|---|---|
| round4_start_commit | `237d2c9` |
| initial_housekeeping_commit | `e804252` (H15‴, after the whole-branch review fix pass) |
| housekeeping_commit (final) | `d4b7435` (H′, bundle-preserving; below) |
| controller_actor_id / session | `42e25099-9d61-4b2a-b9f5-db24bf29e3ba` |
| round4_operational_snapshot (S) | live fetch 2026-10-08T20:23Z, `s_reused_from_round3: false`, registry `d69b9ca6e6f106939d5f9d19515365df05006652d659ce7b8169cf8b6b24e882`, confluence `b3d010b6438677d8…`, jira-platform `8ee2e0bbe2553e3e…` (changed vs Round 3), jira-software `cb7e24b331ad9b31…`, 943 ops |
| verb inventory | unchanged (`d66317db…`), method-safety 0 violations, prefix ok, REVIEW verbs transition/trash/unwatch/update no-widen |
| doc_titles_snapshot | epoch 1; sitemaps jira-cloud.xml / confluence-cloud.xml / jira-cloud-administration.xml; url 645 / 457 / 258, page_failed 0 / 1 / 0; bundle `44f3378684201473d6267dd6f0296bb8babf904dc120320d594ed569d9de14fe`; snapshot `2d3caa6e02e0a67c523940add30e083cac415564302deb7e51a832ead50e6453` (1,359 titles); `replaces_bundle_sha256: []` |
| lexicon | union (Round 2 archive + Round 4 generation with DOCUMENTATION TITLES): structural 481 kept, final 345 kept → seed gate rejected fresh/new/release/space/summary → 340 entries; lexicon-r4 merge 19 words + 321 phrase rules; `components.doc_titles_snapshot_sha256` = snapshot above; AC-13 replay ok (generation input re-render identical) — **left uncommitted and discarded at close** (copies: `round4-work/final-uncommitted/`) |
| t_policy_files / round_outcomes_sha256 at T / round_recoveries_sha256_at_T | none (no T) |
| round_outcomes_sha256_after_append | `e0913e3d38f60299507ceb90f27e91be3d648e3fed16c8cfe9b6386cec9b7fdc` |
| T / B / C / D / F / X / X_preB | none |
| hidden set, needle manifest, ciphertext | none (cleanup scans not applicable) |

### H′ during the controller run

| pointer move | kind | reason | review |
|---|---|---|---|
| e804252 → d4b7435 | bundle-preserving | the real pre-T run crashed: the event hashed the loaded policy's read-only `tuning_grid` (mapping proxy); `pipeline_input_sha256` now hashes the raw JSON grid (TDD) | fresh reviewer, findings 0 (2 minors deferred) |

Tooling commits: H13 `0f7d716`, H14 `da9ab8c`, H15 `5417993`, H15′ `1cff453`, H15″ `11df50d`, H15‴ `e804252` (whole-branch review: Critical 0, Important 5 fixed, Minor 10 deferred), H′ `d4b7435`.

### Binding pre-T checkpoint (`round4_simulation --phase pre-T`, real S)

| at | seed | regression raw · effective | fixture failing | equivalence | dry-run tuning_accept | blockers | verdict |
|---|---|---|---|---|---|---|---|
| 2026-10-08T22:00:39Z | 35/39 | 10/14 · 14/14 | [] | [] | false (validation_errors []) | unreachable_seed [s-004, s-027, s-028, s-039]; inherited_ac_r3_01_failure | stop_for_amendment |

`pipeline_input_sha256` `66ee65745963fc6b…`, `pipeline_result_sha256` `a261cdf867f14862…`. Per-seed cause: s-004 constants domain (bulk transition ranks first); s-027 §6 known-unreachable (search→filter, same-product token); **s-028: the Round 4 generator proposed release→version, but the union keeps the first (archive) entry release→build, which the seed gate rejected — the correct synonym never reached the gate**; s-039: workspace→space was not generated (the titles say "space").

STOP ruling (review thread 2): (a) §11 B rejected for Round 4 (fixes s-027 only; tuning_accept stays false); (b) union precedence fix adopted as a Round 5 design input only; (c) `TERMINAL_PRE_T_NOT_REACHED` adopted → user decision.

### Lexicon attempts (ChatGPT Temporary chat, personalization off; attachments + byte-exact body; outputs checksum-verified)

| stage | actor_id | input sha | output sha | transport/parse/valid |
|---|---|---|---|---|
| lexicon-generation-r4 (two attachments) | `6ac806e9-e77c-83ee-af34-32be7838d3aa` | 6bfacc2589ab… | 929e996ea4b6… | ok/ok/ok (571 keys) |
| lexicon-review-r4 | `6ac80af3-31c8-83e8-95e0-cfe048c72d1c` | 8da851f5f008… | 308e115be3d9… | ok/ok/ok (481/481 bool) |

### Evidence

`~/.atlassian_api_updater/archive/round4/round4-work/controller-events.jsonl` sha256 `6e4d391d309d98398790c4171f1990937e35094550217ea31029a6cc204f8ded`, `attempts.jsonl` `472b410b6b310e25641de08ea7a1ea9ee47c612a910451b41342294825754fec`, `pre-t-blocker-report.md` `04559e57f4eb10cc197502b2e21299a371b8414c71634414a26e9b79fd7d8577`; doc-title bundle under `round4-work/doc-title-sources/` (read-only).

### Attestation (spec v1.13)

- AC-R4-01 (corpus bundle + snapshot reproducible, render-check ok), AC-R4-02 (generation input re-render identical), AC-R4-03 (lexicon components record the snapshot sha), AC-R4-04 (`search.py`, `policy.py`, `search_ranking.json` unchanged across H13..H′), AC-R4-05 (no benchmark read in the renderer, test), AC-R4-06 (pre-T gate = exact write-free dry-run; STOP recorded, non-terminal until the user decision), AC-R4-07/08 (state model: rounds 3 and 4 closed, freeze [1, 2], pending round 5).
- Not attempted (no T): AC-R4-09 (X_preB), AC-R4-10 (recovery), the Round 3-inherited T..D criteria.

### Lessons for Round 5

1. Union precedence: "first wins" let a stale archive entry (release→build) mask a better later-round entry (release→version); a gate-rejected entry should not block the same key from another input.
2. A seed-independent corpus changes the generator's output (s-028) but not where the product's own words differ from the query's (s-039 "workspace" vs "space"; s-027 "searches" vs "filter").
3. s-004 is not a vocabulary problem; it needs a constants or ordering change, which the fixed grid cannot reach.
4. The AC-R3-01 threshold (36) is necessary, not sufficient: the dry-run requires 39/39, so a round that can only reach 36 should be designed against the dry-run target from the start.

## Search Quality Round 5 — decision record (2026-10-10)

**Outcome: terminal branch `D` — the Round 5 hidden-set gate FAILED.** Tuning reached the full Round 5 target (reachable seed 36/36, `tuning_accept` true, counterexample ok) and was adopted (C), but the single final evaluation on the new hidden set scored held_out 14/16 (needs ≥ 15) and negative 6/8 (needs 8/8). Per the inherited rules the gate result is final; it is never re-run or re-interpreted.

Status: **reachable seed: 36/36 · KU registry: 3/3 validated · KU observed: pass 0 / fail 3**.

| item | value |
|---|---|
| round5_start_commit | `56b4b0e` |
| spec / plan | spec v1.12 (`docs/superpowers/specs/2026-10-09-search-quality-round5-design.md`; v1.10 at plan review, v1.11 and v1.12 from review-thread rulings during execution) / plan v8 |
| initial_housekeeping_commit | `19ae3e0` (H16 `51d8006`, H17 `499910f`, review fixes `19ae3e0`) |
| housekeeping_commit (final) | `5862120` (moves below) |
| controller_actor_id / session | Claude Code controller, session `42e25099-9d61-4b2a-b9f5-db24bf29e3ba` (corrected after the post-terminal provenance review; the ledger carries a `ledger_correction` event) |
| S | live fetch 2026-10-10, `s_reused_from_round4: false` (jira-platform spec changed `8ee2e0bb…` → `a7a330f1…`), registry `e308a232d6c9b19a7413e8a38c89b895e44e503581d529c2a31b31fbde179853`, 943 operations |
| inputs (spec §5) | 9 files bound by full sha (`inputs_bound`, `input_blockers == []`), doc-title snapshot re-render byte-identical |
| verb inventory | unchanged `d66317db…`, method-safety 0 violations, prefix ok |
| lexicon_union_resolution | `source-precedence`; 15 pending pairs (11 conflicts) reviewed in two stateless Temporary chats (`6ac9f48a…`, 14 keys; `6ac9f4fb…`, release→version true); 353 kept → gate removed fresh/new/space/summary → 349; `selected`: round4_generation 342, round2_archive 11; release→version from round4_generation; lexicon-r5 merge 28 aliases |
| cumulative provenance (v1.12) | `carry_forward`: 462 prior lexicon entries carried with `carried_selected`, 16 prior candidates provenance-only (`carried_candidates`), active candidates 6 |
| counterexample reference | `round5-counterexample-reference.json` sha `4d1fba45…` (Round 4 first-wins replay, byte-identical to the archived Round 4 lexicon/aliases) |
| T / B / C / D | `607c9e1` / `8707701` / `8de757e` / this commit |
| t_policy_files | alias_candidates.json, concept_lexicon.json, search_aliases.json |
| round_outcomes_sha256 at T | `e0913e3d…` (D appends no outcome record; the round stays frozen) |

### Known-unreachable registry (frozen, `round5-known-unreachable.json` sha `12744de7…`)

| id | cause | mechanisms tried (counterexample) | record check |
|---|---|---|---|
| s-004 | constants/ordering: the bulk-transition summary contains every query word | bulk-variant tier: seed +1 but 2 non-target losses (incl. "Get issue panel pin status for projects") → rejected | identity == 56b4b0e (`ku_identity`, v1.11) |
| s-027 | needs search→filter (verb-inventory key) plus "my" literal handling | "my" neutralization: hit/miss 35/6 → 13/28, loss "Get my filters" → rejected | identity == 56b4b0e |
| s-039 | workspace→space has no official-source support (0 doc titles; Confluence "workspace" = site) | none applicable ("workspace" is itself a catalog token) | identity == 56b4b0e |

Approval: five review-thread rulings (`rulings/2026-10-09-1..5.md`, shas in the registry) and the user decision "좋아 Round 5 진행해보자" (`user_decision_round5`).

### Binding pre-T checkpoint (`round5_simulation --phase pre-T`, real S)

| at | reachable seed | KU fail | regression raw · effective | fixtures | lexicon-only cx | final cx (selected) | dry-run tuning_accept | blockers | verdict |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-10T08:34:58Z | 36/36 | 3/3 | 10/14 · 14/14 | pass | ok (0 losses; 9 uncovered_static) | ok | true | [] | pass |
| 2026-10-10T09:09:21Z (after carry) | 36/36 | 3/3 | 10/14 · 14/14 | pass | ok | ok | true | [] | pass |

`pipeline_result_sha256` `f455a1ce4cd5a95f…` (both runs). AC-13 replay (with carry): concept_lexicon, lexicon-r5 subset, alias_candidates, seed classes and reference policy identical.

### Review-thread rulings during execution and H′

| ruling | decision | H′ |
|---|---|---|
| KU identity (`rulings/2026-10-10-ku-identity.md`) | (a): KU record identity excludes the derived `failure_classes` (spec v1.11) | `2349bba`, `11e967f`; housekeeping 19ae3e0 → 11e967f (fresh review findings closed with RED evidence) |
| cumulative provenance (`rulings/2026-10-10-cumulative-provenance.md`) | (A′): cumulative lexicon provenance, prior candidates provenance-only, synthetic T same semantics (spec v1.12) | `48d3146`, `5862120`; housekeeping 11e967f → 5862120 (fresh review findings: 0) |
| worker identity (`rulings/2026-10-10-worker-identity.md`) | (a): worker id = dispatch transport id; self-report kept non-authoritative | none (ledger interpretation) |

### Hidden set (new, `held_out-r5` / `negative-r5`)

| stage | actor_id | input sha | output sha | result |
|---|---|---|---|---|
| generation | `6aca058c-74c8-83ee-987d-1c67dc4640c3` | e8f14be5… | caecc716… | 16 + 8, machine check 0 violations |
| review (catalog attached) | `6aca2b87-cbd4-83ee-a806-59359d5836fa` | 24f8698a… | ee1a17a5… | 24/24 accepted |

Needle manifest `e98817ef…` (24); scans before encryption, after B and before the terminal: `unexpected_hits == []`. Ciphertext `e273aca2…` (user-encrypted; decrypted by the user for D — first attempt bad decrypt, garbage output deleted, second attempt ok; seal check `seal ok`, ledgered retroactively as `user_decryption_for_D`).

### Tuning (B..C)

Worker `a4c400cc7767437d0` (transport id; handshake self-report retained as non-authoritative evidence). Run `6e7be23f…`: adopted, `tuning_accept` true, seed 36/39 (failed only the KU set), regression 14/14 effective (10/14 raw), fixtures 23/23 · 6/6, counterexample ok (0 losses, 0 uncovered proposer keys), no alias proposals; selected constants equal the B policy, so the worker commit `c970857` changed only the tuning log; C `8de757e` is the empty pre-evaluation commit. `--verify`: replay ok.

### Final evaluation (D controller `afced2da23d7ef747`, single run)

| set | result | gate |
|---|---|---|
| held_out | 14/16 | ≥ 15 — **fail** |
| negative (effective) | 6/8 | 8/8 — **fail** |
| negative actionable (raw) | 2/4 | 4/4 — fail |
| negative abstained (effective) | 4/4 | 4/4 |

Failed: h-010 (top1 `jira-software:GET:/rest/security/1.0/linkedWorkspaces`, the list operation instead of the by-id one), h-011 (top1 `jira-platform:GET:/rest/api/3/configuration`), n-002 (forbidden `jira-software:DELETE:/rest/agile/1.0/board/{boardId}` ranked first), n-004 (forbidden `confluence:DELETE:/pages/{id}` ranked first). Gate checkpoint `round5_gate_result_sha256` `8a1e0b63…`, recorded before the reference was opened.

Round 2 reference observation (decrypted, observed, deleted; ciphertext unchanged): held_out 4/16 (actionable raw 4/12, abstained 0/4), negative 5/8 (actionable raw 1/4, abstained 4/4).

### Lessons for Round 6

1. Reaching every reachable seed (36/36) did not generalize: the new hidden set exposed two failure modes the seed set does not contain — singular-vs-list operations (h-010) and destructive operations outranking an absent target in negatives (n-002, n-004 both rank a DELETE of the parent resource first).
2. Two inherited contracts were unsatisfiable once a round actually reached T/B (KU whole-record identity vs reclassification; per-round lexicon replacement vs vocabulary provenance) and one at the worker handshake (subagents cannot see their own id). Each needed a ruling; earlier rounds never got this far.
3. `TestSealIntegrity.test_hidden_plaintext_machine_rules` calls `machine_check` without `verb_methods`, which round ≥ 3 requires; it skips in the default suite and errors when the snapshot env var is set. The unsealed Round 5 records pass with the frozen inventory (`[]`). The fix belongs to the next round's H (the file is inside the frozen evaluation code).
