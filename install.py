"""Установщик и обновление экземпляра AECored для Debian Linux."""

import argparse
import configparser
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPOSITORY_URL = "https://github.com/lotusv2/AECored_1.2.git"
BASE_DIR = Path("/opt/actv-energy/aecored")
SYSTEMD_DIR = Path("/etc/systemd/system")


def require_root():
    """Проверить запуск установщика от root."""
    if os.geteuid() != 0:
        raise RuntimeError("Установщик должен быть запущен от root")


def check_python():
    """Проверить Python и при необходимости установить python3-venv."""
    if sys.version_info < (3, 7):
        raise RuntimeError("Требуется Python 3.7 или новее")

    try:
        import venv  # noqa: F401
    except ImportError:
        print("Не найден python3-venv. Устанавливаю пакет через apt...")
        run(["apt-get", "update"])
        run(["apt-get", "install", "-y", "python3-venv"])

        try:
            import venv  # noqa: F401
        except ImportError:
            raise RuntimeError("Не удалось установить python3-venv")


def check_command(command):
    """Проверить наличие системной команды."""
    if shutil.which(command) is None:
        raise RuntimeError("Не найдена системная команда: {}".format(command))


def run(command, cwd=None, check=True):
    """Выполнить системную команду."""
    return subprocess.run(command, cwd=cwd, check=check)


def run_optional(command, cwd=None):
    """Выполнить команду, не считая отсутствие сервиса ошибкой."""
    return run(command, cwd=cwd, check=False)


def validate_user_id(user_id):
    """Проверить идентификатор пользователя."""
    try:
        value = int(user_id)
    except (TypeError, ValueError):
        raise ValueError("user_id должен быть целым числом")

    if value < 1:
        raise ValueError("user_id должен быть больше нуля")

    return value


def service_name(user_id):
    """Получить имя systemd-сервиса."""
    return "{}_AECored.service".format(user_id)


def instance_dir(user_id):
    """Получить каталог экземпляра."""
    return BASE_DIR / str(user_id)


def write_config(path, user_id):
    """Создать конфигурацию экземпляра."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[aecored]\n"
        "# Идентификатор пользователя ActiV-Energy.\n"
        "user_id = {}\n".format(user_id),
        encoding="utf-8",
    )


def create_service(user_id, target_dir):
    """Создать systemd unit конкретного экземпляра."""
    name = service_name(user_id)
    python_path = target_dir / ".venv" / "bin" / "python"
    config_path = target_dir / "config.ini"

    content = """[Unit]
Description=ActiV-Energy AECored instance {user_id}
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
NotifyAccess=main
WorkingDirectory={target_dir}
ExecStart={python_path} -m aecored.aecored {config_path}
Restart=on-failure
RestartSec=5
WatchdogSec=30s
TimeoutStartSec=30s
TimeoutStopSec=30s
KillSignal=SIGTERM
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
""".format(
        user_id=user_id,
        target_dir=target_dir,
        python_path=python_path,
        config_path=config_path,
    )

    service_path = SYSTEMD_DIR / name
    service_path.write_text(content, encoding="utf-8")
    return service_path


def prepare_python_venv(target_dir):
    """Создать изолированное окружение Python для экземпляра."""
    run([sys.executable, "-m", "venv", str(target_dir / ".venv")])


def install_from_source(source_dir, user_id):
    """Установить AECored из локального дерева репозитория."""
    source_dir = Path(source_dir).resolve()
    source_package = source_dir / "aecored"
    source_config = source_dir / "config.ini"

    if not source_package.is_dir():
        raise RuntimeError("В исходном каталоге отсутствует aecored/")

    target_dir = instance_dir(user_id)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    run_optional(["systemctl", "stop", service_name(user_id)], cwd=source_dir)

    if target_dir.exists():
        shutil.rmtree(str(target_dir))

    target_dir.mkdir(parents=True)
    shutil.copytree(str(source_package), str(target_dir / "aecored"))

    if source_config.exists():
        shutil.copy2(str(source_config), str(target_dir / "config.ini"))
    else:
        write_config(target_dir / "config.ini", user_id)

    write_config(target_dir / "config.ini", user_id)
    prepare_python_venv(target_dir)
    create_service(user_id, target_dir)

    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", service_name(user_id)])
    run(["systemctl", "start", service_name(user_id)])


def clone_repository():
    """Загрузить свежую версию репозитория во временный каталог."""
    temp_dir = Path(tempfile.mkdtemp(prefix="aecored-update-"))
    try:
        run(["git", "clone", "--depth", "1", REPOSITORY_URL, str(temp_dir / "repo")])
        return temp_dir / "repo", temp_dir
    except Exception:
        shutil.rmtree(str(temp_dir), ignore_errors=True)
        raise


def update_instance(user_id):
    """Остановить экземпляр и заменить его код свежей версией GitHub."""
    user_id = validate_user_id(user_id)
    target_dir = instance_dir(user_id)
    config_path = target_dir / "config.ini"

    if not target_dir.exists():
        raise RuntimeError("Экземпляр {} не установлен".format(user_id))

    preserved_config = None
    if config_path.exists():
        preserved_config = config_path.read_text(encoding="utf-8")

    repo_dir, temp_dir = clone_repository()
    try:
        run(["systemctl", "stop", service_name(user_id)])
        run_optional(["systemctl", "disable", service_name(user_id)])

        if target_dir.exists():
            shutil.rmtree(str(target_dir))

        target_dir.mkdir(parents=True)
        shutil.copytree(str(repo_dir / "aecored"), str(target_dir / "aecored"))

        if preserved_config is not None:
            config_path.write_text(preserved_config, encoding="utf-8")
        else:
            write_config(config_path, user_id)

        prepare_python_venv(target_dir)
        create_service(user_id, target_dir)
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "enable", service_name(user_id)])
        run(["systemctl", "start", service_name(user_id)])
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)


def remove_instance(user_id):
    """Полностью удалить экземпляр и его systemd-сервис."""
    user_id = validate_user_id(user_id)
    name = service_name(user_id)
    target_dir = instance_dir(user_id)
    service_path = SYSTEMD_DIR / name

    run_optional(["systemctl", "stop", name])
    run_optional(["systemctl", "disable", name])

    if service_path.exists():
        service_path.unlink()

    if target_dir.exists():
        shutil.rmtree(str(target_dir))

    run(["systemctl", "daemon-reload"])


def main():
    """Главная функция установщика."""
    parser = argparse.ArgumentParser(description="AECored installer")
    subparsers = parser.add_subparsers(dest="command")

    install_parser = subparsers.add_parser("install", help="установить экземпляр")
    install_parser.add_argument("user_id", type=int)
    install_parser.add_argument(
        "--source",
        default=str(Path(__file__).resolve().parent),
        help="локальный каталог исходного репозитория",
    )

    update_parser = subparsers.add_parser("update", help="обновить экземпляр из GitHub")
    update_parser.add_argument("user_id", type=int)

    remove_parser = subparsers.add_parser("remove", help="удалить экземпляр")
    remove_parser.add_argument("user_id", type=int)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    require_root()
    check_python()
    check_command("systemctl")

    if args.command == "install":
        install_from_source(args.source, validate_user_id(args.user_id))
    elif args.command == "update":
        check_command("git")
        update_instance(validate_user_id(args.user_id))
    elif args.command == "remove":
        remove_instance(validate_user_id(args.user_id))

    print("AECored: операция {} завершена для user_id={}".format(args.command, args.user_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
