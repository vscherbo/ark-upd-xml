#!/usr/bin/env python
"""
upd_generator.py - Генерация XML УПД версии 5.03 с валидацией по XSD.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Union

from lxml import etree

from db_mapping import BillData

logger = logging.getLogger(__name__)


class UpdGenerator:
    """
    Генератор XML-документа УПД.
    """

    def __init__(self, xsd_path: Union[str, Path]):
        """
        Args:
            xsd_path: Путь к файлу XSD-схемы.
        """
        self.xsd_path = Path(xsd_path)
        self.xsd_schema = None
        self._load_xsd()

    def _load_xsd(self):
        """Загружает и парсит XSD-схему."""
        with open(self.xsd_path, "rb") as f:
            schema_root = etree.XML(f.read())
        self.xsd_schema = etree.XMLSchema(schema_root)
        logger.info("XSD-схема успешно загружена из %s", self.xsd_path)

    def generate(self, data: BillData) -> str:
        """
        Генерирует XML-строку УПД на основе данных.
        Возвращает валидный XML как строку (с объявлением).
        """
        # Создаём корневой элемент
        root = etree.Element(
            "Файл",
            ИдФайл=data.upd_file,
            ВерсФорм="5.03",
            ВерсПрог="УПД-Генератор 1.0"
            # nsmap={None: "http://www.w3.org/2001/XMLSchema"}  # необязательно
        )

        # Документ
        doc = etree.SubElement(
            root,
            "Документ",
            КНД="1115131",
            Функция=data.function,
            ПоФактХЖ=data.fact_housing_name or "",
            НаимДокОпр=data.doc_name_operator or "",
            ДатаИнфПр=data.upd_date.strftime("%d.%m.%Y"),
            ВремИнфПр=datetime.now().strftime("%H.%M.%S"),
            НаимЭконСубСост=f"{data.seller.name}, ИНН: {data.seller.inn}",
        )

        # СвСчФакт
        sv_sch = etree.SubElement(
            doc,
            "СвСчФакт",
            НомерДок=data.upd_number,
            ДатаДок=data.upd_date.strftime("%d.%m.%Y"),
        )

        # Продавец
        sv_prod = etree.SubElement(sv_sch, "СвПрод")
        id_sv = etree.SubElement(sv_prod, "ИдСв")
        sv_yul = etree.SubElement(
            id_sv,
            "СвЮЛУч",
            НаимОрг=data.seller.name,
            ИННЮЛ=data.seller.inn,
            КПП=data.seller.kpp,
        )
        # Адрес продавца (АдрРФ)
        addr = etree.SubElement(sv_prod, "Адрес")
        addr_rf = etree.SubElement(
            addr,
            "АдрРФ",
            Индекс=data.seller.address.postal_code or "",
            КодРегион=data.seller.address.region_code,
            НаимРегион=data.seller.address.region_name,
            Улица=data.seller.address.street or "",
            Дом=data.seller.address.house or "",
            Корпус=data.seller.address.building or "",
            Кварт=data.seller.address.apartment or "",
        )
        # Можно добавить Город, НаселПункт, если есть

        # ДокПодтвОтгрНом (документ-основание)
        logger.debug('РеквНомерДок=%s', data.upd_number)
        etree.SubElement(
            sv_sch,
            "ДокПодтвОтгрНом",
            РеквНаимДок=data.doc_name_operator or "",
            РеквНомерДок=data.upd_number,
            РеквДатаДок=data.upd_date.strftime("%d.%m.%Y"),
        )

        # Покупатель
        sv_pok = etree.SubElement(sv_sch, "СвПокуп")
        id_sv_pok = etree.SubElement(sv_pok, "ИдСв")
        sv_yul_pok = etree.SubElement(
            id_sv_pok,
            "СвЮЛУч",
            НаимОрг=data.buyer.name,
            ИННЮЛ=data.buyer.inn,
            КПП=data.buyer.kpp,
        )
        addr_pok = etree.SubElement(sv_pok, "Адрес")
        addr_rf_pok = etree.SubElement(
            addr_pok,
            "АдрРФ",
            Индекс=data.buyer.address.postal_code or "",
            КодРегион=data.buyer.address.region_code,
            НаимРегион=data.buyer.address.region_name,
            Улица=data.buyer.address.street or "",
            Дом=data.buyer.address.house or "",
            Корпус=data.buyer.address.building or "",
            Кварт=data.buyer.address.apartment or "",
        )

        # ДенИзм (валюта)
        etree.SubElement(
            sv_sch,
            "ДенИзм",
            КодОКВ="643",
            НаимОКВ="Российский рубль",
        )

        # ДопСвФХЖ1 - можно добавить, если есть
        # if data.function in ("СЧФДОП", "ДОП"):
        #     dop = etree.SubElement(sv_sch, "ДопСвФХЖ1")
        #     # Пример: СпОбстФСЧФДОП="00005" (как в примере)
        #     if data.function == "СЧФДОП":
        #         dop.set("СпОбстФСЧФДОП", "00005")

        # # ИнфПолФХЖ1 - пример
        # inf_pol = etree.SubElement(sv_sch, "ИнфПолФХЖ1")
        # text_inf = etree.SubElement(inf_pol, "ТекстИнф", Идентиф="СвВыбытияМАРК", Значен="3")

        # ТаблСчФакт
        tabl = etree.SubElement(doc, "ТаблСчФакт")
        total_without_vat = 0.0
        total_with_vat = 0.0
        total_vat = 0.0

        for item in data.items:
            # СведТов
            sved = etree.SubElement(
                tabl,
                "СведТов",
                НомСтр=str(item.row_num),
                НаимТов=item.name,
                ОКЕИ_Тов=item.oktei_code,
                НаимЕдИзм=item.oktei_name,
                КолТов=str(item.quantity),
                ЦенаТов=f"{item.price_without_vat:.2f}",
                СтТовБезНДС=f"{item.total_without_vat:.2f}",
                НалСт=item.vat_rate,
                СтТовУчНал=f"{item.total_with_vat:.2f}",
            )

            # ДопСведТов (КИЗ)
            if item.kiz_list:
                dop_tov = etree.SubElement(sved, "ДопСведТов")
                nom_sred = etree.SubElement(dop_tov, "НомСредИдентТов")
                for kiz in item.kiz_list:
                    etree.SubElement(nom_sred, "КИЗ").text = kiz

            # Акциз
            akciz = etree.SubElement(sved, "Акциз")
            etree.SubElement(akciz, "БезАкциз").text = "без акциза"

            # СумНал
            sum_nal = etree.SubElement(sved, "СумНал")
            etree.SubElement(sum_nal, "СумНал").text = f"{item.vat_amount:.2f}"

            total_without_vat += item.total_without_vat
            total_with_vat += item.total_with_vat
            total_vat += item.vat_amount

        # ВсегоОпл
        vsego = etree.SubElement(
            tabl,
            "ВсегоОпл",
            СтТовБезНДСВсего=f"{total_without_vat:.2f}",
            СтТовУчНалВсего=f"{total_with_vat:.2f}",
        )
        sum_nal_vsego = etree.SubElement(vsego, "СумНалВсего")
        etree.SubElement(sum_nal_vsego, "СумНал").text = f"{total_vat:.2f}"

        # СвПродПер (информация о передаче)
        sv_prod_per = etree.SubElement(doc, "СвПродПер")
        sv_per = etree.SubElement(
            sv_prod_per,
            "СвПер",
            СодОпер=data.operation_content,
            ВидОпер=data.operation_type or "",
            ДатаПер=data.transfer_date.strftime("%d.%m.%Y") if data.transfer_date else "",
            ДатаНачПер=data.transfer_start_date.strftime(
                "%d.%m.%Y") if data.transfer_start_date else "",
            ДатаОконПер=data.transfer_end_date.strftime(
                "%d.%m.%Y") if data.transfer_end_date else "",
        )

        # Основание (ОснПер)
        if data.basis_doc_name:
            etree.SubElement(
                sv_per,
                "ОснПер",
                РеквНаимДок=data.basis_doc_name,
                РеквНомерДок=data.basis_doc_number or "",
                РеквДатаДок=data.basis_doc_date.strftime("%d.%m.%Y") if data.basis_doc_date else "",
            )

        # СвЛицПер (лицо, передавшее товар)
        sv_lits = etree.SubElement(sv_per, "СвЛицПер")
        rab_org = etree.SubElement(
            sv_lits,
            "РабОргПрод",
            Должность=data.signer.position or "",
        )
        fio = etree.SubElement(rab_org, "ФИО")
        fio.set("Фамилия", data.signer.last_name)
        fio.set("Имя", data.signer.first_name)
        if data.signer.middle_name:
            fio.set("Отчество", data.signer.middle_name)

        # Транспортировка
        if data.transport_info or data.incoterms:
            tran = etree.SubElement(sv_per, "Тран")
            if data.transport_info:
                tran.set("СвТран", data.transport_info)
            if data.incoterms:
                tran.set("Инкотермс", data.incoterms)
            if data.incoterms_version:
                tran.set("ВерИнкотермс", data.incoterms_version)

        # Подписант
        podp = etree.SubElement(
            doc,
            "Подписант",
            Должн=data.signer.position or "",
            СпосПодтПолном=data.signer.auth_method,
        )
        fio_podp = etree.SubElement(podp, "ФИО")
        fio_podp.set("Фамилия", data.signer.last_name)
        fio_podp.set("Имя", data.signer.first_name)
        if data.signer.middle_name:
            fio_podp.set("Отчество", data.signer.middle_name)

        # Преобразуем в XML-строку
        xml_str = etree.tostring(
            root,
            encoding="windows-1251",
            xml_declaration=True,
            pretty_print=True,
        ).decode("windows-1251")

        # Валидация
        self._validate(xml_str)

        return xml_str

    def _validate(self, xml_str: str):
        """Проверяет XML на соответствие XSD."""
        try:
            parser = etree.XMLParser()
            root = etree.fromstring(xml_str.encode("windows-1251"), parser)
            self.xsd_schema.assertValid(root)
        except etree.DocumentInvalid as e:
            logger.error("Ошибка валидации XSD: %s", e)
            raise
        except Exception as e:
            logger.error("Ошибка при валидации: %s", e)
            raise

    def generate_and_save(self, data: BillData, output_path: Union[str, Path]) -> str:
        """
        Генерирует XML и сохраняет в файл.
        Возвращает путь к сохранённому файлу.
        """
        xml_str = self.generate(data)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="windows-1251") as f:
            f.write(xml_str)
        logger.info("XML сохранён в %s", output_path)
        return str(output_path)
