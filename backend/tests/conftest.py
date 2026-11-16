import os
import sys
import tempfile
from pathlib import Path

# Testler kullanıcının gerçek veritabanına dokunmasın: geçici DB + YOLO kapalı (hızlı, deterministik)
_tmp = tempfile.mkdtemp(prefix="smart_pantry_test_")
os.environ["SMART_PANTRY_DB_URL"] = f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["SMART_PANTRY_USE_YOLO"] = "0"
os.environ.setdefault("OLLAMA_TIMEOUT_SECONDS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
