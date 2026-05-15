import logging
from datetime import date
from typing import List, Dict, Optional

import anthropic

logger = logging.getLogger(__name__)

# Max news items sent to Claude (prevents prompt overflow)
_MAX_INPUT_ITEMS = 60

_SYSTEM_PROMPT = """\
你是一位专业的 AI 行业分析师，负责每日整理和总结人工智能领域的最新动态，读者为国内科技从业者。

输出规范：
1. 从所有原始条目中挑选最具价值的内容（最多 15 条，优先选实际产品/研究/政策新闻，arXiv 论文次之）
2. 按主题分类：大模型动态 / 产品发布 / 研究进展 / 行业应用 / 政策监管 / 融资并购 / 其他
3. 每条新闻用 1-2 句话概括核心内容；英文新闻翻译成中文
4. 格式使用 Markdown，层次清晰，适合在 IM / 邮件中阅读
5. 不要编造或推断原文中没有的信息\
"""

_USER_TEMPLATE = """\
请根据以下新闻列表，生成 {date} 的 AI 行业日报。

{news_block}

---
严格按照以下格式输出，不要添加额外内容：

# 🤖 AI 行业日报 · {date}

## 📌 今日要点
（3-5 条最重要新闻，每条一句话）

## 📰 详细速览

### [分类名]
- **标题** — 核心内容概述（来源：XXX）

（重复以上 ### 块，按分类展开）

## 💡 今日总结
（1-2 句话，概括今日 AI 行业整体动态）\
"""


def _build_news_block(news_items: List[Dict]) -> str:
    lines = []
    for i, item in enumerate(news_items[:_MAX_INPUT_ITEMS], 1):
        lines.append(f"{i}. [{item['source']}] {item['title']}")
        if item.get("summary"):
            lines.append(f"   {item['summary'][:300]}")
        if item.get("url"):
            lines.append(f"   {item['url']}")
        lines.append("")
    return "\n".join(lines)


def generate_digest(news_items: List[Dict], api_key: Optional[str] = None) -> str:
    """Call Claude to produce a Chinese AI industry daily digest."""
    today_str = date.today().strftime("%Y年%m月%d日")

    if not news_items:
        return f"# 🤖 AI 行业日报 · {today_str}\n\n今日暂无 AI 相关新闻。"

    client = anthropic.Anthropic(api_key=api_key)
    news_block = _build_news_block(news_items)
    prompt = _USER_TEMPLATE.format(date=today_str, news_block=news_block)

    logger.info(f"Calling Claude API with {min(len(news_items), _MAX_INPUT_ITEMS)} items ...")
    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": prompt}],
    )

    digest = response.content[0].text
    usage = response.usage
    logger.info(
        f"Digest generated. input={usage.input_tokens} "
        f"(cache_read={getattr(usage, 'cache_read_input_tokens', 0)}) "
        f"output={usage.output_tokens}"
    )
    return digest
