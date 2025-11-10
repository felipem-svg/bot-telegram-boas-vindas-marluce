from urllib.parse import quote

def deep_link(bot_username: str, start_param: str) -> str:
    return f"https://t.me/{bot_username}?start={quote(start_param)}"
