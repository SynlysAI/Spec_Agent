"""FastAPI 应用入口。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from app.api.v1.router import api_router
from app.core.config import settings


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(
        title="Spec_Agent Backend",
        version="0.1.0",
        description="Spec_Agent 重构项目后端服务（P0）。",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)
    app.mount("/static/outputs", StaticFiles(directory=settings.outputs_root), name="outputs")
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    return app


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """处理请求参数校验异常。

    Args:
        request: 当前请求对象。
        exc: 参数校验异常对象。

    Returns:
        统一错误响应。
    """
    return JSONResponse(
        status_code=422,
        content={
            "code": 40001,
            "message": "invalid parameter",
            "data": {"errors": exc.errors(), "path": str(request.url.path)},
            "request_id": None,
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """处理 HTTPException 并统一错误码。

    Args:
        request: 当前请求对象。
        exc: HTTP 异常对象。

    Returns:
        统一错误响应。
    """
    if exc.status_code == 404:
        code = 40401
        message = "task not found"
    elif exc.status_code == 400:
        code = 40001
        message = "invalid parameter"
    else:
        code = 50001
        message = "internal error"

    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code,
            "message": message,
            "data": {"detail": detail, "path": str(request.url.path)},
            "request_id": None,
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理未捕获异常。

    Args:
        request: 当前请求对象。
        exc: 未捕获异常对象。

    Returns:
        统一错误响应。
    """
    return JSONResponse(
        status_code=500,
        content={
            "code": 50001,
            "message": "internal error",
            "data": {"detail": str(exc), "path": str(request.url.path)},
            "request_id": None,
        },
    )


app = create_app()
