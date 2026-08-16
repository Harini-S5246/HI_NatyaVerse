from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "BAD_REQUEST", extra: dict | None = None):
        self.message, self.status_code, self.code, self.extra = message, status_code, code, extra or {}

def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"message": exc.message, "code": exc.code, **exc.extra})
