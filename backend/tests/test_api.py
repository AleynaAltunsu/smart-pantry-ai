from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def confirm(c, food, qty, when):
    r = c.post("/confirm", json={"food_type": food, "quantity_level": qty, "observed_at": when.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def test_health(client):
    assert client.get("/health").status_code == 200


def test_scan_finds_regions(client):
    with open(DATA / "fake_fridge2.jpg", "rb") as f:
        r = client.post("/scan", files={"file": ("f.jpg", f, "image/jpeg")})
    assert r.status_code == 200
    assert len(r.json()["regions"]) >= 3


def test_consumption_rate_and_history_note(client):
    now = datetime.now()
    confirm(client, "yoğurt", "3plus", now - timedelta(days=4))
    confirm(client, "yoğurt", "1", now)
    confirm(client, "süt", "2", now - timedelta(minutes=5))
    confirm(client, "süt", "1", now)
    hist = client.get("/history").json()
    yog = [h for h in hist if h["food_type"] == "yoğurt" and h["consumption_rate_per_day"] is not None]
    assert yog and abs(yog[0]["consumption_rate_per_day"] - 0.625) < 0.01
    sut = [h for h in hist if h["food_type"] == "süt" and h["days_since_previous"] is not None]
    assert sut and sut[0]["consumption_rate_per_day"] is None
    assert "12 saatten kısa" in sut[0]["rate_note"]


def test_recipes_and_shopping_completion_items(client):
    now = datetime.now()
    for f in ("ıspanak", "domates", "peynir"):
        confirm(client, f, "1", now)
    shop = {i["food_type"] for i in client.get("/shopping-list").json()}
    assert "yufka" in shop          # börek için
    assert "salatalık" in shop      # çoban salatası için
    recipes = client.get("/recipes/recommendations").json()
    assert any(r["also_needed"] for r in recipes)


def test_manual_shopping_item_roundtrip(client):
    r = client.post("/shopping-list/manual", json={"food_type": "tavuk"})
    assert r.status_code == 200
    item_id = r.json()["id"]
    assert client.delete(f"/shopping-list/manual/{item_id}").status_code == 200
