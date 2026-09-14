"""Управление именем процесса AECored в Linux."""

import ctypes
import ctypes.util


class ProcessNameError(RuntimeError):
    """Ошибка установки имени процесса."""


def set_process_name(user_id):
    """Установить системное имя процесса в формате ID_AECored."""
    name = "{}_AECored".format(user_id)

    # Linux ограничивает имя процесса, видимое через /proc/<pid>/comm,
    # длиной 15 байт без завершающего нулевого байта.
    if len(name.encode("utf-8")) > 15:
        raise ProcessNameError(
            "Имя процесса '{}' слишком длинное для Linux (максимум 15 байт)".format(name)
        )

    libc_name = ctypes.util.find_library("c")
    if not libc_name:
        raise ProcessNameError("Не удалось найти системную библиотеку libc")

    libc = ctypes.CDLL(libc_name, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int

    # PR_SET_NAME устанавливает имя текущего процесса/потока Linux.
    result = prctl(15, name.encode("utf-8"), 0, 0, 0)
    if result != 0:
        error_code = ctypes.get_errno()
        raise ProcessNameError(
            "Не удалось установить имя процесса '{}': errno {}".format(name, error_code)
        )

    return name
