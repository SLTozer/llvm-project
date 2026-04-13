# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Provides Windows implementation of formatted/colored console output."""

import sys

import ctypes
import ctypes.wintypes

from ..PrettyOutputBase import (
    PrettyOutputBase,
    PrettyOutputColor,
    Stream,
    _lock,
    _null_lock,
)


class _CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
    # pylint: disable=protected-access
    _fields_ = [
        ("dwSize", ctypes.wintypes._COORD),
        ("dwCursorPosition", ctypes.wintypes._COORD),
        ("wAttributes", ctypes.c_ushort),
        ("srWindow", ctypes.wintypes._SMALL_RECT),
        ("dwMaximumWindowSize", ctypes.wintypes._COORD),
    ]
    # pylint: enable=protected-access


class PrettyOutput(PrettyOutputBase):
    stdout = Stream(sys.stdout, ctypes.windll.kernel32.GetStdHandle(-11))
    stderr = Stream(sys.stderr, ctypes.windll.kernel32.GetStdHandle(-12))

    def __enter__(self):
        info = _CONSOLE_SCREEN_BUFFER_INFO()

        for s in (PrettyOutput.stdout, PrettyOutput.stderr):
            ctypes.windll.kernel32.GetConsoleScreenBufferInfo(s.os, ctypes.byref(info))
            s.orig_color = info.wAttributes

        return self

    def __exit__(self, *args):
        self._restore_orig_color(PrettyOutput.stdout)
        self._restore_orig_color(PrettyOutput.stderr)

    def _restore_orig_color(self, stream, lock=_lock):
        if not stream.color_enabled:
            return

        with lock:
            stream = self._set_valid_stream(stream)
            self.flush(stream)
            if stream.orig_color:
                ctypes.windll.kernel32.SetConsoleTextAttribute(
                    stream.os, stream.orig_color
                )

    def _color(self, text, color, stream, lock=_lock):
        stream = self._set_valid_stream(stream)
        with lock:
            try:
                if stream.color_enabled:
                    ctypes.windll.kernel32.SetConsoleTextAttribute(stream.os, color)
                self._write(text, stream)
            finally:
                if stream.color_enabled:
                    self._restore_orig_color(stream, lock=_null_lock)

    def _get_color_code(color: PrettyOutputColor):
        if color == PrettyOutputColor.RED:
            return 12
        if color == PrettyOutputColor.YELLOW:
            return 14
        if color == PrettyOutputColor.GREEN:
            return 10
        if color == PrettyOutputColor.BLUE:
            return 11
        if color == PrettyOutputColor.GREY:
            return 8
        return 0

    def with_color(
        self, color: PrettyOutputColor, text: str, stream: Stream = None, lock=_lock
    ):
        stream = self._set_valid_stream(stream)
        with lock:
            if stream.color_enabled:
                if color == PrettyOutputColor.DEFAULT:
                    ctypes.windll.kernel32.SetConsoleTextAttribute(
                        stream.os, stream.orig_color
                    )
                else:
                    ctypes.windll.kernel32.SetConsoleTextAttribute(
                        stream.os, PrettyOutput._get_color_code(color)
                    )
            stream.py.write(text)
        if stream.color_enabled:
            self.flush(stream)
