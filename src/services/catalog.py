from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Offer, Product
from src.services.normalization import canonical_product_key, identity_similarity, normalize_token


async def find_or_create_product(
    session: AsyncSession,
    *,
    name: str,
    brand: str | None = None,
    model: str | None = None,
    category: str = "Other",
    description: str | None = None,
    specifications: dict[str, Any] | None = None,
    image_url: str | None = None,
) -> Product:
    key = canonical_product_key(name, brand, model)
    product = await session.scalar(select(Product).where(Product.canonical_key == key))

    if product is None:
        candidates = list(
            (
                await session.scalars(
                    select(Product)
                    .where(func.lower(Product.category) == category.casefold())
                    .limit(500)
                )
            ).all()
        )
        # A name-only review export can still resolve when exactly one product in
        # its category has the same normalized display name.
        exact_names = [candidate for candidate in candidates if normalize_token(candidate.name) == normalize_token(name)]
        if len(exact_names) == 1 and (
            not brand or normalize_token(exact_names[0].brand) == normalize_token(brand)
        ):
            product = exact_names[0]

        # Fuzzy linking is deliberately conservative: require the same normalized
        # brand/category and a very high model-name similarity to avoid false merges.
        if product is None and brand and model:
            best_score = 0.0
            for candidate in candidates:
                if normalize_token(candidate.brand) != normalize_token(brand):
                    continue
                score = identity_similarity(
                    name, brand, model, candidate.name, candidate.brand, candidate.model
                )
                if score >= 0.96 and score > best_score:
                    product, best_score = candidate, score

    if product is None:
        new_product = Product(
            canonical_key=key,
            name=name,
            brand=brand,
            model=model,
            category=category or "Other",
            description=description,
            specifications=specifications or {},
            image_url=image_url,
        )
        try:
            async with session.begin_nested():
                session.add(new_product)
                await session.flush()
            product = new_product
        except IntegrityError:
            # Another worker may have inserted this canonical key at the same time.
            product = await session.scalar(select(Product).where(Product.canonical_key == key))
            if product is None:
                raise
    if product is not None:
        # Newer feeds can enrich a sparse catalogue entry without overwriting
        # values that have already been curated.
        product.brand = product.brand or brand
        product.model = product.model or model
        if product.category == "Other" and category:
            product.category = category
        product.description = product.description or description
        product.image_url = product.image_url or image_url
        if specifications:
            merged = dict(product.specifications or {})
            merged.update(specifications)
            product.specifications = merged
    return product


async def find_offer_by_source_id(
    session: AsyncSession, source: str, external_id: str | None
) -> Offer | None:
    if not external_id:
        return None
    return await session.scalar(
        select(Offer).where(Offer.source == source, Offer.external_id == external_id)
    )


async def product_by_id(session: AsyncSession, product_id: UUID) -> Product | None:
    return await session.get(Product, product_id)


def offer_total(offer: Offer) -> Decimal:
    return offer.price + (offer.shipping_price or Decimal("0"))
