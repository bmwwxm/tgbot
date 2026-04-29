import logging
import time
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(self.dsn, min_size=2, max_size=10)
        await self._create_tables()

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def _create_tables(self) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                language TEXT DEFAULT 'en',
                balance DOUBLE PRECISION DEFAULT 0.0,
                total_deposited DOUBLE PRECISION DEFAULT 0.0,
                total_withdrawn DOUBLE PRECISION DEFAULT 0.0,
                total_earned DOUBLE PRECISION DEFAULT 0.0,
                referrer_id BIGINT DEFAULT NULL,
                referral_earnings DOUBLE PRECISION DEFAULT 0.0,
                deposit_comment TEXT UNIQUE NOT NULL,
                withdraw_address TEXT DEFAULT '',
                is_blocked INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                created_at DOUBLE PRECISION NOT NULL,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id)
            )""")

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                amount DOUBLE PRECISION NOT NULL,
                profit DOUBLE PRECISION DEFAULT 0.0,
                tx_hash TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at DOUBLE PRECISION NOT NULL,
                matures_at DOUBLE PRECISION NOT NULL,
                paid_at DOUBLE PRECISION DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )""")

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                amount DOUBLE PRECISION NOT NULL,
                fee DOUBLE PRECISION DEFAULT 0.0,
                to_address TEXT NOT NULL,
                tx_hash TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at DOUBLE PRECISION NOT NULL,
                completed_at DOUBLE PRECISION DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )""")

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )""")

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_transactions (
                tx_hash TEXT PRIMARY KEY,
                processed_at DOUBLE PRECISION NOT NULL
            )""")

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS public_feed (
                id SERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                amount DOUBLE PRECISION DEFAULT 0.0,
                profit DOUBLE PRECISION DEFAULT 0.0,
                matures_at DOUBLE PRECISION DEFAULT 0.0,
                is_fake INTEGER DEFAULT 0,
                created_at DOUBLE PRECISION NOT NULL
            )""")

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS mines_games (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                bet DOUBLE PRECISION NOT NULL,
                mines_count INTEGER NOT NULL DEFAULT 5,
                field TEXT NOT NULL,
                revealed TEXT NOT NULL DEFAULT '[]',
                multiplier DOUBLE PRECISION DEFAULT 1.0,
                status TEXT DEFAULT 'active',
                server_seed TEXT NOT NULL,
                client_seed TEXT NOT NULL DEFAULT '',
                nonce INTEGER NOT NULL DEFAULT 0,
                created_at DOUBLE PRECISION NOT NULL,
                finished_at DOUBLE PRECISION DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )""")

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_tasks (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                task_id TEXT NOT NULL,
                completed_at DOUBLE PRECISION NOT NULL,
                reward DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                UNIQUE(user_id, task_id)
            )""")
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS crash_games (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                bet DOUBLE PRECISION NOT NULL,
                crash_point DOUBLE PRECISION NOT NULL,
                cashout_at DOUBLE PRECISION DEFAULT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                server_seed TEXT NOT NULL,
                seed_hash TEXT NOT NULL,
                payout DOUBLE PRECISION DEFAULT 0.0,
                created_at DOUBLE PRECISION NOT NULL,
                finished_at DOUBLE PRECISION DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )""")
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS pvp_lobbies (
                id SERIAL PRIMARY KEY,
                creator_id BIGINT NOT NULL,
                bet DOUBLE PRECISION NOT NULL,
                max_players INTEGER NOT NULL DEFAULT 2,
                status TEXT NOT NULL DEFAULT 'waiting',
                winner_id BIGINT DEFAULT NULL,
                winner_number DOUBLE PRECISION DEFAULT NULL,
                commission DOUBLE PRECISION NOT NULL DEFAULT 0.05,
                server_seed TEXT NOT NULL,
                seed_hash TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL,
                finished_at DOUBLE PRECISION DEFAULT NULL,
                FOREIGN KEY (creator_id) REFERENCES users(user_id)
            )""")
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS pvp_players (
                id SERIAL PRIMARY KEY,
                lobby_id INTEGER NOT NULL,
                user_id BIGINT NOT NULL,
                roll DOUBLE PRECISION DEFAULT NULL,
                joined_at DOUBLE PRECISION NOT NULL,
                UNIQUE(lobby_id, user_id),
                FOREIGN KEY (lobby_id) REFERENCES pvp_lobbies(id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )""")
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS contest_submissions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                platform TEXT NOT NULL,
                video_url TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                views_count INTEGER NOT NULL DEFAULT 0,
                last_views INTEGER NOT NULL DEFAULT 0,
                total_paid DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                has_link BOOLEAN NOT NULL DEFAULT FALSE,
                admin_note TEXT NOT NULL DEFAULT '',
                created_at DOUBLE PRECISION NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                UNIQUE(user_id, video_url)
            )""")

    def _row_to_dict(self, row: asyncpg.Record | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def _rows_to_list(self, rows: list[asyncpg.Record]) -> list[dict[str, Any]]:
        return [dict(r) for r in rows]

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
        assert self.pool is not None
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO users
                       (user_id, username, first_name, language,
                        deposit_comment, referrer_id, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                    user_id, username, first_name, language,
                    deposit_comment, referrer_id, time.time(),
                )
            return True
        except asyncpg.UniqueViolationError:
            return False

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1", user_id
            )
        return self._row_to_dict(row)

    async def update_user(self, user_id: int, **kwargs: Any) -> None:
        assert self.pool is not None
        sets = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(kwargs))
        vals = list(kwargs.values()) + [user_id]
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"UPDATE users SET {sets} WHERE user_id = ${len(kwargs)+1}", *vals
            )

    async def add_balance(self, user_id: int, delta: float) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                delta, user_id,
            )

    async def deduct_balance_safe(self, user_id: int, amount: float) -> bool:
        """Atomically deduct balance only if sufficient funds. Returns True on success."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET balance = balance - $1 WHERE user_id = $2 AND balance >= $1",
                amount, user_id,
            )
        return result.split()[-1] != "0"

    async def add_balance_field(self, user_id: int, field: str, delta: float) -> None:
        """Atomically increment a numeric user field (total_earned, referral_earnings, etc)."""
        assert self.pool is not None
        allowed = {"total_earned", "total_withdrawn", "referral_earnings", "total_deposited"}
        if field not in allowed:
            raise ValueError(f"Field {field} not allowed")
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"UPDATE users SET {field} = {field} + $1 WHERE user_id = $2",
                delta, user_id,
            )

    async def get_user_count(self) -> int:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) as c FROM users")
        return row["c"] if row else 0

    async def get_all_users(
        self, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit, offset,
            )
        return self._rows_to_list(rows)

    async def get_active_user_ids(self) -> list[int]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id FROM users WHERE is_blocked = 0"
            )
        return [r["user_id"] for r in rows]

    async def get_referrals(self, user_id: int) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, username, first_name, total_deposited, created_at "
                "FROM users WHERE referrer_id = $1 ORDER BY created_at DESC",
                user_id,
            )
        return self._rows_to_list(rows)

    async def get_user_by_comment(self, comment: str) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE deposit_comment = $1", comment
            )
        return self._row_to_dict(row)

    async def get_admin_ids(self) -> list[int]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id FROM users WHERE is_admin = 1"
            )
        return [r["user_id"] for r in rows]

    # ── Deposits ───────────────────────────────────────────

    async def add_deposit(
        self,
        user_id: int,
        amount: float,
        tx_hash: str,
        maturity_seconds: int,
    ) -> int:
        assert self.pool is not None
        now = time.time()
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO deposits
                   (user_id, amount, tx_hash, status, created_at, matures_at)
                   VALUES ($1, $2, $3, 'pending', $4, $5) RETURNING id""",
                user_id, amount, tx_hash, now, now + maturity_seconds,
            )
            await conn.execute(
                "UPDATE users SET total_deposited = total_deposited + $1 WHERE user_id = $2",
                amount, user_id,
            )
        return row["id"] if row else 0

    async def claim_matured_deposits(self) -> list[dict[str, Any]]:
        """Atomically claim matured deposits by setting status to 'processing'.
        Returns only newly claimed deposits, preventing double-payout."""
        assert self.pool is not None
        now = time.time()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "UPDATE deposits SET status = 'processing' WHERE status = 'pending' AND matures_at <= $1 RETURNING *",
                now,
            )
        return self._rows_to_list(rows)

    async def mark_deposit_paid(self, deposit_id: int, profit: float) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE deposits SET status='paid', profit=$1, paid_at=$2 WHERE id=$3",
                profit, time.time(), deposit_id,
            )

    async def get_user_deposits(self, user_id: int) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM deposits WHERE user_id = $1 ORDER BY created_at DESC",
                user_id,
            )
        return self._rows_to_list(rows)

    async def has_active_deposit(self, user_id: int) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM deposits WHERE user_id = $1 AND status IN ('pending', 'processing') LIMIT 1",
                user_id,
            )
        return row is not None

    async def get_deposits_stats(self) -> dict[str, Any]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT
                    COUNT(*) as total_count,
                    COALESCE(SUM(amount), 0) as total_amount,
                    COALESCE(SUM(CASE WHEN status='paid' THEN profit ELSE 0 END), 0) as total_profit,
                    COUNT(CASE WHEN status='pending' THEN 1 END) as pending_count
                   FROM deposits"""
            )
        return dict(row) if row else {}

    # ── Withdrawals ────────────────────────────────────────

    async def add_withdrawal(
        self, user_id: int, amount: float, fee: float, to_address: str
    ) -> int:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO withdrawals
                   (user_id, amount, fee, to_address, status, created_at)
                   VALUES ($1, $2, $3, $4, 'pending', $5) RETURNING id""",
                user_id, amount, fee, to_address, time.time(),
            )
        return row["id"] if row else 0

    async def mark_withdrawal_sent(self, wid: int, tx_hash: str) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE withdrawals SET status='sent', tx_hash=$1, completed_at=$2 WHERE id=$3",
                tx_hash, time.time(), wid,
            )

    async def mark_withdrawal_failed(self, wid: int) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE withdrawals SET status='failed', completed_at=$1 WHERE id=$2",
                time.time(), wid,
            )

    async def fail_withdrawal_and_refund(self, wid: int, user_id: int, amount: float) -> None:
        """Atomically mark withdrawal as failed and refund the balance."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE withdrawals SET status='failed', completed_at=$1 WHERE id=$2",
                    time.time(), wid,
                )
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                    amount, user_id,
                )

    async def claim_pending_withdrawals(self) -> list[dict[str, Any]]:
        """Atomically claim pending withdrawals for processing."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "UPDATE withdrawals SET status='processing' WHERE status='pending' RETURNING *"
            )
        return self._rows_to_list(rows)

    async def count_recent_withdrawals(self, user_id: int, seconds: int = 60) -> int:
        """Count recent withdrawal requests for rate limiting."""
        assert self.pool is not None
        since = time.time() - seconds
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as c FROM withdrawals WHERE user_id = $1 AND created_at > $2",
                user_id, since,
            )
        return row["c"] if row else 0

    async def get_user_withdrawals(self, user_id: int) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM withdrawals WHERE user_id=$1 ORDER BY created_at DESC",
                user_id,
            )
        return self._rows_to_list(rows)

    async def get_withdrawals_stats(self) -> dict[str, Any]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT
                    COUNT(*) as total_count,
                    COALESCE(SUM(CASE WHEN status='sent' THEN amount ELSE 0 END), 0) as total_sent
                   FROM withdrawals"""
            )
        return dict(row) if row else {}

    async def get_today_stats(self) -> dict[str, Any]:
        assert self.pool is not None
        today_start = time.time() - (time.time() % 86400)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT
                    (SELECT COUNT(*) FROM users WHERE created_at >= $1) as today_users,
                    (SELECT COUNT(*) FROM deposits WHERE created_at >= $1) as today_deposits,
                    (SELECT COALESCE(SUM(amount), 0) FROM deposits WHERE created_at >= $1) as today_deposit_amount,
                    (SELECT COUNT(*) FROM withdrawals WHERE created_at >= $1) as today_withdrawals,
                    (SELECT COALESCE(SUM(amount), 0) FROM withdrawals WHERE created_at >= $1 AND status='sent') as today_withdrawn,
                    (SELECT COUNT(*) FROM withdrawals WHERE status='pending') as pending_withdrawals,
                    (SELECT COALESCE(SUM(balance), 0) FROM users) as total_balance
                """,
                today_start,
            )
        return dict(row) if row else {}

    async def search_users(self, query: str) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            try:
                uid = int(query)
                rows = await conn.fetch(
                    "SELECT * FROM users WHERE user_id = $1", uid
                )
            except ValueError:
                rows = await conn.fetch(
                    "SELECT * FROM users WHERE LOWER(username) LIKE $1 OR LOWER(first_name) LIKE $1 ORDER BY created_at DESC LIMIT 50",
                    f"%{query.lower()}%",
                )
        return self._rows_to_list(rows)

    async def get_all_withdrawals(self, status: str = "pending", limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT w.*, u.username, u.first_name
                   FROM withdrawals w
                   LEFT JOIN users u ON w.user_id = u.user_id
                   WHERE w.status = $1
                   ORDER BY w.created_at DESC LIMIT $2 OFFSET $3""",
                status, limit, offset,
            )
        return self._rows_to_list(rows)

    async def get_all_deposits(self, status: str = "pending", limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            if status == "all":
                rows = await conn.fetch(
                    """SELECT d.*, u.username, u.first_name
                       FROM deposits d
                       LEFT JOIN users u ON d.user_id = u.user_id
                       ORDER BY d.created_at DESC LIMIT $1 OFFSET $2""",
                    limit, offset,
                )
            else:
                rows = await conn.fetch(
                    """SELECT d.*, u.username, u.first_name
                       FROM deposits d
                       LEFT JOIN users u ON d.user_id = u.user_id
                       WHERE d.status = $1
                       ORDER BY d.created_at DESC LIMIT $2 OFFSET $3""",
                    status, limit, offset,
                )
        return self._rows_to_list(rows)

    async def get_user_games(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, bet, mines_count, status, multiplier, created_at, finished_at FROM mines_games WHERE user_id = $1 ORDER BY id DESC LIMIT $2",
                user_id, limit,
            )
        return self._rows_to_list(rows)

    async def get_user_tasks(self, user_id: int) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM user_tasks WHERE user_id = $1 ORDER BY completed_at DESC",
                user_id,
            )
        return self._rows_to_list(rows)

    # ── Processed Transactions ─────────────────────────────

    async def is_tx_processed(self, tx_hash: str) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM processed_transactions WHERE tx_hash=$1", tx_hash
            )
        return row is not None

    async def mark_tx_processed(self, tx_hash: str) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO processed_transactions (tx_hash, processed_at) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                tx_hash, time.time(),
            )

    async def credit_incoming_tx_safe(self, tx_hash: str, user_id: int, amount: float) -> bool:
        """Atomically mark tx as processed and credit balance. Returns False if already processed."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                result = await conn.execute(
                    "INSERT INTO processed_transactions (tx_hash, processed_at) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    tx_hash, time.time(),
                )
                if result.split()[-1] == "0":
                    return False
                await conn.execute(
                    "UPDATE users SET balance = balance + $1, total_deposited = total_deposited + $1 WHERE user_id = $2",
                    amount, user_id,
                )
                return True

    # ── Settings ───────────────────────────────────────────

    async def get_setting(self, key: str) -> str | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM settings WHERE key=$1", key
            )
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO settings (key, value) VALUES ($1, $2)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                key, value,
            )

    async def get_all_settings(self) -> dict[str, str]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in rows}

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
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO public_feed
                   (event_type, display_name, amount, profit, matures_at, is_fake, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                event_type, display_name, amount, profit, matures_at,
                1 if is_fake else 0, time.time(),
            )
        return row["id"] if row else 0

    async def get_feed(self, limit: int = 20) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, event_type, display_name, amount, profit, matures_at, created_at
                   FROM public_feed ORDER BY created_at DESC LIMIT $1""",
                limit,
            )
        return self._rows_to_list(rows)

    # ── Mines Games ────────────────────────────────────────

    async def create_mines_game(
        self, user_id: int, bet: float, mines_count: int,
        field: str, server_seed: str, client_seed: str, nonce: int,
    ) -> int:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO mines_games
                   (user_id, bet, mines_count, field, server_seed, client_seed, nonce, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id""",
                user_id, bet, mines_count, field, server_seed, client_seed, nonce, time.time(),
            )
        return row["id"] if row else 0

    async def start_mines_game_safe(
        self, user_id: int, bet: float, mines_count: int,
        field: str, server_seed: str, client_seed: str, nonce: int,
    ) -> int | None:
        """Atomically check no active game, deduct bet, and create game.
        Returns game_id or None if active game exists or insufficient balance."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    "SELECT id FROM mines_games WHERE user_id = $1 AND status IN ('active', 'cashing_out') FOR UPDATE",
                    user_id,
                )
                if existing:
                    return None
                result = await conn.execute(
                    "UPDATE users SET balance = balance - $1 WHERE user_id = $2 AND balance >= $1",
                    bet, user_id,
                )
                if result.split()[-1] == "0":
                    return None
                row = await conn.fetchrow(
                    """INSERT INTO mines_games
                       (user_id, bet, mines_count, field, server_seed, client_seed, nonce, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id""",
                    user_id, bet, mines_count, field, server_seed, client_seed, nonce, time.time(),
                )
                return row["id"] if row else None

    async def get_active_mines_game(self, user_id: int) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM mines_games WHERE user_id = $1 AND status = 'active' ORDER BY id DESC LIMIT 1",
                user_id,
            )
        return self._row_to_dict(row)

    async def update_mines_game(self, game_id: int, **kwargs: Any) -> None:
        assert self.pool is not None
        sets = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(kwargs))
        vals = list(kwargs.values()) + [game_id]
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"UPDATE mines_games SET {sets} WHERE id = ${len(kwargs)+1}", *vals
            )

    async def reveal_mines_cell_safe(self, user_id: int, cell: int) -> dict[str, Any] | str | None:
        """Atomically reveal a cell in the active mines game using row-level lock.
        Returns dict with result, 'already_revealed' string, or None if no game."""
        import json as _json

        GRID = 25

        def _calc_mult(mines_count: int, revealed_count: int) -> float:
            if revealed_count == 0:
                return 1.0
            safe = GRID - mines_count
            prob = 1.0
            for i in range(revealed_count):
                prob *= (safe - i) / (GRID - i)
            if prob <= 0:
                return 0.0
            return round(0.97 / prob, 2)

        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT * FROM mines_games WHERE user_id = $1 AND status = 'active' ORDER BY id DESC LIMIT 1 FOR UPDATE",
                    user_id,
                )
                if not row:
                    return None
                game = dict(row)
                revealed = _json.loads(game["revealed"])
                if cell in revealed:
                    return "already_revealed"

                mines = _json.loads(game["field"])
                revealed.append(cell)
                hit_mine = cell in mines

                if hit_mine:
                    await conn.execute(
                        "UPDATE mines_games SET revealed=$1, status='lost', multiplier=0.0, finished_at=$2 WHERE id=$3",
                        _json.dumps(revealed), time.time(), game["id"],
                    )
                    return {"game": game, "revealed": revealed, "hit_mine": True, "all_safe": False, "multiplier": 0.0}

                new_mult = _calc_mult(game["mines_count"], len(revealed))
                safe_cells = GRID - game["mines_count"]
                all_safe = len(revealed) >= safe_cells

                if all_safe:
                    payout = game["bet"] * new_mult
                    await conn.execute(
                        "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                        payout, user_id,
                    )
                    await conn.execute(
                        "UPDATE mines_games SET revealed=$1, multiplier=$2, status='won', finished_at=$3 WHERE id=$4",
                        _json.dumps(revealed), new_mult, time.time(), game["id"],
                    )
                    return {"game": game, "revealed": revealed, "hit_mine": False, "all_safe": True, "multiplier": new_mult}

                await conn.execute(
                    "UPDATE mines_games SET revealed=$1, multiplier=$2 WHERE id=$3",
                    _json.dumps(revealed), new_mult, game["id"],
                )
                return {"game": game, "revealed": revealed, "hit_mine": False, "all_safe": False, "multiplier": new_mult}

    async def claim_mines_cashout(self, user_id: int) -> dict[str, Any] | None:
        """Atomically claim active game for cashout. Returns game or None if no active game."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE mines_games SET status = 'cashing_out'
                   WHERE id = (
                       SELECT id FROM mines_games
                       WHERE user_id = $1 AND status = 'active'
                       ORDER BY id DESC LIMIT 1
                   ) AND status = 'active'
                   RETURNING *""",
                user_id,
            )
        return self._row_to_dict(row)

    async def get_mines_history(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, bet, mines_count, multiplier, status, created_at, finished_at
                   FROM mines_games WHERE user_id = $1 ORDER BY id DESC LIMIT $2""",
                user_id, limit,
            )
        return self._rows_to_list(rows)

    # ── Tasks ──────────────────────────────────────────────

    async def get_completed_tasks(self, user_id: int) -> list[str]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT task_id FROM user_tasks WHERE user_id = $1", user_id
            )
        return [r["task_id"] for r in rows]

    async def complete_task(self, user_id: int, task_id: str, reward: float) -> bool:
        """Mark task as completed and add reward to balance. Returns False if already done."""
        assert self.pool is not None
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO user_tasks (user_id, task_id, completed_at, reward) VALUES ($1, $2, $3, $4)",
                        user_id, task_id, time.time(), reward,
                    )
                    await conn.execute(
                        "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                        reward, user_id,
                    )
            return True
        except asyncpg.UniqueViolationError:
            return False

    # ── Contest ────────────────────────────────────────────

    async def add_contest_submission(
        self, user_id: int, platform: str, video_url: str,
    ) -> int | None:
        assert self.pool is not None
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """INSERT INTO contest_submissions
                       (user_id, platform, video_url, created_at, updated_at)
                       VALUES ($1, $2, $3, $4, $4) RETURNING id""",
                    user_id, platform, video_url, time.time(),
                )
            return row["id"] if row else None
        except asyncpg.UniqueViolationError:
            return None

    async def get_user_submissions(self, user_id: int) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM contest_submissions WHERE user_id = $1 ORDER BY created_at DESC",
                user_id,
            )
        return self._rows_to_list(rows)

    async def get_all_contest_submissions(
        self, status: str = "all", limit: int = 50, offset: int = 0,
    ) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            if status == "all":
                rows = await conn.fetch(
                    """SELECT cs.*, u.username, u.first_name
                       FROM contest_submissions cs
                       LEFT JOIN users u ON cs.user_id = u.user_id
                       ORDER BY cs.created_at DESC LIMIT $1 OFFSET $2""",
                    limit, offset,
                )
            else:
                rows = await conn.fetch(
                    """SELECT cs.*, u.username, u.first_name
                       FROM contest_submissions cs
                       LEFT JOIN users u ON cs.user_id = u.user_id
                       WHERE cs.status = $1
                       ORDER BY cs.created_at DESC LIMIT $2 OFFSET $3""",
                    status, limit, offset,
                )
        return self._rows_to_list(rows)

    async def update_contest_submission(
        self, submission_id: int, **kwargs: Any,
    ) -> dict[str, Any] | None:
        assert self.pool is not None
        sets = []
        vals: list[Any] = []
        i = 1
        for k, v in kwargs.items():
            sets.append(f"{k} = ${i}")
            vals.append(v)
            i += 1
        vals.append(time.time())
        sets.append(f"updated_at = ${i}")
        i += 1
        vals.append(submission_id)
        query = f"UPDATE contest_submissions SET {', '.join(sets)} WHERE id = ${i} RETURNING *"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *vals)
        return self._row_to_dict(row)

    async def contest_payout(self, submission_id: int, user_id: int, amount: float, new_views: int) -> bool:
        """Atomically pay contest reward and update submission."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE contest_submissions SET views_count = $1, total_paid = total_paid + $2, last_views = $1, updated_at = $3 WHERE id = $4",
                    new_views, amount, time.time(), submission_id,
                )
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                    amount, user_id,
                )
        return True

    # ── Crash game methods ──────────────────────────────────

    async def get_active_crash_game(self, user_id: int) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM crash_games WHERE user_id = $1 AND status = 'active'",
                user_id,
            )
        return self._row_to_dict(row)

    async def start_crash_game_safe(
        self, user_id: int, bet: float, crash_point: float,
        server_seed: str, seed_hash: str,
    ) -> int | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT user_id FROM users WHERE user_id = $1 AND balance >= $2 FOR UPDATE",
                    user_id, bet,
                )
                if not row:
                    return None
                existing = await conn.fetchrow(
                    "SELECT id FROM crash_games WHERE user_id = $1 AND status = 'active'",
                    user_id,
                )
                if existing:
                    return None
                await conn.execute(
                    "UPDATE users SET balance = balance - $1 WHERE user_id = $2",
                    bet, user_id,
                )
                r = await conn.fetchrow(
                    """INSERT INTO crash_games
                       (user_id, bet, crash_point, server_seed, seed_hash, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6)
                       RETURNING id""",
                    user_id, bet, crash_point, server_seed, seed_hash, time.time(),
                )
                return r["id"] if r else None

    async def crash_cashout_safe(
        self, user_id: int, cashout_multiplier: float,
    ) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                game = await conn.fetchrow(
                    """UPDATE crash_games SET status = 'cashing_out'
                       WHERE user_id = $1 AND status = 'active'
                       RETURNING *""",
                    user_id,
                )
                if not game:
                    return None
                game = dict(game)
                if cashout_multiplier >= game["crash_point"]:
                    await conn.execute(
                        "UPDATE crash_games SET status = 'crashed', finished_at = $1 WHERE id = $2",
                        time.time(), game["id"],
                    )
                    return {
                        "too_late": True,
                        "crash_point": game["crash_point"],
                        "server_seed": game["server_seed"],
                    }
                payout = game["bet"] * cashout_multiplier
                await conn.execute(
                    """UPDATE crash_games
                       SET status = 'cashout', cashout_at = $1, payout = $2, finished_at = $3
                       WHERE id = $4""",
                    cashout_multiplier, payout, time.time(), game["id"],
                )
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                    payout, user_id,
                )
                return {
                    "too_late": False,
                    "crash_point": game["crash_point"],
                    "cashout_at": cashout_multiplier,
                    "payout": payout,
                    "bet": game["bet"],
                    "server_seed": game["server_seed"],
                }

    async def crash_auto_resolve(self, user_id: int) -> dict[str, Any] | None:
        """Auto-resolve a crash game that crashed (player didn't cashout in time)."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                game = await conn.fetchrow(
                    """UPDATE crash_games SET status = 'crashed', finished_at = $1
                       WHERE user_id = $2 AND status = 'active'
                       RETURNING *""",
                    time.time(), user_id,
                )
                return self._row_to_dict(game)

    async def get_crash_history(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, bet, crash_point, cashout_at, status, payout, seed_hash, server_seed, created_at
                   FROM crash_games WHERE user_id = $1
                   ORDER BY created_at DESC LIMIT $2""",
                user_id, limit,
            )
        return self._rows_to_list(rows)

    # ── PvP methods ─────────────────────────────────────────

    async def create_pvp_lobby_safe(
        self, creator_id: int, bet: float, max_players: int,
        server_seed: str, seed_hash: str, commission: float,
    ) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT user_id FROM users WHERE user_id = $1 AND balance >= $2 FOR UPDATE",
                    creator_id, bet,
                )
                if not row:
                    return None
                await conn.execute(
                    "UPDATE users SET balance = balance - $1 WHERE user_id = $2",
                    bet, creator_id,
                )
                now = time.time()
                lobby = await conn.fetchrow(
                    """INSERT INTO pvp_lobbies
                       (creator_id, bet, max_players, server_seed, seed_hash, commission, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                    creator_id, bet, max_players, server_seed, seed_hash, commission, now,
                )
                lobby_id = lobby["id"]
                await conn.execute(
                    "INSERT INTO pvp_players (lobby_id, user_id, joined_at) VALUES ($1, $2, $3)",
                    lobby_id, creator_id, now,
                )
                return {"lobby_id": lobby_id}

    async def join_pvp_lobby_safe(
        self, lobby_id: int, user_id: int,
    ) -> dict[str, Any] | str | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                lobby = await conn.fetchrow(
                    "SELECT * FROM pvp_lobbies WHERE id = $1 AND status = 'waiting' FOR UPDATE",
                    lobby_id,
                )
                if not lobby:
                    return None
                lobby = dict(lobby)
                existing = await conn.fetchrow(
                    "SELECT id FROM pvp_players WHERE lobby_id = $1 AND user_id = $2",
                    lobby_id, user_id,
                )
                if existing:
                    return "already_joined"
                players = await conn.fetch(
                    "SELECT * FROM pvp_players WHERE lobby_id = $1",
                    lobby_id,
                )
                if len(players) >= lobby["max_players"]:
                    return None
                balance_row = await conn.fetchrow(
                    "SELECT user_id FROM users WHERE user_id = $1 AND balance >= $2 FOR UPDATE",
                    user_id, lobby["bet"],
                )
                if not balance_row:
                    return "insufficient"
                await conn.execute(
                    "UPDATE users SET balance = balance - $1 WHERE user_id = $2",
                    lobby["bet"], user_id,
                )
                await conn.execute(
                    "INSERT INTO pvp_players (lobby_id, user_id, joined_at) VALUES ($1, $2, $3)",
                    lobby_id, user_id, time.time(),
                )
                new_players = await conn.fetch(
                    "SELECT * FROM pvp_players WHERE lobby_id = $1",
                    lobby_id,
                )
                return {"lobby": lobby, "players": [dict(p) for p in new_players]}

    async def add_pvp_bot_player(
        self, lobby_id: int, fake_uid: int, display_name: str,
    ) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                lobby = await conn.fetchrow(
                    "SELECT * FROM pvp_lobbies WHERE id = $1 AND status = 'waiting' FOR UPDATE",
                    lobby_id,
                )
                if not lobby:
                    return False
                players = await conn.fetch(
                    "SELECT * FROM pvp_players WHERE lobby_id = $1", lobby_id,
                )
                if len(players) >= lobby["max_players"]:
                    return False
                # Ensure fake user exists in users table
                import secrets as _sec
                fake_comment = f"bot_{_sec.token_hex(8)}"
                await conn.execute(
                    """INSERT INTO users (user_id, balance, first_name, is_blocked, deposit_comment, created_at)
                       VALUES ($1, 0, $2, 0, $3, $4)
                       ON CONFLICT (user_id) DO NOTHING""",
                    fake_uid, display_name, fake_comment, time.time(),
                )
                await conn.execute(
                    "INSERT INTO pvp_players (lobby_id, user_id, joined_at) VALUES ($1, $2, $3)",
                    lobby_id, fake_uid, time.time(),
                )
                return True

    async def get_pvp_lobby(self, lobby_id: int) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM pvp_lobbies WHERE id = $1", lobby_id,
            )
        return self._row_to_dict(row)

    async def get_pvp_players(self, lobby_id: int) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT pp.*, u.username, u.first_name
                   FROM pvp_players pp
                   LEFT JOIN users u ON pp.user_id = u.user_id
                   WHERE pp.lobby_id = $1 ORDER BY pp.joined_at""",
                lobby_id,
            )
        return self._rows_to_list(rows)

    async def get_pvp_lobbies_waiting(self, limit: int = 20) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM pvp_lobbies WHERE status = 'waiting' ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        return self._rows_to_list(rows)

    async def resolve_pvp_lobby(
        self, lobby_id: int, winner_id: int, winner_roll: float,
        rolls: list[tuple[int, float]], prize: float,
    ) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                lobby = await conn.fetchrow(
                    "SELECT * FROM pvp_lobbies WHERE id = $1 AND status = 'waiting' FOR UPDATE",
                    lobby_id,
                )
                if not lobby:
                    return False
                await conn.execute(
                    """UPDATE pvp_lobbies
                       SET status = 'finished', winner_id = $1, winner_number = $2, finished_at = $3
                       WHERE id = $4""",
                    winner_id, winner_roll, time.time(), lobby_id,
                )
                for uid, roll in rolls:
                    await conn.execute(
                        "UPDATE pvp_players SET roll = $1 WHERE lobby_id = $2 AND user_id = $3",
                        roll, lobby_id, uid,
                    )
                # Credit prize to winner (only if real player)
                if winner_id > 0:
                    await conn.execute(
                        "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                        prize, winner_id,
                    )
                return True

    async def get_pvp_history(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT l.*, pp.roll as my_roll,
                          (SELECT COUNT(*) FROM pvp_players WHERE lobby_id = l.id) as player_count
                   FROM pvp_lobbies l
                   JOIN pvp_players pp ON pp.lobby_id = l.id AND pp.user_id = $1
                   WHERE l.status = 'finished'
                   ORDER BY l.finished_at DESC LIMIT $2""",
                user_id, limit,
            )
        return self._rows_to_list(rows)
