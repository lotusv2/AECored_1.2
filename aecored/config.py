"""Загрузка основной конфигурации AECored."""

import configparser
import os


class ConfigError(Exception):
    """Ошибка основной конфигурации AECored."""


class Config:
    """Единая конфигурация одного экземпляра AECored."""

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.user_id = None
        self.paths = {}
        self.modules = {}
        self.http_host = "0.0.0.0"
        self.http_baseport = 9000
        self.http_port = None
        self.http_password = None
        self.http_authentication = True
        self.scheduler_config = None
        self.scheduler_check_interval = 1.0
        self.logging = {}
        self.rabbitmq = {}
        self.rabbitmq_logging = {}

    def load(self):
        """Загрузить и проверить основную конфигурацию."""
        parser = configparser.ConfigParser()

        if not parser.read(self.path, encoding="utf-8"):
            raise ConfigError("Файл конфигурации не найден: {}".format(self.path))

        self._load_aecored(parser)
        self._load_paths(parser)
        self._load_modules(parser)
        self._load_http(parser)
        self._load_scheduler(parser)
        self._load_logging(parser)
        self._load_rabbitmq(parser)
        self._load_rabbitmq_logging(parser)
        self._validate()
        return self

    def _load_aecored(self, parser):
        """Загрузить идентификатор экземпляра."""
        if not parser.has_option("aecored", "user_id"):
            raise ConfigError("В конфигурации отсутствует параметр aecored.user_id")
        try:
            self.user_id = parser.getint("aecored", "user_id")
        except ValueError:
            raise ConfigError("Параметр aecored.user_id должен быть целым числом")
        if self.user_id < 1:
            raise ConfigError("Параметр aecored.user_id должен быть больше нуля")

    def _load_paths(self, parser):
        """Загрузить пути установки."""
        defaults = {
            "root": os.path.dirname(os.path.dirname(self.path)),
            "config": os.path.dirname(self.path),
            "logs": os.path.join(os.path.dirname(os.path.dirname(self.path)), "logs"),
            "drivers": os.path.join(os.path.dirname(os.path.dirname(self.path)), "drivers"),
            "data": os.path.join(os.path.dirname(os.path.dirname(self.path)), "data"),
            "run": os.path.join(os.path.dirname(os.path.dirname(self.path)), "run"),
        }
        for name, default in defaults.items():
            self.paths[name] = os.path.abspath(
                parser.get("paths", name, fallback=default).strip()
            )

    def _load_modules(self, parser):
        """Загрузить переключатели модулей."""
        for name in ("scheduler", "http", "rabbitmq"):
            try:
                self.modules[name] = parser.getboolean(
                    "modules", name, fallback=False
                )
            except ValueError:
                raise ConfigError(
                    "Параметр modules.{} имеет неверное значение".format(name)
                )

    def _load_http(self, parser):
        """Загрузить параметры HTTP-модуля."""
        self.http_host = parser.get("http", "host", fallback="0.0.0.0").strip()
        try:
            self.http_baseport = parser.getint("http", "baseport", fallback=9000)
            self.http_authentication = parser.getboolean(
                "http", "authentication", fallback=True
            )
        except ValueError:
            raise ConfigError("Неверное значение параметра HTTP")

        self.http_port = self.http_baseport + self.user_id
        self.http_password = parser.get(
            "http", "password", fallback="pass{}".format(self.user_id)
        ).strip()

    def _load_scheduler(self, parser):
        """Загрузить параметры Scheduler."""
        default_config = os.path.join(self.paths["config"], "scheduler.ini")
        self.scheduler_config = os.path.abspath(
            parser.get("scheduler", "config", fallback=default_config).strip()
        )
        try:
            self.scheduler_check_interval = parser.getfloat(
                "scheduler", "check_interval", fallback=1.0
            )
        except ValueError:
            raise ConfigError("Параметр scheduler.check_interval должен быть числом")

    def _load_logging(self, parser):
        """Загрузить параметры файлового логирования."""
        try:
            max_size = parser.getint("logging", "max_size", fallback=10485760)
            backup_count = parser.getint("logging", "backup_count", fallback=5)
        except ValueError:
            raise ConfigError("Неверное значение параметров logging.max_size или backup_count")

        self.logging = {
            "level": parser.get("logging", "level", fallback="INFO").strip().upper(),
            "encoding": parser.get("logging", "encoding", fallback="utf-8").strip(),
            "format": parser.get(
                "logging", "format",
                fallback="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            ),
            "max_size": max_size,
            "backup_count": backup_count,
        }

    def _load_rabbitmq(self, parser):
        """Загрузить параметры RabbitMQ."""
        try:
            port = parser.getint("rabbitmq", "port", fallback=5672)
        except ValueError:
            raise ConfigError("Параметр rabbitmq.port должен быть целым числом")
        self.rabbitmq = {
            "host": parser.get("rabbitmq", "host", fallback="127.0.0.1").strip(),
            "port": port,
            "virtual_host": parser.get("rabbitmq", "virtual_host", fallback="/").strip(),
            "username": parser.get("rabbitmq", "username", fallback="ae").strip(),
            "password": parser.get("rabbitmq", "password", fallback="").strip(),
        }

    def _load_rabbitmq_logging(self, parser):
        """Загрузить параметры передачи логов через RabbitMQ."""
        try:
            enabled = parser.getboolean(
                "rabbitmq_logging", "enabled", fallback=False
            )
        except ValueError:
            raise ConfigError("Параметр rabbitmq_logging.enabled имеет неверное значение")
        self.rabbitmq_logging = {
            "enabled": enabled,
            "exchange": parser.get("rabbitmq_logging", "exchange", fallback="ae.logging").strip(),
            "routing_key": parser.get("rabbitmq_logging", "routing_key", fallback="log").strip(),
            "queue": parser.get("rabbitmq_logging", "queue", fallback="cflogger").strip(),
        }

    def _validate(self):
        """Проверить значения, которые влияют на запуск экземпляра."""
        if not 1 <= self.http_port <= 65535:
            raise ConfigError(
                "Вычисленный HTTP-порт должен быть в диапазоне 1-65535: {}".format(
                    self.http_port
                )
            )
        if self.http_baseport < 0:
            raise ConfigError("Параметр http.baseport не может быть отрицательным")
        if self.http_authentication and not self.http_password:
            raise ConfigError("Параметр http.password не может быть пустым")
        if self.scheduler_check_interval <= 0:
            raise ConfigError("Параметр scheduler.check_interval должен быть больше нуля")
        if self.logging["max_size"] <= 0:
            raise ConfigError("Параметр logging.max_size должен быть больше нуля")
        if self.logging["backup_count"] < 0:
            raise ConfigError("Параметр logging.backup_count не может быть отрицательным")
        if self.rabbitmq_logging["enabled"] and not self.modules.get("rabbitmq", False):
            raise ConfigError(
                "rabbitmq_logging.enabled=yes требует modules.rabbitmq=yes"
            )
