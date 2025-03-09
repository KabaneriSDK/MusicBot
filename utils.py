from datetime import datetime, timezone
from urllib.parse import urlparse
import discord
from config import CURRENT_VERSION

def create_embed(title: str, description: str, color: discord.Color = discord.Color.blurple(),
                 thumbnail: str = None, title_url: str = None) -> discord.Embed:
    embed = discord.Embed(title=f"🎶 {title}", description=description, color=color, url=title_url)
    embed.set_author(name="Tusk Town Bot",
                     icon_url=" ЗАМЕНИТЕ НА СВОЮ АВАТАРКУ "https://cdn.discordapp.com/avatars/"")
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    footer_text = "✨ Music Bot © 2025 • Проверьте установку FFmpeg при ошибках"
    embed.set_footer(text=footer_text,
                     icon_url="ЗАМЕНИТЕ НА СВОЮ АВАТАРКУ "https://cdn.discordapp.com/avatars/")
    embed.timestamp = datetime.now(timezone.utc)
    return embed

def is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.scheme and parsed.netloc)

def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    minutes = seconds // 60
    seconds = seconds % 60
    hours = minutes // 60
    minutes = minutes % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

def create_progress_bar(progress: float, total: float, length: int = 20, spinner: str = "🔘") -> str:
    if total <= 0:
        return ""
    percent = progress / total if total else 0
    percent = min(max(percent, 0), 1)
    filled = int(percent * length)
    bar = "▰" * filled + "▱" * (length - filled)
    time_str = f"{format_duration(progress)} / {format_duration(total)}"
    return f"\n{spinner} [{bar}] {int(percent * 100)}% ({time_str})\n"
