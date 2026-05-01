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

    if len(sys.argv) > 1 and sys.argv[1] == "--resume":
        from ncview.utils.history import load_history
        history = load_history()
        if not history:
            print("No history yet.")
            return
        resume_path = history[0]
        if not Path(resume_path).is_dir():
            print(f"Last directory no longer exists: {resume_path}")
            return
        from ncview.app import run
        run(resume_path)
        return

    if len(sys.argv) > 1 and sys.argv[1] == "pins":
        from ncview.utils.pins import load_pins
        pins = load_pins()
        if not pins:
            print("No pins.")
            return
        for p in pins:
            path = p.get("original", p["path"])
            if p["name"]:
                print(f"{p['name']}\t{path}")
            else:
                print(path)
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
        epilog="""\
commands:
  ncview [path]                browse a directory (default: .)
  ncview --resume              reopen the last visited directory
  ncview pins                  list all pinned directories
  ncview pin <path> [-n name]  pin a directory for quick access
  ncview unpin <path>          remove a pinned directory
  ncview info                  show version and config path""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "browse_path", nargs="?", default=".", metavar="path",
        help="Directory to browse (default: current directory)",
    )
    parser.add_argument(
        "-i", action="store_true", dest="ignore_case",
        help="Case-insensitive pin name matching",
    )
    args = parser.parse_args()

    browse = args.browse_path
    if not Path(browse).is_dir():
        # Try matching against pin names
        from ncview.utils.pins import load_pins
        if args.ignore_case:
            query = browse.lower()
            matches = [
                p for p in load_pins()
                if p["name"] and query in p["name"].lower()
            ]
        else:
            matches = [
                p for p in load_pins()
                if p["name"] and browse in p["name"]
            ]
        if len(matches) == 1:
            browse = matches[0].get("original", matches[0]["path"])
        elif len(matches) > 1:
            print(f"Multiple pins match '{browse}':")
            for m in matches:
                print(f"  {m['name']}  {m.get('original', m['path'])}")
            return
        else:
            print(f"Not a directory and no matching pin: {browse}")
            return

    from ncview.app import run
    run(browse)


if __name__ == "__main__":
    main()
