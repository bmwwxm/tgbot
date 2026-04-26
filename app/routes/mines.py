"""Mines game — bet TON, reveal safe cells, cashout or hit a mine."""

import hashlib
import json
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import logging

from app.database import Database
from app.feed_bot import post_to_feed
from app.routes.user import get_current_user

logger = logging.getLogger(__name__)

MIN_WIN_MULTIPLIER = 2.0  # Only post wins with 2x+ multiplier to feed

router = APIRouter(prefix="/api/mines", tags=["mines"])

_db: Database | None = None

GRID_SIZE = 25  # 5x5
MIN_BET = 0.1
MAX_MINES = 24
MIN_MINES = 1


def init_routes(db: Database) -> None:
    global _db
    _db = db


def _generate_field(server_seed: str, client_seed: str, nonce: int, mines_count: int) -> list[int]:
    """Provably fair mine placement using HMAC-SHA256."""
    combined = f"{server_seed}:{client_seed}:{nonce}"
    hash_hex = hashlib.sha256(combined.encode()).hexdigest()

    mine_positions: list[int] = []
    idx = 0
    while len(mine_positions) < mines_count and idx < len(hash_hex) - 3:
        chunk = hash_hex[idx:idx + 4]
        val = int(chunk, 16) % GRID_SIZE
        if val not in mine_positions:
            mine_positions.append(val)
        idx += 1
        if idx >= len(hash_hex) - 3:
            hash_hex = hashlib.sha256(hash_hex.encode()).hexdigest()
            idx = 0

    return sorted(mine_positions)


def _calc_multiplier(mines_count: int, revealed_count: int) -> float:
    """Calculate multiplier based on probability.
    Each reveal reduces safe cells. Multiplier = house_edge / probability_of_sequence."""
    if revealed_count == 0:
        return 1.0
    safe = GRID_SIZE - mines_count
    house_edge = 0.97  # 3% house edge
    prob = 1.0
    for i in range(revealed_count):
        prob *= (safe - i) / (GRID_SIZE - i)
    if prob <= 0:
        return 0.0
    return round(house_edge / prob, 2)


class StartGameRequest(BaseModel):
    bet: float
    mines_count: int = 5


@router.post("/start")
async def start_game(req: StartGameRequest, user: dict = Depends(get_current_user)):
    assert _db is not None

    existing = await _db.get_active_mines_game(user["user_id"])
    if existing:
        raise HTTPException(status_code=400, detail="Finish current game first")

    if req.bet < MIN_BET:
        raise HTTPException(status_code=400, detail=f"Minimum bet: {MIN_BET} TON")
    if req.mines_count < MIN_MINES or req.mines_count > MAX_MINES:
        raise HTTPException(status_code=400, detail=f"Mines: {MIN_MINES}-{MAX_MINES}")

    deducted = await _db.deduct_balance_safe(user["user_id"], req.bet)
    if not deducted:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    server_seed = secrets.token_hex(32)
    client_seed = secrets.token_hex(16)
    nonce = int(time.time())

    mine_positions = _generate_field(server_seed, client_seed, nonce, req.mines_count)
    field_json = json.dumps(mine_positions)

    server_seed_hash = hashlib.sha256(server_seed.encode()).hexdigest()

    game_id = await _db.create_mines_game(
        user_id=user["user_id"],
        bet=req.bet,
        mines_count=req.mines_count,
        field=field_json,
        server_seed=server_seed,
        client_seed=client_seed,
        nonce=nonce,
    )

    return {
        "game_id": game_id,
        "bet": req.bet,
        "mines_count": req.mines_count,
        "grid_size": GRID_SIZE,
        "server_seed_hash": server_seed_hash,
        "client_seed": client_seed,
        "multiplier": 1.0,
        "revealed": [],
    }


class RevealRequest(BaseModel):
    cell: int


@router.post("/reveal")
async def reveal_cell(req: RevealRequest, user: dict = Depends(get_current_user)):
    assert _db is not None

    game = await _db.get_active_mines_game(user["user_id"])
    if not game:
        raise HTTPException(status_code=400, detail="No active game")

    if req.cell < 0 or req.cell >= GRID_SIZE:
        raise HTTPException(status_code=400, detail="Invalid cell")

    revealed = json.loads(game["revealed"])
    if req.cell in revealed:
        raise HTTPException(status_code=400, detail="Cell already revealed")

    mines = json.loads(game["field"])

    if req.cell in mines:
        revealed.append(req.cell)
        await _db.update_mines_game(
            game["id"],
            revealed=json.dumps(revealed),
            status="lost",
            multiplier=0.0,
            finished_at=time.time(),
        )
        return {
            "result": "mine",
            "cell": req.cell,
            "mines": mines,
            "revealed": revealed,
            "multiplier": 0.0,
            "profit": 0.0,
            "game_over": True,
            "server_seed": game["server_seed"],
        }

    revealed.append(req.cell)
    new_multiplier = _calc_multiplier(game["mines_count"], len(revealed))

    safe_cells = GRID_SIZE - game["mines_count"]
    all_safe_revealed = len(revealed) >= safe_cells

    if all_safe_revealed:
        payout = game["bet"] * new_multiplier
        win_profit = payout - game["bet"]
        await _db.add_balance(user["user_id"], payout)
        await _db.update_mines_game(
            game["id"],
            revealed=json.dumps(revealed),
            multiplier=new_multiplier,
            status="won",
            finished_at=time.time(),
        )
        if new_multiplier >= MIN_WIN_MULTIPLIER and win_profit > 0:
            await _post_mines_win(user, win_profit, game["mines_count"], new_multiplier)
        return {
            "result": "win_all",
            "cell": req.cell,
            "mines": mines,
            "revealed": revealed,
            "multiplier": new_multiplier,
            "profit": win_profit,
            "game_over": True,
            "server_seed": game["server_seed"],
        }

    await _db.update_mines_game(
        game["id"],
        revealed=json.dumps(revealed),
        multiplier=new_multiplier,
    )

    return {
        "result": "safe",
        "cell": req.cell,
        "revealed": revealed,
        "multiplier": new_multiplier,
        "next_multiplier": _calc_multiplier(game["mines_count"], len(revealed) + 1),
        "profit": game["bet"] * new_multiplier - game["bet"],
        "game_over": False,
    }


@router.post("/cashout")
async def cashout(user: dict = Depends(get_current_user)):
    assert _db is not None

    game = await _db.claim_mines_cashout(user["user_id"])
    if not game:
        raise HTTPException(status_code=400, detail="No active game")

    revealed = json.loads(game["revealed"])
    if not revealed:
        # Revert status back to active if no cells revealed
        await _db.update_mines_game(game["id"], status="active")
        raise HTTPException(status_code=400, detail="Reveal at least one cell")

    multiplier = game["multiplier"]
    payout = game["bet"] * multiplier
    mines = json.loads(game["field"])

    await _db.add_balance(user["user_id"], payout)
    await _db.update_mines_game(
        game["id"],
        status="cashout",
        finished_at=time.time(),
    )

    profit = payout - game["bet"]
    if multiplier >= MIN_WIN_MULTIPLIER and profit > 0:
        await _post_mines_win(user, profit, game["mines_count"], multiplier)

    return {
        "profit": profit,
        "payout": payout,
        "multiplier": multiplier,
        "mines": mines,
        "server_seed": game["server_seed"],
    }


@router.get("/active")
async def active_game(user: dict = Depends(get_current_user)):
    assert _db is not None
    game = await _db.get_active_mines_game(user["user_id"])
    if not game:
        return {"active": False}

    server_seed_hash = hashlib.sha256(game["server_seed"].encode()).hexdigest()
    revealed = json.loads(game["revealed"])

    return {
        "active": True,
        "game_id": game["id"],
        "bet": game["bet"],
        "mines_count": game["mines_count"],
        "grid_size": GRID_SIZE,
        "revealed": revealed,
        "multiplier": game["multiplier"],
        "next_multiplier": _calc_multiplier(game["mines_count"], len(revealed) + 1),
        "server_seed_hash": server_seed_hash,
        "client_seed": game["client_seed"],
    }


@router.get("/history")
async def game_history(user: dict = Depends(get_current_user)):
    assert _db is not None
    games = await _db.get_mines_history(user["user_id"])
    return {"games": games}


async def _post_mines_win(
    user: dict, profit: float, mines_count: int, multiplier: float
) -> None:
    """Post big mines wins to feed channel and public feed."""
    username = user.get("username", "") or user.get("first_name", "") or f"User{user['user_id']}"
    try:
        await post_to_feed(
            "mines_win",
            username=username,
            profit=profit,
            mines_count=mines_count,
            multiplier=multiplier,
        )
    except Exception as e:
        logger.warning("Feed post error (mines_win): %s", e)

    if _db:
        try:
            display = username if len(username) <= 5 else username[:3] + "***" + username[-2:]
            await _db.add_feed_entry(
                event_type="mines_win",
                display_name=display,
                amount=profit,
                profit=profit,
            )
        except Exception as e:
            logger.warning("Feed entry error (mines_win): %s", e)
