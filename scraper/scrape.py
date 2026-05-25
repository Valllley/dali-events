#!/usr/bin/env python3
"""
大理活动日历 - 数据采集脚本
从多个信息源抓取大理活动信息，用LLM提取结构化数据

使用方法:
  python scrape.py                    # 全量抓取
  python scrape.py --source wechat    # 只抓微信
  python scrape.py --source xiaohongshu  # 只抓小红书
  python scrape.py --dry-run          # 只搜索不提取（省LLM费用）

环境变量:
  OPENAI_API_KEY     - OpenAI API密钥（用于结构化提取）
  SERPAPI_KEY        - SerpAPI密钥（可选，用于搜索引擎）
"""

import json
import os
import sys
import re
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("请安装依赖: pip install requests")
    sys.exit(1)

# --- 配置 ---
DATA_DIR = Path(__file__).parent.parent / "data"
EVENTS_FILE = DATA_DIR / "events.json"

# 搜索关键词
SEARCH_KEYWORDS = [
    "大理活动 本周",
    "大理市集 2026",
    "大理讲座 沙龙",
    "大理音乐现场 演出",
    "大理亲子活动",
    "大理展览 画展",
    "大理民俗 节庆",
    "大理旅居 活动",
    "大理好在 活动",
]

# 已知信源URL
KNOWN_SOURCES = {
    "大理融媒": "https://www.toutiao.com/c/user/token/MS4wLjABAAAA",
    "大理旅游公众号": "微信公众号搜索",
    "大理好在公众号": "微信公众号搜索",
    "大理文旅网": "http://m.daliwenlv.com/",
    "携程大理": "https://m.ctrip.com/webapp/you/community/detail",
}

# LLM提取的Prompt
EXTRACT_PROMPT = """你是一个活动信息提取助手。从以下文本中提取大理的活动信息，输出JSON数组。

提取规则：
1. 只提取"活动"类型的信息，忽略新闻、政策、广告
2. 每个活动必须包含：title, date_start(YYYY-MM-DD), date_end(YYYY-MM-DD), time, location, price, category, description
3. category必须是以下之一：民俗节庆, 市集, 音乐现场, 讲座沙龙, 亲子活动, 展览, 户外, 其他
4. 如果原文没有明确结束日期，date_end = date_start
5. 如果价格免费，price = "免费"
6. 如果有亮点信息，提取到highlights数组
7. 如果有实用提示，提取到tips字段
8. 如果有原文链接，提取到source_url

输出格式（纯JSON，不要markdown代码块）：
[
  {
    "id": "用标题拼音+日期生成简短id",
    "title": "活动标题",
    "date_start": "2026-05-31",
    "date_end": "2026-05-31",
    "time": "14:00-17:00",
    "location": "地点",
    "location_map": "详细地址",
    "price": "免费",
    "category": "讲座沙龙",
    "tags": ["标签1", "标签2"],
    "description": "一句话描述",
    "highlights": ["亮点1", "亮点2"],
    "tips": "实用提示",
    "source_name": "来源名",
    "source_url": "https://..."
  }
]

要提取的文本：
---
{text}
---"""


class DaliEventScraper:
    def __init__(self, api_key: Optional[str] = None, serpapi_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.serpapi_key = serpapi_key or os.getenv("SERPAPI_KEY")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })

    def search_sogou_wechat(self, keyword: str) -> list:
        """通过搜狗微信搜索抓取公众号文章"""
        results = []
        try:
            url = "https://weixin.sogou.com/weixin"
            params = {
                "type": "2",  # 搜索文章
                "query": keyword,
                "s_from": "input",
                "_sug_": "n",
            }
            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                # 提取文章链接和标题
                links = re.findall(r'href="(https?://mp\.weixin\.qq\.com/[^"]+)"', resp.text)
                titles = re.findall(r'<h3[^>]*>.*?<a[^>]*>(.*?)</a>', resp.text, re.DOTALL)
                for link, title in zip(links[:5], titles[:5]):
                    clean_title = re.sub(r'<[^>]+>', '', title).strip()
                    results.append({
                        "title": clean_title,
                        "url": link,
                        "source": "微信公众号"
                    })
        except Exception as e:
            print(f"  搜狗微信搜索失败: {e}")
        return results

    def search_daliwenlv(self) -> list:
        """抓取大理文旅网最新文章"""
        results = []
        try:
            url = "http://m.daliwenlv.com/"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                # 提取文章链接
                links = re.findall(r'href="(/p/\d+\.html)"', resp.text)
                titles = re.findall(r'<a[^>]*href="/p/\d+\.html"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
                for link, title in zip(links[:10], titles[:10]):
                    clean_title = re.sub(r'<[^>]+>', '', title).strip()
                    if clean_title and ('活动' in clean_title or '讲座' in clean_title or '节' in clean_title):
                        results.append({
                            "title": clean_title,
                            "url": f"http://m.daliwenlv.com{link}",
                            "source": "大理文旅网"
                        })
        except Exception as e:
            print(f"  大理文旅网抓取失败: {e}")
        return results

    def fetch_article_content(self, url: str) -> str:
        """抓取文章正文"""
        try:
            resp = self.session.get(url, timeout=15)
            resp.encoding = resp.apparent_encoding
            if resp.status_code == 200:
                # 简单提取正文（去除HTML标签）
                text = re.sub(r'<script[^>]*>.*?</script>', '', resp.text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', '\n', text)
                text = re.sub(r'\n{3,}', '\n\n', text)
                text = re.sub(r'&[a-zA-Z]+;', ' ', text)
                # 截取前3000字（节省LLM token）
                return text.strip()[:3000]
        except Exception as e:
            print(f"  文章抓取失败 {url}: {e}")
        return ""

    def extract_events_with_llm(self, text: str) -> list:
        """用LLM从文本中提取结构化活动数据"""
        if not self.api_key:
            print("  ⚠️ 未设置OPENAI_API_KEY，跳过LLM提取")
            return []

        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)

            prompt = EXTRACT_PROMPT.format(text=text)

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "你是一个精确的活动信息提取助手，只输出JSON。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000,
            )

            content = response.choices[0].message.content.strip()
            # 去掉可能的markdown代码块
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

            events = json.loads(content)
            if isinstance(events, dict):
                events = [events]
            return events

        except Exception as e:
            print(f"  LLM提取失败: {e}")
            return []

    def deduplicate_events(self, new_events: list, existing_events: list) -> list:
        """去重：基于标题+日期生成指纹"""
        existing_ids = {e.get("id") for e in existing_events}
        existing_fingerprints = set()

        for e in existing_events:
            fp = hashlib.md5(
                f"{e.get('title','')}{e.get('date_start','')}{e.get('location','')}".encode()
            ).hexdigest()[:12]
            existing_fingerprints.add(fp)

        deduped = []
        for e in new_events:
            # 先检查id
            if e.get("id") and e["id"] in existing_ids:
                continue
            # 再检查指纹
            fp = hashlib.md5(
                f"{e.get('title','')}{e.get('date_start','')}{e.get('location','')}".encode()
            ).hexdigest()[:12]
            if fp in existing_fingerprints:
                continue
            # 自动生成id
            if not e.get("id"):
                e["id"] = f"auto-{fp}"
            deduped.append(e)

        return deduped

    def filter_future_events(self, events: list) -> list:
        """过滤掉已过期的事件"""
        today = datetime.now().strftime("%Y-%m-%d")
        # 保留今天及未来的，以及跨度包含今天的
        return [e for e in events if e.get("date_end", e.get("date_start", "")) >= today
                or e.get("date_start", "") >= today]

    def load_existing_events(self) -> list:
        """加载已有事件数据"""
        if EVENTS_FILE.exists():
            with open(EVENTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("events", [])
        return []

    def save_events(self, events: list):
        """保存事件数据"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "last_updated": datetime.now().isoformat(),
            "update_source": f"自动采集 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "events": events
        }
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ 已保存 {len(events)} 个活动到 {EVENTS_FILE}")

    def run(self, source: str = "all", dry_run: bool = False):
        """执行完整的采集流程"""
        print("🦋 大理活动日历 - 数据采集")
        print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"   模式: {'dry-run' if dry_run else 'full'}")
        print()

        # 加载已有数据
        existing = self.load_existing_events()
        print(f"📂 已有 {len(existing)} 个活动\n")

        # 收集文章
        articles = []

        if source in ("all", "wechat"):
            print("🔍 搜索微信公众号...")
            for kw in ["大理活动", "大理市集", "大理节庆"]:
                results = self.search_sogou_wechat(kw)
                articles.extend(results)
                print(f"   找到 {len(results)} 篇文章")

        if source in ("all", "web"):
            print("🔍 搜索大理文旅网...")
            results = self.search_daliwenlv()
            articles.extend(results)
            print(f"   找到 {len(results)} 篇文章")

        if not articles:
            print("⚠️ 未找到新文章")
            return

        # 去重文章
        seen_urls = set()
        unique_articles = []
        for a in articles:
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                unique_articles.append(a)
        articles = unique_articles
        print(f"\n📰 共 {len(articles)} 篇待处理文章\n")

        if dry_run:
            for a in articles:
                print(f"   - [{a['source']}] {a['title']}")
                print(f"     {a['url']}")
            print("\n(dry-run模式，跳过内容提取)")
            return

        # 抓取内容 & 提取活动
        all_new_events = []
        for i, article in enumerate(articles):
            print(f"📝 [{i+1}/{len(articles)}] {article['title'][:40]}...")
            content = self.fetch_article_content(article["url"])
            if not content:
                print("   ⚠️ 内容为空，跳过")
                continue

            events = self.extract_events_with_llm(content)
            # 标记来源
            for e in events:
                if not e.get("source_name"):
                    e["source_name"] = article.get("source", "未知")
                if not e.get("source_url"):
                    e["source_url"] = article["url"]

            all_new_events.extend(events)
            print(f"   ✅ 提取到 {len(events)} 个活动")

        # 去重 & 过滤
        deduped = self.deduplicate_events(all_new_events, existing)
        future = self.filter_future_events(deduped)

        print(f"\n📊 采集结果:")
        print(f"   新提取: {len(all_new_events)} 个")
        print(f"   去重后: {len(deduped)} 个")
        print(f"   未过期: {len(future)} 个")

        if future:
            # 合并并保存
            merged = existing + future
            self.save_events(merged)
        else:
            print("   没有新的未过期活动")

        # 即使没有新活动，也更新时间戳
        self.save_events(self.filter_future_events(existing + all_new_events) or existing)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="大理活动日历数据采集")
    parser.add_argument("--source", choices=["all", "wechat", "xiaohongshu", "web"],
                       default="all", help="数据源选择")
    parser.add_argument("--dry-run", action="store_true", help="只搜索不提取")
    args = parser.parse_args()

    scraper = DaliEventScraper()
    scraper.run(source=args.source, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
