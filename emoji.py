def e(emoji_id: str, fallback: str = "") -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

BUTTERFLY   = e("5228718354658769982", "\U0001f98b")
BUBBLE      = e("5395749499656224269", "\U0001f4ac")
BLUE_DOT    = e("5819147036393475340", "\U0001f535")
CHECK       = e("5818804224988811039", "\u2714\ufe0f")
CROSS       = e("5206607081334906820", "\u274c")
MONEY       = e("5210952531676504517", "\U0001f4b8")
MESSAGE     = e("5231449120635370684", "\U0001f4ac")
SETTINGS    = e("5443038326535759644", "\u2699\ufe0f")
WARNING     = e("5341715473882955310", "\u26a0\ufe0f")
BELL        = e("5447644880824181073", "\U0001f514")
PLUS        = e("5458603043203327669", "\u2795")
ARROW_UP    = e("5397916757333654639", "\U0001f53c")
USDT        = e("5449683594425410231", "\U0001f4b2")
FIRE        = e("5366166396281572000", "\U0001f525")
DOLPHIN     = e("5357482496395067996", "\U0001f42c")
GOLD        = e("5318818633860794283", "\U0001f947")
LOLZ        = e("5363999258863223279", "\U0001f4b1")
STOP        = e("5433903218859981178", "\u26d4\ufe0f")
INFO        = e("5458603043203327669", "\u2139\ufe0f")
STATS       = e("5334544901428229844", "\U0001f4ca")
GLOBE       = e("5368324170671202286", "\U0001f310")
SHIELD      = e("5413879163845018757", "\U0001f6e1\ufe0f")
KEY         = e("5368536706236995043", "\U0001f511")
ROCKET      = e("5391197475513433461", "\U0001f680")
LOCK        = e("5377747904037029653", "\U0001f512")

# Country flag fallbacks
FLAGS = {
    "RU": "\U0001f1f7\U0001f1fa",
    "NL": "\U0001f1f3\U0001f1f1",
    "DE": "\U0001f1e9\U0001f1ea",
    "PL": "\U0001f1f5\U0001f1f1",
    "US": "\U0001f1fa\U0001f1f8",
    "GB": "\U0001f1ec\U0001f1e7",
    "FR": "\U0001f1eb\U0001f1f7",
    "FI": "\U0001f1eb\U0001f1ee",
    "SE": "\U0001f1f8\U0001f1ea",
    "KZ": "\U0001f1f0\U0001f1ff",
    "TR": "\U0001f1f9\U0001f1f7",
    "LU": "\U0001f1f1\U0001f1fa",
    "JP": "\U0001f1ef\U0001f1f5",
    "SG": "\U0001f1f8\U0001f1ec",
    "CA": "\U0001f1e8\U0001f1e6",
    "AU": "\U0001f1e6\U0001f1fa",
    "UA": "\U0001f1fa\U0001f1e6",
    "CZ": "\U0001f1e8\U0001f1ff",
    "AT": "\U0001f1e6\U0001f1f9",
    "CH": "\U0001f1e8\U0001f1ed",
    "LT": "\U0001f1f1\U0001f1f9",
    "LV": "\U0001f1f1\U0001f1fb",
    "EE": "\U0001f1ea\U0001f1ea",
    "RO": "\U0001f1f7\U0001f1f4",
    "BG": "\U0001f1e7\U0001f1ec",
    "MD": "\U0001f1f2\U0001f1e9",
}

def flag(country_code: str) -> str:
    return FLAGS.get(country_code.upper(), "\U0001f3f3\ufe0f")
