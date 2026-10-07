import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import IngestionJob, KnowledgeVector, Offer, PriceSnapshot, Product, Review, utcnow
from src.database.session import AsyncSessionLocal
from src.services.catalog import find_offer_by_source_id, find_or_create_product
from src.services.review_analysis import analyze_review

logger = logging.getLogger(__name__)


async def process_ingestion_job(job_id: UUID | str) -> None:
    """Consume a queued, validated product-offer batch."""
    parsed_id = UUID(str(job_id))
    async with AsyncSessionLocal() as session:
        job = await session.get(IngestionJob, parsed_id)
        if job is None:
            logger.warning("Ingestion job %s no longer exists", parsed_id)
            return
        job.status = "running"
        job.started_at = utcnow()
        job.error_message = None
        await session.commit()

        try:
            if job.feed_url:
                from src.collectors.json_feed import fetch_json_feed

                records = await fetch_json_feed(job.feed_url)
                job.total_count = len(records)
                await session.commit()
            else:
                records = job.records_payload or []
            for index, record in enumerate(records, start=1):
                await _upsert_offer(session, job.source, record)
                job.processed_count = index
                if index % 25 == 0:
                    await session.commit()
            job.status = "succeeded"
            job.processed_count = len(records)
            job.finished_at = utcnow()
            await session.commit()
        except Exception as exc:
            await session.rollback()
            failed_job = await session.get(IngestionJob, parsed_id)
            if failed_job is not None:
                failed_job.status = "failed"
                failed_job.error_message = str(exc)[:2000]
                failed_job.finished_at = utcnow()
                await session.commit()
            logger.exception("Ingestion job %s failed", parsed_id)


async def _upsert_offer(session: AsyncSession, source: str, record: dict) -> None:
    product = await find_or_create_product(
        session,
        name=record["name"],
        brand=record.get("brand"),
        model=record.get("model"),
        category=record.get("category", "Other"),
        description=record.get("description"),
        specifications=record.get("specifications") or {},
        image_url=record.get("image_url"),
    )
    external_id = record.get("external_id")
    offer = await find_offer_by_source_id(session, source, external_id)
    old_total = offer.price + (offer.shipping_price or Decimal("0")) if offer is not None else None
    old_currency = offer.currency if offer is not None else None

    price = Decimal(str(record["price"]))
    shipping_value = record.get("shipping_price")
    shipping_price = Decimal(str(shipping_value)) if shipping_value is not None else None
    currency = (record.get("currency") or "EUR").upper()
    region = record.get("region") or "Global"
    condition = record.get("condition") or "new"
    availability = bool(record.get("availability", True))
    raw_data = {
        key: value
        for key, value in record.items()
        if key not in {"name", "brand", "model", "category", "description", "specifications"}
    }

    if offer is None:
        new_offer = Offer(
            product_id=product.id,
            source=source,
            external_id=external_id,
            url=record.get("url"),
            region=region,
            condition=condition,
            price=price,
            shipping_price=shipping_price,
            currency=currency,
            availability=availability,
            last_seen_at=utcnow(),
            raw_data=raw_data,
        )
        try:
            async with session.begin_nested():
                session.add(new_offer)
                await session.flush()
            offer = new_offer
        except IntegrityError:
            # Another worker may have inserted the same source item at the same time.
            offer = await find_offer_by_source_id(session, source, external_id)
            if offer is None:
                raise

    offer.product_id = product.id
    offer.url = record.get("url")
    offer.region = region
    offer.condition = condition
    offer.price = price
    offer.shipping_price = shipping_price
    offer.currency = currency
    offer.availability = availability
    offer.last_seen_at = utcnow()
    offer.raw_data = raw_data
    await session.flush()

    new_total = offer.price + (offer.shipping_price or Decimal("0"))
    if old_total is None or old_total != new_total or old_currency != offer.currency:
        session.add(
            PriceSnapshot(
                product_id=product.id,
                offer_id=offer.id,
                source=source,
                region=offer.region,
                price=new_total,
                currency=offer.currency,
            )
        )


async def ingest_reviews(records: list[dict]) -> int:
    """Store review evidence and rule-based issue signals."""
    async with AsyncSessionLocal() as session:
        inserted = 0
        for record in records:
            product = None
            if record.get("product_id"):
                product_id = record["product_id"]
                product = await session.get(Product, UUID(str(product_id)))
            if product is None:
                product_name = record.get("product_name") or "Unmatched product"
                product = await find_or_create_product(
                    session,
                    name=product_name,
                    brand=record.get("brand"),
                    model=record.get("model"),
                    category=record.get("category") or "Other",
                )

            source = record["source"]
            external_id = record.get("external_id")
            review = None
            if external_id:
                review = await session.scalar(
                    select(Review).where(Review.source == source, Review.external_id == external_id)
                )
            analysis = analyze_review(record["content"])
            if review is None:
                review = Review(product_id=product.id, source=source, external_id=external_id)
                session.add(review)
                inserted += 1
            review.product_id = product.id
            review.source_url = record.get("source_url")
            review.region = record.get("region")
            review.content = record["content"]
            review.rating = record.get("rating")
            review.sentiment = str(analysis["sentiment"])
            review.issue_tags = list(analysis["issue_tags"])
            review.issue_sentiments = dict(analysis["issue_sentiments"])
            await session.flush()

            existing_vector = await session.scalar(
                select(KnowledgeVector).where(KnowledgeVector.review_id == review.id)
            )
            if existing_vector is None:
                session.add(
                    KnowledgeVector(
                        product_id=product.id,
                        review_id=review.id,
                        source=source,
                        content=review.content,
                        embedding=None,
                        metadata_json={
                            "sentiment": review.sentiment,
                            "issue_tags": review.issue_tags,
                            "issue_sentiments": review.issue_sentiments,
                            "region": review.region,
                        },
                    )
                )
            else:
                existing_vector.content = review.content
                existing_vector.metadata_json = {
                    "sentiment": review.sentiment,
                    "issue_tags": review.issue_tags,
                    "issue_sentiments": review.issue_sentiments,
                    "region": review.region,
                }
        await session.commit()
        return inserted
