BUTTERFLY   = "\U0001f98b"
BUBBLE      = "\U0001f4ac"
BLUE_DOT    = "\U0001f535"
CHECK       = "\u2714\ufe0f"
CROSS       = "\u274c"
MONEY       = "\U0001f4b8"
MESSAGE     = "\U0001f4ac"
SETTINGS    = "\u2699\ufe0f"
WARNING     = "\u26a0\ufe0f"
BELL        = "\U0001f514"
PLUS        = "\u2795"
ARROW_UP    = "\U0001f53c"
USDT        = "\U0001f4b2"
FIRE        = "\U0001f525"
DOLPHIN     = "\U0001f42c"
GOLD        = "\U0001f947"
LOLZ        = "\U0001f4b1"
STOP        = "\u26d4\ufe0f"
INFO        = "\u2139\ufe0f"
STATS       = "\U0001f4ca"
GLOBE       = "\U0001f310"
SHIELD      = "\U0001f6e1\ufe0f"
KEY         = "\U0001f511"
ROCKET      = "\U0001f680"
LOCK        = "\U0001f512"

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
