from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SageStock Backend"
    VERSION: str = "0.1.0"
    # api-spec Base URL: https://api.sagestock.app/v1 → 프리픽스는 /v1
    API_V1_PREFIX: str = "/v1"

    # 환경 의존 값 (.env). DB 미연결이어도 앱은 부팅됨(엔진은 lazy).
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sagestock"
    SECRET_KEY: str = "change-me-in-env-with-a-long-random-secret-key"

    # 토큰 수명 (feature-spec D8): access 30분, refresh 14일.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    BACKEND_CORS_ORIGINS: list[str] = []

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
