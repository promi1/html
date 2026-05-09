"""HTML parsers for FunPay pages (kept separate from the HTTP client)."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

from . import exceptions
from .types import (
    Account,
    Category,
    ChatPreview,
    LotFields,
    Message,
    MyLot,
    SubCategory,
    SubCategoryType,
)

_BALANCE_RE = re.compile(r"^([\d\s]+)\s*([^\d\s]+)$")


def parse_account(html: str) -> tuple[Account, list[Category]]:
    """Parse the home page HTML.

    Returns the authenticated user's profile and the full list of game
    categories visible on the home page.
    """
    soup = BeautifulSoup(html, "lxml")
    body = soup.find("body")
    if not body or not body.get("data-app-data"):
        raise exceptions.UnauthorizedError("FunPay home page is missing data-app-data")
    raw_app_data = body.get("data-app-data")
    if isinstance(raw_app_data, list):
        raw_app_data = raw_app_data[0]
    app_data: dict[str, Any] = json.loads(raw_app_data)

    username_node = soup.find("div", class_="user-link-name")
    if not username_node:
        raise exceptions.UnauthorizedError("user-link-name not found — golden_key invalid?")

    balance_node = soup.find("span", class_="badge-balance")
    if balance_node:
        match = _BALANCE_RE.match(balance_node.text.strip())
        if match:
            balance_int = int(match.group(1).replace(" ", "").replace("\xa0", ""))
            currency = match.group(2)
        else:
            balance_int = 0
            currency = ""
    else:
        balance_int = 0
        currency = ""

    sales_node = soup.find("span", class_="badge-trade")
    purchases_node = soup.find("span", class_="badge-orders")

    account = Account(
        user_id=int(app_data["userId"]),
        username=username_node.text.strip(),
        csrf_token=str(app_data["csrf-token"]),
        balance=balance_int,
        currency=currency,
        active_sales=int(sales_node.text.strip()) if sales_node else 0,
        active_purchases=int(purchases_node.text.strip()) if purchases_node else 0,
        locale=str(app_data.get("locale", "ru")),
        phpsessid=None,
    )

    categories = _parse_categories(soup)
    return account, categories


def _parse_categories(soup: BeautifulSoup) -> list[Category]:
    """Parse the games / subcategories sidebar from the home page."""
    tables = soup.find_all("div", class_="promo-game-list")
    if not tables:
        return []
    table = tables[1] if len(tables) > 1 else tables[0]
    games_divs = table.find_all("div", class_="promo-game-item")
    categories: list[Category] = []

    for game_div in games_divs:
        title_div = game_div.find("div", class_="game-title")
        if not title_div or not title_div.get("data-id"):
            continue
        gid = int(title_div["data-id"])
        anchor = game_div.find("a")
        gname = anchor.text.strip() if anchor else f"game-{gid}"
        category = Category(id=gid, name=gname)

        for sub_list in game_div.find_all("ul", class_="list-inline"):
            for li in sub_list.find_all("li"):
                a = li.find("a")
                if not a or not a.get("href"):
                    continue
                href: str = a["href"]
                stype = (
                    SubCategoryType.CURRENCY if "/chips/" in href else SubCategoryType.COMMON
                )
                parts = href.rstrip("/").split("/")
                try:
                    sid = int(parts[-1])
                except ValueError:
                    continue
                category.subcategories.append(
                    SubCategory(id=sid, name=a.text.strip(), type=stype, game_id=gid)
                )
        categories.append(category)
    return categories


def parse_chat_previews(html: str) -> list[ChatPreview]:
    """Parse the chat list panel (`/chat/`)."""
    soup = BeautifulSoup(html, "lxml")
    items = soup.find_all("a", class_="contact-item")
    result: list[ChatPreview] = []
    for item in items:
        chat_id = item.get("data-id") or item.get("data-node-msg")
        if not chat_id:
            continue
        try:
            chat_id_int = int(chat_id)
        except (TypeError, ValueError):
            continue
        name_node = item.find("div", class_="media-user-name")
        msg_node = item.find("div", class_="contact-item-message")
        unread = "unread" in item.get("class", [])
        result.append(
            ChatPreview(
                id=chat_id_int,
                name=name_node.text.strip() if name_node else f"chat-{chat_id_int}",
                last_message=msg_node.text.strip() if msg_node else "",
                unread=unread,
            )
        )
    return result


def parse_chat_history(html: str) -> list[Message]:
    """Parse messages from a chat history page or HTML fragment."""
    soup = BeautifulSoup(html, "lxml")
    messages: list[Message] = []
    last_author_id = 0
    last_author_name: str | None = None

    for item in soup.find_all("div", class_="chat-msg-item"):
        msg_id_attr = item.get("id", "message-0")
        try:
            mid = int(str(msg_id_attr).rsplit("-", 1)[-1])
        except ValueError:
            mid = 0
        author_div = item.find("div", class_="media-user-name")
        if author_div:
            link = author_div.find("a")
            if link and link.get("href"):
                href = link["href"].rstrip("/")
                try:
                    last_author_id = int(href.rsplit("/", 1)[-1])
                except ValueError:
                    last_author_id = 0
            last_author_name = (link.text.strip() if link else None) or last_author_name

        text_node = item.find("div", class_="chat-msg-text")
        image_link_node = item.find("a", class_="chat-img-link")
        image_url = image_link_node.get("href") if image_link_node else None
        text = text_node.text.strip() if text_node else None
        messages.append(
            Message(
                id=mid,
                author_id=last_author_id,
                author_name=last_author_name,
                text=text,
                image_url=image_url,
                raw_html=str(item),
            )
        )
    return messages


def parse_my_lots(html: str, subcategory_id: int) -> list[MyLot]:
    """Parse `/lots/{id}/trade` — seller's own lots in a subcategory."""
    soup = BeautifulSoup(html, "lxml")
    offers = soup.find_all("a", class_="tc-item")
    lots: list[MyLot] = []
    for offer in offers:
        offer_id = offer.get("data-offer")
        if not offer_id:
            continue
        desc = offer.find("div", class_="tc-desc-text")
        server = offer.find("div", class_="tc-server")
        side = offer.find("div", class_="tc-side")
        amount_node = offer.find("div", class_="tc-amount")
        price_node = offer.find("div", class_="tc-price")
        currency_node = price_node.find("span", class_="unit") if price_node else None

        amount: int | None = None
        if amount_node:
            cleaned = amount_node.text.strip().replace("\xa0", "").replace(" ", "")
            if cleaned.isdigit():
                amount = int(cleaned)

        price = 0.0
        if price_node and price_node.get("data-s"):
            try:
                price = float(price_node["data-s"])
            except ValueError:
                price = 0.0

        auto = bool(price_node and price_node.find("i", class_="auto-dlv-icon"))
        active = "warning" not in offer.get("class", [])
        lots.append(
            MyLot(
                id=str(offer_id),
                description=desc.text.strip() if desc else None,
                server=server.text.strip() if server else None,
                side=side.text.strip() if side else None,
                amount=amount,
                price=price,
                currency=currency_node.text.strip() if currency_node else None,
                auto=auto,
                active=active,
            )
        )
    _ = subcategory_id  # kept for future filtering; no-op for now
    return lots


def parse_lot_form(html: str) -> LotFields:
    """Parse the offer-edit form into a flat field map (ready for offerSave).

    Tested for both ``/lots/offerEdit?offer=ID`` (existing lot) and similar
    "create new" forms returned by FunPay.
    """
    soup = BeautifulSoup(html, "lxml")
    form = soup.find("form", class_="form-offer-editor")
    if not form:
        raise exceptions.FunPayError("offerEdit form not found in HTML response")

    fields: dict[str, str] = {}

    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name or name == "query":
            continue
        if inp.get("type") == "checkbox":
            if inp.has_attr("checked"):
                fields[name] = "on"
            continue
        fields[name] = inp.get("value") or ""

    for ta in form.find_all("textarea"):
        name = ta.get("name")
        if not name:
            continue
        fields[name] = ta.text or ""

    for select in form.find_all("select"):
        name = select.get("name")
        if not name:
            continue
        parent = select.find_parent(class_="form-group")
        if parent and "hidden" in parent.get("class", []):
            continue
        chosen = select.find("option", selected=True)
        if chosen and chosen.get("value") is not None:
            fields[name] = chosen["value"]

    raw_offer = form.get("data-offer")
    lot_id_int: int | None = None
    if isinstance(raw_offer, str) and raw_offer.strip():
        try:
            lot_id_int = int(json.loads(unescape(raw_offer)).get("offer"))
        except Exception:
            lot_id_int = None
    elif fields.get("offer_id"):
        try:
            lot_id_int = int(fields["offer_id"])
        except ValueError:
            lot_id_int = None

    sub_id_raw = fields.get("node_id")
    if not sub_id_raw:
        raise exceptions.FunPayError("node_id (subcategory) missing in offerEdit form")
    return LotFields(
        lot_id=lot_id_int,
        subcategory_id=int(sub_id_raw),
        fields=fields,
    )


def parse_csrf(html: str) -> str | None:
    """Best-effort CSRF token extraction from a page's data-app-data."""
    match = re.search(r"data-app-data=['\"]([^'\"]+)['\"]", html)
    if not match:
        return None
    try:
        data = json.loads(unescape(match.group(1)))
    except Exception:
        return None
    token = data.get("csrf-token")
    return str(token) if token else None


def maybe_login_redirect(form: Tag | None) -> bool:
    """Return True if a parsed page is the FunPay login form (cookie expired)."""
    return bool(form and form.get("action", "").endswith("account/login"))
