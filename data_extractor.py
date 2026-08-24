#!/usr/bin/env python
"""
data_extractor.py - Извлечение данных для УПД из PostgreSQL или JSON.
Использует LoggingConnection для логирования запросов.
Поддерживает .pgpass для аутентификации.
"""

import json
import logging
import os
from contextlib import contextmanager
from datetime import date
from typing import Any, Dict, List, Optional, Union

import psycopg2
import psycopg2.extras
import psycopg2.pool
from psycopg2 import sql
from psycopg2.extras import LoggingConnection, LoggingCursor

from db_mapping import (AddressRF, Bank, BillData, BillItem, Buyer, Seller,
                        Signer, Tax)

logger = logging.getLogger(__name__)


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

    def _get_pool(self):
        if self._pool is None:
            pool_kwargs = {
                "minconn": self.min_conn,
                "maxconn": self.max_conn,
                "dsn": self.dsn,
                "cursor_factory": psycopg2.extras.RealDictCursor,
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

    def close(self):
        if self._pool:
            self._pool.closeall()
            self._pool = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class DataExtractor:
    """
    Извлекает данные для УПД из БД или из JSON-файла.
    """

    def __init__(self, use_json: bool = False, json_path: str = "sample_data.json"):
        """
        Args:
            use_json: Если True, читать из JSON вместо БД.
            json_path: Путь к JSON-файлу с данными.
        """
        self.use_json = use_json
        self.json_path = json_path
        self.pg = PGManager() if not use_json else None

    def get_bill_data(self, bill_no: int, upd_number: str) -> BillData:
        """
        Получить все данные для генерации УПД по номеру счёта.
        """
        if self.use_json:
            return self._load_from_json(bill_no, upd_number)
        return self._load_from_db(bill_no, upd_number)

    def _load_from_db(self, bill_no: int, upd_number: str) -> BillData:
        """Извлечение из PostgreSQL."""
        # Получаем основную информацию о счёте
        bill_info = self.pg.fetch_one(
            """
            SELECT "№ счета" AS bill_number,
                   "Дата счета" AS bill_date,
                   "фирма" AS seller_id,
                   "Код" AS buyer_id
            FROM arc_energo."Счета"
            WHERE "№ счета" = %s
            """,
            (bill_no,)
        )
        if not bill_info:
            raise ValueError(f"Счёт {bill_no} не найден")

        # Получаем строки счёта
        items_raw = self.pg.fetch_all(
            """
            SELECT bc."ПозицияСчета" AS row_num,
                   bc."КодСодержания" AS article,
                   bc."Наименование" AS item_name,
                   bc."Кол-во" AS quantity,
                   bc."Ед Изм" AS mes_unit,
                   bc."ЦенаНДС" AS price_with_vat,
                   em.mark AS kiz
            FROM arc_energo."Содержание счета" bc
            LEFT JOIN arc_energo."Расход" r
                ON r."Счет" = bc."№ счета" AND bc."КодПозиции" = r."КодПозиции"
            LEFT JOIN arc_energo.entering_marked em
                ON em."КодОтгрузки" = r."КодОтгрузки"
            WHERE bc."№ счета" = %s
            ORDER BY bc."ПозицияСчета"
            """,
            (bill_no,)
        )

        # Получаем продавца
        seller_raw = self.pg.fetch_one(
            """
            SELECT
                f."Ф_ИНН" AS inn,
                fr."Ф_КПП" AS kpp,
                f."Название" AS name,
                fr."Ф_ЮрАдрес" AS address_text,
                fr."Ф_ОКПО" AS okpo,
                f."Ф_ОГРН" AS ogrn,
                fr."Ф_Банк" AS bank_name,
                fr."Ф_БИК" AS bic,
                fr."Ф_РассчетныйСчет" AS account,
                fr."Ф_КоррСчет" AS corr_account,
                vat_rate(b."фирма", b."Код", b."Дата счета"::date) || '%%' AS vat_rate,
                fs.signer_position,
                fs.signer_fio
            FROM arc_energo."Счета" b
            JOIN arc_energo."ФирмаРеквизиты" fr
                ON fr."КодРеквизитовФирмы" = b."КодРеквизитовФирмы"
            JOIN arc_energo."Фирма" f
                ON fr."КодФирмы" = f."КлючФирмы"
            LEFT JOIN LATERAL (
                SELECT signer_fio, signer_position
                FROM arc_energo.firm_signer(f."КлючФирмы", 'УПД_ОСЗ')
            ) AS fs ON true
            WHERE b."№ счета" = %s
            """,
            (bill_no,)
        )
        if not seller_raw:
            raise ValueError(f"Продавец для счёта {bill_no} не найден")

        # Получаем покупателя
        buyer_raw = self.pg.fetch_one(
            """
            SELECT e."ИНН" AS inn,
                   e."КПП" AS kpp,
                   e."Предприятие" AS name,
                   e."ЮрАдрес" AS address_text
            FROM arc_energo."Предприятия" e
            WHERE e."Код" = %s
            """,
            (bill_info["buyer_id"],)
        )
        if not buyer_raw:
            raise ValueError(f"Покупатель с кодом {bill_info['buyer_id']} не найден")

        # Собираем структуру данных
        # Для простоты предположим, что адрес в БД хранится как текст,
        # и мы не можем его разбить на составные. Поэтому заполним только текстовое поле.
        # В реальном проекте нужно либо парсить, либо хранить структурированно.
        seller_address = AddressRF(
            region_code="78",  # пример, нужно извлекать из address_text
            region_name="г. Санкт-Петербург",
            # В реальности нужно разобрать, но для демонстрации оставим заглушку
        )
        buyer_address = AddressRF(
            region_code="78",
            region_name="г. Санкт-Петербург",
        )

        seller = Seller(
            name=seller_raw["name"],
            inn=seller_raw["inn"],
            kpp=seller_raw["kpp"],
            ogrn=seller_raw.get("ogrn"),
            okpo=seller_raw.get("okpo"),
            address=seller_address,
        )

        buyer = Buyer(
            name=buyer_raw["name"],
            inn=buyer_raw["inn"],
            kpp=buyer_raw.get("kpp", ""),
            address=buyer_address,
        )

        bank = Bank(
            bank_name=seller_raw.get("bank_name", ""),
            bik=seller_raw.get("bic", ""),
            account=seller_raw.get("account", ""),
            corr_account=seller_raw.get("corr_account"),
        )

        tax = Tax(vat_rate=seller_raw.get("vat_rate", "22%"))

        # Разбираем ФИО подписанта (ожидается строка "Фамилия Имя Отчество")
        signer_fio = seller_raw.get("signer_fio", "")
        fio_parts = signer_fio.split()
        signer = Signer(
            last_name=fio_parts[0] if len(fio_parts) > 0 else "",
            first_name=fio_parts[1] if len(fio_parts) > 1 else "",
            middle_name=fio_parts[2] if len(fio_parts) > 2 else None,
            position=seller_raw.get("signer_position", ""),
            auth_method="1",  # по умолчанию без доверенности
        )

        # Преобразуем строки товаров
        items = []
        for row in items_raw:
            # Вычисляем цену без НДС из цены с НДС и ставки
            # Для простоты возьмём ставку из seller_raw (одинаковая для всех товаров)
            vat_rate_str = seller_raw.get("vat_rate", "22%")
            # Преобразуем "22%" в 0.2 для вычислений
            try:
                vat_rate_num = float(vat_rate_str.replace("%", "")) / 100.0
            except ValueError:
                vat_rate_num = 0.22
            price_with_vat = float(row["price_with_vat"]) if row["price_with_vat"] else 0.0
            quantity = float(row["quantity"]) if row["quantity"] else 0.0
            total_with_vat = price_with_vat * quantity
            total_without_vat = total_with_vat / \
                (1 + vat_rate_num) if vat_rate_num != 0 else total_with_vat
            vat_amount = total_with_vat - total_without_vat
            price_without_vat = price_with_vat / \
                (1 + vat_rate_num) if vat_rate_num != 0 else price_with_vat

            kiz_list = []
            if row.get("kiz"):
                kiz_list.append(row["kiz"])

            items.append(
                BillItem(
                    row_num=row["row_num"],
                    name=row["item_name"],
                    oktei_code=row.get("mes_unit", "796"),  # код "шт"
                    oktei_name="шт",  # можно получить из справочника
                    quantity=quantity,
                    price_without_vat=price_without_vat,
                    total_without_vat=total_without_vat,
                    vat_rate=vat_rate_str,
                    vat_amount=vat_amount,
                    total_with_vat=total_with_vat,
                    article=row.get("article"),
                    kiz_list=kiz_list,
                )
            )

        # Формируем BillData
        bill_data = BillData(
            bill_number=str(bill_info["bill_number"]),
            bill_date=bill_info["bill_date"],
            upd_number=upd_number,
            upd_date=date.today(),
            upd_file="",
            function="СЧФДОП",
            fact_housing_name="Документ об отгрузке товаров (выполнении работ), передаче имущественных прав (документ об оказании услуг)",
            doc_name_operator="Счет-фактура и документ об отгрузке товаров (выполнении работ), передаче имущественных прав (документ об оказании услуг)",
            seller=seller,
            buyer=buyer,
            bank=bank,
            tax=tax,
            signer=signer,
            items=items,
            basis_doc_name="Договор продажи",
            basis_doc_number="КИП4828",
            basis_doc_date=date(2026, 8, 10),
            operation_content="Товары переданы",
            operation_type="продажа",
            transfer_date=date(2026, 8, 14),
            transfer_start_date=date(2026, 8, 14),
            transfer_end_date=date(2026, 8, 14),
            transport_info="самовывоз",
            incoterms="EXW",
            incoterms_version="2020",
        )
        return bill_data

    def _load_from_json(self, bill_no: int, upd_number: str) -> BillData:
        """Загрузка из JSON-файла (для отладки)."""
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Проверим, что номер счёта совпадает (если есть поле в JSON)
        # Можно просто вернуть данные, предварительно преобразовав в BillData
        # Для упрощения конвертируем через Pydantic
        data['upd_number'] = upd_number
        return BillData(**data)
