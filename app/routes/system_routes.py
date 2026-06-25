from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["System"])


@router.get("/", summary="Health check")
def health_check() -> dict[str, str]:
    return {"status": "ok", "app": get_settings().app_name}