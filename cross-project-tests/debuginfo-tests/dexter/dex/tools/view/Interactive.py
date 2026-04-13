
from enum import IntEnum
import re
from dex.dextIR import DextIR
from dex.evaluate.Evaluator import DexVisualizer
from dex.utils.ReturnCode import ReturnCode
import curses

# Enums representing color pairs.
class DexterColors(IntEnum):
    DEFAULT = 1
    RED = 2
    YELLOW = 3
    GREEN = 4
    BLUE = 5
    GREY = 6

class ExtraColors(IntEnum):
    INFO = 7
    SEPARATOR = 8

class ColorLine:
    def __init__(self, dex_string=None, default_color: IntEnum = DexterColors.DEFAULT):
        self.text: list[tuple[str, int]] = []
        self.default_color = default_color
        if dex_string is not None:
            # Parse a Dexter color-tagged string into a list of string+curses color pairs.
            color_tags = {
                "r": curses.color_pair(DexterColors.RED),
                "y": curses.color_pair(DexterColors.YELLOW),
                "g": curses.color_pair(DexterColors.GREEN),
                "b": curses.color_pair(DexterColors.BLUE),
                "d": curses.color_pair(DexterColors.DEFAULT),
                "grey": curses.color_pair(DexterColors.GREY),
            }
            # We start with the "default" colour on the stack.
            color_stack: list[int] = [curses.color_pair(default_color)]
            last_str_idx = 0
            for tag in re.finditer(f"<(/|{'|'.join(color_tags.keys())})>", dex_string):
                # Push the preceding string on with whatever color is on the stack.
                preceding_str = dex_string[last_str_idx:tag.start()]
                if preceding_str:
                    self.text.append((preceding_str, color_stack[-1]))
                last_str_idx = tag.end()
                color_tag = tag.group(1)
                if color_tag == "/":
                    if len(color_stack) > 1:
                        color_stack.pop()
                else:
                    color_stack.append(color_tags[color_tag])
            # assert len(color_stack) == 1, f"Imbalanced tags in string '{dex_string}'?"
            final_str = dex_string[last_str_idx:]
            if final_str:
                self.text.append((final_str, color_stack[-1]))

    def print(self, stdscr, y, x, width):
        curr_offset = 0
        for text, color in self.text:
            if curr_offset >= width:
                break
            end_offset = curr_offset + len(text)
            if end_offset > width:
                text = text[:width - curr_offset]
            stdscr.addstr(y, x + curr_offset, text, color)
            curr_offset = end_offset
        if curr_offset < width:
            background = curses.color_pair(self.default_color)
            stdscr.addstr(y, x + curr_offset, " " * (width - curr_offset), background)


class Panel:
    def __init__(
        self, width: int, height: int, x_pos: int, content: list[ColorLine] = []
    ):
        self.width = width
        self.height = height
        self.x_pos = x_pos
        self.scroll_pos: int = 0
        self.content = content

    def draw(self, stdscr):
        for idx, line in enumerate(
            self.content[self.scroll_pos : self.scroll_pos + self.height]
        ):
            line.print(stdscr, idx, self.x_pos, self.width)

    @property
    def max_scroll_pos(self) -> int:
        return max(len(self.content) - self.height, 0)

    def update_content(self, new_content: list[ColorLine]):
        self.content = new_content
        self.scroll_pos = min(self.scroll_pos, self.max_scroll_pos)

    def scroll_line(self, up: bool) -> bool:
        """Scrolls up/down by a single line.
        Returns true if the scroll position actually changed."""
        old_pos = self.scroll_pos
        if up:
            self.scroll_pos = max(self.scroll_pos - 1, 0)
        else:
            self.scroll_pos = min(self.scroll_pos + 1, self.max_scroll_pos)
        return old_pos != self.scroll_pos

    def scroll_page(self, up: bool) -> bool:
        """Scrolls up/down by a full page (i.e. self.height).
        Returns true if the scroll position actually changed."""
        old_pos = self.scroll_pos
        if up:
            self.scroll_pos = max(self.scroll_pos - self.height, 0)
        else:
            self.scroll_pos = min(self.scroll_pos + self.height, self.max_scroll_pos)
        return old_pos != self.scroll_pos

    def scroll_end(self, up: bool) -> bool:
        """Scrolls to the start/end of this panel.
        Returns true if the scroll position actually changed."""
        old_pos = self.scroll_pos
        if up:
            self.scroll_pos = 0
        else:
            self.scroll_pos = self.max_scroll_pos
        return old_pos != self.scroll_pos

    def scroll_to_line(
        self, line: int, top_tolerance: int = 4, bot_tolerance: int = 6
    ) -> bool:
        """Scrolls such that the specified line (indexing into self.content) is on-screen.
        Returns true if the scroll position actually changed."""
        assert (
            top_tolerance + bot_tolerance < self.height
        ), "Strange behaviour follows if this assert hits."
        old_pos = self.scroll_pos
        if max(line - top_tolerance, 0) < self.scroll_pos:
            self.scroll_pos = max(line - top_tolerance, 0)
        elif line + bot_tolerance - self.height > self.scroll_pos:
            self.scroll_pos = min(
                line + bot_tolerance - self.height, self.max_scroll_pos
            )
        return old_pos != self.scroll_pos


def run_interactive(context, dext_ir: DextIR) -> ReturnCode:
    steps_list = [f"Step {step.step_index}" for step in dext_ir.steps]
    if not steps_list:
        context.logger.error(f"Cannot get interactive view of DextIR with 0 steps.")
        return ReturnCode.FAIL
    visualizer = DexVisualizer(context, dext_ir)
    def _run_interactive(stdscr):
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()

        ## Define color pairs
        # Dexter display colors
        curses.init_pair(DexterColors.DEFAULT, curses.COLOR_WHITE, -1)
        curses.init_pair(DexterColors.RED, curses.COLOR_RED, -1)
        curses.init_pair(DexterColors.YELLOW, curses.COLOR_YELLOW, -1)
        curses.init_pair(DexterColors.GREEN, curses.COLOR_GREEN, -1)
        curses.init_pair(DexterColors.BLUE, curses.COLOR_BLUE, -1)
        # Non-curses colors...
        if curses.can_change_color():
            curses.init_color(100, 500, 500, 500)
            curses.init_pair(DexterColors.GREY, 100, -1)
        else:
            curses.init_pair(DexterColors.GREY, curses.COLOR_WHITE, -1)

        curses.init_pair(ExtraColors.INFO, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(ExtraColors.SEPARATOR, curses.COLOR_BLACK, curses.COLOR_WHITE)

        height, width = stdscr.getmaxyx()
        height -= 1

        left_width = 30
        right_width = width - left_width

        current_panel_is_right = True

        step_count = len(steps_list)
        selected_step = step_count - 1
        info_text = str(dext_ir.steps[selected_step].current_location)

        cached_step_content: dict[int, tuple[list[ColorLine], list[ColorLine]]] = {}
        def get_step_content(step_index: int):
            if step_index in cached_step_content:
                return cached_step_content[step_index]
            step_script_content = visualizer.visualize_step(step_index)
            color_step_script_content = [
                ColorLine(l) for l in step_script_content.split("\n")
            ]
            step_content = dext_ir.steps[step_index].detailed_print()
            color_step_content = [ColorLine(l) for l in step_content]
            result = (color_step_script_content, color_step_content)
            cached_step_content[step_index] = result
            return result

        steps_panel = Panel(left_width - 2, height - 1, 0)

        def update_steps_panel():
            """Call after changing either selected_step or current_panel_is_right."""
            highlight_color = (
                ExtraColors.INFO if not current_panel_is_right else DexterColors.GREEN
            )
            normal_color = DexterColors.DEFAULT
            steps_panel.update_content(
                [
                    ColorLine(
                        l, highlight_color if i == selected_step else normal_color
                    )
                    for i, l in enumerate(steps_list)
                ]
            )

        update_steps_panel()
        steps_panel.scroll_to_line(selected_step)
        separator_panel = Panel(
            1,
            height - 1,
            left_width - 1,
            [ColorLine("|", ExtraColors.SEPARATOR) for _ in range(height - 1)],
        )
        script_panel = Panel(right_width - 1, height - 1, left_width)
        step_panel = Panel(right_width - 1, height - 1, left_width)

        def update_right_panels():
            """Call after changing selected_step."""
            script_content, step_content = get_step_content(selected_step)
            script_panel.update_content(script_content)
            step_panel.update_content(step_content)

        update_right_panels()
        right_panels = [script_panel, step_panel]
        current_right_panel_idx = 0

        while True:
            stdscr.clear()

            steps_panel.draw(stdscr)
            separator_panel.draw(stdscr)
            current_right_panel = right_panels[current_right_panel_idx]
            current_right_panel.draw(stdscr)
            stdscr.attron(curses.color_pair(ExtraColors.INFO))
            stdscr.addstr(height - 1, 0, info_text.ljust(width))
            stdscr.attroff(curses.color_pair(ExtraColors.INFO))

            stdscr.refresh()

            key = stdscr.getch()
            if key in (ord('q'), ord('Q')):
                break
            elif key == curses.KEY_UP:
                if current_panel_is_right:
                    current_right_panel.scroll_line(up=True)
                else:
                    if selected_step > 0:
                        selected_step -= 1
                        update_right_panels()
                        info_text = str(dext_ir.steps[selected_step].current_location)
                        update_steps_panel()
                        steps_panel.scroll_to_line(selected_step)
            elif key == curses.KEY_DOWN:
                if current_panel_is_right:
                    current_right_panel.scroll_line(up=False)
                else:
                    if selected_step < step_count - 1:
                        selected_step += 1
                        update_right_panels()
                        info_text = str(dext_ir.steps[selected_step].current_location)
                        update_steps_panel()
                        steps_panel.scroll_to_line(selected_step)
            elif key == curses.KEY_LEFT:
                current_panel_is_right = False
                update_steps_panel()
            elif key == curses.KEY_RIGHT:
                current_panel_is_right = True
                update_steps_panel()
            elif key == curses.KEY_PPAGE:
                if current_panel_is_right:
                    current_right_panel.scroll_page(up=True)
                else:
                    old_step = selected_step
                    selected_step = max(0, selected_step - height)
                    if selected_step != old_step:
                        update_right_panels()
                        info_text = str(dext_ir.steps[selected_step].current_location)
                        update_steps_panel()
                        steps_panel.scroll_to_line(selected_step)
            elif key == curses.KEY_NPAGE:
                if current_panel_is_right:
                    current_right_panel.scroll_page(up=False)
                else:
                    old_step = selected_step
                    selected_step = min(step_count - 1, selected_step + height - 1)
                    if old_step != selected_step:
                        update_right_panels()
                        info_text = str(dext_ir.steps[selected_step].current_location)
                        update_steps_panel()
                        steps_panel.scroll_to_line(selected_step)
            elif key == ord('g'):
                if current_panel_is_right:
                    current_right_panel.scroll_end(up=True)
                else:
                    if selected_step > 0:
                        selected_step = 0
                        update_right_panels()
                        info_text = str(dext_ir.steps[selected_step].current_location)
                        update_steps_panel()
                        steps_panel.scroll_to_line(selected_step)
            elif key == ord('G'):
                if current_panel_is_right:
                    current_right_panel.scroll_end(up=False)
                else:
                    if selected_step < step_count - 1:
                        selected_step = step_count - 1
                        update_right_panels()
                        info_text = str(dext_ir.steps[selected_step].current_location)
                        update_steps_panel()
                        steps_panel.scroll_to_line(selected_step)
            elif key == ord("n") or key == ord("N"):
                if current_panel_is_right:
                    current_right_panel_idx = (current_right_panel_idx + 1) % len(
                        right_panels
                    )

    curses.wrapper(_run_interactive)
    return ReturnCode.OK
