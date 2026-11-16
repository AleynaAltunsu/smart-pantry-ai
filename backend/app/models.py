"""
Smart Pantry AI - ORM Models (MVP1)

Kritik mimari karar: Container != FoodInstance
- Container: fiziksel kap (buzdolabında duran gerçek nesne)
- FoodInstance: o kabın belirli bir zaman aralığında içinde bulunan yiyecek
- Observation: her taramada o FoodInstance için yapılan miktar gözlemi
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Boolean
)
from sqlalchemy.orm import relationship

from app.database import Base


class Container(Base):
    __tablename__ = "containers"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, nullable=True)  # kullanıcı isterse isim verebilir
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    reference_crop_path = Column(String, nullable=True)  # gelecekte embedding eşleştirme için

    food_instances = relationship(
        "FoodInstance", back_populates="container", cascade="all, delete-orphan"
    )


class FoodInstance(Base):
    __tablename__ = "food_instances"

    id = Column(Integer, primary_key=True, index=True)
    container_id = Column(Integer, ForeignKey("containers.id"), nullable=False)
    food_type = Column(String, nullable=False)  # örn: "yoğurt", "tavuk", "ıspanak"
    started_at = Column(DateTime, default=datetime.utcnow)  # ilk TARANDIĞI an
    purchased_at = Column(DateTime, nullable=True)  # elle girilen gerçek SATIN ALMA tarihi
    entry_source = Column(String, default="scan")  # 'scan' (fotoğraftan) | 'manual' (elle eklendi)
    end_reason = Column(String, nullable=True)  # 'consumed' | 'discarded' | 'replaced'
    ended_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    container = relationship("Container", back_populates="food_instances")
    observations = relationship(
        "Observation", back_populates="food_instance", cascade="all, delete-orphan"
    )


class Observation(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, index=True)
    food_instance_id = Column(Integer, ForeignKey("food_instances.id"), nullable=False)
    observed_at = Column(DateTime, default=datetime.utcnow)
    # Porsiyon/seviye tabanlı miktar - ilk MVP'de gram tahmini YOK (bilinçli karar)
    quantity_level = Column(String, nullable=False)  # "less_half" | "1" | "2" | "3plus"
    source = Column(String, default="user_confirmed")  # user_confirmed | ai_predicted

    food_instance = relationship("FoodInstance", back_populates="observations")


class ManualShoppingItem(Base):
    """
    Kullanıcının elle eklediği alışveriş listesi öğeleri (tariften/forecast'tan
    bağımsız - "ekmek al" gibi). Otomatik öğelerle birleştirilip tek listede
    gösterilir, ayrı ayrı silinebilir.
    """
    __tablename__ = "manual_shopping_items"

    id = Column(Integer, primary_key=True, index=True)
    food_type = Column(String, nullable=False)
    note = Column(String, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)


class DismissedShoppingItem(Base):
    """Kullanıcının alışveriş listesinden kaldırdığı OTOMATİK öneriler (tekrar gösterilmez)."""
    __tablename__ = "dismissed_shopping_items"

    id = Column(Integer, primary_key=True, index=True)
    food_type = Column(String, nullable=False)
    dismissed_at = Column(DateTime, default=datetime.utcnow)
