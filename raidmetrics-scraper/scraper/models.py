from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ArchonScrapeRun(Base):
    __tablename__ = "archon_scrape_runs"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    success = Column(Boolean, nullable=False, default=False)
    error_message = Column(String, nullable=True)
    specs_scraped = Column(Integer, nullable=False, default=0)

    snapshots = relationship(
        "ArchonSpecSnapshot", back_populates="run", cascade="all, delete-orphan"
    )


class ArchonSpecSnapshot(Base):
    """One snapshot per spec per scrape run."""
    __tablename__ = "archon_spec_snapshots"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("archon_scrape_runs.id"), nullable=False)
    spec_slug = Column(String, nullable=False)
    class_slug = Column(String, nullable=False)
    scraped_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    run = relationship("ArchonScrapeRun", back_populates="snapshots")
    bis_items = relationship(
        "ArchonBisItem", back_populates="snapshot", cascade="all, delete-orphan"
    )
    popular_items = relationship(
        "ArchonPopularItem", back_populates="snapshot", cascade="all, delete-orphan"
    )
    popular_enchants = relationship(
        "ArchonPopularEnchant", back_populates="snapshot", cascade="all, delete-orphan"
    )
    popular_gems = relationship(
        "ArchonPopularGem", back_populates="snapshot", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("run_id", "spec_slug", "class_slug"),)


class ArchonBisItem(Base):
    """Best-in-slot item per slot, from the Archon overview page."""
    __tablename__ = "archon_bis_items"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("archon_spec_snapshots.id"), nullable=False)
    slot = Column(String, nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=False)
    is_bis = Column(Boolean, nullable=False, default=False)
    usage_percent = Column(Float, nullable=True)
    gem_ids = Column(String, nullable=True)   # comma-separated item IDs, e.g. "100,200"
    enchant_id = Column(Integer, nullable=True)

    snapshot = relationship("ArchonSpecSnapshot", back_populates="bis_items")


class ArchonPopularItem(Base):
    """Most-used items per slot, from gear-and-tier-set."""
    __tablename__ = "archon_popular_items"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("archon_spec_snapshots.id"), nullable=False)
    slot = Column(String, nullable=False)
    rank = Column(Integer, nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=False)
    usage_percent = Column(Float, nullable=True)
    is_crafted = Column(Boolean, nullable=False, default=False)
    is_embellishment = Column(Boolean, nullable=False, default=False)

    snapshot = relationship("ArchonSpecSnapshot", back_populates="popular_items")


class ArchonPopularEnchant(Base):
    """Most-used enchants per slot, from enchants-and-gems."""
    __tablename__ = "archon_popular_enchants"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("archon_spec_snapshots.id"), nullable=False)
    slot = Column(String, nullable=False)
    rank = Column(Integer, nullable=False)
    enchant_id = Column(Integer, nullable=False)
    enchant_name = Column(String, nullable=False)
    usage_percent = Column(Float, nullable=True)

    snapshot = relationship("ArchonSpecSnapshot", back_populates="popular_enchants")


class ArchonPopularGem(Base):
    """Most-used gems (epic / rare), from enchants-and-gems."""
    __tablename__ = "archon_popular_gems"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("archon_spec_snapshots.id"), nullable=False)
    gem_quality = Column(String, nullable=False)  # "epic" | "rare"
    rank = Column(Integer, nullable=False)
    item_id = Column(Integer, nullable=False)
    gem_name = Column(String, nullable=False)
    usage_percent = Column(Float, nullable=True)

    snapshot = relationship("ArchonSpecSnapshot", back_populates="popular_gems")
