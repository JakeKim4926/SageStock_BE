# Macro Event Intelligence Engine — 통합 명세 v1.0

작성일: 2026-07-02 KST
상태: **정본 (canonical)** — v0.4 패치 계열(v0.4.1 ~ v0.4.5)을 단일 문서로 통합
개정: v1.0.1 (2026-07-02) — 구현 전 정합성 수정 4건: alias 기준(§11.4), reaction_target_status 도입(§12, §19), event_outcomes 최소 필드(§16), v1 가격 데이터 원칙(§13.4)
구현 위치: SageStock_BE 내 도메인 모듈 (별도 서비스 아님)

> 이 문서가 구현의 유일한 기준이다. 패치 문서(v0.4.x)는 이 문서로 대체되었다.
> `[정의 신규]` 표시가 붙은 절은 패치에 참조만 있고 정의가 없어 통합 시 새로 정의한 것이다 — 사용자 검토 필요.
> `[통합 보강]` 표시는 v0.4.3~v0.4.5 리뷰에서 합의됐으나 패치 본문에 반영되지 않았던 항목을 통합하며 추가한 것이다.

---

## 1. 목적과 원칙

### 1.1 목적

대형 이벤트(대형 계약, 기관의 기업 연계 발표, 대통령 행정 조치, 대형 기관의 지분 변동)를
**가격·뉴스·커뮤니티 확산 전에 관찰**할 수 있게 하는 정보 선점 엔진.

시스템의 산출물은 이벤트 보드와 리포트다. **후보 종목 추천기가 아니다.**

### 1.2 핵심 원칙

```text
1. 이벤트를 저장하는 것이 목적이 아니라, 선점 창(edge window)이 열려 있는지 판정하는 것이 목적이다.
2. 명시적 식별자가 없으면 체인을 만들지 않는다. 오염된 체인은 승격·중복제거·outcome·점수 검증을 전부 망가뜨린다.
3. LLM 추론·유사도 매칭으로 ticker나 체인을 만들지 않는다.
4. 실패를 조용히 UNKNOWN으로 숨기지 않는다. 항상 status + reason을 저장한다.
5. 산출물은 매수/매도를 언급하지 않는다. 원문 확인 요청 형태로만 출력한다.
```

---

## 2. v1 범위

### 2.1 v1 이벤트 타입 (이 3개만 생성 가능)

```text
MEGA_CONTRACT
PRESIDENTIAL_ACTION
INSTITUTIONAL_CAPITAL_SHIFT
```

Collector와 Router는 위 3개 밖의 타입을 생성해서는 안 된다.

### 2.2 이관 타입

| 타입 | 이관 버전 | 사유 |
|---|---|---|
| CAPITAL_RAISE (8-K Item 3.02) | v1.5 | 좋은/나쁜 이벤트 혼재, 해석 난이도 |
| CORPORATE_TRANSACTION (Item 2.01) | v1.5 | M&A 해석 난이도 |
| EARNINGS_EVENT (Item 2.02) | v1.5 | 실적 이벤트 별도 도메인 |
| AGENCY_COMPANY_LINK (기관 뉴스룸) | v1.5 | NASA/DOE/FAA/FCC/FDA 뉴스룸 collector 필요 |
| KR CUSTOM_BASKET / KR 섹터 basket | v1.5 (일부 v1.1) | 구성종목·가격계산 관리 비용 |
| OpenDART 장중 polling (Edge Window C) | v1.5 | v1은 EOD |
| NATIONAL_INVESTMENT | v2 | 비구조화 원문, 정책성 판단 |
| BOTTLENECK_BREAKTHROUGH | v2 | 기술성 판단, LLM 분류 + 사람 검증 필요 |
| REGULATORY_UNLOCK | v2 | 상동 |
| MANAGEMENT_CHANGE / NEGATIVE_EVENT / GENERAL_EVENT | 미정 | v1 목적과 무관 |

**v1은 전체 의도의 부분집합이다.** 목표는 모든 대형 이벤트를 잡는 것이 아니라,
구조화 소스로 검증 가능한 이벤트 보드와 검증 루프를 먼저 완성하는 것이다.

### 2.3 v1의 알려진 한계 (명시적)

```text
- 조달 레일 밖 기관 보도자료(NASA CLPS, DOE LPO 등) 이벤트는 일부 누락된다. (v1.5 AGENCY_COMPANY_LINK)
- 한국 장중 이벤트는 실시간 처리하지 않는다.
- 프리마켓 반응 측정은 best-effort다.
- Presidential Memorandum은 식별 번호가 없어 White House↔Federal Register 체인이 대부분 불가하다. (중복 허용)
```

---

## 3. 아키텍처 결정

```text
- SageStock_BE 도메인 모듈로 구현한다. (fastapi-structure 레이어 규칙 준수)
- Collector 배치는 GitHub Actions cron으로 트리거한다. (무료 호스팅 구성: Render + GH Actions + Neon PG)
- DB는 기존 Neon PostgreSQL을 공유한다. (macro_* 테이블 prefix)
- 모든 시간은 KST 기준으로 관리하되, 소스 원문 시각은 source timezone으로 저장 후 KST 변환한다.
```

레이어 배치 (fastapi-structure 준수):

```text
app/api/v1/endpoints/macro_events_routes.py   # Event Board API
app/services/macro_events/                    # 파이프라인 서비스들
app/repositories/macro_events_repository.py 등
app/models/macro_*.py
app/batch/macro_collectors/                   # 소스별 collector (GH Actions 진입점)
config/macro_events/                          # yaml/csv 규칙 파일
```

---

## 4. 소스 레지스트리

| source_id | 대상 | source_role | 수집 주기 | publicly_observable_at 기준 |
|---|---|---|---|---|
| US_SEC_EDGAR | Form 4, 13D/13G, 8-K | CONFIRMATION | 15~30분 | filing accepted time |
| US_SAM_GOV | 조달 opportunity | LEAD | 1일 1~2회 | opportunity posted date |
| US_USASPENDING | award / obligation | CONFIRMATION / OUTCOME | 1일 1회 | award publication date |
| US_DEFENSE_CONTRACTS | 일일 국방 계약 발표 | LEAD / CONFIRMATION | 미 동부 17:00 발표 직후 1회 (≈06:00 KST) | 발표 게시 시각 |
| US_WHITE_HOUSE | Presidential Actions | LEAD | 1시간 | published time |
| US_FEDERAL_REGISTER | Presidential Documents | CONFIRMATION | 1일 1~2회 | publication date/time |
| KR_OPENDART | 공급계약, 대량보유, 임원·주요주주 | CONFIRMATION | EOD 1회 (v1) | 접수/공시 시각 |
| KR_MARKET_DATA | KRX 가격/지수 | (데이터) | EOD 1회 | — |

소스 역할 정의:

```text
LEAD_SOURCE:         선행 신호 (이벤트가 확정되기 전 관찰 가능)
CONFIRMATION_SOURCE: 이벤트 확정 확인
OUTCOME_SOURCE:      사후 결과·실제 자금 흐름 확인
```

주의: 지분 공시(Form 4, 13D/13G, 대량보유)는 실제 매수 시점을 선점하는 데이터가 아니다.
엣지는 "공개 filing 감지 후 언론·커뮤니티 확산 전 포착"이며, event_time은 filing 공개 시각이다.

---

## 5. Edge Window와 산출물

### 5.1 Edge Window 정의

| 창 | 정의 | 대표 이벤트 | 산출물 |
|---|---|---|---|
| A | 미국 장후 filing/발표 → 다음 미국 개장 전 | Form 4, 13D/13G, 8-K 1.01, Defense.gov contracts | US Pre-open Event Check (21:30 KST) |
| B | 미국 밤 이벤트 → 한국장 09:00 개장 전 | 계약, 행정명령, SAM.gov, SEC filing | KR Pre-open Event Brief (08:40 KST 이전) |
| C | 한국 장중 공시 | OpenDART | v1은 EOD 저장만. 실시간은 v1.5 |

### 5.2 KR Pre-open Event Brief (08:40 KST 이전)

```text
포함 대상:
- priority_score >= 70
- source_region이 US 또는 GLOBAL인 이벤트 우선 포함 (과도하게 제외하지 않는다)
- kr_impact_domains는 정렬/태그/필터 용도로만 사용

주요 질문:
- 밤새 발생한 대형 이벤트가 개장 전에 확인되었는가?
- 한국 관련 domain에 연결되는가?
- 한국장에서는 아직 반응 전인가?
```

kr_impact_domains (config): space, defense, power_grid, energy, nuclear, ai_infrastructure,
data_center, semiconductor, critical_minerals, battery, quantum, cybersecurity, infrastructure

### 5.3 US Pre-open Event Check (21:30 KST 전후)

```text
포함 대상:
- SEC Form 4 / 13D / 13G / 8-K Item 1.01
- Defense.gov daily contracts
- SAM.gov high-priority opportunity
- USAspending high-value award

주요 질문:
- 장후/장전 filing이 미국 정규장 전에 확인되었는가?
- 원문에 명시된 상장 entity가 이미 프리마켓에서 반응했는가? (best-effort)
```

### 5.4 P1 Event Alert (배치 기반)

초단위 실시간이 아니다. **Collector 배치 완료 직후 새로 감지된 P1 이벤트를 즉시 표시**한다.

```text
발생 조건 (전부 충족):
- priority_score >= 85
- certainty_level >= L4
- propagation_stage <= 2
- market_latency_status in [PRE_REACTION, UNKNOWN]
- source_url 존재
- raw_payload 또는 raw_text 존재

출력 원칙:
- 매수/매도 언급 금지, 원문 확인 요청 형태
- source_role / certainty_level / reaction_target_type / MarketLatency data_quality / next_check_source 표시
```

### 5.5 리포트 생성 전 freshness 조건

freshness 상태 enum은 `FRESH / STALE / FAILED / DISABLED` 4개로 고정하고,
시간 조건은 `max_age_hours` 파라미터로 표현한다. (예: "EDGAR가 6시간 이내 갱신" = fresh_within(US_SEC_EDGAR, 6))

```text
US Pre-open Event Check 생성 전:
- US_SEC_EDGAR fresh_within(당일)
- US_WHITE_HOUSE 또는 US_DEFENSE_CONTRACTS 중 1개 이상 FRESH
- US_SAM_GOV 당일 최소 1회 갱신

KR Pre-open Event Brief 생성 전:
- US_SEC_EDGAR fresh_within(6h)
- US_DEFENSE_CONTRACTS 발표일이면 fresh_within(12h)
- US_SAM_GOV 또는 US_USASPENDING 중 1개 이상 fresh_within(24h)

공통:
- 실패 source는 source_id와 reason을 리포트에 명시한다.
```

---

## 6. 수집 규칙 (소스별)

### 6.1 SAM.gov (LEAD)

수집 대상 opportunity_type: sources_sought, pre_solicitation, solicitation, award_notice

수집 조건 (하나 이상 충족):

```text
조건 A: estimated_value >= 50,000,000 USD
조건 B: agency ∈ {NASA, DoD, DOE, DARPA} AND estimated_value >= 10,000,000 USD
조건 C: agency ∈ {NASA, DoD, DOE, DARPA} AND strong_domain_keyword_match
조건 D: strong_domain_keyword_match AND estimated_value >= 10,000,000 USD
```

estimated_value가 없는 경우:

```text
agency ∈ {NASA, DoD, DOE, DARPA} AND strong_domain_keyword_match → 수집
agency만 매칭 → 제외
keyword만 약하게 매칭 → 제외
```

strong keyword 매칭 기준:

```text
- title에서 phrase keyword 매칭
- 또는 title에서 domain 핵심 keyword 2개 이상
- 또는 summary에서 phrase keyword 1개 이상 + 우선 agency 매칭
```

금지: **agency 단독 매칭 수집, solicitation_number 존재만으로 수집.**
solicitation_number는 수집 조건이 아니라 체인 연결용 필수 저장 필드다.

필수 저장 필드: solicitation_number, notice_id, agency_code, agency_name, posted_date,
response_deadline, opportunity_type, estimated_value, title, summary, source_url, publicly_observable_at

`[통합 보강]` agency 매칭은 문자열 일치가 아니라 **department + sub-tier 계층 기준**으로 구현한다.
(DoD 산하 공고는 department="Dept of Defense", sub-tier=Army/Navy/DARPA 등)

`[통합 보강]` notice 갱신 처리: opportunity_type이 바뀌면(예: pre_solicitation → solicitation) 체인 내 승격 이벤트,
같은 type의 재게시·단순 amendment(마감 연장 등)는 기존 이벤트 업데이트로 처리한다. 새 이벤트를 만들지 않는다.

### 6.2 USAspending (CONFIRMATION / OUTCOME)

```text
신규 award:
- min_award_amount >= 50,000,000 USD (new_award_only)
- 새 macro_event 생성

modification:
- 새 이벤트 생성 금지
- award_id 또는 contract_award_unique_key로 기존 체인에 연결 가능하고
  obligated_amount 증가 >= 10,000,000 USD일 때만 기존 체인에 follow-through(L6 신호)로 반영
- 명시적 연결 키가 없으면 버린다
```

### 6.3 SEC 8-K (CONFIRMATION)

| Item | 처리 | certainty |
|---|---|---|
| 1.01 | MEGA_CONTRACT | 기본 L4, 상대방·금액·기간 있으면 L5 후보 |
| 8.01 | MEGA_CONTRACT (조건부) | 기본 L3 |
| 1.02 / 2.01 / 2.02 / 3.02 / 5.02 / 7.01 | 수집 안 함 (v1.5+) | — |

Item 8.01 안전장치 (전부 충족해야 수집):

```text
1. event_type 후보가 MEGA_CONTRACT
2. strong signal keyword 2개 이상 매칭
   (award, definitive agreement, government contract, NASA, DoD, DOE,
    contract value, purchase order, supply agreement, multi-year)
3. contract / government / agreement 단독 매칭 불가
4. 금액, 상대방, 기관명, award 문구 중 최소 1개 존재
```

### 6.4 SEC Form 4 (CONFIRMATION → INSTITUTIONAL_CAPITAL_SHIFT)

```text
- transaction_code = P (공개시장 매수)만
- min_transaction_value >= 1,000,000 USD
- roles: officer, director, ten_percent_owner
- 제외: option_exercise, grant, automatic_transaction
```

### 6.5 SEC 13D / 13G (CONFIRMATION → INSTITUTIONAL_CAPITAL_SHIFT)

```text
- 신규 13D / 13G 수집
- amendment는 ownership 변화 1.0%p 이상만
- 13G 분기 마감 후 급증은 장애가 아니라 예상 배치 부하: 하루 처리 상한 허용,
  score 70 미만 13G는 리포트 하단 또는 별도 보관
```

### 6.6 OpenDART (CONFIRMATION)

```text
단일판매·공급계약:
- min_contract_amount >= 500억 KRW
- min_contract_to_sales_ratio >= 0.10

대량보유(5%) / 임원·주요주주:
- 신규 보고 수집, 지분 변화 1.0%p 이상
```

### 6.7 Defense.gov Contracts (LEAD / CONFIRMATION)

```text
- daily contracts page에서 계약 항목 수집
- amount >= 50,000,000 USD 우선
- amount >= 7,500,000 USD라도 priority_domain keyword가 강하게 매칭되면 수집 가능
- 수주사명, 계약금액, 기관명, 설명 저장 (최소 3개 필드 추출)
- certainty L5 후보. 단 indefinite-delivery / ceiling value / modification 여부로 Magnitude·Certainty 조정
- modification: 체인 연결 가능하면 follow-through, 불가하면 ACTIVE_UNLINKED 독립 저장
```

### 6.8 White House / Federal Register (PRESIDENTIAL_ACTION)

```text
- White House: Executive Order, Presidential Memorandum, Proclamation 발표 원문 (LEAD)
- Federal Register: 동일 문서의 공식 등록 (CONFIRMATION)
- keyword 매칭 필드: title, abstract, summary (대소문자 무시, word boundary)
```

---

## 7. Chain 규칙

### 7.1 원칙

```text
chain_key  = 같은 이벤트 흐름을 묶는 식별자 (단일 문서 ID 금지)
event_unique_id = 개별 이벤트 고유 ID (accession_number, receipt_no, notice_id 등)
```

**금지 매칭 (v1 전면 금지):** 제목 유사도, 본문 임베딩, 기업명만 일치, 날짜 근접,
금액 유사, LLM 추론 단독. 명시적 식별자가 없으면 체인을 만들지 않는다.

### 7.2 소스별 chain_key

| 대상 | chain_key | event_unique_id | 비고 |
|---|---|---|---|
| SEC 13D/13G | filer_cik + subject_company_cik + form_family | accession_number | 13D와 13D/A는 같은 family |
| SEC Form 4 | issuer_cik + reporting_owner_cik + "FORM_4" | accession_number | 반복 관찰용. 확정성 승격 체인 아님 |
| SEC 8-K | issuer_cik + item_code + counterparty_id | accession_number | counterparty 없으면 사실상 미연결 |
| OpenDART 공급계약 | corp_code + report_family + counterparty_norm + contract_name_norm | receipt_no | 이름 없으면 자동 연결 금지 |
| OpenDART 정정 | original_receipt_no | receipt_no | 원공시 번호 없으면 미연결 |
| OpenDART 지분 | corp_code + reporter_id_or_name + report_family | receipt_no | |
| SAM.gov ↔ USAspending | agency_code + solicitation_number | notice_id / award_id | 양쪽에 명시된 경우만 |
| USAspending | award_id 또는 contract_award_unique_key | — | |
| White House ↔ Federal Register | executive_order_number | — | 아래 7.3 |
| Federal Register 단독 | federal_register_document_number | — | |
| Defense.gov | 명시적 계약번호 있으면 사용, 없으면 미연결 | 발표 항목 ID | `[정의 신규]` |

### 7.3 PRESIDENTIAL_ACTION 체인

```text
- EO 번호가 양쪽에 확인되면 같은 event_chain으로 연결하고 certainty 재계산
- White House 발표 시점에 번호가 없으면 event_status = ACTIVE_UNLINKED로 독립 저장
- 나중에 번호가 확인되면 기존 이벤트 검색 → 체인 연결 → LEAD/CONFIRMATION 단계 기록
- 일시적 중복 표시는 허용한다. 잘못된 자동 체인보다 낫다.
```

`[통합 보강]` chain_key를 presidential_document_number로 일반화한다:
EO 번호 또는 Proclamation 번호. Memorandum은 번호가 없으면 영구 미연결(중복 허용)을 명시한다.

### 7.4 체인 승격

```text
LEAD → CONFIRMATION → OUTCOME 순서로 highest_certainty_level을 갱신한다.
예: SAM.gov solicitation(L3) → award_notice(L5) → USAspending obligated(L6)
Form 4 체인은 승격 체인이 아니라 반복 관찰용이다. 오래 떨어진 반복 거래를 강한 승격으로 해석하지 않는다.
```

---

## 8. Certainty Ladder `[정의 신규]`

패치 전반의 L2~L6 참조와 정합하도록 통합 시 정의했다.

| 레벨 | 정의 | 예 |
|---|---|---|
| L1 | 비공식/루머 | v1 수집 안 함 |
| L2 | 관심/시장조사 | SAM.gov sources_sought |
| L3 | 공식 예고·공고 | pre_solicitation, solicitation, 8-K Item 8.01 기본 |
| L4 | 공식 확정 발표·서명 | 8-K Item 1.01 기본, 행정명령 서명 |
| L5 | award/체결/공식 filing 확인 | award_notice, Defense.gov daily, OpenDART 공급계약, Form 4·13D/13G filing |
| L6 | 자금 집행 확인 | USAspending obligated amount |

---

## 9. Domain Assignment

### 9.1 canonical_domain enum (이것 밖의 domain 저장 금지)

```text
space, defense, power_grid, energy, nuclear, ai_infrastructure, data_center,
semiconductor, critical_minerals, battery, quantum, cybersecurity,
infrastructure, financials, broad_market, unknown
```

keyword_domain_map.domain과 domain_basket_map.domain은 반드시 이 enum만 사용한다.

### 9.2 매칭 규칙

```text
- 매칭 필드: title, summary, official_abstract, structured_description (본문 전체 매칭 금지)
- 대소문자 무시, word boundary 매칭, phrase keyword는 phrase 단위
- title 매칭 > summary 매칭 weight
```

confidence 보정:

| 조건 | 보정 |
|---|---:|
| title phrase match | +5 |
| title word boundary match | +3 |
| summary phrase match | +3 |
| summary word boundary match | +1 |
| 같은 domain 키워드 2개 이상 | +3 |
| source가 해당 domain 전문 기관 | +3 |

### 9.3 ambiguous keywords (단일 목록 — 유일한 진실)

```text
AI, chip, gas, launch, energy, power, security, infrastructure, contract, government,
defense, electricity          # 뒤 2개는 [통합 보강]
```

처리: 단독 매칭 시 domain_confidence 낮게, primary_domain 확정 금지.
phrase keyword 또는 같은 domain 보조 keyword가 추가로 필요. source agency 일치 시 confidence 보정 가능.

### 9.4 할당 절차와 결과 필드

```text
title 매칭 → summary/abstract 매칭 → 구조화 필드 매칭 → weight 합산
→ 최고 domain = primary_domain, 일정 점수 이상 = secondary_domains
```

macro_events 필드: primary_domain, secondary_domains, domain_confidence,
matched_keywords, domain_assignment_version

미할당: primary_domain=unknown, domain_confidence=0, market_latency_status=UNKNOWN.
단 authority·certainty 높은 이벤트는 domain unknown이어도 보드에 표시 가능.

### 9.5 keyword → domain 매핑 (요약)

정본 값은 `config/macro_events/keyword_domain_map.yaml`(Phase 0 산출물)이다. 구조:

```yaml
domains:
  space:
    phrase_keywords: [space station, lunar lander, launch vehicle, satellite constellation]
    keywords: [NASA, lunar, satellite, Artemis]
    ambiguous_keywords: [launch]
  defense:
    phrase_keywords: [missile defense, hypersonic weapon, defense contract]
    keywords: [DoD, DARPA, missile, hypersonic, army, navy, air force]
    ambiguous_keywords: [defense]
  power_grid:
    phrase_keywords: [power grid, electric grid, transmission line, grid connection, power infrastructure]
    keywords: [transformer, transmission, substation]
    ambiguous_keywords: [power, electricity]
  energy:
    phrase_keywords: [energy infrastructure, LNG terminal, oil production, gas pipeline]
    keywords: [LNG, crude oil]
    ambiguous_keywords: [energy, gas]
  nuclear:
    phrase_keywords: [small modular reactor, nuclear reactor, nuclear power]
    keywords: [SMR, uranium, reactor, nuclear]
  ai_infrastructure:
    phrase_keywords: [artificial intelligence, AI infrastructure, compute cluster, GPU cluster, AI accelerator]
    keywords: [GPU]
    ambiguous_keywords: [AI]
  data_center:
    phrase_keywords: [data center, datacenter, hyperscale data center, cloud infrastructure]
    keywords: [hyperscale]
  semiconductor:
    phrase_keywords: [advanced packaging, semiconductor manufacturing, chip fabrication, foundry capacity]
    keywords: [semiconductor, HBM, foundry]
    ambiguous_keywords: [chip]
  critical_minerals:
    phrase_keywords: [rare earth, critical minerals, mineral supply chain]
    keywords: [lithium, nickel, cobalt]
  battery:
    phrase_keywords: [battery supply chain, energy storage system, lithium-ion battery]
    keywords: [ESS, battery]
  quantum:
    phrase_keywords: [quantum computing, quantum communication, quantum sensor]
    keywords: [quantum]
  cybersecurity:
    phrase_keywords: [cyber security, cybersecurity, zero trust, cyber defense]
    keywords: [ransomware, encryption]
    ambiguous_keywords: [security]
  infrastructure:
    phrase_keywords: [infrastructure investment, public infrastructure, transportation infrastructure, critical infrastructure]
    keywords: []
    ambiguous_keywords: [infrastructure]
  financials:
    phrase_keywords: [bank capital, financial institution, asset manager]
    keywords: [banking, financials]
```

---

## 10. Basket Mapping

### 10.1 v1 원칙

실존 ETF 또는 대표 지수만 사용한다. custom basket 가격 계산 로직을 만들지 않는다.

### 10.2 domain_basket_map v1 (정본 값은 config CSV)

```csv
domain,region,basket_type,symbol,priority
space,US,ETF,ITA,1
defense,US,ETF,ITA,1
power_grid,US,ETF,XLU,1
energy,US,ETF,XLE,1
nuclear,US,ETF,URA,1
ai_infrastructure,US,ETF,XLK,1
data_center,US,ETF,XLK,1
semiconductor,US,ETF,SOXX,1
critical_minerals,US,ETF,REMX,1
battery,US,ETF,LIT,1
quantum,US,ETF,XLK,1
cybersecurity,US,ETF,CIBR,1
infrastructure,US,ETF,PAVE,1
financials,US,ETF,XLF,1
broad_market,US,ETF,SPY,1
broad_market,KR,INDEX,KOSPI,1
broad_market,KR,INDEX,KOSDAQ,2
```

### 10.3 KR 처리

```text
v1: KR domain basket 없으면 KOSPI/KOSDAQ broad_market으로 대체
v1.1: defense, space, nuclear, semiconductor, power_grid 우선으로 KR proxy 추가
      (데이터 접근 가능성 확인 전에는 ticker를 명세에 박지 않는다)
```

### 10.4 실패 처리

```text
basket_mapping_status: MAPPED / NO_DOMAIN / NO_BASKET / DATA_UNAVAILABLE
+ basket_mapping_reason 저장. 조용히 UNKNOWN으로 숨기지 않는다.
```

### 10.5 정합성 테스트 (Phase 0 통과 조건)

```text
1. keyword_domain_map의 모든 domain ∈ canonical enum
2. unknown 제외 주요 domain은 최소 1개 US basket 보유
3. domain_basket_map의 모든 domain ∈ canonical enum
4. primary_domain 있는 이벤트는 매핑 성공 또는 명시적 NO_BASKET
```

---

## 11. Entity Resolution

### 11.1 허용 / 금지

```text
허용: CIK / corp_code / UEI exact match, curated alias exact match (정규화 법인명·alias)
금지: 문자열 유사도 ticker 추론, LLM 기반 ticker 추론, parent/subsidiary 임의 추론,
      이름 일부 포함 매핑, 사람이 검증하지 않은 자동 alias 추가
```

### 11.2 절차

```text
원문 entity 추출 → 구조화 ID 확인 → CIK/corp_code/UEI exact → curated alias exact → UNRESOLVED
```

### 11.3 source별 매핑

| 소스 | 1순위 | 2순위 | 실패 시 |
|---|---|---|---|
| SEC Form 4 / 13D·13G / 8-K | CIK | ticker | UNRESOLVED |
| OpenDART | corp_code | 종목코드 | UNRESOLVED |
| Defense.gov / USAspending / SAM.gov | UEI (있으면) | curated alias exact | DOMAIN_BASKET fallback |
| White House / Federal Register | 없음 | 없음 | DOMAIN_BASKET |

resolution_status: RESOLVED_STRUCTURED_ID / RESOLVED_ALIAS_EXACT / UNRESOLVED / NOT_APPLICABLE

### 11.4 entity_alias_map

주요 컬럼: canonical_entity_name, alias_name, normalized_alias, ticker, exchange, cik,
corp_code, uei, country, entity_type, mapping_confidence, verified_by, verified_at, is_active, version

v1 범위:

```text
v1 목표:            미국 대형 방산/항공우주/에너지/반도체 정부 수주사 100~200개 (사람 검증, 버전 관리)
Phase 0 통과 기준:  상위 50개 HIGH confidence alias 시드
확장 시점:          운영 검증 기간에 alias 매핑률을 측정한 뒤 100~200개로 확장
```

alias table은 투자 후보 리스트가 아니라 가격 반응 측정용 식별자 테이블이다.

---

## 12. Reaction Target Selection

```text
MEGA_CONTRACT / INSTITUTIONAL_CAPITAL_SHIFT:
  resolution_status가 RESOLVED_* 인 상장 entity 있음 → LINKED_ENTITY
  없음 → DOMAIN_BASKET → BROAD_MARKET → UNKNOWN

PRESIDENTIAL_ACTION:
  DOMAIN_BASKET → BROAD_MARKET → UNKNOWN
```

이유: entity가 명시된 이벤트를 basket으로만 측정하면
(예: 중형 우주기업 +40%, ITA +0.3%) PRE_REACTION으로 오판한다.

linked_entities는 원문에 명시된 구조화 entity만 담는다.
**관련주 추론·LLM 수혜기업 추가·밸류체인 후보 삽입 금지.**

선정 결과는 `reaction_target_status`로 기록한다:

```text
LINKED_ENTITY_RESOLVED   상장 entity 해결, entity 반응 측정
DOMAIN_BASKET_MAPPED     basket으로 측정
MARKET_INDEX_MAPPED      broad market으로 측정
NO_TARGET                측정 대상 없음 (실패)
DATA_UNAVAILABLE         대상은 있으나 가격 데이터 없음
```

`basket_mapping_status`(§10.4)는 대체하지 않고 유지한다 — basket 단계의 실패 진단용이며,
reaction_target_status는 최종 측정 대상 선정 결과다.

---

## 13. MarketLatency

### 13.1 기준 시각

```text
market_latency_reference_time = publicly_observable_at
(내부 발생 시각이 아니라 공개 관찰 가능 최초 시각. signed_at이 있어도 비공개였다면 사용 금지)
```

시각 필드: event_effective_at, document_signed_at, source_published_at, collected_at_kst,
publicly_observable_at, latency_reference_type(SIGNED_AT/PUBLISHED_AT/FILING_ACCEPTED_AT/COLLECTED_AT)

### 13.2 상태 `[정의 신규]`

```text
market_latency_status: PRE_REACTION(반응 전) / POST_REACTION(이미 반응) / UNKNOWN(측정 불가)
```

### 13.3 프리마켓 (best-effort)

```text
data_quality: PREMARKET_AVAILABLE / DELAYED / EOD_ONLY / DATA_UNAVAILABLE
프리마켓 데이터가 없으면 POST_REACTION으로 억지 판정하지 않고 DATA_UNAVAILABLE로 표시한다.
```

reaction_target_type: LINKED_ENTITY / DOMAIN_BASKET / MARKET_INDEX(BROAD_MARKET) / UNKNOWN

### 13.4 v1 가격 데이터 원칙

```text
- US 개별 종목: EOD/지연 데이터 우선. 프리마켓은 best-effort (§13.3)
- US ETF: SPY, ITA, XLE, XLK, XLU, SOXX, URA, REMX, LIT, CIBR, PAVE, XLF
- KR: KOSPI / KOSDAQ EOD
- 실시간/프리마켓 미확보 시 DATA_UNAVAILABLE (억지 판정 금지)
- 구체 어댑터 선택은 Phase 3 구현 사항 (기존 stocks 도메인 소스 재사용 우선 검토)
```

---

## 14. Propagation Stage

```text
0: 공식 원문만 존재
1: 공식 원문 + 제한적 전문 매체/기관 보도자료
2: 일반 경제지/주요 뉴스 다수 보도
3: 포털 뉴스 확산 또는 검색량 증가
4: 커뮤니티/SNS 확산 (v1 측정 제외)
5: 가격·거래대금 과열
```

v1 측정 대상: 공식 원문 존재, GDELT/뉴스 검색 결과 수, 동일 이벤트 중복 기사 수,
(가능 시) 검색 트렌드 전일 변화. **GDELT 연동 실패 시 OFFICIAL_ONLY로 강등하고 파이프라인은 계속 동작한다.**

data_quality: OFFICIAL_ONLY / NEWS_DELAYED / SEARCH_DAILY / PARTIAL / UNKNOWN (+reason)

---

## 15. PriorityScore

### 15.1 컴포넌트별 clamp (보정 포함 상한 초과 금지)

```text
SourceAuthority:         0 ~ 20
EventMagnitude:          0 ~ 20
Certainty:               0 ~ 15
Novelty:                 0 ~ 15
MarketLatency:         -10 ~ 15
CrossMarketImpact:       0 ~ 10
FollowThroughPotential:  0 ~ 10
NoisePenalty:          -20 ~ 0
AmbiguityPenalty:      -20 ~ 0

priority_score = clamp(raw_score, 0, 100)
```

### 15.2 우선순위 밴드

```text
P1: 85~100   (패치 확정)
P2: 70~84    [정의 신규 — 리포트 포함 기준 70과 정합]
P3: 50~69    [정의 신규]
P4: <50      [정의 신규]
```

---

## 16. 데이터 모델 개요

상세 DDL은 Phase 0 산출물. 테이블과 핵심 필드 그룹:

```text
macro_events            식별(event_unique_id, source_id, event_type), 시각 필드(§13.1),
                        chain(event_chain_id, event_status[ACTIVE, ACTIVE_UNLINKED, ...]),
                        domain(§9.4), linked_entities(JSONB, §11), 점수/레벨(priority_score,
                        certainty_level, propagation_stage), raw_payload/raw_text, source_url
event_chains            chain_key, highest_certainty_level, 이벤트 목록/순서
event_outcomes          event_id, event_chain_id, horizon(1D/3D/5D/10D/20D), measured_at_kst,
                        reaction_target_type/id, price_change_pct, volume_change_ratio,
                        benchmark_change_pct(같은 기간 broad_market: SPY/KOSPI),
                        excess_return_pct(price - benchmark),
                        outcome_label(MOVED/IGNORED/DELAYED/FALSE_POSITIVE/UNKNOWN),
                        score_version, notes — 향후 점수 보정의 원료이므로 Phase 0 DDL에 포함
market_reaction_snapshots  reaction_target_type/id, reaction_target_status(§12),
                        basket_mapping_status/reason, market_latency_status, data_quality,
                        측정 시점별 가격 스냅샷
event_sources           소스 레지스트리 (§4)
source_freshness        source_id, last_success_at_kst, freshness_status, last_error
keyword_domain_map      §8 테이블 (id, keyword, normalized_keyword, domain, region_scope,
                        match_field, match_type, weight, is_active)
entity_alias_map        §11.4
```

---

## 17. 실행 파이프라인 (순서 고정)

```text
Collector
→ Source Freshness Update
→ Normalize
→ Source Role Tagging
→ Event Type Routing
→ Dedup
→ Chain Resolve
→ Domain Assignment
→ Entity Resolution
→ Reaction Target Selection
→ Basket Mapping
→ MarketLatency
→ Propagation Stage
→ PriorityScore
→ Event Board
→ Report / Alert
→ Outcome Tracking
```

순서 제약: Domain Assignment → Basket Mapping → MarketLatency는 필수 선행 관계.
Entity Resolution은 MarketLatency 전. Reaction Target Selection은 Basket Mapping 전.

---

## 18. 구현 계획 (Phase)

각 Phase는 검증 기준을 통과해야 다음으로 진행한다.

### Phase 0 — 기반 (config + 스키마)

```text
산출물: canonical_domain enum, event_type_rules.yaml, keyword_domain_map.yaml,
        domain_basket_map.csv, entity_alias_map.csv(시드), source registry,
        PostgreSQL DDL + Alembic, Source Freshness 모델
검증:   §10.5 정합성 테스트 통과, DDL 마이그레이션 성공
```

### Phase 1 — Collectors + Normalize

```text
산출물: EDGAR, SAM.gov, USAspending, Defense.gov, White House, Federal Register,
        OpenDART collector + Normalize Service + freshness 기록
검증:   각 소스 실데이터 1회 이상 수집 성공, §6 필터 성공 기준
        (solicitation_number 단독 수집 0건, agency 단독 수집 0건 등)
```

### Phase 2 — 파이프라인 서비스

```text
산출물: Source Role Tagging, Event Type Router, Dedup, Chain Resolve,
        Domain Assignment, Entity Resolution, Reaction Target Selection, Basket Mapping
검증:   체인 성공 기준(명시적 식별자 없는 체인 0건, EO 체인 연결/ACTIVE_UNLINKED 동작),
        domain 성공 기준(ambiguous 단독 확정 0건), alias exact match 동작
```

### Phase 3 — 측정 서비스

```text
산출물: MarketLatency, Propagation Stage, PriorityScore
검증:   clamp 단위 테스트, LINKED_ENTITY 우선 측정 케이스,
        실패 시 status+reason 저장 확인, GDELT 미연동 시 OFFICIAL_ONLY 강등 동작
```

### Phase 4 — 산출물

```text
산출물: Event Board API, KR Pre-open Event Brief, US Pre-open Event Check,
        P1 Event Alert, Outcome Tracking Job, GH Actions cron 설정
검증:   §5.5 freshness 조건, 리포트 생성 성공률, P1 Alert 출력 원칙(매수/매도 문구 0건)
```

---

## 19. 운영 성공 기준

```text
- 매 거래일 08:40 KST 이전 KR Brief 생성 성공률 95% 이상
- priority_score 70 이상 이벤트의 해당 edge window 리포트 포함률 90% 이상
- P1/P2 이벤트 중 reaction_target_status가 LINKED_ENTITY_RESOLVED / DOMAIN_BASKET_MAPPED /
  MARKET_INDEX_MAPPED / DATA_UNAVAILABLE 중 하나인 비율 90% 이상 (NO_TARGET만 실패로 계산)
- Collector 실패 시 실패 source_id와 사유를 리포트에 표시
- alias table에 없는 entity의 ticker 추론 0건
```

---

## 부록 A — 통합 시 새로 정의한 항목 (사용자 검토 대상)

```text
1. Certainty Ladder L1~L6 전체 정의 (§8) — 패치의 부분 참조와 정합하도록 구성
2. market_latency_status enum 3종 (§13.2)
3. 우선순위 밴드 P2/P3/P4 경계 (§15.2)
4. Defense.gov chain 규칙 (§7.2)
5. event_outcomes 테이블 개요 (§16)
6. [통합 보강] presidential_document_number 일반화, SAM.gov amendment 처리,
   agency 계층 매칭, ambiguous keyword에 defense/electricity 추가
```
