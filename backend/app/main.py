"""
Smart Pantry AI - Backend (MVP1-6 + v4 düzeltmeleri)

Akış:
  1. POST /scan                    -> fotoğraf yükle, aday nesne bölgelerini al
  2. GET  /containers               -> mevcut kapları listele
  3. GET  /containers/active-summary-> confirm ekranında "hangi kaba ait" seçimi için özet
  4. POST /confirm                  -> kullanıcının onayladığı bölgeyi kaydet
                                        (container_id verilmezse, aynı yiyecek türüyle
                                        aktif bir container varsa OTOMATİK ona bağlanır -
                                        tüketim hızının hesaplanabilmesi için KRİTİK)
  5. GET  /inventory                -> envanter + tüketim hızı + forecast + israf riski
  6. GET  /history                  -> tüm gözlem geçmişi (tarih + gün farkı ile)
  7. GET  /food-types                -> kullanıcının daha önce girdiği yiyecek isimleri
  8. GET  /recipes/recommendations  -> tarif önerileri (LLM varsa LLM, yoksa rule-based)
  9. GET  /shopping-list            -> otomatik + manuel alışveriş listesi
 10. POST/DELETE /shopping-list/manual -> manuel öğe ekle/sil
"""
import uuid
from datetime import datetime
from typing import List, Optional

import os
import threading

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db, ensure_schema
from app import models, schemas
from app.cv.detector import detect_regions
from app import forecasting
from app.recipes import get_recipe_recommendations as get_recipes_for_inventory
from app.shopping import build_shopping_list

Base.metadata.create_all(bind=engine)
ensure_schema(engine)  # eski veritabanına yeni sütunları ekler (veri korunur)

app = FastAPI(title="Smart Pantry AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _warm_up_detector():
    """YOLO-World modeli ilk taramada yüklenirse ilk tarama çok yavaş olur; arka planda önceden yükle."""
    if os.environ.get("SMART_PANTRY_USE_YOLO", "1") != "0":
        from app.cv.detector import warm_up_yolo
        threading.Thread(target=warm_up_yolo, daemon=True).start()


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.post("/scan", response_model=schemas.ScanResponse)
async def scan_fridge(file: UploadFile = File(...)):
    image_bytes = await file.read()
    # CPU-yoğun tespit ayrı iş parçacığında çalışır: tarama sürerken sunucu diğer
    # isteklere (envanter/tarif yenilemeleri) yanıt verebilir.
    result = await run_in_threadpool(detect_regions, image_bytes)
    return schemas.ScanResponse(
        scan_id=str(uuid.uuid4())[:8],
        detector=result["detector"],
        yolo_status=result.get("yolo_status", "unavailable"),
        yolo_message=result.get("yolo_message", ""),
        regions=[schemas.DetectedRegion(**r) for r in result["regions"]],
    )


@app.get("/containers", response_model=List[schemas.ContainerOut])
def list_containers(db: Session = Depends(get_db)):
    return db.query(models.Container).order_by(models.Container.last_seen_at.desc()).all()


@app.get("/containers/active-summary", response_model=List[schemas.ContainerSummary])
def containers_active_summary(db: Session = Depends(get_db)):
    """Confirm ekranında 'bu hangi kaba ait?' seçimi için kısa özet listesi."""
    active_instances = (
        db.query(models.FoodInstance)
        .filter(models.FoodInstance.is_active == True)  # noqa: E712
        .all()
    )
    results = []
    for inst in active_instances:
        last_obs = (
            db.query(models.Observation)
            .filter(models.Observation.food_instance_id == inst.id)
            .order_by(models.Observation.observed_at.desc())
            .first()
        )
        if not last_obs:
            continue
        results.append(schemas.ContainerSummary(
            container_id=inst.container_id,
            food_type=inst.food_type,
            latest_quantity_level=last_obs.quantity_level,
            last_observed_at=last_obs.observed_at,
        ))
    results.sort(key=lambda r: r.last_observed_at, reverse=True)
    return results


@app.get("/food-types", response_model=List[schemas.FoodTypeSuggestion])
def food_type_suggestions(db: Session = Depends(get_db)):
    """
    Kullanıcının daha önce girdiği tüm yiyecek isimleri, kaç kez kullanıldığına
    göre sıralı. Frontend bunu sabit örnek listesiyle birleştirip öneri olarak
    gösteriyor - "elma" bir kere girildiyse bir daha yazmana gerek kalmıyor.
    """
    rows = db.query(models.FoodInstance.food_type).all()
    counts: dict = {}
    for (food_type,) in rows:
        key = food_type.strip()
        counts[key] = counts.get(key, 0) + 1
    suggestions = [
        schemas.FoodTypeSuggestion(food_type=k, use_count=v) for k, v in counts.items()
    ]
    suggestions.sort(key=lambda s: (-s.use_count, s.food_type.lower()))
    return suggestions


def _find_auto_match_container(db: Session, food_type: str) -> Optional[models.Container]:
    """
    container_id verilmediğinde kullanılan otomatik eşleştirme:
    aynı yiyecek türüyle şu anda aktif bir FoodInstance'ı olan bir container
    varsa onu döner (en son görüleni tercih eder). Yoksa None döner (yeni
    container açılır).

    Bu, gerçek görsel re-identification (CLIP/embedding) gelene kadarki
    pratik bir yaklaşım: "aynı isimli ürün = muhtemelen aynı kap".
    """
    key = food_type.strip().lower()
    candidate = (
        db.query(models.FoodInstance)
        .join(models.Container)
        .filter(
            models.FoodInstance.is_active == True,  # noqa: E712
            models.FoodInstance.food_type.ilike(key),
        )
        .order_by(models.Container.last_seen_at.desc())
        .first()
    )
    return candidate.container if candidate else None


@app.post("/confirm", response_model=schemas.ContainerOut)
def confirm_region(
    payload: schemas.ConfirmRegionRequest, db: Session = Depends(get_db)
):
    now = payload.observed_at or datetime.utcnow()

    if payload.container_id is not None:
        container = db.query(models.Container).get(payload.container_id)
        if container is None:
            raise HTTPException(status_code=404, detail="Container bulunamadı")
        container.last_seen_at = now
    elif not payload.force_new_container:
        # KRİTİK DÜZELTME: eskiden container_id verilmediğinde HER ZAMAN yeni
        # bir container açılıyordu - bu yüzden aynı ürünü iki kez tarasan bile
        # asla ikinci bir Observation aynı FoodInstance'a eklenmiyordu ve
        # tüketim hızı hiçbir zaman hesaplanamıyordu. Şimdi önce otomatik
        # eşleştirme deneniyor.
        matched = _find_auto_match_container(db, payload.food_type)
        if matched is not None:
            container = matched
            container.last_seen_at = now
        else:
            container = models.Container(last_seen_at=now)
            db.add(container)
            db.flush()
    else:
        container = models.Container(last_seen_at=now)
        db.add(container)
        db.flush()

    # Bu container için aktif bir FoodInstance var mı ve food_type aynı mı?
    active_instance = (
        db.query(models.FoodInstance)
        .filter(
            models.FoodInstance.container_id == container.id,
            models.FoodInstance.is_active == True,  # noqa: E712
        )
        .first()
    )

    if active_instance and active_instance.food_type.strip().lower() == payload.food_type.strip().lower():
        # Aynı yiyecek devam ediyor -> sadece yeni bir Observation ekle
        instance = active_instance
        if payload.purchased_at is not None:
            instance.purchased_at = payload.purchased_at
    else:
        # Yiyecek değişti (ya da hiç yoktu) -> eski instance'ı kapat, yenisini aç
        if active_instance:
            active_instance.is_active = False
            active_instance.end_reason = "replaced"
            active_instance.ended_at = now
        instance = models.FoodInstance(
            container_id=container.id,
            food_type=payload.food_type,
            started_at=now,
            purchased_at=payload.purchased_at,
            entry_source=payload.entry_source if payload.entry_source in ("scan", "manual") else "scan",
            is_active=True,
        )
        db.add(instance)
        db.flush()

    quantity_level = payload.quantity_level
    if quantity_level == "custom" and payload.custom_quantity_value is not None:
        quantity_level = f"custom:{payload.custom_quantity_value}"

    observation = models.Observation(
        food_instance_id=instance.id,
        observed_at=now,
        quantity_level=quantity_level,
        source="user_confirmed",
    )
    db.add(observation)

    db.commit()
    db.refresh(container)
    return container


def _build_inventory_analytics(db: Session) -> List[dict]:
    """
    MVP1 envanterine MVP2 (tüketim hızı) + MVP3 (forecast) + MVP4 (israf riski,
    tüketim verisi yoksa genel bozulma süresi tahminiyle) analizlerini ekler.
    Diğer endpoint'ler (recipes, shopping-list) de bunu kullanır.
    """
    results = []
    active_instances = (
        db.query(models.FoodInstance)
        .filter(models.FoodInstance.is_active == True)  # noqa: E712
        .all()
    )
    for inst in active_instances:
        observations = (
            db.query(models.Observation)
            .filter(models.Observation.food_instance_id == inst.id)
            .order_by(models.Observation.observed_at.asc())
            .all()
        )
        if not observations:
            continue
        last_obs = observations[-1]

        rate = forecasting.compute_consumption_rate(observations)
        consumption_days_remaining = forecasting.compute_forecast(last_obs.quantity_level, rate)
        leftover_count = forecasting.count_past_leftovers(db, inst.food_type, inst.id)

        risk, risk_label, reasons, days_remaining, basis = forecasting.compute_waste_risk(
            food_type=inst.food_type,
            latest_quantity_level=last_obs.quantity_level,
            consumption_rate=rate,
            consumption_days_remaining=consumption_days_remaining,
            started_at=inst.started_at,
            history_leftover_count=leftover_count,
            purchased_at=inst.purchased_at,
        )

        results.append({
            "container_id": inst.container_id,
            "food_instance_id": inst.id,
            "food_type": inst.food_type,
            "latest_quantity_level": last_obs.quantity_level,
            "last_observed_at": last_obs.observed_at,
            "consumption_rate_per_day": rate,
            "estimated_days_remaining": days_remaining,
            "waste_risk": risk,
            "risk_label": risk_label,
            "waste_reasons": reasons,
            "risk_basis": basis,
            "observation_count": len(observations),
            "purchased_at": inst.purchased_at,
            "entry_source": inst.entry_source or "scan",
        })
    return results


@app.get("/inventory", response_model=List[schemas.InventoryItem])
def get_inventory(db: Session = Depends(get_db)):
    return _build_inventory_analytics(db)


@app.get("/history", response_model=List[schemas.HistoryItem])
def get_history(db: Session = Depends(get_db)):
    """
    Tüm gözlem geçmişi (aktif olsun olmasın TÜM FoodInstance'lar dahil),
    tarih sırasıyla + aynı üründeki bir önceki gözleme göre gün farkıyla.
    """
    all_instances = db.query(models.FoodInstance).all()
    items = []
    for inst in all_instances:
        observations = (
            db.query(models.Observation)
            .filter(models.Observation.food_instance_id == inst.id)
            .order_by(models.Observation.observed_at.asc())
            .all()
        )
        prev_time = None
        prev_quantity = None
        for obs in observations:
            days_since_previous = None
            rate = None
            if prev_time is None:
                note = "İlk tarama - karşılaştıracak önceki kayıt yok."
            else:
                days_since_previous = round((obs.observed_at - prev_time).total_seconds() / 86400.0, 2)
                drop = forecasting.quantity_to_value(prev_quantity) - forecasting.quantity_to_value(obs.quantity_level)
                if days_since_previous < forecasting.MIN_DAYS_FOR_RATE:
                    note = ("İki kayıt arası 12 saatten kısa; bu kadar kısa sürede hız güvenilir "
                            "hesaplanamaz (aynı gün art arda tarama).")
                elif drop <= 0:
                    note = "Miktar azalmamış (aynı kalmış ya da yeniden doldurulmuş) - tüketim yok."
                else:
                    rate = round(drop / days_since_previous, 3)
                    note = f"{round(drop, 2)} porsiyon / {days_since_previous} gün."
            items.append(schemas.HistoryItem(
                food_instance_id=inst.id,
                container_id=inst.container_id,
                food_type=inst.food_type,
                quantity_level=obs.quantity_level,
                observed_at=obs.observed_at,
                days_since_previous=days_since_previous,
                previous_quantity_level=prev_quantity,
                consumption_rate_per_day=rate,
                rate_note=note,
            ))
            prev_time = obs.observed_at
            prev_quantity = obs.quantity_level

    items.sort(key=lambda i: i.observed_at, reverse=True)
    return items


def _planned_food_types(db: Session) -> List[str]:
    """Kullanıcının market listesine elle eklediği ürünler - tariflerde evdekilerle birleştirilir."""
    return [m.food_type for m in db.query(models.ManualShoppingItem).all()]


@app.get("/recipes/recommendations", response_model=List[schemas.RecipeRecommendation])
def recipe_recommendations(db: Session = Depends(get_db)):
    inventory = _build_inventory_analytics(db)
    return get_recipes_for_inventory(inventory, _planned_food_types(db))


@app.get("/shopping-list", response_model=List[schemas.ShoppingListItem])
def shopping_list(db: Session = Depends(get_db)):
    inventory = _build_inventory_analytics(db)
    top_recipes = get_recipes_for_inventory(inventory, _planned_food_types(db))
    auto_items = build_shopping_list(inventory, top_recipes)
    dismissed = {r[0].strip().lower() for r in db.query(models.DismissedShoppingItem.food_type).all()}
    auto_items = [it for it in auto_items if it["food_type"].strip().lower() not in dismissed]

    result = [schemas.ShoppingListItem(**item, source="auto") for item in auto_items]

    manual_items = db.query(models.ManualShoppingItem).order_by(
        models.ManualShoppingItem.added_at.desc()
    ).all()
    for m in manual_items:
        result.append(schemas.ShoppingListItem(
            id=m.id,
            food_type=m.food_type,
            reason=m.note or "Elle eklendi.",
            urgency="manual",
            source="manual",
        ))
    return result


@app.post("/shopping-list/manual", response_model=schemas.ShoppingListItem)
def add_manual_shopping_item(payload: schemas.ManualShoppingItemCreate, db: Session = Depends(get_db)):
    item = models.ManualShoppingItem(food_type=payload.food_type, note=payload.note)
    db.add(item)
    db.commit()
    db.refresh(item)
    return schemas.ShoppingListItem(
        id=item.id,
        food_type=item.food_type,
        reason=item.note or "Elle eklendi.",
        urgency="manual",
        source="manual",
    )


@app.delete("/shopping-list/manual/{item_id}")
def delete_manual_shopping_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(models.ManualShoppingItem).get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Öğe bulunamadı")
    db.delete(item)
    db.commit()
    return {"deleted": True}


@app.post("/shopping-list/dismiss")
def dismiss_shopping_item(payload: schemas.DismissShoppingItemRequest, db: Session = Depends(get_db)):
    """Otomatik bir öneriyi ('bitiyor' / 'tarif için') listeden gizler."""
    db.add(models.DismissedShoppingItem(food_type=payload.food_type))
    db.commit()
    return {"dismissed": payload.food_type}


@app.delete("/shopping-list/dismissed")
def clear_dismissed_shopping_items(db: Session = Depends(get_db)):
    """Gizlenen tüm otomatik önerileri sıfırlar."""
    db.query(models.DismissedShoppingItem).delete()
    db.commit()
    return {"cleared": True}


@app.post("/inventory/{food_instance_id}/remove")
def remove_inventory_item(
    food_instance_id: int,
    payload: schemas.RemoveInventoryRequest,
    db: Session = Depends(get_db),
):
    """
    Envanterden ürün çıkarır (üç farklı anlamda):
      consumed  - "Tükettim": son gözlem olarak 0 porsiyon eklenir, ürün kapanır (israf SAYILMAZ)
      discarded - "Attım/bozuldu": ürün kapanır, geçmişte "israf" olarak sayılır
                  (sonraki risk tahminlerinde bu ürün için uyarıyı yükseltir)
      mistake   - "Yanlış kayıt": ürün ve gözlemleri tamamen SİLİNİR, geçmişte iz kalmaz
    """
    if payload.reason not in ("consumed", "discarded", "mistake"):
        raise HTTPException(status_code=400, detail="reason: consumed | discarded | mistake")

    inst = db.query(models.FoodInstance).get(food_instance_id)
    if inst is None or not inst.is_active:
        raise HTTPException(status_code=404, detail="Aktif envanter ürünü bulunamadı")

    if payload.reason == "mistake":
        container = inst.container
        db.delete(inst)
        db.flush()
        if not container.food_instances:
            db.delete(container)
        db.commit()
        return {"removed": food_instance_id, "reason": "mistake"}

    last_obs = (
        db.query(models.Observation)
        .filter(models.Observation.food_instance_id == inst.id)
        .order_by(models.Observation.observed_at.desc())
        .first()
    )
    when = payload.removed_at or datetime.utcnow()
    if last_obs and when < last_obs.observed_at:
        when = last_obs.observed_at  # çıkarma, son taramadan önce görünmesin

    if payload.reason == "consumed":
        db.add(models.Observation(
            food_instance_id=inst.id,
            observed_at=when,
            quantity_level="custom:0",
            source="user_removed",
        ))
    inst.is_active = False
    inst.ended_at = when
    inst.end_reason = payload.reason
    db.commit()
    return {"removed": food_instance_id, "reason": payload.reason}


@app.get("/cv/status", response_model=schemas.CvStatus)
def cv_status():
    """Dedektörün (YOLO-World / klasik) durumu - arayüz bunu gösterir ve yüklenirken yoklar."""
    from app.cv.detector import get_cv_status
    return get_cv_status()
