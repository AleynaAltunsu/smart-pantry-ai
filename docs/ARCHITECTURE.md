# Architecture

## Components

| Layer | Tech | Notes |
|---|---|---|
| Frontend | single `index.html` (vanilla JS) | no build step; talks to the API via `fetch` (API base configurable in the UI) |
| Backend | FastAPI + SQLAlchemy + SQLite | auto-migration via `ensure_schema()` keeps old DBs working |
| Vision | OpenCV (classical) + optional YOLO-World (ultralytics) | detection runs in a worker thread; YOLO warms up in the background |
| LLM (optional) | Ollama (local) | recipes and shelf-life estimates; always falls back to rule-based |

## Data model

```
Container (physical vessel)  1 ── * FoodInstance (what is in it during a time span)  1 ── * Observation (quantity at a scan)
```

- `FoodInstance.entry_source`: `scan` | `manual`; `end_reason`: `consumed` | `discarded` | `replaced`; `purchased_at` (optional baseline for spoilage).
- A container is auto-matched by food type when the client does not send `container_id`; this is what makes multi-scan consumption rates possible.

## Pipeline

1. **Scan** (`POST /scan`): image downscaled to 1280 px if larger; classical regions (Canny, adaptive threshold, CLAHE, watershed, colour clusters, NMS, solidity/edge filters) or YOLO-World boxes (+ colour clusters for misses). Each region carries `suggested_food_type` (only for confident *specific* classes) plus `suggested_label/category/kind` hints.
2. **Confirm** (`POST /confirm`): user sets food type + quantity (`less_half | 1 | 2 | 3plus | custom`), optional date and purchase date.
3. **Forecast** (`forecasting.py`): quantity levels → portions (0.4 / 1 / 2 / 3.5 / custom). Rate = time-weighted drop over consecutive observation pairs, skipping pairs < 0.5 day apart or without a decrease. Days remaining = current / rate.
4. **Waste risk**: days left from the forecast or from shelf life (table → LLM → default 7 d) measured from `purchased_at`/first scan; thresholds ≤0 spoiled, ≤3 high, ≤5 medium, else low; past leftovers (`discarded`) raise risk.
5. **Recipes** (`recipes.py`): score = 2·required matched − 1.5·required missing + 0.5·optional + 0.3·completing + risk bonus + shopping-list bonus. Home inventory is merged with manually planned shopping items. `ALSO_NEEDED` adds completing ingredients that are suggested for the list.
6. **Shopping list** (`shopping.py`): items about to run out + missing/completing ingredients of the top recipes (pantry staples excluded) + manual items; dismissed items stay hidden.

## Design decisions

- **Human-in-the-loop** instead of trusting detections: quantities and food types are always confirmed.
- **No silent deletions**: items missing from a later scan are only *asked about* (consumed / discarded / still there).
- **Graceful degradation**: no ultralytics → OpenCV; no Ollama → rule-based; no DB columns → auto-migrated.
