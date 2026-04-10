"""FastAPI 应用入口。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.v1.router import api_router
from app.core.config import settings


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。

    函数名称: create_app
    参数说明:
    - 无。
    """
    app = FastAPI(
        title="Spec_Agent Backend",
        version="0.1.0",
        description="Spec_Agent 重构项目后端服务（P0骨架）。",
    )

    app.include_router(api_router, prefix=settings.api_prefix)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    return app


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """请求参数校验异常处理器。

    函数名称: validation_exception_handler
    参数说明:
    - request: 当前请求对象。
    - exc: 参数校验异常对象。
    """
    return JSONResponse(
        status_code=422,
        content={
            "code": 40001,
            "message": "invalid parameter",
            "data": {"errors": exc.errors(), "path": str(request.url.path)},
        },
    )


app = create_app()

