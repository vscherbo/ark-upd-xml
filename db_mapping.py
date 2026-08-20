#!/usr/bin/env python
"""
db_mapping.py - Модели данных и мапперы.

"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal  # , Optional

from pydantic import BaseModel, Field


class Seller(BaseModel):
    """Реквизиты продавца"""
    name: str = ""          # «ООО Ромашка»
    inn: str = ""
    kpp: str = ""
    ogrn: str = ""
    trade_mark: str = ""         # бренд, информативно
    # Адрес
    address: str = ""
    region_code: str = ""        # «77»
    region_name: str = ""        # «г. Москва»
    postal_code: str = ""        # «101000»
    city: str = ""               # «Москва»
    street: str = ""             # «ул. Такая-то»
    house: str = ""              # «1»
    apartment: str = ""          # «10»
    # Прочее
    locality: str = ""           # «мкр. ..., ...» — опциональное поле для АдрРФ


class Bank(BaseModel):
    """Банковские реквизиты продавца."""
    bank_name: str = ""
    bik: str = ""
    corr_account: str = ""
    account: str = ""            # расчётный счёт


class Tax(BaseModel):
    """Налоговый режим и ставка НДС."""
    regime: Literal["ОСНО", "УСН доходы", "УСН доходы минус расходы", "НПД"] = "ОСНО"
    vat_rate: Literal["без НДС", "0%", "5%", "7%", "10%", "20%", "22%"] = "22%"


class Signer(BaseModel):
    """Подписант УПД."""
    last_name: str = ""
    first_name: str = ""
    middle_name: str = ""
    position: str = "Индивидуальный предприниматель"
    # Способ подтверждения полномочий (код из справочника ФНС):
    # 1 — лицо, действующее без доверенности
    # 6 — МЧД
    auth_method: Literal["1", "6"] = "1"
    mchd_number: str = ""        # если auth_method=6
    mchd_date: str = ""          # ДД.ММ.ГГГГ
    mchd_issuer_inn: str = ""


class Buyer(BaseModel):
    """Грузополучатель и покупатель."""
    name: str = ""
    inn: str = ""
    kpp: str = ""
    address: str = ""
    region_code: str = ""
    region_name: str = ""
    postal_code: str = ""
    city: str = ""
    locality: str = ""
    street: str = ""
    house: str = ""
    building: str = ""


class Settings(BaseModel):
    seller: Seller = Field(default_factory=Seller)
    bank: Bank = Field(default_factory=Bank)
    tax: Tax = Field(default_factory=Tax)
    signer: Signer = Field(default_factory=Signer)
    buyer: Buyer = Field(default_factory=Buyer)



@dataclass
class BillItem:
    """Позиция счёта."""
    row_num: int
    article: str
    name: str
    quantity: float
    sum_with_vat: float
    vat_rate_src: str
    vat_amount_src: float
    kiz: str


@dataclass
class Bill:
    """Счёт (документ-основание для УПД)."""
    number: str
    date: date
    seller_id: int
    buyer_id: int
    items: List[BillItem]


def build_settings(seller_data: dict, buyer_data: dict) -> Settings:
    """
    Создаёт объект Settings из данных продавца и покупателя.

    Args:
        seller_data: Словарь с полями из таблицы sellers.
        buyer_data: Словарь с полями из таблицы buyers.

    Returns:
        Settings: объект с реквизитами для генератора УПД.
    """
    seller = Seller(
        inn=seller_data["inn"],
        kpp=seller_data["kpp"],
        # name='ООО "КИП СПБ"',  # seller_data["name"].replace("'", ""),
        name=seller_data["name"],
        address=seller_data.get("address", ""),
        okpo=seller_data.get("okpo", ""),
        ogrn=seller_data.get("ogrn", ""),
    )
    print('models, build_settings seller_data:', seller_data)
    bank = Bank(
        name=seller_data.get("bank_name", ""),
        bic=seller_data.get("bic", ""),
        account=seller_data.get("account", ""),
        corr_account=seller_data.get("corr_account", ""),
    )
    tax = Tax(
        vat_rate=seller_data["vat_rate"],
        tax_system=seller_data.get("tax_system", ""),
    )
    signer = Signer(
        position=seller_data.get("signer_position", ""),
        fio=seller_data["signer_fio"],
        basis=seller_data.get("signer_basis", ""),
        basis_details=seller_data.get("signer_basis_details", ""),
    )
    buyer = Buyer(
        inn=buyer_data["inn"],
        kpp=buyer_data.get("kpp", ""),
        name=buyer_data["name"],
        address=buyer_data.get("address", ""),
    )
    return Settings(seller=seller, bank=bank, tax=tax, signer=signer, buyer=buyer)
