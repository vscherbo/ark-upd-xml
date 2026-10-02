#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
upd_generator.py - Генерация XML УПД версии 5.03 с валидацией по XSD.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Union

from lxml import etree

from db_mapping import AddressGAR, AddressRF, BillData, Signer

logger = logging.getLogger(__name__)


def _fmt_date(d) -> str:
    """Форматирует date в ДД.ММ.ГГГГ или возвращает пустую строку."""
    return d.strftime("%d.%m.%Y") if d else ""


def _add_fio(parent, signer: Signer) -> etree.Element:
    """Добавляет дочерний элемент <ФИО> с атрибутами из signer."""
    fio = etree.SubElement(parent, "ФИО")
    fio.set("Фамилия", signer.last_name)
    fio.set("Имя", signer.first_name)
    if signer.middle_name:
        fio.set("Отчество", signer.middle_name)
    return fio


class UpdGenerator:
    """Генератор XML-документа УПД."""

    def __init__(self, xsd_path: Union[str, Path]):
        """
        Args:
            xsd_path: Путь к файлу XSD-схемы.
        """
        self.xsd_path = Path(xsd_path)
        self.xsd_schema = None
        self._load_xsd()

    # ------------------------------------------------------------------
    # Загрузка XSD
    # ------------------------------------------------------------------
    def _load_xsd(self) -> None:
        with open(self.xsd_path, "rb") as f:
            schema_root = etree.XML(f.read())
        self.xsd_schema = etree.XMLSchema(schema_root)
        logger.info("XSD-схема успешно загружена из %s", self.xsd_path)

    # ------------------------------------------------------------------
    # Хелперы
    # ------------------------------------------------------------------
    def _add_address(self, parent: etree.Element, address) -> None:
        """Добавляет <Адрес> с <АдрРФ> или <АдрГАР> в зависимости от типа."""
        if isinstance(address, AddressRF):
            addr = etree.SubElement(parent, "Адрес")

            attrs: Dict[str, str] = {
                "КодРегион": address.region_code,
                "НаимРегион": address.region_name,
            }
            # Индекс — строго 6 символов
            if address.postal_code and len(address.postal_code) == 6:
                attrs["Индекс"] = address.postal_code
            # Остальные — только если непустые
            if address.district:
                attrs["Район"] = address.district
            if address.city:
                attrs["Город"] = address.city
            if address.locality:
                attrs["НаселПункт"] = address.locality
            if address.street:
                attrs["Улица"] = address.street
            if address.house:
                attrs["Дом"] = address.house
            if address.building:
                attrs["Корпус"] = address.building
            if address.apartment:
                attrs["Кварт"] = address.apartment
            # if address.extra_info:
            #    attrs["ИныеСвед"] = address.extra_info

            etree.SubElement(addr, "АдрРФ", **attrs)

        elif isinstance(address, AddressGAR):
            addr = etree.SubElement(parent, "Адрес")
            gar_attrs = {"ИдНом": address.id_num}
            if address.index and len(address.index) == 6:
                gar_attrs["Индекс"] = address.index
            gar = etree.SubElement(addr, "АдрГАР", **gar_attrs)
            etree.SubElement(gar, "Регион").text = address.region_code
            etree.SubElement(gar, "НаимРегион").text = address.region_name
            if address.municipal_district:
                etree.SubElement(
                    gar, "МуниципРайон",
                    ВидКод=address.municipal_district.vid_kod,
                    Наим=address.municipal_district.naim,
                )
            if address.city_settlement:
                etree.SubElement(
                    gar, "ГородСелПоселен",
                    ВидКод=address.city_settlement.vid_kod,
                    Наим=address.city_settlement.naim,
                )
            if address.locality:
                etree.SubElement(
                    gar, "НаселенПункт",
                    Вид=address.locality.vid,
                    Наим=address.locality.naim,
                )
            if address.planning_structure:
                etree.SubElement(
                    gar, "ЭлПланСтруктур",
                    Тип=address.planning_structure.tip,
                    Наим=address.planning_structure.naim,
                )
            if address.road_network:
                etree.SubElement(
                    gar, "ЭлУлДорСети",
                    Тип=address.road_network.tip,
                    Наим=address.road_network.naim,
                )
            if address.land_plot:
                etree.SubElement(gar, "ЗемелУчасток").text = address.land_plot
            if address.building:
                etree.SubElement(
                    gar, "Здание",
                    Тип=address.building.tip,
                    Номер=address.building.nomer,
                )
            if address.premises:
                etree.SubElement(
                    gar, "ПомещЗдания",
                    Тип=address.premises.tip,
                    Номер=address.premises.nomer,
                )
            if address.apartment_premises:
                etree.SubElement(
                    gar, "ПомещКвартиры",
                    Тип=address.apartment_premises.tip,
                    Номер=address.apartment_premises.nomer,
                )
        else:
            logger.warning("Неизвестный тип адреса: %r", type(address))

    def _add_signer(self, parent: etree.Element, signer: Signer) -> None:
        """
        Добавляет элемент <Подписант>.
        Понижает auth_method до "1", если обязательных данных для
        выбранного способа подтверждения полномочий не хватает.
        """
        auth_method = signer.auth_method

        # Fallback: СвДоверБум (5) без номера/даты — откат на "1"
        if auth_method == "5" and not (signer.paper_doc_number and signer.paper_doc_date):
            logger.warning(
                "auth_method='5' без paper_doc_number/date, откат на '1'"
            )
            auth_method = "1"

        # Fallback: СвДоверЭл (3) без обязательных полей — откат на "1"
        if auth_method == "3" and not (
            signer.mchd_number and signer.mchd_date and signer.mchd_issuer_inn
        ):
            logger.warning(
                "auth_method='3' без mchd_number/date/issuer_inn, откат на '1'"
            )
            auth_method = "1"

        attrs = {"СпосПодтПолном": auth_method}
        if signer.position:
            attrs["Должн"] = signer.position

        podp = etree.SubElement(parent, "Подписант", **attrs)
        _add_fio(podp, signer)

        if auth_method == "5":
            # Бумажная доверенность
            etree.SubElement(
                podp, "СвДоверБум",
                ДатаВыдДовер=_fmt_date(signer.paper_doc_date),
                ВнНомДовер=signer.paper_doc_number or "",
            )
        elif auth_method == "3":
            # МЧД / электронная доверенность
            etree.SubElement(
                podp, "СвДоверЭл",
                НомДовер=signer.mchd_number or "",
                ДатаВыдДовер=_fmt_date(signer.mchd_date),
                ИдСистХран=signer.mchd_issuer_inn or "",  # TODO: уточнить источник
            )

    # ------------------------------------------------------------------
    # Основная генерация
    # ------------------------------------------------------------------
    def generate(self, data: BillData) -> str:
        """
        Генерирует XML-строку УПД на основе данных.
        Возвращает валидный XML как строку (windows-1251).
        """
        # 1. Корневой элемент
        root = etree.Element(
            "Файл",
            ИдФайл=data.upd_file,
            ВерсФорм="5.03",
            ВерсПрог="УПД-Генератор 1.0",
        )

        # 2. Документ
        doc = etree.SubElement(
            root, "Документ",
            КНД="1115131",
            Функция=data.function,
            ПоФактХЖ=data.fact_housing_name or "",
            НаимДокОпр=data.doc_name_operator or "",
            ДатаИнфПр=_fmt_date(data.upd_date),
            ВремИнфПр=datetime.now().strftime("%H.%M.%S"),
            НаимЭконСубСост=f"{data.seller.name}, ИНН: {data.seller.inn}",
        )

        # 3. СвСчФакт
        sv_sch = etree.SubElement(
            doc, "СвСчФакт",
            НомерДок=data.upd_number,
            ДатаДок=_fmt_date(data.upd_date),
        )

        # 3.1 Продавец
        sv_prod = etree.SubElement(sv_sch, "СвПрод")
        id_sv = etree.SubElement(sv_prod, "ИдСв")
        etree.SubElement(
            id_sv, "СвЮЛУч",
            НаимОрг=data.seller.name,
            ИННЮЛ=data.seller.inn,
            КПП=data.seller.kpp,
        )
        if data.seller.address:
            self._add_address(sv_prod, data.seller.address)

        gr_ot = etree.SubElement(sv_sch, "ГрузОт")
        etree.SubElement(gr_ot, "ОнЖе").text = "он же"

        # 3.2 Платёжно-расчётные документы (СвПРД)
        #     XSD: порядок — СвПрод, ГрузОт, ГрузПолуч, СвПРД, ДокПодтвОтгрНом, СвПокуп
        for pp in (data.payment_docs or []):
            etree.SubElement(
                sv_sch, "СвПРД",
                НомерПРД=pp.number,
                ДатаПРД=_fmt_date(pp.date),
            )

        # 3.3 Документ-подтверждение отгрузки (ДокПодтвОтгрНом)
        if (
            data.dok_podtverzh_name
            and data.dok_podtverzh_number
            and data.dok_podtverzh_date
        ):
            etree.SubElement(
                sv_sch, "ДокПодтвОтгрНом",
                РеквНаимДок=data.dok_podtverzh_name,
                РеквНомерДок=data.dok_podtverzh_number,
                РеквДатаДок=_fmt_date(data.dok_podtverzh_date),
            )

        # 3.4 Покупатель
        sv_pok = etree.SubElement(sv_sch, "СвПокуп")
        id_sv_pok = etree.SubElement(sv_pok, "ИдСв")
        # TODO: при is_worker=true использовать СвФЛУч (нужен флаг в Buyer)
        if len(data.buyer.inn) == 10:
            etree.SubElement(
                id_sv_pok, "СвЮЛУч",
                НаимОрг=data.buyer.name,
                ИННЮЛ=data.buyer.inn,
                КПП=data.buyer.kpp,
            )
            if data.buyer.address:
                self._add_address(sv_pok, data.buyer.address)
        if len(data.buyer.inn) == 12:
            prefix = "Индивидуальный предприниматель "
            surname = ""
            firstname = ""
            secondname = ""
            if data.buyer.legal_full_name and data.buyer.legal_full_name.startswith(prefix):
                # Удаляем префикс (если он есть в начале строки)
                if data.buyer.legal_full_name.startswith(prefix):
                    name_part = data.buyer.legal_full_name[len(prefix):]
                else:
                    name_part = data.buyer.legal_full_name  # на случай, если префикса вдруг нет

                # Разбиваем оставшуюся часть на части по пробелу
                parts = name_part.strip().split()

                # Предполагаем формат: Фамилия Имя Отчество
                surname = parts[0] if len(parts) > 0 else ""
                firstname = parts[1] if len(parts) > 1 else ""
                secondname = parts[2] if len(parts) > 2 else ""

            id_sv_ip = etree.SubElement(
                id_sv_pok, "СвИП",
                ИННФЛ=data.buyer.inn,
            )
            etree.SubElement(
                id_sv_ip, "ФИО",
                Фамилия=surname,
                Имя=firstname,
                Отчество=secondname,
            )

        # 3.5 ДенИзм
        etree.SubElement(
            sv_sch, "ДенИзм",
            КодОКВ="643",
            НаимОКВ="Российский рубль",
        )

        # 3.6 ДопСвФХЖ1 — только при наличии ИдГосКон
        if data.state_contract_number:
            etree.SubElement(
                sv_sch, "ДопСвФХЖ1",
                ИдГосКон=data.state_contract_number,
            )

        # 4. ТаблСчФакт
        tabl = etree.SubElement(doc, "ТаблСчФакт")
        total_without_vat = 0.0
        total_with_vat = 0.0
        total_vat = 0.0
        total_qnt = 0.0

        for item in data.items:
            sved = etree.SubElement(
                tabl, "СведТов",
                НомСтр=str(item.row_num),
                НаимТов=item.name,
                ОКЕИ_Тов=item.okei_code,
                НаимЕдИзм=item.okei_name,
                КолТов=str(item.quantity),
                ЦенаТов=f"{item.price_without_vat:.2f}",
                СтТовБезНДС=f"{item.total_without_vat:.2f}",
                НалСт=item.vat_rate,
                СтТовУчНал=f"{item.total_with_vat:.2f}",
            )

            if item.oksm:
                # sved_dt = etree.SubElement(sved, "СвДТ")
                # etree.SubElement(sved_dt, "КодПроисх").text = str(item.oksm)
                # etree.SubElement(sved_dt, "НомерДТ").text = str(item.dt_num)
                sved_dt = etree.SubElement(sved, "СвДТ",
                                           КодПроисх=str(item.oksm),
                                           НомерДТ=str(item.dt_num),
                                           )

            # ДопСведТов — если есть
            if item.kiz_list or item.country_origin:
                dop_tov = etree.SubElement(sved, "ДопСведТов")

                # Страна кратко — если есть
                if item.country_origin:
                    etree.SubElement(dop_tov, "КрНаимСтрПр").text = item.country_origin

                # КИЗ — если есть
                if item.kiz_list:
                    nom_sred = etree.SubElement(dop_tov, "НомСредИдентТов")
                    for kiz in item.kiz_list:
                        etree.SubElement(nom_sred, "КИЗ").text = kiz

            # Акциз
            akciz = etree.SubElement(sved, "Акциз")
            etree.SubElement(akciz, "БезАкциз").text = "без акциза"

            # СумНал (по позиции)
            sum_nal = etree.SubElement(sved, "СумНал")
            etree.SubElement(sum_nal, "СумНал").text = f"{item.vat_amount:.2f}"

            total_without_vat += item.total_without_vat
            total_with_vat += item.total_with_vat
            total_vat += item.vat_amount
            total_qnt += item.quantity

        # 4.1 ВсегоОпл
        vsego = etree.SubElement(
            tabl, "ВсегоОпл",
            СтТовБезНДСВсего=f"{total_without_vat:.2f}",
            СтТовУчНалВсего=f"{total_with_vat:.2f}",
            КолНеттоВс=f"{total_qnt:.2f}",
        )
        sum_nal_vsego = etree.SubElement(vsego, "СумНалВсего")
        etree.SubElement(sum_nal_vsego, "СумНал").text = f"{total_vat:.2f}"

        # 5. СвПродПер
        sv_prod_per = etree.SubElement(doc, "СвПродПер")
        sv_per = etree.SubElement(
            sv_prod_per, "СвПер",
            СодОпер=data.operation_content,
            ВидОпер=data.operation_type or "",
            ДатаПер=_fmt_date(data.transfer_date),
            # ДатаНачПер=_fmt_date(data.transfer_start_date),
            # ДатаОконПер=_fmt_date(data.transfer_end_date),
        )

        # 5.1 ОснПер
        if data.basis_doc_name:
            etree.SubElement(
                sv_per, "ОснПер",
                РеквНаимДок=data.basis_doc_name,
                РеквНомерДок=data.basis_doc_number or "",
                РеквДатаДок=_fmt_date(data.basis_doc_date),
            )

        # 5.2 СвЛицПер — используем первого подписанта (директора)
        signers = data.signers or ([data.signer] if data.signer else [])
        if signers:
            first = signers[0]
            sv_lits = etree.SubElement(sv_per, "СвЛицПер")
            rab_org = etree.SubElement(
                sv_lits, "РабОргПрод",
                Должность=first.position or "",
            )
            _add_fio(rab_org, first)

        # 5.3 Транспортировка
        if data.transport_info or data.incoterms:
            tran = etree.SubElement(sv_per, "Тран")
            if data.transport_info:
                tran.set("СвТран", data.transport_info)
            if data.incoterms:
                tran.set("Инкотермс", data.incoterms)
            if data.incoterms_version:
                tran.set("ВерИнкотермс", data.incoterms_version)

        # 6. Подписанты — цикл по списку (директор + бухгалтер)
        for signer in signers:
            self._add_signer(doc, signer)

        # 7. Сериализация
        xml_str = etree.tostring(
            root,
            encoding="windows-1251",
            xml_declaration=True,
            pretty_print=True,
        ).decode("windows-1251")

        # 8. Валидация
        self._validate(xml_str)
        return xml_str

    # ------------------------------------------------------------------
    # Валидация
    # ------------------------------------------------------------------
    def _validate(self, xml_str: str) -> None:
        """Проверяет XML на соответствие XSD. При ошибке — сохраняет XML."""
        try:
            parser = etree.XMLParser()
            root = etree.fromstring(xml_str.encode("windows-1251"), parser)
            self.xsd_schema.assertValid(root)
        except etree.DocumentInvalid as e:
            logger.error("Ошибка валидации XSD:")
            error_file = "validation_err.txt"
            with open(error_file, "w", encoding="utf-8") as f:
                f.write(xml_str)
            logger.error("XML сохранён в %s", error_file)

            lines = xml_str.splitlines()
            for error in e.error_log:
                line_text = ""
                if error.line and 0 < error.line <= len(lines):
                    line_text = lines[error.line - 1].strip()
                logger.error(
                    "  %s (line %s, column %s) %s",
                    error.message, error.line, error.column, line_text,
                )
            raise
        except Exception as e:
            logger.exception("Ошибка при валидации: %s", e)
            raise

    # ------------------------------------------------------------------
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
