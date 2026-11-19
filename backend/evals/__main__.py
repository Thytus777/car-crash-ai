"""Eval command line: ``python -m evals <command>`` (run from backend/)."""

import argparse
import sys

from evals import dataset


def _validate(_: argparse.Namespace) -> int:
    report = dataset.validate()
    for warning in report.warnings:
        print(f"warning: {warning}")
    for error in report.errors:
        print(f"error: {error}")
    if report.ok:
        print(f"dataset OK: {dataset.dumps(dataset.summary())}")
        return 0
    print(f"{len(report.errors)} error(s)")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="check labels, images and the manifest")
    args = parser.parse_args(argv)
    handlers = {"validate": _validate}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
