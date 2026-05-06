import logging
from datetime import date
from typing import List, Dict, Optional

import anthropic

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是一位专业的 AI 行业分析师，负责每日整理和总结人工智能领域的最新动态，面向国内科技从业者和关注者。

输出要求：
1. 从所有新闻中挑选最具价值的内容（最多 15 条）
2. 按主题分类，例如：大模型动态、产品发布、研究进展、行业应用、政策监管、融资并购等
3. 每条新闻 1-2 句话说明核心内容，语言简洁专业
4. 如有英文新闻，翻译成中文后再输出
5. 整体格式用 Markdown，层次清晰，便于快速浏览\
"""

_USER_TEMPLATE = """\
请根据以下新闻列表，生成 {date} 的 AI 行业日报。

{news_block}

---
输出格式（严格遵守）：

# 🤖 AI 行业日报 · {date}

## 📌 今日要点
（列出 3-5 条最重要的新闻，每条一句话）

## 📰 详细速览

### [分类1]
- **[新闻标题]** — 核心内容概述。

### [分类2]
...

## 💡 今日总结
（1-2 句话，概括今日 AI 行业整体动态及趋势）\
"""


def generate_digest(news_items: List[Dict], api_key: Optional[str] = None) -> str:
    """Call Claude to produce a Chinese daily digest from raw news items."""
    if not news_items:
        today = date.today().strftime("%Y年%m月%d日")
        return f"# 🤖 AI 行业日报 · {today}\n\n今日暂无 AI 相关新闻。"

    client = anthropic.Anthropic(api_key=api_key)
    today_str = date.today().strftime("%Y年%m月%d日")

    # Build compact news block for the prompt
    lines = []
    for i, item in enumerate(news_items, 1):
        lines.append(f"{i}. [{item['source']}] {item['title']}")
        if item.get("summary"):
            lines.append(f"   {item['summary'][:300]}")
        if item.get("url"):
            lines.append(f"   {item['url']}")
        lines.append("")
    news_block = "\n".join(lines)

    prompt = _USER_TEMPLATE.format(date=today_str, news_block=news_block)

    logger.info("Calling Claude API to generate digest ...")
    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},  # enable prompt caching
            }
        ],
        messages=[{"role": "user", "content": prompt}],
    )

    digest = response.content[0].text
    logger.info(
        f"Digest generated. Input tokens: {response.usage.input_tokens}, "
        f"Output tokens: {response.usage.output_tokens}"
    )
    return digest
