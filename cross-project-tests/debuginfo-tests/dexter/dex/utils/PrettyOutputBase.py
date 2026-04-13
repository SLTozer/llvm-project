# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Provides formatted/colored console output on both Windows and Linux.

Do not use this module directly, but instead use via the appropriate platform-
specific module.
"""

import abc
from enum import Enum
from functools import reduce
import re
import sys
import threading
import unittest

from io import StringIO

from dex.utils.Exceptions import Error


class _NullLock(object):
    def __enter__(self):
        return None

    def __exit__(self, *params):
        pass


_lock = threading.Lock()
_null_lock = _NullLock()


class PreserveAutoColors(object):
    def __init__(self, pretty_output):
        self.pretty_output = pretty_output
        self.orig_values = {}
        self.properties = ["auto_reds", "auto_yellows", "auto_greens", "auto_blues"]

    def __enter__(self):
        for p in self.properties:
            self.orig_values[p] = getattr(self.pretty_output, p)[:]
        return self

    def __exit__(self, *args):
        for p in self.properties:
            setattr(self.pretty_output, p, self.orig_values[p])


class Stream(object):
    def __init__(self, py_, os_=None):
        self.py = py_
        self.os = os_
        self.orig_color = None
        self.color_enabled = self.py.isatty()


# Represents the colours available to PrettyOutput; for maximum terminal compatibility, we try not to support too many,
# and may print similar colours as being the same (e.g. white and grey) if we don't have full support for them.
class PrettyOutputColor(Enum):
    RED = "r"
    YELLOW = "y"
    GREEN = "g"
    BLUE = "b"
    DEFAULT = "d"
    AUTO = "a"  # FIXME do we want this?
    GREY = "grey"


# Returns 'text' with all color tags removed.
def strip_color(text: str):
    colors = ["r", "y", "g", "b", "d", "a", "grey"]

    # Find all tags (whether open or close)
    tags = [t for t in re.finditer("<([a-z/]+)>".format("".join(colors)), text)]
    if not tags:
        return text
    last_idx = 0
    result = ""
    for tag in tags:
        tag_start = tag.start()
        if last_idx != tag_start:
            result += text[last_idx:tag_start]
        last_idx = tag.end()
    result += text[last_idx:]
    return result

def ljust_color(text: str, width: int):
    """Left justifies the text, as with `str.ljust`, accounting for color tags."""
    colors = ["r", "y", "g", "b", "d", "a", "grey"]
    tags = [t for t in re.finditer("<([a-z/]+)>".format("".join(colors)), text)]
    tag_len = reduce(lambda n, match: n + match.end() - match.start(), tags, 0)
    return text.ljust(width + tag_len)


class PrettyOutputBase(object, metaclass=abc.ABCMeta):
    stdout = Stream(sys.stdout)
    stderr = Stream(sys.stderr)

    def __init__(self):
        self.auto_reds = []
        self.auto_yellows = []
        self.auto_greens = []
        self.auto_blues = []
        # The stack of colours currently being applied, with the top of the stack being the most recent.
        self._stack = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def _set_valid_stream(self, stream):
        if stream is None:
            return self.__class__.stdout
        return stream

    def _write(
        self,
        text,
        stream: Stream = stdout,
        default_color: PrettyOutputColor = PrettyOutputColor.DEFAULT,
    ):
        text = str(text)

        # Users can embed color control tags in their output
        # (e.g. <r>hello</> <y>world</> would write the word 'hello' in red and
        # 'world' in yellow).
        # This function parses these tags using a very simple recursive
        # descent.
        colors = {
            "r": PrettyOutputColor.RED,
            "y": PrettyOutputColor.YELLOW,
            "g": PrettyOutputColor.GREEN,
            "b": PrettyOutputColor.BLUE,
            "d": PrettyOutputColor.DEFAULT,
            "a": PrettyOutputColor.AUTO,
            "grey": PrettyOutputColor.GREY,
        }

        # Find all tags (whether open or close)
        tags = [t for t in re.finditer(f"<(/|{'|'.join(colors.keys())})>", text)]

        if not tags:
            # No tags.  Just write the text to the current stream and return.
            # 'unmangling' any tags that have been mangled so that they won't
            # render as colors (for example in error output from this
            # function).
            stream = self._set_valid_stream(stream)
            stream.py.write(text)
            return

        open_tags = [i for i in tags if i.group(1) != "/"]
        close_tags = [i for i in tags if i.group(1) == "/"]

        # if len(open_tags) != len(close_tags) or any(
        #     o.start() >= c.start() for (o, c) in zip(open_tags, close_tags)
        # ):
        #     raise Error(
        #         'open/close tag mismatch in "{}"'.format(text.rstrip()).replace(
        #             ">", r"\>"
        #         )
        #     )

        last_idx = 0
        color_stack = [default_color]
        for t in tags:
            # Print the text preceding the current tag
            tag_start = t.start()
            if last_idx != tag_start:
                current_color = color_stack[-1]
                self.with_color(
                    current_color, text[last_idx:tag_start], stream, lock=_null_lock
                )
            # Apply the tag
            contents = t.group(1)
            if contents == "/":
                if len(color_stack) > 1:
                    color_stack.pop()
            else:
                color_stack.append(colors[contents])
            last_idx = t.end()
        assert len(color_stack) == 1
        self.with_color(default_color, text[last_idx:], stream, lock=_null_lock)
        # Reset color to default at the end.
        if default_color != PrettyOutputColor.DEFAULT:
            self.with_color(PrettyOutputColor.DEFAULT, "", stream, lock=_null_lock)
        stream.py.flush()

    def flush(self, stream):
        stream = self._set_valid_stream(stream)
        stream.py.flush()

    def auto(self, text, stream=None, lock=_lock):
        text = str(text)
        stream = self._set_valid_stream(stream)
        lines = text.splitlines(True)

        with lock:
            for line in lines:
                # This is just being cute for the sake of cuteness, but why
                # not?
                line = line.replace("DExTer", "<r>D<y>E<g>x<b>T</></>e</>r</>")

                # Apply the appropriate color method if the expression matches
                # any of
                # the patterns we have set up.
                for color, regexs in (
                    (PrettyOutputColor.RED, self.auto_reds),
                    (PrettyOutputColor.YELLOW, self.auto_yellows),
                    (PrettyOutputColor.GREEN, self.auto_greens),
                    (PrettyOutputColor.BLUE, self.auto_blues),
                ):
                    if any(re.search(regex, line) for regex in regexs):
                        self.with_color(color, line, stream=stream, lock=_null_lock)
                        break
                else:
                    self._write(line, stream=stream)

    def _call_color_impl(self, fn, impl, text, *args, **kwargs):
        try:
            self._stack.append(fn)
            return impl(text, *args, **kwargs)
        finally:
            fn = self._stack.pop()

    @abc.abstractmethod
    def with_color(
        color: PrettyOutputColor, text: str, stream: Stream = None, lock=_lock
    ):
        pass

    def red(self, *args, **kwargs):
        return self._write(*args, **kwargs, default_color=PrettyOutputColor.RED)

    def grey(self, *args, **kwargs):
        return self._write(*args, **kwargs, default_color=PrettyOutputColor.GREY)

    def yellow(self, *args, **kwargs):
        return self._write(*args, **kwargs, default_color=PrettyOutputColor.YELLOW)

    def green(self, *args, **kwargs):
        return self._write(*args, **kwargs, default_color=PrettyOutputColor.GREEN)

    def blue(self, *args, **kwargs):
        return self._write(*args, **kwargs, default_color=PrettyOutputColor.BLUE)

    def default(self, *args, **kwargs):
        return self._write(*args, **kwargs, default_color=PrettyOutputColor.DEFAULT)

    def colortest(self):
        from itertools import combinations, permutations

        fns = (
            (self.red, "rrr"),
            (self.yellow, "yyy"),
            (self.green, "ggg"),
            (self.blue, "bbb"),
            (self.default, "ddd"),
        )

        for l in range(1, len(fns) + 1):
            for comb in combinations(fns, l):
                for perm in permutations(comb):
                    for stream in (None, self.__class__.stderr):
                        perm[0][0]("stdout " if stream is None else "stderr ", stream)
                        for fn, string in perm:
                            fn(string, stream)
                        self.default("\n", stream)

        tests = [
            (self.auto, "default1<r>red2</>default3"),
            (self.red, "red1<r>red2</>red3"),
            (self.blue, "blue1<r>red2</>blue3"),
            (self.red, "red1<y>yellow2</>red3"),
            (self.auto, "default1<y>yellow2<r>red3</></>"),
            (self.auto, "default1<g>green2<r>red3</></>"),
            (self.auto, "default1<g>green2<r>red3</>green4</>default5"),
            (self.auto, "default1<g>green2</>default3<g>green4</>default5"),
            (self.auto, "<r>red1<g>green2</>red3<g>green4</>red5</>"),
            (self.auto, "<r>red1<y><g>green2</>yellow3</>green4</>default5"),
            (self.auto, "<r><y><g><b><d>default1</></><r></></></>red2</>"),
            (self.auto, "<r>red1</>default2<r>red3</><g>green4</>default5"),
            (self.blue, "<r>red1</>blue2<r><r>red3</><g><g>green</></></>"),
            (self.blue, "<r>r<r>r<y>y<r><r><r><r>r</></></></></></></>b"),
        ]

        for fn, text in tests:
            for stream in (None, self.__class__.stderr):
                stream_name = "stdout" if stream is None else "stderr"
                fn("{} {}\n".format(stream_name, text), stream)


class TestPrettyOutput(unittest.TestCase):
    class MockPrettyOutput(PrettyOutputBase):
        def red_impl(self, text, stream=None, **kwargs):
            self._write("[R]{}[/R]".format(text), stream)

        def yellow_impl(self, text, stream=None, **kwargs):
            self._write("[Y]{}[/Y]".format(text), stream)

        def green_impl(self, text, stream=None, **kwargs):
            self._write("[G]{}[/G]".format(text), stream)

        def blue_impl(self, text, stream=None, **kwargs):
            self._write("[B]{}[/B]".format(text), stream)

        def default_impl(self, text, stream=None, **kwargs):
            self._write("[D]{}[/D]".format(text), stream)

    def test_red(self):
        with TestPrettyOutput.MockPrettyOutput() as o:
            stream = Stream(StringIO())
            o.red("hello", stream)
            self.assertEqual(stream.py.getvalue(), "[R]hello[/R]")

    def test_yellow(self):
        with TestPrettyOutput.MockPrettyOutput() as o:
            stream = Stream(StringIO())
            o.yellow("hello", stream)
            self.assertEqual(stream.py.getvalue(), "[Y]hello[/Y]")

    def test_green(self):
        with TestPrettyOutput.MockPrettyOutput() as o:
            stream = Stream(StringIO())
            o.green("hello", stream)
            self.assertEqual(stream.py.getvalue(), "[G]hello[/G]")

    def test_blue(self):
        with TestPrettyOutput.MockPrettyOutput() as o:
            stream = Stream(StringIO())
            o.blue("hello", stream)
            self.assertEqual(stream.py.getvalue(), "[B]hello[/B]")

    def test_default(self):
        with TestPrettyOutput.MockPrettyOutput() as o:
            stream = Stream(StringIO())
            o.default("hello", stream)
            self.assertEqual(stream.py.getvalue(), "[D]hello[/D]")

    def test_auto(self):
        with TestPrettyOutput.MockPrettyOutput() as o:
            stream = Stream(StringIO())
            o.auto_reds.append("foo")
            o.auto("bar\n", stream)
            o.auto("foo\n", stream)
            o.auto("baz\n", stream)
            self.assertEqual(
                stream.py.getvalue(), "[D]bar\n[/D][R]foo\n[/R][D]baz\n[/D]"
            )

            stream = Stream(StringIO())
            o.auto("bar\nfoo\nbaz\n", stream)
            self.assertEqual(
                stream.py.getvalue(), "[D]bar\n[/D][R]foo\n[/R][D]baz\n[/D]"
            )

            stream = Stream(StringIO())
            o.auto("barfoobaz\nbardoobaz\n", stream)
            self.assertEqual(
                stream.py.getvalue(), "[R]barfoobaz\n[/R][D]bardoobaz\n[/D]"
            )

            o.auto_greens.append("doo")
            stream = Stream(StringIO())
            o.auto("barfoobaz\nbardoobaz\n", stream)
            self.assertEqual(
                stream.py.getvalue(), "[R]barfoobaz\n[/R][G]bardoobaz\n[/G]"
            )

    def test_PreserveAutoColors(self):
        with TestPrettyOutput.MockPrettyOutput() as o:
            o.auto_reds.append("foo")
            with PreserveAutoColors(o):
                o.auto_greens.append("bar")
                stream = Stream(StringIO())
                o.auto("foo\nbar\nbaz\n", stream)
                self.assertEqual(
                    stream.py.getvalue(), "[R]foo\n[/R][G]bar\n[/G][D]baz\n[/D]"
                )

            stream = Stream(StringIO())
            o.auto("foo\nbar\nbaz\n", stream)
            self.assertEqual(
                stream.py.getvalue(), "[R]foo\n[/R][D]bar\n[/D][D]baz\n[/D]"
            )

            stream = Stream(StringIO())
            o.yellow("<a>foo</>bar<a>baz</>", stream)
            self.assertEqual(
                stream.py.getvalue(),
                "[Y][Y][/Y][R]foo[/R][Y][Y]bar[/Y][D]baz[/D][Y][/Y][/Y][/Y]",
            )

    def test_tags(self):
        with TestPrettyOutput.MockPrettyOutput() as o:
            stream = Stream(StringIO())
            o.auto("<r>hi</>", stream)
            self.assertEqual(stream.py.getvalue(), "[D][D][/D][R]hi[/R][D][/D][/D]")

            stream = Stream(StringIO())
            o.auto("<r><y>a</>b</>c", stream)
            self.assertEqual(
                stream.py.getvalue(),
                "[D][D][/D][R][R][/R][Y]a[/Y][R]b[/R][/R][D]c[/D][/D]",
            )

            with self.assertRaisesRegex(Error, "tag mismatch"):
                o.auto("<r>hi", stream)

            with self.assertRaisesRegex(Error, "tag mismatch"):
                o.auto("hi</>", stream)

            with self.assertRaisesRegex(Error, "tag mismatch"):
                o.auto("<r><y>hi</>", stream)

            with self.assertRaisesRegex(Error, "tag mismatch"):
                o.auto("<r><y>hi</><r></>", stream)

            with self.assertRaisesRegex(Error, "tag mismatch"):
                o.auto("</>hi<r>", stream)
