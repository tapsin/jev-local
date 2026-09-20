"""JEV-Local: System-1 Decision Engine for Local LLMs."""

from .jev_local import (
    JEVLocal,
    QuestionSpec,
    JEVAnswer,
    JEVResponse,
    decide_action,
    decide_score,
    decide_binary,
)

__all__ = [
    "JEVLocal",
    "QuestionSpec",
    "JEVAnswer",
    "JEVResponse",
    "decide_action",
    "decide_score",
    "decide_binary",
]

__version__ = "0.1.0"