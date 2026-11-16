# Değişiklik Günlüğü (Changelog)

Sürüm notları, en yeniden eskiye. (v11 en üstte.)

## v11
- **Geçmiş tablosunda "Tüketim hızı" sütunu**: her satırda önceki kayda göre porsiyon/gün. Hız hesaplanamıyorsa nedeni yanında yazar
  (ilk tarama / iki kayıt arası 12 saatten kısa / miktar azalmamış).
- **YOLO genel isimleri**: "şişe, kavanoz, saklama kabı, meyve, sebze, sos" gibi genel sınıflar artık yemek adı olarak otomatik
  doldurulmaz; ipucu olarak gösterilir ve kategoriye uygun hızlı seçim butonları öne çıkar. Spesifik sınıflar (domates, süt...)
  yalnızca güven >= 0.35 ise doldurulur (`SMART_PANTRY_PREFILL_CONF` ile değişir).
- **Tarifi tamamlayan malzemeler**: börek -> yufka, çoban salatası -> salatalık/biber/maydanoz vb. alışveriş listesine eklenir.

## v10'da ne değişti

- **Envanterden çıkarma:** envanterdeki her satırda "Çıkar" butonu. Üç seçenek: **✓ Tükettim** (0 porsiyon kaydı eklenir, ürün kapanır, israf sayılmaz) · **🗑 Attım / bozuldu** (ürün kapanır, aynı ürün için sonraki risk uyarısı yükselir) · **✕ Yanlış kayıt (sil)** (ürün ve geçmişi tamamen silinir).
- **"Bu taramada görünmeyen ürünler":** önceki taramada olan ama bu taramada onaylamadığın ürünler (ve elle eklenmemişse) için taramadan sonra bir kart açılır: *Tükettim / Attım / Hâlâ var*. Kamera ürün kaçırabildiği için **hiçbir şey otomatik silinmez**; sen karar verirsin. "Hâlâ var" envanteri değiştirmez, o oturumda tekrar sormaz. "➕ Elle ekle" ile eklenen ürünler asla sorulmaz. Fotoğrafta hiç bölge bulunmadıysa kart açılmaz.
- **Dedektör durumu:** kartta "🎯/🔧 Dedektör: ..." satırı artık nedenini ve çözümünü yazar (ultralytics eksik / clip eksik / model yüklenemedi / yükleniyor). Model yüklenirken satır kendiliğinden güncellenir.
- **İndirmeler pakette:** `backend/models/` içinde YOLO-World ağırlıkları (`yolov8m-worldv2.pt`, `yolov8s-world.pt`) ve `backend/wheels/` içinde `clip` paketi hazır; `pip install -r requirements-cv.txt` internetten ayrıca GitHub/model indirmez (PyTorch gibi normal pip paketleri hâlâ PyPI'den iner). Sadece CLIP'in kendi ağırlık dosyası (~340 MB) bu pakete konamadı; ilk YOLO yüklemesinde bir kez otomatik iner.
- **Veritabanı otomatik göç:** eski `smart_pantry.db` dosyana yeni sütunlar kendiliğinden eklenir, silmen gerekmez.

## v9.1 — YOLO-World kurulumu (git GEREKMEZ)

YOLO-World metin kodlayıcı olarak `clip` paketini ister; ultralytics bunu `git` ile kurmaya çalışır ve Windows'ta git yoksa şu hatayı verir: `Cannot find command 'git'` / `No module named 'clip'`. Bu sürümde `requirements-cv.txt` aynı paketi GitHub'ın zip arşivinden, git olmadan kurar:

```powershell
pip install -r requirements-cv.txt
```
(ya da tek başına: `pip install ftfy regex tqdm https://github.com/ultralytics/CLIP/archive/refs/heads/main.zip`)

Kurduktan sonra backend'i yeniden başlat. İlk açılışta CLIP metin kodlayıcısı (~340 MB) internetten iner; backend penceresinde `[cv/detector] YOLO-World yüklendi: ...` yazısını gör. Bu sırada taramalar **beklemez**: model hazır olana kadar klasik yöntemle anında çalışır (kart üstünde "YOLO modeli arka planda yükleniyor" yazar), hazır olunca otomatik YOLO'ya geçer.

Ayrıca: `clip` eksikse artık gereksiz model indirmesi yapılmaz ve backend penceresinde çözüm komutu net yazılır; ultralytics'in sessiz otomatik pip kurulum denemeleri (yavaş, git hatası veren) kapatıldı.

İndirilen model dosyaları (`yolov8m-worldv2.pt`, `yolov8s-world.pt`) `backend` klasörüne kaydedilir; eski klasörden yenisine kopyalarsan yeniden indirilmez.

## v9'da ne değişti

- **Bozulma tahmini artık gerçekçi:** yedek raf ömrü tablosu ~20 üründen ~100 ürüne çıkarıldı (biber 12 gün, domates 10, kavun 10, ayran 10, elma 28, limon 21, havuç 21...). Tabloda olmayan ürünler eskiden düz 5 gün alıyordu (taze ürünler için çok kısa); artık 7 gün ve ürün adı akıllı eşleşiyor ("kırmızı biber" → biber, "domatesler" → domates). Çiğ tavuk/et/balık gıda güvenliği için bilerek kısa kaldı (2-3 gün); pişmiş tavuk için `pişmiş tavuk` (4 gün) yaz.
- **Şeffaflık:** her ürünün açıklamasında artık "Bu ürün X gün önce ilk kez taranmış / satın alınmış" yazar. Süre bu tarihten sayılır; ürünü tükettiysen ve yeniden taramadıysan sistem hâlâ envanterde sayar. Bu durumda tarihi buradan kontrol edebilirsin.
- **Tarama hızı:** telefon fotoğrafı (~12 MP) tespitte ~5 sn sürüyordu; 1600 pikselden büyük fotoğraflar tespitten önce 1280 piksele küçültülür (ölçüm: ~0.4 sn, bölge sayıları aynı, yanıt 8 kat küçük). 1600 piksel ve altı görüntülere dokunulmaz. Kırpma görselleri 320 piksele indirildi. Tespit ayrı iş parçacığında çalışır (tarama sürerken sunucu kilitlenmez). YOLO-World modeli sunucu açılışında arka planda önceden yüklenir (ilk tarama modeli beklemez). Arama listeleri taramayla paralel yüklenir. Tarama süresi ekranda `(X sn)` olarak görünür.

## v8'de ne değişti

- **Meyve poşetleri (öncelik):**
  - *Renk katmanı:* poşetin kenarı yarı saydam/buruşuk olduğu için kenar tabanlı yöntemler kaçırabiliyor; ama içindeki meyve nötr buzdolabına göre doygun renklidir. Yeni katman doygun renkli bölgeleri bulup yakın olanları tek "poşet" kutusunda birleştirir. Poşetin içindeki tek tek meyve kutuları ise poşet kutusuna katılır (aynı poşet 6 ayrı kart olarak çıkmaz).
  - *YOLO-World:* sınıf listesine "plastic bag with fruit", "bag of oranges/apples/lemons/grapes", "produce bag", "mesh bag of vegetables" gibi poşet/file sınıfları ve tek tek meyve-sebzeler eklendi; güven eşiği düşürüldü (poşetli ürünlerde skor düşük çıkar), daha doğru model (`yolov8m-worldv2`, inmezse `yolov8s-world`) denenir. YOLO'nun kutuları için köşe/doluluk gibi klasik filtreler artık uygulanmaz.
  - *Hibrit:* YOLO'nun hiç kutu koymadığı yerdeki renkli kümeler de listeye eklenir. YOLO hiçbir şey bulamazsa klasik yönteme düşülür.
  - *Elle ekleme:* "➕ Kaçırılan ürünü elle ekle" butonu ile fotoğrafsız kayıt yapılabilir; hangi dedektör olursa olsun hiçbir ürün kaybolmaz.
- **Watershed düzeltmesi:** görüntü kenarına yapışan watershed bölgeleri arka plan parçası olduğu için elenir (sahte kutu üretiyordu).
- **Alışveriş ↔ tarif döngüsü her üründe:** ürün onaylandığında, listeye eklendiğinde/silindiğinde tüm zincir (envanter → tarifler → alışveriş → geçmiş) yeniden hesaplanır. Peş peşe işlemler tek yenilemede birleşir; geç gelen eski yanıt yenisinin üzerine yazmaz. Sunucu tarafında aynı girdi için sonuç 2 dakika önbelleğe alınır (LLM iki kez çağrılmaz); envanter veya liste değişince önbellek geçersiz olur.
- **Meyve tarifleri:** elma, portakal, çilek, üzüm, şeftali, armut, kayısı, limon için tarifler eklendi (eskiden meyve tespit edilse bile tarif çıkmıyordu).

#### Dedektörün hangisi çalıştığını nasıl anlarsın
Tarama sonrası kartın üstündeki satır: `🎯 YOLO-World` ise gerçek model devrede, `🔧 Klasik yöntem` ise YOLO kurulu değil/inmemiş demektir. Poşetli meyve için en iyi sonuç YOLO-World ile alınır: `pip install -r requirements-cv.txt` (backend klasöründe, venv aktifken). İlk taramada model dosyaları internetten iner, ilk açılış birkaç dakika sürebilir. Farklı bir model denemek için: `$env:SMART_PANTRY_YOLO_MODEL="yolov8l-worldv2.pt"`.

## v7'de ne değişti

- **Tarifler artık evdeki ürünler + market listesini birlikte değerlendiriyor.** Alışveriş listesine elle eklediğin her ürün (örn. tavuk) "alınacak" kabul edilip evdekilerle (örn. ıspanak, domates) kombine edilir. Böyle tarifler 🛒 etiketiyle ("tavuk (listede)") gösterilir ve hem listedeki hem evdeki malzemeyi kullandığı için daha yüksek puan alır.
- Listeye bir şey ekleyince/silince tarifler otomatik yenilenir. Listedeki ürün tarifte "eksik" sayılmaz; listeden silersen tarif eski haline döner.
- Ollama kuruluysa LLM de aynı birleşik malzeme listesiyle tarif üretir; kuru liste (rule-based) sadece sınırlı sayıda tarif içerdiği için çeşitlilik için Ollama önerilir.
- Veritabanı şeması v6 ile aynı, `smart_pantry.db` silmen gerekmez.

## v6'da ne değişti

- **Risk etiketleri (yeni eşikler):** 0 günden az kalmış → **🚫 TÜKETME (muhtemelen bozulmuş)**; 0–3 gün → **⚠️ ACİL TÜKET**; 3–5 gün → **Orta risk**; 5 günden fazla → **Düşük risk**. (`forecasting.py`)
- **Satın alma tarihi:** her ürün kartında opsiyonel "Satın alma tarihi" alanı var. Girilirse bozulma süresi ilk tarama tarihinden değil, bu tarihten sayılır.
- **Geçmiş tablosu:** artık "Önceki miktar" ve "Miktar" yan yana, kıyaslayabilirsin.
- **Alışveriş listesi ekle/çıkar:** tarif kartlarında her eksik malzemenin yanında "+ listeye" butonu ve "Tüm eksikleri listeye ekle" butonu var. Listedeki HER öğenin yanında ✕ var (otomatik öğeler gizlenir, "Gizlediklerimi geri getir" ile geri gelir).
- **Kamera:** üç yeni katman — CLAHE (yerel kontrast güçlendirme), watershed segmentasyonu ve daha sıkı "doluluk" (solidity) filtresi. Opak/düşük kontrastlı saklama kutularını yakalamak için eklendi. Test görüntülerinde: köşe testi 3/3, basit görsel 4/4, düşük kontrastlı opak kutu testinde 3 kutudan 2'si (üçüncüsü arka planla neredeyse aynı renkteydi). Gerçek fotoğraflarda sonuç ışığa göre değişir; en iyi sonuç için `requirements-cv.txt` ile YOLO-World'ü kur.

## Kurulum (adım adım)

1. Zip'i çıkar (sağ tık → Tümünü Ayıkla).
2. PowerShell aç: `cd "C:\Users\Aleyna\Downloads\smart-pantry-ai-v6\smart-pantry-ai\backend"`
3. `python -m venv venv`
4. `venv\Scripts\activate`
5. `pip install -r requirements.txt`
6. `uvicorn app.main:app --reload --port 8000` (pencereyi açık bırak)
7. YENİ bir PowerShell penceresi aç, iki komutu AYRI satırlarda yaz:
   - `cd "C:\Users\Aleyna\Downloads\smart-pantry-ai-v6\smart-pantry-ai\frontend"`
   - `python -m http.server 8080`
8. Tarayıcıda `http://localhost:8080` aç.

NOT: veritabanı şeması değişti (yeni sütun/tablo). Eski sürümden `smart_pantry.db` dosyası kaldıysa, `backend` klasöründen silip backend'i yeniden başlat; yoksa "no such column purchased_at" hatası alırsın.

## v5'te ne değişti

- **Tüketim hızı artık akıllı:** eskiden sadece ilk/son gözleme bakıyordu.
  Artık TÜM ardışık gözlem çiftlerini kullanıp zaman-ağırlıklı ortalama
  alıyor (uzun aralıklar kısa olanlardan daha güvenilir sayılıyor), aynı gün
  içindeki tekrar taramaları otomatik atlıyor. Test edildi: 4 gözlemli bir
  senaryoda (biri aynı gün tekrarı) doğru sonucu (0.5 porsiyon/gün) verdi.
- **Manuel tarih girişi:** her bölge kartında artık bir "Tarama tarihi/saati"
  alanı var (varsayılan: şu an), istersen geçmişe dönük bir tarih girebilirsin.
- **CV filtreleri gevşetildi:** önceki sürümde eklenen köşe/kenar
  filtreleri gerçek fotoğraflarda çok agresif kalıp ürün kaçırıyordu. Şimdi:
  köşe filtresi sadece BÜYÜK kutularda uygulanıyor (küçük bir ürün kadrajın
  köşesinde durabilir, bu normal), minimum alan/doluluk eşikleri düşürüldü,
  en-boy oranı sınırı gevşetildi (şişe/kutu gibi uzun ürünler için). Test
  görüntülerinde köşe artefaktları hâlâ elenirken gerçek ürün sayısı
  değişmedi (3/3, 6/6, 4/4) — gerçek fotoğraflarında artık daha fazla ürün
  yakalaman gerekir.

---

## 🚀 Çalıştırma — hiçbir şey değişmedi, aynı adımlar

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Yeni bir terminalde:

```bash
cd frontend
python -m http.server 8080
```

Tarayıcıda `http://localhost:8080` aç. Zip'i her yeni sürümde olduğu gibi
aç, `backend`/`frontend` klasörlerinin olduğu dizine gir, yukarıdaki adımları
izle. Daha önce kurulum yaptıysan (`venv` klasörün zaten varsa) sadece
`pip install -r requirements.txt` komutunu tekrar çalıştırman yeterli - yeni
bir bağımlılık (`requests`, zaten kuruluydu) dışında değişiklik yok.

Opsiyonel kurulumlar (YOLO-World, Ollama) önceki sürümdeki gibi aynı şekilde
çalışıyor, aşağıda tekrar özetlendi.

---

## v4'te ne değişti (senin 7 maddelik geri bildiriminin üzerine)

#### 1) "Bu ne?" cevapların artık hatırlanıyor
Girdiğin her yiyecek ismi (`elma`, `kayısı`, ne yazarsan) veritabanına
kaydediliyor. Yeni bir tarama yaptığında `GET /food-types` çağrılıyor ve daha
önce yazdığın isimler, sabit örnek listenin (yoğurt, tavuk...) ÖNÜNE eklenip
hızlı seçim butonlarında (chip) gösteriliyor. Bir kere "elma" yazdıysan bir
daha yazmana gerek yok. (`main.py: GET /food-types`)

#### 2) CV — köşe/kenar artefaktları için ek filtreler
Önceki sürümde "tüm dolap" hatası (RETR_EXTERNAL → RETR_LIST) düzeltilmişti
ama bazı köşeler hâlâ kutu olarak algılanıyordu. İki yeni filtre eklendi:
- **Kenara değme filtresi:** bir kutu görüntünün 2 veya daha fazla kenarına
  AYNI ANDA değiyorsa (örn. sol+üst köşe) elenir - gerçek bir ürün genelde
  yalnızca 1 kenara yakın olur, dolap köşeleri/çerçeveleri 2+ kenara değer.
- **Solidity (doluluk) filtresi:** kontur alanının, o konturu saran kutunun
  alanına oranı düşükse (ince/L-şekilli/boşluklu bir şekil - tipik bir kenar
  artefaktı) elenir. Gerçek nesneler daha "dolu" bir şekle sahiptir.

**Test edildi:** iki köşeye yapay köşe-gölgesi eklenmiş bir test görüntüsünde,
2 köşe artefaktının 2'si de elendi, ortadaki 3 gerçek ürünün 3'ü de doğru
tespit edildi. (`cv/detector.py`)

Yine de bu klasik yöntem "kaba" kalmaya devam ediyor - **gerçek anlamda çok
daha iyi bir tespit için YOLO-World kurulumunu (aşağıda) öneriyorum**, orada
artık kenar/köşe tahmini değil gerçek bir öğrenilmiş model çalışıyor.

#### 3) Tarif önerileri — çok daha çeşitli ve "gurme"
Rule-based (LLM yoksa devreye giren) tarif veritabanı 6'dan **~20 tarife**
çıkarıldı: "Zeytinyağlı Kekikli Fırın Domates", "Akdeniz Usulü Ispanak-Peynir
Böreği", "Limonlu Tavuk Şiş", "Kayısılı Tavuk (Tatlı-Ekşi)" gibi gerçek
pişirme yöntemi/çeşni içeren tarifler eklendi - artık sadece "domates+peynir
= salata" gibi basit eşleştirmeler yok. Ayrıca LLM prompt'u da (Ollama
kullanılıyorsa) artık açıkça "sıradan değil, çeşni/pişirme yöntemiyle
zenginleştirilmiş, gurme" tarifler istiyor. (`recipes.py`)

#### 4) Alışveriş listesi artık boş kalmıyor + elle ekleme
İki değişiklik:
- Eski "en verimli kombinasyonu bul" mantığı bazen listeyi boş bırakıyordu
  (bir tarifin hiç eksiği yoksa). Artık en verimli birkaç tarifin eksik
  malzemeleri DİREKT listeye ekleniyor - senin istediğin gibi.
- **Elle ekleme:** Alışveriş Listesi kartının altında bir metin kutusu var -
  "ekmek" gibi tariften bağımsız bir şeyi yazıp "Ekle" diyebilirsin. Bu
  öğeler veritabanında saklanıyor (sayfa yenilense de kaybolmuyor), ✕
  butonuyla silinebiliyor. (`shopping.py`, `main.py: POST/DELETE
  /shopping-list/manual`)

#### 5) 3+'dan sonrası için manuel porsiyon girişi
Miktar seçeneklerine 5. bir buton eklendi: "Diğer (gir)". Seçtiğinde bir
sayı kutusu açılıyor, istediğin porsiyon sayısını (örn. 7) yazabiliyorsun.
Bu değer `"custom:7"` gibi saklanıp tüm hesaplamalarda (tüketim hızı,
forecast) normal sayılar gibi kullanılıyor. (`schemas.py`, `forecasting.py:
quantity_to_value`)

#### 6) 🔴 EN ÖNEMLİSİ: tüketim hızı artık gerçekten hesaplanıyor
**Kök neden bulundu:** `/confirm` endpoint'i, `container_id` gönderilmediğinde
HER ZAMAN yepyeni bir container açıyordu. Frontend hiçbir zaman
`container_id` göndermiyordu, yani her taramanda (aynı ürünü de taransan)
tamamen ayrı bir "kap" kaydı oluşuyordu ve bir FoodInstance ASLA ikinci bir
gözlem almıyordu - tüketim hızı hesaplamak için gereken "aynı üründe 2+
gözlem" şartı hiç sağlanamıyordu.

**Düzeltme:** `container_id` verilmediğinde backend artık önce otomatik bir
eşleştirme deniyor - aynı yiyecek türüyle (`food_type`, büyük/küçük harf
duyarsız) hâlâ aktif bir container var mı diye bakıyor, varsa ona bağlanıyor.
Frontend'de de artık her bölge için bir "hangi kaba ait?" seçici var:
**📦 Otomatik eşleştir** (varsayılan), **🆕 Yeni kap**, ya da mevcut
kaplardan birini elle seç.

**Test edildi:** aynı ürünü iki gün arayla iki kez tarayınca artık
`consumption_rate_per_day: 0.5` doğru hesaplanıyor, sadece **1 container**
oluşuyor (2 değil). Ayrıca bunu test ederken ikinci bir gerçek hata daha
bulundu ve düzeltildi: iki tarama ARADAKİ SÜRE ÇOK KISAYSA (örn. aynı gün
içinde art arda test) bölme işlemi anlamsız derecede büyük bir "porsiyon/gün"
değeri üretiyordu (test sırasında `1.594.331 porsiyon/gün` gibi saçma bir
sayı çıktı) - artık en az 12 saatlik bir aralık şartı var, daha kısa
aralıklar "henüz yeterli veri yok" sayılıyor. (`main.py: _find_auto_match_
container`, `forecasting.py: MIN_DAYS_FOR_RATE`)

**Geçmiş sekmesi (5. kart):** artık `GET /history` ile TÜM gözlemlerin
(aktif olsun olmasın) tam listesi, tarih + "önceki taramadan bu yana kaç
gün" bilgisiyle görülebiliyor. Envanterdeki her satırda da kaç kez tarandığı
(`observation_count`) gösteriliyor - tüketim hızının neden var/yok olduğunu
buradan takip edebilirsin.

#### 7) Genel iyileştirmeler
Yukarıdakilerin hepsi gerçek verilerle (curl ile simüle edilmiş çok-günlü
senaryolar dahil) test edildi. Ayrıca:
- `/inventory`, `/history`, `/food-types`, `/containers/active-summary` yeni
  endpoint'lerin hepsi şemalı (Pydantic) ve dokümante edildi
- Frontend artık backend'deki her yeni alanı (custom miktar, container
  seçimi, öğrenilen öneriler, manuel alışveriş, geçmiş) kullanıyor

---

## 🎯 YOLO-World kurulumu (opsiyonel, gerçek nesne tespiti için)

```bash
cd backend
pip install -r requirements-cv.txt
```

API key gerekmez, ilk çalıştırmada model (~50MB) otomatik/ücretsiz iner.
`/scan` yanıtındaki `"detector"` alanı `"yolo_world"` gösteriyorsa devrede
demektir.

## 🧠 Ollama kurulumu (opsiyonel, LLM destekli tarif/risk için)

final-legal-ai-mvp projende zaten kullanıyorsun - muhtemelen ek bir şey
kurmana gerek yok. Farklı model kullanıyorsan:

```bash
export OLLAMA_MODEL=senin-modelin   # Windows: $env:OLLAMA_MODEL="senin-modelin"
```

Ollama kapalıysa hiçbir şey kırılmaz - sistem otomatik olarak rule-based
tariflere ve sabit bozulma-süresi tablosuna düşer.

---

## Proje yapısı

```
smart-pantry-ai/
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI endpoints (10 endpoint)
│   │   ├── models.py           # Container / FoodInstance / Observation / ManualShoppingItem
│   │   ├── schemas.py          # Pydantic şemaları
│   │   ├── database.py         # SQLite bağlantısı
│   │   ├── forecasting.py      # Tüketim hızı + forecast + israf riski
│   │   ├── shelf_life.py       # Genel bozulma süresi (LLM + tablo)
│   │   ├── recipes.py          # ~20 tarif + LLM entegrasyonu
│   │   ├── shopping.py         # Otomatik alışveriş listesi mantığı
│   │   ├── llm_client.py       # Ollama istemcisi
│   │   └── cv/detector.py      # Klasik (çok filtreli) + YOLO-World tespit
│   ├── requirements.txt
│   └── requirements-cv.txt
└── frontend/
    └── index.html              # Tarama + envanter + tarif + alışveriş + geçmiş (5 kart)
```

## Sırada ne var

- Görsel container re-identification (CLIP/SigLIP) - şu an "aynı isim = aynı
  kap" varsayımıyla çalışıyor, iki tane aynı ürün (2 ayrı yoğurt kabı gibi)
  olduğunda karışabilir
- PWA'ya çevirmek / backend'i buluta almak
- Haftalık öğün planı optimizasyonu (OR-Tools)


## v11 değişiklikleri
- **Geçmiş tablosunda "Tüketim hızı" sütunu**: her satırda önceki kayda göre porsiyon/gün. Hız hesaplanamıyorsa nedeni yanında yazar
  (ilk tarama / iki kayıt arası 12 saatten kısa / miktar azalmamış).
- **YOLO genel isimleri**: "şişe, kavanoz, saklama kabı, meyve, sebze, sos" gibi genel sınıflar artık yemek adı olarak otomatik
  doldurulmaz; ipucu olarak gösterilir ve kategoriye uygun hızlı seçim butonları öne çıkar. Spesifik sınıflar (domates, süt...)
  yalnızca güven >= 0.35 ise doldurulur (`SMART_PANTRY_PREFILL_CONF` ile değişir).
- **Tarifi tamamlayan malzemeler**: börek -> yufka, çoban salatası -> salatalık/biber/maydanoz vb. alışveriş listesine eklenir.
