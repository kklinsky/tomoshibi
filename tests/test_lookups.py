import pytest

from tomoshibi import about
from tomoshibi.tools import ToolInputError, validate
from tomoshibi.weather import describe, pick_place

COLUMBUSES = [
    {"name": "Columbus", "admin1": "Georgia", "country": "United States", "country_code": "US", "population": 200000},
    {"name": "Columbus", "admin1": "Ohio", "country": "United States", "country_code": "US", "population": 900000},
    {"name": "Columbus", "admin1": "Indiana", "country": "United States", "country_code": "US", "population": 50000},
]


def test_pick_place_uses_state_abbreviation():
    assert pick_place(COLUMBUSES, "Columbus, GA")["admin1"] == "Georgia"
    assert pick_place(COLUMBUSES, "Columbus, Indiana")["admin1"] == "Indiana"


def test_pick_place_defaults_to_biggest():
    assert pick_place(COLUMBUSES, "Columbus")["admin1"] == "Ohio"
    assert pick_place([], "Nowhere") is None


def test_describe_reads_open_meteo():
    forecast = {
        "current": {"temperature_2m": 58.4, "apparent_temperature": 55.1, "weather_code": 2, "wind_speed_10m": 7.6},
        "daily": {"time": ["2026-10-22", "2026-10-23"], "weather_code": [61, 0],
                  "temperature_2m_max": [61.2, 66.0], "temperature_2m_min": [44.9, 47.0],
                  "precipitation_probability_max": [70, 5]},
    }
    out = describe(forecast, COLUMBUSES[1], "fahrenheit")
    assert out["place"] == "Columbus, Ohio"
    assert out["now"] == {"conditions": "partly cloudy", "temperature": "58°F", "feels_like": "55°F", "wind": "8 mph"}
    assert out["days"][0]["conditions"] == "light rain" and out["days"][0]["chance_of_rain_or_snow"] == "70%"


def test_validate_tool_input():
    schema = {"type": "object", "properties": {"location": {"type": "string"}}, "required": []}
    assert validate(schema, {}) == {}
    assert validate(schema, {"location": "Atlanta, GA"})["location"] == "Atlanta, GA"
    with pytest.raises(ToolInputError):
        validate(schema, {"location": 5})
    with pytest.raises(ToolInputError):
        validate(schema, {"city": "Atlanta"})


def test_lookups_follow_config_toggles():
    on = {"internet": {"web_search": {"enabled": True}, "weather": {"enabled": True}, "news": {"enabled": True}}}
    off = {"internet": {"web_search": {"enabled": False}, "weather": {"enabled": False}, "news": {"enabled": True}}}
    can_on, _ = about.capabilities(on, [])
    can_off, cannot_off = about.capabilities(off, [])
    assert any("weather" in c for c in can_on) and any("internet" in c for c in can_on)
    assert not any("weather" in c or "internet" in c or "news" in c for c in can_off)
    assert "Check today's news." in cannot_off  # news needs web search
