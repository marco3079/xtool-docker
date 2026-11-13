/* ---------- Acompanhamento das lojas (card #wchCard e selos nos projetos) ----------
   script clássico carregado depois de update.js. Usa os globais: $, esc, toast, api (index.html)
   e pmFmtDate (projects.js). Só globais com prefixo wch.
   Dados: GET /api/watch (watch.public()); intervalo: POST /api/watch/config; consulta: POST /api/watch/run. */

const WCH_INTERVALOS=[5,10,15,30,60,120,240];
const WCH_TONS={ok:'var(--ok)',warn:'var(--warn)',bad:'var(--bad)'};
const WCH_PERIODO_MS=60000;

/* último estado recebido de /api/watch; wchErro guarda a falha da última tentativa */
let wchState=null, wchErro='';

function wchProjetos(){return (wchState&&wchState.projects)||{}}

/* hora local HH:MM de um epoch em segundos ("ainda não" quando zero) */
function wchHora(ts){
  if(!ts)return 'ainda não';
  return new Date(ts*1000).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}

/* selo: {store, text, tone} */
function wchBadgeHtml(b,titulo){
  const cor=WCH_TONS[b.tone]||WCH_TONS.warn;
  return `<span class="pill" style="font-size:11px;padding:1px 8px;margin-left:6px;color:${cor}"${titulo?` title="${esc(titulo)}"`:''}>${esc(b.text||'')}</span>`}

/* título do selo: último evento do projeto (da mesma loja, se houver) */
function wchTitulo(info,b){
  const hist=(info&&info.history)||[];
  const e=hist.find(x=>!b.store||x.store===b.store)||hist[0];
  return e?`${pmFmtDate(e.at)} · ${e.text}`:''}

/* preenche os spans .wch-badges[data-wch] dos cards de projeto (chamado também por index.html) */
function wchPaintBadges(){
  document.querySelectorAll('.wch-badges[data-wch]').forEach(el=>{
    const info=wchProjetos()[el.dataset.wch];
    const bs=(info&&info.badges)||[];
    el.innerHTML=bs.map(b=>wchBadgeHtml(b,wchTitulo(info,b))).join('')})}

/* card: monta o esqueleto uma vez; depois só atualiza select, hora e lista */
function wchPaintCard(){
  const card=$('wchCard');if(!card)return;
  const s=wchState;
  if(!s){
    if(!card.querySelector('[data-wch-int]'))card.innerHTML=`<p class="hint">${esc(wchErro||'Carregando…')}</p>`;
    return}
  if(!card.querySelector('[data-wch-int]')){
    card.innerHTML=`<p class="hint">Consulta as lojas dos projetos com versão pendente ou em revisão (e por 24 h depois de uma mudança).</p>
      <div class="pm-row" style="align-items:center;flex-wrap:wrap;gap:10px;margin-top:8px">
        <label for="wchInt">Consultar a cada</label>
        <select id="wchInt" data-wch-int>${WCH_INTERVALOS.map(m=>`<option value="${m}">${m} min</option>`).join('')}</select>
        <button type="button" class="btn sm" data-wch-run>🔄 Consultar agora</button>
        <span class="hint" data-wch-last></span></div>
      <div data-wch-list style="margin-top:12px"></div>
      <p class="hint" style="margin-top:12px">Limites: a Apple não informa o motivo de uma rejeição pela API: abra o App Store Connect. O Google Play não informa se a release está em análise, só a faixa e o estado.</p>`;
    if(!card.dataset.wchBound){
      card.dataset.wchBound='1';
      card.addEventListener('change',wchOnChange);
      card.addEventListener('click',wchOnClick)}}
  const sel=card.querySelector('[data-wch-int]');
  if(sel&&document.activeElement!==sel)sel.value=String(s.intervalMin||15);
  const last=card.querySelector('[data-wch-last]');
  if(last)last.textContent='Última consulta: '+wchHora(s.lastRun);
  const list=card.querySelector('[data-wch-list]');
  if(list){
    const ativos=Object.entries(wchProjetos()).filter(([,p])=>p&&p.active);
    list.innerHTML=ativos.length
      ? ativos.map(([nome,p])=>`<div class="pm-card" style="margin-bottom:8px"><b>${esc(nome)}</b><div>${(p.badges||[]).map(b=>wchBadgeHtml(b,wchTitulo(p,b))).join('')||'<span class="hint">Sem mudanças recentes</span>'}</div></div>`).join('')
      : '<p class="hint">Nenhum projeto em acompanhamento agora.</p>'}}

/* carrega /api/watch, repinta o card e os selos; falha mantém o último estado válido */
async function wchLoad(){
  try{wchState=await api('/api/watch');wchErro=''}
  catch(e){wchErro=e.message||String(e)}
  wchPaintCard();
  wchPaintBadges()}

async function wchSalvarIntervalo(m){
  try{await api('/api/watch/config',{intervalMin:m});toast(`Consulta a cada ${m} min`)}
  catch(e){toast(e.message||String(e))}
  await wchLoad()}

/* "Consultar agora": dispara em segundo plano e recarrega depois de 5 s */
async function wchConsultar(btn){
  btn.disabled=true;
  try{await api('/api/watch/run',{});toast('Consulta iniciada: os selos atualizam em alguns segundos')}
  catch(e){toast(e.message||String(e))}
  setTimeout(()=>{btn.disabled=false;wchLoad()},5000)}

function wchOnChange(e){
  const sel=e.target;
  if(!sel||!sel.matches||!sel.matches('select[data-wch-int]'))return;
  wchSalvarIntervalo(Number(sel.value))}
function wchOnClick(e){
  const btn=e.target.closest&&e.target.closest('[data-wch-run]');
  if(btn&&!btn.disabled)wchConsultar(btn)}

/* arranque: carrega já e repinta a cada 60 s */
wchLoad();
setInterval(wchLoad,WCH_PERIODO_MS);
