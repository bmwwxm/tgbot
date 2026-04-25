"""Monitors incoming TON deposits and matches them to users."""

import logging

from app.database import Database
from app.services.ton import ton_service

logger = logging.getLogger(__name__)


async def check_deposits(db: Database, maturity_seconds: int, min_deposit: float) -> list[dict]:
    """Scan recent transactions, match deposits by comment, record new ones."""
    new_deposits: list[dict] = []
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
        if amount < min_deposit:
            logger.info(
                "Deposit from user %d below minimum: %.4f < %.4f",
                user["user_id"], amount, min_deposit,
            )
            await db.mark_tx_processed(tx_hash)
            continue

        if user["is_blocked"]:
            logger.info("Blocked user %d deposit ignored", user["user_id"])
            await db.mark_tx_processed(tx_hash)
            continue

        deposit_id = await db.add_deposit(
            user_id=user["user_id"],
            amount=amount,
            tx_hash=tx_hash,
            maturity_seconds=maturity_seconds,
        )
        await db.mark_tx_processed(tx_hash)
        new_deposits.append(
            {
                "deposit_id": deposit_id,
                "user_id": user["user_id"],
                "amount": amount,
                "tx_hash": tx_hash,
            }
        )
        logger.info(
            "New deposit #%d: user=%d amount=%.4f",
            deposit_id, user["user_id"], amount,
        )

    return new_deposits
