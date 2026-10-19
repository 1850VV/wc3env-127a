"""Gym-style environment for Warcraft III Legacy; see README.md for setup and use."""

from .env import WC3Env
from .protocol import Action, Observation, ProtocolError
from .session import GameConfig, GameSession, MatchSetup, PlayerConfig

__all__ = [
    "Action",
    "GameConfig",
    "GameSession",
    "MatchSetup",
    "Observation",
    "PlayerConfig",
    "ProtocolError",
    "StepPool",
    "WC3Env",
]


def __getattr__(name):
    # StepPool imports the Windows launcher (kernel32/user32 via ctypes). Load it on first
    # use so the protocol, fake server and session types import on any OS.
    if name == "StepPool":
        from .pool import StepPool

        return StepPool
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
