from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from emoji import GLOBE, ROCKET, INFO, SHIELD

router = Router()

TUTORIALS = {
    "happ": {
        "name": "Happ (iOS / Android)",
        "icon": "\U0001f4f1",
        "text": (
            "\U0001f4f1 <b>Happ — подключение VPN</b>\n\n"
            "<b>iOS:</b>\n"
            "1. Скачайте <b>Happ</b> из App Store\n"
            "2. Откройте приложение\n"
            "3. Нажмите \u2795 → <b>Добавить подписку</b>\n"
            "4. Вставьте ссылку подписки из бота\n"
            "5. Нажмите <b>Подключить</b>\n\n"
            "<b>Android:</b>\n"
            "1. Скачайте <b>Happ</b> или <b>v2rayNG</b> из Google Play\n"
            "2. Нажмите \u2795 → <b>Импорт из буфера</b>\n"
            "3. Вставьте ссылку подписки\n"
            "4. Выберите сервер и подключайтесь"
        )
    },
    "v2rayn": {
        "name": "v2rayN (Windows)",
        "icon": "\U0001f4bb",
        "text": (
            "\U0001f4bb <b>v2rayN — подключение на Windows</b>\n\n"
            "1. Скачайте <b>v2rayN</b>: github.com/2dust/v2rayN\n"
            "2. Распакуйте и запустите\n"
            "3. Правой кнопкой по иконке в трее\n"
            "4. <b>Подписка → Обновление подписки (URL)</b>\n"
            "5. Вставьте ссылку подписки из бота\n"
            "6. Выберите сервер → <b>Активировать</b>\n"
            "7. Включите системный прокси (Автоконфигурация)\n\n"
            "\u2705 Готово! VPN работает."
        )
    },
    "hiddify": {
        "name": "Hiddify (все платформы)",
        "icon": "\U0001f30d",
        "text": (
            "\U0001f30d <b>Hiddify — универсальный клиент</b>\n\n"
            "Работает на: Windows, macOS, Linux, Android, iOS\n\n"
            "1. Скачайте: hiddify.com\n"
            "2. Откройте приложение\n"
            "3. Нажмите \u2795 → <b>Добавить из буфера</b>\n"
            "4. Вставьте ссылку подписки из бота\n"
            "5. Серверы загрузятся автоматически\n"
            "6. Выберите сервер → Подключить\n\n"
            "\U0001f4a1 <b>Совет:</b> включите Smart Route для "
            "автоматического выбора лучшего сервера."
        )
    },
    "nekobox": {
        "name": "NekoBox (Android)",
        "icon": "\U0001f431",
        "text": (
            "\U0001f431 <b>NekoBox — Android</b>\n\n"
            "1. Скачайте <b>NekoBox</b> из GitHub или Google Play\n"
            "2. Откройте → Нажмите \u2795\n"
            "3. <b>Импорт из буфера обмена</b>\n"
            "4. Вставьте ссылку подписки\n"
            "5. Выберите сервер и подключайтесь\n\n"
            "\U0001f4a1 Поддерживает автообновление подписки."
        )
    }
}


def tutorials_kb() -> InlineKeyboardMarkup:
    buttons = []
    for key, t in TUTORIALS.items():
        buttons.append([InlineKeyboardButton(
            text=f"{t['icon']} {t['name']}", callback_data=f"tut:{key}"
        )])
    web_base = f"http://{config.WEBHOOK_BASE_URL}" if config.WEBHOOK_BASE_URL else ""
    if config.TUTORIAL_URL:
        buttons.append([InlineKeyboardButton(
            text=f"{INFO} Подробный гайд", url=config.TUTORIAL_URL
        )])
    elif web_base:
        buttons.append([InlineKeyboardButton(
            text=f"{INFO} Все инструкции на сайте", url=f"{web_base}/help/"
        )])
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "tutorials")
async def tutorials_menu(call: CallbackQuery):
    await call.message.edit_text(
        f"{GLOBE} <b>Туториалы по подключению</b>\n\n"
        f"Выберите ваше устройство / приложение:",
        parse_mode="HTML",
        reply_markup=tutorials_kb()
    )


@router.callback_query(F.data.startswith("tut:"))
async def tutorial_detail(call: CallbackQuery):
    key = call.data.split(":")[1]
    tut = TUTORIALS.get(key)
    if not tut:
        await call.answer("Не найдено")
        return

    await call.message.edit_text(
        tut["text"],
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u25c0\ufe0f Все туториалы", callback_data="tutorials")],
            [InlineKeyboardButton(text="\U0001f3e0 В меню", callback_data="main_menu")]
        ])
    )
