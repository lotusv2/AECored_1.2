"""Тестовая внешняя программа для проверки Scheduler и CFLogger."""

import os
import time

from aecored.cflogger import CFLogger
from aecored.config import Config


config_path = os.environ.get("AECOR_CONFIG_PATH", "config.ini")
config = Config(config_path)
config.load()
cflogger = CFLogger(config)
cflogger.initialize()
logger = cflogger.get_driver_logger("test_driver")

logger.info("Тестовый драйвер запущен")
time.sleep(2)
logger.info("Тестовый драйвер завершает работу")

cflogger.shutdown()
