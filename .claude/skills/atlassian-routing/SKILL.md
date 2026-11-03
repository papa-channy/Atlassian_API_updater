---
name: atlassian-routing
description: Use when asked to read, create, edit, or delete Jira or Confluence data, or to design or check an Atlassian REST request, and both the Atlassian connector and the atlassian-openapi MCP may apply.
---

# Atlassian 라우팅

커넥터(`mcp__claude_ai_Atlassian_MCP__*`)는 실행하고, `atlassian-openapi` MCP는 REST 명세를 설계·검수한다. 후자는 Atlassian을 호출하지 않는다.

## 1. 의도부터
- 실제 조회·생성·수정·삭제 → 커넥터 우선.
- "REST 요청을 설계/검토해 줘" → 2번으로. 커넥터에 같은 기능이 있어도 쓰기·삭제 도구를 호출하지 않는다.
- 실행인지 설계인지 불명확 → 실행 전에 묻는다.

## 2. 커넥터 탐색
직접 도구 → 없으면 `discover` → 실행은 반환된 tier(`executeRead`/`executeWrite`/`executeDestructive`)로, 입력은 그 도구·`discover`가 준 규격 그대로(복제·추측 금지, cloudId는 `getAccessibleAtlassianResources`).
operation은 (a) 제품·리소스 (b) 작업 의미 (c) 필수 입력 매핑 (d) 요청 표현 가능을 모두 만족해야 쓴다. 요청은 명확한데 안 맞으면 질의를 바꿔 최대 2회 재탐색한다. 없으면 **"커넥터에서 발견되지 않음"**이라고 한다("미지원 확인"·"기능 없음" 금지). 같은 제품의 다른 대상 operation(예: Confluence 내보내기)을 빌리지 않는다.

## 3. REST 경로 (커넥터에서 발견되지 않았거나 설계 요청일 때만)
실행 요청인데 발견되지 않았다면 REST 후보를 찾아 대조까지 한다(실행하지 않고 명세로만 제시). 대응 후보가 없으면 그때 중단한다.
`search_operations` → `get_operation` → (바디·참조 스키마가 필요할 때만 `get_schema`) → `build_request_template` → `check_request`.
- 1위를 믿지 않는다. 제품·메서드·경로·설명·스키마를 요청과 대조한다. `actionable: false`는 후보일 뿐이고 `abstain_reason`을 본다. 대응이 없으면 "발견되지 않음"을 알리고 중단한다(틀린 후보를 내밀지 않는다).
- 모르는 필수값은 묻되, 비운 항목을 표시한 템플릿과 검수 결과까지 산출한다.
- 결과는 통과·경고·오류·부분 검증을 구분해 전한다. `compatible: true`는 "유효함"이 아니다. `body_check: "structural"`이면 부분 검증이라고 밝힌다. `effective_required: true` 헤더는 빼지 않고 표시한다.
- 서버 URL·자격증명·curl을 만들지 않는다. 끝에 "요청은 전송되지 않았고 작업은 완료되지 않았다"고 쓴다. 여기서 종료한다.
- 사용한 source의 `provenance`만 보고한다. stale이면 "마지막 정상 캐시 기준"이라 표시하고 최신이라 하지 않는다. unavailable이면 그 출처의 설계를 중단한다.

## 4. 쓰기 확인 (하네스는 막아 주지 않는다)
| 상황 | 행동 |
|---|---|
| 읽기 | 바로 실행 |
| 대상·필수값 누락 | 묻고 실행 안 함 |
| 값을 내가 추론 | 제안하고 확인 후 실행 |
| 요청이 대상·내용을 확정한 일반 생성·수정 | 바로 실행 |
| `executeDestructive`, 삭제, 한 요청에 3건 이상 변경 | 대상·범위·영향을 요약해 보이고 **명시적 승인 후에만** 실행 |

거절·무응답이면 실행하지 않는다. 승인받은 대상·내용과 다른 입력, 같은 작업의 중복 호출을 하지 않는다. 후보가 여럿이면 임의로 고르지 않는다. 확인은 잘못된 operation 선택에 대한 면죄부가 아니다.

## 5. 도구가 없을 때
커넥터가 없으면 그렇다고 알린다(도구 이름을 지어내지 않는다). OpenAPI MCP가 없으면 커넥터로 되는 일만 한다. 둘 다 없으면 알리고 끝낸다.
