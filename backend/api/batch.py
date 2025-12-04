from fastapi import APIRouter
from ..schemas import BatchRequest
from ..config import (
    settings,
    plex_remove_label,
    logger,
    get_movie_tmdb_id,
    load_presets,
)
from ..tmdb_client import get_images_for_movie, get_movie_details
from ..rendering import render_poster_image
from io import BytesIO
import requests
from backend.assets.selection import pick_poster, pick_logo

router = APIRouter()


@router.post("/batch")
def api_batch(req: BatchRequest):

    results = []

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
            if req.save_locally:
                import os
                from pathlib import Path

                # Get movie info for filename
                movie_title = movie_details.get("title", rating_key)
                movie_year = movie_details.get("year", "")

                # Sanitize filename
                safe_title = "".join(c for c in movie_title if c.isalnum() or c in " _-()")
                filename = f"{safe_title} ({movie_year}).jpg" if movie_year else f"{safe_title}.jpg"

                # Save to output directory
                out_dir = os.path.join(settings.OUTPUT_ROOT, "batch")
                os.makedirs(out_dir, exist_ok=True)
                save_path = os.path.join(out_dir, filename)

                img.convert("RGB").save(save_path, "JPEG", quality=95)
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

        except Exception as e:
            logger.error(f"[BATCH] Error for {rating_key}\n{e}")
            results.append({
                "rating_key": rating_key,
                "status": "error",
                "error": str(e),
            })

    return {"results": results}
