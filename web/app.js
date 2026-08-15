const API = {
  status: "/api/status",
  chat: "/api/chat",
  stream: "/api/chat/stream",
  ingest: "/api/knowledge/ingest",
  graph: "/api/knowledge/graph",
  thread: (threadId) => `/api/threads/${encodeURIComponent(threadId)}`,
};

const elements = {
  chatForm: document.querySelector("#chatForm"),
  clearThreadButton: document.querySelector("#clearThreadButton"),
  conversation: document.querySelector("#conversation"),
  conversationList: document.querySelector("#conversationList"),
  graphButton: document.querySelector("#graphButton"),
  graphModal: document.querySelector("#graphModal"),
  graphCanvas: document.querySelector("#graphCanvas"),
  graphDetail: document.querySelector("#graphDetail"),
  closeGraphButton: document.querySelector("#closeGraphButton"),
  conversationCapacity: document.querySelector("#conversationCapacity"),
  userSelector: document.querySelector("#userSelector"),
  subjectSelector: document.querySelector("#subjectSelector"),
  addUserButton: document.querySelector("#addUserButton"),
  addSubjectButton: document.querySelector("#addSubjectButton"),
  deleteSubjectButton: document.querySelector("#deleteSubjectButton"),
  emptyState: document.querySelector("#emptyState"),
  fileSummary: document.querySelector("#fileSummary"),
  knowledgeFiles: document.querySelector("#knowledgeFiles"),
  menuButton: document.querySelector("#menuButton"),
  messageInput: document.querySelector("#messageInput"),
  mobileOverlay: document.querySelector("#mobileOverlay"),
  newThreadButton: document.querySelector("#newThreadButton"),
  newConversationButton: document.querySelector("#newConversationButton"),
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
let conversationMessages = [];
const CONVERSATIONS_KEY = "agent-conversations-v1";
const USERS_KEY = "agent-users-v1";
const SUBJECTS_KEY = "agent-subjects-v1";
const USER_PROFILES_KEY = "agent-user-profiles-v1";
const MAX_CONVERSATIONS = 50;
const CONVERSATION_WARNING_THRESHOLD = 45;

function createId(prefix) {
  const value = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${value.slice(0, 12)}`;
}

function loadIdentity() {
  elements.userId.value = localStorage.getItem("agent-user-id") || createId("user");
  elements.threadId.value = localStorage.getItem("agent-thread-id") || createId("thread");
  const savedSubject = localStorage.getItem("agent-subject-id");
  elements.subjectId.value = !savedSubject || savedSubject === "partner" ? "all" : savedSubject;
  const migratedSubjects = readOptionList(SUBJECTS_KEY, ["all"]).filter((value) => value !== "partner");
  localStorage.setItem(SUBJECTS_KEY, JSON.stringify(migratedSubjects.length ? migratedSubjects : ["all"]));
  syncIdentitySelectors();
  persistIdentity();
}

function readOptionList(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null");
    return Array.isArray(value) && value.length ? value : fallback;
  } catch { return fallback; }
}

function writeOption(key, value) {
  const values = readOptionList(key, []);
  if (!values.includes(value)) localStorage.setItem(key, JSON.stringify([...values, value].slice(0, 50)));
}

function syncSelect(select, options, selected) {
  select.replaceChildren();
  [...new Set(options)].forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value === "all" ? "全部对象（检索所有人的资料）" : value;
    select.append(option);
  });
  select.value = selected;
}

function syncIdentitySelectors() {
  writeOption(USERS_KEY, elements.userId.value);
  writeOption(SUBJECTS_KEY, elements.subjectId.value);
  writeOption(SUBJECTS_KEY, "all");
  const profiles = readUserProfiles();
  if (!profiles.some((profile) => profile.id === elements.userId.value)) {
    profiles.push({ id: elements.userId.value, label: `账号 ${profiles.length + 1}` });
    writeUserProfiles(profiles);
  }
  syncSelect(elements.userSelector, profiles.map((profile) => profile.label), profiles.find((profile) => profile.id === elements.userId.value)?.label);
  [...elements.userSelector.options].forEach((option, index) => { option.value = profiles[index].id; });
  syncSelect(elements.subjectSelector, readOptionList(SUBJECTS_KEY, ["all"]), elements.subjectId.value);
}

function readUserProfiles() {
  try {
    const profiles = JSON.parse(localStorage.getItem(USER_PROFILES_KEY) || "[]");
    return Array.isArray(profiles) ? profiles : [];
  } catch { return []; }
}

function writeUserProfiles(profiles) {
  localStorage.setItem(USER_PROFILES_KEY, JSON.stringify(profiles.slice(0, 50)));
}

function persistIdentity() {
  const userId = elements.userId.value.trim();
  const threadId = elements.threadId.value.trim();
  const subjectId = elements.subjectId.value.trim();
  if (userId) localStorage.setItem("agent-user-id", userId);
  if (threadId) localStorage.setItem("agent-thread-id", threadId);
  if (subjectId) localStorage.setItem("agent-subject-id", subjectId);
  if (elements.userSelector && elements.userSelector.value !== userId) elements.userSelector.value = userId;
  if (elements.subjectSelector && elements.subjectSelector.value !== subjectId) elements.subjectSelector.value = subjectId;
}

function readConversations() {
  try {
    const value = JSON.parse(localStorage.getItem(CONVERSATIONS_KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch { return []; }
}

function saveConversations(conversations) {
  localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations));
}

function saveCurrentConversation() {
  const threadId = elements.threadId.value.trim();
  if (!threadId || !conversationMessages.length) return;
  const conversations = readConversations().filter((item) => item.thread_id !== threadId);
  const firstUser = conversationMessages.find((item) => item.role === "user");
  conversations.unshift({
    thread_id: threadId,
    user_id: elements.userId.value.trim(),
    subject_id: elements.subjectId.value.trim(),
    title: firstUser?.text?.slice(0, 28) || "新会话",
    updated_at: new Date().toISOString(),
    messages: conversationMessages.filter((item) => item.text),
  });
  saveConversations(conversations);
  renderConversationList();
}

function renderConversationList() {
  if (!elements.conversationList) return;
  elements.conversationList.replaceChildren();
  const currentId = elements.threadId.value.trim();
  const conversations = readConversations();
  if (elements.conversationCapacity) {
    elements.conversationCapacity.textContent = `${conversations.length} / ${MAX_CONVERSATIONS}`;
    elements.conversationCapacity.classList.toggle("is-warning", conversations.length >= CONVERSATION_WARNING_THRESHOLD);
  }
  if (!conversations.length) {
    const empty = document.createElement("div");
    empty.className = "conversation-list-empty";
    empty.textContent = "暂无历史会话";
    elements.conversationList.append(empty);
    return;
  }
  conversations.forEach((item) => {
    const row = document.createElement("div");
    row.className = `conversation-row${item.thread_id === currentId ? " is-active" : ""}`;
    const button = document.createElement("button");
    button.type = "button";
    button.className = `conversation-item${item.thread_id === currentId ? " is-active" : ""}`;
    const title = document.createElement("strong");
    title.textContent = item.title || "无标题会话";
    const meta = document.createElement("span");
    meta.textContent = `${item.subject_id || "default"} · ${item.messages?.length || 0} 条`;
    button.append(title, meta);
    button.addEventListener("click", () => switchConversation(item.thread_id));
    const rename = document.createElement("button");
    rename.type = "button";
    rename.className = "conversation-rename";
    rename.textContent = "重命名";
    rename.addEventListener("click", (event) => {
      event.stopPropagation();
      const title = window.prompt("输入新的会话名称", item.title || "");
      if (!title?.trim()) return;
      saveConversations(readConversations().map((conversation) => conversation.thread_id === item.thread_id ? { ...conversation, title: title.trim() } : conversation));
      renderConversationList();
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "conversation-delete";
    remove.textContent = "删除";
    remove.addEventListener("click", (event) => {
      event.stopPropagation();
      if (!window.confirm(`确定删除会话“${item.title || "无标题会话"}”吗？`)) return;
      saveConversations(readConversations().filter((conversation) => conversation.thread_id !== item.thread_id));
      fetch(API.thread(item.thread_id), { method: "DELETE" }).catch(() => {});
      if (item.thread_id === elements.threadId.value.trim()) createNewConversation(true);
      else renderConversationList();
    });
    row.append(button, rename, remove);
    elements.conversationList.append(row);
  });
}

function switchConversation(threadId) {
  const item = readConversations().find((conversation) => conversation.thread_id === threadId);
  if (!item) return;
  elements.userId.value = item.user_id || elements.userId.value;
  elements.subjectId.value = item.subject_id || elements.subjectId.value;
  elements.threadId.value = item.thread_id;
  conversationMessages = Array.isArray(item.messages) ? item.messages : [];
  persistIdentity();
  renderStoredMessages();
  renderConversationList();
  closeSidebar();
}

function renderStoredMessages() {
  elements.conversation.replaceChildren();
  if (!conversationMessages.length) { resetConversation(false); return; }
  conversationMessages.forEach((item) => createMessage(item.role, item.text, false));
}

function showGraphDetail(node) {
  elements.graphDetail.replaceChildren();
  const title = document.createElement("h3");
  title.textContent = node.label;
  const hint = document.createElement("p");
  hint.className = "graph-detail-hint";
  hint.textContent = `${node.notes?.length || 0} 条已保存资料`;
  elements.graphDetail.append(title, hint);
  (node.notes || []).forEach((note) => {
    const article = document.createElement("article");
    article.className = "graph-note";
    const source = document.createElement("strong");
    source.textContent = note.source;
    const content = document.createElement("p");
    content.textContent = note.content;
    article.append(source, content);
    elements.graphDetail.append(article);
  });
}

function renderGraph(data) {
  elements.graphCanvas.replaceChildren();
  if (!data.nodes?.length) {
    const empty = document.createElement("div");
    empty.className = "graph-empty";
    empty.innerHTML = "<div class=\"graph-empty-mark\">◎</div><h3>还没有人物节点</h3><p>在聊天或知识库中确认保存人物资料后，这里会自动生成小球。</p>";
    elements.graphCanvas.append(empty);
    elements.graphDetail.replaceChildren();
    const detailEmpty = document.createElement("div");
    detailEmpty.className = "graph-detail-empty";
    detailEmpty.textContent = "暂无可查看的资料";
    elements.graphDetail.append(detailEmpty);
    return;
  }
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 720 460");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "人物知识图谱");
  data.nodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / data.nodes.length - Math.PI / 2;
    const x = data.nodes.length === 1 ? 360 : 360 + Math.cos(angle) * Math.min(210, 90 + data.nodes.length * 20);
    const y = data.nodes.length === 1 ? 225 : 225 + Math.sin(angle) * Math.min(145, 55 + data.nodes.length * 16);
    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    group.setAttribute("class", "graph-node");
    group.setAttribute("tabindex", "0");
    group.setAttribute("transform", `translate(${x} ${y})`);
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("r", "42");
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("dy", "5");
    label.textContent = node.label;
    const core = document.createElementNS("http://www.w3.org/2000/svg", "g");
    core.setAttribute("class", "graph-node-core");
    core.append(circle, label);
    group.append(core);
    const selectNode = () => {
      svg.querySelectorAll(".graph-node.is-selected").forEach((selected) => selected.classList.remove("is-selected"));
      group.classList.add("is-selected");
      showGraphDetail(node);
    };
    group.addEventListener("click", selectNode);
    group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") selectNode(); });
    svg.append(group);
  });
  elements.graphCanvas.append(svg);
  elements.graphDetail.replaceChildren();
  const detailEmpty = document.createElement("div");
  detailEmpty.className = "graph-detail-empty";
  detailEmpty.textContent = "点击人物节点查看已保存资料";
  elements.graphDetail.append(detailEmpty);
}

async function openGraph() {
  elements.graphModal.hidden = false;
  elements.graphCanvas.textContent = "正在读取知识图谱…";
  try {
    const response = await fetch(`${API.graph}?subject_id=${encodeURIComponent(elements.subjectId.value.trim() || "all")}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderGraph(await response.json());
  } catch (error) {
    elements.graphCanvas.textContent = `读取知识图谱失败：${error.message}`;
  }
}

function closeGraph() { elements.graphModal.hidden = true; }

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

function createMessage(role, text = "", record = true) {
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
  if (record) {
    conversationMessages.push({ role, text });
    saveCurrentConversation();
  }
  scrollConversation();
  return { message, body, content };
}

function createProcessPanel(content) {
  const details = document.createElement("details");
  details.className = "process-panel";
  details.open = true;
  const summary = document.createElement("summary");
  summary.textContent = "执行过程";
  const list = document.createElement("div");
  list.className = "process-steps";
  details.append(summary, list);
  content.insertBefore(details, content.querySelector(".message-text"));
  return {
    add(text) {
      const step = document.createElement("div");
      step.className = "process-step";
      step.textContent = text;
      list.append(step);
    },
    finish() { details.open = false; },
  };
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
  const process = createProcessPanel(assistant.content);
  process.add("已接收问题，正在分析请求");
  process.add("正在判断是否需要检索私人知识库或调用工具");
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
          if (!assistant.body.textContent) process.add("信息处理完成，正在生成回答");
          assistant.body.textContent += extractToken(event);
          const latest = conversationMessages[conversationMessages.length - 1];
          if (latest?.role === "assistant") latest.text = assistant.body.textContent;
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
    process.add("回答生成完成");
  } catch (error) {
    if (error.name !== "AbortError") {
      const message = error instanceof TypeError && error.message === "Failed to fetch"
        ? "无法连接后端服务，请先启动项目并访问 http://127.0.0.1:8000"
        : error.message;
      assistant.body.textContent = `请求失败：${message}`;
      showToast(message, "error");
    }
  } finally {
    const latest = conversationMessages[conversationMessages.length - 1];
    if (latest?.role === "assistant") latest.text = assistant.body.textContent;
    saveCurrentConversation();
    assistant.message.classList.remove("is-streaming");
    process.finish();
    requestController = null;
    elements.sendButton.disabled = false;
    elements.messageInput.disabled = false;
    elements.messageInput.focus();
    scrollConversation();
  }
}

function resetConversation(save = true) {
  conversationMessages = [];
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
  if (save) {
    const threadId = elements.threadId.value.trim();
    saveConversations(readConversations().filter((item) => item.thread_id !== threadId));
    renderConversationList();
  }
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
elements.subjectId.addEventListener("change", persistIdentity);
elements.userSelector.addEventListener("change", () => {
  elements.userId.value = elements.userSelector.value;
  persistIdentity();
});
elements.subjectSelector.addEventListener("change", () => {
  elements.subjectId.value = elements.subjectSelector.value;
  persistIdentity();
});
elements.addUserButton.addEventListener("click", () => {
  const value = window.prompt("输入登录账号 ID");
  if (!value?.trim()) return;
  elements.userId.value = value.trim();
  writeOption(USERS_KEY, elements.userId.value);
  syncIdentitySelectors();
  persistIdentity();
});
elements.addSubjectButton.addEventListener("click", () => {
  const value = window.prompt("输入对象名称，例如：妈妈、爸爸、对象");
  if (!value?.trim()) return;
  elements.subjectId.value = value.trim();
  writeOption(SUBJECTS_KEY, elements.subjectId.value);
  syncIdentitySelectors();
  persistIdentity();
});
elements.graphButton.addEventListener("click", openGraph);
elements.closeGraphButton.addEventListener("click", closeGraph);
elements.graphModal.addEventListener("click", (event) => {
  if (event.target === elements.graphModal) closeGraph();
});
function createNewConversation(force = false) {
  const count = readConversations().length;
  if (!force && count >= MAX_CONVERSATIONS) {
    showToast(`会话已达到 ${MAX_CONVERSATIONS} 个，请先删除不需要的会话`, "error");
    return;
  }
  elements.threadId.value = createId("thread");
  persistIdentity();
  resetConversation();
  closeSidebar();
  showToast("已创建新会话", "success");
  if (count >= CONVERSATION_WARNING_THRESHOLD) {
    showToast(`已有 ${count} 个会话，建议整理并删除不需要的记录`);
  }
}

elements.newThreadButton.addEventListener("click", () => createNewConversation());
elements.newConversationButton.addEventListener("click", () => createNewConversation());
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

const cleanUserButton = elements.addUserButton.cloneNode(true);
elements.addUserButton.replaceWith(cleanUserButton);
elements.addUserButton = cleanUserButton;
elements.addUserButton.addEventListener("click", () => {
  const label = window.prompt("输入账号显示名称，例如：林波");
  if (!label?.trim()) return;
  const profile = { id: createId("user"), label: label.trim() };
  writeUserProfiles([...readUserProfiles().filter((item) => item.label !== profile.label), profile]);
  elements.userId.value = profile.id;
  syncIdentitySelectors();
  persistIdentity();
});
elements.deleteSubjectButton.addEventListener("click", async () => {
  const subjectId = elements.subjectId.value.trim();
  if (!subjectId || subjectId === "all") {
    showToast("全部对象是固定范围，不能删除", "error");
    return;
  }
  if (!window.confirm(`确定删除“${subjectId}”及其本地资料吗？此操作不可恢复。`)) return;
  const response = await fetch(`/api/knowledge/subjects/${encodeURIComponent(subjectId)}`, { method: "DELETE" });
  if (!response.ok) { showToast("删除对象资料失败", "error"); return; }
  localStorage.setItem(SUBJECTS_KEY, JSON.stringify(readOptionList(SUBJECTS_KEY, []).filter((item) => item !== subjectId)));
  elements.subjectId.value = "all";
  syncIdentitySelectors();
  persistIdentity();
  showToast(`已删除${subjectId}及其资料`, "success");
});
loadIdentity();
const existingConversation = readConversations().find((item) => item.thread_id === elements.threadId.value.trim());
if (existingConversation) switchConversation(existingConversation.thread_id);
else renderConversationList();
checkStatus();
elements.messageInput.focus();
