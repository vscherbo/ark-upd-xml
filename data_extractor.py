#!/usr/bin/env python
"""
data_extractor.py - Извлечение данных для УПД из PostgreSQL или JSON.
Использует LoggingConnection для логирования запросов.
Поддерживает .pgpass для аутентификации.

Основной источник данных — функция rep.bill_doc_details_j(bill_no, 'ЭДО'),
возвращающая jsonb. Позиции счёта извлекаются отдельным запросом, так как
функция их не возвращает.

Адреса продавца/покупателя берутся из таблицы ext.gran_address по ОГРН,
для покупателя при отсутствии — запрос в DaData с сохранением в БД.

_load_from_db()
Адрес продавца/покупателя заполняется частично (регион из ИНН, название региона и улица – константы).
--- Даты (основание, передача) установлены фиксированными (2026-08-10, 2026-08-14).
basis_doc_name="Договор продажи",
basis_doc_number="КИП4828",
transport_info="самовывоз",
incoterms="EXW",
incoterms_version="2020",
Signer: auth_method="1",  # по умолчанию без доверенности
"""

import json
import logging
import os
import re
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import psycopg2
import psycopg2.extras
import psycopg2.pool
from psycopg2 import sql
from psycopg2.extras import LoggingConnection, LoggingCursor

import save_address
import suggest_party
from db_mapping import (AddressGAR, AddressRF, Bank, BillData, BillItem, Buyer,
                        NomerTip, PaymentDoc, Seller, Signer, Tax, TipNaim,
                        VidNaim, VidNaimKod)

REGIONS_RU = {
    "01": "Республика Адыгея",
    "02": "Республика Башкортостан",
    "03": "Республика Бурятия",
    "04": "Республика Алтай",
    "05": "Республика Дагестан",
    "06": "Республика Ингушетия",
    "07": "Кабардино‑Балкарская Республика",
    "08": "Республика Калмыкия",
    "09": "Карачаево‑Черкесская Республика",
    "10": "Республика Карелия",
    "11": "Республика Коми",
    "12": "Республика Марий Эл",
    "13": "Республика Мордовия",
    "14": "Республика Саха (Якутия)",
    "15": "Республика Северная Осетия — Алания",
    "16": "Республика Татарстан",
    "17": "Республика Тыва",
    "18": "Удмуртская Республика",
    "19": "Республика Хакасия",
    "20": "Чеченская Республика",
    "21": "Чувашская Республика",
    "22": "Алтайский край",
    "23": "Краснодарский край",
    "24": "Красноярский край",
    "25": "Приморский край",
    "26": "Ставропольский край",
    "27": "Хабаровский край",
    "28": "Амурская область",
    "29": "Архангельская область",
    "30": "Астраханская область",
    "31": "Белгородская область",
    "32": "Брянская область",
    "33": "Владимирская область",
    "34": "Волгоградская область",
    "35": "Вологодская область",
    "36": "Воронежская область",
    "37": "Ивановская область",
    "38": "Иркутская область",
    "39": "Калининградская область",
    "40": "Калужская область",
    "41": "Камчатский край",
    "42": "Кемеровская область — Кузбасс",
    "43": "Кировская область",
    "44": "Костромская область",
    "45": "Курганская область",
    "46": "Курская область",
    "47": "Ленинградская область",
    "48": "Липецкая область",
    "49": "Магаданская область",
    "50": "Московская область",
    "51": "Мурманская область",
    "52": "Нижегородская область",
    "53": "Новгородская область",
    "54": "Новосибирская область",
    "55": "Омская область",
    "56": "Оренбургская область",
    "57": "Орловская область",
    "58": "Пензенская область",
    "59": "Пермский край",
    "60": "Псковская область",
    "61": "Ростовская область",
    "62": "Рязанская область",
    "63": "Самарская область",
    "64": "Саратовская область",
    "65": "Сахалинская область",
    "66": "Свердловская область",
    "67": "Смоленская область",
    "68": "Тамбовская область",
    "69": "Тверская область",
    "70": "Томская область",
    "71": "Тульская область",
    "72": "Тюменская область",
    "73": "Ульяновская область",
    "74": "Челябинская область",
    "75": "Забайкальский край",
    "76": "Ярославская область",
    "77": "Москва",
    "78": "Санкт‑Петербург",
    "79": "Еврейская автономная область",
    "83": "Ненецкий автономный округ",
    "86": "Ханты‑Мансийский автономный округ — Югра",
    "87": "Чукотский автономный округ",
    "89": "Ямало‑Ненецкий автономный округ",
    "91": "Республика Крым",
    "92": "Севастополь"
}

FACT_HOUSING_NAME = (
    "ДОКУМЕНТ об отгрузке товаров (выполнении работ), передаче "
    "имущественных прав (документ об оказании услуг)"
)
DOC_NAME_OPERATOR = "Универсальный передаточный документ"

"""
Автоматика: 2LT-11001972830
АРКОМ: 2LT-11004384984
ОСЗ: 2LT-11004334116
КИПСПБ: 2LT-11000833475
ТДЭС: 2LT-11004343446

### ПЕСОЧНИЦА ###
Автоматика: 2LT-600070554
АРКОМ: 2LT-600072817
ОСЗ: 2LT-600070624
КИПСПБ: 2LT-600072763
ТДЭС: 2LT-600072775
"""


logger = logging.getLogger(__name__)

# ======================================================================
# Вспомогательные парсеры
# ======================================================================


def _parse_date(value: Any) -> Optional[date]:
    """Преобразует строку ISO или date в date, иначе None."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        try:
            return datetime.strptime(s, "%d.%m.%Y").date()
        except ValueError:
            logger.warning("Не удалось разобрать дату: %r", value)
            return None


def _parse_fio(fio: str) -> Tuple[str, str, str]:
    """
    Разбирает строку вида "Иванов И.И." в (Фамилия, Имя, Отчество).
    Возвращает пустые строки, если части не найдены.
    """
    if not fio:
        return "", "", ""
    parts = fio.strip().split()
    last = parts[0] if len(parts) > 0 else ""
    first = parts[1] if len(parts) > 1 else ""
    middle = parts[2] if len(parts) > 2 else ""
    return last, first, middle


_ATTORNEY_DATE_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})")


def _parse_attorney(raw: str) -> Tuple[Optional[str], Optional[date]]:
    """
    Разбирает строку доверенности (формат заранее неизвестен):
    пробует найти дату DD.MM.YYYY, всё остальное считает номером.
    Возвращает (номер, дата).
    """
    if not raw:
        return None, None
    s = raw.strip()
    m = _ATTORNEY_DATE_RE.search(s)
    doc_date: Optional[date] = None
    if m:
        try:
            doc_date = datetime.strptime(m.group(1), "%d.%m.%Y").date()
        except ValueError:
            pass
        s = (s[:m.start()] + s[m.end():]).strip()
    # Убираем типовые префиксы/разделители
    s = s.strip(" ,;№#")
    return (s or None), doc_date

# ======================================================================
# Курсор и менеджер подключений
# ======================================================================


class LoggingResultCursor(psycopg2.extras.RealDictCursor):
    """
    Курсор, логирующий не только запросы, но и результаты выборки.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._logger = logging.getLogger(__name__)

    def execute(self, query, vars=None):
        self._logger.debug("Executing query: %s, params: %s", query, vars)
        return super().execute(query, vars)

    def fetchone(self):
        row = super().fetchone()
        self._logger.debug("Fetch one: %s", row)
        return row

    def fetchall(self):
        rows = super().fetchall()
        self._logger.debug("Fetch all: %s rows", len(rows))
        if rows:
            self._logger.debug("First row sample: %s", rows[0])
        return rows

    def fetchmany(self, size=None):
        rows = super().fetchmany(size)
        self._logger.debug("Fetch many: %s rows", len(rows))
        if rows:
            self._logger.debug("First row sample: %s", rows[0])
        return rows


class PGManager:
    """
    Менеджер подключения к PostgreSQL с пулом соединений.
    Использует LoggingConnection для логирования запросов.
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        min_conn: int = 1,
        max_conn: int = 10,
        log_queries: bool = True,
        log_results: bool = True,
    ):
        """
        Args:
            dsn: Строка подключения (postgresql://user:pass@host/db). Если не указана,
                 берётся из DATABASE_URL.
            min_conn: Минимальное число соединений в пуле.
            max_conn: Максимальное число соединений в пуле.
            log_queries: Логировать ли запросы.
        """
        self.dsn = dsn or os.getenv("DATABASE_URL")
        if not self.dsn:
            raise ValueError(
                "DATABASE_URL не задан. Укажите его в окружении или передайте явно."
            )
        self._pool = None
        self.min_conn = min_conn
        self.max_conn = max_conn
        self.log_queries = log_queries
        self.log_results = log_results

    def _get_pool(self):
        if self._pool is None:
            # Выбираем фабрику курсора
            cursor_factory = (
                LoggingResultCursor if self.log_results
                else psycopg2.extras.RealDictCursor
            )
            pool_kwargs = {
                "minconn": self.min_conn,
                "maxconn": self.max_conn,
                "dsn": self.dsn,
                "cursor_factory": cursor_factory,
            }
            if self.log_queries:
                pool_kwargs["connection_factory"] = LoggingConnection
            self._pool = psycopg2.pool.SimpleConnectionPool(**pool_kwargs)
            # Не инициализируем соединения здесь – они будут создаваться по мере необходимости
        return self._pool

    @contextmanager
    def get_connection(self):
        pool = self._get_pool()
        conn = pool.getconn()
        try:
            # Инициализируем логгер, если используется LoggingConnection
            if self.log_queries and isinstance(conn, LoggingConnection):
                conn.initialize(logger)
            yield conn
        finally:
            pool.putconn(conn)

    @contextmanager
    def transaction(self):
        with self.get_connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def execute(self, query: Union[str, sql.SQL], params=None, conn=None):
        if conn is None:
            with self.get_connection() as c:
                self._execute(c, query, params)
        else:
            self._execute(conn, query, params)

    def _execute(self, conn, query, params):
        with conn.cursor() as cur:
            logger.debug("Executing query: %s", query)
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)

    def fetch_one(self, query: Union[str, sql.SQL], params=None, conn=None):
        if conn is None:
            with self.get_connection() as c:
                return self._fetch_one(c, query, params)
        return self._fetch_one(conn, query, params)

    def _fetch_one(self, conn, query, params):
        with conn.cursor() as cur:
            logger.debug("Fetching one: %s", query)
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            row = cur.fetchone()
            return dict(row) if row else None

    def fetch_all(self, query: Union[str, sql.SQL], params=None, conn=None):
        if conn is None:
            with self.get_connection() as c:
                return self._fetch_all(c, query, params)
        return self._fetch_all(conn, query, params)

    def _fetch_all(self, conn, query, params):
        with conn.cursor() as cur:
            logger.debug("Fetching all: %s", query)
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            rows = cur.fetchall()
            return [dict(row) for row in rows]

    def callproc(self, proc_name: str, params=None):
        with self.get_connection() as c:
            with c.cursor() as cur:
                cur.callproc(proc_name, params)
                return cur.fetchall()

    def fetch_function_json(self, func_sql: str, params: tuple) -> Optional[dict]:
        """
        Вызывает SQL-функцию, возвращающую jsonb, и возвращает её результат
        как Python-объект (dict/list). Пример:
            fetch_function_json("rep.bill_doc_details_j(%s, %s)", (bill_no, 'ЭДО'))
        """
        row = self.fetch_one(f"SELECT {func_sql} AS j", params)
        if not row:
            return None
        return row.get("j")

    def close(self):
        if self._pool:
            self._pool.closeall()
            self._pool = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ======================================================================
# DataExtractor
# ======================================================================

class DataExtractor:
    """Извлекает данные для УПД из БД или из JSON-файла."""

    def __init__(
        self,
        use_json: bool = False,
        json_path: str = "sample_data.json",
        address_format: str = "rf",
        edo_prefix: str = "2LT",
    ):
        self.use_json = use_json
        self.json_path = json_path
        self.address_format = address_format
        self.edo_prefix = edo_prefix
        self.pg = PGManager() if not use_json else None

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------
    def get_bill_data(self, bill_no: int) -> BillData:
        if self.use_json:
            return self._load_from_json(bill_no, "HARD-1234")
        return self._load_from_db(bill_no)

    # ------------------------------------------------------------------
    # Адрес из DaData (для покупателя)
    # ------------------------------------------------------------------
    def get_address(self, query: str) -> int:
        try:
            api_key = suggest_party.load_api_key()
        except (FileNotFoundError, KeyError) as exc:
            logger.error("Не удалось загрузить API-ключ DaData: %s", exc)
            return 1

        try:
            response = suggest_party.suggest(query, "party", api_key)
        except Exception as exc:
            logger.exception("Ошибка запроса DaData: %s", exc)
            return 1

        try:
            db_config = save_address.DBConfig.from_ini()
        except Exception as exc:
            logger.exception("Не удалось загрузить конфигурацию БД: %s", exc)
            return 1

        try:
            inserted = save_address.save_response(response, db_config)
        except Exception as exc:
            logger.exception("Ошибка сохранения в БД: %s", exc)
            return 1

        logger.info("Адрес из DaData сохранён, записей: %d", inserted)
        return 0

    # ------------------------------------------------------------------
    # Адрес из ext.gran_address
    # ------------------------------------------------------------------
    def _get_address_from_gran_address(self, ogrn: str) -> Optional[AddressRF]:
        """Возвращает AddressRF из ext.gran_address по ОГРН или None."""
        if not ogrn:
            return None
        row = self.pg.fetch_one(
            """
            SELECT postal_code, region, region_kladr_id, city_district,
                   city, settlement, street, house, block, flat, ogrn
            FROM ext.gran_address
            WHERE ogrn = %s
            """,
            (ogrn,),
        )
        if not row:
            logger.warning("Адрес для ОГРН '%s' не найден в gran_address", ogrn)
            return None

        region_code = ""
        if row.get("region_kladr_id") and len(row["region_kladr_id"]) >= 2:
            region_code = row["region_kladr_id"][:2]

        return AddressRF(
            postal_code=row.get("postal_code"),
            region_code=region_code,
            region_name=row.get("region"),
            district=row.get("city_district"),
            city=row.get("city"),
            locality=row.get("settlement"),
            street=row.get("street"),
            house=row.get("house"),
            building=row.get("block"),
            apartment=row.get("flat"),
        )

    # ------------------------------------------------------------------
    # Основной метод: извлечение из БД
    # ------------------------------------------------------------------
    def _load_from_db(self, bill_no: int) -> BillData:
        # ------------------------------------------------------------------
        # 1. Основные данные — из функции bill_doc_details_j
        # ------------------------------------------------------------------
        logger.info("Вызываем rep.bill_doc_details_j(%s, 'ЭДО')", bill_no)
        j = self.pg.fetch_function_json(
            "rep.bill_doc_details_j(%s, %s)", (bill_no, "ЭДО")
        )
        if not j:
            raise ValueError(
                f"Функция bill_doc_details_j не вернула данные для счёта {bill_no}"
            )

        document = j.get("document") or {}
        seller_j = j.get("seller") or {}
        buyer_j = j.get("buyer") or {}
        consignee = j.get("consignee") or {}
        signatures = j.get("signatures") or {}
        contracts = j.get("contracts") or {}

        logger.debug("document=%s", document)
        logger.debug("signatures=%s", signatures)
        logger.debug("contracts=%s", contracts)
        logger.debug("consignee=%s", consignee)

        # ------------------------------------------------------------------
        # 2. Позиции счёта — отдельным запросом
        # ------------------------------------------------------------------
        items_raw = self.pg.fetch_all(
            """
            SELECT ROW_NUMBER() OVER (ORDER BY bc."ПозицияСчета" ASC) AS row_num,
                   bc."КодСодержания" AS article,
                   bc."Наименование"   AS item_name,
                   r."Отгружено"       AS quantity,
                   bc."КодОКЕИ"::text  AS mes_code,
                   bc."Ед Изм"         AS mes_unit,
                   bc."ЦенаНДС"        AS price_with_vat,
                   (SELECT string_agg(mark, '^')
                      FROM arc_energo.entering_marked em
                     WHERE em."КодОтгрузки" = r."КодОтгрузки") AS kiz
            FROM arc_energo."Содержание счета" bc
            LEFT JOIN arc_energo."Расход" r
                   ON r."Счет" = bc."№ счета" AND bc."КодПозиции" = r."КодПозиции"
            WHERE bc."№ счета" = %s
            ORDER BY bc."ПозицияСчета"
            """,
            (bill_no,),
        )
        logger.info("Найдено %d позиций", len(items_raw))

        # ------------------------------------------------------------------
        # 3. Адреса
        # ------------------------------------------------------------------
        seller_address: Optional[AddressRF] = None
        if seller_j.get("ogrn"):
            seller_address = self._get_address_from_gran_address(seller_j["ogrn"])
            if not seller_address:
                logger.warning(
                    "Адрес продавца (ОГРН %s) не найден в gran_address",
                    seller_j["ogrn"],
                )

        buyer_address: Optional[AddressRF] = None
        if buyer_j.get("ogrn"):
            buyer_address = self._get_address_from_gran_address(buyer_j["ogrn"])
            if not buyer_address:
                logger.debug(
                    "Адрес покупателя (ОГРН %s) не найден, запрашиваем DaData",
                    buyer_j["ogrn"],
                )
                if self.get_address(buyer_j["ogrn"]) == 0:
                    buyer_address = self._get_address_from_gran_address(buyer_j["ogrn"])

        # ------------------------------------------------------------------
        # 4. Продавец
        # ------------------------------------------------------------------
        seller_inn = seller_j.get("inn", "") or ""
        seller_kpp = seller_j.get("kpp", "") or ""
        seller_edo_id = self.pg.callproc('arc_energo.edo_id', (self.edo_prefix, seller_inn,
                                                               seller_kpp,))
        if not seller_edo_id:
            raise ValueError(
                f'Не удалось получить seller_edo_id для ИНН={seller.inn}, КПП={seller.kpp}')

        seller = Seller(
            name=seller_j.get("legal_name", "") or "",
            # inn=seller_j.get("inn", "") or "",
            # kpp=seller_j.get("kpp", "") or "",
            inn=seller_inn,
            kpp=seller_kpp,
            ogrn=seller_j.get("ogrn"),
            okpo=seller_j.get("okpo"),
            prefix=document.get("prefix"),
            address=seller_address,
            edo_id=seller_edo_id[0]['edo_id']
        )

        # ------------------------------------------------------------------
        # 5. Покупатель
        # ------------------------------------------------------------------
        is_worker = bool(buyer_j.get("is_worker"))
        if is_worker:
            # TODO: реализовать ветку СвФЛУч для покупателя-физлица
            logger.warning(
                "Покупатель — физлицо (worker_fio=%s). Ветка СвФЛУч пока не реализована.",
                buyer_j.get("worker_fio"),
            )
            buyer = Buyer(
                name=buyer_j.get("worker_fio", "") or "",
                inn="",
                kpp="",
                ogrn="",
                address=buyer_address,
            )
        else:
            buyer_inn = buyer_j.get("inn", "") or ""
            buyer_kpp = buyer_j.get("kpp", "") or ""
            buyer_edo_id = self.pg.callproc('arc_energo.edo_id', (self.edo_prefix, buyer_inn,
                                                                  buyer_kpp,))
            if not buyer_edo_id:
                raise ValueError(
                    f'Не удалось получить buyer_edo_id для ИНН={buyer.inn}, КПП={buyer.kpp}')

            buyer = Buyer(
                name=buyer_j.get("legal_name", "") or "",
                # inn=buyer_j.get("inn", "") or "",
                # kpp=buyer_j.get("kpp", "") or "",
                inn=buyer_inn,
                kpp=buyer_kpp,
                ogrn=buyer_j.get("ogrn", "") or "",
                address=buyer_address,
                edo_id=buyer_edo_id[0]['edo_id']
            )

        # ------------------------------------------------------------------
        # 6. Банк продавца
        # ------------------------------------------------------------------
        bank = Bank(
            bank_name=seller_j.get("bank", "") or "",
            bik=seller_j.get("bik", "") or "",
            account=seller_j.get("rs", "") or "",
            corr_account=None,  # в JSON нет к/с продавца
        )

        # ------------------------------------------------------------------
        # 7. Ставка НДС
        # ------------------------------------------------------------------
        vat_rate_raw = document.get("vat_rate")
        vat_rate_str = f"{vat_rate_raw}%" if vat_rate_raw is not None else "22%"
        tax = Tax(vat_rate=vat_rate_str)

        # ------------------------------------------------------------------
        # 8. Подписанты (директор + бухгалтер, если есть)
        # ------------------------------------------------------------------
        signers: List[Signer] = []

        # 8.1 Директор
        last, first, middle = _parse_fio(signatures.get("director") or "")
        director_signer = Signer(
            last_name=last or "—",     # XSD требует minLength=1
            first_name=first or "—",
            middle_name=middle or None,
            position=signatures.get("position") or None,
            auth_method="1",
        )
        attorney_dir = signatures.get("attorney_director")
        if attorney_dir:
            doc_num, doc_date = _parse_attorney(attorney_dir)
            # TODO: уточнить, всегда ли бумажная доверенность (auth_method="5"),
            #       или возможна МЧД (auth_method="3" + СвДоверЭл).
            director_signer.auth_method = "5"
            director_signer.paper_doc_number = doc_num
            director_signer.paper_doc_date = doc_date
        signers.append(director_signer)

        # 8.2 Бухгалтер (если ФИО непустое)
        accountant_fio = (signatures.get("accountant") or "").strip()
        if accountant_fio:
            a_last, a_first, a_middle = _parse_fio(accountant_fio)
            accountant_signer = Signer(
                last_name=a_last or "—",
                first_name=a_first or "—",
                middle_name=a_middle or None,
                # TODO: уточнить должность бухгалтера (в bill_doc_details_j её нет)
                # position="Главный бухгалтер",
                # Пока, как для "директора"
                position=signatures.get("position") or None,
                auth_method="1",
            )
            attorney_acc = signatures.get("attorney_accountant")
            if attorney_acc:
                doc_num, doc_date = _parse_attorney(attorney_acc)
                accountant_signer.auth_method = "5"
                accountant_signer.paper_doc_number = doc_num
                accountant_signer.paper_doc_date = doc_date
            signers.append(accountant_signer)

        # ------------------------------------------------------------------
        # 9. Позиции счёта
        # ------------------------------------------------------------------
        try:
            vat_rate_num = float(vat_rate_str.replace("%", "")) / 100.0
        except ValueError:
            vat_rate_num = 0.22

        items: List[BillItem] = []
        for row in items_raw:
            price_with_vat = float(row["price_with_vat"]) if row["price_with_vat"] else 0.0
            price_without_vat = (
                price_with_vat / (1 + vat_rate_num) if vat_rate_num != 0 else price_with_vat
            )
            quantity = float(row["quantity"]) if row["quantity"] else 0.0
            total_without_vat = price_without_vat * quantity
            total_with_vat = total_without_vat * (1 + vat_rate_num)
            vat_amount = total_with_vat - total_without_vat

            kiz_list: List[str] = []
            if row.get("kiz"):
                kiz_list = [x for x in row["kiz"].split("^") if x]

            items.append(
                BillItem(
                    row_num=row["row_num"],
                    name=row["item_name"],
                    okei_code=str(row.get("mes_code", "796")).zfill(3),
                    okei_name=row.get("mes_unit", "шт") or "шт",
                    quantity=quantity,
                    price_without_vat=round(price_without_vat, 2),
                    total_without_vat=round(total_without_vat, 2),
                    vat_rate=vat_rate_str,
                    vat_amount=round(vat_amount, 2),
                    total_with_vat=round(total_with_vat, 2),
                    article=row.get("article"),
                    kiz_list=kiz_list,
                )
            )

        # ------------------------------------------------------------------
        # 10. Платёжно-расчётные документы (СвПРД)
        # ------------------------------------------------------------------
        payment_docs: List[PaymentDoc] = []
        for pp in contracts.get("bill_pp_list") or []:
            num = pp.get("prd_number")
            d = _parse_date(pp.get("prd_date"))
            if num and d:
                payment_docs.append(PaymentDoc(number=str(num), date=d))

        # ------------------------------------------------------------------
        # 11. Даты и номера для шапки/передачи
        # ------------------------------------------------------------------
        bill_date = _parse_date(document.get("bill_date"))
        factura_date = _parse_date(document.get("factura_date"))
        invoice_date_raw = _parse_date(document.get("invoice_date_raw"))
        parent_date = _parse_date(document.get("parent_date"))

        # СвСчФакт/@НомерДок = COALESCE(sf_num, invoice_num_raw)
        sv_sch_number = (
            document.get("sf_num") or document.get("invoice_num_raw") or ""
        )
        sv_sch_date = factura_date or bill_date

        # Дата передачи: для doc ≠ 'Счет'/'СчетФакс' — invoice_date_raw
        transfer_date = invoice_date_raw or bill_date

        # ------------------------------------------------------------------
        # 12. Документ-подтверждение отгрузки (ДокПодтвОтгрНом)
        # ------------------------------------------------------------------
        dok_podtverzh_name = DOC_NAME_OPERATOR
        dok_podtverzh_number = (
            document.get("sf_num") or document.get("invoice_num_raw") or ""
        )
        dok_podtverzh_date = invoice_date_raw or sv_sch_date

        # ------------------------------------------------------------------
        # 13. Основание (ОснПер)
        # ------------------------------------------------------------------
        basis_from_bill = document.get("basis_from_bill")
        if basis_from_bill:
            basis_doc_name = basis_from_bill
        else:
            basis_doc_name = "Основной договор"

        parent_bill = document.get("parent_bill") or bill_no
        prefix = document.get("prefix") or ""
        parent_bill_str = str(parent_bill)
        if len(parent_bill_str) >= 8:
            basis_doc_number = f"{prefix}{parent_bill_str[:4]}-{parent_bill_str[4:]}"
        else:
            basis_doc_number = f"{prefix}{parent_bill_str}"
        basis_doc_date = parent_date or bill_date

        # ------------------------------------------------------------------
        # 14. ИдГосКон
        # ------------------------------------------------------------------
        state_contract_number = contracts.get("state_contract_number")
        # XSD: 20..25 символов; если не подходит — не выводим
        if state_contract_number and not (20 <= len(state_contract_number) <= 25):
            logger.warning(
                "ИдГосКон=%r имеет недопустимую длину, пропускаем",
                state_contract_number,
            )
            state_contract_number = None

        # ------------------------------------------------------------------
        # 15. BillData
        # ------------------------------------------------------------------
        bill_data = BillData(
            bill_number=str(bill_no),
            bill_date=bill_date,
            upd_number=sv_sch_number,
            upd_date=sv_sch_date or date.today(),
            upd_file="",
            function="СЧФДОП",
            fact_housing_name=FACT_HOUSING_NAME,
            doc_name_operator=DOC_NAME_OPERATOR,
            seller=seller,
            buyer=buyer,
            bank=bank,
            tax=tax,
            # signer оставляем для совместимости (первый)
            signer=signers[0] if signers else None,
            signers=signers,
            items=items,
            payment_docs=payment_docs,
            state_contract_number=state_contract_number,
            basis_doc_name=basis_doc_name,
            basis_doc_number=basis_doc_number,
            basis_doc_date=basis_doc_date,
            operation_content="Товары переданы",
            operation_type="продажа",
            transfer_date=transfer_date,
            transfer_start_date=transfer_date,
            transfer_end_date=transfer_date,
            dok_podtverzh_name=dok_podtverzh_name,
            dok_podtverzh_number=dok_podtverzh_number,
            dok_podtverzh_date=dok_podtverzh_date,
        )
        return bill_data

    # ------------------------------------------------------------------
    def _load_from_json(self, bill_no: int, upd_number: str) -> BillData:
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["upd_number"] = upd_number
        return BillData(**data)
