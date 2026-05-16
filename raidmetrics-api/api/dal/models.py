from datetime import UTC, datetime

from sqlalchemy import (BigInteger, Boolean, Column, DateTime, ForeignKey,
                        Integer, String, UniqueConstraint)
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