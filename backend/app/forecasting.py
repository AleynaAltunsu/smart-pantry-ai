"""
Smart Pantry AI - Forecasting & Waste Risk (MVP2 + MVP3 + MVP4)

Bilinçli tasarım kararı: gram değil, porsiyon/seviye üzerinden çalışıyoruz
(plandaki karar - kameradan gram tahmini güvenilir değil).

MVP2 - Tüketim hızı: art arda gözlemlerden porsiyon/gün hesapla
MVP3 - Forecast: kalan miktar / tüketim hızı = kaç gün sonra bitecek
MVP4 - İsraf riski: kalan süre + geçmiş davranış -> açıklamalı risk skoru
"""
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Observation, FoodInstance

# Porsiyon seviyelerini sayısal değere çeviriyoruz (yaklaşık, kasıtlı olarak kaba)
QUANTITY_VALUES = {
    "less_half": 0.4,
    "1": 1.0,
    "2": 2.0,
    "3plus": 3.5,
}


def quantity_to_value(level: str) -> float:
    if level.startswith("custom:"):
        try:
            return float(level.split(":", 1)[1])
        except (ValueError, IndexError):
            return 1.0
    return QUANTITY_VALUES.get(level, 1.0)


def quantity_label(level: str) -> str:
    """Arayüzde/loglarda gösterilecek okunabilir etiket."""
    if level.startswith("custom:"):
        return f"{quantity_to_value(level):g} porsiyon"
    return {
        "less_half": "½'den az", "1": "1 porsiyon", "2": "2 porsiyon", "3plus": "3+ porsiyon",
    }.get(level, level)


MIN_DAYS_FOR_RATE = 0.5  # bundan daha yakın zamanlı iki tarama, tüketim hızı için güvenilir değil


def compute_consumption_rate(observations: List[Observation]) -> Optional[float]:
    """
    Porsiyon/gün olarak tüketim hızı.

    v5 - daha akıllı hesap: sadece ilk/son gözleme bakmak yerine, ARDIŞIK
    HER ÇİFT arasındaki düşüşü ayrı ayrı hesaplayıp zaman-ağırlıklı ortalama
    alıyoruz. Yani 5 taramalık bir geçmişin hepsi kullanılıyor, sadece ilk ve
    son değil - bu, tek bir hatalı/gürültülü gözlemin tüm tahmini bozmasını
    engeller ve daha fazla veri noktası biriktikçe tahmin doğallıkla iyileşir.

    Kural: yalnızca aralarında en az MIN_DAYS_FOR_RATE (12 saat) olan VE
    miktarı gerçekten azalmış olan ardışık çiftler sayılır (aynı gün içinde
    art arda test taramaları ya da bir yeniden-doldurma/alışveriş olayı
    dışlanır). Sonuç = toplam_azalma / toplam_geçerli_süre (zaman-ağırlıklı
    ortalama - uzun aralıklar kısa olanlardan daha güvenilir kabul edilir).
    """
    if len(observations) < 2:
        return None

    obs_sorted = sorted(observations, key=lambda o: o.observed_at)

    total_drop = 0.0
    total_days = 0.0
    for prev, curr in zip(obs_sorted, obs_sorted[1:]):
        days_elapsed = (curr.observed_at - prev.observed_at).total_seconds() / 86400.0
        if days_elapsed < MIN_DAYS_FOR_RATE:
            continue  # cok yakin zamanli - guvenilir degil, atla
        value_drop = quantity_to_value(prev.quantity_level) - quantity_to_value(curr.quantity_level)
        if value_drop <= 0:
            continue  # miktar artmis/aynı kalmis (yeniden doldurma) - bu araligi sayma
        total_drop += value_drop
        total_days += days_elapsed

    if total_days <= 0:
        return None

    return round(total_drop / total_days, 3)


def compute_forecast(
    latest_quantity_level: str, consumption_rate: Optional[float]
) -> Optional[float]:
    """Kaç gün sonra biteceğini tahmin eder (porsiyon / porsiyon-gün)."""
    if consumption_rate is None or consumption_rate <= 0:
        return None
    remaining_value = quantity_to_value(latest_quantity_level)
    return round(remaining_value / consumption_rate, 1)


RISK_LABELS = {
    "spoiled": "🚫 TÜKETME (muhtemelen bozulmuş)",
    "high": "⚠️ ACİL TÜKET",
    "medium": "Orta risk",
    "low": "Düşük risk",
    "unknown": "Veri yetersiz",
}


def compute_waste_risk(
    food_type: str,
    latest_quantity_level: str,
    consumption_rate: Optional[float],
    consumption_days_remaining: Optional[float],
    started_at: datetime,
    history_leftover_count: int = 0,
    now: Optional[datetime] = None,
    purchased_at: Optional[datetime] = None,
) -> Tuple[str, str, List[str], Optional[float], str]:
    """
    v6 eşikleri:
      days_remaining <= 0       -> spoiled (TÜKETME)
      0 < days_remaining <= 3   -> high    (ACİL TÜKET)
      3 < days_remaining <= 5   -> medium  (Orta risk)
      days_remaining > 5        -> low     (Düşük risk)

    Tüketim geçmişi varsa o önceliklidir; yoksa genel bozulma süresi kullanılır.
    purchased_at verilmişse bozulma süresi started_at (ilk tarama) yerine
    gerçek satın alma tarihinden sayılır.

    Döner: (risk, risk_label, reasons, estimated_days_remaining, basis)
    """
    now = now or datetime.utcnow()
    reasons: List[str] = []

    if consumption_rate is not None and consumption_days_remaining is not None:
        basis = "consumption"
        days_remaining = consumption_days_remaining
        reasons.append(f"Kalan miktar: ~{quantity_to_value(latest_quantity_level):.1f} porsiyon.")
        reasons.append(f"Ortalama tüketim hızın: ~{consumption_rate:.2f} porsiyon/gün.")
    else:
        from app.shelf_life import get_shelf_life
        shelf = get_shelf_life(food_type)
        baseline_start = purchased_at or started_at
        days_since_started = (now - baseline_start).total_seconds() / 86400.0
        days_remaining = round(shelf["typical_days"] - days_since_started, 1)
        basis = shelf["source"]
        date_note = " (satın alma tarihine göre)" if purchased_at else ""
        if basis == "shelf_life_llm" or shelf.get("match") == "default":
            extra = f" {shelf['reasoning']}"
        else:
            extra = " (yaklaşık değer)"
        reasons.append(
            f"Tüketim geçmişi henüz yok - genel bozulma süresi tahmini{date_note}: "
            f"~{shelf['typical_days']:.0f} gün.{extra}"
        )
        origin = "satın alınmış" if purchased_at else "ilk kez taranmış"
        reasons.append(f"Bu ürün {max(days_since_started, 0):.1f} gün önce {origin}.")

    if days_remaining <= 0:
        risk = "spoiled"
        reasons.append("Tahmini raf ömrü dolmuş - muhtemelen bozulmuş, tüketme.")
    elif days_remaining <= 3:
        risk = "high"
        reasons.append(f"Yaklaşık {days_remaining} gün içinde bozulma/tükenme riski var - acil tüket.")
    elif days_remaining <= 5:
        risk = "medium"
        reasons.append(f"Yaklaşık {days_remaining} gün içinde riskli hale gelebilir.")
    else:
        risk = "low"
        reasons.append(f"Yaklaşık {days_remaining} gün daha iyi durumda kalabilir.")

    if history_leftover_count > 0:
        reasons.append(f"Bu ürünü geçmişte {history_leftover_count} kez bitirmeden bırakmışsın.")
        if risk == "low":
            risk = "medium"
        elif risk == "medium":
            risk = "high"

    return risk, RISK_LABELS.get(risk, risk), reasons, days_remaining, basis


def count_past_leftovers(db: Session, food_type: str, exclude_instance_id: int) -> int:
    """
    Aynı yiyecek türü için geçmişte (artık aktif olmayan) kaç FoodInstance,
    son gözleminde hâlâ '1 porsiyon veya üzeri' iken kapanmış (= muhtemelen
    bitirilmeden atılmış/değiştirilmiş).
    """
    past_instances = (
        db.query(FoodInstance)
        .filter(
            FoodInstance.food_type == food_type,
            FoodInstance.is_active == False,  # noqa: E712
            FoodInstance.id != exclude_instance_id,
        )
        .all()
    )

    leftover_count = 0
    for inst in past_instances:
        reason = getattr(inst, "end_reason", None)
        if reason == "consumed":
            continue  # kullanıcı "tükettim" dedi - israf değil
        if reason == "discarded":
            leftover_count += 1  # kullanıcı "attım/bozuldu" dedi - miktar ne olursa olsun israf
            continue
        obs = (
            db.query(Observation)
            .filter(Observation.food_instance_id == inst.id)
            .order_by(Observation.observed_at.desc())
            .first()
        )
        if obs and quantity_to_value(obs.quantity_level) >= 1.0:
            leftover_count += 1

    return leftover_count
