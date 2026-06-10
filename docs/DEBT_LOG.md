# 기술부채 로그 (DEBT_LOG)

이번 작업 범위 밖이라 남겨둔 위험 요소를 기록한다. 즉시 해결이 아니라 추적이 목적이다.
해결한 항목은 `## 해결됨` 섹션으로 옮긴다.

## 열린 항목

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

### [2026-06-10] 임시구현 — 시세/시그널 피드 유니버스 하드코딩 시드
- 위치: app/constants/market.py SEED_UNIVERSE / app/services/market_service.py / app/services/signal_service.py
- 설명: /market/snapshots·/signals 모두 관심종목(watchlist) 기반이어야 하나 watchlist 도메인이 B3라 고정 시드 10종목으로 채움. 사용자별 피드가 아님.
- 위험도: 중
- 후속: B3 watchlist 연동 시 시드 → 사용자 watchlist 기반으로 교체

### [2026-06-10] 임시구현 — 영(young) 종목 지표 워밍업 패딩
- 위치: app/services/stock_service.py _series_to_list
- 설명: 유효봉 60~239개 종목은 ema60/120 워밍업 NaN을 bfill·0.0으로 채워 시리즈 앞부분이 평탄/왜곡됨. 이력 충분한 종목(대다수)은 영향 없음.
- 위험도: 중
- 후속: 장기선은 이력 충분 구간만 노출하거나 워밍업 구간 별도 처리

### [2026-06-10] 구조불일치 — stock_meta 미영속(인메모리 리스팅 캐시)
- 위치: app/data/market_source.py get_listing_index
- 설명: 캐시 만료/콜드스타트 시 첫 search·meta 요청이 전체 KRX+NASDAQ+NYSE 리스팅 다운로드(~15s, tqdm 진행바 stderr 출력)를 유발.
- 위험도: 중
- 후속: B4에서 stock_meta DB 테이블 + 배치 갱신으로 전환

### [2026-06-10] 하드코딩 — Quote.isDelayed 항상 True
- 위치: app/services/stock_service.py get_quote (IS_DELAYED_DEFAULT)
- 설명: fdr 지연 시세라 KR/US 무관 True 고정. feature-spec은 KR 기본 True 명시.
- 위험도: 낮음
- 후속: 실시간 시세 소스 도입 시 시장별 판정(§10)

### [2026-06-10] 기존부채 — mypy 전역 설정 부재 / passlib 스텁 에러
- 위치: app/core/security.py:5 (이번 작업 외), pyproject.toml(설정 없음)
- 설명: mypy 설정이 없어 서드파티 스텁 누락이 에러로 남음. 내 신규 코드는 pandas/fdr import에 인라인 `# type: ignore[import-untyped]`로 처리했으나 근본 설정은 없음. develop에서도 passlib 에러 존재.
- 위험도: 낮음
- 후속: [tool.mypy] ignore_missing_imports 또는 types-passlib/pandas-stubs 도입

## 해결됨

### [2026-06-10] 임시구현 — IndicatorSet cross/divergence 마커 빈 배열 (B2에서 해결)
- 위치: app/services/stock_service.py _build_indicator_set
- 설명: B1에서 crossMarkers/divergenceMarkers를 빈 배열로 반환하던 것을, B2 시그널 탐지(app/services/signal_detector.py)와 계산 공유해 채움.
