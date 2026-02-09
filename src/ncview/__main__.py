"""Entry point for `python -m ncview`."""

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ncview",
        description="Terminal file browser with vim keybindings",
    )
    sub = parser.add_subparsers(dest="command")

    pin_p = sub.add_parser("pin", help="Pin a directory for quick navigation")
    pin_p.add_argument("path", help="Directory to pin")
    pin_p.add_argument("-n", "--name", default="", help="Display name for the pin")

    unpin_p = sub.add_parser("unpin", help="Unpin a directory")
    unpin_p.add_argument("path", help="Directory to unpin")

    # Default browse mode — path is optional and only valid without a subcommand
    parser.add_argument(
        "browse_path", nargs="?", default=".", metavar="path",
        help="Directory to browse (default: current directory)",
    )

    args = parser.parse_args()

    if args.command == "pin":
        from ncview.utils.pins import add_pin
        resolved = str(Path(args.path).resolve())
        add_pin(args.path, name=args.name)
        label = f" ({args.name})" if args.name else ""
        print(f"Pinned: {resolved}{label}")
        return

    if args.command == "unpin":
        from ncview.utils.pins import remove_pin
        resolved = str(Path(args.path).resolve())
        remove_pin(args.path)
        print(f"Unpinned: {resolved}")
        return

    # Default: launch TUI
    from ncview.app import run
    run(args.browse_path)


if __name__ == "__main__":
    main()
