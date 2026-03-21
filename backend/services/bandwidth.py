"""Configurable download rate limiting."""


class BandwidthManager:
    """Token-bucket rate limiter for pre-cache downloads."""

    def __init__(self, rate_mbps: float = 10.0) -> None:
        self._rate_mbps = rate_mbps

    @property
    def rate_mbps(self) -> float:
        return self._rate_mbps

    @rate_mbps.setter
    def rate_mbps(self, value: float) -> None:
        self._rate_mbps = max(0.5, value)

    def status(self) -> dict:
        return {"rate_mbps": self._rate_mbps}
