from __future__ import annotations
import os
import sys
import selfhex_tui
import selfhex_commons
from ansicodelib import ANSIColors as col
from selfhex_commons import col_str, log_info, log_warn, log_err


def get_args(sys_args: list[str]) -> tuple[list[str], str, dict[str, str]]:
    files: list[str] = []
    option_str: str = ""
    dashed_args: dict[str, str] = {}

    for arg in sys_args:
        if arg.startswith("--"):
            arg_clean = arg.lstrip("-").split("=", 1)
            name = arg_clean[0].lower()
            value = arg_clean[1] if len(arg_clean) > 1 else ""
            dashed_args[name] = value
        elif arg.startswith("-"):
            option_str += arg.lstrip("-")
        else:
            files.append(arg)
    return files, option_str, dashed_args

def run_selfhex(file_1: str | None = None, file_2: str | None = None, width: int = 8):
    sys.stdout.write("\033[?1049h")
    sys.stdout.flush()
    print("\033[H", end="")
    result = None
    try:
        result = selfhex_tui.main(file_1, file_2, width)
    except KeyboardInterrupt:
        return
    finally:
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
        if result is not None and result != "success":
            log_warn(f"selfhex quit unexpectedly: {result}", True)
            sys.exit(1)

def check_file(file: str) -> bool:
    if not os.path.exists(file):
        log_err(f"{file} does not exist!", True)
        return False
    if os.path.isdir(file):
        log_err(f"{file} is a directory!", True)
        return False
    return True

def main(sys_args: list[str]):
    files, option_str, args = get_args(sys_args)

    if not files and not option_str and not args:
        run_selfhex(None, None)
        return

    if "help" in args or "h" in option_str:
        print("usage: selfhex [<OPTION>] [<file_1> [<file_2>]] [<ARGS>]")
        print("OPTION:")
        print(col_str("* ", col.FG_RED) + col_str("-h", col.FG_GREEN_EX) + ": print this help")
        print(col_str("* ", col.FG_RED) + col_str("-v", col.FG_GREEN_EX) + ": print version information")
        print(col_str("-c", col.FG_GREEN_EX) + ": clone file 1 for self-diffing. is overridden if file 2 is set.")
        print("ARGS:")
        print(col_str("* ", col.FG_RED) + col_str("--help", col.FG_YELLOW_EX) + ": same as -h")
        print(col_str("* ", col.FG_RED) + col_str("--version", col.FG_YELLOW_EX) + ": same as -v")
        print(col_str("--clone", col.FG_YELLOW_EX) + ": same as -c")
        print("     " + col_str("--keep-clone", col.FG_YELLOW_EX) + ": keep clone file after exit")
        print(col_str("--new", col.FG_YELLOW_EX) + "=<name>: create new file")
        print("     " + col_str("--force", col.FG_YELLOW_EX) + ": overwrite file if it already exists")
        print("     " + col_str("--size", col.FG_YELLOW_EX) + "=<size>: specify file size")
        print(col_str("--width", col.FG_YELLOW_EX) + "=<width>: set bytes per line width on startup")
        print(col_str("* ", col.FG_RED) + col_str("--clear-logs", col.FG_YELLOW_EX) + ": clear logs folder")
        print(col_str("* ", col.FG_RED) + col_str("--show-logs", col.FG_YELLOW_EX) + ": print log folder location")
        print("\nOPTIONS and ARGS marked with " + col_str("*", col.FG_RED) + " will exit early.")
        print("priority goes from top to bottom of this list.")
        return

    if "version" in args or "v" in option_str:
        ver = selfhex_commons.SELFHEX_VERSION
        code = selfhex_commons.SELFHEX_VERCODE

        print(f"{col_str('selfhex', col.FG_GREEN_EX)}"
              f" {col_str(f'v{ver}', col.FG_YELLOW_EX)} ({col_str(code, col.FG_YELLOW_EX)})"
              f" - self-diffing capable hex viewer"
              f" | made with {col_str('♥', col.FG_RED_EX)} by quantum")
        return

    if "clear-logs" in args:
        if os.path.exists(selfhex_commons.LOG_FOLDER):
            for f in os.listdir(selfhex_commons.LOG_FOLDER):
                os.remove(os.path.join(selfhex_commons.LOG_FOLDER, f))
            os.rmdir(selfhex_commons.LOG_FOLDER)
        return

    if "show-logs" in args:
        log_info(f"log folder location is {selfhex_commons.LOG_FOLDER}", True)
        return

    if "new" in args:
        new_file_name = args["new"]
        if not new_file_name:
            log_err("--new requires <name> parameter", True)
            return

        size = None
        if "size" in args:
            try:
                size = selfhex_commons.parse_file_size(args["size"])
            except ValueError:
                log_err(f"invalid size: {args['size']}!", True)
                return

        if not selfhex_commons.create_new_file(new_file_name, size, "force" in args):
            return
        files.insert(0, new_file_name)

    if len(files) > 2:
        log_err("selfhex only supports opening up to two files at a time!", True)
        return

    for f in files:
        if not check_file(f):
            return

    width: str|int = args["width"] if "width" in args else "8"
    try:
        width: int = int(str(width), 0)
    except ValueError:
        log_err(f"invalid width value: {width}", True)
        width: int = 8

    make_clone = "c" in option_str or "clone" in args and args["clone"].lower() in ("", "true", "yes", "y", "1")
    if make_clone and not files:
        log_err("--clone requires a file", True)
        return

    keep_clone = "keep-clone" in args and args["keep-clone"].lower() in ("", "true", "yes", "y", "1")
    try:
        if not files:
            run_selfhex(None, None, width)
        elif len(files) == 1:
            if make_clone:
                log_info("cloning file 1 for self-diffing", True)
                temp_file = selfhex_commons.store_temp_file(files[0])
                run_selfhex(temp_file, files[0], width)
            else:
                run_selfhex(files[0], None, width)
        else:
            same_file = os.path.samefile(files[0], files[1])
            if same_file:
                temp_file = selfhex_commons.store_temp_file(files[0])
                run_selfhex(temp_file, files[0], width)
                return
            elif make_clone:
                log_warn("--clone is ignored when two files are provided.", True)
            run_selfhex(files[0], files[1], width)
    except Exception as e:
        log_err(f"an error occurred running selfhex", True)
        log_err(f"{e}", True)
    finally:
        if not keep_clone:
            selfhex_commons.clear_temp_files()

if __name__ == "__main__":
    if sys.platform not in ("linux", "android"):
        log_info("selfhex currently only works on linux", True)
        sys.exit(0)
    main(sys.argv[1:])