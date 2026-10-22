"""Weather from Open-Meteo (https://open-meteo.com): free, no API key, no account.

Exposed to the AI as the `get_weather` tool. Results are kept for 10 minutes so repeated
questions ("is it going to rain?" three times in an hour) don't refetch.
"""

import json
import time
import urllib.parse
import urllib.request

from tomoshibi.tools import Tool

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_SECONDS = 600

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

# WMO weather interpretation codes, in plain words.
CONDITIONS = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy", 45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle",
    57: "freezing drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains", 80: "rain showers", 81: "rain showers", 82: "heavy rain showers",
    85: "snow showers", 86: "heavy snow showers", 95: "thunderstorms",
    96: "thunderstorms with hail", 99: "thunderstorms with hail",
}


def _get_json(url: str, params: dict) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(full, timeout=8) as resp:
        return json.load(resp)


def pick_place(results: list[dict], query: str) -> dict | None:
    """Choose the geocoding result that best matches "City, State/Country"."""
    if not results:
        return None
    parts = [p.strip() for p in query.split(",")]
    if len(parts) > 1:
        hint = parts[1]
        hint = US_STATES.get(hint.upper(), hint).lower()
        for r in results:
            if hint in (str(r.get("admin1", "")).lower(), str(r.get("country", "")).lower(),
                        str(r.get("country_code", "")).lower()):
                return r
    return max(results, key=lambda r: r.get("population") or 0)


def describe(forecast: dict, place: dict, units: str) -> dict:
    """Trim Open-Meteo's response to what's worth saying out loud."""
    deg = "°F" if units == "fahrenheit" else "°C"
    cur = forecast.get("current", {})
    daily = forecast.get("daily", {})
    days = []
    for i, day in enumerate(daily.get("time", [])[:4]):
        days.append({
            "date": day,
            "conditions": CONDITIONS.get(daily["weather_code"][i], "mixed"),
            "high": f"{round(daily['temperature_2m_max'][i])}{deg}",
            "low": f"{round(daily['temperature_2m_min'][i])}{deg}",
            "chance_of_rain_or_snow": f"{daily['precipitation_probability_max'][i]}%",
        })
    name = ", ".join(x for x in (place.get("name"), place.get("admin1")) if x)
    return {
        "place": name,
        "now": {
            "conditions": CONDITIONS.get(cur.get("weather_code"), "mixed"),
            "temperature": f"{round(cur.get('temperature_2m', 0))}{deg}",
            "feels_like": f"{round(cur.get('apparent_temperature', 0))}{deg}",
            "wind": f"{round(cur.get('wind_speed_10m', 0))} {'mph' if units == 'fahrenheit' else 'km/h'}",
        },
        "days": days,
    }


class Weather:
    def __init__(self, default_location: str, units: str = "fahrenheit"):
        self.default_location = default_location
        self.units = units
        self._cache: dict[str, tuple[float, dict]] = {}

    def lookup(self, location: str | None = None) -> dict:
        query = (location or self.default_location or "").strip()
        if not query:
            return {"error": "No location given and no home location is set."}
        key = query.lower()
        if key in self._cache and time.monotonic() - self._cache[key][0] < CACHE_SECONDS:
            return self._cache[key][1]
        city = query.split(",")[0].strip()
        found = _get_json(GEOCODE_URL, {"name": city, "count": 10, "language": "en", "format": "json"})
        place = pick_place(found.get("results") or [], query)
        if not place:
            return {"error": f"Couldn't find a place called {query}."}
        forecast = _get_json(FORECAST_URL, {
            "latitude": place["latitude"], "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "temperature_unit": self.units,
            "wind_speed_unit": "mph" if self.units == "fahrenheit" else "kmh",
            "timezone": "auto", "forecast_days": 4,
        })
        result = describe(forecast, place, self.units)
        self._cache[key] = (time.monotonic(), result)
        return result

    def tool(self) -> Tool:
        def run(args: dict) -> str:
            try:
                return json.dumps(self.lookup(args.get("location")))
            except OSError as e:
                return json.dumps({"error": f"The weather service couldn't be reached ({e})."})

        home = self.default_location or "home"
        return Tool(
            name="get_weather",
            description=(
                "Current weather and the forecast for the next few days (today first). "
                f"Leave location out for home ({home}). For somewhere else, give "
                "'City, State' or 'City, Country'."
            ),
            input_schema={
                "type": "object",
                "properties": {"location": {"type": "string", "description": "e.g. 'Atlanta, GA'"}},
                "required": [],
                "additionalProperties": False,
            },
            run=run,
        )
