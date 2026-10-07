from datetime import datetime
from decimal import Decimal
import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OfferRecordIn(BaseModel):
    name: str = Field(min_length=2, max_length=300)
    brand: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=160)
    category: str = Field(default="Other", max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    specifications: dict[str, Any] = Field(default_factory=dict)
    image_url: str | None = Field(default=None, max_length=1000)
    external_id: str | None = Field(default=None, max_length=240)
    url: str | None = Field(default=None, max_length=1000)
    region: str = Field(default="Global", max_length=80)
    condition: Literal["new", "used", "refurbished", "open_box"] = "new"
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    shipping_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    availability: bool = True

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        value = value.upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("currency must be a three-letter ISO-style code")
        return value

    @field_validator("name", "brand", "model", "category", "region", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class IngestionJobCreate(BaseModel):
    source: str = Field(min_length=2, max_length=120)
    records: list[OfferRecordIn] = Field(min_length=1, max_length=500)


class IngestionFeedCreate(BaseModel):
    source: str = Field(min_length=2, max_length=120)
    feed_url: str = Field(min_length=10, max_length=2000)


class ReviewRecordIn(BaseModel):
    product_id: UUID | None = None
    product_name: str | None = Field(default=None, min_length=2, max_length=300)
    brand: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=160)
    category: str = Field(default="Other", max_length=100)
    source: str = Field(min_length=2, max_length=120)
    external_id: str | None = Field(default=None, max_length=240)
    source_url: str | None = Field(default=None, max_length=1000)
    region: str | None = Field(default=None, max_length=80)
    content: str = Field(min_length=8, max_length=12000)
    rating: float | None = Field(default=None, ge=0, le=5)


class ReviewBatchCreate(BaseModel):
    reviews: list[ReviewRecordIn] = Field(min_length=1, max_length=500)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str
    status: str
    total_count: int
    processed_count: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ProductOut(BaseModel):
    id: UUID
    name: str
    brand: str | None
    model: str | None
    category: str
    description: str | None
    specifications: dict[str, Any]
    image_url: str | None
    min_price: Decimal | None
    max_price: Decimal | None
    currency: str | None
    offer_count: int
    review_count: int
    top_issues: list[dict[str, Any]] = Field(default_factory=list)


class ProductListOut(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int


class PriceHistoryPoint(BaseModel):
    captured_at: datetime
    price: Decimal
    currency: str
    source: str
    region: str


class ReviewOut(BaseModel):
    id: UUID
    source: str
    source_url: str | None
    region: str | None
    content: str
    rating: Decimal | None
    sentiment: str
    issue_tags: list[str]
    issue_sentiments: dict[str, str] = Field(default_factory=dict)
    created_at: datetime


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["connected"] = "connected"
