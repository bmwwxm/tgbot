"""Telegram bot — /start command, WebApp button, notifications."""

import logging

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)

from app.config import config
from app.database import Database

logger = logging.getLogger(__name__)

bot = Bot(token=config.bot_token) if config.bot_token else None
dp = Dispatcher()

_db: Database | None = None

TEXTS = {
    "ru": {
        "welcome": (
            "💰 <b>GoodMoney</b>\n\n"
            "Добро пожаловать в GoodMoney — платформу для умных инвестиций "
            "на базе AI-арбитража в экосистеме TON.\n\n"
            "🔹 Минимальный депозит: <b>{min_dep} TON</b>\n"
            "🔹 Доходность: <b>+{profit}%</b> за <b>{hours}ч</b>\n"
            "🔹 Реферальная программа: <b>{ref}%</b>\n\n"
            "Нажмите кнопку ниже, чтобы открыть приложение:"
        ),
        "open_app": "💎 Открыть GoodMoney",
        "deposit_received": (
            "✅ <b>Депозит получен!</b>\n\n"
            "Сумма: <b>{amount:.4f} TON</b>\n"
            "Начисление через: <b>{hours}ч</b>"
        ),
        "deposit_matured": (
            "🎉 <b>Депозит созрел!</b>\n\n"
            "Сумма: <b>{amount:.4f} TON</b>\n"
            "Прибыль: <b>+{profit:.4f} TON</b>\n"
            "Зачислено на баланс!"
        ),
        "withdrawal_sent": (
            "💸 <b>Вывод отправлен!</b>\n\n"
            "Сумма: <b>{amount:.4f} TON</b>\n"
            "<a href=\"https://tonviewer.com/transaction/{tx_hash}\">Посмотреть на Tonviewer</a>"
        ),
        "withdrawal_failed": (
            "❌ <b>Ошибка вывода</b>\n\n"
            "Сумма <b>{amount:.4f} TON</b> возвращена на баланс."
        ),
        "referral_bonus": (
            "🤝 <b>Реферальный бонус!</b>\n\n"
            "Вы получили <b>+{amount:.4f} TON</b> от реферала."
        ),
        "balance_topped_up": (
            "💰 <b>Баланс пополнен!</b>\n\n"
            "Зачислено: <b>{amount:.4f} TON</b>\n"
            "Средства доступны для инвестиций и игр."
        ),
        "investment_created": (
            "📈 <b>Инвестиция создана!</b>\n\n"
            "Сумма: <b>{amount:.4f} TON</b>\n"
            "Прибыль: <b>+{profit:.4f} TON</b>\n"
            "Начисление через: <b>{hours}ч</b>"
        ),
    },
    "en": {
        "welcome": (
            "💰 <b>GoodMoney</b>\n\n"
            "Welcome to GoodMoney — a smart investment platform "
            "powered by AI arbitrage in the TON ecosystem.\n\n"
            "🔹 Minimum deposit: <b>{min_dep} TON</b>\n"
            "🔹 Yield: <b>+{profit}%</b> in <b>{hours}h</b>\n"
            "🔹 Referral program: <b>{ref}%</b>\n\n"
            "Tap the button below to open the app:"
        ),
        "open_app": "💎 Open GoodMoney",
        "deposit_received": (
            "✅ <b>Deposit received!</b>\n\n"
            "Amount: <b>{amount:.4f} TON</b>\n"
            "Maturity in: <b>{hours}h</b>"
        ),
        "deposit_matured": (
            "🎉 <b>Deposit matured!</b>\n\n"
            "Amount: <b>{amount:.4f} TON</b>\n"
            "Profit: <b>+{profit:.4f} TON</b>\n"
            "Credited to your balance!"
        ),
        "withdrawal_sent": (
            "💸 <b>Withdrawal sent!</b>\n\n"
            "Amount: <b>{amount:.4f} TON</b>\n"
            "<a href=\"https://tonviewer.com/transaction/{tx_hash}\">View on Tonviewer</a>"
        ),
        "withdrawal_failed": (
            "❌ <b>Withdrawal failed</b>\n\n"
            "Amount <b>{amount:.4f} TON</b> returned to your balance."
        ),
        "referral_bonus": (
            "🤝 <b>Referral bonus!</b>\n\n"
            "You received <b>+{amount:.4f} TON</b> from a referral."
        ),
        "balance_topped_up": (
            "💰 <b>Balance topped up!</b>\n\n"
            "Credited: <b>{amount:.4f} TON</b>\n"
            "Funds available for investments and games."
        ),
        "investment_created": (
            "📈 <b>Investment created!</b>\n\n"
            "Amount: <b>{amount:.4f} TON</b>\n"
            "Profit: <b>+{profit:.4f} TON</b>\n"
            "Maturity in: <b>{hours}h</b>"
        ),
    },
}


def init_bot(db: Database) -> None:
    global _db
    _db = db


async def _get_user_lang(user_id: int) -> str:
    if _db:
        user = await _db.get_user(user_id)
        if user:
            return user.get("language", "en")
    return "en"


async def _get_effective_settings() -> dict:
    if not _db:
        return {
            "min_dep": config.min_deposit,
            "profit": config.profit_percent,
            "hours": config.deposit_maturity_seconds / 3600,
            "ref": config.referral_percent,
        }
    min_dep = await _db.get_setting("min_deposit")
    profit = await _db.get_setting("profit_percent")
    maturity = await _db.get_setting("deposit_maturity_seconds")
    ref = await _db.get_setting("referral_percent")
    return {
        "min_dep": float(min_dep) if min_dep else config.min_deposit,
        "profit": float(profit) if profit else config.profit_percent,
        "hours": (
            int(float(maturity)) if maturity else config.deposit_maturity_seconds
        ) / 3600,
        "ref": float(ref) if ref else config.referral_percent,
    }


@dp.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    if not message.from_user or not bot:
        return
    user_id = message.from_user.id

    lang_code = message.from_user.language_code or "en"
    lang = "ru" if lang_code.startswith("ru") else "en"

    ref_id = None
    if message.text and len(message.text.split()) > 1:
        ref_param = message.text.split()[1]
        try:
            ref_id = int(ref_param)
        except ValueError:
            pass

    if _db:
        from app.services.ton import ton_service

        comment = ton_service.generate_deposit_comment(user_id)
        created = await _db.add_user(
            user_id=user_id,
            username=message.from_user.username or "",
            first_name=message.from_user.first_name or "",
            deposit_comment=comment,
            language=lang,
            referrer_id=ref_id if ref_id and ref_id != user_id else None,
        )
        if not created:
            user = await _db.get_user(user_id)
            if user:
                lang = user.get("language", lang)

        if user_id in config.admin_ids:
            await _db.update_user(user_id, is_admin=1)

        me = await bot.get_me()
        await _db.set_setting("bot_username", me.username or "")

    settings = await _get_effective_settings()
    texts = TEXTS.get(lang, TEXTS["en"])

    webapp_url = config.webapp_url
    start_param = f"?ref={ref_id}" if ref_id else ""

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts["open_app"],
                    web_app=WebAppInfo(url=f"{webapp_url}{start_param}"),
                )
            ]
        ]
    )

    await message.answer(
        texts["welcome"].format(**settings),
        reply_markup=kb,
        parse_mode="HTML",
    )


async def notify_user(user_id: int, event: str, **kwargs) -> None:
    if not bot:
        return
    lang = await _get_user_lang(user_id)
    texts = TEXTS.get(lang, TEXTS["en"])
    template = texts.get(event)
    if not template:
        return

    if event == "deposit_received" and "hours" not in kwargs:
        if _db:
            maturity_str = await _db.get_setting("deposit_maturity_seconds")
            maturity = (
                int(float(maturity_str))
                if maturity_str
                else config.deposit_maturity_seconds
            )
        else:
            maturity = config.deposit_maturity_seconds
        kwargs["hours"] = maturity / 3600

    try:
        text = template.format(**kwargs)
        await bot.send_message(user_id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning("Failed to notify user %d: %s", user_id, e)


async def broadcast_message(user_ids: list[int], message_text: str) -> dict:
    if not bot:
        return {"sent": 0, "failed": 0}
    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, message_text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    return {"sent": sent, "failed": failed}
