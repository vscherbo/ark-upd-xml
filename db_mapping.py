#!/usr/bin/env python
"""
db_mapping.py - Модели данных для генерации УПД.
Использует Pydantic для валидации и сериализации.
"""

from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


class AddressRF(BaseModel):
    """Адрес в формате АдрРФ (для РФ)."""
    postal_code: Optional[str] = Field(None, description="Почтовый индекс")
    region_code: str = Field(..., description="Код субъекта РФ (2 цифры)")
    region_name: str = Field(..., description="Наименование субъекта РФ")
    district: Optional[str] = Field(None, description="Район")
    city: Optional[str] = Field(None, description="Город")
    locality: Optional[str] = Field(None, description="Населенный пункт")
    street: Optional[str] = Field(None, description="Улица")
    house: Optional[str] = Field(None, description="Дом")
    building: Optional[str] = Field(None, description="Корпус")
    apartment: Optional[str] = Field(None, description="Квартира/помещение")
    extra_info: Optional[str] = Field(None, description="Иные сведения об адресе")

# db_mapping.py - добавить после AddressRF


class VidNaimKod(BaseModel):
    """Тип для элементов с видом (кодом) и наименованием (МуниципРайон, ГородСелПоселен)."""
    vid_kod: str = Field(..., description="Вид (код) элемента")
    naim: str = Field(..., description="Наименование элемента")


class VidNaim(BaseModel):
    """Тип для элементов с видом и наименованием (НаселенПункт)."""
    vid: str = Field(..., description="Вид элемента")
    naim: str = Field(..., description="Наименование элемента")


class TipNaim(BaseModel):
    """Тип для элементов с типом и наименованием (ЭлПланСтруктур, ЭлУлДорСети)."""
    tip: str = Field(..., description="Тип элемента")
    naim: str = Field(..., description="Наименование элемента")


class NomerTip(BaseModel):
    """Тип для элементов с типом и номером (Здание, ПомещЗдания, ПомещКвартиры)."""
    tip: str = Field(..., description="Тип элемента")
    nomer: str = Field(..., description="Номер элемента")


class AddressGAR(BaseModel):
    """Адрес в формате АдрГАР (государственный адресный реестр)."""
    id_num: str = Field(..., description="Код ФИАС (ИдНом)")
    index: Optional[str] = Field(None, description="Почтовый индекс")
    region_code: str = Field(..., description="Код субъекта РФ (2 цифры)")
    region_name: str = Field(..., description="Наименование субъекта РФ")
    municipal_district: Optional[VidNaimKod] = None
    city_settlement: Optional[VidNaimKod] = None
    locality: Optional[VidNaim] = None
    planning_structure: Optional[TipNaim] = None
    road_network: Optional[TipNaim] = None
    land_plot: Optional[str] = None
    building: Optional[NomerTip] = None
    premises: Optional[NomerTip] = None
    apartment_premises: Optional[NomerTip] = None


class Seller(BaseModel):
    """Продавец."""
    name: str = Field(..., description="Полное наименование")
    inn: str = Field(..., description="ИНН")
    kpp: str = Field(..., description="КПП")
    ogrn: Optional[str] = Field(None, description="ОГРН")
    okpo: Optional[str] = Field(None, description="ОКПО")
    prefix: Optional[str] = Field(None, description="Префикс в счёт")
    address: Union[AddressRF, AddressGAR] = Field(..., description="Адрес")
    # Дополнительные реквизиты, если нужны
    short_name: Optional[str] = Field(None, description="Сокращенное наименование")
    opf_code: Optional[str] = Field(None, description="Код ОПФ")
    opf_full_name: Optional[str] = Field(None, description="Полное наименование ОПФ")


class Bank(BaseModel):
    """Банковские реквизиты."""
    bank_name: str = Field(..., description="Наименование банка")
    bik: str = Field(..., description="БИК")
    account: str = Field(..., description="Номер расчетного счета")
    corr_account: Optional[str] = Field(None, description="Корреспондентский счет")


class Tax(BaseModel):
    """Налоговые параметры."""
    vat_rate: str = Field(..., description="Ставка НДС (например, '20%', '10/110', 'без НДС')")


class Signer(BaseModel):
    """Подписант УПД."""
    last_name: str = Field(..., description="Фамилия")
    first_name: str = Field(..., description="Имя")
    middle_name: Optional[str] = Field(None, description="Отчество")
    position: Optional[str] = Field(None, description="Должность")
    # Способ подтверждения полномочий:
    # 1 — без доверенности, 2 — по доверенности (бумажной), 3 — МЧД и т.д.
    auth_method: Literal["1", "2", "3", "4", "5", "6"] = Field(
        "1",
        description="Способ подтверждения полномочий (код)"
    )
    # Для доверенности (если auth_method в {3,5}):
    mchd_number: Optional[str] = Field(None, description="Номер доверенности (МЧД)")
    mchd_date: Optional[date] = Field(None, description="Дата выдачи доверенности")
    mchd_issuer_inn: Optional[str] = Field(None, description="ИНН доверителя")
    # Для бумажной доверенности:
    paper_doc_number: Optional[str] = Field(None, description="Внутренний номер доверенности")
    paper_doc_date: Optional[date] = Field(None, description="Дата выдачи бумажной доверенности")


class Buyer(BaseModel):
    """Покупатель (и грузополучатель, если совпадает)."""
    name: str = Field(..., description="Полное наименование")
    inn: str = Field(..., description="ИНН")
    kpp: str = Field(..., description="КПП")
    address: Union[AddressRF, AddressGAR] = Field(..., description="Адрес")


class BillItem(BaseModel):
    """Позиция товара (строка таблицы)."""
    row_num: int = Field(..., description="Номер строки")
    name: str = Field(..., description="Наименование товара/работы/услуги")
    okei_code: str = Field(..., description="Код ОКЕИ")
    okei_name: str = Field(..., description="Наименование единицы измерения")
    quantity: float = Field(..., description="Количество")
    price_without_vat: float = Field(..., description="Цена за единицу без НДС")
    total_without_vat: float = Field(..., description="Стоимость без НДС")
    vat_rate: str = Field(..., description="Ставка НДС")
    vat_amount: float = Field(..., description="Сумма НДС")
    total_with_vat: float = Field(..., description="Стоимость с НДС")
    # Дополнительные поля (необязательные)
    article: Optional[int] = Field(None, description="КодСодержания")
    kiz_list: List[str] = Field(default_factory=list, description="КИЗ (список)")
    # Для прослеживаемости и др. можно добавить, но для примера достаточно.


class BillData(BaseModel):
    """Полный набор данных для генерации УПД."""
    bill_number: str = Field(..., description="Номер счета (основания)")
    bill_date: date = Field(..., description="Дата счета")
    upd_number: str = Field(..., description="Номер УПД")
    upd_date: date = Field(..., description="Дата УПД")
    # ready_date: date = Field(..., description="Сдача")  # adjust ???
    upd_file: str = Field(..., description="Имя файла УПД по правилам")
    function: Literal["СЧФ", "СЧФДОП", "ДОП", "СвРК", "СвЗК"] = Field(
        "СЧФДОП",
        description="Функция документа"
    )
    fact_housing_name: Optional[str] = Field(
        None,
        description="Наименование документа по факту хозяйственной жизни"
    )
    doc_name_operator: Optional[str] = Field(
        None,
        description="Наименование первичного документа, определенное организацией"
    )
    seller: Seller
    buyer: Buyer
    bank: Optional[Bank] = None
    payment_doc_number: str = Field(None, description="Номер платёжного документа")
    payment_doc_date: date = Field(None, description="Дата платёжного документа")
    tax: Tax
    signer: Signer
    items: List[BillItem] = Field(default_factory=list)
    # Основание (документ-основание для отгрузки)
    basis_doc_name: Optional[str] = Field(None, description="Наименование документа-основания")
    basis_doc_number: Optional[str] = Field(None, description="Номер документа-основания")
    basis_doc_date: Optional[date] = Field(None, description="Дата документа-основания")
    # Сведения о передаче (СвПер)
    operation_content: str = Field("Товары переданы", description="Содержание операции")
    operation_type: Optional[str] = Field("продажа", description="Вид операции")
    transfer_date: Optional[date] = None
    transfer_start_date: Optional[date] = None
    transfer_end_date: Optional[date] = None
    # Транспортировка
    transport_info: Optional[str] = Field(None, description="Сведения о транспортировке")
    incoterms: Optional[str] = Field(None, description="Инкотермс (3 буквы)")
    incoterms_version: Optional[str] = Field(None, description="Версия Инкотермс (4 цифры)")
    # Дополнительные информационные поля (ИнфПолФХЖ1,2,3) – можно добавить при необходимости

    class Config:
        use_enum_values = True
