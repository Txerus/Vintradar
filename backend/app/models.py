import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ListingStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    RESERVED = "RESERVED"
    SOLD_CONFIRMED = "SOLD_CONFIRMED"
    DISAPPEARED = "DISAPPEARED"
    DELETED = "DELETED"
    UNKNOWN = "UNKNOWN"


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    include_terms: Mapped[list] = mapped_column(JSON, default=list)
    exclude_terms: Mapped[list] = mapped_column(JSON, default=list)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    min_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    scan_minutes: Mapped[int] = mapped_column(Integer, default=10)
    notify_threshold: Mapped[str] = mapped_column(String(20), default="GOOD")
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bootstrap_pages_done: Mapped[int] = mapped_column(Integer, default=0)


class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(Float)
    total_item_price: Mapped[float] = mapped_column(Float, default=0)
    shipping_estimate: Mapped[float] = mapped_column(Float, default=0)
    buyer_fee: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    url: Mapped[str] = mapped_column(String(1000))
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    image_urls: Mapped[list] = mapped_column(JSON, default=list)
    brand: Mapped[str | None] = mapped_column(String(160), nullable=True)
    category_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    category_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category_path: Mapped[list] = mapped_column(JSON, default=list)
    colors: Mapped[list] = mapped_column(JSON, default=list)
    seller_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    seller_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    seller_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    seller_reviews_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seller_location: Mapped[str | None] = mapped_column(String(240), nullable=True)
    seller_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    seller_last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(80), nullable=True)
    condition_segment: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    size: Mapped[str | None] = mapped_column(String(80), nullable=True)
    favourite_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    view_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enrichment_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    enrichment_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    score_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_median: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_sample_count: Mapped[int] = mapped_column(Integer, default=0)
    score_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pricing_explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    scoring_version: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ListingStatus] = mapped_column(default=ListingStatus.ACTIVE)
    status_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def alert_id(self) -> int | None:
        return getattr(self, "_legacy_alert_id", None)

    @alert_id.setter
    def alert_id(self, value: int | None) -> None:
        # Constructor compatibility only; alert_listings is authoritative in v0.2.
        self._legacy_alert_id = value


class AlertListing(Base):
    __tablename__ = "alert_listings"
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ListingSnapshot(Base):
    __tablename__ = "listing_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    price: Mapped[float] = mapped_column(Float)
    total_item_price: Mapped[float] = mapped_column(Float, default=0)
    favourite_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    view_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[ListingStatus]
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_key: Mapped[str] = mapped_column(String(300), unique=True)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    targeted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ListingProductMatch(Base):
    __tablename__ = "listing_product_match"
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    recognized_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    excluded_from_stats: Mapped[bool] = mapped_column(Boolean, default=False)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)


class PriceStat(Base):
    __tablename__ = "price_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    condition: Mapped[str] = mapped_column(String(80))
    median: Mapped[float] = mapped_column(Float)
    p20: Mapped[float] = mapped_column(Float)
    p75: Mapped[float] = mapped_column(Float)
    sample_count: Mapped[int]
    window_days: Mapped[int] = mapped_column(default=90)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("product_id", "condition"),)


class ExternalPrice(Base):
    __tablename__ = "external_prices"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(50))
    value: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("product_id", "source"),)


class UserFlag(Base):
    __tablename__ = "user_flags"
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    seen: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)


class SellerProfile(Base):
    __tablename__ = "seller_profiles"
    seller_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkerState(Base):
    __tablename__ = "worker_state"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    recent_403_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_429_count: Mapped[int] = mapped_column(Integer, default=0)
    enrichment_queue_size: Mapped[int] = mapped_column(Integer, default=0)
