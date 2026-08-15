const API = {
  status: "/api/status",
  chat: "/api/chat",
  stream: "/api/chat/stream",
  ingest: "/api/knowledge/ingest",
  thread: (threadId) => `/api/threads/${encodeURIComponent(threadId)}`,
};

const elements = {
  chatForm: document.querySelector("#chatForm"),
  clearThreadButton: document.querySelector("#clearThreadButton"),
  conversation: document.querySelector("#conversation"),
  emptyState: document.querySelector("#emptyState"),
  fileSummary: document.querySelector("#fileSummary"),
  knowledgeFiles: document.querySelector("#knowledgeFiles"),
  menuButton: document.querySelector("#menuButton"),
  messageInput: document.querySelector("#messageInput"),
  mobileOverlay: document.querySelector("#mobileOverlay"),
  newThreadButton: document.querySelector("#newThreadButton"),
  refreshStatusButton: document.querySelector("#refreshStatusButton"),
  runtimeMode: document.querySelector("#runtimeMode"),
  sendButton: document.querySelector("#sendButton"),
  sidebar: document.querySelector("#sidebar"),
  statusDot: document.querySelector("#statusDot"),
  statusText: document.querySelector("#statusText"),
  subjectId: document.querySelector("#subjectId"),
  threadId: document.querySelector("#threadId"),
  toastRegion: document.querySelector("#toastRegion"),
  uploadButton: document.querySelector("#uploadButton"),
  uploadProgress: document.querySelector("#uploadProgress"),
  uploadZone: document.querySelector("#uploadZone"),
  userId: document.querySelector("#userId"),
};

let requestController = null;

function createId(prefix) {
  const value = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${value.slice(0, 12)}`;
}

function loadIdentity() {
  elements.userId.value = localStorage.getItem("agent-user-id") || createId("user");
  elements.threadId.value = localStorage.getItem("agent-thread-id") || createId("thread");
  elements.subjectId.value = localStorage.getItem("agent-subject-id") || "partner";
  persistIdentity();
}

function persistIdentity() {
  const userId = elements.userId.value.trim();
  const threadId = elements.threadId.value.trim();
  const subjectId = elements.subjectId.value.trim();
  if (userId) localStorage.setItem("agent-user-id", userId);
  if (threadId) localStorage.setItem("agent-thread-id", threadId);
  if (subjectId) localStorage.setItem("agent-subject-id", subjectId);
}

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${type === "error" ? "is-error" : type === "success" ? "is-success" : ""}`;
  toast.textContent = message;
  elements.toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), 4200);
}

function setStatus(state, text) {
  elements.statusDot.className = `status-dot ${state === "online" ? "is-online" : state === "checking" ? "is-checking" : ""}`;
  elements.statusText.textContent = text;
}

function getRuntimeLabel(data) {
  const details = data.capabilities || data;
  const model = details.model || details.model_name || details.model_provider;
  const memory = details.memory || details.memory_backend || details.short_term_memory;
  const vector = details.vector_store || details.vector_backend || details.rag_backend;
  return [model, memory, vector].filter(Boolean).join(" · ") || "服务已就绪";
}

async function checkStatus() {
  setStatus("checking", "正在检查服务");
  elements.refreshStatusButton.disabled = true;
  try {
    const response = await fetch(API.status, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const healthy = data.status !== "error" && data.healthy !== false;
    const configured = data.configured !== false;
    setStatus(healthy ? "online" : "offline", configured ? (healthy ? "服务正常" : "服务异常") : "等待模型配置");
    elements.runtimeMode.textContent = getRuntimeLabel(data);
  } catch (error) {
    setStatus("offline", "服务未连接");
    elements.runtimeMode.textContent = "离线";
  } finally {
    elements.refreshStatusButton.disabled = false;
  }
}

function scrollConversation() {
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
}

function hideEmptyState() {
  if (elements.emptyState) {
    elements.emptyState.remove();
    elements.emptyState = null;
  }
}

function createMessage(role, text = "") {
  hideEmptyState();
  const message = document.createElement("article");
  message.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = role === "assistant" ? "AI" : "我";

  const content = document.createElement("div");
  const roleLabel = document.createElement("div");
  roleLabel.className = "message-role";
  roleLabel.textContent = role === "assistant" ? "私人助手" : "你";
  const body = document.createElement("div");
  body.className = "message-text";
  body.textContent = text;

  content.append(roleLabel, body);
  message.append(avatar, content);
  elements.conversation.append(message);
  scrollConversation();
  return { message, body, content };
}

function sourceTitle(source, index) {
  if (typeof source === "string") return source;
  return source.title || source.source || source.file_name || source.filename || `来源 ${index + 1}`;
}

function appendSources(container, sources) {
  if (!Array.isArray(sources) || sources.length === 0) return;
  const section = document.createElement("div");
  section.className = "sources";
  const title = document.createElement("div");
  title.className = "sources-title";
  title.textContent = `参考来源 · ${sources.length}`;
  section.append(title);

  sources.forEach((source, index) => {
    const row = document.createElement("div");
    row.className = "source-item";
    const number = document.createElement("span");
    number.className = "source-number";
    number.textContent = `[${index + 1}]`;
    const value = sourceTitle(source, index);
    const url = typeof source === "object" ? source.url : null;
    const description = typeof source === "object" ? source.content || source.snippet : null;
    if (url && /^https?:\/\//i.test(url)) {
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = value;
      row.append(number, link);
    } else {
      const label = document.createElement("span");
      label.textContent = description ? `${value}：${description}` : value;
      row.append(number, label);
    }
    section.append(row);
  });
  container.append(section);
}

function extractToken(data) {
  return data.token ?? data.content ?? data.delta ?? data.answer ?? "";
}

function parseEventBlock(block) {
  const dataLines = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());
  if (!dataLines.length) return null;
  const raw = dataLines.join("\n");
  if (raw === "[DONE]") return { type: "done" };
  try {
    return JSON.parse(raw);
  } catch {
    return { type: "token", token: raw };
  }
}

async function consumeEventStream(response, handlers) {
  if (!response.body) throw new Error("当前浏览器无法读取流式响应");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const event = parseEventBlock(block);
      if (event) handlers.onEvent(event);
    }
    if (done) break;
  }
  const finalEvent = parseEventBlock(buffer);
  if (finalEvent) handlers.onEvent(finalEvent);
}

function getChatPayload() {
  const userId = elements.userId.value.trim();
  const threadId = elements.threadId.value.trim();
  const subjectId = elements.subjectId.value.trim();
  if (!userId || !threadId || !subjectId) throw new Error("用户 ID、对象 ID 和会话 ID 不能为空");
  persistIdentity();
  return { user_id: userId, subject_id: subjectId, thread_id: threadId };
}

async function sendMessage(message) {
  if (requestController) return;
  const payload = { ...getChatPayload(), message };
  createMessage("user", message);
  const assistant = createMessage("assistant");
  assistant.message.classList.add("is-streaming");
  elements.sendButton.disabled = true;
  elements.messageInput.disabled = true;
  requestController = new AbortController();
  let completed = false;

  try {
    const response = await fetch(API.stream, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(payload),
      signal: requestController.signal,
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `请求失败（${response.status}）`);
    }

    await consumeEventStream(response, {
      onEvent(event) {
        if (event.type === "token") {
          assistant.body.textContent += extractToken(event);
        } else if (event.type === "done") {
          const finalAnswer = event.answer ?? event.content;
          if (finalAnswer && !assistant.body.textContent) assistant.body.textContent = finalAnswer;
          appendSources(assistant.content, event.sources);
          completed = true;
        } else if (event.type === "error") {
          throw new Error(event.message || event.error || event.content || "Agent 处理失败");
        }
        scrollConversation();
      },
    });
    if (!assistant.body.textContent) assistant.body.textContent = completed ? "处理完成。" : "服务未返回可显示的内容。";
  } catch (error) {
    if (error.name !== "AbortError") {
      assistant.body.textContent = `请求失败：${error.message}`;
      showToast(error.message, "error");
    }
  } finally {
    assistant.message.classList.remove("is-streaming");
    requestController = null;
    elements.sendButton.disabled = false;
    elements.messageInput.disabled = false;
    elements.messageInput.focus();
    scrollConversation();
  }
}

function resetConversation() {
  elements.conversation.replaceChildren();
  const empty = document.createElement("div");
  empty.className = "empty-state";
  const mark = document.createElement("div");
  mark.className = "empty-mark";
  mark.textContent = "A";
  const title = document.createElement("h2");
  title.textContent = "新会话已就绪";
  const description = document.createElement("p");
  description.textContent = "短期对话上下文已清空，长期记忆是否保留取决于服务端配置。";
  empty.append(mark, title, description);
  elements.conversation.append(empty);
  elements.emptyState = empty;
}

async function clearThread() {
  const threadId = elements.threadId.value.trim();
  if (!threadId) {
    showToast("会话 ID 不能为空", "error");
    return;
  }
  if (!window.confirm(`确定清空会话 ${threadId} 吗？`)) return;
  elements.clearThreadButton.disabled = true;
  try {
    const response = await fetch(API.thread(threadId), { method: "DELETE" });
    if (!response.ok) throw new Error((await response.text()) || `清空失败（${response.status}）`);
    resetConversation();
    showToast("当前会话已清空", "success");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.clearThreadButton.disabled = false;
  }
}

function updateSelectedFiles(files) {
  const selected = Array.from(files || []);
  elements.knowledgeFiles.files = files;
  elements.uploadButton.disabled = selected.length === 0;
  elements.fileSummary.textContent = selected.length
    ? `已选择 ${selected.length} 个文件：${selected.map((file) => file.name).join("、")}`
    : "尚未选择文件";
}

async function uploadKnowledge() {
  const files = Array.from(elements.knowledgeFiles.files || []);
  if (!files.length) return;
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  formData.append("subject_id", elements.subjectId.value.trim());
  elements.uploadButton.disabled = true;
  elements.uploadProgress.hidden = false;
  try {
    const response = await fetch(API.ingest, { method: "POST", body: formData });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || body.message || `导入失败（${response.status}）`);
    const count = body.ingested_chunks ?? body.documents ?? body.files ?? body.count ?? files.length;
    showToast(`知识库导入完成，共处理 ${count} 项`, "success");
    elements.knowledgeFiles.value = "";
    updateSelectedFiles(elements.knowledgeFiles.files);
  } catch (error) {
    showToast(error.message, "error");
    elements.uploadButton.disabled = false;
  } finally {
    elements.uploadProgress.hidden = true;
  }
}

function openSidebar() {
  elements.sidebar.classList.add("is-open");
  elements.mobileOverlay.hidden = false;
}

function closeSidebar() {
  elements.sidebar.classList.remove("is-open");
  elements.mobileOverlay.hidden = true;
}

function autoResizeInput() {
  elements.messageInput.style.height = "auto";
  elements.messageInput.style.height = `${Math.min(elements.messageInput.scrollHeight, 160)}px`;
}

elements.chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = elements.messageInput.value.trim();
  if (!message) return;
  elements.messageInput.value = "";
  autoResizeInput();
  sendMessage(message).catch((error) => showToast(error.message, "error"));
});

elements.messageInput.addEventListener("input", autoResizeInput);
elements.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    elements.chatForm.requestSubmit();
  }
});

elements.userId.addEventListener("change", persistIdentity);
elements.threadId.addEventListener("change", persistIdentity);
elements.newThreadButton.addEventListener("click", () => {
  elements.threadId.value = createId("thread");
  persistIdentity();
  resetConversation();
  closeSidebar();
  showToast("已创建新的本地会话标识", "success");
});
elements.clearThreadButton.addEventListener("click", clearThread);
elements.refreshStatusButton.addEventListener("click", checkStatus);
elements.knowledgeFiles.addEventListener("change", () => updateSelectedFiles(elements.knowledgeFiles.files));
elements.uploadButton.addEventListener("click", uploadKnowledge);
elements.menuButton.addEventListener("click", openSidebar);
elements.mobileOverlay.addEventListener("click", closeSidebar);

for (const eventName of ["dragenter", "dragover"]) {
  elements.uploadZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.uploadZone.classList.add("is-dragging");
  });
}
for (const eventName of ["dragleave", "drop"]) {
  elements.uploadZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.uploadZone.classList.remove("is-dragging");
  });
}
elements.uploadZone.addEventListener("drop", (event) => {
  if (event.dataTransfer?.files?.length) updateSelectedFiles(event.dataTransfer.files);
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.messageInput.value = button.dataset.prompt;
    autoResizeInput();
    elements.messageInput.focus();
  });
});

loadIdentity();
checkStatus();
elements.messageInput.focus();
