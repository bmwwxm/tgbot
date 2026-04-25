from fastapi import APIRouter

from app.database import Database

router = APIRouter(prefix="/api/feed", tags=["feed"])

_db: Database | None = None


def init_routes(db: Database) -> None:
    global _db
    _db = db


@router.get("/recent")
async def recent_feed(limit: int = 20):
    """Public endpoint — no auth required."""
    assert _db is not None
    if limit > 50:
        limit = 50
    entries = await _db.get_feed(limit=limit)
    return {"feed": entries}
