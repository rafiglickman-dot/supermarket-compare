#!/usr/bin/env python3
"""How much does a product cost in every supermarket around me? No receipt needed.

Two steps, both over every branch within the radius (the same branches compare.py would use):

  1. search: find the products that match what the shopper said, grouped by barcode.
     python price_check.py search --near "כפר סבא" --radius 3 --q "אורז פרסי סוגת 1 קג" --q "פרימור תפוזים 1 ליטר" --out RUN/search.json

  2. prices: the chosen barcodes (optionally with a quantity) in every branch, with promotions,
     and the cheapest branch for the whole list.
     python price_check.py prices --near "כפר סבא" --radius 3 --item 7290000211442 --item 7290013608550:2 --out RUN/prices.json

--near is a city ("כפר סבא") or "street and number, city". The radius is straight-line km.
Prices come only from the chains' official files; every row keeps its file name. The headline price
counts promotions open to everyone (fixed price, multi-buy) at the requested quantity. Club deals are
shown separately. Coupons, gifts and minimum-spend deals are never counted.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chains  # noqa: E402
import compare  # noqa: E402
import geo  # noqa: E402

DISCLAIMER = ("חשוב לדעת: המערכת עלולה לטעות ולא תמיד מדייקת ב-100%. היא נשענת על קובצי המחירים שהרשתות מפרסמות "
              "ועל התאמת שם המוצר בידי AI, ומחירים, מבצעים, מלאי וכתובות יכולים להשתנות. זו הערכה ולא הבטחה לסכום "
              "בקופה, אז לפני נסיעה מיוחדת כדאי לוודא מול הסניף.")
LOC_HE = {"verified": "מאומת במפה", "address": "לפי כתובת בלבד", "street": "לפי רחוב בלבד", "manual": "ידני"}


def say(m: str) -> None:
    print(m, flush=True)


def center_of(near: str):
    addr, _, city = near.rpartition(",")
    if addr.strip():
        ll = geo.geocode(addr.strip(), city.strip(), city_fallback=False)
    else:
        ll = geo.city_center(near.strip())
    if not ll:
        raise SystemExit(f"לא מצאתי את המקום: {near}. כתוב עיר, או רחוב, מספר ועיר, למשל: הרצל 10, רמת גן")
    return ll


def branches(a) -> tuple[list[dict], list[str], list[dict]]:
    """Every branch in the radius, downloaded. Returns (ok, unlocated, failed)."""
    center = center_of(a.near)
    chain_list = a.chains.split(",")
    say("מאתר את הסניפים באזור...")
    pois = geo.brand_pois(center, a.radius + 1, {c: chains.CHAINS[c]["osm"] for c in chain_list})
    found, unlocated = compare.in_radius(center, a.radius, chain_list, pois, set())
    if a.per_chain:
        seen: dict[str, int] = {}
        found = [s for s in found if seen.setdefault(s["chain"], 0) < a.per_chain and not seen.__setitem__(s["chain"], seen[s["chain"]] + 1)]
    if not found:
        raise SystemExit("לא נמצא אף סניף ברדיוס הזה. נסה רדיוס גדול יותר.")
    say(f"נמצאו {len(found)} סניפים. מוריד את קובצי המחירים והמבצעים (בפעם הראשונה ביום זה לוקח כמה דקות)...")
    compare.fetch_all(found, say, a.retries)
    failed = [s for s in found if s.get("error")]
    ok = [s for s in found if not s.get("error")]
    for s in ok:
        s["he"] = chains.CHAINS[s["chain"]]["he"]
    return ok, unlocated, failed


def label(s: dict) -> str:
    return f'{s["he"]} {s["info"].get("name", "")}'.strip()


def where(s: dict) -> dict:
    return {"chain": s["chain"], "store": s["store"], "name": label(s), "address": s["info"].get("address", "") if compare.has_address(s["info"]) else "",
            "city": compare.resolved_city(s["info"]), "km": s["km"], "location": LOC_HE.get(s["loc"], s["loc"])}


def failed_rows(failed: list[dict]) -> list[str]:
    return [f'{chains.CHAINS[s["chain"]]["he"]} {s["info"].get("name", "")}'.strip() for s in failed]


# ---------------------------------------------------------------- 1. search
def words_of(q: str) -> list[str]:
    q = re.sub(r'ק"ג|קג|קילו(?:גרם)?', " ק\"ג ", q)
    q = re.sub(r"ליטר|ל'", " ליטר ", q)
    return [w for w in compare.norm(q).split() if len(w) >= 2 or w.isdigit()]


SIZE_WORDS = {'ק"ג', "קג", "ליטר", "גרם", "גר", "מל", 'מ"ל', "יח", "יחידות", "מארז"}


def is_size(word: str) -> bool:
    return word in SIZE_WORDS or bool(re.fullmatch(r"\d+(?:\.\d+)?", word))


def hit(word: str, text: str) -> bool:
    if word.isdigit() or re.fullmatch(r"\d+\.\d+", word):
        return re.search(rf"(?<![\d.]){re.escape(word)}(?![\d])", text) is not None
    return word in text


def search(a) -> None:
    stores, unlocated, failed = branches(a)
    out = {"date": date.today().isoformat(), "near": a.near, "radius_km": a.radius, "queries": [],
           "branches": [where(s) | {"file": s["file"]} for s in stores],
           "failed": failed_rows(failed), "unlocated": unlocated, "disclaimer": DISCLAIMER}
    for q in a.q:
        ws = words_of(q)
        if not any(not is_size(w) for w in ws):
            raise SystemExit(f'"{q}": צריך לפחות מילה אחת שמתארת את המוצר, לא רק גודל.')
        weight = sum(0.5 if is_size(w) else 1 for w in ws)
        cands: dict[str, dict] = {}
        for s in stores:
            for code, it in s["items"].items():
                text = compare.norm(f'{it["name"]} {it.get("manufacturer", "")}')
                content = sum(hit(w, text) for w in ws if not is_size(w))
                if not content:  # "1 ליטר" alone matches every bottle in the shop
                    continue
                score = (content + 0.5 * sum(hit(w, text) for w in ws if is_size(w))) / weight
                c = cands.setdefault(code, {"barcode": code, "names": set(), "score": 0.0, "prices": [], "stores": 0,
                                            "manufacturer": "", "qty": f'{it.get("qty", "")} {it.get("unit", "")}'.strip()})
                c["score"] = max(c["score"], score)
                c["names"].add(it["name"])
                c["manufacturer"] = c["manufacturer"] or it.get("manufacturer", "")
                c["prices"].append(it["price"])
                c["stores"] += 1
        best = sorted((c for c in cands.values() if c["score"] >= a.min_score),
                      key=lambda c: (-c["score"], -c["stores"], min(c["prices"])))[: a.top]
        rows = [{"barcode": c["barcode"], "name": max(c["names"], key=len), "other_names": sorted(c["names"] - {max(c["names"], key=len)}),
                 "manufacturer": c["manufacturer"], "size": c["qty"], "match": round(c["score"], 2),
                 "in_branches": c["stores"], "of_branches": len(stores),
                 "min": min(c["prices"]), "max": max(c["prices"])} for c in best]
        out["queries"].append({"q": q, "candidates": rows})
        say(f'\n=== "{q}" ({len(rows)} מועמדים, מתוך {len(stores)} סניפים)')
        for i, r in enumerate(rows, 1):
            say(f'{i:>2}. {r["name"]} | {r["manufacturer"] or "-"} | {r["size"]} | ברקוד {r["barcode"]} | '
                f'התאמה {r["match"]:.0%} | ב-{r["in_branches"]}/{r["of_branches"]} סניפים | {r["min"]:.2f}-{r["max"]:.2f} ₪')
        if not rows:
            say("לא נמצא מוצר מתאים. נסה מילים אחרות: מותג, סוג וגודל.")
    tail(out)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"\nנשמר: {a.out}\n\n{DISCLAIMER}")


# ---------------------------------------------------------------- 2. prices
def parse_items(xs: list[str]) -> list[tuple[str, float]]:
    out = []
    for x in xs:
        code, _, q = x.partition(":")
        out.append((code.strip().lstrip("0"), float(q) if q else 1.0))
    return out


def price_in(s: dict, items: list[tuple[str, float]]) -> dict:
    """Shelf, open-promo and club totals of the requested items in one branch (missing items are listed)."""
    lines = [(i, code, q, s["items"][code]["price"]) for i, (code, q) in enumerate(items) if code in s["items"]]
    open_amt, open_why = compare.apply_promos(lines, s.get("promos"), club=False)
    club_amt, club_why = compare.apply_promos(lines, s.get("promos"), club=True)
    rows = {}
    for i, code, q, shelf in lines:
        rel = [s["promos"]["promos"][p] for p in s["promos"]["by_item"].get(code, [])] if s.get("promos") else []
        rows[code] = {"shelf_unit": shelf, "qty": q, "shelf": round(q * shelf, 2), "open": round(open_amt[i], 2),
                      "open_promo": open_why.get(i), "club": round(club_amt[i], 2), "club_promo": club_why.get(i),
                      "promos_here": [f'{p["desc"]} (עד {p["end"]}{", מועדון" if p["club"] else ""})' for p in rel]}
    return {"rows": rows, "missing": [code for code, _ in items if code not in s["items"]]}


def prices(a) -> None:
    items = parse_items(a.item)
    stores, unlocated, failed = branches(a)
    names = {}
    for code, _ in items:
        ns = [s["items"][code]["name"] for s in stores if code in s["items"]]
        names[code] = max(ns, key=len) if ns else None
    table = []
    for s in stores:
        p = price_in(s, items)
        full = not p["missing"]
        table.append(where(s) | {"file": s["file"], "promo_file": s.get("promo_file"), "stale": s.get("stale", False),
                                 "items": p["rows"], "missing": p["missing"], "complete": full,
                                 "total_open": round(sum(r["open"] for r in p["rows"].values()), 2),
                                 "total_shelf": round(sum(r["shelf"] for r in p["rows"].values()), 2),
                                 "total_club": round(sum(r["club"] for r in p["rows"].values()), 2)})
    complete = sorted((t for t in table if t["complete"]), key=lambda t: (t["total_open"], t["km"]))
    partial = sorted((t for t in table if not t["complete"] and t["items"]), key=lambda t: (len(t["missing"]), t["total_open"]))
    per_item = {}
    for code, q in items:
        rs = sorted(((t["items"][code]["open"], t["items"][code]["shelf"], t) for t in table if code in t["items"]), key=lambda x: (x[0], x[2]["km"]))
        per_item[code] = {"name": names[code], "qty": q, "found_in": len(rs), "of": len(table),
                          "cheapest": [{"branch": t["name"], "km": t["km"], "open": o, "shelf": sh, "promo": t["items"][code]["open_promo"]} for o, sh, t in rs[:3]],
                          "most_expensive": ({"branch": rs[-1][2]["name"], "open": rs[-1][0]} if rs else None)}
    out = {"date": date.today().isoformat(), "near": a.near, "radius_km": a.radius,
           "items": [{"barcode": c, "qty": q, "name": names[c]} for c, q in items],
           "per_item": per_item, "ranking": complete, "partial": partial,
           "not_carrying": [t["name"] for t in table if not t["items"]],
           "failed": failed_rows(failed), "unlocated": unlocated, "disclaimer": DISCLAIMER}

    for code, q in items:
        pi = per_item[code]
        say(f'\n=== {pi["name"] or "לא נמצא באף סניף"} (ברקוד {code}, כמות {q:g}) | נמצא ב-{pi["found_in"]} מתוך {pi["of"]} סניפים')
        rows = sorted((t for t in table if code in t["items"]), key=lambda t: (t["items"][code]["open"], t["km"]))
        for t in rows:
            r = t["items"][code]
            extra = f' | מבצע: {r["open_promo"]}' if r["open_promo"] else ""
            if r["club"] < r["open"] - 0.005:
                extra += f' | במועדון: {r["club"]:.2f} ({r["club_promo"]})'
            elif not r["open_promo"] and r["promos_here"]:
                extra += f' | יש מבצע שלא חל בכמות הזו: {"; ".join(r["promos_here"])}'
            say(f'  {r["open"]:>7.2f} ₪ | מדף {r["shelf"]:.2f} | {t["name"]} | {t["km"]:.1f} ק"מ ({t["location"]}){" | קובץ ישן" if t["stale"] else ""}{extra}')
    if len(items) > 1:
        say(f"\n=== הסל כולו ({len(items)} מוצרים): {len(complete)} סניפים מחזיקים את כולם")
        for t in complete[:10]:
            say(f'  {t["total_open"]:>8.2f} ₪ | מדף {t["total_shelf"]:.2f} | {t["name"]} | {t["address"] or "אין כתובת בקובץ"} | {t["km"]:.1f} ק"מ')
        if partial:
            say("סניפים חלקיים (חסר בהם מוצר):")
            for t in partial[:8]:
                miss = ", ".join(names[c] or c for c in t["missing"])
                say(f'  {t["total_open"]:>8.2f} ₪ על מה שיש | {t["name"]} | חסר: {miss}')
    tail(out)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"\nנשמר: {a.out}\n\n{DISCLAIMER}")


def tail(out: dict) -> None:
    if out.get("not_carrying"):
        say(f'\nלא מחזיקים אף אחד מהמוצרים: {", ".join(out["not_carrying"])}')
    if out["failed"]:
        say(f'לא ירדו גם אחרי כל הניסיונות (לא נבדקו): {", ".join(out["failed"])}')
    if out["unlocated"]:
        say(f'אי אפשר למקם (לא נבדקו): {", ".join(out["unlocated"])}')


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("search", "prices"):
        p = sub.add_parser(name)
        p.add_argument("--near", required=True, help="a city, or 'street and number, city'")
        p.add_argument("--radius", type=float, default=3.0, help="straight-line km (default 3)")
        p.add_argument("--chains", default=",".join(chains.CHAINS))
        p.add_argument("--per-chain", type=int, default=0, help="only the N closest branches of each chain")
        p.add_argument("--retries", type=int, default=2)
        p.add_argument("--out", required=True)
        if name == "search":
            p.add_argument("--q", action="append", required=True, help="what the shopper said, e.g. 'אורז פרסי סוגת 1 קג'")
            p.add_argument("--top", type=int, default=8)
            p.add_argument("--min-score", type=float, default=0.5)
        else:
            p.add_argument("--item", action="append", required=True, help="barcode or barcode:qty")
    a = ap.parse_args()
    search(a) if a.cmd == "search" else prices(a)


if __name__ == "__main__":
    main()
