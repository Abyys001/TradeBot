import logging

import requests

logger = logging.getLogger(__name__)
TELEGRAM_API_BASE = "https://api.telegram.org/bot"


def send_message(
    bot_token: str, chat_id: int, text: str, parse_mode: str = "HTML"
) -> bool:
    url = f"{TELEGRAM_API_BASE}{bot_token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("telegram send_message not ok: %s", data)
            return False
        return True
    except requests.RequestException as e:
        logger.warning("telegram send_message failed: %s", e)
        return False


def build_trade_alert(
    strategy_name: str,
    symbol: str,
    action: str,
    price: str = "",
    leverage: str = "",
    qty: str = "",
    pnl: str = "",
    time_str: str = "",
    exit_reason: str = "",
    position_side: str = "",
) -> str:
    lines = [
        "<b>🔴 LIVE EXECUTION</b>",
        f"🤖 Strategy: {strategy_name}",
        f"📊 Asset: {symbol}",
        f"🛒 Action: {action}",
    ]
    if position_side:
        lines.append(f"📐 Side: {position_side}")
    if price:
        lines.append(f"💰 {price}")
    if leverage:
        lines.append(f"⚖️ {leverage}")
    if qty:
        lines.append(f"📦 Size: {qty}")
    if pnl:
        emoji = "🟢" if pnl.startswith("+") else "🔴"
        lines.append(f"{emoji} PnL: {pnl}")
    if exit_reason:
        lines.append(f"🏁 Exit reason: {exit_reason}")
    if time_str:
        lines.append(f"⏱️ Time: {time_str} UTC")
    return "\n".join(lines)
