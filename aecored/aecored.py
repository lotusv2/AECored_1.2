"""Главный модуль и демон AECored."""

import argparse
import logging
import signal
import sys
import time

from .config import Config, ConfigError
from .core_module import CoreModule
from .lifecycle import ModuleManager
from .process_name import ProcessNameError, set_process_name
from .systemd_watchdog import SystemdWatchdog


class AECored:
    """Главный объект демона AECored."""

    def __init__(self, config_path):
        self.config_path = config_path
        self.config = Config(config_path)
        self.logger = logging.getLogger("AECored")
        self.watchdog = None
        self.modules = None
        self.running = False
        self._stopping = False

    def initialize(self):
        """Загрузить конфигурацию и инициализировать подсистемы."""
        self.config.load()

        process_name = set_process_name(self.config.user_id)
        self.logger.info(
            "AECored: инициализация, user_id=%s, process_name=%s",
            self.config.user_id,
            process_name,
        )

        self.watchdog = SystemdWatchdog(self.logger)
        self.watchdog.initialize()

        self.modules = ModuleManager(self.config, self.logger)
        self.modules.register(CoreModule(self.config, self.logger))
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
        self.logger.info("AECored: остановка")

        if self.modules is not None:
            self.modules.stop()
            self.modules.shutdown()

        if self.watchdog is not None:
            self.watchdog.shutdown()

        self.logger.info("AECored: остановлен")


def configure_logging():
    """Настроить вывод журнала демона."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


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
        help="путь к конфигурационному файлу",
    )
    args = parser.parse_args(argv)

    configure_logging()
    daemon = AECored(args.config)

    try:
        install_signal_handlers(daemon)
        daemon.initialize()
        daemon.start()
        daemon.run()
    except (ConfigError, ProcessNameError, RuntimeError) as exc:
        daemon.logger.error("AECored: критическая ошибка: %s", exc)
        return 1
    except Exception:
        daemon.logger.exception("AECored: непредвиденная ошибка")
        return 1
    finally:
        daemon.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
