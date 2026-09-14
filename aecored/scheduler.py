"""Планировщик фоновых задач AECored."""

import heapq
import threading
import time

from .module import Module


class SchedulerError(RuntimeError):
    """Ошибка планировщика."""


class ScheduledTask:
    """Описание одной задачи планировщика."""

    def __init__(self, task_id, name, callback, interval=None, run_at=None):
        self.task_id = task_id
        self.name = name
        self.callback = callback
        self.interval = interval
        self.run_at = run_at
        self.cancelled = False


class Scheduler(Module):
    """Планировщик периодических и одноразовых фоновых задач."""

    name = "scheduler"

    def __init__(self, config, logger):
        super().__init__(config, logger)
        self._condition = threading.Condition()
        self._tasks = {}
        self._queue = []
        self._sequence = 0
        self._thread = None
        self._stopping = False

    def initialize(self):
        """Подготовить планировщик к запуску."""
        with self._condition:
            self._tasks.clear()
            self._queue = []
            self._sequence = 0
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

    def add_interval(self, name, interval, callback, immediate=False):
        """Добавить периодическую задачу и вернуть её идентификатор."""
        if interval <= 0:
            raise SchedulerError("Интервал задачи должен быть больше нуля")
        if not callable(callback):
            raise SchedulerError("callback задачи должен быть вызываемым объектом")

        first_run = time.monotonic()
        if not immediate:
            first_run += interval

        return self._add_task(
            name=name,
            callback=callback,
            interval=float(interval),
            run_at=first_run,
        )

    def add_once(self, name, delay, callback):
        """Добавить одноразовую задачу и вернуть её идентификатор."""
        if delay < 0:
            raise SchedulerError("Задержка задачи не может быть отрицательной")
        if not callable(callback):
            raise SchedulerError("callback задачи должен быть вызываемым объектом")

        return self._add_task(
            name=name,
            callback=callback,
            interval=None,
            run_at=time.monotonic() + float(delay),
        )

    def cancel(self, task_id):
        """Отменить задачу по идентификатору."""
        with self._condition:
            task = self._tasks.get(task_id)
            if task is None:
                return False

            task.cancelled = True
            del self._tasks[task_id]
            self._condition.notify()
            return True

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
            self._tasks.clear()
            self._queue = []
        return True

    def _add_task(self, name, callback, interval, run_at):
        with self._condition:
            self._sequence += 1
            task_id = self._sequence
            task = ScheduledTask(
                task_id=task_id,
                name=name,
                callback=callback,
                interval=interval,
                run_at=run_at,
            )
            self._tasks[task_id] = task
            heapq.heappush(self._queue, (run_at, task_id))
            self._condition.notify()
            return task_id

    def _run(self):
        while True:
            task = self._wait_for_task()
            if task is None:
                return

            try:
                task.callback()
            except Exception:
                self.logger.exception(
                    "Планировщик: ошибка выполнения задачи %s",
                    task.name,
                )

            if task.interval is not None:
                self._reschedule(task)
            else:
                with self._condition:
                    self._tasks.pop(task.task_id, None)

    def _wait_for_task(self):
        with self._condition:
            while not self._stopping:
                if not self._queue:
                    self._condition.wait()
                    continue

                run_at, task_id = self._queue[0]
                delay = run_at - time.monotonic()
                if delay > 0:
                    self._condition.wait(timeout=delay)
                    continue

                heapq.heappop(self._queue)
                task = self._tasks.get(task_id)
                if task is None or task.cancelled:
                    continue

                return task

            return None

    def _reschedule(self, task):
        with self._condition:
            if self._stopping or task.cancelled or task.task_id not in self._tasks:
                return

            task.run_at = time.monotonic() + task.interval
            heapq.heappush(self._queue, (task.run_at, task.task_id))
            self._condition.notify()
