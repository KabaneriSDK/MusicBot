import logging
import structlog
from logging.handlers import TimedRotatingFileHandler
from queue import Queue

# Очередь для логов, которую можно использовать в GUI
log_queue: Queue = Queue()

class UnifiedQueueHandler(logging.Handler):
    def __init__(self, formatter: logging.Formatter) -> None:
        super().__init__()
        self.setFormatter(formatter)
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            log_queue.put_nowait(msg)
        except Exception:
            self.handleError(record)

def setup_logging() -> None:
    timestamper = structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S")
    shared_processors = [
        timestamper,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(ensure_ascii=False)
    ]
    structlog.configure(
        processors=shared_processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logger_root = logging.getLogger()
    logger_root.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger_root.addHandler(console_handler)
    file_handler = TimedRotatingFileHandler("bot.log", when="midnight", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger_root.addHandler(file_handler)
    gui_handler = UnifiedQueueHandler(formatter)
    gui_handler.setLevel(logging.INFO)
    logger_root.addHandler(gui_handler)

setup_logging()
logger = structlog.get_logger()
