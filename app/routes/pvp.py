"""PvP Battle — multiplayer lobbies where players bet and one winner takes all."""

import asyncio
import hashlib
import random
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import logging

from app.database import Database
from app.feed_bot import post_to_feed
from app.routes.user import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pvp", tags=["pvp"])

_db: Database | None = None

MIN_BET = 0.1
MAX_BET = 50.0
COMMISSION = 0.05  # 5%
MIN_PLAYERS = 2
MAX_PLAYERS = 10

# Fake player names — look like real Telegram users
_FAKE_NAMES = [
    "Alex", "Дмитрий", "Maria", "Андрей", "Nikita", "Елена", "Sergey",
    "Ольга", "Pavel", "Анна", "Ivan", "Катя", "Vlad", "Максим",
    "Артём", "Светлана", "Roman", "Юлия", "Denis", "Марк",
    "Тимур", "Даниил", "Кирилл", "Арина", "Полина", "Илья",
    "Viktor", "Алиса", "Игорь", "Вера", "Олег", "Лиза",
    "Руслан", "Мария", "Костя", "Настя", "Глеб", "Соня",
    "Егор", "Лера", "Матвей", "Вика", "Степан", "Милана",
    "crypto_king", "ton_master", "lucky_bet", "win4ever",
    "profit_hunter", "diamond_h", "moon_shot", "mega_win",
]

_FAKE_SUFFIXES = ["", "💎", "🚀", "⭐", "🔥", "💰", "🎯", "🏆", "👑", ""]

# Track pending bot joins {lobby_id: asyncio.Task}
_bot_tasks: dict[int, asyncio.Task] = {}


def init_routes(db: Database) -> None:
    global _db
    _db = db


def _generate_fake_name() -> str:
    name = random.choice(_FAKE_NAMES)
    suffix = random.choice(_FAKE_SUFFIXES)
    if random.random() < 0.3:
        name = name + str(random.randint(1, 99))
    return name + suffix


def _generate_rolls(server_seed: str, num_players: int) -> list[float]:
    """Generate provably fair rolls for all players."""
    rolls = []
    for i in range(num_players):
        combined = f"{server_seed}:player:{i}"
        h = hashlib.sha256(combined.encode()).hexdigest()
        val = int(h[:8], 16) / 0xFFFFFFFF * 100
        rolls.append(round(val, 2))
    return rolls


class CreateLobbyRequest(BaseModel):
    bet: float
    max_players: int = 2


class JoinLobbyRequest(BaseModel):
    lobby_id: int


@router.post("/create")
async def create_lobby(req: CreateLobbyRequest, user: dict = Depends(get_current_user)):
    assert _db is not None

    if req.bet < MIN_BET:
        raise HTTPException(status_code=400, detail=f"Minimum bet: {MIN_BET} TON")
    if req.bet > MAX_BET:
        raise HTTPException(status_code=400, detail=f"Maximum bet: {MAX_BET} TON")
    if req.max_players < MIN_PLAYERS or req.max_players > MAX_PLAYERS:
        raise HTTPException(status_code=400, detail=f"Players: {MIN_PLAYERS}-{MAX_PLAYERS}")

    server_seed = secrets.token_hex(32)
    seed_hash = hashlib.sha256(server_seed.encode()).hexdigest()

    result = await _db.create_pvp_lobby_safe(
        creator_id=user["user_id"],
        bet=req.bet,
        max_players=req.max_players,
        server_seed=server_seed,
        seed_hash=seed_hash,
        commission=COMMISSION,
    )
    if not result:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    lobby_id = result["lobby_id"]

    # Schedule bots to join after random delays
    _schedule_bots(lobby_id, req.bet, req.max_players - 1)

    return {
        "lobby_id": lobby_id,
        "bet": req.bet,
        "max_players": req.max_players,
        "seed_hash": seed_hash,
        "players": [_player_info(user)],
    }


@router.post("/join")
async def join_lobby(req: JoinLobbyRequest, user: dict = Depends(get_current_user)):
    assert _db is not None

    result = await _db.join_pvp_lobby_safe(req.lobby_id, user["user_id"])
    if result is None:
        raise HTTPException(status_code=400, detail="Lobby not found or full")
    if result == "insufficient":
        raise HTTPException(status_code=400, detail="Insufficient balance")
    if result == "already_joined":
        raise HTTPException(status_code=400, detail="Already in this lobby")

    lobby = result["lobby"]
    players = result["players"]

    if len(players) >= lobby["max_players"]:
        # Cancel any remaining bot tasks for this lobby
        task = _bot_tasks.pop(lobby["id"], None)
        if task:
            task.cancel()
        await _resolve_lobby(lobby["id"])

    lobby_data = await _db.get_pvp_lobby(req.lobby_id)
    players_data = await _db.get_pvp_players(req.lobby_id)
    return {
        "lobby_id": req.lobby_id,
        "status": lobby_data["status"] if lobby_data else "waiting",
        "players": [_format_player(p) for p in players_data],
    }


@router.get("/lobbies")
async def list_lobbies(user: dict = Depends(get_current_user)):
    assert _db is not None
    lobbies = await _db.get_pvp_lobbies_waiting()
    result = []
    for lb in lobbies:
        players = await _db.get_pvp_players(lb["id"])
        result.append({
            "lobby_id": lb["id"],
            "bet": lb["bet"],
            "max_players": lb["max_players"],
            "current_players": len(players),
            "players": [_format_player(p) for p in players],
            "created_at": lb["created_at"],
            "seed_hash": lb["seed_hash"],
        })
    return {"lobbies": result}


@router.get("/lobby/{lobby_id}")
async def get_lobby(lobby_id: int, user: dict = Depends(get_current_user)):
    assert _db is not None
    lobby = await _db.get_pvp_lobby(lobby_id)
    if not lobby:
        raise HTTPException(status_code=404, detail="Lobby not found")
    players = await _db.get_pvp_players(lobby_id)
    return {
        "lobby_id": lobby["id"],
        "bet": lobby["bet"],
        "max_players": lobby["max_players"],
        "status": lobby["status"],
        "winner_id": lobby["winner_id"],
        "winner_number": lobby["winner_number"],
        "seed_hash": lobby["seed_hash"],
        "server_seed": lobby["server_seed"] if lobby["status"] == "finished" else None,
        "commission": lobby["commission"],
        "players": [_format_player(p) for p in players],
        "created_at": lobby["created_at"],
    }


@router.get("/history")
async def game_history(user: dict = Depends(get_current_user)):
    assert _db is not None
    games = await _db.get_pvp_history(user["user_id"])
    return {"games": games}


def _player_info(user: dict) -> dict:
    return {
        "user_id": user["user_id"],
        "name": user.get("first_name") or user.get("username") or f"Player",
        "is_bot": False,
    }


def _format_player(p: dict) -> dict:
    name = p.get("first_name") or p.get("username") or p.get("display_name") or "Player"
    return {
        "user_id": p["user_id"],
        "name": name,
        "roll": p.get("roll"),
    }


def _schedule_bots(lobby_id: int, bet: float, num_bots: int):
    """Schedule fake bot players to join lobby with realistic delays."""
    async def _add_bots():
        try:
            assert _db is not None
            bots_to_add = random.randint(max(1, num_bots - 1), num_bots)
            for i in range(bots_to_add):
                delay = random.uniform(2.0, 8.0) + i * random.uniform(1.5, 4.0)
                await asyncio.sleep(delay)

                lobby = await _db.get_pvp_lobby(lobby_id)
                if not lobby or lobby["status"] != "waiting":
                    break

                players = await _db.get_pvp_players(lobby_id)
                if len(players) >= lobby["max_players"]:
                    break

                fake_name = _generate_fake_name()
                fake_uid = -(1000000 + random.randint(0, 9999999))

                joined = await _db.add_pvp_bot_player(lobby_id, fake_uid, fake_name)
                if not joined:
                    continue

                players = await _db.get_pvp_players(lobby_id)
                if len(players) >= lobby["max_players"]:
                    await _resolve_lobby(lobby_id)
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Bot scheduling error for lobby %s: %s", lobby_id, e)
        finally:
            _bot_tasks.pop(lobby_id, None)

    task = asyncio.create_task(_add_bots())
    _bot_tasks[lobby_id] = task


async def _resolve_lobby(lobby_id: int):
    """Resolve the lobby — roll for all players, pick winner, distribute prize."""
    assert _db is not None

    lobby = await _db.get_pvp_lobby(lobby_id)
    if not lobby or lobby["status"] != "waiting":
        return

    players = await _db.get_pvp_players(lobby_id)
    if len(players) < 2:
        return

    rolls = _generate_rolls(lobby["server_seed"], len(players))

    # Bias: if there are real players, slightly boost their rolls (hidden advantage)
    real_indices = [i for i, p in enumerate(players) if p["user_id"] > 0]
    if real_indices:
        for idx in real_indices:
            # 60% chance real player gets a boost
            if random.random() < 0.6:
                rolls[idx] = min(99.99, rolls[idx] + random.uniform(5, 25))

    # Find winner (highest roll)
    best_idx = max(range(len(rolls)), key=lambda i: rolls[i])
    winner = players[best_idx]

    total_pot = lobby["bet"] * len(players)
    commission_amount = total_pot * lobby["commission"]
    prize = total_pot - commission_amount

    await _db.resolve_pvp_lobby(
        lobby_id=lobby_id,
        winner_id=winner["user_id"],
        winner_roll=rolls[best_idx],
        rolls=list(zip([p["user_id"] for p in players], rolls)),
        prize=prize,
    )

    # Post to feed if big win
    if prize >= 0.5:
        name = winner.get("first_name") or winner.get("display_name") or "Player"
        try:
            display = name if len(name) <= 5 else name[:3] + "***" + name[-2:]
            await _db.add_feed_entry(
                event_type="pvp_win",
                display_name=display,
                amount=prize,
                profit=prize - lobby["bet"],
            )
        except Exception:
            pass
