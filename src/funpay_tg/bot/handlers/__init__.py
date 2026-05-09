"""Bot handler routers."""

from aiogram import Router

from . import chats, lots, proxies, sell, settings, start


def all_routers() -> list[Router]:
    """Return all registered routers in the order they should be included."""
    return [
        start.router,
        proxies.router,
        chats.router,
        lots.router,
        sell.router,
        settings.router,
    ]
