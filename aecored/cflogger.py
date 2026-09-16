"""Локальная подсистема файлового логирования AECored."""

import logging
import os
from logging.handlers import RotatingFileHandler


class CFLoggerError(RuntimeError):
    """Ошибка подсистемы CFLogger."""


class CFLogger:
    """Управляет локальными логами ядра, модулей и драйверов."""

    name = "cflogger"

    def __init__(self, config):
        self.config = config
        self.root_path = config.paths["root"]
        self.logs_path = config.paths["logs"]
        self.drivers_path = config.paths["drivers"]
        self.running = False
        self._handlers = {}

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
        logger.setLevel(self._get_log_level())
        logger.propagate = False

        handler = RotatingFileHandler(
            log_path,
            maxBytes=self.config.logging["max_size"],
            backupCount=self.config.logging["backup_count"],
            encoding=self.config.logging["encoding"],
        )
        handler.setFormatter(logging.Formatter(self.config.logging["format"]))
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
            driver_root = os.path.join(self.drivers_path, driver_name)

        log_dir = os.path.join(driver_root, "logs")
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError as exc:
            raise CFLoggerError(
                "Не удалось создать каталог логов драйвера: {}".format(log_dir)
            ) from exc

        log_path = os.path.join(log_dir, "{}.log".format(driver_name))
        logger = logging.getLogger("AECored.driver.{}".format(driver_name))
        logger.setLevel(self._get_log_level())
        logger.propagate = False

        handler = RotatingFileHandler(
            log_path,
            maxBytes=self.config.logging["max_size"],
            backupCount=self.config.logging["backup_count"],
            encoding=self.config.logging["encoding"],
        )
        handler.setFormatter(logging.Formatter(self.config.logging["format"]))
        logger.addHandler(handler)
        self._handlers[key] = logger
        return logger

    def _get_log_level(self):
        """Получить числовой уровень логирования."""
        level_name = self.config.logging["level"]
        level = getattr(logging, level_name, None)
        if not isinstance(level, int):
            raise CFLoggerError(
                "Неизвестный уровень логирования: {}".format(level_name)
            )
        return level
