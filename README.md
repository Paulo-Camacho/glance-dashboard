# Glance

A quiet, self-hosted dashboard designed to stay open on a dedicated screen. The backend keeps OAuth tokens off the browser and the frontend is deliberately framework-free, so the laptop has very little to run.

It shows:

- **Weather at a glance** — a large current temperature and sky condition, with feels-like, humidity, wind, the live UV index (with a plain-language level), and the next sunrise or sunset.
- **Today's sky outlook** — whether the day is clearing up or clouding over, with hourly icons through sunset. Hidden once the sun is down.
- **A five-day forecast** with highs, lows, and rain chance.
- **Upcoming Google Calendar events** (optional, read-only).
- **Themes** — pick from Forest, Dracula, Nord, Solarized Dark, Monokai, Gruvbox, One Dark, or Tokyo Night using the palette button in the top right. Your choice is remembered in the browser.

## Run it

Python 3.10.7 or newer is recommended.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
DASHBOARD_LOCATION="Portland, OR" .venv/bin/python app.py
```

Open <http://127.0.0.1:8080>. Weather works without an API key. Set `DASHBOARD_UNITS=celsius` for metric units.

## Connect Google Calendar

1. In [Google Cloud](https://console.cloud.google.com/), create a project and enable the Google Calendar API.
2. Configure the Google Auth consent screen. For a personal Gmail account, select **External** and add your own email as a test user.
3. Create an OAuth client with application type **Desktop app**.
4. Download its JSON file and save it in this folder as `credentials.json`.
5. Authorize read-only access:

   ```bash
   .venv/bin/python app.py --authorize-calendar
   ```

The browser will ask for consent once. The resulting refresh token is stored in `data/google-token.json`, which is excluded from source control. Restart the dashboard and events will appear.

### Showing more than your main calendar

By default only your primary calendar is read. To include everything you subscribe to — Canvas or other iCal feeds, shared and team calendars:

```bash
GOOGLE_CALENDAR_ID=all .venv/bin/python app.py
```

`all` follows the calendars you have enabled in Google Calendar; anything you have unchecked there is skipped. To pick specific ones instead, pass a comma-separated list of calendar IDs (Google Calendar → hover a calendar → **Settings** → **Integrate calendar** → **Calendar ID**):

```bash
GOOGLE_CALENDAR_ID="primary,abc123@group.calendar.google.com" .venv/bin/python app.py
```

Events from all selected calendars are merged and sorted together, and each row shows which calendar it came from. A calendar that can't be read is skipped rather than breaking the card.

## Start automatically

Edit `dashboard.service` if the project is not at `~/projects/dashboard` or you want a different city. Then install it as a user service:

```bash
mkdir -p ~/.config/systemd/user
cp dashboard.service ~/.config/systemd/user/glance-dashboard.service
systemctl --user daemon-reload
systemctl --user enable --now glance-dashboard.service
```

To keep it alive after logout, an administrator can run `sudo loginctl enable-linger "$USER"` once. For the display, open Chromium in app/kiosk mode at login:

```bash
chromium --kiosk --noerrdialogs --disable-infobars http://127.0.0.1:8080
```

## Configuration

All settings are environment variables; see `.env.example`. Use `DASHBOARD_HOST=0.0.0.0` only if you want other devices on your local network to reach it. Calendar access is read-only.

## Growing it

New data sources belong behind `/api/...` routes in `app.py`, while each visual module is a separate card in `templates/index.html`. This keeps credentials server-side and avoids coupling future widgets to the weather or calendar code.
