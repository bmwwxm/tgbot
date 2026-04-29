# 🏦 GoodMoney — Telegram Mini App Investment Bot

AI-powered arbitrage investment platform built as a Telegram Mini App with TON blockchain integration.

## Features

- **Telegram Mini App** — Beautiful dark-themed SPA with full mobile support
- **TON Deposits** — Via TON Connect wallet or manual transfer with comment
- **Auto Payouts** — +10% profit automatically credited after 10 hours
- **Auto Withdrawals** — Instant withdrawals to any TON wallet
- **Referral Program** — 10% commission from referral profits
- **Admin Panel** — Statistics, user management, settings, broadcast, balance adjustmentss
- **Feed Channel** — Second bot publishes real-time payouts to a public channel
- **Multi-language** — Russian and English with auto-detection
- **Fully Configurable** — All parameters adjustable via admin panel or `.env`

## Architecture

```
┌─────────────────────────────────────────┐
│           Telegram Mini App             │
│  (HTML/CSS/JS + TON Connect SDK)        │
├─────────────────────────────────────────┤
│           FastAPI Backend               │
│  ┌──────────┐  ┌──────────────────┐     │
│  │ REST API │  │  Telegram Bot    │     │
│  │ /api/*   │  │  (notifications) │     │
│  └──────────┘  └──────────────────┘     │
│  ┌──────────┐  ┌──────────────────┐     │
│  │ Scheduler│  │   Feed Bot       │     │
│  │ (payouts)│  │   (channel feed) │     │
│  └──────────┘  └──────────────────┘     │
│  ┌──────────────────────────────────┐   │
│  │   TON Service (toncenter API)    │   │
│  └──────────────────────────────────┘   │
│  ┌──────────────────────────────────┐   │
│  │      SQLite Database             │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Telegram Bot token (from [@BotFather](https://t.me/BotFather))
- TON wallet with mnemonics
- TON Center API key (free at [toncenter.com](https://toncenter.com/))
- HTTPS domain (required for Telegram Mini App)

### 1. Clone & Install

```bash
git clone <repo-url>
cd ton-invest-bot
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your values
```

**Required settings:**
| Variable | Description |
|---|---|
| `BOT_TOKEN` | Main Telegram bot token |
| `WALLET_MNEMONICS` | 24-word mnemonic of the hot wallet |
| `WEBAPP_URL` | Public HTTPS URL where the app is hosted |
| `ADMIN_IDS` | Your Telegram user ID (comma-separated) |

**Optional (Feed Channel):**
| Variable | Description |
|---|---|
| `FEED_BOT_TOKEN` | Second bot token for the feed channel |
| `FEED_CHANNEL_ID` | Channel/group ID for payout feed |
| `FEED_LANG` | Feed language: `ru` or `en` |

### 3. Run

```bash
python -m app.main
```

The server starts on `http://0.0.0.0:8000`. The Mini App frontend is served at the root URL.

### 4. Set up the Telegram Bot

1. Open [@BotFather](https://t.me/BotFather)
2. Send `/mybots` → select your bot → **Bot Settings** → **Menu Button** → Set URL to your `WEBAPP_URL`
3. Or use the inline WebApp button that appears with `/start`

### 5. Set up the Feed Channel (optional)

1. Create a channel/group in Telegram
2. Create a second bot via @BotFather
3. Add the second bot as admin to the channel
4. Set `FEED_BOT_TOKEN` and `FEED_CHANNEL_ID` in `.env`

## Docker

```bash
docker build -t goodmoney .
docker run -d --name goodmoney \
  --env-file .env \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  goodmoney
```

## Investment Settings

All settings can be changed on the fly via the **Admin Panel** inside the Mini App:

| Setting | Default | Description |
|---|---|---|
| Min Deposit | 10 TON | Minimum deposit amount |
| Profit | 10% | Return on deposit |
| Maturity | 36000s (10h) | Time until payout |
| Referral | 10% | Commission from referral profits |
| Min Withdrawal | 1 TON | Minimum withdrawal |
| Withdrawal Fee | 0.01 TON | Fixed fee per withdrawal |

## Admin Panel

Access the admin panel through the bottom navigation (visible only to admins).

**Features:**
- 📊 **Statistics** — Users, deposits, withdrawals, wallet balance
- 👥 **Users** — View, block/unblock, promote/demote admins, adjust balances
- ⚙️ **Settings** — Change all investment parameters on the fly
- 📢 **Broadcast** — Send messages to all active users

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/user/register` | Register/login user |
| GET | `/api/user/me` | Get current user |
| GET | `/api/deposit/info` | Get deposit address & comment |
| GET | `/api/deposit/history` | Deposit history |
| GET | `/api/deposit/active` | Active deposits |
| POST | `/api/withdraw/create` | Request withdrawal |
| GET | `/api/withdraw/history` | Withdrawal history |
| GET | `/api/referral/info` | Referral link & stats |
| GET | `/api/admin/stats` | Admin statistics |
| GET | `/api/admin/users` | Admin user list |
| POST | `/api/admin/settings` | Update settings |
| POST | `/api/admin/broadcast` | Send broadcast |
| POST | `/api/admin/block` | Block/unblock user |
| POST | `/api/admin/grant` | Grant/revoke admin |
| POST | `/api/admin/balance` | Adjust user balance |

## Security

- Telegram WebApp `initData` validation (HMAC-SHA256)
- Admin access controlled by `ADMIN_IDS` and database flag
- Wallet mnemonics stored only in `.env` (never committed)
- Transaction deduplication via `processed_transactions` table

## License

MIT
