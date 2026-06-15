"""SageStock 지표 엔진.

`D:\\Projects\\SageStock_AI\\SageStock.py`(오프라인 연구용 엔진)를 거의 그대로 이식한다
(feature-spec §4.2 "거의 그대로 이식"). 원본 메서드는 비파괴로 유지하고, 차트 표시용
다기간 EMA 시리즈만 별도 메서드(`Make_Chart_Emas`)로 추가한다.

원본은 모델 입력용 단일값 피처(BB_PercentB, 정규화 MACD 등)를 만든다 — 이들 메서드는
예측(B5)에서 쓰며, B1 차트는 이 중 밴드/스토캐스틱/RSI/이격도 시리즈만 사용한다.
"""

RSI_PERIOD = 14
DISPARITY_PERIOD = 20
BOLLINGER_BANDS_PERIOD = 20
BOLLINGER_STD_DEV_FACTOR = 2


class SageStock:
    def __init__(self, df):
        if 'Close' not in df.columns:
            raise ValueError("df에는 'Close' 컬럼이 필요합니다.")

        self.df = df.copy()

    def Make_RSI(self, period=RSI_PERIOD):
        # 1. 전일 대비 변동폭 계산
        delta = self.df['Close'].diff(1)

        # 2. 상승분(up)과 하락분(down)의 분리
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)

        # 3. 지수 이동 평균(EMA)으로 평균 상승/하락 강도 계산
        # com=period-1이면 alpha = 1 / period 이므로 웰즈 와일더 방식에 가까움
        au = up.ewm(
            com=period - 1,
            min_periods=period,
            adjust=False
        ).mean()

        ad = down.ewm(
            com=period - 1,
            min_periods=period,
            adjust=False
        ).mean()

        # 4. 상대강도(RS) 계산 및 RSI 변환
        rs = au / ad
        self.df['RSI'] = 100 - (100 / (1 + rs))

        return self

    def Make_Disparity_EMA(self, period=DISPARITY_PERIOD):
        # 1. 20일 지수이동평균선 계산
        ema = self.df['Close'].ewm(
            span=period,
            adjust=False,
            min_periods=period
        ).mean()

        # 2. 이격도 계산 ((주가 / 이평선) * 100)
        self.df['EMA20'] = ema
        self.df['Disparity_EMA20'] = (self.df['Close'] / ema) * 100

        return self

    def Make_Bollinger_Bands(
        self,
        period=BOLLINGER_BANDS_PERIOD,
        std_dev_factor=BOLLINGER_STD_DEV_FACTOR
    ):
        # 1. 중심선 계산
        self.df['BB_MA20'] = self.df['Close'].rolling(window=period).mean()

        # 2. 표준편차 계산
        std_dev = self.df['Close'].rolling(window=period).std()

        # 3. 상한선 및 하한선 계산
        self.df['BB_Upper'] = self.df['BB_MA20'] + (std_dev * std_dev_factor)
        self.df['BB_Lower'] = self.df['BB_MA20'] - (std_dev * std_dev_factor)

        # 4. 상대값 피처 (절대 가격은 비정상이라 모델 일반화 불가 → 상대값 사용)
        #    %B: 밴드 내 위치(0=하한, 1=상한), Bandwidth: 변동성(밴드폭 / 중심선)
        band_width = self.df['BB_Upper'] - self.df['BB_Lower']
        self.df['BB_PercentB'] = (self.df['Close'] - self.df['BB_Lower']) / band_width
        self.df['BB_Bandwidth'] = band_width / self.df['BB_MA20']

        return self

    def Make_Returns(self, periods=(1, 5, 10, 20)):
        # 다기간 누적 수익률 (%). 가격 차이가 아닌 비율이라 정상(stationary)
        for p in periods:
            self.df[f'Return_{p}'] = self.df['Close'].pct_change(p) * 100

        return self

    def Make_Volatility(self, period=20):
        # 일간 수익률의 변동성 (rolling std). 변동성 국면을 모델에 전달
        daily_ret = self.df['Close'].pct_change()
        self.df['Volatility_20'] = daily_ret.rolling(window=period).std() * 100

        return self

    def Make_Volume(self, period=20):
        # 거래량 자체는 비정상 → 평균 대비 비율로 정규화 (거래량 급증 포착)
        vol_ma = self.df['Volume'].rolling(window=period).mean()
        self.df['Volume_Ratio'] = self.df['Volume'] / vol_ma

        return self

    def Make_Squeeze(self, period=60):
        # 변동성 압축: 최근 period 내 밴드폭의 상대 위치(0=최저=압축, 1=최고=확장).
        # 압축(낮은 값) 뒤 분출이 잦아 급등 전조로 쓴다. Make_Bollinger_Bands 후 호출.
        bw = self.df['BB_Bandwidth']
        bw_min = bw.rolling(window=period).min()
        bw_max = bw.rolling(window=period).max()
        self.df['BB_Squeeze'] = (bw - bw_min) / (bw_max - bw_min)

        return self

    def Make_MACD(self, fast=12, slow=26, signal=9):
        ema_fast = self.df['Close'].ewm(span=fast, adjust=False).mean()
        ema_slow = self.df['Close'].ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()

        # MACD는 가격 단위라 비정상 → Close로 나눠 정규화 (%)
        self.df['MACD'] = (macd / self.df['Close']) * 100
        self.df['MACD_Hist'] = ((macd - macd_signal) / self.df['Close']) * 100

        return self

    def Make_Stochastic(self, period=14, smooth=3):
        # %K, %D 모두 0~100 범위로 이미 정상
        low_min = self.df['Low'].rolling(window=period).min()
        high_max = self.df['High'].rolling(window=period).max()

        percent_k = (self.df['Close'] - low_min) / (high_max - low_min) * 100
        self.df['Stoch_K'] = percent_k
        self.df['Stoch_D'] = percent_k.rolling(window=smooth).mean()

        return self

    def Make_Chart_Emas(self, spans=(5, 20, 60, 120)):
        # 차트 표시용 다기간 EMA 시리즈(원본 비파괴 추가, feature-spec §4.2 ema5/60/120 확장).
        # 원본은 EMA20만 만든다 → 차트는 ema5/20/60/120 배열이 필요.
        for span in spans:
            self.df[f'EMA{span}'] = self.df['Close'].ewm(
                span=span,
                adjust=False,
                min_periods=span,
            ).mean()

        return self

    def Make_All_Indicators(self):
        self.Make_RSI()
        self.Make_Disparity_EMA()
        self.Make_Bollinger_Bands()
        self.Make_Returns()
        self.Make_Volatility()
        self.Make_Volume()
        self.Make_Squeeze()  # BB_Bandwidth 의존 → Bollinger 이후
        self.Make_MACD()
        self.Make_Stochastic()

        return self

    def Drop_Na(self):
        # 분모 0(완전 평탄 구간 등)으로 생긴 inf를 NaN으로 바꿔 함께 제거.
        # (dropna는 inf를 거르지 못해 XGBoost에 inf가 유입될 수 있음)
        import numpy as np
        self.df = self.df.replace([np.inf, -np.inf], np.nan).dropna()

        return self

    def Get_DataFrame(self):
        return self.df
