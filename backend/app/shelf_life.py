"""
Smart Pantry AI - Shelf Life Estimation

Kullanıcının istediği iyileştirme: tek gözlemli (henüz tüketim geçmişi
olmayan) ürünler için de bir risk fikri vermek. "Veri yetersiz" demek yerine,
o yiyeceğin GENEL bozulma süresini kullanıyoruz.

İki katman:
1. Ollama (varsa) - herhangi bir yiyecek için genelleşebilir, esnek tahmin
2. Sabit tablo - Ollama yoksa/başarısız olursa devreye giren yedek

Sonuçlar bellek-içi cache'leniyor (aynı yiyecek türü için tekrar tekrar
LLM'e sormaya gerek yok - sunucu her yeniden başladığında sıfırlanır).
"""
import re
from typing import Dict, Optional, Tuple

from app.llm_client import ask_json

# Yedek tablo: Ollama kullanılamıyorsa devreye girer. Gün cinsinden,
# buzdolabında saklama için kaba/yaklaşık değerler.
# Yedek tablo: Ollama kullanılamıyorsa devreye girer. Gün cinsinden, BUZDOLABINDA
# saklanan bütün/açılmamış ürünler için yaklaşık değerler. Çiğ et/tavuk/balık gibi
# gıda güvenliği açısından kritik ürünler bilerek kısa tutuldu.
FALLBACK_SHELF_LIFE_DAYS: Dict[str, float] = {
    # süt ürünleri / yumurta
    "süt": 6, "yoğurt": 10, "ayran": 10, "kefir": 14, "peynir": 14, "beyaz peynir": 14,
    "kaşar": 21, "lor": 5, "labne": 10, "krema": 7, "tereyağı": 30, "yumurta": 28,
    # et / balık (çiğ: kısa) ve şarküteri
    "tavuk": 2, "pişmiş tavuk": 4, "hindi": 2, "kıyma": 2, "et": 3, "biftek": 3, "balık": 2,
    "sucuk": 14, "salam": 7, "jambon": 7, "sosis": 7,
    # hazır / pişmiş yemekler
    "kalan yemek": 4, "yemek": 4, "çorba": 4, "pilav": 4, "makarna": 4, "salata": 3,
    "hummus": 7, "turşu": 90, "zeytin": 30, "reçel": 60,
    # sebze
    "ıspanak": 5, "marul": 5, "roka": 4, "maydanoz": 7, "dereotu": 5, "domates": 10,
    "salatalık": 7, "biber": 12, "dolmalık biber": 12, "sivri biber": 10, "patlıcan": 7,
    "kabak": 7, "havuç": 21, "patates": 30, "soğan": 30, "sarımsak": 30, "brokoli": 5,
    "karnabahar": 7, "lahana": 14, "mantar": 5, "turp": 10, "pırasa": 10, "kereviz": 14,
    "pancar": 14, "mısır": 5, "bezelye": 5, "fasulye": 5, "avokado": 5, "sebze": 7,
    # meyve
    "limon": 21, "portakal": 21, "mandalina": 14, "greyfurt": 21, "elma": 28, "armut": 10,
    "üzüm": 10, "çilek": 5, "muz": 6, "kayısı": 6, "şeftali": 6, "kavun": 10, "karpuz": 10,
    "kiraz": 7, "vişne": 5, "erik": 6, "incir": 4, "nar": 30, "kivi": 14, "ananas": 7,
    "mango": 6, "ahududu": 3, "böğürtlen": 3, "yaban mersini": 10, "hurma": 14, "meyve": 7,
    # içecek
    "soda": 180, "maden suyu": 180, "kola": 180, "meyve suyu": 7,
}
DEFAULT_SHELF_LIFE_DAYS = 7.0  # tabloda olmayan bir yiyecek için genel varsayım (eskiden 5 gündü, taze ürünler için çok kısaydı)
_PLURAL_SUFFIXES = ("ler", "lar", "i", "ı", "u", "ü", "si", "sı", "in", "ın", "un", "ün")


def lookup_fallback_days(key: str) -> Tuple[float, str]:
    """
    Yiyecek adından tablo değerini bulur. Döner: (gün, eşleşme_türü)
    eşleşme_türü: "exact" | "keyword" | "default"
    - Tam eşleşme önce denenir.
    - Sonra kelime sınırlarıyla en uzun anahtar bulunur ("kırmızı biber" -> "biber",
      "meyve suyu" -> "meyve suyu"; "su" gibi kısa anahtarın yanlış eşleşmesini önler).
    - Çoğul/ek almış hâller de eşleşir ("domatesler", "elmalar").
    """
    if key in FALLBACK_SHELF_LIFE_DAYS:
        return FALLBACK_SHELF_LIFE_DAYS[key], "exact"

    padded = f" {key} "
    tokens = re.findall(r"\w+", key, flags=re.UNICODE)
    for k in sorted(FALLBACK_SHELF_LIFE_DAYS, key=len, reverse=True):
        if f" {k} " in padded:
            return FALLBACK_SHELF_LIFE_DAYS[k], "keyword"
        for t in tokens:
            if any(t == k + suf for suf in _PLURAL_SUFFIXES):
                return FALLBACK_SHELF_LIFE_DAYS[k], "keyword"
    return DEFAULT_SHELF_LIFE_DAYS, "default"


_cache: Dict[str, dict] = {}


def _ask_llm_shelf_life(food_type: str) -> Optional[dict]:
    prompt = (
        f"Bir buzdolabında saklanan '{food_type}' genellikle kaç günde "
        "bozulur, tazeliğini kaybeder ya da tüketilmesi önerilmeyen hale gelir?\n"
        "SADECE şu JSON formatında yanıt ver, başka hiçbir metin ekleme:\n"
        '{"typical_days": <sayı>, "reasoning": "<kısa, tek cümlelik Türkçe açıklama>"}'
    )
    data = ask_json(prompt)
    if not isinstance(data, dict):
        return None
    try:
        days = float(data["typical_days"])
        if days <= 0 or days > 365:
            return None
        reasoning = str(data.get("reasoning", "")).strip()
        return {"typical_days": days, "reasoning": reasoning, "source": "shelf_life_llm"}
    except (KeyError, ValueError, TypeError):
        return None


def get_shelf_life(food_type: str) -> dict:
    """Returns {"typical_days": float, "reasoning": str, "source": str}"""
    key = food_type.strip().lower()
    if key in _cache:
        return _cache[key]

    result = _ask_llm_shelf_life(key)
    if result is None:
        days, match = lookup_fallback_days(key)
        reasoning = (
            "Bu ürün tabloda yok, genel varsayım kullanıldı." if match == "default"
            else "Genel/yaklaşık bir tahmin (sabit tablo)."
        )
        result = {
            "typical_days": days,
            "reasoning": reasoning,
            "source": "shelf_life_table",
            "match": match,
        }

    _cache[key] = result
    return result
