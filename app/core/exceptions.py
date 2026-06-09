import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.constants import error_codes

logger = logging.getLogger(__name__)

# 프레임워크 레벨 HTTP 에러(라우팅 404, 405 등)도 api-spec §0 envelope로 통일.
_STATUS_TO_CODE: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: error_codes.INVALID_REQUEST,
    status.HTTP_401_UNAUTHORIZED: error_codes.UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: error_codes.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: error_codes.DATA_NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: error_codes.INVALID_REQUEST,
}


class AppError(Exception):
    """도메인 예외. api-spec §0 에러 바디 {code, message}로 매핑된다."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _error_body(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_body(error_codes.INVALID_REQUEST, "요청 파라미터가 올바르지 않습니다."),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, error_codes.INTERNAL_ERROR)
        message = exc.detail if isinstance(exc.detail, str) else code
        return JSONResponse(status_code=exc.status_code, content=_error_body(code, message))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(error_codes.INTERNAL_ERROR, "서버 오류가 발생했습니다."),
        )
