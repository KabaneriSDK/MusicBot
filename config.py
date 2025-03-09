import os
import platform
import discord
import asyncio

# Discord Token – заменить на актуальный!
TOKEN: str = "YOUR_DISCORD_BOT_TOKEN"

# Глобальные константы и настройки
FFMPEG_BINARY: str = "ffmpeg"
CURRENT_VERSION: str = "dev.ver"
CACHE_DIR: str = "music_cache"
MAX_CACHE_SIZE: int = 1024 * 1024 * 1024  # 1 ГБ

# Настройка FFmpeg
SAMPLE_RATE = 48000
CHANNELS = 2
filter_chain_parts = [
    f"[0:a]aformat=sample_fmts=fltp:sample_rates={SAMPLE_RATE}:channel_layouts=stereo",
    "loudnorm=I=-16:TP=-1.5:LRA=11",
    "bass=g=3",
    "dynaudnorm=f=150:g=15",
    "aresample=async=1"
]
filter_chain = ", ".join(filter_chain_parts)
ffmpeg_args = [
    "-vn",
    f'-filter_complex "{filter_chain}"',
    "-reconnect 1",
    "-reconnect_streamed 1",
    "-reconnect_at_eof 1",
    "-reconnect_delay_max 2",
    "-err_detect ignore_err"
]
ffmpeg_opts_no_fade: str = " ".join(ffmpeg_args)
ffmpeg_options: dict = {'options': '-vn'}

# Intents для Discord
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

# Кэш существует
os.makedirs(CACHE_DIR, exist_ok=True)

# Для Windows используем корректную политику событий asyncio
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
