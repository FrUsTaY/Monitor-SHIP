#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Финальный тест форматирования таблицы мониторинга с end=\"\"."""

from ships import get_active_ships
from utils import colored, print_colored

# Заголовки таблицы
print("=" * 85)
print(colored(f"  МОНИТОРИНГ СУДОВ (обновлено: 13:30:00)", "bold"))
print("=" * 85)
print(f"{'№':<4} {'Название':<25} {'Статус':<15} {'Соединения'}")
print("-" * 85)

# Вывод судов
for idx, ship in enumerate(get_active_ships()[:10], 1):
    name = ship.get("name", "Без имени")
    
    # Список соединений - только названия спутников, без IP
    conns = ship.get("connections", [])
    conn_names = [c.get('satellite', '?') for c in conns]
    conn_str = ", ".join(conn_names)
    
    # Статус (пример)
    status = "не в сети"
    
    # Маркер изменения
    change_marker = " *" if idx in [1, 2, 3] else ""
    
    # Выводим строку (каждый столбец отдельно, чтобы избежать проблем с ANSI-кодами)
    # Номер и название - без цвета
    print(f"{idx:<4} {name:<25}", end="")
    # Статус - цветной (добавляем пробел после статуса, end="" чтобы не переходить на новую строку)
    status_text = f" {status}"
    print_colored(status_text, "green" if status == "в сети" else "red" if status == "не в сети" else "yellow", end="")
    # Соединения и маркер - без цвета
    print(f" {conn_str:<30}{change_marker}")

print("-" * 85)
print("  * — статус изменился в последнем цикле")
