#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль мониторинга с асинхронным параллельным опросом.
Содержит логику проверки статусов, счётчики последовательных сбоев,
и режим непрерывного мониторинга с перерисовкой экрана.
"""

import asyncio
import sys
import signal
import time
import os
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import platform

from utils import colored, clear_screen, format_timestamp, print_colored, is_valid_ip, ansi_len
from ships import get_active_ships, save_ships, load_ships
from config import get_setting
from logger import write_hourly_log, write_partial_log, get_date_filename, write_lock, LOG_DIR


class ShipMonitor:
    """
    Класс для мониторинга судов.
    Хранит состояние каждого судна: текущий статус, счётчики последовательных
    успехов/неудач, статистику для логирования.
    """

    def __init__(self):
        # Словарь для хранения состояния судов по имени
        # { "имя": { "status": "в сети", "fail_count": 0, "success_count": 0,
        #            "hour_success": 0, "hour_fail": 0, "last_hour_recorded": None } }
        self.states = {}
        self.running = False
        self.monitor_task = None
        self.log_task = None
        self.flush_task = None  # Задача для периодического сброса буфера логов
        self.start_time = None
        self._lock = asyncio.Lock()  # Lock для синхронизации записи логов

    def reset_state(self, ship_name: str) -> None:
        """Инициализирует или сбрасывает состояние судна."""
        self.states[ship_name] = {
            "status": "не проверено",
            "fail_count": 0,
            "success_count": 0,
            "hour_success": 0,
            "hour_fail": 0,
            "last_status_change": None,
            "last_hour_recorded": None,  # Сбрасываем, чтобы записать в первый же час
            "method": None               # Метод проверки (ICMP или TCP:порт)
        }

    def get_state(self, ship_name: str) -> dict:
        """Возвращает состояние судна, при необходимости создаёт новое."""
        if ship_name not in self.states:
            self.reset_state(ship_name)
        return self.states[ship_name]

    async def _ping_icmp(self, ip: str, timeout: int = 3) -> bool:
        # Валидация IP-адреса
        if not is_valid_ip(ip):
            return False
        
        system = platform.system().lower()
        if system == "windows":
            timeout_ms = timeout * 1000
            cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(timeout), ip]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(process.wait(), timeout=timeout + 1)
            stdout, _ = await process.communicate()
            encoding = "cp866" if system == "windows" else "utf-8"
            output = stdout.decode(encoding, errors='ignore')

            # Ищем строку с ответом от целевого IP
            for line in output.splitlines():
                if ip in line:
                    # Если есть "число байт=" или "bytes=" или "TTL" — успех
                    if "число байт=" in line or "bytes=" in line or "TTL" in line:
                        return True
                    # Если есть "недоступен" или "unreachable" — ошибка
                    if "недоступен" in line or "unreachable" in line:
                        return False
            # Если не нашли явного успеха — считаем неудачей
            return False
        except asyncio.TimeoutError:
            return False
        except Exception:
            return False

    async def _check_tcp_port(self, ip: str, port: int, timeout: int = 3) -> bool:
        """
        Проверяет доступность TCP-порта на указанном IP.
        Возвращает True, если соединение установлено.
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=timeout
            )
            writer.close()
            await writer.wait_closed()
            return True
        except:
            return False

    async def ping_host(self, ip: str, timeout: int = 3) -> Tuple[bool, Optional[str]]:
        """
        Комбинированная проверка: сначала ICMP, затем TCP (порт из настроек).
        Возвращает (is_online, method), где method = "ICMP" или "TCP:порт" или None.
        """
        # Проверяем ICMP
        icmp_ok = await self._ping_icmp(ip, timeout)
        if icmp_ok:
            return True, "ICMP"

        # Если ICMP не удался, пробуем TCP
        tcp_port = get_setting("tcp_port")
        tcp_ok = await self._check_tcp_port(ip, tcp_port, timeout)
        if tcp_ok:
            return True, f"TCP:{tcp_port}"

        # Ни один метод не сработал
        return False, None

    async def check_ship(self, ship: Dict) -> Tuple[str, bool, Optional[str]]:
        """
        Проверяет все соединения судна.
        Возвращает (имя_судна, статус_в_сети, метод_проверки).
        """
        name = ship.get("name", "Без имени")
        connections = ship.get("connections", [])

        if not connections:
            return name, False, None

        # Проверяем все IP параллельно
        tasks = []
        for conn in connections:
            ip = conn.get("ip", "").strip()
            if ip:
                tasks.append(self.ping_host(ip))

        if not tasks:
            return name, False, None

        results = await asyncio.gather(*tasks, return_exceptions=True)
        # Если хотя бы один ping успешен – судно в сети
        for result in results:
            if isinstance(result, tuple) and len(result) == 2:
                is_online, method = result
                if is_online:
                    return name, True, method

        return name, False, None

    def update_status(self, ship_name: str, is_online: bool, method: Optional[str] = None) -> bool:
        """
        Обновляет статус судна на основе последовательных проверок.
        Возвращает True, если статус изменился.
        """
        state = self.get_state(ship_name)
        current_status = state["status"]

        # Обновляем счётчики для логирования
        if is_online:
            state["hour_success"] += 1
            state["success_count"] += 1
            state["fail_count"] = 0
            # Сохраняем метод, если он передан (для логирования)
            if method:
                state["method"] = method
        else:
            state["hour_fail"] += 1
            state["fail_count"] += 1
            state["success_count"] = 0
            # Если судно не в сети, метод сбрасываем
            state["method"] = None

        # Получаем пороги из настроек
        offline_threshold = get_setting("offline_threshold")
        online_threshold = get_setting("online_threshold")

        new_status = current_status

        # Если судно не проверено - требуем подтверждения статуса
        if current_status == "не проверено":
            if is_online and state["success_count"] >= online_threshold:
                new_status = "в сети"
                state["success_count"] = 0
                state["fail_count"] = 0
                # Если метод не передан, но судно в сети, пробуем взять из предыдущего состояния или ставим "неизвестно"
                if method is not None:
                    state["method"] = method
                elif "method" not in state or state["method"] is None:
                    state["method"] = "неизвестно"
            elif not is_online and state["fail_count"] >= offline_threshold:
                new_status = "не в сети"
                state["fail_count"] = 0
                state["method"] = None

        # Если судно в сети
        elif current_status == "в сети":
            if state["fail_count"] >= offline_threshold:
                new_status = "не в сети"
                state["fail_count"] = 0
                state["method"] = None

        # Если судно не в сети
        elif current_status == "не в сети":
            if state["success_count"] >= online_threshold:
                new_status = "в сети"
                state["success_count"] = 0
                state["fail_count"] = 0
                # Если метод не передан, но судно в сети, пробуем взять из предыдущего состояния или ставим "неизвестно"
                if method is not None:
                    state["method"] = method
                elif "method" not in state or state["method"] is None:
                    state["method"] = "неизвестно"
                # При возврате в сеть метод будет передан из check_ship

        if new_status != current_status:
            # Не записываем в лог, если статус был "не проверено" (первый запуск мониторинга)
            if current_status != "не проверено":
                state["status"] = new_status
                state["last_status_change"] = time.time()
                # Если статус изменился, записываем событие в лог
                self._log_status_change(ship_name, current_status, new_status)
            else:
                state["status"] = new_status
            return True

        return False

    def _log_status_change(self, ship_name: str, old_status: str, new_status: str) -> None:
        """Записывает изменение статуса судна в лог."""
        from logger import ensure_log_dir, get_date_filename, LOG_DIR
        from datetime import datetime
        import os
        
        ensure_log_dir()
        filename = os.path.join(LOG_DIR, get_date_filename())
        
        # Получаем заметки
        from ships import load_ships
        ships = load_ships()
        notes = ""
        for ship in ships:
            if ship.get("name", "").lower() == ship_name.lower():
                notes = ship.get("notes", "")
                break
        
        # Формируем сообщение о смене статуса с заметками
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"[{timestamp}] Статус changed: '{old_status}' -> '{new_status}'"
        if notes:
            msg += f" | Заметки: {notes}"
        
        try:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(f"{ship_name} - {msg}\n")
                f.flush()  # Гарантированная запись на диск
                os.fsync(f.fileno())  # Дополнительная синхронизация с диском
        except IOError as e:
            print(f"Ошибка записи в лог смены статуса: {e}")

    def _log_notes_change(self, ship_name: str, action: str, notes: str) -> None:
        """Записывает изменение заметок судна в лог."""
        from logger import ensure_log_dir, get_date_filename, LOG_DIR
        from datetime import datetime
        import os
        
        ensure_log_dir()
        filename = os.path.join(LOG_DIR, get_date_filename())
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"[{timestamp}] {action}"
        if notes:
            # Берем только первую строку заметки
            first_note = notes.split("\n")[0].strip()
            msg += f" | Заметки: {first_note}"
        
        try:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(f"{ship_name} - {msg}\n")
                f.flush()  # Гарантированная запись на диск
                os.fsync(f.fileno())  # Дополнительная синхронизация с диском
        except IOError as e:
            print(f"Ошибка записи в лог изменений заметок: {e}")
    
    def _log_write(self, ship_name: str, message: str) -> None:
        """Вспомогательная функция для записи других событий в лог с flush()."""
        from logger import ensure_log_dir, get_date_filename, LOG_DIR
        from datetime import datetime
        import os
        
        ensure_log_dir()
        filename = os.path.join(LOG_DIR, get_date_filename())
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"[{timestamp}] {message}"
        
        try:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(f"{ship_name} - {msg}\n")
                f.flush()  # Гарантированная запись на диск
                os.fsync(f.fileno())  # Дополнительная синхронизация с диском
        except IOError as e:
            print(f"Ошибка записи в лог: {e}")

    async def monitor_cycle(self) -> List[Dict]:
        """
        Один цикл мониторинга: проверяет все активные суда параллельно,
        обновляет статусы и возвращает список изменений.
        """
        ships = get_active_ships()
        if not ships:
            return []

        # Параллельно проверяем все суда
        tasks = [self.check_ship(ship) for ship in ships]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        changes = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                continue
            if len(result) == 3:
                ship_name, is_online, method = result
                if self.update_status(ship_name, is_online, method):
                    # Если статус изменился, сохраняем данные
                    changes.append({
                        "name": ship_name,
                        "status": self.states[ship_name]["status"]
                    })

        # Сохраняем изменения в файл
        if changes:
            all_ships = load_ships()
            for change in changes:
                for ship in all_ships:
                    if ship.get("name") == change["name"]:
                        ship["status"] = change["status"]
                        break
            save_ships(all_ships)

        return changes

    def display_status(self, changes: List[Dict] = None) -> None:
        """
        Отображает текущие статусы всех судов в виде таблицы.
        Очищает экран перед выводом.
        """
        clear_screen()
        ships = get_active_ships()

        # Получаем настройки
        interval = get_setting("monitor_interval")
        offline_thr = get_setting("offline_threshold")
        online_thr = get_setting("online_threshold")

        # Заголовок
        print("=" * 120)
        print(colored(f"  МОНИТОРИНГ СУДОВ (обновлено: {format_timestamp()})", "bold"))
        print(colored(f"  Всего активных судов: {len(ships)}", "cyan"))
        print(colored(f"  Интервал: {interval}с | Offline порог: {offline_thr} | Online порог: {online_thr}", "gray"))
        print("=" * 120)

        if not ships:
            print(colored("  Нет активных судов для мониторинга.", "yellow"))
            return

        # Заголовки таблицы
        print(f"{'№':<4} {'Название':<25} {'Статус':<30} {'Соединения':<30} {'Заметки'}")
        print("-" * 120)

        # Вывод судов
        for idx, ship in enumerate(ships, 1):
            name = ship.get("name", "Без имени")
            state = self.get_state(name)
            status = state["status"]
            method = state.get("method", None)

            # Формируем статус с методом
            display_status = status
            if status == "в сети" and method:
                display_status = f"{status} ({method})"

            # Цвет статуса
            if status == "в сети":
                status_colored = colored(display_status, "green")
            elif status == "не в сети":
                status_colored = colored(display_status, "red")
            else:
                status_colored = colored(display_status, "yellow")

            # Список соединений - только названия спутников, без IP
            conns = ship.get("connections", [])
            conn_names = [c.get('satellite', '?') for c in conns]
            conn_str = ", ".join(conn_names)

            # Маркер изменения
            change_marker = ""
            if changes:
                for ch in changes:
                    if ch["name"] == name:
                        change_marker = " *"
                        break

            # Выводим строку (используем ansi_len для правильного выравнивания)
            print(f"{idx:<4} {name:<25}", end="")
            status_len = ansi_len(status_colored)
            padding = " " * (30 - status_len)
            print(f"{status_colored}{padding}", end="")
            
            # Получаем заметки
            notes = ship.get("notes", "")
            # Выводим заметки без обрезки, просто добавляем в конец строки
            print(f"{conn_str:<30} {notes}{change_marker}")
            print("-" * 120)
        print("  * — статус изменился в последнем цикле")
        print(colored("  Для остановки нажмите Ctrl+C", "yellow"))

    async def flush_logs_periodically(self) -> None:
        """
        Фоновая задача для периодического сброса буфера логов.
        Вызывает flush() для всех открытых файлов логов каждые 10 секунд.
        """
        # Убедимся, что папка для логов существует
        from logger import ensure_log_dir
        ensure_log_dir()
        
        while self.running:
            try:
                await asyncio.sleep(10)  # Каждые 10 секунд
                
                # Получаем список дат для текущей и предыдущей минуты
                now = datetime.now()
                filenames_to_flush = []
                
                # Добавляем файл текущего дня
                filenames_to_flush.append(os.path.join(LOG_DIR, get_date_filename(now)))
                
                # Добавляем файл предыдущего дня (если сейчас начало нового дня)
                if now.hour == 0 and now.minute == 0:
                    prev_day = now - timedelta(days=1)
                    filenames_to_flush.append(os.path.join(LOG_DIR, get_date_filename(prev_day)))
                
                # flush каждый файл
                for filename in filenames_to_flush:
                    if os.path.exists(filename):
                        try:
                            with open(filename, "a", encoding="utf-8") as f:
                                f.flush()
                                os.fsync(f.fileno())
                        except:
                            pass  # Игнорируем ошибки
            except asyncio.CancelledError:
                break
            except Exception:
                pass  # Игнорируем ошибки в фоновой задаче

    async def run_monitor(self):
        """
        Основной цикл мониторинга.
        Запускается в фоновом режиме и работает до получения сигнала остановки.
        """
        self.running = True
        self.start_time = datetime.now()
        interval = get_setting("monitor_interval")

        print_colored("\n=== МОНИТОРИНГ ЗАПУЩЕН ===", "bold")
        print_colored("Для остановки нажмите Ctrl+C\n", "yellow")

        # Запускаем фоновую задачу для периодического сброса буфера логов
        self.flush_task = asyncio.create_task(self.flush_logs_periodically())

        # Инициализируем состояния для всех судов
        ships = get_active_ships()
        for ship in ships:
            self.reset_state(ship.get("name", "Без имени"))

        # Первый цикл – показываем текущие статусы
        changes = await self.monitor_cycle()
        self.display_status(changes)

        # Основной цикл
        while self.running:
            try:
                await asyncio.sleep(interval)
                if not self.running:
                    break

                changes = await self.monitor_cycle()
                self.display_status(changes)

                # Проверка смены часа для логирования
                current_hour = datetime.now().hour
                hour_changed = False
                for state in self.states.values():
                    # Если last_hour_recorded None (первый запуск) или изменился час
                    if state["last_hour_recorded"] is None or state["last_hour_recorded"] != current_hour:
                        hour_changed = True
                        break
                if hour_changed:
                    try:
                        stats = self.get_stats_for_logging()
                        if stats:
                            await write_hourly_log(stats)
                    finally:
                        self.reset_hour_stats()

            except asyncio.CancelledError:
                break
            except Exception as e:
                print_colored(f"Ошибка в цикле мониторинга: {e}", "red")
                await asyncio.sleep(5)

    def stop(self):
        """Останавливает мониторинг и предлагает сохранить лог."""
        if self.running:
            self.running = False
            # Останавливаем фоновую задачу сброса буфера
            if self.flush_task:
                self.flush_task.cancel()
            # Даём время на завершение цикла
            time.sleep(0.5)
            # Запускаем асинхронную функцию через asyncio.run
            try:
                asyncio.run(self.ask_and_log_partial())
            except RuntimeError:
                # Event loop уже закрыт, пропускаем
                pass

    def get_stats_for_logging(self) -> Dict:
        """
        Возвращает собранную статистику за текущий час для всех судов.
        Формат: { "имя": (success, fail, method) }
        method берется из состояния судна (если оно в сети и есть метод).
        """
        stats = {}
        for name, state in self.states.items():
            if state["hour_success"] > 0 or state["hour_fail"] > 0:
                method = state.get("method", None)
                stats[name] = (state["hour_success"], state["hour_fail"], method)
        return stats

    def reset_hour_stats(self) -> None:
        """Сбрасывает часовую статистику для всех судов."""
        current_hour = datetime.now().hour
        for state in self.states.values():
            state["hour_success"] = 0
            state["hour_fail"] = 0
            state["last_hour_recorded"] = current_hour

    async def ask_and_log_partial(self):
        """Спрашивает пользователя, сохранить ли лог за текущую сессию."""
        if self.start_time is None:
            return
        stats = self.get_stats_for_logging()
        if not stats:
            print_colored("Нет статистики для записи (все счётчики нулевые).", "yellow")
            # Сбрасываем start_time, чтобы не спрашивать при повторном выходе
            self.start_time = None
            return
        
        # Спрашиваем пользователя (всегда интерактивно)
        print_colored("\nМониторинг остановлен. Сохранить лог за текущую сессию? (y/n): ", "cyan", end="")
        try:
            # Используем обычный input(), не asyncio.to_thread
            # Так как мы находимся в asyncio.run(), это будет работать
            answer = input().strip().lower()
        except (EOFError, OSError, KeyboardInterrupt):
            # В неинтерактивном режиме (без консоли) пропускаем запрос
            print_colored("(ввод недоступен, лог не сохранён)", "yellow")
            # Сбрасываем start_time, чтобы не спрашивать при повторном выходе
            self.start_time = None
            return
        if answer in ('y', 'yes', 'да'):
            end_time = datetime.now()
            await write_partial_log(stats, self.start_time, end_time)
            print_colored(f"Лог сохранён в {get_date_filename(end_time)}", "green")
        else:
            print_colored("Лог не сохранён.", "yellow")
        # Сбрасываем start_time, чтобы не спрашивать при повторном выходе
        self.start_time = None


# Глобальный экземпляр монитора
monitor = ShipMonitor()


async def run_monitor_mode():
    """Запускает режим мониторинга в отдельной задаче."""
    await monitor.run_monitor()


def start_monitor():
    """Синхронная обёртка для запуска мониторинга."""
    async def run_monitor_with_log():
        try:
            # Настраиваем обработчик сигнала для корректного завершения
            def signal_handler(sig, frame):
                print_colored("\nОстановка мониторинга...", "yellow")
                monitor.running = False

            signal.signal(signal.SIGINT, signal_handler)
            
            # Запускаем асинхронный мониторинг
            await run_monitor_mode()
        finally:
            # После завершения мониторинга - спрашиваем о сохранении лога
            if monitor.start_time is not None:
                await monitor.ask_and_log_partial()
    
    try:
        asyncio.run(run_monitor_with_log())
    except Exception as e:
        print_colored(f"\nОшибка запуска мониторинга: {e}", "red")
    
    # Пауза перед возвратом в меню, чтобы пользователь увидел результат
    input("\nНажмите Enter для возврата в меню...")