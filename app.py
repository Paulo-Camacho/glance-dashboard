#!/usr/bin/env python3
"""Glance: a small, self-hosted ambient dashboard."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template


ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DASHBOARD_DATA_DIR", ROOT / "data"))
CREDENTIALS_FILE = Path(
    os.environ.get("GOOGLE_CREDENTIALS_FILE", ROOT / "credentials.json")
)
TOKEN_FILE = Path(os.environ.get("GOOGLE_TOKEN_FILE", DATA_DIR / "google-token.json"))
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

app = Flask(__name__)
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def cached(key: str, ttl_seconds: int, loader):
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < ttl_seconds:
            return hit[1]
    value = loader()
    with _cache_lock:
        _cache[key] = (time.monotonic(), value)
    return value


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "GlanceDashboard/1.0"})
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.load(response)


def configured_location() -> str:
    return os.environ.get("DASHBOARD_LOCATION", "San Francisco, CA")


def geocode(location: str) -> dict[str, Any]:
    def load():
        query = urllib.parse.urlencode({"name": location, "count": 1, "language": "en"})
        data = fetch_json(f"https://geocoding-api.open-meteo.com/v1/search?{query}")
        if not data.get("results"):
            raise ValueError(f"Could not find a location matching {location!r}")
        return data["results"][0]

    return cached(f"geocode:{location}", 24 * 60 * 60, load)


def load_weather() -> dict[str, Any]:
    place = geocode(configured_location())
    units = os.environ.get("DASHBOARD_UNITS", "fahrenheit").lower()
    temperature_unit = "celsius" if units.startswith("c") else "fahrenheit"
    wind_unit = "kmh" if temperature_unit == "celsius" else "mph"
    params = urllib.parse.urlencode(
        {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "timezone": "auto",
            "temperature_unit": temperature_unit,
            "wind_speed_unit": wind_unit,
            "current": ",".join(
                [
                    "temperature_2m",
                    "apparent_temperature",
                    "relative_humidity_2m",
                    "weather_code",
                    "is_day",
                    "wind_speed_10m",
                ]
            ),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "sunrise",
                    "sunset",
                ]
            ),
            "forecast_days": 6,
        }
    )
    forecast = fetch_json(f"https://api.open-meteo.com/v1/forecast?{params}")
    daily = forecast["daily"]
    days = []
    for index, date in enumerate(daily["time"]):
        days.append(
            {
                "date": date,
                "code": daily["weather_code"][index],
                "high": daily["temperature_2m_max"][index],
                "low": daily["temperature_2m_min"][index],
                "precipitation": daily["precipitation_probability_max"][index],
            }
        )
    return {
        "location": place["name"],
        "region": place.get("admin1") or place.get("country"),
        "timezone": forecast["timezone"],
        "temperatureUnit": forecast["current_units"]["temperature_2m"],
        "windUnit": forecast["current_units"]["wind_speed_10m"],
        "current": {
            "temperature": forecast["current"]["temperature_2m"],
            "feelsLike": forecast["current"]["apparent_temperature"],
            "humidity": forecast["current"]["relative_humidity_2m"],
            "wind": forecast["current"]["wind_speed_10m"],
            "code": forecast["current"]["weather_code"],
            "isDay": bool(forecast["current"]["is_day"]),
        },
        "days": days,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def calendar_credentials():
    if not TOKEN_FILE.exists():
        return None

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE), CALENDAR_SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    return credentials if credentials.valid else None


def load_calendar_events() -> list[dict[str, Any]]:
    credentials = calendar_credentials()
    if not credentials:
        return []

    from googleapiclient.discovery import build

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=int(os.environ.get("CALENDAR_DAYS", "7")))
    service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
    result = (
        service.events()
        .list(
            calendarId=os.environ.get("GOOGLE_CALENDAR_ID", "primary"),
            timeMin=now.isoformat(),
            timeMax=horizon.isoformat(),
            maxResults=int(os.environ.get("CALENDAR_MAX_EVENTS", "12")),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = []
    for event in result.get("items", []):
        if event.get("status") == "cancelled":
            continue
        start = event.get("start", {})
        end = event.get("end", {})
        events.append(
            {
                "id": event.get("id"),
                "title": event.get("summary", "Untitled event"),
                "start": start.get("dateTime") or start.get("date"),
                "end": end.get("dateTime") or end.get("date"),
                "allDay": "date" in start,
                "location": event.get("location"),
                "link": event.get("htmlLink"),
            }
        )
    return events


def authorize_calendar() -> None:
    if not CREDENTIALS_FILE.exists():
        raise SystemExit(
            f"Missing {CREDENTIALS_FILE}. Download Desktop app OAuth credentials "
            "from Google Cloud and save them there first."
        )
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), CALENDAR_SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    print(f"Google Calendar connected. Token saved to {TOKEN_FILE}")


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/config")
def api_config():
    return jsonify(
        {
            "calendarConfigured": TOKEN_FILE.exists(),
            "calendarCredentialsPresent": CREDENTIALS_FILE.exists(),
            "location": configured_location(),
        }
    )


@app.get("/api/weather")
def api_weather():
    try:
        return jsonify(cached("weather", 10 * 60, load_weather))
    except Exception as error:
        app.logger.exception("Weather update failed")
        return jsonify({"error": str(error)}), 502


@app.get("/api/calendar")
def api_calendar():
    if not TOKEN_FILE.exists():
        return jsonify({"connected": False, "events": []})
    try:
        return jsonify(
            {
                "connected": True,
                "events": cached("calendar", 3 * 60, load_calendar_events),
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as error:
        app.logger.exception("Calendar update failed")
        return jsonify({"connected": True, "events": [], "error": str(error)}), 502


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-calendar", action="store_true")
    parser.add_argument("--host", default=os.environ.get("DASHBOARD_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DASHBOARD_PORT", "8080")))
    args = parser.parse_args()
    if args.authorize_calendar:
        authorize_calendar()
        return
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
