from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Entry:
    time: datetime
    sid: int | None
    content: str | None
    ms_score: int | None = None


@dataclass(frozen=True)
class Context:
    previous: tuple[Entry, ...]
    current: tuple[Entry, ...]
    previous_text: str | None = None

    @property
    def turn_key(self):
        return self.current[0].time.isoformat()

    def payload(self):
        # No timestamps, names, scores or device credentials go to the model.
        return {
            "previous_speaker": self.previous[0].sid,
            "previous_turn": self.previous_text if self.previous_text is not None else "\n".join(e.content or "" for e in self.previous),
            "current_speaker": self.current[0].sid,
            "current_turn": "\n".join(e.content for e in self.current),
        }


def select_context(rows: list[Entry], exhausted: bool, gap: float) -> Context | None:
    """Rows are newest first. Require two complete, uninterrupted turns.

    An extra row beyond the configured query limit tells us whether history was
    truncated. Never classify using a silently truncated previous turn.
    """
    if not rows:
        return None
    groups: list[list[Entry]] = [[]]
    boundary_seen = False
    for row in rows:
        if row.sid is None or not row.content or not row.content.strip():
            boundary_seen = True
            break
        prior = groups[-1][-1] if groups[-1] else None
        if prior and (prior.time - row.time).total_seconds() > gap:
            boundary_seen = True
            break
        if prior and row.sid != prior.sid:
            if len(groups) == 2:
                boundary_seen = True
                break
            groups.append([])
        groups[-1].append(row)
    if len(groups) != 2 or not (exhausted or boundary_seen):
        return None
    return Context(tuple(reversed(groups[1])), tuple(reversed(groups[0])))
