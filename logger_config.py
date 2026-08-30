import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import List

from collections import deque
import threading

class RecentLogHandler(logging.Handler):
    """In-memory ring buffer storing the last 50 log messages for Telegram live debug UI."""
    recent_logs: deque = deque(maxlen=50)
    _lock = threading.Lock()

    def emit(self, record):
        try:
            msg = self.format(record)
            with RecentLogHandler._lock:
                RecentLogHandler.recent_logs.append(msg)
        except Exception:
            pass

def init_logging(log_file: str = "aggregator.log", level: str = "INFO"):
    """
    Centralized logging initializer.
    Outputs detailed logs with line numbers & timestamps to Console, File, and Memory.
    """
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return root_logger

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    log_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Console Stream Handler (stdout)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(log_formatter)
    root_logger.addHandler(stream_handler)

    # 2. In-memory handler for Telegram /logs dashboard
    recent_handler = RecentLogHandler()
    recent_handler.setFormatter(log_formatter)
    root_logger.addHandler(recent_handler)

    # 3. Rotating File Handler (app.log)
    try:
        file_handler = RotatingFileHandler("app.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(log_formatter)
        
        class AppFilter(logging.Filter):
            def filter(self, record):
                return not (record.name.startswith("master_bot") or 
                            record.name.startswith("aiogram") or 
                            record.name.startswith("user_agent") or 
                            record.name.startswith("bot_handlers"))
                            
        file_handler.addFilter(AppFilter())
        root_logger.addHandler(file_handler)
    except Exception as e:
        sys.stderr.write(f"Warning: Could not initialize file logging: {e}\n")

    # 4. Dedicated Bot Log File (bot.log)
    try:
        bot_file_handler = RotatingFileHandler("bot.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
        bot_file_handler.setFormatter(log_formatter)
        
        class BotFilter(logging.Filter):
            def filter(self, record):
                return (record.name.startswith("master_bot") or 
                        record.name.startswith("aiogram") or 
                        record.name.startswith("user_agent") or 
                        record.name.startswith("bot_handlers"))
                
        bot_file_handler.addFilter(BotFilter())
        root_logger.addHandler(bot_file_handler)
    except Exception as e:
        sys.stderr.write(f"Warning: Could not initialize bot file logging: {e}\n")

    return root_logger
