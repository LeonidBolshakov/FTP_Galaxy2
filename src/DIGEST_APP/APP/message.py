from __future__ import annotations
import ctypes

_MB_OK = 0x00000000
_MB_ICONERROR = 0x00000010
_MB_ICONWARNING = 0x00000030
_MB_ICONINFORMATION = 0x00000040
_MB_TOPMOST = 0x00040000
_MB_SETFOREGROUND = 0x00010000

TITLE = "Дайджест обновлений"


def show_error(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(
        None,
        text,
        TITLE,
        _MB_OK | _MB_ICONERROR | _MB_TOPMOST | _MB_SETFOREGROUND,
    )


def show_warning(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(
        None,
        text,
        TITLE,
        _MB_OK | _MB_ICONWARNING | _MB_TOPMOST | _MB_SETFOREGROUND,
    )
