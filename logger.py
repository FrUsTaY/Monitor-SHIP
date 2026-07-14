#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль логирования.
Отвечает за ежечасную запись статистики потерь и выгрузку отчётов по судну.
"""

import os
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from utils import get_date_filename, format_datetime, colored
from utils import get_base_path

# Папка для логов
LOG_DIR = os.path.join(get_base_path(), "logs")

# Global lock for thread-safe log writing
write_lock = asyncio.Lock()


def ensure_log_dir() -> None:
    """Создаёт папку для логов, если её нет."""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)


async def write_hourly_log(stats: Dict[str, Tuple[int, int, Optional[str]]]) -> None:
    """
    Записывает часовую статистику в лог-файл (асинхронная версия с lock).
    stats: { "имя_судна": (success, fail, method) }
    method может быть "ICMP", "TCP:22" или None (если судно было недоступно)
    """
    if not stats:
        return

    ensure_log_dir()
    now = datetime.now()
    # Определяем часовой интервал
    start_hour = now.replace(minute=0, second=0, microsecond=0)
    end_hour = start_hour + timedelta(hours=1)
    time_range = f"{format_datetime(start_hour)} - {format_datetime(end_hour)}"

    filename = os.path.join(LOG_DIR, get_date_filename(now))

    # Проверяем, не записывали ли уже этот час
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()
            # Если этот час уже есть в файле, пропускаем
            if f"===== {time_range} =====" in content:
                return

    # Формируем запись
    lines = []
    lines.append(f"\n===== {time_range} =====")
    lines.append(f"Записано: {format_datetime(now)}")

    for ship_name, (success, fail, method) in sorted(stats.items()):
        total = success + fail
        if total == 0:
            loss = "нет данных"
        else:
            loss_percent = (fail / total) * 100
            loss = f"{loss_percent:.1f}%"
            # Добавляем метод, если он есть
            if method:
                loss += f" (по {method})"
        
        # Получаем заметки судна
        notes = ""
        try:
            from ships import load_ships
            ships = load_ships()
            for ship in ships:
                if ship.get("name", "").lower() == ship_name.lower():
                    notes = ship.get("notes", "")
                    break
        except:
            pass
        
        # Добавляем заметки, если есть
        if notes:
            # Берем только первую строку заметки
            first_note = notes.split("\n")[0].strip()
            loss += f" - {first_note}"

        lines.append(f"{ship_name} - потеря пакетов {loss}")

    lines.append("=" * 50)

    # Записываем в файл с lock'ом и flush для защиты от аварийного отключения
    try:
        async with write_lock:
            with open(filename, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
                f.flush()  # Гарантированная запись на диск
                os.fsync(f.fileno())  # Дополнительная синхронизация с диском
    except IOError as e:
        print(f"Ошибка записи лога: {e}")


def read_logs_for_period(start_date: datetime, end_date: datetime) -> Dict[str, List[Dict]]:
    """
    Читает логи за указанный период.
    Возвращает словарь: { "имя_судна": [ { "time_range": "...", "loss": "..." }, ... ] }
    """
    ensure_log_dir()
    result = {}

    # Перебираем все дни в периоде
    current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_day = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

    while current_date <= end_day:
        filename = os.path.join(LOG_DIR, get_date_filename(current_date))
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()

            # Ищем заголовки блоков ===== ... =====
            import re
            # Исправленное регулярное выражение для захвата строк с пробелами и дефисами
            pattern = r'===== (.+?) ====='
            matches = list(re.finditer(pattern, content))
            
            for i, match in enumerate(matches):
                time_range = match.group(1).strip()
                
                # Находим начало данных (после строки "Записано:...")
                end_pos = match.end()
                
                # Ищем следующий заголовок или конец файла
                if i + 1 < len(matches):
                    next_start = matches[i + 1].start()
                    block_content = content[end_pos:next_start]
                else:
                    block_content = content[end_pos:]
                
                # Ищем строку "Записано:" и начинаем данные с неё + 1
                data_start = block_content.find("Записано:")
                if data_start == -1:
                    continue
                
                # Находим конец строки "Записано:..."
                data_start = block_content.find("\n", data_start)
                if data_start == -1:
                    continue
                data_start += 1  # Пропускаем \n
                
                # Парсим строки данных
                lines = block_content[data_start:].split("\n")
                for line in lines:
                    if not line.strip():
                        continue
                    
                    # Парсим строку: "Судно Амурское - потеря пакетов 12.5%"
                    if " - потеря пакетов " in line:
                        parts = line.split(" - потеря пакетов ")
                        if len(parts) == 2:
                            ship_name = parts[0].strip()
                            loss = parts[1].strip()

                            # Проверяем, попадает ли временной интервал в наш период
                            try:
                                start_time_str = time_range.split(" - ")[0].strip()
                                # Удаляем "=====" и "(неполный час)" из начала строки
                                start_time_str = start_time_str.replace("=====", "").replace("(неполный час)", "").strip()
                                block_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M")
                                if start_date <= block_time <= end_date:
                                    if ship_name not in result:
                                        result[ship_name] = []
                                    result[ship_name].append({
                                        "time_range": time_range,
                                        "loss": loss
                                    })
                            except (ValueError, IndexError):
                                pass

        current_date += timedelta(days=1)

    # Сортируем записи по времени для каждого судна
    for ship_name in result:
        result[ship_name].sort(key=lambda x: x["time_range"])

    return result


def export_ship_report(ship_name: str, start_date: datetime, end_date: datetime) -> Optional[str]:
    """
    Экспортирует отчёт по конкретному судну за период.
    Возвращает имя созданного файла или None в случае ошибки.
    """
    ensure_log_dir()

    # Получаем все логи за период
    all_logs = read_logs_for_period(start_date, end_date)

    if ship_name not in all_logs or not all_logs[ship_name]:
        return None

    # Формируем отчёт
    # Заменяем недопустимые символы в имени файла на подчёркивание
    import re
    safe_ship_name = re.sub(r'[<>:"/\\|?*]', '_', ship_name)
    filename = os.path.join(LOG_DIR, f"report_{safe_ship_name}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.txt")

    with open(filename, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write(f"ОТЧЁТ ПО СУДНУ: {ship_name}\n")
        f.write(f"Период: {format_datetime(start_date)} - {format_datetime(end_date)}\n")
        f.write(f"Сформирован: {format_datetime()}\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"{'ВРЕМЕННОЙ ИНТЕРВАЛ':<30} {'ПОТЕРЯ ПАКЕТОВ'}\n")
        f.write("-" * 70 + "\n")

        for entry in all_logs[ship_name]:
            time_range = entry["time_range"]
            loss = entry["loss"]
            f.write(f"{time_range:<30} {loss}\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write(f"Всего записей: {len(all_logs[ship_name])}\n")

    return filename


def parse_period_input() -> Optional[Tuple[datetime, datetime]]:
    """
    Запрашивает у пользователя период для выгрузки отчёта.
    Возвращает (start_date, end_date) или None при отмене.
    """
    print("\n--- Выгрузка отчёта по судну ---")
    print("Введите период в формате ГГГГ-ММ-ДД ЧЧ:ММ")
    print("Примеры:")
    print("  2026-06-20 00:00")
    print("  2026-06-24 23:59")
    print("Для выбора за последние 7 дней введите: 7")
    print("Для выбора за месяц введите: 30")
    print("Для отмены введите: q")

    start_input = input("Начало периода: ").strip()

    if start_input.lower() == 'q':
        print("Отмена.")
        return None

    # Проверяем специальные команды
    if start_input.isdigit():
        days = int(start_input)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        return start_date, end_date

    end_input = input("Конец периода (или Enter для текущего времени): ").strip()
    if not end_input:
        end_date = datetime.now()
    elif end_input.lower() == 'q':
        print("Отмена.")
        return None
    else:
        try:
            end_date = datetime.strptime(end_input, "%Y-%m-%d %H:%M")
        except ValueError:
            print(colored("Неверный формат даты.", "red"))
            return None

    try:
        start_date = datetime.strptime(start_input, "%Y-%m-%d %H:%M")
    except ValueError:
        print(colored("Неверный формат даты.", "red"))
        return None

    if start_date > end_date:
        print(colored("Начало периода не может быть позже конца.", "red"))
        return None

    return start_date, end_date


def show_ship_report() -> None:
    """
    Интерактивная функция выгрузки отчёта по судну.
    """
    from ships import load_ships

    ships = load_ships()
    if not ships:
        print(colored("Нет зарегистрированных судов.", "yellow"))
        return

    # Выводим список судов
    print("\nСписок судов:")
    for idx, ship in enumerate(ships, 1):
        name = ship.get("name", "Без имени")
        status = ship.get("status", "неизвестно")
        status_colored = colored(status, "green" if status == "в сети" else "red" if status == "не в сети" else "yellow")
        print(f"  {idx}. {name} ({status_colored})")

    choice = input("\nВведите номер или название судна: ").strip()

    if not choice:
        print(colored("Отмена.", "yellow"))
        return

    # Находим судно
    target_ship = None
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(ships):
            target_ship = ships[idx]
    except ValueError:
        for ship in ships:
            if ship.get("name", "").lower() == choice.lower():
                target_ship = ship
                break

    if not target_ship:
        print(colored("Судно не найдено.", "red"))
        return

    ship_name = target_ship.get("name")

    # Запрашиваем период
    period = parse_period_input()
    if not period:
        return

    start_date, end_date = period

    # Формируем отчёт
    print(f"\nФормируем отчёт для судна '{ship_name}' за период {format_datetime(start_date)} - {format_datetime(end_date)}...")

    filename = export_ship_report(ship_name, start_date, end_date)

    if filename:
        print(colored(f"Отчёт сохранён в файл: {filename}", "green"))
        print(colored(f"Всего записей: {len(read_logs_for_period(start_date, end_date).get(ship_name, []))}", "cyan"))
    else:
        print(colored(f"Нет данных по судну '{ship_name}' за указанный период.", "yellow"))
    
    input("\nНажмите Enter для продолжения...")

async def write_partial_log(stats: Dict[str, Tuple[int, int, Optional[str]]], start_time: datetime, end_time: datetime) -> None:
    """
    Записывает лог за произвольный интервал (неполный час) (асинхронная версия с lock).
    stats: { "имя_судна": (success, fail, method) }
    start_time, end_time – datetime объекты.
    """
    if not stats:
        return

    ensure_log_dir()
    time_range = f"{format_datetime(start_time)} - {format_datetime(end_time)}"

    filename = os.path.join(LOG_DIR, get_date_filename(end_time))

    # Формируем запись
    lines = []
    lines.append(f"\n===== {time_range} (неполный час) =====")
    lines.append(f"Записано: {format_datetime(end_time)}")

    for ship_name, (success, fail, method) in sorted(stats.items()):
        total = success + fail
        if total == 0:
            loss = "нет данных"
        else:
            loss_percent = (fail / total) * 100
            loss = f"{loss_percent:.1f}%"
            # Добавляем метод, если он есть
            if method:
                loss += f" (по {method})"
        
        # Получаем заметки судна
        notes = ""
        try:
            from ships import load_ships
            ships = load_ships()
            for ship in ships:
                if ship.get("name", "").lower() == ship_name.lower():
                    notes = ship.get("notes", "")
                    break
        except:
            pass
        
        # Добавляем заметки, если есть
        if notes:
            # Берем только первую строку заметки
            first_note = notes.split("\n")[0].strip()
            loss += f" - {first_note}"

        lines.append(f"{ship_name} - потеря пакетов {loss}")

    lines.append("=" * 50)

    try:
        async with write_lock:
            with open(filename, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
                f.flush()  # Гарантированная запись на диск
                os.fsync(f.fileno())  # Дополнительная синхронизация с диском
    except IOError as e:
        print(f"Ошибка записи лога: {e}")