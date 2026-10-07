from decimal import Decimal

from sqlalchemy import func, select

from src.database.models import KnowledgeVector, Product, Review
from src.database.session import AsyncSessionLocal
from src.services.catalog import find_or_create_product
from src.services.ingestion import _upsert_offer
from src.services.review_analysis import analyze_review


DEMO_OFFERS = [
    {
        "name": "GeForce RTX 4070 SUPER 12GB", "brand": "NVIDIA", "model": "RTX 4070 SUPER",
        "category": "Graphics cards", "description": "Demo listing for a high-performance graphics card.",
        "specifications": {"memory": "12 GB GDDR6X", "interface": "PCIe 4.0"},
        "external_id": "demo-gpu-nl", "region": "Netherlands", "condition": "new",
        "price": "629.00", "currency": "EUR", "url": "https://example.invalid/demo/gpu-nl",
    },
    {
        "name": "GeForce RTX 4070 SUPER 12GB", "brand": "NVIDIA", "model": "RTX 4070 SUPER",
        "category": "Graphics cards", "specifications": {"memory": "12 GB GDDR6X"},
        "external_id": "demo-gpu-de", "region": "Germany", "condition": "new",
        "price": "599.00", "currency": "EUR", "url": "https://example.invalid/demo/gpu-de",
    },
    {
        "name": "GeForce RTX 4070 SUPER 12GB", "brand": "NVIDIA", "model": "RTX 4070 SUPER",
        "category": "Graphics cards", "specifications": {"memory": "12 GB GDDR6X"},
        "external_id": "demo-gpu-used", "region": "Netherlands", "condition": "used",
        "price": "495.00", "currency": "EUR", "availability": True,
        "url": "https://example.invalid/demo/gpu-used",
    },
    {
        "name": "MacBook Air 15-inch M3", "brand": "Apple", "model": "MacBook Air 15 M3",
        "category": "Laptops", "description": "Lightweight laptop, demo catalogue record.",
        "specifications": {"display": "15.3 inch", "memory": "16 GB", "storage": "512 GB"},
        "external_id": "demo-macbook-nl", "region": "Netherlands", "condition": "new",
        "price": "1599.00", "currency": "EUR", "url": "https://example.invalid/demo/macbook-nl",
    },
    {
        "name": "MacBook Air 15-inch M3", "brand": "Apple", "model": "MacBook Air 15 M3",
        "category": "Laptops", "specifications": {"memory": "16 GB", "storage": "512 GB"},
        "external_id": "demo-macbook-de", "region": "Germany", "condition": "new",
        "price": "1549.00", "currency": "EUR", "url": "https://example.invalid/demo/macbook-de",
    },
    {
        "name": "Galaxy S24 Ultra 256GB", "brand": "Samsung", "model": "Galaxy S24 Ultra",
        "category": "Smartphones", "specifications": {"storage": "256 GB", "display": "6.8 inch AMOLED"},
        "external_id": "demo-galaxy-nl", "region": "Netherlands", "condition": "new",
        "price": "999.00", "currency": "EUR", "url": "https://example.invalid/demo/galaxy-nl",
    },
    {
        "name": "WH-1000XM5 Wireless Headphones", "brand": "Sony", "model": "WH-1000XM5",
        "category": "Audio", "specifications": {"type": "Over-ear", "noise_cancelling": True},
        "external_id": "demo-headphones-nl", "region": "Netherlands", "condition": "new",
        "price": "329.00", "currency": "EUR", "url": "https://example.invalid/demo/headphones-nl",
    },
    {
        "name": "WH-1000XM5 Wireless Headphones", "brand": "Sony", "model": "WH-1000XM5",
        "category": "Audio", "specifications": {"type": "Over-ear"},
        "external_id": "demo-headphones-de", "region": "Germany", "condition": "refurbished",
        "price": "249.00", "currency": "EUR", "url": "https://example.invalid/demo/headphones-de",
    },
    {
        "name": "ThinkPad T14 Gen 4", "brand": "Lenovo", "model": "ThinkPad T14 Gen 4",
        "category": "Laptops", "specifications": {"display": "14 inch", "memory": "32 GB"},
        "external_id": "demo-thinkpad-nl", "region": "Netherlands", "condition": "new",
        "price": "1349.00", "currency": "EUR", "url": "https://example.invalid/demo/thinkpad-nl",
    },
    {
        "name": "DualSense Wireless Controller", "brand": "Sony", "model": "DualSense",
        "category": "Gaming", "specifications": {"connectivity": "Bluetooth / USB-C"},
        "external_id": "demo-controller-nl", "region": "Netherlands", "condition": "new",
        "price": "69.99", "currency": "EUR", "url": "https://example.invalid/demo/controller-nl",
    },
]

# source id, source, product identity (name, brand, model, category), text, rating, region
DEMO_REVIEWS = [
    ("demo-review-1", "4PDA demo", ("GeForce RTX 4070 SUPER 12GB", "NVIDIA", "RTX 4070 SUPER", "Graphics cards"), "Cooling is quiet in normal use, but the fan gets noisy under sustained load.", 3.5, "Netherlands"),
    ("demo-review-2", "Community demo", ("GeForce RTX 4070 SUPER 12GB", "NVIDIA", "RTX 4070 SUPER", "Graphics cards"), "Excellent performance and no overheating in my compact case.", 5.0, "Germany"),
    ("demo-review-3", "Community demo", ("MacBook Air 15-inch M3", "Apple", "MacBook Air 15 M3", "Laptops"), "Great battery life and a quiet design for travel.", 5.0, "Netherlands"),
    ("demo-review-4", "Forum demo", ("MacBook Air 15-inch M3", "Apple", "MacBook Air 15 M3", "Laptops"), "The display is lovely, but the battery drains faster than expected on video calls.", 3.0, "Germany"),
    ("demo-review-5", "Forum demo", ("Galaxy S24 Ultra 256GB", "Samsung", "Galaxy S24 Ultra", "Smartphones"), "Excellent screen. The phone gets hot while gaming.", 3.5, "Netherlands"),
    ("demo-review-6", "Community demo", ("WH-1000XM5 Wireless Headphones", "Sony", "WH-1000XM5", "Audio"), "Comfortable and reliable; recommend them for commuting.", 5.0, "Netherlands"),
    ("demo-review-7", "Forum demo", ("WH-1000XM5 Wireless Headphones", "Sony", "WH-1000XM5", "Audio"), "The headband started cracking after a few months.", 2.0, "Germany"),
    ("demo-review-8", "Community demo", ("ThinkPad T14 Gen 4", "Lenovo", "ThinkPad T14 Gen 4", "Laptops"), "Fast, sturdy, and the keyboard is excellent.", 4.5, "Netherlands"),
]


async def seed_demo_data() -> None:
    async with AsyncSessionLocal() as session:
        product_count = await session.scalar(select(func.count()).select_from(Product))
        if product_count:
            return

        for offer in DEMO_OFFERS:
            await _upsert_offer(session, "Demo feed", offer)

        for external_id, source, identity, content, rating, region in DEMO_REVIEWS:
            name, brand, model, category = identity
            product = await find_or_create_product(
                session, name=name, brand=brand, model=model, category=category
            )
            analysis = analyze_review(content)
            review = Review(
                product_id=product.id,
                source=source,
                external_id=external_id,
                region=region,
                content=content,
                rating=Decimal(str(rating)),
                sentiment=analysis["sentiment"],
                issue_tags=analysis["issue_tags"],
                issue_sentiments=analysis["issue_sentiments"],
            )
            session.add(review)
            await session.flush()
            session.add(
                KnowledgeVector(
                    product_id=product.id,
                    review_id=review.id,
                    source=source,
                    content=content,
                    embedding=None,
                    metadata_json={
                        "sentiment": review.sentiment,
                        "issue_tags": review.issue_tags,
                        "issue_sentiments": review.issue_sentiments,
                    },
                )
            )
        await session.commit()
