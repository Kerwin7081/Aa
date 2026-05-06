"""Push the daily digest to configured notification channels.

Supported channels (configured via environment variables):
  - 企业微信 (WeCom)  : WECOM_WEBHOOK_URL
  - 钉钉 (DingTalk)   : DINGTALK_WEBHOOK_URL  [+ DINGTALK_SECRET for signing]
  - 飞书 (Feishu)     : FEISHU_WEBHOOK_URL
  - Telegram          : TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  - Email (SMTP)      : EMAIL_SMTP_HOST + EMAIL_SMTP_PORT + EMAIL_USERNAME
                        + EMAIL_PASSWORD + EMAIL_TO
"""

import base64
import hashlib
import hmac
import logging
import os
import smtplib
import time
import urllib.parse
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# WeCom markdown limit
_WECOM_MAX = 4096
# DingTalk markdown limit
_DINGTALK_MAX = 20000
# Telegram message limit
_TELEGRAM_MAX = 4096


def _post(url: str, payload: dict, timeout: int = 10) -> dict:
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# 企业微信 (WeCom / WeChat Work)
# ---------------------------------------------------------------------------

def publish_wecom(content: str, webhook_url: str) -> bool:
    try:
        result = _post(webhook_url, {
            "msgtype": "markdown",
            "markdown": {"content": content[:_WECOM_MAX]},
        })
        if result.get("errcode") == 0:
            logger.info("[WeCom] pushed successfully")
            return True
        logger.error(f"[WeCom] push failed: {result}")
        return False
    except Exception as e:
        logger.error(f"[WeCom] error: {e}")
        return False


# ---------------------------------------------------------------------------
# 钉钉 (DingTalk)
# ---------------------------------------------------------------------------

def _dingtalk_sign(secret: str) -> tuple[str, str]:
    timestamp = str(round(time.time() * 1000))
    msg = f"{timestamp}\n{secret}"
    sig = base64.b64encode(
        hmac.new(secret.encode(), msg.encode(), digestmod=hashlib.sha256).digest()
    ).decode()
    return timestamp, urllib.parse.quote_plus(sig)


def publish_dingtalk(content: str, webhook_url: str, secret: Optional[str] = None) -> bool:
    url = webhook_url
    if secret:
        ts, sign = _dingtalk_sign(secret)
        url = f"{webhook_url}&timestamp={ts}&sign={sign}"
    try:
        result = _post(url, {
            "msgtype": "markdown",
            "markdown": {"title": "AI 行业日报", "text": content[:_DINGTALK_MAX]},
        })
        if result.get("errcode") == 0:
            logger.info("[DingTalk] pushed successfully")
            return True
        logger.error(f"[DingTalk] push failed: {result}")
        return False
    except Exception as e:
        logger.error(f"[DingTalk] error: {e}")
        return False


# ---------------------------------------------------------------------------
# 飞书 (Feishu / Lark)
# ---------------------------------------------------------------------------

def publish_feishu(content: str, webhook_url: str) -> bool:
    try:
        result = _post(webhook_url, {
            "msg_type": "text",
            "content": {"text": content},
        })
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            logger.info("[Feishu] pushed successfully")
            return True
        logger.error(f"[Feishu] push failed: {result}")
        return False
    except Exception as e:
        logger.error(f"[Feishu] error: {e}")
        return False


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def publish_telegram(content: str, bot_token: str, chat_id: str) -> bool:
    api = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = [content[i:i + _TELEGRAM_MAX] for i in range(0, len(content), _TELEGRAM_MAX)]
    ok = True
    for chunk in chunks:
        try:
            result = _post(api, {"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"})
            if not result.get("ok"):
                # Retry without parse_mode (some markdown may be invalid)
                result = _post(api, {"chat_id": chat_id, "text": chunk})
                if not result.get("ok"):
                    logger.error(f"[Telegram] push failed: {result}")
                    ok = False
        except Exception as e:
            logger.error(f"[Telegram] error: {e}")
            ok = False
    if ok:
        logger.info("[Telegram] pushed successfully")
    return ok


# ---------------------------------------------------------------------------
# Email (SMTP)
# ---------------------------------------------------------------------------

def publish_email(
    content: str,
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    to_addrs: str,
    use_ssl: bool = True,
) -> bool:
    subject = f"AI 行业日报 · {date.today().strftime('%Y-%m-%d')}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = username
    msg["To"] = to_addrs

    msg.attach(MIMEText(content, "plain", "utf-8"))
    # Simple HTML wrapper
    html = "<html><body><pre style='font-family:sans-serif;white-space:pre-wrap'>" + content + "</pre></body></html>"
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if use_ssl:
            srv = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            srv = smtplib.SMTP(smtp_host, smtp_port)
            srv.starttls()
        srv.login(username, password)
        srv.sendmail(username, [a.strip() for a in to_addrs.split(",")], msg.as_string())
        srv.quit()
        logger.info("[Email] sent successfully")
        return True
    except Exception as e:
        logger.error(f"[Email] error: {e}")
        return False


# ---------------------------------------------------------------------------
# Dispatch to all configured channels
# ---------------------------------------------------------------------------

def publish_all(content: str) -> None:
    dispatched = False

    if url := os.environ.get("WECOM_WEBHOOK_URL"):
        publish_wecom(content, url)
        dispatched = True

    if url := os.environ.get("DINGTALK_WEBHOOK_URL"):
        publish_dingtalk(content, url, os.environ.get("DINGTALK_SECRET"))
        dispatched = True

    if url := os.environ.get("FEISHU_WEBHOOK_URL"):
        publish_feishu(content, url)
        dispatched = True

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        publish_telegram(content, token, chat_id)
        dispatched = True

    smtp_host = os.environ.get("EMAIL_SMTP_HOST")
    email_to = os.environ.get("EMAIL_TO")
    if smtp_host and email_to:
        publish_email(
            content,
            smtp_host=smtp_host,
            smtp_port=int(os.environ.get("EMAIL_SMTP_PORT", "465")),
            username=os.environ.get("EMAIL_USERNAME", ""),
            password=os.environ.get("EMAIL_PASSWORD", ""),
            to_addrs=email_to,
        )
        dispatched = True

    if not dispatched:
        logger.warning(
            "No push channel configured. Set at least one of: "
            "WECOM_WEBHOOK_URL / DINGTALK_WEBHOOK_URL / FEISHU_WEBHOOK_URL / "
            "TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID / EMAIL_SMTP_HOST+EMAIL_TO"
        )
