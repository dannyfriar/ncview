"""Entry point for `python -m ncview`."""

import argparse
import sys
from pathlib import Path


def _handle_subcommand() -> None:
    """Handle pin/unpin subcommands."""
    parser = argparse.ArgumentParser(prog="ncview")
    sub = parser.add_subparsers(dest="command")

    pin_p = sub.add_parser("pin", help="Pin a directory for quick navigation")
    pin_p.add_argument("path", help="Directory to pin")
    pin_p.add_argument("-n", "--name", default="", help="Display name for the pin")

    unpin_p = sub.add_parser("unpin", help="Unpin a directory")
    unpin_p.add_argument("path", help="Directory to unpin")

    args = parser.parse_args()

    if args.command == "pin":
        from ncview.utils.pins import add_pin
        resolved = str(Path(args.path).resolve())
        overwritten = add_pin(args.path, name=args.name)
        label = f" ({args.name})" if args.name else ""
        if overwritten:
            print(f"Updated existing pin: {resolved}{label}")
        else:
            print(f"Pinned: {resolved}{label}")
    elif args.command == "unpin":
        from ncview.utils.pins import remove_pin
        resolved = str(Path(args.path).resolve())
        remove_pin(args.path)
        print(f"Unpinned: {resolved}")


def main() -> None:
    # Route pin/unpin subcommands to separate parser to avoid
    # argparse conflict between subparsers and positional browse_path.
    if len(sys.argv) > 1 and sys.argv[1] in ("pin", "unpin"):
        _handle_subcommand()
        return

    if len(sys.argv) > 1 and sys.argv[1] == "info":
        from importlib.metadata import version
        from ncview.utils.config import config_dir
        print(f"ncview {version('ncview')}")
        print(f"config: {config_dir()}")
        return

    parser = argparse.ArgumentParser(
        prog="ncview",
        description="Terminal file browser with vim keybindings",
    )
    parser.add_argument(
        "browse_path", nargs="?", default=".", metavar="path",
        help="Directory to browse (default: current directory)",
    )
    args = parser.parse_args()

    from ncview.app import run
    run(args.browse_path)


if __name__ == "__main__":
    main()
