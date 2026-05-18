from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class SeasonConfig(Base):
    __tablename__ = "season_config"
    id = Column(Integer, primary_key=True, index=True)
    season_name = Column(String, nullable=False)
    zone_ids = Column(JSONB, nullable=False)
    mythic_ilvl_cap = Column(Integer, nullable=False)
    heroic_ilvl_cap = Column(Integer, nullable=False)
    normal_ilvl_cap = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


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

    wowhead_bis_items = relationship(
        "WowheadBisItem", back_populates="snapshot", cascade="all, delete-orphan"
    )


class ArchonPopularItem(Base):
    """Most-used items per slot, from gear-and-tier-set."""
    __tablename__ = "archon_popular_items"
    __table_args__ = (Index("ix_popular_items_snapshot_id", "snapshot_id"),)

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("archon_spec_snapshots.id"), nullable=False)
    slot = Column(String, nullable=False)
    rank = Column(Integer, nullable=False)
    item_id = Column(Integer, nullable=False)
    item_id2 = Column(Integer, nullable=True)
    item_name = Column(String, nullable=False)
    usage_percent = Column(Float, nullable=True)
    is_crafted = Column(Boolean, nullable=False, default=False)
    is_embellishment = Column(Boolean, nullable=False, default=False)

    snapshot = relationship("ArchonSpecSnapshot", back_populates="popular_items")


class WowheadBisItem(Base):
    """BiS items from WoWhead guides, one row per slot per spec snapshot."""
    __tablename__ = "wowhead_bis_items"
    __table_args__ = (Index("ix_wowhead_bis_snapshot_id", "snapshot_id"),)

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("archon_spec_snapshots.id"), nullable=False)
    slot = Column(String, nullable=False)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=False, default="")

    snapshot = relationship("ArchonSpecSnapshot", back_populates="wowhead_bis_items")


class ArchonPopularEnchant(Base):
    """Most-used enchants per slot, from enchants-and-gems."""
    __tablename__ = "archon_popular_enchants"
    __table_args__ = (Index("ix_popular_enchants_snapshot_id", "snapshot_id"),)

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("archon_spec_snapshots.id"), nullable=False)
    slot = Column(String, nullable=False)
    rank = Column(Integer, nullable=False)
    enchant_id = Column(Integer, nullable=False)
    enchant_name = Column(String, nullable=False)
    usage_percent = Column(Float, nullable=True)
    icon_name = Column(String, nullable=False, server_default="")

    snapshot = relationship("ArchonSpecSnapshot", back_populates="popular_enchants")


class ArchonPopularGem(Base):
    """Most-used gems (epic / rare), from enchants-and-gems."""
    __tablename__ = "archon_popular_gems"
    __table_args__ = (Index("ix_popular_gems_snapshot_id", "snapshot_id"),)

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("archon_spec_snapshots.id"), nullable=False)
    gem_quality = Column(String, nullable=False)  # "epic" | "rare"
    rank = Column(Integer, nullable=False)
    item_id = Column(Integer, nullable=False)
    gem_name = Column(String, nullable=False)
    usage_percent = Column(Float, nullable=True)

    snapshot = relationship("ArchonSpecSnapshot", back_populates="popular_gems")
