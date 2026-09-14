"""Загрузка основной конфигурации AECored."""

import configparser


class ConfigError(Exception):
    """Ошибка основной конфигурации AECored."""


class Config:
    """Основная конфигурация одного экземпляра AECored."""

    def __init__(self, path):
        self.path = path
        self.user_id = None
        self.http_host = "0.0.0.0"
        self.http_port = None
        self.http_password = None

    def load(self):
        """Загрузить основную конфигурацию из INI-файла."""
        parser = configparser.ConfigParser()

        if not parser.read(self.path, encoding="utf-8"):
            raise ConfigError("Файл конфигурации не найден: {}".format(self.path))

        if not parser.has_option("aecored", "user_id"):
            raise ConfigError("В конфигурации отсутствует параметр aecored.user_id")

        try:
            self.user_id = parser.getint("aecored", "user_id")
        except ValueError:
            raise ConfigError("Параметр aecored.user_id должен быть целым числом")

        if self.user_id < 1:
            raise ConfigError("Параметр aecored.user_id должен быть больше нуля")

        self.http_host = parser.get("http", "host", fallback="0.0.0.0").strip()

        try:
            self.http_port = parser.getint(
                "http",
                "port",
                fallback=90000 + self.user_id,
            )
        except ValueError:
            raise ConfigError("Параметр http.port должен быть целым числом")

        if self.http_port < 1 or self.http_port > 65535:
            raise ConfigError("Параметр http.port должен быть в диапазоне 1-65535")

        self.http_password = parser.get(
            "http",
            "password",
            fallback="pass{}".format(self.user_id),
        ).strip()

        if not self.http_password:
            raise ConfigError("Параметр http.password не может быть пустым")

        return self
