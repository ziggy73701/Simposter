import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..config import settings
from ..schemas import UISettings

router = APIRouter()

_settings_file = Path(settings.SETTINGS_DIR) / "ui_settings.json"
_legacy_settings_file = Path(settings.CONFIG_DIR) / "ui_settings.json"


def _default_ui_settings() -> UISettings:
    """Defaults seeded from environment to make docker-compose setup easier."""
    return UISettings(
        plex={
            "url": settings.PLEX_URL,
            "token": settings.PLEX_TOKEN,
            "movieLibraryName": settings.PLEX_MOVIE_LIBRARY_NAME,
        },
        tmdb={"apiKey": getattr(settings, "TMDB_API_KEY", "")},
        tvdb={"apiKey": "", "comingSoon": True},
    )


def _read_settings() -> UISettings:
    """
    Read settings from disk, creating the file with defaults if missing.
    Mirrors the simple JSON read/write pattern we use for presets.
    """
    try:
        if not _settings_file.exists() and _legacy_settings_file.exists():
            try:
                _settings_file.parent.mkdir(parents=True, exist_ok=True)
                _legacy_settings_file.replace(_settings_file)
            except OSError:
                data = json.loads(_legacy_settings_file.read_text(encoding="utf-8"))
                _settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

        if not _settings_file.exists():
            defaults = _default_ui_settings().model_dump(
                exclude_none=False, exclude_defaults=False, exclude_unset=False
            )
            _settings_file.parent.mkdir(parents=True, exist_ok=True)
            _settings_file.write_text(json.dumps(defaults, indent=2), encoding="utf-8")
            return UISettings(**defaults)

        data = json.loads(_settings_file.read_text(encoding="utf-8"))
        # Merge with defaults so newly added fields are included (nested merge for settings groups)
        defaults = _default_ui_settings().model_dump(exclude_none=False, exclude_defaults=False)
        merged = {**defaults, **data}
        for nested_key in ("plex", "tmdb", "tvdb"):
            merged[nested_key] = {**defaults.get(nested_key, {}), **data.get(nested_key, {})}

        if merged != data:
            _settings_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        return UISettings(**merged)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read settings: {e}")


@router.get("/ui-settings")
def get_ui_settings():
    settings_obj = _read_settings()
    return JSONResponse(content=settings_obj.model_dump(exclude_none=False, exclude_defaults=False, exclude_unset=False))


@router.post("/ui-settings")
def save_ui_settings(payload: UISettings):
    try:
        _settings_file.parent.mkdir(parents=True, exist_ok=True)
        # Merge defaults + current file + incoming payload to avoid losing fields
        defaults = _default_ui_settings().model_dump(exclude_none=False, exclude_defaults=False, exclude_unset=False)
        current = _read_settings().model_dump(
            exclude_none=False, exclude_defaults=False, exclude_unset=False
        )
        incoming = payload.model_dump(
            exclude_none=False, exclude_defaults=False, exclude_unset=False
        )
        merged = {**defaults, **current, **incoming}
        for nested_key in ("plex", "tmdb", "tvdb"):
            merged[nested_key] = {
                **defaults.get(nested_key, {}),
                **current.get(nested_key, {}),
                **incoming.get(nested_key, {}),
            }

        _settings_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        return merged
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {e}")
