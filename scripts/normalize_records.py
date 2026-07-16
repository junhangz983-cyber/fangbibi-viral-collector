#!/usr/bin/env python3
"""Normalize MediaCrawler-like exports into a fixed Feishu-ready CSV."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

FIELDS = [
    "标题",
    "链接",
    "平台",
    "对标账号",
    "发布时间",
    "点赞",
    "收藏",
    "评论",
    "分享",
    "开头钩子",
    "爆点判断",
]

LINK_KEYS = ("aweme_url", "note_url", "url", "link", "share_url")
TITLE_KEYS = ("title", "desc", "content", "text")
ACCOUNT_KEYS = ("nickname", "author_name", "user_name", "user_nickname")
TIME_KEYS = ("create_time", "time", "publish_time", "publishTime")
LIKE_KEYS = ("liked_count", "digg_count", "like_count", "likes", "thumbs_up")
FAVORITE_KEYS = ("collected_count", "collect_count", "favorite_count", "fav_count")
COMMENT_KEYS = ("comment_count", "comments_count", "comments")
SHARE_KEYS = ("share_count", "shares_count", "share")


def is_content_record(value: Dict[str, Any]) -> bool:
    has_link = any(key in value for key in LINK_KEYS)
    has_title = any(key in value for key in TITLE_KEYS)
    has_time_and_metric = any(key in value for key in TIME_KEYS) and any(
        key in value for key in (*LIKE_KEYS, *FAVORITE_KEYS, *COMMENT_KEYS, *SHARE_KEYS)
    )
    return has_link or has_title or has_time_and_metric


def coerce_rows(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from coerce_rows(item)
        return
    if isinstance(value, dict):
        if is_content_record(value):
            yield value
        for item in value.values():
            if isinstance(item, (dict, list)):
                yield from coerce_rows(item)


def load_records(path: Path) -> List[Dict[str, Any]]:
    if path.is_dir():
        records: List[Dict[str, Any]] = []
        for child in sorted(path.rglob("*")):
            if child.suffix.lower() in {".json", ".jsonl", ".csv"}:
                records.extend(load_records(child))
        return records

    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as fh:
            return list(csv.DictReader(fh))

    if path.suffix.lower() == ".jsonl":
        rows: List[Dict[str, Any]] = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.extend(coerce_rows(json.loads(line)))
        return rows

    if path.suffix.lower() == ".json":
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return list(coerce_rows(data))

    return []


def find_value(record: Any, keys: Sequence[str]) -> Any:
    if isinstance(record, dict):
        for key in keys:
            value = record.get(key)
            if value not in (None, "", [], {}):
                return value
        for value in record.values():
            found = find_value(value, keys)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(record, list):
        for item in record:
            found = find_value(item, keys)
            if found not in (None, "", [], {}):
                return found
    return ""


def first_text(record: Dict[str, Any], keys: Sequence[str]) -> str:
    value = find_value(record, keys)
    return str(value).strip() if value not in (None, "", [], {}) else ""


def parse_int(value: Any) -> int:
    if value in (None, "", []):
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def format_time(value: Any) -> str:
    if value in (None, "", []):
        return ""
    if isinstance(value, (int, float)):
        number = int(value)
        if number > 10_000_000_000:
            number //= 1000
        return dt.datetime.fromtimestamp(number).strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).strip()
    if re.fullmatch(r"\d{10,13}", text):
        return format_time(int(text))
    return text


def cut_hook(text: str, limit: int = 28) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    for sep in ("。", "！", "?", "？", "；", ";", "，", ",", "\n"):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
            break
    return text[:limit]


def infer_platform(record: Dict[str, Any], default: str) -> str:
    link = first_text(record, LINK_KEYS).lower()
    if "xiaohongshu" in link or "xhs" in link:
        return "小红书"
    if "douyin" in link:
        return "抖音"
    platform = first_text(record, ("platform", "source_platform"))
    if platform:
        return platform
    return default


def explode_judgment(title: str, hook: str, like_count: int, favorite_count: int, comment_count: int, share_count: int) -> str:
    text = f"{title} {hook}"
    mother_signals = ["妈妈", "母亲", "母爱", "给妈妈", "照顾妈妈", "妈妈打钱", "给妈", "妈"]
    signal_hit = any(signal in text for signal in mother_signals)
    if like_count >= 10000 or (like_count >= 5000 and comment_count + share_count + favorite_count >= 1000):
        return "高爆｜强互动"
    if like_count >= 5000 and signal_hit:
        return "入选｜母题强共鸣"
    if like_count >= 5000:
        return "入选｜可对标"
    return "待审"


def normalize_record(record: Dict[str, Any], default_platform: str) -> Dict[str, str]:
    title = first_text(record, TITLE_KEYS)
    desc = first_text(record, ("desc", "content", "text"))
    link = first_text(record, LINK_KEYS)
    account = first_text(record, ACCOUNT_KEYS)
    platform = infer_platform(record, default_platform)
    publish_time = format_time(first_text(record, TIME_KEYS) or record.get("create_time"))
    like_count = parse_int(first_text(record, LIKE_KEYS))
    favorite_count = parse_int(first_text(record, FAVORITE_KEYS))
    comment_count = parse_int(first_text(record, COMMENT_KEYS))
    share_count = parse_int(first_text(record, SHARE_KEYS))
    source_text = title or desc
    hook = cut_hook(source_text)
    judgment = explode_judgment(title, hook, like_count, favorite_count, comment_count, share_count)

    if not title and desc:
        title = cut_hook(desc, 48)

    return {
        "标题": title,
        "链接": link,
        "平台": platform,
        "对标账号": account,
        "发布时间": publish_time,
        "点赞": str(like_count),
        "收藏": str(favorite_count),
        "评论": str(comment_count),
        "分享": str(share_count),
        "开头钩子": hook,
        "爆点判断": judgment,
    }


def dedupe_rows(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    result: List[Dict[str, str]] = []
    for row in rows:
        key = row["链接"] or f'{row["标题"]}|{row["对标账号"]}|{row["发布时间"]}'
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--platform", default="抖音")
    parser.add_argument("--min-likes", type=int, default=5000)
    args = parser.parse_args()

    records: List[Dict[str, Any]] = []
    for item in args.input:
        records.extend(load_records(Path(item)))

    rows = []
    for record in records:
        row = normalize_record(record, args.platform)
        if parse_int(row["点赞"]) >= args.min_likes:
            rows.append(row)

    rows = dedupe_rows(rows)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
