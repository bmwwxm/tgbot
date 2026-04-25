from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import config
from app.database import Database
from app.routes.user import get_current_user

router = APIRouter(prefix="/api/withdraw", tags=["withdraw"])

_db: Database | None = None


def init_routes(db: Database) -> None:
    global _db
    _db = db


class WithdrawRequest(BaseModel):
    amount: float
    to_address: str


@router.post("/create")
async def create_withdrawal(
    req: WithdrawRequest,
    user: dict = Depends(get_current_user),
):
    assert _db is not None

    min_w_str = await _db.get_setting("min_withdrawal")
    min_withdrawal = float(min_w_str) if min_w_str else config.min_withdrawal
    fee_str = await _db.get_setting("withdrawal_fee")
    fee = float(fee_str) if fee_str else config.withdrawal_fee

    if req.amount < min_withdrawal:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum withdrawal: {min_withdrawal} TON",
        )
    if not req.to_address or len(req.to_address) < 20:
        raise HTTPException(status_code=400, detail="Invalid TON address")

    recent = await _db.count_recent_withdrawals(user["user_id"], seconds=60)
    if recent >= 3:
        raise HTTPException(
            status_code=429, detail="Too many withdrawal requests. Wait 1 minute."
        )

    deducted = await _db.deduct_balance_safe(user["user_id"], req.amount)
    if not deducted:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    wid = await _db.add_withdrawal(
        user_id=user["user_id"],
        amount=req.amount,
        fee=fee,
        to_address=req.to_address,
    )
    return {
        "status": "pending",
        "withdrawal_id": wid,
        "amount": req.amount,
        "fee": fee,
        "net_amount": req.amount - fee,
    }


@router.get("/history")
async def withdrawal_history(user: dict = Depends(get_current_user)):
    assert _db is not None
    withdrawals = await _db.get_user_withdrawals(user["user_id"])
    return {"withdrawals": withdrawals}


@router.get("/info")
async def withdrawal_info(user: dict = Depends(get_current_user)):
    assert _db is not None
    min_w_str = await _db.get_setting("min_withdrawal")
    min_withdrawal = float(min_w_str) if min_w_str else config.min_withdrawal
    fee_str = await _db.get_setting("withdrawal_fee")
    fee = float(fee_str) if fee_str else config.withdrawal_fee
    return {
        "min_withdrawal": min_withdrawal,
        "fee": fee,
        "balance": user["balance"],
    }
