"""Обновления окна из фоновых потоков во Flet 1.0.

Flet 1.0 отправляет изменения окну через asyncio.Queue: `send_message`
кладёт сообщение `put_nowait`, а цикл событий его забирает. Из чужого
потока такая очередь цикл не будит, и сообщение лежит, пока цикл не
проснётся по другой причине — движение мыши над окном, нажатие, таймер.
У Centurio из фоновых потоков приходит многое: метка «открыто» от
монитора процессов, найденные программы, значки, меню трея, уведомления.
Без мыши над окном всё это не появлялось вовсе.

Здесь отправка из чужого потока переносится в цикл событий через
`call_soon_threadsafe`, который цикл будит. Порядок сообщений сохраняется:
пока перенесённые не ушли, отправки из самого цикла встают за ними.
"""
from __future__ import annotations

import asyncio
import threading

_MARK = "_centurio_thread_safe"


def install() -> bool:
    """Поставить обёртку; True — если поставлена сейчас или раньше."""
    try:
        from flet.messaging.flet_socket_server import FletSocketServer
    except ImportError:
        return False
    original = FletSocketServer.send_message
    if getattr(original, _MARK, False):
        return True
    lock = threading.Lock()
    pending = {"count": 0}

    def deferred(self, message):
        with lock:
            pending["count"] -= 1
        original(self, message)

    def send_message(self, message):
        loop = getattr(self, "loop", None)
        try:
            on_loop = asyncio.get_running_loop() is loop
        except RuntimeError:
            on_loop = False
        if loop is None or loop.is_closed():
            return original(self, message)
        with lock:
            direct = on_loop and pending["count"] == 0
            if not direct:
                pending["count"] += 1
        if direct:
            return original(self, message)
        try:
            loop.call_soon_threadsafe(deferred, self, message)
        except RuntimeError:
            # Цикл закрылся между проверкой и вызовом — программа выходит.
            with lock:
                pending["count"] -= 1

    setattr(send_message, _MARK, True)
    FletSocketServer.send_message = send_message
    return True
