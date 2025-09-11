# filename: runner.py
# -*- coding: utf-8 -*-

import os, time, subprocess, sys
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI")

def tehran_now():
    return datetime.now(timezone(timedelta(hours=3, minutes=30)))

def is_trading_day(dt):
    # Python weekday(): Mon=0 ... Sun=6
    # بورس تهران باز: Sat(5), Sun(6), Mon(0), Tue(1), Wed(2)
    # تعطیل: Thu(3), Fri(4)
    return dt.weekday() not in (3, 4)

def count_today():
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI env var not set")
    today = tehran_now().strftime("%Y-%m-%d")
    client = MongoClient(MONGO_URI)
    col = client["bors"]["daily_50cols"]
    cnt = col.count_documents({"تاریخ": today})
    client.close()
    return today, cnt

def run_ingest_once():
    print("→ running daily_ingest_1300.py", flush=True)
    subprocess.run(["python", "daily_ingest_1300.py"], check=True)

def main():
    now = tehran_now()
    if not is_trading_day(now):
        print(f"ℹ️ {now.strftime('%Y-%m-%d')} تعطیل بازار است؛ اجرا رد شد.")
        sys.exit(0)

    # پس از ۱۳:۰۰ ممکن است چند دقیقه تأخیر در داده باشد → تا ۳۰ دقیقه، هر ۵ دقیقه یک‌بار تکرار
    tries, delay = 6, 300  # 6 * 5min = 30min
    for i in range(1, tries + 1):
        print(f"--- Attempt {i}/{tries} ---", flush=True)
        run_ingest_once()
        today, cnt = count_today()
        print(f"[verify] Tehran today = {today} | inserted docs = {cnt}", flush=True)
        if cnt and cnt > 0:
            print("✅ Data present. Done.", flush=True)
            return
        if i < tries:
            print(f"⌛ هنوز صفر است؛ {delay}s صبر می‌کنیم و دوباره تلاش می‌کنیم ...", flush=True)
            time.sleep(delay)

    print("❌ پایان پنجرهٔ ۳۰ دقیقه‌ای و هنوز داده‌ای درج نشده (احتمالاً تأخیر سرویس/تعطیلی مناسبتی).")

if __name__ == "__main__":
    main()
