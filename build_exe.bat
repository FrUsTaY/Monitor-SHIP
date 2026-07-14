@echo off
chcp 65001 >nul
title Сборка Monitor SHIP.exe
echo ========================================
echo   СБОРКА MONITOR SHIP.EXE
echo ========================================
echo.

REM Переходим в папку со скриптом
cd /d "%~dp0"

REM Проверяем наличие PyInstaller
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] PyInstaller не найден!
    echo Установите его командой: pip install pyinstaller
    pause
    exit /b 1
)

echo Очистка старых файлов сборки...
if exist build (
    echo   Удаляем папку build...
    rmdir /s /q build
)
if exist dist (
    echo   Удаляем папку dist...
    rmdir /s /q dist
)
if exist main.spec (
    echo   Удаляем main.spec...
    del /f /q main.spec
)
echo.

echo Запуск PyInstaller...
echo.
pyinstaller --onefile --console --icon=Icon.ico main.py

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Сборка не удалась! Проверьте ошибки выше.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   СБОРКА УСПЕШНО ЗАВЕРШЕНА!
echo ========================================
echo.
echo Готовый файл: dist\main.exe
echo.
echo Рекомендации:
echo   1. Переименуйте main.exe в Monitor SHIP.exe
echo   2. Скопируйте его в нужную папку вместе с ships.json
echo   3. При первом запуске создадутся config.json и папка logs
echo.
pause