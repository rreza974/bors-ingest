# filename: runner.py
# -*- coding: utf-8 -*-

import os, time, subprocess
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI")

def count_today():
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI env var not set")
    tehran = timezone(timedelta(hours=3, minutes=30))
    today = datetime.now(tehran).strftime("%Y-%m-%d")
    client = MongoClient(MONGO_URI)
    col = client["bors"]["daily_50cols"]
    cnt = col.count_documents({"تاریخ": today})
    client.close()
    return today, cnt

def run_ingest_once():
    # اجرای اسکریپت اصلی
    subprocess.run(["python", "daily_ingest_1300.py"], check=True)

def main():
    tries = 3           # تا ۳ بار تلاش
    delay = 300         # فاصله بین تلاش‌ها: ۵ دقیقه
    for i in range(1, tries+1):
        print(f"--- Attempt {i}/{tries} ---")
        run_ingest_once()
        today, cnt = count_today()
        print(f"[verify] Tehran today = {today} | inserted docs = {cnt}")
        if cnt and cnt > 0:
            print("✅ Data present. Done.")
            return
        if i < tries:
            print(f"⚠️ No data yet. Sleeping {delay}s then retry...")
            time.sleep(delay)
    print("❌ Finished retries with zero inserts.")

if __name__ == "__main__":
    main()
