from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eva", description="ULJS00201 translation workflow")
    subcommands = parser.add_subparsers(dest="command", required=True)

    export = subcommands.add_parser("export", help="Export file-level ParaTranz JSON")
    export.add_argument("--iso", type=Path, required=True)
    export.add_argument("--translations", type=Path, required=True)
    export.add_argument("--work-dir", type=Path, required=True)
    export.add_argument("--report", type=Path, required=True)

    check = subcommands.add_parser("check", help="Validate translations against the source PKG")
    check.add_argument("--iso", type=Path, required=True)
    check.add_argument("--eboot", type=Path, required=True)
    check.add_argument("--translations", type=Path, required=True)
    check.add_argument("--work-dir", type=Path, required=True)
    check.add_argument("--report", type=Path, required=True)

    build = subcommands.add_parser("build", help="Build the translated PKG and sparse-overlay ISO")
    build.add_argument("--iso", type=Path, required=True)
    build.add_argument("--translations", type=Path, required=True)
    build.add_argument("--overrides", type=Path, required=True)
    build.add_argument("--build-dir", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)

    verify = subcommands.add_parser("verify", help="Verify a patched ISO and its NEVA.PKG")
    verify.add_argument("--source-iso", type=Path, required=True)
    verify.add_argument("--patched-iso", type=Path, required=True)
    verify.add_argument("--translations", type=Path, required=True)
    verify.add_argument("--report", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "export":
            result = workflow.export_translations(
                args.iso, args.translations, args.work_dir, args.report
            )
        elif args.command == "check":
            result = workflow.check_translations(
                args.iso, args.eboot, args.translations, args.work_dir, args.report
            )
        elif args.command == "build":
            result = workflow.build_image(
                args.iso, args.translations, args.overrides, args.build_dir, args.output
            )
        else:
            result = workflow.verify_image(
                args.source_iso, args.patched_iso, args.translations, args.report
            )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
