#!/usr/bin/env python3
"""Collect visible Douyin search results through the user's logged-in Chrome session."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


FIELDS = ["标题", "链接", "平台", "对标账号", "点赞", "爆点", "入库日期", "搜索关键词"]
METRIC_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)(万)?$")
EXISTING_URL_PATTERN = re.compile(r"https?://[^\])\s]+")


def request_json(url: str, body: str | None = None) -> Any:
    request = urllib.request.Request(url, data=body.encode("utf-8") if body else None)
    if body:
        request.add_header("Content-Type", "text/plain; charset=utf-8")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(3):
        try:
            with opener.open(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.HTTPError, urllib.error.URLError):
            if attempt == 2:
                raise
            time.sleep(2)
    raise RuntimeError("unreachable")


class ChromeCDP:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint.rstrip("/")

    def new_tab(self, url: str) -> str:
        result = request_json(f"{self.endpoint}/new?url={urllib.parse.quote(url, safe='')}")
        return result["targetId"]

    def eval(self, target_id: str, expression: str) -> Any:
        result = request_json(f"{self.endpoint}/eval?target={target_id}", expression)
        value = result.get("value")
        return json.loads(value) if isinstance(value, str) else value

    def scroll(self, target_id: str, amount: int) -> None:
        request_json(f"{self.endpoint}/scroll?target={target_id}&y={amount}")

    def click_at(self, target_id: str, selector: str) -> None:
        request_json(f"{self.endpoint}/clickAt?target={target_id}", selector)

    def close(self, target_id: str) -> None:
        request_json(f"{self.endpoint}/close?target={target_id}")


def parse_likes(value: str) -> int | None:
    match = METRIC_PATTERN.fullmatch(value.strip())
    if not match:
        return None
    return int(float(match.group(1)) * (10_000 if match.group(2) else 1))


def parse_card(text: str, link: str, topic: str, min_likes: int) -> dict[str, Any] | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    metric_index = next((index for index, line in enumerate(lines) if parse_likes(line) is not None), None)
    if metric_index is None or metric_index + 2 >= len(lines):
        return None
    likes = parse_likes(lines[metric_index])
    if likes is None or likes < min_likes:
        return None

    title = lines[metric_index + 1]
    author_index = next((index for index in range(metric_index + 2, len(lines)) if lines[index].startswith("@")), None)
    if author_index is None:
        return None
    author = lines[author_index][1:]
    relative_time = lines[author_index + 1] if author_index + 1 < len(lines) else ""
    return {
        "标题": title,
        "链接": link,
        "平台": "抖音",
        "对标账号": author,
        "点赞": likes,
        "爆点": f"待复核｜{topic}搜索命中，搜索页发布时间显示为{relative_time or '未知'}",
        "入库日期": datetime.now().strftime("%Y-%m-%d 00:00:00"),
        "搜索关键词": topic,
    }


def collect_topic(cdp: ChromeCDP, topic: str, min_likes: int) -> list[dict[str, Any]]:
    target_id = cdp.new_tab(f"https://www.douyin.com/search/{urllib.parse.quote(topic)}?type=general")
    expression = """JSON.stringify([...document.querySelectorAll('.search-result-card')].map(card => {
      const fiberKey = Object.keys(card).find(key => key.startsWith('__reactFiber'));
      const root = fiberKey && card[fiberKey];
      const seen = new Set();
      let awemeKey = '';
      const walk = (value, depth) => {
        if (depth > 7 || !value || typeof value !== 'object' || seen.has(value) || awemeKey) return;
        seen.add(value);
        if (typeof value.key === 'string' && value.key.includes('_aweme_')) { awemeKey = value.key; return; }
        for (const key of Object.keys(value)) {
          if (key === 'return' || key === 'stateNode' || key === 'alternate') continue;
          try { walk(value[key], depth + 1); } catch (_) {}
        }
      };
      walk(root, 0);
      const match = awemeKey.match(/_aweme_(\\d+)/);
      return match ? { text: card.innerText.trim(), href: `https://www.douyin.com/video/${match[1]}` } : null;
    }).filter(Boolean))"""
    try:
        time.sleep(2)
        cdp.click_at(target_id, '[data-key="video"]')
        cards_by_link: dict[str, dict[str, str]] = {}
        for _ in range(4):
            cdp.scroll(target_id, 900)
            time.sleep(2)
            for card in cdp.eval(target_id, expression) or []:
                cards_by_link[card["href"]] = card
        records = [parse_card(card["text"], card["href"], topic, min_likes) for card in cards_by_link.values()]
        return [record for record in records if record]
    finally:
        cdp.close(target_id)


def existing_feishu_urls(base_token: str, table_id: str) -> set[str]:
    urls = set()
    offset = 0
    while True:
        command = [
            "lark-cli", "base", "+record-list", "--base-token", base_token, "--table-id", table_id,
            "--field-id", "链接", "--offset", str(offset), "--limit", "200", "--format", "json", "--as", "user",
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout).get("data", {})
        for row in payload.get("data", []):
            if row and isinstance(row[0], str):
                urls.update(EXISTING_URL_PATTERN.findall(row[0]))
        if not payload.get("has_more"):
            return urls
        offset += 200


def merge_by_link(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        existing = merged.get(record["链接"])
        if not existing:
            merged[record["链接"]] = record
            continue
        keywords = set(existing["搜索关键词"].split("｜")) | set(record["搜索关键词"].split("｜"))
        existing["搜索关键词"] = "｜".join(sorted(keywords))
    return list(merged.values())


def write_feishu(records: list[dict[str, Any]], base_token: str, table_id: str, max_new_records: int = 0) -> list[dict[str, Any]]:
    existing_urls = existing_feishu_urls(base_token, table_id)
    new_records = [record for record in records if record["链接"] not in existing_urls]
    if max_new_records:
        new_records = new_records[:max_new_records]
    if not new_records:
        return []
    for start in range(0, len(new_records), 200):
        rows = [[record.get(field) for field in FIELDS] for record in new_records[start:start + 200]]
        payload = json.dumps({"fields": FIELDS, "rows": rows}, ensure_ascii=False)
        command = [
            "lark-cli", "base", "+record-batch-create", "--base-token", base_token, "--table-id", table_id,
            "--as", "user", "--json", payload,
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
    return new_records


def send_feishu_notification(records: list[dict[str, Any]], user_id: str) -> None:
    date_label = datetime.now().strftime("%Y-%m-%d")
    lines = [f"方比比爆款监测｜{date_label}", f"今日新增 {len(records)} 条 2 万赞以上内容。"]
    if records:
        for index, record in enumerate(sorted(records, key=lambda item: item["点赞"], reverse=True)[:10], start=1):
            lines.append(f"{index}. [{record['标题']}]({record['链接']})｜{record['点赞']:,}赞｜{record['搜索关键词']}")
    else:
        lines.append("没有新增爆款，已完成链接去重检查。")
    command = [
        "lark-cli", "im", "+messages-send", "--as", "bot", "--user-id", user_id,
        "--markdown", "\n".join(lines), "--idempotency-key", f"fangbibi-viral-{date_label}",
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topics-file", default=str(Path(__file__).parents[1] / "config" / "mother_topics.json"))
    parser.add_argument("--cdp-endpoint", default="http://localhost:3456")
    parser.add_argument("--output", default=str(Path.home() / "Library" / "Application Support" / "fangbibi-viral-collector" / "latest.json"))
    parser.add_argument("--write-feishu", action="store_true")
    parser.add_argument("--base-token")
    parser.add_argument("--table-id")
    parser.add_argument("--notify-user-id")
    parser.add_argument("--max-per-topic", type=int, default=0)
    parser.add_argument("--max-new-records", type=int, default=0)
    args = parser.parse_args()

    config = json.loads(Path(args.topics_file).read_text(encoding="utf-8"))
    min_likes = int(config.get("min_likes", 20_000))
    cdp = ChromeCDP(args.cdp_endpoint)
    records: list[dict[str, Any]] = []
    for topic in config["topics"]:
        topic_records = collect_topic(cdp, topic, min_likes)
        records.extend(topic_records[:args.max_per_topic] if args.max_per_topic else topic_records)

    unique_records = merge_by_link(records)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(unique_records, ensure_ascii=False, indent=2), encoding="utf-8")

    inserted_records: list[dict[str, Any]] = []
    if args.write_feishu:
        if not args.base_token or not args.table_id:
            parser.error("--write-feishu requires --base-token and --table-id")
        inserted_records = write_feishu(unique_records, args.base_token, args.table_id, args.max_new_records)
    if args.notify_user_id:
        if not args.write_feishu:
            parser.error("--notify-user-id requires --write-feishu")
        send_feishu_notification(inserted_records, args.notify_user_id)
    print(json.dumps({"collected": len(unique_records), "inserted": len(inserted_records), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
