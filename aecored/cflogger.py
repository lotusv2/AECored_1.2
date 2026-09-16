"""Локальная подсистема файлового логирования AECored."""

import logging
import os
from logging.handlers import RotatingFileHandler


class CFLoggerError(RuntimeError):
    """Ошибка подсистемы CFLogger."""


class CFLogger:
    """Управляет локальными логами ядра, модулей и драйверов."""

    name = "cflogger"
    MAX_BYTES = 10 * 1024 * 1024
    BACKUP_COUNT = 5
    ENCODING = "utf-8"
    FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    def __init__(self, config_path):
        self.config_path = os.path.abspath(config_path)
        self.root_path = self._get_root_path(self.config_path)
        self.logs_path = os.path.join(self.root_path, "logs")
        self.running = False
        self._handlers = {}

    @staticmethod
    def _get_root_path(config_path):
        """Определить корень установки по расположению config.ini."""
        config_dir = os.path.dirname(os.path.abspath(config_path))
        if os.path.basename(config_dir) == "config":
            parent_dir = os.path.dirname(config_dir)
            if os.path.basename(parent_dir) == "core":
                return os.path.dirname(parent_dir)
            return parent_dir
        return config_dir

    def initialize(self):
        """Подготовить каталог локальных логов."""
        try:
            os.makedirs(self.logs_path, exist_ok=True)
        except OSError as exc:
            raise CFLoggerError(
                "Не удалось создать каталог логов: {}".format(self.logs_path)
            ) from exc
        return True

    def start(self):
        """Запустить подсистему локального логирования."""
        self.running = True

    def stop(self):
        """Остановить подсистему локального логирования."""
        self.running = False

    def shutdown(self):
        """Закрыть обработчики файловых логов."""
        for logger in list(self._handlers.values()):
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)
        self._handlers.clear()
        return True

    def get_logger(self, name):
        """Получить логгер ядра или модуля."""
        if not name:
            raise ValueError("Имя логгера не может быть пустым")

        if name in self._handlers:
            return self._handlers[name]

        log_path = os.path.join(self.logs_path, "{}.log".format(name))
        logger = logging.getLogger("AECored.{}".format(name))
        logger.setLevel(logging.INFO)
        logger.propagate = False

        handler = RotatingFileHandler(
            log_path,
            maxBytes=self.MAX_BYTES,
            backupCount=self.BACKUP_COUNT,
            encoding=self.ENCODING,
        )
        handler.setFormatter(logging.Formatter(self.FORMAT))
        logger.addHandler(handler)
        self._handlers[name] = logger
        return logger

    def get_driver_logger(self, driver_name, driver_path=None):
        """Получить логгер драйвера в каталоге logs самого драйвера."""
        if not driver_name:
            raise ValueError("Имя драйвера не может быть пустым")

        key = "driver:{}".format(driver_name)
        if key in self._handlers:
            return self._handlers[key]

        if driver_path:
            driver_root = os.path.abspath(driver_path)
        else:
            driver_root = os.path.join(self.root_path, "drivers", driver_name)

        log_dir = os.path.join(driver_root, "logs")
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError as exc:
            raise CFLoggerError(
                "Не удалось создать каталог логов драйвера: {}".format(log_dir)
            ) from exc

        log_path = os.path.join(log_dir, "{}.log".format(driver_name))
        logger = logging.getLogger("AECored.driver.{}".format(driver_name))
        logger.setLevel(logging.INFO)
        logger.propagate = False

        handler = RotatingFileHandler(
            log_path,
            maxBytes=self.MAX_BYTES,
            backupCount=self.BACKUP_COUNT,
            encoding=self.ENCODING,
        )
        handler.setFormatter(logging.Formatter(self.FORMAT))
        logger.addHandler(handler)
        self._handlers[key] = logger
        return logger
