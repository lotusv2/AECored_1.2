"""Планировщик запуска внешних Python-программ AECored."""

import os
import subprocess
import sys
import threading
from datetime import datetime

from .config import Config, ConfigError
from .cron_schedule import CronSchedule, CronScheduleError
from .module import Module


class SchedulerError(RuntimeError):
    """Ошибка планировщика."""


class ScheduledTask:
    """Описание задачи планировщика."""

    def __init__(self, name, command, schedule):
        self.name = name
        self.command = command
        self.schedule = schedule
        self.next_run = None


class Scheduler(Module):
    """Запускает внешние Python-программы по cron-расписанию."""

    name = "scheduler"
    CONFIG_CHECK_INTERVAL = 1.0

    def __init__(self, config, logger):
        super().__init__(config, logger)
        self._condition = threading.Condition()
        self._tasks = []
        self._thread = None
        self._stopping = False
        self._config_mtime = None

    def initialize(self):
        """Загрузить задачи из конфигурации и подготовить расписание."""
        tasks = self._build_tasks(self.config.tasks)

        with self._condition:
            self._tasks = tasks
            self._stopping = False
            self._config_mtime = self._get_config_mtime()
        return True

    def start(self):
        """Запустить поток планировщика."""
        with self._condition:
            if self.running:
                return
            self._stopping = False
            self.running = True
            self._thread = threading.Thread(
                target=self._run,
                name="aecored-scheduler",
                daemon=True,
            )
            self._thread.start()

        self.logger.info("Модуль %s запущен", self.name)

    def stop(self):
        """Остановить поток планировщика."""
        with self._condition:
            if not self.running:
                return
            self.running = False
            self._stopping = True
            self._condition.notify_all()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=10)

        self._thread = None
        self.logger.info("Модуль %s остановлен", self.name)

    def shutdown(self):
        """Освободить ресурсы планировщика."""
        self.stop()
        with self._condition:
            self._tasks = []
        return True

    def _run(self):
        while True:
            self._reload_config_if_changed()

            task = self._wait_for_task()
            if task is None:
                return

            self._start_task(task)
            self._schedule_next(task)

    def _wait_for_task(self):
        with self._condition:
            while not self._stopping:
                if not self._tasks:
                    self._condition.wait(timeout=self.CONFIG_CHECK_INTERVAL)
                    return None if self._stopping else self._check_and_continue()

                now = datetime.now()
                task = min(self._tasks, key=lambda item: item.next_run)
                delay = (task.next_run - now).total_seconds()

                if delay > 0:
                    self._condition.wait(
                        timeout=min(delay, self.CONFIG_CHECK_INTERVAL)
                    )
                    if self._stopping:
                        return None
                    if self._config_changed():
                        return None
                    continue

                return task

            return None

    def _check_and_continue(self):
        """Проверить конфигурацию после ожидания без задач."""
        if self._config_changed():
            return None
        return None

    def _reload_config_if_changed(self):
        """Перечитать задачи после изменения файла конфигурации."""
        if not self._config_changed():
            return False

        try:
            new_config = Config(self.config.path).load()
            tasks = self._build_tasks(new_config.tasks)
        except (ConfigError, CronScheduleError, SchedulerError):
            self.logger.exception(
                "Не удалось перечитать конфигурацию планировщика; "
                "продолжается работа с предыдущей конфигурацией"
            )
            self._config_mtime = self._get_config_mtime()
            return False

        with self._condition:
            self._tasks = tasks
            self._config_mtime = self._get_config_mtime()
            self._condition.notify_all()

        self.logger.info("Конфигурация планировщика перечитана")
        return True

    def _build_tasks(self, config_tasks):
        """Создать внутренние задачи из конфигурации."""
        now = datetime.now()
        tasks = []

        for item in config_tasks:
            if not item["enabled"]:
                self.logger.info("Задача %s отключена", item["name"])
                continue

            try:
                schedule = CronSchedule(item["schedule"])
                task = ScheduledTask(item["name"], item["command"], schedule)
                task.next_run = schedule.next_run(now)
            except CronScheduleError as exc:
                raise SchedulerError(
                    "Ошибка расписания задачи {}: {}".format(item["name"], exc)
                )

            tasks.append(task)
            self.logger.info(
                "Задача %s зарегистрирована, следующий запуск: %s",
                task.name,
                task.next_run.strftime("%Y-%m-%d %H:%M:%S"),
            )

        return tasks

    def _config_changed(self):
        """Проверить изменение времени модификации конфигурации."""
        current_mtime = self._get_config_mtime()
        return current_mtime != self._config_mtime

    def _get_config_mtime(self):
        """Получить время изменения файла конфигурации."""
        try:
            return os.stat(self.config.path).st_mtime_ns
        except OSError:
            return None

    def _start_task(self, task):
        """Запустить программу задачи и не ждать её завершения."""
        try:
            process = subprocess.Popen([sys.executable, task.command])
            self.logger.info(
                "Задача %s запущена: %s (PID=%s)",
                task.name,
                task.command,
                process.pid,
            )
        except OSError:
            self.logger.exception(
                "Не удалось запустить задачу %s: %s",
                task.name,
                task.command,
            )

    def _schedule_next(self, task):
        """Вычислить следующее время запуска задачи."""
        with self._condition:
            task.next_run = task.schedule.next_run(task.next_run)
            self._condition.notify()
