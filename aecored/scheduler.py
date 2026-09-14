"""Планировщик запуска внешних Python-программ AECored."""

import os
import subprocess
import sys
import threading
from datetime import datetime

from .cron_schedule import CronSchedule, CronScheduleError
from .module import Module
from .scheduler_config import SchedulerConfig, SchedulerConfigError


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

    def __init__(self, config, logger, config_path):
        super().__init__(config, logger)
        self.config_path = config_path
        self._condition = threading.Condition()
        self._tasks = []
        self._thread = None
        self._stopping = False
        self._config_mtime = None

    def initialize(self):
        """Загрузить задачи из отдельной конфигурации Scheduler."""
        self._reload_config(initial=True)

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
            if self._check_config_changed():
                self._reload_config()

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
                    return None if self._stopping else self._wait_result_after_check()

                now = datetime.now()
                task = min(self._tasks, key=lambda item: item.next_run)
                delay = (task.next_run - now).total_seconds()

                if delay > 0:
                    self._condition.wait(
                        timeout=min(delay, self.CONFIG_CHECK_INTERVAL)
                    )
                    if self._stopping:
                        return None
                    if self._check_config_changed():
                        self._reload_config()
                    continue

                return task

            return None

    def _wait_result_after_check(self):
        """Проверить конфигурацию после ожидания."""
        if self._check_config_changed():
            self._reload_config()
        return None

    def _check_config_changed(self):
        """Проверить изменение файла конфигурации Scheduler."""
        current_mtime = self._get_config_mtime()
        return current_mtime != self._config_mtime

    def _get_config_mtime(self):
        try:
            return os.stat(self.config_path).st_mtime_ns
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
            task.next_run = task.schedule.next_run(datetime.now())
            self._condition.notify_all()

    def _reload_config(self, initial=False):
        """Перечитать конфигурацию Scheduler."""
        scheduler_config = SchedulerConfig(self.config_path)

        try:
            scheduler_config.load()
            now = datetime.now()
            tasks = []

            for item in scheduler_config.tasks:
                if not item["enabled"]:
                    self.logger.info("Задача %s отключена", item["name"])
                    continue

                schedule = CronSchedule(item["schedule"])
                task = ScheduledTask(item["name"], item["command"], schedule)
                task.next_run = schedule.next_run(now)
                tasks.append(task)

        except (SchedulerConfigError, CronScheduleError) as exc:
            if initial:
                raise SchedulerError(str(exc))

            self.logger.error(
                "Не удалось перечитать конфигурацию Scheduler: %s. "
                "Сохраняется предыдущая конфигурация.",
                exc,
            )
            self._config_mtime = self._get_config_mtime()
            return False

        with self._condition:
            self._tasks = tasks
            self._config_mtime = self._get_config_mtime()
            self._condition.notify_all()

        self.logger.info(
            "Конфигурация Scheduler %s: задач: %s",
            "загружена" if not initial else "инициализирована",
            len(tasks),
        )
        return True
