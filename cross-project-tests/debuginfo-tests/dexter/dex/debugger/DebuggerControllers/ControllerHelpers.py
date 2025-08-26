# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
# See https://llvm.org/LICENSE.txt for license information.
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception

import os
from itertools import chain


def in_source_file(source_files, step_info):
    if not step_info.current_frame:
        return False
    if not step_info.current_location.path:
        return False
    if not os.path.exists(step_info.current_location.path):
        return False
    return any(
        os.path.samefile(step_info.current_location.path, f) for f in source_files
    )


def have_hit_line(watch, loc):
    if hasattr(watch, "on_line"):
        return watch.on_line == loc.lineno
    elif hasattr(watch, "_from_line"):
        return watch._from_line <= loc.lineno and watch._to_line >= loc.lineno
    elif watch.lineno == loc.lineno:
        return True
    return False

