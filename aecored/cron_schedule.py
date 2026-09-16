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
        (0, 7),
    )

    def __init__(self, expression):
        self.expression = expression.strip()
        fields = self.expression.split()
        if len(fields) != 5:
            raise CronScheduleError("Cron-выражение должно содержать 5 полей")

        self._fields = []
        self._wildcards = []
        for value, limits in zip(fields, self.FIELD_LIMITS):
            self._fields.append(self._parse_field(value, limits))
            self._wildcards.append(value.strip() == "*")

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
        minute_matches = value.minute in self._fields[0]
        hour_matches = value.hour in self._fields[1]
        month_matches = value.month in self._fields[3]

        # Python: понедельник=0...воскресенье=6.
        # Cron: воскресенье=0 или 7, понедельник=1...суббота=6.
        cron_weekday = (value.weekday() + 1) % 7
        day_of_month_matches = value.day in self._fields[2]
        day_of_week_matches = cron_weekday in self._fields[4]

        if self._wildcards[2] or self._wildcards[4]:
            day_matches = day_of_month_matches and day_of_week_matches
        else:
            # Стандартная cron-семантика: при заданных обоих полях
            # задача запускается при совпадении любого из них.
            day_matches = day_of_month_matches or day_of_week_matches

        return (
            minute_matches
            and hour_matches
            and day_matches
            and month_matches
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

            values = range(start, end + 1, step)
            if maximum == 7:
                result.update(0 if item_value == 7 else item_value for item_value in values)
            else:
                result.update(values)

        return frozenset(result)
