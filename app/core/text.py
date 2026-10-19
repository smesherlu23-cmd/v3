from __future__ import annotations

import functools
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


def _swap_layout(text: str) -> str:
    """Тот же набор клавиш в другой раскладке: «еуд» и «tel»."""
    return text.translate(_TO_EN if _CYRILLIC.search(text) else _TO_RU)


_CYRILLIC = re.compile("[а-яё]")


@functools.lru_cache(maxsize=4096)
def _name_index(name: str):
    words = tuple(_words_of(name))
    translit = tuple(_translit_word(w) for w in words)
    return " ".join(words), words, " ".join(translit), translit, "".join(w[0] for w in words)


def _rank(flat: str, plain: str, words, acronym: str, substring: bool) -> int | None:
    if plain.startswith(flat):
        return 0
    if any(w.startswith(flat) for w in words):
        return 1
    if acronym and len(flat) >= 2 and " " not in flat and acronym.startswith(flat):
        return 2
    if substring and flat in plain:
        return 3
    return None


def _best(*ranks):
    found = [r for r in ranks if r is not None]
    return min(found) if found else None


SWAPPED_PENALTY = 5


def match_rank(name: str, query: str) -> int | None:
    """Насколько хорошо `name` подходит под запрос; меньше — лучше, None — мимо.

    0 — имя начинается с запроса, 1 — какое-то слово, 2 — первые буквы слов
    («vsc» → Visual Studio Code), 3 — вхождение (от двух букв: одна буква
    внутри слова ничего не говорит). Запрос кириллицей сверяется ещё и с
    именем, прочитанным русскими буквами («хром» → Chrome). Запрос в другой
    раскладке («еуд» → Telegram) — только если прямо ничего не подошло, и с
    понижением, чтобы не обгонять настоящие совпадения.
    """
    flat = " ".join(_words_of(query or ""))
    if not flat:
        return None
    plain, words, translit, translit_words, acronym = _name_index(name or "")
    if not words:
        return None
    longer = len(flat) >= 2
    best = _rank(flat, plain, words, acronym, longer)
    if _CYRILLIC.search(flat):
        best = _best(best, _rank(flat, translit, translit_words, "", longer))
    if best is not None or not longer:
        return best
    swapped = " ".join(_words_of(_swap_layout(flat)))
    if not swapped or swapped == flat:
        return None
    rank = _rank(swapped, plain, words, acronym, len(swapped) >= 3)
    return None if rank is None else rank + SWAPPED_PENALTY


def match_spans(name: str, query: str) -> list[tuple[str, bool]]:
    """Куски имени для подсветки того, что совпало с запросом."""
    name = name or ""
    low = name.lower()
    flat = " ".join(_words_of(query or ""))
    if not flat or len(low) != len(name):
        return [(name, False)]
    spans = []
    for needle in (flat, " ".join(_words_of(_swap_layout(flat)))):
        if not needle:
            continue
        for part in needle.split(" "):
            start = low.find(part)
            if start >= 0:
                spans.append((start, start + len(part)))
        if spans:
            break
    if not spans and len(flat) >= 2 and " " not in flat:
        starts = [m.start() for m in re.finditer(r"[0-9a-zа-яё+#]+", low)]
        if "".join(low[i] for i in starts).startswith(flat):
            spans = [(i, i + 1) for i in starts[:len(flat)]]
    if not spans:
        return [(name, False)]
    out, pos = [], 0
    for start, end in sorted(set(spans)):
        if start < pos:
            continue
        if start > pos:
            out.append((name[pos:start], False))
        out.append((name[start:end], True))
        pos = end
    if pos < len(name):
        out.append((name[pos:], False))
    return out
