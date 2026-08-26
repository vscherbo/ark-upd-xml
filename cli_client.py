#!/usr/bin/env python
"""
cli_client.py - CLI-инструмент для генерации УПД.
"""

import argparse
import logging
import sys
from pathlib import Path

from data_extractor import DataExtractor
from filename_generator import FilenameGenerator
from upd_generator import UpdGenerator

LOG_FORMAT = '[%(filename)-22s:%(lineno)4s - %(funcName)20s()] \
            %(levelname)-7s | %(asctime)-15s | %(message)s'

# logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Генерация УПД (Универсальный передаточный документ) версии 5.03"
    )
    parser.add_argument(
        "--bill-number",
        type=int,
        required=True,
        help="Номер счёта (из базы данных)",
    )
    parser.add_argument(
        "--upd-number",
        type=str,
        required=True,
        help="Номер УПД (присваиваемый при генерации)",
    )
    parser.add_argument(
        "--address-format",
        choices=["rf", "gar"],
        default="rf",
        help="Формат адреса: rf - АдрРФ, gar - АдрГАР",
    )
    parser.add_argument(
        "--use-json",
        action="store_true",
        help="Использовать JSON-файл вместо БД (для отладки)",
    )
    parser.add_argument(
        "--json-path",
        type=str,
        default="sample_data.json",
        help="Путь к JSON-файлу с данными (если --use-json)",
    )
    parser.add_argument(
        "--xsd-path",
        type=str,
        default="ON_NSCHFDOPPR_1_997_01_05_03_05.xsd",
        help="Путь к XSD-схеме",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Каталог для сохранения XML-файлов",
    )

    args = parser.parse_args()

    # Создаём каталог для вывода
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Извлечение данных
    extractor = DataExtractor(
        use_json=args.use_json,
        json_path=args.json_path,
        address_format=args.address_format,
    )
    try:
        bill_data = extractor.get_bill_data(args.bill_number, args.upd_number)
    except Exception as e:
        logger.error("Ошибка извлечения данных: %s", e)
        sys.exit(1)

    logger.info("Данные извлечены, количество позиций в счёте: %s", len(bill_data.items))

    # seller_id = bill_data.seller.inn          # выбор ЭДО Ид
    # buyer_id = bill_data.buyer.inn
    seller_id = '2LT-600072763'
    buyer_id = '2LT-600070554'

    has_kiz = any(item.kiz_list for item in bill_data.items)

    id_file = FilenameGenerator.generate(seller_id, buyer_id, has_kiz)
    logger.debug('id_file=%s', id_file)
    bill_data.upd_file = id_file

    filename = id_file + ".xml"
    output_path = output_dir / filename

    # Генерация XML (внутри используется bill_data.upd_number)
    generator = UpdGenerator(xsd_path=args.xsd_path)
    try:
        generator.generate_and_save(bill_data, output_path)
        logger.info("УПД успешно сгенерирован: %s", output_path)
    except Exception as e:
        logger.error("Ошибка генерации УПД: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
