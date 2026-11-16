from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class DetectedRegion(BaseModel):
    """Bir taramada bulunan aday nesne bölgesi (henüz kayıt edilmedi)."""
    region_id: str
    bbox: List[int]  # [x, y, w, h]
    crop_base64: str  # kullanıcıya gösterilecek küçük görsel
    suggested_container_id: Optional[int] = None  # basit eşleştirme varsa
    suggested_food_type: Optional[str] = None  # YOLO-World kullanılıyorsa dolu gelir
    suggested_confidence: Optional[float] = None
    suggested_label: Optional[str] = None      # model ne gördü (ör. "şişe") - ipucu olarak gösterilir
    suggested_category: Optional[str] = None   # ör. "İçecek/sos", "Meyve-sebze", "Süt ürünü", "Hazır yemek"
    suggestion_kind: Optional[str] = None      # "specific" | "maybe" | "generic"


class ScanResponse(BaseModel):
    scan_id: str
    detector: str  # "yolo_world" | "classical" - hangi yöntem kullanıldı
    yolo_status: str = "unavailable"  # "ready" | "loading" | "unavailable" | "disabled"
    yolo_message: str = ""  # kullanıcıya gösterilecek açıklama
    regions: List[DetectedRegion]


class ConfirmRegionRequest(BaseModel):
    container_id: Optional[int] = None  # None -> otomatik eşleştir ya da yeni oluştur
    force_new_container: bool = False    # True -> otomatik eşleştirmeyi atla, hep yeni container aç
    food_type: str
    quantity_level: str  # less_half | 1 | 2 | 3plus | custom
    custom_quantity_value: Optional[float] = None  # quantity_level == "custom" ise porsiyon sayısı
    # Normalde backend "şimdi" zamanını kullanır. Bu alan yalnızca geçmişe
    # dönük veri girişi / test senaryoları için opsiyoneldir.
    observed_at: Optional[datetime] = None
    # Elle girilen GERÇEK satın alma tarihi; israf riski hesabında started_at yerine kullanılır
    purchased_at: Optional[datetime] = None
    entry_source: str = "scan"  # 'manual' = fotoğrafsız elle eklendi


class ObservationOut(BaseModel):
    id: int
    observed_at: datetime
    quantity_level: str
    source: str

    class Config:
        from_attributes = True


class FoodInstanceOut(BaseModel):
    id: int
    food_type: str
    started_at: datetime
    is_active: bool
    observations: List[ObservationOut] = []

    class Config:
        from_attributes = True


class ContainerOut(BaseModel):
    id: int
    label: Optional[str]
    last_seen_at: datetime
    food_instances: List[FoodInstanceOut] = []

    class Config:
        from_attributes = True


class ContainerSummary(BaseModel):
    """Kullanıcının 'bu hangi kaba ait?' seçimi yapması için kısa özet."""
    container_id: int
    food_type: str
    latest_quantity_level: str
    last_observed_at: datetime


class InventoryItem(BaseModel):
    container_id: int
    food_instance_id: int
    food_type: str
    latest_quantity_level: str
    last_observed_at: datetime
    # MVP2/3/4 - analiz alanları (yeterli veri yoksa None)
    consumption_rate_per_day: Optional[float] = None  # porsiyon/gün
    estimated_days_remaining: Optional[float] = None
    waste_risk: str = "unknown"  # low | medium | high | spoiled | unknown
    risk_label: str = ""
    waste_reasons: List[str] = []
    risk_basis: str = "consumption"  # "consumption" | "shelf_life_llm" | "shelf_life_table"
    observation_count: int = 1
    purchased_at: Optional[datetime] = None
    entry_source: str = "scan"


class RecipeRecommendation(BaseModel):
    name: str
    score: float
    matched_ingredients: List[str]
    missing_ingredients: List[str]
    uses_high_risk_ingredients: List[str]
    also_needed: List[str] = []  # tarifi tamamlayan (zorunlu olmayan) eksikler
    from_shopping_list: List[str] = []  # bu tarifte market listesinden gelen malzemeler
    reasons: List[str]
    source: str = "rule_based"  # "llm" | "rule_based"


class ShoppingListItem(BaseModel):
    id: Optional[int] = None  # sadece manuel öğelerde dolu (silmek için gerekli)
    food_type: str
    reason: str
    urgency: str  # "runs_out_soon" | "needed_for_recipe" | "manual"
    source: str = "auto"  # "auto" | "manual"


class ManualShoppingItemCreate(BaseModel):
    food_type: str
    note: Optional[str] = None


class DismissShoppingItemRequest(BaseModel):
    food_type: str


class FoodTypeSuggestion(BaseModel):
    food_type: str
    use_count: int


class HistoryItem(BaseModel):
    food_instance_id: int
    container_id: int
    food_type: str
    quantity_level: str
    observed_at: datetime
    days_since_previous: Optional[float] = None
    previous_quantity_level: Optional[str] = None
    consumption_rate_per_day: Optional[float] = None  # önceki gözleme göre porsiyon/gün
    rate_note: str = ""                                # hız neden yok / nasıl hesaplandı


class RemoveInventoryRequest(BaseModel):
    reason: str  # "consumed" (tükettim) | "discarded" (attım/bozuldu) | "mistake" (yanlış kayıt, tamamen sil)
    removed_at: Optional[datetime] = None  # arayüzün yerel saati; verilmezse sunucu saati


class CvStatus(BaseModel):
    status: str   # "ready" | "loading" | "unavailable" | "disabled"
    reason: str
    message: str
    model: Optional[str] = None
