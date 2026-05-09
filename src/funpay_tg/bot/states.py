"""Aiogram FSM states used across handlers."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ProxyStates(StatesGroup):
    waiting_for_url = State()


class ChatStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_photo = State()


class SellStates(StatesGroup):
    waiting_for_game_query = State()
    waiting_for_subcategory = State()
    waiting_for_short_description = State()
    waiting_for_full_description = State()
    waiting_for_price = State()
    waiting_for_amount = State()
    waiting_for_photo = State()


class AIStates(StatesGroup):
    waiting_for_draft = State()
