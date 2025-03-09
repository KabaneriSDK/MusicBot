import sys
import os
import asyncio
from PySide6.QtWidgets import QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QTextEdit, QLabel, QDialog, QDialogButtonBox, QSplitter, QProgressBar
from PySide6.QtGui import QIcon, QPainter, QLinearGradient, QColor, QGraphicsDropShadowEffect, QAction
from PySide6.QtCore import QTimer, Qt, Signal
from logging_config import log_queue, logger
from utils import format_duration

class CustomProgressBar(QProgressBar):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        painter.setBrush(QColor("#555555"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 10, 10)
        progress = self.value() / 100.0
        fill_width = int(rect.width() * progress)
        fill_rect = rect.adjusted(0, 0, -rect.width() + fill_width, 0)
        gradient = QLinearGradient(0, 0, fill_width, 0)
        gradient.setColorAt(0.0, QColor("#76c7c0"))
        gradient.setColorAt(1.0, QColor("#a8e6cf"))
        painter.setBrush(gradient)
        painter.drawRoundedRect(fill_rect, 10, 10)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(rect, Qt.AlignCenter, f"{self.value()}%")
        painter.end()

class BotGUI(QMainWindow):
    track_info_signal = Signal(dict)
    stats_update_signal = Signal(dict)
    notification_signal = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Crimean Bot - Modern Edition")
        self.resize(900, 600)
        self.current_theme = "dark"
        base_dir = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
        icon_path = os.path.join(base_dir, "my_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.apply_styles()
        self.setup_menu()
        self.track_label = QLabel("Сейчас не играет")
        self.track_label.setWordWrap(True)
        self.progress_label = QLabel("")
        self.progress_bar = CustomProgressBar()
        self.status_label = QLabel("")
        self.stats_label = QLabel("Статистика: пока нет данных")
        self.notification_label = QLabel("")
        self.notification_label.setStyleSheet("color: red; font-weight: bold;")
        self.setup_ui()
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.update_logs)
        self.log_timer.start(300)
        self.track_timer = QTimer(self)
        self.track_timer.timeout.connect(self.update_track_info)
        self.track_timer.start(1000)
        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self.update_stats)
        self.stats_timer.start(2000)
        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self.update_queue)
        self.queue_timer.start(5000)
        self.track_info_signal.connect(self.on_track_info_update)
        self.stats_update_signal.connect(self.on_stats_update)
        self.notification_signal.connect(self.show_notification)
        self.fun_facts = [
            "Знаете, что майнинг – это весело!",
            "Майнер запущен – деньги текут рекой!",
            "Кто сказал, что музыка не может быть добычей?",
            "Запускаем майнер – пусть процессор заработает с улыбкой!"
        ]

    def apply_styles(self) -> None:
        if self.current_theme == "dark":
            self.setStyleSheet("""
                QMainWindow { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                                stop:0 #2c2c2c, stop:1 #1a1a1a);
                }
                QLabel#headerLabel { 
                    color: #f0f0f0; 
                    font-size: 26px; 
                    font-weight: bold; 
                    padding: 15px; 
                }
                QPushButton { 
                    background-color: #3a3a3a; 
                    color: #f0f0f0; 
                    border: 2px solid #555; 
                    border-radius: 10px; 
                    padding: 10px; 
                    font-size: 15px; 
                }
                QPushButton:hover { 
                    background-color: #505050; 
                }
                QTextEdit { 
                    background-color: #1e1a1a; 
                    color: #dcdcdc; 
                    border: 1px solid #444; 
                    border-radius: 5px; 
                    font-family: "Consolas", monospace; 
                    font-size: 12px; 
                }
                QMenuBar { 
                    background-color: #2c2c2c; 
                    color: #f0f0f0; 
                }
                QMenuBar::item { 
                    background-color: #2c2c2c; 
                    color: #f0f0f0; 
                    padding: 5px 10px; 
                }
                QMenuBar::item:selected { 
                    background-color: #444; 
                }
                QMenu { 
                    background-color: #3a3a3a; 
                    color: #f0f0f0; 
                }
                QMenu::item:selected { 
                    background-color: #505050; 
                }
                QLabel { 
                    color: #f0f0f0; 
                }
            """)
        elif self.current_theme == "light":
            self.setStyleSheet("""
                QMainWindow { 
                    background: #f0f0f0;
                }
                QLabel#headerLabel { 
                    color: #333; 
                    font-size: 26px; 
                    font-weight: bold; 
                    padding: 15px; 
                }
                QPushButton { 
                    background-color: #e0e0e0; 
                    color: #333; 
                    border: 2px solid #aaa; 
                    border-radius: 10px; 
                    padding: 10px; 
                    font-size: 15px; 
                }
                QPushButton:hover { 
                    background-color: #d0d0d0; 
                }
                QTextEdit { 
                    background-color: #ffffff; 
                    color: #333; 
                    border: 1px solid #ccc; 
                    border-radius: 5px; 
                    font-family: "Consolas", monospace; 
                    font-size: 12px; 
                }
                QMenuBar { 
                    background-color: #e0e0e0; 
                    color: #333; 
                }
                QMenuBar::item { 
                    background-color: #e0e0e0; 
                    color: #333; 
                    padding: 5px 10px; 
                }
                QMenuBar::item:selected { 
                    background-color: #ccc; 
                }
                QMenu { 
                    background-color: #f9f9f9; 
                    color: #333; 
                }
                QMenu::item:selected { 
                    background-color: #ddd; 
                }
                QLabel { 
                    color: #333; 
                }
            """)
        elif self.current_theme == "rainbow":
            self.setStyleSheet("""
                QMainWindow { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 red, stop:0.16 orange, stop:0.33 yellow, stop:0.5 green, stop:0.66 blue, stop:0.83 indigo, stop:1 violet);
                }
                QLabel#headerLabel { 
                    color: white; 
                    font-size: 26px; 
                    font-weight: bold; 
                    padding: 15px; 
                }
                QPushButton { 
                    background-color: rgba(0,0,0,0.5); 
                    color: white; 
                    border: 2px solid white; 
                    border-radius: 10px; 
                    padding: 10px; 
                    font-size: 15px; 
                }
                QPushButton:hover { 
                    background-color: rgba(255,255,255,0.2); 
                }
                QTextEdit { 
                    background-color: rgba(0,0,0,0.7); 
                    color: white; 
                    border: 1px solid white; 
                    border-radius: 5px; 
                    font-family: "Consolas", monospace; 
                    font-size: 12px; 
                }
                QMenuBar { 
                    background-color: rgba(0,0,0,0.5); 
                    color: white; 
                }
                QMenuBar::item { 
                    background-color: rgba(0,0,0,0.5); 
                    color: white; 
                    padding: 5px 10px; 
                }
                QMenuBar::item:selected { 
                    background-color: rgba(255,255,255,0.2); 
                }
                QMenu { 
                    background-color: rgba(0,0,0,0.7); 
                    color: white; 
                }
                QMenu::item:selected { 
                    background-color: rgba(255,255,255,0.2); 
                }
            """)

    def setup_menu(self) -> None:
        menubar = self.menuBar()
        settings_menu = menubar.addMenu("Настройки")
        theme_action = QAction("Переключить тему", self)
        theme_action.triggered.connect(self.toggle_theme)
        settings_menu.addAction(theme_action)
        settings_action = QAction("Параметры", self)
        settings_action.triggered.connect(self.open_settings)
        settings_menu.addAction(settings_action)
        about_action = QAction("О программе", self)
        about_action.triggered.connect(self.show_about)
        menubar.addAction(about_action)

    def setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        header = QLabel("Панель управления ботом")
        header.setObjectName("headerLabel")
        header.setAlignment(Qt.AlignCenter)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setOffset(3, 3)
        header.setGraphicsEffect(shadow)
        main_layout.addWidget(header)
        main_layout.addWidget(self.notification_label)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.stats_label)
        splitter = QSplitter(Qt.Horizontal)
        control_panel = QWidget()
        control_layout = QGridLayout(control_panel)
        control_layout.setSpacing(15)
        btn_about = QPushButton("О программе")
        btn_about.clicked.connect(self.show_about)
        btn_miner = QPushButton("Включить Майнер")
        btn_miner.setToolTip("Запустить майнер")
        btn_miner.clicked.connect(self.open_miner)
        btn_shutdown = QPushButton("Выключить бота")
        btn_shutdown.clicked.connect(self.close)
        control_layout.addWidget(btn_about, 0, 0)
        control_layout.addWidget(btn_miner, 0, 1)
        control_layout.addWidget(btn_shutdown, 1, 0, 1, 2)
        control_layout.addWidget(self.track_label, 2, 0, 1, 2)
        control_layout.addWidget(self.progress_label, 3, 0, 1, 2)
        control_layout.addWidget(self.progress_bar, 4, 0, 1, 2)
        self.btn_playpause = QPushButton("Пауза")
        self.btn_playpause.clicked.connect(self.toggle_play_pause)
        self.btn_skip = QPushButton("Пропустить")
        self.btn_skip.clicked.connect(self.skip_track)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.valueChanged.connect(self.change_volume)
        queue_label = QLabel("Очередь треков:")
        self.queue_text = QTextEdit()
        self.queue_text.setReadOnly(True)
        control_layout.addWidget(self.btn_playpause, 5, 0)
        control_layout.addWidget(self.btn_skip, 5, 1)
        control_layout.addWidget(self.volume_slider, 6, 0, 1, 2)
        control_layout.addWidget(queue_label, 7, 0, 1, 2)
        control_layout.addWidget(self.queue_text, 8, 0, 1, 2)
        splitter.addWidget(control_panel)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        splitter.addWidget(self.log_text)
        splitter.setSizes([400, 500])
        main_layout.addWidget(splitter)

    def update_logs(self) -> None:
        try:
            while not log_queue.empty():
                msg = log_queue.get_nowait()
                self.log_text.append(msg)
                self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        except Exception as e:
            logger.error("Ошибка обновления логов в GUI", extra={"error": str(e)})

    def update_track_info(self) -> None:
        try:
            # Пример получения информации о треке (реализация зависит от глобального состояния)
            state = asyncio.run_coroutine_threadsafe(track_state.get_state(), asyncio.get_event_loop()).result(timeout=1)
            self.track_info_signal.emit(state)
        except Exception as e:
            logger.error("Ошибка обновления информации о треке", extra={"error": str(e)})

    def update_stats(self) -> None:
        try:
            if hasattr(self, 'music_cog') and self.music_cog:
                future = asyncio.run_coroutine_threadsafe(self.music_cog.get_overall_stats(), asyncio.get_event_loop())
                stats = future.result(timeout=1)
                self.stats_update_signal.emit(stats)
        except Exception as e:
            logger.error("Ошибка обновления статистики", extra={"error": str(e)})

    def update_queue(self) -> None:
        try:
            if hasattr(self, 'music_cog') and self.music_cog:
                future = asyncio.run_coroutine_threadsafe(self.music_cog.get_queue_state(), asyncio.get_event_loop())
                queue_state = future.result(timeout=1)
                text_lines = []
                for guild_id, titles in queue_state.items():
                    if titles:
                        guild = self.music_cog.bot.get_guild(guild_id)
                        server_name = guild.name if guild else f"Guild {guild_id}"
                        text_lines.append(f"Очередь ({server_name}):")
                        for i, title in enumerate(titles, start=1):
                            if i == 1:
                                text_lines.append(f"► {i}. {title}")
                            else:
                                text_lines.append(f"{i}. {title}")
                    else:
                        text_lines.append("Очередь пуста.")
                if not text_lines:
                    text_lines.append("Очередь пуста.")
                self.queue_text.setText("\n".join(text_lines))
        except Exception as e:
            logger.error("Ошибка обновления очереди", extra={"error": str(e)})

    def on_track_info_update(self, state: dict) -> None:
        self.track_label.setText(f"Сейчас играет: {state.get('title', 'Нет трека')}")
        duration = state.get("duration", 0)
        progress = state.get("progress", 0)
        percent = int((progress / duration) * 100) if duration > 0 else 0
        self.progress_bar.setValue(percent)
        self.progress_label.setText(f"{format_duration(progress)} / {format_duration(duration)}")

    def on_stats_update(self, stats: dict) -> None:
        self.stats_label.setText(f"Общее число треков: {stats.get('total_tracks', 0)}")

    def show_notification(self, message: str) -> None:
        self.notification_label.setText(message)
        QTimer.singleShot(3000, lambda: self.notification_label.setText(""))

    def open_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Настройки")
        dialog.resize(400, 300)
        layout = QVBoxLayout(dialog)
        label = QLabel("Настройки пока не реализованы.")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        dialog.exec()
        self.status_label.setText("Настройки закрыты")

    def show_about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("О программе")
        dialog.resize(320, 180)
        layout = QVBoxLayout(dialog)
        info_label = QLabel("Версия бота: Modern Edition")
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        dialog.exec()

    def toggle_theme(self) -> None:
        themes = ["dark", "light", "rainbow"]
        current_index = themes.index(self.current_theme)
        self.current_theme = themes[(current_index + 1) % len(themes)]
        self.apply_styles()

    def toggle_play_pause(self) -> None:
        # Здесь можно добавить управление воспроизведением через GUI
        pass

    def skip_track(self) -> None:
        # Здесь можно добавить логику пропуска трека
        pass

    def change_volume(self, value: int) -> None:
        # Здесь можно добавить логику изменения громкости
        pass

    def open_miner(self) -> None:
        # Заглушка для функции майнера
        self.show_notification("Майнер запущен!")
