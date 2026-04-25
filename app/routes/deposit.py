from fastapi import APIRouter, Depends

from app.config import config
from app.database import Database
from app.routes.user import get_current_user
from app.services.ton import ton_service

router = APIRouter(prefix="/api/deposit", tags=["deposit"])

_db: Database | None = None


def init_routes(db: Database) -> None:
    global _db
    _db = db


@router.get("/info")
async def deposit_info(user: dict = Depends(get_current_user)):
    assert _db is not None
    min_dep_str = await _db.get_setting("min_deposit")
    min_deposit = float(min_dep_str) if min_dep_str else config.min_deposit

    profit_str = await _db.get_setting("profit_percent")
    profit_pct = float(profit_str) if profit_str else config.profit_percent

    maturity_str = await _db.get_setting("deposit_maturity_seconds")
    maturity = int(float(maturity_str)) if maturity_str else config.deposit_maturity_seconds

    return {
        "wallet_address": ton_service.wallet_address,
        "deposit_comment": user["deposit_comment"],
        "min_deposit": min_deposit,
        "profit_percent": profit_pct,
        "maturity_hours": maturity / 3600,
    }


@router.get("/history")
async def deposit_history(user: dict = Depends(get_current_user)):
    assert _db is not None
    deposits = await _db.get_user_deposits(user["user_id"])
    return {"deposits": deposits}


@router.get("/active")
async def active_deposits(user: dict = Depends(get_current_user)):
    assert _db is not None
    deposits = await _db.get_user_deposits(user["user_id"])
    active = [d for d in deposits if d["status"] == "pending"]
    return {"active_deposits": active}
