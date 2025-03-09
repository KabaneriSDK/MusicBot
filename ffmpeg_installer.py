import os
import sys
import shutil
import zipfile
import time
import threading
import asyncio
import subprocess
import platform
import aiohttp
import aiofiles
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
from PySide6.QtCore import Qt
from logging_config import logger
from config import CACHE_DIR, FFMPEG_BINARY

class FFmpegInstallDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Установка FFmpeg")
        self.setFixedSize(400, 150)
        layout = QVBoxLayout(self)
        self.label = QLabel("Подготовка к установке FFmpeg...", self)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        self.close_button = QPushButton("Закрыть", self)
        self.close_button.clicked.connect(self.close)
        self.close_button.hide()
        layout.addWidget(self.close_button)

    def update_message(self, message: str) -> None:
        self.label.setText(message)

    def show_close_button(self) -> None:
        self.close_button.show()

class FFmpegInstaller:
    def __init__(self) -> None:
        self.current_os = platform.system()

    async def install(self) -> None:
        global FFMPEG_BINARY
        if shutil.which("ffmpeg") is not None:
            logger.info("FFmpeg уже установлен в системе.")
            FFMPEG_BINARY = shutil.which("ffmpeg")
            return
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            candidate = os.path.join(exe_dir, "ffmpeg.exe") if self.current_os == "Windows" else os.path.join(exe_dir, "ffmpeg")
            if os.path.exists(candidate):
                os.environ["PATH"] += os.pathsep + exe_dir
                FFMPEG_BINARY = candidate
                logger.info("FFmpeg загружен из папки exe: %s", candidate)
                return
            else:
                logger.error("FFmpeg не найден в папке exe. Пожалуйста, разместите ffmpeg рядом с приложением.")
                return
        for root, dirs, files in os.walk(CACHE_DIR):
            if ("ffmpeg.exe" in files) or ("ffmpeg" in files):
                ffmpeg_path = os.path.join(root, "ffmpeg.exe") if "ffmpeg.exe" in files else os.path.join(root, "ffmpeg")
                os.environ["PATH"] += os.pathsep + root
                FFMPEG_BINARY = ffmpeg_path
                logger.info("FFmpeg уже загружен в кэше. Путь: %s", root)
                return
        if threading.current_thread() != threading.main_thread():
            logger.warning("Установка FFmpeg не может быть выполнена в не-GUI потоке. Пропускаем установку.")
            return
        dialog = FFmpegInstallDialog()
        dialog.show()
        await asyncio.sleep(0.5)
        logger.info("FFmpeg не найден, начинаем установку...")
        success = False
        if self.current_os == "Windows":
            dialog.update_message("Скачивание FFmpeg...")
            url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            temp_zip = os.path.join(CACHE_DIR, "ffmpeg.zip")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            logger.error("Не удалось загрузить FFmpeg: статус %s", resp.status)
                            dialog.update_message("Ошибка загрузки FFmpeg.")
                            await asyncio.sleep(10)
                            dialog.show_close_button()
                            return
                        async with aiofiles.open(temp_zip, "wb") as f:
                            await f.write(await resp.read())
                dialog.update_message("Распаковка архива FFmpeg...")
                def extract_zip():
                    with zipfile.ZipFile(temp_zip, "r") as zip_ref:
                        zip_ref.extractall(CACHE_DIR)
                await asyncio.to_thread(extract_zip)
                ffmpeg_path = None
                for root, dirs, files in os.walk(CACHE_DIR):
                    if "ffmpeg.exe" in files:
                        ffmpeg_path = root
                        break
                if ffmpeg_path:
                    os.environ["PATH"] += os.pathsep + ffmpeg_path
                    FFMPEG_BINARY = os.path.join(ffmpeg_path, "ffmpeg.exe")
                    logger.info("FFmpeg установлен. Путь: %s", ffmpeg_path)
                    dialog.update_message("FFmpeg успешно установлен!")
                    success = True
                else:
                    logger.error("Не удалось найти ffmpeg.exe после извлечения.")
                    dialog.update_message("Ошибка установки: ffmpeg.exe не найден.")
            except Exception as e:
                logger.error("Ошибка установки FFmpeg на Windows: %s", str(e))
                dialog.update_message("Ошибка установки FFmpeg.")
        elif self.current_os == "Linux":
            dialog.update_message("Установка FFmpeg через пакетный менеджер...")
            try:
                if shutil.which("apt-get") is not None:
                    subprocess.run(["sudo", "apt-get", "update"], check=True)
                    subprocess.run(["sudo", "apt-get", "install", "-y", "ffmpeg"], check=True)
                elif shutil.which("dnf") is not None:
                    subprocess.run(["sudo", "dnf", "install", "-y", "ffmpeg"], check=True)
                elif shutil.which("yum") is not None:
                    subprocess.run(["sudo", "yum", "install", "-y", "ffmpeg"], check=True)
                elif shutil.which("pacman") is not None:
                    subprocess.run(["sudo", "pacman", "-Sy", "--noconfirm", "ffmpeg"], check=True)
                else:
                    raise Exception("Пакетный менеджер не найден.")
                ffmpeg_exe = shutil.which("ffmpeg")
                if ffmpeg_exe:
                    FFMPEG_BINARY = ffmpeg_exe
                    logger.info("FFmpeg успешно установлен через пакетный менеджер.")
                    dialog.update_message("FFmpeg успешно установлен!")
                    success = True
                else:
                    raise Exception("FFmpeg не найден после установки.")
            except Exception as e:
                logger.error("Ошибка установки FFmpeg через пакетный менеджер: %s", str(e))
                dialog.update_message("Ошибка установки через пакетный менеджер.")
        elif self.current_os == "Darwin":
            dialog.update_message("Установка FFmpeg через Homebrew...")
            try:
                subprocess.run(["brew", "install", "ffmpeg"], check=True)
                ffmpeg_exe = shutil.which("ffmpeg")
                if ffmpeg_exe:
                    FFMPEG_BINARY = ffmpeg_exe
                    logger.info("FFmpeg успешно установлен через Homebrew.")
                    dialog.update_message("FFmpeg успешно установлен!")
                    success = True
                else:
                    raise Exception("FFmpeg не найден после установки через Homebrew.")
            except Exception as e:
                logger.error("Ошибка установки FFmpeg через Homebrew: %s", str(e))
                dialog.update_message("Ошибка установки через Homebrew.")
        else:
            logger.error("Операционная система %s не поддерживается для автоматической установки FFmpeg.", self.current_os)
            dialog.update_message(f"ОС {self.current_os} не поддерживается.")
        if success:
            await asyncio.sleep(3)
            dialog.close()
        else:
            await asyncio.sleep(10)
            dialog.show_close_button()
