const palette = [
  { color: "#7459e8", soft: "#f0ecff" },
  { color: "#eb6593", soft: "#fff0f5" },
  { color: "#239dba", soft: "#e8f8fc" },
  { color: "#cf8c27", soft: "#fff5df" },
  { color: "#1ca785", soft: "#e5f8f2" },
  { color: "#d451aa", soft: "#ffedf8" },
  { color: "#3976d2", soft: "#edf4ff" },
  { color: "#d96a43", soft: "#fff0e9" },
  { color: "#57934f", soft: "#eff8ec" },
  { color: "#765b9f", soft: "#f4efff" },
];

const feed = document.querySelector("#message-feed");
const emptyState = document.querySelector("#empty-state");
const connectionPill = document.querySelector("#connection-pill");
const connectionLabel = document.querySelector("#connection-label");
const feedCount = document.querySelector("#feed-count");
const jumpButton = document.querySelector("#jump-button");

const seenIds = new Set();
const seenOrder = [];
let receivedCount = 0;

function speakerStyle(sid) {
  if (sid === null || sid === undefined) {
    return { color: "#8b89a2", soft: "#f0eff4" };
  }
  return palette[(Math.max(1, Number(sid)) - 1) % palette.length];
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

function appendMessage(record, eventId) {
  if (!rememberEvent(eventId)) return;
  emptyState.hidden = true;

  const style = speakerStyle(record.sid);
  const message = document.createElement("article");
  message.className = "message";
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
  bubble.textContent = record.content || "Transcript text unavailable.";

  meta.append(name, time);
  body.append(meta, bubble);
  message.append(avatar, body);
  feed.append(message);

  receivedCount += 1;
  feedCount.textContent = `${receivedCount} ${receivedCount === 1 ? "message" : "messages"}`;
  feed.scrollTop = feed.scrollHeight;
}

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
