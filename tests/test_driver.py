"""Тестовая внешняя программа для проверки Scheduler и CFLogger."""

import os
import time

from aecored.cflogger import CFLogger


config_path = os.environ.get("AECOR_CONFIG_PATH", "config.ini")
cflogger = CFLogger(config_path)
cflogger.initialize()
logger = cflogger.get_driver_logger("test_driver")

logger.info("Тестовый драйвер запущен")
time.sleep(2)
logger.info("Тестовый драйвер завершает работу")

cflogger.shutdown()
