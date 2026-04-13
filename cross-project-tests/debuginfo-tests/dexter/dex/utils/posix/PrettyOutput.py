# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Provides POSIX implementation of formatted/colored console output."""

from ..PrettyOutputBase import PrettyOutputBase, PrettyOutputColor, Stream, _lock


class PrettyOutput(PrettyOutputBase):
    def _color(self, text, color, stream, lock=_lock):
        """Use ANSI escape codes to provide color on Linux."""
        stream = self._set_valid_stream(stream)
        with lock:
            if stream.color_enabled:
                text = "\033[{}m{}\033[0m".format(color, text)
            self._write(text, stream)

    def _get_color_code(color: PrettyOutputColor):
        if color == PrettyOutputColor.RED:
            return 91
        if color == PrettyOutputColor.YELLOW:
            return 93
        if color == PrettyOutputColor.GREEN:
            return 92
        if color == PrettyOutputColor.BLUE:
            return 96
        if color == PrettyOutputColor.GREY:
            return 90
        return 0

    def with_color(
        self, color: PrettyOutputColor, text: str, stream: Stream = None, lock=_lock
    ):
        """Use ANSI escape codes to provide color on Linux."""
        stream = self._set_valid_stream(stream)
        with lock:
            if stream.color_enabled:
                text = f"\033[{PrettyOutput._get_color_code(color)}m{text}"
            stream.py.write(text)
