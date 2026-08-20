#!/usr/bin/env python
"""
upd_generator.py - Генератор XML-документа УПД.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from lxml import etree

from db_mapping import BillItem, Settings

logger = logging.getLogger(__name__)


class UPDGeneratorError(Exception):
    """Исключение, возникающее при ошибках генерации УПД."""
    pass


class UPDGenerator:
    """
    Класс для генерации XML-документа УПД по шаблону и данным из Settings.
    """

    def __init__(self, xsd_path: Path):
        """
        Инициализирует генератор с путём к XSD-схеме.

        Args:
            xsd_path: Путь к файлу XSD-схемы.
        """
        self.xsd_path = xsd_path
        self.schema = self._load_schema(xsd_path)

    def _load_schema(self, xsd_path: Path) -> etree.XMLSchema:
        """Загружает XSD-схему из файла."""
        logger.info("Loading XSD schema from: %s", xsd_path)
        try:
            with open(xsd_path, 'rb') as f:  # Открываем бинарно
                schema_doc = etree.parse(f)
            schema = etree.XMLSchema(schema_doc)
            logger.info("XSD schema loaded successfully.")
            return schema
        except etree.XMLSyntaxError as e:
            logger.error("Failed to parse XSD schema: %s", e)
            raise UPDGeneratorError(f"Invalid XSD syntax: {e}")
        except FileNotFoundError:
            logger.error("XSD file not found: %s", xsd_path)
            raise UPDGeneratorError(f"XSD file not found: {xsd_path}")

    def validate_xml(self, xml_doc: etree._ElementTree) -> bool:
        """Валидирует XML-документ по загруженной схеме."""
        logger.debug("Validating XML document against schema.")
        is_valid = self.schema.validate(xml_doc)
        if not is_valid:
            logger.error("XML validation failed. Errors:")
            for error in self.schema.error_log:
                logger.error("- %s", error.message)
        else:
            logger.info("XML document validated successfully.")
        return is_valid

    def generate_xml(self, settings: Settings, bill_items: List[BillItem], invoice_number: str,
                     invoice_date: str, upd_number: int) -> etree._ElementTree:
        """
        Генерирует XML-документ УПД.

        Args:
            settings: Объект Settings с данными.
            bill_items: Список позиций счёта.
            invoice_number: Номер счёта.
            invoice_date: Дата счёта (DD.MM.YYYY).
            upd_number: Номер УПД.

        Returns:
            etree._ElementTree: Сгенерированный XML-документ.
        """
        logger.info("Starting XML generation for UPD number: %s", upd_number)

        # --- Создание корневого элемента ---
        # Используем кириллические имена тегов и атрибутов из XSD
        root = etree.Element("{http://www.w3.org/2001/XMLSchema}Файл")  # Пример namespace
        # В данном случае, namespace в XSD для элементов не указан, поэтому используем просто имена
        # Но в XML они должны быть в кодировке, соответствующей XSD и output.
        # lxml по умолчанию использует UTF-8. XSD в windows-1251.
        # При сериализации в XML нужно указать encoding='windows-1251'.

        # Корректируем пространство имён и имена элементов под XSD 5.03
        # Пример namespace, если бы было объявлено
        NSMAP = {None: "urn:cbr.ru:fn:ON_NSCHFDOPPR_5_03"}
        # Файл
        root = etree.Element("Файл", nsmap=NSMAP)
        root.set("ИдФайл", f"ON_NSCHFDOPPR_GENERATED_{upd_number}")  # Пример ID
        root.set("ВерсФорм", "5.03")  # Версия 5.03
        root.set("ВерсПрог", "ARK-UPD-XML Generator 1.0")

        # Документ
        doc = etree.SubElement(root, "Документ")
        doc.set("КНД", "1115131")
        doc.set("Функция", "СЧФДОП")  # Счет-фактура и документ об отгрузке
        doc.set("ПофактХЖ", "Документ об отгрузке товаров (выполнении работ), передаче имущественных прав (документ об оказании услуг)")
        doc.set("НаимДокОпр", "Счет-фактура и документ об отгрузке товаров (выполнении работ), передаче имущественных прав (документ об оказании услуг)")
        doc.set("ДатаИнфПр", datetime.now().strftime("%d.%m.%Y"))  # Дата формирования
        doc.set("ВремИнфПр", datetime.now().strftime("%H.%M.%S"))  # Время формирования
        # Составитель
        doc.set("НаимЭконСубСост", f"{settings.seller.name}, ИНН: {settings.seller.inn}")

        # СвСчФакт (Сведения о счете-фактуре)
        sv_sch_fact = etree.SubElement(doc, "СвСчФакт")
        sv_sch_fact.set("НомерСчФ", invoice_number)
        sv_sch_fact.set("ДатаСчФ", invoice_date)
        sv_sch_fact.set("КодОКВ", "643")  # RUB

        # СвПрод (Продавец)
        sv_prod = etree.SubElement(sv_sch_fact, "СвПрод")
        id_sv_prod = etree.SubElement(sv_prod, "ИдСв")
        sv_yul_uch = etree.SubElement(id_sv_prod, "СвЮЛУч")
        sv_yul_uch.set("НаимОрг", settings.seller.name)
        sv_yul_uch.set("ИННЮЛ", settings.seller.inn)
        sv_yul_uch.set("КПП", settings.seller.kpp)

        addr_prod = etree.SubElement(sv_prod, "Адрес")
        addr_rf_prod = etree.SubElement(addr_prod, "АдрРФ")
        addr_rf_prod.set("Индекс", settings.seller.postal_code)
        addr_rf_prod.set("КодРегион", settings.seller.region_code)
        # XSD не требует НаимРегион в АдрРФ
        # addr_rf_prod.set("НаимРегион", settings.seller.region_name)
        addr_rf_prod.set("Город", settings.seller.city)
        addr_rf_prod.set("Улица", settings.seller.street)
        addr_rf_prod.set("Дом", settings.seller.house)
        addr_rf_prod.set("Корпус", " ")  # Заглушка
        addr_rf_prod.set("Кварт", settings.seller.apartment)

        # СвПокуп (Покупатель)
        sv_pokup = etree.SubElement(sv_sch_fact, "СвПокуп")
        id_sv_pokup = etree.SubElement(sv_pokup, "ИдСв")
        sv_yul_uch_pokup = etree.SubElement(id_sv_pokup, "СвЮЛУч")
        sv_yul_uch_pokup.set("НаимОрг", settings.buyer.name)
        sv_yul_uch_pokup.set("ИННЮЛ", settings.buyer.inn)
        sv_yul_uch_pokup.set("КПП", settings.buyer.kpp)

        addr_pokup = etree.SubElement(sv_pokup, "Адрес")
        addr_rf_pokup = etree.SubElement(addr_pokup, "АдрРФ")
        addr_rf_pokup.set("Индекс", settings.buyer.postal_code)
        addr_rf_pokup.set("КодРегион", settings.buyer.region_code)
        # addr_rf_pokup.set("НаимРегион", settings.buyer.region_name)
        addr_rf_pokup.set("Город", settings.buyer.city)
        addr_rf_pokup.set("Улица", settings.buyer.street)
        addr_rf_pokup.set("Дом", settings.buyer.house)
        addr_rf_pokup.set("Корпус", settings.buyer.building or " ")
        addr_rf_pokup.set("Кварт", settings.buyer.apartment or " ")

        # Таблица СчФакт (Таблица с товарами)
        table_sch_fact = etree.SubElement(doc, "ТаблСчФакт")
        total_sum_without_vat = 0.0
        total_sum_with_vat = 0.0
        total_vat_amount = 0.0

        for item in bill_items:
            sv_tov = etree.SubElement(table_sch_fact, "СведТов")
            sv_tov.set("НомСтр", str(item.row_num))
            sv_tov.set("НаимТов", item.name)
            sv_tov.set("ОКЕИ_Тов", "796")  # шт - пример
            sv_tov.set("НаимЕдИзм", "шт")  # шт - пример
            sv_tov.set("КолТов", str(item.quantity))
            sv_tov.set("ЦенаТов", str(item.sum_with_vat / item.quantity))  # Цена за единицу
            sv_tov.set("СтТовБезНДС", str(item.sum_with_vat /
                       (1 + float(item.vat_rate_src.replace('%', ''))/100)))
            sv_tov.set("НалСт", item.vat_rate_src)
            sv_tov.set("СтТовУчНал", str(item.sum_with_vat))

            # Акциз
            akc = etree.SubElement(sv_tov, "Акциз")
            etree.SubElement(akc, "БезАкциз").text = "без акциза"

            # Сумма НДС
            nds = etree.SubElement(sv_tov, "СумНал")
            etree.SubElement(nds, "СумНал").text = str(item.vat_amount_src)

            # Обновляем итоговые суммы
            total_sum_with_vat += item.sum_with_vat
            total_vat_amount += item.vat_amount_src
            total_sum_without_vat += item.sum_with_vat - item.vat_amount_src

        # Всего к оплате
        total_opl = etree.SubElement(table_sch_fact, "ВсегоОпл")
        total_opl.set("СтТовБезНДСВсего", f"{total_sum_without_vat:.2f}")
        total_opl.set("СтТовУчНалВсего", f"{total_sum_with_vat:.2f}")

        nds_total = etree.SubElement(total_opl, "СумНалВсего")
        etree.SubElement(nds_total, "СумНал").text = f"{total_vat_amount:.2f}"

        # СвПродПер (Сведения о передаче)
        sv_prod_per = etree.SubElement(doc, "СвПродПер")
        sv_per = etree.SubElement(sv_prod_per, "СвПер")
        sv_per.set("СодОпер", "Товары переданы")
        sv_per.set("ВидОпер", "продажа")
        sv_per.set("ДатаПер", invoice_date)  # Дата передачи
        # sv_per.set("ДатаНач", invoice_date) # Если требуется
        # sv_per.set("ДатаОкон", invoice_date)

        # Основание
        osn_per = etree.SubElement(sv_per, "ОснПер")
        osn_per.set("НаимОсн", "Договор продажи")
        osn_per.set("НомОсн", f"Дог-{invoice_number}")
        osn_per.set("ДатаОсн", invoice_date)

        # Лицо, передавшее товар
        sv_lic_p = etree.SubElement(sv_per, "СвЛицПер")
        rab_org_prod = etree.SubElement(sv_lic_p, "РабОргПрод")
        rab_org_prod.set("Должность", settings.signer.position)
        fio_el = etree.SubElement(rab_org_prod, "ФИО")
        fio_el.set("Фамилия", settings.signer.last_name)
        fio_el.set("Имя", settings.signer.first_name)
        fio_el.set("Отчество", settings.signer.middle_name)

        # Подписант
        podpisant = etree.SubElement(doc, "Подписант")
        podpisant.set("ОблПолн", "0")
        podpisant.set("Статус", "1")
        podpisant.set("ОснПолн", "Должностные обязанности")
        podpisant.set("Должн", settings.signer.position)

        fio_podp = etree.SubElement(podpisant, "ФИО")
        fio_podp.set("Фамилия", settings.signer.last_name)
        fio_podp.set("Имя", settings.signer.first_name)
        fio_podp.set("Отчество", settings.signer.middle_name)

        xml_doc = etree.ElementTree(root)
        logger.info("XML generation completed for UPD number: %s", upd_number)
        return xml_doc

    def save_xml(self, xml_doc: etree._ElementTree, output_path: Path):
        """
        Сохраняет XML-документ в файл.

        Args:
            xml_doc: XML-документ.
            output_path: Путь для сохранения файла.
        """
        logger.info("Saving XML document to: %s", output_path)
        # Устанавливаем кодировку windows-1251 при сохранении
        try:
            # serializing to bytes with cp1251 encoding
            xml_bytes = etree.tostring(xml_doc, pretty_print=True,
                                       encoding='cp1251', xml_declaration=True)
            with open(output_path, 'wb') as f:  # Open in binary mode for bytes
                f.write(xml_bytes)
            logger.info("XML document saved successfully.")
        except Exception as e:
            logger.error("Failed to save XML document: %s", e)
            raise UPDGeneratorError(f"Failed to save XML: {e}")

    def generate_and_save(self, settings: Settings, bill_items: List[BillItem], invoice_number: str,
                          invoice_date: str, upd_number: int, output_path: Path) -> bool:
        """
        Генерирует XML, валидирует его и сохраняет в файл.

        Args:
            settings: Объект Settings с данными.
            bill_items: Список позиций счёта.
            invoice_number: Номер счёта.
            invoice_date: Дата счёта (DD.MM.YYYY).
            upd_number: Номер УПД.
            output_path: Путь для сохранения файла.

        Returns:
            bool: True, если успешно, False в противном случае.
        """
        logger.info("Starting full generation and save process for UPD number: %s", upd_number)
        try:
            xml_doc = self.generate_xml(
                settings, bill_items, invoice_number, invoice_date, upd_number)
            is_valid = self.validate_xml(xml_doc)
            if not is_valid:
                logger.error("Generated XML is not valid according to XSD. Not saving.")
                return False
            self.save_xml(xml_doc, output_path)
            logger.info(
                "Full generation and save process completed successfully for UPD number: %s",
                upd_number)
            return True
        except UPDGeneratorError as e:
            logger.error("Generation or save failed due to generator error: %s", e)
            return False
        except Exception as e:
            logger.error("Unexpected error during generation or save: %s", e)
            return False
