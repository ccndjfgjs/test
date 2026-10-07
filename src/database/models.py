from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# Keep local SQLite development lightweight while using pgvector in PostgreSQL.
EMBEDDING_TYPE = JSON().with_variant(Vector(384), "postgresql")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("canonical_key", name="uq_products_canonical_key"),
        Index("ix_products_category_brand", "category", "brand"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    canonical_key: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="Other")
    description: Mapped[str | None] = mapped_column(Text)
    specifications: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    image_url: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    offers: Mapped[list[Offer]] = relationship(
        back_populates="product", cascade="all, delete-orphan", passive_deletes=True
    )
    reviews: Mapped[list[Review]] = relationship(
        back_populates="product", cascade="all, delete-orphan", passive_deletes=True
    )


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_offers_source_external_id"),
        Index("ix_offers_product_region", "product_id", "region"),
        Index("ix_offers_source_seen", "source", "last_seen_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(240))
    url: Mapped[str | None] = mapped_column(String(1000))
    region: Mapped[str] = mapped_column(String(80), nullable=False, default="Global")
    condition: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    availability: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    product: Mapped[Product] = relationship(back_populates="offers")


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (Index("ix_price_snapshots_product_captured", "product_id", "captured_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    offer_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("offers.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    region: Mapped[str] = mapped_column(String(80), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_reviews_source_external_id"),
        Index("ix_reviews_product_created", "product_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(240))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    region: Mapped[str | None] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 1))
    sentiment: Mapped[str] = mapped_column(String(20), nullable=False, default="neutral")
    issue_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    issue_sentiments: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    product: Mapped[Product] = relationship(back_populates="reviews")


class KnowledgeVector(Base):
    """Review/search corpus; embeddings are optional until a model is configured."""

    __tablename__ = "knowledge_vector"
    __table_args__ = (Index("ix_knowledge_vector_product", "product_id"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )
    review_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(EMBEDDING_TYPE)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (Index("ix_ingestion_jobs_status_created", "status", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    total_count: Mapped[int] = mapped_column(nullable=False, default=0)
    processed_count: Mapped[int] = mapped_column(nullable=False, default=0)
    records_payload: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    feed_url: Mapped[str | None] = mapped_column(String(2000))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
