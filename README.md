# Simposter v1.1 🎬🖼️ — TMDb‑Powered Poster Builder with Live Plex Integration

> **Simposter** is a fast, template‑based poster generator built for Plex users who want consistent, high‑quality artwork — with live previews, TMDb artwork browsing, JSON presets, and one‑click Plex uploads.

![Image](https://github.com/user-attachments/assets/53ab475b-3fec-4b14-a7a4-a12e6589e27c)
---

## ✨ Core Features

### 🎞 Plex‑Aware Movie Picker
- Connects directly to your Plex server using:
  - `PLEX_URL`
  - `PLEX_TOKEN`
  - `PLEX_MOVIE_LIBRARY_NAME`
- Automatically loads your **movie list** (sorted alphabetically).
- Selecting a movie triggers:
  - TMDb ID lookup  
  - TMDb poster + logo fetch  
  - Existing Plex poster preview  

---

### 🖼 TMDb Artwork Integration
- Fetches **posters + logos** for the selected movie.
- Thumbnail browsing with:
  - Quick‑select strips  
  - “View All” modal gallery  
- Filters:
  - **All**
  - **Textless**
  - **With Text**

This lets you visually explore all TMDb artwork for a title without leaving the app.

---

### 🎚 Full‑Control Renderer (Universal Template)
The universal template supports precise adjustments:

| Control | Description |
|--------|-------------|
| Poster Zoom | Crop/scale the base poster |
| Poster Shift Y | Vertical framing adjustment |
| Matte Height | Add a matte border at bottom |
| Fade Height | Gradient fade into bottom matte |
| Vignette | Subtle edge darkening |
| Grain | Film‑grain texture |
| Logo Scale | Size of TMDb logo |
| Logo Position | Vertical placement of the logo |

All values update the **live preview automatically** (250ms debounce).

---

### 🔣 Logo Modes
Choose how movie logos are handled:

- **Stock** — keep TMDb logo untouched  
- **Match** — automatically recolor the logo using dominant poster color  
- **Custom Hex** — define a manual color tint (`#RRGGBB`)  

Logo tinting is handled by alpha‑aware per‑pixel recoloring.

---

### 💾 JSON Presets
Presets allow 100% reproducible styling:

- Load presets from `presets.json`
- Modify sliders in the UI
- Click **Save / Overwrite** to update or add a preset
- Export/import via **Copy JSON** / **Apply JSON**

Presets are stored persistently in **/config/presets.json**, which is mounted from your host.

---

### 📂 File Output
Saving locally produces:

```
/poster-outputs/Movie Title (Year)/Movie Title (Year).jpg
```

Output root is adjustable via environment variables and mapped volumes.

---

### 📡 Send to Plex + Live Poster Refresh
- Render → upload to Plex in one click  
- Automatically removes selected **label tags** (e.g., Kometa overlays)  
- Refreshes the **Existing Poster** preview after upload  
- Works across modern Plex versions

---

![Image](https://github.com/user-attachments/assets/91c0ce89-1984-4b20-b4a6-a03a3fd8bfdc)


## 🧱 Tech Stack

**Backend**
- Python 3.11  
- FastAPI  
- Pillow (PIL)  
- Requests  

**Frontend**
- Pure HTML + vanilla JavaScript  
- Zero build tools  

**Integrations**
- Plex API (metadata, labels, artwork)  
- TMDb API (posters, logos)

---

## 📁 Project Structure

```
.
├── backend/
│   ├── main.py           # FastAPI app, preview, save, Plex upload, labeling
│   ├── tmdb_client.py    # TMDb image + logo fetch
│   ├── templates/
│   │   ├── __init__.py   # Template registry
│   │   └── universal.py  # Universal 2:3 poster rendering engine
│   └── presets.json      # Default presets
├── frontend/
│   └── index.html        # Entire UI + JS logic
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## ⚙️ Environment Variables

| Variable | Required | Purpose | Example |
|----------|----------|---------|---------|
| `PLEX_URL` | ✔ | Base hostname of Plex server | `http://myplex:32400` |
| `PLEX_TOKEN` | ✔ | Plex API token | `xxxyyyzzz` |
| `PLEX_MOVIE_LIBRARY_NAME` | ✔ | Name of Plex movie library | `Movies` |
| `TMDB_API_KEY` | ✔ | TMDb API key | `abcd1234` |
| `OUTPUT_ROOT` | Optional | Internal output folder | `/poster-outputs` |
| `CONFIG_DIR` | Optional | Persistent config directory | `/config` |

### How Library Name Works
Simposter performs a lookup:
1. GET `/library/sections`
2. Match section title to your `PLEX_MOVIE_LIBRARY_NAME`
3. Use that section’s numeric ID internally

This keeps the Docker variables human‑friendly.

---

## 🐳 Running with Docker (Recommended)

### 1. Build
```bash
docker build -t simposter:latest .
```

### 2. Run
```bash
docker run -d   --name simposter   -p 8000:8000   -e PLEX_URL="http://<your-plex-ip>:32400"   -e PLEX_TOKEN="your_token"   -e PLEX_MOVIE_LIBRARY_NAME="Movies"   -e TMDB_API_KEY="your_tmdb_key"   -v /mnt/user/appdata/poster-maker/config:/config   -v /mnt/user/appdata/poster-maker/outputs:/poster-outputs   simposter:latest
```

Then open:

```
http://localhost:8000
```

---

## 🖥 Running Locally (Dev Mode)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export PLEX_URL="http://localhost:32400"
export PLEX_TOKEN="xxx"
export PLEX_MOVIE_LIBRARY_NAME="Movies"
export TMDB_API_KEY="yourkey"

uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🧩 Usage Workflow

1. **Pick a movie** (Pulled from Plex)
2. **Select a poster + logo** (from TMDb)
3. **Adjust renderer controls**  
4. **Choose logo mode**  
5. **Preview auto‑updates**
6. **Save locally** or **Send to Plex**
7. (Optional) **Remove labels** (Kometa overlay labels, etc.)
8. (Optional) **Save as preset**  

---

## 💡 Tips & Tricks

- Textless posters blend best with matte + fade settings  
- Logo “Match” mode works best on bright posters  
- Saving presets lets you rapidly build consistent sets  
- Use the **logs window** to debug TMDb or Plex issues  
- Poster rendering is always 2:3 ratio (1000×1500 internal resolution)

---

## 🛣 Roadmap

- TV + collections support  
- Multiple template engines (DarkMatte 2.0, Cinematic, Blu‑ray style, etc.)  
- Batch mode (generate entire library automatically)  
- User-uploaded logos  
- Multi-user environment file presets  
- Hotkeys for faster workflow  

---


---

## 📜 License
MIT License — free to modify, fork, use, break, improve.

