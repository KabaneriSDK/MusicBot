import asyncio
import sys
from discord.ext import commands
from config import TOKEN, intents
from music_cog import Music, GLOBAL_DISCORD_LOOP, GLOBAL_MUSIC_COG
from dependencies import ensure_admin, ensure_dependencies

def main():
    ensure_dependencies()
    ensure_admin()
    bot = commands.Bot(command_prefix="!", intents=intents)
    music_cog = Music(bot)
    bot.add_cog(music_cog)
    global GLOBAL_DISCORD_LOOP, GLOBAL_MUSIC_COG
    GLOBAL_DISCORD_LOOP = asyncio.get_event_loop()
    GLOBAL_MUSIC_COG = music_cog
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
