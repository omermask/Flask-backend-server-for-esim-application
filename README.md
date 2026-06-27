# eSIM Ego Server

Production-grade backend API server for an eSIM (embedded SIM) digital marketplace. Built with Flask, PostgreSQL, Redis, and Celery, serving a multi-platform eSIM store with wallet payments, real-time updates, and a full admin panel.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![Flask](https://img.shields.io/badge/flask-3.1-black)](https://flask.palletsprojects.com)
[![PostgreSQL](https://img.shields.io/badge/postgresql-16-blue)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/redis-7-red)](https://redis.io)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/omermask/esim-ego-server?style=social)](https://github.com/omermask/esim-ego-server/stargazers)
[![CI](https://github.com/omermask/esim-ego-server/actions/workflows/ci.yml/badge.svg)](https://github.com/omermask/esim-ego-server/actions/workflows/ci.yml)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker)](https://github.com/omermask/esim-ego-server/pkgs/container/esim-ego-server)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Provider Integrations](#provider-integrations)
- [Authentication & Security](#authentication--security)
- [Database Schema](#database-schema)
- [Deployment](#deployment)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

eSIM Ego Server is the backend for a complete eSIM marketplace platform. Customers can browse data plans, purchase them via local payment methods (ZainCash, FIB, QiCard), and have eSIM profiles activated on their devices instantly.

The system supports:
- **Dual-mode inventory** — pre-purchased ICCIDs (bulk) and real-time on-demand activation
- **Wallet system** — user balances, deposits, freezes, and transactions
- **Multi-currency** — IQD, USD, and dynamic exchange rates
- **Multi-language** — 12 languages including Arabic, Kurdish, Turkish, Persian, and English
- **Admin panel API** — full CRUD for users, orders, plans, inventory, coupons, taxes, refunds, and more
- **Real-time notifications** — WebSocket-powered order and wallet updates

---

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Flutter App  │────▶│  eSIM Ego Server │────▶│   PostgreSQL    │
│  (Dashboard)  │     │   (Flask API)    │     │                 │
└──────────────┘     │                   │     └─────────────────┘
                     │  ┌─────────────┐  │     ┌─────────────────┐
┌──────────────┐     │  │   Celery    │◀┼────▶│      Redis      │
│  Web Client  │────▶│  │  (Workers)  │  │     │ (Cache/Queue)   │
└──────────────┘     │  └─────────────┘  │     └─────────────────┘
                     │                   │
┌──────────────┐     │  ┌─────────────┐  │     ┌─────────────────┐
│  Providers   │◀────┼──│  SocketIO   │  │     │   Firebase      │
│  (eSIM/SMS/  │     │  │  (Realtime) │  │     │  Cloud Msging   │
│   Payment)   │────▶│  └─────────────┘  │     └─────────────────┘
└──────────────┘     └──────────────────┘
```

**Request flow:**
1. Client authenticates via OTP/phone, receives JWT tokens
2. All subsequent requests include `Authorization: Bearer <access_token>`
3. Middleware validates token, enforces rate limits, checks IP whitelist (admin)
4. Route handler processes business logic via service layer
5. Response returned in unified format with automatic translation

---

## Tech Stack

| Category | Technology | Purpose |
|---|---|---|
| **Framework** | Flask 3.1 | Web server & API |
| **Database** | PostgreSQL 16 | Primary data store |
| **Cache & Queue** | Redis 7 | Token blacklist, rate limits, Celery broker, SocketIO MQ |
| **ORM** | SQLAlchemy 2.0 | Database abstraction |
| **Migrations** | Alembic 1.15 | Schema versioning (18 migrations) |
| **Task Queue** | Celery 5.5 | Async background jobs |
| **Real-time** | Flask-SocketIO | WebSocket events |
| **Auth** | JWT (HS256) + bcrypt + TOTP | Access/refresh tokens, 2FA |
| **Validation** | Pydantic 2.11 | Request/response validation |
| **Rate Limiting** | Flask-Limiter 3.10 | Redis-backed |
| **Push** | Firebase Cloud Messaging | Push notifications |
| **WSGI** | Gunicorn + gevent | Production server |
| **PDF** | fpdf2 | Invoices & reports |
| **Excel** | openpyxl | Report export |

---

## Features

### Customer Features
- Phone-based OTP registration/login
- Browse data plans with caching
- Create and pay for orders (wallet, ZainCash, FIB, QiCard)
- View order history and eSIM installation details
- Wallet: balance, deposits, transactions
- Support tickets with messaging
- Referral program with rewards
- Push notifications

### Admin Features
- **Dashboard** — revenue, orders, users, growth analytics
- **Orders** — list, filter, approve, cancel, reprocess
- **Users** — list, search, ban/unban, role management, wallet adjust
- **Plans** — CRUD, sort order, toggle active
- **Inventory** — ICCID management, bulk import, stats
- **Finance** — exchange rates, tax rates, coupons, refunds
- **Support** — ticket management, assign, close
- **Reports** — financial reports (PDF/XLSX)
- **Backups** — create, list, download, cleanup
- **Audit Log** — full admin action trail
- **System Settings** — dynamic config management
- **2FA** — TOTP two-factor authentication
- **Referral** — reward stats, settings

### Platform Features
- Multi-language (12 languages)
- Multi-currency with auto-fetch exchange rates
- Dual inventory mode (hybrid / inventory-only / on-demand-only)
- Idempotency guarantees for payments
- Rate limiting per endpoint group
- Comprehensive audit trail
- Provider plugin system (drop-in new providers)

---

## Quick Start

### Option A: Docker Compose (recommended)

```bash
git clone https://github.com/omermask/esim-ego-server.git
cd esim-ego-server
cp .env.example .env
# Edit .env with your secrets
docker compose up -d
```

This starts PostgreSQL, Redis, the Flask API (with auto-migration), Celery worker, and Celery beat — all with a single command.

### Option B: Manual Setup

#### Prerequisites
- Python 3.11+
- PostgreSQL 16+
- Redis 7+

#### 1. Clone & Setup

```bash
git clone https://github.com/omermask/esim-ego-server.git
cd esim-ego-server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials (database, Redis, secrets)
```

#### 3. Database

```bash
# Create PostgreSQL database
createdb esim_ego

# Run migrations
alembic upgrade head
```

#### 4. Run

```bash
# Development
python run.py

# Production
gunicorn -c gunicorn.conf.py 'app:create_app()'
```

### Verify

```bash
curl http://localhost:5000/health
# {"status":"healthy","database":"connected","redis":"connected"}
```

---

## Configuration

Key environment variables (see `.env.example` for full list):

| Variable | Required | Default | Description |
|---|---|---|---|
| `ENVIRONMENT` | No | `development` | `development`, `staging`, or `production` |
| `SECRET_KEY` | **Yes** | — | Min 32 characters |
| `API_KEYS_ENCRYPTION_KEY` | **Yes** | — | Min 16 characters |
| `DB_HOST` | **Yes** | `localhost` | PostgreSQL host |
| `DB_NAME` | **Yes** | `esim_ego` | Database name |
| `REDIS_HOST` | No | `localhost` | Redis host |
| `JWT_ACCESS_TOKEN_EXPIRY_MINUTES` | No | `15` | Access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRY_DAYS` | No | `7` | Refresh token TTL |
| `CORS_ORIGINS` | No | `*` | Comma-separated origins |
| `PURCHASE_MODE` | No | `hybrid` | `hybrid`, `inventory_only`, `on_demand_only` |
| `ADMIN_IP_WHITELIST` | No | — | CIDR ranges for admin endpoints |

### Rate Limits (configurable)
| Endpoint Group | Limit |
|---|---|
| Auth (`/auth/*`) | 5 requests/min |
| General API | 30 requests/min |
| Admin endpoints | 60 requests/min |

---

## API Reference

All endpoints are prefixed with `/api/v1`.

### Authentication

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Register with phone number |
| POST | `/auth/login` | Request OTP |
| POST | `/auth/verify-otp` | Verify OTP, get tokens |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/auth/logout` | Revoke tokens |

### Plans

| Method | Path | Description |
|---|---|---|
| GET | `/plans` | List active plans (cached 300s) |
| GET | `/plans/{id}` | Plan details |

### Orders

| Method | Path | Description |
|---|---|---|
| POST | `/orders` | Create order |
| GET | `/orders` | List user orders |
| GET | `/orders/{id}` | Order details |

### Wallet

| Method | Path | Description |
|---|---|---|
| GET | `/wallet` | Get balance |
| GET | `/wallet/transactions` | Transaction history |
| POST | `/wallet/deposit` | Request deposit |

### Payments

| Method | Path | Description |
|---|---|---|
| GET | `/payments/{id}` | Payment status |
| POST | `/payments/deposit/confirm` | Confirm deposit |
| POST | `/payments/{id}/cancel` | Cancel payment |

### Admin Users

| Method | Path | Description |
|---|---|---|
| GET | `/admin/users` | List users (paginated) |
| GET | `/admin/users/{id}` | User details |
| PUT | `/admin/users/{id}/role` | Change role |
| PUT | `/admin/users/{id}/ban` | Ban/unban user |

### Admin Orders

| Method | Path | Description |
|---|---|---|
| GET | `/admin/orders` | List orders (filtered) |
| GET | `/admin/orders/{id}` | Order details |
| PUT | `/admin/orders/{id}/status` | Update status |
| POST | `/admin/orders/{id}/cancel` | Cancel order |
| POST | `/admin/orders/{id}/reprocess` | Reprocess failed |

### Admin Plans

| Method | Path | Description |
|---|---|---|
| POST | `/admin/plans` | Create plan |
| PUT | `/admin/plans/{id}` | Update plan |
| DELETE | `/admin/plans/{id}` | Delete plan |
| PUT | `/admin/plans/{id}/toggle-active` | Toggle active |
| PUT | `/admin/plans/sort-order` | Reorder plans |

### Admin Finance

| Method | Path | Description |
|---|---|---|
| GET/POST | `/admin/exchange-rates` | List/create rates |
| PUT | `/admin/exchange-rates/{id}` | Update rate |
| GET/POST | `/admin/tax-rates` | List/create tax rates |
| GET/POST/DELETE | `/admin/coupons` | CRUD coupons |
| POST | `/admin/refund` | Process refund |
| GET | `/admin/wallet/adjust` | Adjust user wallet |

### Admin Reports & Analytics

| Method | Path | Description |
|---|---|---|
| GET | `/admin/analytics/dashboard` | Dashboard stats |
| GET | `/admin/analytics/revenue` | Revenue analytics |
| GET | `/admin/analytics/orders` | Order analytics |
| GET | `/admin/analytics/users` | User analytics |
| GET | `/admin/reports/financial` | Financial report (PDF/XLSX) |

### Admin Support

| Method | Path | Description |
|---|---|---|
| GET | `/admin/support/tickets` | List tickets |
| PUT | `/admin/support/tickets/{id}/status` | Open/close ticket |
| POST | `/admin/support/tickets/{id}/assign` | Assign to admin |

### Admin Backups

| Method | Path | Description |
|---|---|---|
| POST | `/admin/backup/create` | Create backup |
| GET | `/admin/backup/list` | List backups |
| GET | `/admin/backup/download/{id}` | Download backup |
| DELETE | `/admin/backup/{id}` | Delete backup |

### Inventory

| Method | Path | Description |
|---|---|---|
| GET | `/admin/inventory` | List inventory |
| POST | `/admin/inventory/import` | Bulk import ICCIDs |
| POST | `/admin/inventory/activate` | Activate specific ICCID |
| GET | `/admin/inventory/stats` | Inventory statistics |

### System & Settings

| Method | Path | Description |
|---|---|---|
| GET/POST/PUT/DELETE | `/admin/settings` | System settings CRUD |
| GET | `/admin/referral/stats` | Referral statistics |
| PUT | `/admin/referral/settings` | Update referral config |

### Callback Webhooks

| Method | Path | Source | Security |
|---|---|---|---|
| POST | `/esim/callback` | eSIM provider | HMAC signature |
| POST | `/callback/otpiq` | OTPIQ SMS | IP restrict + HMAC |

### WebSocket (SocketIO)

| Event | Direction | Description |
|---|---|---|
| `connect` | Client→Server | Auth via `Authorization` header |
| `order_update` | Server→Client | Real-time order status changes |
| `wallet_update` | Server→Client | Real-time balance changes |
| `push` | Server→Client | Push notification delivery |

---

## Provider Integrations — Plugin Architecture

The system is built with a **fully decoupled plugin architecture**. The core code never references any specific provider by name — it discovers them automatically at runtime. This means **any developer can add a new provider** (eSIM, SMS, or payment) by simply creating a single Python file in the right directory, without modifying any core code.

### How It Works

```
app/providers/
├── base.py              # Abstract base classes (ESIMProviderBase, SMSProviderBase, PaymentProviderBase)
├── registry.py           # Auto-discovery: scans directories, registers decorated classes
├── esim/
│   └── your_provider.py  # ← Drop a new file here, it's auto-loaded
├── payment/
│   └── your_provider.py  # ← Drop a new file here, it's auto-loaded
└── sms/
    └── your_provider.py  # ← Drop a new file here, it's auto-loaded
```

**To add a new provider, you only need to:**
1. Create a new Python file in the appropriate folder (e.g., `app/providers/esim/my_provider.py`)
2. Create a class that inherits from the base class (e.g., `ESIMProviderBase`)
3. Decorate it with the registration decorator (e.g., `@esim_provider("my_provider")`)
4. Add your API credentials to `.env` — done.

No modifications to routes, services, models, or configuration files are needed. The registry (`app/providers/registry.py`) uses `pkgutil.iter_modules` to scan for new files on startup and registers them automatically.

### Currently Integrated Providers

#### eSIM Providers
| Provider | File | Status | Features |
|---|---|---|---|
| **eSIMGo** | `app/providers/esim/esimgo.py` | ✅ Active | Catalogue, order, bundle activation, install details, usage callbacks |

*To add a new eSIM provider: create `app/providers/esim/your_company.py`, extend `ESIMProviderBase`, add `@esim_provider("your_company")`.*

#### SMS Providers
| Provider | File | Status | Features |
|---|---|---|---|
| **BulkSMSIraq** | `app/providers/sms/bulksmsiraq.py` | ✅ Active | OTP, SMS, balance check, 28 error codes, sandbox |
| **OTPIQ** | `app/providers/sms/otpiq.py` | ✅ Active | OTP, webhook callbacks, HMAC signing |

*To add a new SMS provider: create `app/providers/sms/your_company.py`, extend `SMSProviderBase`, add `@sms_provider("your_company")`.*

#### Payment Providers
| Provider | File | Status | Features |
|---|---|---|---|
| **ZainCash** | `app/providers/payment/zaincash.py` | ✅ Active | Iraqi mobile wallet, JWT-signed, UAT/Production |
| **FIB** | `app/providers/payment/fib.py` | ✅ Active | Fast Iraq Bank, OAuth2 client credentials |
| **QiCard (SuperQI)** | `app/providers/payment/superqi.py` | ✅ Active | Credit/debit card, full state machine, webhooks, refunds |

*To add a new payment provider: create `app/providers/payment/your_company.py`, extend `PaymentProviderBase`, add `@payment_provider("your_company")`.*

### Base Classes (what your provider must implement)

| Base Class | Required Methods |
|---|---|
| `ESIMProviderBase` | `activate_bundle()`, `get_bundle_status()`, `create_order()`, `get_install_details()`, `get_catalogue()`, `handle_usage_callback()` |
| `SMSProviderBase` | `send_otp()`, `send_sms()`, `verify_otp()`, `get_balance()` |
| `PaymentProviderBase` | `initiate_payment()`, `verify_webhook()` |

### Configuration

Once registered, the provider is selected dynamically at runtime via the admin settings:
```
ALLOWED_SMS_PROVIDERS=["bulksmsiraq","otpiq","your_new_provider"]
ALLOWED_ESIM_PROVIDERS=["esimgo","your_new_provider"]
ALLOWED_PAYMENT_PROVIDERS=["zaincash","qicard","fib","your_new_provider"]
```

Provider credentials are securely encrypted at rest using `API_KEYS_ENCRYPTION_KEY` and stored in the database. Each provider's API calls are fully logged to `EsimProviderTransaction` / `SMSProviderTransaction` for audit and debugging.

---

## Authentication & Security

### Token System

```
┌─────────┐     ┌───────────┐     ┌──────────┐
│  Phone   │────▶│ OTP Verify│────▶│  Tokens  │
│  Login   │     │  (3 tries)│     │ Access   │
└─────────┘     └───────────┘     │ (15 min) │
                                  │ Refresh  │
                                  │ (7 days) │
                                  └──────────┘
```

### Security Layers
1. **bcrypt** password hashing (12 rounds)
2. **JWT HS256** dual token (access + refresh)
3. **TOTP 2FA** via pyotp (optional, admin-only)
4. **Token blacklisting** via Redis
5. **Token versioning** — logout-all instantly invalidates all sessions
6. **Rate limiting** — per-endpoint-group
7. **IP whitelist** — CIDR-based admin access control
8. **Idempotency** — prevents duplicate payments
9. **Security headers** — `X-Content-Type-Options`, `X-Frame-Options`, no Server header
10. **HMAC verification** — callback webhook signing

---

## Database Schema

The database consists of 25+ tables managed through 18 Alembic migrations.

**Core tables:**
- `users`, `otp_codes`, `device_sessions`, `device_tokens`
- `plans`, `orders`, `order_items`, `payments`
- `wallets`, `wallet_transactions`, `wallet_freezes`
- `coupons`, `coupon_usages`, `tax_rates`, `exchange_rates`
- `esim_inventory`, `import_batches`, `esim_provider_transactions`
- `support_tickets`, `support_messages`
- `refunds`, `referral_rewards`
- `audit_logs`, `backup_records`, `system_settings`
- `notification_templates`, `idempotency_records`

Run `alembic upgrade head` to apply all migrations.

---

## Deployment

### Docker Compose (recommended)

```bash
docker compose up -d
```

Starts PostgreSQL, Redis, Flask API, Celery worker, and Celery beat. Configure via `.env`.

### Production (Gunicorn + System Services)

```bash
gunicorn -c gunicorn.conf.py 'app:create_app()'
```

Default config: 4 gevent workers, `0.0.0.0:5000`, 30s timeout.

### Required Services
- PostgreSQL 16+
- Redis 7+
- Celery worker (for background tasks)

```bash
celery -A app.celery_app worker --loglevel=info --concurrency=2
celery -A app.celery_app beat --loglevel=info
```

### Environment Checklist
| Check | Why |
|---|---|
| `SECRET_KEY` set | JWT signing, session security |
| `API_KEYS_ENCRYPTION_KEY` set | Provider credential encryption |
| Database created + migrated | Data persistence |
| Redis running | Rate limiting, token blacklist, Celery |
| `.env` excluded from git | Never commit secrets |

---

## Project Structure

```
esim-ego-server/
├── app/
│   ├── __init__.py          # Flask app factory, blueprint registration
│   ├── celery_app.py        # Celery application instance
│   ├── socketio.py          # WebSocket events
│   ├── core/
│   │   ├── constants.py     # App-wide constants
│   │   ├── database.py      # SQLAlchemy engine + session
│   │   ├── errors.py        # Custom error classes
│   │   ├── i18n.py          # Translation manager
│   │   ├── middleware.py     # Request/response middleware
│   │   ├── response.py      # Unified response format
│   │   ├── security.py      # JWT, bcrypt, TOTP, rate limiting
│   │   └── validators.py    # Pydantic request schemas
│   ├── models/              # SQLAlchemy models (21 files)
│   ├── routes/              # API route blueprints (17 files)
│   ├── services/            # Business logic layer (25 files)
│   ├── providers/           # Plugin-based integrations
│   │   ├── esim/            # eSIM activation providers
│   │   ├── payment/         # Payment gateway providers
│   │   └── sms/             # SMS/OTP providers
│   ├── tasks/               # Celery background tasks
│   └── translations/        # 12 language JSON files
├── alembic/                 # Database migrations (18 versions)
├── scripts/                 # Utility scripts
├── config.py                # Pydantic settings model
├── Dockerfile               # Production Docker image
├── docker-compose.yml       # Multi-service orchestration
├── run.py                   # Entry point (dev/prod)
├── gunicorn.conf.py         # Production server config
├── requirements.txt         # Python dependencies
├── .env.example             # Environment template
├── CONTRIBUTING.md          # Contribution guidelines
├── CODE_OF_CONDUCT.md       # Community standards
├── SECURITY.md              # Security policy
└── .github/                 # Issue templates & CI workflows
```

### Key Patterns

| Pattern | Description |
|---|---|
| **Service layer** | All business logic in `app/services/`, routes are thin |
| **Provider plugins** | Auto-discovered via decorators, zero config for new providers |
| **Unified response** | All endpoints return `{success, status, code, message, data, meta}` |
| **Auto-translation** | Error messages translated via `Accept-Language` header |
| **Pagination** | All list endpoints support `page`, `per_page` (max 100) |

---

## Contributing

Please read our [Contributing Guide](CONTRIBUTING.md) and [Code of Conduct](CODE_OF_CONDUCT.md) before submitting changes.

Quick overview:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines
- Write tests for new services
- Follow existing provider plugin pattern for new integrations
- Add translation keys for user-facing messages
- Run `alembic upgrade head` after pulling new migrations
- Format with `black` and lint with `flake8`

### Build the User & Admin Frontends
You can contribute by building frontend applications (mobile or web) that connect to this API. The server is fully API-driven — any client can consume it:

- **[Admin Dashboard](https://github.com/omermask/esim-ego-dashboard)** — A Flutter admin panel. Contribute new screens, widgets, or features.
- **User App** — Build a customer-facing app (Flutter, React Native, or web) using the public endpoints (`/auth`, `/plans`, `/orders`, `/wallet`, etc.)
- **New Admin Features** — Add new admin screens or improve existing ones in the Flutter dashboard

The API is fully documented in [API.md](API.md) with all endpoints, request/response formats, and authentication details. Any HTTP client can integrate.

### Reporting Security Issues
See [SECURITY.md](SECURITY.md) for our responsible disclosure policy.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Author

**omer jasim** — [oj33593@gmail.com](mailto:oj33593@gmail.com)

---

## Support

- **Issues**: [GitHub Issues](https://github.com/omermask/esim-ego-server/issues)
- **Documentation**: See [API.md](API.md) for endpoint details
- **Admin Dashboard**: Available at [esim-ego-dashboard](https://github.com/omermask/esim-ego-dashboard) (Flutter)
