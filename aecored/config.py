"""Загрузка конфигурации AECored."""

import configparser


class ConfigError(Exception):
    """Ошибка конфигурации AECored."""


class Config:
    """Конфигурация одного экземпляра AECored."""

    def __init__(self, path):
        self.path = path
        self.user_id = None
        self.tasks = []

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

        self.tasks = []
        for section in parser.sections():
            if not section.startswith("task:"):
                continue

            task_name = section[5:].strip()
            if not task_name:
                raise ConfigError("Имя задачи не может быть пустым: {}".format(section))

            try:
                enabled = parser.getboolean(section, "enabled", fallback=True)
            except ValueError:
                raise ConfigError(
                    "Параметр enabled задачи {} имеет неверное значение".format(task_name)
                )

            command = parser.get(section, "command", fallback="").strip()
            schedule = parser.get(section, "schedule", fallback="").strip()

            if not command:
                raise ConfigError(
                    "В задаче {} отсутствует параметр command".format(task_name)
                )
            if not schedule:
                raise ConfigError(
                    "В задаче {} отсутствует параметр schedule".format(task_name)
                )

            self.tasks.append(
                {
                    "name": task_name,
                    "enabled": enabled,
                    "command": command,
                    "schedule": schedule,
                }
            )

        return self
