# 🧊 Smart Pantry AI (Türkçe)

> 🇬🇧 English: [README.md](README.md)

Buzdolabı fotoğrafından **tüketim hızı → bitiş tahmini → israf/bozulma riski → tarif önerisi → alışveriş listesi** üreten, tamamen yerelde çalışan web uygulaması. API anahtarı gerekmez, veri bilgisayarından çıkmaz.

## Akış

📷 Tara → ✅ Doğrula (insan onayı) → 📦 Envanter → 📈 Tüketim hızı → ⏳ Bitiş tahmini → ⚠️ İsraf riski → 🍽 Tarif → 🛒 Alışveriş → 🕘 Geçmiş

## Özellikler

- **Nesne tespiti:** OpenCV (klasik) + isteğe bağlı YOLO-World. Model sadece *aday* bölge önerir; yiyecek türünü ve miktarı sen onaylarsın.
- **Genel isimler (şişe, kavanoz, saklama kabı, meyve…)** otomatik doldurulmaz, ipucu olarak gösterilir: kapalı kabın içi görüntüden bilinemez.
- **Tüketim hızı:** aynı kabın ardışık gözlemlerinden, zaman ağırlıklı. 12 saatten kısa aralıklar veya miktarın azalmadığı durumlarda hız hesaplanmaz; Geçmiş tablosu nedenini yazar.
- **İsraf riski:** ≤0 gün 🚫 TÜKETME · ≤3 gün ⚠️ ACİL TÜKET · ≤5 gün orta · üstü düşük. ~100 ürünlük raf ömrü tablosu, opsiyonel Ollama LLM, satın alma tarihi.
- **Tarif + alışveriş:** evdekiler + market listesi birlikte değerlendirilir; tarifi tamamlayan malzemeler (börek→yufka, çoban salatası→salatalık…) listeye önerilir.
- **Envanterden çıkarma:** Tükettim / Attım / Yanlış kayıt; sonraki taramada görünmeyen ürünler için *sen karar verirsin*.

## Kurulum (Windows PowerShell)

```powershell
git clone https://github.com/AleynaAltunsu/smart-pantry-ai.git
cd smart-pantry-ai\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-cv.txt
uvicorn app.main:app --reload
```

İkinci PowerShell penceresi:

```powershell
cd smart-pantry-ai\frontend
python -m http.server 5500
```

Tarayıcıda **http://localhost:5500** → Ctrl+F5. API: `http://127.0.0.1:8000` (`/health`, `/docs`).

- `requirements-cv.txt` (YOLO-World) isteğe bağlıdır; kurulmazsa klasik yöntem kullanılır. İlk YOLO yüklemesinde model ağırlıkları ve CLIP (~340 MB) bir kez iner. `clip` paketi `backend/wheels` içinde hazırdır, **git gerekmez**.
- Yol boşluk içeriyorsa tırnak kullan: `cd "C:\Users\...\smart-pantry-ai\backend"`.
- Backend (8000) ve frontend (5500) ayrı portlarda çalışır; ikisi de açık kalmalı.

## Test

```powershell
cd backend
pip install -r requirements-dev.txt
pytest -q
```

## Ayarlar

Ortam değişkenleri için [README.md](README.md#configuration-environment-variables) tablosuna bak (`SMART_PANTRY_USE_YOLO`, `SMART_PANTRY_PREFILL_CONF`, `OLLAMA_MODEL` …). PowerShell örneği: `$env:SMART_PANTRY_USE_YOLO="0"`.

## Gizlilik

Veriler yerel SQLite dosyasında (`smart_pantry.db`, git'e girmez). Fotoğraflar bellekte işlenir, saklanmaz.

Sürüm geçmişi: [docs/CHANGELOG.md](docs/CHANGELOG.md)
