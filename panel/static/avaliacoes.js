/* ---------- Avaliações das lojas (App Store e Google Play) ----------
   script clássico carregado depois de lojas.js. Usa os globais: $, esc, toast, api (index.html),
   pmModal, pmClose, pmCur, pmBusy (projects.js).
   avAbrir(project) abre o popup pelo projeto; avSelos() preenche os selos .av-badge[data-av] dos cards.
   Dados: GET /api/reviews/summary, GET /api/reviews, POST /api/reviews/fetch|draft|ai|reply.
   Só globais com prefixo av (avAbrir, avSelos e funções av*). */

const AV_PAGE=20;
const AV_LOJAS={ios:'🍎 App Store',android:'<span style="color:#34a853">▶</span> Google Play'};
const AV_NOMES={ios:'App Store',android:'Google Play'};
const AV_DICA_VINCULO='Vincule a loja em Gerenciar lojas publicadas.';

(function avInitStyle(){
  if(document.getElementById('avStyle'))return;
  const s=document.createElement('style');s.id='avStyle';
  s.textContent=`
.av-top{display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin-bottom:12px}
.av-avg{font-size:26px;font-weight:700;color:var(--warn)}
.av-bars{flex:1;min-width:200px;display:grid;gap:4px}
.av-bar-row{display:grid;grid-template-columns:34px 1fr 40px;gap:8px;align-items:center;font-size:12px;color:var(--muted)}
.av-track{height:8px;border-radius:99px;background:var(--panel2);overflow:hidden;border:1px solid var(--line)}
.av-track i{display:block;height:100%;background:var(--accent)}
.av-side{display:flex;flex-direction:column;gap:6px;align-items:flex-start}
.av-filtros{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;margin-bottom:10px}
.av-filtros select,.av-extra{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:9px;padding:6px 8px;font:inherit}
.av-extra{width:100%;box-sizing:border-box;margin-bottom:12px}
.av-item{border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:10px;background:var(--panel2)}
.av-stars{color:var(--warn);letter-spacing:1px}
.av-meta{font-size:12px;color:var(--muted);margin:2px 0 6px}
.av-body{white-space:pre-wrap;font-size:13px;line-height:1.5}
.av-resp{margin-top:10px;padding:10px 12px;border-left:3px solid var(--accent);background:var(--panel);border-radius:8px}
.av-ed{margin-top:10px}
.av-ed textarea{width:100%;box-sizing:border-box;resize:vertical;font:inherit;color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.av-ed textarea.av-over{border-color:var(--bad)}
.av-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;margin-top:6px}
.av-cnt{font-size:12px;color:var(--muted)}
.av-cnt.av-over{color:var(--bad)}
.av-btns{display:flex;flex-wrap:wrap;gap:6px}
.av-btns .btn{padding:6px 10px;font-size:13px}
.av-box{background:rgba(255,95,95,.12);border:1px solid var(--bad);border-radius:12px;padding:10px 12px;margin-bottom:12px;font-size:13px}
.av-tabs button:disabled{opacity:.45;cursor:not-allowed}
`;
  document.head.appendChild(s)})();

/* popup aberto (um por vez): {project, ov, tab, L:{ios,android} (listagem), errs:{ios,android},
   only (só sem resposta), stars (''|'1'..'5'), extra (orientação da IA), shown (itens visíveis),
   edit:{key:true} (resposta sendo editada), txt:{key:texto}, pend:{key:{k,id,t}} (rascunho agendado),
   tok, el, body}. key = loja + '|' + id da avaliação. */
let avS=null;

/* ---------- helpers ---------- */
function avAlive(){return !!(avS&&pmCur&&pmCur.el===avS.el)}
function avKey(k,id){return k+'|'+id}
function avLen(s){return Array.from(String(s||'')).length}
function avNum(n){return n==null?'—':Number(n).toFixed(1).replace('.',',')}
function avHora(ts){return ts?new Date(ts*1000).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'}):'ainda não'}
function avDate(v){
  if(v==null||v==='')return '—';
  const d=typeof v==='number'?new Date(v*1000):new Date(v);
  return isNaN(d.getTime())?String(v):d.toLocaleString('pt-BR')}
/* mensagem para o usuário; 403 da Apple vira a orientação sobre o papel da chave */
function avMsg(k,e){
  const m=(e&&e.message)||String(e);
  if(k==='ios'&&/403|forbidden/i.test(m))return 'A chave da API precisa do papel Admin, App Manager ou Customer Support para ler avaliações.';
  return m}
function avLim(k){
  const L=avS&&avS.L[k];
  return (L&&L.limits&&L.limits.replyMax)||(k==='android'?350:5970)}
function avLinked(k){return !!(avS&&avS.ov&&avS.ov[k])}
function avItem(k,id){
  const L=avS.L[k];
  return ((L&&L.items)||[]).find(x=>x.id===id)||null}
/* texto atual do editor; na 1ª vez vem do rascunho salvo (ou da resposta, se estiver editando) */
function avTxt(S,k,it){
  const key=avKey(k,it.id);
  if(!(key in S.txt))S.txt[key]=(it.response&&S.edit[key])?(it.response.body||''):(it.draft||'');
  return S.txt[key]}
function avFiltradas(L){
  const items=(L&&L.items)||[];
  return avS.stars?items.filter(it=>String(it.rating)===avS.stars):items}
/* busca o elemento do editor/contador pela chave, sem repintar a lista (não perde o foco) */
function avFind(attr,key){
  return [...avS.body.querySelectorAll('['+attr+']')].find(el=>el.getAttribute(attr)===key)||null}
function avCnt(key,txt,max){
  const over=avLen(txt)>max;
  const c=avFind('data-av-cnt',key);
  if(c){c.textContent=avLen(txt)+'/'+max;c.classList.toggle('av-over',over)}
  const ta=avFind('data-av-ta',key);
  if(ta)ta.classList.toggle('av-over',over)}

/* ---------- rascunho: agendado 1 s depois de parar de digitar; sem repintar ---------- */
function avCancelar(S,key){
  const p=S.pend[key];
  if(p){clearTimeout(p.t);delete S.pend[key]}}
function avAgendar(S,k,id){
  const key=avKey(k,id);
  avCancelar(S,key);
  S.pend[key]={k,id,t:setTimeout(()=>avSalvarRascunho(S,k,id,true),1000)}}
async function avSalvarRascunho(S,k,id,auto){
  const key=avKey(k,id);
  avCancelar(S,key);
  try{
    await api('/api/reviews/draft',{project:S.project,store:k,id,text:S.txt[key]||''});
    if(!auto)toast('Rascunho salvo')}
  catch(e){toast(avMsg(k,e))}}

/* ---------- abertura ---------- */
async function avAbrir(project){
  const done=pmBusy('Abrindo avaliações…');
  let ov=null;
  try{ov=await api('/api/reviews/summary?project='+encodeURIComponent(project))}
  catch(e){toast(e.message||String(e))}
  finally{done()}
  if(!ov)return;
  avOpen(project,ov)}

function avOpen(project,ov){
  if(avS)Object.values(avS.pend).forEach(p=>avSalvarRascunho(avS,p.k,p.id,true));
  const first=['ios','android'].find(k=>ov[k])||'ios';
  avS={project,ov,tab:first,L:{ios:null,android:null},errs:{ios:'',android:''},only:true,stars:'',extra:'',
    shown:AV_PAGE,edit:{},txt:{},pend:{},tok:0,el:null,body:null};
  const S=avS;
  const m=pmModal('⭐ Avaliações — '+project,
    '<div class="segtabs av-tabs" data-av-tabs></div><div data-av-pane></div>',
    [{label:'Fechar',cls:'',onClick:()=>pmClose()}]);
  S.el=m.el;S.body=m.body;
  const box=m.el.querySelector('.pm-box');if(box)box.style.maxWidth='min(900px,96vw)';
  m.body.addEventListener('click',avOnClick);
  m.body.addEventListener('input',avOnInput);
  m.body.addEventListener('change',avOnChange);
  avPaint();
  if(avLinked(first))avLoad(first)}

/* ---------- carga da listagem da loja atual ---------- */
async function avLoad(k){
  const S=avS, tok=++S.tok;
  let r=null;
  try{
    r=await api('/api/reviews?project='+encodeURIComponent(S.project)+'&store='+k+'&unanswered='+(S.only?1:0));
    S.errs[k]=''}
  catch(e){S.errs[k]=avMsg(k,e)}
  if(S!==avS||!avAlive()||tok!==S.tok)return;
  if(r)S.L[k]=r;
  avPaint()}

/* ---------- pintura ---------- */
function avTabsHtml(){
  return ['ios','android'].map(k=>{
    const on=avLinked(k);
    return `<button type="button" data-av-tab="${k}" class="${avS.tab===k?'on':''}"${on?'':` disabled title="${esc(AV_DICA_VINCULO)}"`}>${AV_LOJAS[k]}</button>`}).join('')}

function avTopoHtml(L){
  const c=(L&&L.counts)||{};
  const tot=c.total||0, byStar=c.byStar||{};
  const bars=[5,4,3,2,1].map(s=>{
    const n=byStar[String(s)]||0, pct=tot?Math.round(n*100/tot):0;
    return `<div class="av-bar-row"><span>${s}★</span><div class="av-track"><i style="width:${pct}%"></i></div><span>${n}</span></div>`}).join('');
  return `<div class="av-top">
    <div><div class="av-avg">★ ${avNum(c.avg)}</div><div class="hint">${tot} ${tot===1?'avaliação':'avaliações'} · ${c.unanswered||0} sem resposta</div></div>
    <div class="av-bars">${bars}</div>
    <div class="av-side"><div class="hint">${L&&L.fetchedAt?'Atualizado às '+avHora(L.fetchedAt):'Ainda não buscado'}</div>
      <button type="button" class="btn sm" data-av-fetch>🔄 Buscar avaliações</button></div>
  </div>`}

function avItemHtml(k,it){
  const key=avKey(k,it.id), id=esc(it.id);
  const r=Math.max(0,Math.min(5,Number(it.rating)||0));
  const meta=[it.author||'',
    k==='ios'?(it.territory?'Território: '+it.territory:''):(it.language?'Idioma: '+it.language:''),
    it.appVersion?'Versão '+it.appVersion:'',
    avDate(it.createdAt)].filter(Boolean).map(x=>esc(x)).join(' · ');
  let h=`<div class="av-item" data-av-item="${id}">
    <div class="av-stars">${'★'.repeat(r)}${'☆'.repeat(5-r)}</div>
    ${it.title?`<b>${esc(it.title)}</b>`:''}
    <div class="av-meta">${meta}</div>
    <div class="av-body">${esc(it.body||'(sem texto)')}</div>`;
  const resp=it.response;
  if(resp&&!avS.edit[key]){
    h+=`<div class="av-resp">
      <div class="av-meta">Sua resposta${k==='ios'&&resp.state?' ('+esc(resp.state)+')':''}${resp.updatedAt?' · '+esc(avDate(resp.updatedAt)):''}</div>
      <div class="av-body">${esc(resp.body||'')}</div>
      <div class="av-btns" style="margin-top:8px"><button type="button" class="btn" data-av-act="edit" data-av-id="${id}">Editar resposta</button></div>
    </div>`;
  }else{
    const txt=avTxt(avS,k,it), max=avLim(k), over=avLen(txt)>max;
    h+=`<div class="av-ed">
      <textarea data-av-ta="${esc(key)}" data-av-id="${id}" rows="4" class="${over?'av-over':''}" placeholder="Escreva a resposta…">${esc(txt)}</textarea>
      <div class="av-row">
        <span class="av-cnt${over?' av-over':''}" data-av-cnt="${esc(key)}">${avLen(txt)}/${max}</span>
        <div class="av-btns">
          <button type="button" class="btn" data-av-act="ai" data-av-id="${id}">✨ Rascunho com IA</button>
          <button type="button" class="btn" data-av-act="draft" data-av-id="${id}">Salvar rascunho</button>
          <button type="button" class="btn pri" data-av-act="send" data-av-id="${id}">Enviar resposta</button>
          ${resp?`<button type="button" class="btn" data-av-act="cancel" data-av-id="${id}">Cancelar</button>`:''}
        </div>
      </div>
    </div>`;
  }
  return h+'</div>'}

function avListaHtml(L){
  if(!L)return '<p class="hint">Carregando…</p>';
  const todas=avFiltradas(L);
  if(!todas.length)return `<p class="hint">${avS.only?'Nenhuma avaliação sem resposta com este filtro.':'Nenhuma avaliação com este filtro. Clique em "Buscar avaliações".'}</p>`;
  const mostra=todas.slice(0,avS.shown);
  const resto=todas.length-mostra.length;
  return mostra.map(it=>avItemHtml(avS.tab,it)).join('')+
    (resto>0?`<div style="text-align:center"><button type="button" class="btn sm" data-av-more>Mostrar mais (${resto} restantes)</button></div>`:'')}

function avPaneHtml(k){
  const L=avS.L[k];
  const lim=(L&&L.limits)||{};
  const err=avS.errs[k]||(L&&L.error)||'';
  const opts=['','5','4','3','2','1'].map(v=>`<option value="${v}"${avS.stars===v?' selected':''}>${v?v+' ★':'Todas'}</option>`).join('');
  return avTopoHtml(L)+`
    <div class="av-filtros">
      <label class="check"><input type="checkbox" data-av-only${avS.only?' checked':''}>Só sem resposta</label>
      <label class="hint">Estrelas <select data-av-stars>${opts}</select></label>
    </div>
    <label class="hint" for="avExtra">Orientação para a IA (opcional)</label>
    <input type="text" id="avExtra" class="av-extra" data-av-extra value="${esc(avS.extra)}" placeholder="ex.: canal de suporte para o cliente">
    ${lim.note?`<p class="hint">${esc(lim.note)}</p>`:''}
    ${err?`<div class="av-box">${esc(avMsg(k,{message:err}))}</div>`:''}
    <div data-av-list>${avListaHtml(L)}</div>`}

function avPaint(){
  if(!avAlive())return;
  const tabs=avS.body.querySelector('[data-av-tabs]'), pane=avS.body.querySelector('[data-av-pane]');
  if(!tabs||!pane)return;
  tabs.innerHTML=avTabsHtml();
  if(!avLinked(avS.tab)){
    pane.innerHTML=`<p class="hint">Loja não vinculada. ${esc(AV_DICA_VINCULO)}</p>`;
    return}
  pane.innerHTML=avPaneHtml(avS.tab)}

/* ---------- ações ---------- */
function avSwitchTab(k){
  if(!avLinked(k)||k===avS.tab)return;
  avS.tab=k;avS.shown=AV_PAGE;
  avPaint();avLoad(k)}

async function avBuscar(btn){
  const S=avS, k=S.tab;
  btn.disabled=true;btn.textContent='Buscando…';
  try{
    const r=await api('/api/reviews/fetch',{project:S.project,store:k});
    toast(r.new?`${r.new} ${r.new===1?'nova avaliação':'novas avaliações'}`:'Nenhuma avaliação nova')}
  catch(e){toast(avMsg(k,e))}
  if(S!==avS)return;
  await avLoad(k)}

/* editor: "edit" abre a resposta atual para editar; "cancel" volta à resposta sem salvar */
function avAcao(act,id,btn){
  const S=avS, k=S.tab, key=avKey(k,id), it=avItem(k,id);
  if(!it)return;
  if(act==='edit'){S.edit[key]=true;S.txt[key]=(it.response&&it.response.body)||'';avPaint();return}
  if(act==='cancel'){delete S.edit[key];delete S.txt[key];avCancelar(S,key);avPaint();return}
  if(act==='draft'){avSalvarRascunho(S,k,id,false);return}
  if(act==='ai'){avIA(S,k,id,btn);return}
  if(act==='send'){avEnviar(S,k,id,btn);return}
}

/* rascunho com IA: preenche o textarea; o servidor já grava como rascunho. Não envia. */
async function avIA(S,k,id,btn){
  const key=avKey(k,id);
  if(btn){btn.disabled=true;btn.textContent='Gerando…'}
  try{
    const r=await api('/api/reviews/ai',{project:S.project,store:k,id,extra:S.extra||''});
    if(S!==avS||!avAlive())return;
    S.txt[key]=r.text||'';
    avCancelar(S,key);
    const ta=avFind('data-av-ta',key);
    if(ta)ta.value=S.txt[key];
    avCnt(key,S.txt[key],avLim(k));
    toast('Rascunho gerado: revise antes de enviar')}
  catch(e){toast(avMsg(k,e))}
  finally{if(btn&&btn.isConnected){btn.disabled=false;btn.textContent='✨ Rascunho com IA'}}}

/* envia a resposta (pública na loja); confirma antes e atualiza o item com a resposta devolvida */
async function avEnviar(S,k,id,btn){
  const key=avKey(k,id), text=(S.txt[key]||'').trim(), max=avLim(k), it=avItem(k,id);
  if(!text){toast('Escreva a resposta antes de enviar');return}
  if(avLen(text)>max){toast(`A resposta tem no máximo ${max} caracteres`);return}
  if(!confirm('Enviar esta resposta para a loja? Ela fica pública.'))return;
  avCancelar(S,key);
  if(btn){btn.disabled=true;btn.textContent='Enviando…'}
  try{
    const R=await api('/api/reviews/reply',{project:S.project,store:k,id,text});
    if(S!==avS||!avAlive())return;
    const L=S.L[k];
    if(L){
      const i=(L.items||[]).findIndex(x=>x.id===id);
      if(i>=0)L.items[i]=R;
      if(it&&!it.response&&L.counts)L.counts.unanswered=Math.max(0,(L.counts.unanswered||0)-1)}
    delete S.edit[key];delete S.txt[key];
    toast('Resposta enviada');
    avPaint()}
  catch(e){
    toast(avMsg(k,e));
    if(btn&&btn.isConnected){btn.disabled=false;btn.textContent='Enviar resposta'}}}

/* ---------- eventos (delegados no corpo do popup) ---------- */
function avOnClick(e){
  if(!avAlive())return;
  const t=e.target;
  const tab=t.closest&&t.closest('[data-av-tab]');
  if(tab&&avS.body.contains(tab)){if(!tab.disabled)avSwitchTab(tab.dataset.avTab);return}
  const f=t.closest&&t.closest('[data-av-fetch]');
  if(f&&avS.body.contains(f)){avBuscar(f);return}
  if(t.closest&&t.closest('[data-av-more]')){avS.shown+=AV_PAGE;avPaint();return}
  const b=t.closest&&t.closest('[data-av-act]');
  if(b&&avS.body.contains(b))avAcao(b.dataset.avAct,b.dataset.avId,b)}

function avOnInput(e){
  if(!avAlive())return;
  const t=e.target;
  if(t.matches&&t.matches('[data-av-extra]')){avS.extra=t.value;return}
  if(t.matches&&t.matches('textarea[data-av-ta]')){
    const k=avS.tab, id=t.dataset.avId, key=avKey(k,id);
    avS.txt[key]=t.value;
    avCnt(key,t.value,avLim(k));
    avAgendar(avS,k,id)}}

function avOnChange(e){
  if(!avAlive())return;
  const t=e.target;
  if(t.matches&&t.matches('[data-av-only]')){avS.only=t.checked;avS.shown=AV_PAGE;avLoad(avS.tab);return}
  if(t.matches&&t.matches('[data-av-stars]')){avS.stars=t.value;avS.shown=AV_PAGE;avPaint()}}

/* ---------- selos nos cards dos projetos (.av-badge[data-av]) ---------- */
/* chamado por index.html depois de renderizar os projetos; sem loop, uma consulta por projeto */
async function avSelos(){
  const els=[...document.querySelectorAll('.av-badge[data-av]')];
  if(!els.length)return;
  const nomes=[...new Set(els.map(el=>el.dataset.av))];
  const res={};
  await Promise.all(nomes.map(async p=>{
    try{res[p]=await api('/api/reviews/summary?project='+encodeURIComponent(p))}
    catch(e){res[p]=null}}));
  els.forEach(el=>{
    const s=res[el.dataset.av];
    if(!s){el.textContent='';el.removeAttribute('title');return}
    let n=0;
    const partes=[];
    ['ios','android'].forEach(k=>{
      const x=s[k];
      if(!x)return;
      n+=x.unanswered||0;
      partes.push(AV_NOMES[k]+' ★'+avNum(x.avg))});
    el.textContent=n>0?`⭐ ${n} sem resposta`:'';
    if(partes.length)el.title=partes.join(' · ');else el.removeAttribute('title')})}
