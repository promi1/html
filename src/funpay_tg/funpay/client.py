"""Asynchronous FunPay client built on top of httpx."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import string
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx

from . import exceptions, parsers
from .proxies import build_async_client
from .types import (
    Account,
    Category,
    ChatPreview,
    LotFields,
    Message,
    MyLot,
    SubCategoryType,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://funpay.com"
_LOGIN_PATH = "/account/login"


class FunPayClient:
    """High-level async client for the FunPay seller API.

    Authenticates via the ``golden_key`` cookie. Reads pages via httpx, parses
    HTML with bs4/lxml, and posts form-encoded payloads to the JSON endpoints
    used by the public FunPay UI.

    Use as an async context manager::

        async with FunPayClient(golden_key="...", user_agent=UA) as fp:
            account = await fp.bootstrap()
            chats = await fp.get_chat_previews()
    """

    def __init__(
        self,
        *,
        golden_key: str,
        user_agent: str,
        proxy: str | None = None,
    ):
        self._golden_key = golden_key
        self._user_agent = user_agent
        self._proxy = proxy
        self._client: httpx.AsyncClient | None = None
        self._account: Account | None = None
        self._categories: list[Category] = []
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> FunPayClient:
        self._client = build_async_client(self._proxy, user_agent=self._user_agent)
        self._client.cookies.set("golden_key", self._golden_key, domain="funpay.com")
        self._client.cookies.set("locale", "ru", domain="funpay.com")
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def account(self) -> Account:
        if self._account is None:
            raise exceptions.FunPayError("FunPayClient is not bootstrapped — call bootstrap() first")
        return self._account

    @property
    def categories(self) -> list[Category]:
        return list(self._categories)

    # -------------------------------------------------------------------------
    # Low-level HTTP wrapper
    # -------------------------------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: Any | None = None,
        files: Any | None = None,
        headers: dict[str, str] | None = None,
        max_redirects: int = 5,
    ) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("FunPayClient must be used as async context manager")

        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        merged_headers = {"Accept": "*/*"}
        if headers:
            merged_headers.update(headers)

        response: httpx.Response | None = None
        for _ in range(max_redirects + 1):
            response = await self._client.request(
                method, url, data=data, files=files, headers=merged_headers
            )
            if 300 <= response.status_code < 400 and "Location" in response.headers:
                location = response.headers["Location"]
                if location.endswith(_LOGIN_PATH):
                    raise exceptions.UnauthorizedError(
                        "FunPay redirected to /account/login (golden_key invalid?)"
                    )
                url = location if location.startswith("http") else f"{BASE_URL}{location}"
                continue
            break
        else:  # pragma: no cover — too many redirects
            raise exceptions.RequestFailedError(
                response.status_code if response else 0, "Too many redirects"
            )

        assert response is not None
        if response.status_code == 403:
            raise exceptions.UnauthorizedError("FunPay returned 403 (banned / rate-limited?)")
        if response.status_code >= 500:
            raise exceptions.RequestFailedError(response.status_code, response.text[:300])
        return response

    # -------------------------------------------------------------------------
    # Bootstrap / categories
    # -------------------------------------------------------------------------
    async def bootstrap(self) -> Account:
        """Fetch the home page, populate user info and category listings."""
        async with self._lock:
            response = await self._request("GET", "/")
            html = response.text
            account, categories = parsers.parse_account(html)
            phpsessid = response.cookies.get("PHPSESSID")
            if phpsessid:
                account.phpsessid = phpsessid
            self._account = account
            self._categories = categories
            return account

    def search_categories(self, query: str) -> list[Category]:
        """Filter the in-memory categories list by name (case-insensitive)."""
        q = query.strip().lower()
        if not q:
            return list(self._categories)
        return [c for c in self._categories if q in c.name.lower()]

    def get_category(self, category_id: int) -> Category | None:
        for c in self._categories:
            if c.id == category_id:
                return c
        return None

    # -------------------------------------------------------------------------
    # Chats
    # -------------------------------------------------------------------------
    async def get_chat_previews(self) -> list[ChatPreview]:
        """Return a list of recent chats from the chat panel."""
        response = await self._request("GET", "/chat/")
        return parsers.parse_chat_previews(response.text)

    async def get_chat_history(
        self, chat_id: int, last_message_id: int | None = None
    ) -> list[Message]:
        """Fetch message history for a private chat.

        ``last_message_id`` may be passed to anchor the "context" — leaving it
        as ``None`` requests the latest full history.
        """
        last = last_message_id if last_message_id is not None else 99999999999
        response = await self._request(
            "GET",
            f"/chat/history?node={chat_id}&last_message={last}",
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        try:
            data = response.json()
        except json.JSONDecodeError:
            return parsers.parse_chat_history(response.text)
        chat_html = data.get("chat", {}).get("html", "") if isinstance(data, dict) else ""
        return parsers.parse_chat_history(chat_html)

    async def send_message(self, chat_id: int, text: str) -> dict[str, Any]:
        """Send a plain-text message to a private chat."""
        request_obj = {
            "action": "chat_message",
            "data": {"node": chat_id, "last_message": -1, "content": text},
        }
        return await self._runner_post(request_obj)

    async def send_image(self, chat_id: int, file_path: str | Path) -> dict[str, Any]:
        """Upload an image and immediately attach it to a chat message."""
        image_id = await self.upload_image(file_path)
        request_obj = {
            "action": "chat_message",
            "data": {
                "node": chat_id,
                "last_message": -1,
                "content": "",
                "image_id": image_id,
            },
        }
        return await self._runner_post(request_obj)

    async def upload_image(self, file_path: str | Path) -> int:
        """Upload an image to FunPay and return its ``fileId``."""
        path = Path(file_path)
        data = await asyncio.to_thread(path.read_bytes)
        boundary = "----WebKitFormBoundary" + "".join(
            random.sample(string.ascii_letters + string.digits, 16)
        )
        files = {
            "file": ("upload.png", BytesIO(data), "image/png"),
            "file_id": (None, "0"),
        }
        headers = {
            "x-requested-with": "XMLHttpRequest",
            "Accept": "*/*",
        }
        response = await self._request(
            "POST", "/file/addChatImage", files=files, headers=headers
        )
        if response.status_code != 200:
            raise exceptions.ImageUploadError(
                f"Upload failed: HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise exceptions.ImageUploadError(f"Upload returned non-JSON: {response.text[:200]}") from exc
        file_id = payload.get("fileId")
        if not file_id:
            raise exceptions.ImageUploadError(f"Upload missing fileId in response: {payload}")
        # boundary kept for parity with FunPay's expected multipart shape
        _ = boundary
        return int(file_id)

    async def _runner_post(self, request_obj: dict[str, Any]) -> dict[str, Any]:
        if self._account is None:
            raise exceptions.FunPayError("Not bootstrapped — call bootstrap() first")
        payload = {
            "objects": "[]",
            "request": json.dumps(request_obj, ensure_ascii=False),
            "csrf_token": self._account.csrf_token,
        }
        headers = {
            "x-requested-with": "XMLHttpRequest",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        response = await self._request("POST", "/runner/", data=payload, headers=headers)
        if response.status_code != 200:
            raise exceptions.RequestFailedError(response.status_code, response.text[:200])
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise exceptions.FunPayError(f"runner returned non-JSON: {response.text[:200]}") from exc
        resp = data.get("response") or {}
        if isinstance(resp, dict) and resp.get("error"):
            raise exceptions.MessageNotDeliveredError(
                request_obj.get("data", {}).get("node", "?"), str(resp.get("error"))
            )
        return data

    # -------------------------------------------------------------------------
    # Lots
    # -------------------------------------------------------------------------
    async def get_my_lots(self, subcategory_id: int) -> list[MyLot]:
        response = await self._request("GET", f"/lots/{subcategory_id}/trade")
        return parsers.parse_my_lots(response.text, subcategory_id)

    async def get_lot_form(
        self, *, lot_id: int | None = None, subcategory_id: int | None = None
    ) -> LotFields:
        """Fetch the offer-edit form for an existing lot or a fresh subcategory."""
        if lot_id is not None:
            path = f"/lots/offerEdit?offer={lot_id}"
        elif subcategory_id is not None:
            path = f"/lots/offerEdit?node={subcategory_id}"
        else:
            raise ValueError("Either lot_id or subcategory_id is required")
        response = await self._request("GET", path)
        form = parsers.parse_lot_form(response.text)
        token = parsers.parse_csrf(response.text)
        if token and self._account is not None:
            self._account.csrf_token = token
        return form

    async def save_lot(self, fields: LotFields) -> dict[str, Any]:
        """Send a filled-in offer form to ``/lots/offerSave``."""
        if self._account is None:
            raise exceptions.FunPayError("Not bootstrapped — call bootstrap() first")
        payload = dict(fields.fields)
        payload["csrf_token"] = self._account.csrf_token
        if fields.lot_id is not None:
            payload.setdefault("offer_id", str(fields.lot_id))
        headers = {
            "x-requested-with": "XMLHttpRequest",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        response = await self._request("POST", "/lots/offerSave", data=payload, headers=headers)
        if response.status_code != 200:
            raise exceptions.LotSavingError(f"HTTP {response.status_code}: {response.text[:200]}")
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise exceptions.LotSavingError(
                f"offerSave returned non-JSON: {response.text[:200]}"
            ) from exc
        if data.get("error") or data.get("errors"):
            errors_dict: dict[str, str] = {}
            errs = data.get("errors") or []
            if isinstance(errs, list):
                for pair in errs:
                    if isinstance(pair, list) and len(pair) == 2:
                        errors_dict[str(pair[0])] = str(pair[1])
            elif isinstance(errs, dict):
                errors_dict = {str(k): str(v) for k, v in errs.items()}
            raise exceptions.LotSavingError(
                str(data.get("error") or "validation"), errors_dict
            )
        return data

    async def raise_lots(self, category_id: int) -> bool:
        """Bump all subcategories of a category. Returns True on success."""
        if self._account is None:
            raise exceptions.FunPayError("Not bootstrapped — call bootstrap() first")
        category = self.get_category(category_id)
        if category is None or not category.subcategories:
            raise exceptions.CategoryNotFoundError(f"Category {category_id} not loaded")
        common_subs = [s for s in category.subcategories if s.type == SubCategoryType.COMMON]
        if not common_subs:
            return False
        payload: dict[str, Any] = {
            "game_id": category_id,
            "node_id": common_subs[0].id,
            "node_ids[]": [s.id for s in common_subs],
        }
        headers = {
            "x-requested-with": "XMLHttpRequest",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        response = await self._request("POST", "/lots/raise", data=payload, headers=headers)
        try:
            data = response.json()
        except json.JSONDecodeError:
            return False
        return not data.get("error")
