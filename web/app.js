'use strict';
const $ = id => document.getElementById(id);
let token = '', offset = 0, total = 0;
const selected = new Map(), comparison = new Map();
function el(tag, text, cls) { const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(cls)e.className=cls; return e; }
function status(message, error=false) {$('status').textContent=message;$('status').className=error?'error':'';}
async function api(path, data) {
  const response=await fetch('/api/'+path, data===undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Research-Token':token},body:JSON.stringify(data)});
  const result=await response.json(); if(!response.ok)throw new Error(result.error||'操作失败'); return result;
}
function run(fn) { return async event => {try{await fn(event);}catch(error){status(error.message,true);}}; }
function cite(p) {return `《${p.title}》 · ${p.author||'译者/作者未记录'} · ${p.edition||'版本未记录'} · ${p.page?'PDF 第 '+p.page+' 页（文件物理页）':'文本无页码'} · 段 ${p.ordinal} · P${p.passage_id||p.id}`;}
function button(text, action) { const b=el('button',text);b.type='button';b.addEventListener('click',run(action));return b; }
function show(view) {document.querySelectorAll('.view').forEach(e=>e.hidden=e.id!==view);document.querySelectorAll('nav button').forEach(e=>e.classList.toggle('active',e.dataset.view===view));$('view-title').textContent={library:'典籍与检索',compare:'原文对照',research:'分析工作区',notes:'研究笔记'}[view];}
document.querySelectorAll('nav button').forEach(b=>b.addEventListener('click',()=>show(b.dataset.view)));
function sourceCard(p) {const div=el('article',undefined,'passage');div.append(el('div',cite(p),'citation'),el('p',p.text,'source'));return div;}
function updateSelection() {
  $('selected').replaceChildren();$('note-passage').replaceChildren();
  if(!selected.size)$('selected').append(el('p','尚未选取材料。请先在典籍检索结果中选段。','empty'));
  selected.forEach(p=>{
    const row=el('div',undefined,'toolbar');row.append(el('span',cite(p),'citation'),button('移除',()=>{selected.delete(p.id);updateSelection();}));$('selected').append(row);
    const o=el('option',cite(p));o.value=p.id;$('note-passage').append(o);
  });
  // The prompt must never appear current after evidence changes.
  $('prompt').value='';
}
function updateComparison() {
  $('comparison').replaceChildren();
  if(!comparison.size)$('comparison').append(el('p','尚未加入原文。','empty'));
  comparison.forEach(p=>{const card=sourceCard(p);card.classList.add('panel');card.append(button('移除',()=>{comparison.delete(p.id);updateComparison();}));$('comparison').append(card);});
}
async function loadBooks() {
  const books=await api('books'), current=$('book-filter').value;
  $('book-filter').replaceChildren(el('option','全部典籍'));
  $('book-filter').firstChild.value='';
  books.forEach(b=>{const o=el('option',b.title);o.value=b.id;$('book-filter').append(o);});
  $('book-filter').value=current;
  $('book-count').textContent=books.length;$('passage-count').textContent=books.reduce((n,b)=>n+b.passages,0);
  $('book-list').textContent=books.map(b=>`${b.title}（${b.passages}段）`).join(' · ')||'尚未导入典籍。先展开上方“导入典籍”添加文件。';
}
async function search(reset=true) {
  if(reset)offset=0;
  const q=new URLSearchParams({book:$('book-filter').value,q:$('query').value,offset:String(offset)});
  const result=await api('passages?'+q);total=result.total;
  $('result-count').textContent=`共 ${total} 段${total?' · 当前 '+(offset+1)+'—'+(offset+result.items.length):''}。按文件顺序排列；不做语义扩展或繁简转换。`;
  $('results').replaceChildren();
  if(!result.items.length)$('results').append(el('p','没有匹配的原文。','empty'));
  result.items.forEach(p=>{const card=sourceCard(p), actions=el('div',undefined,'toolbar');actions.append(
    button('选作研究材料',()=>{if(selected.size>=20&&!selected.has(p.id))throw new Error('最多选择 20 段。');selected.set(p.id,p);updateSelection();status(`已选 ${selected.size} 段，可进入“分析工作区”。`);}),
    button('加入对照',()=>{if(comparison.size>=2&&!comparison.has(p.id))throw new Error('对照区最多两段，请先移除一段。');comparison.set(p.id,p);updateComparison();status('已加入原文对照。');}),
    button('写笔记',()=>{if(selected.size>=20&&!selected.has(p.id))throw new Error('请先移除一些研究材料。');selected.set(p.id,p);updateSelection();$('note-passage').value=p.id;show('research');$('note-body').focus();}));card.append(actions);$('results').append(card);});
  $('previous').disabled=offset===0;$('next').disabled=offset+100>=total;
}
async function loadNotes() {
  const notes=await api('notes');$('note-count').textContent=notes.length;$('notes-list').replaceChildren();
  if(!notes.length)$('notes-list').append(el('p','还没有笔记。选择一段原文开始记录。','empty'));
  notes.forEach(n=>{const card=el('article',undefined,'panel');card.append(el('span',n.kind,'tag'),el('p',cite(n),'citation'),el('p',n.body,'source'));const details=el('details');details.append(el('summary','查看关联原文'),el('p',n.text,'source'));card.append(details,el('p',n.created,'muted'));$('notes-list').append(card);});
}
$('search').addEventListener('click',run(()=>search()));$('query').addEventListener('keydown',run(e=>{if(e.key==='Enter')return search();}));$('book-filter').addEventListener('change',run(()=>search()));
$('previous').addEventListener('click',run(()=>{offset=Math.max(0,offset-100);return search(false);}));$('next').addEventListener('click',run(()=>{offset+=100;return search(false);}));
$('import-form').addEventListener('submit',run(async e=>{
  e.preventDefault();const form=e.target, file=form.elements.file.files[0];if(!file)throw new Error('请选择文件。');if(file.size>25*1024*1024)throw new Error('文件上限 25 MB。');
  const submit=form.querySelector('button[type=submit]');submit.disabled=true;status('正在提取文字并建立索引…');
  try{const data=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(new Error('文件读取失败。'));r.readAsDataURL(file);});
    const result=await api('import',{filename:file.name,data,title:form.elements.title.value,author:form.elements.author.value,edition:form.elements.edition.value});
    await loadBooks();$('book-filter').value=result.id;$('query').value='';await search();form.reset();status(`导入成功：${result.passages} 段。${result.empty_pages?'有 '+result.empty_pages+' 页未提取到文字，请核查原 PDF。':''}`);
  }finally{submit.disabled=false;}
}));
$('clear-selection').addEventListener('click',()=>{selected.clear();updateSelection();});
$('question').addEventListener('input',()=>{$('prompt').value='';});
$('make-prompt').addEventListener('click',run(async()=>{const result=await api('prompt',{ids:[...selected.keys()],question:$('question').value});$('prompt').value=result.prompt;status('提示词已生成；尚未执行 AI 分析。');}));
$('note-form').addEventListener('submit',run(async e=>{e.preventDefault();if(!$('note-passage').value)throw new Error('请先选择原文。');await api('notes',{passage_id:Number($('note-passage').value),kind:$('note-kind').value,body:$('note-body').value});$('note-body').value='';await loadNotes();status('笔记已保存，包含关联原文与出处。');}));
function download(name, text, type) {const u=URL.createObjectURL(new Blob([text],{type}));const a=el('a');a.href=u;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);}
$('download-prompt').addEventListener('click',run(()=>{if(!$('prompt').value)throw new Error('请先生成提示词。');download('research-prompt.txt',$('prompt').value,'text/plain;charset=utf-8');}));
$('export-notes').addEventListener('click',run(async()=>download('research-notes.md',(await api('export')).markdown,'text/markdown;charset=utf-8')));
$('export-data').addEventListener('click',run(async()=>download('research-data.json',JSON.stringify((await api('export')).backup,null,2),'application/json;charset=utf-8')));
run(async()=>{token=(await api('session')).token;await loadBooks();await search();await loadNotes();updateSelection();updateComparison();})();
