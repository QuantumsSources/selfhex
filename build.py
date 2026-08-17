import sys
import shutil
import subprocess
from pathlib import Path
import importlib.util

if sys.version_info < (3, 9):
    print("error: selfhex requires Python 3.9 or higher to build.")
    sys.exit(1)

if shutil.which("pyinstaller") is None:
    print("error: 'pyinstaller' is not installed")
    print("       install via pip or pipx")
    sys.exit(1)

if importlib.util.find_spec("colorama") is None:
    print("error: 'colorama' is not installed")
    print("       install via pip, or your package manager")
    sys.exit(1)

result = subprocess.run(["killall", "selfhex"])
if result.returncode == 0:
    print("> killed previous selfhex processes")

HOME = Path.home()
INSTALL_DIR = HOME / ".local/share/selfhex"
BIN_DIR = HOME / ".local/bin"
DESKTOP_DIR = HOME / ".local/share/applications"
SRC_DIR = Path("src")
BUILD_TARGET = SRC_DIR / "selfhex.py"

if not BUILD_TARGET.exists():
    print(f"error: could not find build target at {BUILD_TARGET}")
    sys.exit(1)

print("> compiling selfhex")
cmd = ["pyinstaller", "--clean", "--onedir", "--noconfirm", str(BUILD_TARGET)]
result = subprocess.run(cmd)

if result.returncode != 0:
    print("error: build failed.")
    sys.exit(1)

DIST_DIR = Path("dist/selfhex")
if not DIST_DIR.exists():
    print(f"error: expected build output at {DIST_DIR}, not found")
    sys.exit(1)

print(f"> installing to {INSTALL_DIR}")
INSTALL_DIR.mkdir(parents=True, exist_ok=True)
BIN_DIR.mkdir(parents=True, exist_ok=True)
DESKTOP_DIR.mkdir(parents=True, exist_ok=True)

shutil.copy(SRC_DIR / "selfhex.png", DIST_DIR)
shutil.copytree(DIST_DIR, INSTALL_DIR, dirs_exist_ok=True)

symlink_path = BIN_DIR / "selfhex"
if symlink_path.is_symlink() or symlink_path.exists():
    symlink_path.unlink()
symlink_path.symlink_to(INSTALL_DIR / "selfhex")

icon_file = INSTALL_DIR / "selfhex.png"
icon_path = str(icon_file) if icon_file.exists() else "utilities-terminal"

print(f"> creating desktop entry in {DESKTOP_DIR}")
desktop_content = f"""[Desktop Entry]
Version=1.0
Name=selfhex
Comment=Self-diffing capable hex viewer
Exec={INSTALL_DIR / 'selfhex'} %F
Icon={icon_path}
Terminal=true
Type=Application
Categories=Development;Utility;
"""

desktop_file = DESKTOP_DIR / "selfhex.desktop"
desktop_file.write_text(desktop_content)

print("\n> selfhex successfully installed!")
print("> reboot, or update your desktop database (and icons), to finish installation.")
