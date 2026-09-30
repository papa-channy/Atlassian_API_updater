# Phase 3 진입 재판정 기록 (readiness)

기준: [Phase 2.5 spec v1.2 §18](superpowers/specs/2026-09-29-phase2.5-discovery-hardening-design.md#18-phase-3-진입-재판정-기준-분리-docsphase3-readinessmd에-기록).
이 문서는 평가 결과를 **기록만** 한다. 벤치마크(`tests/benchmarks/search_queries.json`)의 held_out/negative와
`intelligence/data/search_aliases.json`은 동결 상태이며, 실패 질의의 반영은 §7.3 승격 절차(별도의 후속 변경)로만 한다.

## 판정 요약 (2026-09-30, 1차)

| 축 | 기준 (§18) | 1차 결과 | 판정 |
|---|---|---|---|
| Discovery | held_out top-1 ≥ 90%, negative 실패 0 (실제 캐시) | held_out 6/12 (50%), negative 7/8 (실패 1), seed 7/9 | **미충족** |
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

## Spec amendment (v1.2, 미출시이므로 transpiler version은 1 유지)

- §11.2 transpiler rule 5: `oneOf` → `anyOf`로 변환한다. Atlassian의 union 스키마는 가지가 서로 겹쳐서
  `oneOf`의 "정확히 하나" 의미로는 유효한 payload도 거부되기 때문이다. `oas_transpiler_version`은 1 그대로 둔다.
- 알려진 한계: `additionalProperties`/`not` 값 스키마 아래의 `readOnly`는 본문에서 검출하지 않는다. 스키마 오류
  메시지는 제출값을 되풀이하지 않으므로 `anyOf`/`pattern` 실패는 "violates <validator>" 식의 일반 문구로 나온다.
