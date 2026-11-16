"""Owner command line: python -m backend.app.cli <command> (from the project root).

  create-user EMAIL [--days 365] [--start YYYY-MM-DD] [--admin] [--max-devices 2]   prints the license key once
  list-users
  extend-user EMAIL --end YYYY-MM-DD
  disable-user EMAIL | enable-user EMAIL
  reset-devices EMAIL
  public-key [--out desktop/license_public_key.pem]     ship this file with desktop builds
  plan [DAY]                                            the day's decision windows and credit estimate (free)
  results                                               refresh results and grade logged picks (free)
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from .db import SessionLocal, User, init_db
from .security import generate_api_key, hash_key, public_key_pem


def _user(s, ident):
    return s.execute(select(User).where(User.identifier == ident)).scalar_one_or_none()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m backend.app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    cu = sub.add_parser("create-user"); cu.add_argument("identifier"); cu.add_argument("--days", type=int, default=365)
    cu.add_argument("--start"); cu.add_argument("--admin", action="store_true"); cu.add_argument("--plan", default="pro")
    cu.add_argument("--max-devices", type=int, default=2)
    sub.add_parser("list-users")
    eu = sub.add_parser("extend-user"); eu.add_argument("identifier"); eu.add_argument("--end", required=True)
    for c in ("disable-user", "enable-user", "reset-devices"):
        sub.add_parser(c).add_argument("identifier")
    pk = sub.add_parser("public-key"); pk.add_argument("--out")
    pl = sub.add_parser("plan"); pl.add_argument("day", nargs="?")
    sub.add_parser("results")
    a = p.parse_args(argv)
    init_db()

    with SessionLocal() as s:
        if a.cmd == "create-user":
            if _user(s, a.identifier):
                print("User already exists"); return 1
            start = datetime.combine(date.fromisoformat(a.start) if a.start else date.today(), datetime.min.time(), tzinfo=timezone.utc)
            key = generate_api_key()
            u = User(identifier=a.identifier, api_key_hash=hash_key(key), api_key_prefix=key[:4], key_start_date=start,
                     key_end_date=start + timedelta(days=a.days, hours=23, minutes=59), role="admin" if a.admin else "user",
                     plan=a.plan, max_devices=a.max_devices, devices=[])
            s.add(u); s.commit()
            print(f"Created {u.identifier} (id {u.id}) valid {start.date()} -> {u.key_end_date.date()}")
            print(f"License key (shown once): {key}")
        elif a.cmd == "list-users":
            for u in s.execute(select(User).order_by(User.id)).scalars():
                print(f"{u.id:4} {u.identifier:35} {u.role:6} {u.plan:6} {u.key_start_date:%Y-%m-%d} -> {u.key_end_date:%Y-%m-%d} "
                      f"{'active' if u.is_active else 'DISABLED'} devices={len(u.devices or [])}/{u.max_devices}")
        elif a.cmd in ("extend-user", "disable-user", "enable-user", "reset-devices"):
            u = _user(s, a.identifier)
            if not u:
                print("No such user"); return 1
            if a.cmd == "extend-user":
                u.key_end_date = datetime.combine(date.fromisoformat(a.end), datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc)
            elif a.cmd == "reset-devices":
                u.devices = []
            else:
                u.is_active = a.cmd == "enable-user"
            s.commit()
            print(f"{u.identifier}: active={u.is_active}, until {u.key_end_date:%Y-%m-%d}, devices {len(u.devices or [])}")
        elif a.cmd == "public-key":
            pem = public_key_pem()
            if a.out:
                Path(a.out).write_text(pem, encoding="utf-8"); print(f"Wrote {a.out}")
            else:
                print(pem)
        elif a.cmd == "plan":
            from . import runner
            print(json.dumps(runner.plan(a.day), indent=1))
        elif a.cmd == "results":
            import livepicks
            livepicks.refresh_results()
            livepicks.settle(refresh=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
