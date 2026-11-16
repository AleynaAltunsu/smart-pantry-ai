"""
Smart Pantry AI - Database setup
SQLite kullanıyoruz (MVP için yeterli, ileride PostgreSQL'e geçilebilir).
"""
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

# Varsayılan: çalışma klasöründe smart_pantry.db. Değiştirmek için: SMART_PANTRY_DB_URL=sqlite:///C:/yol/db.sqlite
DATABASE_URL = os.environ.get("SMART_PANTRY_DB_URL", "sqlite:///./smart_pantry.db")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema(eng=None):
    """
    SQLite için hafif otomatik göç: eski bir veritabanına sonradan eklenen sütunları
    ekler. Böylece sürüm değiştirince `smart_pantry.db` silmen GEREKMEZ, verin korunur.
    """
    eng = eng or engine
    wanted = {
        "food_instances": {
            "purchased_at": "DATETIME",   # v6
            "entry_source": "VARCHAR",    # v10: 'scan' | 'manual'
            "end_reason": "VARCHAR",      # v10: 'consumed' | 'discarded' | 'replaced'
        },
    }
    insp = inspect(eng)
    existing_tables = set(insp.get_table_names())
    with eng.begin() as conn:
        for table, cols in wanted.items():
            if table not in existing_tables:
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
