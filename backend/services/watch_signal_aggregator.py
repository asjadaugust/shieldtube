"""Real-time aggregation of watch engagement signals from progress events."""

from datetime import datetime, timezone

import aiosqlite


class WatchSignalAggregator:
    """Processes progress events and maintains per-session engagement metrics."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db
        self._sessions: dict[str, dict] = {}

    async def process_event(
        self,
        video_id: str,
        position_seconds: int,
        duration: int,
        event: str | None = None,
        speed: float | None = None,
    ) -> None:
        if event is None:
            event = "playing"
        if speed is None:
            speed = 1.0

        session = self._sessions.get(video_id)
        if session is None:
            session = {
                "session_start": datetime.now(timezone.utc).isoformat(),
                "pause_count": 0,
                "seek_forward_count": 0,
                "speeds": [speed],
                "last_position": position_seconds,
                "time_of_day": datetime.now(timezone.utc).hour,
                "event_count": 0,
            }
            self._sessions[video_id] = session

        session["event_count"] += 1

        if event == "paused":
            session["pause_count"] += 1
        elif event == "seeked":
            if position_seconds > session["last_position"]:
                session["seek_forward_count"] += 1
        elif event in ("completed", "abandoned"):
            completion_rate = position_seconds / duration if duration > 0 else 0.0
            abandoned_at_pct = (position_seconds / duration if duration > 0 else None) if event == "abandoned" else None
            avg_speed = sum(session["speeds"]) / len(session["speeds"])

            await self._db.execute(
                """INSERT OR REPLACE INTO watch_signals
                   (video_id, session_start, completion_rate, pause_count,
                    seek_forward_count, avg_playback_speed, time_of_day, abandoned_at_pct)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (video_id, session["session_start"], completion_rate,
                 session["pause_count"], session["seek_forward_count"],
                 avg_speed, session["time_of_day"], abandoned_at_pct),
            )
            await self._db.commit()
            del self._sessions[video_id]
            return

        session["speeds"].append(speed)
        session["last_position"] = position_seconds

        # Persist partial signals every 5th playing event to avoid data loss on restart
        if event == "playing" and session["event_count"] % 5 == 0:
            completion_rate = position_seconds / duration if duration > 0 else 0.0
            avg_speed = sum(session["speeds"]) / len(session["speeds"])
            await self._db.execute(
                """INSERT OR REPLACE INTO watch_signals
                   (video_id, session_start, completion_rate, pause_count,
                    seek_forward_count, avg_playback_speed, time_of_day, abandoned_at_pct)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
                (video_id, session["session_start"], completion_rate,
                 session["pause_count"], session["seek_forward_count"],
                 avg_speed, session["time_of_day"]),
            )
            await self._db.commit()

    async def get_signals(self, video_id: str) -> list:
        from backend.db.repositories import WatchSignalRepo
        repo = WatchSignalRepo(self._db)
        return await repo.get_for_video(video_id)
