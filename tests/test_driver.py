"""Тестовая внешняя программа для проверки Scheduler."""

import logging
import time


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] test_driver: %(message)s",
)

logger = logging.getLogger("test_driver")
logger.info("Тестовый драйвер запущен")
time.sleep(2)
logger.info("Тестовый драйвер завершает работу")
