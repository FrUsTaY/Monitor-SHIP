#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Вспомогательные утилиты: цвета, очистка экрана, форматирование.
"""

import os
import sys
import time
from datetime import datetime

# Цвета ANSI
COLORS = {
    "green": "\033[92m",
    "red": "\033[91m",
    "yellow": "\033[93m",
    "reset": "\033[0m",
    "bold": "\033[1m",
    "cyan": "\033[96m",
    "gray": "\033[90m",
}


def colored(text: str, color: str = "reset") -> str:
    """Оборачивает текст в цветовые ANSI-коды."""
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def ansi_len(text: str) -> int:
    """Вычисляет длину строки без ANSI-кодов."""
    import re
    # Удаляем ANSI-коды (формат: \x1b[...m)
    ansi_escape = re.compile(r'\x1B\[[0-9;]*m')
    return len(ansi_escape.sub('', text))


def print_colored(text: str, color: str = "reset", end: str = "\n") -> None:
    """Печатает цветной текст."""
    print(colored(text, color), end=end)


def clear_screen() -> None:
    """Очищает экран терминала."""
    os.system('cls' if os.name == 'nt' else 'clear')


def format_timestamp(ts: float = None) -> str:
    """Возвращает строку времени в формате ЧЧ:ММ:СС."""
    if ts is None:
        ts = time.time()
    return time.strftime("%H:%M:%S", time.localtime(ts))


def format_datetime(dt: datetime = None) -> str:
    """Возвращает строку даты и времени в формате ГГГГ-ММ-ДД ЧЧ:ММ."""
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%Y-%m-%d %H:%M")


def parse_datetime(s: str) -> datetime:
    """Парсит строку вида ГГГГ-ММ-ДД ЧЧ:ММ в datetime."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def get_date_filename(date: datetime = None) -> str:
    """Возвращает имя файла лога для указанной даты."""
    if date is None:
        date = datetime.now()
    return f"logs_{date.strftime('%Y-%m-%d')}.log"


def is_valid_ip(ip: str) -> bool:
    """Проверяет валидность IPv4-адреса."""
    if not ip or not isinstance(ip, str):
        return False
    ip = ip.strip()
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isdigit():
            return False
        num = int(part)
        if num < 0 or num > 255:
            return False
        # Проверка на ведущие нули (кроме самого "0")
        if len(part) > 1 and part[0] == '0':
            return False
    return True

def get_base_path() -> str:
    """
    Возвращает путь к папке, где находится исполняемый файл (или скрипт).
    При работе в .exe (PyInstaller) – возвращает папку с .exe.
    При запуске как скрипт – возвращает папку с main.py.
    """
    if getattr(sys, 'frozen', False):
        # Запущено как .exe (PyInstaller)
        return os.path.dirname(sys.executable)
    else:
        # Запущено как скрипт
        return os.path.dirname(os.path.abspath(__file__))