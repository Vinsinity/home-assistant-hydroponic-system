"""Command-line entry point for standalone GrowAsist."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .server import serve
from .storage import GrowAsistStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="growasist")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("GROWASIST_DATA_DIR", "growasist-data"),
        help="Persistent data directory (default: growasist-data)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    serve_command = commands.add_parser("serve", help="Run the standalone API")
    serve_command.add_argument("--host", default="127.0.0.1")
    serve_command.add_argument("--port", type=int, default=8080)
    serve_command.add_argument(
        "--api-token",
        default=os.environ.get("GROWASIST_API_TOKEN", ""),
        help="Bearer token; required when listening on the LAN",
    )

    commands.add_parser("check", help="Verify SQLite and journal integrity")

    backup_command = commands.add_parser("backup", help="Create a consistent DB backup")
    backup_command.add_argument("destination")

    import_command = commands.add_parser(
        "import-ha", help="Merge a checksummed Home Assistant journal export"
    )
    import_command.add_argument("export_file")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one standalone command."""
    args = _parser().parse_args(argv)
    data_dir = Path(args.data_dir).expanduser().resolve()
    store = GrowAsistStore(data_dir / "growasist.db")

    if args.command == "serve":
        serve(
            store,
            host=args.host,
            port=args.port,
            api_token=args.api_token,
        )
        return 0
    if args.command == "check":
        print(json.dumps(store.health(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "backup":
        print(store.backup(args.destination))
        return 0
    if args.command == "import-ha":
        with Path(args.export_file).open(encoding="utf-8") as export_file:
            payload = json.load(export_file)
        state = store.import_home_assistant_export(payload)
        print(
            json.dumps(
                {
                    "cultivations": len(state["cultivations"]["records"]),
                    "events": len(state["events"]),
                    "engine_enabled": state["engine_enabled"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    return 2
