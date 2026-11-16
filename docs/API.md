# API

Base URL `http://127.0.0.1:8000` · interactive docs at `/docs` (Swagger) and `/redoc`.

| Method & path | Purpose |
|---|---|
| `GET /health` | liveness |
| `GET /cv/status` | detector state (`yolo_world` / `classical`, reason, message) |
| `POST /scan` (multipart `file`) | detect candidate regions → `regions[]` with crop, bbox, hints |
| `GET /containers`, `GET /containers/active-summary` | containers and their latest state |
| `POST /confirm` | save one confirmed region (`food_type`, `quantity_level`, optional `container_id`, `observed_at`, `purchased_at`, `entry_source`) |
| `GET /food-types` | previously entered names (autocomplete chips) |
| `GET /inventory` | active items + consumption rate, forecast, waste risk |
| `POST /inventory/{id}/remove` | `reason`: `consumed` \| `discarded` \| `mistake` |
| `GET /history` | all observations with `days_since_previous`, `consumption_rate_per_day`, `rate_note` |
| `GET /recipes/recommendations` | scored recipes incl. `missing_ingredients`, `also_needed`, `from_shopping_list` |
| `GET /shopping-list` | auto + manual items |
| `POST /shopping-list/manual`, `DELETE /shopping-list/manual/{id}` | manage manual items |
| `POST /shopping-list/dismiss`, `DELETE /shopping-list/dismissed` | hide / restore auto items |

Example:

```bash
curl -X POST http://127.0.0.1:8000/confirm -H "Content-Type: application/json" \
  -d '{"food_type":"yoğurt","quantity_level":"1"}'
curl http://127.0.0.1:8000/inventory
```
