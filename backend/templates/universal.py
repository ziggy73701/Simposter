# backend/templates/universal.py
from typing import Dict, Any, Optional
from PIL import Image, ImageFilter, ImageDraw
import random


# ============================================================
# Helpers
# ============================================================

def _resize_cover(
    img: Image.Image,
    target_w: int,
    target_h: int,
    zoom: float = 1.0
) -> Image.Image:
    """Resize to fully cover canvas, then center-crop."""
    w, h = img.size
    if w == 0 or h == 0:
        return img.resize((target_w, target_h), Image.LANCZOS)

    base_scale = max(target_w / w, target_h / h)
    scale = base_scale * max(zoom, 0.01)

    new_w = int(w * scale)
    new_h = int(h * scale)
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    x = max(0, (new_w - target_w) // 2)
    y = max(0, (new_h - target_h) // 2)
    return resized.crop((x, y, x + target_w, y + target_h))


def _add_vignette(img: Image.Image, strength: float) -> Image.Image:
    if strength <= 0:
        return img

    img = img.convert("RGB")
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)

    steps = 50
    max_r = max(w, h)
    for i in range(steps):
        r = max_r * (i / steps)
        a = int(255 * strength * (i / steps))
        bbox = (w/2 - r, h/2 - r, w/2 + r, h/2 + r)
        draw.ellipse(bbox, fill=a)

    mask = mask.filter(ImageFilter.GaussianBlur(80))
    black = Image.new("RGB", (w, h), 0)

    return Image.composite(black, img, mask)


def _add_grain(img: Image.Image, amount: float) -> Image.Image:
    if amount <= 0:
        return img

    img = img.convert("RGB")
    w, h = img.size
    noise = Image.new("L", (w, h))
    px = noise.load()

    rng = random.Random()
    for y in range(h):
        for x in range(w):
            v = 128 + int(rng.uniform(-128 * amount, 128 * amount))
            px[x, y] = max(0, min(255, v))

    noise = noise.filter(ImageFilter.GaussianBlur(1.4))
    noise_rgb = Image.merge("RGB", (noise, noise, noise))

    return Image.blend(img, noise_rgb, amount)


# ============================================================
# Universal Renderer
# ============================================================

def render(
    background: Image.Image,
    logo: Optional[Image.Image],
    options: Dict[str, Any] | None,
) -> Image.Image:

    if options is None:
        options = {}

    canvas_w = 2000
    canvas_h = 3000

    # ---------------- OPTIONS ----------------
    poster_zoom = float(options.get("poster_zoom", 1.0))
    poster_shift_y = float(options.get("poster_shift_y", 0.0))

    matte_height_ratio = float(options.get("matte_height_ratio", 0.0))
    fade_height_ratio = float(options.get("fade_height_ratio", 0.0))

    vignette_strength = float(options.get("vignette_strength", 0.0))
    grain_amount = float(options.get("grain_amount", 0.0))

    logo_scale = float(options.get("logo_scale", 0.5))  # width fraction
    logo_position = float(options.get("logo_offset", 75))  # NOW 0–100%

    logo_mode = options.get("logo_mode", "stock")
    logo_hex = options.get("logo_hex", "#FFFFFF")

    # ---------------- BASE POSTER ----------------
    base = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 255))

    poster = _resize_cover(background, canvas_w, canvas_h, zoom=poster_zoom)
    shift_px = int(poster_shift_y * canvas_h)
    base.paste(poster, (0, shift_px))

    # ---------------- MATTE / FADE ----------------
    matte_h = int(canvas_h * matte_height_ratio)
    fade_h = int(canvas_h * fade_height_ratio)

    if matte_h > 0 or fade_h > 0:
        mask = Image.new("L", (canvas_w, canvas_h), 0)
        mp = mask.load()

        matte_start = canvas_h - matte_h
        fade_start = max(0, matte_start - fade_h)

        for y in range(canvas_h):
            if y >= matte_start:
                a = 255
            elif y >= fade_start:
                t = (y - fade_start) / max(fade_h, 1)
                a = int(255 * t)
            else:
                a = 0

            for x in range(canvas_w):
                mp[x, y] = a

        matte_black = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 255))
        base = Image.composite(matte_black, base, mask)

    # ---------------- APPLY EFFECTS (POSTER ONLY) ----------------
    poster_processed = base.convert("RGB")
    poster_processed = _add_vignette(poster_processed, vignette_strength)
    poster_processed = _add_grain(poster_processed, grain_amount)

    base = poster_processed.convert("RGBA")

    # ---------------- PREPARE LOGO ----------------
        # ------------- LOGO DRAWING (absolute positioning, not matte-based) -------------
        # ---------------- PREPARE LOGO (absolute positioning, not matte-based) ----------------
    if logo is not None:
        logo = logo.convert("RGBA")

        # Apply logo color mode BEFORE whitening
        if logo_mode == "match":
            # Average poster color
            poster_avg = background.resize((1, 1), Image.Resampling.LANCZOS).getpixel((0, 0))
            r, g, b = poster_avg[:3]
            tinted = Image.new("RGBA", logo.size, (r, g, b, 255))
            logo = Image.blend(logo, tinted, 0.6)

        elif logo_mode == "hex":
            h = logo_hex.lstrip("#")
            r, g, b = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
            tinted = Image.new("RGBA", logo.size, (r, g, b, 255))
            logo = Image.blend(logo, tinted, 1.0)

        if logo_mode in ("match", "hex"):
            # Pure white conversion only for recoloring modes
            r, g, b, a = logo.split()
            logo = Image.merge(
                "RGBA",
                (
                    Image.new("L", logo.size, 255),
                    Image.new("L", logo.size, 255),
                    Image.new("L", logo.size, 255),
                    a,
                ),
            )


        # Resize logo
        max_w = int(canvas_w * logo_scale)
        scale = max_w / logo.width
        new_size = (int(logo.width * scale), int(logo.height * scale))
        logo = logo.resize(new_size, Image.LANCZOS)

        # ---- NEW ABSOLUTE POSITION LOGIC (0–1 range) ----
        pos = float(options.get("logo_offset", 0.75))  # default 75%
        pos = max(0.0, min(1.0, pos))  # clamp

        y_logo = int((canvas_h - logo.height) * pos)
        x_logo = (canvas_w - logo.width) // 2

        base.alpha_composite(logo, (x_logo, y_logo))

        #base_rgba.alpha_composite(logo, (x_logo, y_logo))


    return base.convert("RGB")
