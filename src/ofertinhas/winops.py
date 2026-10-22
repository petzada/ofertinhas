"""Integração com o Windows: não suspender enquanto o backend roda."""

import sys
from collections.abc import Callable

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _set_thread_execution_state(flags: int) -> None:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(flags)


def keep_awake(
    active: bool, set_state: Callable[[int], None] = _set_thread_execution_state
) -> None:
    """Pede ao Windows para não suspender (a tela pode apagar normalmente)."""
    set_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED if active else ES_CONTINUOUS)
