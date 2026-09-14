"""Минимальный системный модуль AECored."""

import threading

from .module import Module


class CoreModule(Module):
    """Проверяет, что внутренний цикл AECored работает."""

    name = "core"

    def __init__(self, config, logger):
        super().__init__(config, logger)
        self._stop_event = threading.Event()
        self._thread = None
        self._heartbeat = 0

    def initialize(self):
        """Подготовить внутренний цикл ядра."""
        self._heartbeat = 0
        return True

    def start(self):
        """Запустить внутренний поток ядра."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="aecored-core",
            daemon=True,
        )
        self._thread.start()
        self.running = True
        self.logger.info("Основной модуль AECored запущен")

    def _run(self):
        """Выполнять базовый цикл ядра."""
        while not self._stop_event.wait(1.0):
            self._heartbeat += 1

    def is_alive(self):
        """Вернуть состояние внутреннего потока ядра."""
        return self._thread is not None and self._thread.is_alive()

    def stop(self):
        """Остановить внутренний поток ядра."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self.running = False
        self.logger.info("Основной модуль AECored остановлен")

    def shutdown(self):
        """Освободить ресурсы основного модуля."""
        self._thread = None
