import os
import time
from typing import Any

import aiosqlite


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()

    async def close(self) -> None:
        if self.db:
            await self.db.close()

    async def _create_tables(self) -> None:
        assert self.db is not None
        await self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                language TEXT DEFAULT 'en',
                balance REAL DEFAULT 0.0,
                total_deposited REAL DEFAULT 0.0,
                total_withdrawn REAL DEFAULT 0.0,
                total_earned REAL DEFAULT 0.0,
                referrer_id INTEGER DEFAULT NULL,
                referral_earnings REAL DEFAULT 0.0,
                deposit_comment TEXT UNIQUE NOT NULL,
                withdraw_address TEXT DEFAULT '',
                is_blocked INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                profit REAL DEFAULT 0.0,
                tx_hash TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at REAL NOT NULL,
                matures_at REAL NOT NULL,
                paid_at REAL DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                fee REAL DEFAULT 0.0,
                to_address TEXT NOT NULL,
                tx_hash TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at REAL NOT NULL,
                completed_at REAL DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS processed_transactions (
                tx_hash TEXT PRIMARY KEY,
                processed_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS public_feed (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                amount REAL DEFAULT 0.0,
                profit REAL DEFAULT 0.0,
                matures_at REAL DEFAULT 0.0,
                is_fake INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mines_games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                bet REAL NOT NULL,
                mines_count INTEGER NOT NULL DEFAULT 5,
                field TEXT NOT NULL,
                revealed TEXT NOT NULL DEFAULT '[]',
                multiplier REAL DEFAULT 1.0,
                status TEXT DEFAULT 'active',
                server_seed TEXT NOT NULL,
                client_seed TEXT NOT NULL DEFAULT '',
                nonce INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                finished_at REAL DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            """
        )
        await self.db.commit()

    # ── Users ──────────────────────────────────────────────

    async def add_user(
        self,
        user_id: int,
        username: str,
        first_name: str,
        deposit_comment: str,
        language: str = "en",
        referrer_id: int | None = None,
    ) -> bool:
        assert self.db is not None
        try:
            await self.db.execute(
                """INSERT INTO users
                   (user_id, username, first_name, language,
                    deposit_comment, referrer_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id, username, first_name, language,
                    deposit_comment, referrer_id, time.time(),
                ),
            )
            await self.db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        assert self.db is not None
        cur = await self.db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def update_user(self, user_id: int, **kwargs: Any) -> None:
        assert self.db is not None
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [user_id]
        await self.db.execute(
            f"UPDATE users SET {sets} WHERE user_id = ?", vals
        )
        await self.db.commit()

    async def add_balance(self, user_id: int, delta: float) -> None:
        assert self.db is not None
        await self.db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (delta, user_id),
        )
        await self.db.commit()

    async def deduct_balance_safe(self, user_id: int, amount: float) -> bool:
        """Atomically deduct balance only if sufficient funds. Returns True on success."""
        assert self.db is not None
        cur = await self.db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
            (amount, user_id, amount),
        )
        await self.db.commit()
        return cur.rowcount > 0

    async def add_balance_field(self, user_id: int, field: str, delta: float) -> None:
        """Atomically increment a numeric user field (total_earned, referral_earnings, etc)."""
        assert self.db is not None
        allowed = {"total_earned", "total_withdrawn", "referral_earnings", "total_deposited"}
        if field not in allowed:
            raise ValueError(f"Field {field} not allowed")
        await self.db.execute(
            f"UPDATE users SET {field} = {field} + ? WHERE user_id = ?",
            (delta, user_id),
        )
        await self.db.commit()

    async def get_user_count(self) -> int:
        assert self.db is not None
        cur = await self.db.execute("SELECT COUNT(*) as c FROM users")
        row = await cur.fetchone()
        return row["c"] if row else 0

    async def get_all_users(
        self, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        assert self.db is not None
        cur = await self.db.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_active_user_ids(self) -> list[int]:
        assert self.db is not None
        cur = await self.db.execute(
            "SELECT user_id FROM users WHERE is_blocked = 0"
        )
        return [r["user_id"] for r in await cur.fetchall()]

    async def get_referrals(self, user_id: int) -> list[dict[str, Any]]:
        assert self.db is not None
        cur = await self.db.execute(
            "SELECT user_id, username, first_name, total_deposited, created_at "
            "FROM users WHERE referrer_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_user_by_comment(self, comment: str) -> dict[str, Any] | None:
        assert self.db is not None
        cur = await self.db.execute(
            "SELECT * FROM users WHERE deposit_comment = ?", (comment,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_admin_ids(self) -> list[int]:
        assert self.db is not None
        cur = await self.db.execute(
            "SELECT user_id FROM users WHERE is_admin = 1"
        )
        return [r["user_id"] for r in await cur.fetchall()]

    # ── Deposits ───────────────────────────────────────────

    async def add_deposit(
        self,
        user_id: int,
        amount: float,
        tx_hash: str,
        maturity_seconds: int,
    ) -> int:
        assert self.db is not None
        now = time.time()
        cur = await self.db.execute(
            """INSERT INTO deposits
               (user_id, amount, tx_hash, status, created_at, matures_at)
               VALUES (?, ?, ?, 'pending', ?, ?)""",
            (user_id, amount, tx_hash, now, now + maturity_seconds),
        )
        await self.db.execute(
            "UPDATE users SET total_deposited = total_deposited + ? WHERE user_id = ?",
            (amount, user_id),
        )
        await self.db.commit()
        return cur.lastrowid or 0

    async def claim_matured_deposits(self) -> list[dict[str, Any]]:
        """Atomically claim matured deposits by setting status to 'processing'.
        Returns only newly claimed deposits, preventing double-payout."""
        assert self.db is not None
        now = time.time()
        await self.db.execute(
            "UPDATE deposits SET status = 'processing' WHERE status = 'pending' AND matures_at <= ?",
            (now,),
        )
        await self.db.commit()
        cur = await self.db.execute(
            "SELECT * FROM deposits WHERE status = 'processing'"
        )
        return [dict(r) for r in await cur.fetchall()]

    async def mark_deposit_paid(self, deposit_id: int, profit: float) -> None:
        assert self.db is not None
        await self.db.execute(
            "UPDATE deposits SET status='paid', profit=?, paid_at=? WHERE id=?",
            (profit, time.time(), deposit_id),
        )
        await self.db.commit()

    async def get_user_deposits(self, user_id: int) -> list[dict[str, Any]]:
        assert self.db is not None
        cur = await self.db.execute(
            "SELECT * FROM deposits WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_deposits_stats(self) -> dict[str, Any]:
        assert self.db is not None
        cur = await self.db.execute(
            """SELECT
                COUNT(*) as total_count,
                COALESCE(SUM(amount), 0) as total_amount,
                COALESCE(SUM(CASE WHEN status='paid' THEN profit ELSE 0 END), 0) as total_profit,
                COUNT(CASE WHEN status='pending' THEN 1 END) as pending_count
               FROM deposits"""
        )
        row = await cur.fetchone()
        return dict(row) if row else {}

    # ── Withdrawals ────────────────────────────────────────

    async def add_withdrawal(
        self, user_id: int, amount: float, fee: float, to_address: str
    ) -> int:
        assert self.db is not None
        cur = await self.db.execute(
            """INSERT INTO withdrawals
               (user_id, amount, fee, to_address, status, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?)""",
            (user_id, amount, fee, to_address, time.time()),
        )
        await self.db.commit()
        return cur.lastrowid or 0

    async def mark_withdrawal_sent(self, wid: int, tx_hash: str) -> None:
        assert self.db is not None
        await self.db.execute(
            "UPDATE withdrawals SET status='sent', tx_hash=?, completed_at=? WHERE id=?",
            (tx_hash, time.time(), wid),
        )
        await self.db.commit()

    async def mark_withdrawal_failed(self, wid: int) -> None:
        assert self.db is not None
        await self.db.execute(
            "UPDATE withdrawals SET status='failed', completed_at=? WHERE id=?",
            (time.time(), wid),
        )
        await self.db.commit()

    async def fail_withdrawal_and_refund(self, wid: int, user_id: int, amount: float) -> None:
        """Atomically mark withdrawal as failed and refund the balance."""
        assert self.db is not None
        await self.db.execute(
            "UPDATE withdrawals SET status='failed', completed_at=? WHERE id=?",
            (time.time(), wid),
        )
        await self.db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id),
        )
        await self.db.commit()

    async def claim_pending_withdrawals(self) -> list[dict[str, Any]]:
        """Atomically claim pending withdrawals for processing."""
        assert self.db is not None
        await self.db.execute(
            "UPDATE withdrawals SET status='processing' WHERE status='pending'"
        )
        await self.db.commit()
        cur = await self.db.execute(
            "SELECT * FROM withdrawals WHERE status='processing' ORDER BY created_at"
        )
        return [dict(r) for r in await cur.fetchall()]

    async def count_recent_withdrawals(self, user_id: int, seconds: int = 60) -> int:
        """Count recent withdrawal requests for rate limiting."""
        assert self.db is not None
        since = time.time() - seconds
        cur = await self.db.execute(
            "SELECT COUNT(*) as c FROM withdrawals WHERE user_id = ? AND created_at > ?",
            (user_id, since),
        )
        row = await cur.fetchone()
        return row["c"] if row else 0

    async def get_user_withdrawals(self, user_id: int) -> list[dict[str, Any]]:
        assert self.db is not None
        cur = await self.db.execute(
            "SELECT * FROM withdrawals WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_withdrawals_stats(self) -> dict[str, Any]:
        assert self.db is not None
        cur = await self.db.execute(
            """SELECT
                COUNT(*) as total_count,
                COALESCE(SUM(CASE WHEN status='sent' THEN amount ELSE 0 END), 0) as total_sent
               FROM withdrawals"""
        )
        row = await cur.fetchone()
        return dict(row) if row else {}

    # ── Processed Transactions ─────────────────────────────

    async def is_tx_processed(self, tx_hash: str) -> bool:
        assert self.db is not None
        cur = await self.db.execute(
            "SELECT 1 FROM processed_transactions WHERE tx_hash=?", (tx_hash,)
        )
        return await cur.fetchone() is not None

    async def mark_tx_processed(self, tx_hash: str) -> None:
        assert self.db is not None
        await self.db.execute(
            "INSERT OR IGNORE INTO processed_transactions (tx_hash, processed_at) VALUES (?,?)",
            (tx_hash, time.time()),
        )
        await self.db.commit()

    # ── Settings ───────────────────────────────────────────

    async def get_setting(self, key: str) -> str | None:
        assert self.db is not None
        cur = await self.db.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        )
        row = await cur.fetchone()
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        assert self.db is not None
        await self.db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
            (key, value),
        )
        await self.db.commit()

    async def get_all_settings(self) -> dict[str, str]:
        assert self.db is not None
        cur = await self.db.execute("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in await cur.fetchall()}

    # ── Public Feed ────────────────────────────────────────

    async def add_feed_entry(
        self,
        event_type: str,
        display_name: str,
        amount: float,
        profit: float = 0.0,
        matures_at: float = 0.0,
        is_fake: bool = False,
    ) -> int:
        assert self.db is not None
        cur = await self.db.execute(
            """INSERT INTO public_feed
               (event_type, display_name, amount, profit, matures_at, is_fake, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_type, display_name, amount, profit, matures_at,
             1 if is_fake else 0, time.time()),
        )
        await self.db.commit()
        return cur.lastrowid or 0

    async def get_feed(self, limit: int = 20) -> list[dict[str, Any]]:
        assert self.db is not None
        cur = await self.db.execute(
            """SELECT id, event_type, display_name, amount, profit, matures_at, created_at
               FROM public_feed ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]

    # ── Mines Games ────────────────────────────────────────

    async def create_mines_game(
        self, user_id: int, bet: float, mines_count: int,
        field: str, server_seed: str, client_seed: str, nonce: int,
    ) -> int:
        assert self.db is not None
        cur = await self.db.execute(
            """INSERT INTO mines_games
               (user_id, bet, mines_count, field, server_seed, client_seed, nonce, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, bet, mines_count, field, server_seed, client_seed, nonce, time.time()),
        )
        await self.db.commit()
        return cur.lastrowid or 0

    async def get_active_mines_game(self, user_id: int) -> dict[str, Any] | None:
        assert self.db is not None
        cur = await self.db.execute(
            "SELECT * FROM mines_games WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def update_mines_game(self, game_id: int, **kwargs: Any) -> None:
        assert self.db is not None
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [game_id]
        await self.db.execute(
            f"UPDATE mines_games SET {sets} WHERE id = ?", vals
        )
        await self.db.commit()

    async def get_mines_history(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        assert self.db is not None
        cur = await self.db.execute(
            """SELECT id, bet, mines_count, multiplier, status, created_at, finished_at
               FROM mines_games WHERE user_id = ? ORDER BY id DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]
