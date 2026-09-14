"""Загрузка отдельной конфигурации планировщика AECored."""

import configparser


class SchedulerConfigError(Exception):
    """Ошибка конфигурации планировщика."""


class SchedulerConfig:
    """Конфигурация задач Scheduler."""

    def __init__(self, path):
        self.path = path
        self.tasks = []

    def load(self):
        """Загрузить задачи из INI-файла планировщика."""
        parser = configparser.ConfigParser()

        if not parser.read(self.path, encoding="utf-8"):
            raise SchedulerConfigError(
                "Файл конфигурации Scheduler не найден: {}".format(self.path)
            )

        tasks = []

        for section in parser.sections():
            if not section.startswith("task:"):
                continue

            task_name = section[5:].strip()
            if not task_name:
                raise SchedulerConfigError(
                    "Имя задачи не может быть пустым: {}".format(section)
                )

            try:
                enabled = parser.getboolean(section, "enabled", fallback=True)
            except ValueError:
                raise SchedulerConfigError(
                    "Параметр enabled задачи {} имеет неверное значение".format(
                        task_name
                    )
                )

            command = parser.get(section, "command", fallback="").strip()
            schedule = parser.get(section, "schedule", fallback="").strip()

            if not command:
                raise SchedulerConfigError(
                    "В задаче {} отсутствует параметр command".format(task_name)
                )
            if not schedule:
                raise SchedulerConfigError(
                    "В задаче {} отсутствует параметр schedule".format(task_name)
                )

            tasks.append(
                {
                    "name": task_name,
                    "enabled": enabled,
                    "command": command,
                    "schedule": schedule,
                }
            )

        self.tasks = tasks
        return self
