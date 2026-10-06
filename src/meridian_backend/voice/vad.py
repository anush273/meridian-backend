from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite


class VADEvent(StrEnum):
    SPEECH = "speech"
    SILENCE = "silence"


class VADState(StrEnum):
    IDLE = "IDLE"
    SPEAKING = "SPEAKING"
    POSSIBLE_END = "POSSIBLE_END"


class TurnEvent(StrEnum):
    USER_TURN_COMPLETE = "USER_TURN_COMPLETE"


@dataclass
class FakeVAD:
    """Endpoint simulated VAD events using consecutive silence duration.

    Each event describes an interval of audio, not time spent processing it.
    VAD supplies speech/silence; the endpoint threshold decides turn completion.
    """

    endpoint_threshold_ms: float = 500
    state: VADState = field(default=VADState.IDLE, init=False)
    silence_ms: float = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not isfinite(self.endpoint_threshold_ms) or self.endpoint_threshold_ms <= 0:
            raise ValueError("endpoint_threshold_ms must be finite and positive")

    def process_event(self, event: VADEvent | str, duration_ms: float = 0) -> TurnEvent | None:
        """Return a completion event once silence reaches the endpoint threshold."""
        event = VADEvent(event)
        if not isfinite(duration_ms) or duration_ms < 0:
            raise ValueError("duration_ms must be finite and non-negative")

        if event == VADEvent.SPEECH:
            self.state = VADState.SPEAKING
            self.silence_ms = 0
        elif self.state != VADState.IDLE:
            self.silence_ms += duration_ms
            self.state = VADState.POSSIBLE_END
            if self.silence_ms >= self.endpoint_threshold_ms:
                self.state = VADState.IDLE
                self.silence_ms = 0
                return TurnEvent.USER_TURN_COMPLETE
        return None
