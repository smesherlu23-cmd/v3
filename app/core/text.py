from __future__ import annotations

import re
import shlex
import time


def split_args(text: str) -> list[str]:
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    lexer.commenters = ""
    return list(lexer)


def launch_key(item) -> str:
    """Что именно запускается: путь и аргументы, без учёта регистра.

    Ярлыки приложений Chrome или Discord ведут на один и тот же exe с разными
    аргументами — по одному пути они склеивались в одну запись.
    """
    path = str(item.get("path") or "").strip().lower()
    args = item.get("args")
    if isinstance(args, (list, tuple)):
        args = " ".join(str(a) for a in args)
    args = str(args or "").strip().lower()
    return f"{path}\x00{args}" if args else path


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


# Поиск. Пользователь набирает не в той раскладке («еуд» вместо «tel») и
# по-русски («телеграм», «ворд»), а имена программ чаще латиницей.
_EN_KEYS = "`qwertyuiop[]asdfghjkl;'zxcvbnm,."
_RU_KEYS = "ёйцукенгшщзхъфывапролджэячсмитьбю"
_TO_RU = str.maketrans(_EN_KEYS, _RU_KEYS)
_TO_EN = str.maketrans(_RU_KEYS, _EN_KEYS)

_TRANSLIT = (
    ("shch", "щ"), ("sch", "щ"), ("chr", "хр"), ("dge", "дж"), ("you", "ю"),
    ("ch", "ч"), ("sh", "ш"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("wh", "в"),
    ("ph", "ф"), ("th", "т"), ("ya", "я"), ("yu", "ю"), ("yo", "ё"), ("oo", "у"),
    ("ee", "и"), ("ea", "и"), ("xc", "кс"), ("ck", "к"),
    ("a", "а"), ("b", "б"), ("c", "к"), ("d", "д"), ("e", "е"), ("f", "ф"), ("g", "г"),
    ("h", "х"), ("i", "и"), ("j", "дж"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"),
    ("o", "о"), ("p", "п"), ("q", "к"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"),
    ("v", "в"), ("w", "в"), ("x", "кс"), ("y", "и"), ("z", "з"),
)


def _words_of(text: str) -> list[str]:
    return [w for w in re.split(r"[^0-9a-zа-яё+#]+", text.lower()) if w]


def _translit_word(word: str) -> str:
    out = ["э"] if word.startswith("e") else []
    i = 1 if out else 0
    while i < len(word):
        for lat, cyr in _TRANSLIT:
            if word.startswith(lat, i):
                out.append(cyr)
                i += len(lat)
                break
        else:
            out.append(word[i])
            i += 1
    return "".join(out)


def query_variants(query: str) -> list[str]:
    q = (query or "").strip().lower()
    if not q:
        return []
    return list(dict.fromkeys(v for v in (q, q.translate(_TO_RU), q.translate(_TO_EN)) if v))


def match_rank(name: str, query: str) -> int | None:
    """Насколько хорошо `name` подходит под запрос; меньше — лучше, None — мимо.

    0 — имя начинается с запроса, 1 — какое-то слово, 2 — первые буквы слов
    («vsc» → Visual Studio Code), 3 — просто вхождение. Каждый уровень
    проверяется и для запроса в другой раскладке, и для имени, прочитанного
    русскими буквами.
    """
    words = _words_of(name)
    if not words:
        return None
    plain = " ".join(words)
    translit_words = [_translit_word(w) for w in words]
    translit = " ".join(translit_words)
    acronym = "".join(w[0] for w in words)
    best = None
    for q in query_variants(query):
        flat = " ".join(_words_of(q)) or q
        if plain.startswith(flat) or translit.startswith(flat):
            rank = 0
        elif any(w.startswith(flat) for w in words + translit_words):
            rank = 1
        elif len(flat) >= 2 and " " not in flat and acronym.startswith(flat):
            rank = 2
        elif flat in plain or flat in translit:
            rank = 3
        else:
            continue
        best = rank if best is None else min(best, rank)
    return best
