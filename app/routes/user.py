import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, unquote

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from app.config import config
from app.database import Database

router = APIRouter(prefix="/api/user", tags=["user"])

_db: Database | None = None


def init_routes(db: Database) -> None:
    global _db
    _db = db


def validate_init_data(init_data: str) -> dict | None:
    """Validate Telegram WebApp initData and return parsed data."""
    if not init_data or not config.bot_token:
        return None
    try:
        parsed = parse_qs(init_data)
        check_hash = parsed.get("hash", [""])[0]
        if not check_hash:
            return None

        data_pairs = []
        for key, values in sorted(parsed.items()):
            if key == "hash":
                continue
            data_pairs.append(f"{key}={unquote(values[0])}")
        data_check_string = "\n".join(data_pairs)

        secret_key = hmac.new(
            b"WebAppData", config.bot_token.encode(), hashlib.sha256
        ).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if computed_hash != check_hash:
            return None

        auth_date = int(parsed.get("auth_date", ["0"])[0])
        if time.time() - auth_date > 86400:
            return None

        user_str = parsed.get("user", [""])[0]
        if user_str:
            return json.loads(unquote(user_str))
        return None
    except Exception:
        return None


async def get_current_user(x_init_data: str = Header(default="")) -> dict:
    assert _db is not None
    tg_user = validate_init_data(x_init_data)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Invalid auth")
    user_id = tg_user["id"]
    user = await _db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not registered")
    if user["is_blocked"]:
        raise HTTPException(status_code=403, detail="User is blocked")
    return user


class RegisterRequest(BaseModel):
    ref: str = ""
    language: str = "en"


@router.post("/register")
async def register(req: RegisterRequest, x_init_data: str = Header(default="")):
    assert _db is not None
    tg_user = validate_init_data(x_init_data)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Invalid auth")

    user_id = tg_user["id"]
    existing = await _db.get_user(user_id)
    if existing:
        is_admin = (
            existing["is_admin"]
            or user_id in config.admin_ids
        )
        return {
            "status": "exists",
            "user": {**existing, "is_admin": is_admin},
        }

    referrer_id = None
    if req.ref:
        try:
            ref_id = int(req.ref)
            ref_user = await _db.get_user(ref_id)
            if ref_user and ref_id != user_id:
                referrer_id = ref_id
        except ValueError:
            pass

    from app.services.ton import ton_service

    comment = ton_service.generate_deposit_comment(user_id)

    await _db.add_user(
        user_id=user_id,
        username=tg_user.get("username", ""),
        first_name=tg_user.get("first_name", ""),
        deposit_comment=comment,
        language=req.language,
        referrer_id=referrer_id,
    )

    if user_id in config.admin_ids:
        await _db.update_user(user_id, is_admin=1)

    user = await _db.get_user(user_id)
    return {"status": "created", "user": user}


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    is_admin = user["is_admin"] or user["user_id"] in config.admin_ids
    return {**user, "is_admin": is_admin}


@router.post("/language")
async def set_language(
    lang: dict,
    user: dict = Depends(get_current_user),
):
    assert _db is not None
    language = lang.get("language", "en")
    if language not in ("en", "ru"):
        language = "en"
    await _db.update_user(user["user_id"], language=language)
    return {"status": "ok"}
