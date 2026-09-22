#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Библиотека для запросов к DaData Suggestions API.

Публичный API:
    load_api_key(conf_file)                 -> str
    suggest(query, resource, api_key)       -> dict   # распарсенный ответ
    suggest_text(query, resource, api_key)  -> str    # сырой текст ответа
"""

import argparse
import configparser
import json
import logging
import sys

import requests

BASE_URL = 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/%s'
DEFAULT_CONF_FILE = 'dadata.conf'
DEFAULT_SECTION = 'dadata_login'
DEFAULT_OPTION = 'API_KEY'


def load_api_key(conf_file=DEFAULT_CONF_FILE,
                 section=DEFAULT_SECTION,
                 option=DEFAULT_OPTION) -> str:
    """Читает API-ключ DaData из ini-файла."""
    cfg = configparser.ConfigParser(allow_no_value=True)
    if not cfg.read(conf_file):
        raise FileNotFoundError('Не найден файл конфигурации: %s' % conf_file)
    if not cfg.has_section(section) or not cfg.has_option(section, option):
        raise KeyError('В %s нет [%s]/%s' % (conf_file, section, option))
    return cfg.get(section, option)


def suggest_text(query: str, resource: str, api_key: str, timeout: int = 30) -> str:
    """Отправляет запрос в DaData и возвращает сырой текст ответа (JSON)."""
    url = BASE_URL % resource
    headers = {
        'Authorization': 'Token %s' % api_key,
        'Content-Type': 'application/json',
    }
    logging.info('DaData запрос: resource=%s, query=%s', resource, query)
    resp = requests.post(
        url,
        data=json.dumps({'query': query}, ensure_ascii=False),
        headers=headers,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.text


def suggest(query: str, resource: str, api_key: str, timeout: int = 30) -> dict:
    """
    Отправляет запрос в DaData и возвращает уже распарсенный ответ
    (dict со структурой {'suggestions': [...]}).
    Именно этот объект передаётся затем в save_address.save_response(...).
    """
    text = suggest_text(query, resource, api_key, timeout=timeout)
    return json.loads(text)


def _main() -> None:
    parser = argparse.ArgumentParser(description='Запрос к ЕГРЮЛ/ЕГРИП (DaData).')
    parser.add_argument('--query', required=True, help='текст запроса')
    parser.add_argument('--resource', required=True, help='REST метод')
    parser.add_argument('--conf', default=DEFAULT_CONF_FILE,
                        help='ini-файл с API-ключом')
    parser.add_argument('--log_level', default='DEBUG', help='уровень логирования')
    args = parser.parse_args()

    numeric_level = getattr(logging, args.log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % args.log_level)
    log_format = ('[%(filename)-20s:%(lineno)4s - %(funcName)20s()] '
                  '%(levelname)-7s | %(asctime)-15s | %(message)s')
    logging.basicConfig(filename='suggest_party.log',
                        filemode='a',
                        format=log_format,
                        level=numeric_level)

    api_key = load_api_key(args.conf)
    sys.stdout.write(suggest_text(args.query, args.resource, api_key))


if __name__ == '__main__':
    _main()
