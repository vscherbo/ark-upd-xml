#!/usr/bin/env python
"""
cli_client.py - CLI-инструмент для генерации УПД.
"""
import argparse
import logging
import sys
from pathlib import Path

from data_extractor import PGManager, extract_data_from_db
from db_mapping import BillItem  # Для создания списка позиций
from filename_generator import generate_filename
from upd_generator import UPDGenerator

# --- Настройка логирования ---
logger = logging.getLogger(__name__)
LOG_FORMAT = '[%(filename)-22s:%(lineno)4s - %(funcName)20s()] \
            %(levelname)-7s | %(asctime)-15s | %(message)s'

# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)


def main():
    """Основная функция CLI-клиента."""
    parser = argparse.ArgumentParser(description="Generate UPD XML file.")
    parser.add_argument("--invoice-number", type=int, required=True, help="Invoice number")
    parser.add_argument("--upd-number", type=int, required=True, help="UPD number")

    args = parser.parse_args()

    invoice_number = args.invoice_number
    upd_number = args.upd_number

    logger.info("CLI Client started. Invoice: %s, UPD: %s", invoice_number, upd_number)

    # --- 1. Подготовка ---
    output_dir = Path("output/")
    output_dir.mkdir(exist_ok=True)  # Создать, если не существует
    filename = generate_filename(upd_number)
    output_path = output_dir / filename

    xsd_path = Path("ON_NSCHFDOPPR.xsd")  # Предполагаем, что файл рядом
    if not xsd_path.exists():
        logger.error("XSD file not found at: %s", xsd_path)
        sys.exit(1)  # Завершить с ошибкой

    # --- 2. Извлечение данных ---
    # Используем строку подключения из переменной окружения, например:
    # export DATABASE_URL="postgresql://my_user@my_host/my_db_name"
    # или передаём её явно в конструктор PGManager
    # Здесь предполагаем, что DATABASE_URL установлен
    try:
        pg_manager = PGManager()  # Использует DATABASE_URL из env
        with pg_manager:  # Управление соединением через контекстный менеджер
            settings = extract_data_from_db(pg_manager, invoice_number)
            # Заглушка: получить bill_items из extract_data_from_db
            # На практике, extract_data_from_db должен возвращать и BillItems
            # или другой способ получения списка позиций
            # Предположим, что мы можем получить их отдельным вызовом или они встроены в Settings
            # Для простоты, создадим заглушку для bill_items
            # В реальной реализации, bill_items должны быть получены внутри extract_data_from_db
            # и возвращены вместе с settings
            # ИЛИ extract_data_from_db возвращает более комплексный объект
            # содержащий и settings и bill_items
            # --- ВАЖНО ---
            # Функция extract_data_from_db должна быть изменена, чтобы возвращать
            # список объектов BillItem, например, кортеж (settings, bill_items)
            # или новый класс/словарь с обоими полями.
            # Пока возвращаем заглушку.
            # Правильная реализация extract_data_from_db должна включать:
            # bill_items_raw = pg_manager.get_bill_items(invoice_number)
            # bill_items = [BillItem(..., name=item['item_name'], ...) for item in bill_items_raw]
            # return settings, bill_items
            # И здесь:
            # settings, bill_items = extract_data_from_db(pg_manager, invoice_number)

            # --- ЗАГЛУШКА ---
            from datetime import date
            bill_items = [
                BillItem(row_num=1, article="ART001", name="Товар 1", quantity=2.0,
                         sum_with_vat=5982.0, vat_rate_src="22%", vat_amount_src=1078.72, kiz=""),
                BillItem(row_num=2, article="ART002", name="Товар 2", quantity=3.0,
                         sum_with_vat=14169.0, vat_rate_src="22%", vat_amount_src=2555.07, kiz="")
            ]
            # Предположим, что дата счёта извлекается из bill_data
            # bill_data = pg_manager.get_bill(invoice_number)
            # invoice_date = bill_data['bill_date'].strftime("%d.%m.%Y")
            invoice_date = date.today().strftime("%d.%m.%Y")  # Заглушка
            # --- ЗАГЛУШКА ---

    except ValueError as e:
        logger.error("Data extraction failed: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Database error during extraction: %s", e)
        sys.exit(1)

    # --- 3. Генерация и сохранение ---
    try:
        generator = UPDGenerator(xsd_path)
        success = generator.generate_and_save(
            settings=settings,
            bill_items=bill_items,
            invoice_number=str(invoice_number),
            invoice_date=invoice_date,  # DD.MM.YYYY
            upd_number=upd_number,
            output_path=output_path
        )
        if not success:
            logger.error("UPD generation or validation failed.")
            sys.exit(1)
    except Exception as e:
        logger.error("Error during UPD generation or save: %s", e)
        sys.exit(1)

    # --- 4. Логирование в БД ---
    try:
        # Предполагаем, что дата УПД - это дата счёта или текущая дата
        # log_upd_generation ожидает строку даты в формате DD.MM.YYYY
        pg_manager.log_upd_generation(
            bill_no=invoice_number,
            upd_number=upd_number,
            upd_date=invoice_date,
            output_path=output_path
        )
    except Exception as e:
        # Не критично для основного процесса, но логируем
        logger.warning("Failed to log UPD generation to DB: %s", e)

    logger.info("UPD XML file generated successfully: %s", output_path)


if __name__ == "__main__":
    main()
