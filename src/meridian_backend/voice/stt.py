import asyncio


async def fake_stt(chunk: bytes) -> None:
    """Simulate an STT service that takes one second per audio chunk."""
    await asyncio.sleep(1)
