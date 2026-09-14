"""Управление жизненным циклом модулей AECored."""


class ModuleManager:
    """Инициализирует, запускает и останавливает модули."""

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.modules = []

    def register(self, module):
        """Зарегистрировать модуль."""
        self.modules.append(module)

    def initialize(self):
        """Инициализировать все зарегистрированные модули."""
        for module in self.modules:
            self.logger.info("Инициализация модуля %s", module.name)
            if not module.initialize():
                raise RuntimeError("Не удалось инициализировать модуль {}".format(module.name))

    def start(self):
        """Запустить все зарегистрированные модули."""
        started = []
        try:
            for module in self.modules:
                module.start()
                started.append(module)
        except Exception:
            # Уже запущенные модули останавливаем при частичном отказе запуска.
            for module in reversed(started):
                try:
                    module.stop()
                except Exception:
                    self.logger.exception("Ошибка остановки модуля %s", module.name)
            raise

    def stop(self):
        """Остановить все модули в обратном порядке."""
        for module in reversed(self.modules):
            try:
                module.stop()
            except Exception:
                self.logger.exception("Ошибка остановки модуля %s", module.name)

    def shutdown(self):
        """Освободить ресурсы всех модулей."""
        for module in reversed(self.modules):
            try:
                module.shutdown()
            except Exception:
                self.logger.exception("Ошибка завершения модуля %s", module.name)
