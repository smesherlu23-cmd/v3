from __future__ import annotations

import shlex
import time


def split_args(text: str) -> list[str]:
    r"""Разобрать строку аргументов так, как её понимает Windows.

    Ни один готовый режим `shlex` здесь не подходит. `posix=False` не снимает
    кавычки — программа получала значение вместе с ними, а перед запуском от
    администратора `subprocess.list2cmdline` экранировал уже закавыченный
    токен ещё раз:

        ввод      : --file "C:\Program Files\a.txt"
        сохранено : ['--file', '"C:\\Program Files\\a.txt"']
        командная : --file "\"C:\Program Files\a.txt\""

    `posix=True` кавычки снимает, но считает обратную косую черту
    экранированием — а в Windows это разделитель пути, и `C:\Program Files`
    превратился бы в `C:Program Files`. Поэтому берётся posix-лексер с
    отключённым экранированием. Комментарии тоже выключены: иначе `#` в
    середине URL обрубил бы остаток строки.

    Незакрытая кавычка поднимает `ValueError` — вызывающий решает сам, как
    поступить с явно неправильным вводом.
    """
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    lexer.commenters = ""
    return list(lexer)


def _plural(n, one, few, many):
    m10, m100 = n % 10, n % 100
    if m10 == 1 and m100 != 11:
        return one
    if 2 <= m10 <= 4 and not (10 <= m100 < 20):
        return few
    return many


def initials(name: str) -> str:
    n = (name or "?").strip()
    return n[0].upper() if n else "?"


def time_ago(ms: int) -> str:
    if not ms:
        return ""
    diff = time.time() * 1000 - ms
    m = int(diff // 60000)
    if m < 1:
        return "только что"
    if m < 60:
        return f"{m} {_plural(m, 'минуту', 'минуты', 'минут')} назад"
    h = m // 60
    if h < 24:
        return f"{h} {_plural(h, 'час', 'часа', 'часов')} назад"
    d = h // 24
    return f"{d} {_plural(d, 'день', 'дня', 'дней')} назад"


def short_ago(ms: int) -> str:
    if not ms:
        return ""
    diff = time.time() * 1000 - ms
    hours = int(diff // 3600000)
    if hours < 24:
        return "сегодня"
    days = hours // 24
    if days == 1:
        return "вчера"
    return f"{days} {_plural(days, 'день', 'дня', 'дней')} назад"


def plu_apps(n):
    return _plural(n, "приложение", "приложения", "приложений")


def plu_programs(n):
    return _plural(n, "программа", "программы", "программ")


def plu_windows(n):
    return _plural(n, "окно", "окна", "окон")
