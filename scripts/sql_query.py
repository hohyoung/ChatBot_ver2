#!/usr/bin/env python3
from __future__ import annotations
import sys, argparse, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "backend" / "app" / "db" / "users.sqlite3"


def run_sql(sql: str):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute(sql)
        # SELECT 계열이면 결과 출력
        if sql.strip().lower().startswith(("select", "pragma", "with")):
            rows = cur.fetchall()
            if rows:
                cols = rows[0].keys()
                print("| " + " | ".join(cols) + " |")
                print("|-" + "-|-".join("-" * len(c) for c in cols) + "-|")
                for r in rows:
                    print("| " + " | ".join(str(r[c]) for c in cols) + " |")
            else:
                print("(no rows)")
        else:
            con.commit()
            print(f"(ok) {cur.rowcount} row(s) affected")
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser(description="Run ad-hoc SQL on users.sqlite3")
    ap.add_argument("sql", nargs="?", help="SQL to execute (quote it)")
    ap.add_argument("-f", "--file", type=str, help="Read SQL from file")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    if args.file:
        sql = Path(args.file).read_text(encoding="utf-8")
    elif args.sql:
        sql = args.sql
    else:
        print("Provide SQL or -f file.sql", file=sys.stderr)
        sys.exit(2)

    run_sql(sql)


if __name__ == "__main__":
    main()
