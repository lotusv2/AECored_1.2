"""Главный модуль и демон AECored."""

import argparse
import signal
import sys
import time

from .cflogger import CFLogger
from .config import Config, ConfigError
from .http import HttpModule
from .lifecycle import ModuleManager
from .process_name import ProcessNameError, set_process_name
from .scheduler import Scheduler
from .systemd_watchdog import SystemdWatchdog


class AECored:
    """Главный объект демона AECored."""

    def __init__(self, config_path):
        self.config_path = config_path
        self.scheduler_config_path = self._get_scheduler_config_path(config_path)
        self.config = Config(config_path)
        self.cflogger = CFLogger(config_path)
        self.logger = None
        self.watchdog = None
        self.modules = None
        self.scheduler = None
        self.http = None
        self.running = False
        self._stopping = False

    @staticmethod
    def _get_scheduler_config_path(config_path):
        """Получить путь к отдельной конфигурации Scheduler."""
        import os

        directory = os.path.dirname(os.path.abspath(config_path))
        return os.path.join(directory, "scheduler.ini")

    def initialize(self):
        """Загрузить конфигурацию и инициализировать подсистемы."""
        self.config.load()

        # CFLogger является первым компонентом, который должен быть готов,
        # потому что остальные части ядра получают свои логгеры через него.
        self.cflogger.initialize()
        self.logger = self.cflogger.get_logger("aecored")

        process_name = set_process_name(self.config.user_id)
        self.logger.info(
            "AECored: инициализация, user_id=%s, process_name=%s",
            self.config.user_id,
            process_name,
        )

        self.watchdog = SystemdWatchdog(self.logger)
        self.watchdog.initialize()

        self.modules = ModuleManager(self.config, self.logger)
        self.scheduler = Scheduler(
            self.config,
            self.cflogger.get_logger("scheduler"),
            self.scheduler_config_path,
            self.cflogger,
        )
        self.http = HttpModule(
            self.config,
            self.cflogger.get_logger("http"),
            self.scheduler,
        )

        # CFLogger уже подготовлен до создания остальных модулей. Регистрация
        # в ModuleManager нужна для единого жизненного цикла подсистемы.
        self.modules.register(self.cflogger)
        self.modules.register(self.scheduler)
        self.modules.register(self.http)
        self.modules.initialize()

    def start(self):
        """Запустить все зарегистрированные модули."""
        if self.modules is None:
            raise RuntimeError("AECored не инициализирован")

        self.modules.start()
        self.running = True

        if self.watchdog is not None:
            self.watchdog.ready()

        self.logger.info("AECored: демон запущен")

    def run(self):
        """Выполнить основной цикл демона."""
        if not self.running:
            raise RuntimeError("AECored не запущен")

        while self.running:
            if self.watchdog is not None:
                self.watchdog.watchdog()
            time.sleep(10)

    def stop(self):
        """Остановить демон и все его модули."""
        if self._stopping:
            return

        self._stopping = True
        self.running = False
        if self.logger is not None:
            self.logger.info("AECored: остановка")

        if self.modules is not None:
            self.modules.stop()
            if self.logger is not None:
                self.logger.info("AECored: остановлен")
            self.modules.shutdown()
        elif self.logger is not None:
            self.logger.info("AECored: остановлен")

        if self.watchdog is not None:
            self.watchdog.shutdown()


def install_signal_handlers(daemon):
    """Установить обработчики сигналов завершения."""

    def handle_signal(signum, _frame):
        daemon.logger.info("AECored: получен сигнал %s", signum)
        daemon.stop()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)


def main(argv=None):
    """Точка входа для запуска AECored."""
    parser = argparse.ArgumentParser(description="AECored — ядро ActiV-Energy")
    parser.add_argument(
        "config",
        nargs="?",
        default="config.ini",
        help="путь к основной конфигурации AECored",
    )
    args = parser.parse_args(argv)

    daemon = AECored(args.config)

    try:
        install_signal_handlers(daemon)
        daemon.initialize()
        daemon.start()
        daemon.run()
    except (ConfigError, ProcessNameError, RuntimeError) as exc:
        if daemon.logger is not None:
            daemon.logger.error("AECored: критическая ошибка: %s", exc)
        else:
            print("AECored: критическая ошибка: {}".format(exc), file=sys.stderr)
        return 1
    except Exception:
        if daemon.logger is not None:
            daemon.logger.exception("AECored: непредвиденная ошибка")
        else:
            print("AECored: непредвиденная ошибка", file=sys.stderr)
        return 1
    finally:
        daemon.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
