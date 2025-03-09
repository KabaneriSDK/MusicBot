import time
import asyncio
import random
import os
from typing import Dict, List, Optional, Any, Tuple
from downloader import PartialYTDLSource
from logging_config import logger

class TrackState:
    def __init__(self) -> None:
        self.title: str = "Нет трека"
        self.progress: float = 0.0
        self.duration: float = 0.0
        self.start_time: float = 0.0
        self.lock = asyncio.Lock()

    async def update(self, title: str, duration: float, progress: float, start_time: float) -> None:
        async with self.lock:
            self.title = title
            self.duration = duration
            self.progress = progress
            self.start_time = start_time

    async def get_state(self) -> Dict[str, Any]:
        async with self.lock:
            return {
                "title": self.title,
                "progress": self.progress,
                "duration": self.duration,
                "start_time": self.start_time
            }

# Глобальный объект для отслеживания состояния трека
track_state = TrackState()

class MusicQueue:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[PartialYTDLSource] = asyncio.Queue()
        self.history: List[Dict[str, Any]] = []
        self.stats: int = 0
        self.loop_mode: str = "none"

    async def add_track(self, track: PartialYTDLSource) -> None:
        await self.queue.put(track)

    async def add_tracks(self, tracks: List[PartialYTDLSource]) -> None:
        for track in tracks:
            await self.queue.put(track)

    async def get_next_track(self) -> Optional[PartialYTDLSource]:
        if self.queue.empty():
            return None
        track = await self.queue.get()
        if self.loop_mode in ("single", "all"):
            await self.queue.put(track)
        self.history.append({"title": track.title, "played_at": time.time()})
        self.stats += 1
        return track

    async def clear(self) -> None:
        while not self.queue.empty():
            await self.queue.get()

    async def shuffle(self) -> None:
        items: List[PartialYTDLSource] = []
        while not self.queue.empty():
            items.append(await self.queue.get())
        random.shuffle(items)
        for item in items:
            await self.queue.put(item)

    async def remove(self, index: int) -> Optional[PartialYTDLSource]:
        items: List[PartialYTDLSource] = []
        removed: Optional[PartialYTDLSource] = None
        while not self.queue.empty():
            items.append(await self.queue.get())
        if 0 <= index < len(items):
            removed = items.pop(index)
        for item in items:
            await self.queue.put(item)
        return removed

class CacheCleaner:
    def __init__(self, cache_dir: str, max_cache_size: int) -> None:
        self.cache_dir = cache_dir
        self.max_cache_size = max_cache_size

    async def cleanup(self) -> None:
        removed = 0
        now = time.time()

        def cleanup_files() -> int:
            count = 0
            for fname in os.listdir(self.cache_dir):
                fpath = os.path.join(self.cache_dir, fname)
                if os.path.isfile(fpath) and (now - os.path.getmtime(fpath) > 3600):
                    try:
                        os.remove(fpath)
                        count += 1
                    except Exception as e:
                        logger.error("Ошибка удаления файла из кэша", extra={"file": fpath, "error": str(e)})
            return count

        removed += await asyncio.to_thread(cleanup_files)

        def calculate_total_size() -> int:
            return sum(os.path.getsize(os.path.join(self.cache_dir, f))
                       for f in os.listdir(self.cache_dir)
                       if os.path.isfile(os.path.join(self.cache_dir, f)))
        total_size = await asyncio.to_thread(calculate_total_size)
        if total_size > self.max_cache_size:
            def get_files() -> List[Tuple[str, float]]:
                return sorted(
                    [(os.path.join(self.cache_dir, f), os.path.getmtime(os.path.join(self.cache_dir, f)))
                     for f in os.listdir(self.cache_dir)
                     if os.path.isfile(os.path.join(self.cache_dir, f))],
                    key=lambda x: x[1]
                )
            files = await asyncio.to_thread(get_files)
            for fpath, _ in files:
                try:
                    os.remove(fpath)
                    removed += 1
                except Exception as e:
                    logger.error("Ошибка удаления файла из кэша", extra={"file": fpath, "error": str(e)})
                total_size -= os.path.getsize(fpath) if os.path.exists(fpath) else 0
                if total_size <= self.max_cache_size:
                    break
        if removed:
            logger.info("Очищено файлов из кэша", extra={"count": removed})
