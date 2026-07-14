#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Главный модуль приложения.
Содержит меню и связывает все остальные модули.
"""

import sys
import time
import asyncio
import logging
from typing import List, Dict

from utils import colored, print_colored, clear_screen, format_timestamp
from config import load_config, save_config, get_setting, update_setting
from ships import (
    load_ships, save_ships, add_ship, delete_ship, find_ship,
    update_ship, toggle_blocked, get_blocked_ships, get_active_ships, update_notes
)
from monitor import monitor, start_monitor
from logger import write_hourly_log, show_ship_report, ensure_log_dir


def show_menu() -> None:
    """Отображает главное меню."""
    clear_screen()
    print_colored("\n" + "=" * 60, "bold")
    print_colored("  RTCOMM MONITORING ONLINE", "bold")
    print_colored("=" * 60, "bold")
    ships = load_ships()
    print(f"  Всего судов: {len(ships)}")
    blocked_count = len(get_blocked_ships())
    print(f"  В блокировке: {blocked_count}")
    print_colored("=" * 60, "bold")
    print("\n  Выберите действие:")
    print("  1. Показать список судов")
    print("  2. Добавить новое судно")
    print("  3. Удалить судно")
    print("  4. Редактировать судно")
    print("  5. Заблокированные суда")
    print("  6. Обновить статусы (ручной опрос)")
    print("  7. Запустить непрерывный мониторинг")
    print("  8. Настройки мониторинга")
    print("  9. Выгрузить лог по судну")
    print("  0. Выход")
    print_colored("=" * 60, "bold")


def show_ship_list() -> None:
    """Отображает список всех судов с деталями."""
    from utils import ansi_len
    ships = load_ships()
    if not ships:
        print_colored("\nСписок судов пуст.", "yellow")
        input("\nНажмите Enter для продолжения...")
        return

    clear_screen()
    print("\n" + "=" * 110)
    print(f"{'№':<4} {'Название':<20} {'Статус':<15} {'Блокировка':<15} {'Соединения':<30} {'Заметки'}")
    print("=" * 110)

    for idx, ship in enumerate(ships, 1):
        name = ship.get("name", "Без имени")
        status = ship.get("status", "неизвестно")
        blocked = "[Блок]" if ship.get("blocked", False) else "[Актив]"
        connections = ship.get("connections", [])
        notes = ship.get("notes", "")
        
        # Формируем строку соединений
        conn_parts = []
        for c in connections:
            sat = c.get('satellite', '?')
            ip = c.get('ip', '?')
            conn_parts.append(f"{sat}, {ip}")
        conn_str = "; ".join(conn_parts)

        # Цвет статуса
        if status == "в сети":
            status_colored = colored(status, "green")
        elif status == "не в сети":
            status_colored = colored(status, "red")
        else:
            status_colored = colored(status, "yellow")

        # Цвет блокировки
        blocked_colored = colored(blocked, "gray" if "Да" in blocked else "reset")

        # Выравнивание с учетом ANSI-кодов
        status_len = ansi_len(status_colored)
        status_padding = " " * (15 - status_len)
        blocked_len = ansi_len(blocked_colored)
        blocked_padding = " " * (15 - blocked_len)
        
        # Обрезаем заметки, если они слишком длинные
        # Выводим заметки без выравнивания
        notes_display = notes
        
        # Выводим строку без лишних пробелов (padding уже содержит пробелы)
        print(f"{idx:<4} {name:<20} {status_colored}{status_padding}{blocked_colored}{blocked_padding} {conn_str:<30} {notes_display}")
        print("-" * 110)

    print("=" * 110)
    input("\nНажмите Enter для продолжения...")


def add_ship_interactive() -> None:
    """Интерактивное добавление судна."""
    clear_screen()
    print_colored("\n--- ДОБАВЛЕНИЕ НОВОГО СУДНА ---", "bold")

    name = input("Введите название судна: ").strip()
    if not name:
        print_colored("Название не может быть пустым.", "red")
        input("\nНажмите Enter...")
        return

    ships = load_ships()
    if any(s.get("name", "").lower() == name.lower() for s in ships):
        print_colored("Судно с таким названием уже существует.", "red")
        input("\nНажмите Enter...")
        return

    connections = []
    print("\nДобавьте спутники (IP-адреса).")
    print("Для завершения введите пустое название спутника.\n")

    while True:
        sat_name = input("Название спутника (Enter для завершения): ").strip()
        if not sat_name:
            break

        ip = input(f"IP-адрес для спутника '{sat_name}': ").strip()
        if not ip:
            print_colored("IP не может быть пустым, пропускаем.", "red")
            continue

        # Простая проверка IP
        parts = ip.split(".")
        if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            print_colored("Неверный формат IP-адреса. Пропускаем.", "red")
            continue

        connections.append({"satellite": sat_name, "ip": ip})
        print_colored(f"Спутник '{sat_name}' добавлен.", "green")

    if not connections:
        print_colored("Не добавлено ни одного соединения. Судно не будет создано.", "yellow")
        input("\nНажмите Enter...")
        return

    if add_ship(name, connections):
        print_colored(f"\nСудно '{name}' добавлено с {len(connections)} спутниками.", "green")
    else:
        print_colored(f"\nОшибка: судно '{name}' уже существует.", "red")

    input("\nНажмите Enter для продолжения...")


def delete_ship_interactive() -> None:
    """Интерактивное удаление судна."""
    ships = load_ships()
    if not ships:
        print_colored("\nСписок судов пуст.", "yellow")
        input("\nНажмите Enter...")
        return

    clear_screen()
    print_colored("\n--- УДАЛЕНИЕ СУДНА ---", "bold")
    print("\nСписок судов:")
    for idx, ship in enumerate(ships, 1):
        name = ship.get("name", "Без имени")
        status = ship.get("status", "неизвестно")
        status_colored = colored(status, "green" if status == "в сети" else "red" if status == "не в сети" else "yellow")
        print(f"  {idx}. {name} ({status_colored})")

    choice = input("\nВведите номер или название судна для удаления (или Enter для отмены): ").strip()

    if not choice:
        print_colored("Отмена.", "yellow")
        input("\nНажмите Enter...")
        return

    if delete_ship(choice):
        print_colored(f"Судно удалено.", "green")
    else:
        print_colored("Судно не найдено.", "red")

    input("\nНажмите Enter для продолжения...")


def edit_ship_interactive() -> None:
    """Интерактивное редактирование судна."""
    ships = load_ships()
    if not ships:
        print_colored("\nСписок судов пуст.", "yellow")
        input("\nНажмите Enter...")
        return

    clear_screen()
    print_colored("\n--- РЕДАКТИРОВАНИЕ СУДНА ---", "bold")
    print("\nСписок судов:")
    for idx, ship in enumerate(ships, 1):
        name = ship.get("name", "Без имени")
        status = ship.get("status", "неизвестно")
        blocked = "[Блок]" if ship.get("blocked", False) else ""
        status_colored = colored(status, "green" if status == "в сети" else "red" if status == "не в сети" else "yellow")
        print(f"  {idx}. {name} {blocked} ({status_colored})")

    choice = input("\nВведите номер или название судна (или Enter для отмены): ").strip()

    if not choice:
        print_colored("Отмена.", "yellow")
        input("\nНажмите Enter...")
        return

    ship = find_ship(choice)
    if not ship:
        print_colored("Судно не найдено.", "red")
        input("\nНажмите Enter...")
        return

    name = ship.get("name")
    connections = ship.get("connections", [])
    blocked = ship.get("blocked", False)
    notes = ship.get("notes", "")

    while True:
        clear_screen()
        print_colored(f"\n--- РЕДАКТИРОВАНИЕ: {name} ---", "bold")
        print(f"Текущие соединения:")
        for i, conn in enumerate(connections, 1):
            print(f"  {i}. {conn.get('satellite')} - {conn.get('ip')}")

        print(f"\nСтатус блокировки: {'[Блок]' if blocked else '[Актив]'}")
        print(f"Текущие заметки: {'(нет)' if not notes else notes}")

        print("\nДействия:")
        print("  1. Добавить соединение")
        print("  2. Удалить соединение")
        print("  3. Изменить IP соединения")
        print("  4. Переключить блокировку")
        print("  5. Редактировать заметки")
        print("  6. Вернуться в меню")

        action = input("\nВыберите действие (1-6): ").strip()

        if action == "1":
            sat_name = input("Название спутника: ").strip()
            if not sat_name:
                print_colored("Название не может быть пустым.", "red")
            else:
                ip = input(f"IP-адрес для спутника '{sat_name}': ").strip()
                if ip:
                    parts = ip.split(".")
                    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                        connections.append({"satellite": sat_name, "ip": ip})
                        update_ship(name, {"connections": connections})
                        print_colored("Соединение добавлено.", "green")
                    else:
                        print_colored("Неверный формат IP.", "red")
                else:
                    print_colored("IP не может быть пустым.", "red")

        elif action == "2":
            if not connections:
                print_colored("Нет соединений для удаления.", "yellow")
            else:
                num = input("Введите номер соединения для удаления: ").strip()
                try:
                    idx = int(num) - 1
                    if 0 <= idx < len(connections):
                        removed = connections.pop(idx)
                        update_ship(name, {"connections": connections})
                        print_colored(f"Соединение '{removed.get('satellite')}' удалено.", "green")
                    else:
                        print_colored("Неверный номер.", "red")
                except ValueError:
                    print_colored("Введите число.", "red")

        elif action == "3":
            if not connections:
                print_colored("Нет соединений для изменения.", "yellow")
            else:
                num = input("Введите номер соединения для изменения IP: ").strip()
                try:
                    idx = int(num) - 1
                    if 0 <= idx < len(connections):
                        conn = connections[idx]
                        new_ip = input(f"Новый IP для '{conn.get('satellite')}' (текущий: {conn.get('ip')}): ").strip()
                        if new_ip:
                            parts = new_ip.split(".")
                            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                                conn["ip"] = new_ip
                                update_ship(name, {"connections": connections})
                                print_colored("IP обновлён.", "green")
                            else:
                                print_colored("Неверный формат IP.", "red")
                        else:
                            print_colored("IP не может быть пустым.", "red")
                    else:
                        print_colored("Неверный номер.", "red")
                except ValueError:
                    print_colored("Введите число.", "red")

        elif action == "4":
            new_blocked = toggle_blocked(name)
            if new_blocked is not None:
                status_text = "заблокировано" if new_blocked else "разблокировано"
                print_colored(f"Судно {status_text}.", "green")
                blocked = new_blocked
            else:
                print_colored("Ошибка изменения статуса блокировки.", "red")

        elif action == "5":
            edit_notes_interactive(name)
            # Обновляем данные судна после редактирования заметок
            ship = find_ship(name)
            if ship:
                notes = ship.get("notes", "")

        elif action == "6":
            print_colored("Возврат в меню.", "yellow")
            break

        else:
            print_colored("Неверный выбор.", "red")

        if action != "6":
            input("\nНажмите Enter для продолжения...")


def edit_notes_interactive(ship_name: str) -> None:
    """Интерактивное редактирование заметок судна."""
    ship = find_ship(ship_name)
    if not ship:
        print_colored("Судно не найдено.", "red")
        input("\nНажмите Enter...")
        return

    clear_screen()
    print_colored(f"\n--- РЕДАКТИРОВАНИЕ ЗАМЕТОК: {ship_name} ---", "bold")
    
    current_notes = ship.get("notes", "")
    print(f"Текущие заметки: {current_notes if current_notes else '(нет)'}")
    print("\nВыберите действие:")
    print("  1. Добавить новую заметку")
    print("  2. Очистить все заметки")
    print("  3. Вернуться назад")
    
    action = input("\nВыберите действие (1-3): ").strip()
    
    if action == "1":
        clear_screen()
        print_colored(f"\n--- ДОБАВЛЕНИЕ ЗАМЕТКИ: {ship_name} ---", "bold")
        print("Введите заметку (например: 'Судно в порту', 'Технические работы'):")
        new_note = input("> ").strip()
        
        if new_note:
            # Добавляем к существующим заметкам с новой строки
            if current_notes:
                updated_notes = current_notes + "\n" + new_note
            else:
                updated_notes = new_note
            
            if update_notes(ship_name, updated_notes):
                print_colored("Заметка добавлена.", "green")
                # Записываем изменение в лог судна (с первой строкой заметки)
                monitor._log_notes_change(ship_name, f"Добавлена заметка", updated_notes)
            else:
                print_colored("Ошибка при сохранении заметки.", "red")
        else:
            print_colored("Заметка не может быть пустой.", "yellow")
    
    elif action == "2":
        clear_screen()
        print_colored(f"\n--- ОЧИСТКА ЗАМЕТОК: {ship_name} ---", "bold")
        if current_notes:
            confirm = input("Вы уверены? (y - да, n - нет): ").strip().lower()
            if confirm == "y":
                if update_notes(ship_name, ""):
                    print_colored("Все заметки удалены.", "green")
                    # Записываем изменение в лог судна
                    monitor._log_notes_change(ship_name, "Очищены все заметки", "")
                else:
                    print_colored("Ошибка при очистке заметок.", "red")
            else:
                print_colored("Отмена.", "yellow")
        else:
            print_colored("Нет заметок для очистки.", "yellow")
    
    elif action == "3":
        print_colored("Отмена.", "yellow")
    else:
        print_colored("Неверный выбор.", "red")


def write_log_entry(ship_name: str, message: str) -> None:
    """Записывает событие в лог судна."""
    import os
    from logger import ensure_log_dir, get_date_filename
    
    ensure_log_dir()
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    filename = os.path.join(log_dir, get_date_filename())
    
    try:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"{ship_name} - {message}\n")
    except IOError as e:
        print(f"Ошибка записи в лог: {e}")


def show_blocked_ships() -> None:
    """Показывает список заблокированных судов и позволяет разблокировать."""
    blocked = get_blocked_ships()
    if not blocked:
        print_colored("\nНет заблокированных судов.", "yellow")
        input("\nНажмите Enter...")
        return

    clear_screen()
    print_colored("\n--- ЗАБЛОКИРОВАННЫЕ СУДА ---", "bold")
    print("\nСписок заблокированных судов:")
    for idx, ship in enumerate(blocked, 1):
        name = ship.get("name", "Без имени")
        status = ship.get("status", "неизвестно")
        print(f"  {idx}. {name} (статус: {status})")

    print("\nДействия:")
    print("  1. Разблокировать судно")
    print("  2. Вернуться в меню")

    action = input("\nВыберите действие (1-2): ").strip()

    if action == "1":
        choice = input("Введите номер или название судна для разблокировки: ").strip()
        if not choice:
            print_colored("Отмена.", "yellow")
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(blocked):
                    ship = blocked[idx]
                    new_blocked = toggle_blocked(ship.get("name"))
                    if new_blocked is not None and not new_blocked:
                        print_colored(f"Судно '{ship.get('name')}' разблокировано.", "green")
                    else:
                        print_colored("Ошибка разблокировки.", "red")
            except ValueError:
                for ship in blocked:
                    if ship.get("name", "").lower() == choice.lower():
                        new_blocked = toggle_blocked(ship.get("name"))
                        if new_blocked is not None and not new_blocked:
                            print_colored(f"Судно '{ship.get('name')}' разблокировано.", "green")
                        else:
                            print_colored("Ошибка разблокировки.", "red")
                        break
                else:
                    print_colored("Судно не найдено.", "red")

    elif action == "2":
        print_colored("Отмена.", "yellow")
    else:
        print_colored("Неверный выбор.", "red")

    input("\nНажмите Enter для продолжения...")


def update_statuses() -> None:
    """Ручное обновление статусов всех судов."""
    print_colored("\nОбновление статусов судов...", "yellow")
    ships = get_active_ships()

    if not ships:
        print_colored("Нет активных судов.", "yellow")
        input("\nНажмите Enter...")
        return

    async def update():
        tasks = [monitor.check_ship(ship) for ship in ships]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        changes = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                continue
            # check_ship теперь возвращает (ship_name, is_online, method)
            ship_name, is_online, method = result
            if monitor.update_status(ship_name, is_online, method):
                changes.append({"name": ship_name, "status": monitor.states[ship_name]["status"]})

        # Сохраняем изменения
        if changes:
            all_ships = load_ships()
            for change in changes:
                for ship in all_ships:
                    if ship.get("name") == change["name"]:
                        ship["status"] = change["status"]
                        break
            save_ships(all_ships)

        return changes

    # Запускаем асинхронное обновление через asyncio.run (Python 3.7+)
    try:
        changes = asyncio.run(update())

        if changes:
            print_colored(f"Обновлено {len(changes)} судов.", "green")
            for change in changes:
                status_colored = colored(change["status"], "green" if change["status"] == "в сети" else "red")
                print(f"  {change['name']} - {status_colored}")
        else:
            print_colored("Статусы не изменились.", "yellow")

    except Exception as e:
        print_colored(f"Ошибка обновления: {e}", "red")

    input("\nНажмите Enter для продолжения...")


def configure_monitoring() -> None:
    """Настройка параметров мониторинга."""
    config = load_config()
    clear_screen()
    print_colored("\n--- НАСТРОЙКИ МОНИТОРИНГА ---", "bold")
    print(f"  1. Интервал между циклами (сейчас: {config['monitor_interval']} сек)")
    print(f"  2. Порог перехода в 'не в сети' (сейчас: {config['offline_threshold']} неудач)")
    print(f"  3. Порог возврата в 'в сети' (сейчас: {config['online_threshold']} успехов)")
    print(f"  4. Порт для TCP-проверки (сейчас: {config.get('tcp_port', 22)})")
    print("  5. Вернуться в меню")

    choice = input("\nВыберите параметр для изменения (1-5): ").strip()

    if choice == "1":
        value = input(f"Новый интервал (сек, текущий: {config['monitor_interval']}): ").strip()
        if value.isdigit() and int(value) > 0:
            update_setting("monitor_interval", int(value))
            print_colored(f"Интервал установлен на {value} сек.", "green")
        else:
            print_colored("Неверное значение.", "red")

    elif choice == "2":
        value = input(f"Новый порог неудач (текущий: {config['offline_threshold']}): ").strip()
        if value.isdigit() and int(value) > 0:
            update_setting("offline_threshold", int(value))
            print_colored(f"Порог неудач установлен на {value}.", "green")
        else:
            print_colored("Неверное значение.", "red")

    elif choice == "3":
        value = input(f"Новый порог успехов (текущий: {config['online_threshold']}): ").strip()
        if value.isdigit() and int(value) > 0:
            update_setting("online_threshold", int(value))
            print_colored(f"Порог успехов установлен на {value}.", "green")
        else:
            print_colored("Неверное значение.", "red")

    elif choice == "4":
        value = input(f"Новый порт для TCP-проверки (текущий: {config.get('tcp_port', 22)}): ").strip()
        if value.isdigit() and 1 <= int(value) <= 65535:
            update_setting("tcp_port", int(value))
            print_colored(f"Порт установлен на {value}.", "green")
        else:
            print_colored("Неверное значение (должен быть от 1 до 65535).", "red")

    elif choice == "5":
        print_colored("Отмена.", "yellow")
    else:
        print_colored("Неверный выбор.", "red")

    input("\nНажмите Enter для продолжения...")


def main():
    """Главная функция приложения."""
    # Создаём папку для логов
    ensure_log_dir()

    # Загружаем суда и показываем предупреждение при ошибке
    ships = load_ships()
    if ships is None or len(ships) == 0:
        print_colored("\n⚠️ ВНИМАНИЕ: Список судов пуст или файл ships.json повреждён!", "yellow")
        print_colored("   Данные судов могут быть утеряны.", "yellow")
        input("\nНажмите Enter для продолжения...")

    while True:
        show_menu()
        choice = input("Ваш выбор: ").strip()

        if choice == "1":
            show_ship_list()
        elif choice == "2":
            add_ship_interactive()
        elif choice == "3":
            delete_ship_interactive()
        elif choice == "4":
            edit_ship_interactive()
        elif choice == "5":
            show_blocked_ships()
        elif choice == "6":
            update_statuses()
        elif choice == "7":
            # Запуск мониторинга
            print_colored("\nЗапуск непрерывного мониторинга...", "green")
            start_monitor()
            # После остановки мониторинга возвращаемся в меню
        elif choice == "8":
            configure_monitoring()
        elif choice == "9":
            show_ship_report()
        elif choice == "0":
            print_colored("\nДо свидания!", "yellow")
            input("\nНажмите Enter для выхода...")
            sys.exit(0)
        else:
            print_colored("Неверный выбор. Пожалуйста, выберите от 0 до 9.", "red")
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_colored("\nПринудительное завершение.", "yellow")
        sys.exit(0)