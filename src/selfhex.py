from __future__ import annotations
import os
import sys
import selfhex_tui
import selfhex_commons
from colorama import Fore
from selfhex_commons import col_str


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

def run_selfhex(file_1: str | None = None, file_2: str | None = None):
    sys.stdout.write("\033[?1049h")
    sys.stdout.flush()
    print("\033[H", end="")
    result = None
    try:
        print("selfhex: Loading selfhex. Please wait.")
        result = selfhex_tui.main(file_1, file_2)
    except KeyboardInterrupt:
        return
    finally:
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
        if result is not None and result != "success":
            print(f"selfhex: {result}")
            sys.exit(1)

def check_file(file: str) -> bool:
    if not os.path.exists(file):
        print(f"selfhex: error: {file} does not exist!")
        return False
    if os.path.isdir(file):
        print(f"selfhex: error: {file} is a directory!")
        return False
    return True

def main(sys_args: list[str]):
    files, option_str, args = get_args(sys_args)

    if not files and not option_str and not args:
        run_selfhex(None, None)
        return

    if "clear-logs" in args:
        if os.path.exists(selfhex_commons.LOG_FOLDER):
            for f in os.listdir(selfhex_commons.LOG_FOLDER):
                os.remove(os.path.join(selfhex_commons.LOG_FOLDER, f))
            os.rmdir(selfhex_commons.LOG_FOLDER)
        return

    if "show-logs" in args:
        print(f"selfhex: info: log folder location is {selfhex_commons.LOG_FOLDER}")
        return

    if "help" in args or "h" in option_str:
        print("usage: selfhex [<OPTION>] [<file_1> [<file_2>]] [<ARGS>]")
        print("OPTION:")
        print(col_str("-h", Fore.LIGHTGREEN_EX) + ": print this help")
        print(col_str("-v", Fore.LIGHTGREEN_EX) + ": print version information")
        print(col_str("-c", Fore.LIGHTGREEN_EX) + ": clone file 1 for self-diffing. is overridden if file 2 is set.")
        print("ARGS:")
        print(col_str("--help", Fore.LIGHTYELLOW_EX) + ": same as -h")
        print(col_str("--version", Fore.LIGHTYELLOW_EX) + ": same as -v")
        print(col_str("--clone", Fore.LIGHTYELLOW_EX) + ": same as -c")
        print("     " + col_str("--keep-clone", Fore.LIGHTYELLOW_EX) + ": keep clone file after exit")
        print(col_str("--new", Fore.LIGHTYELLOW_EX) + "=<name>: create new file")
        print("     " + col_str("--force", Fore.LIGHTYELLOW_EX) + ": overwrite file if it already exists")
        print("     " + col_str("--size", Fore.LIGHTYELLOW_EX) + "=<size>: specify file size")
        print(col_str("--clear-logs", Fore.LIGHTYELLOW_EX) + ": clear logs folder")
        print(col_str("--show-logs", Fore.LIGHTYELLOW_EX) + ": print log folder location")
        return

    if "version" in args or "v" in option_str:
        ver = selfhex_commons.SELFHEX_VERSION
        code = selfhex_commons.SELFHEX_VERCODE

        print(f"{col_str('selfhex', Fore.LIGHTGREEN_EX)}"
                        f" {col_str(f'v{ver}', Fore.LIGHTYELLOW_EX)} ({col_str(code, Fore.LIGHTYELLOW_EX)})"
                        f" - self-diffing capable hex viewer"
                        f" | made with {col_str('♥', Fore.RED)} by quantum")
        return

    if "new" in args:
        new_file_name = args["new"]
        if not new_file_name:
            print("selfhex: error: --new requires <name> parameter")
            return

        size = None
        if "size" in args:
            try:
                size = selfhex_commons.parse_file_size(args["size"])
            except ValueError:
                print(f"selfhex: error: invalid size: {args['size']}!")
                return

        if not selfhex_commons.create_new_file(new_file_name, size, "force" in args):
            return
        files.insert(0, new_file_name)

    if len(files) > 2:
        print("selfhex: error: selfhex only supports opening up to two files at a time!")
        return

    for f in files:
        if not check_file(f):
            return

    make_clone = "c" in option_str or "clone" in args and args["clone"].lower() in ("", "true", "yes", "y", "1")
    keep_clone = "keep-clone" in args and args["keep-clone"].lower() in ("", "true", "yes", "y", "1")
    try:
        if len(files) == 1:
            if make_clone:
                print("selfhex: info: cloning file 1 for self-diffing")
                temp_file = selfhex_commons.store_temp_file(files[0])
                run_selfhex(temp_file, files[0])
            else:
                run_selfhex(files[0], None)
        else:
            same_file = os.path.samefile(files[0], files[1])
            if same_file:
                temp_file = selfhex_commons.store_temp_file(files[0])
                run_selfhex(temp_file, files[0])
                return
            elif make_clone:
                print("selfhex: warning: --clone is ignored when two files are provided.")
            run_selfhex(files[0], files[1])
    except Exception as e:
        print(f"selfhex: error: an error occurred running selfhex")
        print(f"selfhex: error: {e}")
    finally:
        if not keep_clone:
            selfhex_commons.clear_temp_files()

if __name__ == "__main__":
    if sys.platform not in ("linux", "android"):
        print("selfhex: selfhex currently only works on linux")
        sys.exit(0)
    main(sys.argv[1:])