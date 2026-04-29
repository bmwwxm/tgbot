"""Monitors incoming TON transfers and credits them to user balance."""

import logging

from app.database import Database
from app.services.ton import ton_service

logger = logging.getLogger(__name__)

# Minimum TON to accept (avoid dust)
MIN_TOPUP = 0.1


async def check_incoming(db: Database) -> list[dict]:
    """Scan recent transactions, match by comment, credit to user balance."""
    credited: list[dict] = []
    try:
        transactions = await ton_service.get_transactions(limit=50)
        incoming = ton_service.parse_incoming_transactions(transactions)
    except Exception as e:
        logger.error("Error fetching transactions: %s", e)
        return []

    for tx in incoming:
        tx_hash = tx["tx_hash"]
        if not tx_hash:
            continue
        if await db.is_tx_processed(tx_hash):
            continue

        comment = tx["comment"].strip()
        if not comment:
            await db.mark_tx_processed(tx_hash)
            continue

        user = await db.get_user_by_comment(comment)
        if not user:
            await db.mark_tx_processed(tx_hash)
            continue

        amount = tx["amount"]
        if amount < MIN_TOPUP:
            await db.mark_tx_processed(tx_hash)
            continue

        if user["is_blocked"]:
            logger.info("Blocked user %d top-up ignored", user["user_id"])
            await db.mark_tx_processed(tx_hash)
            continue

        ok = await db.credit_incoming_tx_safe(tx_hash, user["user_id"], amount)
        if not ok:
            continue

        credited.append(
            {
                "user_id": user["user_id"],
                "amount": amount,
                "tx_hash": tx_hash,
            }
        )
        logger.info(
            "Top-up: user=%d amount=%.4f tx=%s",
            user["user_id"], amount, tx_hash,
        )

    return credited
