"""TON blockchain service — wallet operations, balance checks, transfers."""

import asyncio
import base64
import hashlib
import logging
from typing import Any

import aiohttp
from tonsdk.contract.wallet import Wallets, WalletVersionEnum
from tonsdk.utils import to_nano, from_nano, bytes_to_b64str

from app.config import config

logger = logging.getLogger(__name__)


class TonService:
    def __init__(self) -> None:
        self._wallet_address: str = ""
        self._wallet: Any = None
        self._keypair: Any = None
        self._session: aiohttp.ClientSession | None = None

    async def init(self) -> None:
        self._session = aiohttp.ClientSession()
        if config.wallet_mnemonics:
            mnemonics = config.wallet_mnemonics.split()
            _mnemonics, _pub, _priv, wallet = Wallets.from_mnemonics(
                mnemonics, WalletVersionEnum.v4r2, 0
            )
            self._wallet = wallet
            self._wallet_address = wallet.address.to_string(
                is_user_friendly=True, is_bounceable=False, is_url_safe=True
            )
            logger.info("Wallet initialized: %s", self._wallet_address)

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    @property
    def wallet_address(self) -> str:
        return self._wallet_address

    def generate_deposit_comment(self, user_id: int) -> str:
        raw = f"goodmoney_{user_id}_{hashlib.md5(str(user_id).encode()).hexdigest()[:8]}"
        return raw

    async def _api_call(
        self, method: str, params: dict[str, Any] | None = None, use_post: bool = False,
    ) -> dict[str, Any]:
        assert self._session is not None
        url = f"{config.toncenter_base_url}/{method}"
        headers: dict[str, str] = {}
        if config.toncenter_api_key:
            headers["X-API-Key"] = config.toncenter_api_key
        for attempt in range(3):
            try:
                if use_post:
                    async with self._session.post(
                        url, json=params or {}, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp:
                        data = await resp.json()
                else:
                    async with self._session.get(
                        url, params=params or {}, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp:
                        data = await resp.json()
                if data.get("ok"):
                    return data.get("result", {})
                logger.warning("API error (%s): %s", method, data)
                return {}
            except Exception as e:
                logger.warning("API call attempt %d failed: %s", attempt + 1, e)
                if attempt < 2:
                    await asyncio.sleep(2)
        return {}

    async def get_wallet_balance(self) -> float:
        if not self._wallet_address:
            return 0.0
        result = await self._api_call(
            "getAddressBalance", {"address": self._wallet_address}
        )
        if isinstance(result, str) and result.isdigit():
            return float(from_nano(int(result), "ton"))
        if isinstance(result, (int, float)):
            return float(from_nano(int(result), "ton"))
        return 0.0

    async def get_transactions(
        self, limit: int = 20, lt: int | None = None, hash_val: str | None = None
    ) -> list[dict[str, Any]]:
        if not self._wallet_address:
            return []
        params: dict[str, Any] = {
            "address": self._wallet_address,
            "limit": limit,
        }
        if lt and hash_val:
            params["lt"] = lt
            params["hash"] = hash_val
        result = await self._api_call("getTransactions", params)
        if isinstance(result, list):
            return result
        return []

    def parse_incoming_transactions(
        self, transactions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        incoming: list[dict[str, Any]] = []
        for tx in transactions:
            in_msg = tx.get("in_msg", {})
            if not in_msg:
                continue
            value = int(in_msg.get("value", "0"))
            if value <= 0:
                continue
            source = in_msg.get("source", "")
            if not source:
                continue
            comment = ""
            msg_data = in_msg.get("msg_data", {})
            if msg_data.get("@type") == "msg.dataText":
                try:
                    comment = base64.b64decode(msg_data.get("text", "")).decode(
                        "utf-8", errors="ignore"
                    )
                except Exception:
                    comment = ""
            tx_hash = base64.b64encode(
                bytes.fromhex(tx.get("transaction_id", {}).get("hash", ""))
            ).decode() if tx.get("transaction_id", {}).get("hash") else ""
            if not tx_hash:
                lt_val = tx.get("transaction_id", {}).get("lt", "")
                tx_hash = f"lt_{lt_val}"
            incoming.append(
                {
                    "tx_hash": tx_hash,
                    "from_address": source,
                    "amount": float(from_nano(value, "ton")),
                    "comment": comment,
                    "utime": tx.get("utime", 0),
                }
            )
        return incoming

    async def send_ton(self, to_address: str, amount: float, comment: str = "") -> str:
        if not self._wallet:
            raise RuntimeError("Wallet not initialized")

        seqno_result = await self._api_call(
            "runGetMethod",
            {"address": self._wallet_address, "method": "seqno", "stack": []},
            use_post=True,
        )
        seqno = 0
        if isinstance(seqno_result, dict):
            stack = seqno_result.get("stack", [])
            if stack and len(stack) > 0:
                val = stack[0]
                if isinstance(val, list) and len(val) >= 2:
                    seqno = int(val[1], 16)
                elif isinstance(val, (int, str)):
                    seqno = int(val)

        nano_amount = to_nano(amount, "ton")
        body = None
        if comment:
            from tonsdk.boc import begin_cell

            body = (
                begin_cell()
                .store_uint(0, 32)
                .store_string(comment)
                .end_cell()
            )

        query = self._wallet.create_transfer_message(
            to_addr=to_address,
            amount=nano_amount,
            seqno=seqno,
            payload=body,
        )
        boc = bytes_to_b64str(query["message"].to_boc(False))

        result = await self._send_boc(boc)
        if result:
            logger.info("Sent %.4f TON to %s", amount, to_address)
            return result
        raise RuntimeError(f"Failed to send {amount} TON to {to_address}")

    async def _send_boc(self, boc: str) -> str:
        assert self._session is not None
        url = f"{config.toncenter_base_url}/sendBoc"
        headers: dict[str, str] = {}
        if config.toncenter_api_key:
            headers["X-API-Key"] = config.toncenter_api_key
        try:
            async with self._session.post(
                url,
                json={"boc": boc},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return data.get("result", {}).get("hash", "sent")
                logger.error("sendBoc error: %s", data)
        except Exception as e:
            logger.error("sendBoc exception: %s", e)
        return ""


ton_service = TonService()
