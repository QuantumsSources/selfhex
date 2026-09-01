import sys


class ANSICursor:
    @staticmethod
    def cur_up(rows: int = 1):
        sys.stdout.write(f"\033[{rows}A")

    @staticmethod
    def cur_dn(rows: int = 1):
        sys.stdout.write(f"\033[{rows}B")

    @staticmethod
    def cur_fwd(cols: int = 1):
        sys.stdout.write(f"\033[{cols}C")

    @staticmethod
    def cur_bwd(cols: int = 1):
        sys.stdout.write(f"\033[{cols}D")

    @staticmethod
    def cur_goto(row: int, col: int):
        sys.stdout.write(f"\033[{row};{col}H")

    @staticmethod
    def cur_reset():
        sys.stdout.write(f"\033[1;1H")

    @staticmethod
    def cur_hide():
        sys.stdout.write("\033[?25l")

    @staticmethod
    def cur_show():
        sys.stdout.write(f"\033[?25h")

class ANSIBuffer:
    @staticmethod
    def buf_flush():
        sys.stdout.flush()

    @staticmethod
    def buf_clear():
        sys.stdout.write("\033[2J")

    @staticmethod
    def buf_scroll_up(lines: int = 1):
        sys.stdout.write(f"\033[{lines}S")

    @staticmethod
    def buf_scroll_dn(lines: int = 1):
        sys.stdout.write(f"\033[{lines}T")

    @staticmethod
    def buf_enable_alt():
        sys.stdout.write(f"\033[?1049h")

    @staticmethod
    def buf_disable_alt():
        sys.stdout.write(f"\033[?1049l")

    @staticmethod
    def buf_set_title(title: str):
        sys.stdout.write(f"\033]0;{title}\033\\\\")

    @staticmethod
    def buf_get_hypr(url: str, label: str = "") -> str:
        return f"\033]8;;{url}\033\\\\{label}\033]8;;\033\\\\"

class ANSIStyles:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    REVERSE = "\033[7m"
    HIDDEN = "\033[8m"
    STRIKE = "\033[9m"

class ANSIForeground:
    FG_DARK = "\033[30m"
    FG_RED = "\033[31m"
    FG_GREEN = "\033[32m"
    FG_YELLOW = "\033[33m"
    FG_BLUE = "\033[34m"
    FG_MAGENTA = "\033[35m"
    FG_CYAN = "\033[36m"
    FG_WHITE = "\033[37m"

    FG_DARK_EX = "\033[90m"
    FG_RED_EX = "\033[91m"
    FG_GREEN_EX = "\033[92m"
    FG_YELLOW_EX = "\033[93m"
    FG_BLUE_EX = "\033[94m"
    FG_MAGENTA_EX = "\033[95m"
    FG_CYAN_EX = "\033[96m"
    FG_WHITE_EX = "\033[97m"

class ANSIBackground:
    BG_DARK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"

    BG_DARK_EX = "\033[100m"
    BG_RED_EX = "\033[101m"
    BG_GREEN_EX = "\033[102m"
    BG_YELLOW_EX = "\033[103m"
    BG_BLUE_EX = "\033[104m"
    BG_MAGENTA_EX = "\033[105m"
    BG_CYAN_EX = "\033[106m"
    BG_WHITE_EX = "\033[107m"

class ANSIColors(ANSIStyles, ANSIForeground, ANSIBackground):
    @staticmethod
    def apply_colors(text: str, *colors: str) -> str:
        prefix = ""
        for color in colors:
            prefix += color
        return f"{prefix}{text}{ANSIStyles.RESET}"