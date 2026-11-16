# 🧊 Smart Pantry AI

[![CI](https://github.com/AleynaAltunsu/smart-pantry-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/AleynaAltunsu/smart-pantry-ai/actions)
![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green)

> 🇹🇷 Türkçe dokümantasyon: **[README.tr.md](README.tr.md)**

A local, privacy-first web app that turns a photo of your fridge into **consumption forecasts, spoilage warnings, recipe suggestions and a shopping list**. No cloud, no API key: everything runs on your machine.

## How it works

```
📷 Scan photo ─▶ ✅ Confirm (human-in-the-loop) ─▶ 📦 Inventory
      │                                                │
 OpenCV + YOLO-World                      consumption rate ─▶ run-out forecast
 object proposals                                      └────▶ waste / spoilage risk
                                                               │
                                       🍽 Recipes ◀────────────┘
                                          │  (rule-based DB, optional local LLM via Ollama)
                                          ▼
                                    🛒 Shopping list  (missing + recipe-completing items + manual)
```

- **Detection:** classical OpenCV pipeline (Canny, CLAHE, watershed, colour clustering for produce bags) with an optional **YOLO-World** open-vocabulary detector. YOLO loads in the background; scans never block.
- **Human-in-the-loop:** the model only *proposes* regions. You confirm the food type and quantity. Generic detections ("bottle", "container", "fruit") are shown as hints, never auto-filled, because the contents of a closed container cannot be known from an image.
- **Consumption rate:** time-weighted over consecutive observations of the same container; pairs less than 12 h apart or without a decrease are ignored (the History table explains why a rate is missing).
- **Waste risk:** shelf-life table (~100 foods) + optional LLM + your purchase date → `low / medium / high (urgent) / spoiled`.
- **Recipes & shopping:** recipes combine what is at home with items already on your shopping list; completing ingredients (pastry sheets for börek, cucumber for shepherd's salad…) are suggested for the list.

## Quick start

Requirements: Python 3.10+ (tested on 3.11–3.13).

```bash
git clone https://github.com/AleynaAltunsu/smart-pantry-ai.git
cd smart-pantry-ai/backend
python -m venv venv
# Windows: venv\Scripts\activate      macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-cv.txt      # optional: YOLO-World (PyTorch, ~1-2 GB)
uvicorn app.main:app --reload
```

In a second terminal:

```bash
cd smart-pantry-ai/frontend
python -m http.server 5500
```

Open **http://localhost:5500** (hard refresh with Ctrl+F5). The API runs on `http://127.0.0.1:8000` (health check: `/health`, interactive docs: `/docs`).

Helper scripts: `scripts/start-backend.ps1`, `scripts/start-frontend.ps1` (Windows) and `scripts/start.sh` (macOS/Linux).

> Without `requirements-cv.txt` the app falls back to the classical detector automatically. On first YOLO use, ultralytics downloads the weights (~30–60 MB) and CLIP's text encoder (~340 MB) once. `clip` is bundled as a wheel in `backend/wheels`, so **git is not required** on Windows.

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `SMART_PANTRY_USE_YOLO` | `1` | `0` disables YOLO-World (classical only) |
| `SMART_PANTRY_YOLO_MODEL` | – | custom weights, e.g. `yolov8l-worldv2.pt` |
| `SMART_PANTRY_PREFILL_CONF` | `0.35` | min confidence to auto-fill a *specific* food name |
| `SMART_PANTRY_DB_URL` | `sqlite:///./smart_pantry.db` | database location |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | `http://localhost:11434` / `llama3.2` | optional local LLM for recipes & shelf life |
| `OLLAMA_TIMEOUT_SECONDS` | `20` | LLM timeout; on failure the rule-based path is used |

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q
```

Covers the API flow (scan → confirm → history/rate → recipes → shopping), YOLO class interpretation and classical-detector regressions on synthetic fridge images.

## Project layout

```
backend/app/        FastAPI app (main, schemas, models, forecasting, recipes, shopping, shelf_life, llm_client)
backend/app/cv/     detector.py – OpenCV + YOLO-World pipeline
backend/tests/      pytest suite + synthetic test images
frontend/           single-file UI (index.html, no build step)
docs/               ARCHITECTURE.md, API.md, CHANGELOG.md
```

More: [Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [Changelog](docs/CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

## Privacy

All data stays in a local SQLite file (`smart_pantry.db`, git-ignored). Photos are processed in memory and not stored. No telemetry.

## Limitations

- Quantity is user-confirmed; the app does not estimate volume from pixels.
- Open-vocabulary detection can miss items inside bags/opaque containers; use "add manually".
- The UI language is Turkish; recipes and shelf-life data are Turkish-centric.

## License

MIT © 2026 Aleyna Altunsu
