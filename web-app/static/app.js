const palette = [
  { color: "#7459e8", soft: "#f0ecff", darkColor: "#b49bff", darkSoft: "rgba(116, 89, 232, 0.16)" },
  { color: "#eb6593", soft: "#fff0f5", darkColor: "#ff8fb8", darkSoft: "rgba(235, 101, 147, 0.15)" },
  { color: "#239dba", soft: "#e8f8fc", darkColor: "#65dfff", darkSoft: "rgba(35, 157, 186, 0.17)" },
  { color: "#cf8c27", soft: "#fff5df", darkColor: "#ffd166", darkSoft: "rgba(207, 140, 39, 0.16)" },
  { color: "#1ca785", soft: "#e5f8f2", darkColor: "#50e5bd", darkSoft: "rgba(28, 167, 133, 0.16)" },
  { color: "#d451aa", soft: "#ffedf8", darkColor: "#ff89db", darkSoft: "rgba(212, 81, 170, 0.15)" },
  { color: "#3976d2", soft: "#edf4ff", darkColor: "#84aaff", darkSoft: "rgba(57, 118, 210, 0.17)" },
  { color: "#d96a43", soft: "#fff0e9", darkColor: "#ff9a70", darkSoft: "rgba(217, 106, 67, 0.16)" },
  { color: "#57934f", soft: "#eff8ec", darkColor: "#98ed88", darkSoft: "rgba(87, 147, 79, 0.16)" },
  { color: "#765b9f", soft: "#f4efff", darkColor: "#d3a6ff", darkSoft: "rgba(118, 91, 159, 0.17)" },
];

const feed = document.querySelector("#message-feed");
const emptyState = document.querySelector("#empty-state");
const connectionPill = document.querySelector("#connection-pill");
const connectionLabel = document.querySelector("#connection-label");
const themeToggle = document.querySelector("#theme-toggle");
const themeToggleIcon = document.querySelector("#theme-toggle-icon");
const themeToggleLabel = document.querySelector("#theme-toggle-label");
const feedCount = document.querySelector("#feed-count");
const jumpButton = document.querySelector("#jump-button");

const seenIds = new Set();
const seenOrder = [];
let messageCount = 0;

function speakerStyle(sid) {
  const isDark = document.documentElement.dataset.theme === "dark";
  if (sid === null || sid === undefined) {
    return isDark
      ? { color: "#b7b4ca", soft: "rgba(183, 180, 202, 0.12)" }
      : { color: "#8b89a2", soft: "#f0eff4" };
  }
  const speaker = palette[(Math.max(1, Number(sid)) - 1) % palette.length];
  return isDark
    ? { color: speaker.darkColor, soft: speaker.darkSoft }
    : speaker;
}

function formatTime(value) {
  const date = new Date(`${value}Z`);
  if (Number.isNaN(date.getTime())) return "Time unavailable";
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function setConnection(state, label) {
  connectionPill.dataset.state = state;
  connectionPill.setAttribute("aria-label", label);
  connectionLabel.textContent = label;
}

function rememberEvent(id) {
  if (!id) return true;
  if (seenIds.has(id)) return false;
  seenIds.add(id);
  seenOrder.push(id);
  if (seenOrder.length > 2000) {
    seenIds.delete(seenOrder.shift());
  }
  return true;
}

function createZapIndicator() {
  const indicator = document.createElement("span");
  indicator.className = "zap-indicator";
  indicator.setAttribute("role", "img");
  indicator.setAttribute("aria-label", "Zap sent");
  indicator.textContent = "⚡";
  return indicator;
}

function appendMessage(record, eventId) {
  if (!rememberEvent(eventId)) return;
  const shouldScrollToLatest =
    feed.scrollHeight - feed.clientHeight - feed.scrollTop <= 8;
  emptyState.hidden = true;

  const speakerId = String(record.sid ?? "");
  const content = record.content || "Transcript text unavailable.";
  const previousMessage = feed.lastElementChild;
  if (
    previousMessage?.classList.contains("message") &&
    previousMessage.dataset.speakerId === speakerId
  ) {
    const bubble = previousMessage.querySelector(".message-bubble");
    bubble.textContent += `\n${content}`;
    const messageContent = previousMessage.querySelector(".message-content");
    if (record.zap_sent === true && !messageContent.querySelector(".zap-indicator")) {
      messageContent.append(createZapIndicator());
    }
  } else {
    const style = speakerStyle(record.sid);
    const message = document.createElement("article");
    message.className = "message";
    message.dataset.speakerId = speakerId;
    message.style.setProperty("--speaker-color", style.color);
    message.style.setProperty("--speaker-soft", style.soft);

    const avatar = document.createElement("span");
    avatar.className = "speaker-avatar";
    avatar.textContent = record.sid === null ? "?" : `S${record.sid}`;
    avatar.setAttribute("aria-hidden", "true");

    const body = document.createElement("div");
    body.className = "message-body";
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const name = document.createElement("span");
    name.className = "speaker-name";
    name.textContent = record.sid === null ? "Unassigned speaker" : `Speaker ${record.sid}`;
    const time = document.createElement("time");
    time.className = "message-time";
    time.dateTime = `${record.time}Z`;
    time.textContent = formatTime(record.time);
    time.title = new Date(`${record.time}Z`).toLocaleString();
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.textContent = content;

    meta.append(name, time);
    const messageContent = document.createElement("div");
    messageContent.className = "message-content";
    messageContent.append(bubble);
    if (record.zap_sent === true) {
      messageContent.append(createZapIndicator());
    }
    body.append(meta, messageContent);
    message.append(avatar, body);
    feed.append(message);

    messageCount += 1;
    feedCount.textContent = `${messageCount} ${messageCount === 1 ? "message" : "messages"}`;
  }

  if (shouldScrollToLatest) {
    feed.scrollTop = feed.scrollHeight;
  }
}

function setTheme(theme) {
  const isDark = theme === "dark";
  document.documentElement.dataset.theme = isDark ? "dark" : "light";
  themeToggle.setAttribute("aria-pressed", String(isDark));
  themeToggleIcon.textContent = isDark ? "☀" : "☾";
  themeToggleLabel.textContent = isDark ? "Light mode" : "Dark mode";
  document.querySelector("#theme-color").content = isDark ? "#080910" : "#f7f5ff";
  localStorage.setItem("well-actually-theme", isDark ? "dark" : "light");

  for (const message of feed.querySelectorAll(".message")) {
    const speakerId = message.dataset.speakerId;
    const sid = speakerId === "" ? null : Number(speakerId);
    const style = speakerStyle(sid);
    message.style.setProperty("--speaker-color", style.color);
    message.style.setProperty("--speaker-soft", style.soft);
  }
}

setTheme(localStorage.getItem("well-actually-theme") ?? "dark");
themeToggle.addEventListener("click", () => {
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});

jumpButton.addEventListener("click", () => {
  feed.scrollTo({ top: feed.scrollHeight, behavior: "smooth" });
});

const stream = new EventSource("/api/speech-log/stream");

stream.addEventListener("open", () => {
  setConnection("connected", "Database stream connected");
});

stream.addEventListener("connected", (event) => {
  const data = JSON.parse(event.data);
  setConnection("connected", data.initial_count ? "Live · recent speech loaded" : "Live · waiting for speech");
});

stream.addEventListener("speech", (event) => {
  try {
    appendMessage(JSON.parse(event.data), event.lastEventId);
    setConnection("connected", "Database stream connected");
  } catch {
    setConnection("error", "Received an unreadable speech event");
  }
});

stream.addEventListener("dashboard-error", (event) => {
  let message = "Database connection interrupted. Reconnecting…";
  try {
    message = JSON.parse(event.data).message || message;
  } catch {
    // Keep the safe default status text.
  }
  setConnection("reconnecting", message);
});

stream.addEventListener("error", () => {
  if (stream.readyState === EventSource.CONNECTING) {
    setConnection("reconnecting", "Reconnecting to speech log");
  } else if (stream.readyState === EventSource.CLOSED) {
    setConnection("error", "Speech stream closed");
  }
});
