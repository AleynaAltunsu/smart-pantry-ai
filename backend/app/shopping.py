"""
Smart Pantry AI - Shopping List (MVP6, v4 - basitleştirildi)

Kullanıcı geri bildirimi: eski "en iyi kombinasyonu bul" mantığı çok
agresifti - bir tarifin eksik malzemesi olmadığında (evdekilerle zaten
yapılabiliyorsa) liste boş görünüyordu ve bu "bozuk" gibi hissettiriyordu.

Yeni mantık, daha öngörülebilir ve kullanıcı isteğiyle birebir örtüşüyor:
"tarif önerilerindeki eksik malzemeleri DİREKT olarak listeye al."

İki kaynak:
1. Forecast: yakında bitecek ürünler ("runs_out_soon")
2. En iyi puanlı ilk birkaç tarifin eksik malzemeleri ("needed_for_recipe") -
   verimlilik sırasına göre (az eksikle çok değer katan tarifler önce)

Kuru mutfak stoğu (PANTRY_STAPLES) hiçbir zaman alışveriş listesine eklenmez.
Manuel öğeler (kullanıcının elle eklediği) main.py tarafında ayrıca birleştirilir.
"""
from typing import List, Dict

from app.recipes import PANTRY_STAPLES


def build_shopping_list(
    inventory_analytics: List[dict],
    top_recipes: List[dict],
    days_threshold: float = 2.0,
    max_recipes_considered: int = 8,
    max_items: int = 14,
) -> List[Dict]:
    items: Dict[str, Dict] = {}

    # 1) Yakında bitecek ürünler (her zaman öncelikli - gerçek/somut ihtiyaç)
    for item in inventory_analytics:
        days_left = item.get("estimated_days_remaining")
        if days_left is not None and days_left <= days_threshold:
            food = item["food_type"]
            items[food.lower()] = {
                "food_type": food,
                "reason": f"Yaklaşık {days_left} gün içinde bitebilir.",
                "urgency": "runs_out_soon",
            }

    # 2) En verimli (az eksikle çok değer katan) tariflerden başlayarak
    #    ilk birkaçının eksiklerini DİREKT listeye ekle.
    ranked = sorted(top_recipes, key=lambda r: r["score"], reverse=True)
    for recipe in ranked[:max_recipes_considered]:
        for missing in recipe["missing_ingredients"]:
            if missing.lower() in PANTRY_STAPLES:
                continue
            key = missing.lower()
            if key in items:
                continue  # zaten "yakında bitecek" olarak eklenmiş
            items[key] = {
                "food_type": missing,
                "reason": f"'{recipe['name']}' tarifi için gerekli.",
                "urgency": "needed_for_recipe",
            }

        # Tarifi tamamlayan malzemeler (börek -> yufka, çoban salatası -> salatalık ...)
        for extra in recipe.get("also_needed", []) or []:
            key = extra.lower()
            if key in items or key in PANTRY_STAPLES:
                continue
            items[key] = {
                "food_type": extra,
                "reason": f"'{recipe['name']}' tarifini tamamlamak için.",
                "urgency": "needed_for_recipe",
            }

    return list(items.values())[:max_items]
