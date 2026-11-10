"""A stand-in for Segment's client, so the telemetry tests never reach the network."""

from dataclasses import dataclass, field

import viktorbarzin_telemetry as telemetry

PRODUCTION = {
    "TELEMETRY_WRITE_KEY": "a-write-key-for-the-tests",
    "TELEMETRY_HOST": "http://event-pipeline.test",
    "TELEMETRY_ENVIRONMENT": "production",
}


@dataclass
class Sent:
    event: str
    properties: dict[str, telemetry.JsonValue]
    user_id: str | None
    anonymous_id: str | None
    context: dict[str, telemetry.JsonValue] = field(default_factory=dict)


@dataclass
class FakeEvents:
    """Keeps what it was handed, in the shape `telemetry.EventClient` asks for."""

    tracks: list[Sent] = field(default_factory=list)
    flushed: int = 0

    def track(
        self,
        *,
        user_id: str | None,
        event: str,
        properties: dict[str, telemetry.JsonValue],
        context: dict[str, telemetry.JsonValue],
        anonymous_id: str | None,
    ) -> object:
        self.tracks.append(Sent(event, properties, user_id, anonymous_id, context))
        return None

    def identify(
        self,
        *,
        user_id: str,
        traits: dict[str, telemetry.JsonValue],
        context: dict[str, telemetry.JsonValue],
        anonymous_id: str | None,
    ) -> object:
        return None

    def flush(self) -> None:
        self.flushed += 1

    def named(self, event: str) -> list[Sent]:
        return [sent for sent in self.tracks if sent.event == event]
