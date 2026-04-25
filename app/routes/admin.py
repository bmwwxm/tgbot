from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from app.config import config
from app.database import Database
from app.routes.user import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])

_db: Database | None = None


def init_routes(db: Database) -> None:
    global _db
    _db = db


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user["is_admin"] and user["user_id"] not in config.admin_ids:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── Statistics ──────────────────────────────────────────

@router.get("/stats")
async def stats(admin: dict = Depends(require_admin)):
    assert _db is not None
    from app.services.ton import ton_service

    user_count = await _db.get_user_count()
    dep_stats = await _db.get_deposits_stats()
    wd_stats = await _db.get_withdrawals_stats()
    wallet_balance = await ton_service.get_wallet_balance()

    return {
        "total_users": user_count,
        "total_deposits": dep_stats.get("total_count", 0),
        "total_deposit_amount": dep_stats.get("total_amount", 0),
        "total_profit_paid": dep_stats.get("total_profit", 0),
        "pending_deposits": dep_stats.get("pending_count", 0),
        "total_withdrawals": wd_stats.get("total_count", 0),
        "total_withdrawn": wd_stats.get("total_sent", 0),
        "wallet_balance": wallet_balance,
        "wallet_address": ton_service.wallet_address,
    }


# ── Users ───────────────────────────────────────────────

@router.get("/users")
async def list_users(
    limit: int = 50,
    offset: int = 0,
    admin: dict = Depends(require_admin),
):
    assert _db is not None
    users = await _db.get_all_users(limit=limit, offset=offset)
    total = await _db.get_user_count()
    return {"users": users, "total": total}


class BlockRequest(BaseModel):
    user_id: int
    blocked: bool


@router.post("/block")
async def block_user(req: BlockRequest, admin: dict = Depends(require_admin)):
    assert _db is not None
    user = await _db.get_user(req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await _db.update_user(req.user_id, is_blocked=1 if req.blocked else 0)
    return {"status": "ok", "user_id": req.user_id, "blocked": req.blocked}


class AdminGrantRequest(BaseModel):
    user_id: int
    is_admin: bool


@router.post("/grant")
async def grant_admin(req: AdminGrantRequest, admin: dict = Depends(require_admin)):
    assert _db is not None
    user = await _db.get_user(req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await _db.update_user(req.user_id, is_admin=1 if req.is_admin else 0)
    return {"status": "ok", "user_id": req.user_id, "is_admin": req.is_admin}


# ── Balance adjustment ──────────────────────────────────

class BalanceAdjust(BaseModel):
    user_id: int
    amount: float
    reason: str = ""


@router.post("/balance")
async def adjust_balance(req: BalanceAdjust, admin: dict = Depends(require_admin)):
    assert _db is not None
    user = await _db.get_user(req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if req.amount < 0:
        ok = await _db.deduct_balance_safe(req.user_id, abs(req.amount))
        if not ok:
            raise HTTPException(status_code=400, detail="Insufficient balance for deduction")
    else:
        await _db.add_balance(req.user_id, req.amount)
    updated = await _db.get_user(req.user_id)
    return {
        "status": "ok",
        "user_id": req.user_id,
        "new_balance": updated["balance"] if updated else 0,
    }


# ── Settings ────────────────────────────────────────────

EDITABLE_SETTINGS = [
    "min_deposit",
    "profit_percent",
    "deposit_maturity_seconds",
    "referral_percent",
    "min_withdrawal",
    "withdrawal_fee",
]


@router.get("/settings")
async def get_settings(admin: dict = Depends(require_admin)):
    assert _db is not None
    db_settings = await _db.get_all_settings()
    result = {}
    for key in EDITABLE_SETTINGS:
        if key in db_settings:
            result[key] = db_settings[key]
        else:
            result[key] = str(getattr(config, key))
    return result


class UpdateSettings(BaseModel):
    settings: dict[str, str]


@router.post("/settings")
async def update_settings(req: UpdateSettings, admin: dict = Depends(require_admin)):
    assert _db is not None
    updated = {}
    for key, value in req.settings.items():
        if key not in EDITABLE_SETTINGS:
            continue
        try:
            float(value)
        except ValueError:
            continue
        await _db.set_setting(key, value)
        updated[key] = value
    return {"status": "ok", "updated": updated}


# ── Broadcast ───────────────────────────────────────────

class BroadcastRequest(BaseModel):
    message: str


@router.post("/broadcast")
async def broadcast(req: BroadcastRequest, admin: dict = Depends(require_admin)):
    assert _db is not None
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")
    user_ids = await _db.get_active_user_ids()
    return {
        "status": "queued",
        "message": req.message,
        "target_users": len(user_ids),
        "user_ids": user_ids,
    }


# ── User detail ─────────────────────────────────────────

@router.get("/user/{user_id}")
async def user_detail(user_id: int, admin: dict = Depends(require_admin)):
    assert _db is not None
    user = await _db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    deposits = await _db.get_user_deposits(user_id)
    withdrawals = await _db.get_user_withdrawals(user_id)
    referrals = await _db.get_referrals(user_id)
    return {
        "user": user,
        "deposits": deposits,
        "withdrawals": withdrawals,
        "referrals": referrals,
    }


# ── Fake Feed ───────────────────────────────────────────

class FakeFeedRequest(BaseModel):
    event_type: str = "deposit"
    display_name: str = ""
    amount: float = 10.0
    profit: float = 0.0
    maturity_hours: float = 10.0


@router.post("/fake-feed")
async def create_fake_feed(req: FakeFeedRequest, admin: dict = Depends(require_admin)):
    assert _db is not None
    import time

    allowed_types = {"deposit", "payout", "withdrawal"}
    if req.event_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Type must be one of: {allowed_types}")
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    matures_at = time.time() + req.maturity_hours * 3600 if req.event_type == "deposit" else 0.0

    fid = await _db.add_feed_entry(
        event_type=req.event_type,
        display_name=req.display_name or _random_name(),
        amount=req.amount,
        profit=req.profit,
        matures_at=matures_at,
        is_fake=True,
    )
    return {"status": "ok", "feed_id": fid}


def _random_name() -> str:
    import random
    names = [
        "Alex", "Maria", "Dmitry", "Anna", "Ivan", "Elena", "Sergey", "Olga",
        "Maxim", "Natalia", "Andrey", "Ekaterina", "Pavel", "Tatyana", "Viktor",
        "John", "Emma", "James", "Sophie", "Michael", "Lisa", "David", "Sarah",
    ]
    name = random.choice(names)
    suffix = random.randint(10, 99)
    return f"{name}***{suffix}"
