#!/usr/bin/env python3
"""
Daily Weather Agent for Kids
Fetches weather from Open-Meteo (primary) + NOAA (fallback/enrichment) for
Watertown MA & Naples ME, generates a colorful kid-friendly HTML page, and
optionally pushes it to GitHub Pages.

Push model
----------
By default this script ONLY writes the HTML file (OUTPUT_PATH). Pushing is left
to the CI workflow (git commit + push), which avoids the double-commit race the
old setup had. To push directly via the GitHub Contents API (handy for local
runs), set PUSH_VIA_API=1 and provide a token in GITHUB_TOKEN.

Environment variables
---------------------
  OUTPUT_PATH   where to write the HTML (default: index.html)
  PUSH_VIA_API  "1"/"true" to push via the GitHub API from this script
  GITHUB_TOKEN  token used only when PUSH_VIA_API is set
"""

import urllib.request
import urllib.error
import json
import random
import base64
import os
import sys
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# ─── Configuration ──────────────────────────────────────────────────────────

LOCATIONS = [
    {"name": "Watertown", "state": "MA", "lat": 42.3709, "lon": -71.1828, "emoji": "🏙️"},
    {"name": "Naples", "state": "ME", "lat": 43.9590, "lon": -70.5878, "emoji": "🌲"},
]

GITHUB_OWNER = "sam-melnick"
GITHUB_REPO = "Weather"
GITHUB_FILE = "index.html"

# Wind speed (mph) at/above which we call it out to kids.
WIND_ALERT_MPH = 20

FUN_FACTS = [
    # Weather + Minecraft mashups
    "In Minecraft, it snows in cold biomes. In real life, snow only forms when clouds are below 32°F! ❄️",
    "Minecraft rain makes crops grow faster. Real rain helps gardens grow too! 🌧️",
    "Lightning in Minecraft can turn pigs into Zombie Pigmen. Real lightning is 5 times hotter than the sun! ⚡",
    "Minecraft has 3 weather types: clear, rain, and thunder. Earth has over 100 types of clouds! ☁️",
    "In Minecraft, you can sleep through storms. Real thunderstorms can last for hours! ⛈️",
    "Tridents in Minecraft work with lightning. Real lightning hits Earth about 100 times every second! ⚡",
    "Snow golems melt in hot biomes. Real snowmen melt when it gets above 32°F! ☃️",
    # Truck + weather facts
    "Garbage trucks have to work in ALL weather! Rain, snow, or sun. Those drivers are tough! 🚛",
    "Fire trucks carry 500 gallons of water. That is heavier than a grand piano! 🚒",
    "Fire trucks can pump water even when it is super cold outside. They have special heaters! 🚒",
    "Garbage trucks have big wipers to see in the rain. Some wipers are 2 feet long! 🚛",
    "Fire trucks go slower in the snow to stay safe. Even heroes have to be careful on ice! 🚒❄️",
    # Pure weather facts (simple words)
    "Snowflakes always have 6 sides. But no two look the same! ❄️",
    "It can rain frogs and fish! Big winds pick them up and drop them far away. 🐸",
    "Fog is just a cloud that sits on the ground! 🌫️",
    "A rainbow is a full circle. You can only see half from the ground! 🌈",
    "Clouds look light but one cloud can weigh as much as 100 elephants! ☁️",
    "Dogs can smell a storm before it gets here! 🐕",
    "Hailstones can be as big as a baseball! 🧊",
    "The fastest wind ever was 253 miles per hour. That is faster than a race car! 🌪️",
    "Rain has a special smell. It is called petrichor. Cool word, right? 🌿",
    "A dust devil is a tiny tornado made of dust and hot air! 🌀",
]

# ─── Weather API Helpers ────────────────────────────────────────────────────

def fetch_json(url, headers=None, retries=3, retry_delay=5):
    """Fetch a URL and return parsed JSON. Retries on 5xx errors and timeouts."""
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "WeatherAgentForKids/1.0 (samelnick@gmail.com)")
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code >= 500 and attempt < retries:
                print(f"  ⚠ Attempt {attempt}/{retries} got HTTP {e.code} for {url} — retrying in {retry_delay}s...", file=sys.stderr)
                time.sleep(retry_delay)
                continue
            print(f"  ⚠ Failed to fetch {url}: HTTP {e.code}", file=sys.stderr)
            return None
        except Exception as e:
            if attempt < retries:
                print(f"  ⚠ Attempt {attempt}/{retries} failed for {url}: {e} — retrying in {retry_delay}s...", file=sys.stderr)
                time.sleep(retry_delay)
                continue
            print(f"  ⚠ Failed to fetch {url} after {retries} attempts: {e}", file=sys.stderr)
            return None


def fetch_open_meteo(lat, lon):
    """
    Fetch hourly + daily forecast from Open-Meteo.
    Falls back to a request without precipitation_probability if the full
    request fails (known issue: open-meteo/open-meteo#1801).
    """
    base = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    tail = "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=America%2FNew_York&forecast_days=7"
    params_full = (
        "&current=temperature_2m,weather_code,wind_speed_10m"
        "&hourly=temperature_2m,precipitation_probability,weather_code,wind_speed_10m,precipitation,snowfall"
        "&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max,precipitation_sum,snowfall_sum,wind_speed_10m_max,sunrise,sunset"
    ) + tail
    params_fallback = (
        "&current=temperature_2m,weather_code,wind_speed_10m"
        "&hourly=temperature_2m,weather_code,wind_speed_10m,precipitation,snowfall"
        "&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum,snowfall_sum,wind_speed_10m_max,sunrise,sunset"
    ) + tail

    print("  Fetching Open-Meteo...", file=sys.stderr)
    result = fetch_json(base + params_full)
    if result:
        return result

    print("  ⚠ Full request failed — retrying without precipitation_probability...", file=sys.stderr)
    result = fetch_json(base + params_fallback)
    if result:
        print("  ✅ Fallback succeeded (no precip probability data).", file=sys.stderr)
    return result


def fetch_noaa_forecast(lat, lon):
    """Fetch forecast from NOAA. Two-step: grid point, then hourly + daily."""
    print("  Fetching NOAA grid point...", file=sys.stderr)
    points = fetch_json(f"https://api.weather.gov/points/{lat},{lon}")
    if not points:
        return None, None

    props = points.get("properties", {})
    hourly_url = props.get("forecastHourly")
    daily_url = props.get("forecast")

    hourly = None
    daily = None
    if hourly_url:
        print("  Fetching NOAA hourly...", file=sys.stderr)
        hourly = fetch_json(hourly_url)
    if daily_url:
        print("  Fetching NOAA daily...", file=sys.stderr)
        daily = fetch_json(daily_url)

    return hourly, daily


# ─── Weather Code → Description/Icon Mapping ────────────────────────────────

# Single source of truth for WMO code → (kid description, emoji).
# Used for the server-rendered page AND injected into the client-side JS,
# so the two can never drift apart.
WMO_CODES = {
    0: ("Sunny!", "☀️"),
    1: ("Mostly sunny", "🌤️"),
    2: ("Some clouds", "⛅"),
    3: ("Cloudy", "☁️"),
    45: ("Foggy", "🌫️"),
    48: ("Foggy", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Drizzle", "🌦️"),
    55: ("Lots of drizzle", "🌧️"),
    61: ("A little rain", "🌦️"),
    63: ("Rainy", "🌧️"),
    65: ("Big rain!", "🌧️"),
    66: ("Icy rain", "🧊🌧️"),
    67: ("Lots of icy rain!", "🧊🌧️"),
    71: ("Light snow", "🌨️"),
    73: ("Snowy!", "❄️"),
    75: ("Big snow!", "❄️❄️"),
    77: ("Snow bits", "❄️"),
    80: ("Some showers", "🌦️"),
    81: ("Showers", "🌧️"),
    82: ("Big showers!", "⛈️"),
    85: ("Light snow showers", "🌨️"),
    86: ("Big snow showers!", "❄️❄️"),
    95: ("Thunderstorm!", "⛈️"),
    96: ("Thunder + hail!", "⛈️🧊"),
    99: ("Big thunder + hail!", "⛈️🧊"),
}


def wmo_desc(code):
    return WMO_CODES.get(code, ("Unknown", "🌡️"))


def noaa_short_to_code(short):
    """
    Map a NOAA 'shortForecast' string to the closest WMO code, so NOAA data
    produces correct icons instead of everything defaulting to 'Sunny!'.
    Order matters: most severe / most specific first.
    """
    if not short:
        return 0
    s = short.lower()
    # Thunder / hail
    if "hail" in s and "thunder" in s:
        return 96
    if "thunder" in s or "t-storm" in s or "tstorm" in s:
        return 95
    # Freezing / ice
    if "ice" in s or "freezing" in s or "sleet" in s or "wintry mix" in s:
        return 66
    # Snow
    if "snow" in s or "flurr" in s or "blizzard" in s:
        if any(w in s for w in ["heavy", "lots", "blizzard"]):
            return 75
        if "light" in s or "flurr" in s or "chance" in s:
            return 71
        return 73
    # Rain / showers / drizzle
    if "drizzle" in s:
        return 53
    if "shower" in s:
        return 80
    if "rain" in s:
        if "heavy" in s:
            return 65
        if "light" in s or "chance" in s or "slight" in s:
            return 61
        return 63
    # Fog
    if "fog" in s or "haze" in s:
        return 45
    # Clouds
    if "mostly cloudy" in s or "overcast" in s:
        return 3
    if "partly" in s or "few clouds" in s or "mostly sunny" in s:
        return 2
    if "cloud" in s:
        return 3
    # Clear
    if "sunny" in s or "clear" in s or "fair" in s:
        return 0
    return 0


# ─── Data Processing ─────────────────────────────────────────────────────────

def format_precip(inches, precip_type="rain"):
    """Format precipitation in kid-friendly words. Uses feet for 12+ inches."""
    if inches <= 0:
        return ""
    if inches >= 12:
        feet = round(inches / 12, 1)
        if feet == int(feet):
            feet = int(feet)
        unit = "foot" if feet == 1 else "feet"
        return f"{feet} {unit} of {precip_type}"
    unit = "inch" if inches == 1 else "inches"
    return f"{inches} {unit} of {precip_type}"


def format_precip_short(inches, precip_type="rain"):
    """Shorter format for 7-day badges."""
    if inches <= 0:
        return ""
    if inches >= 12:
        feet = round(inches / 12, 1)
        if feet == int(feet):
            feet = int(feet)
        return f"{feet} ft"
    return f"{inches} in"


def _most_common(codes):
    """Return the most frequent weather code (ties: first seen). 0 if empty."""
    if not codes:
        return 0
    return Counter(codes).most_common(1)[0][0]


def _weather_flags(codes):
    """Given weather codes, return (rain, snow, storm) booleans."""
    rain = snow = storm = False
    for c in codes:
        dl = wmo_desc(c)[0].lower()
        if any(w in dl for w in ["rain", "drizzle", "shower"]):
            rain = True
        if any(w in dl for w in ["snow", "freezing", "icy"]):
            snow = True
        if "thunder" in dl:
            storm = True
    return rain, snow, storm


def get_outfit_suggestion(temp_f, lunch_code, day_codes=None, month=None):
    """
    Kid-friendly outfit suggestion.

    Temperature is anchored to lunchtime/recess (temp_f). Rain/snow/storm advice
    looks at the WHOLE day (day_codes) so morning-commute weather is covered.
    Temperature bands are tuned for a kid who runs cold (warmer layers ~5°F
    sooner than a neutral scale).
    """
    # Whole-day precip flags; fall back to the lunchtime code if no day data.
    rain, snow, storm = _weather_flags(day_codes if day_codes else [lunch_code])
    lunch_dl = wmo_desc(lunch_code)[0].lower()
    sunny = any(w in lunch_dl for w in ["sunny", "clear"])

    if month is None:
        month = datetime.now(ET).month
    sunscreen_season = 4 <= month <= 10

    suggestions = []

    # "Runs cold" bands: cut points shifted up ~5°F vs a neutral scale.
    if temp_f <= 25:
        suggestions.append("🧥 SUPER cold! Wear your big coat, snow pants, hat, gloves, and boots!")
    elif temp_f <= 37:
        suggestions.append("🧥 Freezing out! Wear your winter coat, hat, and gloves!")
    elif temp_f <= 50:
        suggestions.append("🧶 Chilly! Wear a warm jacket. A hat is a good idea too!")
    elif temp_f <= 60:
        suggestions.append("🧥 A bit cool. A hoodie or medium jacket is perfect!")
    elif temp_f <= 70:
        suggestions.append("👕 Nice out! Long sleeves or a light jacket!")
    elif temp_f <= 80:
        suggestions.append("😎 T-shirt weather! Feels great outside!")
    elif temp_f <= 90:
        suggestions.append("🩳 Shorts and t-shirt day!")
    else:
        suggestions.append("🥵 SO hot! Wear light clothes. Drink lots of water!")

    if rain:
        suggestions.append("☔ Bring your rain jacket and rain boots!")
    if snow:
        suggestions.append("🥾 Snow boots and snow gear today!")
    if storm:
        suggestions.append("⚡ Thunderstorms! Stay inside when you hear thunder!")

    if sunny and not rain and not snow:
        suggestions.append("🕶️ Wear your sunglasses!")
        if sunscreen_season:
            suggestions.append("🧴 Put on sunscreen before you go out!")

    return " ".join(suggestions)


# ─── Fun-fact selection (day-stable + weather-matched) ───────────────────────

def _day_theme(locations_data):
    """Pick a weather theme for the day from all locations' codes/temps."""
    codes = []
    highs, lows = [], []
    for li in locations_data:
        d = li.get("data")
        if not d:
            continue
        for p in d.get("periods", {}).values():
            codes.append(p.get("weather_code", 0))
        for h in d.get("hourly", []):
            codes.append(h.get("weather_code", 0))
        seven = d.get("seven_day", [])
        if seven:
            if seven[0].get("high") is not None:
                highs.append(seven[0]["high"])
            if seven[0].get("low") is not None:
                lows.append(seven[0]["low"])
    cs = set(codes)
    if cs & {71, 73, 75, 77, 85, 86}:
        return "snow"
    if cs & {95, 96, 99}:
        return "storm"
    if cs & {51, 53, 55, 61, 63, 65, 66, 67, 80, 81, 82}:
        return "rain"
    if highs and max(highs) >= 85:
        return "hot"
    if lows and min(lows) <= 25:
        return "cold"
    return None


def _theme_pool(theme):
    """Facts that fit a theme (by keyword). Empty list if none/unknown."""
    keywords = {
        "snow": ["snow", "❄", "☃", "hail", "🧊"],
        "storm": ["lightning", "thunder", "storm", "⚡", "⛈"],
        "rain": ["rain", "🌧", "drizzle", "petrichor", "frogs and fish"],
        "hot": ["hot", "sun", "☀", "dust devil", "wind"],
        "cold": ["snow", "cold", "❄", "☃"],
    }.get(theme, [])
    if not keywords:
        return []
    return [f for f in FUN_FACTS if any(k in f.lower() for k in keywords)]


def pick_fun_fact(locations_data, when):
    """
    Choose the 'Cool Fact of the Day'. Weather-matched when possible, and
    day-stable: seeded by the date so the morning and midday runs agree.
    """
    pool = _theme_pool(_day_theme(locations_data)) or FUN_FACTS
    rng = random.Random(when.strftime("%Y-%m-%d"))
    return rng.choice(pool)


def process_open_meteo(data):
    """Process Open-Meteo data into our standard format."""
    if not data:
        return None

    current = data.get("current", {})
    hourly = data.get("hourly", {})
    daily = data.get("daily", {})

    current_temp = current.get("temperature_2m")
    current_code = current.get("weather_code", 0)
    current_wind = current.get("wind_speed_10m")
    if current_temp is not None:
        current_temp = round(current_temp)
    if current_wind is not None:
        current_wind = round(current_wind)

    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    codes = hourly.get("weather_code", [])
    precip = hourly.get("precipitation_probability", [])
    winds = hourly.get("wind_speed_10m", [])
    rain_mm = hourly.get("precipitation", [])
    snow_cm = hourly.get("snowfall", [])

    now_est = datetime.now(ET)
    today_str = now_est.strftime("%Y-%m-%d")

    # Lunchtime temp (11:00 and 12:00 hours, averaged)
    lunch_temps = []
    lunch_codes = []
    for i, t in enumerate(times):
        if t.startswith(today_str) and ("T11:" in t or "T12:" in t):
            if i < len(temps):
                lunch_temps.append(temps[i])
            if i < len(codes):
                lunch_codes.append(codes[i])

    lunch_temp = round(sum(lunch_temps) / len(lunch_temps)) if lunch_temps else None
    lunch_code = lunch_codes[0] if lunch_codes else 0

    periods = {"morning": (6, 11), "afternoon": (12, 17), "evening": (18, 22)}
    period_data = {}

    for period_name, (start_h, end_h) in periods.items():
        p_temps, p_codes, p_precip, p_rain, p_snow = [], [], [], [], []
        for i, t in enumerate(times):
            if t.startswith(today_str):
                hour = int(t.split("T")[1].split(":")[0])
                if start_h <= hour <= end_h:
                    if i < len(temps):
                        p_temps.append(temps[i])
                    if i < len(codes):
                        p_codes.append(codes[i])
                    if i < len(precip):
                        p_precip.append(precip[i])
                    if i < len(rain_mm):
                        p_rain.append(rain_mm[i])
                    if i < len(snow_cm):
                        p_snow.append(snow_cm[i])

        if p_temps:
            total_rain_in = round(sum(p_rain) / 25.4, 1) if p_rain else 0
            total_snow_in = round(sum(p_snow) / 2.54, 1) if p_snow else 0
            period_data[period_name] = {
                "temp_high": round(max(p_temps)),
                "temp_low": round(min(p_temps)),
                # Most common condition in the block (not the worst hour), so a
                # single drizzly hour doesn't turn a sunny afternoon rainy.
                "weather_code": _most_common(p_codes),
                # Peak precip chance is still surfaced separately below.
                "precip_chance": max(p_precip) if p_precip else 0,
                "rain_inches": total_rain_in,
                "snow_inches": total_snow_in,
            }

    # Hourly forecast for today (6 AM to 10 PM)
    hourly_forecast = []
    for i, t in enumerate(times):
        if t.startswith(today_str):
            hour = int(t.split("T")[1].split(":")[0])
            if 6 <= hour <= 22:
                h_temp = round(temps[i]) if i < len(temps) else None
                h_code = codes[i] if i < len(codes) else 0
                h_precip = precip[i] if i < len(precip) else 0
                h_wind = round(winds[i]) if i < len(winds) else 0
                if h_temp is not None:
                    hourly_forecast.append({
                        "hour": hour,
                        "temp": h_temp,
                        "weather_code": h_code,
                        "precip_chance": h_precip,
                        "wind": h_wind,
                    })

    # 7-day forecast
    daily_dates = daily.get("time", [])
    daily_highs = daily.get("temperature_2m_max", [])
    daily_lows = daily.get("temperature_2m_min", [])
    daily_codes = daily.get("weather_code", [])
    daily_precip = daily.get("precipitation_probability_max", [])
    daily_rain_sum = daily.get("precipitation_sum", [])
    daily_snow_sum = daily.get("snowfall_sum", [])
    daily_wind_max = daily.get("wind_speed_10m_max", [])

    seven_day = []
    for i in range(min(7, len(daily_dates))):
        rain_in = round(daily_rain_sum[i] / 25.4, 1) if i < len(daily_rain_sum) and daily_rain_sum[i] else 0
        snow_in = round(daily_snow_sum[i] / 2.54, 1) if i < len(daily_snow_sum) and daily_snow_sum[i] else 0
        wind_max = round(daily_wind_max[i]) if i < len(daily_wind_max) and daily_wind_max[i] else 0
        seven_day.append({
            "date": daily_dates[i] if i < len(daily_dates) else "",
            "high": round(daily_highs[i]) if i < len(daily_highs) else None,
            "low": round(daily_lows[i]) if i < len(daily_lows) else None,
            "weather_code": daily_codes[i] if i < len(daily_codes) else 0,
            "precip_chance": daily_precip[i] if i < len(daily_precip) else 0,
            "rain_inches": rain_in,
            "snow_inches": snow_in,
            "wind_max": wind_max,
        })

    return {
        "source": "Open-Meteo",
        "current_temp": current_temp,
        "current_code": current_code,
        "current_wind": current_wind,
        "lunch_temp": lunch_temp,
        "lunch_code": lunch_code,
        "periods": period_data,
        "hourly": hourly_forecast,
        "seven_day": seven_day,
    }


def process_noaa(hourly_data, daily_data):
    """
    Process NOAA data into our standard format.

    Unlike the old version, this now (a) derives a WMO weather code from NOAA's
    shortForecast text so icons are correct, and (b) populates the hourly
    timeline, so NOAA can stand on its own if Open-Meteo is down.
    """
    if not hourly_data and not daily_data:
        return None

    now_est = datetime.now(ET)
    today_str = now_est.strftime("%Y-%m-%d")

    result = {
        "source": "NOAA",
        "current_temp": None,
        "current_code": 0,
        "current_wind": None,
        "lunch_temp": None,
        "lunch_code": 0,
        "periods": {},
        "hourly": [],
        "seven_day": [],
    }

    if hourly_data:
        periods_list = hourly_data.get("properties", {}).get("periods", [])
        lunch_temps, lunch_codes = [], []
        # period_name -> {"temps": [], "codes": [], "precip": [], "wind": []}
        bins = {p: {"temps": [], "codes": [], "precip": [], "wind": []}
                for p in ("morning", "afternoon", "evening")}
        current_hour = now_est.hour

        for p in periods_list:
            start = p.get("startTime", "")
            if not start.startswith(today_str):
                continue

            hour = int(start.split("T")[1].split(":")[0])
            temp = p.get("temperature")
            code = noaa_short_to_code(p.get("shortForecast", ""))
            pop = (p.get("probabilityOfPrecipitation") or {}).get("value") or 0
            wind = _parse_wind_mph(p.get("windSpeed", ""))

            if hour == current_hour and result["current_temp"] is None:
                result["current_temp"] = temp
                result["current_code"] = code
                result["current_wind"] = wind

            if 6 <= hour <= 22 and temp is not None:
                result["hourly"].append({
                    "hour": hour, "temp": temp, "weather_code": code,
                    "precip_chance": pop, "wind": wind,
                })

            if 11 <= hour <= 12:
                lunch_temps.append(temp)
                lunch_codes.append(code)

            if 6 <= hour <= 11:
                b = bins["morning"]
            elif 12 <= hour <= 17:
                b = bins["afternoon"]
            elif 18 <= hour <= 22:
                b = bins["evening"]
            else:
                b = None
            if b is not None and temp is not None:
                b["temps"].append(temp)
                b["codes"].append(code)
                b["precip"].append(pop)
                b["wind"].append(wind)

        if lunch_temps:
            result["lunch_temp"] = round(sum(lunch_temps) / len(lunch_temps))
            result["lunch_code"] = _most_common(lunch_codes)

        for pname, b in bins.items():
            if b["temps"]:
                result["periods"][pname] = {
                    "temp_high": max(b["temps"]),
                    "temp_low": min(b["temps"]),
                    "weather_code": _most_common(b["codes"]),
                    "precip_chance": max(b["precip"]) if b["precip"] else 0,
                }

    if daily_data:
        periods_list = daily_data.get("properties", {}).get("periods", [])
        day_data = {}
        for p in periods_list:
            start = p.get("startTime", "")[:10]
            temp = p.get("temperature")
            is_night = not p.get("isDaytime", True)
            detail = p.get("detailedForecast", "")
            short = p.get("shortForecast", "")

            if start not in day_data:
                day_data[start] = {"date": start, "high": None, "low": None,
                                   "description": "", "short": "", "weather_code": 0}

            if is_night:
                day_data[start]["low"] = temp
            else:
                day_data[start]["high"] = temp
                day_data[start]["description"] = detail
                day_data[start]["short"] = short
                day_data[start]["weather_code"] = noaa_short_to_code(short)

        for date_key in sorted(day_data.keys())[:7]:
            d = day_data[date_key]
            result["seven_day"].append({
                "date": d["date"],
                "high": d["high"],
                "low": d["low"],
                "weather_code": d["weather_code"],
                "description": d.get("description", ""),
                "short": d.get("short", ""),
            })

    return result


def _parse_wind_mph(wind_str):
    """NOAA windSpeed looks like '10 mph' or '5 to 15 mph'. Return the max int."""
    nums = [int(tok) for tok in wind_str.replace("to", " ").split() if tok.isdigit()]
    return max(nums) if nums else 0


def blend_forecasts(open_meteo, noaa):
    """
    Blend two forecast sources. Prefer Open-Meteo for codes/icons/hourly,
    enrich with NOAA descriptions and average the temperatures.
    """
    if not open_meteo and not noaa:
        return None
    if not open_meteo:
        return noaa
    if not noaa:
        return open_meteo

    blended = {
        "current_temp": None,
        "current_code": open_meteo.get("current_code", 0),
        "current_wind": open_meteo.get("current_wind"),
        "lunch_temp": None,
        "lunch_temp_range": None,
        "lunch_code": open_meteo.get("lunch_code", 0),
        "periods": {},
        "hourly": open_meteo.get("hourly", []) or noaa.get("hourly", []),
        "seven_day": [],
    }

    om_current = open_meteo.get("current_temp")
    noaa_current = noaa.get("current_temp")
    if om_current is not None and noaa_current is not None:
        blended["current_temp"] = round((om_current + noaa_current) / 2)
    else:
        blended["current_temp"] = om_current if om_current is not None else noaa_current

    om_lunch = open_meteo.get("lunch_temp")
    noaa_lunch = noaa.get("lunch_temp")
    if om_lunch is not None and noaa_lunch is not None:
        blended["lunch_temp"] = round((om_lunch + noaa_lunch) / 2)
        if abs(om_lunch - noaa_lunch) > 3:
            blended["lunch_temp_range"] = (min(om_lunch, noaa_lunch), max(om_lunch, noaa_lunch))
    else:
        blended["lunch_temp"] = om_lunch if om_lunch is not None else noaa_lunch

    for period_name in ["morning", "afternoon", "evening"]:
        om_p = open_meteo.get("periods", {}).get(period_name)
        noaa_p = noaa.get("periods", {}).get(period_name)
        if om_p and noaa_p:
            blended["periods"][period_name] = {
                "temp_high": round((om_p["temp_high"] + noaa_p["temp_high"]) / 2),
                "temp_low": round((om_p["temp_low"] + noaa_p["temp_low"]) / 2),
                "weather_code": om_p["weather_code"],
                "precip_chance": om_p.get("precip_chance", 0),
                "rain_inches": om_p.get("rain_inches", 0),
                "snow_inches": om_p.get("snow_inches", 0),
            }
        elif om_p:
            blended["periods"][period_name] = om_p
        elif noaa_p:
            blended["periods"][period_name] = noaa_p

    om_seven = open_meteo.get("seven_day", [])
    noaa_seven = noaa.get("seven_day", [])
    noaa_by_date = {d["date"]: d for d in noaa_seven}

    for day in om_seven:
        noaa_day = noaa_by_date.get(day["date"], {})
        blended_day = dict(day)
        if noaa_day.get("high") is not None and day.get("high") is not None:
            blended_day["high"] = round((day["high"] + noaa_day["high"]) / 2)
        if noaa_day.get("low") is not None and day.get("low") is not None:
            blended_day["low"] = round((day["low"] + noaa_day["low"]) / 2)
        blended_day["description"] = noaa_day.get("description", "")
        blended_day["short"] = noaa_day.get("short", "")
        blended["seven_day"].append(blended_day)

    # If Open-Meteo had no 7-day (rare), fall back to NOAA's.
    if not blended["seven_day"] and noaa_seven:
        blended["seven_day"] = noaa_seven

    return blended


# ─── HTML Generation ─────────────────────────────────────────────────────────

def day_name(date_str):
    """Convert YYYY-MM-DD to a day name (Sunday, Monday, ...)."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")
    except ValueError:
        return date_str


def should_alert(seven_day):
    """Check 7-day forecast for anything notable kids should know about."""
    alerts = []
    seen = set()

    def add(msg):
        if msg not in seen:
            seen.add(msg)
            alerts.append(msg)

    for day in seven_day:
        d_name = day_name(day.get("date", ""))
        high = day.get("high")
        low = day.get("low")
        code = day.get("weather_code", 0)
        short = day.get("short", "")
        on_day = f"on {d_name}"

        snow_in = day.get("snow_inches", 0)
        precip_prob = day.get("precip_chance", 0)
        wind_max = day.get("wind_max", 0)

        if wind_max and wind_max >= WIND_ALERT_MPH:
            add(f"💨 Windy {on_day}! Winds up to {wind_max} mph!")
        if code in (73, 75, 77, 85, 86):
            if snow_in >= 6:
                add(f"❄️ Snow {on_day}! Maybe a snow day!")
            elif precip_prob >= 75:
                add(f"❄️ Snow {on_day}!")
            else:
                add(f"❄️ Maybe snow {on_day}!")
        elif code in (95, 96, 99):
            add(f"⛈️ Big storms {on_day}! Stay safe!")
        elif code in (66, 67):
            add(f"🧊 Icy rain {on_day}! Watch your step!")
        elif high and high >= 90:
            add(f"🥵 Super hot {on_day}! It will be {high} degrees! Drink water!")
        elif low and low <= 10:
            add(f"🥶 Very very cold {on_day}! Only {low} degrees! Bundle up!")

        for text in [short, day.get("description", "")]:
            tl = text.lower()
            if "blizzard" in tl:
                add(f"🌨️ Blizzard {on_day}! Lots of snow and wind! Stay inside!")
            if "ice storm" in tl:
                add(f"🧊 Ice storm {on_day}! Be very careful outside!")

    return alerts


def generate_html(locations_data, generated_time):
    """Generate the full kid-friendly HTML page."""
    fact = pick_fun_fact(locations_data, generated_time)
    date_display = generated_time.strftime("%A, %B %d, %Y")
    time_display = generated_time.strftime("%I:%M %p")
    # Inject the Python WMO map into the client JS so the two never diverge.
    wmo_js = json.dumps({str(k): list(v) for k, v in WMO_CODES.items()}, ensure_ascii=False)

    location_cards = ""
    for loc_info in locations_data:
        loc = loc_info["location"]
        data = loc_info["data"]

        if not data:
            location_cards += f"""
            <div class="location-card">
                <h2>{loc['emoji']} {loc['name']}, {loc['state']}</h2>
                <p class="error">Couldn't fetch weather data. Try refreshing!</p>
            </div>"""
            continue

        current_temp = data.get("current_temp")
        current_code = data.get("current_code", 0)
        current_wind = data.get("current_wind")
        current_desc, current_icon = wmo_desc(current_code)
        cur_temp_display = f"{current_temp}°F" if current_temp is not None else "..."
        cur_desc_display = current_desc if current_temp is not None else "Loading..."
        cur_icon_display = current_icon if current_temp is not None else "🌡️"
        cur_wind_html = ""
        if current_wind is not None and current_wind >= WIND_ALERT_MPH:
            cur_wind_html = f'<div class="current-wind">💨 {current_wind} mph winds!</div>'
        current_html = f"""
            <div class="current-section" data-lat="{loc['lat']}" data-lon="{loc['lon']}">
                <div class="current-label">🌡️ Right Now</div>
                <div class="current-icon">{cur_icon_display}</div>
                <div class="current-temp">{cur_temp_display}</div>
                <div class="current-desc">{cur_desc_display}</div>
                {cur_wind_html}
            </div>"""

        lunch_temp = data.get("lunch_temp", "?")
        lunch_range = data.get("lunch_temp_range")
        lunch_code = data.get("lunch_code", 0)
        lunch_desc, lunch_icon = wmo_desc(lunch_code)
        lunch_display = f"{lunch_temp}°F"
        if lunch_range:
            lunch_display = f"{lunch_range[0]}–{lunch_range[1]}°F"

        # Whole-day condition codes (hourly + period blocks) so the outfit
        # advice covers morning-commute rain, not just the recess snapshot.
        day_codes = [h.get("weather_code", 0) for h in data.get("hourly", [])]
        day_codes += [p.get("weather_code", 0) for p in data.get("periods", {}).values()]
        outfit = get_outfit_suggestion(
            lunch_temp if isinstance(lunch_temp, (int, float)) else 50,
            lunch_code,
            day_codes=day_codes,
            month=generated_time.month,
        )

        periods_html = ""
        period_labels = {
            "morning": ("🌅 Morning", "6am–12pm"),
            "afternoon": ("☀️ Afternoon", "12pm–6pm"),
            "evening": ("🌙 Evening", "6pm–10pm"),
        }
        for pname, (plabel, ptime) in period_labels.items():
            pdata = data.get("periods", {}).get(pname)
            if pdata:
                p_desc, p_icon = wmo_desc(pdata.get("weather_code", 0))
                p_precip = pdata.get("precip_chance", 0)
                p_rain = pdata.get("rain_inches", 0)
                p_snow = pdata.get("snow_inches", 0)

                precip_bar = ""
                if p_snow > 0:
                    precip_bar = f'<div class="precip">❄️ {format_precip(p_snow, "snow")}</div>'
                elif p_rain > 0:
                    precip_bar = f'<div class="precip">🌧️ {format_precip(p_rain, "rain")}</div>'
                elif p_precip > 0:
                    precip_bar = f'<div class="precip">💧 {p_precip}% chance of rain</div>'

                periods_html += f"""
                <div class="period-card">
                    <div class="period-label">{plabel}</div>
                    <div class="period-time">{ptime}</div>
                    <div class="period-icon">{p_icon}</div>
                    <div class="period-temp">{pdata['temp_high']}°F</div>
                    <div class="period-desc">{p_desc}</div>
                    {precip_bar}
                </div>"""
            else:
                periods_html += f"""
                <div class="period-card">
                    <div class="period-label">{plabel}</div>
                    <div class="period-icon">❓</div>
                    <div class="period-desc">No data yet</div>
                </div>"""

        hourly_html = ""
        hourly_data = data.get("hourly", [])
        if hourly_data:
            hourly_items = ""
            for h in hourly_data:
                h_hour = h["hour"]
                h_temp = h["temp"]
                h_code = h["weather_code"]
                h_precip = h.get("precip_chance", 0)
                _, h_icon = wmo_desc(h_code)
                if h_hour == 0:
                    h_label = "12 AM"
                elif h_hour < 12:
                    h_label = f"{h_hour} AM"
                elif h_hour == 12:
                    h_label = "12 PM"
                else:
                    h_label = f"{h_hour - 12} PM"
                h_wind = h.get("wind", 0)
                precip_dot = f'<div class="hour-precip">💧{h_precip}%</div>' if h_precip > 30 else ""
                wind_dot = f'<div class="hour-wind">💨{h_wind} mph</div>' if h_wind >= WIND_ALERT_MPH else ""
                hourly_items += f"""
                <div class="hour-card">
                    <div class="hour-label">{h_label}</div>
                    <div class="hour-icon">{h_icon}</div>
                    <div class="hour-temp">{h_temp}°</div>
                    {precip_dot}
                    {wind_dot}
                </div>"""
            hourly_html = f"""
            <div class="hourly-section">
                <h3>⏰ Hour by Hour</h3>
                <div class="hourly-scroll">{hourly_items}
                </div>
            </div>"""

        seven_day_html = ""
        for day in data.get("seven_day", []):
            d_desc, d_icon = wmo_desc(day.get("weather_code", 0))
            d_name = day_name(day.get("date", ""))
            d_high = day.get("high", "?")
            d_low = day.get("low", "?")
            d_precip = day.get("precip_chance", 0)
            d_rain = day.get("rain_inches", 0)
            d_snow = day.get("snow_inches", 0)
            d_short = day.get("short", d_desc)
            if d_short:
                d_desc = d_short

            precip_badge = ""
            if d_snow and d_snow > 0:
                pct = f" ({d_precip}%)" if d_precip and d_precip > 0 else ""
                precip_badge = f'<span class="precip-badge">❄️ {format_precip_short(d_snow, "snow")}{pct}</span>'
            elif d_rain and d_rain > 0:
                pct = f" ({d_precip}%)" if d_precip and d_precip > 0 else ""
                precip_badge = f'<span class="precip-badge">🌧️ {format_precip_short(d_rain, "rain")}{pct}</span>'
            elif d_precip and d_precip > 0:
                precip_badge = f'<span class="precip-badge">💧{d_precip}%</span>'

            seven_day_html += f"""
            <div class="day-card">
                <div class="day-name">{d_name}</div>
                <div class="day-icon">{d_icon}</div>
                <div class="day-temps"><span class="high">{d_high}°</span> / <span class="low">{d_low}°</span></div>
                <div class="day-desc">{d_desc}</div>
                {precip_badge}
            </div>"""

        alerts = should_alert(data.get("seven_day", []))
        alerts_html = ""
        if alerts:
            alerts_items = "".join(f"<li>{a}</li>" for a in alerts)
            alerts_html = f"""
            <div class="alerts-section">
                <h3>🚨 Heads Up This Week!</h3>
                <ul>{alerts_items}</ul>
            </div>"""

        location_cards += f"""
        <div class="location-card">
            <h2>{loc['emoji']} {loc['name']}, {loc['state']}</h2>

            {current_html}

            <div class="lunchtime-section">
                <div class="lunch-label">🍕 Lunchtime / Recess (11:40am – 12pm)</div>
                <div class="lunch-icon">{lunch_icon}</div>
                <div class="lunch-temp">{lunch_display}</div>
                <div class="lunch-desc">{lunch_desc}</div>
            </div>

            <div class="outfit-section">
                <div class="outfit-label">👗 What to Wear</div>
                <div class="outfit-text">{outfit}</div>
            </div>

            <div class="periods-section">
                <h3>Today's Forecast</h3>
                <div class="periods-grid">
                    {periods_html}
                </div>
            </div>

            {hourly_html}

            <div class="seven-day-section">
                <h3>📅 Next 7 Days</h3>
                <div class="seven-day-grid">
                    {seven_day_html}
                </div>
            </div>

            {alerts_html}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Today's Weather!</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=OpenDyslexic:wght@400;700&display=swap" rel="stylesheet">
    <style>
        @font-face {{
            font-family: 'OpenDyslexic';
            src: local('OpenDyslexic');
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'OpenDyslexic', 'Comic Sans MS', 'Segoe UI', sans-serif;
            background: linear-gradient(180deg, #b71c1c 0%, #d32f2f 30%, #e57373 100%);
            min-height: 100vh;
            padding: 20px;
            color: #2a2a2a;
            letter-spacing: 0.04em;
            word-spacing: 0.12em;
            line-height: 1.8;
            font-size: 18px;
        }}
        .container {{ max-width: 850px; margin: 0 auto; }}
        .pixel-border {{
            border: 4px solid #5d4037;
            box-shadow: inset 0 0 0 2px #8d6e63, 4px 4px 0 0 rgba(0,0,0,0.15);
            image-rendering: pixelated;
        }}
        .header {{ text-align: center; color: white; margin-bottom: 24px; padding: 16px; }}
        .header h1 {{ font-size: 2em; margin-bottom: 6px; text-shadow: 3px 3px 0 rgba(0,0,0,0.3); }}
        .header .date {{ font-size: 1.15em; opacity: 0.95; }}
        .header .updated {{ font-size: 0.9em; opacity: 0.8; margin-top: 4px; }}
        .fun-fact {{
            background: #4caf50; border-radius: 4px; padding: 18px 22px;
            margin-bottom: 24px; color: white; text-align: center;
        }}
        .fun-fact .label {{ font-weight: 700; font-size: 1.1em; margin-bottom: 8px; }}
        .fun-fact .fact-text {{ font-size: 1.05em; line-height: 1.8; }}
        .location-card {{ background: #fff8f0; border-radius: 4px; padding: 24px; margin-bottom: 24px; }}
        .location-card h2 {{
            font-size: 1.4em; margin-bottom: 16px; color: #b71c1c;
            border-bottom: 4px solid #d32f2f; padding-bottom: 10px;
        }}
        .current-section {{
            text-align: center;
            background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
            border: 3px solid #64b5f6; border-radius: 4px; padding: 20px; margin-bottom: 18px;
        }}
        .current-label {{ font-size: 1.15em; font-weight: 700; color: #1565c0; margin-bottom: 8px; }}
        .current-icon {{ font-size: 2.8em; margin: 8px 0; }}
        .current-temp {{ font-size: 2.8em; font-weight: 800; color: #1565c0; }}
        .current-desc {{ font-size: 1em; color: #1976d2; margin-top: 4px; }}
        .current-wind {{ font-size: 1em; font-weight: 700; color: #6a1b9a; margin-top: 6px; }}
        .hour-wind {{ font-size: 0.75em; color: #6a1b9a; margin-top: 2px; }}
        .lunchtime-section {{
            text-align: center;
            background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);
            border: 3px solid #ef9a9a; border-radius: 4px; padding: 24px; margin-bottom: 18px;
        }}
        .lunch-label {{ font-size: 1.15em; font-weight: 700; color: #c62828; margin-bottom: 10px; }}
        .lunch-icon {{ font-size: 3.5em; margin: 10px 0; }}
        .lunch-temp {{ font-size: 3.5em; font-weight: 700; color: #b71c1c; }}
        .lunch-desc {{ font-size: 1.15em; color: #555; margin-top: 6px; }}
        .outfit-section {{
            background: #fff3e0; border: 3px solid #ffcc80; border-radius: 4px;
            padding: 16px 20px; margin-bottom: 18px;
        }}
        .outfit-label {{ font-weight: 700; font-size: 1.1em; margin-bottom: 8px; color: #e65100; }}
        .outfit-text {{ font-size: 1.05em; line-height: 1.8; color: #4e342e; }}
        .hourly-section {{ margin-bottom: 18px; }}
        .hourly-section h3 {{ font-size: 1.2em; color: #c62828; margin-bottom: 12px; }}
        .hourly-scroll {{
            display: flex; overflow-x: auto; gap: 8px; padding: 8px 0 12px 0;
            -webkit-overflow-scrolling: touch; scrollbar-width: thin;
        }}
        .hourly-scroll::-webkit-scrollbar {{ height: 6px; }}
        .hourly-scroll::-webkit-scrollbar-thumb {{ background: #ef9a9a; border-radius: 3px; }}
        .hour-card {{
            flex: 0 0 auto; text-align: center;
            background: linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%);
            border: 2px solid #ffca28; border-radius: 4px; padding: 10px 14px; min-width: 75px;
        }}
        .hour-label {{ font-size: 0.85em; font-weight: 700; color: #f57f17; margin-bottom: 4px; }}
        .hour-icon {{ font-size: 1.6em; margin: 4px 0; }}
        .hour-temp {{ font-size: 1.2em; font-weight: 800; color: #e65100; }}
        .hour-precip {{ font-size: 0.75em; color: #1565c0; margin-top: 4px; }}
        .periods-section h3, .seven-day-section h3 {{ font-size: 1.2em; color: #c62828; margin-bottom: 14px; }}
        .periods-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 22px; }}
        .period-card {{ background: white; border-radius: 4px; padding: 16px; text-align: center; border: 3px solid #e0e0e0; }}
        .period-label {{ font-weight: 700; font-size: 1em; color: #c62828; }}
        .period-time {{ font-size: 0.85em; color: #888; margin-bottom: 8px; }}
        .period-icon {{ font-size: 2.5em; margin: 8px 0; }}
        .period-temp {{ font-size: 1.5em; font-weight: 700; color: #333; }}
        .period-desc {{ font-size: 0.95em; color: #666; margin-top: 6px; }}
        .precip {{ font-size: 0.9em; color: #1565c0; margin-top: 8px; font-weight: 700; }}
        .seven-day-grid {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; margin-bottom: 18px; }}
        .day-card {{ background: white; border-radius: 4px; padding: 12px 8px; text-align: center; border: 3px solid #e0e0e0; }}
        .day-name {{ font-weight: 700; font-size: 0.9em; color: #c62828; margin-bottom: 6px; }}
        .day-icon {{ font-size: 1.8em; margin: 6px 0; }}
        .day-temps {{ font-size: 1em; margin: 6px 0; }}
        .high {{ color: #c62828; font-weight: 700; }}
        .low {{ color: #1565c0; font-weight: 700; }}
        .day-desc {{ font-size: 0.8em; color: #777; line-height: 1.5; }}
        .precip-badge {{
            display: inline-block; background: #e3f2fd; color: #1565c0; font-size: 0.8em;
            padding: 3px 8px; border-radius: 4px; margin-top: 6px; font-weight: 700;
        }}
        .alerts-section {{
            background: #fff9c4; border: 4px solid #fdd835; border-radius: 4px;
            padding: 16px 20px; margin-top: 14px;
        }}
        .alerts-section h3 {{ color: #e65100; margin-bottom: 10px; font-size: 1.15em; }}
        .alerts-section ul {{ list-style: none; padding: 0; }}
        .alerts-section li {{ padding: 6px 0; font-size: 1em; color: #bf360c; line-height: 1.7; }}
        .error {{ color: #c62828; text-align: center; padding: 20px; font-size: 1.1em; }}
        .footer {{ text-align: center; color: rgba(255,255,255,0.75); font-size: 0.85em; margin-top: 20px; padding-bottom: 24px; }}
        @media (max-width: 700px) {{
            .seven-day-grid {{ grid-template-columns: repeat(4, 1fr); }}
            .header h1 {{ font-size: 1.6em; }}
            body {{ font-size: 16px; }}
        }}
        @media (max-width: 480px) {{
            body {{ padding: 12px; font-size: 15px; }}
            .seven-day-grid {{ grid-template-columns: repeat(3, 1fr); }}
            .periods-grid {{ grid-template-columns: 1fr; }}
            .lunch-temp {{ font-size: 2.8em; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌤️ Weather Report! 🌤️</h1>
            <div class="date">{date_display}</div>
            <div class="updated">Updated at {time_display} ET</div>
        </div>

        <div class="fun-fact pixel-border">
            <div class="label">🧠 Cool Fact of the Day!</div>
            <div class="fact-text">{fact}</div>
        </div>

        {location_cards}

        <div class="footer">
            Data from NOAA + Open-Meteo &bull; Made with ❤️ by Dad
        </div>
    </div>

    <script>
    // WMO weather code to [description, emoji] — injected from Python so the
    // server-rendered page and this live updater always agree.
    const wmoMap = {wmo_js};

    function updateCurrentTemps() {{
        document.querySelectorAll('.current-section').forEach(function(section) {{
            var lat = section.getAttribute('data-lat');
            var lon = section.getAttribute('data-lon');
            if (!lat || !lon) return;

            var url = 'https://api.open-meteo.com/v1/forecast?latitude=' + lat
                + '&longitude=' + lon
                + '&current=temperature_2m,weather_code,wind_speed_10m'
                + '&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=America%2FNew_York';

            fetch(url)
                .then(function(r) {{ return r.json(); }})
                .then(function(data) {{
                    if (data && data.current) {{
                        var temp = Math.round(data.current.temperature_2m);
                        var code = data.current.weather_code || 0;
                        var wind = Math.round(data.current.wind_speed_10m || 0);
                        var info = wmoMap[code] || ["Unknown", "🌡️"];

                        section.querySelector('.current-temp').textContent = temp + '°F';
                        section.querySelector('.current-icon').textContent = info[1];
                        section.querySelector('.current-desc').textContent = info[0];

                        var windEl = section.querySelector('.current-wind');
                        if (wind >= {WIND_ALERT_MPH}) {{
                            if (!windEl) {{
                                windEl = document.createElement('div');
                                windEl.className = 'current-wind';
                                section.appendChild(windEl);
                            }}
                            windEl.textContent = '💨 ' + wind + ' mph winds!';
                        }} else if (windEl) {{
                            windEl.textContent = '';
                        }}
                    }}
                }})
                .catch(function(e) {{ console.log('Weather fetch error:', e); }});
        }});
    }}

    updateCurrentTemps();
    setInterval(updateCurrentTemps, 30 * 60 * 1000);
    </script>
</body>
</html>"""

    return html


# ─── GitHub Push (optional, local convenience only) ──────────────────────────

def push_to_github(html_content, token):
    """Push HTML to GitHub repo using the Contents API."""
    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE}"

    sha = None
    try:
        existing = fetch_json(api_url, headers={"Authorization": f"token {token}"})
        if existing:
            sha = existing.get("sha")
    except Exception:
        pass

    content_b64 = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")
    payload = {
        "message": f"Update weather forecast - {datetime.now(ET).strftime('%Y-%m-%d %H:%M')}",
        "content": content_b64,
    }
    if sha:
        payload["sha"] = sha

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(api_url, data=data, method="PUT")
    req.add_header("Authorization", f"token {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "WeatherAgentForKids/1.0")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            json.loads(resp.read().decode())
            print(f"✅ Pushed to GitHub! URL: https://{GITHUB_OWNER}.github.io/{GITHUB_REPO}/", file=sys.stderr)
            return True
    except urllib.error.HTTPError as e:
        print(f"❌ GitHub push failed: {e.code} - {e.read().decode()}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ GitHub push failed: {e}", file=sys.stderr)
        return False


# ─── Main ────────────────────────────────────────────────────────────────────

def _truthy(val):
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def main():
    print("🌤️ Daily Weather Agent starting...", file=sys.stderr)

    now_est = datetime.now(ET)
    print(f"📅 Date: {now_est.strftime('%Y-%m-%d %H:%M %Z')}", file=sys.stderr)

    locations_data = []
    for loc in LOCATIONS:
        print(f"\n📍 Fetching weather for {loc['name']}, {loc['state']}...", file=sys.stderr)
        om_data = fetch_open_meteo(loc["lat"], loc["lon"])
        noaa_hourly, noaa_daily = fetch_noaa_forecast(loc["lat"], loc["lon"])

        om_processed = process_open_meteo(om_data)
        noaa_processed = process_noaa(noaa_hourly, noaa_daily)
        blended = blend_forecasts(om_processed, noaa_processed)

        if blended:
            print(f"  ✅ Lunchtime temp: {blended.get('lunch_temp', '?')}°F", file=sys.stderr)
        else:
            print("  ❌ No data available", file=sys.stderr)

        locations_data.append({"location": loc, "data": blended})

    # ── Quality gate: don't overwrite a good page with a broken one ──
    has_any_data = False
    has_hourly = False
    for loc_info in locations_data:
        data = loc_info["data"]
        if data:
            has_any_data = True
            if data.get("hourly") and len(data["hourly"]) >= 3:
                has_hourly = True

    if not has_any_data:
        print("\n🚫 NO weather data at all — both APIs failed for all locations.", file=sys.stderr)
        print("   Skipping page generation to protect the existing page.", file=sys.stderr)
        sys.exit(1)

    if not has_hourly:
        print("\n⚠️ Hourly data missing for every location — page would be degraded.", file=sys.stderr)
        print("   Skipping to protect the existing page.", file=sys.stderr)
        sys.exit(1)

    print("\n🎨 Generating HTML page...", file=sys.stderr)
    html = generate_html(locations_data, now_est)

    output_path = os.environ.get("OUTPUT_PATH", "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"💾 Saved to {output_path}", file=sys.stderr)

    # Direct API push is OPT-IN (local convenience). In CI the workflow commits
    # and pushes the file, so we don't double-push here.
    if _truthy(os.environ.get("PUSH_VIA_API", "")):
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            print("\n❌ PUSH_VIA_API set but GITHUB_TOKEN is empty.", file=sys.stderr)
            sys.exit(1)
        print("\n🚀 Pushing to GitHub Pages via API...", file=sys.stderr)
        if not push_to_github(html, token):
            print("\n❌ Push failed — exiting with error.", file=sys.stderr)
            sys.exit(1)
    else:
        print("\n📁 File written. Push is handled by the workflow (or set PUSH_VIA_API=1).", file=sys.stderr)

    print("\n✨ Done!", file=sys.stderr)


if __name__ == "__main__":
    main()
