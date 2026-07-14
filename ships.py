#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Управление данными судов.
Данные хранятся в файле ships.json в папке с программой.
"""

import json
import os
from typing import List, Dict, Optional
from utils import get_base_path

DATA_FILE = os.path.join(get_base_path(), "ships.json")


def load_ships() -> List[Dict]:
    """
    Загружает список судов из ships.json.
    Если файла нет – возвращает пустой список.
    Автоматически конвертирует старый формат (один IP) в новый (соединения).
    """
    if not os.path.exists(DATA_FILE):
        return []

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                return []

            # Конвертация старого формата в новый
            for ship in data:
                # Если есть поле "ip" и нет "connections" – конвертируем
                if "ip" in ship and "connections" not in ship:
                    ship["connections"] = [{"satellite": "Основной", "ip": ship.pop("ip")}]

                # Если нет поля "blocked" – добавляем (по умолчанию False)
                if "blocked" not in ship:
                    ship["blocked"] = False

                # Если нет поля "notes" – добавляем (пустая строка по умолчанию)
                if "notes" not in ship:
                    ship["notes"] = ""

                # Если нет поля "status" – добавляем
                if "status" not in ship:
                    ship["status"] = "не проверено"

                # Убеждаемся, что connections есть и это список
                if "connections" not in ship or not isinstance(ship["connections"], list):
                    ship["connections"] = []

            return data
    except json.JSONDecodeError as e:
        print(f"Ошибка: файл {DATA_FILE} повреждён ({e}). Используется пустой список.")
        return []
    except IOError as e:
        print(f"Ошибка чтения файла {DATA_FILE}: {e}")
        return []


def save_ships(ships: List[Dict]) -> None:
    """Сохраняет список судов в ships.json."""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(ships, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Ошибка сохранения данных: {e}")


def add_ship(name: str, connections: List[Dict]) -> bool:
    """
    Добавляет новое судно.
    Возвращает True, если успешно, False если судно с таким именем уже существует.
    """
    ships = load_ships()
    if any(s.get("name", "").lower() == name.lower() for s in ships):
        return False

    new_ship = {
        "name": name,
        "connections": connections,
        "status": "не проверено",
        "blocked": False,
        "notes": ""
    }
    ships.append(new_ship)
    save_ships(ships)
    return True


def delete_ship(identifier: str) -> bool:
    """
    Удаляет судно по названию или номеру (в виде строки).
    Возвращает True, если удалено, иначе False.
    """
    ships = load_ships()
    if not ships:
        return False

    # Пробуем интерпретировать как номер (индекс + 1)
    try:
        idx = int(identifier) - 1
        if 0 <= idx < len(ships):
            ships.pop(idx)
            save_ships(ships)
            return True
    except ValueError:
        pass

    # Ищем по названию (регистронезависимо)
    for i, ship in enumerate(ships):
        if ship.get("name", "").lower() == identifier.lower():
            ships.pop(i)
            save_ships(ships)
            return True

    return False


def find_ship(identifier: str) -> Optional[Dict]:
    """
    Находит судно по названию или номеру.
    Возвращает словарь судна или None.
    """
    ships = load_ships()
    if not ships:
        return None

    try:
        idx = int(identifier) - 1
        if 0 <= idx < len(ships):
            return ships[idx]
    except ValueError:
        pass

    for ship in ships:
        if ship.get("name", "").lower() == identifier.lower():
            return ship

    return None


def update_ship(name: str, new_data: Dict) -> bool:
    """
    Обновляет данные судна по названию.
    Возвращает True, если обновлено.
    """
    ships = load_ships()
    for ship in ships:
        if ship.get("name", "").lower() == name.lower():
            # Обновляем только разрешённые поля
            if "connections" in new_data:
                ship["connections"] = new_data["connections"]
            if "blocked" in new_data:
                ship["blocked"] = new_data["blocked"]
            if "status" in new_data:
                ship["status"] = new_data["status"]
            if "notes" in new_data:
                ship["notes"] = new_data["notes"]
            save_ships(ships)
            return True
    return False


def toggle_blocked(name: str) -> Optional[bool]:
    """
    Переключает статус блокировки судна.
    Возвращает новый статус (True/False) или None, если судно не найдено.
    """
    ships = load_ships()
    for ship in ships:
        if ship.get("name", "").lower() == name.lower():
            ship["blocked"] = not ship.get("blocked", False)
            save_ships(ships)
            return ship["blocked"]
    return None


def update_notes(name: str, notes: str) -> bool:
    """
    Обновляет заметки судна.
    Возвращает True, если обновлено.
    """
    ships = load_ships()
    for ship in ships:
        if ship.get("name", "").lower() == name.lower():
            ship["notes"] = notes
            save_ships(ships)
            return True
    return None


def get_blocked_ships() -> List[Dict]:
    """Возвращает список только заблокированных судов."""
    ships = load_ships()
    return [s for s in ships if s.get("blocked", False)]


def get_active_ships() -> List[Dict]:
    """Возвращает список только активных (не заблокированных) судов."""
    ships = load_ships()
    return [s for s in ships if not s.get("blocked", False)]