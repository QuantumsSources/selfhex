from __future__ import annotations
import os
import re
import select
import tty
import sys
import mmap
import signal
import termios
import selfhex_commons
from ansicodelib import ANSIForeground, ANSIColors as col
from selfhex_commons import col_str, log_info, log_warn, log_err

def get_slice(mm: mmap.mmap | None, offset: int, length: int) -> bytes:
    if not mm or offset >= len(mm):
        return b""
    return mm[offset:offset + length]

def open_mmap(path: str | None):
    if not path or not os.path.exists(path):
        return None, None, 0

    size = os.path.getsize(path)
    if size == 0:
        return None, None, 0

    f = open(path, "rb")
    mm = mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ)
    return f, mm, size

class TerminalResized(Exception):
    pass

class HexViewer:
    def __init__(self, file_1_path: str | None = None, file_2_path: str | None = None, bytes_per_line: int = 8):
        self.file_1_path = file_1_path
        self.file_2_path = file_2_path
        self.bytes_per_line = bytes_per_line

        self.created_clones = []
        self.f_1, self.mm_1, self.len_1 = None, None, 0
        self.f_2, self.mm_2, self.len_2 = None, None, 0

        self.current_line = 1
        self.marks = {}
        self.mark_pages = {}
        self.mark_lengths = {}
        self.mark_cols = {}
        self.marked_bytes = {}
        self._rebuild_mark_pages()

        self.running = True
        self.fits = True
        self.diff_mode = False
        self.region_diff = None

        self._off_digits = 4
        self.reload_files()
        if self.file_1_path:
            self.message = "Press ':' for commands, 'Q' to quit, ↑/↓ to scroll."
        else:
            self.message = "Press ':' for commands, 'Q' to quit."

    def _close_files(self):
        for mm in (self.mm_1, self.mm_2):
            if mm is not None:
                try:
                    mm.close()
                except Exception:
                    pass
        for f in (self.f_1, self.f_2):
            if f is not None:
                try:
                    f.close()
                except Exception:
                    pass

        self.f_1, self.mm_1, self.len_1 = None, None, 0
        self.f_2, self.mm_2, self.len_2 = None, None, 0

    def reload_files(self):
        try:
            self._close_files()

            self.f_1, self.mm_1, self.len_1 = open_mmap(self.file_1_path)
            if self.file_2_path:
                self.f_2, self.mm_2, self.len_2 = open_mmap(self.file_2_path)

            max_len = max(self.len_1, self.len_2)
            if self.region_diff:
                self.region_diff["buf1"] = self.mm_1 if self.mm_1 else b""
                self.region_diff["buf2"] = self.mm_2 if self.mm_2 else (self.mm_1 if self.mm_1 else b"")
                max_off: int = max(self.region_diff["start1"] + self.region_diff["length"],
                                   self.region_diff["start2"] + self.region_diff["length"])
                self._off_digits = max(4, len(f"{max_off:X}"))
            else:
                self._off_digits = max(4, len(f"{max_len:X}"))

            num_files = 0
            if self.file_1_path:
                num_files += 1
            if self.file_2_path:
                num_files += 1
            msg = f"{num_files if num_files > 0 else 'No'} file{'' if num_files == 1 else 's'}{' loaded successfully' if num_files > 0 else ' to reload'}"
            msg_size = f" (0x{self.len_1:04X}"
            if num_files > 0:
                if self.file_2_path:
                    msg_size += f" + 0x{self.len_2:04X} bytes; 0x{self.len_1 + self.len_2:04X} bytes total)"
                else:
                    msg_size += " bytes.)"
                self.message = msg + msg_size
            else:
                self.message = msg
            log_info("Files reloaded successfully!")
        except Exception as e:
            self.message = f"Error loading files: {e}"
            log_err(f"Error loading files: {e}")

    @property
    def total_data_lines(self) -> int:
        if self.region_diff:
            length = self.region_diff["length"]
            return (length + self.bytes_per_line - 1) // max(1, self.bytes_per_line)

        max_len = max(self.len_1, self.len_2)
        if max_len == 0:
            return 0
        return (max_len + self.bytes_per_line - 1) // max(1, self.bytes_per_line)

    @staticmethod
    def _center_line(line: str, buf: str = " "):
        ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        columns = os.get_terminal_size().columns
        visible_len = len(ANSI_ESCAPE.sub('', line))
        pad, comp = divmod(max(0, columns - visible_len), 2)

        return (buf * pad) + line + (buf * (pad + comp))

    def _get_header_line(self) -> str:
        if not self.fits:
            msg = " OUT OF SPACE! "
            return self._center_line(msg, "*")

        asc_width = max(7, self.bytes_per_line)
        asc_hdr_1 = f"{'ascii 1':^{asc_width}}"
        asc_hdr_2 = f"{'ascii 2':^{asc_width}}"

        if self.region_diff:
            rg = self.region_diff
            lbl1 = "File 1" if not rg["is_same_file"] else "Region 1"
            lbl2 = "File 2" if not rg["is_same_file"] else "Region 2"
            col_width = max(23, self.bytes_per_line * 3 - 1)
            off_col_width = self._off_digits + 4
            off_hdr_1 = f"{'off 1':^{off_col_width}}"
            off_hdr_2 = f"{'off 2':^{off_col_width}}"
            return f"{off_hdr_1} | {lbl1:^{col_width}} | {asc_hdr_1} | {off_hdr_2} | {lbl2:^{col_width}} | {asc_hdr_2} |"

        off_col_width = self._off_digits + 4
        off_hdr = f"{'offset':^{off_col_width}}"

        if self.file_1_path:
            header_1, col_width_1 = self._format_path_header(self.file_1_path)

            if self.file_2_path:
                header_2, col_width_2 = self._format_path_header(self.file_2_path)
                return f"{off_hdr} | {header_1} | {asc_hdr_1} | {header_2} | {asc_hdr_2} |"
            else:
                return f"{off_hdr} | {header_1} | {asc_hdr_1} |"
        else:
            msg = " NO FILES LOADED! "
            return self._center_line(msg, "*")

    def _get_line(self, line_idx: int) -> str:
        if line_idx == 0:
            return self._get_header_line()

        data_row = line_idx - 1
        if data_row < 0 or data_row >= self.total_data_lines:
            return ""

        if self.region_diff:
            return self._format_region_diff_line(data_row)
        return self._format_standard_line(data_row)

    @staticmethod
    def _format_byte(b: int, is_diff: bool = False, mark_col: str | None = None) -> str:
        hex_b = f"{b:02X}"

        if mark_col:
            fg = getattr(ANSIForeground, mark_col.upper(), col.FG_YELLOW)

            if is_diff:
                return col_str(hex_b, col.UNDERLINE + col.FG_RED)
            return fg + hex_b + col.RESET
        if is_diff:
            return col.FG_RED + hex_b + col.RESET
        if b == 0:
            return col.FG_DARK + "00" + col.RESET
        return hex_b

    @staticmethod
    def _get_ascii_char(b: int, is_diff: bool = False, mark_col: str|None = None) -> str:
        char = chr(b) if 32 <= b <= 126 else "."
        if mark_col:
            fg = getattr(ANSIForeground, mark_col.upper(), col.FG_YELLOW)

            if is_diff:
                return col_str(char, col.UNDERLINE + col.FG_RED)
            return fg + char + col.RESET
        if is_diff:
            return col.FG_RED + char + col.RESET
        if b == 0:
            return col.FG_DARK + char + col.RESET
        return char

    def _format_standard_line(self, data_row: int) -> str:
        offset = data_row * self.bytes_per_line
        fmt_offset = f"{offset:0{self._off_digits}X}"

        chunk_1 = get_slice(self.mm_1, offset, self.bytes_per_line)
        chunk_2 = get_slice(self.mm_2, offset, self.bytes_per_line) if self.mm_2 else b""

        col_width_1 = self._format_path_header(self.file_1_path)[1] if self.mm_1 and self.file_1_path else 23
        col_width_2 = self._format_path_header(self.file_2_path)[1] if self.mm_2 and self.file_2_path else 23
        asc_width = max(7, self.bytes_per_line)

        line_1_parts, line_2_parts = [], []
        ascii_1_parts, ascii_2_parts = [], []

        for i in range(self.bytes_per_line):
            b1 = chunk_1[i] if i < len(chunk_1) else None
            b2 = chunk_2[i] if i < len(chunk_2) else None

            is_diff = False
            if self.diff_mode and self.mm_2:
                if b1 != b2:
                    is_diff = True

            byte_offset = offset + i
            mark_col = None
            if self.marked_bytes.get(byte_offset, None) is not None:
                mark_col = self.mark_cols[self.marked_bytes[byte_offset][-1]]

            if b1 is not None:
                line_1_parts.append(self._format_byte(b1, is_diff, mark_col))
                ascii_1_parts.append(self._get_ascii_char(b1, is_diff, mark_col))
            if b2 is not None:
                line_2_parts.append(self._format_byte(b2, is_diff, mark_col))
                ascii_2_parts.append(self._get_ascii_char(b2, is_diff, mark_col))

        vis_len_1 = len(chunk_1) * 3 - 1 if chunk_1 else 0
        vis_len_2 = len(chunk_2) * 3 - 1 if chunk_2 else 0

        pad_hex_1 = " " * (col_width_1 - vis_len_1)
        pad_hex_2 = " " * (col_width_2 - vis_len_2)
        pad_asc_1 = " " * (asc_width - len(chunk_1))
        pad_asc_2 = " " * (asc_width - len(chunk_2))

        str_1, str_2 = " ".join(line_1_parts), " ".join(line_2_parts)
        str_asc_1, str_asc_2 = "".join(ascii_1_parts), "".join(ascii_2_parts)

        if self.mm_2:
            return f"[0x{fmt_offset}] | {str_1}{pad_hex_1} | {str_asc_1}{pad_asc_1} | {str_2}{pad_hex_2} | {str_asc_2}{pad_asc_2} |"
        else:
            return f"[0x{fmt_offset}] | {str_1}{pad_hex_1} | {str_asc_1}{pad_asc_1} |"

    def _format_region_diff_line(self, data_row: int) -> str:
        rg = self.region_diff
        start1, start2, length = rg["start1"], rg["start2"], rg["length"]
        buf1 = rg["buf1"]
        buf2 = rg["buf2"]

        rel_off = data_row * self.bytes_per_line
        off1 = start1 + rel_off
        off2 = start2 + rel_off

        len1 = min(self.bytes_per_line, start1 + length - off1)
        len2 = min(self.bytes_per_line, start2 + length - off2)

        chunk_1 = get_slice(buf1, off1, len1)
        chunk_2 = get_slice(buf2, off2, len2)

        col_width = max(23, self.bytes_per_line * 3 - 1)
        asc_width = max(7, self.bytes_per_line)

        line_1_parts, line_2_parts = [], []
        ascii_1_parts, ascii_2_parts = [], []

        for i in range(self.bytes_per_line):
            b1 = chunk_1[i] if i < len(chunk_1) else None
            b2 = chunk_2[i] if i < len(chunk_2) else None

            is_diff = (b1 != b2)
            mark_col_1 = None
            if self.marked_bytes.get(off1, None) is not None:
                mark_col_1 = self.mark_cols[self.marked_bytes[off1][-1]]
            mark_col_2 = None
            if self.marked_bytes.get(off2, None) is not None:
                mark_col_2 = self.mark_cols[self.marked_bytes[off2][-1]]

            if b1 is not None:
                line_1_parts.append(self._format_byte(b1, is_diff, mark_col_1))
                ascii_1_parts.append(self._get_ascii_char(b1, is_diff, mark_col_1))
            if b2 is not None:
                line_2_parts.append(self._format_byte(b2, is_diff, mark_col_2))
                ascii_2_parts.append(self._get_ascii_char(b2, is_diff, mark_col_2))

        vis_len_1 = len(chunk_1) * 3 - 1 if chunk_1 else 0
        vis_len_2 = len(chunk_2) * 3 - 1 if chunk_2 else 0

        pad_hex_1 = " " * (col_width - vis_len_1)
        pad_hex_2 = " " * (col_width - vis_len_2)
        pad_asc_1 = " " * (asc_width - len(chunk_1))
        pad_asc_2 = " " * (asc_width - len(chunk_2))

        str_1, str_2 = " ".join(line_1_parts), " ".join(line_2_parts)
        str_asc_1, str_asc_2 = "".join(ascii_1_parts), "".join(ascii_2_parts)

        fmt_off1 = f"0x{off1:0{self._off_digits}X}"
        fmt_off2 = f"0x{off2:0{self._off_digits}X}"

        return (
            f"[{fmt_off1}] | {str_1}{pad_hex_1} | {str_asc_1}{pad_asc_1} | "
            f"[{fmt_off2}] | {str_2}{pad_hex_2} | {str_asc_2}{pad_asc_2} |"
        )

    def render(self) -> bool:
        console_size = os.get_terminal_size()
        min_size = selfhex_commons.MIN_TERMINAL_SIZE

        max_lines = console_size.lines - 3

        if console_size.columns < min_size[0] or console_size.lines < min_size[1]:
            self.fits = False
            header_str = self._get_line(0)
            buf = ["\x1b[H", header_str + "\x1b[K\n"]

            for i in range(max_lines):
                if i < len(selfhex_commons.SELFHEX_SMALL_MSG):
                    line = selfhex_commons.SELFHEX_SMALL_MSG[i]
                    if console_size.columns < min_size[0]:
                        line = line.replace("%C", col_str("%C", col.FG_RED_EX))
                    if console_size.lines < min_size[1]:
                        line = line.replace("%L", col_str("%L", col.FG_RED_EX))
                    line = line.replace("%C", str(console_size.columns)).replace("%L", str(console_size.lines))
                    buf.append(f"{self._center_line(line)}\x1b[K\n")
                else:
                    buf.append("\x1b[K\n")

            sep = "-" * console_size.columns
            buf.append(f"{sep}\x1b[K\n")

            msg = "Commands disabled."
            buf.append(f"{msg}\x1b[K")
        else:
            self.fits = True

            header_str = self._center_line(self._get_line(0))
            buf = ["\x1b[H", header_str + "\x1b[K\n"]

            total_view_lines = self.total_data_lines + 1

            for i in range(max_lines):
                if self._has_files():
                    idx = self.current_line + i
                    if idx < total_view_lines:
                        line_str = self._center_line(self._get_line(idx))
                        buf.append(line_str + "\x1b[K\n")
                    else:
                        if idx == total_view_lines + console_size.lines - 6:
                            buf.append(f"{self._center_line(col_str(
                                '(woah... it\'s so empty down here...)', col.FG_DARK_EX))}\x1b[K\n")
                            continue
                        buf.append(f"\x1b[K\n")
                else:
                    if i < len(selfhex_commons.SELFHEX_EMPTY_MSG):
                        buf.append(f"{self._center_line(selfhex_commons.SELFHEX_EMPTY_MSG[i])}\x1b[K\n")
                    else:
                        buf.append("\x1b[K\n")

            sep = "-" * console_size.columns
            buf.append(f"{sep}\x1b[K\n")

            safe_msg = re.sub(r'\x1b(?!\[[0-9;]*m)', '^[', self.message)
            buf.append(f"{safe_msg}\x1b[K")

        sys.stdout.write("".join(buf))
        sys.stdout.flush()
        return True

    def _format_path_header(self, path: str) -> tuple[str, int]:
        min_width = max(23, self.bytes_per_line * 3 - 1)
        if not path:
            return " " * min_width, min_width

        max_width = max(32, min_width)
        path_len = len(path)

        if path_len <= min_width:
            col_width = min_width
            display_path = path
        elif path_len <= max_width:
            col_width = path_len
            display_path = path
        else:
            col_width = max_width
            display_path = "..." + path[-(max_width - 3):]

        return display_path.center(col_width), col_width

    def _parse_offset(self, token: str) -> int:
        token = token.strip()
        if token in self.marks:
            return self.marks[token]
        try:
            return int(token, 0)
        except ValueError:
            return int(token, 16)

    def _read_raw_line(self, prompt: str = ":") -> str | None:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        def _on_sigwinch(_, __):
            raise TerminalResized()
        old_handler = signal.signal(signal.SIGWINCH, _on_sigwinch)

        sys.stdout.write(f"\r\x1b[K{prompt}")
        sys.stdout.flush()

        buf = []
        try:
            tty.setcbreak(fd)
            while True:
                try:
                    r, _, _ = select.select([sys.stdin], [], [], 0.2)
                    if not r:
                        continue
                    char = sys.stdin.read(1)
                except TerminalResized:
                    self.render()
                    if not self.fits:
                        return None
                    sys.stdout.write(f"\r\x1b[K{prompt}{''.join(buf)}")
                    sys.stdout.flush()
                    continue

                if char in ('\r', '\n'):
                    break
                elif char in ('\x03', '\x1b'):
                    return None
                elif char in ('\x7f', '\x08'):
                    if buf:
                        buf.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                elif 32 <= ord(char) <= 126:
                    buf.append(char)
                    sys.stdout.write(char)
                    sys.stdout.flush()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            signal.signal(signal.SIGWINCH, old_handler)
        return "".join(buf)

    def _has_files(self) -> bool:
        return self.file_1_path is not None or self.file_2_path is not None

    def _mark_bytes(self, name: str, start_off: int, end_off: int):
        for i in range(end_off - start_off):
            offset = start_off + i
            if self.marked_bytes.get(offset, None) is None:
                self.marked_bytes[offset] = []
            self.marked_bytes[offset].append(name)

    def _unmark_bytes(self, name: str, start_off: int, end_off: int):
        for i in range(end_off - start_off):
            offset = start_off + i
            if self.marked_bytes.get(offset, None) is None:
                continue
            marks: list[str] = self.marked_bytes[offset]
            marks.remove(name)
            if not marks:
                self.marked_bytes.pop(offset, None)

    def _rebuild_mark_pages(self):
        if not self.marks:
            self.mark_pages = {1: "No marks to show."}
            return

        self.mark_pages = {}
        page = ""
        last_page = 1
        for mark in self.marks:
            if len(page) + len(mark) > selfhex_commons.MIN_TERMINAL_SIZE[0] - 1:
                self.mark_pages[last_page] = page.removesuffix(", ")
                page = ""
                last_page += 1
            page += f"{mark}, "
        if page:
            self.mark_pages[last_page] = page.removesuffix(", ")

    @staticmethod
    def get_mark_name(mark: str):
        return mark.upper().strip()[0:16]

    @staticmethod
    def get_color_name(color: str):
        if not color.startswith("FG_"):
            color = "FG_" + color
        return color.upper()

    def prompt_command(self):
        if not self.fits:
            return

        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)

        raw_input = self._read_raw_line(prompt=":")
        if raw_input is None:
            log_warn("CTRL+C, ESC, or terminal resize mid prompt!")
            return

        cmd_line = raw_input.strip()
        cmd_line = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', cmd_line)

        if not cmd_line:
            return

        parts = cmd_line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("j", "jmp", "jump"):
            if not self._has_files():
                self.message = "Please load a file before using the j[mp] command."
                return
            self.cmd_jump(args)
        elif cmd in ("m", "mrk", "mark"):
            if not self._has_files():
                self.message = "Please load a file before using the m[rk] command."
                return
            self.cmd_mark(args)
        elif cmd in ("um", "umk", "unmark"):
            if not self._has_files():
                self.message = "Please load a file before using the um[k] command."
                return
            self.cmd_unmark(args)
        elif cmd in ("r", "rel", "reload"):
            if not self._has_files():
                self.message = "Please load a file before using the r[el] command."
                return
            self.reload_files()
        elif cmd in ("c", "cln", "clone"):
            if not self._has_files():
                self.message = "Please load a file before using the c[ln] command."
            self.cmd_clone()
        elif cmd in ("f", "fn", "find"):
            if not self._has_files():
                self.message = "Please load a file before using the f[n] command."
                return
            self.cmd_find(args)
        elif cmd in ("s", "str", "stretch"):
            self.cmd_stretch(args)
        elif cmd in ("l", "ld", "load"):
            self.cmd_load(args)
        elif cmd in ("u", "uld", "unload"):
            if not self._has_files():
                self.message = "Please load a file before using the u[ld] command."
                return
            self.cmd_unload(args)
        elif cmd in ("n", "new"):
            self.cmd_new(args)
        elif cmd in ("sw", "swap"):
            if not self._has_files():
                self.message = "Please load a file before using the sw[ap] command."
                return
            self.cmd_swap()
        elif cmd in ("d", "diff"):
            if not self._has_files():
                self.message = "Please load a file before using the d[iff] command."
                return
            self.cmd_diff(args)
        elif cmd in ("q", "quit"):
            self.running = False
        elif cmd in ("h", "help", "?"):
            self.cmd_help(args)
        elif cmd in ("v", "ver", "version"):
            self.cmd_ver()
        else:
            self.message = f"Unknown command: ':{cmd}'."
            log_err(f"Unknown command: ':{cmd}'")

    def cmd_help(self, args):
        if not args:
            self.message = (f"Usage: h[elp] [<page>|<cmd>]"
                            f" | Commands: {len(selfhex_commons.COMMAND_HELP)}"
                            f" | Pages: 1-{len(selfhex_commons.HELP_PAGES)}")
        else:
            try:
                args[0] = int(args[0], 0)
            except ValueError:
                command = args[0].strip(":")
                if selfhex_commons.COMMAND_ALIASES.get(command, None) is not None:
                    command = selfhex_commons.COMMAND_ALIASES.get(command)

                if selfhex_commons.COMMAND_HELP.get(command, None) is not None:
                    self.message = selfhex_commons.COMMAND_HELP.get(command)
                else:
                    self.message = f"Invalid page no. or command: {args[0]}"
                    log_err(f"h[elp]: Invalid page no. or command: {args[0]}")
                return
            page_idx = max(1, min(args[0], len(selfhex_commons.HELP_PAGES)))
            page_content = selfhex_commons.HELP_PAGES[page_idx]
            self.message = f"{page_idx}/{len(selfhex_commons.HELP_PAGES)}: {page_content}"

    def cmd_ver(self):
        ver = selfhex_commons.SELFHEX_VERSION
        code = selfhex_commons.SELFHEX_VERCODE

        self.message = (f"{col_str('selfhex', col.FG_GREEN_EX)}"
                        f" {col_str(f'v{ver}', col.FG_YELLOW_EX)} ({col_str(code, col.FG_YELLOW_EX)})"
                        f" | made with {col_str('♥', col.FG_RED_EX)} by quantum")
        return

    def cmd_new(self, args):
        if not args:
            self.message = "Usage: n[ew] <name> [<size>] [force]"
            return
        if self.file_1_path and self.file_2_path:
            self.message = "No free slots to create file! Run u[ld]!"
            log_warn("n[ew]: Tried to create file with no free slots")
            return

        file_name = args[0]
        size = None
        force = "force" in args

        if len(args) >= 2:
            try:
                size = selfhex_commons.parse_file_size(args[1])
            except ValueError:
                pass
        if not selfhex_commons.create_new_file(file_name, size, force):
            self.message = f"Failed to create new file {file_name}"
            log_warn(f"n[ew]: Failed to create new file {file_name}")
            return

        self.cmd_load([file_name])
        log_info(f"n[ew]: Created and loaded new file {file_name}")

    def cmd_clone(self):
        if self.file_1_path and self.file_2_path:
            self.message = "No free slots to clone file! Run u[ld]!"
            log_warn("c[ln]: Tried to clone file with no free slots")
            return
        if not self.file_1_path:
            return
        temp_file = selfhex_commons.store_temp_file(self.file_1_path)
        self.file_2_path = temp_file
        self.created_clones.append(temp_file)
        self.reload_files()
        self.message = "Cloned slot 1 into slot 2"
        log_info(f"c[ln]: Cloned {self.file_1_path} into {self.file_2_path}")
        return

    def cmd_stretch(self, args):
        if not args:
            self.message = f"Current width: {self.bytes_per_line} bytes. Usage: s[tr] [<width>]"
            return
        try:
            new_width = self._parse_offset(args[0])
            if new_width <= 0:
                self.message = "Width must be greater than 0."
                log_warn("s[tr]: Attempt to set view width to non-positive value")
                return

            current_byte_offset = (self.current_line - 1) * self.bytes_per_line
            self.bytes_per_line = new_width

            self.current_line = (current_byte_offset // self.bytes_per_line) + 1
            self.message = (f"View width set to {self.bytes_per_line} byte"
                            f"{'' if self.bytes_per_line == 1 else 's'} per line")
            log_info(f"s[tr]: Set view width to {self.bytes_per_line} byte"
                        f"{'' if self.bytes_per_line == 1 else 's'} per line")
        except Exception as e:
            if "\x1b" in args[0]:
                self.message = "no"
            else:
                self.message = f"Invalid width value: {repr(args[0])}"
            log_warn(f"s[tr]: Invalid width value: {repr(args[0])} ({e})")

    def cmd_load(self, args):
        if not args:
            self.message = "Usage: l[d] <file>"
            return
        if not os.path.isfile(args[0]):
            self.message = f"File not found: {args[0]}"
            log_err(f"l[d]: File not found: {args[0]}")
            return
        if not self.file_1_path:
            self.file_1_path = args[0]
            log_info(f"l[d]: Loading file {self.file_1_path}")
            self.cmd_diff(["off"])
            self.reload_files()
        elif not self.file_2_path:
            self.file_2_path = args[0]
            if self.file_1_path == self.file_2_path:
                self.file_2_path = selfhex_commons.store_temp_file(args[0])
                log_info(f"l[d]: Clone file {args[0]} into slot 2")
            log_info(f"l[d]: Loading file {self.file_2_path}")
            self.cmd_diff(["off"])
            self.reload_files()
        else:
            self.message = "No free slots to open file! Run u[ld]!"
            log_warn("l[d]: Tried to load file with no free slots")

    def cmd_unload(self, args):
        if not args:
            self.file_1_path = None
            self.file_2_path = None
            for clone in self.created_clones:
                selfhex_commons.remove_temp_file(clone)

            self.cmd_diff(["off"])
            log_info("u[ld]: Unloading all files")
            self.reload_files()
            self.message = "Unloaded all files."
            return
        try:
            args[0] = int(args[0], 0)
            if args[0] not in (1, 2):
                raise ValueError
        except ValueError:
            self.message = f"Invalid slot: {args[0]}"
            log_err(f"u[ld]: Tried unloading invalid slot {str(args[0])}")
            return

        if args[0] == 1:
            if not self.file_1_path:
                self.message = "No file in slot 1!"
                log_warn("u[ld]: No file to unload in slot 1.")
                return
            if self.file_1_path in self.created_clones:
                selfhex_commons.remove_temp_file(self.file_1_path)
                log_info(f"u[ld]: Removing clone {self.file_1_path}")
            self.file_1_path = self.file_2_path
            self.file_2_path = None

            self.cmd_diff(["off"])
            self.reload_files()
            if self.file_1_path:
                log_info("u[ld]: Unloaded slot 1 and moved slot 2 into it")
                self.message = "Unloaded slot 1 and moved slot 2 into it"
            else:
                log_info("u[ld]: Unloaded slot 1.")
                self.message = "Unloaded slot 1"
            return
        elif args[0] == 2:
            if not self.file_2_path:
                self.message = "No file in slot 2!"
                log_warn("u[ld]: No file to unload in slot 2")
                return
            if self.file_2_path in self.created_clones:
                selfhex_commons.remove_temp_file(self.file_2_path)
                log_info(f"u[ld]: Removing clone {self.file_2_path}")

            self.file_2_path = None
            self.region_diff = None
            self.diff_mode = False

            self.reload_files()
            log_info("u[ld]: Unloaded slot 2")
            self.message = "Unloaded slot 2"
            return

    def cmd_swap(self):
        if not self.file_1_path:
            self.message = "No file in slot 1!"
            log_warn("sw[ap]: No file in slot 1 to swap")
            return
        if not self.file_2_path:
            self.message = "No file in slot 2!"
            log_warn("sw[ap]: No file in slot 2 to swap")
            return
        temp_2_path = self.file_2_path
        self.file_2_path = self.file_1_path
        self.file_1_path = temp_2_path
        self.reload_files()
        self.message = "Swapped slot 1 and 2."
        log_info("sw[ap]: Swapped slot 1 and 2")

    def cmd_diff(self, args):
        buf1 = self.mm_1 if self.mm_1 else b""
        buf2 = self.mm_2 if self.mm_2 else buf1
        len1 = self.len_1
        len2 = self.len_2 if self.mm_2 else len1

        if not args:
            if self.region_diff:
                self.region_diff = None
                self.diff_mode = False
                self.message = "Region diff disabled."
                log_info("d[iff]: Region diff disabled")
            else:
                self.diff_mode = not self.diff_mode
                if buf1 == buf2:
                    self.region_diff = {
                        "start1": 0, "start2": 0, "length": len1,
                        "buf1": buf1, "buf2": buf1, "is_same_file": True
                    }
                    self._off_digits = max(4, len(f"{len1:X}"))
                status = "enabled" if self.diff_mode else "disabled"
                self.message = f"Diff mode is now {status}."
            return

        if args[0].lower() == "off":
            self.region_diff = None
            self.diff_mode = False
            self.message = "Diff mode disabled."
            log_info("d[iff]: Diff mode disabled")
            return

        try:
            if len(args) == 1:
                start1 = self._parse_offset(args[0])
                if start1 > len1:
                    self.message = "Offset 1 out of file"
                    return
                start2 = start1
                length = len1 - start1
            elif len(args) >= 2:
                start1 = self._parse_offset(args[0])
                if start1 > len1:
                    self.message = "Offset 1 out of file"
                    return
                start2 = self._parse_offset(args[1])
                if start2 > len2:
                    self.message = "Offset 2 out of file"
                    return
                length = max(len1 - start1, len2 - start2)
            else:
                self.message = "Usage: d[iff] [off|(<off1> [<off2> [<range>]])]"
                return

            if len(args) >= 3:
                length = self._parse_offset(args[2])

            if length <= 0:
                self.message = "Invalid length"
                log_err("d[iff]: Diff length not positive value")
                return
            elif length > max(len1 - start1, len2 - start2):
                length = max(len1 - start1, len2 - start2)

            self.region_diff = {
                "start1": start1,
                "start2": start2,
                "length": length,
                "buf1": buf1,
                "buf2": buf2,
                "is_same_file": buf1 == buf2
            }
            self.diff_mode = True
            self.current_line = 1
            max_off = max(start1 + length, start2 + length)
            self._off_digits = max(4, len(f"{max_off:X}"))
            self.message = f"Diffing 0x{start1:04X} vs 0x{start2:04X} (size: 0x{length:04X} / {length} bytes)"
        except Exception as e:
            self.message = f"Error parsing regions: {e}"
            log_err(f"d[iff]: Error parsing regions: {e}")

    def cmd_jump(self, args):
        if not args:
            self.message = "Usage: j[mp] ([+-]<offset>)|<mark>"
            return

        target = args[0].strip()
        relative = None
        if target.startswith("+"):
            relative = "+"
            target = target[1:]
        elif target.startswith("-"):
            relative = "-"
            target = target[1:]

        if self.get_mark_name(target) in self.marks:
            target_offset = self.marks[self.get_mark_name(target)]
        else:
            try:
                target_offset = int(target, 0)
            except ValueError:
                try:
                    target_offset = int(target, 16)
                except ValueError:
                    self.message = f"Invalid offset or unknown mark: {args[0]}"
                    log_err(f"j[mp]: Invalid offset or unknown mark: {args[0]}")
                    return

        current_byte_offset = (self.current_line - 1) * self.bytes_per_line

        if relative == "+":
            final_offset = current_byte_offset + target_offset
        elif relative == "-":
            final_offset = current_byte_offset - target_offset
        else:
            final_offset = target_offset

        final_offset = max(0, final_offset)
        line_idx = final_offset // self.bytes_per_line
        max_scroll = max(1, self.total_data_lines)

        self.current_line = max(1, min(max_scroll, line_idx + 1))
        self.message = f"Jumped to 0x{final_offset:04X}"

    def cmd_mark(self, args: list[str]):
        if not args:
            self.message = f"Marks set: {len(self.marks)} | Pages: 1/{len(self.mark_pages)}"
            return

        try:
            page = int(args[0], 0)
            page_idx = max(1, min(page, len(self.mark_pages)))
            page_content = self.mark_pages[page_idx]
            self.message = page_content
            return
        except ValueError:
            name = self.get_mark_name(args[0])

        color: str | None = None
        nums = []

        for arg in args[1:]:
            if hasattr(ANSIForeground, self.get_color_name(arg)):
                if color is None:
                    color = self.get_color_name(arg)
            else:
                try:
                    num = int(arg, 0)
                    nums.append(num)
                except ValueError:
                    try:
                        num = self._parse_offset(arg)
                        nums.append(num)
                    except ValueError:
                        pass

        if not nums:
            offset = (self.current_line - 1) * self.bytes_per_line
        else:
            offset = max(0, nums[0])

        mark_len = self.bytes_per_line
        if len(nums) > 1:
            mark_len = nums[1]

        moved = None
        if name in self.marks:
            moved = name
            old_offset = self.marks[name]
            old_length = self.mark_lengths.get(name)
            self._unmark_bytes(name, old_offset, old_offset + old_length)

        self.marks[name] = offset
        self.mark_lengths[name] = mark_len
        self._mark_bytes(name, offset, offset + mark_len)
        if color is not None:
            self.mark_cols[name] = self.get_color_name(color)
        else:
            self.mark_cols[name] = selfhex_commons.get_rand_color()

        if moved is not None:
            self.message = f"Moved mark '{moved}' to 0x{offset:04X}"
            log_info(f"m[rk]: Moved mark '{moved}' to 0x{offset:04X}")
        else:
            self.message = f"Set new mark '{name}' @ 0x{offset:04X}"
            log_info(f"m[rk]: Set new mark {name} @ 0x{offset:04X}")
        self._rebuild_mark_pages()
        return

    def cmd_unmark(self, args):
        if not args:
            self.message = "Usage: um[k] <name>"
            return

        name = self.get_mark_name(args[0])
        if name in self.marks:
            offset = self.marks[name]
            length = self.mark_lengths[name]
            self._unmark_bytes(name, offset, offset + length)

            self.mark_cols.pop(name, None)
            self.mark_lengths.pop(name, None)
            self.marks.pop(name, None)
            self.message = f"Cleared mark {name}"
            log_info(f"u[m]: Cleared mark {name}")
            self._rebuild_mark_pages()

            return
        self.message = f"Mark {name} not found."
        log_warn(f"u[m]: Mark {name} not found.")
        return

    def cmd_find(self, args):
        if not args:
            self.message = 'Usage: f[n] (<hex>|"<str>")'
            return

        if not self.mm_1 or self.len_1 == 0:
            self.message = "No file loaded in slot 1 or file is empty."
            log_warn("f[n]: No file loaded in slot 1 or file is empty.")
            return

        s = "".join(args).replace(" ", "").strip()
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            target_bytes = s[1:-1].encode("utf-8", errors="ignore")
        elif s.lower().startswith("0x"):
            clean_hex = s[2:]
            if len(clean_hex) % 2 != 0:
                clean_hex = "0" + clean_hex
            try:
                target_bytes = bytes.fromhex(clean_hex)
            except ValueError:
                self.message = f"Invalid hex string '{s}'"
                log_warn(f"f[n]: Invalid hex string '{s}'")
                return
        else:
            try:
                target_bytes = bytes.fromhex(s)
            except ValueError:
                target_bytes = s.encode("utf-8", errors="ignore")

        current_offset = (self.current_line - 1) * self.bytes_per_line

        idx: int = self.mm_1.find(target_bytes, current_offset + 1)
        if idx == -1:
            idx = self.mm_1.find(target_bytes, 0, current_offset)
        if idx != -1:
            self.cmd_jump([str(idx)])
            mark_name = self.get_mark_name(target_bytes.hex())
            self.cmd_mark([f"f_{mark_name}", str(idx), str(len(target_bytes))])

            self.message = f"Found sequence at 0x{idx:04X}"
            log_info(f"f[n]: Found sequence at 0x{idx:04X}")
        else:
            self.message = (f"Hex sequence {target_bytes} not found in file 1"
                            f"{f' after 0x{current_offset:04X}' if current_offset > 0 else ''}.")
            log_info(f"f[n]: Hex sequence {target_bytes} not found in file 1"
                     f"{f' after 0x{current_offset:04X}' if current_offset > 0 else ''}.")

    def run(self) -> str:
        exit_status = "success"

        try:
            while self.running:
                if not self.render():
                    log_err("An error occurred during the rendering process.")
                    exit_status = "An error occurred during the rendering process."
                    break

                key = selfhex_commons.get_key()
                if key is None:
                    continue

                max_scroll = max(1, self.total_data_lines)

                if key in ("UP", "w", "k"):
                    self.current_line = max(1, self.current_line - 1)
                    self.message = ""
                elif key in ("DOWN", "s", "j"):
                    self.current_line = min(max_scroll, self.current_line + 1)
                    self.message = ""
                elif key in ("SHIFT_UP", "W", "K"):
                    self.current_line = max(1, self.current_line - selfhex_commons.FAST_SCROLL_OFFSET)
                    self.message = ""
                elif key in ("SHIFT_DOWN", "S", "J"):
                    self.current_line = min(max_scroll, self.current_line + selfhex_commons.FAST_SCROLL_OFFSET)
                    self.message = ""
                elif key in ("q", "Q"):
                    self.running = False
                elif key == ":":
                    self.prompt_command()
        except OSError:
            log_err("selfhex tried to run in non-native terminal environment")
            exit_status = "selfhex tried to run in non-native terminal environment."
        except Exception as e:
            lines = selfhex_commons.get_traceback_lines(e.__traceback__)
            log_err(f"An unknown error occurred while running selfhex @ ln{'s' if len(lines) > 1 else ''} {' > '.join(lines)}: {e}")
            exit_status = f"An unknown error occurred while running selfhex @ ln{'s' if len(lines) > 1 else ''} {' > '.join(lines)}: {e}"
        finally:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
            for clone in self.created_clones:
                selfhex_commons.remove_temp_file(clone)
                log_info(f"Removing clone {clone}")
            log_info("Quitting!")
            selfhex_commons.log_stop()

        return exit_status

def main(file_1: str | None = None, file_2: str | None = None, width: int = 8) -> str:
    viewer = HexViewer(file_1, file_2, width)
    return viewer.run()