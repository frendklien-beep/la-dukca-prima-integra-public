from datetime import datetime
from zoneinfo import ZoneInfo

MAKASSAR = ZoneInfo("Asia/Makassar")


def greeting_for_hour(hour: int) -> str:
    if 5 <= hour <= 10:
        return "Selamat pagi."
    if 11 <= hour <= 14:
        return "Selamat siang."
    if 15 <= hour <= 17:
        return "Selamat sore."
    return "Selamat malam."


def greeting_for(now_utc: datetime) -> str:
    return greeting_for_hour(now_utc.astimezone(MAKASSAR).hour)
