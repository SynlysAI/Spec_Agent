"""化学结构图片接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from app.services.chem_image_service import chem_image_service

router = APIRouter(prefix="/chemistry", tags=["chemistry"])


@router.get("/molecule-image")
def get_molecule_image(
    smiles: str = Query(..., description="分子 SMILES"),
    size: int = Query(default=320, ge=120, le=1024, description="图片宽高像素"),
) -> Response:
    """根据 SMILES 返回分子结构 PNG 图片。

    Args:
        smiles: 分子 SMILES 字符串。
        size: 图片尺寸。

    Returns:
        PNG 图片二进制响应。
    """
    try:
        image_bytes = chem_image_service.render_smiles_png(smiles=smiles, size=size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/function-group-image")
def get_function_group_image(
    smarts: str = Query(..., description="官能团 SMARTS"),
    size: int = Query(default=280, ge=120, le=1024, description="图片宽高像素"),
) -> Response:
    """根据 SMARTS 返回官能团结构 PNG 图片。

    Args:
        smarts: 官能团 SMARTS 字符串。
        size: 图片尺寸。

    Returns:
        PNG 图片二进制响应。
    """
    try:
        image_bytes = chem_image_service.render_smarts_png(smarts=smarts, size=size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
