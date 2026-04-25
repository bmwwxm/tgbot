"""Background scheduler for deposit maturity, withdrawals, and monitoring."""

import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import config
from app.database import Database
from app.feed_bot import post_to_feed
from app.services.monitor import check_incoming
from app.services.ton import ton_service

logger = logging.getLogger(__name__)


def _mask_name(name: str) -> str:
    """Mask user name for public feed: 'Alexander' -> 'Ale***er'."""
    if not name or len(name) < 3:
        return "User***"
    return name[:3] + "***" + name[-2:]

scheduler = AsyncIOScheduler()

_db: Database | None = None
_bot_notify: Any = None


def init_scheduler(db: Database, bot_notify_func: Any = None) -> None:
    global _db, _bot_notify
    _db = db
    _bot_notify = bot_notify_func

    scheduler.add_job(
        _monitor_deposits, "interval", seconds=30, id="monitor_deposits",
        max_instances=1, misfire_grace_time=60,
    )
    scheduler.add_job(
        _process_matured_deposits, "interval", seconds=60, id="process_matured",
        max_instances=1, misfire_grace_time=60,
    )
    scheduler.add_job(
        _process_withdrawals, "interval", seconds=30, id="process_withdrawals",
        max_instances=1, misfire_grace_time=60,
    )


async def _get_effective_setting(key: str, default: float) -> float:
    assert _db is not None
    val = await _db.get_setting(key)
    return float(val) if val else default


async def _monitor_deposits() -> None:
    """Monitor incoming TON transfers and credit to user balance."""
    assert _db is not None
    credited = await check_incoming(_db)
    for tx in credited:
        if _bot_notify:
            try:
                await _bot_notify(
                    tx["user_id"],
                    "balance_topped_up",
                    amount=tx["amount"],
                )
            except Exception as e:
                logger.warning("Notify error: %s", e)


async def _process_matured_deposits() -> None:
    assert _db is not None
    matured = await _db.claim_matured_deposits()
    profit_pct = await _get_effective_setting("profit_percent", config.profit_percent)
    ref_pct = await _get_effective_setting("referral_percent", config.referral_percent)

    for dep in matured:
        user_id = dep["user_id"]
        amount = dep["amount"]
        profit = amount * (profit_pct / 100.0)

        await _db.add_balance(user_id, amount + profit)
        await _db.add_balance_field(user_id, "total_earned", profit)
        await _db.mark_deposit_paid(dep["id"], profit)

        user_for_feed = await _db.get_user(user_id)
        payout_name = _mask_name(user_for_feed.get("first_name", "") if user_for_feed else "")
        await _db.add_feed_entry(
            event_type="payout",
            display_name=payout_name,
            amount=amount,
            profit=profit,
        )

        logger.info(
            "Deposit #%d matured: user=%d amount=%.4f profit=%.4f",
            dep["id"], user_id, amount, profit,
        )

        if _bot_notify:
            try:
                await _bot_notify(
                    user_id, "deposit_matured",
                    amount=amount, profit=profit,
                )
            except Exception as e:
                logger.warning("Notify error: %s", e)
        try:
            await post_to_feed(
                "deposit_matured",
                amount=amount,
                profit=profit,
                total=amount + profit,
            )
        except Exception as e:
            logger.warning("Feed post error: %s", e)

        user = await _db.get_user(user_id)
        if user and user.get("referrer_id"):
            referrer_id = user["referrer_id"]
            ref_bonus = profit * (ref_pct / 100.0)
            await _db.add_balance(referrer_id, ref_bonus)
            await _db.add_balance_field(referrer_id, "referral_earnings", ref_bonus)
            logger.info(
                "Referral bonus: referrer=%d bonus=%.4f from user=%d",
                referrer_id, ref_bonus, user_id,
            )
            if _bot_notify:
                try:
                    await _bot_notify(
                        referrer_id, "referral_bonus",
                        amount=ref_bonus, from_user=user_id,
                    )
                except Exception as e:
                    logger.warning("Notify error: %s", e)
            try:
                await post_to_feed("referral_bonus", amount=ref_bonus)
            except Exception as e:
                logger.warning("Feed post error: %s", e)


async def _process_withdrawals() -> None:
    assert _db is not None
    pending = await _db.claim_pending_withdrawals()
    for w in pending:
        wid = w["id"]
        user_id = w["user_id"]
        amount = w["amount"]
        fee = w["fee"]
        to_addr = w["to_address"]
        send_amount = amount - fee

        if send_amount <= 0:
            await _db.fail_withdrawal_and_refund(wid, user_id, amount)
            continue

        try:
            bot_username = await _db.get_setting("bot_username")
            bot_link = f"t.me/{bot_username}" if bot_username else config.webapp_url or "GoodMoney"
            comment = f"GoodMoney | {bot_link}"
            tx_hash = await ton_service.send_ton(
                to_addr, send_amount, comment=comment
            )
            await _db.mark_withdrawal_sent(wid, tx_hash)
            await _db.add_balance_field(user_id, "total_withdrawn", amount)
            logger.info(
                "Withdrawal #%d sent: user=%d amount=%.4f to=%s",
                wid, user_id, send_amount, to_addr,
            )
            user_for_feed = await _db.get_user(user_id)
            wd_name = _mask_name(user_for_feed.get("first_name", "") if user_for_feed else "")
            await _db.add_feed_entry(
                event_type="withdrawal",
                display_name=wd_name,
                amount=send_amount,
            )
            if _bot_notify:
                try:
                    await _bot_notify(
                        user_id, "withdrawal_sent",
                        amount=send_amount, tx_hash=tx_hash,
                    )
                except Exception as e:
                    logger.warning("Notify error: %s", e)
            try:
                await post_to_feed(
                    "withdrawal_sent", amount=send_amount, tx_hash=tx_hash,
                )
            except Exception as e:
                logger.warning("Feed post error: %s", e)

        except Exception as e:
            logger.error("Withdrawal #%d failed: %s", wid, e)
            await _db.fail_withdrawal_and_refund(wid, user_id, amount)
            if _bot_notify:
                try:
                    await _bot_notify(user_id, "withdrawal_failed", amount=amount)
                except Exception as e2:
                    logger.warning("Notify error: %s", e2)
