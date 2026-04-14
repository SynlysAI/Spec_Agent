"""FastAPI 应用入口。"""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from app.api.v1.router import api_router
from app.core.config import settings


def _resolve_request_id(request: Request) -> str:
    """解析请求追踪 ID。

    Args:
        request: 当前请求对象。

    Returns:
        请求追踪 ID；若请求头未提供则自动生成。
    """
    header_request_id = request.headers.get("x-request-id")
    if header_request_id:
        return header_request_id
    return uuid4().hex


def _map_http_error(status_code: int) -> tuple[int, str]:
    """映射 HTTP 状态到统一错误语义。

    Args:
        status_code: HTTP 状态码。

    Returns:
        业务错误码与错误消息元组。
    """
    if status_code == 400:
        return 40001, "invalid parameter"
    if status_code == 404:
        return 40401, "resource not found"
    if status_code == 422:
        return 42201, "validation failed"
    if status_code == 502:
        return 50201, "upstream service error"
    if status_code == 504:
        return 50401, "upstream timeout"
    return 50001, "internal error"


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(
        title="Spec_Agent Backend",
        version="0.1.0",
        description="Spec_Agent 重构项目后端服务（P0）。",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
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
    request_id = _resolve_request_id(request)
    return JSONResponse(
        status_code=422,
        content={
            "code": 42201,
            "message": "validation failed",
            "data": {
                "detail": "request validation failed",
                "errors": exc.errors(),
                "path": str(request.url.path),
            },
            "request_id": request_id,
        },
        headers={"X-Request-Id": request_id},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """处理 HTTPException 并统一错误码。

    Args:
        request: 当前请求对象。
        exc: HTTP 异常对象。

    Returns:
        统一错误响应。
    """
    code, message = _map_http_error(exc.status_code)
    request_id = _resolve_request_id(request)

    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code,
            "message": message,
            "data": {"detail": detail, "path": str(request.url.path)},
            "request_id": request_id,
        },
        headers={"X-Request-Id": request_id},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理未捕获异常。

    Args:
        request: 当前请求对象。
        exc: 未捕获异常对象。

    Returns:
        统一错误响应。
    """
    request_id = _resolve_request_id(request)
    return JSONResponse(
        status_code=500,
        content={
            "code": 50001,
            "message": "internal error",
            "data": {"detail": str(exc), "path": str(request.url.path)},
            "request_id": request_id,
        },
        headers={"X-Request-Id": request_id},
    )


app = create_app()
