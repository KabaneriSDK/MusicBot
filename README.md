# Описание модулей проекта

## 1. **config.py**
Этот модуль содержит глобальные настройки и константы:
- **FFMPEG_BINARY, CURRENT_VERSION, CACHE_DIR, MAX_CACHE_SIZE**  
  – Имя бинарного файла ffmpeg, версия бота, папка для кэширования аудио и максимальный размер кэша.
- **Настройки обработки аудио:**  
  – Параметры частоты дискретизации, каналов и фильтры (на основе ffmpeg).
- **Discord‑настройки:**  
  – Токен бота (замените на свой), а также настройка intents (необходимые для работы с текстовыми и голосовыми каналами).
- **Инициализация:**  
  – Проверка существования папки для кэша и корректная настройка событийного цикла для Windows.

---

## 2. **dependencies.py**
Здесь находятся функции для проверки прав и зависимостей:
- **ensure_admin()**  
  – Проверяет, запущен ли скрипт с правами администратора. Если нет – запрашивает повышение прав (Windows/Posix).
- **ensure_dependencies()**  
  – Проверяет наличие всех необходимых сторонних библиотек (discord.py, yt-dlp, aiohttp, aiofiles, structlog, PySide6, PyNaCl). При отсутствии – автоматически устанавливает недостающие пакеты через pip.

---

## 3. **logging_config.py**
Этот модуль отвечает за настройку логирования:
- Используется библиотека **structlog** для структурированного логирования.
- Настраиваются консольный вывод, файловый вывод (с ротацией файлов) и специальный лог‑хендлер (UnifiedQueueHandler), который отправляет сообщения в очередь для обновления логов в GUI.
- Экспортируется глобальный объект `logger` и `log_queue` для использования в других модулях.

---

## 4. **utils.py**
Модуль содержит вспомогательные функции, используемые по всему проекту:
- **create_embed()**  
  – Формирует стандартное Discord‑embed сообщение с заданным заголовком, описанием, цветом, миниатюрой и ссылкой.
- **is_valid_url()**  
  – Проверяет корректность URL по схеме и наличию домена.
- **format_duration()**  
  – Преобразует число секунд в строку вида «MM:SS» или «HH:MM:SS».
- **create_progress_bar()**  
  – Создает строковое представление прогресс-бара для отображения состояния воспроизведения.

---

## 5. **downloader.py**
Отвечает за загрузку аудио-треков с использованием библиотеки **yt-dlp**:
- **TrackDownloadError**  
  – Кастомное исключение для ошибок загрузки трека.
- **PartialDownloader**  
  – Класс, который реализует загрузку с поддержкой буферизации. Отслеживает прогресс через progress‑hook и сигнализирует, когда достаточно данных для начала воспроизведения.
- **PartialYTDLSource**  
  – Наследуется от `discord.PCMVolumeTransformer` и оборачивает информацию о треке. Содержит метод `create_partial()`, который скачивает аудио, пытаясь сначала загрузить в полном качестве, а при необходимости – переключиться на более низкое качество.
- **find_alternative_tracks()**  
  – Функция для поиска альтернативных вариантов трека (например, если оригинал недоступен по региональным ограничениям).

---

## 6. **music_queue.py**
Модуль для работы с очередью воспроизведения:
- **TrackState**  
  – Хранит текущее состояние трека (название, длительность, прогресс, время старта) с использованием асинхронного блокирования.
- **track_state**  
  – Глобальный объект для доступа к состоянию воспроизведения.
- **MusicQueue**  
  – Реализует асинхронную очередь для хранения объектов `PartialYTDLSource`, историю воспроизведения, статистику (количество сыгранных треков) и режим повторения.
- **CacheCleaner**  
  – Класс для периодической очистки кэша: удаляет устаревшие или избыточные аудиофайлы.

---

## 7. **music_cog.py**
Это основное ядро Discord‑бота:
- Реализован в виде Cog для библиотеки **discord.py**.
- Содержит команды для управления воспроизведением:  
  – **play, pause, resume, skip, remove, clear, stop, list, history, stats, control, helps**.
- **ensure_voice_client()**  
  – Вспомогательная функция для подключения к голосовому каналу.
- Фоновые задачи:  
  – Автоматическое отключение (если в канале нет пользователей), обновление прогресса воспроизведения, очистка кэша.
- **ControlView**  
  – Интерактивное представление с кнопками для управления воспроизведением (пауза/возобновление, пропуск, режим повторения, шаффл, очистка очереди, стоп).

---

## 8. **ffmpeg_installer.py**
Модуль для установки FFmpeg, если он не найден:
- **FFmpegInstallDialog**  
  – Диалоговое окно (на базе PySide6), информирующее пользователя о ходе установки FFmpeg.
- **FFmpegInstaller**  
  – Класс, который проверяет наличие FFmpeg в системе и, при необходимости, загружает и распаковывает архив с FFmpeg. Реализована логика для разных операционных систем (Windows, Linux, macOS).

---

## 9. **gui.py**
Реализует графический интерфейс для управления ботом (на базе PySide6):
- **CustomProgressBar**  
  – Кастомный виджет прогресс-бара с округленными углами и градиентной заливкой.
- **BotGUI**  
  – Главное окно приложения. Содержит:
  - Элементы для отображения информации о треке (название, прогресс, длительность).
  - Текстовое поле для отображения логов (получаемых из `log_queue`).
  - Элементы управления (кнопки для паузы/возобновления, пропуска трека, изменения громкости, запуска майнера).
  - Таймеры для периодического обновления логов, информации о треке, статистики и очереди.  
    – Методы, такие как `toggle_play_pause`, `skip_track` и `change_volume`, реализованы и отправляют уведомления, а также обновляют состояние кнопок.  
    – Интерфейс может работать автономно или интегрироваться с логикой Music Cog.

---

## 10. **main.py**
Точка входа в приложение:
- Вызывает функции из **dependencies.py** для проверки прав и установки зависимостей.
- Создает экземпляр Discord‑бота, задает префикс команд и intents.
- Загружает Cog из **music_cog.py** и устанавливает глобальные переменные для интеграции между модулями.
- Запускает бота с использованием токена из **config.py**.

---

# Инструкция по установке и запуску

## 1. Требования
- **Python 3.8 или выше.**
- Установленный **pip** для управления пакетами.
- Рекомендуется использовать виртуальное окружение.
- Для работы GUI требуется установленный **PySide6**.

## 2. Получение кода
Склонируйте репозиторий (или загрузите архив проекта) и перейдите в папку проекта:

3. Установка зависимостей
Рекомендуемый способ – создание виртуального окружения:

bash
Копировать
python -m venv venv
Активируйте виртуальное окружение:

На Windows: venv\Scripts\activate
На Linux/macOS: source venv/bin/activate
Установка пакетов: Создайте файл requirements.txt со следующим содержимым:
discord.py
yt-dlp
aiohttp
aiofiles
structlog
PySide6
PyNaCl
Затем выполните: pip install -r requirements.txt
Автоматическая проверка зависимостей:
При запуске бота функция ensure_dependencies() (из модуля dependencies.py) проверит наличие необходимых библиотек и попытается установить недостающие, если запуск происходит с правами администратора.

4. Настройка
Откройте файл config.py и замените значение переменной TOKEN на токен вашего Discord‑бота.
При необходимости измените другие настройки (например, путь к кэшу, параметры FFmpeg).
5. Запуск Discord‑бота (без GUI)
Для запуска бота выполните: python main.py
Бот подключится к Discord с использованием заданного токена и будет готов принимать команды (например, !play, !pause и т.д.).

6. Запуск графического интерфейса (GUI)
Если вы хотите запустить отдельное приложение с графическим интерфейсом для управления ботом, выполните: python gui.py
Откроется окно с элементами управления, логами и информацией о воспроизведении.

Кнопки для паузы/возобновления, пропуска, изменения громкости и запуска майнера реализованы и выводят уведомления.
Для интеграции с реальным управлением (например, вызовами методов из Music Cog) достаточно доработать соответствующие функции.
7. FFmpeg
Обязательный компонент для обработки аудио.
Модуль ffmpeg_installer.py проверяет наличие FFmpeg и, если его нет, предлагает скачать и установить его автоматически (с диалоговым окном, если запускается в GUI‑режиме).

Если вы предпочитаете установить FFmpeg вручную, скачайте его с официального сайта и добавьте путь к бинарнику в системную переменную PATH.

8. Дополнительная информация
Структура проекта:
Проект разделен на отдельные модули по функциональному назначению – от конфигурации и зависимостей до логирования, загрузки аудио, управления очередью, команд Discord и GUI. Это позволяет легко поддерживать и расширять проект.
Документация кода:
Каждый модуль снабжен комментариями, описывающими его функции. Рекомендуется изучить код для понимания деталей работы.
Логи:
Логи записываются как в консоль, так и в файл bot.log. Также они отображаются в графическом интерфейсе через очередь логов.
Поддержка:
Если возникнут вопросы или проблемы, обратитесь к логам для диагностики ошибок. Вы также можете дорабатывать функции, учитывая комментарии в коде.
