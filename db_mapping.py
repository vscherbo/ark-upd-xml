#!/usr/bin/env python
"""
db_mapping.py - Модели данных для генерации УПД.
Использует Pydantic для валидации и сериализации.
"""

from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

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


class Seller(BaseModel):
    """Продавец."""
    name: str = Field(..., description="Полное наименование")
    inn: str = Field(..., description="ИНН")
    kpp: str = Field(..., description="КПП")
    ogrn: Optional[str] = Field(None, description="ОГРН")
    okpo: Optional[str] = Field(None, description="ОКПО")
    address: AddressRF = Field(..., description="Адрес")
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
    address: AddressRF = Field(..., description="Адрес")


class BillItem(BaseModel):
    """Позиция товара (строка таблицы)."""
    row_num: int = Field(..., description="Номер строки")
    name: str = Field(..., description="Наименование товара/работы/услуги")
    oktei_code: str = Field(..., description="Код ОКЕИ")
    oktei_name: str = Field(..., description="Наименование единицы измерения")
    quantity: float = Field(..., description="Количество")
    price_without_vat: float = Field(..., description="Цена за единицу без НДС")
    total_without_vat: float = Field(..., description="Стоимость без НДС")
    vat_rate: str = Field(..., description="Ставка НДС")
    vat_amount: float = Field(..., description="Сумма НДС")
    total_with_vat: float = Field(..., description="Стоимость с НДС")
    # Дополнительные поля (необязательные)
    article: Optional[str] = Field(None, description="Артикул")
    kiz_list: List[str] = Field(default_factory=list, description="КИЗ (список)")
    # Для прослеживаемости и др. можно добавить, но для примера достаточно.


class BillData(BaseModel):
    """Полный набор данных для генерации УПД."""
    bill_number: str = Field(..., description="Номер счета-фактуры (основания)")
    bill_date: date = Field(..., description="Дата счета")
    upd_number: str = Field(..., description="Номер УПД (присваивается при генерации)")
    upd_date: date = Field(..., description="Дата УПД (обычно текущая)")
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
