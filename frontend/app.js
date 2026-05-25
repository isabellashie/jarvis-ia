/**
 * JARVIS Acadêmico — Frontend JavaScript
 * Gerencia chat, agenda, tarefas, documentos e funcionalidades de aprendizado.
 */

// ── Config ────────────────────────────────────────────────────────────────────
const API = '';  // Mesmo host (backend serve o frontend estático)
// Para dev separado: const API = 'http://localhost:8000';

// ── Estado da aplicação ───────────────────────────────────────────────────────
const state = {
  conversationHistory: [],
  conversationId: generateId(),
  isLoading: false,
  currentMainTab: 'chat',
  hasMessages: false,
};

// ── Utilitários ───────────────────────────────────────────────────────────────

function generateId() {
  return Math.random().toString(36).substring(2, 10);
}

function toast(msg, type = 'info', duration = 3500) {
  const c = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

function setLoading(loading) {
  state.isLoading = loading;
  const btn = document.getElementById('send-btn');
  const input = document.getElementById('chat-input');
  btn.disabled = loading;
  input.disabled = loading;
  if (loading) btn.innerHTML = '<span class="spin">⟳</span>';
  else btn.innerHTML = '➤';
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

function scrollToBottom() {
  const msgs = document.getElementById('chat-messages');
  msgs.scrollTop = msgs.scrollHeight;
}

function formatDateTime(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

/** Converte markdown básico para HTML para renderização nas bolhas */
function markdownToHtml(text) {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^#{1,3}\s(.+)$/gm, '<strong>$1</strong>')
    .replace(/^[-•]\s(.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n/g, '<br>');
}

// ── Relógio em tempo real ─────────────────────────────────────────────────────

function updateClock() {
  const now = new Date();
  document.getElementById('clock-date').textContent =
    now.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' });
  document.getElementById('clock-time').textContent =
    now.toLocaleTimeString('pt-BR');
}
updateClock();
setInterval(updateClock, 1000);

// ── Navegação de tabs ─────────────────────────────────────────────────────────

function switchMainTab(tab, btn) {
  // Esconde tudo
  document.getElementById('chat-tab').classList.add('hidden');
  document.getElementById('learn-tab').classList.add('hidden');
  document.getElementById('logs-tab').classList.add('hidden');

  // Remove active de todas as tabs
  document.querySelectorAll('.main-tab').forEach(t => t.classList.remove('active'));

  // Ativa a tab selecionada
  document.getElementById(`${tab}-tab`).classList.remove('hidden');
  btn.classList.add('active');
  state.currentMainTab = tab;

  // Carrega dados sob demanda
  if (tab === 'logs') loadLogs();
}

// ── Chat ──────────────────────────────────────────────────────────────────────

function handleInputKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function sendChip(text) {
  document.getElementById('chat-input').value = text;
  // Garante que está na tab de chat
  const chatTabBtn = document.querySelector('.main-tab');
  switchMainTab('chat', chatTabBtn);
  sendMessage();
}

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text || state.isLoading) return;

  input.value = '';
  input.style.height = 'auto';

  // Esconde welcome screen na primeira mensagem
  if (!state.hasMessages) {
    const ws = document.getElementById('welcome-screen');
    if (ws) ws.remove();
    state.hasMessages = true;
  }

  // Adiciona mensagem do usuário
  appendMessage('user', text);
  state.conversationHistory.push({ role: 'user', content: text });

  // Mostra typing indicator
  setLoading(true);
  const typingEl = appendTypingIndicator();

  try {
    const resp = await fetch(`${API}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mensagens: state.conversationHistory,
        conversa_id: state.conversationId,
      }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const data = await resp.json();
    typingEl.remove();

    // Monta resposta com indicadores de tool calls
    const toolCallHtml = buildToolCallHtml(data.tool_calls || []);
    appendMessage('assistant', data.resposta, toolCallHtml);

    state.conversationHistory.push({ role: 'assistant', content: data.resposta });

    // Atualiza sidebar se ferramenta de agenda/tarefas foi chamada
    const toolNames = (data.tool_calls || []).map(t => t.ferramenta);
    if (toolNames.some(n => n.includes('agenda'))) loadAgenda('hoje');
    if (toolNames.some(n => n.includes('tarefa'))) loadTasks('pendentes');
    if (toolNames.some(n => n.includes('reindexar'))) loadDocuments();

  } catch (err) {
    typingEl.remove();
    appendMessage('assistant', `❌ Erro ao comunicar com o JARVIS: ${err.message}`);
    toast(`Erro: ${err.message}`, 'error');
  } finally {
    setLoading(false);
    scrollToBottom();
  }
}

function buildToolCallHtml(toolCalls) {
  if (!toolCalls.length) return '';
  return toolCalls.map(t => `
    <div class="tool-call-indicator">
      ${t.ferramenta}(${Object.keys(t.argumentos || {}).map(k => `${k}: ${JSON.stringify(t.argumentos[k])}`).join(', ')})
    </div>
  `).join('');
}

function appendMessage(role, content, prefixHtml = '') {
  const container = document.getElementById('chat-messages');

  const avatarEmoji = role === 'assistant' ? '🤖' : '👤';
  const senderLabel = role === 'assistant' ? 'JARVIS' : 'VOCÊ';

  const el = document.createElement('div');
  el.className = `msg ${role}`;
  el.innerHTML = `
    <div class="msg-avatar">${avatarEmoji}</div>
    <div class="msg-body">
      <div class="msg-sender">${senderLabel}</div>
      ${prefixHtml}
      <div class="msg-bubble">${markdownToHtml(content)}</div>
    </div>
  `;
  container.appendChild(el);
  scrollToBottom();
  return el;
}

function appendTypingIndicator() {
  const container = document.getElementById('chat-messages');
  const el = document.createElement('div');
  el.className = 'msg assistant';
  el.innerHTML = `
    <div class="msg-avatar">🤖</div>
    <div class="msg-body">
      <div class="msg-sender">JARVIS</div>
      <div class="typing-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>
  `;
  container.appendChild(el);
  scrollToBottom();
  return el;
}

// ── Agenda ────────────────────────────────────────────────────────────────────

async function loadAgenda(periodo = 'hoje', btn = null) {
  // Atualiza botão ativo
  if (btn) {
    document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }

  const list = document.getElementById('agenda-list');
  list.innerHTML = '<div class="empty-state">Carregando...</div>';

  try {
    const resp = await fetch(`${API}/agenda?periodo=${encodeURIComponent(periodo)}`);
    const data = await resp.json();
    renderAgenda(data.eventos || []);
  } catch (e) {
    list.innerHTML = '<div class="empty-state text-red">Erro ao carregar agenda</div>';
  }
}

function renderAgenda(eventos) {
  const list = document.getElementById('agenda-list');
  if (!eventos.length) {
    list.innerHTML = '<div class="empty-state">Nenhum evento encontrado.</div>';
    return;
  }

  list.innerHTML = eventos.map(e => {
    const tipo = e.tipo || 'aula';
    const tipoClass = `tipo-${tipo.toLowerCase()}`;
    return `
      <div class="agenda-item">
        <div class="agenda-time">${e.horario || '--:--'}</div>
        <div class="agenda-info">
          <div class="agenda-title">${e.titulo}</div>
          <div class="agenda-meta">${e.local ? '📍 ' + e.local : ''} ${e.data}</div>
        </div>
        <span class="tipo-badge ${tipoClass}">${tipo}</span>
      </div>
    `;
  }).join('');
}

async function addEvento() {
  const titulo   = document.getElementById('evt-titulo').value.trim();
  const data     = document.getElementById('evt-data').value;
  const horario  = document.getElementById('evt-horario').value;
  const tipo     = document.getElementById('evt-tipo').value;
  const local    = document.getElementById('evt-local').value.trim();

  if (!titulo || !data) { toast('Preencha título e data!', 'error'); return; }

  try {
    const resp = await fetch(`${API}/agenda`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ titulo, data, horario, tipo, local }),
    });
    if (!resp.ok) throw new Error((await resp.json()).detail);
    toast('Evento adicionado!', 'success');
    // Limpa campos
    ['evt-titulo', 'evt-data', 'evt-horario', 'evt-local'].forEach(id => document.getElementById(id).value = '');
    loadAgenda('hoje');
  } catch (e) {
    toast(`Erro: ${e.message}`, 'error');
  }
}

// ── Tarefas ───────────────────────────────────────────────────────────────────

async function loadTasks(filtro = 'pendentes', btn = null) {
  if (btn) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }

  const list = document.getElementById('tasks-list');
  list.innerHTML = '<div class="empty-state">Carregando...</div>';

  try {
    const resp = await fetch(`${API}/tasks?filtro=${filtro}`);
    const data = await resp.json();
    renderTasks(data.tarefas || []);
  } catch (e) {
    list.innerHTML = '<div class="empty-state text-red">Erro ao carregar tarefas</div>';
  }
}

function renderTasks(tarefas) {
  const list = document.getElementById('tasks-list');
  if (!tarefas.length) {
    list.innerHTML = '<div class="empty-state">Nenhuma tarefa encontrada.</div>';
    return;
  }

  list.innerHTML = tarefas.map(t => {
    const done = t.concluida;
    const priorClass = `prior-${(t.prioridade || 'baixa').replace('é', 'e')}`;
    return `
      <div class="task-item ${done ? 'done' : ''}" id="task-${t.id}">
        <div class="task-check ${done ? 'checked' : ''}" onclick="${done ? '' : `completeTask(${t.id})`}"></div>
        <div class="task-info">
          <div class="task-title">${t.titulo}</div>
          <div class="task-meta">
            <span class="prioridade-badge ${priorClass}">${t.prioridade}</span>
            ${t.disciplina ? `<span style="font-family:var(--font-mono);font-size:9px;color:var(--text-muted);">${t.disciplina}</span>` : ''}
            ${t.prazo ? `<span class="task-deadline">📅 ${t.prazo}</span>` : ''}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

async function addTarefa() {
  const titulo      = document.getElementById('task-titulo').value.trim();
  const disciplina  = document.getElementById('task-disciplina').value.trim();
  const prioridade  = document.getElementById('task-prioridade').value;
  const prazo       = document.getElementById('task-prazo').value;

  if (!titulo) { toast('Digite o título da tarefa!', 'error'); return; }

  try {
    const resp = await fetch(`${API}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ titulo, disciplina, prioridade, prazo }),
    });
    if (!resp.ok) throw new Error((await resp.json()).detail);
    toast('Tarefa adicionada!', 'success');
    ['task-titulo', 'task-disciplina', 'task-prazo'].forEach(id => document.getElementById(id).value = '');
    loadTasks('pendentes');
  } catch (e) {
    toast(`Erro: ${e.message}`, 'error');
  }
}

async function completeTask(id) {
  try {
    const resp = await fetch(`${API}/tasks/${id}/complete`, { method: 'PUT' });
    if (!resp.ok) throw new Error((await resp.json()).detail);
    toast('Tarefa concluída! ✓', 'success');
    // Atualiza visual imediatamente
    const el = document.getElementById(`task-${id}`);
    if (el) {
      el.classList.add('done');
      el.querySelector('.task-check').classList.add('checked');
      el.querySelector('.task-check').onclick = null;
    }
  } catch (e) {
    toast(`Erro: ${e.message}`, 'error');
  }
}

// ── Documentos RAG ────────────────────────────────────────────────────────────

async function loadDocuments() {
  const list = document.getElementById('docs-list');
  try {
    const resp = await fetch(`${API}/documents`);
    const data = await resp.json();
    if (!data.documentos.length) {
      list.innerHTML = '<div class="empty-state">Nenhum documento indexado.</div>';
      return;
    }
    list.innerHTML = data.documentos.map(d => `
      <div class="doc-item">
        <span class="doc-icon">${d.endsWith('.pdf') ? '📄' : '📝'}</span>
        <span>${d}</span>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = '<div class="empty-state text-red">Erro ao carregar docs</div>';
  }
}

async function uploadDocument(input) {
  const file = input.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  toast(`Enviando ${file.name}...`, 'info', 5000);

  try {
    const resp = await fetch(`${API}/documents/upload`, {
      method: 'POST',
      body: formData,
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail);
    toast(`✓ ${file.name} indexado! (${data.novos_chunks} chunks)`, 'success');
    loadDocuments();
  } catch (e) {
    toast(`Erro no upload: ${e.message}`, 'error');
  }

  input.value = '';
}

// ── Aprendizado: Exercícios ───────────────────────────────────────────────────

async function gerarExercicios() {
  const tema = document.getElementById('ex-tema').value.trim();
  const qtd  = parseInt(document.getElementById('ex-qtd').value);

  if (!tema) { toast('Digite um tema!', 'error'); return; }

  const btn    = document.getElementById('ex-btn');
  const result = document.getElementById('ex-result');

  btn.disabled = true;
  btn.textContent = '⟳ GERANDO...';
  result.innerHTML = '<span style="color:var(--text-muted); font-family:var(--font-mono); font-size:11px;">O JARVIS está consultando os materiais e criando exercícios...</span>';

  try {
    const resp = await fetch(`${API}/learn/exercises`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tema, quantidade: qtd }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail);
    result.innerHTML = markdownToHtml(data.exercicios);
    toast('Exercícios gerados!', 'success');
  } catch (e) {
    result.innerHTML = `<span style="color:var(--red);">Erro: ${e.message}</span>`;
    toast(`Erro: ${e.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'GERAR';
  }
}

// ── Aprendizado: Avaliação de Resposta ────────────────────────────────────────

async function avaliarResposta() {
  const pergunta = document.getElementById('eval-pergunta').value.trim();
  const resposta = document.getElementById('eval-resposta').value.trim();
  const tema     = document.getElementById('eval-tema').value.trim();

  if (!pergunta || !resposta) { toast('Preencha a pergunta e sua resposta!', 'error'); return; }

  const btn    = document.getElementById('eval-btn');
  const result = document.getElementById('eval-result');

  btn.disabled = true;
  btn.textContent = '⟳ AVALIANDO...';
  result.innerHTML = '<span style="color:var(--text-muted); font-family:var(--font-mono); font-size:11px;">O JARVIS está avaliando sua resposta...</span>';

  try {
    const resp = await fetch(`${API}/learn/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pergunta,
        resposta_aluno: resposta,
        tema: tema || pergunta,
      }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail);
    result.innerHTML = markdownToHtml(data.feedback);
    toast('Avaliação concluída!', 'success');
  } catch (e) {
    result.innerHTML = `<span style="color:var(--red);">Erro: ${e.message}</span>`;
    toast(`Erro: ${e.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'AVALIAR RESPOSTA';
  }
}

// ── Logs ──────────────────────────────────────────────────────────────────────

async function loadLogs() {
  const panel   = document.getElementById('logs-panel');
  const summary = document.getElementById('logs-summary');

  panel.innerHTML = '<div class="empty-state">Carregando logs...</div>';

  try {
    const [logsResp, summaryResp] = await Promise.all([
      fetch(`${API}/logs?limite=30`),
      fetch(`${API}/logs/summary`),
    ]);

    const logsData    = await logsResp.json();
    const summaryData = await summaryResp.json();

    summary.textContent = `${summaryData.total} chamadas · ${Math.round((summaryData.taxa_erro || 0) * 100)}% erros`;

    if (!logsData.logs.length) {
      panel.innerHTML = '<div class="empty-state">Nenhum log registrado ainda.</div>';
      return;
    }

    panel.innerHTML = logsData.logs.map(log => {
      const ts = new Date(log.timestamp).toLocaleString('pt-BR');
      const statusClass = log.status === 'sucesso' ? 'log-ok' : 'log-err';
      const statusLabel = log.status === 'sucesso' ? '✓ OK' : '✗ ERRO';
      const entrada = JSON.stringify(log.entrada || {}, null, 0).substring(0, 120);
      return `
        <div class="log-entry">
          <div class="log-header">
            <span class="log-tool">${log.ferramenta}</span>
            <span class="${statusClass}">${statusLabel}</span>
            ${log.duracao_ms != null ? `<span class="log-ms">${log.duracao_ms}ms</span>` : ''}
            <span class="log-ts">${ts}</span>
          </div>
          <div class="log-detail">↳ ${entrada}${entrada.length >= 120 ? '...' : ''}</div>
          ${log.erro ? `<div class="log-detail text-red" style="margin-top:3px;">⚠ ${log.erro}</div>` : ''}
        </div>
      `;
    }).join('');

  } catch (e) {
    panel.innerHTML = `<div class="empty-state text-red">Erro ao carregar logs: ${e.message}</div>`;
  }
}

async function clearLogs() {
  if (!confirm('Limpar todos os logs? Esta ação não pode ser desfeita.')) return;
  try {
    await fetch(`${API}/logs`, { method: 'DELETE' });
    toast('Logs limpos.', 'success');
    loadLogs();
  } catch (e) {
    toast(`Erro: ${e.message}`, 'error');
  }
}

// ── Inicialização ─────────────────────────────────────────────────────────────

async function init() {
  // Carrega dados iniciais em paralelo
  await Promise.allSettled([
    loadAgenda('hoje'),
    loadTasks('pendentes'),
    loadDocuments(),
  ]);
}

init();
