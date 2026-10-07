from __future__ import annotations

from collections import Counter
from decimal import Decimal
from uuid import UUID

import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    HealthOut,
    IngestionFeedCreate,
    IngestionJobCreate,
    JobOut,
    ProductListOut,
    ProductOut,
    ReviewBatchCreate,
)
from src.config import settings
from src.database.models import IngestionJob, Offer, PriceSnapshot, Product, Review
from src.database.session import get_session
from src.collectors.json_feed import validate_feed_url
from src.services.catalog import offer_total
from src.services.ingestion import ingest_reviews, process_ingestion_job
from src.services.review_analysis import issue_summary

router = APIRouter(prefix="/api")


def require_ingestion_key(
    x_ingestion_key: str | None = Header(default=None, alias="X-Ingestion-Key"),
) -> None:
    if settings.ingestion_api_key and not secrets.compare_digest(
        x_ingestion_key or "", settings.ingestion_api_key
    ):
        raise HTTPException(status_code=401, detail="A valid X-Ingestion-Key is required")


def _schedule_ingestion(job_id: UUID, background_tasks: BackgroundTasks) -> None:
    if settings.use_celery:
        from src.tasks import process_ingestion_job as celery_ingest

        celery_ingest.delay(str(job_id))
    else:
        background_tasks.add_task(process_ingestion_job, str(job_id))


@router.get("/health", response_model=HealthOut, tags=["system"])
async def health(session: AsyncSession = Depends(get_session)) -> HealthOut:
    await session.execute(text("SELECT 1"))
    return HealthOut()


@router.get("/dashboard", tags=["analytics"])
async def dashboard(session: AsyncSession = Depends(get_session)) -> dict:
    product_count = await session.scalar(select(func.count(Product.id))) or 0
    offer_count = await session.scalar(select(func.count(Offer.id))) or 0
    source_count = await session.scalar(select(func.count(func.distinct(Offer.source)))) or 0
    region_count = await session.scalar(select(func.count(func.distinct(Offer.region)))) or 0
    review_count = await session.scalar(select(func.count(Review.id))) or 0
    active_jobs = await session.scalar(
        select(func.count(IngestionJob.id)).where(IngestionJob.status.in_(["queued", "running"]))
    ) or 0

    category_rows = (
        await session.execute(
            select(Product.category, func.count(Product.id).label("count"))
            .group_by(Product.category)
            .order_by(func.count(Product.id).desc())
        )
    ).all()
    reviews = list((await session.scalars(select(Review).order_by(Review.created_at.desc()).limit(250))).all())
    issues = issue_summary(reviews)
    recent_jobs = list(
        (
            await session.scalars(select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(5))
        ).all()
    )
    return {
        "metrics": {
            "products": product_count,
            "offers": offer_count,
            "sources": source_count,
            "regions": region_count,
            "reviews": review_count,
            "active_jobs": active_jobs,
        },
        "categories": [{"name": row.category, "count": row.count} for row in category_rows],
        "top_issues": issues[:5],
        "recent_jobs": [JobOut.model_validate(job).model_dump(mode="json") for job in recent_jobs],
    }


@router.get("/catalog/categories", tags=["catalog"])
async def categories(session: AsyncSession = Depends(get_session)) -> list[str]:
    result = await session.scalars(select(Product.category).distinct().order_by(Product.category))
    return list(result.all())


@router.get("/products", response_model=ProductListOut, tags=["catalog"])
async def list_products(
    q: str | None = Query(default=None, max_length=160),
    category: str | None = Query(default=None, max_length=100),
    region: str | None = Query(default=None, max_length=80),
    source: str | None = Query(default=None, max_length=120),
    condition: str | None = Query(default=None, max_length=32),
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    sort: str = Query(default="name", pattern="^(name|price_asc|price_desc|newest)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> ProductListOut:
    conditions = []
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(
            or_(Product.name.ilike(pattern), Product.brand.ilike(pattern), Product.model.ilike(pattern))
        )
    if category:
        conditions.append(Product.category.ilike(category))
    if region:
        conditions.append(Product.offers.any(Offer.region.ilike(region)))
    if source:
        conditions.append(Product.offers.any(Offer.source.ilike(source)))
    if condition:
        conditions.append(Product.offers.any(Offer.condition == condition))
    minimum_offer_price = (
        select(func.min(Offer.price + func.coalesce(Offer.shipping_price, 0)))
        .where(Offer.product_id == Product.id, Offer.availability.is_(True))
        .correlate(Product)
        .scalar_subquery()
    )
    if min_price is not None:
        conditions.append(minimum_offer_price >= min_price)
    if max_price is not None:
        conditions.append(minimum_offer_price <= max_price)

    total = await session.scalar(select(func.count(Product.id)).where(*conditions)) or 0
    query = (
        select(Product)
        .options(selectinload(Product.offers), selectinload(Product.reviews))
        .where(*conditions)
    )
    if sort == "price_asc":
        query = query.order_by(minimum_offer_price.asc().nulls_last(), Product.name.asc())
    elif sort == "price_desc":
        query = query.order_by(minimum_offer_price.desc().nulls_last(), Product.name.asc())
    elif sort == "newest":
        query = query.order_by(Product.created_at.desc())
    else:
        query = query.order_by(Product.name.asc())
    products = list(
        (
            await session.scalars(query.offset((page - 1) * page_size).limit(page_size))
        ).unique().all()
    )
    return ProductListOut(
        items=[_product_summary(product, region=region, condition=condition) for product in products],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/products/{product_id}", tags=["catalog"])
async def product_detail(
    product_id: UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    product = await session.scalar(
        select(Product)
        .options(selectinload(Product.offers), selectinload(Product.reviews))
        .where(Product.id == product_id)
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    offers = sorted(product.offers, key=lambda offer: (not offer.availability, offer_total(offer)))
    reviews = sorted(product.reviews, key=lambda review: review.created_at, reverse=True)
    return {
        "product": _product_summary(product).model_dump(mode="json"),
        "offers": [_offer_json(offer) for offer in offers],
        "reviews": [_review_json(review) for review in reviews[:8]],
    }


@router.get("/products/{product_id}/history", tags=["analytics"])
async def product_price_history(
    product_id: UUID,
    limit: int = Query(default=60, ge=1, le=250),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    exists = await session.get(Product, product_id)
    if exists is None:
        raise HTTPException(status_code=404, detail="Product not found")
    points = list(
        (
            await session.scalars(
                select(PriceSnapshot)
                .where(PriceSnapshot.product_id == product_id)
                .order_by(PriceSnapshot.captured_at.desc())
                .limit(limit)
            )
        ).all()
    )
    points.reverse()
    return [
        {
            "captured_at": point.captured_at.isoformat(),
            "price": float(point.price),
            "currency": point.currency,
            "source": point.source,
            "region": point.region,
        }
        for point in points
    ]


@router.get("/products/{product_id}/insights", tags=["analytics"])
async def product_insights(
    product_id: UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    reviews = list(
        (
            await session.scalars(
                select(Review).where(Review.product_id == product_id).order_by(Review.created_at.desc())
            )
        ).all()
    )
    issue_data = issue_summary(reviews)
    return {
        "product_id": str(product_id),
        "review_count": len(reviews),
        "negative_review_share": round(
            sum(review.sentiment == "negative" for review in reviews) / len(reviews), 3
        ) if reviews else 0,
        "issues": issue_data,
        "sentiment": dict(Counter(review.sentiment for review in reviews)),
    }


@router.get("/insights", tags=["analytics"])
async def global_insights(session: AsyncSession = Depends(get_session)) -> dict:
    reviews = list((await session.scalars(select(Review).order_by(Review.created_at.desc()).limit(1000))).all())
    products = await session.scalar(select(func.count(Product.id))) or 0
    return {
        "review_count": len(reviews),
        "product_count": products,
        "issues": issue_summary(reviews),
        "sentiment": dict(Counter(review.sentiment for review in reviews)),
        "method": "Explainable keyword signals; examples link to source reviews. Not a verified defect rate.",
    }


@router.post("/ingestion/jobs", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED, tags=["ingestion"])
async def create_ingestion_job(
    payload: IngestionJobCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    _auth: None = Depends(require_ingestion_key),
) -> JobOut:
    job = IngestionJob(
        source=payload.source.strip(),
        status="queued",
        total_count=len(payload.records),
        records_payload=[record.model_dump(mode="json") for record in payload.records],
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    try:
        _schedule_ingestion(job.id, background_tasks)
    except Exception as exc:
        job.status = "failed"
        job.error_message = f"Queue unavailable: {exc}"[:2000]
        await session.commit()
        raise HTTPException(status_code=503, detail="The ingestion queue is unavailable") from exc
    return JobOut.model_validate(job)


@router.post("/ingestion/feed-jobs", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED, tags=["ingestion"])
async def create_feed_job(
    payload: IngestionFeedCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    _auth: None = Depends(require_ingestion_key),
) -> JobOut:
    try:
        validate_feed_url(payload.feed_url)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    job = IngestionJob(
        source=payload.source.strip(),
        feed_url=payload.feed_url,
        status="queued",
        total_count=0,
        records_payload=[],
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    try:
        _schedule_ingestion(job.id, background_tasks)
    except Exception as exc:
        job.status = "failed"
        job.error_message = f"Queue unavailable: {exc}"[:2000]
        await session.commit()
        raise HTTPException(status_code=503, detail="The ingestion queue is unavailable") from exc
    return JobOut.model_validate(job)


@router.get("/ingestion/jobs", response_model=list[JobOut], tags=["ingestion"])
async def list_ingestion_jobs(
    limit: int = Query(default=20, ge=1, le=100), session: AsyncSession = Depends(get_session)
) -> list[JobOut]:
    jobs = list(
        (
            await session.scalars(select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(limit))
        ).all()
    )
    return [JobOut.model_validate(job) for job in jobs]


@router.get("/ingestion/jobs/{job_id}", response_model=JobOut, tags=["ingestion"])
async def ingestion_job_status(job_id: UUID, session: AsyncSession = Depends(get_session)) -> JobOut:
    job = await session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return JobOut.model_validate(job)


@router.post("/reviews/batch", status_code=status.HTTP_201_CREATED, tags=["community"])
async def create_reviews(
    payload: ReviewBatchCreate,
    _auth: None = Depends(require_ingestion_key),
) -> dict:
    inserted = await ingest_reviews([review.model_dump(mode="json") for review in payload.reviews])
    return {"received": len(payload.reviews), "created": inserted, "status": "processed"}


@router.get("/sources", tags=["ingestion"])
async def list_sources(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (
        await session.execute(
            select(Offer.source, func.count(Offer.id).label("offer_count"), func.count(func.distinct(Offer.region)).label("regions"))
            .group_by(Offer.source)
            .order_by(func.count(Offer.id).desc())
        )
    ).all()
    return [
        {"name": row.source, "offer_count": row.offer_count, "regions": row.regions, "mode": "authorized feed/import"}
        for row in rows
    ]


def _product_summary(
    product: Product, *, region: str | None = None, condition: str | None = None
) -> ProductOut:
    offers = [offer for offer in product.offers if offer.availability]
    if region:
        offers = [offer for offer in offers if offer.region.casefold() == region.casefold()]
    if condition:
        offers = [offer for offer in offers if offer.condition == condition]
    offers.sort(key=offer_total)
    reviews = product.reviews
    return ProductOut(
        id=product.id,
        name=product.name,
        brand=product.brand,
        model=product.model,
        category=product.category,
        description=product.description,
        specifications=product.specifications or {},
        image_url=product.image_url,
        min_price=offer_total(offers[0]) if offers else None,
        max_price=offer_total(offers[-1]) if offers else None,
        currency=offers[0].currency if offers else None,
        offer_count=len(offers),
        review_count=len(reviews),
        top_issues=issue_summary(reviews)[:2],
    )


def _offer_json(offer: Offer) -> dict:
    return {
        "id": str(offer.id),
        "source": offer.source,
        "external_id": offer.external_id,
        "url": offer.url,
        "region": offer.region,
        "condition": offer.condition,
        "price": float(offer.price),
        "shipping_price": float(offer.shipping_price) if offer.shipping_price is not None else None,
        "total_price": float(offer_total(offer)),
        "currency": offer.currency,
        "availability": offer.availability,
        "last_seen_at": offer.last_seen_at.isoformat(),
    }


def _review_json(review: Review) -> dict:
    return {
        "id": str(review.id),
        "source": review.source,
        "source_url": review.source_url,
        "region": review.region,
        "content": review.content,
        "rating": float(review.rating) if review.rating is not None else None,
        "sentiment": review.sentiment,
        "issue_tags": review.issue_tags or [],
        "issue_sentiments": review.issue_sentiments or {},
        "created_at": review.created_at.isoformat(),
    }
