"""Парсер расписания СибГУ: HTML страницы группы -> data.json

Запуск:  python3 parse.py page.html data.json
Нужен пакет beautifulsoup4 (pip3 install beautifulsoup4)
"""
import json
import re
import sys
from datetime import datetime

from bs4 import BeautifulSoup

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def clean(text):
    """Убирает переносы и двойные пробелы"""
    return re.sub(r"\s+", " ", text or "").strip()


def parse_lesson(ul):
    """Один <ul> = одна пара: предмет, тип, препод, аудитория, подгруппа"""
    lesson = {"name": "", "type": "", "teacher": "", "room": "", "address": "", "subgroup": ""}
    for li in ul.find_all("li", recursive=False):
        icon = li.find("i")
        kind = " ".join(icon.get("class", [])) if icon else ""
        if "fa-bookmark" in kind:
            name = li.find("span", class_="name")
            lesson["name"] = clean(name.get_text()) if name else ""
            m = re.search(r"\(([^)]+)\)", li.get_text())  # «(Лекция)»
            lesson["type"] = m.group(1) if m else ""
        elif "fa-user" in kind:
            lesson["teacher"] = clean(li.get_text())
        elif "fa-compass" in kind:
            a = li.find("a")
            lesson["room"] = clean(li.get_text()).replace('"', "")
            lesson["address"] = clean(a.get("title", "")) if a else ""
        elif "fa-paperclip" in kind:
            lesson["subgroup"] = clean(li.get_text())
    return lesson


def parse(html):
    soup = BeautifulSoup(html, "html.parser")

    # Заголовок: «28.09.2026 - 1 неделя» — от него считаем чётность недель
    h4 = clean(soup.find("h4", class_="text-center").get_text())
    date_str, week_str = re.search(r"(\d{2}\.\d{2}\.\d{4}).*?(\d)\s*неделя", h4).groups()
    group = clean(soup.find("h3", class_="text-center").get_text()).split(" ")[0].strip('"')

    weeks = {}
    for week in (1, 2):
        tab = soup.find(id=f"week_{week}_tab")
        days = {}
        for day in tab.find_all("div", class_="day"):
            day_key = next(c for c in day["class"] if c in DAYS)
            lessons = []
            for line in day.select(".body > .line"):
                t = clean(line.select_one(".time .hidden-xs").get_text())
                start, end = t.split("-")
                # В одном слоте может быть несколько <ul> (разные подгруппы)
                for ul in line.select(".discipline ul.list-unstyled"):
                    lessons.append({"start": start, "end": end, **parse_lesson(ul)})
            days[day_key] = lessons
        weeks[str(week)] = days

    return {
        "group": group,
        "anchor": {"date": datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d"), "week": int(week_str)},
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "weeks": weeks,
    }


def make_ics(data, subgroup=0, until="20261231T235959", remind_min=15):
    """Календарь .ics: каждая пара повторяется раз в 2 недели до конца семестра.
    subgroup=0 — все пары, 1 или 2 — без пар чужой подгруппы"""
    from datetime import timedelta

    anchor = datetime.strptime(data["anchor"]["date"], "%Y-%m-%d")
    anchor_mon = anchor - timedelta(days=anchor.weekday())
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//pary//sibsau//RU", "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:Пары {data['group']}" + (f" ({subgroup} подгр.)" if subgroup else ""),
        "X-WR-TIMEZONE:Asia/Krasnoyarsk", "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        # Часовой пояс Красноярска: UTC+7 круглый год
        "BEGIN:VTIMEZONE", "TZID:Asia/Krasnoyarsk", "BEGIN:STANDARD", "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0700", "TZOFFSETTO:+0700", "TZNAME:+07", "END:STANDARD", "END:VTIMEZONE",
    ]
    for week, days in data["weeks"].items():
        # Понедельник ближайшей недели с этим номером
        mon = anchor_mon + timedelta(weeks=(int(week) - data["anchor"]["week"]) % 2)
        for day, lessons in days.items():
            date = mon + timedelta(days=DAYS.index(day))
            for i, l in enumerate(lessons):
                sg = re.sub(r"\D", "", l["subgroup"])
                if subgroup and sg and int(sg) != subgroup:
                    continue
                d = date.strftime("%Y%m%d")
                name = l["name"].capitalize()
                room = l["room"]
                lines += [
                    "BEGIN:VEVENT",
                    f"UID:{data['group']}-w{week}-{day}-{i}-s{subgroup}@pary",
                    f"DTSTAMP:{data['updated'].replace('-', '')}T000000",
                    f"DTSTART;TZID=Asia/Krasnoyarsk:{d}T{l['start'].replace(':', '')}00",
                    f"DTEND;TZID=Asia/Krasnoyarsk:{d}T{l['end'].replace(':', '')}00",
                    f"RRULE:FREQ=WEEKLY;INTERVAL=2;UNTIL={until}",
                    f"SUMMARY:{name} ({l['type'].replace('Лабораторная работа', 'лаба').lower()})",
                    f"LOCATION:{room}",
                    f"DESCRIPTION:{l['teacher']}" + (f"\\n{l['subgroup']}" if l["subgroup"] else ""),
                    "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{name}, {room}",
                    f"TRIGGER:-PT{remind_min}M", "END:VALARM",
                    "END:VEVENT",
                ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "page.html"
    dst = sys.argv[2] if len(sys.argv) > 2 else "data.json"
    data = parse(open(src, encoding="utf-8").read())
    # Если пары не поменялись — оставляем старую дату обновления, чтобы не было пустых коммитов
    import os
    if os.path.exists(dst):
        old = json.load(open(dst, encoding="utf-8"))
        if old.get("weeks") == data["weeks"] and old.get("anchor") == data["anchor"]:
            data["updated"] = old["updated"]
    json.dump(data, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out_dir = os.path.dirname(os.path.abspath(dst))
    for sg in (0, 1, 2):
        name = "schedule.ics" if sg == 0 else f"schedule-{sg}.ics"
        with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="") as f:
            f.write(make_ics(data, sg))
    total = sum(len(v) for w in data["weeks"].values() for v in w.values())
    print(f"{data['group']}: {total} пар, опорная дата {data['anchor']}")
