<div align="center">

# selfhex
A _self-diffing_ capable hex viewer.\
Made with ♥ by quantum.

<img src="assets/diff_example.png" alt="selfhex diffing 0x2000 with 0x4000 of the same file for 0x2000 bytes" width="600"/>
<br>
<sub>selfhex diffing 0x2000 with 0x4000 of the same file for 0x2000 bytes</sub>

</div>

## Features
### Self-diffing capable
- Clone a file with the `:c[ln]` command; <sub>(selfhex will clean it automatically when it's unloaded, or you quit)</sub>
- Diff two files, or different regions of the same file with the `:d[iff]` command;

### Custom-built terminal interface
- Brand-new interface made from the ground up, with no external dependencies.
- _Vim-like-ish_ command system.

### Marks & findings
- Locate hex strings quickly with the `:f[n]` command;
- Keep track of your findings with the `:m[rk]` command;

## Requirements
To run selfhex, you'll need:
- Python v3.9+, for everything;
- That's it;

## Installation
> [!important]
> Currently, due to _heavy, unsupervised_ usage of `termios` and `tty`, selfhex only works on Linux and Android
<sub>(through Termux)</sub>.\
> It *might* run through WSL, though it's not tested!

To install selfhex, you'll need one thing:
- `nuitka`, to compile it (aur/deb: `nuitka`);
- This list has two bullet points, but you only had to read the first;

Then, clone the repository, and run `build.py`, like this:
```bash
git clone https://github.com/QuantumsSources/selfhex.git
cd selfhex
python3 build.py
```
This will compile selfhex, link the binary to `~/.local/bin/selfhex`, and add a desktop entry.

## Usage
### Command line
- Launch selfhex with your files loaded straight away with `selfhex <file> [<file>]`;
- You can also clone files from the command line with `selfhex <file> --clone`;
- And even create new files with `selfhex --new=<name> --size=<size>`;

### Interactive interface
- For only **$0.00**, everything above, _plus_...
- Load your files with the `:l[d]` command, or clone with `:c[ln]`;
- Need help? Run `:h[elp]` with either a page, or a command;

## Notes
- The icon for selfhex is ~~stolen~~ _borrowed_ from Sonic the Hedgehog 3.<br/>Original sprite by SEGA and Sonic Team, with minimal edits by me.

<p align="center"><sub>(woah... it's so empty down here...)</sub></p>