/* ---------- Projetos: "Gerenciar lojas publicadas" (App Store, Google Play, Steam) ----------
   script clássico carregado depois de database.js e lojas2.js.
   Abre um pmModal com 3 abas. Usa os globais: $, esc, toast, api, bi, go, pmModal, pmClose, pmBusy, pmFmtDate,
   pmCur, projConfigure, projBuild, projDeliver (projects.js / deliver.js / index.html) e de lojas2.js:
   LOJAS_FIELDS, lojasIaPopup, lojasImagesHtml, lojasImagesBind.
   Só globais: lojasAbrir e funções/variáveis com prefixo lj. */

const ljTabs=['ios','android','pc'];
const ljIcons={ios:'apple',android:'googleplay',pc:'steam'};
const ljActs={accounts:1,configure:1,build:1,deliver:1};
const ljRoleLabels={prod:'Produção',dev:'Desenvolvimento'};

(function ljInitStyle(){
  if(document.getElementById('ljStyle'))return;
  const s=document.createElement('style');s.id='ljStyle';
  s.textContent=`
.lj-warnbox{background:rgba(245,176,65,.12);border:1px solid var(--warn);border-radius:12px;padding:12px 14px;margin-bottom:12px;font-size:13px}
.lj-steps{margin:8px 0 0;padding-left:20px;font-size:13px}
.lj-tabs button b{font-size:13px}
.lj-chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 12px}
.lj-chips .btn{padding:5px 10px;font-size:13px}
.lj-dot{color:var(--warn);font-size:11px}
.lj-fld textarea{width:100%;box-sizing:border-box;resize:vertical;font:inherit;color:var(--text);background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.lj-fld.lj-changed textarea{border-color:var(--warn)}
.lj-fld label{display:block;margin-bottom:4px}
.lj-cnt{text-align:right;font-size:12px}
.lj-cnt.lj-over{color:var(--bad)}
.lj-bar{flex-wrap:wrap}
`;
  document.head.appendChild(s)})();

/* estado do popup aberto (um por vez): {project, ov, tab, st:{ios,android,pc}, el, body} */
let ljS=null;

/* ---------- helpers ---------- */
function ljAlive(){return !!(ljS&&pmCur&&pmCur.el===ljS.el)}
function ljStore(k){
  const all=(ljS&&ljS.ov&&ljS.ov.stores)||{};
  return all[k]||{state:'error',label:k,problem:'Loja indisponível.',steps:[],actions:[]}}
function ljSt(k){
  if(!ljS.st[k])ljS.st[k]={version:'',build:'',f:null,orig:{},cur:{},loc:'',loading:false,err:'',tok:0,loadedVersion:null};
  return ljS.st[k]}
function ljCopy(o){return JSON.parse(JSON.stringify(o||{}))}
function ljGet(o,loc,fid){const r=o&&o[loc];const v=r?r[fid]:'';return v==null?'':String(v)}
function ljChg(st,loc,fid){return ljGet(st.cur,loc,fid).trim()!==ljGet(st.orig,loc,fid).trim()}
function ljLocChanged(st,loc){return ((st.f&&st.f.fieldList)||[]).some(fid=>ljChg(st,loc,fid))}
function ljFieldLabel(fid){return (typeof LOJAS_FIELDS!=='undefined'&&LOJAS_FIELDS[fid])||fid}
function ljLocLabel(l){const c=((ljS&&ljS.ov&&ljS.ov.catalog)||[]).find(x=>x.code===l);return c?c.label:l}
function ljRows(fid){return (fid==='description'||fid==='fullDescription'||fid==='whatsNew')?6:3}
function ljOver(txt,lim){return !!lim&&String(txt||'').length>lim}
function ljCntTxt(txt,lim){return String(txt||'').length+(lim?'/'+lim:'')}
function ljDate(v){
  if(v==null||v==='')return '—';
  if(typeof v==='number')return pmFmtDate(v);
  const d=new Date(v);
  return isNaN(d.getTime())?String(v):d.toLocaleString('pt-BR')}
function ljStateTxt(s){
  return {no_account:'conta não vinculada',no_app:'app não encontrado',not_published:'ainda não publicado',error:'erro ao consultar a loja'}[s]||'indisponível'}
/* contagem das alterações: sendable = alteradas e não vazias (são enviadas); emptied = apagadas (não enviadas) */
function ljCount(k){
  const st=ljSt(k), f=st.f, out={changed:0,sendable:0,emptied:0,over:0,locs:0,data:{}};
  if(!f)return out;
  const lim=f.limits||{};
  for(const loc of Object.keys(f.locales||{})){
    for(const fid of (f.fieldList||[])){
      if(!ljChg(st,loc,fid))continue;
      const cur=ljGet(st.cur,loc,fid);
      out.changed++;
      if(!cur.trim()){out.emptied++;continue}
      out.sendable++;
      if(lim[fid]&&cur.length>lim[fid])out.over++;
      (out.data[loc]||(out.data[loc]={}))[fid]=cur.trim();
    }
  }
  out.locs=Object.keys(out.data).length;
  return out}
function ljDirtyAny(k){
  if(!ljS||!k||!ljS.st[k]||!ljS.st[k].f)return false;
  return ljCount(k).changed>0}

/* ---------- abertura ---------- */
async function lojasAbrir(project){
  const done=pmBusy('Abrindo as lojas…');
  let ov=null;
  try{ov=await api('/api/lojas/overview?project='+encodeURIComponent(project))}
  catch(e){toast(e.message)}
  finally{done()}
  if(!ov)return;
  ljOpen(project,ov)}

function ljOpen(project,ov){
  const first=ljTabs.find(k=>ljStore(k).state==='ok')||'ios';
  ljS={project,ov,tab:first,st:{},el:null,body:null};
  const m=pmModal('🏪 Gerenciar lojas publicadas — '+project,
    '<div class="segtabs lj-tabs" data-lj-tabs></div><div data-lj-pane></div>',
    [{label:'Fechar',cls:'',onClick:()=>ljClose()}]);
  ljS.el=m.el;ljS.body=m.body;
  const box=m.el.querySelector('.pm-box');if(box)box.style.maxWidth='min(980px,96vw)';
  m.body.addEventListener('click',ljOnClick);
  m.body.addEventListener('input',ljOnInput);
  m.body.addEventListener('change',ljOnChange);
  ljRenderPane()}

function ljClose(){
  if(ljDirtyAny(ljS&&ljS.tab)&&!confirm('Há alterações não salvas. Fechar mesmo assim?'))return;
  pmClose()}

/* ---------- eventos (delegação no corpo do modal) ---------- */
function ljOnClick(e){
  if(!ljAlive())return;
  const t=e.target.closest&&e.target.closest('[data-lj-tab],[data-lj-loc],[data-lj-act]');
  if(!t||!ljS.body.contains(t))return;
  if(t.hasAttribute('data-lj-tab'))return ljSwitchTab(t.dataset.ljTab);
  if(t.hasAttribute('data-lj-loc'))return ljSwitchLoc(t.dataset.ljLoc);
  ljAct(t.dataset.ljAct)}
function ljOnInput(e){
  if(!ljAlive())return;
  const ta=e.target;
  if(ta&&ta.matches&&ta.matches('textarea[data-lj-field]'))ljOnTyped(ta)}
function ljOnChange(e){
  if(!ljAlive())return;
  const sel=e.target;
  if(sel&&sel.matches&&sel.matches('select[data-lj-ver]'))ljPickVersion(sel)}

function ljAct(id){
  if(!id)return;
  if(id==='ia')return ljIa();
  if(id==='save')return ljSave(ljS.tab);
  if(id==='pedit')return ljEditPending(ljS.tab);
  if(id==='submit')return ljSubmit(ljS.tab);
  if(id==='promote')return ljPromote(ljS.tab);
  if(!ljActs[id])return;
  if(ljDirtyAny(ljS.tab)&&!confirm('Há alterações não salvas. Sair mesmo assim?'))return;
  const p=ljS.project;
  pmClose();
  if(id==='accounts')go('accounts');
  else if(id==='configure')projConfigure(p);
  else if(id==='build')projBuild(p);
  else if(id==='deliver')projDeliver(p)}

/* ---------- troca de aba, idioma e versão ---------- */
function ljSwitchTab(t){
  if(!ljAlive()||t===ljS.tab||!ljTabs.includes(t))return;
  const cur=ljS.tab;
  if(ljDirtyAny(cur)){
    if(!confirm('Há alterações não salvas nesta loja. Descartar e trocar de aba?'))return;
    ljRevert(cur)}
  ljS.tab=t;
  ljRenderPane()}
function ljRevert(k){const st=ljSt(k);st.cur=ljCopy(st.orig)}
function ljSwitchLoc(l){
  if(!ljAlive())return;
  const k=ljS.tab,st=ljSt(k);
  if(!st.f||l===st.loc||!Object.prototype.hasOwnProperty.call(st.f.locales||{},l))return;
  st.loc=l;
  ljRenderFields(k)}
function ljPickVersion(sel){
  const k=ljS.tab,st=ljSt(k);
  const v=sel.value,opt=sel.selectedOptions&&sel.selectedOptions[0];
  if(v===st.version)return;
  if(ljDirtyAny(k)&&!confirm('Descartar as alterações não salvas e carregar a versão '+v+'?')){sel.value=st.version;return}
  st.version=v;st.build=(opt&&opt.dataset.build)||'';
  ljLoad(k)}

/* ---------- render ---------- */
function ljRenderTabs(){
  const box=ljS.body.querySelector('[data-lj-tabs]');if(!box)return;
  box.innerHTML=ljTabs.map(k=>{
    const S=ljStore(k),ok=S.state==='ok';
    return `<button type="button" data-lj-tab="${k}" class="${k===ljS.tab?'on':''}">${bi(ljIcons[k])}<span>${esc(S.label||k)}</span><b style="color:${ok?'var(--ok)':'var(--warn)'}">${ok?'✔':'⚠'}</b></button>`}).join('')}

function ljRenderPane(){
  if(!ljAlive())return;
  const pane=ljS.body.querySelector('[data-lj-pane]');if(!pane)return;
  const k=ljS.tab,S=ljStore(k);
  ljRenderTabs();
  if(S.state!=='ok'){pane.innerHTML=ljWarnHtml(k,S);return}
  if(k==='pc'){pane.innerHTML=ljSteamHtml(S);return}
  pane.innerHTML=ljStoreHtml(k,S);
  const st=ljSt(k);
  if(!st.version){
    const box=pane.querySelector('[data-lj-fields]');
    if(box)box.innerHTML='<p class="hint">Nenhuma versão disponível para editar.</p>';
    return}
  if(st.loading||(st.f&&st.loadedVersion===st.version))ljRenderFields(k);
  else ljLoad(k)}

/* aviso de loja fora do ar: problema, passos e botões das ações */
function ljWarnHtml(k,S){
  const steps=S.steps||[];
  const acts=(S.actions||[]).filter(a=>a&&ljActs[a.id]);
  return `<div class="lj-warnbox"><b>⚠ ${esc(S.label||k)}: ${esc(ljStateTxt(S.state))}</b>
    ${S.problem?`<p style="margin:8px 0 0">${esc(S.problem)}</p>`:''}
    ${steps.length?`<ol class="lj-steps">${steps.map(s=>`<li>${esc(s)}</li>`).join('')}</ol>`:''}
    ${acts.length?`<div class="pm-row" style="margin:10px 0 0">${acts.map(a=>`<button type="button" class="btn sm${a.id==='accounts'||a.id==='configure'?'':' pri'}" data-lj-act="${esc(a.id)}">${esc(a.label||a.id)}</button>`).join('')}</div>`:''}
  </div>`}

/* Steam: sem página editável; só mostra builds e atalhos */
function ljSteamHtml(S){
  const sv=S.store||{},lt=S.latest||null,vs=S.versions||[];
  return `<div class="pm-grid" style="grid-template-columns:repeat(auto-fill,minmax(260px,1fr));margin-bottom:12px">
      <div class="pm-card"><b>Na Steam</b>
        <div>versão ${esc(sv.version||'—')} · branch ${esc(sv.track||'—')}</div>
        <div class="hint">${esc(ljDate(sv.date))}</div></div>
      <div class="pm-card"><b>Mais recente</b>
        ${lt?`<div>v${esc(lt.version)} (build ${esc(lt.build)})</div>`:'<div class="hint">Nenhum build release enviável</div>'}</div>
    </div>
    ${S.upToDate?'<span class="pill ok"><i></i>Já enviada</span>':''}
    <div class="pm-sec" style="margin-top:12px"><b>Builds</b>
      <ul style="margin:6px 0 0;padding-left:20px;font-size:13px">${vs.map(v=>`<li>v${esc(v.version)} (build ${esc(v.build)})${v.deliverable===false?' · bloqueada: '+esc(v.reason||''):''}</li>`).join('')||'<li class="hint">nenhum build release</li>'}</ul></div>
    <p class="hint">A página da loja da Steam (textos e imagens) é editada no painel do Steamworks: o painel só envia builds.</p>
    <div class="pm-row"><button type="button" class="btn pri" data-lj-act="deliver">📤 Enviar para a Steam</button><button type="button" class="btn" data-lj-act="configure">⚙ Configurar</button></div>`}

/* cabeçalho das lojas ios/android: na loja x mais recente, selos */
function ljHeadHtml(S){
  const sv=S.store||null,lt=S.latest||null;
  const url=sv&&sv.url&&/^https?:\/\//.test(String(sv.url))?` <a href="${esc(sv.url)}" target="_blank" rel="noopener">abrir na loja</a>`:'';
  const acc=S.account&&S.account.label?` · conta ${esc(S.account.label)}`:'';
  const bld=b=>b&&b.build?` (build ${esc(b.build)})`:'';
  const storeTxt=sv?`<div>v${esc(sv.version)}${bld(sv)}</div>
      <div class="hint">${esc(sv.state||'')}${sv.track?' · faixa '+esc(sv.track):''}${sv.date?' · '+esc(ljDate(sv.date)):''}${url}</div>`:'<div class="hint">Não publicada</div>';
  const latestTxt=lt?`<div>v${esc(lt.version)}${bld(lt)}</div>
      ${lt.source==='apple'?'<div class="hint">já enviado ao App Store Connect (TestFlight)</div>':''}
      ${lt.database?`<div class="hint">🗄 ${esc(lt.database.name||'')}${lt.database.role?' · '+esc(ljRoleLabels[lt.database.role]||lt.database.role):''}</div>`:''}`:'<div class="hint">Nenhum build release enviável</div>';
  const pd=S.pending||null;
  /* versão criada na loja que espera envio (ou promoção): cartão próprio, sem o selo "nova versão" dela */
  const showNewer=!!S.newer&&!(pd&&lt&&String(pd.version)===String(lt.version));
  const pendHtml=pd?`<div class="pm-card" style="border-left:4px solid var(--warn);margin-bottom:12px"><b>v${esc(pd.version)} · ${esc(pd.label||'')}</b>
      ${pd.canSubmit?'<div class="hint">Criada na loja: falta enviar para a revisão</div>':''}
      ${pd.canPromote?'<div class="hint">Falta promover para produção</div>':''}
      <div class="pm-row" style="margin:10px 0 0"><button type="button" class="btn sm" data-lj-act="pedit">✏️ Editar</button>${pd.canSubmit?'<button type="button" class="btn sm pri" data-lj-act="submit">📨 Enviar para revisão</button>':''}${pd.canPromote?'<button type="button" class="btn sm pri" data-lj-act="promote">🚀 Promover para produção</button>':''}</div></div>`:'';
  return `<div class="pm-grid" style="grid-template-columns:repeat(auto-fill,minmax(260px,1fr));margin-bottom:12px">
      <div class="pm-card"><b>Na loja</b>${storeTxt}<div class="hint">${esc(S.appRef||'')}${acc}</div></div>
      <div class="pm-card"><b>Mais recente disponível</b>${latestTxt}</div>
    </div>
    ${pendHtml}${S.upToDate&&lt?`<div style="margin-bottom:12px"><span class="pill ok"><i></i>✔ Já está publicada: a versão ${esc(lt.version)} é a mais recente</span></div>`:''}
    ${showNewer?'<div style="margin-bottom:12px"><span class="pill warn"><i></i>Nova versão disponível para publicar</span></div>':''}`}

/* versão padrão: a pendente (criada na loja), depois a mais recente; senão a da loja */
function ljDefaultVer(S){
  const lt=S.latest,sv=S.store;
  if(S.pending&&S.pending.version)return {version:String(S.pending.version),build:String(S.pending.build||'')};
  if(lt&&lt.version)return {version:String(lt.version),build:String(lt.build||'')};
  if(sv&&sv.version)return {version:String(sv.version),build:String(sv.build||'')};
  const first=(S.versions||[])[0];
  return first?{version:String(first.version),build:String(first.build||'')}:{version:'',build:''}}

function ljVerOpts(S,sel){
  const list=S.versions||[],sv=S.store||null,storeV=sv&&sv.version?String(sv.version):'';
  let html='';
  /* a versão da loja pode não ter build local: entra como opção própria */
  if(storeV&&!list.some(v=>String(v.version)===storeV))
    html+=`<option value="${esc(storeV)}" data-build="${esc(sv.build||'')}" ${storeV===sel?'selected':''}>v${esc(storeV)} · na loja (sem build local)</option>`;
  /* a versão pendente (criada na loja) também pode não ter build local: entra como opção própria */
  const pd=S.pending||null,pv=pd&&pd.version?String(pd.version):'';
  if(pv&&pv!==storeV&&!list.some(v=>String(v.version)===pv))
    html+=`<option value="${esc(pv)}" data-build="${esc(pd.build||'')}" ${pv===sel?'selected':''}>v${esc(pv)} · pendente na loja (sem build local)</option>`;
  html+=list.map(v=>{
    const na=storeV&&String(v.version)===storeV;
    const blocked=v.deliverable===false;
    const lbl=`v${v.version}${v.build?' (build '+v.build+')':''}${v.source==='apple'?' · no App Store Connect':''}${na?' · na loja':''}${blocked?' · bloqueada: '+(v.reason||''):''}`;
    return `<option value="${esc(v.version)}" data-build="${esc(v.build)}"${blocked?' disabled':''} ${String(v.version)===sel?'selected':''}>${esc(lbl)}</option>`}).join('');
  return html}

function ljStoreHtml(k,S){
  const st=ljSt(k);
  if(!st.version){const d=ljDefaultVer(S);st.version=d.version;st.build=d.build}
  return ljHeadHtml(S)+
    `<div class="field"><label for="ljVer">Versão</label><select id="ljVer" data-lj-ver>${ljVerOpts(S,st.version)}</select></div>`+
    `<div data-lj-fields></div>`}

/* ---------- carregamento dos campos ---------- */
async function ljLoad(k){
  if(!ljAlive())return;
  const st=ljSt(k),tok=++st.tok;
  const project=ljS.project,version=st.version,build=st.build||'';
  st.loading=true;st.err='';st.f=null;st.orig={};st.cur={};st.loadedVersion=null;
  ljRenderFields(k);
  let f=null,err='';
  try{
    f=await api('/api/lojas/fields?project='+encodeURIComponent(project)+'&store='+encodeURIComponent(k)+
      '&version='+encodeURIComponent(version)+'&build='+encodeURIComponent(build))}
  catch(e){err=e.message||String(e)}
  if(!ljAlive()||st.tok!==tok)return;
  st.loading=false;
  if(f)ljApply(k,f,version);
  else st.err=err;
  ljRenderFields(k)}

function ljApply(k,f,version){
  const st=ljSt(k);
  st.f=f;st.loadedVersion=version;
  st.orig=ljCopy(f.locales);st.cur=ljCopy(f.locales);
  const locs=Object.keys(f.locales||{});
  if(!locs.includes(st.loc))st.loc=locs[0]||''}

function ljRenderFields(k){
  if(!ljAlive()||ljS.tab!==k)return;
  const box=ljS.body.querySelector('[data-lj-pane] [data-lj-fields]');if(!box)return;
  box.innerHTML=ljFieldsHtml(k);
  ljRenderImages(k)}

function ljFieldsHtml(k){
  const st=ljSt(k),f=st.f;
  if(st.loading)return '<p class="hint">Carregando campos…</p>';
  if(st.err)return `<p class="pm-err">${esc(st.err)}</p>`;
  if(!f)return '';
  const locs=Object.keys(f.locales||{});
  if(!locs.length)return '<p class="hint">Nenhum idioma disponível nesta loja.</p>';
  if(!locs.includes(st.loc))st.loc=locs[0];
  const warn=f.editable?'':`<div class="lj-warnbox">${esc(f.editReason||'Esta versão não pode ser editada.')}</div>`;
  const note=f.note?`<p class="hint" style="margin:8px 0 0">${esc(f.note)}</p>`:'';
  return `${warn}${ljChipsHtml(k)}<div data-lj-flist>${ljFieldsListHtml(k)}</div><div data-lj-imgs></div>${ljBarHtml(k)}${note}`}

function ljChipsHtml(k){
  const st=ljSt(k),locs=Object.keys((st.f&&st.f.locales)||{});
  return `<div class="lj-chips" data-lj-chips>${locs.map(l=>`<button type="button" class="btn sm${l===st.loc?' pri':''}" data-lj-loc="${esc(l)}">${esc(ljLocLabel(l))}${ljLocChanged(st,l)?' <span class="lj-dot">●</span>':''}</button>`).join('')}</div>`}

function ljFieldsListHtml(k){
  const st=ljSt(k),f=st.f,loc=st.loc,ro=f.editable?'':' readonly';
  return (f.fieldList||[]).map(fid=>{
    const txt=ljGet(st.cur,loc,fid),lim=(f.limits||{})[fid],chg=ljChg(st,loc,fid);
    const lead=txt.startsWith('\n')?'\n':'';
    return `<div class="field lj-fld${chg?' lj-changed':''}" data-lj-wrap="${esc(fid)}">
      <label for="ljF-${esc(fid)}">${esc(ljFieldLabel(fid))}${chg?' <span class="lj-dot">● alterado</span>':''}</label>
      <textarea id="ljF-${esc(fid)}" data-lj-field="${esc(fid)}" rows="${ljRows(fid)}"${ro}>${lead}${esc(txt)}</textarea>
      <div class="hint lj-cnt${ljOver(txt,lim)?' lj-over':''}" data-lj-cnt="${esc(fid)}">${esc(ljCntTxt(txt,lim))}</div></div>`}).join('')}

/* motivos de desabilitar "Enviar para revisão" (ios) e "Promover" (android); '' = pode usar */
function ljSubmitWhy(P,st){
  if(!P||!P.canSubmit)return 'Só é possível enviar uma versão criada na App Store em estado editável';
  if(String(P.version)!==String(st.version))return 'Selecione a versão '+P.version+' para enviar';
  return ''}
function ljPromoteWhy(P,st){
  if(!P||!P.canPromote)return 'Não há release pendente de promoção nesta loja';
  if(String(P.build||'')!==String(st.build||''))return 'Selecione o build '+(P.build||'')+' para promover';
  return ''}

function ljBarHtml(k){
  const st=ljSt(k),f=st.f||{},c=ljCount(k),P=ljStore(k).pending||null;
  const canSave=!!f.editable&&c.sendable>0;
  const msg=c.changed?`${c.changed} campo(s) alterado(s)`:'Nenhuma alteração';
  const emp=c.emptied?` · ${c.emptied} apagado(s): não são enviados`:'';
  let extra='';
  if(k==='ios'){
    const why=ljSubmitWhy(P,st);
    extra=`<button type="button" class="btn pri" data-lj-act="submit" title="${esc(why||'Anexa o maior build válido da versão e envia para a revisão da Apple')}"${why?' disabled':''}>📨 Enviar para revisão</button>`}
  else if(k==='android'){
    const why=ljPromoteWhy(P,st);
    extra=`<button type="button" class="btn pri" data-lj-act="promote" title="${esc(why||'Copia este build para a faixa de destino')}"${why?' disabled':''}>🚀 Promover para produção</button>`}
  return `<div class="pm-row lj-bar" data-lj-bar style="margin-top:12px">
    <button type="button" class="btn" data-lj-act="ia"${f.editable?'':' disabled'}>✨ Gerar com IA</button>
    <button type="button" class="btn pri" data-lj-act="save"${canSave?'':' disabled'}>💾 Atualizar na loja</button>
    ${extra}
    <span class="hint">${esc(msg+emp)}</span></div>`}

/* repinta só chips e barra (sem recriar o textarea, para não perder o foco) */
function ljRefreshChrome(k){
  const chips=ljS.body.querySelector('[data-lj-chips]');if(chips)chips.outerHTML=ljChipsHtml(k);
  const bar=ljS.body.querySelector('[data-lj-bar]');if(bar)bar.outerHTML=ljBarHtml(k)}

/* digitação: grava em st.cur e atualiza contador/marca do campo */
function ljOnTyped(ta){
  const k=ljS.tab,st=ljSt(k),f=st.f;
  if(!f)return;
  const fid=ta.dataset.ljField,loc=st.loc;
  if(!st.cur[loc])st.cur[loc]={};
  st.cur[loc][fid]=ta.value;
  const wrap=ta.closest('[data-lj-wrap]');
  if(wrap){
    const chg=ljChg(st,loc,fid);
    wrap.classList.toggle('lj-changed',chg);
    const lab=wrap.querySelector('label');
    if(lab)lab.innerHTML=esc(ljFieldLabel(fid))+(chg?' <span class="lj-dot">● alterado</span>':'');
    const lim=(f.limits||{})[fid];
    const c=wrap.querySelector('[data-lj-cnt]');
    if(c){c.textContent=ljCntTxt(ta.value,lim);c.classList.toggle('lj-over',ljOver(ta.value,lim))}
  }
  ljRefreshChrome(k)}

/* ---------- imagens (o componente vive em lojas2.js; recriado a cada render para não duplicar eventos) ---------- */
function ljRenderImages(k){
  if(!ljAlive()||ljS.tab!==k)return;
  const old=ljS.body.querySelector('[data-lj-pane] [data-lj-imgs]');
  const st=ljSt(k),f=st.f;
  if(!old||!f)return;
  if(typeof lojasImagesHtml!=='function'||typeof lojasImagesBind!=='function'){
    old.innerHTML='<p class="hint">Imagens indisponíveis (lojas2.js não carregado).</p>';return}
  const loc=st.loc,ctx=ljCtx(k);
  const imgs=((f.images||{})[loc])||{},kinds=f.imageKinds||[];
  const nd=document.createElement('div');
  nd.setAttribute('data-lj-imgs','');
  nd.innerHTML=lojasImagesHtml(ctx,loc,imgs,kinds);
  old.replaceWith(nd);
  lojasImagesBind(nd,ctx,loc,imgs,kinds,images=>{
    if(!ljAlive()||!st.f)return;
    st.f.images=st.f.images||{};
    st.f.images[loc]=images||{};
    if(st.loc===loc&&ljS.tab===k)ljRenderImages(k)})}

/* contexto para lojas2.js (IA e imagens) */
function ljCtx(k){
  const st=ljSt(k),f=st.f||{};
  return {
    project:ljS.project,store:k,version:st.version,build:st.build||'',
    appName:ljS.project,
    fieldList:f.fieldList||[],limits:f.limits||{},
    locales:Object.keys(f.locales||{}),
    catalog:(ljS.ov&&ljS.ov.catalog)||[],
    getValues:()=>ljCopy(st.cur),
    setValue:(loc,field,text)=>{
      if(!st.cur[loc])st.cur[loc]={};
      st.cur[loc][field]=String(text==null?'':text)},
    imageKinds:f.imageKinds||[]}}

/* ---------- ações ---------- */
async function ljIa(){
  if(!ljAlive())return;
  const k=ljS.tab,st=ljSt(k);
  if(!st.f||!st.f.editable)return;
  if(typeof lojasIaPopup!=='function')return toast('Popup de IA indisponível (lojas2.js não carregado)');
  await lojasIaPopup(ljCtx(k),res=>{
    if(!ljAlive())return;
    const n=(res&&res.generated)||0;
    toast(n?`${n} campo(s) gerado(s) — revise antes de atualizar`:'Nenhum campo foi gerado');
    ljRenderFields(k)})}

async function ljSave(k){
  if(!ljAlive()||ljS.tab!==k)return;
  const st=ljSt(k),f=st.f;
  if(!f||!f.editable)return;
  const c=ljCount(k);
  if(!c.sendable)return toast('Nenhuma alteração para salvar');
  const S=ljStore(k);
  const names=Object.keys(c.data).map(ljLocLabel).join(', ');
  let msg=`Atualizar ${S.label||k} agora?\n\nVersão: ${st.version}\n${c.sendable} campo(s) em ${c.locs} idioma(s): ${names}\n\nNão envia build nem submete para revisão.`;
  if(c.emptied)msg+=`\n\n${c.emptied} campo(s) apagado(s) não serão enviados.`;
  if(c.over)msg+=`\n\n${c.over} campo(s) passam do limite e podem ser recusados pela loja.`;
  if(!confirm(msg))return;
  const done=pmBusy('Atualizando na loja…');
  let r=null;
  try{
    r=await api('/api/lojas/save',{project:ljS.project,store:k,version:st.version,build:st.build||'',data:{locales:c.data}})}
  catch(e){toast(e.message)}
  finally{done()}
  if(!r)return;
  toast(`${(r.saved||[]).length} campo(s) atualizados na loja`);
  if((r.warnings||[]).length)toast(r.warnings.join(' · '));
  await ljLoad(k);
  await ljRefreshOv()}

/* recarrega o overview (cartão pendente, selos) sem mexer em aba, versão, idioma nem textos */
async function ljRefreshOv(){
  if(!ljAlive())return;
  const project=ljS.project;
  let ov=null;
  try{ov=await api('/api/lojas/overview?project='+encodeURIComponent(project))}
  catch(e){toast(e.message)}
  if(!ov||!ljAlive())return;
  ljS.ov=ov;
  ljRenderPane()}

/* seleciona uma versão no select e recarrega os campos (confirma se há alterações não salvas) */
function ljSetVersion(k,v,b){
  const st=ljSt(k);
  if(ljDirtyAny(k)&&!confirm('Descartar as alterações não salvas e carregar a versão '+v+'?'))return false;
  st.version=v;st.build=b||'';
  const sel=ljS.body.querySelector('select[data-lj-ver]');
  if(sel)sel.value=v;
  ljLoad(k);
  return true}

/* "✏️ Editar" do cartão pendente: seleciona a versão pendente, recarrega os campos e rola até eles */
function ljEditPending(k){
  if(!ljAlive()||ljS.tab!==k)return;
  const P=ljStore(k).pending||null;
  if(!P||!P.version)return;
  if(!ljSetVersion(k,String(P.version),String(P.build||'')))return;
  const sel=ljS.body.querySelector('select[data-lj-ver]');
  if(sel)sel.scrollIntoView({block:'center'})}

/* "📨 Enviar para revisão" (ios): anexa o maior build válido da versão pendente e envia */
async function ljSubmit(k){
  if(!ljAlive()||ljS.tab!==k)return;
  const P=ljStore(k).pending||null;
  if(!P||!P.canSubmit)return toast('Esta versão não pode ser enviada para revisão agora');
  const v=String(P.version),b=P.build?String(P.build):'';
  const unsaved=ljDirtyAny(k)?'\n\nHá alterações não salvas nos campos: elas não entram neste envio.':'';
  if(!confirm(`A versão ${v}${b?' (build '+b+')':''} será anexada e enviada para a revisão da Apple. Continuar?`+unsaved))return;
  const done=pmBusy('Enviando para revisão…');
  let r=null;
  try{r=await api('/api/lojas/submit',{project:ljS.project,store:k,version:v,build:b})}
  catch(e){toast(e.message)}
  finally{done()}
  if(!r)return;
  toast(r.message||'Versão enviada para revisão');
  await ljRefreshOv()}

/* "🚀 Promover para produção" (android): diálogo com faixa de destino, status e fração; depois POST */
function ljPromote(k){
  if(!ljAlive()||ljS.tab!==k)return;
  const P=ljStore(k).pending||null;
  if(!P||!P.canPromote)return toast('Não há release pendente de promoção nesta loja');
  const from=String(P.track||'');
  const TL={production:'Produção',beta:'Teste aberto (beta)',alpha:'Teste fechado (alpha)',internal:'Teste interno (internal)'};
  const targets=['production','beta','alpha','internal'].filter(t=>t!==from);
  const html=`<p class="hint" style="margin:0 0 10px">Copia o build <b>${esc(P.build||'')}</b> (v${esc(P.version)}) da faixa <b>${esc(from)}</b> para a faixa de destino, mantendo as notas da versão.</p>
    <div class="field"><label for="ljPrTo">Faixa de destino</label><select id="ljPrTo">${targets.map(t=>`<option value="${esc(t)}"${t==='production'?' selected':''}>${esc(TL[t])}</option>`).join('')}</select></div>
    <div class="field"><label for="ljPrSt">Status</label><select id="ljPrSt">
      <option value="completed" selected>Liberar para todos</option>
      <option value="inProgress">Liberação gradual</option>
      <option value="draft">Só rascunho</option></select></div>
    <div class="field" id="ljPrFrW" style="display:none"><label for="ljPrFr">Percentual dos usuários (1 a 100)</label><input id="ljPrFr" type="number" min="1" max="100" step="1" value="10"></div>
    <div class="pm-err" id="ljPrMsg"></div>`;
  if(typeof lojasOverlay!=='function')return toast('Diálogo indisponível (lojas2.js não carregado)');
  const done=pmBusy('Abrindo…');
  let ov=null;
  const doPromote=async()=>{
    const q=sel=>ov.body.querySelector(sel);
    const body={project:ljS.project,store:k,version:String(P.version),build:String(P.build||''),
      to_track:q('#ljPrTo').value,status:q('#ljPrSt').value,from_track:from};
    if(body.status==='inProgress'){
      const pct=Number(q('#ljPrFr').value);
      if(!(pct>=1&&pct<=100)){q('#ljPrMsg').textContent='Informe um percentual entre 1 e 100';return}
      body.fraction=pct/100}
    q('#ljPrMsg').textContent='';
    const busy=pmBusy('Promovendo…');
    let r=null;
    try{r=await api('/api/lojas/promote',body)}
    catch(e){q('#ljPrMsg').textContent=e.message||String(e)}
    finally{busy()}
    if(!r)return;
    ov.close();
    toast(r.message||'Build promovido');
    await ljRefreshOv()};
  ov=lojasOverlay('Promover para produção — v'+P.version,html,[
    {label:'Cancelar',cls:'',onClick:()=>ov.close()},
    {label:'🚀 Promover',cls:'pri',onClick:()=>doPromote()}]);
  ov.body.querySelector('#ljPrSt').onchange=e=>{
    ov.body.querySelector('#ljPrFrW').style.display=e.target.value==='inProgress'?'':'none'};
  done()}
