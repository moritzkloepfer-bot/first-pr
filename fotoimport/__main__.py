import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="fotoimport", description="Fotos vom Android-Handy importieren")
    parser.add_argument("befehl", nargs="?", default="importieren",
                        choices=["importieren", "waechter", "einrichten"],
                        help="importieren (Standard), waechter (Autostart) oder einrichten")
    args = parser.parse_args()
    if args.befehl == "waechter":
        from .watcher import run
        return run()
    from .gui import run
    return run(force_setup=args.befehl == "einrichten")


sys.exit(main())
