#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
errors.py - Утилиты для компактного вывода ошибок валидации pydantic
и безопасного построения моделей.
"""

from __future__ import annotations

import logging
from typing import Any, Type, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_INPUT_REPR = 120


def format_pydantic_error(exc: ValidationError) -> str:
    """
    Форматирует ValidationError в компактный многострочный список.

    Каждая проблема:
        • path.to.field: сообщение (получено: <repr>)
    """
    lines: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", ())) or "<root>"
        msg = err.get("msg", "?")
        inp = err.get("input", None)
        inp_repr = repr(inp)
        if len(inp_repr) > _MAX_INPUT_REPR:
            inp_repr = inp_repr[: _MAX_INPUT_REPR - 3] + "..."
        lines.append(f"  • {loc}: {msg} (получено: {inp_repr})")
    return "\n".join(lines)


def build_model(model_cls: Type[T], context: str, **kwargs: Any) -> T:
    """
    Безопасно создаёт pydantic-модель.

    При ValidationError логирует компактный список проблем и возбуждает
    ValueError с кратким описанием (детали остаются в логе).

    Args:
        model_cls: класс модели (Seller, Buyer, BillData, ...).
        context:   строка-идентификатор, например
                   "покупатель ИНН=1215231842 КПП=121501001".
        **kwargs:  аргументы для конструктора модели.
    """
    try:
        return model_cls(**kwargs)
    except ValidationError as exc:
        logger.error(
            "Ошибка валидации %s (%s): %d проблем(ы)\n%s",
            model_cls.__name__,
            context,
            len(exc.errors()),
            format_pydantic_error(exc),
        )
        raise ValueError(
            f"Модель {model_cls.__name__} ({context}) не прошла валидацию: "
            f"{len(exc.errors())} ошибок(и), детали — в логе"
        ) from exc
