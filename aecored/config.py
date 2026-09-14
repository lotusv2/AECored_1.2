"""Загрузка конфигурации AECored."""

import configparser


class ConfigError(Exception):
    """Ошибка конфигурации AECored."""


class Config:
    """Конфигурация одного экземпляра AECored."""

    def __init__(self, path):
        self.path = path
        self.user_id = None

    def load(self):
        """Загрузить конфигурацию из INI-файла."""
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

        return self
