import enum
from datetime import datetime, timezone
from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey, JSON, Integer, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase): pass
class ListingStatus(str,enum.Enum):
    ACTIVE="ACTIVE"; SOLD_CONFIRMED="SOLD_CONFIRMED"; DISAPPEARED="DISAPPEARED"; DELETED="DELETED"; UNKNOWN="UNKNOWN"
class Alert(Base):
    __tablename__="alerts"
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(160))
    include_terms: Mapped[list]=mapped_column(JSON, default=list)
    exclude_terms: Mapped[list]=mapped_column(JSON, default=list)
    filters: Mapped[dict]=mapped_column(JSON, default=dict)
    min_price: Mapped[float|None]=mapped_column(Float, nullable=True)
    max_price: Mapped[float|None]=mapped_column(Float, nullable=True)
    scan_minutes: Mapped[int]=mapped_column(Integer, default=10)
    notify_threshold: Mapped[str]=mapped_column(String(20), default="GOOD")
    paused: Mapped[bool]=mapped_column(Boolean, default=False)
    last_scan_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
class Listing(Base):
    __tablename__="listings"
    id: Mapped[int]=mapped_column(primary_key=True)
    alert_id: Mapped[int]=mapped_column(ForeignKey("alerts.id",ondelete="CASCADE"), index=True)
    external_id: Mapped[str]=mapped_column(String(80), index=True)
    title: Mapped[str]=mapped_column(String(500))
    description: Mapped[str]=mapped_column(String(5000), default="")
    price: Mapped[float]=mapped_column(Float)
    shipping_estimate: Mapped[float]=mapped_column(Float, default=0)
    buyer_fee: Mapped[float]=mapped_column(Float, default=0)
    currency: Mapped[str]=mapped_column(String(8), default="EUR")
    url: Mapped[str]=mapped_column(String(1000))
    image_url: Mapped[str|None]=mapped_column(String(1000), nullable=True)
    image_urls: Mapped[list]=mapped_column(JSON, default=list)
    seller_name: Mapped[str|None]=mapped_column(String(160), nullable=True)
    seller_rating: Mapped[float|None]=mapped_column(Float, nullable=True)
    seller_reviews_count: Mapped[int|None]=mapped_column(Integer, nullable=True)
    condition: Mapped[str|None]=mapped_column(String(80), nullable=True)
    size: Mapped[str|None]=mapped_column(String(80), nullable=True)
    score_label: Mapped[str|None]=mapped_column(String(20), nullable=True)
    score_percentile: Mapped[float|None]=mapped_column(Float, nullable=True)
    score_median: Mapped[float|None]=mapped_column(Float, nullable=True)
    score_sample_count: Mapped[int]=mapped_column(Integer, default=0)
    score_confidence: Mapped[str|None]=mapped_column(String(20), nullable=True)
    status: Mapped[ListingStatus]=mapped_column(default=ListingStatus.ACTIVE)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__=(UniqueConstraint("alert_id","external_id"),)
class ListingSnapshot(Base):
    __tablename__="listing_snapshots"
    id: Mapped[int]=mapped_column(primary_key=True)
    listing_id: Mapped[int]=mapped_column(ForeignKey("listings.id",ondelete="CASCADE"), index=True)
    price: Mapped[float]=mapped_column(Float)
    status: Mapped[ListingStatus]
    observed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class Product(Base):
    __tablename__="products"
    id: Mapped[int]=mapped_column(primary_key=True)
    canonical_key: Mapped[str]=mapped_column(String(300), unique=True)
    brand: Mapped[str|None]=mapped_column(String(120), nullable=True)
    model: Mapped[str|None]=mapped_column(String(200), nullable=True)
    attributes: Mapped[dict]=mapped_column(JSON, default=dict)
class ListingProductMatch(Base):
    __tablename__="listing_product_match"
    listing_id: Mapped[int]=mapped_column(ForeignKey("listings.id",ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[int]=mapped_column(ForeignKey("products.id",ondelete="CASCADE"))
    confidence: Mapped[float]=mapped_column(Float, default=0)
class PriceStat(Base):
    __tablename__="price_stats"
    id: Mapped[int]=mapped_column(primary_key=True)
    product_id: Mapped[int]=mapped_column(ForeignKey("products.id",ondelete="CASCADE"), index=True)
    condition: Mapped[str]=mapped_column(String(80))
    median: Mapped[float]=mapped_column(Float)
    p20: Mapped[float]=mapped_column(Float)
    p75: Mapped[float]=mapped_column(Float)
    sample_count: Mapped[int]
    window_days: Mapped[int]=mapped_column(default=60)
class ExternalPrice(Base):
    __tablename__="external_prices"
    id: Mapped[int]=mapped_column(primary_key=True)
    product_id: Mapped[int]=mapped_column(ForeignKey("products.id",ondelete="CASCADE"), index=True)
    source: Mapped[str]=mapped_column(String(50))
    value: Mapped[float]=mapped_column(Float)
    currency: Mapped[str]=mapped_column(String(8), default="EUR")
    payload: Mapped[dict]=mapped_column(JSON, default=dict)
class UserFlag(Base):
    __tablename__="user_flags"
    listing_id: Mapped[int]=mapped_column(ForeignKey("listings.id",ondelete="CASCADE"), primary_key=True)
    favorite: Mapped[bool]=mapped_column(Boolean, default=False)
    seen: Mapped[bool]=mapped_column(Boolean, default=False)
    hidden: Mapped[bool]=mapped_column(Boolean, default=False)
