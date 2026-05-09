"""Unit tests for the FunPay HTML parsers."""

from __future__ import annotations

import json

from funpay_tg.funpay.parsers import (
    parse_account,
    parse_chat_history,
    parse_chat_previews,
    parse_lot_form,
    parse_my_lots,
)

_APP_DATA = json.dumps(
    {
        "userId": 123,
        "csrf-token": "tok-abc",
        "locale": "ru",
    }
)


HOME_HTML = f"""
<html><body data-app-data='{_APP_DATA}'>
<div class="user-link-name">SellerBob</div>
<span class="badge badge-balance">1 234 RUB</span>
<span class="badge badge-trade">5</span>
<span class="badge badge-orders">2</span>
<a class="menu-item-logout" href="/logout/">logout</a>

<div class="promo-game-list">
  <div class="promo-game-item">
    <div class="game-title" data-id="42"></div>
    <a>Steam</a>
    <ul class="list-inline" data-id="42">
      <li><a href="/lots/100/">Аккаунты</a></li>
      <li><a href="/chips/200/">Пополнение</a></li>
    </ul>
  </div>
</div>
<div class="promo-game-list">
  <div class="promo-game-item">
    <div class="game-title" data-id="42"></div>
    <a>Steam</a>
    <ul class="list-inline" data-id="42">
      <li><a href="/lots/100/">Аккаунты</a></li>
      <li><a href="/chips/200/">Пополнение</a></li>
    </ul>
  </div>
</div>
</body></html>
"""


def test_parse_account_extracts_profile_and_categories() -> None:
    account, categories = parse_account(HOME_HTML)
    assert account.user_id == 123
    assert account.username == "SellerBob"
    assert account.csrf_token == "tok-abc"
    assert account.balance == 1234
    assert account.currency == "RUB"
    assert account.active_sales == 5
    assert account.active_purchases == 2
    assert categories and categories[0].name == "Steam"
    sub_names = [s.name for s in categories[0].subcategories]
    assert "Аккаунты" in sub_names
    assert "Пополнение" in sub_names


CHAT_LIST_HTML = """
<div>
  <a class="contact-item unread" data-id="111">
    <div class="media-user-name">Иван</div>
    <div class="contact-item-message">Привет!</div>
  </a>
  <a class="contact-item" data-id="222">
    <div class="media-user-name">Петр</div>
    <div class="contact-item-message">Хочу купить</div>
  </a>
</div>
"""


def test_parse_chat_previews() -> None:
    previews = parse_chat_previews(CHAT_LIST_HTML)
    assert [p.id for p in previews] == [111, 222]
    assert previews[0].unread is True
    assert previews[1].unread is False
    assert previews[0].name == "Иван"
    assert previews[1].last_message == "Хочу купить"


CHAT_HISTORY_HTML = """
<div>
  <div class="chat-msg-item" id="message-1">
    <div class="media-user-name"><a href="/users/9/">Иван</a></div>
    <div class="chat-msg-text">Привет</div>
  </div>
  <div class="chat-msg-item" id="message-2">
    <div class="chat-msg-text">Сколько стоит?</div>
  </div>
</div>
"""


def test_parse_chat_history_carries_author_forward() -> None:
    msgs = parse_chat_history(CHAT_HISTORY_HTML)
    assert [m.id for m in msgs] == [1, 2]
    assert msgs[0].author_id == 9
    assert msgs[0].author_name == "Иван"
    # Second message reuses the previously seen author info
    assert msgs[1].author_id == 9
    assert msgs[1].text == "Сколько стоит?"


MY_LOTS_HTML = """
<div>
  <a class="tc-item" data-offer="alpha">
    <div class="tc-desc-text">Аккаунт CS</div>
    <div class="tc-amount">10</div>
    <div class="tc-price" data-s="199.5">199.5 <span class="unit">₽</span></div>
  </a>
  <a class="tc-item warning" data-offer="beta">
    <div class="tc-desc-text">Аккаунт Dota</div>
    <div class="tc-price" data-s="500"><i class="auto-dlv-icon"></i>500 <span class="unit">₽</span></div>
  </a>
</div>
"""


def test_parse_my_lots() -> None:
    lots = parse_my_lots(MY_LOTS_HTML, subcategory_id=42)
    assert lots[0].id == "alpha"
    assert lots[0].active is True
    assert lots[0].amount == 10
    assert lots[0].price == 199.5
    assert lots[1].id == "beta"
    assert lots[1].active is False
    assert lots[1].auto is True


LOT_FORM_HTML = """
<form class="form-offer-editor" data-offer='{"offer": 555}'>
  <input name="csrf_token" value="tok"/>
  <input name="offer_id" value="555"/>
  <input name="node_id" value="1234"/>
  <input name="price" value="100"/>
  <input name="amount" value="3"/>
  <textarea name="fields[summary][ru]">Заголовок</textarea>
  <textarea name="fields[desc][ru]">Описание</textarea>
  <input type="checkbox" name="active" checked/>
  <input type="checkbox" name="auto_delivery"/>
  <input name="query" value="ignored"/>
</form>
"""


def test_parse_lot_form_extracts_fields_and_ids() -> None:
    form = parse_lot_form(LOT_FORM_HTML)
    assert form.lot_id == 555
    assert form.subcategory_id == 1234
    assert form.fields["price"] == "100"
    assert form.fields["fields[summary][ru]"] == "Заголовок"
    assert form.fields["fields[desc][ru]"] == "Описание"
    assert form.fields["active"] == "on"
    assert "auto_delivery" not in form.fields
    assert "query" not in form.fields
