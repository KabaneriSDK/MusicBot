# MusicBot
Discord MusicBot

├── __init__.py         # (может быть пустым)
├── config.py           # глобальные константы, настройки (TOKEN, CACHE_DIR, FFmpeg‑опции, intents)
├── dependencies.py     # функции ensure_admin и ensure_dependencies
├── logging_config.py   # настройка логирования и единый лог‑хендлер для GUI
├── utils.py            # вспомогательные функции (create_embed, is_valid_url, форматирование длительности, progress bar)
├── downloader.py       # классы PartialDownloader, PartialYTDLSource и функция поиска альтернатив
├── music_queue.py      # реализация очереди, состояния трека, очистки кэша и глобальный track_state
├── music_cog.py        # Discord‑Cog с командами (play, pause, skip, list, control и т.д.) и UI‑элементами (ControlView)
├── ffmpeg_installer.py # диалог и класс установки FFmpeg
├── gui.py              # реализация GUI (BotGUI, CustomProgressBar и пр.)
├── main.py             # точка входа: создаёт экземпляр бота, загружает Cog, запускает бота
