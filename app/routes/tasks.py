import logging

import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import config
from app.database import Database
from app.routes.user import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_db: Database | None = None

TASKS = [
    {
        "id": "join_channel",
        "chat_id": "@goodmoneygroup",
        "reward": 0.01,
        "link": "https://t.me/goodmoneygroup",
    },
    {
        "id": "join_chat",
        "chat_id": "@originaltonchat",
        "reward": 0.01,
        "link": "https://t.me/originaltonchat",
    },
]


def init_routes(db: Database) -> None:
    global _db
    _db = db


async def check_membership(user_id: int, chat_id: str) -> bool:
    """Check if user is a member of the chat/channel via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{config.bot_token}/getChatMember"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params={"chat_id": chat_id, "user_id": user_id}) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    logger.warning("getChatMember failed for %s in %s: %s", user_id, chat_id, data)
                    return False
                status = data["result"]["status"]
                return status in ("member", "administrator", "creator")
    except Exception as e:
        logger.error("Membership check error: %s", e)
        return False


@router.get("")
async def list_tasks(user: dict = Depends(get_current_user)):
    assert _db is not None
    completed = await _db.get_completed_tasks(user["user_id"])
    result = []
    for task in TASKS:
        result.append({
            "id": task["id"],
            "reward": task["reward"],
            "link": task["link"],
            "completed": task["id"] in completed,
        })
    return {"tasks": result}


class ClaimRequest(BaseModel):
    task_id: str


@router.post("/claim")
async def claim_task(req: ClaimRequest, user: dict = Depends(get_current_user)):
    assert _db is not None

    task = next((t for t in TASKS if t["id"] == req.task_id), None)
    if not task:
        raise HTTPException(status_code=400, detail="Unknown task")

    completed = await _db.get_completed_tasks(user["user_id"])
    if req.task_id in completed:
        raise HTTPException(status_code=400, detail="Task already completed")

    is_member = await check_membership(user["user_id"], task["chat_id"])
    if not is_member:
        raise HTTPException(status_code=400, detail="Not a member")

    ok = await _db.complete_task(user["user_id"], req.task_id, task["reward"])
    if not ok:
        raise HTTPException(status_code=400, detail="Task already completed")

    return {"success": True, "reward": task["reward"]}
