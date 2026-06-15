from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SageStock Backend"
    VERSION: str = "0.1.0"
    # api-spec Base URL: https://api.sagestock.app/v1 → 프리픽스는 /v1
    API_V1_PREFIX: str = "/v1"

    # 공개 루트 호스트(스킴+호스트, /v1 미포함). 환경별로 달라 env로 둔다.
    # OpenAPI servers에 사용 → Swagger가 환경별 올바른 호스트를 가리킨다.
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # 환경 의존 값 (.env). DB 미연결이어도 앱은 부팅됨(엔진은 lazy).
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sagestock"
    SECRET_KEY: str = "change-me-in-env-with-a-long-random-secret-key"

    # 토큰 수명 (feature-spec D8): access 30분, refresh 14일.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # 한국투자증권(KIS) Open API — 국내(KR) 실시간 현재가.
    # 키 미설정 시 fdr 일봉(지연 시세)으로 폴백 → 앱은 키 없이도 동작.
    KIS_APP_KEY: str = ""
    KIS_APP_SECRET: str = ""
    KIS_BASE_URL: str = "https://openapi.koreainvestment.com:9443"

    BACKEND_CORS_ORIGINS: list[str] = []

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
