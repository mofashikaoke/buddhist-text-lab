'use strict';
/* Notebook workspace: home (list of notebooks) -> sources | chat | Studio. */
const $ = id => document.getElementById(id);
const S = { nb: null, books: [], notes: [], convs: [], conv: null, reader: null, busy: false, studioBusy: new Set() };
let token = '', aiConfig = {}, statusTimer, nbEditing = null, noteState = null, viewing = null;

const ICON = {
  trash: '<svg class="ico" viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12h10l1-12M9 7V4h6v3"/></svg>',
  edit: '<svg class="ico" viewBox="0 0 24 24"><path d="M4 20l4-1 11-11-3-3L5 16l-1 4z"/></svg>',
  plus: '<svg class="ico" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
  back: '<svg class="ico" viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/></svg>',
};
const ORIGIN = { manual: '手动', chat: '对话', studio: 'Studio', analysis: '分析' };
const TILES = [
  { kind: 'summary', title: '来源摘要', desc: '主旨、脉络与核心主张' },
  { kind: 'glossary', title: '术语表', desc: '关键术语及其出处' },
  { kind: 'structure', title: '论证结构', desc: '前提、推导与结论' },
  { kind: 'questions', title: '研究问题', desc: '值得继续追问的问题' },
  { kind: 'analysis', title: '深度分析', desc: '针对一个问题，先找最强反驳', wide: true },
];
const SUGGESTIONS = ['这些来源的核心论点是什么？', '关键术语在材料中的具体含义？', '不同来源的表述有什么差异？', '有哪些值得核查的疑点？'];

/* ---------- utilities ---------- */
function el(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
function status(message, error = false) {
  $('status').textContent = message; $('status').className = error ? 'error' : '';
  clearTimeout(statusTimer); statusTimer = setTimeout(() => { $('status').textContent = ''; }, error ? 9000 : 5000);
}
async function api(path, data) {
  const headers = { 'Content-Type': 'application/json', 'X-Research-Token': token, 'X-Notebook-ID': S.nb ? S.nb.id : 'default' };
  const response = await fetch('/api/' + path, { method: data === undefined ? 'GET' : 'POST', headers, ...(data === undefined ? {} : { body: JSON.stringify(data) }) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '操作失败');
  return result;
}
function run(fn) { return async event => { try { await fn(event); } catch (error) { status(error.message, true); } }; }
function button(text, action) { const b = el('button', text); b.type = 'button'; b.addEventListener('click', run(action)); return b; }
function iconButton(svg, title, action) {
  const b = el('button'); b.type = 'button'; b.title = title; b.setAttribute('aria-label', title); b.innerHTML = svg;
  b.addEventListener('click', run(async event => { event.stopPropagation(); await action(event); })); return b;
}
function formatTime(iso) { const d = new Date(iso || ''); return isNaN(d) ? '' : d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
function formatChars(n) { return n >= 10000 ? (n / 10000).toFixed(1) + ' 万字' : n + ' 字'; }
function cite(p) { return `《${p.title}》 · ${p.author || '译者/作者未记录'} · ${p.edition || '版本未记录'} · ${p.page ? 'PDF 第 ' + p.page + ' 页（文件物理页）' : '文本无页码'} · 段 ${p.ordinal} · P${p.passage_id || p.id}`; }
function autosize() { const t = $('chat-input'); if (!t.offsetWidth) return; t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 180) + 'px'; }
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); }
  catch (e) { const t = el('textarea'); t.value = text; document.body.append(t); t.select(); document.execCommand('copy'); t.remove(); }
  status('已复制。');
}
async function download(name, text, type) {
  if (window.pywebview?.api) { const r = await window.pywebview.api.save_text(name, text); status(r.saved ? '文件已保存。' : '已取消保存。'); return; }
  const u = URL.createObjectURL(new Blob([text], { type })), a = el('a'); a.href = u; a.download = name; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 1000);
}
function highlight(text, forms) {
  const p = el('p', undefined, 'excerpt'), terms = [...new Set(forms || [])].sort((a, b) => b.length - a.length);
  if (!terms.length) { p.textContent = text; return p; }
  const pattern = new RegExp(terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');
  let start = 0;
  for (const m of text.matchAll(pattern)) { p.append(text.slice(start, m.index), el('mark', m[0])); start = m.index + m[0].length; }
  p.append(text.slice(start));
  return p;
}

/* ---------- rich text for answers and notes (small, DOM-based markdown subset) ---------- */
function citeButton(label, p) {
  const b = button(label, () => showPassage(p)); b.classList.add('cite');
  b.title = p.text.slice(0, 120) + (p.text.length > 120 ? '…' : ''); return b;
}
function inline(parent, text, byId) {
  let last = 0;
  for (const m of text.matchAll(/\*\*(.+?)\*\*|`([^`]+)`|\bP(\d+)\b/g)) {
    parent.append(text.slice(last, m.index));
    if (m[1] !== undefined) parent.append(el('strong', m[1]));
    else if (m[2] !== undefined) parent.append(el('code', m[2]));
    else { const p = byId.get(Number(m[3])); parent.append(p ? citeButton(m[0], p) : m[0]); }
    last = m.index + m[0].length;
  }
  parent.append(text.slice(last));
}
function richText(text, evidence = []) {
  const byId = new Map(evidence.map(p => [p.id, p])), root = el('div', undefined, 'rich');
  let para = [], list = null, quote = null;
  const flushPara = () => {
    if (!para.length) return;
    const p = el('p'); para.forEach((line, i) => { if (i) p.append(el('br')); inline(p, line, byId); }); root.append(p); para = [];
  };
  const reset = () => { flushPara(); list = null; quote = null; };
  for (const raw of text.replace(/\r\n/g, '\n').split('\n')) {
    const line = raw.trimEnd();
    let m;
    if (!line.trim()) { reset(); continue; }
    if ((m = line.match(/^(#{1,4})\s+(.*)$/))) { reset(); const h = el('h' + (m[1].length === 1 ? 4 : m[1].length === 2 ? 5 : 6)); inline(h, m[2], byId); root.append(h); continue; }
    if ((m = line.match(/^\s*([-*•]|\d+[.)、])\s+(.*)$/))) {
      flushPara(); quote = null;
      const tag = /\d/.test(m[1]) ? 'ol' : 'ul';
      if (!list || list.tagName.toLowerCase() !== tag) { list = el(tag); root.append(list); }
      const li = el('li'); inline(li, m[2], byId); list.append(li); continue;
    }
    if ((m = line.match(/^>\s?(.*)$/))) {
      flushPara(); list = null;
      if (!quote) { quote = el('blockquote'); root.append(quote); } else quote.append(el('br'));
      inline(quote, m[1], byId); continue;
    }
    list = null; quote = null; para.push(line);
  }
  flushPara();
  return root;
}

/* ---------- home: notebooks ---------- */
async function showHome() {
  S.nb = null; $('workspace').hidden = true; $('home').hidden = false;
  renderHome(await api('notebooks'));
}
function hue(id) { return [...id].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 0); }
function renderHome(rows) {
  const grid = $('nb-grid'); grid.replaceChildren();
  const fresh = el('div', undefined, 'nb-card nb-new'); fresh.tabIndex = 0;
  const plus = el('span', undefined, 'plus'); plus.innerHTML = ICON.plus;
  fresh.append(plus, el('b', '新建研究本'));
  fresh.addEventListener('click', () => openNbDialog(null));
  fresh.addEventListener('keydown', e => { if (e.key === 'Enter') openNbDialog(null); });
  grid.append(fresh);
  rows.forEach(r => {
    const card = el('div', undefined, 'nb-card'); card.style.setProperty('--h', hue(r.id)); card.tabIndex = 0;
    const acts = el('div', undefined, 'acts');
    acts.append(iconButton(ICON.edit, '重命名', () => openNbDialog(r)));
    if (r.id !== 'default') acts.append(iconButton(ICON.trash, '删除研究本', async () => {
      if (!confirm(`删除研究本“${r.name}”及其全部来源、对话和笔记？此操作不可恢复。`)) return;
      await api('notebook-delete', { id: r.id }); await showHome(); status('研究本已删除。');
    }));
    card.append(el('h3', r.name), el('div', `${r.sources} 个来源 · ${r.notes} 条笔记 · ${r.conversations} 个对话`, 'meta'),
      el('div', `更新于 ${formatTime(r.updated)}`, 'meta'), acts);
    card.addEventListener('click', run(() => openNotebook(r)));
    card.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target === card) run(() => openNotebook(r))(); });
    grid.append(card);
  });
}
function openNbDialog(row) {
  nbEditing = row; $('nb-heading').textContent = row ? '重命名研究本' : '新建研究本'; $('nb-submit').textContent = row ? '保存' : '创建';
  $('nb-name').value = row ? row.name : ''; $('nb-dialog').showModal(); $('nb-name').focus(); $('nb-name').select();
}
$('nb-form').addEventListener('submit', run(async e => {
  e.preventDefault();
  const name = $('nb-name').value;
  if (nbEditing) {
    const r = await api('notebook-rename', { id: nbEditing.id, name });
    if (S.nb && S.nb.id === r.id) { S.nb.name = r.name; $('nb-title').textContent = r.name; }
    $('nb-dialog').close(); if (!$('home').hidden) await showHome();
  } else {
    const r = await api('notebook-create', { name });
    $('nb-dialog').close(); await openNotebook({ ...r, sources: 0, notes: 0, conversations: 0 });
  }
}));

/* ---------- workspace ---------- */
async function openNotebook(row) {
  S.nb = row; S.books = []; S.notes = []; S.convs = []; S.conv = null; S.reader = null;
  $('home').hidden = true; $('workspace').hidden = false; $('nb-title').textContent = row.name;
  renderTiles(); newChat();
  await Promise.all([loadBooks(), loadNotes(), loadConvs()]);
  setPane(S.books.length ? 'chat' : 'sources');
}
function setPane(name) {
  $('panes').dataset.active = name;
  document.querySelectorAll('#mtabs button').forEach(b => b.classList.toggle('active', b.dataset.pane === name));
}
document.querySelectorAll('#mtabs button').forEach(b => b.addEventListener('click', () => setPane(b.dataset.pane)));
$('back-home').addEventListener('click', run(showHome));
$('nb-title').addEventListener('click', () => { if (S.nb) openNbDialog(S.nb); });

/* ---------- sources ---------- */
async function loadBooks() { S.books = await api('books'); renderSources(); updateScope(); }
function enabledBooks() { return S.books.filter(b => b.enabled); }
function updateScope() {
  const on = enabledBooks(), chars = on.reduce((n, b) => n + b.chars, 0), all = $('select-all');
  $('scope-count').textContent = S.books.length ? `${on.length}/${S.books.length} 已启用` : '';
  all.disabled = !S.books.length; all.checked = S.books.length > 0 && on.length === S.books.length; all.indeterminate = on.length > 0 && on.length < S.books.length;
  $('scope-pill').textContent = on.length ? `基于 ${on.length} 个来源 · ${formatChars(chars)}` : '未启用任何来源';
  $('scope-pill').classList.toggle('warn', !on.length);
  if (!S.conv && !$('messages').querySelector('.msg')) { showGreeting(); renderSuggestions(); }
}
function renderSources() { if (S.reader) renderReader(); else renderSourceList(); }
function renderSourceList() {
  const body = $('sources-body'); body.replaceChildren(); $('source-controls').hidden = false;
  if (!S.books.length) {
    const card = el('div', undefined, 'empty-card');
    card.append(el('div', '添加来源以开始', 'big'), el('p', '导入 PDF、TXT 或 Markdown，也可以把文件拖到这里。', 'muted'), button('导入典籍', () => openImport()));
    body.append(card); return;
  }
  S.books.forEach(b => {
    const row = el('div', undefined, 'src' + (b.enabled ? '' : ' off')), box = el('input');
    box.type = 'checkbox'; box.checked = !!b.enabled; box.setAttribute('aria-label', '启用 ' + b.title);
    box.addEventListener('click', e => e.stopPropagation());
    box.addEventListener('change', run(async () => { await api('book-enable', { id: b.id, enabled: box.checked }); b.enabled = box.checked ? 1 : 0; renderSourceList(); updateScope(); }));
    const name = el('div', undefined, 'name');
    name.append(el('b', b.title), el('span', `${b.passages} 段 · ${formatChars(b.chars)}${b.author ? ' · ' + b.author : ''}`));
    const acts = el('span', undefined, 'acts');
    acts.append(iconButton(ICON.trash, '删除来源', async () => {
      if (!confirm(`删除《${b.title}》及其全部段落？已有对话和笔记会保留各自引用的原文快照。`)) return;
      await api('book-delete', { id: b.id }); await loadBooks(); status('来源已删除。');
    }));
    row.title = '点击阅读原文'; row.append(box, name, acts);
    row.addEventListener('click', run(() => openReader(b)));
    body.append(row);
  });
}
$('select-all').addEventListener('change', run(async e => { await api('book-enable', { id: null, enabled: e.target.checked }); await loadBooks(); }));

/* reader: the passages of one source, with search */
function openReader(book) { S.reader = { book, offset: 0, query: '', fold: false, total: 0 }; renderReader(); return loadReader(); }
function renderReader() {
  const r = S.reader, body = $('sources-body'); body.replaceChildren(); $('source-controls').hidden = true;
  const head = el('div', undefined, 'reader-head');
  head.append(iconButton(ICON.back, '返回来源列表', () => { S.reader = null; renderSources(); }), el('b', r.book.title));
  const query = el('input'); query.id = 'query'; query.placeholder = '在这部典籍中检索，空格分隔多个词'; query.value = r.query;
  query.addEventListener('keydown', run(e => { if (e.key === 'Enter' && !e.isComposing) { r.query = query.value; r.offset = 0; return loadReader(); } }));
  const fold = el('label', undefined, 'fold'), foldBox = el('input'); foldBox.type = 'checkbox'; foldBox.checked = r.fold;
  foldBox.addEventListener('change', run(() => { r.fold = foldBox.checked; r.query = query.value; r.offset = 0; return loadReader(); }));
  fold.append(foldBox, document.createTextNode(' 繁简互通'));
  const bar = el('div', undefined, 'toolbar');
  bar.append(button('检索', () => { r.query = query.value; r.offset = 0; return loadReader(); }),
    button('‹', () => { r.offset = Math.max(0, r.offset - 100); return loadReader(); }),
    button('›', () => { r.offset += 100; return loadReader(); }));
  bar.children[1].id = 'prev-page'; bar.children[2].id = 'next-page';
  const count = el('p', undefined, 'muted'); count.id = 'reader-count';
  const results = el('div'); results.id = 'results';
  body.append(head, query, fold, bar, count, results);
}
async function loadReader() {
  const r = S.reader, q = new URLSearchParams({ book: r.book.id, q: r.query, offset: String(r.offset), fold: r.fold ? '1' : '0' });
  const res = await api('passages?' + q);
  if (S.reader !== r) return;
  r.total = res.total;
  $('reader-count').textContent = res.total ? `共 ${res.total} 段 · 当前 ${r.offset + 1}—${r.offset + res.items.length}${r.query.trim() ? '；多个关键词须同时出现' : ''}` : '没有匹配的原文。';
  $('prev-page').disabled = r.offset === 0; $('next-page').disabled = r.offset + 100 >= res.total;
  const box = $('results'); box.replaceChildren();
  res.items.forEach(p => {
    const card = el('article', undefined, 'passage');
    const acts = el('div', undefined, 'toolbar');
    acts.append(button('存为笔记', () => openNote(null, [p])), button('复制引文', () => copyText(cite(p) + '\n' + p.text)));
    card.append(el('div', `段 ${p.ordinal}${p.page ? ' · PDF 第 ' + p.page + ' 页' : ''} · P${p.id}`, 'citation'), highlight(p.text, res.highlight), acts);
    box.append(card);
  });
  $('sources-body').scrollTop = 0;
}

/* import: dialog, drag and drop */
function openImport(file) {
  const form = $('import-form');
  if (file) {
    const dt = new DataTransfer(); dt.items.add(file); form.elements.file.files = dt.files;
    if (!form.elements.title.value) form.elements.title.value = file.name.replace(/\.[^.]+$/, '');
  }
  $('import-dialog').showModal();
}
$('add-source').addEventListener('click', () => openImport());
$('import-form').elements.file.addEventListener('change', e => {
  const f = e.target.files[0], title = $('import-form').elements.title;
  if (f && !title.value) title.value = f.name.replace(/\.[^.]+$/, '');
});
const dropZone = $('panel-sources');
['dragenter', 'dragover'].forEach(t => dropZone.addEventListener(t, e => { if (e.dataTransfer?.types.includes('Files')) { e.preventDefault(); dropZone.classList.add('drop'); } }));
['dragleave', 'drop'].forEach(t => dropZone.addEventListener(t, e => { if (t === 'dragleave' && dropZone.contains(e.relatedTarget)) return; dropZone.classList.remove('drop'); }));
dropZone.addEventListener('drop', e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) openImport(f); });
$('import-form').addEventListener('submit', run(async e => {
  e.preventDefault(); const form = e.target, file = form.elements.file.files[0];
  if (!file) throw new Error('请选择文件。'); if (file.size > 25 * 1024 * 1024) throw new Error('文件上限 25 MB。');
  const submit = form.querySelector('button[type=submit]'); submit.disabled = true; status('正在提取文字并建立索引…');
  try {
    const data = await new Promise((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(r.result.split(',')[1]); r.onerror = () => reject(new Error('文件读取失败。')); r.readAsDataURL(file); });
    const result = await api('import', { filename: file.name, data, title: form.elements.title.value, author: form.elements.author.value, edition: form.elements.edition.value });
    S.reader = null; await loadBooks(); form.reset(); $('import-dialog').close();
    status(`导入成功：${result.passages} 段，已启用。${result.empty_pages ? '有 ' + result.empty_pages + ' 页未提取到文字，请核查原 PDF。' : ''}`);
  } finally { submit.disabled = false; }
}));

/* ---------- passage viewer ---------- */
function showPassage(p) { viewing = p; $('source-citation').textContent = cite(p); $('source-body').textContent = p.text; $('source-dialog').showModal(); }
$('source-note').addEventListener('click', () => { $('source-dialog').close(); openNote(null, [viewing]); });
$('source-copy').addEventListener('click', () => copyText(cite(viewing) + '\n' + viewing.text));

/* ---------- chat ---------- */
async function loadConvs() { S.convs = await api('conversations'); renderHistory(); }
function newChat() {
  S.conv = null; $('chat-title').textContent = '新对话'; $('history').hidden = true;
  showGreeting(); renderSuggestions(); renderHistory();
}
function showGreeting() {
  const box = el('div', undefined, 'empty'), on = enabledBooks();
  if (!S.books.length) box.append(el('h2', '先添加一些来源', 'greeting'), el('p', '在左侧“来源”中导入典籍，然后围绕它们提问。', 'muted'));
  else if (!on.length) box.append(el('h2', '请启用至少一个来源', 'greeting'), el('p', '在左侧勾选要参与对话的典籍。', 'muted'));
  else box.append(el('h2', '你好，想研读哪段佛典？', 'greeting'), el('p', `已启用 ${on.length} 个来源，直接提问即可。`, 'greeting-sub'),
    el('p', '回答只依据已启用的来源，并标注 P编号；点击编号查看原文。较长的来源会按问题检索相关段落。', 'muted'));
  $('messages').replaceChildren(box);
}
function renderSuggestions() {
  const box = $('suggestions'); box.replaceChildren();
  if (S.conv || !enabledBooks().length) return;
  SUGGESTIONS.forEach(q => box.append(button(q, () => { $('chat-input').value = q; autosize(); $('chat-input').focus(); })));
}
async function selectConv(id) {
  const data = await api('conversation?id=' + id);
  S.conv = data.conversation; $('chat-title').textContent = S.conv.title; $('history').hidden = true;
  $('messages').replaceChildren(...data.messages.map(m => renderMessage(m, m.evidence.length ? m.evidence : S.conv.context)));
  renderSuggestions(); renderHistory(); scrollThread();
}
function renderMessage(m, evidence) {
  if (m.role === 'user') return el('div', m.body, 'msg user');
  const div = el('div', undefined, 'msg assistant');
  div.append(richText(m.body, evidence));
  (m.warnings || []).forEach(w => div.append(el('div', '⚠ ' + w, 'warn')));
  const acts = el('div', undefined, 'msg-actions');
  acts.append(button('保存到笔记', async () => {
    const note = await api('notes', { message_id: m.id, title: S.conv ? S.conv.title : '' });
    S.notes.unshift(note); renderNotes(); status('回答已保存为笔记，只保留其引用的原文。');
  }), button('复制', () => copyText(m.body)));
  div.append(acts, el('div', formatTime(m.created), 'time'));
  return div;
}
function scrollThread() { $('thread').scrollTop = $('thread').scrollHeight; }
function setBusy(busy) { S.busy = busy; $('send-chat').disabled = busy; $('new-chat').disabled = busy; }
async function sendChat() {
  if (S.busy) return;
  const text = $('chat-input').value.trim();
  if (!text) throw new Error('请输入问题。');
  if (!enabledBooks().length) throw new Error('请先在“来源”中添加并启用至少一个典籍。');
  if (!aiConfig.model) { $('settings-dialog').showModal(); throw new Error('请先配置并保存 AI 接口。'); }
  setBusy(true);
  const box = $('messages'); box.querySelector('.empty')?.remove(); $('suggestions').replaceChildren();
  const mine = el('div', text, 'msg user'), thinking = el('div', undefined, 'msg assistant thinking');
  thinking.append(el('div', '正在检索并研读来源', 'rich')); box.append(mine, thinking); scrollThread();
  $('chat-input').value = ''; autosize(); status('AI 正在回答…');
  try {
    const r = await api('chat', { conversation_id: S.conv ? S.conv.id : undefined, message: text });
    await loadConvs(); await selectConv(r.conversation_id); status('回答已保存到本次对话。');
  } catch (error) {
    mine.remove(); thinking.remove(); $('chat-input').value = text; autosize();
    if (!S.conv && !box.children.length) { showGreeting(); renderSuggestions(); }
    throw error;
  } finally { setBusy(false); }
}
$('send-chat').addEventListener('click', run(sendChat));
$('chat-input').addEventListener('input', autosize);
window.addEventListener('resize', autosize);
$('chat-input').addEventListener('keydown', run(e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); return sendChat(); } }));
$('new-chat').addEventListener('click', () => { newChat(); $('chat-input').focus(); });
$('toggle-history').addEventListener('click', e => { e.stopPropagation(); $('history').hidden = !$('history').hidden; });
document.addEventListener('click', e => { if (!$('history').hidden && !e.target.closest('#history')) $('history').hidden = true; });

function renderHistory() {
  const box = $('history'); box.replaceChildren();
  if (!S.convs.length) box.append(el('p', '还没有对话。', 'muted'));
  S.convs.forEach(c => {
    const row = el('div', undefined, 'hist-item' + (S.conv && S.conv.id === c.id ? ' active' : '')), name = el('span', c.title, 'name');
    row.title = c.title; row.addEventListener('click', run(() => selectConv(c.id)));
    const rename = () => {
      const input = el('input'); input.value = c.title; input.maxLength = 60; input.setAttribute('aria-label', '对话名称');
      let done = false;
      const finish = run(async save => {
        if (done) return; done = true;
        const title = input.value.trim();
        if (save && title && title !== c.title) {
          await api('conversation-rename', { id: c.id, title });
          if (S.conv && S.conv.id === c.id) { S.conv.title = title.slice(0, 60); $('chat-title').textContent = S.conv.title; }
        }
        await loadConvs(); $('history').hidden = false;
      });
      input.addEventListener('click', e => e.stopPropagation());
      input.addEventListener('keydown', e => { if (e.isComposing) return; if (e.key === 'Enter') finish(true); if (e.key === 'Escape') finish(false); });
      input.addEventListener('blur', () => finish(true));
      name.replaceWith(input); input.focus(); input.select();
    };
    const acts = el('span', undefined, 'acts');
    acts.append(iconButton(ICON.edit, '重命名', rename), iconButton(ICON.trash, '删除对话', async () => {
      if (!confirm(`删除对话“${c.title}”？`)) return;
      await api('conversation-delete', { id: c.id }); if (S.conv && S.conv.id === c.id) newChat();
      await loadConvs(); $('history').hidden = false; status('对话已删除。');
    }));
    row.append(name, acts); box.append(row);
  });
}

/* ---------- Studio and notes ---------- */
function renderTiles() {
  const box = $('studio-tiles'); box.replaceChildren();
  TILES.forEach(t => {
    const b = el('button', undefined, 'tile' + (t.wide ? ' wide' : '')); b.type = 'button'; b.dataset.kind = t.kind;
    b.append(el('b', t.title), el('span', t.desc));
    b.addEventListener('click', run(() => t.kind === 'analysis' ? openAnalysis() : runStudio(t)));
    box.append(b);
  });
}
async function runStudio(tile, question = '') {
  if (S.studioBusy.has(tile.kind)) return;
  if (!enabledBooks().length) throw new Error('请先在“来源”中添加并启用至少一个典籍。');
  if (!aiConfig.model) { $('settings-dialog').showModal(); throw new Error('请先配置并保存 AI 接口。'); }
  const b = document.querySelector(`.tile[data-kind="${tile.kind}"]`), label = b.lastChild;
  S.studioBusy.add(tile.kind); b.classList.add('busy'); label.textContent = '生成中，可能需要几分钟…'; status(`正在生成${tile.title}…`);
  try {
    const note = await api('studio', { kind: tile.kind, question });
    S.notes.unshift(note); renderNotes(); status(`${tile.title}已生成并保存到笔记。`); openNote(note);
  } finally { S.studioBusy.delete(tile.kind); b.classList.remove('busy'); label.textContent = tile.desc; }
}
function openAnalysis() { $('analysis-prompt').hidden = true; $('analysis-copy').hidden = true; $('analysis-dialog').showModal(); $('analysis-question').focus(); }
$('analysis-form').addEventListener('submit', run(async e => {
  e.preventDefault(); const question = $('analysis-question').value; $('analysis-dialog').close();
  await runStudio(TILES.find(t => t.kind === 'analysis'), question);
}));
$('analysis-prompt-btn').addEventListener('click', run(async () => {
  const question = $('analysis-question').value.trim(); if (!question) throw new Error('请先填写研究问题。');
  const r = await api('prompt', { kind: 'analysis', question });
  $('analysis-prompt').value = r.prompt; $('analysis-prompt').hidden = false; $('analysis-copy').hidden = false;
  status(`提示词已生成（${r.passages}/${r.total} 段原文）；尚未执行 AI 分析。`);
}));
$('analysis-copy').addEventListener('click', () => copyText($('analysis-prompt').value));

async function loadNotes() { S.notes = await api('notes'); renderNotes(); }
function renderNotes() {
  const box = $('notes-list'); box.replaceChildren();
  if (!S.notes.length) { box.append(el('p', '还没有笔记。可以保存对话回答、生成 Studio 产出，或在原文旁添加笔记。', 'muted')); return; }
  S.notes.forEach(n => {
    const card = el('div', undefined, 'note-card'), tags = el('div');
    tags.append(el('span', n.kind, 'tag'), el('span', ORIGIN[n.origin] || n.origin, 'tag origin'));
    if (n.evidence.length) tags.append(el('span', `引用 ${n.evidence.length} 段`, 'muted'));
    card.append(el('b', n.title || n.body.slice(0, 24)), el('div', n.body.replace(/[#*`>]/g, ''), 'snippet'), tags);
    card.addEventListener('click', () => openNote(n));
    box.append(card);
  });
}
function openNote(note, passages = []) {
  noteState = { id: note ? note.id : null, passageIds: passages.map(p => p.id) };
  const evidence = note ? note.evidence : passages;
  $('note-heading').textContent = note ? '笔记' : '新笔记';
  $('note-title').value = note ? note.title : ''; $('note-kind').value = note ? note.kind : '个人笔记'; $('note-body').value = note ? note.body : '';
  $('note-delete').hidden = !note; $('note-submit').textContent = note ? '保存修改' : '保存笔记';
  const warnings = $('note-warnings'); warnings.replaceChildren(...(note ? note.warnings : []).map(w => el('p', '⚠ ' + w, 'muted')));
  const box = $('note-evidence'); box.replaceChildren();
  if (evidence.length) box.append(el('h3', '引用的原文'));
  evidence.forEach(p => { const d = el('details', undefined, 'ev'); d.append(el('summary', cite(p)), el('div', p.text, 'source')); box.append(d); });
  $('note-dialog').showModal(); $('note-body').focus();
}
$('add-note').addEventListener('click', () => openNote(null));
$('note-form').addEventListener('submit', run(async e => {
  e.preventDefault();
  const payload = { title: $('note-title').value, kind: $('note-kind').value, body: $('note-body').value };
  if (noteState.id) {
    const saved = await api('note-update', { id: noteState.id, ...payload });
    S.notes = S.notes.map(n => n.id === saved.id ? saved : n); status('笔记已更新。');
  } else {
    S.notes.unshift(await api('notes', { ...payload, passage_ids: noteState.passageIds })); status('笔记已保存。');
  }
  renderNotes(); $('note-dialog').close();
}));
$('note-delete').addEventListener('click', run(async () => {
  if (!confirm('删除这条笔记？')) return;
  await api('note-delete', { id: noteState.id }); S.notes = S.notes.filter(n => n.id !== noteState.id);
  renderNotes(); $('note-dialog').close(); status('笔记已删除。');
}));
$('note-copy').addEventListener('click', () => copyText(($('note-title').value ? $('note-title').value + '\n\n' : '') + $('note-body').value));

/* ---------- export, settings ---------- */
$('export-md').addEventListener('click', run(async () => download('research-notes.md', (await api('export')).markdown, 'text/markdown;charset=utf-8')));
$('export-json').addEventListener('click', run(async () => download('research-data.json', JSON.stringify((await api('export')).backup, null, 2), 'application/json;charset=utf-8')));
async function loadSettings() {
  aiConfig = await api('settings');
  $('api-base').value = aiConfig.base_url; $('api-model').value = aiConfig.model;
  $('api-tokens').value = aiConfig.max_tokens; $('api-token-field').value = aiConfig.token_field;
  $('remember-key').checked = aiConfig.key_saved; $('remember-key').disabled = !aiConfig.can_save_key;
  $('ai-destination').textContent = `AI 接口：${aiConfig.base_url} · 模型：${aiConfig.model || '尚未配置'}。发起请求会发送检索到的原文及最近对话。`;
  $('key-status').textContent = aiConfig.has_key ? (aiConfig.key_saved ? '密钥已由 Windows 加密保存。' : '密钥仅在本次程序运行期间有效。') : '尚未填写密钥。本机无密钥服务可留空。';
}
['home-settings', 'ws-settings'].forEach(id => $(id).addEventListener('click', () => $('settings-dialog').showModal()));
async function saveSettings() {
  await api('settings', { base_url: $('api-base').value, model: $('api-model').value, api_key: $('api-key').value, max_tokens: Number($('api-tokens').value), token_field: $('api-token-field').value, remember_key: $('remember-key').checked });
  $('api-key').value = ''; await loadSettings();
}
$('settings-form').addEventListener('submit', run(async e => { e.preventDefault(); await saveSettings(); $('settings-dialog').close(); status('AI 设置已保存。'); }));
$('fetch-models').addEventListener('click', run(async () => {
  if (!$('api-base').value.trim()) throw new Error('请先填写 API 基础地址。');
  const b = $('fetch-models'); b.disabled = true; status('正在向服务商查询可用模型…');
  try {
    const r = await api('models', { base_url: $('api-base').value, api_key: $('api-key').value });
    $('model-list').replaceChildren(...r.models.map(m => { const o = el('option'); o.value = m; return o; }));
    const pick = $('model-pick'); pick.replaceChildren(el('option', `选择模型（共 ${r.models.length} 个）`));
    pick.firstChild.value = ''; r.models.forEach(m => { const o = el('option', m); o.value = m; pick.append(o); });
    pick.hidden = false; status(`查到 ${r.models.length} 个可用模型，请在下拉框中选择。`);
  } finally { b.disabled = false; }
}));
$('model-pick').addEventListener('change', e => { if (e.target.value) $('api-model').value = e.target.value; });
$('forget-key').addEventListener('click', run(async () => { await api('settings', { ...aiConfig, clear_key: true, remember_key: false }); $('api-key').value = ''; await loadSettings(); status('密钥已清除。'); }));
$('test-ai').addEventListener('click', run(async () => {
  // Test what is in the form: save it first, otherwise the previous (saved) settings would be tested.
  if (!$('settings-form').reportValidity()) return;
  const b = $('test-ai'); b.disabled = true; status('正在保存并测试连接…');
  try { await saveSettings(); const r = await api('ai-test', {}); status(r.message); } finally { b.disabled = false; }
}));
$('open-data').addEventListener('click', run(async () => { if (window.pywebview?.api) await window.pywebview.api.open_data_folder(); else status('源码模式的数据目录位于项目 data 文件夹。'); }));

run(async () => { token = (await api('session')).token; await loadSettings(); await showHome(); })();
