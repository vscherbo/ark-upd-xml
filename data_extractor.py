"""
db_extractor.py - Менеджер подключения к PostgreSQL.

Обеспечивает:
- Подключение к БД с параметрами из переменных окружения
- Выполнение запросов с параметрами (защита от SQL-инъекций)
- Контекстный менеджер для транзакций
- Логирование всех запросов и ошибок
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Union

import psycopg2
import psycopg2.extras
from psycopg2 import sql
from psycopg2.pool import SimpleConnectionPool

logger = logging.getLogger(__name__)


SELECT_BILL = 'SELECT "№ счета" AS bill_no, "Дата счета" AS bill_date, "фирма" AS seller_id, \
"Код" AS buyer_id FROM arc_energo."Счета" WHERE "№ счета" = %s'

SEL_BILL_ITEMS = 'SELECT bc."ПозицияСчета" AS row_num, bc."КодСодержания" AS article, \
bc."Наименование" AS item_name, bc."Кол-во" AS quantity, \
bc."Ед Изм" AS mes_unit, bc."ЦенаНДС" AS price_with_vat, NULL AS kiz \
FROM arc_energo."Содержание счета" bc \
WHERE "№ счета" = %s \
UNION \
SELECT bc."ПозицияСчета", bc."КодСодержания", bc."Наименование", bc."Кол-во", \
bc."Ед Изм", bc."ЦенаНДС" \
, em.mark as kiz \
FROM arc_energo."Содержание счета" bc \
JOIN arc_energo."Расход" r ON r."Счет" = "№ счета" AND bc."КодПозиции" = r."КодПозиции" \
JOIN arc_energo.entering_marked em ON em."КодОтгрузки" =  r."КодОтгрузки" \
WHERE "№ счета" = %s \
ORDER BY 1;'
# ORDER BY bc."ПозицияСчета";'


#    '22%%' AS vat_rate,
#    -- vat_rate(b."фирма", b."Код", b."Дата счета"::date)|| "%" AS vat_rate,
SEL_SELLER = """SELECT
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
    vat_rate(b."фирма", b."Код", b."Дата счета"::date)|| '%%' AS vat_rate,
    '' AS tax_system,
    fs.signer_position,
    fs.signer_fio
FROM
arc_energo."Счета" b
JOIN arc_energo."ФирмаРеквизиты" fr ON fr."КодРеквизитовФирмы" = b."КодРеквизитовФирмы"
JOIN arc_energo."Фирма" f ON fr."КодФирмы" = f."КлючФирмы"
LEFT JOIN LATERAL (
    SELECT signer_fio, signer_position
    FROM arc_energo.firm_signer(f."КлючФирмы", 'УПД_ОСЗ') -- ???
) AS fs ON true
WHERE b."№ счета" = %s;"""


SEL_BUYER = """SELECT e."ИНН" AS inn,
e."КПП" AS kpp,
e."Предприятие" AS name,
e."ЮрАдрес" AS address
FROM arc_energo."Предприятия" e
WHERE e."Код" = %s;"""

INS_LOG = """INSERT INTO rep.upd_xml_log
                 (bill_no, upd_number, upd_date, generated_at, xml_file_path, status)
                 VALUES (%s, %s, %s, NOW(), %s, 'success')"""


class PGManager:
    """
    Менеджер подключения к PostgreSQL.

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
            self._pool = SimpleConnectionPool(
                self.min_conn,
                self.max_conn,
                self.dsn,
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
        return self._pool

    @contextmanager
    def get_connection(self):
        """Получить соединение из пула (контекстный менеджер)."""
        pool = self._get_pool()
        conn = pool.getconn()
        try:
            yield conn
        finally:
            pool.putconn(conn)

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
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def execute(
        self,
        query: Union[str, sql.SQL],
        params: Optional[Dict[str, Any]] = None,
        conn=None,
    ) -> None:
        """
        Выполнить запрос без возврата результата (INSERT, UPDATE, DELETE).

        Args:
            query: SQL-запрос (строка или sql.SQL).
            params: Параметры для подстановки (словарь или кортеж).
            conn: Соединение (если не указано, берётся новое из пула).
        """
        if conn is None:
            with self.get_connection() as loc_conn:
                self._execute(loc_conn, query, params)
        else:
            self._execute(loc_conn, query, params)

    def _execute(self, conn, query, params):
        with conn.cursor() as cur:
            logger.debug("Executing query: %s", query)
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)

    def fetch_one(
        self,
        query: Union[str, sql.SQL],
        params: Optional[Dict[str, Any]] = None,
        conn=None,
    ) -> Optional[Dict[str, Any]]:
        """Выполнить запрос и вернуть одну строку как словарь."""
        if conn is None:
            with self.get_connection() as loc_conn:
                return self._fetch_one(loc_conn, query, params)
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

    def fetch_all(
        self,
        query: Union[str, sql.SQL],
        params: Optional[Dict[str, Any]] = None,
        conn=None,
    ) -> List[Dict[str, Any]]:
        """Выполнить запрос и вернуть все строки как список словарей."""
        if conn is None:
            with self.get_connection() as loc_conn:
                return self._fetch_all(loc_conn, query, params)
        return self._fetch_all(loc_conn, query, params)

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
        """Закрыть все соединения в пуле."""
        if self._pool:
            self._pool.closeall()
            self._pool = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_bill(self, bill_no: int) -> Optional[Dict]:
        """ Возвращает данные счёта """
        return self.fetch_one(SELECT_BILL, (bill_no,))

    def get_bill_items(self, bill_no: int) -> List[Dict]:
        """ Возвращает данные строк счёта """
        return self.fetch_all(SEL_BILL_ITEMS, (bill_no, bill_no))

    def get_seller(self, bill_no: int) -> Optional[Dict]:
        """ Возвращает данные продавца """
        return self.fetch_one(SEL_SELLER, (bill_no,))

    def get_buyer(self, buyer_kod: int) -> Optional[Dict]:
        """ Возвращает данные покупателя """
        return self.fetch_one(SEL_BUYER, (buyer_kod,))

    def log_upd_generation(self, bill_no,
                           upd_number,
                           upd_date,
                           output_path):
        """ Протоколирует создание УПД """
        self.execute(INS_LOG,
                     (bill_no, upd_number, upd_date, str(output_path))
                     )
