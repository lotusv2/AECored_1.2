"""Планировщик запуска внешних Python-программ AECored."""

import subprocess
import sys
import threading
from datetime import datetime

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

    def __init__(self, config, logger):
        super().__init__(config, logger)
        self._condition = threading.Condition()
        self._tasks = []
        self._thread = None
        self._stopping = False

    def initialize(self):
        """Загрузить задачи из конфигурации и подготовить расписание."""
        now = datetime.now()
        tasks = []

        for item in self.config.tasks:
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

        with self._condition:
            self._tasks = tasks
            self._stopping = False
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
            task = self._wait_for_task()
            if task is None:
                return

            self._start_task(task)
            self._schedule_next(task)

    def _wait_for_task(self):
        with self._condition:
            while not self._stopping:
                if not self._tasks:
                    self._condition.wait()
                    continue

                now = datetime.now()
                task = min(self._tasks, key=lambda item: item.next_run)
                delay = (task.next_run - now).total_seconds()

                if delay > 0:
                    self._condition.wait(timeout=delay)
                    continue

                return task

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
