#!/bin/bash
# Запуск бота в фоне (можно закрыть терминал).
# Логи пишутся в bot.log в папке проекта.

cd "$(dirname "$0")"
nohup .venv/bin/python main.py >> bot.log 2>&1 &
echo $! > bot.pid
echo "Бот запущен в фоне. PID: $(cat bot.pid)"
echo "Логи: $(pwd)/bot.log"
echo "Остановить: kill \$(cat bot.pid)"
