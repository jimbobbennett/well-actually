const palette = [
  { color: "#b49bff", soft: "rgba(116, 89, 232, 0.16)" },
  { color: "#ff8fb8", soft: "rgba(235, 101, 147, 0.15)" },
  { color: "#65dfff", soft: "rgba(35, 157, 186, 0.17)" },
  { color: "#ffd166", soft: "rgba(207, 140, 39, 0.16)" },
  { color: "#50e5bd", soft: "rgba(28, 167, 133, 0.16)" },
  { color: "#ff89db", soft: "rgba(212, 81, 170, 0.15)" },
  { color: "#84aaff", soft: "rgba(57, 118, 210, 0.17)" },
  { color: "#ff9a70", soft: "rgba(217, 106, 67, 0.16)" },
  { color: "#98ed88", soft: "rgba(87, 147, 79, 0.16)" },
  { color: "#d3a6ff", soft: "rgba(118, 91, 159, 0.17)" },
];

const feed = document.querySelector("#message-feed");
const emptyState = document.querySelector("#empty-state");
const connectionLabel = document.querySelector("#connection-label");
const feedCount = document.querySelector("#feed-count");
const jumpButton = document.querySelector("#jump-button");

const seenIds = new Set();
const seenOrder = [];
const recordsByEventId = new Map();
const messageStates = new WeakMap();
let messageCount = 0;

function speakerStyle(sid) {
  if (sid === null || sid === undefined) {
    return { color: "#b7b4ca", soft: "rgba(183, 180, 202, 0.12)" };
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

function setConnection(label) {
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

function setZapSent(recordState, zapSent, animate = false) {
  if (recordState.zapSent === zapSent) return;
  recordState.zapSent = zapSent;
  const { bubbleState } = recordState;
  bubbleState.zapCount += zapSent ? 1 : -1;
  const isShocked = bubbleState.zapCount > 0;
  bubbleState.bubble.classList.toggle("message-bubble--shocked", isShocked);

  const indicator = bubbleState.messageContent.querySelector(".zap-indicator");
  if (isShocked && !indicator) {
    bubbleState.messageContent.append(createZapIndicator());
  } else if (!isShocked && indicator) {
    indicator.remove();
  }

  if (animate && zapSent) {
    bubbleState.bubble.classList.remove("message-bubble--zap-detected");
    void bubbleState.bubble.offsetWidth;
    bubbleState.bubble.classList.add("message-bubble--zap-detected");
  }
}

function appendMessage(record, eventId) {
  if (!rememberEvent(eventId)) return;
  const shouldScrollToLatest =
    feed.scrollHeight - feed.clientHeight - feed.scrollTop <= 8;
  emptyState.hidden = true;

  const speakerId = String(record.sid ?? "");
  const content = record.content || "Transcript text unavailable.";
  const previousMessage = feed.lastElementChild;
  let bubbleState;
  if (
    previousMessage?.classList.contains("message") &&
    previousMessage.dataset.speakerId === speakerId
  ) {
    const bubble = previousMessage.querySelector(".message-bubble");
    bubble.textContent += `\n${content}`;
    bubbleState = messageStates.get(previousMessage);
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
    body.append(meta, messageContent);
    message.append(avatar, body);
    feed.append(message);
    bubbleState = { bubble, messageContent, zapCount: 0 };
    messageStates.set(message, bubbleState);
    bubble.addEventListener("animationend", (animationEvent) => {
      if (animationEvent.animationName === "zap-impact") {
        bubble.classList.remove("message-bubble--zap-detected");
      }
    });

    messageCount += 1;
    feedCount.textContent = `${messageCount} ${messageCount === 1 ? "message" : "messages"}`;
  }

  const recordState = { bubbleState, zapSent: false };
  recordsByEventId.set(eventId || record.time, recordState);
  setZapSent(recordState, record.zap_sent === true);

  if (shouldScrollToLatest) {
    feed.scrollTop = feed.scrollHeight;
  }
}

function updateMessage(record) {
  const recordState = recordsByEventId.get(record.time);
  if (!recordState) return;
  const zapSent = record.zap_sent === true;
  setZapSent(recordState, zapSent, zapSent && !recordState.zapSent);
}

jumpButton.addEventListener("click", () => {
  feed.scrollTo({ top: feed.scrollHeight, behavior: "smooth" });
});

const stream = new EventSource("/api/speech-log/stream");

stream.addEventListener("open", () => {
  setConnection("Database stream connected");
});

stream.addEventListener("connected", (event) => {
  const data = JSON.parse(event.data);
  setConnection(data.initial_count ? "Live · recent speech loaded" : "Live · waiting for speech");
});

stream.addEventListener("speech", (event) => {
  try {
    appendMessage(JSON.parse(event.data), event.lastEventId);
    setConnection("Database stream connected");
  } catch {
    setConnection("Received an unreadable speech event");
  }
});

stream.addEventListener("speech-update", (event) => {
  try {
    updateMessage(JSON.parse(event.data));
  } catch {
    setConnection("Received an unreadable speech update");
  }
});

stream.addEventListener("dashboard-error", (event) => {
  let message = "Database connection interrupted. Reconnecting…";
  try {
    message = JSON.parse(event.data).message || message;
  } catch {
    // Keep the safe default status text.
  }
  setConnection(message);
});

stream.addEventListener("error", () => {
  if (stream.readyState === EventSource.CONNECTING) {
    setConnection("Reconnecting to speech log");
  } else if (stream.readyState === EventSource.CLOSED) {
    setConnection("Speech stream closed");
  }
});
