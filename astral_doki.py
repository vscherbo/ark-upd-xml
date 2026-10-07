#!/usr/bin/env python
"""Модуль для работы с API Астрал.Доки.

Реализованы:
- авторизация по email/паролю (POST /api/v2/auth/byLogin);
- обновление access-токена по refresh-токену (тот же метод);
- получение списка ИдЭДО контрагента (GET /async/v1/counterparties/{inn}/globalId)
  — ответ синхронный (StringResultList);
- ожидание результата асинхронных операций через ленту событий
  (GET /async/v1/counterparties/newEvents) — для будущих методов;
- вспомогательный метод получения статуса процесса
  (GET /async/v1/processes/{processId}).

Пароль и прочие секреты читаются из .env.
CLI: --inn, --kpp.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

LOG_FORMAT = '[%(filename)-22s:%(lineno)4s - %(funcName)-20s()] \
            %(levelname)-7s | %(asctime)-15s | %(message)s'

# --------------------------------------------------------------------------- #
# Исключения
# --------------------------------------------------------------------------- #


class AstralDocsError(Exception):
    """Базовое исключение модуля."""


class AstralAuthError(AstralDocsError):
    """Ошибка аутентификации/авторизации."""


class AstralApiError(AstralDocsError):
    """Ошибка HTTP-ответа API."""

    def __init__(self, status_code: int, message: str, response_body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class AstralProcessError(AstralDocsError):
    """Асинхронный процесс завершился с ошибкой или не дождались события."""


class AstralValidationError(AstralDocsError):
    """Ошибка валидации входных аргументов."""


# --------------------------------------------------------------------------- #
# Клиент
# --------------------------------------------------------------------------- #

class AstralDocsClient:
    """Клиент API Астрал.Доки."""

    DEFAULT_BASE_URL = "https://api.doc.astral.ru"
    DEFAULT_TIMEOUT = 30
    DEFAULT_TOKEN_REFRESH_MARGIN = 60          # секунд
    DEFAULT_EVENT_WAIT_TIMEOUT = 300           # секунд
    DEFAULT_EVENT_POLL_INTERVAL = 5            # секунд

    LOGIN_PATH = "/api/v2/auth/byLogin"
    COUNTERPARTY_GLOBAL_ID_PATH = "/async/v1/counterparties/{inn}/globalId"
    COUNTERPARTY_EVENTS_PATH = "/async/v1/counterparties/newEvents"
    PROCESS_STATUS_PATH = "/async/v1/processes/{process_id}"

    def __init__(
        self,
        email: str,
        password: str,
        abonent_id: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        token_refresh_margin: int = DEFAULT_TOKEN_REFRESH_MARGIN,
    ) -> None:
        self.email = email
        self.password = password
        self.abonent_id = abonent_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token_refresh_margin = token_refresh_margin

        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.access_token_valid_before: Optional[datetime] = None

        self._session = requests.Session()

    # ------------------------------------------------------------------ #
    # Вспомогательное
    # ------------------------------------------------------------------ #

    @staticmethod
    def _mask_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        if not headers:
            return {}
        masked = dict(headers)
        if "Authorization" in masked:
            masked["Authorization"] = "Bearer ***"
        return masked

    @staticmethod
    def _sanitize_json(payload: Any) -> Any:
        if isinstance(payload, dict):
            sanitized = dict(payload)
            for secret_key in ("password", "refreshToken"):
                if secret_key in sanitized:
                    sanitized[secret_key] = "***"
            return sanitized
        return payload

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized)
        except ValueError:
            logger.warning("Не удалось распарсить дату: %s", value)
            return None

    # ------------------------------------------------------------------ #
    # Низкоуровневые HTTP-обёртки
    # ------------------------------------------------------------------ #

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        with_auth: bool = True,
        with_abonent: bool = True,
        stream: bool = False,
    ) -> requests.Response:
        url = self.base_url + path
        headers: Dict[str, str] = {"Accept": "application/json"}

        if with_auth:
            self._ensure_valid_token()
            if self.access_token:
                headers["Authorization"] = "Bearer " + self.access_token

        if with_abonent:
            headers["abonentId"] = self.abonent_id

        if json_body is not None and files is None:
            headers["Content-Type"] = "application/json"

        logger.debug(
            "HTTP-запрос: %s %s params=%s headers=%s json=%s",
            method,
            url,
            params,
            self._mask_headers(headers),
            self._sanitize_json(json_body),
        )

        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_body,
                files=files,
                timeout=self.timeout,
                stream=stream,
            )
        except RequestException as exc:
            logger.error("Сетевая ошибка при вызове %s %s: %s", method, url, exc)
            raise AstralApiError(0, "Сетевая ошибка: %s" % exc) from exc

        self._log_response(response)
        return response

    @staticmethod
    def _log_response(response: requests.Response) -> None:
        try:
            body = response.text
        except Exception:  # noqa: BLE001
            body = "<не удалось прочитать тело ответа>"

        truncated = body if len(body) <= 4000 else body[:4000] + "...<обрезано>"
        logger.debug(
            "HTTP-ответ: status=%s url=%s body=%s",
            response.status_code,
            response.url,
            truncated,
        )

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        if response.status_code < 400:
            return

        message = "HTTP %s" % response.status_code
        body: Any = None
        try:
            body = response.json()
        except ValueError:
            body = response.text

        if isinstance(body, dict):
            detail = (
                body.get("message")
                or body.get("error")
                or body.get("error_description")
            )
            if detail:
                message = "%s: %s" % (message, detail)

        logger.error("Ошибка API: status=%s body=%s", response.status_code, body)

        if response.status_code in (401, 403):
            raise AstralAuthError(message)
        raise AstralApiError(response.status_code, message, body)

    # ------------------------------------------------------------------ #
    # Авторизация и токены
    # ------------------------------------------------------------------ #

    def _ensure_valid_token(self) -> None:
        if not self.access_token:
            self.authenticate()
            return

        if self.access_token_valid_before is None:
            return

        tz = self.access_token_valid_before.tzinfo or timezone.utc
        now = datetime.now(tz=tz)
        if self.access_token_valid_before - now <= timedelta(
            seconds=self.token_refresh_margin
        ):
            logger.info(
                "Access-токен истекает в %s, обновляем заранее",
                self.access_token_valid_before,
            )
            self.refresh_access_token()

    def authenticate(self) -> None:
        logger.info("Авторизация по email=%s", self.email)
        payload = {"email": self.email, "password": self.password}
        response = self._request(
            "POST",
            self.LOGIN_PATH,
            json_body=payload,
            with_auth=False,
            with_abonent=False,
        )
        self._raise_for_status(response)
        self._store_tokens(self._safe_json(response))

    def refresh_access_token(self) -> None:
        if not self.refresh_token:
            logger.warning("refresh_token отсутствует, выполняем полную авторизацию")
            self.authenticate()
            return

        logger.info("Обновление access-токена по refresh_token")
        payload = {"refreshToken": self.refresh_token}
        response = self._request(
            "POST",
            self.LOGIN_PATH,
            json_body=payload,
            with_auth=False,
            with_abonent=False,
        )
        self._raise_for_status(response)
        self._store_tokens(self._safe_json(response))

    @staticmethod
    def _safe_json(response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise AstralApiError(
                response.status_code,
                "Ответ авторизации не является JSON: %s" % response.text[:200],
                response.text,
            ) from exc

    def _store_tokens(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            raise AstralAuthError("Неожиданный ответ авторизации: %r" % (payload,))

        access = payload.get("accessToken")
        refresh = payload.get("refreshToken")
        valid_before = payload.get("validBefore")

        if not access:
            raise AstralAuthError("В ответе отсутствует accessToken: %r" % (payload,))

        self.access_token = access
        if refresh:
            self.refresh_token = refresh
        self.access_token_valid_before = self._parse_datetime(valid_before)

        logger.info(
            "Токены получены, access_token действует до %s",
            self.access_token_valid_before,
        )

    # ------------------------------------------------------------------ #
    # Контрагенты: получение ИдЭДО
    # ------------------------------------------------------------------ #

    def get_counterparty_global_ids(
        self,
        inn: str,
        kpp: Optional[str] = None,
        *,
        wait_timeout: int = DEFAULT_EVENT_WAIT_TIMEOUT,
        poll_interval: int = DEFAULT_EVENT_POLL_INTERVAL,
        date_from: Optional[datetime] = None,
    ) -> List[str]:
        """Получить список ИдЭДО контрагента по ИНН/КПП.

        Ответ метода синхронный (StringResultList). Оставлена и ветка для
        асинхронного ответа (processId + ожидание события) — на случай,
        если поведение метода изменится или понадобится другим методам.

        :param inn: ИНН контрагента (10 цифр — ЮЛ, 12 — ИП/ФЛ).
        :param kpp: КПП контрагента (обязателен для ЮЛ).
        """
        if date_from is None:
            date_from = datetime.now(tz=timezone.utc) - timedelta(hours=1)

        params: Dict[str, Any] = {}
        if kpp:
            params["kpp"] = kpp

        path = self.COUNTERPARTY_GLOBAL_ID_PATH.format(inn=inn)
        response = self._request("GET", path, params=params)
        self._raise_for_status(response)

        raw_text = response.text
        logger.debug("globalId: сырой ответ (len=%s): %s", len(raw_text), raw_text)

        try:
            body: Any = response.json()
        except ValueError as exc:
            raise AstralApiError(
                response.status_code,
                "Ответ globalId не является JSON: %s" % raw_text[:200],
                raw_text,
            ) from exc

        logger.debug("globalId: разобранный JSON: %r", body)

        # Вариант A: синхронный ответ {"count": N, "data": [...]}
        if isinstance(body, dict) and "data" in body and "count" in body:
            data = body.get("data") or []
            logger.info("globalId: синхронный ответ, ИдЭДО=%s", data)
            return [str(item) for item in data]

        # Вариант B: асинхронный ответ — processId (на будущее)
        process_id = self._extract_process_id(body)
        if not process_id:
            raise AstralApiError(
                response.status_code,
                "Не удалось распознать ответ globalId: %r" % (body,),
                body,
            )

        logger.info("globalId: запущен процесс processId=%s", process_id)
        event = self._wait_for_counterparty_event(
            process_id=process_id,
            date_from=date_from,
            wait_timeout=wait_timeout,
            poll_interval=poll_interval,
        )
        return self._extract_global_ids_from_event(event)

    @staticmethod
    def _extract_process_id(body: Any) -> Optional[str]:
        if isinstance(body, str) and body:
            return body
        if isinstance(body, dict):
            for key in ("processId", "processID", "process_id"):
                value = body.get(key)
                if isinstance(value, str) and value:
                    return value
        return None

    def get_counterparties_events(
        self,
        *,
        date_from: datetime,
        date_to: Optional[datetime] = None,
        process_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "dateFrom": date_from.isoformat(),
            "limit": limit,
            "offset": offset,
        }
        if date_to is not None:
            params["dateTo"] = date_to.isoformat()
        if process_id:
            params["processId"] = process_id
        if entity_id:
            params["entityId"] = entity_id
        if event_type:
            params["eventType"] = event_type

        response = self._request(
            "GET",
            self.COUNTERPARTY_EVENTS_PATH,
            params=params,
        )
        self._raise_for_status(response)

        try:
            body: Any = response.json()
        except ValueError as exc:
            raise AstralApiError(
                response.status_code,
                "Ответ ленты контрагентов не JSON: %s" % response.text[:200],
                response.text,
            ) from exc

        if not isinstance(body, dict):
            logger.warning("Неожиданный формат ленты: %r", body)
            return []

        events = body.get("events") or []
        return list(events)

    def _wait_for_counterparty_event(
        self,
        process_id: str,
        date_from: datetime,
        wait_timeout: int,
        poll_interval: int,
    ) -> Dict[str, Any]:
        deadline = time.monotonic() + wait_timeout
        attempt = 0

        while time.monotonic() < deadline:
            attempt += 1
            events = self.get_counterparties_events(
                date_from=date_from,
                process_id=process_id,
            )
            logger.debug(
                "Лента контрагентов (попытка %s): получено событий %s",
                attempt,
                len(events),
            )

            if events:
                event = max(
                    events,
                    key=lambda item: item.get("eventDate") or "",
                )
                logger.info(
                    "Найдено событие по processId=%s: eventType=%s entityId=%s",
                    process_id,
                    event.get("eventType"),
                    event.get("entityId"),
                )
                return event

            time.sleep(poll_interval)

        raise AstralProcessError(
            "Не дождались события по processId=%s за %s сек." % (process_id, wait_timeout)
        )

    @staticmethod
    def _extract_global_ids_from_event(event: Dict[str, Any]) -> List[str]:
        properties = event.get("properties") or {}
        if not isinstance(properties, dict):
            logger.warning("properties события не dict: %r", properties)
            return []

        for key in ("globalIds", "globalId", "data", "result", "value", "ids"):
            value = properties.get(key)
            if isinstance(value, list):
                return [str(item) for item in value]
            if isinstance(value, str) and value:
                return [value]

        for nested_key in ("result", "data"):
            nested = properties.get(nested_key)
            if isinstance(nested, dict):
                for key in ("globalIds", "globalId", "data", "ids"):
                    value = nested.get(key)
                    if isinstance(value, list):
                        return [str(item) for item in value]
                    if isinstance(value, str) and value:
                        return [value]

        logger.warning(
            "Не удалось извлечь ИдЭДО из события: eventType=%s properties=%r",
            event.get("eventType"),
            properties,
        )
        return []

    # ------------------------------------------------------------------ #
    # Статус процесса
    # ------------------------------------------------------------------ #

    def get_process_status(self, process_id: str) -> Dict[str, Any]:
        path = self.PROCESS_STATUS_PATH.format(process_id=process_id)
        response = self._request("GET", path)
        self._raise_for_status(response)

        try:
            body: Any = response.json()
        except ValueError as exc:
            raise AstralApiError(
                response.status_code,
                "Ответ статуса процесса не JSON: %s" % response.text[:200],
                response.text,
            ) from exc

        if not isinstance(body, dict):
            raise AstralApiError(
                response.status_code,
                "Неожиданный формат статуса процесса: %r" % (body,),
                body,
            )
        return body


# --------------------------------------------------------------------------- #
# Валидация CLI-аргументов
# --------------------------------------------------------------------------- #

def validate_inn_kpp(inn: str, kpp: Optional[str]) -> None:
    """Проверить корректность пары ИНН/КПП.

    - ИНН 10 цифр → КПП обязателен, ровно 9 цифр.
    - ИНН 12 цифр → КПП не нужен.
    - Иные длины ИНН → ошибка.
    """
    if not inn.isdigit():
        raise AstralValidationError("ИНН должен состоять только из цифр: %r" % inn)

    inn_len = len(inn)

    if inn_len == 10:
        if not kpp:
            raise AstralValidationError(
                "Для ИНН из 10 цифр (ЮЛ) обязательно указывать --kpp."
            )
        if not kpp.isdigit():
            raise AstralValidationError(
                "КПП должен состоять только из цифр: %r" % kpp
            )
        if len(kpp) != 9:
            raise AstralValidationError(
                "КПП должен содержать ровно 9 цифр, получено %s: %r"
                % (len(kpp), kpp)
            )
    elif inn_len == 12:
        if kpp:
            logger.warning(
                "ИНН из 12 цифр (ИП/ФЛ) — КПП не требуется, "
                "переданное значение %r будет проигнорировано",
                kpp,
            )
    else:
        raise AstralValidationError(
            "ИНН должен содержать 10 или 12 цифр, получено %s: %r"
            % (inn_len, inn)
        )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Получение списка ИдЭДО контрагента через API Астрал.Доки.",
    )
    parser.add_argument(
        "--inn",
        required=True,
        type=str,
        help="ИНН контрагента: 10 цифр (ЮЛ) или 12 цифр (ИП/ФЛ).",
    )
    parser.add_argument(
        "--kpp",
        required=False,
        type=str,
        default=None,
        help="КПП контрагента (9 цифр). Обязателен, если ИНН состоит из 10 цифр.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Уровень логирования (по умолчанию INFO).",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        type=str,
        help="Файл для записи логов. Если не указан — логи выводятся в stdout.",
    )
    return parser


def _load_settings() -> Dict[str, str]:
    """Загрузить настройки из .env и переменных окружения."""
    load_dotenv()

    email = os.getenv("ASTRAL_EMAIL")
    password = os.getenv("ASTRAL_PASSWORD")
    abonent_id = os.getenv("ASTRAL_ABONENT_ID")
    base_url = os.getenv("ASTRAL_BASE_URL", AstralDocsClient.DEFAULT_BASE_URL)

    missing = [
        name
        for name, value in (
            ("ASTRAL_EMAIL", email),
            ("ASTRAL_PASSWORD", password),
            ("ASTRAL_ABONENT_ID", abonent_id),
        )
        if not value
    ]
    if missing:
        raise AstralValidationError(
            "Не заданы обязательные переменные окружения: %s. "
            "Проверьте файл .env." % ", ".join(missing)
        )

    return {
        "email": email,
        "password": password,
        "abonent_id": abonent_id,
        "base_url": base_url,
    }


def _configure_logging(level_name: str, log_file: Optional[str]) -> None:
    """Настроить логирование: в файл, если указан, иначе в stdout."""
    level = getattr(logging, level_name)

    if log_file:
        handler: logging.Handler = logging.FileHandler(
            log_file, mode="a", encoding="utf-8"
        )
    else:
        handler = logging.StreamHandler(stream=sys.stdout)

    handler.setLevel(level)
    handler.setFormatter(
        # logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        logging.Formatter(LOG_FORMAT)
    )

    root = logging.getLogger()
    # Сбрасываем ранее установленные обработчики (на случай повторных вызовов).
    for existing in list(root.handlers):
        root.removeHandler(existing)

    root.addHandler(handler)
    root.setLevel(level)


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.log_level, args.log_file)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format=LOG_FORMAT,
    )

    try:
        validate_inn_kpp(args.inn, args.kpp)
        settings = _load_settings()
    except AstralValidationError as exc:
        logger.error("Ошибка конфигурации: %s", exc)
        return 2

    client = AstralDocsClient(
        email=settings["email"],
        password=settings["password"],
        abonent_id=settings["abonent_id"],
        base_url=settings["base_url"],
    )

    try:
        ids = client.get_counterparty_global_ids(inn=args.inn, kpp=args.kpp)
        logger.info("Получены ИдЭДО для ИНН=%s КПП=%s: %s", args.inn, args.kpp, ids)
        print('^'.join(ids), file=sys.stdout, end='', flush=True)
        return 0
    except AstralDocsError as exc:
        logger.error("Ошибка при получении ИдЭДО: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
