import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app, lifespan


@pytest.mark.asyncio
async def test_dashboard_and_catalog_api():
    async with lifespan(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            health = await client.get("/api/health")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"

            created = await client.post(
                "/api/ingestion/jobs",
                json={
                    "source": "test feed",
                    "records": [{
                        "name": "Test laptop 14",
                        "brand": "Example",
                        "model": "T14",
                        "category": "Laptops",
                        "region": "Netherlands",
                        "price": "799.00",
                        "currency": "EUR",
                        "external_id": "test-001",
                    }],
                },
            )
            assert created.status_code == 202
            # ASGI background tasks finish before the test client call returns.
            job = await client.get(f"/api/ingestion/jobs/{created.json()['id']}")
            assert job.json()["status"] == "succeeded"

            products = await client.get("/api/products?q=T14")
            assert products.status_code == 200
            assert products.json()["total"] == 1
            product = products.json()["items"][0]
            assert product["min_price"] == "799.00"

            review_response = await client.post(
                "/api/reviews/batch",
                json={"reviews": [{
                    "product_id": product["id"],
                    "source": "test forum",
                    "external_id": "review-001",
                    "content": "The fan is noisy during games.",
                    "rating": 3.0,
                }]},
            )
            assert review_response.status_code == 201
            insights = await client.get(f"/api/products/{product['id']}/insights")
            assert insights.json()["issues"][0]["tag"] == "cooling_noise"

            blocked_feed = await client.post(
                "/api/ingestion/feed-jobs",
                json={"source": "external", "feed_url": "https://not-allowlisted.example/feed.json"},
            )
            assert blocked_feed.status_code == 403
