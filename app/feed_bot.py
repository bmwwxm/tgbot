"""Second Telegram bot — real-time payout feed to a public channel.

This bot posts deposit, maturity, withdrawal, and referral events
to a configured Telegram channel/group in real time.
"""

import logging
import os

from aiogram import Bot

from app.config import config

logger = logging.getLogger(__name__)

FEED_BOT_TOKEN = os.getenv("FEED_BOT_TOKEN", "")
FEED_CHANNEL_ID = os.getenv("FEED_CHANNEL_ID", "")

feed_bot: Bot | None = None

if FEED_BOT_TOKEN:
    feed_bot = Bot(token=FEED_BOT_TOKEN)

FEED_TEMPLATES = {
    "ru": {
        "deposit_received": (
            "💎 <b>Новый депозит</b>\n\n"
            "Пользователь внёс <b>{amount:.4f} TON</b>\n"
            "Ожидаемая прибыль: <b>+{profit:.4f} TON</b>\n"
            "Начисление через <b>{hours}ч</b>"
        ),
        "deposit_matured": (
            "🎉 <b>Выплата!</b>\n\n"
            "Депозит: <b>{amount:.4f} TON</b>\n"
            "Прибыль: <b>+{profit:.4f} TON</b>\n"
            "Итого начислено: <b>{total:.4f} TON</b>"
        ),
        "withdrawal_sent": (
            "💸 <b>Вывод средств</b>\n\n"
            "Отправлено: <b>{amount:.4f} TON</b>\n"
            "TX: <code>{tx_hash}</code>"
        ),
        "referral_bonus": (
            "🤝 <b>Реферальный бонус</b>\n\n"
            "Начислено: <b>+{amount:.4f} TON</b>"
        ),
        "mines_win": (
            "💣💰 <b>Выигрыш в минах!</b>\n\n"
            "@{username} только что поднял <b>{profit:.4f} TON</b> "
            "на <b>{mines_count}</b> минах!\n"
            "Множитель: <b>{multiplier:.2f}x</b>"
        ),
        "crash_win": (
            "🚀💰 <b>Выигрыш в Краш!</b>\n\n"
            "@{username} забрал <b>{profit:.4f} TON</b>\n"
            "Множитель: <b>{multiplier:.2f}x</b>"
        ),
        "pvp_win": (
            "⚔️🏆 <b>Победа в PvP!</b>\n\n"
            "@{username} выиграл битву и забрал <b>{profit:.4f} TON</b>"
        ),
    },
    "en": {
        "deposit_received": (
            "💎 <b>New Deposit</b>\n\n"
            "User deposited <b>{amount:.4f} TON</b>\n"
            "Expected profit: <b>+{profit:.4f} TON</b>\n"
            "Maturity in <b>{hours}h</b>"
        ),
        "deposit_matured": (
            "🎉 <b>Payout!</b>\n\n"
            "Deposit: <b>{amount:.4f} TON</b>\n"
            "Profit: <b>+{profit:.4f} TON</b>\n"
            "Total credited: <b>{total:.4f} TON</b>"
        ),
        "withdrawal_sent": (
            "💸 <b>Withdrawal</b>\n\n"
            "Sent: <b>{amount:.4f} TON</b>\n"
            "TX: <code>{tx_hash}</code>"
        ),
        "referral_bonus": (
            "🤝 <b>Referral Bonus</b>\n\n"
            "Credited: <b>+{amount:.4f} TON</b>"
        ),
        "mines_win": (
            "💣💰 <b>Mines Win!</b>\n\n"
            "@{username} just won <b>{profit:.4f} TON</b> "
            "with <b>{mines_count}</b> mines!\n"
            "Multiplier: <b>{multiplier:.2f}x</b>"
        ),
        "crash_win": (
            "🚀💰 <b>Crash Win!</b>\n\n"
            "@{username} cashed out <b>{profit:.4f} TON</b>\n"
            "Multiplier: <b>{multiplier:.2f}x</b>"
        ),
        "pvp_win": (
            "⚔️🏆 <b>PvP Victory!</b>\n\n"
            "@{username} won the battle and took <b>{profit:.4f} TON</b>"
        ),
    },
}

FEED_LANG = os.getenv("FEED_LANG", "ru")


async def post_to_feed(event: str, **kwargs) -> None:
    """Post an event to the feed channel."""
    if not feed_bot or not FEED_CHANNEL_ID:
        return

    templates = FEED_TEMPLATES.get(FEED_LANG, FEED_TEMPLATES["en"])
    template = templates.get(event)
    if not template:
        return

    try:
        text = template.format(**kwargs)
        await feed_bot.send_message(
            chat_id=FEED_CHANNEL_ID,
            text=text,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Failed to post to feed channel: %s", e)


async def close_feed_bot() -> None:
    if feed_bot:
        await feed_bot.session.close()
