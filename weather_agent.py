#!/usr/bin/env python3
"""
Daily Weather Agent for Kids
Fetches weather from NOAA + Open-Meteo for Watertown MA & Naples ME,
generates a colorful kid-friendly HTML page, and pushes to GitHub Pages.
"""

import urllib.request
import urllib.error
import json
import random
import base64
import os
import sys
from datetime import datetime, timedelta, timezone

# ─── Configuration ──────────────────────────────────────────────────────────

LOCATIONS = [
    {
        "name": "Watertown",
        "state": "MA",
        "lat": 42.3709,
        "lon": -71.1828,
        "emoji": "🏙️",
        "noaa_grid": None,  # fetched dynamically
    },
    {
        "name": "Naples",
        "state": "ME",
        "lat": 43.9590,
        "lon": -70.5878,
        "emoji": "🌲",
        "noaa_grid": None,
    },
]

GITHUB_OWNER = "sam-melnick"
GITHUB_REPO = "Weather"
GITHUB_FILE = "index.html"

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

OUTFIT_RULES = [
    # (max_temp_F, condition_keyword, suggestion)
    # These are checked in order; first match wins
]

# ─── Weather API Helpers ────────────────────────────────────────────────────

def fetch_json(url, headers=None):
    """Fetch a URL and return parsed JSON."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "WeatherAgentForKids/1.0 (samelnick@gmail.com)")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  ⚠ Failed to fetch {url}: {e}", file=sys.stderr)
        return None


def fetch_open_meteo(lat, lon):
    """
    Fetch hourly + daily forecast from Open-Meteo.
    Returns dict with 'hourly' and 'daily' data.
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,precipitation_probability,weather_code,wind_speed_10m,precipitation,snowfall"
        f"&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max,precipitation_sum,snowfall_sum,sunrise,sunset"
        f"&temperature_unit=fahrenheit"
        f"&wind_speed_unit=mph"
        f"&timezone=America%2FNew_York"
        f"&forecast_days=7"
    )
    print(f"  Fetching Open-Meteo...", file=sys.stderr)
    return fetch_json(url)


def fetch_noaa_forecast(lat, lon):
    """
    Fetch forecast from NOAA Weather.gov API.
    Two-step: get grid point, then fetch hourly + daily.
    """
    print(f"  Fetching NOAA grid point...", file=sys.stderr)
    points = fetch_json(f"https://api.weather.gov/points/{lat},{lon}")
    if not points:
        return None, None

    props = points.get("properties", {})
    hourly_url = props.get("forecastHourly")
    daily_url = props.get("forecast")

    hourly = None
    daily = None
    if hourly_url:
        print(f"  Fetching NOAA hourly...", file=sys.stderr)
        hourly = fetch_json(hourly_url)
    if daily_url:
        print(f"  Fetching NOAA daily...", file=sys.stderr)
        daily = fetch_json(daily_url)

    return hourly, daily


# ─── Weather Code → Description/Icon Mapping ────────────────────────────────

# Weather codes with simple, short descriptions (easy to read!)
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


# ─── Data Processing ─────────────────────────────────────────────────────────

def format_precip(inches, precip_type="rain"):
    """Format precipitation amount in kid-friendly words. Uses feet for 12+ inches."""
    if inches <= 0:
        return ""
    if inches >= 12:
        feet = round(inches / 12, 1)
        if feet == int(feet):
            feet = int(feet)
        unit = "foot" if feet == 1 else "feet"
        return f"{feet} {unit} of {precip_type}"
    else:
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
        unit = "ft" if feet != 1 else "ft"
        return f"{feet} {unit}"
    else:
        unit = "in" if inches != 1 else "in"
        return f"{inches} {unit}"


def get_outfit_suggestion(temp_f, weather_code, month=None):
    """Return a kid-friendly outfit suggestion. Short sentences, simple words."""
    desc, _ = wmo_desc(weather_code)
    desc_lower = desc.lower()

    rain = any(w in desc_lower for w in ["rain", "drizzle", "shower"])
    snow = any(w in desc_lower for w in ["snow", "freezing"])
    storm = "thunder" in desc_lower
    sunny = any(w in desc_lower for w in ["sunny", "clear"])

    # Figure out if it's sunscreen season (spring/summer/fall = April-October)
    if month is None:
        month = datetime.now().month
    sunscreen_season = 4 <= month <= 10

    suggestions = []

    if temp_f <= 20:
        suggestions.append("🧥 SUPER cold! Wear your big coat, snow pants, hat, gloves, and boots!")
    elif temp_f <= 32:
        suggestions.append("🧥 Freezing out! Wear your winter coat, hat, and gloves!")
    elif temp_f <= 45:
        suggestions.append("🧶 Chilly! Wear a warm jacket. A hat is a good idea too!")
    elif temp_f <= 55:
        suggestions.append("🧥 A bit cool. A hoodie or medium jacket is perfect!")
    elif temp_f <= 65:
        suggestions.append("👕 Nice out! Long sleeves or a light jacket!")
    elif temp_f <= 75:
        suggestions.append("😎 T-shirt weather! Feels great outside!")
    elif temp_f <= 85:
        suggestions.append("🩳 Shorts and t-shirt day!")
    else:
        suggestions.append("🥵 SO hot! Wear light clothes. Drink lots of water!")

    if rain:
        suggestions.append("☔ Bring your rain jacket and rain boots!")
    if snow:
        suggestions.append("🥾 Snow boots and snow gear today!")
    if storm:
        suggestions.append("⚡ Thunderstorms! Stay inside when you hear thunder!")

    # Sunny day extras
    if sunny and not rain and not snow:
        suggestions.append("🕶️ Wear your sunglasses!")
        if sunscreen_season:
            suggestions.append("🧴 Put on sunscreen before you go out!")

    return " ".join(suggestions)


def process_open_meteo(data):
    """
    Process Open-Meteo data into our standard format.
    Returns dict with lunchtime temp, morning/afternoon/evening, and 7-day.
    """
    if not data:
        return None

    hourly = data.get("hourly", {})
    daily = data.get("daily", {})

    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    codes = hourly.get("weather_code", [])
    precip = hourly.get("precipitation_probability", [])
    winds = hourly.get("wind_speed_10m", [])
    rain_mm = hourly.get("precipitation", [])
    snow_cm = hourly.get("snowfall", [])

    # Find today's date
    now_est = datetime.now(timezone(timedelta(hours=-5)))
    today_str = now_est.strftime("%Y-%m-%d")

    # Find lunchtime temp (11:00 and 12:00 hours, average them)
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

    # Morning (6-11), Afternoon (12-17), Evening (18-22)
    periods = {"morning": (6, 11), "afternoon": (12, 17), "evening": (18, 22)}
    period_data = {}

    for period_name, (start_h, end_h) in periods.items():
        p_temps = []
        p_codes = []
        p_precip = []
        p_rain = []
        p_snow = []
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
            # Sum up rain/snow for the period, convert to inches
            total_rain_in = round(sum(p_rain) / 25.4, 1) if p_rain else 0
            total_snow_in = round(sum(p_snow) / 2.54, 1) if p_snow else 0
            period_data[period_name] = {
                "temp_high": round(max(p_temps)),
                "temp_low": round(min(p_temps)),
                "weather_code": max(p_codes) if p_codes else 0,
                "precip_chance": max(p_precip) if p_precip else 0,
                "rain_inches": total_rain_in,
                "snow_inches": total_snow_in,
            }

    # 7-day forecast
    daily_dates = daily.get("time", [])
    daily_highs = daily.get("temperature_2m_max", [])
    daily_lows = daily.get("temperature_2m_min", [])
    daily_codes = daily.get("weather_code", [])
    daily_precip = daily.get("precipitation_probability_max", [])
    daily_rain_sum = daily.get("precipitation_sum", [])
    daily_snow_sum = daily.get("snowfall_sum", [])

    seven_day = []
    for i in range(min(7, len(daily_dates))):
        # Convert mm to inches for rain, cm to inches for snow
        rain_in = round(daily_rain_sum[i] / 25.4, 1) if i < len(daily_rain_sum) and daily_rain_sum[i] else 0
        snow_in = round(daily_snow_sum[i] / 2.54, 1) if i < len(daily_snow_sum) and daily_snow_sum[i] else 0
        seven_day.append({
            "date": daily_dates[i] if i < len(daily_dates) else "",
            "high": round(daily_highs[i]) if i < len(daily_highs) else None,
            "low": round(daily_lows[i]) if i < len(daily_lows) else None,
            "weather_code": daily_codes[i] if i < len(daily_codes) else 0,
            "precip_chance": daily_precip[i] if i < len(daily_precip) else 0,
            "rain_inches": rain_in,
            "snow_inches": snow_in,
        })

    return {
        "source": "Open-Meteo",
        "lunch_temp": lunch_temp,
        "lunch_code": lunch_code,
        "periods": period_data,
        "seven_day": seven_day,
    }


def process_noaa(hourly_data, daily_data):
    """Process NOAA data into our standard format."""
    if not hourly_data and not daily_data:
        return None

    now_est = datetime.now(timezone(timedelta(hours=-5)))
    today_str = now_est.strftime("%Y-%m-%d")

    result = {
        "source": "NOAA",
        "lunch_temp": None,
        "lunch_code": 0,
        "periods": {},
        "seven_day": [],
    }

    # Process hourly for lunchtime and period breakdowns
    if hourly_data:
        periods_list = hourly_data.get("properties", {}).get("periods", [])
        lunch_temps = []
        period_temps = {"morning": [], "afternoon": [], "evening": []}

        for p in periods_list:
            start = p.get("startTime", "")
            if not start.startswith(today_str):
                continue

            hour = int(start.split("T")[1].split(":")[0])
            temp = p.get("temperature")

            if 11 <= hour <= 12:
                lunch_temps.append(temp)

            if 6 <= hour <= 11:
                period_temps["morning"].append(temp)
            elif 12 <= hour <= 17:
                period_temps["afternoon"].append(temp)
            elif 18 <= hour <= 22:
                period_temps["evening"].append(temp)

        if lunch_temps:
            result["lunch_temp"] = round(sum(lunch_temps) / len(lunch_temps))

        for pname, tlist in period_temps.items():
            if tlist:
                result["periods"][pname] = {
                    "temp_high": max(tlist),
                    "temp_low": min(tlist),
                    "weather_code": 0,
                    "precip_chance": 0,
                }

    # Process daily for 7-day
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
                day_data[start] = {"date": start, "high": None, "low": None, "description": "", "short": ""}

            if is_night:
                day_data[start]["low"] = temp
            else:
                day_data[start]["high"] = temp
                day_data[start]["description"] = detail
                day_data[start]["short"] = short

        for date_key in sorted(day_data.keys())[:7]:
            d = day_data[date_key]
            result["seven_day"].append({
                "date": d["date"],
                "high": d["high"],
                "low": d["low"],
                "weather_code": 0,
                "description": d.get("description", ""),
                "short": d.get("short", ""),
            })

    return result


def blend_forecasts(open_meteo, noaa):
    """
    Blend two forecast sources. If they disagree, show a range.
    Prefer Open-Meteo for codes/icons, NOAA for descriptions.
    """
    if not open_meteo and not noaa:
        return None
    if not open_meteo:
        return noaa
    if not noaa:
        return open_meteo

    blended = {
        "lunch_temp": None,
        "lunch_temp_range": None,
        "lunch_code": open_meteo.get("lunch_code", 0),
        "periods": {},
        "seven_day": [],
    }

    # Blend lunchtime temps
    om_lunch = open_meteo.get("lunch_temp")
    noaa_lunch = noaa.get("lunch_temp")

    if om_lunch is not None and noaa_lunch is not None:
        avg = round((om_lunch + noaa_lunch) / 2)
        blended["lunch_temp"] = avg
        if abs(om_lunch - noaa_lunch) > 3:
            blended["lunch_temp_range"] = (min(om_lunch, noaa_lunch), max(om_lunch, noaa_lunch))
    else:
        blended["lunch_temp"] = om_lunch or noaa_lunch

    # Blend periods
    for period_name in ["morning", "afternoon", "evening"]:
        om_p = open_meteo.get("periods", {}).get(period_name)
        noaa_p = noaa.get("periods", {}).get(period_name)

        if om_p and noaa_p:
            blended["periods"][period_name] = {
                "temp_high": round((om_p["temp_high"] + noaa_p["temp_high"]) / 2),
                "temp_low": round((om_p["temp_low"] + noaa_p["temp_low"]) / 2),
                "weather_code": om_p["weather_code"],
                "precip_chance": om_p.get("precip_chance", 0),
            }
        elif om_p:
            blended["periods"][period_name] = om_p
        elif noaa_p:
            blended["periods"][period_name] = noaa_p

    # Use Open-Meteo for 7-day (more structured), enrich with NOAA descriptions
    om_seven = open_meteo.get("seven_day", [])
    noaa_seven = noaa.get("seven_day", [])
    noaa_by_date = {d["date"]: d for d in noaa_seven}

    for day in om_seven:
        noaa_day = noaa_by_date.get(day["date"], {})
        blended_day = dict(day)

        # Average temps if both available
        if noaa_day.get("high") is not None and day.get("high") is not None:
            blended_day["high"] = round((day["high"] + noaa_day["high"]) / 2)
        if noaa_day.get("low") is not None and day.get("low") is not None:
            blended_day["low"] = round((day["low"] + noaa_day["low"]) / 2)

        blended_day["description"] = noaa_day.get("description", "")
        blended_day["short"] = noaa_day.get("short", "")
        blended["seven_day"].append(blended_day)

    return blended


# ─── HTML Generation ─────────────────────────────────────────────────────────

def day_name(date_str):
    """Convert YYYY-MM-DD to day name."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        now = datetime.now()
        if d.date() == now.date():
            return "Today"
        elif d.date() == (now + timedelta(days=1)).date():
            return "Tomorrow"
        return d.strftime("%A")
    except:
        return date_str


def should_alert(seven_day):
    """Check 7-day forecast for anything notable kids should know about."""
    alerts = []
    for day in seven_day:
        d_name = day_name(day.get("date", ""))
        high = day.get("high")
        low = day.get("low")
        code = day.get("weather_code", 0)
        desc, _ = wmo_desc(code)
        short = day.get("short", "")

        # Check for notable conditions (simple words!)
        # Use "today" / "tomorrow" without "on", but "on Wednesday" etc.
        on_day = d_name if d_name in ("Today", "Tomorrow") else f"on {d_name}"

        snow_in = day.get("snow_inches", 0)
        if code in (73, 75, 77, 85, 86):
            if snow_in >= 6:
                alerts.append(f"❄️ Snow {on_day}! Maybe a snow day!")
            else:
                alerts.append(f"❄️ Snow {on_day}!")
        elif code in (95, 96, 99):
            alerts.append(f"⛈️ Big storms {on_day}! Stay safe!")
        elif code in (66, 67):
            alerts.append(f"🧊 Icy rain {on_day}! Watch your step!")
        elif high and high >= 90:
            alerts.append(f"🥵 Super hot {on_day}! It will be {high} degrees! Drink water!")
        elif low and low <= 10:
            alerts.append(f"🥶 Very very cold {on_day}! Only {low} degrees! Bundle up!")

        # Check NOAA descriptions for keywords
        for text in [short, day.get("description", "")]:
            text_lower = text.lower()
            if "blizzard" in text_lower and "Blizzard" not in str(alerts):
                alerts.append(f"🌨️ Blizzard {on_day}! Lots of snow and wind! Stay inside!")
            if "ice storm" in text_lower:
                alerts.append(f"🧊 Ice storm {on_day}! Be very careful outside!")

    return alerts


def generate_html(locations_data, generated_time):
    """Generate the full kid-friendly HTML page."""
    fact = random.choice(FUN_FACTS)
    date_display = generated_time.strftime("%A, %B %d, %Y")
    time_display = generated_time.strftime("%I:%M %p")

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

        # Lunchtime section
        lunch_temp = data.get("lunch_temp", "?")
        lunch_range = data.get("lunch_temp_range")
        lunch_code = data.get("lunch_code", 0)
        lunch_desc, lunch_icon = wmo_desc(lunch_code)

        lunch_display = f"{lunch_temp}°F"
        if lunch_range:
            lunch_display = f"{lunch_range[0]}–{lunch_range[1]}°F"

        # Outfit
        outfit = get_outfit_suggestion(
            lunch_temp if isinstance(lunch_temp, (int, float)) else 50,
            lunch_code,
            month=generated_time.month
        )

        # Periods
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

                # Build precipitation info line
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

        # 7-day forecast
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

            # Use NOAA short forecast if available, otherwise WMO description
            if d_short:
                d_desc = d_short

            # Show snow or rain amounts, fall back to % chance
            precip_badge = ""
            if d_snow and d_snow > 0:
                precip_badge = f'<span class="precip-badge">❄️ {format_precip_short(d_snow, "snow")}</span>'
            elif d_rain and d_rain > 0:
                precip_badge = f'<span class="precip-badge">🌧️ {format_precip_short(d_rain, "rain")}</span>'
            elif d_precip and d_precip > 30:
                precip_badge = f'<span class="precip-badge">💧{d_precip}%</span>'

            seven_day_html += f"""
            <div class="day-card">
                <div class="day-name">{d_name}</div>
                <div class="day-icon">{d_icon}</div>
                <div class="day-temps"><span class="high">{d_high}°</span> / <span class="low">{d_low}°</span></div>
                <div class="day-desc">{d_desc}</div>
                {precip_badge}
            </div>"""

        # Alerts for this location
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

            <div class="seven-day-section">
                <h3>📅 Next 7 Days</h3>
                <div class="seven-day-grid">
                    {seven_day_html}
                </div>
            </div>

            {alerts_html}
        </div>"""

    # Build full HTML — Red/Minecraft theme, OpenDyslexic, accessibility-first
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Today's Weather!</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=OpenDyslexic:wght@400;700&display=swap" rel="stylesheet">
    <style>
        /* ── OpenDyslexic fallback: if Google Fonts CDN fails, use system sans ── */
        @font-face {{
            font-family: 'OpenDyslexic';
            src: local('OpenDyslexic');
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            /* OpenDyslexic primary, fallback to clean sans-serif */
            font-family: 'OpenDyslexic', 'Comic Sans MS', 'Segoe UI', sans-serif;
            /* Red-themed gradient background */
            background: linear-gradient(180deg, #b71c1c 0%, #d32f2f 30%, #e57373 100%);
            min-height: 100vh;
            padding: 20px;
            color: #2a2a2a;
            /* Wider letter + word spacing helps dyslexia */
            letter-spacing: 0.04em;
            word-spacing: 0.12em;
            line-height: 1.8;
            font-size: 18px;
        }}

        .container {{
            max-width: 850px;
            margin: 0 auto;
        }}

        /* ── Pixel-art decorative border (Minecraft-style) ── */
        .pixel-border {{
            border: 4px solid #5d4037;
            box-shadow:
                inset 0 0 0 2px #8d6e63,
                4px 4px 0 0 rgba(0,0,0,0.15);
            image-rendering: pixelated;
        }}

        /* ── Header ── */
        .header {{
            text-align: center;
            color: white;
            margin-bottom: 24px;
            padding: 16px;
        }}

        .header h1 {{
            font-size: 2em;
            margin-bottom: 6px;
            text-shadow: 3px 3px 0 rgba(0,0,0,0.3);
        }}

        .header .date {{
            font-size: 1.15em;
            opacity: 0.95;
        }}

        .header .updated {{
            font-size: 0.9em;
            opacity: 0.8;
            margin-top: 4px;
        }}

        /* ── Fun Fact ── */
        .fun-fact {{
            background: #4caf50;
            border-radius: 4px;
            padding: 18px 22px;
            margin-bottom: 24px;
            color: white;
            text-align: center;
        }}

        .fun-fact .label {{
            font-weight: 700;
            font-size: 1.1em;
            margin-bottom: 8px;
        }}

        .fun-fact .fact-text {{
            font-size: 1.05em;
            line-height: 1.8;
        }}

        /* ── Location Cards ── */
        .location-card {{
            background: #fff8f0;
            border-radius: 4px;
            padding: 24px;
            margin-bottom: 24px;
        }}

        .location-card h2 {{
            font-size: 1.4em;
            margin-bottom: 16px;
            color: #b71c1c;
            border-bottom: 4px solid #d32f2f;
            padding-bottom: 10px;
        }}

        /* ── Lunchtime (the BIG number) ── */
        .lunchtime-section {{
            text-align: center;
            /* Warm cream with red accent */
            background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);
            border: 3px solid #ef9a9a;
            border-radius: 4px;
            padding: 24px;
            margin-bottom: 18px;
        }}

        .lunch-label {{
            font-size: 1.15em;
            font-weight: 700;
            color: #c62828;
            margin-bottom: 10px;
        }}

        .lunch-icon {{
            font-size: 3.5em;
            margin: 10px 0;
        }}

        .lunch-temp {{
            font-size: 3.5em;
            font-weight: 700;
            color: #b71c1c;
        }}

        .lunch-desc {{
            font-size: 1.15em;
            color: #555;
            margin-top: 6px;
        }}

        /* ── Outfit ── */
        .outfit-section {{
            background: #fff3e0;
            border: 3px solid #ffcc80;
            border-radius: 4px;
            padding: 16px 20px;
            margin-bottom: 18px;
        }}

        .outfit-label {{
            font-weight: 700;
            font-size: 1.1em;
            margin-bottom: 8px;
            color: #e65100;
        }}

        .outfit-text {{
            font-size: 1.05em;
            line-height: 1.8;
            color: #4e342e;
        }}

        /* ── Period Cards (Morning/Afternoon/Evening) ── */
        .periods-section h3,
        .seven-day-section h3 {{
            font-size: 1.2em;
            color: #c62828;
            margin-bottom: 14px;
        }}

        .periods-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 14px;
            margin-bottom: 22px;
        }}

        .period-card {{
            background: white;
            border-radius: 4px;
            padding: 16px;
            text-align: center;
            border: 3px solid #e0e0e0;
        }}

        .period-label {{
            font-weight: 700;
            font-size: 1em;
            color: #c62828;
        }}

        .period-time {{
            font-size: 0.85em;
            color: #888;
            margin-bottom: 8px;
        }}

        .period-icon {{
            font-size: 2.5em;
            margin: 8px 0;
        }}

        .period-temp {{
            font-size: 1.5em;
            font-weight: 700;
            color: #333;
        }}

        .period-desc {{
            font-size: 0.95em;
            color: #666;
            margin-top: 6px;
        }}

        .precip {{
            font-size: 0.9em;
            color: #1565c0;
            margin-top: 8px;
            font-weight: 700;
        }}

        /* ── 7-Day Cards ── */
        .seven-day-grid {{
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 10px;
            margin-bottom: 18px;
        }}

        .day-card {{
            background: white;
            border-radius: 4px;
            padding: 12px 8px;
            text-align: center;
            border: 3px solid #e0e0e0;
        }}

        .day-name {{
            font-weight: 700;
            font-size: 0.9em;
            color: #c62828;
            margin-bottom: 6px;
        }}

        .day-icon {{
            font-size: 1.8em;
            margin: 6px 0;
        }}

        .day-temps {{
            font-size: 1em;
            margin: 6px 0;
        }}

        .high {{
            color: #c62828;
            font-weight: 700;
        }}

        .low {{
            color: #1565c0;
            font-weight: 700;
        }}

        .day-desc {{
            font-size: 0.8em;
            color: #777;
            line-height: 1.5;
        }}

        .precip-badge {{
            display: inline-block;
            background: #e3f2fd;
            color: #1565c0;
            font-size: 0.8em;
            padding: 3px 8px;
            border-radius: 4px;
            margin-top: 6px;
            font-weight: 700;
        }}

        /* ── Alerts ── */
        .alerts-section {{
            background: #fff9c4;
            border: 4px solid #fdd835;
            border-radius: 4px;
            padding: 16px 20px;
            margin-top: 14px;
        }}

        .alerts-section h3 {{
            color: #e65100;
            margin-bottom: 10px;
            font-size: 1.15em;
        }}

        .alerts-section ul {{
            list-style: none;
            padding: 0;
        }}

        .alerts-section li {{
            padding: 6px 0;
            font-size: 1em;
            color: #bf360c;
            line-height: 1.7;
        }}

        .error {{
            color: #c62828;
            text-align: center;
            padding: 20px;
            font-size: 1.1em;
        }}

        /* ── Footer with pixel pickaxe ── */
        .footer {{
            text-align: center;
            color: rgba(255,255,255,0.75);
            font-size: 0.85em;
            margin-top: 20px;
            padding-bottom: 24px;
        }}

        /* ── Responsive ── */
        @media (max-width: 700px) {{
            .seven-day-grid {{
                grid-template-columns: repeat(4, 1fr);
            }}
            .header h1 {{
                font-size: 1.6em;
            }}
            body {{
                font-size: 16px;
            }}
        }}

        @media (max-width: 480px) {{
            body {{
                padding: 12px;
                font-size: 15px;
            }}
            .seven-day-grid {{
                grid-template-columns: repeat(3, 1fr);
            }}
            .periods-grid {{
                grid-template-columns: 1fr;
            }}
            .lunch-temp {{
                font-size: 2.8em;
            }}
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
</body>
</html>"""

    return html


# ─── GitHub Push ─────────────────────────────────────────────────────────────

def push_to_github(html_content, token):
    """Push HTML to GitHub repo using the Contents API."""
    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE}"

    # First, get the current file's SHA (needed for updates)
    sha = None
    try:
        existing = fetch_json(api_url, headers={"Authorization": f"token {token}"})
        if existing:
            sha = existing.get("sha")
    except:
        pass

    # Encode content
    content_b64 = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")

    payload = {
        "message": f"Update weather forecast - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
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
            result = json.loads(resp.read().decode())
            print(f"✅ Pushed to GitHub! URL: https://{GITHUB_OWNER}.github.io/{GITHUB_REPO}/", file=sys.stderr)
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"❌ GitHub push failed: {e.code} - {body}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ GitHub push failed: {e}", file=sys.stderr)
        return False


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("🌤️ Daily Weather Agent starting...", file=sys.stderr)

    github_token = os.environ.get("GITHUB_TOKEN", "")

    now_est = datetime.now(timezone(timedelta(hours=-5)))
    print(f"📅 Date: {now_est.strftime('%Y-%m-%d %H:%M %Z')}", file=sys.stderr)

    locations_data = []

    for loc in LOCATIONS:
        print(f"\n📍 Fetching weather for {loc['name']}, {loc['state']}...", file=sys.stderr)

        # Fetch from both sources
        om_data = fetch_open_meteo(loc["lat"], loc["lon"])
        noaa_hourly, noaa_daily = fetch_noaa_forecast(loc["lat"], loc["lon"])

        # Process each source
        om_processed = process_open_meteo(om_data)
        noaa_processed = process_noaa(noaa_hourly, noaa_daily)

        # Blend them
        blended = blend_forecasts(om_processed, noaa_processed)

        if blended:
            print(f"  ✅ Lunchtime temp: {blended.get('lunch_temp', '?')}°F", file=sys.stderr)
        else:
            print(f"  ❌ No data available", file=sys.stderr)

        locations_data.append({"location": loc, "data": blended})

    # Generate HTML
    print("\n🎨 Generating HTML page...", file=sys.stderr)
    html = generate_html(locations_data, now_est)

    # Save locally
    output_path = os.environ.get("OUTPUT_PATH", "index.html")
    with open(output_path, "w") as f:
        f.write(html)
    print(f"💾 Saved to {output_path}", file=sys.stderr)

    # Push to GitHub if token is available
    if github_token:
        print("\n🚀 Pushing to GitHub Pages...", file=sys.stderr)
        push_to_github(html, github_token)
    else:
        print("\n⚠ No GITHUB_TOKEN set — skipping GitHub push.", file=sys.stderr)
        print("  Set GITHUB_TOKEN environment variable to enable auto-push.", file=sys.stderr)

    print("\n✨ Done!", file=sys.stderr)


if __name__ == "__main__":
    main()
