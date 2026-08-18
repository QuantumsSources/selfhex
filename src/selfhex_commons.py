from __future__ import annotations
import re
import os
import sys
import tty
import time
import select
import random
import termios
from colorama import Fore, init

SELFHEX_VERSION = "1.20.6+7"
SELFHEX_VERCODE = "Painter"
MIN_TERMINAL_SIZE = (80, 20)
FAST_SCROLL_OFFSET = 128

init()

def col_str(string: str, fg: Fore|None = None) -> str:
    if fg is not None:
        string = fg + string + Fore.RESET
    return string

SELFHEX_EMPTY_MSG = [
    f"",
    f"Welcome to {col_str('selfhex', Fore.LIGHTGREEN_EX)}!",
    f"",
    f"This space is where your files will appear once you load them!",
    f"You can use the {col_str('load (:l[d])', Fore.LIGHTYELLOW_EX)} command to do so.",
    f"",
    f"Alternatively, you can use the {col_str('new (:n[ew])', Fore.LIGHTYELLOW_EX)} command to create...",
    f"...a new file and load it into the next free slot.",
    f"",
    f"For a list of all commands, use the {col_str('help (:h[elp])', Fore.LIGHTYELLOW_EX)} command.",
    f"",
    f"You are running version {col_str(SELFHEX_VERSION, Fore.LIGHTYELLOW_EX)}"
        f" ({col_str(SELFHEX_VERCODE, Fore.LIGHTYELLOW_EX)})"
        f" of {col_str('selfhex', Fore.LIGHTGREEN_EX)}."
]

SELFHEX_SMALL_MSG = [
    f"",
    f"selfhex is feeling...",
    f"...claustrophobic!",
    f"",
    f"The min. size is {MIN_TERMINAL_SIZE[0]}x{MIN_TERMINAL_SIZE[1]}.",
    f"(currently %Cx%L)"
]

COMMANDS = [
    "h[elp] [<page>|<cmd>]",
    "v[er]",
    "n[ew] <name> [<size>] [force]",
    "r[el]",
    "c[ln]",
    "d[iff] [off|(<off1> [<off2> [<range>]])]",
    "f[n] (<hex>|<str>)",
    "j[mp] ([+-]<offset>)|<mark>",
    "m[rk] [<name> [<col>] [<off> [<len>]]]",
    "um[k] <name>",
    "l[d] <file>",
    "u[ld] [1|2]",
    "sw[ap]",
    "s[tr] [<width>]"
]

HELP_PAGES = {}
def _load_cmds():
    page = ""
    last_page = 1
    for cmd in COMMANDS:
        if len(page) + len(cmd) > MIN_TERMINAL_SIZE[0] - 1:
            HELP_PAGES[last_page] = page.removesuffix(", ")
            page = ""
            last_page += 1
        page += f"{cmd}, "
    if page:
        HELP_PAGES[last_page] = page.removesuffix(", ")

_load_cmds()

COMMAND_HELP = {
    "h":  "h[elp] [<page>|<cmd>]: display general help page or command usage",
    "v":  "v[er]: show selfhex version",
    "n":  "n[ew] <name> [<size>] [force]: create & load a new file",
    "r":  "r[el]: reload loaded files from disk",
    "c":  "c[ln]: clone file 1 for self-diffing",
    "d":  "d[iff] [off|(<off1> [<off2> [<range>]])]: compare files, offsets, or ranges",
    "f":  "f[n] (<hex>|<str>): search for hex sequence or text in file 1",
    "j":  "j[mp] ([+-]<offset>|<mark>): jump to abs/rel offset or mark",
    "m":  "m[rk] [<name> [<col>] [<off> [<len>]]]: place a mark at given offset",
    "um":  "um[k] <name>: clear a mark",
    "l":  "l[d] <file>: load a file into next free slot",
    "u":  "u[ld] [1|2]: unload slot 1, 2, or both",
    "sw": "sw[ap]: swap files in slot 1 and slot 2",
    "s":  "s[tr] [<width>]: set display width (bytes per line)",
}

COMMAND_ALIASES = {
    "help": "h",
    "ver": "v",
    "version": "v",
    "new": "n",
    "diff": "d",
    "fn": "f",
    "find": "f",
    "rel": "r",
    "reload": "r",
    "cln": "c",
    "clone": "c",
    "jmp": "j",
    "jump": "j",
    "mrk": "m",
    "mark": "m",
    "umk": "um",
    "unmark": "um",
    "str": "s",
    "stretch": "s",
    "swap": "sw",
    "ld": "l",
    "load": "l",
    "uld": "u",
    "unload": "u"
}

def get_key(timeout: float = 0.05):
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        r, _, _ = select.select([fd], [], [], timeout)
        if not r:
            return None

        ch_bytes = os.read(fd, 1)
        if not ch_bytes:
            return None
        ch = ch_bytes.decode('utf-8')

        if ch == "\x1b":
            r2, _, _ = select.select([fd], [], [], 0.05)
            if r2:
                ch2 = os.read(fd, 1).decode('utf-8')
                if ch2 == "[":
                    r3, _, _ = select.select([fd], [], [], 0.05)
                    if r3:
                        ch3 = os.read(fd, 1).decode('utf-8')
                        if ch3 == "A":
                            return "UP"
                        if ch3 == "B":
                            return "DOWN"
                        if ch3 == "1":
                            r4, _, _ = select.select([fd], [], [], 0.05)
                            if r4:
                                seq = os.read(fd, 3).decode('utf-8')
                                if seq == ";2A":
                                    return "SHIFT_UP"
                                if seq == ";2B":
                                    return "SHIFT_DOWN"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old_settings)

def create_new_file(name: str, sz: int | None = None, force: bool = False) -> bool:
    if os.path.exists(name):
        if not force:
            entity_type = "folder" if os.path.isdir(name) else "file"
            print(f"selfhex: error: {entity_type} with name {name} already exists!")
            return False
        else:
            print(f"selfhex: warning: overwriting file {name}")
            os.remove(name)

    with open(name, "wb") as f:
        if sz is not None:
            f.write(random.randbytes(sz))

    size_msg = f" ({sz} bytes)" if sz is not None else ""
    print(f"selfhex: info: created file {name}{size_msg}")
    return True

SESSION_TEMP_FILES: list[str] = []

def store_temp_file(file: str) -> str:
    temp_path = file + ".old"
    with open(file, "rb") as src, open(temp_path, "wb") as dst:
        dst.write(src.read())
    SESSION_TEMP_FILES.append(temp_path)
    return temp_path

def remove_temp_file(file: str):
    if not SESSION_TEMP_FILES:
        return
    if file in SESSION_TEMP_FILES:
        SESSION_TEMP_FILES.remove(file)
        if os.path.exists(file):
            try:
                os.remove(file)
            except OSError:
                pass

def clear_temp_files():
    while SESSION_TEMP_FILES:
        temp_file = SESSION_TEMP_FILES.pop()
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError:
                pass

def parse_file_size(size_str: str) -> int:
    if not isinstance(size_str, str):
        raise TypeError(f"Expected string, got {type(size_str).__name__}")

    size_str = size_str.strip()
    if not size_str:
        raise ValueError("Cannot parse empty string")

    try:
        return int(size_str, 0)
    except ValueError:
        pass

    pattern = r"^\s*([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)\s*([a-zA-Z]+)?\s*$"
    match = re.match(pattern, size_str)

    if not match:
        raise ValueError(f"Invalid file size format: '{size_str}'")

    num_str, unit = match.groups()
    number = float(num_str)

    if not unit:
        return int(number)

    unit = unit.lower()

    standard_units = {
        "b": 0, "byte": 0, "bytes": 0,
        "k": 1, "kb": 1, "kilobyte": 1, "kilobytes": 1,
        "m": 2, "mb": 2, "megabyte": 2, "megabytes": 2,
        "g": 3, "gb": 3, "gigabyte": 3, "gigabytes": 3
    }

    iec_units = {
        "kib": 1, "kibibyte": 1, "kibibytes": 1,
        "mib": 2, "mebibyte": 2, "mebibytes": 2,
        "gib": 3, "gibibyte": 3, "gibibytes": 3
    }

    if unit in iec_units:
        multiplier = 1024 ** iec_units[unit]
    elif unit in standard_units:
        multiplier = 1000 ** standard_units[unit]
    else:
        raise ValueError(f"Unknown size unit: '{unit}' in '{size_str}'")

    return int(number * multiplier)

def get_rand_color() -> str:
    PALETTE = ["CYAN", "MAGENTA", "YELLOW", "GREEN", "BLUE", "LIGHTWHITE_EX"]
    return random.choice(PALETTE)

close_log_file_path: str = ""
latest_log_file_path: str = ""
LOG_FOLDER = os.path.expanduser("~/.selfhex")

def log(level: str, message: str):
    if close_log_file_path == "" or latest_log_file_path == "":
        return
    cur_time = time.strftime("%H:%M:%S")
    try:
        with open(latest_log_file_path, "a") as f:
            f.write(f"{level} @ {cur_time}: {message}\n")
    except Exception as e:
        sys.stderr.write(f"Logging error: {e}\n")

def log_init():
    global close_log_file_path, latest_log_file_path

    if not os.path.exists(LOG_FOLDER):
        os.makedirs(LOG_FOLDER, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    close_log_file_path = os.path.join(LOG_FOLDER, f"selfhex-{timestamp}.log")
    latest_log_file_path = os.path.join(LOG_FOLDER, "latest.log")

    open(close_log_file_path, "w").close()
    open(latest_log_file_path, "w").close()

    log("INFO", f"Logging started.")

def log_stop():
    if close_log_file_path == "" or latest_log_file_path == "":
        return
    log("INFO", f"Transferring logs to {close_log_file_path}")
    log("INFO", "Stopping logs")

    try:
        with open(latest_log_file_path, "rb") as src, open(close_log_file_path, "wb") as dst:
            dst.write(src.read())
    except Exception as e:
        sys.stderr.write(f"Log transfer error: {e}\n")