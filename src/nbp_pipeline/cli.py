from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta
import httpx

from nbp_pipeline.ingest import ingest_range
from nbp_pipeline.state import advance_watermark, read_watermark

log = logging.getLogger("nbp_pipeline")

DEFAULT_START = date(2020,1,1)

def run(start: date, end: date)-> None:
    """Function to ingest time chunck of data and progress the watermark after success in landing a table"""
    if start > end:
        log.info("Nothing to fetch: Up to date with data")
        return
    log.info("Ingesting %s..%s", start, end)
    with httpx.Client(timeout=10) as client:
        latest= ingest_range(client, start, end)
    if latest is None:
        log.info("No new tables published")
        return
    log.info("Watermark is now %s", advance_watermark(latest))

def cmd_ingest(args: argparse.Namespace) -> int:
    watermark = read_watermark()
    start = watermark + timedelta(days=1) if watermark else DEFAULT_START
    run(start, date.today())
    return 0

def cmd_backfill(args: argparse.Namespace) -> int:
    run(args.from_date, args.to_date or date.today())
    return 0

def cmd_not_ready(args: argparse.Namespace) -> int:
    log.error("'%s' is not implemented yet", args.command)
    return 1

def build_parser()-> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nbp_pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ingest", help="fetch everything after the watermark")

    backfill = sub.add_parser("backfill", help="fetch an explicit date range")
    backfill.add_argument("--from", dest="from_date", type=date.fromisoformat, required=True)
    backfill.add_argument("--to", dest="to_date", type=date.fromisoformat)

    sub.add_parser("transform", help="build staging and warehouse")
    sub.add_parser("check", help="run data quality checks")
    return parser

COMMANDS ={"ingest": cmd_ingest, "backfill": cmd_backfill} #, "transform": cmd_transform, "check": cmd_check}  

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())