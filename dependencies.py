import sys
import os
import subprocess
import importlib
import platform
from logging_config import logger

def ensure_admin() -> None:
    """Проверяет и запрашивает права администратора, если необходимо."""
    if platform.system() == "Windows":
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            params = " ".join([f'"{arg}"' for arg in sys.argv])
            logger.info("Перезапуск с правами администратора...")
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
            sys.exit()
    elif os.name == 'posix':
        if os.geteuid() != 0:
            try:
                os.execlp('sudo', 'sudo', sys.executable, *sys.argv)
            except Exception as e:
                logger.error("Не удалось получить права администратора. Запустите скрипт с sudo.")
                sys.exit(1)

def ensure_dependencies() -> None:
    """Проверяет наличие и при необходимости устанавливает недостающие зависимости."""
    required_packages = {
        "discord": "discord.py",
        "yt_dlp": "yt-dlp",
        "aiohttp": "aiohttp",
        "aiofiles": "aiofiles",
        "structlog": "structlog",
        "PySide6": "PySide6",
        "nacl": "PyNaCl"
    }
    missing_packages = []
    for module, package in required_packages.items():
        try:
            importlib.import_module(module)
        except ImportError:
            missing_packages.append(package)
    if missing_packages:
        logger.info(f"[DEP] Установка отсутствующих пакетов: {', '.join(missing_packages)}")
        result = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade"] + missing_packages)
        if result.returncode != 0:
            logger.error(f"[DEP] Не удалось установить пакеты: {', '.join(missing_packages)}. Завершение работы.")
            sys.exit(1)
