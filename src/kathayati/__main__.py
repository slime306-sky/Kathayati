import argparse
import logging

from .api import init_db
from .worker import run_worker


def main() -> None:
    parser = argparse.ArgumentParser(prog="kathayati")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="create the notifications table")
    w = sub.add_parser("worker", help="run the delivery worker")
    w.add_argument("--once", action="store_true", help="drain due notifications, then exit")
    w.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "init-db":
        init_db()
        print("notifications table ready")
    else:
        run_worker(once=args.once, poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()
