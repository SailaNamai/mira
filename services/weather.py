# services.weather.py

import requests
from datetime import datetime
debug = True

def get_weather(lat, lon, date=None, debug=debug):
    weather_full = get_weather_summary(lat, lon, date, debug=debug)
    weather_formated = format_weather_summary(weather_full)
    return weather_formated

def get_weather_summary(lat, lon, date=None, debug=debug):
    """
    Gets hourly weather and daily sun times from Open-Meteo for a given location and date.
    Returns a structured dictionary with sun times and hourly weather data.
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    else:
        date = _normalize_date(date)

    base_url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,precipitation,wind_speed_10m,snowfall,snow_depth",
        "daily": "sunrise,sunset",
        "timezone": "auto",
        "start_date": date,
        "end_date": date
    }

    try:
        response = requests.get(base_url, params=params)
        data = response.json()

        # Extract sun times
        daily = data.get("daily", {})
        sunrise = daily.get("sunrise", [None])[0]
        sunset = daily.get("sunset", [None])[0]

        # Extract hourly weather
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        summary = {
            "sun_times": {"date": date, "sunrise": sunrise, "sunset": sunset},
            "hourly": []
        }

        for i, time in enumerate(times):
            if time.startswith(date):
                entry = {
                    "time": time[-5:],
                    "temperature_c": hourly["temperature_2m"][i],
                    "precipitation_mm": hourly["precipitation"][i],
                    "wind_speed_kmh": hourly["wind_speed_10m"][i],
                    "snowfall_cm": hourly.get("snowfall", [0.0])[i],
                    "snow_depth_cm": hourly.get("snow_depth", [0.0])[i]
                }
                summary["hourly"].append(entry)
        if debug:
            print(summary)
        return summary
    except Exception as e:
        print("[Weather] Failed:", e)
        return None

def format_weather_summary(summary):
    """
    Formats weather summary into readable hourly lines with contextual labels.
    """
    def parse_hour(time_str):
        return int(time_str.split(":")[0])

    def get_period(hour, sunrise_hour, sunset_hour):
        if hour < sunrise_hour:
            return "Before Sunrise"
        elif hour == sunrise_hour:
            return "Sunrise"
        elif hour < 12:
            return "Morning"
        elif hour < 15:
            return "Midday"
        elif hour < sunset_hour:
            return "Afternoon"
        elif hour == sunset_hour:
            return "Sundown"
        else:
            return "After Sundown"

    sunrise_hour = parse_hour(summary["sun_times"]["sunrise"][-5:])
    sunset_hour = parse_hour(summary["sun_times"]["sunset"][-5:])
    dt = datetime.strptime(summary["sun_times"]["date"], "%Y-%m-%d")
    weekday = dt.strftime("%A")
    date_str = dt.strftime("%d.%m.%Y")

    lines = [f"- Weather forecast for {weekday}, {date_str}:"]
    for entry in summary["hourly"]:
        hour = parse_hour(entry["time"])
        period = get_period(hour, sunrise_hour, sunset_hour)

        line = f"\t- {entry['time']} to {entry['time'][:-2]}59: {period}, Temperature {entry['temperature_c']}°C"

        if entry["precipitation_mm"] > 0:
            line += f", possible Precipitation {entry['precipitation_mm']} mm"
        if entry["snowfall_cm"] > 0:
            line += f", possible Snowfall {entry['snowfall_cm']} cm"
        if entry["snow_depth_cm"] > 0:
            line += f", estimated Snow depth {entry['snow_depth_cm']} cm"
        if entry["wind_speed_kmh"] > 0:
            line += f", Winds up to {entry['wind_speed_kmh']} km/h"
        lines.append(line)
    return "\n".join(lines)

def _normalize_date(date_str):
    """Converts various date formats to YYYY-MM-DD."""
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y%m%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {date_str}")

# Example coordinates for Bremen lat=53.07, lon=8.80,
if __name__ == "__main__":
    weather = get_weather(lat=53.07, lon=8.80, date=None)
    print(weather)