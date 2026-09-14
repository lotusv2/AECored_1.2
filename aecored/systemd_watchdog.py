"""Минимальная интеграция с systemd watchdog без внешних зависимостей."""

import os
import socket


class SystemdWatchdog:
    """Отправляет READY/WATCHDOG уведомления в systemd."""

    def __init__(self, logger):
        self.logger = logger
        self.notify_socket = os.environ.get("NOTIFY_SOCKET")
        self.socket = None

    def initialize(self):
        """Подготовить Unix-сокет systemd, если он передан окружением."""
        if not self.notify_socket:
            self.logger.info("NOTIFY_SOCKET не задан; watchdog systemd отключен")
            return True

        address = self.notify_socket
        if address.startswith("@"):  # Абстрактный Unix-сокет Linux.
            address = "\0" + address[1:]

        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.notify_socket = address
        return True

    def notify(self, message):
        """Отправить уведомление systemd."""
        if self.socket is None:
            return

        try:
            self.socket.sendto(message.encode("utf-8"), self.notify_socket)
        except OSError:
            self.logger.exception("Ошибка отправки уведомления systemd")

    def ready(self):
        """Сообщить systemd об успешной инициализации."""
        self.notify("READY=1")

    def watchdog(self):
        """Сообщить systemd, что демон продолжает работать."""
        self.notify("WATCHDOG=1")

    def shutdown(self):
        """Закрыть Unix-сокет."""
        if self.socket is not None:
            self.socket.close()
            self.socket = None
