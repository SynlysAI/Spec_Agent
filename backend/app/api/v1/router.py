"""V1 路由聚合模块。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.acceptance import router as acceptance_router
from app.api.v1.endpoints.chemistry import router as chemistry_router
from app.api.v1.endpoints.dialogue import router as dialogue_router
from app.api.v1.endpoints.files import router as files_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.nmr_server import router as nmr_server_router
from app.api.v1.endpoints.spectra import router as spectra_router
from app.api.v1.endpoints.tasks import router as tasks_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(files_router)
api_router.include_router(tasks_router)
api_router.include_router(nmr_server_router)
api_router.include_router(chemistry_router)
api_router.include_router(spectra_router)
api_router.include_router(dialogue_router)
api_router.include_router(acceptance_router)
