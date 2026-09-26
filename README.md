# Meridian Backend

A commerce API built with FastAPI, async SQLAlchemy, and PostgreSQL. The implemented HTTP endpoints create, list, and retrieve orders. Customers and products must already exist in the database before an order can be created.

## Contents

- [Current capabilities](#current-capabilities)
- [Architecture and rationale](#architecture-and-rationale)
- [Project structure](#project-structure)
- [How an order request works](#how-an-order-request-works)
- [Database relationships](#database-relationships)
- [Sessions and transactions](#sessions-and-transactions)
- [Configuration and local setup](#configuration-and-local-setup)
- [API usage](#api-usage)
- [Schema migrations](#schema-migrations)
- [Testing and checks](#testing-and-checks)
- [Errors and request logging](#errors-and-request-logging)
- [Current limitations](#current-limitations)

## Current capabilities

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Returns a basic application health response; does not check database connectivity |
| `GET /orders` | Lists stored orders |
| `POST /orders` | Creates a pending order for an existing customer and products |
| `GET /orders/{order_id}` | Retrieves an order by UUID |

The service also has methods for paid orders, revenue, customer filtering, and the highest-value order. These are not exposed as HTTP endpoints. Payment, inventory, and shipping modules exist, but the order routes do not invoke them.

## Architecture and rationale

The application uses a **layered architecture within one backend application**. Each layer has a specific responsibility, allowing business calculations, HTTP handling, and database access to change independently.

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

**Why:** a change to an endpoint or response format should not require rewriting SQL or monetary calculations. Central exception handlers translate domain errors into HTTP responses.

### 2. Schemas: the public data contract

`schemas/` contains Pydantic models for input validation and output serialization. For example, `CreateOrder` requires at least one item and positive integer quantities. Clients cannot choose an order's initial status through this schema.

**Why:** malformed requests can be rejected at the API boundary, and response fields can evolve separately from table definitions. Request validation does not replace database constraints or service-level checks.

### 3. Domain models: business data and calculations

`models/` contains Python dataclasses such as `Order`, `OrderItem`, `Customer`, and `Product`. Order subtotal, tax, total, and state-transition behavior live here. Monetary calculations use `Decimal`.

**Why:** calculations can run and be tested without FastAPI or a database session. Construct money from strings, such as `Decimal("25.00")`, to avoid introducing binary floating-point approximations.

### 4. Services: coordinate a business operation

`services/order_service.py` checks whether the customer and products exist, constructs a domain order, and asks the repository to save it. Missing references raise domain-specific exceptions.

**Why:** routes stay small, and business operations can be reused outside HTTP requests. The service currently depends on the concrete `OrderRepository` class; this is a pragmatic separation, not complete isolation from the persistence implementation.

### 5. Repositories: database access

`repositories/order_repository.py` owns SQLAlchemy queries and persistence. It loads the required relationships before returning domain objects. It also commits newly created orders and rolls back failed writes.

**Why:** SQL and relationship-loading decisions stay in one place. The rest of the application works with domain objects rather than accessing ORM attributes that might trigger additional database queries.

### 6. Database models and mappers: the storage boundary

`db/models/` defines tables, columns, foreign keys, and ORM relationships. `db/mappers.py` converts loaded ORM instances into domain dataclasses. `api/mappers.py` separately converts domain objects into response schemas.

```text
Database row -> ORM model -> domain object -> API response schema -> JSON
```

**Why three representations?** They answer different questions: how data is stored, how business behavior works, and what the client may send or receive. The cost is extra classes and mapping code. In a smaller CRUD-only application, fewer representations could be sufficient; here the separation supports learning and independent business logic.

### 7. Dependency injection: assemble objects for a request

`api/dependencies.py` builds the dependency chain:

```text
Request -> AsyncSession -> OrderRepository -> OrderService -> route
```

**Why:** routes do not create database connections themselves. Object construction is centralized, and dependencies can be replaced in tests.

## Project structure

```text
src/meridian_backend/
├── main.py                 # App assembly, lifespan, routers, middleware
├── api/
│   ├── routes/             # HTTP endpoints
│   ├── dependencies.py     # Session, repository, and service injection
│   ├── exception_handlers.py
│   └── mappers.py          # Domain objects -> API responses
├── core/                   # Settings, exceptions, logging, middleware
├── db/
│   ├── base.py             # Shared SQLAlchemy declarative base
│   ├── session.py          # Async engine and session factory
│   ├── models/             # ORM table definitions
│   └── mappers.py          # ORM objects -> domain objects
├── models/                 # Domain dataclasses and calculations
├── repositories/           # SQL queries and persistence
├── schemas/                # Pydantic request/response contracts
├── services/               # Business operations
└── tests/                  # API and unit tests
migrations/                 # Alembic environment and versioned migrations
alembic.ini                 # Alembic configuration
```

## How an order request works

For `POST /orders`:

1. Middleware creates a request ID, and FastAPI validates the JSON against `CreateOrder`.
2. Dependencies provide a request-scoped session, repository, and service.
3. The service asks the repository for the customer and requested products.
4. Missing references produce a domain error, which the API converts to a 404.
5. The service constructs a pending domain order with a new UUID.
6. The repository constructs ORM order and item objects and commits them together.
7. The API mapper builds the response, including Decimal subtotal, tax, and total.
8. The session closes when the dependency exits.

Reads use `selectinload()` to load customers, order items, and their products before database mapping. This avoids relying on implicit relationship loading inside the mapper when using async sessions.

## Database relationships

```mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : places
    ORDERS ||--o{ ORDER_ITEMS : contains
    PRODUCTS ||--o{ ORDER_ITEMS : appears_in
```

| Foreign key | Meaning |
| --- | --- |
| `orders.customer_id -> customers.id` | Each order belongs to one customer |
| `order_items.order_id -> orders.id` | Each line item belongs to one order |
| `order_items.product_id -> products.id` | Each line item references one product |

The foreign key goes on the **many side** of each one-to-many association. A customer can have many orders, so each order stores its customer ID. A product can appear in many orders, so each order item stores its product ID and quantity.

- **Foreign keys** enforce valid references in the database after migrations are applied.
- **`relationship()`** provides Python navigation such as `order.customer` and `order.items`; it does not create another table column.
- **`back_populates`** names the reverse Python relationship: `CustomerModel.orders` pairs with `OrderModel.customer`.

For a detailed explanation with examples and exercises, see the [database relationships PDF](docs/database-relationships-guide.pdf).

## Sessions and transactions

App startup creates one async engine and session factory per application process. A dependency opens an `AsyncSession` for each request that needs database access. Shutdown disposes the engine.

The repository's `add()` method currently owns the write transaction: it commits an order and its items together, and rolls back on failure. The session dependency handles session cleanup; it does not automatically commit requests.

**Why async:** database waits can yield control to other requests. It does not make an individual SQL query faster. Keep each session scoped to its request rather than sharing one session globally.

**Tradeoff:** repository-owned commits are simple for the current create-order operation. If a future operation must atomically write through several repositories, move transaction ownership to that coordinating operation or a unit-of-work abstraction.

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

Create a local `.env` using your actual credentials:

```dotenv
APP_NAME="Meridian Commerce API"
APP_VERSION="0.1.0"
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://meridian:YOUR_PASSWORD@localhost:5432/meridian
```

`DATABASE_URL` is required. The other fields have defaults. Settings read `.env` relative to the working directory and are cached by `get_settings()` using `lru_cache`; restart the process after changing settings. Keep real credentials out of version control.

`LOG_LEVEL` is also declared in settings, but the current logging initializer uses a fixed INFO level.

For an existing Homebrew PostgreSQL 18 installation on macOS, start the service with:

```sh
brew services start postgresql@18
```

### Apply migrations and start the API

```sh
uv run alembic upgrade head
uv run uvicorn meridian_backend.main:app --reload
```

Use the Uvicorn command above to start the server. The current `meridian-backend` package script is not wired to launch the API.

Open [interactive API docs](http://127.0.0.1:8000/docs), or check:

```sh
curl http://127.0.0.1:8000/health
```

## API usage

The following UUIDs are illustrative. Replace them with IDs of an existing customer and product in your database. Customer/product creation endpoints and a seed command are not implemented yet.

```sh
curl -X POST http://127.0.0.1:8000/orders \
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

A successful creation returns HTTP 201. Retrieve records with `GET /orders` or `GET /orders/{order_id}`. Monetary response fields are serialized as strings to preserve decimal representation.

## Schema migrations

Alembic stores schema changes as versioned migrations. Existing migrations should be applied during setup; generate a new revision only when intentionally changing the schema:

```sh
uv run alembic revision --autogenerate -m "describe schema change"
# Review the generated file in migrations/versions/.
uv run alembic upgrade head
```

Autogeneration connects to the configured database and compares it with registered ORM metadata. PostgreSQL must be running, credentials must be valid, and all model classes must be imported so their tables appear in `Base.metadata`. Generating a revision does not apply it.

## Testing and checks

Run the test suite:

```sh
uv run pytest -q
```

Settings still require a database URL during app import. To run tests without configuring a PostgreSQL server, supply an explicit test URL:

```sh
DATABASE_URL=sqlite+aiosqlite:///:memory: uv run pytest -q
```

API fixtures replace the engine with a temporary SQLite database and create tables from metadata. Unit tests cover domain behavior and service behavior with mocked repositories. Session tests check lifecycle cleanup.

**Testing boundary:** SQLite tests do not validate PostgreSQL-specific behavior or prove that Alembic migrations work. The SQLite fixtures also do not explicitly enable foreign-key enforcement. Verify migrations and database constraints against PostgreSQL separately.

Run static checks as needed:

```sh
uv run ruff check src
uv run mypy src/meridian_backend
```

These are project-wide diagnostic commands; not all existing modules are guaranteed to pass them.

## Errors and request logging

Missing orders, customers, and products map to HTTP 404. FastAPI handles request validation errors with HTTP 422. Unexpected exceptions are logged and return a generic HTTP 500 response.

Middleware stores a UUID in `request.state.request_id` and adds `X-Request-ID` to responses returned through it. Request log records include method, path, status, and elapsed milliseconds as extra fields. The current text formatter does not print those extra fields, and elapsed time measures response creation rather than complete streaming-body delivery. The outer unhandled-error response path does not currently guarantee an `X-Request-ID` header.

## Current limitations

- Authentication, pagination, customer/product CRUD routes, and a seed workflow are not implemented.
- Revenue and customer filtering currently load orders and filter in Python. Larger datasets would benefit from database-side filtering and aggregation.
- Order totals use the current product price; order items do not snapshot the price at purchase time.
- Decimal arithmetic is used, but no explicit currency-rounding policy exists. Product prices are stored as `Numeric(12, 2)`.
- The highest-order method raises `ValueError` for an empty collection; it is not exposed as an endpoint.
- Schema migrations are applied explicitly, not during application startup. The health endpoint is not a database readiness check.
