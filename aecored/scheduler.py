"""Планировщик запуска внешних Python-программ AECored."""

import configparser
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

    def __init__(self, config, logger, config_path, cflogger):
        super().__init__(config, logger)
        self.config_path = config_path
        self.cflogger = cflogger
        self._condition = threading.Condition()
        self._config_lock = threading.Lock()
        self._tasks = []
        self._thread = None
        self._stopping = False
        self._config_mtime = None

    def initialize(self):
        """Загрузить задачи из отдельной конфигурации Scheduler."""
        return self._reload_config(initial=True)

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

        self.logger.info("Scheduler: рабочий поток создаётся")
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

    def get_tasks(self):
        """Вернуть текущее состояние задач Scheduler."""
        with self._condition:
            return [
                {
                    "name": task.name,
                    "command": task.command,
                    "schedule": task.schedule.expression,
                    "next_run": task.next_run.isoformat() if task.next_run else None,
                }
                for task in self._tasks
            ]

    def add_task(self, name, command, schedule, enabled=True):
        """Добавить или заменить задачу и сохранить её в scheduler.ini."""
        if not name:
            raise ValueError("Имя задачи не может быть пустым")
        if "/" in name or "\\" in name or "[" in name or "]" in name:
            raise ValueError("Имя задачи содержит недопустимые символы")
        if not command:
            raise ValueError("Команда не может быть пустой")

        try:
            CronSchedule(schedule)
        except CronScheduleError as exc:
            raise ValueError(str(exc))

        with self._config_lock:
            parser = self._read_config_parser()
            section = "task:{}".format(name)
            parser[section] = {
                "enabled": "yes" if enabled else "no",
                "command": command,
                "schedule": schedule,
            }
            self._write_config_parser(parser)

        if not self._reload_config():
            raise ValueError("Не удалось применить новую задачу Scheduler")

        self.logger.info("Задача %s добавлена через HTTP-модуль", name)

        with self._condition:
            task = next((item for item in self._tasks if item.name == name), None)
            if task is None:
                raise ValueError("Задача не найдена после загрузки конфигурации")
            return {
                "name": task.name,
                "command": task.command,
                "schedule": task.schedule.expression,
                "next_run": task.next_run.isoformat() if task.next_run else None,
            }

    def remove_task(self, name):
        """Удалить задачу и сохранить изменение в scheduler.ini."""
        with self._config_lock:
            parser = self._read_config_parser()
            section = "task:{}".format(name)
            if not parser.has_section(section):
                raise KeyError(name)
            parser.remove_section(section)
            self._write_config_parser(parser)

        if not self._reload_config():
            raise ValueError("Не удалось применить удаление задачи Scheduler")

        self.logger.info("Задача %s удалена через HTTP-модуль", name)

    def _read_config_parser(self):
        """Загрузить scheduler.ini для изменения."""
        parser = configparser.ConfigParser()
        if not parser.read(self.config_path, encoding="utf-8"):
            raise ValueError(
                "Файл конфигурации Scheduler не найден: {}".format(self.config_path)
            )
        return parser

    def _write_config_parser(self, parser):
        """Сохранить scheduler.ini."""
        temporary_path = "{}.tmp".format(self.config_path)
        try:
            with open(temporary_path, "w", encoding="utf-8") as config_file:
                parser.write(config_file)
            os.replace(temporary_path, self.config_path)
        except OSError as exc:
            try:
                os.remove(temporary_path)
            except OSError:
                pass
            raise ValueError("Не удалось сохранить scheduler.ini: {}".format(exc))

    def _run(self):
        """Рабочий цикл Scheduler."""
        self.logger.info("Scheduler: рабочий цикл запущен")
        try:
            while True:
                if self._check_config_changed():
                    self.logger.info("Scheduler: обнаружено изменение конфигурации")
                    self._reload_config()

                task = self._wait_for_task()
                if task is None:
                    with self._condition:
                        if self._stopping:
                            self.logger.info("Scheduler: рабочий цикл остановлен")
                            return
                    continue

                self.logger.info(
                    "Scheduler: наступило время задачи '%s' (schedule=%s)",
                    task.name,
                    task.schedule.expression,
                )
                self._start_task(task)
                self._schedule_next(task)
        except Exception:
            self.logger.exception("Scheduler: критическая ошибка рабочего цикла")
            with self._condition:
                self.running = False

    def _wait_for_task(self):
        with self._condition:
            while not self._stopping:
                if not self._tasks:
                    self._condition.wait(timeout=self.config.scheduler_check_interval)
                    return None

                now = datetime.now()
                task = min(self._tasks, key=lambda item: item.next_run)
                delay = (task.next_run - now).total_seconds()

                if delay > 0:
                    self._condition.wait(
                        timeout=min(delay, self.config.scheduler_check_interval)
                    )
                    if self._stopping:
                        return None
                    return None

                return task

            return None

    def _check_config_changed(self):
        """Проверить изменение файла конфигурации Scheduler."""
        current_mtime = self._get_config_mtime()
        return current_mtime != self._config_mtime

    def _get_config_mtime(self):
        """Получить время изменения файла конфигурации."""
        try:
            return os.stat(self.config_path).st_mtime_ns
        except OSError:
            return None

    def _resolve_command_path(self, command):
        """Преобразовать путь задачи в абсолютный путь относительно корня AECored."""
        if os.path.isabs(command):
            return command
        return os.path.abspath(os.path.join(self.config.paths["root"], command))

    def _start_task(self, task):
        """Запустить программу задачи и не ждать её завершения."""
        command_path = self._resolve_command_path(task.command)
        self.logger.info(
            "Scheduler: запуск задачи '%s': python %s",
            task.name,
            command_path,
        )
        try:
            environment = self._build_task_environment(task)
            process = subprocess.Popen(
                [sys.executable, command_path],
                cwd=self.config.paths["root"],
                env=environment,
            )
            self.logger.info(
                "Scheduler: задача '%s' запущена, PID=%s",
                task.name,
                process.pid,
            )
            threading.Thread(
                target=self._wait_for_process,
                args=(task.name, process),
                name="aecored-task-{}".format(task.name),
                daemon=True,
            ).start()
        except OSError:
            self.logger.exception(
                "Scheduler: не удалось запустить задачу '%s': %s",
                task.name,
                command_path,
            )

    def _build_task_environment(self, task):
        """Подготовить окружение внешнего драйвера для CFLogger."""
        environment = os.environ.copy()
        environment["AECOR_CONFIG_PATH"] = self.config.path
        environment["AECOR_ROOT_PATH"] = self.cflogger.root_path

        python_path = environment.get("PYTHONPATH", "")
        paths = [self.cflogger.root_path]
        if python_path:
            paths.append(python_path)
        environment["PYTHONPATH"] = os.pathsep.join(paths)

        environment["AECOR_TASK_NAME"] = task.name
        return environment

    def _wait_for_process(self, task_name, process):
        """Дождаться завершения задачи и записать код возврата."""
        try:
            return_code = process.wait()
            self.logger.info(
                "Scheduler: задача '%s' завершена, код=%s, PID=%s",
                task_name,
                return_code,
                process.pid,
            )
        except Exception:
            self.logger.exception(
                "Scheduler: ошибка ожидания задачи '%s', PID=%s",
                task_name,
                process.pid,
            )

    def _schedule_next(self, task):
        """Вычислить следующее время запуска задачи."""
        with self._condition:
            task.next_run = task.schedule.next_run(datetime.now())
            self._condition.notify_all()
            self.logger.info(
                "Scheduler: следующая задача '%s' запланирована на %s",
                task.name,
                task.next_run.isoformat(),
            )

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
                self.logger.info(
                    "Scheduler: задача '%s' загружена, следующий запуск: %s",
                    task.name,
                    task.next_run.isoformat(),
                )

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
