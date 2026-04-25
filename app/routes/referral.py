from fastapi import APIRouter, Depends

from app.config import config
from app.database import Database
from app.routes.user import get_current_user

router = APIRouter(prefix="/api/referral", tags=["referral"])

_db: Database | None = None


def init_routes(db: Database) -> None:
    global _db
    _db = db


@router.get("/info")
async def referral_info(user: dict = Depends(get_current_user)):
    assert _db is not None
    ref_pct_str = await _db.get_setting("referral_percent")
    ref_pct = float(ref_pct_str) if ref_pct_str else config.referral_percent
    referrals = await _db.get_referrals(user["user_id"])
    return {
        "referral_link": f"https://t.me/{await _get_bot_username()}?startapp={user['user_id']}",
        "referral_percent": ref_pct,
        "referral_earnings": user["referral_earnings"],
        "referral_count": len(referrals),
        "referrals": referrals,
    }


async def _get_bot_username() -> str:
    assert _db is not None
    cached = await _db.get_setting("bot_username")
    if cached:
        return cached
    return "your_bot"
