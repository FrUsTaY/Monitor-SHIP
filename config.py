#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Управление настройками мониторинга.
Настройки хранятся в файле config.json в папке с программой.
"""

import json
import os
from utils import get_base_path

# Имя файла конфигурации
CONFIG_FILE = os.path.join(get_base_path(), "config.json")

# Значения по умолчанию
DEFAULT_CONFIG = {
    "monitor_interval": 10,      # секунд между циклами проверки
    "offline_threshold": 3,      # последовательных неудач для перехода в офлайн
    "online_threshold": 1,       # последовательных успехов для возврата в онлайн
    "tcp_port": 22,              # порт для TCP-проверки (SSH)
}


def load_config() -> dict:
    """
    Загружает настройки из config.json.
    Если файла нет или он повреждён – создаёт с настройками по умолчанию.
    Возвращает словарь с настройками.
    """
    if not os.path.exists(CONFIG_FILE):
        return save_config(DEFAULT_CONFIG.copy())

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        # Проверяем, что все ключи есть, если нет – добавляем из DEFAULT_CONFIG
        for key, value in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = value
        return config
    except (json.JSONDecodeError, IOError):
        # Если файл повреждён, пересоздаём
        return save_config(DEFAULT_CONFIG.copy())


def save_config(config: dict) -> dict:
    """Сохраняет настройки в config.json и возвращает их."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Ошибка сохранения настроек: {e}")
    return config


def get_setting(key: str) -> any:
    """Возвращает значение конкретной настройки."""
    config = load_config()
    return config.get(key, DEFAULT_CONFIG.get(key))


def update_setting(key: str, value: any) -> None:
    """Обновляет одну настройку и сохраняет."""
    config = load_config()
    config[key] = value
    save_config(config)


def update_settings(new_config: dict) -> None:
    """Обновляет несколько настроек сразу."""
    config = load_config()
    config.update(new_config)
    save_config(config)