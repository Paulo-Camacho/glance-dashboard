const $ = (selector) => document.querySelector(selector);

const weatherCodes = {
  0: ["Clear", "☀"], 1: ["Mostly clear", "☀"], 2: ["Partly cloudy", "◒"],
  3: ["Overcast", "☁"], 45: ["Foggy", "≋"], 48: ["Icy fog", "≋"],
  51: ["Light drizzle", "☂"], 53: ["Drizzle", "☂"], 55: ["Heavy drizzle", "☂"],
  56: ["Freezing drizzle", "☂"], 57: ["Freezing drizzle", "☂"],
  61: ["Light rain", "☂"], 63: ["Rain", "☂"], 65: ["Heavy rain", "☂"],
  66: ["Freezing rain", "☂"], 67: ["Freezing rain", "☂"],
  71: ["Light snow", "✦"], 73: ["Snow", "✦"], 75: ["Heavy snow", "✦"], 77: ["Snow grains", "✦"],
  80: ["Rain showers", "☂"], 81: ["Rain showers", "☂"], 82: ["Heavy showers", "☂"],
  85: ["Snow showers", "✦"], 86: ["Heavy snow", "✦"],
  95: ["Thunderstorms", "ϟ"], 96: ["Storms with hail", "ϟ"], 99: ["Storms with hail", "ϟ"]
};

function condition(code, isDay = true) {
  const value = weatherCodes[code] || ["Changing skies", "◒"];
  if (!isDay && (code === 0 || code === 1)) return [value[0], "☾"];
  return value;
}

function tick() {
  const now = new Date();
  $("#clock").textContent = new Intl.DateTimeFormat([], { hour: "numeric", minute: "2-digit" }).format(now);
  $("#date").textContent = new Intl.DateTimeFormat([], { weekday: "long", month: "long", day: "numeric" }).format(now);
  $("#day-number").textContent = now.getDate();
  $("#day-name").textContent = new Intl.DateTimeFormat([], { weekday: "long" }).format(now);
  $("#month-name").textContent = new Intl.DateTimeFormat([], { month: "long", year: "numeric" }).format(now);
}

async function getJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function renderWeather(data) {
  const current = data.current;
  const [label, icon] = condition(current.code, current.isDay);
  $("#location").textContent = [data.location, data.region].filter(Boolean).join(", ");
  $("#temperature").textContent = `${Math.round(current.temperature)}°`;
  $("#condition").textContent = label;
  $("#weather-icon").textContent = icon;
  $("#feels-like").textContent = `${Math.round(current.feelsLike)}°`;
  $("#humidity").textContent = `${current.humidity}%`;
  $("#wind").textContent = `${Math.round(current.wind)} ${data.windUnit}`;
  $("#forecast").innerHTML = data.days.slice(1, 6).map((day) => {
    const [, dayIcon] = condition(day.code);
    const name = new Intl.DateTimeFormat([], { weekday: "short", timeZone: "UTC" }).format(new Date(`${day.date}T12:00:00Z`));
    return `<div class="forecast-day">
      <span class="forecast-name">${name}</span><span class="forecast-icon">${dayIcon}</span>
      <span class="forecast-temp">${Math.round(day.high)}° <span>${Math.round(day.low)}°</span></span>
      <span class="rain">${day.precipitation ?? 0}% rain</span>
    </div>`;
  }).join("");
}

function dateKey(value) { return value.slice(0, 10); }

function eventTime(event) {
  if (event.allDay) return { day: "All day", time: "" };
  const start = new Date(event.start);
  return {
    day: new Intl.DateTimeFormat([], { weekday: "short" }).format(start),
    time: new Intl.DateTimeFormat([], { hour: "numeric", minute: "2-digit" }).format(start)
  };
}

function renderEvents(data) {
  const status = $("#calendar-status");
  status.classList.toggle("online", data.connected && !data.error);
  if (!data.connected) {
    $("#events").innerHTML = `<div class="empty"><strong>Connect Google Calendar</strong><p>Add your OAuth <code>credentials.json</code>, then run <code>python app.py --authorize-calendar</code>.</p></div>`;
    $("#next-up").innerHTML = `<span class="eyebrow">Next up</span><p>Connect your calendar to see what’s ahead.</p>`;
    return;
  }
  if (data.error) throw new Error(data.error);
  if (!data.events.length) {
    $("#events").innerHTML = `<div class="empty"><strong>Your week is clear</strong><p>No upcoming events found in the next seven days.</p></div>`;
    $("#next-up").innerHTML = `<span class="eyebrow">Next up</span><p>Nothing scheduled. Enjoy the space.</p>`;
    return;
  }
  const today = dateKey(new Date().toISOString());
  $("#events").innerHTML = data.events.slice(0, 5).map((event) => {
    const when = eventTime(event);
    const eventDate = dateKey(event.start);
    const day = eventDate === today ? "Today" : when.day;
    const tag = event.link ? "a" : "div";
    const link = event.link ? ` href="${event.link}" target="_blank" rel="noreferrer"` : "";
    return `<${tag} class="event"${link}><div class="event-time"><strong>${day}</strong>${when.time}</div><span class="event-bar"></span><div class="event-copy"><div class="event-title">${escapeHtml(event.title)}</div>${event.location ? `<div class="event-meta">${escapeHtml(event.location)}</div>` : ""}</div></${tag}>`;
  }).join("");
  const first = data.events[0], when = eventTime(first);
  $("#next-up").innerHTML = `<span class="eyebrow">Next up</span><p>${escapeHtml(first.title)}<small>${first.allDay ? "All day" : `${when.day} · ${when.time}`}</small></p>`;
}

function escapeHtml(value) {
  const node = document.createElement("span"); node.textContent = value; return node.innerHTML;
}

function showError(target, message) {
  $(target).innerHTML = `<div class="empty"><strong>Couldn’t update</strong><p>${escapeHtml(message)}</p></div>`;
}

async function refresh() {
  const results = await Promise.allSettled([getJson("/api/weather"), getJson("/api/calendar")]);
  if (results[0].status === "fulfilled") renderWeather(results[0].value);
  else { $("#condition").textContent = "Weather unavailable"; $("#location").textContent = results[0].reason.message; }
  if (results[1].status === "fulfilled") renderEvents(results[1].value);
  else showError("#events", results[1].reason.message);
  $("#last-updated").textContent = `Updated ${new Intl.DateTimeFormat([], { hour: "numeric", minute: "2-digit" }).format(new Date())}`;
}

tick();
refresh();
setInterval(tick, 1000);
setInterval(refresh, 3 * 60 * 1000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
