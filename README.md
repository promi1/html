# FunPay TG Bot

Личный Telegram-бот для управления вашим аккаунтом на [FunPay](https://funpay.com/):
переписка, создание лотов, AI-помощник для описаний, поддержка прокси.

> ⚠️ Бот не является официальным продуктом FunPay. Используйте на свой страх и риск
> и следите за условиями использования площадки.

## Возможности (MVP)

- 🔐 **Авторизация владельца:** только указанный `TELEGRAM_ADMIN_IDS` имеет доступ.
- 🌐 **Прокси:** пул HTTP/HTTPS/SOCKS5 прокси (датацентр / резидент), назначение и ротация.
- 💬 **Чаты:** список активных диалогов, история переписки, ответ текстом/фото
  прямо из Telegram.
- 🛒 **Создание лота:** поиск игры/приложения как на FunPay → выбор подкатегории
  (аккаунты / рефералы / подписки / прочее) → описание + детальное описание + фото →
  автозаполнение полей формы FunPay.
- 🤖 **AI-помощник:** одной кнопкой улучшает черновик описания через OpenAI
  (`gpt-4o-mini` по умолчанию).
- 📦 **Управление лотами:** просмотр своих активных лотов, включение/выключение,
  поднятие категории.

## Установка

Требуется **Python 3.11+**.

```bash
git clone https://github.com/promi1/html.git funpay-tg-bot
cd funpay-tg-bot

python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate

pip install -e .
cp .env.example .env
# Заполните .env (см. ниже)

funpay-tg-bot
```

## Заполнение `.env`

| Переменная | Где взять / пример |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Создайте бота у [@BotFather](https://t.me/BotFather), скопируйте токен. |
| `TELEGRAM_ADMIN_IDS` | Ваш числовой Telegram ID (узнать у [@userinfobot](https://t.me/userinfobot)). |
| `FUNPAY_GOLDEN_KEY` | Откройте `funpay.com` в браузере → DevTools → Application → Cookies → значение `golden_key`. |
| `FUNPAY_PROXY` | (опционально) `http://user:pass@host:port` или `socks5://user:pass@host:port`. |
| `OPENAI_API_KEY` | (опционально) для AI-кнопки. Получить на [platform.openai.com](https://platform.openai.com/api-keys). |

## Архитектура

```
src/funpay_tg/
├── main.py            # точка входа (asyncio + aiogram dispatcher)
├── config.py          # pydantic-settings: переменные окружения
├── db.py              # aiosqlite: прокси, шаблоны, кэш
├── ai.py              # OpenAI клиент (опционально)
├── funpay/
│   ├── client.py      # асинхронный httpx-клиент к funpay.com
│   ├── parsers.py     # lxml/bs4 парсинг страниц
│   ├── types.py       # dataclass-модели
│   ├── exceptions.py
│   └── proxies.py     # пул прокси / ротация
└── bot/
    ├── handlers/      # обработчики aiogram
    │   ├── start.py
    │   ├── settings.py
    │   ├── proxies.py
    │   ├── chats.py
    │   ├── lots.py
    │   └── sell.py    # FSM «продать лот»
    ├── keyboards.py
    ├── states.py      # aiogram FSM состояния
    └── middlewares.py # ACL: только админы
```

## Безопасность

- `golden_key` хранится только в `.env` локально. Никуда не отправляется кроме
  `funpay.com` (через ваш прокси, если задан).
- Бот принимает команды только от `TELEGRAM_ADMIN_IDS`.
- Никаких сторонних API не вызывается без вашего согласия.

## Дальнейшее развитие

После MVP планируется:

- Авто-выдача товаров (по триггеру нового заказа).
- Авто-поднятие лотов по расписанию.
- Автоответы (триггеры на текст сообщения).
- Интеграции с сервисами накрутки / перепродажи (по запросу).
- Web-панель управления (FastAPI + React).

## Лицензия

MIT.
