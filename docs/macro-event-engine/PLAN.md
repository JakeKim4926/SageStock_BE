# Macro Event Engine — 개발 플랜 체크리스트

정본 명세: [SPEC.md](SPEC.md) | 작성일: 2026-07-02
운영 규칙: 각 Phase의 **통과 게이트**를 전부 체크해야 다음 Phase 시작.
체크 갱신은 해당 작업을 머지한 커밋에서 함께 한다. 이 파일이 진행 상태의 정본이다.

브랜치 전략 (git flow): Phase당 1개 feature 브랜치 → develop 머지.
`feature/macro-phase0-foundation` → `feature/macro-phase1-collectors` → …

---

## 선행 준비 (Phase 0 시작 전)

- [ ] SPEC 부록 A(통합 시 신규 정의 항목) 사용자 검토 완료
- [ ] API 키 발급/확인
  - [x] SAM.gov API key — .env 저장 확인 완료 (2026-07-02)
  - [x] OpenDART API key — .env `DART_API_KEY` 확인 완료
  - [x] SEC EDGAR User-Agent — `SageStock wer1915@gmail.com` 형식 (EDGAR는 연락 이메일 포함 UA 요구)
  - [x] USAspending / Federal Register — 키 불필요 확인 완료
- [x] keyword_domain_map: v1은 yaml 직접 로드로 확정 (DB 동기화는 v1.5)
- [x] 가격 데이터: v1은 EOD/지연 데이터로 확정 (SPEC §13.4) — 구체 어댑터 선택은 Phase 3
- [x] P1 Alert 채널: **이메일**로 확정 — 발송 방식(SMTP 등)과 자격증명 .env 추가는 Phase 4 착수 전까지
- [x] 배치 실행 방식 확정 (2026-07-04): GH Actions 러너가 `python -m app.batch...` 직접 실행 + Neon 직결.
      Render HTTP 미경유 (콜드스타트·100초 타임아웃·스핀다운 회피). SPEC §3 참조

---

## Phase 0 — 기반 (config + enum + 스키마)

브랜치: `feature/macro-phase0-foundation`

### 구현

- [ ] `app/constants/macro_domains.py` — canonical_domain enum 16종 (SPEC §9.1)
- [ ] `app/constants/macro_enums.py` — event_type(3종), source_role, certainty_level(L1~L6),
      market_latency_status, resolution_status, basket_mapping_status, reaction_target_status,
      freshness_status,
      event_status(ACTIVE / ACTIVE_UNLINKED 등), propagation data_quality
- [x] `config/macro_events/keyword_domain_map.yaml` — SPEC §9.5 + ambiguous 단일 목록 §9.3
- [x] `config/macro_events/event_type_rules.yaml` — 수집 조건(§6), chain 규칙(§7), clamp(§15)
- [x] `config/macro_events/domain_basket_map.csv` — §10.2 (17행)
- [ ] `config/macro_events/entity_alias_map.csv` — 시드: 미국 대형 정부 수주사
  - [ ] Phase 0 게이트 기준: 상위 50개 HIGH confidence 시드 (방산/항공우주 위주, verified_by/verified_at 채움)
  - [ ] v1 목표 100~200개 — 운영 검증에서 alias 매핑률 측정 후 확장 (SPEC §11.4)
- [ ] config 로더 (`app/services/macro_events/config_loader.py`) — yaml/csv 파싱 + 스키마 검증
- [ ] SQLAlchemy 모델 (`app/models/macro_*.py`) — SPEC §16:
  - [ ] macro_events (시각 필드 6종 §13.1, domain 필드 5종 §9.4, linked_entities JSONB 포함)
  - [ ] macro_event_chains
  - [ ] macro_event_outcomes (§16 최소 필드: horizon, price/benchmark/excess_return,
        outcome_label, score_version 포함 — 점수 보정 원료, Phase 0 DDL에 필수)
  - [ ] macro_market_reaction_snapshots (basket_mapping_status/reason 포함 §10.4)
  - [ ] macro_event_sources (소스 레지스트리 §4 시드 데이터 포함)
  - [ ] macro_source_freshness
  - [ ] macro_entity_alias_map
- [ ] Alembic migration 작성
- [ ] 배치 실행 경로 스모크 테스트 — `.github/workflows/macro-batch-smoke.yml` (workflow_dispatch):
      checkout → uv sync → `python -m app.batch.smoke` (Neon `SELECT 1` + config 로더 1회).
      `DATABASE_URL`은 GH repo secret. 이후 Phase 1~4 배치가 전부 이 실행 경로를 재사용

### 통과 게이트

- [ ] 정합성 pytest (SPEC §10.5): keyword domain ⊆ enum / basket domain ⊆ enum /
      unknown 제외 domain의 US basket 커버리지 / ambiguous 키워드가 keywords에 중복 등재 안 됨
- [ ] config 로더 단위 테스트 (잘못된 domain·필드 누락 시 명시적 에러)
- [ ] `alembic upgrade head` + `downgrade` 왕복 성공 (로컬 + Neon)
- [x] GH Actions 러너에서 스모크 잡 1회 성공 (러너→Neon 직결 + 의존성 설치 검증) — 2026-07-04, run 28707687394
- [ ] rule-check 통과

---

## Phase 1 — Collectors + Normalize

브랜치: `feature/macro-phase1-collectors`
공통 패턴: collector(수집) / parser(추출) / 필터(수집 조건) 분리. 실패는 freshness에 FAILED + last_error.
Phase 1에서는 수동/로컬 실행으로 검증한다 (GH Actions cron 배선은 Phase 4).
collector 진입점은 `python -m` 실행 가능하게 만든다 — Phase 0 스모크와 동일한 실행 경로.

### 공통 기반

- [ ] collector 베이스 (`app/batch/macro_collectors/base.py`) — 실행 기록, freshness 갱신,
      publicly_observable_at 설정, raw_payload 보존, 예외 시 FAILED 기록
- [ ] Normalize Service — 공통 이벤트 스키마 변환, source timezone → KST 변환
- [ ] 수집 결과 저장 repository (dedup 전 단계 staging 또는 event_unique_id upsert)

### Collector별 (각각: 클라이언트 → 파싱 → 필터 → 저장 → 단위 테스트)

- [ ] **SEC EDGAR** (§6.3~6.5) — 최우선
  - [ ] EDGAR 조회 (UA 헤더, rate limit 준수), Form 4 / SC 13D·13G / 8-K 대상
  - [ ] Form 4: code P만, $1M 이상, roles 필터, option/grant/automatic 제외
  - [ ] 13D/13G: 신규 + amendment 1.0%p 이상, form_family 정규화, 13G 일 처리 상한
  - [ ] 8-K: Item 1.01 / 조건부 8.01 (strong signal 2개+, 단독 키워드 거부)
- [ ] **SAM.gov** (§6.1)
  - [ ] Opportunities API, opportunity_type 4종
  - [ ] 조건 A~D 필터 + estimated_value 부재 규칙 (agency 단독 수집 금지)
  - [ ] agency 계층 매칭 (department + sub-tier)
  - [ ] notice 갱신 처리: type 전환=승격, 동일 type 재게시=업데이트
  - [ ] 필수 저장 필드 12종
- [ ] **USAspending** (§6.2) — 신규 award $50M+ / modification은 delta $10M+ 체인 반영만
- [ ] **Defense.gov Contracts** (§6.7) — HTML 파싱, 항목 분리, 금액·수주사·기관 추출(3/4 필드),
      $50M+ 또는 $7.5M+ strong keyword, modification 구분
- [ ] **White House** (§6.8) — collector/parser/router 분리, EO 번호 후보 추출,
      파싱 실패 시 이벤트 생성 금지 또는 PARTIAL
- [ ] **Federal Register** (§6.8) — Presidential Documents, EO 번호 필드, document_number
- [ ] **OpenDART** (§6.6) — 공급계약(500억+, 매출比 10%+), 대량보유/임원 보고(1.0%p+), EOD 1회

### 통과 게이트

- [ ] 소스 7종 각각 실데이터 수집 ≥1회 성공 (수집 건수·샘플 기록)
- [ ] 필터 검증: solicitation_number 단독 수집 0건 / agency 단독 수집 0건 /
      8.01 단독 키워드 수집 0건 / estimated_value 없는 SAM 이벤트는 전부 strong match
- [ ] 모든 저장 이벤트에 publicly_observable_at + event_unique_id 존재
- [ ] collector 강제 실패 시 freshness FAILED + last_error 기록 확인
- [ ] EDGAR rate limit 준수 확인 (429/차단 없음)
- [ ] rule-check + debt-log-guard

---

## Phase 2 — 파이프라인 서비스

브랜치: `feature/macro-phase2-pipeline`
순서 제약(SPEC §17): Domain → Entity → Reaction Target → Basket. 위반 금지.

### 구현

- [ ] Source Role Tagging — 레지스트리 기반 LEAD/CONFIRMATION/OUTCOME 태깅
- [ ] Event Type Router — taxonomy 3종 강제 (밖의 타입 생성 시 예외 발생)
- [ ] Dedup Service — event_unique_id 기준 중복 제거
- [ ] Chain Resolve Service (§7)
  - [ ] 소스별 chain_key 생성기 (fuzzy 입력 경로 자체가 없게 설계)
  - [ ] ACTIVE_UNLINKED 처리 + presidential_document_number 사후 백필 잡
  - [ ] LEAD→CONFIRMATION→OUTCOME 승격 시 highest_certainty_level 갱신
  - [ ] Form 4 체인은 승격 제외 (반복 관찰 전용)
- [ ] Domain Assignment Service (§9) — word boundary/phrase 매칭, ambiguous 단독 확정 금지,
      confidence 보정표, matched_keywords 기록, 미할당 unknown 처리
- [ ] Entity Resolution Service (§11) — 구조화 ID exact → alias exact → UNRESOLVED,
      resolution_status 기록
- [ ] Reaction Target Selection (§12) — 타입별 우선순위 + fallback 사유 저장 +
      reaction_target_status 기록 (LINKED_ENTITY_RESOLVED ~ NO_TARGET)
- [ ] Basket Mapping Service (§10) — KR broad_market fallback, 실패 status+reason

### 통과 게이트

- [ ] 체인 테스트: 명시적 식별자 없는 체인 0건 / 13D→13D/A 동일 체인 /
      SAM solicitation→award_notice→USAspending 승격 시나리오 /
      EO 번호 백필 연결 + 번호 없는 memorandum은 ACTIVE_UNLINKED 유지
- [ ] 도메인 테스트: ambiguous 단독 primary 확정 0건 / "launch 단독→space 미확정" /
      NASA 이벤트→space→ITA 매핑 성공 (v0.4.1 결함 회귀 테스트)
- [ ] entity 테스트: "Lockheed Martin Corp., Bethesda, Maryland"→LMT (alias exact) /
      alias 없는 이름→UNRESOLVED+DOMAIN_BASKET fallback / 유사 이름 오매핑 0건
- [ ] 실데이터 파이프라인 1회 통과 (Phase 1 수집분 → 보드 저장 직전까지)
- [ ] rule-check + debt-log-guard

---

## Phase 3 — 측정 서비스

브랜치: `feature/macro-phase3-scoring`

### 구현

- [ ] 가격 데이터 어댑터 — LINKED_ENTITY(US 티커)·ETF·KOSPI/KOSDAQ 조회
      (v1 원칙: EOD/지연 데이터, SPEC §13.4 — 기존 stocks 도메인 소스 재사용 우선 검토 후 어댑터 확정)
- [ ] MarketLatency Service (§13) — publicly_observable_at 기준, entity 우선 측정,
      PRE/POST_REACTION/UNKNOWN 판정, 프리마켓 best-effort + data_quality
- [ ] Propagation Stage Service (§14) — v1은 OFFICIAL_ONLY 기본,
      GDELT/뉴스 카운트는 optional (실패 시 강등, 파이프라인 계속)
- [ ] PriorityScore Service (§15) — 컴포넌트 9종 산정 + 항목별 clamp + 총점 clamp + P밴드
- [ ] market_reaction_snapshots 기록

### 통과 게이트

- [ ] clamp 단위 테스트 (경계값: Form 4 20+3+3→20 케이스 포함)
- [ ] 오판정 방지 테스트: entity 급등 + basket 무반응 → PRE_REACTION 아님 (SPEC §12 시나리오)
- [ ] 프리마켓 데이터 부재 → POST_REACTION 억지 판정 없이 DATA_UNAVAILABLE
- [ ] GDELT 미연동 상태에서 전체 파이프라인 정상 완료 (OFFICIAL_ONLY)
- [ ] 실데이터 이벤트 ≥20건에 점수 부여 후 수동 샘플 검토 (P1 과다/과소 여부)
- [ ] rule-check + debt-log-guard

---

## Phase 4 — 산출물 + 운영 배선

브랜치: `feature/macro-phase4-outputs`

### 구현

- [ ] Event Board API — `GET /v1/macro-events` (+필터: event_type, domain, P밴드, edge window),
      상세 조회(체인·reaction 포함). fastapi-structure 준수
- [ ] KR Pre-open Event Brief 생성기 (§5.2) — score 70+, freshness 게이트(§5.5), 실패 소스 명시
- [ ] US Pre-open Event Check 생성기 (§5.3)
- [ ] P1 Event Alert (§5.4) — 발생 조건 5종 + 출력 원칙(매수/매도 문구 금지), 결정된 채널로 발송
- [ ] Outcome Tracking Job — 체인별 사후 결과 기록 (event_outcomes)
- [ ] GH Actions cron 배선 — 러너가 collector 모듈 직접 실행 (Render 미경유, Phase 0 스모크 경로 재사용).
      수집 주기(§4: EDGAR 15~30분, WH 1시간, Defense.gov ≈06:00 KST,
      나머지 일 1~2회) + 리포트 트리거(08:40 / 21:30 KST 이전 완료되도록 여유 포함)
- [ ] 운영 로그/실패 가시화 (리포트 내 freshness 표시)

### 통과 게이트

- [ ] 리포트 2종 실제 생성 (실데이터, 지정 시각 조건 충족)
- [ ] freshness 게이트 동작: 소스 강제 실패 시 리포트에 source_id+reason 표시
- [ ] P1 Alert 출력 검사: 매수/매도 문구 0건, 필수 표시 항목 6종 포함
- [ ] cron 스케줄이 KST 기준 시각과 일치 (GH Actions는 UTC — 변환 검증)
- [ ] 운영 성공 기준(SPEC §19) 측정 방법 마련 (최소: 생성 성공/포함률 로그)
- [ ] rule-check + debt-log-guard

---

## 운영 검증 (Phase 4 이후 2주)

- [ ] 매 거래일 리포트 2종 생성 성공률 추적 (목표 95%)
- [ ] SAM.gov / EDGAR 실볼륨 확인 → 필터 임계값 재조정 여부 판단
- [ ] entity alias 매핑률 측정 → alias 100~200개 확장
- [ ] P1/P2 이벤트의 reaction_target_status 분포 추적 (NO_TARGET 비율 = 실패 지표, SPEC §19)
- [ ] 키워드 오탐 샘플 검토 → ambiguous 목록/weight 조정
- [ ] v1.5 백로그 정리 (AGENCY_COMPANY_LINK, KR 섹터 basket, OpenDART 장중, CAPITAL_RAISE)
