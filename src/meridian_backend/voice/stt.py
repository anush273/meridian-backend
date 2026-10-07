import asyncio


async def fake_stt(chunk: bytes) -> None:
    """Simulate an STT service that takes one second per audio chunk."""
    await asyncio.sleep(1)


class FakeStreamingSTT:
    """Collect fake UTF-8 audio chunks and return one transcript per turn."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []

    async def send_audio(self, chunk: bytes) -> None:
        await fake_stt(chunk)
        self._chunks.append(chunk)

    async def finalize(self) -> str:
        transcript = b"".join(self._chunks).decode("utf-8", errors="replace")
        self._chunks.clear()
        return transcript
