# AECored_1.2

Ядро системы учета энергии ActiV-Energy.

Рабочая заготовка ядра построена как модульное приложение Python 3.7+ для Debian Linux. Установка, обновление и удаление экземпляра выполняются внешним установщиком AEInstall.

## Текущая структура

```text
AECored_1.2/
├── aecored/
│   ├── __init__.py
│   ├── aecored.py             # Главный модуль и точка входа
│   ├── config.py              # Загрузка и проверка конфигурации
│   ├── module.py              # Базовый интерфейс модулей
│   ├── lifecycle.py           # Жизненный цикл модулей
│   ├── core_module.py         # Минимальный внутренний модуль ядра
│   ├── systemd_watchdog.py    # Интеграция с watchdog systemd
│   └── process_name.py        # Установка имени процесса Linux
├── config/
│   └── config.ini             # Шаблон основной конфигурации
├── tests/
├── requirements.txt
└── .gitignore
```

## Конфигурация

Основной шаблон конфигурации хранится в `config/config.ini`. Он используется как единый шаблон для установщика AEInstall.

При установке AEInstall копирует этот шаблон в конфигурацию конкретного экземпляра и подставляет параметры клиента, включая `user_id` и пути установки.

Пример:

```ini
[aecored]
user_id = 10

[paths]
root = /home/activ-energy
config = /home/activ-energy/config
logs = /home/activ-energy/logs
drivers = /home/activ-energy/drivers
data = /home/activ-energy/data
run = /home/activ-energy/run
```

Для ручного запуска можно явно указать путь к конфигурации:

```bash
python3 -m aecored.aecored /path/to/aecored.ini
```
