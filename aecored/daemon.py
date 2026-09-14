"""Основной процесс-демон AECored."""

import argparse
import logging
import signal
import sys
import threading

from .config import Config, ConfigError
from .core_module import CoreModule
from .lifecycle import ModuleManager
from .process_name import set_process_name
from .systemd_watchdog import SystemdWatchdog


class AECored:
    """Основной объект демона и координатор его модулей."""

    def __init__(self, config_path):
        self.config = Config(config_path)
        self.logger = logging.getLogger("aecored")
        self.stop_event = threading.Event()
        self.module_manager = None
        self.watchdog = None

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

        self.module_manager = ModuleManager(self.config, self.logger)
        self.module_manager.register(CoreModule(self.config, self.logger))
        self.module_manager.initialize()

    def start(self):
        """Запустить демон и его модули."""
        self.module_manager.start()
        self.watchdog.ready()
        self.logger.info("AECored запущен, user_id=%s", self.config.user_id)

    def run(self):
        """Основной цикл демона."""
        while not self.stop_event.wait(10.0):
            self.watchdog.watchdog()

    def stop(self):
        """Корректно остановить демон."""
        if self.stop_event.is_set():
            return

        self.logger.info("Получена команда остановки AECored")
        self.stop_event.set()

        if self.module_manager is not None:
            self.module_manager.stop()
            self.module_manager.shutdown()

        if self.watchdog is not None:
            self.watchdog.shutdown()

        self.logger.info("AECored остановлен")


def configure_logging():
    """Настроить вывод логов демона в stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )


def install_signal_handlers(daemon):
    """Установить обработчики сигналов управления процессом."""
    def handle_signal(signum, _frame):
        # SIGKILL обработать программно невозможно — его обрабатывает systemd.
        if signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            daemon.stop()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGHUP, handle_signal)


def main(argv=None):
    """Точка входа AECored."""
    parser = argparse.ArgumentParser(description="AECored ActiV-Energy daemon")
    parser.add_argument(
        "config",
        nargs="?",
        default="config.ini",
        help="путь к файлу конфигурации",
    )
    args = parser.parse_args(argv)

    configure_logging()
    daemon = AECored(args.config)
    install_signal_handlers(daemon)

    try:
        daemon.initialize()
        daemon.start()
        daemon.run()
    except ConfigError as exc:
        logging.getLogger("aecored").error("Ошибка конфигурации: %s", exc)
        return 2
    except Exception:
        logging.getLogger("aecored").exception("Критическая ошибка AECored")
        return 1
    finally:
        daemon.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
