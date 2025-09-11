# filename: daily_ingest_1300.py
# -*- coding: utf-8 -*-

import os, time, requests
from pymongo import MongoClient, errors

# === تنظیم متغیرهای محیطی در Render ===
TOKEN     = os.getenv("TOKEN")        # توکن ChartAPI
MONGO_URI = os.getenv("MONGO_URI")    # اتصال MongoDB

DB_NAME   = "bors"
COLL_NAME = "daily_50cols"
BASE      = f"https://bourse.chartapi.ir/{TOKEN}" if TOKEN else None
SLEEP     = 0.25

def get_json(path, params=None, retry=4):
    if not BASE: raise RuntimeError("TOKEN env var not set")
    url = f"{BASE}/{path}"
    for i in range(retry):
        try:
            r = requests.get(url, params=params, timeout=40)
            r.raise_for_status()
            return r.json()
        except Exception:
            if i == retry - 1:
                raise
            time.sleep(0.8 * (i + 1))

def get_collection():
    if not MONGO_URI: raise RuntimeError("MONGO_URI env var not set")
    client = MongoClient(
        MONGO_URI,
        retryWrites=True,
        maxPoolSize=1,
        serverSelectionTimeoutMS=20000,
        connectTimeoutMS=20000,
        socketTimeoutMS=600000,
    )
    col = client[DB_NAME][COLL_NAME]
    try:
        col.create_index([("نماد", 1), ("تاریخ", 1)], unique=True, background=True)
    except Exception:
        pass
    return client, col

def fetch_symbols():
    data = get_json("alldata")
    rows = data if isinstance(data, list) else []
    out = []
    for row in rows:
        name = row.get("name") or row.get("Name") or row.get("symbol")
        mkt  = row.get("MarketType") or row.get("market") or row.get("market_type")
        if name and isinstance(name, str) and (mkt in ("بورس", "فرابورس")):
            out.append(name.strip())
    # یکتا و مرتب
    return sorted(list(dict.fromkeys([s for s in out if s])))

def build_today_doc(sym):
    # کندل تعدیل‌شده امروز
    time.sleep(SLEEP)
    candel = get_json("candeldata", {"name": sym, "type": 2})
    if not isinstance(candel, list) or not candel:
        raise RuntimeError("candeldata empty")
    last = candel[-1]
    prev = candel[-2] if len(candel) >= 2 else None

    def g(d, k, default=None): return d.get(k, default) if isinstance(d, dict) else default

    date_str  = g(last, "date", "")
    open_adj  = int(round(float(g(last, "Open",   0) or 0)))
    high_adj  = int(round(float(g(last, "high",   0) or 0)))
    low_adj   = int(round(float(g(last, "low",    0) or 0)))
    close_adj = int(round(float(g(last, "Close",  0) or 0)))
    vol_adj   = int(round(float(g(last, "volume", 0) or 0)))
    yest_close= int(round(float(g(prev, "Close", 0) or 0))) if prev else None

    # حقیقی/حقوقی امروز
    time.sleep(SLEEP)
    flows = get_json("coo_real_history", {"name": sym})
    flows_last = flows[-1] if isinstance(flows, list) and flows else {}
    if flows_last.get("date") != date_str:
        for r in reversed(flows or []):
            if r.get("date") == date_str:
                flows_last = r
                break

    to_int = lambda x: int(round(float(x or 0)))
    rb_count = to_int(flows_last.get("real_buy_count"))
    rs_count = to_int(flows_last.get("real_sell_count"))
    cb_count = to_int(flows_last.get("co_buy_count"))
    cs_count = to_int(flows_last.get("co_sell_count"))
    rb_val   = to_int(flows_last.get("real_buy_value"))
    rs_val   = to_int(flows_last.get("real_sell_value"))
    cb_val   = to_int(flows_last.get("co_buy_value"))
    cs_val   = to_int(flows_last.get("co_sell_value"))

    percap_buy  = (rb_val / rb_count) if rb_count > 0 else None
    percap_sell = (rs_val / rs_count) if rs_count > 0 else None
    power  = (percap_buy / percap_sell) if (percap_buy and percap_sell) else None
    inflow = rb_val - rs_val
    pct    = ((close_adj / yest_close - 1) * 100.0) if (yest_close and yest_close != 0) else None

    doc = {
        "نماد": sym, "تاریخ": str(date_str),
        # قیمت‌ها (همه تعدیل)
        "اولین قیمت": open_adj, "بیشترین قیمت": high_adj, "کمترین قیمت": low_adj,
        "قیمت پایانی": close_adj, "آخرین قیمت": close_adj, "قیمت پایانی (تعدیل شده)": close_adj,
        "قیمت دیروز": yest_close, "حجم": vol_adj,
        # درصدها
        "درصد تغییر آخرین قیمت": round(pct, 4) if pct is not None else None,
        "درصد تغییر قیمت پایانی": round(pct, 4) if pct is not None else None,
        # حقیقی/حقوقی
        "کدهای خریدار حقیقی": rb_count, "کدهای فروشنده حقیقی": rs_count,
        "کدهای خریدار حقوقی": cb_count, "کدهای فروشنده حقوقی": cs_count,
        "ارزش خرید حقیقی (تومان)": rb_val, "ارزش فروش حقیقی (تومان)": rs_val,
        "ارزش خرید حقوقی (تومان)": cb_val, "ارزش فروش حقوقی (تومان)": cs_val,
        # مشتقات
        "سرانه خرید (تومان)": round(percap_buy, 2) if percap_buy else None,
        "سرانه فروش (تومان)": round(percap_sell, 2) if percap_sell else None,
        "قدرت خرید": round(power, 4) if power else None,
        "ورود پول (تومان)": inflow,
        "ارزش معاملات (تومان)": rb_val + cb_val,
    }
    return doc

def main():
    client, col = get_collection()
    syms = fetch_symbols()
    ok, skip = 0, 0
    for i, s in enumerate(syms, 1):
        try:
            doc = build_today_doc(s)
            col.update_one({"نماد": doc["نماد"], "تاریخ": doc["تاریخ"]}, {"$set": doc}, upsert=True)
            ok += 1
            print(f"[{i}/{len(syms)}] OK {s} {doc['تاریخ']}")
        except Exception as e:
            skip += 1
            print(f"[{i}/{len(syms)}] SKIP {s} → {e}")
        time.sleep(SLEEP)
    try: client.close()
    except: pass
    print(f"Done. ok={ok}, skip={skip}")

if __name__ == "__main__":
    main()
