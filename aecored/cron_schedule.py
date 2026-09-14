"""Разбор cron-выражений и вычисление следующего запуска."""

from datetime import timedelta


class CronScheduleError(ValueError):
    """Ошибка cron-выражения."""


class CronSchedule:
    """Простой cron-планировщик с пятью стандартными полями."""

    FIELD_LIMITS = (
        (0, 59),
        (0, 23),
        (1, 31),
        (1, 12),
        (0, 6),
    )

    def __init__(self, expression):
        self.expression = expression.strip()
        fields = self.expression.split()
        if len(fields) != 5:
            raise CronScheduleError("Cron-выражение должно содержать 5 полей")

        self._fields = []
        for value, limits in zip(fields, self.FIELD_LIMITS):
            self._fields.append(self._parse_field(value, limits))

    def next_run(self, after):
        """Вернуть ближайшее время запуска после указанного момента."""
        current = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(366 * 24 * 60 * 2):
            if self._matches(current):
                return current
            current += timedelta(minutes=1)

        raise CronScheduleError(
            "Не удалось вычислить следующее время запуска для: {}".format(
                self.expression
            )
        )

    def _matches(self, value):
        return (
            value.minute in self._fields[0]
            and value.hour in self._fields[1]
            and value.day in self._fields[2]
            and value.month in self._fields[3]
            and value.weekday() in self._fields[4]
        )

    @staticmethod
    def _parse_field(value, limits):
        minimum, maximum = limits
        result = set()

        for item in value.split(","):
            item = item.strip()
            if not item:
                raise CronScheduleError("Пустое поле cron-выражения")

            if "/" in item:
                base, step_text = item.split("/", 1)
                try:
                    step = int(step_text)
                except ValueError:
                    raise CronScheduleError(
                        "Неверный шаг cron-поля: {}".format(item)
                    )
                if step <= 0:
                    raise CronScheduleError(
                        "Шаг cron-поля должен быть больше нуля: {}".format(item)
                    )
            else:
                base = item
                step = 1

            if base == "*":
                start, end = minimum, maximum
            elif "-" in base:
                parts = base.split("-", 1)
                try:
                    start, end = int(parts[0]), int(parts[1])
                except ValueError:
                    raise CronScheduleError(
                        "Неверный диапазон cron-поля: {}".format(item)
                    )
            else:
                try:
                    start = end = int(base)
                except ValueError:
                    raise CronScheduleError(
                        "Неверное значение cron-поля: {}".format(item)
                    )

            if start < minimum or end > maximum or start > end:
                raise CronScheduleError(
                    "Значение cron-поля вне диапазона: {}".format(item)
                )

            result.update(range(start, end + 1, step))

        return frozenset(result)
