from __future__ import annotations

import flet as ft

from ...core.text import looks_like_target, plu_programs
from .. import colors as C
from .. import widgets as Wg
from ..format import T, cat_icon
from .common import _field, _screen_header


def _add_state(ui):
    state = ui._add_ui
    if state is not None:
        return state
    state = {"root": ft.Column([], spacing=0, expand=True)}
    ui._add_ui = state
    return state


def build_add_screen(ui):
    state = _add_state(ui)
    root = state["root"]
    body = _scanning(ui) if ui.scan.scanning() else _found_list(ui, state)
    root.controls = [_add_header(ui), _add_search(ui, state), body, _add_footer(ui)]
    return root


def _add_header(ui):
    groups = [] if ui.scan.scanning() else ui.scan.found_groups()
    total = sum(g["total"] for g in groups)
    fresh = sum(g["new"] for g in groups)
    if ui.scan.scanning():
        subtitle = "Смотрю, что установлено"
    elif total:
        subtitle = f"{total} {plu_programs(total)} на компьютере, {fresh} из них новые"
    else:
        subtitle = "Установленных программ не нашлось"

    rescan = Wg.secondary_btn("Сканировать снова",
                              (lambda: None) if ui.scan.scanning()
                              else (lambda: ui.scan.start_scan(force=True)),
                              ft.Icons.REFRESH_ROUNDED)
    if ui.scan.scanning():
        rescan.content.controls[0] = Wg.spinner(16)
    return _screen_header("Найти и добавить", subtitle, ui.back_to_grid, extra=[rescan])


def _input_field(ui, state):
    """Одно поле вместо двух одинаковых на вид: имя ищет среди найденного,
    путь или адрес сайта — добавляется кнопкой справа или Enter."""
    field = state.get("input_field")
    if field is None:
        field = _field(ui.view, "add_search", ui.view.add_query or ui.view.manual_path,
                       "Найти или вставить путь, адрес сайта",
                       on_change=lambda e: ui.scan.set_add_input(e.control.value),
                       on_submit=lambda e: ui.in_background(ui.scan.submit_add_input,
                                                            e.control.value))
        state["input_field"] = field
    elif not ui.view.add_query and not ui.view.manual_path and field.value:
        field.value = ""
    return field


def _input_box(ui, state):
    box = state.get("input_box")
    if box is None:
        state["input_add"] = ft.Container()
        box = ft.Container(
            ft.Row([ft.Icon(ft.Icons.SEARCH_ROUNDED, size=16, color=C.MUTED_2),
                    _input_field(ui, state), state["input_add"]],
                   spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=40, bgcolor=C.CARD, border=ft.Border.all(1, C.LINE), border_radius=C.R,
            padding=ft.Padding.only(left=12, right=4), expand=True)
        state["input_box"] = box
    path = ui.view.manual_path
    state["input_add"].content = (
        Wg.primary_btn("Добавить в список",
                       lambda: ui.in_background(ui.scan.add_manual_path, path),
                       ui._accent(), ft.Icons.ADD_ROUNDED, height=32)
        if looks_like_target(path) else None)
    return box


def _add_search(ui, state):
    holder = state.get("search_col")
    if holder is None:
        holder = ft.Column([], spacing=0, tight=True)
        state["search_col"] = holder
    if ui.scan.scanning():
        holder.controls = []
        return holder

    only_new = ft.Container(
        ft.Row([T("Только новые", size=C.FS_BODY, color=C.TEXT_2),
                Wg.toggle(ui.view.only_new, lambda v: ui.scan.toggle_only_new(), ui._accent())],
               spacing=8, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=40, padding=ft.Padding.symmetric(horizontal=12), border_radius=C.R,
        on_click=lambda e: ui.scan.toggle_only_new())

    row = state.get("search_row")
    if row is None:
        row = ft.Row([], spacing=8)
        state["search_row"] = row
        state["search_row_holder"] = ft.Container(
            row, padding=ft.Padding.only(left=24, top=16, right=24, bottom=12))
    row.controls = [
        _input_box(ui, state),
        Wg.secondary_btn("Файл…", ui.scan.pick_file, ft.Icons.INSERT_DRIVE_FILE_OUTLINED,
                         height=40),
        Wg.secondary_btn("Папка…", ui.scan.pick_folder, ft.Icons.FOLDER_OPEN_ROUNDED, height=40),
        Wg.hoverable(only_new, None, C.CARD),
    ]
    holder.controls = [state["search_row_holder"]]
    return holder


def _scanning(ui):
    return ft.Container(
        ft.Column([Wg.spinner(36), T("Смотрю, что установлено", size=C.FS_TITLE,
                                     color=C.TEXT_2)],
                  spacing=24, tight=True,
                  horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                  alignment=ft.MainAxisAlignment.CENTER),
        expand=True, alignment=ft.Alignment.CENTER)


def _found_list(ui, state):
    groups = ui.scan.found_groups()
    ui.scan.preselect_new(groups)
    rows = [_inline_error(ui, err) for err in ui.scan.scan_errors()]
    if not groups:
        rows.append(_add_empty(ui))
    for group in groups:
        rows.append(_add_group(ui, group))

    col = state.get("rows_col")
    if col is None:
        col = ft.Column(rows, spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)
        state["rows_col"] = col
        state["rows_holder"] = ft.Container(col, expand=True,
                                            padding=ft.Padding.only(left=24, right=24, bottom=8))
    else:
        col.controls = rows
    return state["rows_holder"]


def _inline_error(ui, err):
    return ft.Container(
        ft.Row([ft.Icon(ft.Icons.ERROR_OUTLINE_ROUNDED, size=16, color=C.DANGER),
                ft.Column([T(f"{err.get('label') or 'Источник'} не отдал список программ",
                             size=C.FS_BODY, color=C.TEXT),
                           T("Остальные источники прочитались", size=C.FS_SMALL,
                             color=C.MUTED)],
                          spacing=2, expand=True, tight=True),
                Wg.secondary_btn("Повторить", lambda: ui.scan.start_scan(force=True),
                                 height=32),
                Wg.quiet_btn("Скрыть", ui.scan.dismiss_scan_errors, color=C.MUTED)],
               spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor=C.ERR_BG, border=ft.Border.all(1, C.ERR_BORDER), border_radius=C.R_LARGE,
        padding=ft.Padding.symmetric(vertical=12, horizontal=16), margin=ft.Margin.only(bottom=8))


def _add_empty(ui):
    # «Всё уже в библиотеке» — только если поиск вообще что-то нашёл: пустой
    # результат (скажем, PowerShell запрещён политикой) так не называется.
    only_new = ui.view.only_new and bool(ui.scan.cached_discovery())
    return ft.Container(
        ft.Column([
            T("Новых программ не нашлось" if only_new else "Ничего не нашлось",
              size=C.FS_TITLE, weight=ft.FontWeight.BOLD, color=C.TEXT),
            T("Всё установленное уже в библиотеке." if only_new
              else "Автоматический поиск ничего не дал — выберите файл или папку "
                   "либо вставьте выше путь или адрес сайта.", size=C.FS_BODY, color=C.MUTED),
            ft.Container(ft.Row([
                Wg.secondary_btn("Показать все найденные" if only_new else "Повторить поиск",
                                 ui.scan.toggle_only_new if only_new
                                 else (lambda: ui.scan.start_scan(force=True))),
                Wg.secondary_btn("Выбрать файл", ui.scan.pick_file, ft.Icons.FOLDER_OPEN_ROUNDED),
            ], spacing=8), padding=ft.Padding.only(top=8)),
        ], spacing=8, tight=True), width=480, padding=ft.Padding.only(top=32))


def _add_group(ui, group):
    keys = [r["key"] for r in group["rows"] if r["is_new"]]
    picked = [k for k in keys if k in ui.view.add_sel]
    accent = ui._accent()
    if keys and len(picked) == len(keys):
        box, box_color = ft.Icons.CHECK_BOX_ROUNDED, accent
    elif picked:
        box, box_color = ft.Icons.INDETERMINATE_CHECK_BOX_ROUNDED, accent
    else:
        box, box_color = ft.Icons.CHECK_BOX_OUTLINE_BLANK_ROUNDED, C.FAINT

    cat = group.get("cat")
    glyph = (Wg.cat_glyph(cat, size=16) if cat
             else ft.Icon(cat_icon(group["icon"]), size=16, color=C.MUTED))
    count = f"{len(picked)} из {len(keys)}" if keys else "уже в библиотеке"
    head = [ft.Icon(box, size=18, color=box_color), glyph,
            T(group["label"], size=C.FS_BODY, weight=ft.FontWeight.W_600, color=C.TEXT),
            T(count, size=C.FS_SMALL, color=C.MUTED_2),
            ft.Container(height=1, bgcolor=C.LINE, expand=True)]

    header = ft.Container(ft.Row(head, spacing=8,
                                 vertical_alignment=ft.CrossAxisAlignment.CENTER),
                          height=40, padding=ft.Padding.symmetric(horizontal=12),
                          tooltip="Отметить или снять всю группу",
                          on_click=lambda e, g=group: ui.scan.toggle_add_group(g))
    rows = [header] + [_add_row(ui, row) for row in group["rows"]]
    return ft.Container(ft.Column(rows, spacing=2), padding=ft.Padding.only(bottom=12))


def _add_row(ui, row):
    checked = row["key"] in ui.view.add_sel
    accent = ui._accent()
    if not row["is_new"]:
        box = ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, size=18, color=C.GREEN)
    else:
        box = ft.Icon(ft.Icons.CHECK_BOX_ROUNDED if checked else ft.Icons.CHECK_BOX_OUTLINE_BLANK_ROUNDED,
                      size=18, color=accent if checked else C.FAINT)

    item = row["item"]
    lines = [T(row["name"], size=C.FS_BODY, weight=ft.FontWeight.W_500, color=C.TEXT,
               max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)]
    # Источник — мелкой подписью: важно, куда программа ляжет, а не откуда.
    note = row.get("source_label") or ""
    if not row["is_new"]:
        note = "уже в библиотеке"
    if note:
        lines.append(T(note, size=C.FS_SMALL, color=C.MUTED_2, max_lines=1))
    controls = [box, ui.icon_slot(item, 32, 8, glyph=16),
                ft.Column(lines, spacing=2, tight=True, expand=True)]

    if row["is_new"]:
        cat_id = ui.scan.add_category_for(row)
        cat = next((c for c in ui.categories() if c["id"] == cat_id), None)
        chip = ft.Container(
            ft.Row([Wg.cat_glyph(cat, size=14) if cat
                    else T("Категория", size=C.FS_SMALL, color=C.MUTED_2),
                    T(cat["name"], size=C.FS_SMALL, color=C.TEXT_2) if cat else ft.Container(),
                    ft.Icon(ft.Icons.SWAP_VERT_ROUNDED, size=14, color=C.FAINT)],
                   spacing=8, tight=True),
            height=28, padding=ft.Padding.symmetric(horizontal=12),
            bgcolor=C.RAISED if checked else C.CARD, border_radius=14,
            tooltip="Другая категория",
            on_click=lambda e, r=row: ui.scan.cycle_add_category(r))
        controls.append(chip)

    rest = C.CARD if checked else None
    container = ft.Container(
        ft.Row(controls, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=52, padding=ft.Padding.symmetric(horizontal=12), border_radius=C.R,
        bgcolor=rest, opacity=0.5 if not row["is_new"] else 1,
        on_click=lambda e, r=row: ui.scan.toggle_add_row(r))
    return Wg.hoverable(container, rest, C.RAISED) if row["is_new"] else container


def _add_footer(ui):
    count = len(ui.view.add_sel)
    left = [T(f"Отмечено {count}" if count else "Ничего не отмечено", size=C.FS_BODY,
              weight=ft.FontWeight.W_600, color=C.TEXT)]
    return ft.Container(
        ft.Row(left + [
            ft.Container(expand=True),
            ft.Container(Wg.secondary_btn("Решу позже", ui.scan.defer_add, ft.Icons.INBOX_ROUNDED),
                         tooltip="Отмеченное подождёт в «Новых программах» — "
                                 "разложите по одной, когда будет время"),
            Wg.primary_btn(f"Добавить {count}" if count else "Добавить", ui.scan.commit_add,
                           ui._accent(), ft.Icons.ADD_ROUNDED),
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        height=64, padding=ft.Padding.symmetric(horizontal=24),
        border=ft.Border.only(top=ft.BorderSide(1, C.LINE)))
