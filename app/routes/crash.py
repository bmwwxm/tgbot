"""Crash game — place a bet, watch the multiplier rise, cashout before it crashes."""

import hashlib
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import logging

from app.database import Database
from app.feed_bot import post_to_feed
from app.routes.user import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crash", tags=["crash"])

_db: Database | None = None

MIN_BET = 0.1
MAX_BET = 100.0
HOUSE_EDGE = 0.04


def init_routes(db: Database) -> None:
    global _db
    _db = db


def _generate_crash_point(server_seed: str) -> float:
    """Provably fair crash point using HMAC-SHA256."""
    h = hashlib.sha256(server_seed.encode()).hexdigest()
    # Use first 13 hex chars (52 bits) for high precision
    val = int(h[:13], 16)
    # e = 2^52, crash point formula with house edge
    e = 2**52
    # This gives a distribution where crash at 1.0x happens ~4% of the time (house edge)
    result = (1 - HOUSE_EDGE) * e / (e - val)
    # Cap minimum at 1.0 (instant crash)
    return max(1.0, round(result, 2))


class CrashBetRequest(BaseModel):
    bet: float


class CrashCashoutRequest(BaseModel):
    multiplier: float


@router.post("/bet")
async def place_bet(req: CrashBetRequest, user: dict = Depends(get_current_user)):
    assert _db is not None

    if req.bet < MIN_BET:
        raise HTTPException(status_code=400, detail=f"Minimum bet: {MIN_BET} TON")
    if req.bet > MAX_BET:
        raise HTTPException(status_code=400, detail=f"Maximum bet: {MAX_BET} TON")

    # Check no active crash game
    active = await _db.get_active_crash_game(user["user_id"])
    if active:
        raise HTTPException(status_code=400, detail="Finish current game first")

    server_seed = secrets.token_hex(32)
    seed_hash = hashlib.sha256(server_seed.encode()).hexdigest()
    crash_point = _generate_crash_point(server_seed)

    game_id = await _db.start_crash_game_safe(
        user_id=user["user_id"],
        bet=req.bet,
        crash_point=crash_point,
        server_seed=server_seed,
        seed_hash=seed_hash,
    )
    if not game_id:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    return {
        "game_id": game_id,
        "bet": req.bet,
        "seed_hash": seed_hash,
        "crash_point": crash_point,
    }


@router.post("/cashout")
async def cashout(req: CrashCashoutRequest, user: dict = Depends(get_current_user)):
    assert _db is not None

    result = await _db.crash_cashout_safe(user["user_id"], req.multiplier)
    if result is None:
        raise HTTPException(status_code=400, detail="No active game or already crashed")

    if result.get("too_late"):
        return {
            "status": "crashed",
            "crash_point": result["crash_point"],
            "multiplier": 0,
            "payout": 0,
            "server_seed": result["server_seed"],
        }

    payout = result["payout"]
    profit = payout - result["bet"]

    if profit > 0 and result["cashout_at"] >= 2.0:
        username = user.get("username", "") or user.get("first_name", "") or f"User{user['user_id']}"
        try:
            await post_to_feed(
                "crash_win",
                username=username,
                profit=profit,
                multiplier=result["cashout_at"],
            )
        except Exception:
            pass
        try:
            display = username if len(username) <= 5 else username[:3] + "***" + username[-2:]
            await _db.add_feed_entry(
                event_type="crash_win",
                display_name=display,
                amount=profit,
                profit=profit,
            )
        except Exception:
            pass

    return {
        "status": "cashout",
        "crash_point": result["crash_point"],
        "cashout_at": result["cashout_at"],
        "payout": payout,
        "profit": profit,
        "server_seed": result["server_seed"],
    }


@router.get("/active")
async def active_game(user: dict = Depends(get_current_user)):
    assert _db is not None
    game = await _db.get_active_crash_game(user["user_id"])
    if not game:
        return {"active": False}
    return {
        "active": True,
        "game_id": game["id"],
        "bet": game["bet"],
        "seed_hash": game["seed_hash"],
        "crash_point": game["crash_point"],
        "created_at": game["created_at"],
    }


@router.get("/history")
async def game_history(user: dict = Depends(get_current_user)):
    assert _db is not None
    games = await _db.get_crash_history(user["user_id"])
    return {"games": games}
