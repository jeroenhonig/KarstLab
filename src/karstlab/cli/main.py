"""KarstLab command-line interface."""

from __future__ import annotations

import argparse

from karstlab.version import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="karstlab",
        description="KarstLab terrain analysis toolkit.",
    )
    parser.add_argument("--version", action="version", version=f"KarstLab {__version__}")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("doctor", help="Check the local KarstLab runtime environment.")

    return parser


def run_doctor() -> int:
    print(f"KarstLab {__version__}")
    print("Runtime check: package import OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return run_doctor()

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

