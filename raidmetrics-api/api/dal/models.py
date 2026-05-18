from datetime import UTC, datetime

from sqlalchemy import (BigInteger, Boolean, Column, DateTime, Float,
                        ForeignKey, Integer, String, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class WowItemIcon(Base):
    __tablename__ = "wow_item_icons"
    item_id = Column(Integer, primary_key=True)
    icon_url = Column(String, nullable=False)
    fetched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    blizzard_sub = Column(String, unique=True, index=True)
    blizzard_access_token = Column(String, nullable=True)
    email = Column(String, unique=True, index=True)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    refresh_tokens = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    token_hash = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)
    replaced_by = Column(Integer, nullable=True)  # id of token that replaced this one
    user_agent = Column(String, nullable=True)
    ip = Column(String, nullable=True)

    user = relationship("User", back_populates="refresh_tokens")


class UserCharacter(Base):
    __tablename__ = "user_characters"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    character_name = Column(String, nullable=False)
    realm_slug = Column(String, nullable=False)
    guild_id = Column(BigInteger, nullable=True)
    is_gm = Column(Boolean, default=False)
    is_officer = Column(Boolean, default=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (UniqueConstraint("user_id", "character_name", "realm_slug"),)


class RaidRoster(Base):
    __tablename__ = "raid_rosters"
    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(BigInteger, nullable=False, index=True)
    guild_name = Column(String, nullable=False)
    guild_realm_slug = Column(String, nullable=False)
    difficulty = Column(String, nullable=False)  # 'normal', 'heroic', 'mythic'
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    members = relationship(
        "RaidRosterMember",
        back_populates="roster",
        cascade="all, delete-orphan",
        order_by="RaidRosterMember.sort_order",
    )
    __table_args__ = (UniqueConstraint("guild_id", "difficulty"),)


class RaidRosterMember(Base):
    __tablename__ = "raid_roster_members"
    id = Column(Integer, primary_key=True, index=True)
    roster_id = Column(Integer, ForeignKey("raid_rosters.id"), nullable=False)
    character_name = Column(String, nullable=False)
    character_realm = Column(String, nullable=False)
    character_class = Column(String, nullable=True)
    role = Column(String, nullable=True)  # 'tank' | 'healer' | 'dps'
    sort_order = Column(Integer, default=0)

    roster = relationship("RaidRoster", back_populates="members")


class SeasonConfig(Base):
    __tablename__ = "season_config"
    id = Column(Integer, primary_key=True, index=True)
    season_name = Column(String, nullable=False)       # e.g. "Season 1 Raids"
    zone_ids = Column(JSONB, nullable=False)            # [1307, 1308, 1314]
    mythic_ilvl_cap = Column(Integer, nullable=False)  # 289
    heroic_ilvl_cap = Column(Integer, nullable=False)  # 276
    normal_ilvl_cap = Column(Integer, nullable=False)  # 263
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class LootReport(Base):
    __tablename__ = "loot_reports"
    id = Column(Integer, primary_key=True, index=True)
    guild_id = Column(BigInteger, nullable=False, index=True)
    character_name = Column(String, nullable=False)
    realm_slug = Column(String, nullable=False)
    difficulty = Column(String, nullable=False)         # 'normal', 'heroic', 'mythic'
    raidbots_report_id = Column(String, nullable=False)
    baseline_dps = Column(Float, nullable=False)
    equipped_items = Column(JSONB, nullable=False)      # snapshot of gear at sim time
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    items = relationship(
        "LootReportItem",
        back_populates="report",
        cascade="all, delete-orphan",
    )
    __table_args__ = (UniqueConstraint("guild_id", "character_name", "realm_slug", "difficulty"),)


class LootReportItem(Base):
    __tablename__ = "loot_report_items"
    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("loot_reports.id"), nullable=False, index=True)
    zone_id = Column(Integer, nullable=False)
    encounter_id = Column(Integer, nullable=False)
    item_id = Column(Integer, nullable=False)
    item_ilvl = Column(Integer, nullable=False)
    slot_name = Column(String, nullable=False)
    item_name = Column(String, nullable=True)
    boss_name = Column(String, nullable=True)
    raid_name = Column(String, nullable=True)
    upgrade_dps = Column(Float, nullable=False)
    upgrade_pct = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    report = relationship("LootReport", back_populates="items")


class BossLootItem(Base):
    """Items that drop from each raid boss, scraped from Blizzard's Journal API."""
    __tablename__ = "boss_loot_items"
    id = Column(Integer, primary_key=True, index=True)
    encounter_id = Column(Integer, nullable=False, index=True)
    zone_id = Column(Integer, nullable=False)
    boss_name = Column(String, nullable=True)
    item_id = Column(Integer, nullable=False)
    item_name = Column(String, nullable=True)
    is_token = Column(Boolean, nullable=False, default=False)
    synthesizes_slot = Column(String, nullable=True)   # e.g. 'legs'; null for non-tokens
    allowed_class_ids = Column(JSONB, nullable=True)   # null = unrestricted
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (UniqueConstraint("encounter_id", "item_id"),)