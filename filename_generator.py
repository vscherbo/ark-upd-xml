#!/usr/bin/env python
"""
filename_generator.py - Генератор имён файлов для УПД.
"""
import logging

logger = logging.getLogger(__name__)


def generate_filename(upd_number: int) -> str:
    """
    Генерирует имя файла УПД.

    Args:
        upd_number: Номер УПД.

    Returns:
        str: Имя файла в формате 'upd{upd_number}.xml'.
    """
    logger.debug("Generating filename for UPD number: %s", upd_number)
    # Пока простая логика, как в задании
    return f"upd{upd_number}.xml"
