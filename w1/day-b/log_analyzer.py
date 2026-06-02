"""
log_analyzer.py — Mini Log Analyzer
Usage: python log_analyzer.py <logfile>

Output:
  1. Tổng số dòng, số template unique
  2. Top-5 template (count + % tổng)
  3. Template tăng đột biến trong 1 giờ gần nhất (so với trung bình)
  4. New templates (chưa xuất hiện trước 1 giờ gần nhất)
"""

import sys
import re

# Fix Windows console encoding for non-ASCII output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collections import defaultdict
from datetime import datetime, timedelta

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig


# ── Log format patterns ───────────────────────────────────────────────────────

# Hadoop/HDFS: "2015-10-18 18:01:47,978 INFO [thread] class: message"
_HADOOP_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \w+ \[.*?\] [\w\.\$]+: (.+)$'
)

# Zookeeper: "2015-07-29 17:41:44,747 - INFO  [thread:class@line] - message"
_ZOOKEEPER_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - \w+\s+\[.*?\] - (.+)$'
)

_TS_FORMAT = '%Y-%m-%d %H:%M:%S'


def _detect_and_parse(line: str):
    """Try each known pattern, return (datetime, message) or None."""
    for pattern in (_HADOOP_PATTERN, _ZOOKEEPER_PATTERN):
        m = pattern.match(line.strip())
        if m:
            ts = datetime.strptime(m.group(1), _TS_FORMAT)
            return ts, m.group(2)
    return None


# ── Core analysis ─────────────────────────────────────────────────────────────

def analyze(log_file: str):
    # 1. Load raw lines
    with open(log_file, encoding='utf-8', errors='replace') as f:
        raw_lines = f.readlines()

    total_lines = len(raw_lines)

    # 2. Init Drain3
    cfg = TemplateMinerConfig()
    cfg.drain_sim_th = 0.5
    miner = TemplateMiner(config=cfg)

    # 3. Parse lines: collect (timestamp, template_id)
    entries = []          # list of (datetime, cluster_id)
    skipped = 0

    for line in raw_lines:
        parsed = _detect_and_parse(line)
        if parsed is None:
            skipped += 1
            continue
        ts, msg = parsed
        result = miner.add_log_message(msg)
        entries.append((ts, result["cluster_id"]))

    # Build lookup: cluster_id → template string
    clusters_map = {c.cluster_id: c for c in miner.drain.clusters}

    # 4. Aggregate: count per template (all time)
    count_all = defaultdict(int)
    for _, cid in entries:
        count_all[cid] += 1

    unique_templates = len(clusters_map)
    parsed_lines = len(entries)

    # 5. Split into "before last hour" vs "last hour"
    if entries:
        last_ts = max(ts for ts, _ in entries)
        cutoff  = last_ts - timedelta(hours=1)
    else:
        last_ts = cutoff = datetime.min

    count_before = defaultdict(int)
    count_last_h = defaultdict(int)
    seen_before  = set()

    for ts, cid in entries:
        if ts <= cutoff:
            count_before[cid] += 1
            seen_before.add(cid)
        else:
            count_last_h[cid] += 1

    # 6. Spike detection: templates whose rate in last-hour > 3× mean-before-rate
    #    mean_before_rate = count_before[cid] / total windows before cutoff
    #    We use raw counts (simpler, still meaningful for 2k-line datasets)
    spikes = []
    for cid, cnt_h in count_last_h.items():
        avg = count_before.get(cid, 0)
        if avg == 0:
            continue  # new template — handled separately
        if cnt_h > 3 * avg:
            spikes.append((cid, cnt_h, avg))
    spikes.sort(key=lambda x: x[1] / max(x[2], 1), reverse=True)

    # 7. New templates in last hour (never seen before cutoff)
    new_in_last_h = [cid for cid in count_last_h if cid not in seen_before]

    # ── Print results ─────────────────────────────────────────────────────────

    sep = "=" * 60

    print(sep)
    print(f"  Log Analyzer — {log_file}")
    print(sep)

    print(f"\n[1] TỔNG QUAN")
    print(f"    Tổng dòng log       : {total_lines:,}")
    print(f"    Dòng parse được     : {parsed_lines:,}  ({skipped} dòng bỏ qua)")
    print(f"    Unique templates    : {unique_templates}")
    print(f"    Thời gian bắt đầu   : {min(ts for ts, _ in entries) if entries else 'N/A'}")
    print(f"    Thời gian kết thúc  : {last_ts if entries else 'N/A'}")

    print(f"\n[2] TOP-5 TEMPLATES (theo tần suất)")
    top5 = sorted(count_all.items(), key=lambda x: x[1], reverse=True)[:5]
    for rank, (cid, cnt) in enumerate(top5, 1):
        pct = cnt / parsed_lines * 100 if parsed_lines else 0
        template_text = clusters_map[cid].get_template()
        # Truncate long templates for readability
        display = template_text if len(template_text) <= 80 else template_text[:77] + "..."
        print(f"    #{rank}  [ID={cid:>4}]  count={cnt:>5}  ({pct:5.1f}%)  {display}")

    print(f"\n[3] SPIKE TEMPLATES trong 1 giờ gần nhất (> 3× trung bình trước đó)")
    print(f"    Mốc thời gian cắt   : {cutoff}")
    if spikes:
        for cid, cnt_h, avg in spikes[:10]:
            ratio = cnt_h / max(avg, 1)
            template_text = clusters_map[cid].get_template()
            display = template_text if len(template_text) <= 70 else template_text[:67] + "..."
            print(f"    [ID={cid:>4}]  last_h={cnt_h}  avg_before={avg}  ratio={ratio:.1f}×  {display}")
    else:
        print("    → Không phát hiện spike đáng kể.")

    print(f"\n[4] NEW TEMPLATES trong 1 giờ gần nhất ({len(new_in_last_h)} templates)")
    if new_in_last_h:
        for cid in new_in_last_h[:10]:
            template_text = clusters_map[cid].get_template()
            display = template_text if len(template_text) <= 80 else template_text[:77] + "..."
            print(f"    [ID={cid:>4}]  {display}")
        if len(new_in_last_h) > 10:
            print(f"    ... và {len(new_in_last_h) - 10} template mới khác.")
    else:
        print("    → Không có template mới trong 1 giờ gần nhất.")

    print(f"\n{sep}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python log_analyzer.py <logfile>")
        sys.exit(1)
    analyze(sys.argv[1])
