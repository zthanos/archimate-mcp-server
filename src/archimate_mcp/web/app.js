const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("chat-form");
const promptEl = document.getElementById("prompt");
const statusEl = document.getElementById("status");
const runInfoEl = document.getElementById("run-info");
const toolLogEl = document.getElementById("tool-log");
const streamModeEl = document.getElementById("stream-mode");

let sessionId = null;

async function ensureSession() {
  if (sessionId) return sessionId;
  const response = await fetch("/api/session", { method: "POST" });
  const data = await response.json();
  sessionId = data.session_id;
  return sessionId;
}

function appendMessage(role, text) {
  const item = document.createElement("article");
  item.className = `message ${role}`;
  item.innerHTML = `<div class="badge">${role}</div><pre>${escapeHtml(text)}</pre>`;
  messagesEl.appendChild(item);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderRunInfo(data) {
  const lines = [
    `session_id: ${data.session_id}`,
    `mcp_url: ${data.mcp_url || "-"}`,
    `skill_path: ${data.skill_path || "-"}`,
    `export_path: ${data.export_path || "-"}`,
  ];
  runInfoEl.textContent = lines.join("\n");
}

function renderToolLog(entries) {
  if (!entries || entries.length === 0) {
    toolLogEl.textContent = "No tool calls yet.";
    return;
  }

  const text = entries
    .map((entry, index) => {
      const parts = [
        `${index + 1}. ${entry.name}`,
        `args: ${JSON.stringify(entry.arguments, null, 2)}`,
      ];
      if (entry.error) {
        parts.push(`error: ${entry.error}`);
      } else {
        parts.push(`result: ${JSON.stringify(entry.result, null, 2)}`);
      }
      return parts.join("\n");
    })
    .join("\n\n");

  toolLogEl.textContent = text;
}

async function readEventStream(response, handlers) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const rawEvent of events) {
      const lines = rawEvent.split("\n");
      let eventName = "message";
      let data = "";

      for (const line of lines) {
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          data += line.slice(5).trim();
        }
      }

      if (!data) continue;
      handlers(eventName, JSON.parse(data));
    }
  }
}

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = promptEl.value.trim();
  if (!message) return;

  appendMessage("user", message);
  promptEl.value = "";
  statusEl.textContent = "Running...";

  try {
    await ensureSession();
    const stream = streamModeEl.checked;
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message, stream }),
    });

    if (stream) {
      if (!response.ok) {
        const data = await response.json();
        appendMessage("assistant", `Error: ${data.error || "Unknown error"}`);
        renderRunInfo(data);
        return;
      }

      let finalData = null;
      let streamedToolLogs = [];

      await readEventStream(response, (eventName, data) => {
        if (eventName === "plan") {
          toolLogEl.textContent = `Planned tools:\n${(data.planned_tools || []).join("\n")}`;
        } else if (eventName === "tool") {
          streamedToolLogs.push(data);
          renderToolLog(streamedToolLogs);
        } else if (eventName === "status") {
          statusEl.textContent = data.message || "Running...";
        } else if (eventName === "final") {
          finalData = data;
        } else if (eventName === "error") {
          appendMessage("assistant", `Error: ${data.error || "Unknown error"}`);
          renderRunInfo(data);
        }
      });

      if (finalData) {
        appendMessage("assistant", finalData.assistant_message);
        renderRunInfo(finalData);
        renderToolLog(finalData.tool_logs || streamedToolLogs);
      }
    } else {
      const data = await response.json();
      if (!response.ok) {
        appendMessage("assistant", `Error: ${data.error || "Unknown error"}`);
        renderRunInfo(data);
        return;
      }

      appendMessage("assistant", data.assistant_message);
      renderRunInfo(data);
      renderToolLog(data.tool_logs);
    }
  } catch (error) {
    appendMessage("assistant", `Error: ${error.message}`);
  } finally {
    statusEl.textContent = "Ready";
  }
});
