import time
import asyncio
import youtube_dl
import discord
import os
from typing import Optional, Dict, Any, List, Union
from config import CACHE_DIR, ffmpeg_opts_no_fade, FFMPEG_BINARY, ytdl_format_options
from utils import is_valid_url, format_duration
from logging_config import logger

class TrackDownloadError(Exception):
    pass

download_semaphore = asyncio.Semaphore(5)

class PartialDownloader:
    def __init__(self, url: str, min_buffer_duration: int = 10) -> None:
        self.url: str = url
        self.min_buffer_duration: int = min_buffer_duration
        self.file_path: Optional[str] = None
        self.info: Optional[Dict[str, Any]] = None
        self.ready_to_play: asyncio.Event = asyncio.Event()
        self.download_finished: asyncio.Event = asyncio.Event()
        self.approx_bitrate: int = 320
        self.bytes_per_second: int = (self.approx_bitrate * 1000) // 8

    def progress_hook(self, status: Dict[str, Any]) -> None:
        tmp_path = status.get('tmpfilename')
        if tmp_path and not self.file_path:
            self.file_path = tmp_path
        if status.get('status') == 'downloading':
            downloaded = status.get('downloaded_bytes', 0)
            if (not self.ready_to_play.is_set() and downloaded / self.bytes_per_second >= self.min_buffer_duration):
                logger.debug("Буфер достигнут", extra={"downloaded": downloaded})
                self.ready_to_play.set()
        elif status.get('status') in ('finished', 'error'):
            final_path = status.get('filename')
            if final_path:
                self.file_path = final_path
            self.ready_to_play.set()
            self.download_finished.set()

    async def download(self) -> None:
        local_opts = dict(ytdl_format_options)
        local_opts['progress_hooks'] = [self.progress_hook]
        async with download_semaphore:
            def _work_with_retry() -> Dict[str, Any]:
                attempts = 3
                delay = 1
                for i in range(attempts):
                    try:
                        with youtube_dl.YoutubeDL(local_opts) as ydl:
                            meta = ydl.extract_info(self.url, download=False)
                            if meta is None:
                                raise TrackDownloadError("Видео недоступно")
                            self.info = meta
                            if meta.get("id") and meta.get("ext"):
                                cache_path = os.path.join(CACHE_DIR, f"{meta['id']}.{meta['ext']}")
                                if os.path.exists(cache_path):
                                    self.file_path = cache_path
                                    logger.info("Используется кэшированный файл", extra={"file": cache_path})
                                    self.ready_to_play.set()
                                    return meta
                            ydl.process_ie_result(meta, download=True)
                            return meta
                    except Exception as e:
                        logger.error("Ошибка загрузки (попытка %d)", i + 1, extra={"error": str(e)})
                        if i == attempts - 1:
                            raise TrackDownloadError(str(e)) from e
                        time.sleep(delay)
                        delay *= 2
                raise TrackDownloadError("Не удалось загрузить трек")
            try:
                info = await asyncio.to_thread(_work_with_retry)
                self.info = info
            except Exception as e:
                logger.error("Ошибка загрузки", extra={"error": str(e)})
                self.ready_to_play.set()
                raise
            finally:
                self.download_finished.set()

class PartialYTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source: discord.FFmpegPCMAudio, *, data: Dict[str, Any], volume: float = 0.7,
                 file_path: Optional[str] = None) -> None:
        super().__init__(source, volume)
        self.data: Dict[str, Any] = data or {}
        self.title: str = self.data.get("title") or "Unknown"
        self.url: Optional[str] = self.data.get("url")
        self.thumbnail: Optional[str] = self.data.get("thumbnail")
        self.file_path: Optional[str] = file_path

    def cleanup_file(self) -> None:
        if self.file_path and os.path.exists(self.file_path):
            try:
                os.remove(self.file_path)
                logger.info("Удалён файл", extra={"file": self.file_path})
            except Exception as e:
                logger.error("Ошибка удаления файла", extra={"file": self.file_path, "error": str(e)})

    @classmethod
    async def create_partial(cls, url: str, min_buffer_sec: int = 10) -> "PartialYTDLSource":
        if url.startswith("http") and not is_valid_url(url):
            raise TrackDownloadError("Некорректный URL.")
        downloader = PartialDownloader(url, min_buffer_duration=min_buffer_sec)
        task = asyncio.create_task(downloader.download())
        try:
            await asyncio.wait_for(downloader.ready_to_play.wait(), timeout=60)
        except asyncio.TimeoutError:
            logger.warning("Время ожидания буферизации истекло, пробуем более низкое качество...")
            low_opts = dict(ytdl_format_options)
            low_opts['format'] = 'worstaudio/bestaudio'
            low_opts['outtmpl'] = f'{CACHE_DIR}/%(id)s_low.%(ext)s'
            info_low = None
            try:
                info_low = await asyncio.to_thread(lambda: youtube_dl.YoutubeDL(low_opts).extract_info(url, download=True))
            except Exception as e:
                raise TrackDownloadError(f"Не удалось загрузить трек (низкое качество): {e}") from e
            low_path = None
            if info_low:
                low_path = os.path.join(CACHE_DIR, f"{info_low.get('id')}_low.{info_low.get('ext')}")
            if not low_path or not os.path.exists(low_path):
                raise TrackDownloadError("Не удалось получить аудио даже в низком качестве.")
            source = discord.FFmpegPCMAudio(low_path, executable=FFMPEG_BINARY, options=ffmpeg_opts_no_fade)
            data = {
                "title": info_low.get("title") or info_low.get("fulltitle") or "Unknown",
                "url": info_low.get("webpage_url"),
                "thumbnail": info_low.get("thumbnail"),
                "duration": info_low.get("duration"),
            }
            if not task.done():
                task.cancel()
            return cls(source, data=data, file_path=low_path)
        if task.done() and task.exception():
            exc = task.exception()
            logger.warning("Ошибка загрузки трека, пробуем более низкое качество...", extra={"error": str(exc)})
            low_opts = dict(ytdl_format_options)
            low_opts['format'] = 'worstaudio/bestaudio'
            low_opts['outtmpl'] = f'{CACHE_DIR}/%(id)s_low.%(ext)s'
            info_low = None
            try:
                info_low = await asyncio.to_thread(lambda: youtube_dl.YoutubeDL(low_opts).extract_info(url, download=True))
            except Exception as e:
                raise TrackDownloadError(f"Не удалось загрузить трек (низкое качество): {e}") from e
            low_path = None
            if info_low:
                low_path = os.path.join(CACHE_DIR, f"{info_low.get('id')}_low.{info_low.get('ext')}")
            if not low_path or not os.path.exists(low_path):
                raise TrackDownloadError("Не удалось получить аудио даже в низком качестве.")
            source = discord.FFmpegPCMAudio(low_path, executable=FFMPEG_BINARY, options=ffmpeg_opts_no_fade)
            data = {
                "title": info_low.get("title") or info_low.get("fulltitle") or "Unknown",
                "url": info_low.get("webpage_url"),
                "thumbnail": info_low.get("thumbnail"),
                "duration": info_low.get("duration"),
            }
            return cls(source, data=data, file_path=low_path)
        if not downloader.file_path or not os.path.exists(downloader.file_path):
            raise TrackDownloadError("Не удалось получить локальный файл. Проверьте установку FFmpeg.")
        source = discord.FFmpegPCMAudio(downloader.file_path, executable=FFMPEG_BINARY, options=ffmpeg_opts_no_fade)
        info_dict = downloader.info or {}
        data = {
            "title": info_dict.get("title") or info_dict.get("fulltitle") or "Unknown",
            "url": info_dict.get("webpage_url"),
            "thumbnail": info_dict.get("thumbnail"),
            "duration": info_dict.get("duration"),
        }
        return cls(source, data=data, file_path=downloader.file_path)

async def find_alternative_tracks(query: str) -> List[Dict[str, Any]]:
    search_query = f"ytsearch10:{query}"
    try:
        info = await asyncio.to_thread(lambda: youtube_dl.YoutubeDL(ytdl_format_options).extract_info(search_query, download=False))
        results = info.get("entries", [])
        results.sort(key=lambda x: 0 if "llyrics" in (((x.get("title") or "").lower()) + ((x.get("description") or "").lower())) else 1)
        return results
    except Exception as e:
        logger.exception("Ошибка поиска альтернатив", extra={"error": str(e)})
        return []
