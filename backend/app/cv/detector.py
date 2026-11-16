"""
Smart Pantry AI - CV Detection Layer (v2)

İki katman var:

1. classical_detect_regions() — OpenCV tabanlı, bağımlılıksız, her zaman çalışır.
   v1'deki temel sorunları düzeltir:
   - "Bütün dolap tek kutu" problemi -> alan oranı filtresi (görüntünün
     %55'inden büyük kutular elenir)
   - "Raf kenarı/dolap köşesi container sanılıyor" problemi -> en-boy oranı
     filtresi (çok ince/uzun şeritler elenir) + Canny'nin yanına adaptif
     eşikleme eklenerek daha "nesne" şekilli bölgeler yakalanır
   - Tekrarlayan/örtüşen kutular -> basit IoU tabanlı NMS

2. yolo_world_detect_regions() — GERÇEK bir açık-kelime dağarcıklı nesne
   dedektörü (ultralytics YOLO-World). "Bazı ürünleri okumadı" sorununu asıl
   çözen katman: hem daha iyi bölge önerileri üretir hem de her bölge için
   bir "suggested_food_type" tahmini döner (kullanıcı yine onaylıyor -
   human-in-the-loop korunuyor, sadece daha az soru sormak gerekiyor).

   Bu katman OPSİYONELDİR: `pip install -r requirements-cv.txt` ile kurulmazsa
   ya da model ilk kez internetten inemezse, sistem otomatik olarak
   classical_detect_regions()'a düşer. Hiçbir zaman uygulamayı çökertmez.

Hangi yöntemin kullanıldığı /scan yanıtındaki "detector" alanından görülebilir.
"""
import base64
import importlib.util
import os
import threading
import uuid
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------

MAX_AREA_RATIO = 0.42     # görüntünün bu oranından büyük kutular elenir (= "tüm dolap"/"yarım dolap")
MIN_AREA_RATIO = 0.006    # bundan küçük kutular gürültü sayılır (v5: gevşetildi - küçük ürünler kaçmasın)
MAX_ASPECT_RATIO = 5.0    # en/boy oranı bundan büyükse "raf kenarı/köşe" sayılır (v5: gevşetildi - şişe/kutu gibi uzun ürünler)
MIN_SOLIDITY = 0.55       # gerçek ürünler ~0.98-0.99, köşe/çerçeve artefaktları 0.06-0.62 (test edildi)
EDGE_MARGIN_RATIO = 0.015 # görüntü kenarına bu kadar yakınsa "kenara değiyor" sayılır
CORNER_FILTER_MIN_AREA_RATIO = 0.10  # v5: köşe filtresi SADECE büyük kutularda uygulanır - küçük bir ürün kadraj köşesinde durabilir, bu normaldir
NMS_IOU_THRESHOLD = 0.4


CROP_MAX_SIDE = 320  # arayüz 88px'lik küçük resim gösteriyor; 320px bol yeterli


def _encode_crop_to_base64(crop: np.ndarray) -> str:
    if crop.size == 0:
        return ""
    longest = max(crop.shape[:2])
    if longest > CROP_MAX_SIDE:
        scale = CROP_MAX_SIDE / longest
        crop = cv2.resize(
            crop, (max(1, int(crop.shape[1] * scale)), max(1, int(crop.shape[0] * scale))),
            interpolation=cv2.INTER_AREA,
        )
    success, buffer = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not success:
        return ""
    return base64.b64encode(buffer).decode("utf-8")


DOWNSCALE_TRIGGER_SIDE = 1600  # bundan büyük fotoğraflar küçültülür (telefon fotoğrafları ~4000px)
DETECT_TARGET_SIDE = 1280       # tespit bu boyutta yapılır


def _prepare_image_bytes(image_bytes: bytes) -> bytes:
    """
    Çok büyük (telefon) fotoğraflarını tespitten önce küçültür. Ölçüm (12 MP):
    tespit ~5 sn -> ~0.3 sn, bölge sayıları aynı; filtre/çekirdek boyutları da
    zaten ~1000px'lik görüntülere göre ayarlı. <=1600px görüntülere dokunulmaz
    (davranış birebir aynı kalır).
    """
    arr = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return image_bytes
    h, w = arr.shape[:2]
    if max(h, w) <= DOWNSCALE_TRIGGER_SIDE:
        return image_bytes
    scale = DETECT_TARGET_SIDE / max(h, w)
    small = cv2.resize(arr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return buf.tobytes() if ok else image_bytes


def _iou(a, b) -> float:
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _nms(boxes: List[tuple], scores: List[float]) -> List[int]:
    """Basit greedy NMS. boxes: [(x,y,w,h), ...]. Döner: kalan indexler."""
    order = sorted(range(len(boxes)), key=lambda i: scores[i], reverse=True)
    keep = []
    while order:
        i = order.pop(0)
        keep.append(i)
        order = [j for j in order if _iou(boxes[i], boxes[j]) < NMS_IOU_THRESHOLD]
    return keep


def _touches_two_or_more_edges(x, y, bw, bh, img_w, img_h, area_ratio: float) -> bool:
    """
    Dolap köşesi/raf kenarı tespiti: gerçek bir ürün genelde görüntünün
    yalnızca bir kenarına (ör. alt kenar, kadraj dışına taşan bir kap) yakın
    olur. İki veya daha fazla kenara AYNI ANDA değen BÜYÜK bir kutu (sol+üst
    gibi) çoğunlukla dolabın fiziksel köşesi/çerçevesidir.

    v5 düzeltmesi: bu filtre artık SADECE büyük kutularda uygulanıyor
    (area_ratio > CORNER_FILTER_MIN_AREA_RATIO). Küçük bir ürün kadrajın
    köşesinde durabilir - bu normaldir ve elenmemeli. Eskiden bu filtre her
    boyuttaki kutuya uygulanıp gerçek ürünleri de siliyordu.
    """
    if area_ratio <= CORNER_FILTER_MIN_AREA_RATIO:
        return False
    margin_x = img_w * EDGE_MARGIN_RATIO
    margin_y = img_h * EDGE_MARGIN_RATIO
    touches_left = x <= margin_x
    touches_top = y <= margin_y
    touches_right = (x + bw) >= (img_w - margin_x)
    touches_bottom = (y + bh) >= (img_h - margin_y)
    return sum([touches_left, touches_top, touches_right, touches_bottom]) >= 2


def _valid_box(x, y, bw, bh, img_w, img_h, solidity: Optional[float] = None) -> bool:
    area = bw * bh
    img_area = img_w * img_h
    area_ratio = area / img_area if img_area else 0
    if area_ratio > MAX_AREA_RATIO or area_ratio < MIN_AREA_RATIO:
        return False
    aspect = max(bw / max(bh, 1), bh / max(bw, 1))
    if aspect > MAX_ASPECT_RATIO:
        return False
    if _touches_two_or_more_edges(x, y, bw, bh, img_w, img_h, area_ratio):
        return False
    if solidity is not None and solidity < MIN_SOLIDITY:
        return False
    return True


# ---------------------------------------------------------------------------
# 1) Klasik yöntem (bağımlılıksız, her zaman çalışır) — v2, filtreli
# ---------------------------------------------------------------------------

def _candidates_from_edges(gray: np.ndarray) -> List[tuple]:
    """Döner: [(x, y, w, h, solidity), ...]"""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)
    # RETR_LIST (RETR_EXTERNAL DEĞİL): dolabın dış çerçevesi/raf kenarları
    # kapalı bir döngü oluşturursa, RETR_EXTERNAL yalnızca o dış konturu
    # döner ve İÇİNDEKİ tüm ürünleri (iç içe geçmiş konturları) görmezden
    # gelir - "tüm dolap tek kutu" hatasının asıl nedeni buydu.
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        contour_area = cv2.contourArea(c)
        box_area = max(bw * bh, 1)
        solidity = contour_area / box_area
        out.append((x, y, bw, bh, solidity))
    return out


def _candidates_from_adaptive_threshold(gray: np.ndarray) -> List[tuple]:
    """Canny'nin kaçırdığı yumuşak-kenarlı/soluk nesneleri (meyve, kap vb.)
    yakalamak için ikinci bir aday üretici. Döner: [(x, y, w, h, solidity), ...]"""
    blurred = cv2.medianBlur(gray, 7)
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 25, 5,
    )
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        contour_area = cv2.contourArea(c)
        box_area = max(bw * bh, 1)
        solidity = contour_area / box_area
        out.append((x, y, bw, bh, solidity))
    return out


def _enhance_local_contrast(gray: np.ndarray) -> np.ndarray:
    """CLAHE: yerel kontrastı güçlendirir - opak/düşük kontrastlı saklama kutuları için."""
    clahe = cv2.createCLAHE(clipLimit=4.5, tileGridSize=(6, 6))
    return clahe.apply(gray)


def _candidates_from_watershed(img: np.ndarray) -> List[tuple]:
    """CLAHE + Otsu + mesafe dönüşümlü watershed. Döner: [(x, y, w, h, solidity), ...]"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(_enhance_local_contrast(gray), (7, 7), 0)
    out = []
    for thresh_type in (cv2.THRESH_BINARY, cv2.THRESH_BINARY_INV):
        try:
            _, thresh = cv2.threshold(blurred, 0, 255, thresh_type + cv2.THRESH_OTSU)
        except cv2.error:
            continue
        kernel = np.ones((5, 5), np.uint8)
        opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)
        sure_bg = cv2.dilate(opened, kernel, iterations=3)
        dist = cv2.distanceTransform(opened, cv2.DIST_L2, 5)
        if dist.max() <= 0:
            continue
        _, sure_fg = cv2.threshold(dist, 0.4 * dist.max(), 255, 0)
        sure_fg = np.uint8(sure_fg)
        unknown = cv2.subtract(sure_bg, sure_fg)
        num_labels, markers = cv2.connectedComponents(sure_fg)
        if num_labels <= 1:
            continue
        markers = markers + 1
        markers[unknown == 255] = 0
        markers = cv2.watershed(img, markers)
        for label in np.unique(markers):
            if label <= 1:
                continue
            mask = np.uint8(markers == label) * 255
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                x, y, bw, bh = cv2.boundingRect(c)
                # Watershed, görüntü sınırını "sınır çizgisi" olarak işaretler; bu yüzden
                # kenara yapışan bölgeler çoğunlukla arka plan parçalarıdır (x=1 / y=1 imzası).
                # Kenardaki gerçek ürünler zaten kenar/eşik katmanlarıyla bulunur.
                if x <= 1 or y <= 1 or x + bw >= img.shape[1] - 1 or y + bh >= img.shape[0] - 1:
                    continue
                out.append((x, y, bw, bh, cv2.contourArea(c) / max(bw * bh, 1)))
    return out


COLOR_MIN_SATURATION = 70       # HSV doygunluk eşiği: meyve/sebze/renkli ambalaj "renklidir", buzdolabı içi nötr
COLOR_MIN_VALUE = 50
COLOR_MIN_FILL = 0.20           # kutu içindeki renkli piksel oranı (seyrek/boş kutuları ele)
CONTAIN_THRESHOLD = 0.80        # bir kutunun %80'i başka kutunun içindeyse "içinde" sayılır
CLUSTER_MEMBER_MAX_AREA_FRACTION = 0.25  # küme üyeleri kümenin en fazla %25'i kadar olmalı (yan yana duran büyük ürünleri birleştirme)


def _containment(inner: tuple, outer: tuple) -> float:
    """inner kutusunun alanının ne kadarı outer içinde (0..1). Kutular (x, y, w, h)."""
    ix1, iy1 = max(inner[0], outer[0]), max(inner[1], outer[1])
    ix2 = min(inner[0] + inner[2], outer[0] + outer[2])
    iy2 = min(inner[1] + inner[3], outer[1] + outer[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    return inter / max(inner[2] * inner[3], 1)


def _color_cluster_boxes(img: np.ndarray) -> List[tuple]:
    """
    v8 - MEYVE POŞETİ katmanı: kenar/kontrast yerine RENGE bakar.

    Neden: plastik poşetler yarı saydam, buruşuk ve yansımalıdır; kenarları
    kopuk/silik olduğu için Canny/eşikleme/watershed poşeti bulamaz. Ama
    içindeki meyve (portakal, elma, limon, muz...) buzdolabının nötr gri/beyaz
    iç yüzeyine göre belirgin şekilde DOYGUN renklidir. Doygun pikselleri
    bulup, birbirine yakın olanları morfolojik kapamayla tek kümeye
    birleştiriyoruz - poşetin içindeki meyveler tek kutu olur.

    Döner: [(x, y, w, h), ...] (geçerli kutular)
    """
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat, val = hsv[..., 1], hsv[..., 2]
    raw = ((sat >= COLOR_MIN_SATURATION) & (val >= COLOR_MIN_VALUE)).astype(np.uint8) * 255
    if raw.mean() / 255.0 > 0.45:
        # Renkli aydınlatma / çok renkli sahne: eşiği görüntüye göre yükselt
        thr = max(COLOR_MIN_SATURATION, int(np.percentile(sat, 80)))
        raw = ((sat >= thr) & (val >= COLOR_MIN_VALUE)).astype(np.uint8) * 255
    raw = cv2.morphologyEx(raw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    k = max(7, int(min(h, w) * 0.02)) | 1
    closed = cv2.morphologyEx(
        raw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)), iterations=2
    )
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if not _valid_box(x, y, bw, bh, w, h, None):
            continue
        fill = float((raw[y:y + bh, x:x + bw] > 0).mean())
        if fill < COLOR_MIN_FILL:
            continue
        boxes.append((x, y, bw, bh))
    return boxes


def _merge_color_clusters(base_boxes: List[tuple], color_boxes: List[tuple]) -> List[tuple]:
    """
    Mevcut (kenar/eşik/watershed) kutularını bozmadan renk kümelerini ekler:
    - Küme, zaten bulunmuş bir kutuyla büyük ölçüde çakışıyorsa -> atla (kopya olmasın)
    - Kümenin içinde 2+ KÜÇÜK kutu varsa (poşetteki tek tek meyveler) -> hepsi
      tek "poşet" kutusuyla değiştirilir
    - Hiçbir şeyle çakışmıyorsa (kaçırılmış bir poşet/ürün) -> eklenir
    Yan yana duran büyük ürünler (üyeler kümenin %25'inden büyük) birleştirilmez.
    """
    result = list(base_boxes)
    for c in color_boxes:
        c_area = c[2] * c[3]
        dup = [b for b in result if _iou(b, c) > 0.5]
        if dup:
            # Poşet/küme zaten tek kutu olarak bulunmuş: içindeki tek tek meyve kutularını sil
            result = [
                b for b in result
                if b in dup or not (
                    _containment(b, c) >= CONTAIN_THRESHOLD
                    and b[2] * b[3] <= CLUSTER_MEMBER_MAX_AREA_FRACTION * c_area
                )
            ]
            continue
        contained = [b for b in result if _containment(b, c) >= CONTAIN_THRESHOLD]
        if len(contained) >= 2:
            if all(b[2] * b[3] <= CLUSTER_MEMBER_MAX_AREA_FRACTION * c_area for b in contained):
                result = [b for b in result if b not in contained]
                result.append(c)
            continue
        if len(contained) == 1:
            continue  # zaten tespit edilmiş tek bir ürün - kopya ekleme
        if any(_iou(b, c) > 0.4 for b in result):
            continue
        result.append(c)
    return result


def classical_detect_regions(image_bytes: bytes, max_regions: int = 10, use_color: bool = True) -> List[dict]:
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    enhanced_gray = _enhance_local_contrast(gray)
    raw_candidates = (
        _candidates_from_edges(gray)
        + _candidates_from_edges(enhanced_gray)
        + _candidates_from_adaptive_threshold(gray)
        + _candidates_from_adaptive_threshold(enhanced_gray)
        + _candidates_from_watershed(img)
    )

    valid = [
        (x, y, bw, bh) for (x, y, bw, bh, solidity) in raw_candidates
        if _valid_box(x, y, bw, bh, w, h, solidity)
    ]

    base_boxes: List[tuple] = []
    if valid:
        # Skor: alan büyüklüğü (basit bir "belirginlik" ölçüsü olarak kullanılıyor)
        scores = [bw * bh for (_, _, bw, bh) in valid]
        base_boxes = [valid[i] for i in _nms(valid, scores)]

    if use_color:
        base_boxes = _merge_color_clusters(base_boxes, _color_cluster_boxes(img))

    base_boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
    boxes_final = base_boxes[:max_regions]
    keep_idx = list(range(len(boxes_final)))
    valid = boxes_final

    regions = []
    for i in keep_idx:
        x, y, bw, bh = valid[i]
        crop = img[y:y + bh, x:x + bw]
        regions.append({
            "region_id": str(uuid.uuid4())[:8],
            "bbox": [int(x), int(y), int(bw), int(bh)],
            "crop_base64": _encode_crop_to_base64(crop),
            "suggested_food_type": None,
            "suggested_confidence": None,
        })
    return regions


# ---------------------------------------------------------------------------
# 2) YOLO-World (opsiyonel, gerçek açık-kelime nesne tespiti + sınıf tahmini)
# ---------------------------------------------------------------------------

# Aday sınıflar: hem kap/paket türleri hem de sık görülen buzdolabı ürünleri.
# Açık kelime dağarcığı sayesinde model bunlara benzeyen HERHANGİ bir nesneyi
# tespit etmeye çalışır (COCO'nun sabit 80 sınıfıyla sınırlı değiliz).
YOLO_WORLD_CLASSES = [
    # --- kap / paket / hazır ürünler ---
    "yogurt container", "milk carton", "cheese", "leftover food in a container",
    "raw chicken", "plastic bottle", "glass jar", "plastic food container",
    "bowl with food", "soda can", "egg carton", "butter", "jam jar", "sauce bottle",
    # --- meyve / sebze (tek tek) ---
    "tomato", "lemon", "banana", "apricot", "bell pepper", "spinach",
    "apple", "orange", "pear", "peach", "grapes", "strawberries",
    "cucumber", "carrot", "potato", "onion", "fruit", "vegetable",
    # --- v8: POŞET/FİLE İÇİNDEKİ MEYVE-SEBZE (kullanıcının kaçırılan ürünleri) ---
    "plastic bag with fruit", "bag of fruit", "produce bag", "mesh bag of vegetables",
    "bag of apples", "bag of oranges", "bag of lemons", "bag of grapes",
    "bunch of bananas",
]

# Model çıktısı İngilizce -> arayüzde önerilecek Türkçe tahmin
_CLASS_TO_TR = {
    "yogurt container": "yoğurt", "milk carton": "süt", "cheese": "peynir",
    "leftover food in a container": "kalan yemek", "raw chicken": "tavuk",
    "plastic bottle": "şişe", "glass jar": "kavanoz", "plastic food container": "saklama kabı",
    "bowl with food": "yemek kabı", "soda can": "soda", "egg carton": "yumurta",
    "butter": "tereyağı", "jam jar": "reçel", "sauce bottle": "sos",
    "tomato": "domates", "lemon": "limon", "banana": "muz", "apricot": "kayısı",
    "bell pepper": "dolmalık biber", "spinach": "ıspanak", "apple": "elma",
    "orange": "portakal", "pear": "armut", "peach": "şeftali", "grapes": "üzüm",
    "strawberries": "çilek", "cucumber": "salatalık", "carrot": "havuç",
    "potato": "patates", "onion": "soğan", "fruit": "meyve", "vegetable": "sebze",
    "plastic bag with fruit": "meyve", "bag of fruit": "meyve", "produce bag": "meyve",
    "mesh bag of vegetables": "sebze", "bag of apples": "elma", "bag of oranges": "portakal",
    "bag of lemons": "limon", "bag of grapes": "üzüm", "bunch of bananas": "muz",
}

# --- v11: GENEL (jenerik) sınıflar ---------------------------------------------------------
# Kapalı bir şişenin/saklama kabının İÇİNDE ne olduğunu görüntüden bilmek mümkün değil.
# Bu yüzden bu sınıflar yemek adı olarak otomatik DOLDURULMAZ; yalnızca ipucu (etiket + kategori)
# olarak gösterilir ve kullanıcı seçer. Spesifik sınıflar (domates, süt...) yeterince eminse doldurulur.
GENERIC_CLASSES = {
    "plastic bottle": ("şişe", "İçecek / sos"),
    "glass jar": ("kavanoz", "Konserve / reçel / turşu"),
    "plastic food container": ("saklama kabı", "Hazır yemek / kalan yemek"),
    "bowl with food": ("yemek kabı", "Hazır yemek / kalan yemek"),
    "sauce bottle": ("sos şişesi", "İçecek / sos"),
    "soda can": ("kutu içecek", "İçecek / sos"),
    "fruit": ("meyve", "Meyve"),
    "vegetable": ("sebze", "Sebze"),
    "plastic bag with fruit": ("meyve poşeti", "Meyve"),
    "bag of fruit": ("meyve poşeti", "Meyve"),
    "produce bag": ("sebze-meyve poşeti", "Meyve / sebze"),
    "mesh bag of vegetables": ("sebze filesi", "Sebze"),
}
YOLO_PREFILL_MIN_CONF = float(os.environ.get("SMART_PANTRY_PREFILL_CONF", "0.35"))


def _interpret_class(class_name, conf):
    """-> (suggested_food_type, label, category, kind). kind: specific | maybe | generic"""
    if not class_name:
        return None, None, None, None
    if class_name in GENERIC_CLASSES:
        label, cat = GENERIC_CLASSES[class_name]
        return None, label, cat, "generic"
    tr = _CLASS_TO_TR.get(class_name)
    if not tr:
        return None, None, None, None
    if conf >= YOLO_PREFILL_MIN_CONF:
        return tr, tr, None, "specific"
    return None, tr, None, "maybe"


_yolo_model = None
_yolo_load_attempted = False
YOLO_CONFIDENCE_THRESHOLD = 0.08   # v8: düşürüldü - poşetli/yarı saydam ürünlerde güven skoru düşük çıkar
YOLO_MAX_AREA_RATIO = 0.60         # v8: öğrenilmiş modelin kutuları için klasik filtrelerden daha cömert
YOLO_MAX_ASPECT_RATIO = 8.0


def _yolo_model_candidates() -> List[str]:
    """Önce (varsa) SMART_PANTRY_YOLO_MODEL, sonra daha doğru olan m-worldv2, olmazsa s-world."""
    names = []
    custom = os.environ.get("SMART_PANTRY_YOLO_MODEL")
    if custom:
        names.append(custom)
    names += ["yolov8m-worldv2.pt", "yolov8s-world.pt"]
    return names


_yolo_lock = threading.Lock()
_yolo_reason = "not_started"  # not_started | ready | ultralytics_missing | clip_missing | load_failed
_yolo_error = ""
_yolo_model_name: Optional[str] = None
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"  # backend/models (pakete dahil model dosyaları)

CLIP_INSTALL_HELP = (
    "[cv/detector] YOLO-World için 'clip' paketi eksik (git GEREKMEZ). Çözüm:\n"
    "    pip install -r requirements-cv.txt   (backend klasöründe, venv aktifken)\n"
    "  Kurduktan sonra backend'i yeniden başlat. Şimdilik klasik yöntem kullanılıyor."
)


def _resolve_model_path(name: str) -> str:
    """backend/models içinde varsa yerel dosyayı kullan (internetten indirme gerekmez)."""
    local = MODELS_DIR / name
    return str(local) if local.exists() else name


def _try_load_yolo_world():
    """Modeli (gerekirse) yükler. Yalnızca açılış ısınması çağırır; tarama istekleri BEKLEMEZ."""
    with _yolo_lock:
        return _load_yolo_locked()


def get_yolo_status() -> str:
    """'ready' (model hazır) | 'loading' (arka planda yükleniyor) | 'unavailable'."""
    if _yolo_model is not None:
        return "ready"
    if _yolo_lock.locked():
        return "loading"
    return "unavailable"


def get_cv_status() -> dict:
    """Kullanıcıya gösterilecek dedektör durumu ve (varsa) çözüm önerisi."""
    if os.environ.get("SMART_PANTRY_USE_YOLO", "1") == "0":
        return {"status": "disabled", "reason": "disabled", "model": None,
                "message": "YOLO kapalı (SMART_PANTRY_USE_YOLO=0), klasik yöntem kullanılıyor."}
    if _yolo_model is not None:
        return {"status": "ready", "reason": "ready", "model": _yolo_model_name,
                "message": f"YOLO-World hazır (model: {_yolo_model_name})."}
    if _yolo_lock.locked() or not _yolo_load_attempted:
        return {"status": "loading", "reason": "loading", "model": None,
                "message": "YOLO modeli arka planda yükleniyor. İlk seferde CLIP dosyası (~340 MB) "
                           "iner, birkaç dakika sürebilir; hazır olunca otomatik devreye girer."}
    messages = {
        "ultralytics_missing": "ultralytics kurulu değil. Çözüm: backend klasöründe (venv aktifken) "
                               "`pip install -r requirements-cv.txt`, sonra backend'i yeniden başlat.",
        "clip_missing": "clip paketi eksik. Çözüm: backend klasöründe (venv aktifken) "
                        "`pip install -r requirements-cv.txt`, sonra backend'i yeniden başlat.",
        "load_failed": f"Model yüklenemedi: {_yolo_error[:180]}. Ayrıntı için backend penceresindeki "
                       "[cv/detector] satırlarına bak.",
    }
    return {"status": "unavailable", "reason": _yolo_reason, "model": None,
            "message": messages.get(_yolo_reason, "YOLO kullanılamıyor.")}


def _get_model_for_scan():
    """
    Tarama isteği için hazır modeli döner; hazır değilse BEKLEMEZ (None döner ->
    o tarama klasik yöntemle anında çalışır). İlk yükleme CLIP ağırlıklarını da
    indirir (birkaç yüz MB, birkaç dakika) - taramanın o süre takılı kalmaması için.
    Henüz hiç yükleme denenmediyse arka planda başlatır.
    """
    if _yolo_model is not None:
        return _yolo_model
    if not _yolo_load_attempted and not _yolo_lock.locked():
        threading.Thread(target=warm_up_yolo, daemon=True).start()
    return None


def warm_up_yolo() -> None:
    """Açılışta arka planda çağrılır: modeli yükler ve ilk çıkarımı ısıtır."""
    model = _try_load_yolo_world()
    if model is None:
        return
    try:
        model.predict(np.zeros((640, 640, 3), np.uint8), conf=0.5, verbose=False)  # ilk çıkarım ısınması
    except Exception as e:
        print(f"[cv/detector] ısınma çıkarımı atlandı: {e}")


def _load_yolo_locked():
    global _yolo_model, _yolo_load_attempted, _yolo_reason, _yolo_error, _yolo_model_name
    if _yolo_load_attempted:
        return _yolo_model
    _yolo_load_attempted = True
    # ultralytics eksik paketleri sessizce pip ile kurmaya çalışır (CLIP için `git` ister).
    # Git yoksa hem yavaş hem hatalı; kapatıp eksikse net bir mesaj verip klasiğe düşüyoruz.
    os.environ.setdefault("YOLO_AUTOINSTALL", "false")
    try:
        from ultralytics import YOLO  # noqa: opsiyonel bağımlılık
    except Exception as e:
        _yolo_reason, _yolo_error = "ultralytics_missing", str(e)
        print(f"[cv/detector] ultralytics kurulu değil, klasik yönteme düşülüyor: {e}")
        return None
    if importlib.util.find_spec("clip") is None:
        _yolo_reason = "clip_missing"
        print(CLIP_INSTALL_HELP)  # ağırlıkları indirip sonra patlamak yerine baştan dur
        return None
    for name in _yolo_model_candidates():
        try:
            model = YOLO(_resolve_model_path(name))  # yerel dosya varsa indirme yok
            model.set_classes(YOLO_WORLD_CLASSES)
            _yolo_model, _yolo_model_name, _yolo_reason = model, name, "ready"
            print(f"[cv/detector] YOLO-World yüklendi: {name}")
            break
        except Exception as e:
            _yolo_reason, _yolo_error = "load_failed", f"{name}: {e}"
            print(f"[cv/detector] {name} yüklenemedi: {e}")
            if isinstance(e, ModuleNotFoundError) and getattr(e, "name", "") == "clip":
                _yolo_reason = "clip_missing"
                print(CLIP_INSTALL_HELP)
                break  # sorun model değil, paket - diğer modeli denemenin anlamı yok
            print("[cv/detector] sıradaki model deneniyor...")
    return _yolo_model


def _valid_yolo_box(x, y, bw, bh, img_w, img_h) -> bool:
    """YOLO kutuları için gevşek doğrulama: köşe/solidity gibi KLASİK-kontur filtreleri uygulanmaz."""
    img_area = img_w * img_h
    area_ratio = (bw * bh) / img_area if img_area else 0
    if area_ratio > YOLO_MAX_AREA_RATIO or area_ratio < MIN_AREA_RATIO * 0.5:
        return False
    return max(bw / max(bh, 1), bh / max(bw, 1)) <= YOLO_MAX_ASPECT_RATIO


def yolo_world_detect_regions(image_bytes: bytes, max_regions: int = 12) -> Optional[List[dict]]:
    model = _get_model_for_scan()
    if model is None:
        return None

    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    h, w = img.shape[:2]

    try:
        results = model.predict(
            img, conf=YOLO_CONFIDENCE_THRESHOLD, iou=0.5, agnostic_nms=True,
            imgsz=800, verbose=False,
        )
    except Exception as e:
        print(f"[cv/detector] YOLO-World inference hatası, klasik yönteme düşülüyor: {e}")
        return None

    regions = []
    if results:
        for box in results[0].boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            bw, bh = x2 - x1, y2 - y1
            if not _valid_yolo_box(x1, y1, bw, bh, w, h):
                continue
            cls_idx = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            class_name = YOLO_WORLD_CLASSES[cls_idx] if cls_idx < len(YOLO_WORLD_CLASSES) else None
            suggested, s_label, s_cat, s_kind = _interpret_class(class_name, conf)

            crop = img[int(y1):int(y2), int(x1):int(x2)]
            regions.append({
                "region_id": str(uuid.uuid4())[:8],
                "bbox": [int(x1), int(y1), int(bw), int(bh)],
                "crop_base64": _encode_crop_to_base64(crop),
                "suggested_food_type": suggested,
                "suggested_confidence": round(conf, 2),
                "suggested_label": s_label,
                "suggested_category": s_cat,
                "suggestion_kind": s_kind,
            })

    regions.sort(key=lambda r: r["suggested_confidence"] or 0, reverse=True)

    if not regions:
        # YOLO hiçbir ürün bulamadıysa renk kutularıyla yetinme (beyaz/renksiz ürünler kaybolur);
        # boş dön -> detect_regions klasik (renk dahil) yönteme düşer.
        return []

    # HİBRİT: YOLO'nun hiç kutu koymadığı yerlerdeki renkli kümeleri (ör. YOLO'nun
    # kaçırdığı meyve poşetleri) ekle. Yalnızca mevcut kutularla çakışmayanlar eklenir.
    try:
        for (cx, cy, cw, ch) in _color_cluster_boxes(img):
            c = (cx, cy, cw, ch)
            clash = any(
                _iou(c, tuple(r["bbox"])) > 0.2
                or _containment(c, tuple(r["bbox"])) > 0.5
                or _containment(tuple(r["bbox"]), c) > 0.5
                for r in regions
            )
            if clash:
                continue
            regions.append({
                "region_id": str(uuid.uuid4())[:8],
                "bbox": [int(cx), int(cy), int(cw), int(ch)],
                "crop_base64": _encode_crop_to_base64(img[cy:cy + ch, cx:cx + cw]),
                "suggested_food_type": None,
                "suggested_confidence": None,
            })
    except Exception as e:
        print(f"[cv/detector] renk kümesi eklenemedi (YOLO sonuçları korunuyor): {e}")

    return regions[:max_regions]


# ---------------------------------------------------------------------------
# Dışa açılan tek fonksiyon
# ---------------------------------------------------------------------------

def detect_regions(image_bytes: bytes, max_regions: int = 14) -> dict:
    """
    Önce YOLO-World'ü dener (kuruluysa). Başarısız olursa/kurulu değilse
    klasik filtreli yönteme düşer. İkisi de her zaman çalışacak şekilde
    tasarlandı - biri patlarsa uygulama çökmez.

    Dönüş: {"regions": [...], "detector": "yolo_world" | "classical"}
    """
    image_bytes = _prepare_image_bytes(image_bytes)
    use_yolo = os.environ.get("SMART_PANTRY_USE_YOLO", "1") != "0"

    if use_yolo:
        yolo_regions = yolo_world_detect_regions(image_bytes, max_regions)
        if yolo_regions:  # None (hazır değil/kurulu değil/hata) ya da boş liste -> klasik yönteme düş
            return {"regions": yolo_regions, "detector": "yolo_world", "yolo_status": "ready",
                    "yolo_message": get_cv_status()["message"]}

    cv = get_cv_status()
    return {
        "regions": classical_detect_regions(image_bytes, max_regions),
        "detector": "classical",
        "yolo_status": cv["status"],
        "yolo_message": cv["message"],
    }
