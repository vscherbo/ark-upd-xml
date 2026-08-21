#!/usr/bin/env python
"""
filename_generator.py - Генерация имени файла и идентификатора ИдФайл.
Формат: ON_NSCHFDOPPR_{buyer_id}_{seller_id}_{YYYYMMDD}_{GUID}_0_{kiz}_0_0_0_0.xml
"""

import uuid
from datetime import datetime


class FilenameGenerator:
    """Генератор имени файла и идентификатора."""

    @staticmethod
    def generate(seller_id: str, buyer_id: str, kiz: bool = False) -> str:
        """
        Генерирует идентификатор файла (ИдФайл) без расширения.

        Args:
            seller_id: Идентификатор продавца (например, ИНН или внутренний код).
            buyer_id: Идентификатор покупателя.
            kiz: Признак наличия КИЗ в позициях.

        Returns:
            Строка вида: ON_NSCHFDOPPR_{buyer_id}_{seller_id}_{YYYYMMDD}_{GUID}_0_{1/0}_0_0_0_0
        """
        today = datetime.now().strftime("%Y%m%d")
        guid = str(uuid.uuid4())  # 36 символов
        guid = '2d9e88fc-dd99-49a4-b843-6c7c61dd3901'
        kiz_flag = "1" if kiz else "0"
        # Все остальные поля (N2, N4, N5, N6, N7) равны 0
        return f"ON_NSCHFDOPPR_{seller_id}_{buyer_id}_{today}_{guid}_0_{kiz_flag}_0_0_0_00"
