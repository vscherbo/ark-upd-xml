#!/usr/bin/env python
"""
data_extractor.py - Извлечение данных из PostgreSQL.
Обеспечивает:
- Подключение к БД с использованием .pgpass.
- Выполнение запросов с параметрами.
- Контекстный менеджер для транзакций.
- Логирование всех запросов и ошибок с поддержкой кириллицы.
- Преобразование данных в формат, ожидаемый генератором.
"""
import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Union

import psycopg2
import psycopg2.extras
from psycopg2 import sql
from psycopg2.pool import SimpleConnectionPool

from db_mapping import Bill, BillItem, Settings, build_settings

# --- Настройка логирования ---
logger = logging.getLogger(__name__)

# --- SQL Запросы ---
SELECT_BILL = '''
SELECT "№ счета" AS bill_no, "Дата счета" AS bill_date, "фирма" AS seller_id, "Код" AS buyer_id
FROM arc_energo."Счета"
WHERE "№ счета" = %s
'''

SEL_BILL_ITEMS = '''
SELECT bc."ПозицияСчета" AS row_num, bc."КодСодержания" AS article,
       bc."Наименование" AS item_name, bc."Кол-во" AS quantity,
       bc."Ед Изм" AS mes_unit, bc."ЦенаНДС" AS price_with_vat, NULL AS kiz
FROM arc_energo."Содержание счета" bc
WHERE "№ счета" = %s
UNION
SELECT bc."ПозицияСчета", bc."КодСодержания", bc."Наименование", bc."Кол-во",
       bc."Ед Изм", bc."ЦенаНДС", em.kiz
FROM arc_energo."Содержание счета" bc
JOIN arc_energo."Расход" r ON r."Счет" = "№ счета" AND bc."КодПозиции" = r."КодПозиции"
JOIN arc_energo.entering_marked em ON em."КодОтгрузки" = r."КодОтгрузки"
WHERE "№ счета" = %s
ORDER BY 1;
'''

SEL_SELLER = """
SELECT
    f."Ф_ИНН" AS inn,
    fr."Ф_КПП" AS kpp,
    f."Название" AS name,
    fr."Ф_ЮрАдрес" AS address,
    fr."Ф_ОКПО" AS okpo,
    f."Ф_ОГРН" AS ogrn,
    fr."Ф_Банк" AS bank_name,
    fr."Ф_БИК" AS bic,
    fr."Ф_РассчетныйСчет" AS account,
    fr."Ф_КоррСчет" AS corr_account,
    vat_rate(b."фирма", b."Код", b."Дата счета"::date)|| '%' AS vat_rate,
    '' AS tax_system,
    fs.signer_position,
    fs.signer_fio
FROM
    arc_energo."Счета" b
JOIN arc_energo."ФирмаРеквизиты" fr ON fr."КодРеквизитовФирмы" = b."КодРеквизитовФирмы"
JOIN arc_energo."Фирма" f ON fr."КодФирмы" = f."КлючФирмы"
LEFT JOIN LATERAL (
    SELECT signer_fio, signer_position
    FROM arc_energo.firm_signer(f."КлючФирмы", 'УПД_ОСЗ')
) AS fs ON true
WHERE b."№ счета" = %s;
"""

SEL_BUYER = """
SELECT e."ИНН" AS inn,
       e."КПП" AS kpp,
       e."Предприятие" AS name,
       e."ЮрАдрес" AS address
FROM arc_energo."Предприятия" e
WHERE e."Код" = %s;
"""

INS_LOG = """
INSERT INTO rep.upd_xml_log
(bill_no, upd_number, upd_date, generated_at, xml_file_path, status)
VALUES (%s, %s, %s, NOW(), %s, 'success')
"""


# --- Кастомный курсор для логирования ---
class LoggingCursor(psycopg2.extras.RealDictCursor):
    """Кастомный курсор, логирующий SQL-запросы."""

    def execute(self, query, vars=None):
        # Логируем запрос и параметры перед выполнением
        logger.debug("Executing query: %s with vars: %s", query, vars)
        try:
            super().execute(query, vars)
        except Exception as e:
            logger.error("Query execution failed: %s", e)
            raise  # Пробрасываем исключение дальше

    def callproc(self, procname, vars=None):
        logger.debug("Calling procedure: %s with vars: %s", procname, vars)
        try:
            super().callproc(procname, vars)
        except Exception as e:
            logger.error("Procedure call failed: %s", e)
            raise


class LoggingConnection(psycopg2.extensions.connection):
    """Кастомное соединение, использующее LoggingCursor."""

    def cursor(self, *args, **kwargs):
        kwargs.setdefault('cursor_factory', LoggingCursor)
        return super().cursor(*args, **kwargs)


class PGManager:
    """
    Менеджер подключения к PostgreSQL.
    Использует .pgpass для аутентификации.
    Пример использования:
         with PGManager() as pg:
             rows = pg.fetch_all("SELECT * FROM users WHERE id = %s", (user_id,))
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        min_conn: int = 1,
        max_conn: int = 10,
    ):
        """
        Инициализация менеджера.

        Args:
            dsn: Строка подключения (например, postgresql://user:pass@localhost/db).
                 Если не указана, берётся из переменной окружения DATABASE_URL.
                 Для аутентификации через .pgpass, строка должна содержать user и host.
                 Пример: "postgresql://my_user@my_host/my_db_name"
            min_conn: Минимальное количество соединений в пуле.
            max_conn: Максимальное количество соединений в пуле.
        """
        self.dsn = dsn or os.getenv("DATABASE_URL")
        if not self.dsn:
            raise ValueError(
                "DATABASE_URL не задан. Укажите его в переменных окружения "
                "или передайте явно в конструктор."
            )
        self._pool = None
        self.min_conn = min_conn
        self.max_conn = max_conn

    def _get_pool(self) -> SimpleConnectionPool:
        """Ленивое создание пула соединений."""
        if self._pool is None:
            logger.debug("Creating connection pool with DSN: %s", self.dsn)
            # Указываем cursor_factory на уровне пула
            self._pool = SimpleConnectionPool(
                self.min_conn,
                self.max_conn,
                self.dsn,
                connection_factory=LoggingConnection,  # Используем кастомное соединение
                # Запасной курсор, если LoggingConnection не используется
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
        return self._pool

    @contextmanager
    def get_connection(self):
        """Получить соединение из пула (контекстный менеджер)."""
        pool = self._get_pool()
        conn = pool.getconn()
        try:
            logger.debug("Connection retrieved from pool.")
            yield conn
        finally:
            pool.putconn(conn)
            logger.debug("Connection returned to pool.")

    @contextmanager
    def transaction(self):
        """
        Контекстный менеджер для транзакций.
        Пример:
            with pg.transaction() as conn:
                pg.execute("INSERT INTO ...", conn=conn)
                pg.execute("UPDATE ...", conn=conn)
                # Если возникнет исключение, транзакция будет откачена.
        """
        with self.get_connection() as conn:
            try:
                logger.info("Starting transaction.")
                yield conn
                conn.commit()
                logger.info("Transaction committed.")
            except Exception as e:
                logger.error("Transaction failed, rolling back: %s", e)
                conn.rollback()
                raise

    def execute(
        self,
        query: Union[str, sql.SQL],
        params: Optional[tuple] = None,  # psycopg2 ожидает tuple или None
        conn=None,
    ) -> None:
        """
        Выполнить запрос без возврата результата (INSERT, UPDATE, DELETE).

        Args:
            query: SQL-запрос (строка или sql.SQL).
            params: Параметры для подстановки (tuple).
            conn: Соединение (если не указано, берётся новое из пула).
        """
        if conn is None:
            with self.get_connection() as loc_conn:
                self._execute(loc_conn, query, params)
        else:
            self._execute(conn, query, params)

    def _execute(self, conn, query, params):
        with conn.cursor() as cur:  # Используется LoggingCursor
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)

    def fetch_one(
        self,
        query: Union[str, sql.SQL],
        params: Optional[tuple] = None,
        conn=None,
    ) -> Optional[Dict[str, Any]]:
        """Выполнить запрос и вернуть одну строку как словарь."""
        if conn is None:
            with self.get_connection() as loc_conn:
                return self._fetch_one(loc_conn, query, params)
        return self._fetch_one(conn, query, params)

    def _fetch_one(self, conn, query, params):
        with conn.cursor() as cur:  # Используется LoggingCursor
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            row = cur.fetchone()
            return dict(row) if row else None

    def fetch_all(
        self,
        query: Union[str, sql.SQL],
        params: Optional[tuple] = None,
        conn=None,
    ) -> List[Dict[str, Any]]:
        """Выполнить запрос и вернуть все строки как список словарей."""
        if conn is None:
            with self.get_connection() as loc_conn:
                return self._fetch_all(loc_conn, query, params)
        return self._fetch_all(conn, query, params)

    def _fetch_all(self, conn, query, params):
        with conn.cursor() as cur:  # Используется LoggingCursor
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            rows = cur.fetchall()
            return [dict(row) for row in rows]

    def close(self):
        """Закрыть все соединения в пуле."""
        if self._pool:
            logger.info("Closing connection pool.")
            self._pool.closeall()
            self._pool = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_bill(self, bill_no: int) -> Optional[Dict[str, Any]]:
        """Возвращает данные счёта."""
        logger.info("Fetching bill data for number: %s", bill_no)
        return self.fetch_one(SELECT_BILL, (bill_no,))

    def get_bill_items(self, bill_no: int) -> List[Dict[str, Any]]:
        """Возвращает данные строк счёта."""
        logger.info("Fetching bill items for number: %s", bill_no)
        # Запрос SEL_BILL_ITEMS использует bill_no дважды
        return self.fetch_all(SEL_BILL_ITEMS, (bill_no, bill_no))

    def get_seller(self, bill_no: int) -> Optional[Dict[str, Any]]:
        """Возвращает данные продавца."""
        logger.info("Fetching seller data for bill number: %s", bill_no)
        return self.fetch_one(SEL_SELLER, (bill_no,))

    def get_buyer(self, buyer_kod: int) -> Optional[Dict[str, Any]]:
        """Возвращает данные покупателя."""
        logger.info("Fetching buyer data for kod: %s", buyer_kod)
        return self.fetch_one(SEL_BUYER, (buyer_kod,))

    def log_upd_generation(self, bill_no, upd_number, upd_date, output_path):
        """Протоколирует создание УПД."""
        logger.info("Logging UPD generation for bill: %s, UPD: %s", bill_no, upd_number)
        self.execute(INS_LOG, (bill_no, upd_number, upd_date, str(output_path)))


def extract_data_from_db(pg_manager: PGManager, invoice_number: int) -> Settings:
    """
    Извлекает данные из PostgreSQL и преобразует их в формат Settings.

    Args:
        pg_manager: Экземпляр PGManager.
        invoice_number: Номер счёта.

    Returns:
        Settings: Объект с данными продавца, покупателя, товаров и т.д.
    """
    logger.info("Starting data extraction for invoice number: %s", invoice_number)

    # 1. Получить основные данные счёта
    bill_data = pg_manager.get_bill(invoice_number)
    if not bill_data:
        raise ValueError(f"Bill with number {invoice_number} not found.")

    seller_data = pg_manager.get_seller(invoice_number)
    if not seller_data:
        raise ValueError(f"Seller data for bill {invoice_number} not found.")

    buyer_data = pg_manager.get_buyer(bill_data['buyer_id'])
    if not buyer_data:
        raise ValueError(f"Buyer data for kod {bill_data['buyer_id']} not found.")

    # 2. Получить позиции счёта
    bill_items_raw = pg_manager.get_bill_items(invoice_number)

    # 3. Преобразовать в модели pydantic/dataclass
    #    Предполагаем, что vat_rate_src и vat_amount_src вычисляются из price_with_vat
    #    или других данных. Примерная логика:
    #    vat_rate_str = seller_data.get('vat_rate', '20%') # например
    #    rate_percent = float(vat_rate_str.replace('%', '')) / 100
    #    total_without_vat = total_with_vat / (1 + rate_percent)
    #    vat_amount = total_with_vat - total_without_vat
    #    Пока используем заглушки, так как точная формула неизвестна.
    bill_items = []
    for raw_item in bill_items_raw:
        # Пример вычисления суммы с НДС
        sum_with_vat = raw_item['quantity'] * raw_item['price_with_vat']
        # Заглушка для НДС
        vat_rate_str = seller_data.get('vat_rate', '20%')
        rate_decimal = float(vat_rate_str.replace('%', '')) / 100
        sum_without_vat = sum_with_vat / (1 + rate_decimal)
        vat_amount_calc = sum_with_vat - sum_without_vat

        item = BillItem(
            row_num=raw_item['row_num'],
            article=raw_item['article'],
            name=raw_item['item_name'],
            quantity=raw_item['quantity'],
            sum_with_vat=sum_with_vat,
            vat_rate_src=vat_rate_str,
            vat_amount_src=vat_amount_calc,
            kiz=raw_item.get('kiz', '')  # Может быть None
        )
        bill_items.append(item)

    # 4. Создать объект Settings
    settings = build_settings(seller_data, buyer_data)
    logger.info("Data extraction completed successfully for invoice number: %s", invoice_number)
    return settings
