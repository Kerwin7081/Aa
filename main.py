#!/usr/bin/env python3
"""AI 行业新闻日报 — 入口脚本

用法:
  python main.py                  # 正常运行，抓取并推送
  python main.py --dry-run        # 仅生成日报，不推送
  python main.py --config <path>  # 指定配置文件路径
"""

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")

# Make sure src/ is importable when running from project root
sys.path.insert(0, str(Path(__file__).parent))

from src.fetcher import fetch_all
from src.summarizer import generate_digest
from src.publisher import publish_all


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AI 行业新闻日报生成器")
    p.add_argument("--config", default="config/sources.yaml", help="新闻源配置文件路径")
    p.add_argument("--dry-run", action="store_true", help="仅生成日报，不推送到任何渠道")
    p.add_argument("--output-dir", default="digests", help="日报 Markdown 文件保存目录")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("环境变量 ANTHROPIC_API_KEY 未设置，请先配置后再运行。")
        sys.exit(1)

    # ── Step 1: 抓取新闻 ──────────────────────────────────────────────────
    logger.info("Step 1/3  抓取新闻 RSS ...")
    news_items = fetch_all(args.config)
    logger.info(f"共获取 {len(news_items)} 条不重复新闻")

    # ── Step 2: 生成日报 ──────────────────────────────────────────────────
    logger.info("Step 2/3  调用 Claude API 生成日报 ...")
    digest = generate_digest(news_items, api_key=api_key)

    # 保存到本地文件
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{date.today().isoformat()}.md"
    output_file.write_text(digest, encoding="utf-8")
    logger.info(f"日报已保存至 {output_file}")

    # 打印到控制台
    print("\n" + "=" * 70)
    print(digest)
    print("=" * 70 + "\n")

    # ── Step 3: 推送 ──────────────────────────────────────────────────────
    if args.dry_run:
        logger.info("Step 3/3  --dry-run 模式，跳过推送")
    else:
        logger.info("Step 3/3  推送日报到配置的渠道 ...")
        publish_all(digest)

    logger.info("完成！")


if __name__ == "__main__":
    main()
