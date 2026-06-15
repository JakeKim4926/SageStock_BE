# 기술부채 로그 (DEBT_LOG)

이번 작업 범위 밖이라 남겨둔 위험 요소를 기록한다. 즉시 해결이 아니라 추적이 목적이다.
해결한 항목은 `## 해결됨` 섹션으로 옮긴다.

## 열린 항목

### [2026-06-15] 검증누락 — KIS HTTP 왕복 통합테스트 없음
- 위치: app/data/kis_source.py get_current_quote / _get_token
- 설명: _parse_quote 단위테스트와 미설정·비KR None 케이스만 커버. 실제 토큰 발급→현재가 GET의 httpx 왕복과 KIS 응답 스키마(필드명 stck_prpr 등)는 키 부재로 미검증. 필드명이 실제와 다르면 파싱 실패→폴백으로 숨겨짐.
- 위험도: 중
- 후속: httpx MockTransport로 경로 테스트 + 실키로 1회 스모크 후 필드 확정

### [2026-06-15] 후속분리 — 해외(US) 종목 실시간 현재가 미구현
- 위치: app/services/market_service.py _build_snapshot / app/services/stock_service.py get_quote
- 설명: KIS 국내 현재가만 붙임. US는 여전히 fdr 일봉 지연. is_delayed는 KR(KIS)만 False, US는 True 유지(의도된 1차 범위).
- 위험도: 낮음
- 후속: KIS 해외주식 현재가(별도 tr_id) 도입 검토

### [2026-06-15] 임시구현 — 실시간 현재가 캐시 없음·KIS 선행 호출
- 위치: app/data/kis_source.py get_current_quote (호출: market_service/stock_service)
- 설명: 매 요청·관심종목 수만큼 KIS를 호출하고 결과 캐시 없음. KIS를 fdr보다 선행 호출해, KIS가 느리면 타임아웃(5s)만큼 응답 지연. 1인 앱·소규모 watchlist엔 충분하나 폴링 주기↑/유니버스↑ 시 호출량·레이턴시 부담.
- 위험도: 중
- 후속: 단기 TTL 캐시(수 초) 또는 동시성 제한 도입

### [2026-06-11] 구조변경 — 서빙 메타가 stock_meta DB 선행 적재에 의존
- 위치: app/services/stock_meta_service.py / market_source.get_listing_index는 이제 배치 전용
- 설명: search/단건메타/watchlist·holdings 조인이 모두 stock_meta DB를 읽음. 배치 미실행(빈 테이블) 시 검색=빈결과, 단건=404. 콜드스타트 ~15s 제거를 위한 의도된 트레이드오프이나, 운영상 배치 선행이 필수 전제가 됨.
- 위험도: 중
- 후속: 배포 파이프라인에 마이그레이션 후 stock_meta 배치 1회 + cron 등록

### [2026-06-11] 임시구현 — paper_account 가입 시 미생성·첫 접근 시 지연 생성
- 위치: app/services/paper_service.py _get_or_create_account
- 설명: feature-spec §4.6은 "계정 생성 시 cash=seed"이나 signup(auth_service)은 손대지 않고 /paper 첫 접근 때 시드로 지연 생성. 동작은 동일하나 계정 생성 시점이 명세와 다름.
- 위험도: 낮음
- 후속: signup 트랜잭션에서 paper_account 생성으로 이동 검토

### [2026-06-10] 임시구현 — 다이버전스 탐지 단순 3봉 피벗
- 위치: app/services/signal_detector.py _pivots/_detect_divergences
- 설명: 국소 저점/고점을 3봉 피벗으로만 잡아 직전 두 피벗을 비교. 완만한 스윙/노이즈에 취약해 정식 스윙 탐지 대비 오탐·누락 가능.
- 위험도: 중
- 후속: ATR/주기 기반 스윙 탐지 또는 피벗 강도 임계값 도입

### [2026-06-10] 임시구현 — /signals 피드 최신성 컷오프 없음
- 위치: app/services/signal_service.py get_signals
- 설명: 120봉 윈도우 전체에서 탐지해 최대 ~6개월 전 시그널까지 포함. 최신순 정렬+페이지네이션으로 최근 것이 위로 오지만 total이 커지고 오래된 시그널이 노이즈가 될 수 있음.
- 위험도: 낮음
- 후속: 최근 N봉/일 컷오프 파라미터 도입 (api-spec 협의)

### [2026-06-10] 임시구현 — 영(young) 종목 지표 워밍업 패딩
- 위치: app/services/stock_service.py _series_to_list
- 설명: 유효봉 60~239개 종목은 ema60/120 워밍업 NaN을 bfill·0.0으로 채워 시리즈 앞부분이 평탄/왜곡됨. 이력 충분한 종목(대다수)은 영향 없음.
- 위험도: 중
- 후속: 장기선은 이력 충분 구간만 노출하거나 워밍업 구간 별도 처리

### [2026-06-10] 기존부채 — mypy 전역 설정 부재 / passlib 스텁 에러
- 위치: app/core/security.py:5 (이번 작업 외), pyproject.toml(설정 없음)
- 설명: mypy 설정이 없어 서드파티 스텁 누락이 에러로 남음. 내 신규 코드는 pandas/fdr import에 인라인 `# type: ignore[import-untyped]`로 처리했으나 근본 설정은 없음. develop에서도 passlib 에러 존재.
- 위험도: 낮음
- 후속: [tool.mypy] ignore_missing_imports 또는 types-passlib/pandas-stubs 도입

## 해결됨

### [2026-06-11] 검증누락 — stock_meta 배치 end-to-end 미실행 (2026-06-15 해결)
- 위치: app/batch/refresh_stock_meta.py / .github/workflows/refresh-stock-meta.yml
- 설명: 운영 Neon에 수동 1회 적재(~9.5천종목) + GitHub Actions 워크플로 수동 실행으로 end-to-end 검증 완료(1m28s, replace_all). 일배치 cron(매일 03:00 KST)도 등록 — "배포 파이프라인에 cron 등록" 후속도 함께 해소.

### [2026-06-10] 하드코딩 — Quote.isDelayed 항상 True (KIS 실시간 도입에서 부분 해결)
- 위치: app/services/stock_service.py get_quote / app/data/kis_source.py
- 설명: KR 종목은 KIS 실시간 현재가 도입으로 is_delayed=False 판정(시장별 분기). US 잔여(여전히 fdr 지연)는 위 열린 항목 "후속분리 — 해외(US) 종목 실시간 현재가 미구현"으로 이관.

### [2026-06-10] 구조불일치 — stock_meta 미영속(인메모리 리스팅 캐시) (B4에서 해결)
- 위치: app/services/stock_meta_service.py / app/repositories/stock_meta_repository.py / app/batch/refresh_stock_meta.py
- 설명: 콜드스타트 시 전체 리스팅 다운로드(~15s)를 유발하던 인메모리 캐시 의존을, stock_meta DB 테이블 + 일배치(replace_all)로 전환. 서빙(search·단건·조인)은 DB를 읽고, fdr 리스팅은 배치 전용. get_listing_index는 배치에서만 사용.

### [2026-06-11] 구조불일치 — /paper/holdings 현재가 종목별 순차 조회 (B3에서 해결)
- 위치: app/services/paper_service.py get_holdings
- 설명: 보유 종목별 현재가를 순차 await하던 것을 asyncio.gather로 동시 조회로 변경(market_service.get_snapshots와 동일 패턴). 보유 종목 수만큼 지연 누적되던 문제 해소.

### [2026-06-10] 임시구현 — 시세/시그널 피드 유니버스 하드코딩 시드 (B3에서 해결)
- 위치: app/services/market_service.py get_snapshots / app/services/signal_service.py get_signals
- 설명: /market/snapshots·/signals가 고정 시드(SEED_UNIVERSE)를 쓰던 것을, B3 watchlist 도메인 추가 후 로그인 사용자 watchlist 기반 유니버스로 교체. SEED_UNIVERSE 상수 제거. 빈 watchlist는 빈 피드를 반환한다.

### [2026-06-10] 임시구현 — IndicatorSet cross/divergence 마커 빈 배열 (B2에서 해결)
- 위치: app/services/stock_service.py _build_indicator_set
- 설명: B1에서 crossMarkers/divergenceMarkers를 빈 배열로 반환하던 것을, B2 시그널 탐지(app/services/signal_detector.py)와 계산 공유해 채움.
