"""
Smart Pantry AI - Recipe Recommendation (MVP5, v4 - genişletilmiş)

Kullanıcı geri bildirimi: eski 6 tariflik liste çok "yüzeysel" kaldı (örn.
sadece domates+peynir varken "Peynirli Domates Salatası" gibi basit bir
öneri). Şimdi:
- Rule-based veritabanı ~25 tarife çıkarıldı, daha "gurme"/gerçekçi
  kombinasyonlar (zeytinyağlı-kekikli, fırında, marine edilmiş vb.) eklendi
- Pantry stapleları (zeytinyağı, kekik, sarımsak, limon suyu vb. çeşni
  malzemeleri dahil) genişletildi ki basit malzemeler sıradan durmasın
- LLM prompt'u açıkça "sıradan/basit değil, gerçekçi ama yaratıcı" istiyor

Bilinçli tasarım kararı (plandaki gibi): önce kontrollü, deterministik bir
tarif veritabanı + rule-based skorlama; LLM varsa öncelik ona verilir.
"""
from typing import List, Dict, Optional

from app.llm_client import ask_json

# Kuru mutfak stoğu - bunlar hep evde var kabul edilir, eksik malzeme sayılmaz.
# Çeşni/baharat malzemeleri de dahil edildi ki tarifler "sade" değil "lezzetli"
# görünsün (zeytinyağlı-kekikli domates gibi).
PANTRY_STAPLES = {
    "bulgur", "pirinç", "makarna", "mercimek", "nohut", "yağ", "zeytinyağı",
    "tuz", "baharat", "un", "şeker", "soğan", "sarımsak", "kekik", "nane",
    "karabiber", "pul biber", "limon suyu", "sirke", "yumurta", "tarçın", "bal",
}

# Genişletilmiş, deterministik tarif veritabanı.
# required: bu tarif için MUTLAKA gereken değişken (perishable) malzemeler
# optional: varsa daha iyi olur ama olmasa da olur
RECIPES: List[Dict] = [
    {
        "name": "Zeytinyağlı Kekikli Fırın Domates",
        "required": ["domates"],
        "optional": ["peynir"],
        "pantry_used": ["zeytinyağı", "kekik", "tuz", "sarımsak"],
    },
    {
        "name": "Akdeniz Usulü Ispanak-Peynir Böreği",
        "required": ["ıspanak", "peynir"],
        "optional": [],
        "pantry_used": ["yağ", "yumurta", "tuz"],
    },
    {
        "name": "Sarımsaklı Zeytinyağlı Ispanak Kavurma",
        "required": ["ıspanak"],
        "optional": ["domates"],
        "pantry_used": ["zeytinyağı", "sarımsak", "tuz", "pul biber"],
    },
    {
        "name": "Fırında Kekikli Tavuk But",
        "required": ["tavuk"],
        "optional": ["dolmalık biber", "domates"],
        "pantry_used": ["zeytinyağı", "kekik", "karabiber", "tuz"],
    },
    {
        "name": "Ispanaklı Tavuklu Bulgur Pilavı",
        "required": ["ıspanak", "tavuk"],
        "optional": ["soğan"],
        "pantry_used": ["bulgur", "yağ", "tuz"],
    },
    {
        "name": "Domatesli Fırın Tavuk",
        "required": ["tavuk", "domates"],
        "optional": ["dolmalık biber"],
        "pantry_used": ["zeytinyağı", "tuz", "baharat", "kekik"],
    },
    {
        "name": "Yoğurtlu Sarımsaklı Ispanak Yemeği (Borani)",
        "required": ["ıspanak", "yoğurt"],
        "optional": [],
        "pantry_used": ["sarımsak", "tuz", "yağ"],
    },
    {
        "name": "Kekikli Zeytinyağlı Domates-Peynir Salatası",
        "required": ["domates", "peynir"],
        "optional": [],
        "pantry_used": ["zeytinyağı", "kekik", "karabiber"],
    },
    {
        "name": "Ev Yapımı Yoğurt Sosu (Cacık Alternatifi)",
        "required": ["yoğurt"],
        "optional": ["salatalık"],
        "pantry_used": ["sarımsak", "tuz", "nane"],
    },
    {
        "name": "Sütlü Mercimek Çorbası",
        "required": ["süt"],
        "optional": [],
        "pantry_used": ["mercimek", "yağ", "tuz"],
    },
    {
        "name": "Peynirli Omlet",
        "required": ["peynir"],
        "optional": ["domates", "dolmalık biber"],
        "pantry_used": ["yumurta", "yağ", "tuz"],
    },
    {
        "name": "Limonlu Tavuk Şiş",
        "required": ["tavuk"],
        "optional": ["dolmalık biber"],
        "pantry_used": ["limon suyu", "zeytinyağı", "sarımsak", "kekik"],
    },
    {
        "name": "Meyveli Yoğurt Kâsesi",
        "required": ["yoğurt"],
        "optional": ["muz", "kayısı", "elma"],
        "pantry_used": ["bal (varsa)"],
    },
    {
        "name": "Karışık Meyve Salatası",
        "required": ["muz"],
        "optional": ["kayısı", "elma", "limon"],
        "pantry_used": [],
    },
    {
        "name": "Dolmalık Biber Dolması (Sade)",
        "required": ["dolmalık biber"],
        "optional": ["domates"],
        "pantry_used": ["pirinç", "soğan", "zeytinyağı", "tuz"],
    },
    {
        "name": "Fırında Sebzeli Peynir Graten",
        "required": ["peynir", "dolmalık biber"],
        "optional": ["domates"],
        "pantry_used": ["zeytinyağı", "tuz", "karabiber"],
    },
    {
        "name": "Kalan Yemek Değerlendirme (Fırın/Tava Tazeleme)",
        "required": ["kalan yemek"],
        "optional": [],
        "pantry_used": ["yağ"],
    },
    {
        "name": "Limonlu Ispanak Çorbası",
        "required": ["ıspanak"],
        "optional": ["süt"],
        "pantry_used": ["limon suyu", "soğan", "yağ", "tuz"],
    },
    {
        "name": "Kayısılı Tavuk (Tatlı-Ekşi)",
        "required": ["tavuk", "kayısı"],
        "optional": [],
        "pantry_used": ["soğan", "zeytinyağı", "karabiber", "tuz"],
    },
    {
        "name": "Salatalık-Domates-Peynir Çoban Salatası",
        "required": ["domates", "peynir"],
        "optional": [],
        "pantry_used": ["zeytinyağı", "limon suyu", "tuz"],
    },
    # --- v8: meyve odaklı tarifler (poşetli meyveler artık tespit ediliyor) ---
    {
        "name": "Fırında Tarçınlı Elma",
        "required": ["elma"],
        "optional": ["yoğurt"],
        "pantry_used": ["tarçın", "bal"],
    },
    {
        "name": "Portakallı Yoğurtlu Kek",
        "required": ["portakal"],
        "optional": ["yoğurt", "limon"],
        "pantry_used": ["yumurta", "un", "şeker"],
    },
    {
        "name": "Portakallı Havuç Salatası (Nane-Zeytinyağlı)",
        "required": ["portakal"],
        "optional": ["havuç", "limon"],
        "pantry_used": ["zeytinyağı", "nane", "tuz"],
    },
    {
        "name": "Çilekli Yoğurtlu Smoothie",
        "required": ["çilek"],
        "optional": ["yoğurt", "muz", "süt"],
        "pantry_used": ["bal"],
    },
    {
        "name": "Üzümlü Peynir Tabağı",
        "required": ["üzüm"],
        "optional": ["peynir"],
        "pantry_used": ["bal"],
    },
    {
        "name": "Şeftalili Yoğurt Kâsesi",
        "required": ["şeftali"],
        "optional": ["yoğurt", "muz"],
        "pantry_used": ["bal"],
    },
    {
        "name": "Tarçınlı Armut Kompostosu",
        "required": ["armut"],
        "optional": ["elma"],
        "pantry_used": ["tarçın", "şeker"],
    },
    {
        "name": "Kayısı Kompostosu",
        "required": ["kayısı"],
        "optional": ["elma"],
        "pantry_used": ["şeker"],
    },
    {
        "name": "Taze Limonata (Naneli)",
        "required": ["limon"],
        "optional": [],
        "pantry_used": ["şeker", "nane"],
    },
]


# Tarifi "tamamlayan" malzemeler: zorunlu olmayabilir ama tarifin gerçekten o tarif olması için
# genelde gerekir (börekte yufka, çoban salatasında salatalık...). Evde yoksa alışveriş listesine
# "tarifi tamamlamak için" olarak önerilir. Mutfak stoğundakiler (PANTRY_STAPLES) zaten hariç tutulur.
ALSO_NEEDED = {
    "Akdeniz Usulü Ispanak-Peynir Böreği": ["yufka"],
    "Salatalık-Domates-Peynir Çoban Salatası": ["salatalık", "dolmalık biber", "maydanoz"],
    "Kekikli Zeytinyağlı Domates-Peynir Salatası": ["salatalık", "maydanoz"],
    "Ispanaklı Tavuklu Bulgur Pilavı": ["havuç"],
    "Domatesli Fırın Tavuk": ["dolmalık biber", "patates"],
    "Fırında Kekikli Tavuk But": ["patates"],
    "Limonlu Tavuk Şiş": ["dolmalık biber", "yoğurt"],
    "Yoğurtlu Sarımsaklı Ispanak Yemeği (Borani)": ["ceviz"],
    "Ev Yapımı Yoğurt Sosu (Cacık Alternatifi)": ["salatalık", "nane"],
    "Sütlü Mercimek Çorbası": ["havuç", "patates"],
    "Peynirli Omlet": ["domates", "dolmalık biber"],
    "Meyveli Yoğurt Kâsesi": ["bal", "ceviz"],
    "Karışık Meyve Salatası": ["elma", "portakal"],
    "Dolmalık Biber Dolması (Sade)": ["domates", "maydanoz"],
    "Fırında Sebzeli Peynir Graten": ["patates", "süt"],
    "Limonlu Ispanak Çorbası": ["havuç", "patates"],
    "Kayısılı Tavuk (Tatlı-Ekşi)": ["pirinç"],
    "Portakallı Yoğurtlu Kek": ["yumurta", "un"],
    "Portakallı Havuç Salatası (Nane-Zeytinyağlı)": ["havuç"],
    "Çilekli Yoğurtlu Smoothie": ["muz", "yoğurt"],
    "Üzümlü Peynir Tabağı": ["ceviz"],
}


def _norm(s: str) -> str:
    return s.strip().lower()


def score_recipes(
    inventory_food_types: List[str],
    waste_risk_map: Dict[str, str],
    planned_food_types: Optional[List[str]] = None,
) -> List[Dict]:
    """
    inventory_food_types: envanterdeki (aktif) yiyecek adları
    waste_risk_map: {food_type: risk_level} - MVP4'ten gelen israf riski

    Skor = 2 * eşleşen_zorunlu - 1.5 * eksik_zorunlu + 0.5 * eşleşen_opsiyonel
           + 1 * (yüksek riskli malzeme kullanımı bonus)
    """
    # planned_food_types: market listesindeki (henüz evde olmayan ama alınacak) ürünler.
    # Evdekilerle BİRLEŞTİRİLİP tarifler birlikte değerlendirilir.
    home = {_norm(f) for f in inventory_food_types}
    planned = {_norm(f) for f in (planned_food_types or [])} - home
    have = home | planned
    results = []

    for recipe in RECIPES:
        required = [_norm(x) for x in recipe["required"]]
        optional = [_norm(x) for x in recipe["optional"]]

        matched_required = [r for r in required if r in have]
        missing_required = [r for r in required if r not in have]
        matched_optional = [o for o in optional if o in have]
        also = [_norm(x) for x in ALSO_NEEDED.get(recipe["name"], [])
                if _norm(x) not in required and _norm(x) not in optional]
        matched_also = [a for a in also if a in have]
        missing_also = [a for a in also if a not in have and a not in PANTRY_STAPLES]

        if not matched_required:
            # Hiçbir zorunlu malzeme yoksa bu tarifi hiç önerme
            continue

        high_risk_used = [
            r for r in matched_required
            if waste_risk_map.get(r) in ("high", "medium")
        ]

        score = (
            2.0 * len(matched_required)
            - 1.5 * len(missing_required)
            + 0.5 * len(matched_optional)
            + 0.3 * len(matched_also)
            + 1.0 * len(high_risk_used)
        )

        used = matched_required + matched_optional + matched_also
        from_list = [x for x in used if x in planned]
        from_home = [x for x in used if x in home]
        # Market listesindeki malzemeleri kullanan tarif küçük bonus alır; evdekilerle
        # listedekileri BİRLEŞTİREN tarif ek bonus alır.
        score += 0.5 * len(from_list) + (1.0 if from_list and from_home else 0.0)

        reasons = []
        if from_list and from_home:
            reasons.append(
                f"Evdekiler ({', '.join(from_home)}) ile market listendekileri ({', '.join(from_list)}) birleştiriyor."
            )
        elif from_list:
            reasons.append(f"Market listendeki malzemelerle yapılabilir: {', '.join(from_list)}.")
        if high_risk_used:
            reasons.append(
                f"İsraf riski yüksek olan şunları değerlendiriyor: {', '.join(high_risk_used)}."
            )
        if not missing_required:
            reasons.append("Yeni alışveriş gerektirmiyor (zorunlu malzemelerin hepsi evde).")
        else:
            reasons.append(f"Eksik: {', '.join(missing_required)}.")
        if missing_also:
            reasons.append(f"Tarifi tamamlamak için alınabilir: {', '.join(missing_also)}.")

        results.append({
            "name": recipe["name"],
            "score": round(score, 2),
            "matched_ingredients": matched_required + matched_optional + matched_also,
            "missing_ingredients": missing_required,
            "also_needed": missing_also,
            "uses_high_risk_ingredients": high_risk_used,
            "reasons": reasons,
            "from_shopping_list": from_list,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    for r in results:
        r["source"] = "rule_based"
    return results


# ---------------------------------------------------------------------------
# LLM tabanlı tarif üretimi (Ollama, opsiyonel) - önceliklidir
# ---------------------------------------------------------------------------

def _ask_llm_recipes(inventory_items: List[dict]) -> Optional[List[Dict]]:
    """
    Kullanıcı isteği: tarifler çeşitli, yenilesi ve "gurme" hissi versin -
    sadece "X + Y = salata" gibi basit kombinasyonlar değil.

    Ollama kullanılamıyorsa None döner - çağıran taraf rule-based'e düşer.
    """
    if not inventory_items:
        return None

    items_desc = "\n".join(
        (f"- {it['food_type']}: market listesinde (alınacak, henüz evde yok)"
         if it.get("planned")
         else f"- {it['food_type']}: {it['latest_quantity_level']} porsiyon, israf riski: {it['waste_risk']}")
        for it in inventory_items
    )
    planned_set = {_norm(it["food_type"]) for it in inventory_items if it.get("planned")}
    pantry_list = ", ".join(sorted(PANTRY_STAPLES))

    prompt = f"""Bir buzdolabı takip uygulaması için tarif önerisi üretiyorsun.
Hedef kitle: yemek yapmayı seven, sıradan değil biraz "gurme"/lezzetli
sonuçlar isteyen bir kullanıcı.

Evdeki değişken (buzdolabı) malzemeler:
{items_desc}

'market listesinde' etiketli malzemeler yakında alınacak; evdeki malzemelerle
bunları KOMBİNE eden tarifleri öncelikli öner.

Şu kuru mutfak stoğu ve çeşni malzemeleri her zaman evde var kabul edilir
(bunları eksik malzeme SAYMA, ama tariflerde KULLAN - sade "domates+peynir
salatası" yerine "zeytinyağlı kekikli domates-peynir salatası" gibi çeşni
ekleyerek daha lezzetli hale getir): {pantry_list}

Görev: Bu malzemelerle yapılabilecek 4-6 GERÇEKÇİ ama ÇEŞİTLİ ve YENİLESİ
tarif öner (Türk mutfağı + Akdeniz + dünya mutfağından karışık olabilir).
KURALLAR:
- Basit/sıradan iki malzemeyi yan yana koyup "salata" demek yerine, pişirme
  yöntemi (fırında, kavurma, marine), çeşni (kekik, sarımsak, limon, zeytinyağı)
  ve sunum ekleyerek gerçek bir tarif hissi ver.
- Öncelik "israf riski: high" veya "medium" olan malzemeleri kullanan
  tariflere verilmeli.
- Sadece yukarıda listelenen değişken malzemeleri "required_ingredients"
  olarak kullan (listede olmayan bir malzeme UYDURMA).
- Evde olmayan ama tarifi tamamlayacak 0-2 ek malzemeyi "missing_ingredients"
  alanına yaz (kuru mutfak/çeşni stoğunu tekrar yazma).
- Her tarifte en az bir hazırlama detayı geçsin (fırında, kavurma, marine
  edilmiş, taze doğranmış gibi) - "reasoning" alanında bunu belirt.

SADECE şu JSON formatında bir liste döndür, başka hiçbir metin ekleme:
[
  {{
    "name": "<gerçek, iştah açıcı bir tarif adı>",
    "required_ingredients": ["<yukarıdaki listeden birebir isimler>"],
    "missing_ingredients": ["<varsa, en fazla 2 tane>"],
    "reasoning": "<1-2 cümle, hazırlama tarzını da içersin, Türkçe>"
  }}
]"""

    data = ask_json(prompt)
    if not isinstance(data, list):
        return None

    have_lower = {_norm(it["food_type"]) for it in inventory_items}
    risk_map = {_norm(it["food_type"]): it["waste_risk"] for it in inventory_items}

    results = []
    for recipe in data:
        try:
            name = str(recipe["name"]).strip()
            required = [_norm(x) for x in recipe.get("required_ingredients", [])]
            missing = [str(x).strip() for x in recipe.get("missing_ingredients", [])]
            missing = [m for m in missing if _norm(m) not in have_lower]  # listede olanı eksik sayma
            reasoning = str(recipe.get("reasoning", "")).strip()
        except (KeyError, TypeError, ValueError):
            continue

        # LLM'in uydurduğu (envanterde olmayan) malzemeleri required'dan temizle -
        # güvenlik: sadece gerçekten elimizdeki malzemeleri "matched" sayıyoruz.
        matched = [r for r in required if r in have_lower]
        if not matched:
            continue

        high_risk_used = [r for r in matched if risk_map.get(r) in ("high", "medium")]
        score = 2.0 * len(matched) - 1.5 * len(missing) + 1.0 * len(high_risk_used)
        from_list = [m for m in matched if m in planned_set]
        has_home = any(m not in planned_set for m in matched)
        score += 0.5 * len(from_list) + (1.0 if from_list and has_home else 0.0)

        reasons = [reasoning] if reasoning else []
        if from_list:
            reasons.append(f"Market listendeki şunları kullanıyor: {', '.join(from_list)}.")
        if high_risk_used:
            reasons.append(f"İsraf riski taşıyan malzemeleri değerlendiriyor: {', '.join(high_risk_used)}.")

        results.append({
            "name": name,
            "score": round(score, 2),
            "matched_ingredients": matched,
            "missing_ingredients": missing,
            "uses_high_risk_ingredients": high_risk_used,
            "reasons": reasons,
            "from_shopping_list": from_list,
            "source": "llm",
        })

    if not results:
        return None

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


import copy
import json
import time

_RECIPE_CACHE = {"key": None, "ts": 0.0, "value": None}
RECIPE_CACHE_TTL_SECONDS = 120


def _cache_key(inventory_items: List[dict], planned_only: List[str]) -> str:
    inv = sorted((_norm(it["food_type"]), str(it["latest_quantity_level"]), str(it["waste_risk"])) for it in inventory_items)
    return json.dumps([inv, sorted(_norm(p) for p in planned_only)], ensure_ascii=False)


def get_recipe_recommendations(
    inventory_items: List[dict],
    planned_food_types: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Ana giriş noktası. Evdeki ürünler VE market listesindeki (planned) ürünler
    birlikte değerlendirilir - tarifler iki kaynağı kombine edebilir.
    Önce LLM denenir, olmazsa genişletilmiş rule-based listeye düşülür.

    Aynı girdi (envanter + liste) için sonuç kısa süre önbelleğe alınır: bir
    yenileme sırasında /recipes ve /shopping-list aynı hesaplamayı paylaşır
    (LLM iki kez çağrılmaz, iki ekran da aynı sonucu gösterir). Envanter veya
    liste değiştiği anda anahtar değişir, hesaplama yeniden yapılır.
    """
    home_norm = {_norm(it["food_type"]) for it in inventory_items}
    planned_only = []
    for p in planned_food_types or []:
        if _norm(p) not in home_norm and _norm(p) not in {_norm(x) for x in planned_only}:
            planned_only.append(p.strip())

    key = _cache_key(inventory_items, planned_only)
    now = time.time()
    if _RECIPE_CACHE["key"] == key and now - _RECIPE_CACHE["ts"] < RECIPE_CACHE_TTL_SECONDS:
        return copy.deepcopy(_RECIPE_CACHE["value"])

    combined = list(inventory_items) + [
        {"food_type": p, "latest_quantity_level": "1", "waste_risk": "low", "planned": True}
        for p in planned_only
    ]

    result = _ask_llm_recipes(combined)
    if not result:
        food_types = [it["food_type"] for it in inventory_items]
        risk_map = {_norm(it["food_type"]): it["waste_risk"] for it in inventory_items}
        result = score_recipes(food_types, risk_map, planned_only)

    _RECIPE_CACHE.update({"key": key, "ts": now, "value": copy.deepcopy(result)})
    return result
