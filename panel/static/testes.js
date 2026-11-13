/* ---------- Testes (TestFlight e Google Play) ----------
   script clássico carregado depois de lojas.js. Usa os globais: $, esc, toast, api (index.html),
   pmModal, pmClose, pmCur (projects.js). Só globais com prefixo ts.
   Abertura: tsAbrir(project) (modal "🧪 Testes — <projeto>").
   Dados: GET /api/testes/ios?project= e GET /api/testes/android?project=.
   Ações: POST /api/testes/ios/* e /api/testes/android/testers; promoção Android: POST /api/lojas/promote
   (mesmo body de ljPromote em lojas.js). A IA só gera rascunho; nada é salvo sem o botão "Salvar". */

const TS_TESTER_STATES={INVITED:'Convidado',ACCEPTED:'Aceito',INSTALLED:'Instalado',REVOKED:'Revogado',EXPIRED:'Expirado'};
const TS_PROCESSING={VALID:'Pronto',PROCESSING:'Processando',FAILED:'Falhou',INVALID:'Inválido'};
const TS_EXTERNAL={READY_FOR_BETA_TESTING:'Pronto para teste',IN_BETA_TESTING:'Em teste',EXPIRED:'Expirado',
  IN_EXPORT_COMPLIANCE_REVIEW:'Análise de exportação',MISSING_EXPORT_COMPLIANCE:'Falta exportação',
  PROCESSING_EXCEPTION:'Erro de processamento',IN_REVIEW:'Em revisão',WAITING_FOR_REVIEW:'Aguardando revisão',
  BETA_APPROVED:'Aprovado',BETA_REJECTED:'Rejeitado'};
const TS_TRACK_LABELS={internal:'Teste interno (internal)',alpha:'Teste fechado (alpha)',beta:'Teste aberto (beta)',production:'Produção'};
const TS_TRACK_ORDER=['production','beta','alpha','internal'];
const TS_RELEASE_STATUS={completed:'Concluído',draft:'Rascunho',inProgress:'Liberação gradual',halted:'Pausado'};
const TS_PROMOTE_STATUS={completed:'Liberar para todos',inProgress:'Liberação gradual',draft:'Só rascunho'};

/* estado da janela aberta: {project, el, body, tab, ios, android, err:{ios,android}, open, gmsg, newGroup, build, review, promoteTrack} */
let tsS=null;

(function tsInitStyle(){
  if(document.getElementById('tsStyle'))return;
  const s=document.createElement('style');s.id='tsStyle';
  s.textContent=`
.ts-sec{margin:0 0 18px}
.ts-sec h4{margin:0 0 8px;font-size:15px}
.ts-card{border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-bottom:8px;background:var(--panel2)}
.ts-panel{border:1px solid var(--line);border-radius:12px;padding:12px;margin:8px 0 14px;background:var(--panel2)}
.ts-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.ts-grow{flex:1;min-width:0}
.ts-w{width:100%;box-sizing:border-box}
.ts-inp{font:inherit;color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:6px 10px;box-sizing:border-box}
.ts-test{width:100%;box-sizing:border-box;resize:vertical;font:inherit;color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.ts-field{margin:8px 0}
.ts-field label,.ts-lbl{display:block;margin-bottom:4px;font-size:13px}
.ts-chk{display:flex;gap:6px;align-items:center;font-size:13px;margin:8px 0}
.ts-note{font-size:12px;color:var(--muted);margin:6px 0 0}
.ts-msg{color:var(--bad);font-size:13px;margin-top:6px;white-space:pre-wrap}
.ts-warnbox{background:rgba(245,176,65,.12);border:1px solid var(--warn);border-radius:12px;padding:12px 14px;font-size:13px}
.ts-tbl{width:100%;border-collapse:collapse;font-size:13px}
.ts-tbl th,.ts-tbl td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.ts-tbl th{color:var(--muted);font-weight:500}
.ts-tbl tr.ts-old td{color:var(--muted);opacity:.6}
.ts-tbl tr.ts-exp-row td{padding:0 0 8px}
.segtabs button:disabled{opacity:.45;cursor:not-allowed}
`;
  document.head.appendChild(s)})();

/* ---------- utilidades ---------- */
function tsAlive(){return !!(tsS&&tsS.el&&pmCur&&pmCur.el===tsS.el)}
function tsDate(iso){return iso?new Date(iso).toLocaleString('pt-BR'):'—'}
function tsLoc(x){return typeof x==='string'?x:String((x&&(x.code||x.locale))||'')}
function tsLocales(){return ((tsS&&tsS.ios&&tsS.ios.locales)||[]).map(tsLoc).filter(Boolean)}
function tsTopCode(codes){
  const c=(codes||[]).map(String).filter(Boolean).sort((a,b)=>Number(b)-Number(a));
  return c[0]||''}
function tsExternal(x){
  if(!x)return '—';
  return TS_EXTERNAL[x]||String(x).replace(/_/g,' ').toLowerCase()}
function tsBuild(id){return ((tsS&&tsS.ios&&tsS.ios.builds)||[]).find(b=>b.id===id)}
function tsAndroidTrack(k){return ((tsS&&tsS.android&&tsS.android.tracks)||[]).find(t=>t.track===k)}

/* executa uma ação: desabilita o botão, mostra erro (no campo msgEl ou em toast) e ignora resposta
   de uma janela que já foi fechada/reaberta */
async function tsRun(btn,fn,msgEl){
  const S=tsS;
  if(btn){if(btn.disabled)return null;btn.disabled=true}
  if(msgEl)msgEl.textContent='';
  let r=null;
  try{r=await fn()}
  catch(e){const m=e.message||String(e);if(msgEl)msgEl.textContent=m;else toast(m);r=null}
  finally{if(btn)btn.disabled=false}
  return S===tsS&&tsAlive()?r:null}

async function tsCopy(v){
  try{await navigator.clipboard.writeText(v);toast('Link copiado')}
  catch(e){toast('Não foi possível copiar. Selecione o link e copie manualmente.')}}

/* ---------- abertura e carga ---------- */
function tsAbrir(project){
  if(!project)return toast('Escolha um projeto');
  tsS={project:String(project),el:null,body:null,tab:'ios',ios:null,android:null,
    err:{ios:'',android:''},open:{},gmsg:{},newGroup:false,build:'',review:'',promoteTrack:''};
  const m=pmModal('🧪 Testes — '+project,
    '<div class="segtabs" data-ts-tabs></div><div data-ts-pane><p class="hint">Carregando…</p></div>',[]);
  tsS.el=m.el;tsS.body=m.body;
  m.body.addEventListener('click',tsOnClick);
  m.body.addEventListener('change',tsOnChange);
  tsLoadAll()}

/* carrega as duas abas em paralelo; a aba sem vínculo fica desabilitada com a mensagem do servidor */
async function tsLoadAll(){
  const S=tsS;
  await Promise.all([tsFetch('ios',S),tsFetch('android',S)]);
  if(S!==tsS||!tsAlive())return;
  if(!S.ios&&S.android)S.tab='android';
  tsRenderAll()}

/* devolve a mensagem de erro ('' se ok) e guarda o resultado na sessão */
async function tsFetch(k,S){
  const url=(k==='ios'?'/api/testes/ios?project=':'/api/testes/android?project=')+encodeURIComponent(S.project);
  let d=null,err='';
  try{d=await api(url)}catch(e){err=e.message||String(e)}
  if(S===tsS&&tsAlive()){S[k]=d;S.err[k]=err}
  return err}

/* recarrega uma aba depois de uma ação; falha mantém os dados anteriores e avisa */
async function tsReload(k){
  const S=tsS,old=S[k];
  const err=await tsFetch(k,S);
  if(S!==tsS||!tsAlive())return;
  if(err&&old){S[k]=old;S.err[k]='';toast(err)}
  tsRenderAll()}

/* ---------- render ---------- */
function tsRenderAll(){
  if(!tsAlive())return;
  const tabs=tsS.body.querySelector('[data-ts-tabs]');
  if(tabs){
    const T=[['ios','TestFlight (iOS)'],['android','Google Play (Android)']];
    tabs.innerHTML=T.map(([k,l])=>{
      const dis=!tsS[k];
      return `<button type="button" data-ts-tab="${k}" class="${k===tsS.tab?'on':''}"${dis?` disabled title="${esc(tsS.err[k]||'Indisponível')}"`:''}>${esc(l)}${dis?' ⚠':''}</button>`}).join('')}
  tsRenderPane()}

function tsRenderPane(){
  if(!tsAlive())return;
  const pane=tsS.body.querySelector('[data-ts-pane]');if(!pane)return;
  const k=tsS.tab,data=tsS[k];
  if(!data){pane.innerHTML=`<div class="ts-warnbox">${esc(tsS.err[k]||'Sem dados.')}</div>`;return}
  pane.innerHTML=k==='ios'?tsIosHtml():tsAndroidHtml()}

/* ---------- TestFlight ---------- */
function tsIosHtml(){
  const o=tsS.ios,w=(o.warnings||[]).filter(Boolean);
  const warn=w.length?`<div class="ts-warnbox" style="font-size:12px;margin-bottom:12px">Algumas informações não carregaram:<ul style="margin:6px 0 0;padding-left:18px">${w.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:'';
  return warn+tsGroupsHtml(o.groups||[])+tsBuildsHtml(o.builds||[],o)}

function tsGroupsHtml(groups){
  const newBox=tsS.newGroup?`<div class="ts-panel" data-ts-newbox>
      <div class="ts-row">
        <input class="ts-inp ts-grow" data-ts-newname placeholder="Nome do grupo" maxlength="100">
        <select class="ts-inp" data-ts-newint><option value="0">Externo</option><option value="1">Interno</option></select>
        <button type="button" class="btn sm pri" data-ts-act="creategroup">Criar grupo</button>
        <button type="button" class="btn sm" data-ts-act="togglenew">Cancelar</button>
      </div>
      <p class="ts-note">Grupo interno: só usuários da equipe do App Store Connect. Grupo externo: testadores por e-mail ou link público (o build precisa de revisão beta).</p>
    </div>`:'';
  const cards=groups.map(tsGroupCard).join('')||'<p class="hint">Nenhum grupo de testadores ainda.</p>';
  return `<div class="ts-sec">
    <div class="ts-row" style="justify-content:space-between"><h4>Grupos de testadores</h4>
      <button type="button" class="btn sm" data-ts-act="togglenew">➕ Novo grupo</button></div>
    ${newBox}${cards}</div>`}

function tsGroupCard(g){
  const open=!!tsS.open[g.id];
  const testers=g.testers||[];
  const count=g.testerCount!=null?g.testerCount:testers.length;
  const link=g.internal
    ?'<p class="ts-note">Grupo interno: sem link público. Só entram usuários da equipe do App Store Connect.</p>'
    :tsLinkHtml(g);
  return `<div class="ts-card" data-ts-group="${esc(g.id)}">
    <div class="ts-row"><b class="ts-grow">${esc(g.name||'(sem nome)')}</b>
      <span class="pill" style="font-size:11px">${g.internal?'Interno':'Externo'}</span>
      <span class="hint">${esc(String(count))} testador(es)</span>
      <button type="button" class="btn sm" data-ts-act="toggle" data-ts-g="${esc(g.id)}">${open?'▲ Recolher':'▼ Expandir'}</button></div>
    ${link}
    ${open?tsTestersHtml(g,testers):''}</div>`}

function tsLinkHtml(g){
  const on=!!g.publicLinkEnabled;
  const lim=g.publicLinkLimit!=null?String(g.publicLinkLimit):'';
  return `<div class="ts-row" style="margin-top:8px">
    ${on&&g.publicLink
      ?`<input class="ts-inp ts-grow" readonly value="${esc(g.publicLink)}">
         <button type="button" class="btn sm" data-ts-act="copy" data-ts-v="${esc(g.publicLink)}">📋 Copiar</button>`
      :'<span class="hint ts-grow">Link público desligado.</span>'}
    <input class="ts-inp" type="number" min="1" step="1" style="width:120px" placeholder="Sem limite" value="${esc(lim)}" data-ts-limit title="Limite de testadores pelo link (vazio = sem limite)">
    <button type="button" class="btn sm${on?'':' pri'}" data-ts-act="link" data-ts-g="${esc(g.id)}" data-ts-on="${on?'0':'1'}">${on?'Desligar link':'Ligar link'}</button>
  </div>`}

function tsTestersHtml(g,testers){
  const rows=testers.map(t=>`<tr>
    <td>${esc(t.email||'')}</td>
    <td>${esc([t.firstName,t.lastName].filter(Boolean).join(' ')||'—')}</td>
    <td>${esc(TS_TESTER_STATES[t.state]||t.state||'—')}</td>
    <td style="text-align:right"><button type="button" class="btn sm" data-ts-act="rmtester" data-ts-g="${esc(g.id)}" data-ts-t="${esc(t.id)}">Remover</button></td></tr>`).join('');
  const msg=tsS.gmsg[g.id]||'';
  return `<div style="margin-top:10px">
    ${testers.length
      ?`<div style="overflow-x:auto"><table class="ts-tbl"><thead><tr><th>E-mail</th><th>Nome</th><th>Estado</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`
      :'<p class="hint">Nenhum testador neste grupo.</p>'}
    <div class="ts-field"><label>Adicionar testadores (um e-mail por linha)
      <textarea class="ts-test" rows="3" data-ts-emails></textarea></label></div>
    <div class="ts-row"><button type="button" class="btn sm" data-ts-act="addtesters" data-ts-g="${esc(g.id)}">➕ Adicionar</button></div>
    ${g.internal?'<p class="ts-note">Grupo interno: a Apple só aceita usuários da equipe do App Store Connect.</p>':''}
    ${msg?`<div class="ts-msg">${esc(msg)}</div>`:''}
  </div>`}

function tsBuildsHtml(builds,o){
  if(!builds.length)return '<div class="ts-sec"><h4>Builds</h4><p class="hint">Nenhum build enviado ainda.</p></div>';
  const groups=o.groups||[];
  const gname=id=>{const g=groups.find(x=>x.id===id);return g?g.name:''};
  const rows=builds.map(b=>{
    const gtxt=(b.groups||[]).map(gname).filter(Boolean).join(', ')||'—';
    const sel=tsS.build===b.id;
    return `<tr class="${b.expired?'ts-old':''}">
      <td>${esc(b.version||'')} (${esc(b.build||'')})</td>
      <td>${esc(tsDate(b.uploadedAt))}</td>
      <td>${esc(TS_PROCESSING[b.processing]||b.processing||'—')}</td>
      <td>${esc(tsExternal(b.externalState))}${b.expired?' · expirado':''}</td>
      <td>${esc(b.reviewLabel||(b.review&&b.review.state)||'—')}</td>
      <td>${esc(gtxt)}</td>
      <td><button type="button" class="btn sm" data-ts-act="build" data-ts-b="${esc(b.id)}">${sel?'▲ Fechar':'⚙ Gerenciar'}</button></td></tr>
      ${sel?`<tr class="ts-exp-row"><td colspan="7">${tsBuildPanelHtml(b,o)}</td></tr>`:''}`}).join('');
  return `<div class="ts-sec"><h4>Builds</h4>
    <div style="overflow-x:auto"><table class="ts-tbl">
      <thead><tr><th>Versão (build)</th><th>Enviado em</th><th>Processamento</th><th>Estado externo</th><th>Revisão beta</th><th>Grupos</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table></div></div>`}

function tsBuildPanelHtml(b,o){
  const groups=o.groups||[],locs=tsLocales();
  const gopts=groups.map(g=>`<option value="${esc(g.id)}">${esc(g.name||g.id)}</option>`).join('');
  /* o overview traz "O que testar" só do 1º idioma; os demais começam vazios */
  const wtt=locs.map((l,i)=>{
    const v=i===0?(b.whatToTest||''):'';
    return `<div class="ts-field"><label>${esc(l)}
      <textarea class="ts-test" rows="3" maxlength="4000" data-ts-wtt="${esc(l)}" data-ts-orig="${esc(v)}">${esc(v)}</textarea></label></div>`}).join('')
    ||'<p class="hint">Projeto sem idiomas de loja.</p>';
  const review=tsS.review===b.id
    ?tsReviewFormHtml(b,o)
    :`<div class="ts-row" style="margin-top:6px"><button type="button" class="btn sm" data-ts-act="reviewform" data-ts-b="${esc(b.id)}">📨 Enviar para revisão beta…</button></div>`;
  return `<div class="ts-panel" data-ts-bp="${esc(b.id)}">
    <div class="ts-sec"><b>Grupos</b>
      <div class="ts-row" style="margin-top:6px">${groups.length
        ?`<select class="ts-inp" data-ts-togroup>${gopts}</select>
          <button type="button" class="btn sm" data-ts-act="togroup">Colocar no grupo…</button>`
        :'<span class="hint">Crie um grupo antes de colocar o build.</span>'}</div></div>
    <div class="ts-sec"><b>O que testar</b> <span class="hint">texto para os testadores, por idioma</span>
      ${wtt}
      <div class="ts-row">
        <input class="ts-inp ts-grow" data-ts-extra placeholder="Instruções extras para a IA (opcional)">
        <button type="button" class="btn sm" data-ts-act="wttai">✨ Gerar com IA</button>
        <button type="button" class="btn sm pri" data-ts-act="wttsave">💾 Salvar</button>
      </div>
      <p class="ts-note">A IA só faz rascunho: revise antes de salvar.</p></div>
    <div class="ts-sec"><b>Revisão beta</b>${review}</div>
  </div>`}

/* formulário da revisão beta: contato, conta demo, notas e, por idioma, descrição + e-mail de feedback */
function tsReviewFormHtml(b,o){
  const d=o.reviewDetails||{},info=o.betaInfo||{},locs=tsLocales();
  const txt=(k,lbl)=>`<div class="ts-field"><label>${esc(lbl)}<input class="ts-inp ts-w" data-ts-rd="${k}" value="${esc(d[k]||'')}"></label></div>`;
  const locBlocks=locs.map(l=>{
    const i=info[l]||{};
    return `<div class="ts-card"><b>${esc(l)}</b>
      <div class="ts-field"><label>Descrição<textarea class="ts-test" rows="3" data-ts-bi-desc="${esc(l)}">${esc(i.description||'')}</textarea></label></div>
      <div class="ts-field"><label>E-mail de feedback<input class="ts-inp ts-w" data-ts-bi-mail="${esc(l)}" value="${esc(i.feedbackEmail||'')}"></label></div></div>`}).join('')
    ||'<p class="hint">Projeto sem idiomas de loja.</p>';
  return `<div class="ts-panel" data-ts-rf="${esc(b.id)}">
    <b>Contato para a revisão</b>
    ${txt('contactFirstName','Nome')}
    ${txt('contactLastName','Sobrenome')}
    ${txt('contactPhone','Telefone')}
    ${txt('contactEmail','E-mail')}
    <label class="ts-chk"><input type="checkbox" data-ts-rd="demoAccountRequired"${d.demoAccountRequired?' checked':''}> A revisão precisa de conta demo</label>
    ${txt('demoAccountName','Usuário da conta demo')}
    <div class="ts-field"><label>Senha da conta demo<input type="password" class="ts-inp ts-w" data-ts-rd="demoAccountPassword" value="${esc(d.demoAccountPassword||'')}"></label></div>
    <div class="ts-field"><label>Notas para o revisor<textarea class="ts-test" rows="3" data-ts-rd="notes">${esc(d.notes||'')}</textarea></label></div>
    <b>Por idioma</b>
    ${locBlocks}
    <div class="ts-row" style="margin-top:8px">
      <button type="button" class="btn sm pri" data-ts-act="submitreview">📨 Enviar para revisão beta</button>
      <button type="button" class="btn sm" data-ts-act="reviewform" data-ts-b="${esc(b.id)}">Cancelar</button>
    </div>
    <div class="ts-msg" data-ts-msg></div>
  </div>`}

/* ---------- Google Play ---------- */
function tsAndroidHtml(){
  const o=tsS.android,tracks=o.tracks||[];
  const invite=o.optInUrl?`<div class="ts-card">
    <b>Link de convite</b>
    <div class="ts-row" style="margin-top:6px">
      <input class="ts-inp ts-grow" readonly value="${esc(o.optInUrl)}">
      <button type="button" class="btn sm" data-ts-act="copy" data-ts-v="${esc(o.optInUrl)}">📋 Copiar</button>
    </div>
    <p class="ts-note">Link para o testador entrar nas faixas de teste do app.</p></div>`:'';
  const body=tracks.length
    ?tracks.map(tsTrackHtml).join('')
    :'<p class="hint">Nenhuma faixa de teste encontrada.</p>';
  return `${invite}${body}
    <p class="ts-note">Limite: as listas de e-mail dos testadores ficam no Play Console; pela API só dá para usar Google Groups.</p>`}

function tsTrackHtml(t){
  const name=TS_TRACK_LABELS[t.track]||t.track;
  const rels=t.releases||[];
  const gg=Array.isArray(t.testers)?t.testers:((t.testers&&t.testers.googleGroups)||[]);
  const rows=rels.map(r=>`<tr>
    <td>${esc(r.name||'—')}</td>
    <td>${esc((r.versionCodes||[]).join(', ')||'—')}</td>
    <td>${esc(TS_RELEASE_STATUS[r.status]||r.status||'—')}</td>
    <td>${r.userFraction!=null?esc(String(Math.round(r.userFraction*100)))+'%':'—'}</td></tr>`).join('');
  const promo=rels.length
    ?`<button type="button" class="btn sm" data-ts-act="promote" data-ts-track="${esc(t.track)}">🚀 Promover para…</button>`:'';
  const pf=(rels.length&&tsS.promoteTrack===t.track)?tsPromoteHtml(t):'';
  return `<div class="ts-card" data-ts-track="${esc(t.track)}">
    <div class="ts-row"><b class="ts-grow">${esc(name)}</b>${promo}</div>
    ${rels.length
      ?`<div style="overflow-x:auto"><table class="ts-tbl"><thead><tr><th>Nome</th><th>versionCodes</th><th>Estado</th><th>Fração</th></tr></thead><tbody>${rows}</tbody></table></div>`
      :'<p class="hint">Sem releases nesta faixa.</p>'}
    ${pf}
    <div class="ts-field"><label>Google Groups (um por linha)
      <textarea class="ts-test" rows="3" data-ts-groups>${esc(gg.join('\n'))}</textarea></label></div>
    <div class="ts-row"><button type="button" class="btn sm" data-ts-act="savetesters" data-ts-track="${esc(t.track)}">💾 Salvar Google Groups</button></div>
  </div>`}

function tsPromoteHtml(t){
  const rels=t.releases||[];
  const targets=TS_TRACK_ORDER.filter(x=>x!==t.track);
  return `<div class="ts-panel" data-ts-pf="${esc(t.track)}">
    <div class="ts-field"><label>Versão
      <select class="ts-inp ts-w" data-ts-pfrel>${rels.map((r,i)=>`<option value="${i}">${esc(r.name||'(sem nome)')} — código ${esc(tsTopCode(r.versionCodes)||'—')}</option>`).join('')}</select></label></div>
    <div class="ts-field"><label>Faixa de destino
      <select class="ts-inp ts-w" data-ts-pfto>${targets.map(x=>`<option value="${x}"${x==='production'?' selected':''}>${esc(TS_TRACK_LABELS[x])}</option>`).join('')}</select></label></div>
    <div class="ts-field"><label>Status
      <select class="ts-inp ts-w" data-ts-pfst>${Object.keys(TS_PROMOTE_STATUS).map(k=>`<option value="${k}"${k==='completed'?' selected':''}>${esc(TS_PROMOTE_STATUS[k])}</option>`).join('')}</select></label></div>
    <div class="ts-field" data-ts-pffrw hidden><label>Percentual dos usuários (1 a 100)
      <input class="ts-inp ts-w" type="number" min="1" max="100" step="1" value="10" data-ts-pffr></label></div>
    <div class="ts-row">
      <button type="button" class="btn sm pri" data-ts-act="promotego">🚀 Promover</button>
      <button type="button" class="btn sm" data-ts-act="promote" data-ts-track="${esc(t.track)}">Cancelar</button>
    </div>
    <div class="ts-msg" data-ts-msg></div>
  </div>`}

/* ---------- eventos (delegação no corpo do modal) ---------- */
function tsOnClick(e){
  if(!tsAlive())return;
  const t=e.target.closest&&e.target.closest('[data-ts-tab],[data-ts-act]');
  if(!t||!tsS.body.contains(t))return;
  if(t.hasAttribute('data-ts-tab'))return tsSwitchTab(t.dataset.tsTab);
  tsAct(t.dataset.tsAct,t)}

function tsOnChange(e){
  if(!tsAlive())return;
  const sel=e.target;
  if(sel&&sel.matches&&sel.matches('select[data-ts-pfst]')){
    const fr=sel.closest('[data-ts-pf]').querySelector('[data-ts-pffrw]');
    if(fr)fr.hidden=sel.value!=='inProgress'}}

function tsSwitchTab(k){
  if(!tsAlive()||k===tsS.tab||!tsS[k])return;
  tsS.tab=k;
  tsRenderAll()}

async function tsAct(id,btn){
  if(!id||!tsAlive())return;
  const P=tsS.project;
  switch(id){
    /* ----- grupos ----- */
    case 'togglenew':
      tsS.newGroup=!tsS.newGroup;tsRenderPane();return;
    case 'toggle':{
      const gid=btn.dataset.tsG;
      tsS.open[gid]=!tsS.open[gid];tsRenderPane();return}
    case 'creategroup':{
      const box=btn.closest('[data-ts-newbox]');
      const name=box.querySelector('[data-ts-newname]').value.trim();
      const internal=box.querySelector('[data-ts-newint]').value==='1';
      if(!name)return toast('Informe o nome do grupo');
      const r=await tsRun(btn,()=>api('/api/testes/ios/group',{project:P,name,internal}));
      if(!r)return;
      tsS.newGroup=false;toast('Grupo criado');
      await tsReload('ios');return}
    case 'link':{
      const card=btn.closest('[data-ts-group]');
      const gid=btn.dataset.tsG,enabled=btn.dataset.tsOn==='1';
      let limit=null;
      if(enabled){
        const v=(card.querySelector('[data-ts-limit]').value||'').trim();
        if(v!==''){
          limit=Number(v);
          if(!Number.isInteger(limit)||limit<1)return toast('O limite precisa ser um número inteiro maior que zero')}}
      const r=await tsRun(btn,()=>api('/api/testes/ios/link',{project:P,groupId:gid,enabled,limit}));
      if(!r)return;
      toast(enabled?'Link público ligado':'Link público desligado');
      await tsReload('ios');return}
    case 'copy':
      return tsCopy(btn.dataset.tsV||'');
    case 'addtesters':{
      const card=btn.closest('[data-ts-group]');
      const gid=btn.dataset.tsG;
      const text=card.querySelector('[data-ts-emails]').value.trim();
      if(!text)return toast('Informe ao menos um e-mail');
      const r=await tsRun(btn,()=>api('/api/testes/ios/testers/add',{project:P,groupId:gid,emails:text}));
      if(!r)return;
      const added=(r.added||[]).length,errs=r.errors||[];
      tsS.gmsg[gid]=errs.map(x=>`${x.email}: ${x.error}`).join('\n');
      toast(errs.length?`${added} adicionado(s), ${errs.length} com erro (veja no grupo)`:`${added} testador(es) adicionado(s)`);
      await tsReload('ios');return}
    case 'rmtester':{
      if(!confirm('Remover este testador do grupo?'))return;
      const gid=btn.dataset.tsG,tid=btn.dataset.tsT;
      const r=await tsRun(btn,()=>api('/api/testes/ios/testers/remove',{project:P,groupId:gid,testerId:tid}));
      if(!r)return;
      toast('Testador removido');
      await tsReload('ios');return}

    /* ----- builds ----- */
    case 'build':{
      const bid=btn.dataset.tsB;
      tsS.build=tsS.build===bid?'':bid;tsS.review='';
      tsRenderPane();return}
    case 'togroup':{
      const bp=btn.closest('[data-ts-bp]');
      const gid=bp.querySelector('[data-ts-togroup]').value;
      if(!gid)return toast('Escolha um grupo');
      const r=await tsRun(btn,()=>api('/api/testes/ios/build',{project:P,groupId:gid,buildId:bp.dataset.tsBp}));
      if(!r)return;
      toast('Build colocado no grupo');
      await tsReload('ios');return}
    case 'wttai':{
      const bp=btn.closest('[data-ts-bp]');
      const b=tsBuild(bp.dataset.tsBp);
      if(!b)return;
      const extra=(bp.querySelector('[data-ts-extra]').value||'').trim();
      const r=await tsRun(btn,()=>api('/api/testes/ios/whattotest/ai',{project:P,version:b.version||'',locales:tsLocales(),extra}));
      if(!r)return;
      const m=(r.texts&&typeof r.texts==='object')?r.texts:r;
      let n=0;
      bp.querySelectorAll('[data-ts-wtt]').forEach(ta=>{
        const v=m[ta.dataset.tsWtt];
        if(typeof v==='string'){ta.value=v;n++}});
      toast(n?'Texto gerado: revise antes de salvar':'A IA não devolveu texto para os idiomas do projeto');
      return}
    case 'wttsave':{
      const bp=btn.closest('[data-ts-bp]');
      const texts={};
      bp.querySelectorAll('[data-ts-wtt]').forEach(ta=>{
        if(ta.value!==(ta.dataset.tsOrig||''))texts[ta.dataset.tsWtt]=ta.value});
      if(!Object.keys(texts).length)return toast('Nada mudou em "O que testar"');
      const r=await tsRun(btn,()=>api('/api/testes/ios/whattotest',{project:P,buildId:bp.dataset.tsBp,texts}));
      if(!r)return;
      toast('"O que testar" salvo');
      await tsReload('ios');return}
    case 'reviewform':{
      const bid=btn.dataset.tsB||btn.closest('[data-ts-rf]').dataset.tsRf;
      tsS.review=tsS.review===bid?'':bid;
      tsRenderPane();return}
    case 'submitreview':
      return tsSubmitReview(btn);

    /* ----- Google Play ----- */
    case 'promote':{
      const track=btn.dataset.tsTrack;
      tsS.promoteTrack=tsS.promoteTrack===track?'':track;
      tsRenderPane();return}
    case 'promotego':
      return tsPromote(btn);
    case 'savetesters':{
      const track=btn.dataset.tsTrack;
      const groups=btn.closest('[data-ts-track]').querySelector('[data-ts-groups]').value;
      const r=await tsRun(btn,()=>api('/api/testes/android/testers',{project:P,track,groups}));
      if(!r)return;
      toast('Google Groups salvos');
      await tsReload('android');return}
  }}

/* envia a revisão beta: só manda os idiomas com texto; confirma antes porque sai para a Apple */
async function tsSubmitReview(btn){
  const box=btn.closest('[data-ts-rf]');
  const bid=box.dataset.tsRf;
  const msg=box.querySelector('[data-ts-msg]');
  const details={};
  box.querySelectorAll('[data-ts-rd]').forEach(el=>{
    details[el.dataset.tsRd]=el.type==='checkbox'?el.checked:el.value.trim()});
  const info={};
  const slot=l=>(info[l]=info[l]||{description:'',feedbackEmail:''});
  box.querySelectorAll('[data-ts-bi-desc]').forEach(el=>{slot(el.dataset.tsBiDesc).description=el.value.trim()});
  box.querySelectorAll('[data-ts-bi-mail]').forEach(el=>{slot(el.dataset.tsBiMail).feedbackEmail=el.value.trim()});
  Object.keys(info).forEach(l=>{if(!info[l].description&&!info[l].feedbackEmail)delete info[l]});
  if(!confirm('Enviar este build para a revisão beta da Apple?'))return;
  const r=await tsRun(btn,()=>api('/api/testes/ios/submit',{project:tsS.project,buildId:bid,details,info}),msg);
  if(!r)return;
  tsS.review='';
  toast(r.message||'Enviado para a revisão beta');
  await tsReload('ios')}

/* promoção Android: mesmo body que ljPromote (lojas.js) usa em /api/lojas/promote */
async function tsPromote(btn){
  const box=btn.closest('[data-ts-pf]');
  const from=box.dataset.tsPf;
  const tr=tsAndroidTrack(from);
  const rel=((tr&&tr.releases)||[])[Number(box.querySelector('[data-ts-pfrel]').value)];
  if(!rel)return toast('Escolha a versão');
  const build=tsTopCode(rel.versionCodes);
  if(!build)return toast('Esta versão não tem versionCode');
  const vm=String(rel.name||'').match(/\d+(\.\d+){0,3}/);
  const body={project:tsS.project,store:'android',version:vm?vm[0]:build,
    to_track:box.querySelector('[data-ts-pfto]').value,
    status:box.querySelector('[data-ts-pfst]').value,from_track:from};
  if(body.status==='inProgress'){
    const pct=Number(box.querySelector('[data-ts-pffr]').value);
    if(!(pct>=1&&pct<=100))return toast('Informe um percentual entre 1 e 100');
    body.fraction=pct/100}
  if(!confirm(`Promover a versão ${rel.name||body.version} (build ${build}) para ${TS_TRACK_LABELS[body.to_track]||body.to_track}?`))return;
  const msg=box.querySelector('[data-ts-msg]');
  const r=await tsRun(btn,()=>api('/api/lojas/promote',body),msg);
  if(!r)return;
  tsS.promoteTrack='';
  toast(r.message||'Build promovido');
  await tsReload('android')}
