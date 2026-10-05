"""Which response objects playback produced.

Playback records the calls it answers. If an adapter is also active and wraps
the playback, it must not record the same call a second time.
"""

from __future__ import annotations

from typing import Any

_PLAYED: set[int] = set()
_ACTIVE: list[object] = []


def mark_played(response: Any) -> None:
    if _ACTIVE:
        _PLAYED.add(id(response))


def was_played_back(response: Any) -> bool:
    return bool(_ACTIVE) and id(response) in _PLAYED


def enter(owner: object) -> None:
    _ACTIVE.append(owner)


def leave(owner: object) -> None:
    if owner in _ACTIVE:
        _ACTIVE.remove(owner)
    if not _ACTIVE:
        _PLAYED.clear()
