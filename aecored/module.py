"""Базовый интерфейс модулей AECored."""


class Module:
    """Базовый класс подключаемого модуля."""

    name = "module"

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.running = False

    def initialize(self):
        """Подготовить модуль к запуску."""
        return True

    def start(self):
        """Запустить модуль."""
        self.running = True
        self.logger.info("Модуль %s запущен", self.name)

    def stop(self):
        """Остановить модуль."""
        self.running = False
        self.logger.info("Модуль %s остановлен", self.name)

    def shutdown(self):
        """Освободить ресурсы модуля."""
        return True
