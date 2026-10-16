import sys
import time
import shutil
import subprocess

from pathlib import Path
from subprocess import CompletedProcess
from src.selfhex_core import SELFHEX_VERSION, SELFHEX_VERCODE

BUILD_SCRIPT_VERSION = "1.1"

def run(args: str|list[str]) -> CompletedProcess:
    return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if sys.platform not in ("linux", "android"):
    print("error: currently selfhex only works on linux!")
    sys.exit(1)

if sys.version_info < (3, 10):
    print("error: selfhex requires python 3.10 or higher to build.")
    sys.exit(1)

if shutil.which("nuitka") is None and run(["python", "-m", "nuitka", "--version"]).returncode != 0:
    print("error: 'nuitka' is not installed")
    print("       install via pip, pipx, or native (aur, apt, etc...)")
    sys.exit(1)

def _clean():
    if Path("selfhex.dist").exists():
        shutil.rmtree(Path("selfhex.dist"))
    if Path("selfhex.build").exists():
        shutil.rmtree(Path("selfhex.build"))
_clean()

result = run(["killall", "selfhex"])
if result.returncode == 0:
    print("> killed previous selfhex processes\n")

HOME = Path.home()
INSTALL_DIR = HOME / ".local/share/selfhex"
BIN_DIR = HOME / ".local/bin"
DESKTOP_DIR = HOME / ".local/share/applications"

SRC_DIR = Path("src")
BUILD_TARGET = SRC_DIR / "selfhex.py"
SRC_FMTS_DIR = Path("fmts")
FMTS_DIR = Path(INSTALL_DIR / "fmts")

if not BUILD_TARGET.exists():
    print(f"error: could not find build target at {BUILD_TARGET}")
    print(f"       make sure to be in directory {Path(__file__).resolve().parent} and try again")
    sys.exit(1)

def _build() -> CompletedProcess:
    cmd = ["nuitka", "--mode=standalone", "--include-package=yaml", str(BUILD_TARGET)]
    try:
        return subprocess.run(cmd)
    except KeyboardInterrupt:
        print("error: build interrupted!")
        sys.exit(1)

if INSTALL_DIR.exists():
    if input(f"> clean old build files? ({INSTALL_DIR}) [Y/n] ").lower().strip() in ("y", "yes", ""):
        (BIN_DIR / "selfhex.bin").unlink(True)
        shutil.rmtree(INSTALL_DIR)
        print("> cleaned old build files\n")

print(f"> compiling selfhex with build.py v{BUILD_SCRIPT_VERSION} (this might take a while!)")
start = time.time()
result = _build()

if result.returncode != 0:
    print("error: build failed.")
    sys.exit(1)
print(f"> build complete in ~{(time.time() - start):.1f}s!")

DIST_DIR = Path("selfhex.dist")
BUILD_DIR = Path("selfhex.build")
if not DIST_DIR.exists() or not BUILD_DIR.exists():
    print(f"error: expected build output at {DIST_DIR} and {BUILD_DIR}, of which one or both were not found:")
    if not DIST_DIR.exists():
        print(f"       {DIST_DIR} was not found.")
    if not BUILD_DIR.exists():
        print(f"       {BUILD_DIR} was not found.")
    sys.exit(1)

print(f"> installing to {INSTALL_DIR}")
INSTALL_DIR.mkdir(parents=True, exist_ok=True)
BIN_DIR.mkdir(parents=True, exist_ok=True)
DESKTOP_DIR.mkdir(parents=True, exist_ok=True)

shutil.copy(SRC_DIR / "selfhex.png", DIST_DIR)
shutil.copytree(DIST_DIR, INSTALL_DIR, dirs_exist_ok=True)
shutil.copytree(SRC_FMTS_DIR, FMTS_DIR, dirs_exist_ok=True)

symlink_path = BIN_DIR / "selfhex"
if symlink_path.is_symlink() or symlink_path.exists():
    symlink_path.unlink()
symlink_path.symlink_to(INSTALL_DIR / "selfhex.bin")

icon_file = INSTALL_DIR / "selfhex.png"
icon_path = str(icon_file) if icon_file.exists() else "utilities-terminal"

print(f"\n> creating desktop entry in {DESKTOP_DIR}")
desktop_content = f"""[Desktop Entry]
Version=1.0
Name=selfhex
Comment=Self-diffing capable hex viewer.
Exec={BIN_DIR / 'selfhex'} %F
Icon={icon_path}
Terminal=true
Type=Application
Categories=Development;Utility;
"""

desktop_file = DESKTOP_DIR / "selfhex.desktop"
desktop_file.write_text(desktop_content)

if input("> update desktop database and icon cache? [Y/n] ").lower().strip() in ("y", "yes", ""):
    print("> updating desktop database")
    run("update-desktop-database")
    print("> updating icon cache")
    run("gtk-update-icon-cache")

if input("\n> remove temporary build files? [Y/n] ").lower().strip() in ("y", "yes", ""):
    _clean()
    print("> build files removed")

if run(["selfhex", "-h"]).returncode != 0:
    print("\n> install failed!")
    sys.exit(1)

print(f"\n> selfhex successfully installed selfhex v{SELFHEX_VERSION} ({SELFHEX_VERCODE})!")
print("> see usage with 'selfhex --help'")