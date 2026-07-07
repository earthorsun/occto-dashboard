#!/usr/bin/env python3
"""OCCTO 広域予備率Web公表システムから連系線潮流・エリア予備率を取得しJSON化する。
出典: 電力広域的運営推進機関 (OCCTO) https://web-kohyo.occto.or.jp/
本スクリプトが生成するデータは速報値・非公式であり、正確性を保証しない。
"""
import csv
import io
import json
import os
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://web-kohyo.occto.or.jp/kks-web-public/download/downloadCsv"
JST = timezone(timedelta(hours=9))
OUT_DIR = "data"
UA = "occto-dashboard/1.0 (personal use)"

KIND_RESERVE_TODAY = "02"   # 広域予備率ブロック情報(翌日・当日) = エリア予備率
KIND_TIELINE_TODAY = "04"   # 広域予備率連系線情報(翌日・当日) = 連系線潮流


def fetch_csv(jh_sybt: str, day: datetime):
    ymd = day.strftime("%Y/%m/%d")
    params = {"jhSybt": jh_sybt, "tgtYmdFrom": ymd, "tgtYmdTo": ymd}
    r = requests.get(BASE, params=params, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    text = r.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    return [row for row in reader if row]


def parse_float(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def build_tieline(day: datetime):
    rows = fetch_csv(KIND_TIELINE_TODAY, day)
    update_ts = rows[0][0] if rows and len(rows[0]) == 1 else ""
    data_rows = [r for r in rows if len(r) >= 16 and "/" in r[0]]
    lines = {}
    for r in data_rows:
        name = r[2]
        rec = {
            "time": r[1],
            "flow": parse_float(r[7]),
            "fwd_capacity": parse_float(r[3]),
            "rev_capacity": parse_float(r[4]),
            "fwd_free": parse_float(r[9]),
            "rev_free": parse_float(r[10]),
            "fwd_split": r[13] if len(r) > 13 else "",
            "rev_split": r[14] if len(r) > 14 else "",
        }
        lines.setdefault(name, []).append(rec)
    return {"source_update": update_ts, "date": day.strftime("%Y-%m-%d"), "lines": lines}


def build_reserve(day: datetime):
    rows = fetch_csv(KIND_RESERVE_TODAY, day)
    update_ts = rows[0][0] if rows and len(rows[0]) == 1 else ""
    data_rows = [r for r in rows if len(r) >= 12 and "/" in r[0]]
    areas = {}
    for r in data_rows:
        area = r[3]
        demand = parse_float(r[9])
        supply = parse_float(r[10])
        margin = parse_float(r[11])
        rate = None
        if demand and margin is not None and demand != 0:
            rate = round(margin / demand * 100, 2)
        rec = {
            "time": r[1],
            "wide_reserve_pct": parse_float(r[7]),
            "wide_usage_pct": parse_float(r[8]),
            "area_demand": demand,
            "area_supply": supply,
            "area_margin": margin,
            "area_reserve_pct": rate,
        }
        areas.setdefault(area, []).append(rec)
    return {"source_update": update_ts, "date": day.strftime("%Y-%m-%d"), "areas": areas}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    now = datetime.now(JST)

    def try_days(builder):
        for delta in (0, 1):
            d = now - timedelta(days=delta)
            try:
                result = builder(d)
                key = "lines" if "lines" in result else "areas"
                if result[key]:
                    return result
            except Exception as e:
                print(f"  {builder.__name__} day-{delta} failed: {e}")
        return {"error": "no data", "date": now.strftime("%Y-%m-%d")}

    tieline = try_days(build_tieline)
    reserve = try_days(build_reserve)

    with open(f"{OUT_DIR}/tieline.json", "w", encoding="utf-8") as f:
        json.dump(tieline, f, ensure_ascii=False)
    with open(f"{OUT_DIR}/reserve.json", "w", encoding="utf-8") as f:
        json.dump(reserve, f, ensure_ascii=False)
    with open(f"{OUT_DIR}/updated.json", "w", encoding="utf-8") as f:
        json.dump({"fetched_at": now.isoformat()}, f, ensure_ascii=False)

    print(f"done: {now.isoformat()}")


if __name__ == "__main__":
    main()
