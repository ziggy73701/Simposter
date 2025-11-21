# backend/tmdb_client.py
import os
from typing import Dict, Any, List

import requests

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"


class TMDBError(Exception):
    pass


def _tmdb_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if not TMDB_API_KEY:
        raise TMDBError("TMDB_API_KEY not set")

    url = f"{TMDB_API_BASE}{path}"
    params = dict(params)
    params["api_key"] = TMDB_API_KEY

    r = requests.get(url, params=params, timeout=15)
    if not r.ok:
        raise TMDBError(f"TMDb HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def _make_img_url(file_path: str, size: str = "original") -> str:
    # size examples: w342, w500, w780, original
    return f"{TMDB_IMG_BASE}/{size}{file_path}"


def _build_image_entry(p: Dict[str, Any], kind: str) -> Dict[str, Any]:
    """
    kind: 'poster' | 'backdrop' | 'logo'
    """
    path = p.get("file_path")
    if not path:
        return {}

    lang = p.get("iso_639_1")
    width = p.get("width")
    height = p.get("height")

    if kind == "logo":
        thumb_size = "w300"
    elif kind == "backdrop":
        thumb_size = "w780"
    else:
        # posters
        thumb_size = "w342"

    return {
        "url": _make_img_url(path, "original"),
        "thumb": _make_img_url(path, thumb_size),
        "width": width,
        "height": height,
        "language": lang,
        "has_text": bool(lang),
    }


def get_images_for_movie(tmdb_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return structured posters / backdrops / logos for a movie.

    Each entry has:
      - url        : full-size image
      - thumb      : smaller preview
      - width/height
      - language   : 'en', 'fr', None, ...
      - has_text   : heuristic: language != None
    """
    data = _tmdb_get(
        f"/movie/{tmdb_id}/images",
        {
            "include_image_language": "en,null",
        },
    )

    posters: List[Dict[str, Any]] = []
    for p in data.get("posters", []):
        entry = _build_image_entry(p, "poster")
        if entry:
            posters.append(entry)

    backdrops: List[Dict[str, Any]] = []
    for b in data.get("backdrops", []):
        entry = _build_image_entry(b, "backdrop")
        if entry:
            backdrops.append(entry)

    logos: List[Dict[str, Any]] = []
    for l in data.get("logos", []):
        entry = _build_image_entry(l, "logo")
        if entry:
            logos.append(entry)

    return {
        "posters": posters,
        "backdrops": backdrops,
        "logos": logos,
    }
