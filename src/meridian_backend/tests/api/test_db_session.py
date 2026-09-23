from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_backend.api.dependencies import get_db_session
from meridian_backend.main import lifespan


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_session_context_exits_on_success_or_failure(fails: bool) -> None:
    app = FastAPI()
    session = AsyncMock(spec=AsyncSession)
    context = AsyncMock()
    context.__aenter__.return_value = session
    context.__aexit__.return_value = False
    factory = MagicMock(return_value=context)
    app.state.session_factory = factory
    request = Request({"type": "http", "app": app})
    dependency = get_db_session(request)

    assert await anext(dependency) is session
    if fails:
        with pytest.raises(RuntimeError, match="Request failed"):
            await dependency.athrow(RuntimeError("Request failed"))
    else:
        with pytest.raises(StopAsyncIteration):
            await anext(dependency)

    factory.assert_called_once_with()
    context.__aexit__.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_lifespan_disposes_engine(monkeypatch: pytest.MonkeyPatch, fails: bool) -> None:
    engine = MagicMock()
    engine.dispose = AsyncMock()
    factory = MagicMock()
    monkeypatch.setattr("meridian_backend.main.create_engine", lambda url: engine)
    monkeypatch.setattr("meridian_backend.main.create_session_factory", lambda eng: factory)
    app = FastAPI()

    async def run() -> None:
        async with lifespan(app):
            assert app.state.session_factory is factory
            if fails:
                raise RuntimeError("App failed")

    if fails:
        with pytest.raises(RuntimeError, match="App failed"):
            await run()
    else:
        await run()

    engine.dispose.assert_awaited_once()
