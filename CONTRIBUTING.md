# Contributing

1. Fork + branch (`feature/short-name`).
2. `cd backend && pip install -r requirements-dev.txt && pytest -q` must pass.
3. Keep the frontend a single dependency-free `index.html`.
4. New recipes: add to `RECIPES` (and optionally `ALSO_NEEDED`) in `backend/app/recipes.py`; new shelf-life entries in `backend/app/shelf_life.py`.
5. Open a PR describing the behaviour change and attach a screenshot for UI changes.

Never commit personal data (`*.db`) or large model weights (`*.pt`).
