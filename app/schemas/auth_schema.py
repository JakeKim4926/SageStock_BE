from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    # 와이어 포맷은 camelCase(api-spec §1). 내부는 snake_case 유지.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SignupRequest(_CamelModel):
    # 1인 전용 앱 — 로그인 식별자는 이메일 형식을 강제하지 않는다(아이디 허용).
    email: str
    password: str
    name: str


class LoginRequest(_CamelModel):
    email: str
    password: str
    auto_login: bool = False


class RefreshRequest(_CamelModel):
    refresh_token: str


class LogoutRequest(_CamelModel):
    refresh_token: str


class TokenResponse(_CamelModel):
    access_token: str
    refresh_token: str
    access_expires_in: int


class AccessTokenResponse(_CamelModel):
    access_token: str
    access_expires_in: int
