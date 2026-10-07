from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from src.api.routes import router
from src.config import settings
from src.database.models import Base
from src.database.session import engine

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Prepare database resources before serving requests and release them on shutdown."""
    async with engine.begin() as connection:
        if settings.database_url.startswith("postgresql"):
            # The pgvector extension is supplied by the pgvector/pgvector Postgres image.
            await connection.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.create_all)

    if settings.seed_demo_data:
        from src.seed import seed_demo_data

        await seed_demo_data()

    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description=(
        "Electronics catalog, regional offer tracking, ingestion jobs and explainable "
        "community issue signals. Connect only authorized feeds and APIs."
    ),
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(WEB_DIR / "favicon.svg", media_type="image/svg+xml")
