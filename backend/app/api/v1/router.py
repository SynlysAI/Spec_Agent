"""V1 路由聚合模块。"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi import Depends

from app.api.v1.endpoints.acceptance import router as acceptance_router
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.chemistry import router as chemistry_router
from app.api.v1.endpoints.consistency import router as consistency_router
from app.api.v1.endpoints.dialogue import router as dialogue_router
from app.api.v1.endpoints.files import router as files_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.lab_collect import router as lab_collect_router
from app.api.v1.endpoints.lcms_convert import router as lcms_convert_router
from app.api.v1.endpoints.nmr_server import router as nmr_server_router
from app.api.v1.endpoints.raman_capture import router as raman_capture_router
from app.api.v1.endpoints.spectra import router as spectra_router
from app.api.v1.endpoints.tasks import router as tasks_router
from app.core.auth import require_authenticated
from app.core.auth import require_admin

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(files_router, dependencies=[Depends(require_authenticated)])
api_router.include_router(tasks_router, dependencies=[Depends(require_authenticated)])
api_router.include_router(lab_collect_router, dependencies=[Depends(require_admin)])
api_router.include_router(nmr_server_router, dependencies=[Depends(require_authenticated)])
api_router.include_router(raman_capture_router, dependencies=[Depends(require_authenticated)])
api_router.include_router(lcms_convert_router, dependencies=[Depends(require_authenticated)])
api_router.include_router(chemistry_router, dependencies=[Depends(require_authenticated)])
api_router.include_router(spectra_router, dependencies=[Depends(require_authenticated)])
api_router.include_router(dialogue_router, dependencies=[Depends(require_authenticated)])
api_router.include_router(acceptance_router, dependencies=[Depends(require_admin)])
api_router.include_router(consistency_router, dependencies=[Depends(require_admin)])
