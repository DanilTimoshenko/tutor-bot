#!/bin/bash
cd "$(dirname "$0")"
if [ -f bot.pid ]; then
  kill "$(cat bot.pid)" 2>/dev/null && echo "Бот остановлен." || echo "Процесс уже не запущен."
  rm -f bot.pid
else
  echo "Файл bot.pid не найден. Останови вручную: pkill -f 'python main.py'"
fi
