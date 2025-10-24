#!/usr/bin/env python3

import os
import sys
import re
from pathlib import Path
from typing import List, Optional
import curses


class AsciiDocFile:
    def __init__(self, path: Path):
        self.path = path
        self.content = path.read_text()
        self.lines = self.content.splitlines(keepends=True)

    def has_content_type(self) -> bool:
        return ":_mod-docs-content-type:" in self.content

    def find_first_heading_id(self) -> Optional[int]:
        for i, line in enumerate(self.lines):
            if re.match(r"^\[id=.*\]", line.strip()):
                return i
        return None

    def add_content_type(self, content_type: str) -> bool:
        heading_line = self.find_first_heading_id()
        if heading_line is None:
            return False

        new_line = f":_mod-docs-content-type: {content_type}\n"
        self.lines.insert(heading_line, new_line)
        self.path.write_text("".join(self.lines))
        return True

    def add_review_marker(self) -> bool:
        heading_line = self.find_first_heading_id()
        if heading_line is None:
            return False

        # Adds 'TODO: needs-type-review' instead of a mod type
        new_line = "// TODO: needs-type-review\n"
        self.lines.insert(heading_line, new_line)
        self.path.write_text("".join(self.lines))
        return True


class AsciiDocTUI:
    def __init__(self, directory: str):
        self.directory = Path(directory)
        self.files = self._find_asciidoc_files()
        self.current_index = 0
        self.scroll_offset = 0
        self.last_modification = None

    def _find_asciidoc_files(self) -> List[AsciiDocFile]:
        files = []
        for adoc_file in sorted(self.directory.rglob("*.adoc")):
            if adoc_file.is_file():
                try:
                    doc = AsciiDocFile(adoc_file)
                    if not doc.has_content_type():
                        files.append(doc)
                except Exception:
                    continue
        return files

    def run(self, stdscr):
        curses.curs_set(0)
        stdscr.clear()

        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)

        if not self.files:
            stdscr.addstr(
                0, 0, "No AsciiDoc files found without content type metadata."
            )
            stdscr.addstr(1, 0, "Press any key to exit...")
            stdscr.getch()
            return

        while self.current_index < len(self.files):
            self._draw_screen(stdscr)
            key = stdscr.getch()

            if key == ord("q") or key == ord("Q"):
                break
            elif key == ord("c") or key == ord("C"):
                self._add_type("CONCEPT", stdscr)
            elif key == ord("p") or key == ord("P"):
                self._add_type("PROCEDURE", stdscr)
            elif key == ord("r") or key == ord("R"):
                self._add_type("REFERENCE", stdscr)
            elif key == ord("?"):
                self._mark_for_review(stdscr)
            elif key == ord("u") or key == ord("U"):
                self._undo(stdscr)
            elif key == ord("f") or key == ord("F"):
                self._next_file()
            elif key == ord("b") or key == ord("B"):
                self._prev_file()
            elif key == ord("m") or key == ord("M"):
                self._scroll_down(stdscr)
            elif key == curses.KEY_DOWN:
                self._scroll_down(stdscr)
            elif key == curses.KEY_UP:
                self._scroll_up()

        stdscr.clear()
        stdscr.addstr(
            0, 0, f"Processed {self.current_index} of {len(self.files)} files."
        )
        stdscr.addstr(1, 0, "Press any key to exit...")
        stdscr.getch()

    def _draw_screen(self, stdscr):
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        current_file = self.files[self.current_index]

        header = (
            f"File {self.current_index + 1}/{len(self.files)}: {current_file.path.name}"
        )
        stdscr.addstr(0, 0, header[: width - 1], curses.color_pair(1))

        help_text = "[C]oncept [P]rocedure [R]eference [?]Review [U]ndo [F]wd [B]ack [M]ore [Q]uit"
        stdscr.addstr(1, 0, help_text[: width - 1], curses.color_pair(3))

        stdscr.addstr(2, 0, "─" * (width - 1))

        content_start = 3
        content_height = height - content_start - 1

        lines_to_show = current_file.lines[
            self.scroll_offset : self.scroll_offset + content_height
        ]

        for i, line in enumerate(lines_to_show):
            try:
                if re.match(r"^\[id=.*\]", line.strip()):
                    stdscr.addstr(
                        content_start + i, 0, line[: width - 1], curses.color_pair(2)
                    )
                else:
                    stdscr.addstr(content_start + i, 0, line[: width - 1])
            except curses.error:
                pass

        if self.scroll_offset + content_height < len(current_file.lines):
            try:
                stdscr.addstr(
                    height - 1,
                    0,
                    f"[More content below - line {self.scroll_offset + content_height}/{len(current_file.lines)}]",
                    curses.color_pair(3),
                )
            except curses.error:
                pass

        stdscr.refresh()

    def _add_type(self, content_type: str, stdscr):
        current_file = self.files[self.current_index]

        self.last_modification = (self.current_index, current_file.lines.copy())

        if current_file.add_content_type(content_type):
            height, width = stdscr.getmaxyx()
            msg = f"Added {content_type} to {current_file.path.name}"
            try:
                stdscr.addstr(height - 1, 0, msg[: width - 1], curses.color_pair(2))
                stdscr.refresh()
                curses.napms(1000)
            except curses.error:
                pass

        self._next_file()

    def _next_file(self):
        if self.current_index < len(self.files):
            self.current_index += 1
            self.scroll_offset = 0

    def _prev_file(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.scroll_offset = 0

    def _scroll_down(self, stdscr):
        height, _ = stdscr.getmaxyx()
        content_height = height - 4
        current_file = self.files[self.current_index]

        if self.scroll_offset + content_height < len(current_file.lines):
            self.scroll_offset += min(
                10, len(current_file.lines) - self.scroll_offset - content_height
            )

    def _scroll_up(self):
        self.scroll_offset = max(0, self.scroll_offset - 10)

    def _mark_for_review(self, stdscr):
        current_file = self.files[self.current_index]

        self.last_modification = (self.current_index, current_file.lines.copy())

        if current_file.add_review_marker():
            height, width = stdscr.getmaxyx()
            msg = f"Marked {current_file.path.name} for review"
            try:
                stdscr.addstr(height - 1, 0, msg[: width - 1], curses.color_pair(3))
                stdscr.refresh()
                curses.napms(1000)
            except curses.error:
                pass

        self._next_file()

    def _undo(self, stdscr):
        if self.last_modification is None:
            height, width = stdscr.getmaxyx()
            try:
                stdscr.addstr(
                    height - 1, 0, "Nothing to undo"[: width - 1], curses.color_pair(3)
                )
                stdscr.refresh()
                curses.napms(2000)
            except curses.error:
                pass
            return

        file_index, original_lines = self.last_modification
        undone_file = self.files[file_index]

        undone_file.lines = original_lines
        undone_file.path.write_text("".join(original_lines))

        self.last_modification = None

        height, width = stdscr.getmaxyx()
        msg = f"Undid changes to {undone_file.path.name}"
        try:
            stdscr.addstr(height - 1, 0, msg[: width - 1], curses.color_pair(2))
            stdscr.refresh()
            curses.napms(2000)
        except curses.error:
            pass

        self.current_index = file_index
        self.scroll_offset = 0


def main():
    if len(sys.argv) != 2:
        print("Usage: python module_tagger.py <modules_directory>")
        print("\nAdds content type metadata to AsciiDoc module files.")
        print("The script will process all .adoc files in the given directory")
        print("that don't already have :_mod-docs-content-type: metadata.")
        sys.exit(1)

    directory = sys.argv[1]

    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a valid directory")
        sys.exit(1)

    tui = AsciiDocTUI(directory)

    try:
        curses.wrapper(tui.run)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
