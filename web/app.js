'use strict';
const $ = id => document.getElementById(id);
let token = '', offset = 0, total = 0, aiConfig = {}, aiBusy = false, chatBusy = false;
const context = new Map(), comparison = new Map();
let currentConv = null, editingNote = null, lastResults = [], notebookId = localStorage.getItem('notebook') || 'default';
function el(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
let statusTimer;
function status(message, error = false) {
  $('status').textContent = message; $('status').className = error ? 'error' : '';
  clearTimeout(statusTimer); statusTimer = setTimeout(() => { $('status').textContent = ''; }, error ? 9000 : 5000);
}
async function api(path, data) {
  const response = await fetch('/api/' + path, { method: data === undefined ? 'GET' : 'POST', headers: { 'Content-Type': 'application/json', 'X-Research-Token': token, 'X-Notebook-ID': notebookId }, ...(data === undefined ? {} : {body: JSON.stringify(data)}) });
  const result = await response.json(); if (!response.ok) throw new Error(result.error || '操作失败'); return result;
}
function run(fn) { return async event => { try { await fn(event); } catch (error) { status(error.message, true); } }; }
function cite(p) { return `《${p.title}》 · ${p.author || '译者/作者未记录'} · ${p.edition || '版本未记录'} · ${p.page ? 'PDF 第 ' + p.page + ' 页（文件物理页）' : '文本无页码'} · 段 ${p.ordinal} · P${p.passage_id || p.id}`; }
function shortCite(p) { return `《${p.title}》段${p.ordinal} · P${p.passage_id || p.id}`; }
const ICON_TRASH = '<svg class="ico" viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12h10l1-12M9 7V4h6v3"/></svg>';
const ICON_EDIT = '<svg class="ico" viewBox="0 0 24 24"><path d="M4 20l4-1 11-11-3-3L5 16l-1 4z"/></svg>';
function iconButton(svg, title, action) {
  const b = el('button'); b.type = 'button'; b.title = title; b.setAttribute('aria-label', title); b.innerHTML = svg;
  b.addEventListener('click', run(async event => { event.stopPropagation(); await action(); })); return b;
}
function autosize() { const t = $('chat-input'); t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 180) + 'px'; }
function setSidebar(open) { document.body.classList.toggle('side-closed', !open); try { localStorage.setItem('sidebar', open ? '1' : '0'); } catch (e) {} }
function button(text, action) { const b = el('button', text); b.type = 'button'; b.addEventListener('click', run(action)); return b; }

/* ---------- 来源 ---------- */
async function loadBooks() {
  const books = await api('books'), current = $('book-filter').value;
  $('book-filter').replaceChildren(el('option', '全部典籍')); $('book-filter').firstChild.value = '';
  books.forEach(b => { const o = el('option', b.title); o.value = b.id; $('book-filter').append(o); });
  $('book-filter').value = current;
  $('book-count').textContent = books.length ? `${books.length} 部 · ${books.reduce((n, b) => n + b.passages, 0)} 段` : '';
  $('book-list').replaceChildren();
  if (!books.length) $('book-list').append(el('p', '还没有典籍，点“导入”添加。', 'empty muted'));
  books.forEach(b => {
    const row = el('div', undefined, 'side-item'), acts = el('span', undefined, 'acts');
    row.title = '在原文库中检索这部典籍';
    row.addEventListener('click', run(async () => { $('book-filter').value = b.id; $('query').value = ''; selectTab('sources'); await search(); }));
    acts.append(iconButton(ICON_TRASH, '删除典籍', async () => { if (!confirm(`删除《${b.title}》及其全部段落与关联笔记？此操作不可恢复。`)) return;
      await api('book-delete', { id: b.id });
      [...context.keys()].forEach(id => { const p = context.get(id); if (p.book_id === b.id || p.title === b.title) context.delete(id); });
      updateContext(); await loadBooks(); await search(); status('典籍已删除。'); }));
    row.append(el('span', b.title, 'name'), el('span', b.passages + '段', 'count'), acts);
    $('book-list').append(row);
  });
}
async function search(reset = true) {
  if (reset) offset = 0;
  const q = new URLSearchParams({ book: $('book-filter').value, q: $('query').value, offset: String(offset), fold: $('fold-script').checked ? '1' : '0' });
  const result = await api('passages?' + q); total = result.total; lastResults = result.items;
  $('result-count').textContent = `共 ${total} 段${total ? ' · 当前 ' + (offset + 1) + '—' + (offset + result.items.length) : ''}。按文件顺序排列；多个关键词用空格分隔，须同时出现；不做语义扩展；繁简互通默认关闭。`;
  $('results').replaceChildren();
  if (!result.items.length) $('results').append(el('p', '没有匹配的原文。', 'empty'));
  result.items.forEach(p => {
    const card = el('article', undefined, 'passage' + (context.has(p.id) ? ' picked' : ''));
    card.append(el('div', cite(p), 'citation'), highlight(p.text, result.highlight));
    const actions = el('div', undefined, 'toolbar');
    actions.append(
      button('查看全文', () => showSource(p)),
      button('加入对话', () => { addContext(p); card.classList.add('picked'); }),
      button('对照', () => { if (comparison.size >= 2 && !comparison.has(p.id)) throw new Error('对照区最多两段，请先移除一段。'); comparison.set(p.id, p); updateComparison(); }),
      button('写笔记', () => { addContext(p, true); selectTab('notes'); $('note-passage').value = p.id; $('note-body').focus(); }));
    card.append(actions); $('results').append(card);
  });
  $('previous').disabled = offset === 0; $('next').disabled = offset + 100 >= total;
  refreshNotePassages();
}
function highlight(text, forms) {
  const p = el('p', undefined, 'excerpt'), terms = [...new Set(forms)].sort((a, b) => b.length - a.length);
  if (!terms.length) { p.textContent = text; return p; }
  const pattern = new RegExp(terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');
  let start = 0;
  for (const m of text.matchAll(pattern)) { p.append(text.slice(start, m.index), el('mark', m[0])); start = m.index + m[0].length; }
  p.append(text.slice(start));
  return p;
}
function addContext(p, silent) {
  if (context.size >= 20 && !context.has(p.id)) throw new Error('依据原文最多 20 段。');
  if (currentConv) throw new Error('当前对话的依据原文已固定，请先切换到“新对话”。');
  context.set(p.id, p); updateContext(); refreshNotePassages();
  if (!silent) status(`已加入对话依据（${context.size}/20）。`);
}
function updateContext() {
  $('context-count').textContent = context.size;
  $('context-chips').replaceChildren();
  if (!context.size) $('context-chips').append(el('span', '点输入框左下角的“＋”选择依据原文。', 'muted'));
  context.forEach(p => {
    const chip = el('span', undefined, 'chip'); chip.append(button(shortCite(p),()=>showSource(p)));
    if (!currentConv) { const x = el('button', '✕'); x.title = '移除'; x.addEventListener('click', () => { context.delete(p.id); updateContext(); refreshNotePassages(); }); chip.append(x); }
    $('context-chips').append(chip);
  });
  updateSuggestions();
}
function updateSuggestions() {
  $('suggestions').replaceChildren();
  if (currentConv) return;
  ['这些原文的核心论点是什么？', '关键术语在本段中的具体含义？', '各段表述之间有什么差异？'].forEach(q => {
    const b = button(q, () => { $('chat-input').value = q; autosize(); $('chat-input').focus(); });
    $('suggestions').append(b);
  });
}

/* ---------- 对话 ---------- */
let convRows = [];
function updateTitle() { $('chat-title').textContent = currentConv ? currentConv.title : '新对话'; }
async function loadConversations() { convRows = await api('conversations'); renderConversations(); }
function renderConversations() {
  const list = $('conv-list'); list.replaceChildren();
  if (!convRows.length) list.append(el('p', '还没有对话。', 'empty muted'));
  convRows.forEach(c => {
    const row = el('div', undefined, 'side-item' + (currentConv && currentConv.id === c.id ? ' active' : '')), name = el('span', c.title, 'name');
    row.title = c.title;
    row.addEventListener('click', run(() => selectConversation(c.id)));
    const rename = () => {
      const input = el('input'); input.value = c.title; input.maxLength = 60; input.style.margin = '0'; input.setAttribute('aria-label', '对话名称');
      let done = false;
      const finish = run(async save => {
        if (done) return; done = true;
        const title = input.value.trim();
        if (save && title && title !== c.title) {
          await api('conversation-rename', { id: c.id, title });
          if (currentConv && currentConv.id === c.id) { currentConv.title = title.slice(0, 60); updateTitle(); }
        }
        await loadConversations();
      });
      input.addEventListener('click', e => e.stopPropagation());
      input.addEventListener('keydown', e => { if (e.isComposing) return; if (e.key === 'Enter') finish(true); if (e.key === 'Escape') finish(false); });
      input.addEventListener('blur', () => finish(true));
      name.replaceWith(input); input.focus(); input.select();
    };
    const acts = el('span', undefined, 'acts');
    acts.append(iconButton(ICON_EDIT, '重命名', rename),
      iconButton(ICON_TRASH, '删除对话', async () => { if (!confirm(`删除对话“${c.title}”？`)) return;
        await api('conversation-delete', { id: c.id }); if (currentConv && currentConv.id === c.id) newConversation();
        await loadConversations(); status('对话已删除。'); }));
    row.append(name, acts); list.append(row);
  });
}
function showGreeting() {
  const box = el('div', undefined, 'empty');
  box.append(el('h2', '你好，想研读哪段佛典？', 'greeting'), el('p', '从原文出发，保留出处与疑问。', 'greeting-sub'),
    el('p', '点输入框左下角的“＋”检索并选择依据原文，然后提问；回答只引用所选原文并标注 P编号。', 'muted'));
  $('messages').replaceChildren(box);
}
function newConversation() {
  currentConv = null; context.clear(); showGreeting(); updateTitle(); renderConversations(); updateContext();
}
async function selectConversation(id) {
  if (!id) { newConversation(); return; }
  const data = await api('conversation?id=' + id);
  currentConv = data.conversation; context.clear();
  data.conversation.context.forEach(p => context.set(p.id, p));
  $('messages').replaceChildren();
  data.messages.forEach(m => $('messages').append(renderMessage(m)));
  updateTitle(); renderConversations(); updateContext(); scrollMessages();
  refreshNotePassages();
}
function renderMessage(m) {
  const div = el('div', undefined, 'msg ' + m.role);
  div.append(el('div', m.role === 'user' ? '你' : 'AI 助手', 'who'), messageBody(m.body));
  if(m.role==='assistant') div.append(button('保存为笔记',async()=>{const first=[...context.values()][0];if(!first)throw new Error('当前没有关联原文。');await api('notes',{passage_id:first.id,kind:'AI 推断',body:m.body});await loadNotes();selectTab('notes');status('回答已保存为 AI 推断笔记。');}));
  (m.warnings || []).forEach(w => div.append(el('div', '⚠ ' + w, 'warn')));
  div.append(el('div', formatTime(m.created), 'time'));
  return div;
}
function formatTime(iso) { const d = new Date(iso || ''); return isNaN(d) ? '' : d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
function scrollMessages() { $('messages').scrollTop = $('messages').scrollHeight; }
async function sendChat() {
  if (chatBusy || aiBusy) return;
  const text = $('chat-input').value.trim();
  if (!text) throw new Error('请输入问题。');
  if (!currentConv && !context.size) throw new Error('请先在左侧选择依据原文。');
  if (!aiConfig.model) { $('settings-dialog').showModal(); throw new Error('请先配置并保存 AI 接口。'); }
  chatBusy = true; setBusy(true);
  let succeeded=false;
  $('messages').querySelector('.empty')?.remove();
  $('messages').append(renderMessage({ role: 'user', body: text }));
  scrollMessages(); status('AI 正在回答…');
  const thinking = el('div', undefined, 'msg assistant thinking'); thinking.append(el('div', 'AI 助手', 'who'), el('div', '正在研读所选原文', 'body')); $('messages').append(thinking); scrollMessages();
  try {
    const payload = currentConv ? { conversation_id: currentConv.id, message: text } : { ids: [...context.keys()], message: text };
    const r = await api('chat', payload);
    thinking.remove();succeeded=true;
    $('messages').append(renderMessage({ role: 'assistant', body: r.text, warnings: r.warnings }));
    scrollMessages(); $('chat-input').value = ''; autosize(); status('回答已保存到本次对话。');
    await loadConversations(); await selectConversation(r.conversation_id);
  } finally { thinking.remove();chatBusy = false;setBusy(false); if(!succeeded){const pending=$('messages').querySelector('.msg.user:last-of-type');if(pending)pending.remove();if(!currentConv&&!$('messages').children.length)showGreeting();status('请求失败，问题仍保留，可重试。',true);} }
}

/* ---------- 右栏：对照 / 笔记 / 分析 ---------- */
function selectTab(name) { $('drawer').hidden = false; document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name)); ['sources', 'compare', 'notes', 'analyses'].forEach(t => $('tab-' + t).hidden = t !== name); }
document.querySelectorAll('.tabs button').forEach(b => b.addEventListener('click', () => selectTab(b.dataset.tab)));
function updateComparison() {
  $('comparison').replaceChildren();
  if (!comparison.size) $('comparison').append(el('p', '尚未加入原文。', 'empty'));
  comparison.forEach(p => { const card = el('div', undefined, 'panel'); card.append(el('div', cite(p), 'citation'), el('p', p.text, 'source'), button('移除', () => { comparison.delete(p.id); updateComparison(); })); $('comparison').append(card); });
}
function refreshNotePassages() {
  const sel = $('note-passage'), cur = sel.value;
  sel.replaceChildren();
  const seen = new Set();
  [...context.values(), ...lastResults].forEach(p => { if (seen.has(p.id)) return; seen.add(p.id); const o = el('option', shortCite(p)); o.value = p.id; sel.append(o); });
  if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
}
async function loadNotes() {
  const notes = await api('notes'); $('notes-list').replaceChildren();
  if (!notes.length) $('notes-list').append(el('p', '还没有笔记。', 'empty'));
  notes.forEach(n => {
    const card = el('div', undefined, 'note-card');
    card.append(el('span', n.kind, 'tag'), el('p', cite(n), 'citation'), el('p', n.body, 'body'), el('p', n.created, 'muted'));
    const actions = el('div', undefined, 'actions');
    actions.append(button('编辑', () => { editingNote = n.id; $('note-passage').required=false; $('note-passage').disabled=true; $('note-passage').value = n.passage_id; $('note-kind').value = n.kind; $('note-body').value = n.body; $('note-submit').textContent = '保存修改'; $('note-cancel').hidden = false; $('note-body').focus(); }),
      button('删除', async () => { if (!confirm('删除这条笔记？')) return; await api('note-delete', { id: n.id }); await loadNotes(); status('笔记已删除。'); }));
    card.append(actions); $('notes-list').append(card);
  });
}
function renderAnalysis(a) {
  const card = el('article', undefined, 'panel');
  card.append(el('span', 'AI 推断 · 待人工核查', 'tag'), el('p', `分析 ${a.id} · ${a.model} · ${a.created}`, 'citation'), el('p', a.question || '原文分析'));
  (a.warnings || []).forEach(w => card.append(el('p', '⚠ ' + w, 'muted')));
  card.append(el('div', a.body, 'source'));
  if (a.evidence) { const d = el('details'); d.append(el('summary', '查看本次分析的原文快照')); a.evidence.forEach(p => { const c = el('div', undefined, 'panel'); c.append(el('div', cite(p), 'citation'), el('p', p.text, 'source')); d.append(c); }); card.append(d); }
  return card;
}
async function loadAnalyses() {
  $('analysis-history').replaceChildren(); $('analysis-history').append(el('h2', '分析记录'));
  const rows = await api('analyses');
  if (!rows.length) $('analysis-history').append(el('p', '暂无分析记录。', 'empty'));
  rows.forEach(a => $('analysis-history').append(renderAnalysis(a)));
}

/* ---------- 设置 / 导入 / 导出 ---------- */
async function loadSettings() {
  aiConfig = await api('settings');
  $('api-base').value = aiConfig.base_url; $('api-model').value = aiConfig.model;
  $('api-tokens').value = aiConfig.max_tokens; $('api-token-field').value = aiConfig.token_field;
  $('remember-key').checked = aiConfig.key_saved; $('remember-key').disabled = !aiConfig.can_save_key;
  $('ai-destination').textContent=`AI 接口：${aiConfig.base_url} · 模型：${aiConfig.model||'尚未配置'}。发起请求会发送所选原文及最近对话。`;
  $('key-status').textContent = aiConfig.has_key ? (aiConfig.key_saved ? '密钥已由 Windows 加密保存。' : '密钥仅在本次程序运行期间有效。') : '尚未填写密钥。本机无密钥服务可留空。';
}
async function download(name, text, type) { if(window.pywebview?.api){const r=await window.pywebview.api.save_text(name,text);status(r.saved?'文件已保存。':'已取消保存。');return;}  const u = URL.createObjectURL(new Blob([text], { type })); const a = el('a'); a.href = u; a.download = name; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 1000); }

/* ---------- 事件 ---------- */
$('search').addEventListener('click', run(() => search()));
$('query').addEventListener('keydown', run(e => { if (e.key === 'Enter') return search(); }));
$('book-filter').addEventListener('change', run(() => search()));
$('fold-script').addEventListener('change', run(() => search()));
$('previous').addEventListener('click', run(() => { offset = Math.max(0, offset - 100); return search(false); }));
$('next').addEventListener('click', run(() => { offset += 100; return search(false); }));
$('new-chat').addEventListener('click', () => { newConversation(); $('chat-input').focus(); });
$('toggle-sidebar').addEventListener('click', () => setSidebar(false));
$('open-sidebar').addEventListener('click', () => setSidebar(true));
$('open-drawer').addEventListener('click', () => { if ($('drawer').hidden) selectTab('sources'); else $('drawer').hidden = true; });
$('add-source').addEventListener('click', () => { selectTab('sources'); $('query').focus(); });
$('close-drawer').addEventListener('click', () => { $('drawer').hidden = true; });
$('chat-input').addEventListener('input', autosize);
$('send-chat').addEventListener('click', run(sendChat));
$('chat-input').addEventListener('keydown', run(e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); return sendChat(); } }));
$('btn-analyze').addEventListener('click', run(async () => {
  if (aiBusy || chatBusy) return; if (!context.size) throw new Error('请先在左侧选择依据原文。');
  if (!aiConfig.model) { $('settings-dialog').showModal(); throw new Error('请先配置并保存 AI 接口。'); }
  const ids = [...context.keys()], question = $('analysis-question').value || $('chat-input').value;
  aiBusy = true; setBusy(true);selectTab('analyses'); status('正在生成结构化分析，可能需要几分钟…');
  try { const r = await api('analyze', { ids, question }); $('ai-result').replaceChildren(renderAnalysis({ ...r, question })); await loadAnalyses(); status('结构化分析已保存。'); }
  finally { aiBusy = false;setBusy(false); }
}));
$('btn-make-prompt').addEventListener('click', run(async () => { const r = await api('prompt', { ids: [...context.keys()], question: $('analysis-question').value }); $('prompt').value = r.prompt; status('提示词已生成；尚未执行 AI 分析。'); }));
$('download-prompt').addEventListener('click', run(() => { if (!$('prompt').value) throw new Error('请先生成提示词。'); download('research-prompt.txt', $('prompt').value, 'text/plain;charset=utf-8'); }));
$('note-form').addEventListener('submit', run(async e => {
  e.preventDefault();
  const payload = { passage_id: Number($('note-passage').value), kind: $('note-kind').value, body: $('note-body').value };
  if (editingNote) { await api('note-update', { id: editingNote, ...payload }); editingNote = null; $('note-passage').required=true;$('note-passage').disabled=false; $('note-submit').textContent = '保存笔记'; $('note-cancel').hidden = true; status('笔记已更新。'); }
  else { await api('notes', payload); status('笔记已保存。'); }
  $('note-body').value = ''; await loadNotes();
}));
$('note-cancel').addEventListener('click', () => { editingNote = null; $('note-passage').required=true;$('note-passage').disabled=false; $('note-submit').textContent = '保存笔记'; $('note-cancel').hidden = true; $('note-body').value = ''; });
$('btn-import').addEventListener('click', () => $('import-dialog').showModal());
$('btn-settings').addEventListener('click', () => $('settings-dialog').showModal());
$('import-form').addEventListener('submit', run(async e => {
  e.preventDefault(); const form = e.target, file = form.elements.file.files[0];
  if (!file) throw new Error('请选择文件。'); if (file.size > 25 * 1024 * 1024) throw new Error('文件上限 25 MB。');
  const submit = form.querySelector('button[type=submit]'); submit.disabled = true; status('正在提取文字并建立索引…');
  try {
    const data = await new Promise((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(r.result.split(',')[1]); r.onerror = () => reject(new Error('文件读取失败。')); r.readAsDataURL(file); });
    const result = await api('import', { filename: file.name, data, title: form.elements.title.value, author: form.elements.author.value, edition: form.elements.edition.value });
    await loadBooks(); $('book-filter').value = result.id; $('query').value = ''; await search(); form.reset(); $('import-dialog').close();
    status(`导入成功：${result.passages} 段。${result.empty_pages ? '有 ' + result.empty_pages + ' 页未提取到文字，请核查原 PDF。' : ''}`);
  } finally { submit.disabled = false; }
}));
$('settings-form').addEventListener('submit', run(async e => { e.preventDefault(); await api('settings', { base_url: $('api-base').value, model: $('api-model').value, api_key: $('api-key').value, max_tokens: Number($('api-tokens').value), token_field: $('api-token-field').value, remember_key: $('remember-key').checked }); $('api-key').value = ''; await loadSettings(); $('settings-dialog').close(); status('AI 设置已保存。'); }));
$('forget-key').addEventListener('click', run(async () => { await api('settings', { ...aiConfig, clear_key: true, remember_key: false }); $('api-key').value = ''; await loadSettings(); status('密钥已清除。'); }));
$('test-ai').addEventListener('click', run(async () => { const b = $('test-ai'); b.disabled = true; status('正在测试已保存的接口配置…'); try { const r = await api('ai-test', {}); status(r.message); } finally { b.disabled = false; } }));
$('btn-export-md').addEventListener('click', run(async () => download('research-notes.md', (await api('export')).markdown, 'text/markdown;charset=utf-8')));
$('btn-export-json').addEventListener('click', run(async () => download('research-data.json', JSON.stringify((await api('export')).backup, null, 2), 'application/json;charset=utf-8')));
run(async () => { token = (await api('session')).token; await loadNotebooks(); await loadBooks(); await search(); await loadNotes(); await loadAnalyses(); updateContext(); updateComparison(); newConversation(); await loadConversations(); await loadSettings(); })();

function showSource(p){$('source-citation').textContent=cite(p);$('source-body').textContent=p.text;$('source-dialog').showModal();}
function citeButton(label,p){const b=button(label,()=>showSource(p));b.title=p.text.slice(0,120)+(p.text.length>120?'…':'');return b;}
function messageBody(text){const body=el('div',undefined,'body');const pattern=/\bP(\d+)\b/g;let start=0;for(const m of text.matchAll(pattern)){body.append(document.createTextNode(text.slice(start,m.index)));const p=context.get(Number(m[1]));body.append(p?citeButton(m[0],p):document.createTextNode(m[0]));start=m.index+m[0].length;}body.append(document.createTextNode(text.slice(start)));return body;}
function setBusy(busy){['notebook-select','new-notebook','new-chat','add-source','btn-import','book-filter','send-chat','btn-analyze'].forEach(id=>$(id).disabled=busy);}
async function loadNotebooks(){const rows=await api('notebooks');if(!rows.some(r=>r.id===notebookId))notebookId='default';$('notebook-select').replaceChildren();rows.forEach(r=>{const o=el('option',r.name);o.value=r.id;$('notebook-select').append(o);});$('notebook-select').value=notebookId;}
async function switchNotebook(id){if(chatBusy||aiBusy)throw new Error('请等待当前分析完成。');notebookId=id;localStorage.setItem('notebook',id);context.clear();comparison.clear();editingNote=null;lastResults=[];$('query').value='';$('book-filter').value='';$('note-cancel').click();$('chat-input').value='';$('analysis-question').value='';$('ai-result').replaceChildren();$('prompt').value='';newConversation();updateComparison();await loadBooks();await search();await loadNotes();await loadAnalyses();await loadConversations();status('已切换研究本。');}
$('notebook-select').addEventListener('change',run(e=>switchNotebook(e.target.value)));
$('new-notebook').addEventListener('click',()=>{$('notebook-dialog').showModal();$('notebook-name').focus();});
$('notebook-form').addEventListener('submit',run(async e=>{e.preventDefault();const n=await api('notebook-create',{name:$('notebook-name').value});await loadNotebooks();await switchNotebook(n.id);$('notebook-select').value=n.id;$('notebook-dialog').close();$('notebook-name').value='';}));
$('open-data').addEventListener('click',run(async()=>{if(window.pywebview?.api)await window.pywebview.api.open_data_folder();else status('源码模式的数据目录位于项目 data 文件夹。');}));
try { if (localStorage.getItem('sidebar') === '0' || innerWidth < 860) setSidebar(false); } catch (e) {}
