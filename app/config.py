import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    admin_ids: list[int] = field(default_factory=list)

    wallet_mnemonics: str = field(
        default_factory=lambda: os.getenv("WALLET_MNEMONICS", "")
    )
    toncenter_api_key: str = field(
        default_factory=lambda: os.getenv("TONCENTER_API_KEY", "")
    )
    ton_network: str = field(
        default_factory=lambda: os.getenv("TON_NETWORK", "mainnet")
    )

    min_deposit: float = 10.0
    profit_percent: float = 10.0
    deposit_maturity_seconds: int = 36000
    referral_percent: float = 10.0
    min_withdrawal: float = 1.0
    withdrawal_fee: float = 0.01

    webapp_url: str = field(default_factory=lambda: os.getenv("WEBAPP_URL", ""))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = 8000

    def __post_init__(self) -> None:
        raw = os.getenv("ADMIN_IDS", "")
        self.admin_ids = [
            int(x.strip()) for x in raw.split(",") if x.strip().isdigit()
        ]
        for attr, env_key, tp in [
            ("min_deposit", "MIN_DEPOSIT", float),
            ("profit_percent", "PROFIT_PERCENT", float),
            ("deposit_maturity_seconds", "DEPOSIT_MATURITY_SECONDS", int),
            ("referral_percent", "REFERRAL_PERCENT", float),
            ("min_withdrawal", "MIN_WITHDRAWAL", float),
            ("withdrawal_fee", "WITHDRAWAL_FEE", float),
            ("port", "PORT", int),
        ]:
            val = os.getenv(env_key)
            if val:
                setattr(self, attr, tp(val))

    @property
    def toncenter_base_url(self) -> str:
        if self.ton_network == "mainnet":
            return "https://toncenter.com/api/v2"
        return "https://testnet.toncenter.com/api/v2"


config = Config()
