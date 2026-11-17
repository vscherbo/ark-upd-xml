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


class UpdGenerationError(Exception):
    """
    Ошибка формирования XML УПД.
    Поднимается при нарушении бизнес-правил или провале XSD-валидации.
    Сообщение уже содержит всю нужную диагностику — traceback не нужен.
    """


_MAX_SNIPPET = 200


def _format_xsd_error(err) -> str:
    """Одна строка отчёта об ошибке XSD."""
    loc_parts = []
    if err.line:
        loc_parts.append(f"строка {err.line}")
    if err.column:
        loc_parts.append(f"поз. {err.column}")
    loc = ", ".join(loc_parts) or "без позиции"
    return f"[{loc}] {err.message}"


def _set_opt(attrs: dict, key: str, value) -> None:
    """Кладёт атрибут в словарь только если значение непустое."""
    if value is None:
        return
    s = str(value).strip()
    if s:
        attrs[key] = s


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

            attrs: dict[str, str] = {
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
        Добавляет <Подписант>. Поддерживает:
          auth_method=1 — без доверенности;
          auth_method=3 — МЧД (СвДоверЭл);
          auth_method=5 — бумажная доверенность (СвДоверБум).
        При неполных данных — откат на '1' с предупреждением.
        """
        auth_method = signer.auth_method

        # МЧД: обязательны number, issue_date, storage_id
        if auth_method == "3":
            m = signer.mchd
            if not (m and m.number and m.issue_date and m.storage_id):
                logger.warning(
                    "auth_method='3' без обязательных полей МЧД "
                    "(number/issue_date/storage_id) — откат на '1'"
                )
                auth_method = "1"

        # Бумажная: обязательны paper_doc_number, paper_doc_date
        if auth_method == "5" and not (
            signer.paper_doc_number and signer.paper_doc_date
        ):
            logger.warning(
                "auth_method='5' без paper_doc_number/date — откат на '1'"
            )
            auth_method = "1"

        attrs: Dict[str, str] = {"СпосПодтПолном": auth_method}
        _set_opt(attrs, "Должн", signer.position)
        _set_opt(attrs, "ТипПодпис", signer.tip_podpis)

        podp = etree.SubElement(parent, "Подписант", **attrs)
        _add_fio(podp, signer)

        if auth_method == "3" and signer.mchd:
            m = signer.mchd
            doc_attrs: Dict[str, str] = {
                "НомДовер": m.number,
                "ДатаВыдДовер": _fmt_date(m.issue_date),
                "ИдСистХран": m.storage_id,
            }
            _set_opt(doc_attrs, "ВнНомДовер", m.inner_number)
            if m.inner_reg_date:
                doc_attrs["ДатаВнРегДовер"] = _fmt_date(m.inner_reg_date)
            _set_opt(doc_attrs, "УРЛСист", m.system_url)
            etree.SubElement(podp, "СвДоверЭл", **doc_attrs)

        elif auth_method == "5":
            etree.SubElement(
                podp, "СвДоверБум",
                ДатаВыдДовер=_fmt_date(signer.paper_doc_date),
                ВнНомДовер=signer.paper_doc_number or "",
            )
    # ------------------------------------------------------------------
    # Основная генерация
    # ------------------------------------------------------------------

    def generate(self, data: BillData) -> str:
        try:
            xml_str = self._build_xml(data)
        except UpdGenerationError:
            raise
        except Exception as exc:
            logger.exception(
                "Неожиданная ошибка при сборке XML УПД (счёт=%s, upd=%s)",
                data.bill_number, data.upd_number,
            )
            raise UpdGenerationError(
                f"Ошибка сборки XML УПД: {type(exc).__name__}: {exc}"
            ) from exc

        self._validate(xml_str)
        return xml_str

    def _build_xml(self, data: BillData) -> str:
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
        # 2. Документ — ПоФактХЖ и НаимДокОпр опциональны, minLength=1
        doc_attrs = {
            "КНД": "1115131",
            "Функция": data.function,
            "ДатаИнфПр": _fmt_date(data.upd_date),
            "ВремИнфПр": datetime.now().strftime("%H.%M.%S"),
        }
        _set_opt(doc_attrs, "ПоФактХЖ", data.fact_housing_name)
        _set_opt(doc_attrs, "НаимДокОпр", data.doc_name_operator)
        _set_opt(doc_attrs, "НаимЭконСубСост",
                 f"{data.seller.name}, ИНН: {data.seller.inn}" if data.seller.name else None)
        doc = etree.SubElement(root, "Документ", **doc_attrs)
        """
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
        """

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

        gr_pol = etree.SubElement(sv_sch, "ГрузПолуч")
        id_gr_pol = etree.SubElement(gr_pol, "ИдСв")
        if len(data.buyer.inn) == 10:
            etree.SubElement(
                id_gr_pol, "СвЮЛУч",
                НаимОрг=data.buyer.name,
                ИННЮЛ=data.buyer.inn,
                КПП=data.buyer.kpp,
            )
            if data.buyer.address:
                self._add_address(gr_pol, data.buyer.address)
        elif len(data.buyer.inn) == 12:
            id_sv_ip = etree.SubElement(
                id_gr_pol, "СвИП",
                ИННФЛ=data.buyer.inn,
            )
            etree.SubElement(
                id_sv_ip, "ФИО",
                Фамилия=data.buyer.surname,
                Имя=data.buyer.firstname,
                Отчество=data.buyer.secondname,
            )

        # 3.2 Платёжно-расчётные документы (СвПРД)
        #     XSD: порядок — СвПрод, ГрузОт, ГрузПолуч, СвПРД, ДокПодтвОтгрНом, СвПокуп
        for pp in (data.payment_docs or []):
            etree.SubElement(
                sv_sch, "СвПРД",
                НомерПРД=pp.prd_number,
                ДатаПРД=_fmt_date(pp.prd_date),
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
        elif len(data.buyer.inn) == 12:
            id_sv_ip = etree.SubElement(
                id_sv_pok, "СвИП",
                ИННФЛ=data.buyer.inn,
            )
            etree.SubElement(
                id_sv_ip, "ФИО",
                Фамилия=data.buyer.surname,
                Имя=data.buyer.firstname,
                Отчество=data.buyer.secondname,
            )

        # 3.5 ДенИзм
        etree.SubElement(
            sv_sch, "ДенИзм",
            КодОКВ="643",
            НаимОКВ="Российский рубль",
        )

        # 3.6 ДопСвФХЖ1 — если есть ИдГосКон и/или авансовые СФ (строка 5б)
        if data.state_contract_number or data.sopr_docs:
            dop_attrs = {}
            _set_opt(dop_attrs, "ИдГосКон", data.state_contract_number)
            dop = etree.SubElement(sv_sch, "ДопСвФХЖ1", **dop_attrs)

            # Строка 5б — реквизиты авансовых счетов-фактур
            for doc in data.sopr_docs:
                sopr_attrs = {
                    "РеквНаимДок": doc.name,
                    "РеквНомерДок": doc.number,
                    "РеквДатаДок": _fmt_date(doc.doc_date),
                }
                _set_opt(sopr_attrs, "РеквДопСведДок", doc.extra_info)
                etree.SubElement(dop, "СопрДокФХЖ", **sopr_attrs)

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
        sv_per_attrs = {
            "СодОпер": data.operation_content,
            "ДатаПер": _fmt_date(data.transfer_date),
        }
        _set_opt(sv_per_attrs, "ВидОпер", data.operation_type)
        sv_per = etree.SubElement(sv_prod_per, "СвПер", **sv_per_attrs)
        """
        sv_per = etree.SubElement(
            sv_prod_per, "СвПер",
            СодОпер=data.operation_content,
            ВидОпер=data.operation_type or "",
            ДатаПер=_fmt_date(data.transfer_date),
            # ДатаНачПер=_fmt_date(data.transfer_start_date),
            # ДатаОконПер=_fmt_date(data.transfer_end_date),
        )
        """

        # 5.1 ОснПер
        if data.basis_doc_name:
            etree.SubElement(
                sv_per, "ОснПер",
                РеквНаимДок=data.basis_doc_name,
                РеквНомерДок=data.basis_doc_number or "",
                РеквДатаДок=_fmt_date(data.basis_doc_date),
            )

        # 5.2 СвЛицПер — только если у первого подписанта есть должность
        signers = data.signers or ([data.signer] if data.signer else [])
        if signers:
            first = signers[0]
            if first.position:
                sv_lits = etree.SubElement(sv_per, "СвЛицПер")
                rab_org = etree.SubElement(
                    sv_lits, "РабОргПрод",
                    Должность=first.position,   # уже непустое
                )
                _add_fio(rab_org, first)
            else:
                logger.warning(
                    "СвЛицПер пропущен для счёта %s (УПД %s): "
                    "у подписанта '%s %s %s' не задана должность",
                    data.bill_number,
                    data.upd_number,
                    first.last_name,
                    first.first_name,
                    first.middle_name or "",
                )

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
        # self._validate(xml_str)
        return xml_str

    # ------------------------------------------------------------------
    # Валидация
    # ------------------------------------------------------------------
    def _validate(self, xml_str: str) -> None:
        """
        Проверяет XML по XSD. При ошибке:
          • сохраняет XML в validation_err.txt (UTF-8) для отладки;
          • логирует структурированный список проблем;
          • поднимает UpdGenerationError с кратким итогом.
        """
        try:
            parser = etree.XMLParser()
            root = etree.fromstring(xml_str.encode("windows-1251"), parser)
            self.xsd_schema.assertValid(root)

        except etree.DocumentInvalid as exc:
            error_file = "validation_err.txt"
            with open(error_file, "w", encoding="utf-8") as f:
                f.write(xml_str)

            lines = xml_str.splitlines()
            problems = []
            for err in exc.error_log:
                line_text = ""
                if err.line and 0 < err.line <= len(lines):
                    snippet = lines[err.line - 1].strip()
                    if len(snippet) > _MAX_SNIPPET:
                        snippet = snippet[:_MAX_SNIPPET - 3] + "..."
                    line_text = snippet
                problems.append((_format_xsd_error(err), line_text))

            summary_lines = [
                f"XML не прошёл XSD-валидацию: {len(problems)} ошибок(и). "
                f"Полный XML — в {error_file}."
            ]
            for i, (msg, snippet) in enumerate(problems, 1):
                summary_lines.append(f"  {i}. {msg}")
                if snippet:
                    summary_lines.append(f"     фрагмент: {snippet}")

            summary = "\n".join(summary_lines)
            logger.error(summary)
            raise UpdGenerationError(summary) from exc

        except Exception as exc:
            logger.exception("Непредвиденная ошибка при валидации XML")
            raise UpdGenerationError(
                f"Непредвиденная ошибка при XSD-валидации: {exc}"
            ) from exc

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
