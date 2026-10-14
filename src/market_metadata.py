EXCHANGE_CURRENCIES = {
    "AT": "AUD",
    "FH": "EUR",
    "FP": "EUR",
    "GR": "EUR",
    "GY": "EUR",
    "HK": "HKD",
    "JT": "JPY",
    "KP": "KRW",
    "KQ": "KRW",
    "UN": "USD",
    "UQ": "USD",
    "UR": "USD",
    "US": "USD",
    "UW": "USD",
    "UF": "USD",
}


def bloomberg_exchange(identifier: str) -> str | None:
    parts = str(identifier).strip().split()
    if len(parts) < 2:
        return None
    return parts[-2] if parts[-1].lower() == "equity" else parts[-1]


def infer_currency(identifier: str) -> str | None:
    exchange = bloomberg_exchange(identifier)
    return EXCHANGE_CURRENCIES.get(exchange)
