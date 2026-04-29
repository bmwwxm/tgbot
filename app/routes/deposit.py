import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import config
from app.database import Database
from app.feed_bot import post_to_feed
from app.routes.user import get_current_user
from app.services.ton import ton_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/deposit", tags=["deposit"])

_db: Database | None = None
_bot_notify = None


def init_routes(db: Database, bot_notify_func=None) -> None:
    global _db, _bot_notify
    _db = db
    _bot_notify = bot_notify_func


def _mask_name(name: str) -> str:
    if not name or len(name) < 3:
        return "User***"
    return name[:3] + "***" + name[-2:]


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
        "balance": user["balance"],
    }


class InvestRequest(BaseModel):
    amount: float


@router.post("/invest")
async def create_investment(req: InvestRequest, user: dict = Depends(get_current_user)):
    """Create an investment deposit from user's balance."""
    assert _db is not None

    min_dep_str = await _db.get_setting("min_deposit")
    min_deposit = float(min_dep_str) if min_dep_str else config.min_deposit

    if req.amount < min_deposit:
        raise HTTPException(status_code=400, detail=f"Minimum investment: {min_deposit} TON")

    ok = await _db.deduct_balance_safe(user["user_id"], req.amount)
    if not ok:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    maturity_str = await _db.get_setting("deposit_maturity_seconds")
    maturity = int(float(maturity_str)) if maturity_str else config.deposit_maturity_seconds

    profit_str = await _db.get_setting("profit_percent")
    profit_pct = float(profit_str) if profit_str else config.profit_percent

    deposit_id = await _db.add_deposit(
        user_id=user["user_id"],
        amount=req.amount,
        tx_hash=f"invest_{user['user_id']}_{int(time.time())}",
        maturity_seconds=maturity,
    )

    expected_profit = req.amount * (profit_pct / 100.0)
    maturity_h = maturity / 3600

    name = _mask_name(user.get("first_name", ""))
    await _db.add_feed_entry(
        event_type="deposit",
        display_name=name,
        amount=req.amount,
        profit=expected_profit,
        matures_at=time.time() + maturity,
    )

    if _bot_notify:
        try:
            await _bot_notify(
                user["user_id"], "investment_created",
                amount=req.amount, profit=expected_profit, hours=maturity_h,
            )
        except Exception as e:
            logger.warning("Notify error: %s", e)

    try:
        await post_to_feed(
            "deposit_received",
            amount=req.amount,
            profit=expected_profit,
            hours=maturity_h,
        )
    except Exception as e:
        logger.warning("Feed post error: %s", e)

    return {
        "status": "ok",
        "deposit_id": deposit_id,
        "amount": req.amount,
        "profit": expected_profit,
        "maturity_hours": maturity_h,
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
