# backend/main.py
import base64
import os
import re
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Any, Dict, List, Optional
from fastapi import APIRouter
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from PIL import Image

from .templates import list_templates, get_renderer
from .tmdb_client import get_images_for_movie, TMDBError

import json

# ---------------- Environment ----------------

PLEX_URL = os.getenv("PLEX_URL", "http://localhost:32400")
PLEX_TOKEN = os.getenv("PLEX_TOKEN", "")
PLEX_MOVIE_LIB_ID = os.getenv("PLEX_MOVIE_LIB_ID", "1")

OUTPUT_ROOT = os.getenv("OUTPUT_ROOT", "/poster-outputs")

# ---------------- FastAPI ----------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

def load_presets():
    path = os.path.join(os.path.dirname(__file__), "presets.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------- Data Models ----------------

class Movie(BaseModel):
    key: str
    title: str
    year: Optional[int] = None


class MovieTMDbResponse(BaseModel):
    tmdb_id: Optional[int]


class PreviewRequest(BaseModel):
    template_id: str
    background_url: str
    logo_url: Optional[str] = None
    options: Optional[Dict[str, Any]] = None


class SaveRequest(PreviewRequest):
    movie_title: str
    movie_year: Optional[int] = None
    filename: Optional[str] = "poster.jpg"

class PresetSaveRequest(BaseModel):
    preset_id: str
    options: Dict[str, Any]

class PlexUploadRequest(BaseModel):
    rating_key: str
    background_url: str
    logo_url: Optional[str] = None
    options: Optional[Dict[str, Any]] = None
    filename: Optional[str] = "poster.jpg"



# ---------------- Helpers ----------------

def _plex_headers() -> Dict[str, str]:
    return {"X-Plex-Token": PLEX_TOKEN}


def _get_plex_movies() -> List[Movie]:
    url = f"{PLEX_URL}/library/sections/{PLEX_MOVIE_LIB_ID}/all?type=1"
    r = requests.get(url, headers=_plex_headers(), timeout=15)
    r.raise_for_status()

    root = ET.fromstring(r.text)
    movies: List[Movie] = []

    for video in root.findall(".//Video"):
        key = video.get("ratingKey")
        title = video.get("title") or ""
        year = video.get("year")
        movies.append(Movie(key=key, title=title, year=int(year) if year else None))

    # You mentioned preferring most-recent first; Plex returns newest last,
    # so we reverse to show most recently added at the top.
    movies.reverse()
    return movies


def extract_tmdb_id_from_metadata(xml_text: str) -> Optional[int]:
    if xml_text.startswith("<html"):
        return None

    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None

    for guid in root.findall(".//Guid"):
        gid = guid.get("id") or ""
        match = re.search(r"(?:tmdb|themoviedb)://(\d+)", gid)
        if match:
            return int(match.group(1))

    return None


def get_movie_tmdb_id(rating_key: str) -> Optional[int]:
    url = f"{PLEX_URL}/library/metadata/{rating_key}"
    r = requests.get(url, headers=_plex_headers(), timeout=10)
    r.raise_for_status()
    return extract_tmdb_id_from_metadata(r.text)


def _download_image(url: str) -> Optional[Image.Image]:
    try:
        r = requests.get(url, timeout=12, allow_redirects=True)
        r.raise_for_status()

        data = BytesIO(r.content)

        # Try WebP → JPG conversion if needed
        try:
            img = Image.open(data)
            img.load()
        except Exception:
            # sometimes TMDb returns weird headers
            return None

        # Always convert to RGBA for safe processing
        return img.convert("RGBA")

    except Exception as e:
        print(f"[WARN] Failed to load image: {url} → {e}")
        return None




# ---------------- API Routes ----------------

@app.get("/api/templates")
def api_templates():
    """
    Returns template groups + presets from presets.json:
    [
      { id, name, description, presets: [ {id, name, options}, ... ] },
      ...
    ]
    """
    return list_templates()

@app.get("/api/presets")
def api_presets():
    return load_presets()

@app.get("/api/movies", response_model=List[Movie])
def api_movies():
    return _get_plex_movies()


@app.get("/api/movie/{rating_key}/tmdb", response_model=MovieTMDbResponse)
def api_movie_tmdb(rating_key: str):
    tmdb_id = get_movie_tmdb_id(rating_key)
    return MovieTMDbResponse(tmdb_id=tmdb_id)


@app.get("/api/tmdb/{tmdb_id}/images")
def api_tmdb_images(tmdb_id: int):
    try:
        return get_images_for_movie(tmdb_id)
    except TMDBError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/preview")
def api_preview(req: PreviewRequest):
    bg = _download_image(req.background_url)
    logo = _download_image(req.logo_url) if req.logo_url else None

    renderer = get_renderer(req.template_id)
    img = renderer(bg, logo, req.options or {})

    buf = BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=95)
    return {"image_base64": base64.b64encode(buf.getvalue()).decode()}


@app.post("/api/save")
def api_save(req: SaveRequest):
    bg = _download_image(req.background_url)
    logo = _download_image(req.logo_url) if req.logo_url else None

    renderer = get_renderer(req.template_id)
    img = renderer(bg, logo, req.options or {})

    # Folder name: "Movie Title (Year)" or just title
    folder = f"{req.movie_title} ({req.movie_year})" if req.movie_year else req.movie_title
    folder = "".join(c for c in folder if c.isalnum() or c in " _-()")
    out_dir = os.path.join(OUTPUT_ROOT, folder)
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, req.filename or "poster.jpg")
    img.convert("RGB").save(out_path, "JPEG", quality=95)
    return {"status": "ok", "path": out_path}
    



@app.post("/api/send_to_plex")
def api_send_to_plex(req: PlexUploadRequest):
    bg = _download_image(req.background_url)
    if bg is None:
        raise HTTPException(status_code=400, detail="Invalid background image.")

    logo = _download_image(req.logo_url) if req.logo_url else None

    renderer = get_renderer("default")
    img = renderer(bg, logo, req.options or {})

    buf = BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=95)
    payload = buf.getvalue()

    # Upload as LOCAL POSTER
    upload_url = f"{PLEX_URL}/library/metadata/{req.rating_key}/posters"
    headers = {
        "X-Plex-Token": PLEX_TOKEN,
        "Content-Type": "image/jpeg"
    }

    r = requests.post(upload_url, headers=headers, data=payload)
    if r.status_code not in (200, 201, 204):
        raise HTTPException(status_code=500, detail=f"Plex upload failed: {r.text}")
    # ---------------------------
    # Remove Plex label "overlay"
    # ---------------------------
    remove_label_url = f"{PLEX_URL}/library/metadata/{req.rating_key}?label[0].tag.overlay="
    requests.put(remove_label_url, headers={"X-Plex-Token": PLEX_TOKEN})
    return {"status": "ok", "message": "Poster sent to Plex."}

@app.post("/api/presets/save")
def api_save_preset(req: PresetSaveRequest):
    preset_id = req.preset_id
    options = req.options

    try:
        with open("backend/presets.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"default": {"presets": []}}

    presets = data.setdefault("default", {}).setdefault("presets", [])

    # overwrite existing if found
    existing = next((p for p in presets if p["id"] == preset_id), None)

    if existing:
        existing["options"] = options
    else:
        presets.append({
            "id": preset_id,
            "name": preset_id,
            "options": options
        })

    with open("backend/presets.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return {"message": f"Preset '{preset_id}' saved."}
