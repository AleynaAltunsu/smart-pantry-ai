"""
Smart Pantry AI - LLM Client (Ollama)

Neden Ollama: tamamen yerel çalışır, ücretsizdir, API key gerektirmez.
(final-legal-ai-mvp projende zaten Ollama kullanıyorsun - aynı kurulum burada
da işe yarar.)

Bu modül iki yerde kullanılıyor:
- forecasting.py: bir yiyeceğin genel bozulma süresini tahmin etmek için
- recipes.py: envanterden gerçek/yaratıcı tarif önerileri üretmek için

TASARIM KARARI: Ollama çalışmıyorsa (kurulu değil / model çekilmemiş / kapalı)
sistem SESSİZCE ve OTOMATİK olarak rule-based fallback'lere düşer. Uygulama
LLM olmadan da eksiksiz çalışmaya devam eder - sadece daha basit tahminlerle.
"""
import json
import os
from typing import Optional, Union

import requests

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "20"))

_ollama_available: Optional[bool] = None  # None = henüz kontrol edilmedi


def is_ollama_available() -> bool:
    """Sonucu cache'ler - her istek için tekrar tekrar denemeyelim."""
    global _ollama_available
    if _ollama_available is not None:
        return _ollama_available
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        _ollama_available = resp.status_code == 200
    except Exception:
        _ollama_available = False
    return _ollama_available


def ask_json(prompt: str) -> Optional[Union[dict, list]]:
    """
    Ollama'ya bir prompt gönderir, JSON parse edilmiş yanıtı döner.
    Herhangi bir hata durumunda (bağlantı yok, model yok, bozuk JSON) None döner
    - çağıran taraf bunu "LLM kullanılamadı, fallback'e düş" olarak yorumlamalı.
    """
    if not is_ollama_available():
        return None

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        raw_text = resp.json().get("response", "")
        return json.loads(raw_text)
    except requests.exceptions.RequestException as e:
        print(f"[llm_client] Ollama isteği başarısız, fallback'e düşülüyor: {e}")
        return None
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"[llm_client] Ollama yanıtı JSON olarak parse edilemedi: {e}")
        return None
