import asyncio
import time
import random
import subprocess
import discord
from discord.ext import commands
from typing import Optional, Dict, Any, List
from utils import create_embed, is_valid_url, format_duration, create_progress_bar
from downloader import PartialYTDLSource, find_alternative_tracks, TrackDownloadError
from music_queue import MusicQueue, track_state, CacheCleaner
from config import CACHE_DIR, MAX_CACHE_SIZE, FFMPEG_BINARY, ffmpeg_opts_no_fade, ytdl_format_options
from logging_config import logger

# Глобальные переменные для использования в асинхронных вызовах (будут установлены в main.py)
GLOBAL_DISCORD_LOOP = None
GLOBAL_MUSIC_COG = None

async def ensure_voice_client(ctx: commands.Context, retries: int = 5) -> Optional[discord.VoiceClient]:
    if not ctx.author.voice:
        await ctx.send(embed=create_embed("❌ Ошибка", "*Вы не в голосовом канале!*", discord.Color.red()))
        return None
    channel = ctx.author.voice.channel
    vc = ctx.voice_client
    for attempt in range(retries):
        try:
            if vc:
                if vc.channel.id != channel.id:
                    await vc.move_to(channel)
                if not vc.is_connected():
                    await asyncio.sleep(1)
                return vc
            else:
                vc = await channel.connect(timeout=60)
                await asyncio.sleep(1)
                return vc
        except Exception as e:
            logger.error("Ошибка подключения", extra={"attempt": attempt + 1, "error": str(e)})
            await asyncio.sleep(2 ** (attempt + 1))
    await ctx.send(embed=create_embed("❌ Ошибка", "*Не удалось подключиться к каналу.*", discord.Color.red()))
    return None

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.queues: Dict[int, MusicQueue] = {}
        self.current_track: Dict[int, Optional[PartialYTDLSource]] = {}
        self.track_start_time: Dict[int, float] = {}
        self.control_messages: Dict[int, discord.Message] = {}
        self.previous_tracks: Dict[int, List[PartialYTDLSource]] = {}
        self.cache_cleaner: CacheCleaner = CacheCleaner(CACHE_DIR, MAX_CACHE_SIZE)
        self.play_next_lock = asyncio.Lock()

    async def cog_load(self) -> None:
        self.auto_disconnect_task = asyncio.create_task(self._auto_disconnect_loop())
        self.progress_update_task = asyncio.create_task(self._progress_update_loop())
        self.cleanup_cache_task = asyncio.create_task(self._cleanup_cache_loop())

    async def _auto_disconnect_loop(self) -> None:
        try:
            while not self.bot.is_closed():
                for guild in self.bot.guilds:
                    vc = guild.voice_client
                    if vc and vc.channel:
                        non_bot = [m for m in vc.channel.members if not m.bot]
                        if not non_bot:
                            await vc.disconnect()
                            self.queues.pop(guild.id, None)
                            logger.info("Автоотключение", extra={"guild": guild.name})
                            text_channels = [ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages]
                            if text_channels:
                                await text_channels[0].send(embed=create_embed(
                                    "🔇 Автоотключение",
                                    f"*Отключаюсь из {vc.channel.mention} из-за отсутствия пользователей.*",
                                    discord.Color.red()))
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("Задача автоотключения завершена")
        except Exception as e:
            logger.error("Ошибка в автоотключении", extra={"error": str(e)})

    async def _progress_update_loop(self) -> None:
        try:
            spinner_frames = ["◐", "◓", "◑", "◒"]
            while not self.bot.is_closed():
                for guild in self.bot.guilds:
                    vc = guild.voice_client
                    if not vc or not vc.is_playing():
                        continue
                    track = self.current_track.get(guild.id)
                    if not track:
                        continue
                    duration = track.data.get("duration") or 0
                    elapsed = time.time() - self.track_start_time.get(guild.id, time.time())
                    if duration and elapsed > duration:
                        elapsed = duration
                    spinner = spinner_frames[int(time.time()) % len(spinner_frames)]
                    progress_bar = create_progress_bar(elapsed, duration, spinner=spinner)
                    await track_state.update(track.title, duration, elapsed, self.track_start_time.get(guild.id, time.time()))
                    if guild.id in self.control_messages:
                        try:
                            embed_msg = self.control_messages[guild.id]
                            embed = embed_msg.embeds[0]
                            embed.title = f"▶ Сейчас играет: **[{track.title}]({track.data.get('url', '')})**"
                            embed.description = f"**Длительность:** {format_duration(duration)}"
                            embed.clear_fields()
                            embed.add_field(name="Прогресс", value=progress_bar, inline=True)
                            await embed_msg.edit(embed=embed)
                        except Exception as e:
                            logger.error("Ошибка обновления прогресса", extra={"error": str(e)})
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            logger.info("Задача обновления прогресса завершена")
        except Exception as e:
            logger.error("Ошибка в цикле обновления прогресса", extra={"error": str(e)})

    async def _cleanup_cache_loop(self) -> None:
        try:
            while not self.bot.is_closed():
                await self.cache_cleaner.cleanup()
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("Задача очистки кэша завершена")
        except Exception as e:
            logger.error("Ошибка в цикле очистки кэша", extra={"error": str(e)})

    async def play_next(self, ctx: commands.Context) -> None:
        async with self.play_next_lock:
            vc = ctx.voice_client
            if not vc or not vc.is_connected():
                logger.debug("Голосовое соединение отсутствует – пытаемся переподключиться.")
                vc = await ensure_voice_client(ctx)
                if not vc:
                    await ctx.send(embed=create_embed("❌ Ошибка", "*Не удалось подключиться к голосовому каналу.*", discord.Color.red()))
                    return
            guild_id = ctx.guild.id
            queue_obj = self.queues.get(guild_id)
            if not queue_obj:
                self.current_track.pop(guild_id, None)
                return
            track = await queue_obj.get_next_track()
            if not track:
                return
            self.previous_tracks.setdefault(guild_id, [])
            if guild_id in self.current_track and self.current_track[guild_id] is not None:
                prev = self.current_track[guild_id]
                self.previous_tracks[guild_id].append(prev)
                if len(self.previous_tracks[guild_id]) > 50:
                    self.previous_tracks[guild_id].pop(0)
            self.current_track[guild_id] = track
            self.track_start_time[guild_id] = time.time()
            await track_state.update(track.title, track.data.get("duration") or 0, 0, self.track_start_time[guild_id])
            def after_playing(error: Optional[Exception]) -> None:
                if error:
                    logger.error("Ошибка воспроизведения", extra={"error": str(error)})
                try:
                    track.cleanup_file()
                except Exception as e:
                    logger.error("Ошибка очистки файла", extra={"file": track.file_path, "error": str(e)})
                if ctx.voice_client and ctx.voice_client.is_connected() and GLOBAL_DISCORD_LOOP:
                    asyncio.run_coroutine_threadsafe(self.play_next(ctx), GLOBAL_DISCORD_LOOP)
                else:
                    logger.warning("Голосовое соединение отсутствует, пытаюсь переподключиться...")
                    try:
                        fut = asyncio.run_coroutine_threadsafe(ensure_voice_client(ctx), GLOBAL_DISCORD_LOOP)
                        new_vc = fut.result(timeout=10)
                        if new_vc and new_vc.is_connected():
                            logger.info("Голосовое соединение восстановлено")
                            asyncio.run_coroutine_threadsafe(self.play_next(ctx), GLOBAL_DISCORD_LOOP)
                        else:
                            logger.error("Не удалось переподключиться к голосовому каналу")
                    except Exception as e:
                        logger.exception("Ошибка при переподключении", extra={"error": str(e)})
            try:
                vc.play(track, after=after_playing)
            except Exception as e:
                logger.error("Ошибка запуска трека", extra={"error": str(e)})
                asyncio.create_task(ctx.send(embed=create_embed("❌ Ошибка", "*Не удалось запустить трек. Проверьте установку FFmpeg.*", discord.Color.red())))
                return
            duration = track.data.get("duration") or 0
            emb = create_embed("▶ Сейчас играет", f"**[{track.title}]({track.data.get('url', '')})**", discord.Color.blurple(), thumbnail=track.thumbnail, title_url=track.data.get("url"))
            emb.add_field(name="Длительность", value=format_duration(duration), inline=True)
            emb.add_field(name="Прогресс", value=create_progress_bar(0, duration), inline=True)
            msg = await ctx.send(embed=emb, view=ControlView(self, ctx))
            self.control_messages[guild_id] = msg

    @commands.command(name="list")
    async def list_tracks(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id
        msg = ""
        num = 1
        if guild_id in self.current_track and self.current_track[guild_id] is not None:
            msg += f"**Сейчас играет:** _{self.current_track[guild_id].title}_\n\n"
        queue_obj = self.queues.get(guild_id)
        if queue_obj:
            items = list(queue_obj.queue._queue)
            if items:
                msg += "**Очередь:**\n"
                for track in items:
                    msg += f"{num}. {track.title}\n"
                    num += 1
        if not msg:
            msg = "Очередь пуста."
        await ctx.send(embed=create_embed("Очередь треков", msg, discord.Color.blue()))

    @commands.command(name="leave")
    async def leave(self, ctx: commands.Context) -> None:
        vc = ctx.voice_client
        if vc:
            await vc.disconnect()
            self.queues.pop(ctx.guild.id, None)
            await ctx.send(embed=create_embed("Отключение", "*Отключился от канала.*", discord.Color.red()))
        else:
            await ctx.send(embed=create_embed("❌ Ошибка", "*Я не в голосовом канале.*", discord.Color.red()))

    @commands.command(name="play")
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        vc = await ensure_voice_client(ctx)
        if not vc:
            return
        if not isinstance(query, str) or not query.strip():
            await ctx.send(embed=create_embed("❌ Ошибка", "*Неверный запрос.*", discord.Color.red()))
            return
        if query.startswith("http") and not is_valid_url(query):
            await ctx.send(embed=create_embed("❌ Ошибка", "*Неверный URL.*", discord.Color.red()))
            return
        if "list=" in query:
            await ctx.send(embed=create_embed("Плейлист", "*Начинаю загрузку плейлиста...*", discord.Color.blurple()))
            try:
                info = await asyncio.to_thread(lambda: youtube_dl.YoutubeDL(ytdl_format_options).extract_info(query, download=False))
                if 'entries' not in info:
                    raise Exception("Плейлист не найден.")
                entries = info['entries'][:10]
                async def load_track(entry: Dict[str, Any]) -> Optional[PartialYTDLSource]:
                    url = entry.get("webpage_url")
                    try:
                        return await PartialYTDLSource.create_partial(url)
                    except Exception as e:
                        logger.error("Ошибка загрузки трека", extra={"error": str(e)})
                        return None
                tracks_raw = await asyncio.gather(*(load_track(entry) for entry in entries))
                tracks = [t for t in tracks_raw if t is not None]
                if not tracks:
                    await ctx.send(embed=create_embed("❌ Ошибка", "*Не удалось загрузить треки.*", discord.Color.red()))
                    return
                if ctx.guild.id not in self.queues:
                    self.queues[ctx.guild.id] = MusicQueue()
                await self.queues[ctx.guild.id].add_tracks(tracks)
                await ctx.send(embed=create_embed("✅ Добавлено", f"*Добавлено {len(tracks)} треков в очередь.*", discord.Color.green()))
                if not vc.is_playing():
                    await self.play_next(ctx)
            except Exception as e:
                logger.error("Ошибка плейлиста", extra={"error": str(e)})
                await ctx.send(embed=create_embed("❌ Ошибка", f"*{e}*", discord.Color.red()))
            return
        if not query.startswith("http"):
            search_query = f"ytsearch5:{query}"
            await ctx.send(embed=create_embed("Поиск", f"*Ищу: **{query}***", discord.Color.blurple()))
            try:
                info = await asyncio.to_thread(lambda: youtube_dl.YoutubeDL(ytdl_format_options).extract_info(search_query, download=False))
                results = info.get("entries", [])
                if not results:
                    raise Exception("Ничего не найдено.")
            except Exception as e:
                logger.error("Ошибка поиска", extra={"error": str(e)})
                await ctx.send(embed=create_embed("❌ Ошибка", f"*{e}*", discord.Color.red()))
                return
            query = results[0]["webpage_url"]
        async with ctx.typing():
            try:
                partial_source = await PartialYTDLSource.create_partial(query)
            except Exception as e:
                err_text = str(e).lower()
                if any(keyword in err_text for keyword in ["block", "geo", "nonetype", "unavailable", "недоступно", "не удалось получить локальный файл"]):
                    await ctx.send(embed=create_embed("Альтернативные варианты", "*Данный трек недоступен в вашем регионе. Ищу альтернативы...*", discord.Color.orange()))
                    alternatives = await find_alternative_tracks(query)
                    if not alternatives:
                        await ctx.send(embed=create_embed("❌ Ошибка", "*Не удалось найти альтернативные варианты.*", discord.Color.red()))
                        return
                    alt_options = ""
                    for i, alt in enumerate(alternatives, start=1):
                        title = alt.get("title", "Неизвестно")
                        alt_options += f"{i}. {title}\n"
                    await ctx.send(embed=create_embed("Альтернативные варианты", f"*Данный трек недоступен.*\nВыберите альтернативу, отправив номер:\n{alt_options}", discord.Color.blue()))
                    def check(m):
                        return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
                    try:
                        reply = await self.bot.wait_for("message", check=check, timeout=30)
                        choice = int(reply.content)
                        if choice < 1 or choice > len(alternatives):
                            await ctx.send(embed=create_embed("Отмена", "*Неверный номер. Альтернативный поиск отменён.*", discord.Color.orange()))
                            return
                        query = alternatives[choice - 1]["webpage_url"]
                    except asyncio.TimeoutError:
                        await ctx.send(embed=create_embed("Отмена", "*Время ожидания ответа истекло. Альтернативный поиск отменён.*", discord.Color.orange()))
                        return
                    try:
                        partial_source = await PartialYTDLSource.create_partial(query)
                    except Exception as e2:
                        await ctx.send(embed=create_embed("❌ Ошибка", f"*Ошибка загрузки альтернативы: {e2}*", discord.Color.red()))
                        return
                else:
                    await ctx.send(embed=create_embed("❌ Ошибка", f"*Ошибка загрузки: {e}\nСовет: проверьте установку FFmpeg.*", discord.Color.red()))
                    return
        if ctx.guild.id not in self.queues:
            self.queues[ctx.guild.id] = MusicQueue()
        await self.queues[ctx.guild.id].add_track(partial_source)
        await ctx.send(embed=create_embed("✅ Добавлено", f"*[{partial_source.title}]({partial_source.data.get('url', '')})* добавлен в очередь.", discord.Color.green(), thumbnail=partial_source.thumbnail))
        if not vc.is_playing():
            await self.play_next(ctx)

    @commands.command(name="pause")
    async def pause(self, ctx: commands.Context) -> None:
        vc = ctx.voice_client
        if not vc or not vc.is_playing():
            await ctx.send(embed=create_embed("❌ Ошибка", "*Ничего не воспроизводится.*", discord.Color.red()))
        else:
            vc.pause()
            await ctx.send(embed=create_embed("ℹ️ Пауза", "*Воспроизведение приостановлено.*", discord.Color.blue()))

    @commands.command(name="resume")
    async def resume(self, ctx: commands.Context) -> None:
        vc = ctx.voice_client
        if not vc or not vc.is_paused():
            await ctx.send(embed=create_embed("❌ Ошибка", "*Нет трека на паузе.*", discord.Color.red()))
        else:
            vc.resume()
            await ctx.send(embed=create_embed("ℹ️ Возобновление", "*Воспроизведение возобновлено.*", discord.Color.blue()))

    @commands.command(name="skip")
    async def skip(self, ctx: commands.Context) -> None:
        vc = ctx.voice_client
        if not vc or not vc.is_playing():
            await ctx.send(embed=create_embed("❌ Ошибка", "*Ничего не воспроизводится.*", discord.Color.red()))
        else:
            vc.stop()
            await ctx.send(embed=create_embed("ℹ️ Пропустить", "*Трек пропущен.*", discord.Color.blue()))

    @commands.command(name="remove")
    async def remove(self, ctx: commands.Context, index: int) -> None:
        guild_id = ctx.guild.id
        if guild_id not in self.queues or self.queues[guild_id].queue.empty():
            await ctx.send(embed=create_embed("❌ Ошибка", "*Очередь пуста.*", discord.Color.red()))
            return
        removed_track = await self.queues[guild_id].remove(index - 1)
        if removed_track is None:
            await ctx.send(embed=create_embed("❌ Ошибка", "*Неверный номер трека.*", discord.Color.red()))
        else:
            await ctx.send(embed=create_embed("🗑️ Удалено", f"*{removed_track.title}* удалён из очереди.", discord.Color.orange()))

    @commands.command(name="clear")
    async def clear(self, ctx: commands.Context) -> None:
        if ctx.guild.id in self.queues:
            await self.queues[ctx.guild.id].clear()
            await ctx.send(embed=create_embed("⚠️ Очистка очереди", "*Очередь очищена.*", discord.Color.green()))
        else:
            await ctx.send(embed=create_embed("❌ Ошибка", "*Очередь пуста.*", discord.Color.red()))

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context) -> None:
        vc = ctx.voice_client
        if vc:
            vc.stop()
            if ctx.guild.id in self.queues:
                await self.queues[ctx.guild.id].clear()
            await ctx.send(embed=create_embed("❌ Стоп", "*Воспроизведение остановлено, очередь очищена.*", discord.Color.red()))
        else:
            await ctx.send(embed=create_embed("❌ Ошибка", "*Я не в голосовом канале.*", discord.Color.red()))

    @commands.command(name="history")
    async def history(self, ctx: commands.Context) -> None:
        if ctx.guild.id in self.queues and self.queues[ctx.guild.id].history:
            hist = "\n".join(f"{item['title']} ({time.strftime('%H:%M:%S', time.gmtime(item['played_at']))})" for item in self.queues[ctx.guild.id].history[-10:])
            await ctx.send(embed=create_embed("⚠️ История треков", hist, discord.Color.blue()))
        else:
            await ctx.send(embed=create_embed("⚠️ История треков", "*История пуста.*", discord.Color.orange()))

    @commands.command(name="stats")
    async def stats(self, ctx: commands.Context) -> None:
        if ctx.guild.id in self.queues:
            played = self.queues[ctx.guild.id].stats
            await ctx.send(embed=create_embed("ℹ️ Статистика", f"*Сыграно треков: {played}*", discord.Color.blue()))
        else:
            await ctx.send(embed=create_embed("ℹ️ Статистика", "*Нет статистики для данного сервера.*", discord.Color.orange()))

    @commands.command(name="control")
    async def control(self, ctx: commands.Context) -> None:
        emb = create_embed("Панель управления", "*Информация о текущем треке будет обновляться автоматически.*", discord.Color.blurple())
        msg = await ctx.send(embed=emb, view=ControlView(self, ctx))
        self.control_messages[ctx.guild.id] = msg

    @commands.command(name="helps")
    async def help_command(self, ctx: commands.Context) -> None:
        commands_info = [
            ("!leave", "Отключиться от голосового канала"),
            ("!play <URL/запрос>", "Проиграть трек или плейлист"),
            ("!pause", "Поставить на паузу"),
            ("!resume", "Возобновить воспроизведение"),
            ("!skip", "Пропустить трек"),
            ("!list", "Посмотреть номер треков"),
            ("!remove <номер>", "Удалить трек из очереди"),
            ("!clear", "Очистить очередь"),
            ("!stop", "Остановить воспроизведение"),
            ("!history", "Показать историю воспроизведения"),
            ("!control", "Панель управления"),
            ("!stats", "Показать статистику воспроизведения")
        ]
        embed = create_embed("🎵 Доступные команды", "", discord.Color.blurple())
        for cmd, desc in commands_info:
            embed.add_field(name=cmd, value=desc, inline=False)
        embed.set_footer(text="Используйте префикс '!' перед командами.")
        await ctx.send(embed=embed)

    async def get_overall_stats(self) -> Dict[str, Any]:
        total = sum(queue.stats for queue in self.queues.values())
        return {"total_tracks": total}

    async def get_queue_state(self) -> Dict[int, List[str]]:
        return {gid: [track.title for track in q.queue._queue] for gid, q in self.queues.items()}

class ControlView(discord.ui.View):
    def __init__(self, cog: Music, ctx: commands.Context) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.ctx = ctx

    @discord.ui.button(label="⏸ Пауза", style=discord.ButtonStyle.secondary, custom_id="toggle")
    async def toggle_playback(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        vc = self.ctx.voice_client
        if not vc:
            await interaction.response.send_message("Бот не подключён к голосовому каналу.", ephemeral=True)
            return
        if vc.is_playing():
            vc.pause()
            button.label = "▶ Возобновить"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("Воспроизведение приостановлено.", ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            button.label = "⏸ Пауза"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("Воспроизведение возобновлено.", ephemeral=True)
        else:
            await interaction.response.send_message("Нет трека для управления.", ephemeral=True)

    @discord.ui.button(label="⏭ Пропустить", style=discord.ButtonStyle.primary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        vc = self.ctx.voice_client
        if not vc or not vc.is_playing():
            await interaction.response.send_message("Ничего не воспроизводится.", ephemeral=True)
        else:
            vc.stop()
            await interaction.response.send_message("Трек пропущен.", ephemeral=True)

    @discord.ui.button(label="🔁 Повтор: none", style=discord.ButtonStyle.success)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild_id = self.ctx.guild.id
        if guild_id in self.cog.queues:
            current = self.cog.queues[guild_id].loop_mode
            new_mode = {"none": "single", "single": "all", "all": "none"}[current]
            self.cog.queues[guild_id].loop_mode = new_mode
            button.label = f"🔁 Повтор: {new_mode}"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"Режим повтора изменён на: **{new_mode}**", ephemeral=True)
        else:
            await interaction.response.send_message("Очередь пуста.", ephemeral=True)

    @discord.ui.button(label="🔀 Шаффл", style=discord.ButtonStyle.success)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild_id = self.ctx.guild.id
        if guild_id in self.cog.queues:
            await self.cog.queues[guild_id].shuffle()
            await interaction.response.send_message("Очередь перемешана.", ephemeral=True)
        else:
            await interaction.response.send_message("Очередь пуста.", ephemeral=True)

    @discord.ui.button(label="🗑 Очистить", style=discord.ButtonStyle.danger)
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild_id = self.ctx.guild.id
        if guild_id in self.cog.queues:
            await self.cog.queues[guild_id].clear()
            await interaction.response.send_message("Очередь очищена.", ephemeral=True)
        else:
            await interaction.response.send_message("Очередь пуста.", ephemeral=True)

    @discord.ui.button(label="⏹ Стоп", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        vc = self.ctx.voice_client
        if vc:
            vc.stop()
            if self.ctx.guild.id in self.cog.queues:
                await self.cog.queues[self.ctx.guild.id].clear()
            await interaction.response.send_message("Воспроизведение остановлено и очередь очищена.", ephemeral=True)
        else:
            await interaction.response.send_message("Я не в голосовом канале.", ephemeral=True)
