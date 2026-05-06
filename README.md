# AI 行业新闻日报

每天自动抓取 AI 行业最新资讯，通过 Claude AI 生成中文日报，并推送到你指定的渠道。

## 功能

- **多源聚合**：TechCrunch、VentureBeat、MIT Technology Review、The Verge、机器之心、量子位等 9 个 RSS 源
- **AI 摘要**：使用 Claude Opus 自动整理、分类、翻译，生成结构化中文日报
- **多渠道推送**：企业微信 · 钉钉 · 飞书 · Telegram · 邮件（按需配置）
- **定时运行**：GitHub Actions 每天北京时间 09:00 自动执行
- **日报存档**：每期日报以 Markdown 文件保存在 `digests/` 目录

## 快速开始

### 1. Fork 本仓库

### 2. 配置 Secrets

在仓库 **Settings → Secrets and variables → Actions** 中添加：

| Secret | 说明 | 必填 |
|--------|------|------|
| `ANTHROPIC_API_KEY` | Anthropic API Key | ✅ |
| `WECOM_WEBHOOK_URL` | 企业微信机器人 Webhook | 至少配置一个推送渠道 |
| `DINGTALK_WEBHOOK_URL` | 钉钉机器人 Webhook | |
| `DINGTALK_SECRET` | 钉钉机器人加签密钥（可选） | |
| `FEISHU_WEBHOOK_URL` | 飞书机器人 Webhook | |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | |
| `TELEGRAM_CHAT_ID` | Telegram 目标 Chat ID | |
| `EMAIL_SMTP_HOST` | SMTP 服务器地址 | |
| `EMAIL_SMTP_PORT` | SMTP 端口（默认 465） | |
| `EMAIL_USERNAME` | SMTP 邮箱账号 | |
| `EMAIL_PASSWORD` | SMTP 邮箱密码/授权码 | |
| `EMAIL_TO` | 收件人邮箱（多个用逗号分隔） | |

### 3. 手动触发测试

进入 **Actions → AI 行业日报 → Run workflow**，可选 `dry_run=true` 仅生成日报不推送。

## 自定义新闻源

编辑 `config/sources.yaml`：

```yaml
sources:
  - name: "你的来源名"
    url: "RSS Feed URL"
    language: "zh"   # zh 或 en

settings:
  hours_lookback: 24        # 抓取过去多少小时的新闻
  max_items_per_source: 10  # 每个来源最多抓取条数
```

## 本地运行

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
# 可选：设置推送渠道
export WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx

python main.py           # 正常运行
python main.py --dry-run # 仅生成，不推送
```

## 项目结构

```
.
├── main.py                        # 入口脚本
├── requirements.txt
├── config/
│   └── sources.yaml               # 新闻源配置
├── src/
│   ├── fetcher.py                 # RSS 抓取与去重
│   ├── summarizer.py              # Claude API 摘要
│   └── publisher.py               # 多渠道推送
├── digests/                       # 历史日报存档
└── .github/workflows/
    └── daily_digest.yml           # GitHub Actions 定时任务
```
