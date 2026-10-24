from __future__ import annotations

import flet as ft

from ...core import queries
from ...core.text import plu_programs
from .. import colors as C
from .. import menus
from .. import widgets as Wg
from ..format import T


def build_triage_screen(ui):
    """«Новые программы»: по одной карточке, решение одной клавишей.

    Раньше экран назывался «Разбор» — слово нигде не объяснялось.
    """
    queue = ui.inbox()
    if not queue:
        return _triage_done(ui)

    item = queue[0]
    total = len(queue)
    done = getattr(ui.triage, "done_count", 0)
    picks = queries.suggest_categories(item, ui.categories())
    keyed, rest = picks[:queries.TRIAGE_KEYS], picks[queries.TRIAGE_KEYS:]

    head = ft.Container(
        ft.Row([ft.Column([
            T("Новые программы", size=C.FS_HEADING, weight=ft.FontWeight.BOLD, color=C.TEXT),
            T(f"Осталось {total} · разложено {done}. Куда положить эту?",
              size=C.FS_SMALL, color=C.MUTED_2),
        ], spacing=4, tight=True, expand=True),
            Wg.quiet_btn("Отложить все", ui.triage.triage_defer_all, color=C.MUTED)],
            spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.only(left=24, top=24, right=24))

    accent = ui._accent()
    bar = ft.Container(
        ft.Row([ft.Container(height=4, border_radius=2, bgcolor=accent,
                             expand=max(done, 1), visible=bool(done)),
                ft.Container(height=4, border_radius=2, bgcolor=C.LINE, expand=total)],
               spacing=4), padding=ft.Padding.only(left=24, top=16, right=24))

    chips = []
    for index, cat in enumerate(keyed):
        first = index == 0
        row = [T(str(index + 1), size=C.FS_CAPTION, weight=ft.FontWeight.BOLD,
                 color=C.MUTED if first else C.MUTED_2, font_family="monospace"),
               Wg.cat_glyph(cat, size=18),
               T(cat["name"], size=C.FS_BODY, weight=ft.FontWeight.W_600 if first else None,
                 color=C.TEXT if first else C.TEXT_2)]
        chip = ft.Container(
            ft.Row(row, spacing=8, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=44, padding=ft.Padding.symmetric(horizontal=16), border_radius=C.R,
            bgcolor=C.RAISED if first else C.CARD,
            border=ft.Border.all(1, C.BORDER if first else C.TRANSPARENT),
            tooltip="Предложенная — Enter" if first else None,
            on_click=lambda e, cid=cat["id"], iid=item["id"]: ui.triage.triage_place(iid, cid))
        chips.append(Wg.hoverable(chip, chip.bgcolor, C.RAISED))
    if rest:
        more = ft.Container(
            ft.Row([T("Ещё…", size=C.FS_BODY, color=C.TEXT_2),
                    ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=16, color=C.FAINT)],
                   spacing=4, tight=True),
            height=44, padding=ft.Padding.symmetric(horizontal=16), border_radius=C.R,
            border=ft.Border.all(1, C.BORDER),
            on_click=lambda e, r=rest, iid=item["id"]: _more_menu(ui, iid, r, e))
        chips.append(Wg.hoverable(more, None, C.RAISED))

    source = queries.SOURCES.get(item.get("source") or "", {}).get("label", "")
    card = ft.Column([
        ft.Container(ui.icon_slot(item, 96, 24, glyph=44), alignment=ft.Alignment.CENTER),
        ft.Column([
            T(item["name"], size=C.FS_DISPLAY, weight=ft.FontWeight.BOLD, color=C.TEXT,
              text_align=ft.TextAlign.CENTER),
            T(f"Найдено: {source}" if source else "", size=C.FS_SMALL, color=C.MUTED_2),
        ], spacing=8, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Container(ft.Row(chips, spacing=8, wrap=True, run_spacing=8,
                            alignment=ft.MainAxisAlignment.CENTER), width=720),
    ], spacing=24, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER)

    def hint(key, label, on_click=None, tooltip=None):
        content = ft.Row([Wg.key_chip(key), T(label, size=C.FS_SMALL, color=C.MUTED_2)],
                         spacing=8, tight=True)
        if on_click is None:
            return content
        return Wg.hoverable(ft.Container(content, tooltip=tooltip, border_radius=C.R_SMALL,
                                         padding=ft.Padding.symmetric(vertical=4, horizontal=4),
                                         on_click=lambda e: on_click()), None, C.CARD)

    keys = f"1–{min(len(keyed), queries.TRIAGE_KEYS)}" if len(keyed) > 1 else "1"
    footer = ft.Container(
        ft.Row([hint(keys, "положить в категорию"), hint("Enter", "в предложенную"),
                hint("→", "показать позже", lambda iid=item["id"]: ui.triage.triage_skip(iid),
                     "Вернётся в конец очереди"),
                ft.Container(expand=True),
                hint("Del", "не нужна", lambda iid=item["id"]: ui.triage.triage_drop(iid),
                     "Больше не предлагать")],
               spacing=24, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=52, padding=ft.Padding.symmetric(horizontal=24),
        border=ft.Border.only(top=ft.BorderSide(1, C.LINE)))

    return ft.Column([head, bar,
                      ft.Container(card, expand=True, padding=ft.Padding.symmetric(horizontal=24),
                                   alignment=ft.Alignment.CENTER),
                      footer], spacing=0, expand=True)


def _more_menu(ui, item_id, cats, e):
    x, y = ui.context_menus.menu_at(e)
    rows = [menus.item(cat.get("icon") or "folder", cat["name"],
                       lambda cid=cat["id"]: ui.triage.triage_place(item_id, cid))
            for cat in cats]
    ui.menu.show(x, y, rows, header=menus.text_header("Остальные категории"))


def _triage_done(ui):
    done = getattr(ui.triage, "done_count", 0)
    text = (f"{done} {plu_programs(done)} {'лежит' if done % 10 == 1 and done % 100 != 11 else 'лежат'}"
            " по местам. " if done else "")
    later = ("Новое Centurio найдёт сам и покажет здесь." if ui.setting("auto_rescan")
             else "Чтобы найти новое, нажмите «Поискать ещё» или включите "
                  "автопроверку в настройках.")
    return ft.Container(
        ft.Column([
            ft.Container(ft.Icon(ft.Icons.CHECK, size=28, color=C.GREEN),
                         width=64, height=64, border_radius=C.R_LARGE, bgcolor=C.OK_BG,
                         border=ft.Border.all(1, C.OK_BORDER),
                         alignment=ft.Alignment.CENTER),
            T("Всё разложено", size=C.FS_HEADING, weight=ft.FontWeight.BOLD, color=C.TEXT),
            T(text + later,
              size=C.FS_BODY, color=C.MUTED, width=320, text_align=ft.TextAlign.CENTER),
            ft.Container(ft.Row([
                Wg.primary_btn("К библиотеке", ui.back_to_grid, ui._accent()),
                Wg.secondary_btn("Поискать ещё", ui.open_add),
            ], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
                padding=ft.Padding.only(top=8)),
        ], spacing=16, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER),
        expand=True, alignment=ft.Alignment.CENTER, padding=ft.Padding.all(32))
