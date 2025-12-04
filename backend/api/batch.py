import os
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import requests
import yaml
from fastapi import APIRouter

from backend.assets.selection import pick_logo, pick_poster
from ..config import (
    get_movie_tmdb_id,
    load_presets,
    logger,
    plex_remove_label,
    settings,
)
from ..rendering import render_poster_image
from ..schemas import BatchRequest
from ..tmdb_client import get_images_for_movie, get_movie_details

router = APIRouter()


def _normalize_bucket(title: str) -> str:
    """Derive the bucket letter/number for YAML output."""

    trimmed_title = (title or "").lstrip()
    if trimmed_title.lower().startswith("the "):
        trimmed_title = trimmed_title[4:].lstrip()

    for char in trimmed_title:
        if char.isalpha():
            return char.lower()
        if char.isdigit():
            return "0"

    return "_"


def _poster_filename(title: str, year: str | int | None) -> tuple[str, str]:
    """Return the folder letter and sanitized filename for poster output."""

    trimmed_title = title.lstrip()
    if trimmed_title.lower().startswith("the "):
        trimmed_title = trimmed_title[4:].lstrip()

    folder_letter = next((c for c in trimmed_title if c.isalpha()), "_")
    folder_letter = folder_letter.lower() if folder_letter.isalpha() else "_"

    safe_title = "".join(c for c in title if c.isalnum() or c in " _-()")
    filename = f"{safe_title} ({year}).jpg" if year else f"{safe_title}.jpg"

    return folder_letter, filename


@router.post("/batch")
def api_batch(req: BatchRequest):

    results = []
    yaml_entries: dict[str, dict] = defaultdict(dict)

    render_options = dict(req.options or {})

    poster_filter = render_options.get("poster_filter", "all")
    logo_preference = render_options.get("logo_preference", "first")

    if req.preset_id:
        presets = load_presets()
        template_presets = presets.get(req.template_id, {}).get("presets", [])
        preset = next((p for p in template_presets if p.get("id") == req.preset_id), None)

        if preset:
            preset_options = preset.get("options", {})
            render_options = {**render_options, **preset_options}
            poster_filter = render_options.get("poster_filter", poster_filter)
            logo_preference = render_options.get("logo_preference", logo_preference)
            logger.debug(
                "[BATCH] Applied preset '%s' options: %s", req.preset_id, preset_options
            )
        else:
            logger.warning(
                "[BATCH] Preset '%s' not found for template '%s'", req.preset_id, req.template_id
            )

    base_render_options = dict(render_options)

    yaml_root = Path(settings.OUTPUT_ROOT) / "batch_yaml"

    for rating_key in req.rating_keys:
        try:
            logger.info("[BATCH] Start rating_key=%s template=%s", rating_key, req.template_id)

            # ---------------------------
            # TMDb Fetch
            # ---------------------------
            tmdb_id = get_movie_tmdb_id(rating_key)
            if not tmdb_id:
                raise Exception("No TMDb ID found.")
            logger.debug("[BATCH] rating_key=%s tmdb_id=%s", rating_key, tmdb_id)

            imgs = get_images_for_movie(tmdb_id)
            posters = imgs.get("posters", [])
            logos = imgs.get("logos", [])
            logger.debug(
                "[BATCH] rating_key=%s posters=%d logos=%d filter=%s logo_pref=%s",
                rating_key,
                len(posters),
                len(logos),
                poster_filter,
                logo_preference,
            )

            # Fetch movie details for template variables
            movie_details = get_movie_details(tmdb_id)
            logger.debug("[BATCH] Movie details: title='%s' year=%s", movie_details.get("title"), movie_details.get("year"))

            # ---------------------------
            # Auto-select assets
            # ---------------------------
            render_options = dict(base_render_options)

            logo_mode = render_options.get("logo_mode", "first")

            poster = pick_poster(posters, poster_filter)
            logo = pick_logo(logos, logo_preference) if logo_mode != "none" else None
            
            if not poster:
                raise Exception("No valid poster found.")

            poster_url = poster.get("url")
            logo_url = logo.get("url") if logo else None
            logger.info(f"[BATCH] Picked logo pref={logo_preference}")
            logger.info(f"[BATCH] Picked poster={poster_url}")
            logger.info(f"[BATCH] Picked logo={logo_url}")
            # ---------------------------
            # Render for EACH MOVIE
            # ---------------------------
            # Add movie details to options for template variable substitution
            render_options["movie_title"] = movie_details.get("title", "")
            if movie_details.get("year"):
                render_options["movie_year"] = str(movie_details.get("year"))

            img = render_poster_image(
                req.template_id,
                poster_url,
                logo_url,
                render_options,
            )

            # ---------------------------
            # Save locally (if requested)
            # ---------------------------
            save_path = None
            poster_relative_path = None
            should_save_image = req.save_locally or req.generate_yaml

            # Get movie info for filename
            movie_title = movie_details.get("title", rating_key)
            movie_year = movie_details.get("year", "")

            if should_save_image:
                folder_letter, filename = _poster_filename(movie_title, movie_year)

                # Save to output directory
                out_dir = os.path.join(settings.OUTPUT_ROOT, "batch", folder_letter)
                os.makedirs(out_dir, exist_ok=True)
                save_path = os.path.join(out_dir, filename)

                img.convert("RGB").save(save_path, "JPEG", quality=95)
                poster_relative_path = os.path.relpath(save_path, settings.OUTPUT_ROOT).replace(os.sep, "/")
                logger.info(f"[BATCH] Saved locally: {save_path}")

            # ---------------------------
            # Upload to Plex (if requested)
            # ---------------------------
            if req.send_to_plex:
                buf = BytesIO()
                img.convert("RGB").save(buf, "JPEG", quality=95)
                payload = buf.getvalue()

                plex_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/posters"
                headers = {
                    "X-Plex-Token": settings.PLEX_TOKEN,
                    "Content-Type": "image/jpeg",
                }

                r = requests.post(plex_url, headers=headers, data=payload, timeout=20)
                r.raise_for_status()

                # Label removal
                for label in req.labels or []:
                    plex_remove_label(rating_key, label)

                logger.info(f"[BATCH] Uploaded to Plex: {rating_key}")

            result = {
                "rating_key": rating_key,
                "poster_used": poster_url,
                "logo_used": logo_url,
                "status": "ok",
            }
            if save_path:
                result["save_path"] = save_path
            results.append(result)

            # Collect YAML metadata if requested
            if req.generate_yaml:
                bucket = _normalize_bucket(movie_title)
                entry = {
                    "title": movie_title,
                    "year": movie_year,
                }

                if poster_relative_path:
                    entry["file_poster"] = poster_relative_path

                yaml_entries[bucket][movie_title] = entry

        except Exception as e:
            logger.error(f"[BATCH] Error for {rating_key}\n{e}")
            results.append({
                "rating_key": rating_key,
                "status": "error",
                "error": str(e),
            })

    yaml_files_written: list[str] = []
    if req.generate_yaml and yaml_entries:
        yaml_root.mkdir(parents=True, exist_ok=True)

        for bucket, entries in yaml_entries.items():
            yaml_path = yaml_root / f"{bucket}.yml"

            existing_metadata = {}
            if yaml_path.exists():
                try:
                    loaded = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                    if isinstance(loaded, dict):
                        existing_metadata = loaded.get("metadata", {}) or {}
                except Exception as e:
                    logger.warning("[BATCH] Failed to read YAML %s: %s", yaml_path, e)

            merged_metadata = {**existing_metadata, **entries}
            data = {"metadata": merged_metadata}

            try:
                yaml.safe_dump(
                    data,
                    yaml_path.open("w", encoding="utf-8"),
                    # Preserve insertion order to match the order movies were processed
                    # so the resulting YAML remains aligned with user expectations.
                    sort_keys=False,
                    allow_unicode=True,
                    default_flow_style=False,
                )
                yaml_files_written.append(str(yaml_path))
                logger.info("[BATCH] Wrote YAML: %s", yaml_path)
            except Exception as e:
                logger.error("[BATCH] Failed to write YAML %s: %s", yaml_path, e)

    return {"results": results, "yaml_files": yaml_files_written}
