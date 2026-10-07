# Meridian Backend

Meridian Backend is a commerce API. It uses FastAPI, async SQLAlchemy, and PostgreSQL. The HTTP endpoints register users, issue access tokens, and create, list, and get orders. A WebSocket endpoint supports real-time JSON messages. The voice module contains a separate simulation. Before you create an order, make sure that its customer and products exist in the database.

## Contents

- [Current capabilities](#current-capabilities)
- [Architecture and rationale](#architecture-and-rationale)
- [Project structure](#project-structure)
- [How an order request works](#how-an-order-request-works)
- [Authentication and access](#authentication-and-access)
- [Real-time connections](#real-time-connections)
- [Voice simulation](#voice-simulation)
- [Database relationships](#database-relationships)
- [Sessions and transactions](#sessions-and-transactions)
- [Configuration and local setup](#configuration-and-local-setup)
- [API usage](#api-usage)
- [Schema migrations](#schema-migrations)
- [Testing and checks](#testing-and-checks)
- [Errors and request logging](#errors-and-request-logging)
- [Current limitations](#current-limitations)
- [Future work and learning roadmap](#future-work-and-learning-roadmap)

## Current capabilities

| Endpoint | Access | Behavior |
| --- | --- | --- |
| `GET /health` | Public | Returns application health. Does not check the database |
| `POST /register` | Public | Creates an active user with the `CUSTOMER` role |
| `POST /login` | Public | Returns a JWT access token |
| `GET /me` | Active user | Returns the current user's public fields |
| `GET /admin/check` | Active admin | Confirms admin access |
| `GET /orders` | Public | Lists all stored orders |
| `POST /orders` | Active user | Creates or replays an order. Requires `Idempotency-key` |
| `GET /orders/{order_id}` | Active user | Gets an order for a linked customer or an admin |
| `WS /realtime/ws` | Public | Supports ready, echo, ping, acknowledgement, and session resume messages |

The order service also has methods for paid orders, revenue, customer filters, and the order with the highest value. These methods have no HTTP endpoints.

The seed script creates a customer and two products. Customer and product repositories exist. Customer and product CRUD routes are not registered. `api/routes/customer.py` is empty.

Payment, inventory, and shipping services simulate external operations. The order routes do not call them. Voice processing is also simulated and has no registered endpoint.

## Architecture and rationale

The application uses a **layered architecture within one backend application**. Each layer has one main function. You can change business calculations, HTTP handling, and database access separately.

```mermaid
flowchart TD
    Client[HTTP client] --> Route[API route and Pydantic validation]
    Route --> Service[OrderService: business operations]
    Service --> Repo[OrderRepository: queries and persistence]
    Repo --> DB[(PostgreSQL)]
    Repo --> Mapper[Database mapper]
    Mapper --> Domain[Domain objects]
    Domain --> Service
    Service --> Response[API mapper and response schema]
    Response --> Client
```

### 1. API routes: the HTTP boundary

`api/routes/` defines URLs, request parameters, response schemas, and HTTP success codes. Routes await service methods and convert the results into API responses.

**Reason:** you can change an endpoint or response format without changes to SQL or money calculations. Central exception handlers convert domain errors to HTTP responses.

### 2. Schemas: the public data contract

`schemas/` contains Pydantic models. These models validate input and serialize output. For example, `CreateOrder` requires at least one item. Each quantity must be a positive integer. Clients cannot set the initial order status through this schema.

**Reason:** the API can reject invalid requests before it calls a service. You can change response fields separately from table definitions. Keep database constraints and service checks as well as request validation.

### 3. Domain models: business data and calculations

`models/` contains Python dataclasses such as `Order`, `OrderItem`, `Customer`, and `Product`. These models calculate order subtotal, tax, and total. They also define order status changes. Monetary calculations use `Decimal`.

**Reason:** you can run and test calculations without FastAPI or a database session. Create money values from strings, such as `Decimal("25.00")`. This prevents binary floating-point approximations.

### 4. Services: coordinate a business operation

`services/order_service.py` checks that the customer and products exist. It creates a domain order. It then asks the repository to save the order. A missing customer or product causes a domain exception.

**Reason:** routes stay small. You can use business operations outside HTTP requests. The service depends on the concrete `OrderRepository` class. Thus, the service still depends on part of the database implementation.

### 5. Repositories: database access

`repositories/order_repository.py` controls SQLAlchemy queries and database writes. It loads the required relationships before it returns domain objects. It flushes new orders to the database. `OrderService.create_order()` controls commit and rollback.

**Reason:** SQL and relationship loading stay in one place. The other layers use domain objects. They do not read ORM attributes that can cause more database queries.

### 6. Database models and mappers: the storage boundary

`db/models/` defines tables, columns, foreign keys, and ORM relationships. `db/mappers.py` converts loaded ORM instances into domain dataclasses. `api/mappers.py` separately converts domain objects into response schemas.

```text
Database row -> ORM model -> domain object -> API response schema -> JSON
```

**Reason for three representations:** database models define how to store data. Domain models define business behavior. API schemas define what clients can send and receive. This design needs more classes and mapping code. A smaller CRUD-only application can use fewer representations. This project uses separate representations to support learning and independent business logic.

### 7. Dependency injection: assemble objects for a request

`api/dependencies.py` builds the dependency chain:

```text
Request -> AsyncSession -> OrderRepository -> OrderService -> route
```

**Reason:** routes do not create database connections. One module creates the required objects. You can replace dependencies in tests.

## Project structure

```text
src/meridian_backend/
├── main.py                 # App assembly, lifespan, routers, middleware
├── api/
│   ├── routes/             # Auth, order, health, and WebSocket endpoints
│   ├── dependencies.py     # Session, repository, and service injection
│   ├── exception_handlers.py
│   └── mappers.py          # Domain objects -> API responses
├── core/                   # Settings, security, exceptions, logging, middleware
├── db/
│   ├── base.py             # Shared SQLAlchemy declarative base
│   ├── session.py          # Async engine and session factory
│   ├── models/             # ORM table definitions
│   └── mappers.py          # ORM objects -> domain objects
├── models/                 # Domain dataclasses and calculations
├── repositories/           # SQL queries and persistence
├── schemas/                # Pydantic request/response contracts
├── services/               # Auth, orders, and simulated external operations
├── realtime/               # Connections, sessions, message queues, and replay
├── voice/                  # Simulated audio, VAD, STT, LLM, and TTS
├── scripts/seed.py         # Development customer and products
└── tests/                  # API and unit tests
migrations/                 # Alembic environment and versioned migrations
alembic.ini                 # Alembic configuration
```

## How an order request works

For `POST /orders`:

1. Middleware creates a request ID. FastAPI validates the JSON against `CreateOrder`.
2. Authentication checks the bearer token and loads an active user in a separate database session.
3. Dependencies provide the order service and repositories with one shared session.
4. The service starts a transaction. It claims the idempotency key for the user and `CREATE_ORDER` operation.
5. If the claim already exists, the service returns its stored order. It does not compare the new request body.
6. For a new claim, the service loads the customer and products. A missing reference causes HTTP 404 and transaction rollback.
7. The service creates a pending domain order with a new UUID. The repository creates and flushes ORM order and item objects.
8. The transaction commits the order and idempotency record together.
9. The API mapper builds the response. Money fields are serialized as strings. The request session then closes.

Read operations use `selectinload()` before database mapping. This loads customers, order items, and their products. The mapper does not need implicit relationship loading with async sessions.

A repeated successful request returns HTTP 201 and the same order. Use a new idempotency key for a new order.

## Authentication and access

`AuthService` hashes passwords with pwdlib's recommended Argon2 hasher. Registration requires a name, a valid email address, and a password of 8 to 128 characters. User email addresses are unique.

Login returns `access_token` and `token_type: "bearer"`. Tokens contain the user UUID in `sub` and an expiration in `exp`. The default algorithm is `HS256`. The default token lifetime is 30 minutes.

Send the token in `Authorization: Bearer <token>`. Protected routes validate the token, load the user, and check that the user is active. Admin access also requires the `ADMIN` role.

Registration does not create a customer or set `users.customer_id`. There is no API to link a user to a customer or change a user's role. Set these values through a separate database administration workflow when required.

Order access is currently different for each route:

- `GET /orders` is public and returns all orders.
- `POST /orders` requires an active user. It does not check that the requested customer belongs to that user.
- `GET /orders/{order_id}` permits admins and users whose `customer_id` matches the order's customer. Other users receive HTTP 403.

The application has no refresh token, logout, password reset, or token revocation endpoint.

## Real-time connections

Connect to `ws://127.0.0.1:8000/realtime/ws`. The endpoint does not require a bearer token. It accepts JSON messages with this format:

```json
{"type": "ping", "sequence": 1, "data": {}}
```

`type` is a string. `sequence` is a non-negative integer. `data` is an object and defaults to `{}`.

| Message | Result |
| --- | --- |
| Server `connection.ready` | Uses sequence 0. Includes `connection_id` and `session_id` |
| Client `ping` | Returns `pong` with the same sequence and data |
| Client `echo` | Returns `echo.response` with the same sequence and data |
| Client `ack` | Acknowledges retained session messages through the supplied sequence |
| Invalid acknowledgement | Returns `error` with code `INVALID_ACK` |
| Unsupported type | Returns `error` with code `UNKNOWN_MESSAGE_TYPE` |

Send a message within each 30-second receive interval. If no message arrives, the server closes the connection with code 4000 and reason `heartbeat timeout`.

To resume a disconnected session, connect to `/realtime/ws?session_id=<session-uuid>`. An unknown, expired, or already connected session is rejected with code 1008. A resumed connection receives `connection.ready` before retained messages.

The connection manager provides `send_session_message()` for server updates. It assigns sequences from 1 and retains messages until acknowledgement. An acknowledgement removes all pending messages through that sequence. Reconnection replays the remaining messages in order. Ping and echo replies use direct sends and are not retained for replay. The current routes do not publish order or voice updates through `send_session_message()`.

Each connection has an outbound queue of 100 messages and a sender task. A full queue disconnects the connection. Each session can retain 1,000 pending messages by default. A full pending buffer raises `BufferError`.

Sessions remain in process memory. Disconnected sessions expire after 1,800 seconds without activity. A background task checks expiration every 60 seconds. Application shutdown stops cleanup and waits for connection sender tasks. Session resume does not survive a process restart or work across separate worker processes.

## Voice simulation

`voice/session.py` defines `VoiceSession`. It is not connected to `/realtime/ws` or another route. The code simulates voice processing for tests and development.

- Incoming binary audio uses a queue with a capacity of five chunks. Producers wait when the queue is full.
- `process_audio()` sends each chunk to a supplied callback. The default fake STT callback waits one second and produces no transcript.
- `FakeVAD` accepts explicit speech and silence events. It completes a user turn after 500 milliseconds of consecutive silence by default.
- The session has `IDLE`, `AGENT_SPEAKING`, and `USER_SPEAKING` states.
- `start_agent_turn()` starts simulated LLM and TTS tasks. It requires the `IDLE` state.
- The fake LLM streams a fixed response. Fake TTS encodes text as UTF-8 bytes. These bytes are not playable speech audio.
- A text queue with a capacity of ten chunks connects LLM output to TTS. An explicit end-of-stream marker stops TTS.
- Speech during an agent turn cancels LLM and TTS tasks. It clears pending agent text and audio. It preserves incoming audio and independent business work.
- Provider failure logs the error, cancels the other output task, and clears pending output.

The module has methods to receive binary audio and process chunks. No route starts these methods or sends queued agent audio to a client. Real STT, LLM, TTS, and audio-based VAD providers are not configured.

## Database relationships

```mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : places
    ORDERS ||--o{ ORDER_ITEMS : contains
    PRODUCTS ||--o{ ORDER_ITEMS : appears_in
    CUSTOMERS o|--o{ USERS : linked_to
    USERS ||--o{ IDEMPOTENCY_RECORDS : owns
```

| Foreign key | Meaning |
| --- | --- |
| `orders.customer_id -> customers.id` | Each order belongs to one customer |
| `order_items.order_id -> orders.id` | Each line item belongs to one order |
| `order_items.product_id -> products.id` | Each line item references one product |
| `users.customer_id -> customers.id` | A user can have a customer link. The link can be null |
| `idempotency_records.user_id -> users.id` | Each idempotency record belongs to one user |

`idempotency_records.resource_id` stores the order UUID without an order foreign key. A unique constraint covers user, operation, and key.

Put the foreign key on the **many side** of each one-to-many relationship. A customer can have many orders, so each order stores its customer ID. A product can appear in many orders, so each order item stores its product ID and quantity.

- **Foreign keys** enforce valid references in the database after migrations are applied.
- **`relationship()`** provides Python navigation such as `order.customer` and `order.items`; it does not create another table column.
- **`back_populates`** names the reverse Python relationship: `CustomerModel.orders` pairs with `OrderModel.customer`.

For a detailed explanation with examples and exercises, see the [database relationships PDF](docs/database-relationships-guide.pdf).

## Sessions and transactions

App startup creates one async engine and session factory per application process. A dependency opens an `AsyncSession` for each request that needs database access. Shutdown disposes the engine.

Authentication reads use a separate session. This prevents authentication from starting a transaction in the session used for order writes.

`OrderService.create_order()` uses `async with self.session.begin()`. The idempotency claim, reference checks, and order write share this transaction. Success commits before the method returns. An exception rolls back the transaction. Repository write methods flush changes without a commit.

`AuthService.register()` also controls its write transaction. The session dependency opens and closes sessions; it does not commit them.

While a request waits for the database, other requests can run. Async does not make one SQL query faster. Use a separate session for each request.

Outside HTTP requests, pass the same session to a write service and its repositories. Make sure that no transaction is active before the service starts its own transaction. For direct repository writes, start a transaction in the calling code.

## Configuration and local setup

### Prerequisites

- Python 3.14 or newer
- `uv`
- A running PostgreSQL server with an existing login role and database

Run commands from the repository root.

### Install dependencies

```sh
uv sync
```

### Configure the environment

Create a local `.env` file. Use your database credentials:

```dotenv
APP_NAME="Meridian Commerce API"
APP_VERSION="0.1.0"
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://meridian:YOUR_PASSWORD@localhost:5432/meridian
JWT_SECRET_KEY=REPLACE_WITH_A_RANDOM_SECRET
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

`DATABASE_URL` and `JWT_SECRET_KEY` are required. Use a random secret for JWT signing. The other fields have defaults. Settings read `.env` from the working directory. `get_settings()` uses `lru_cache` to cache the settings. After you change settings, restart the process. Do not put real credentials in version control.

Settings also define `LOG_LEVEL`. The logging initializer currently uses a fixed INFO level.

For an existing Homebrew PostgreSQL 18 installation on macOS, start the service with:

```sh
brew services start postgresql@18
```

### Apply migrations, seed data, and start the API

```sh
uv run alembic upgrade head
uv run python -m meridian_backend.scripts.seed
uv run uvicorn meridian_backend.main:app --reload
```

The seed script prints customer and product UUIDs. It inserts new records on every run. It does not create a login user or an admin.

Use the Uvicorn command above to start the server. The `meridian-backend` package script does not start the API.

Open [interactive API docs](http://127.0.0.1:8000/docs), or check:

```sh
curl http://127.0.0.1:8000/health
```

## API usage

Register a user:

```sh
curl -X POST http://127.0.0.1:8000/register \
  -H 'Content-Type: application/json' \
  -d '{"name":"Test User","email":"user@example.com","password":"example-password-123"}'
```

Log in:

```sh
curl -X POST http://127.0.0.1:8000/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","password":"example-password-123"}'
```

Copy `access_token` from the response. Set it in your shell:

```sh
TOKEN='PASTE_ACCESS_TOKEN_HERE'
curl http://127.0.0.1:8000/me -H "Authorization: Bearer $TOKEN"
```

Create an order. Replace the example UUIDs with the customer and product IDs from the seed script. Choose a new idempotency key for each new order:

```sh
curl -X POST http://127.0.0.1:8000/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Idempotency-key: example-order-001' \
  -H 'Content-Type: application/json' \
  -d '{
    "customer_id": "11111111-1111-4111-8111-111111111111",
    "items": [
      {
        "product_id": "22222222-2222-4222-8222-222222222222",
        "quantity": 2
      }
    ]
  }'
```

Order creation and replay return HTTP 201. Money fields are strings. The default tax rate is 18%.

`GET /orders` lists orders without a token. To use `GET /orders/{order_id}`, send a bearer token for an admin or a user linked to that order's customer. Registration alone does not set this link.

## Schema migrations

Alembic stores schema changes as versioned migrations. Apply existing migrations during setup. Generate a new revision only when you change the schema:

```sh
uv run alembic revision --autogenerate -m "describe schema change"
# Review the generated file in migrations/versions/.
uv run alembic upgrade head
```

Autogeneration connects to the configured database. It compares the database schema with registered ORM metadata. Make sure that PostgreSQL is running and that the credentials are valid. Import all model classes so that their tables appear in `Base.metadata`. A new revision does not change the database until you apply it.

## Testing and checks

Run the test suite:

```sh
uv run pytest -q
```

Settings require a database URL and JWT secret during app import. To run tests without configuring a PostgreSQL server, supply an explicit test URL:

```sh
DATABASE_URL=sqlite+aiosqlite:///:memory: JWT_SECRET_KEY=test-only-secret-do-not-use-in-production uv run pytest -q
```

API fixtures replace the engine with a temporary SQLite database and create tables from metadata. Unit tests cover domain behavior and service behavior with mocked repositories. Session tests check lifecycle cleanup. Auth tests cover registration, login, and token checks. A dedicated order test covers authenticated creation, rollback, and idempotent replay. Real-time tests cover session resume, acknowledgement, queues, and cleanup. Voice tests cover turn detection, interruption, streaming, and provider failures.

Some older order tests still use earlier service signatures or omit required auth and idempotency headers. They need updates before the full suite can serve as a passing check.

**Test limits:** SQLite tests do not check PostgreSQL-specific behavior. They also do not prove that Alembic migrations work. The SQLite fixtures do not explicitly enable foreign-key enforcement. Check migrations and database constraints against PostgreSQL separately.

Run static checks as needed:

```sh
uv run ruff check src
uv run mypy src/meridian_backend
```

These commands check the full project. Some existing modules can fail these checks.

## Errors and request logging

A missing order, customer, or product causes HTTP 404. Duplicate user registration causes HTTP 409. Invalid login credentials or access tokens cause HTTP 401. Inactive users and permission failures cause HTTP 403. FastAPI returns HTTP 422 for request validation errors. The application logs unexpected exceptions. It returns a generic HTTP 500 response for these exceptions.

Middleware stores a UUID in `request.state.request_id`. It adds `X-Request-ID` to responses that pass through it. Request log records have extra fields for method, path, status, and elapsed milliseconds. The text formatter does not print these fields. Elapsed time measures response creation. It does not measure delivery of the complete streaming body. Responses from the outer unhandled-error path can have no `X-Request-ID` header.

## Current limitations

- Order listing is public. Order creation checks authentication but does not enforce customer ownership.
- Registration does not create or link a customer. No API manages roles or user-to-customer links.
- Refresh tokens, logout, password reset, and token revocation are not implemented.
- Pagination and customer/product CRUD endpoints are not implemented. The seed script inserts duplicate sample data on repeated runs.
- Idempotency keys are scoped to user and operation. Reused keys return the original order without request-body comparison. There is no expiry or cleanup policy.
- The idempotency claim uses PostgreSQL `ON CONFLICT`. SQLite tests do not establish PostgreSQL concurrency behavior.
- Real-time connections have no authentication. Sessions and replay buffers are local to one process.
- Ping and echo replies are not retained. Order events and voice output are not connected to the real-time route.
- Voice providers are simulations. Agent audio has an unbounded output queue and no route to send it to clients.
- Revenue and customer filters load orders and filter in Python.
- Order items use current product prices. They do not store purchase-time prices.
- Decimal arithmetic has no explicit currency-rounding policy. Product prices use `Numeric(12, 2)`.
- `mark_paid()` checks the domain transition from `PENDING` to `PAID`. No route persists this transition.
- The highest-order method raises `ValueError` for an empty collection. It has no endpoint.
- Migrations require an explicit command. The health endpoint does not check database readiness.
- Some older tests and project-wide lint/type checks need updates.

## Future work and learning roadmap

This roadmap lists proposed work. Select a stage before you implement it.

### 1. Verify database behavior and update tests

- [ ] Update older order tests for actor arguments, repository dependencies, bearer tokens, and idempotency headers.
- [ ] Apply all migrations to a dedicated PostgreSQL database. Check tables, foreign keys, and unique constraints.
- [ ] Test persistence across app restarts, concurrent idempotency claims, and transaction rollback against PostgreSQL.
- [ ] Enable foreign-key enforcement in SQLite fixtures.
- [ ] Add a credential-free `.env.example`.

**Learning focus:** separate ORM definitions, migration files, the database schema, and stored data.

### 2. Complete customer access and authorization

- [ ] Define how registration creates or links a customer.
- [ ] Enforce the selected access rules for order listing and creation.
- [ ] Add customer and product management routes with explicit permissions.
- [ ] Define update and deletion rules for customers and products used by orders.
- [ ] Make the seed workflow repeatable without duplicate sample data.
- [ ] Define refresh, revocation, and password recovery behavior if required.

**Learning focus:** authentication identifies a user. Authorization controls what the user can do.

### 3. Connect real-time events and voice providers

- [ ] Define WebSocket authentication and session ownership.
- [ ] Publish selected application events through retained session messages.
- [ ] Define shared session storage before deployment with multiple workers.
- [ ] Define malformed-message handling and delivery guarantees.
- [ ] Add a voice route and supervise receive, processing, and output tasks.
- [ ] Replace fake providers with real STT, VAD, LLM, and TTS integrations.
- [ ] Define audio formats and bound the agent audio queue.
- [ ] Test disconnect cleanup and interrupted output through the complete voice route.

**Learning focus:** keep conversation cancellation separate from durable business operations. A replayed message does not prove that a business action ran exactly once.

### 4. Preserve order history and improve database queries

- [ ] Store purchase-time prices on order items. Define how to migrate existing orders.
- [ ] Choose a currency and rounding policy.
- [ ] Persist permitted order-status transitions and test invalid transitions.
- [ ] Define the result for a highest-order query with no orders.
- [ ] Add bounded pagination and database-side filters and revenue calculations.
- [ ] Define idempotency payload checks, key validation, retention, and cleanup.

**Learning focus:** Decimal handles arithmetic. Business rules determine historical prices, rounding, and valid status changes.

### 5. Improve operations and external integrations

- [ ] Use the configured log level. Print request IDs, paths, status codes, and durations.
- [ ] Check request-ID propagation on unexpected errors.
- [ ] Add a database readiness endpoint.
- [ ] Make the package entry point start the API. Resolve lint and type-check failures.
- [ ] Add automated CI checks and deployment configuration.
- [ ] Define retries, failure handling, and idempotency before connecting payment, inventory, and shipping providers.

A database rollback cannot undo an external payment. Review transaction ownership before an operation uses several repositories or external services.

For each stage, follow a request through route -> service -> repository -> database. Then follow the response through the mappers. Test normal behavior and failure cases. Update this README when behavior changes. Use the [relationships guide](docs/database-relationships-guide.pdf) to review foreign keys and ORM navigation.
