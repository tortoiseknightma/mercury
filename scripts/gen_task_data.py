"""Generate all input + expected files for the 7 new benchmark tasks."""
import csv
import io
import json
import math
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)
TASKS = Path("src/mercury/eval/tasks")

# ============================================================
# multi-001: Multi-source CSV merge with GBK + JSON corrections
# ============================================================
def gen_multi_001():
    d = TASKS / "multi" / "multi-001"
    d.mkdir(parents=True, exist_ok=True)

    rows_2023 = [
        {"order_id": 1001, "product": "笔记本电脑", "quantity": 2, "unit_price": 5999.00, "date": "2023-06-15"},
        {"order_id": 1002, "product": "无线鼠标", "quantity": 10, "unit_price": 79.90, "date": "2023-07-20"},
        {"order_id": 1003, "product": "机械键盘", "quantity": 5, "unit_price": 349.00, "date": "2023-08-01"},
        {"order_id": 1002, "product": "无线鼠标", "quantity": 10, "unit_price": 79.90, "date": "2023-07-20"},  # dup
        {"order_id": 1004, "product": "显示器", "quantity": 3, "unit_price": 2199.00, "date": "2023-09-10"},
        {"order_id": 1005, "product": "USB集线器", "quantity": 20, "unit_price": 45.50, "date": "2023-11-05"},
    ]
    # Write as GBK
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["order_id","product","quantity","unit_price","date"])
    w.writeheader()
    w.writerows(rows_2023)
    (d / "sales_2023.csv").write_bytes(buf.getvalue().encode("gbk"))

    rows_2024 = [
        {"Order_ID": 2001, "Product": "蓝牙耳机", "Quantity": 15, "Unit_Price": 199.00, "Date": "2024-01-10"},
        {"Order_ID": 2002, "Product": "移动硬盘", "Quantity": 8, "Unit_Price": 459.00, "Date": "2024-02-28"},
        {"Order_ID": 2003, "Product": "平板电脑", "Quantity": 4, "Unit_Price": 3299.00, "Date": "2024-03-15"},
        {"Order_ID": 2004, "Product": "充电宝", "Quantity": 25, "Unit_Price": 89.90, "Date": "2024-05-20"},
        {"Order_ID": 2005, "Product": "摄像头", "Quantity": 6, "Unit_Price": 279.00, "Date": "2024-07-01"},
    ]
    buf2 = io.StringIO()
    w2 = csv.DictWriter(buf2, fieldnames=["Order_ID","Product","Quantity","Unit_Price","Date"])
    w2.writeheader()
    w2.writerows(rows_2024)
    (d / "sales_2024.csv").write_text(buf2.getvalue(), encoding="utf-8")

    corrections = [
        {"order_id": 1003, "field": "unit_price", "new_value": 329.00},
        {"order_id": 2002, "field": "quantity", "new_value": 10},
    ]
    (d / "corrections.json").write_text(json.dumps(corrections, ensure_ascii=False, indent=2), encoding="utf-8")

    # Build expected
    all_rows = [
        {"order_id": 1001, "product": "笔记本电脑", "quantity": 2, "unit_price": 5999.00, "date": "2023-06-15"},
        {"order_id": 1002, "product": "无线鼠标", "quantity": 10, "unit_price": 79.90, "date": "2023-07-20"},
        {"order_id": 1003, "product": "机械键盘", "quantity": 5, "unit_price": 329.00, "date": "2023-08-01"},  # corrected
        {"order_id": 1004, "product": "显示器", "quantity": 3, "unit_price": 2199.00, "date": "2023-09-10"},
        {"order_id": 1005, "product": "USB集线器", "quantity": 20, "unit_price": 45.50, "date": "2023-11-05"},
        {"order_id": 2001, "product": "蓝牙耳机", "quantity": 15, "unit_price": 199.00, "date": "2024-01-10"},
        {"order_id": 2002, "product": "移动硬盘", "quantity": 10, "unit_price": 459.00, "date": "2024-02-28"},  # corrected
        {"order_id": 2003, "product": "平板电脑", "quantity": 4, "unit_price": 3299.00, "date": "2024-03-15"},
        {"order_id": 2004, "product": "充电宝", "quantity": 25, "unit_price": 89.90, "date": "2024-05-20"},
        {"order_id": 2005, "product": "摄像头", "quantity": 6, "unit_price": 279.00, "date": "2024-07-01"},
    ]
    import pandas as pd
    df = pd.DataFrame(all_rows).sort_values("order_id").reset_index(drop=True)
    df.to_csv(d / "expected.csv", index=False)
    print("  multi-001 OK")


# ============================================================
# multi-002: Multi-table JOIN + currency conversion
# ============================================================
def gen_multi_002():
    d = TASKS / "multi" / "multi-002"
    d.mkdir(parents=True, exist_ok=True)

    orders = [
        {"order_id": "A01", "product_id": "P1", "amount": 120.00, "currency": "EUR", "order_date": "2024-03-01"},
        {"order_id": "A02", "product_id": "P2", "amount": 8500.00, "currency": "JPY", "order_date": "2024-03-01"},
        {"order_id": "A03", "product_id": "P3", "amount": 250.00, "currency": "USD", "order_date": "2024-03-15"},
        {"order_id": "A04", "product_id": "P1", "amount": 95.50, "currency": "EUR", "order_date": "2024-03-15"},
        {"order_id": "A05", "product_id": "P4", "amount": 750.00, "currency": "GBP", "order_date": "2024-03-20"},
        {"order_id": "A06", "product_id": "P2", "amount": 12000.00, "currency": "JPY", "order_date": "2024-03-22"},
        {"order_id": "A07", "product_id": "P5", "amount": 45.00, "currency": "EUR", "order_date": "2024-04-01"},
        {"order_id": "A08", "product_id": "P3", "amount": 300.00, "currency": "USD", "order_date": "2024-04-05"},
    ]
    products = [
        {"product_id": "P1", "product_name": "Widget A", "category": "Electronics"},
        {"product_id": "P2", "product_name": "Gadget B", "category": "Electronics"},
        {"product_id": "P3", "product_name": "Tool C",   "category": "Hardware"},
        {"product_id": "P4", "product_name": "Part D",   "category": "Hardware"},
        {"product_id": "P5", "product_name": "Supply E",  "category": "Office"},
    ]
    rates = {
        "2024-03-01": {"EUR": 1.08, "JPY": 0.0067, "GBP": 1.27, "USD": 1.0},
        "2024-03-15": {"EUR": 1.09, "JPY": 0.0066, "GBP": 1.28, "USD": 1.0},
        "2024-03-20": {"EUR": 1.08, "JPY": 0.0068, "GBP": 1.26, "USD": 1.0},
        "2024-04-01": {"EUR": 1.07, "JPY": 0.0065, "GBP": 1.25, "USD": 1.0},
    }

    import pandas as pd
    pd.DataFrame(orders).to_csv(d / "orders.csv", index=False)
    pd.DataFrame(products).to_csv(d / "products.csv", index=False)
    (d / "exchange_rates.json").write_text(json.dumps(rates, indent=2), encoding="utf-8")

    # Compute expected: for A06 date 2024-03-22 → no exact match, fallback to nearest earlier = 2024-03-20
    # For A08 date 2024-04-05 → fallback to 2024-04-01
    rate_lookup = {
        "A01": 1.08, "A02": 0.0067, "A03": 1.0, "A04": 1.09,
        "A05": 1.26, "A06": 0.0068, "A07": 1.07, "A08": 1.0,
    }
    results = []
    for o in orders:
        r = rate_lookup[o["order_id"]]
        usd = round(o["amount"] * r, 2)
        p = next(p for p in products if p["product_id"] == o["product_id"])
        results.append({"category": p["category"], "amount_usd": usd})

    df = pd.DataFrame(results)
    agg = df.groupby("category").agg(
        total_usd=("amount_usd", "sum"),
        order_count=("amount_usd", "count"),
    ).reset_index()
    agg["total_usd"] = agg["total_usd"].round(2)
    agg = agg.sort_values("category").reset_index(drop=True)
    agg.to_csv(d / "expected.csv", index=False)
    print("  multi-002 OK")


# ============================================================
# xml-001: Namespaced XML → flat CSV
# ============================================================
def gen_xml_001():
    d = TASKS / "xml" / "xml-001"
    d.mkdir(parents=True, exist_ok=True)

    xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<bk:catalog xmlns:bk="http://example.com/books" xmlns:pub="http://example.com/publisher">
  <bk:book isbn="978-0-13-468599-1">
    <bk:title>The Pragmatic Programmer</bk:title>
    <bk:author>
      <bk:name>David Thomas</bk:name>
      <bk:nationality>British</bk:nationality>
    </bk:author>
    <pub:publisher>Addison-Wesley</pub:publisher>
    <bk:price currency="USD">49.99</bk:price>
    <bk:year>2019</bk:year>
  </bk:book>
  <bk:book isbn="978-0-596-51774-8">
    <bk:title>JavaScript: The Good Parts</bk:title>
    <bk:author>
      <bk:name>Douglas Crockford</bk:name>
      <bk:nationality>American</bk:nationality>
    </bk:author>
    <pub:publisher>O'Reilly Media</pub:publisher>
    <bk:price currency="USD">29.99</bk:price>
    <bk:year>2008</bk:year>
  </bk:book>
  <bk:book isbn="978-1-49-195016-0">
    <bk:title>Fluent Python</bk:title>
    <bk:author>
      <bk:name>Luciano Ramalho</bk:name>
      <bk:nationality>Brazilian</bk:nationality>
    </bk:author>
    <pub:publisher>O'Reilly Media</pub:publisher>
    <bk:price currency="USD">59.99</bk:price>
    <bk:year>2022</bk:year>
  </bk:book>
  <bk:book isbn="978-0-13-235088-4">
    <bk:title>Clean Code</bk:title>
    <bk:author>
      <bk:name>Robert C. Martin</bk:name>
      <bk:nationality>American</bk:nationality>
    </bk:author>
    <pub:publisher>Prentice Hall</pub:publisher>
    <bk:price currency="USD">39.99</bk:price>
    <bk:year>2008</bk:year>
  </bk:book>
  <bk:book isbn="978-1-09-813989-0">
    <bk:title>Designing Data-Intensive Applications</bk:title>
    <bk:author>
      <bk:name>Martin Kleppmann</bk:name>
      <bk:nationality>German</bk:nationality>
    </bk:author>
    <pub:publisher>O'Reilly Media</pub:publisher>
    <bk:price currency="USD">44.99</bk:price>
    <bk:year>2017</bk:year>
  </bk:book>
</bk:catalog>
'''
    (d / "catalog.xml").write_text(xml_content, encoding="utf-8")

    import pandas as pd
    expected = pd.DataFrame([
        {"isbn": "978-0-13-468599-1", "title": "The Pragmatic Programmer", "author_name": "David Thomas", "author_nationality": "British", "publisher": "Addison-Wesley", "price": 49.99, "year": 2019},
        {"isbn": "978-0-596-51774-8", "title": "JavaScript: The Good Parts", "author_name": "Douglas Crockford", "author_nationality": "American", "publisher": "O'Reilly Media", "price": 29.99, "year": 2008},
        {"isbn": "978-1-49-195016-0", "title": "Fluent Python", "author_name": "Luciano Ramalho", "author_nationality": "Brazilian", "publisher": "O'Reilly Media", "price": 59.99, "year": 2022},
        {"isbn": "978-0-13-235088-4", "title": "Clean Code", "author_name": "Robert C. Martin", "author_nationality": "American", "publisher": "Prentice Hall", "price": 39.99, "year": 2008},
        {"isbn": "978-1-09-813989-0", "title": "Designing Data-Intensive Applications", "author_name": "Martin Kleppmann", "author_nationality": "German", "publisher": "O'Reilly Media", "price": 44.99, "year": 2017},
    ])
    expected.to_csv(d / "expected.csv", index=False)
    print("  xml-001 OK")


# ============================================================
# xml-002: Broken XML repair + extraction
# ============================================================
def gen_xml_002():
    d = TASKS / "xml" / "xml-002"
    d.mkdir(parents=True, exist_ok=True)

    # BOM + unclosed tags + mixed HTML entities
    broken = '\ufeff<?xml version="1.0" encoding="UTF-8"?>\n'
    broken += '<rss version="2.0">\n<channel>\n'
    broken += '<title>Tech News Feed</title>\n'
    broken += '''<item>
  <title>Python 3.13 Released with &amp; New Features</title>
  <link>https://example.com/python313</link>
  <pubDate>Mon, 15 Jan 2024 10:00:00 GMT</pubDate>
  <description><![CDATA[Python 3.13 brings <b>exciting</b> new features including pattern matching improvements &amp; faster execution.]]></description>
</item>
<item>
  <title>AI Agents &mdash; The Next Frontier</title>
  <link>https://example.com/ai-agents
  <pubDate>Wed, 20 Feb 2024 14:30:00 GMT</pubDate>
  <description>The rise of autonomous <i>AI agents</i> is transforming how we build &amp; deploy software systems.</description>
</item>
<item>
  <title>Rust vs Go: 2024 Comparison</title>
  <link>https://example.com/rust-vs-go</link>
  <pubDate>Fri, 01 Mar 2024 09:15:00 GMT</pubDate>
  <description><![CDATA[A comprehensive <strong>comparison</strong> of Rust and Go for systems programming & web backends.]]></description>
</item>
<item>
  <title>Database Trends &amp; Predictions</title>
  <link>https://example.com/db-trends</link>
  <pubDate>Sun, 10 Mar 2024 16:45:00 GMT</pubDate>
  <description>Vector databases, NewSQL, and the return of <em>stored procedures</em> &mdash; what&apos;s next for data storage?</description>
</item>
'''
    broken += '</channel>\n</rss>'

    (d / "broken_feed.xml").write_text(broken, encoding="utf-8-sig")

    import pandas as pd
    expected = pd.DataFrame([
        {"title": "Python 3.13 Released with & New Features", "link": "https://example.com/python313", "pub_date": "Mon, 15 Jan 2024 10:00:00 GMT", "description": "Python 3.13 brings exciting new features including pattern matching improvements & faster execution."},
        {"title": "AI Agents \u2014 The Next Frontier", "link": "https://example.com/ai-agents", "pub_date": "Wed, 20 Feb 2024 14:30:00 GMT", "description": "The rise of autonomous AI agents is transforming how we build & deploy software systems."},
        {"title": "Rust vs Go: 2024 Comparison", "link": "https://example.com/rust-vs-go", "pub_date": "Fri, 01 Mar 2024 09:15:00 GMT", "description": "A comprehensive comparison of Rust and Go for systems programming & web backends."},
        {"title": "Database Trends & Predictions", "link": "https://example.com/db-trends", "pub_date": "Sun, 10 Mar 2024 16:45:00 GMT", "description": "Vector databases, NewSQL, and the return of stored procedures \u2014 what's next for data storage?"},
    ])
    expected.to_csv(d / "expected.csv", index=False)
    print("  xml-002 OK")


# ============================================================
# pipeline-001: Anomaly detection
# ============================================================
def gen_pipeline_001():
    d = TASKS / "pipeline" / "pipeline-001"
    d.mkdir(parents=True, exist_ok=True)

    import pandas as pd
    import numpy as np
    np.random.seed(42)

    n = 200
    base = 100.0
    noise = np.random.normal(0, 2, n)
    values = base + noise

    # Inject spike anomalies at specific positions
    spike_indices = [15, 42, 78, 123, 167]
    for i in spike_indices:
        values[i] = base + np.random.choice([-1, 1]) * (15 + np.random.uniform(0, 5))

    # Inject drift anomalies (gradual shift)
    drift_indices = [90, 91, 92, 93, 94]
    for i in drift_indices:
        values[i] = base + 12 + np.random.uniform(0, 3)

    timestamps = [datetime(2024, 1, 1) + timedelta(minutes=5*i) for i in range(n)]

    df = pd.DataFrame({
        "timestamp": [t.strftime("%Y-%m-%d %H:%M:%S") for t in timestamps],
        "value": [round(v, 2) for v in values],
    })
    df.to_csv(d / "sensor_readings.csv", index=False)

    # Compute expected: Z-score > 3 based on full dataset mean/std
    mean_val = values.mean()
    std_val = values.std()
    anomalies = [abs(v - mean_val) > 3 * std_val for v in values]
    df["is_anomaly"] = anomalies
    df.to_csv(d / "expected.csv", index=False)
    anomaly_count = sum(anomalies)
    print(f"  pipeline-001 OK ({anomaly_count} anomalies)")


# ============================================================
# pipeline-002: Time series alignment + interpolation
# ============================================================
def gen_pipeline_002():
    d = TASKS / "pipeline" / "pipeline-002"
    d.mkdir(parents=True, exist_ok=True)

    import pandas as pd
    import numpy as np
    np.random.seed(42)

    start = datetime(2024, 6, 1, 0, 0)

    # Station A: every 5 minutes for 2 hours = 25 points
    a_times = [start + timedelta(minutes=5*i) for i in range(25)]
    a_values = [20.0 + 3*math.sin(i*0.3) + random.uniform(-0.5, 0.5) for i in range(25)]
    a_values = [round(v, 2) for v in a_values]

    df_a = pd.DataFrame({
        "timestamp": [t.strftime("%Y-%m-%d %H:%M:%S") for t in a_times],
        "value": a_values,
    })
    df_a.to_csv(d / "station_a.csv", index=False)

    # Station B: every 7 minutes for 2 hours = ~17 points, drop a few
    b_times = [start + timedelta(minutes=7*i) for i in range(18)]
    b_values = [18.0 + 2*math.cos(i*0.25) + random.uniform(-0.3, 0.3) for i in range(18)]
    b_values = [round(v, 2) for v in b_values]
    # Remove indices 5, 10 to simulate gaps
    b_times = [t for i, t in enumerate(b_times) if i not in (5, 10)]
    b_values = [v for i, v in enumerate(b_values) if i not in (5, 10)]

    df_b = pd.DataFrame({
        "timestamp": [t.strftime("%Y-%m-%d %H:%M:%S") for t in b_times],
        "value": b_values,
    })
    df_b.to_csv(d / "station_b.csv", index=False)

    # Build expected: 1-minute grid from 00:00 to 02:00 = 121 points
    grid = [start + timedelta(minutes=i) for i in range(121)]

    # Interpolate A
    a_ts = pd.Series(a_values, index=pd.to_datetime(a_times))
    a_resampled = a_ts.resample("1min").interpolate(method="time")
    a_resampled = a_resampled.reindex(pd.to_datetime(grid))
    # Forward-fill any NaNs at edges
    a_resampled = a_resampled.interpolate(method="time").ffill().bfill()

    # Interpolate B
    b_ts = pd.Series(b_values, index=pd.to_datetime(b_times))
    b_resampled = b_ts.resample("1min").interpolate(method="time")
    b_resampled = b_resampled.reindex(pd.to_datetime(grid))
    b_resampled = b_resampled.interpolate(method="time").ffill().bfill()

    expected = pd.DataFrame({
        "timestamp": [t.strftime("%Y-%m-%d %H:%M:%S") for t in grid],
        "a_value": [round(v, 2) for v in a_resampled.values],
        "b_value": [round(v, 2) for v in b_resampled.values],
        "diff": [round(a - b, 2) for a, b in zip(a_resampled.values, b_resampled.values)],
    })
    expected.to_csv(d / "expected.csv", index=False)
    print("  pipeline-002 OK")


# ============================================================
# pipeline-003: Natural language query → filtered CSV
# ============================================================
def gen_pipeline_003():
    d = TASKS / "pipeline" / "pipeline-003"
    d.mkdir(parents=True, exist_ok=True)

    import pandas as pd

    transactions = []
    categories = ["Electronics", "Clothing", "Food", "Office", "Electronics", "Clothing"]
    types = ["purchase", "refund", "purchase", "purchase", "refund", "purchase"]
    random.seed(42)
    base_date = datetime(2024, 1, 1)
    for i in range(60):
        cat = categories[i % len(categories)]
        typ = types[i % len(types)]
        amount = round(random.uniform(50, 25000), 2)
        date = base_date + timedelta(days=random.randint(0, 364))
        transactions.append({
            "transaction_id": f"TXN-{1000+i}",
            "date": date.strftime("%Y-%m-%d"),
            "category": cat,
            "type": typ,
            "amount": amount,
        })

    df = pd.DataFrame(transactions)
    df.to_csv(d / "transactions.csv", index=False)

    query = (
        "Find all refund transactions in Q3 2024 (July 1 to September 30) "
        "where the amount exceeds 5000 and the category is Electronics."
    )
    (d / "query.txt").write_text(query, encoding="utf-8")

    # Compute expected
    df["date"] = pd.to_datetime(df["date"])
    mask = (
        (df["type"] == "refund") &
        (df["date"] >= "2024-07-01") &
        (df["date"] <= "2024-09-30") &
        (df["amount"] > 5000) &
        (df["category"] == "Electronics")
    )
    result = df[mask].copy()
    result["date"] = result["date"].dt.strftime("%Y-%m-%d")
    result = result.sort_values("date").reset_index(drop=True)
    result.to_csv(d / "expected.csv", index=False)
    print(f"  pipeline-003 OK ({len(result)} matching rows)")


if __name__ == "__main__":
    print("Generating task data...")
    gen_multi_001()
    gen_multi_002()
    gen_xml_001()
    gen_xml_002()
    gen_pipeline_001()
    gen_pipeline_002()
    gen_pipeline_003()
    print("Done!")
