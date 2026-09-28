#!/bin/bash
# Обновить расписание: скачать страницу группы, пересобрать data.json и календари, выложить на GitHub
# Запуск из папки проекта:  ./update.sh
# VPN на время запуска лучше выключить: сайт СибГУ может не пускать зарубежные адреса
set -e
cd "$(dirname "$0")"

URL="https://timetable.pallada.sibsau.ru/timetable/group/14344"
curl -sSL --max-time 30 -A "Mozilla/5.0" "$URL" -o page.html
python3 parse.py page.html data.json

if git diff --quiet -- data.json schedule*.ics; then
  echo "Расписание не поменялось"
else
  git add data.json schedule*.ics
  git commit -m "Обновил расписание $(date +%d.%m.%Y)"
  git push
  echo "Готово, через минуту обновится на телефоне"
fi
