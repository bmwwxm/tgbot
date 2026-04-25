"""GoodMoney — Main application entry point."""

import asyncio
import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import config
from app.database import Database
from app.bot import bot, dp, init_bot, notify_user, broadcast_message
from app.routes import user as user_routes
from app.routes import deposit as deposit_routes
from app.routes import withdraw as withdraw_routes
from app.routes import referral as referral_routes
from app.routes import admin as admin_routes
from app.routes import feed as feed_routes
from app.routes import mines as mines_routes
from app.services.ton import ton_service
from app.feed_bot import close_feed_bot
from app.services.scheduler import scheduler, init_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="GoodMoney", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database(config.db_path)

user_routes.init_routes(db)
deposit_routes.init_routes(db, notify_user)
withdraw_routes.init_routes(db)
referral_routes.init_routes(db)
admin_routes.init_routes(db)
feed_routes.init_routes(db)
mines_routes.init_routes(db)

app.include_router(user_routes.router)
app.include_router(deposit_routes.router)
app.include_router(withdraw_routes.router)
app.include_router(referral_routes.router)
app.include_router(admin_routes.router)
app.include_router(feed_routes.router)
app.include_router(mines_routes.router)


# ── Broadcast endpoint (called from admin route) ───────
from fastapi import Request


@app.post("/api/admin/broadcast/send")
async def send_broadcast(request: Request):
    data = await request.json()
    user_ids = data.get("user_ids", [])
    message = data.get("message", "")
    result = await broadcast_message(user_ids, message)
    return result


# ── Health check ────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "network": config.ton_network}


# ── Settings (public, for frontend) ────────────────────
@app.get("/api/settings")
async def public_settings():
    min_dep = await db.get_setting("min_deposit")
    profit = await db.get_setting("profit_percent")
    maturity = await db.get_setting("deposit_maturity_seconds")
    ref = await db.get_setting("referral_percent")
    min_w = await db.get_setting("min_withdrawal")
    fee = await db.get_setting("withdrawal_fee")
    return {
        "min_deposit": float(min_dep) if min_dep else config.min_deposit,
        "profit_percent": float(profit) if profit else config.profit_percent,
        "maturity_hours": (
            int(float(maturity)) if maturity else config.deposit_maturity_seconds
        )
        / 3600,
        "referral_percent": float(ref) if ref else config.referral_percent,
        "min_withdrawal": float(min_w) if min_w else config.min_withdrawal,
        "withdrawal_fee": float(fee) if fee else config.withdrawal_fee,
    }


# ── Serve frontend ─────────────────────────────────────
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


# ── Lifecycle ──────────────────────────────────────────
@app.on_event("startup")
async def startup():
    logger.info("Starting GoodMoney...")
    await db.connect()
    await ton_service.init()
    init_bot(db)
    init_scheduler(db, notify_user)
    scheduler.start()
    logger.info("Scheduler started")

    if bot:
        asyncio.create_task(_start_polling())
    logger.info("GoodMoney started successfully")


async def _start_polling():
    try:
        assert bot is not None
        me = await bot.get_me()
        logger.info("Bot started: @%s", me.username)
        await db.set_setting("bot_username", me.username or "")
        await dp.start_polling(bot, handle_signals=False)
    except Exception as e:
        logger.error("Bot polling error: %s", e)


@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down...")
    scheduler.shutdown(wait=False)
    if bot:
        await bot.session.close()
    await close_feed_bot()
    await ton_service.close()
    await db.close()


def main():
    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
