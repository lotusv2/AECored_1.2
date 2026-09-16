"""HTTP-модуль AECored на базе Flask."""

import hmac
import logging
import threading

from flask import Flask, jsonify, request

from .module import Module


class HttpModuleError(RuntimeError):
    """Ошибка HTTP-модуля."""


class HttpModule(Module):
    """Принимает команды для модулей AECored через HTTP."""

    name = "http"

    def __init__(self, config, logger, scheduler):
        super().__init__(config, logger)
        self.scheduler = scheduler
        self.app = Flask("AECored-HTTP")
        self._thread = None
        self._loggers = []
        self._configure_routes()

    def initialize(self):
        """Подготовить HTTP-модуль."""
        self._configure_logging()
        self.logger.info(
            "HTTP-модуль: host=%s, port=%s, авторизация=%s",
            self.config.http_host,
            self.config.http_port,
            "включена" if self.config.http_authentication else "отключена",
        )
        return True

    def start(self):
        """Запустить HTTP-сервер в отдельном потоке."""
        if self.running:
            return

        self.running = True
        self._thread = threading.Thread(
            target=self._run_server,
            name="aecored-http",
            daemon=True,
        )
        self._thread.start()
        self.logger.info(
            "Модуль %s запущен: %s:%s",
            self.name,
            self.config.http_host,
            self.config.http_port,
        )

    def stop(self):
        """Остановить HTTP-сервер."""
        self.running = False
        # Flask development server будет завершён вместе с daemon-потоком.
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None
        self.logger.info("Модуль %s остановлен", self.name)

    def shutdown(self):
        """Освободить ресурсы HTTP-модуля."""
        self.stop()
        self._remove_logging()
        return True

    def _configure_logging(self):
        """Перенаправить сообщения Flask и Werkzeug в лог HTTP-модуля."""
        handlers = list(self.logger.handlers)
        if not handlers:
            return

        for logger_name in ("werkzeug", "AECored-HTTP"):
            log = logging.getLogger(logger_name)
            log.setLevel(logging.INFO)
            log.propagate = False
            for handler in handlers:
                if handler not in log.handlers:
                    log.addHandler(handler)
                    self._loggers.append((log, handler))

    def _remove_logging(self):
        """Удалить обработчики HTTP-логирования."""
        for log, handler in self._loggers:
            if handler in log.handlers:
                log.removeHandler(handler)
        self._loggers = []

    def _run_server(self):
        """Запустить Flask без встроенного reloader."""
        try:
            self.app.run(
                host=self.config.http_host,
                port=self.config.http_port,
                debug=False,
                use_reloader=False,
                threaded=True,
            )
        except Exception:
            self.logger.exception("HTTP-модуль: ошибка Flask-сервера")
            self.running = False

    def _authorized(self):
        """Проверить HTTP Basic Authentication."""
        if not self.config.http_authentication:
            return True

        auth = request.authorization
        if auth is None:
            return False

        expected_user = str(self.config.user_id)
        expected_password = self.config.http_password

        return (
            hmac.compare_digest(auth.username or "", expected_user)
            and hmac.compare_digest(auth.password or "", expected_password)
        )

    def _unauthorized(self):
        """Вернуть ответ для неавторизованного запроса."""
        response = jsonify({"error": "Требуется авторизация"})
        response.status_code = 401
        response.headers["WWW-Authenticate"] = 'Basic realm="AECored"'
        return response

    def _configure_routes(self):
        """Зарегистрировать команды для модулей."""

        @self.app.before_request
        def require_authentication():
            if not self._authorized():
                return self._unauthorized()
            return None

        @self.app.route("/module/scheduler/tasks", methods=["GET"])
        def scheduler_tasks():
            """Получить список задач Scheduler."""
            return jsonify({"module": "scheduler", "tasks": self.scheduler.get_tasks()})

        @self.app.route("/module/scheduler/tasks", methods=["POST"])
        def scheduler_create_task():
            """Создать или заменить задачу Scheduler."""
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify({"error": "Требуется JSON-объект"}), 400

            required = ("name", "command", "schedule")
            missing = [field for field in required if not str(data.get(field, "")).strip()]
            if missing:
                return jsonify({"error": "Отсутствуют параметры: {}".format(", ".join(missing))}), 400

            try:
                task = self.scheduler.add_task(
                    name=str(data["name"]).strip(),
                    command=str(data["command"]).strip(),
                    schedule=str(data["schedule"]).strip(),
                    enabled=bool(data.get("enabled", True)),
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

            return jsonify({"module": "scheduler", "task": task}), 200

        @self.app.route("/module/scheduler/tasks/<task_name>", methods=["DELETE"])
        def scheduler_delete_task(task_name):
            """Удалить задачу Scheduler."""
            try:
                self.scheduler.remove_task(task_name)
            except KeyError:
                return jsonify({"error": "Задача не найдена"}), 404
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

            return jsonify({"module": "scheduler", "task": task_name, "removed": True})
