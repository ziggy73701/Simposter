from fastapi import APIRouter

from . import (
    presets,
    templates,
    movies,
    plexsend,
    preview,
    save,
    batch,
    uploads,
    logs,
    webhooks,
    ui_settings,
)

router = APIRouter()

router.include_router(presets.router)
router.include_router(templates.router)
router.include_router(movies.router)
router.include_router(plexsend.router)
router.include_router(preview.router)
router.include_router(save.router)
router.include_router(batch.router)
router.include_router(uploads.router)
router.include_router(logs.router)
router.include_router(webhooks.router)
router.include_router(ui_settings.router)
