"""Versioned, validated JSON snapshots at research-storage boundaries."""

from typing import Any, Literal, Protocol, TypedDict


class WorkspaceSnapshot(TypedDict):
    revision: int
    workspace: dict[str, Any]


class StateSnapshot(TypedDict):
    revision: int
    state: dict[str, Any]


BatchMutation = Literal["advance", "pause", "resume", "cancel", "skip_uncertain"]


class BatchCreation(Protocol):
    @property
    def location(self) -> str: ...
    @property
    def scope(self) -> Literal["web", "linkedin", "facebook", "instagram"]: ...
    @property
    def target(self) -> int: ...
