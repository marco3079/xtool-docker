/* ---------- PC (Electron) e Steam: compilar o site como app de PC e enviar para a Steam ---------- */
/* script clássico carregado depois do script principal do index.html: usa os globais $, val, chk, esc, toast, api, run, go, projCache, saveProjMeta, applyVerSrc, bumpLast */
let pcCur=null, steamAccs=[], steamApps=[], pcWanted=null, pcBuilt=false, steamBuilt=false;
let pcWantedApp=null, steamAppsBuilt=false; /* pcWantedApp = {accountId, appId} pedido por openPcPublishApp */
/* perfil do tipo de código atual (/api/pc/profile): {type,preBuild,webDir,warnings,errors,project}; null = sem perfil */
let pcProfile=null;
/* verificação de login das contas Steam: id -> último resultado de /api/steam/check ou {state:'checking'} */
let steamStat={}, steamChecking=false, steamWatchTimer=null;
/* id da conta Steam principal (vem do topo); '' se não houver */
const steamPrincipalId=()=>(typeof topState!=='undefined'&&topState&&topState.defaults&&topState.defaults.steamAccountId)||'';

/* ---------- aba PC / Steam ---------- */
function buildPcSection(){
  $('s-pc').innerHTML=`
  <div class="segtabs"><button data-t="publish" onclick="go('publish')">🍎 App Store (iOS)</button><button data-t="android" onclick="go('android')"><span style="color:#34a853">▶</span> Google Play (Android)</button><button data-t="pc" onclick="go('pc')">🎮 Steam (PC)</button></div>
  <div class="row" style="margin-bottom:14px">
    <select id="pcProject" style="max-width:260px" onchange="loadPc()"></select>
    <select id="pcSteamAcc" style="max-width:260px" onchange="pcAccChanged()"></select>
    <select id="pcSteamApp" style="max-width:260px" onchange="pcAppChanged()"></select>
    <button class="btn" onclick="loadPc()">Recarregar</button>
  </div>
  <div id="pcInfo"></div>
  <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(340px,1fr))">
    <div class="card"><h3>1 · Versão</h3><p>Nome que aparece na Steam e no app de PC (precisa ser maior que o último build).</p>
      <div class="field"><label>A versão vem de</label><select id="pcVerSrc" onchange="setPcVerSrc(this.value)"></select></div>
      <div class="field"><label>Versão</label><input type="text" id="pcVersion" placeholder="1.0.0" style="font-family:var(--mono)"></div>
      <div class="field"><label>Nome do app</label><input type="text" id="pcAppName" placeholder="Nome do app" onchange="savePcMeta({appName:this.value.trim()})"></div>
    </div>
    <div class="card"><h3>2 · Compilar para PC</h3><p>Empacota o site do projeto como app de PC (Electron).</p>
      <div class="field"><label>Tipo de código</label><select id="pcType" onchange="pcTypeChanged()"></select></div>
      <div class="hint" id="pcTypeHint" style="margin:-4px 0 10px"></div>
      <div class="field"><label>Plataformas</label><div class="row">
        <label class="check" style="margin:0 10px 0 0"><input type="checkbox" id="pcPlat-win32" checked onchange="pcPlatChanged()">Windows</label>
        <label class="check" style="margin:0 10px 0 0"><input type="checkbox" id="pcPlat-linux" onchange="pcPlatChanged()">Linux</label>
        <label class="check" style="margin:0 10px 0 0"><input type="checkbox" id="pcPlat-darwin" onchange="pcPlatChanged()">macOS</label>
      </div></div>
      <label class="check"><input type="checkbox" id="pcZip" onchange="savePcMeta({zip:chk('pcZip')})">Gerar .zip para baixar</label>
      <div class="field"><label>Comando antes do build</label><input type="text" id="pcPre" style="font-family:var(--mono)" onchange="savePcMeta({preBuild:val('pcPre')})"></div>
      <p class="hint" style="margin:-6px 0 10px">vazio = padrão detectado, - = pular</p>
      <div class="field"><label>Pasta do site</label><input type="text" id="pcWebDir" style="font-family:var(--mono)" onchange="savePcMeta({webDir:val('pcWebDir')})"></div>
      <p class="hint" style="margin:-6px 0 10px">vazio = detectado</p>
      <div class="field"><label>Versão do Electron</label><input type="text" id="pcElectron" placeholder="33.4.11" style="font-family:var(--mono)" onchange="savePcMeta({electronVersion:val('pcElectron')})"></div>
      <p class="hint" style="margin:0 0 6px">O site abre por arquivo dentro do Electron: use caminhos relativos (Vite: base './').</p>
      <p class="hint" style="margin:0">macOS sai sem assinatura/notarização.</p>
    </div>
    <div class="card"><h3>3 · Descrição do build (Steam)</h3><p>Texto curto do build na Steam (até 200 caracteres). Gere com IA ou escreva.</p>
      <div class="row"><select id="pcAi" style="max-width:220px"></select>
        <input type="text" id="pcExtra" placeholder="Observações para a IA (opcional)" style="flex:1">
        <button class="btn pri" onclick="genPcDesc()">✨ Gerar com IA</button></div>
      <textarea id="pcDesc" rows="4" maxlength="200" oninput="$('pcDescCnt').textContent=this.value.length+'/200'" style="width:100%;margin-top:10px;background:var(--input);border:1px solid var(--line);border-radius:9px;padding:10px;color:var(--text);font:inherit;resize:vertical"></textarea>
      <div class="hint" id="pcDescCnt" style="text-align:right">0/200</div>
      <details style="margin-top:10px"><summary class="hint" style="cursor:pointer">Ver mudanças enviadas para a IA</summary><pre id="pcChanges" style="white-space:pre-wrap;font-family:var(--mono);font-size:12px;color:var(--muted);max-height:220px;overflow:auto"></pre></details>
    </div>
    <div class="card"><h3>4 · Compilar e enviar</h3><p>Gera os arquivos de PC e, se marcado, envia o build para a Steam.</p>
      <label class="check"><input type="checkbox" id="pcBuild" checked>Compilar antes de enviar</label>
      <label class="check"><input type="checkbox" id="pcUpload" onchange="pcSync()">Enviar para a Steam</label>
      <div class="field"><label>Branch</label><input type="text" id="pcBranch" placeholder="branch a liberar (ex.: beta) — vazio = só enviar" style="font-family:var(--mono)" onchange="pcBranchChanged()"></div>
      <p class="hint" style="margin:-6px 0 10px">A branch default não pode ser liberada pelo painel.</p>
      <div class="row"><button class="btn" onclick="runPc('build')">🛠️ Só compilar</button><button class="btn pri" onclick="runPc('release')">🚀 Iniciar</button><span class="hint" id="pcWarn"></span></div>
    </div>
  </div>`;
}

async function initPc(){
  if(!pcBuilt){buildPcSection();pcBuilt=true}
  try{projCache=await api('/api/projects')}catch(e){$('pcInfo').innerHTML=`<div class="empty">${esc(e.message)}</div>`;return}
  const L=projCache.filter(p=>(p.platforms||[]).includes('pc'));
  const keep=pcWanted||val('pcProject');pcWanted=null;
  $('pcProject').innerHTML=L.length?L.map(p=>`<option value="${esc(p.name)}" ${p.name===keep?'selected':''}>${esc(p.name)}</option>`).join(''):'<option value="">nenhum projeto de PC</option>';
  try{const ai=await api('/api/ai');$('pcAi').innerHTML=Object.keys(ai.providers).length?Object.keys(ai.providers).map(k=>`<option value="${esc(k)}" ${k===ai.default?'selected':''}>${esc(ai.catalog[k]?.label||k)} · ${esc(ai.providers[k].model||'')}</option>`).join(''):'<option value="">configure uma IA</option>'}
  catch(e){$('pcAi').innerHTML='<option value="">IA indisponível</option>'}
  await loadPc()}

async function loadPc(){
  const p=val('pcProject');
  if(!p){pcCur=null;$('pcInfo').innerHTML='<div class="empty">Nenhum projeto com package.json. Importe um projeto web/Capacitor em GitHub ou Projetos.</div>';return}
  $('pcInfo').innerHTML='<div class="empty">Carregando…</div>';
  try{pcCur=await api('/api/pc/info?project='+encodeURIComponent(p))}catch(e){pcCur=null;$('pcInfo').innerHTML=`<div class="empty">${esc(e.message)}</div>`;return}
  const I=pcCur,M=I.meta||{},D=I.detect||{},S=I.steam||{};
  const when=t=>t?(typeof t==='number'?new Date(t*1000):new Date(t)).toLocaleString('pt-BR'):'';
  steamAccs=I.steamAccounts||[];steamApps=I.steamApps||[];
  $('pcSteamAcc').innerHTML='<option value="">— sem envio —</option>'+steamAccs.map(a=>`<option value="${esc(a.id)}">${esc(a.label)}</option>`).join('');
  $('pcSteamAcc').value=S.accountId||steamPrincipalId()||'';
  pcFillApps();
  if(pcWantedApp){const w=pcWantedApp;pcWantedApp=null;
    if(steamAccs.some(a=>a.id===w.accountId)){$('pcSteamAcc').value=w.accountId;pcFillApps();$('pcSteamApp').value=String(w.appId)}}
  const vs=M.lastVersionName?bumpLast(M.lastVersionName):(D.version||'1.0.0');
  if($('pcVersion').dataset.p!==p){$('pcVersion').value=vs;$('pcVersion').dataset.p=p;$('pcDesc').value='';$('pcDescCnt').textContent='0/200'}
  $('pcVersion').dataset.auto=vs;
  applyVerSrc('pc',I);
  $('pcAppName').value=M.appName||D.appName||p;
  const plats=M.platforms||['win32'];
  ['win32','linux','darwin'].forEach(x=>{$('pcPlat-'+x).checked=plats.includes(x)});
  $('pcZip').checked=!!M.zip;
  $('pcPre').value=M.preBuild??D.defaultPreBuild??'';
  $('pcWebDir').value=M.webDir??'';
  $('pcElectron').value=M.electronVersion??'';
  pcProfile=null;
  $('pcType').innerHTML=(I.types||[]).map(t=>`<option value="${esc(t.id)}">${esc(t.label)}</option>`).join('');
  $('pcType').value=M.projectType||'auto';
  pcShowProfile();
  const acc=val('pcSteamAcc'),aid=val('pcSteamApp');
  const app=steamApps.find(a=>a.accountId===acc&&String(a.appId)===aid);
  $('pcBranch').value=S.branch??(app?app.branch:'')??'';
  $('pcChanges').textContent=I.changes||'(sem histórico git — escreva as observações para a IA)';
  const lr=S.lastRelease,b=M.lastBuild;
  $('pcInfo').innerHTML=`<div class="card" style="margin-bottom:16px">
    <h3 style="margin:0">${esc(I.project)} ${D.name?`<span class="hint" style="font-family:var(--mono)">${esc(D.name)}</span>`:''}</h3>
    ${I.detect?`<p style="margin:6px 0 0">Capacitor: ${D.capacitor?'sim':'não'} · pasta do site <span style="font-family:var(--mono)">${esc(D.webDir||'—')}</span> (${D.webDirExists?'existe':'não existe'}) · Electron no projeto: ${D.hasElectron?'sim':'não'}</p>`:'<p class="hint" style="margin:6px 0 0">Projeto sem package.json detectado.</p>'}
    ${I.steamcmd?'':'<p style="color:var(--warn);margin:8px 0 0">steamcmd não encontrado: reconstrua a imagem</p>'}
    <p class="hint" style="margin:8px 0 0">Última publicação na Steam: ${lr?`v${esc(lr.versionName||'?')} · ${esc(lr.branch||'default')}${when(lr.at)?' · '+esc(when(lr.at)):''}`:'nenhuma pelo painel'}</p>
    <p class="hint" style="margin:4px 0 0">Último build de PC: ${b?`v${esc(b.versionName||'?')}${when(b.at)?' · '+esc(when(b.at)):''}`:'nenhum ainda'}</p>
  </div>`;
  pcSync()}

async function savePcMeta(patch){
  if(!pcCur)return;
  pcCur.meta={...(pcCur.meta||{}),...patch};
  try{await api('/api/projects/meta',{project:pcCur.project,patch:{pc:pcCur.meta}})}catch(e){toast(e.message)}}
async function saveSteamMeta(patch){
  if(!pcCur)return;
  pcCur.steam={...(pcCur.steam||{}),...patch};
  try{await api('/api/projects/meta',{project:pcCur.project,patch:{steam:pcCur.steam}})}catch(e){toast(e.message)}}

function pcPlatChanged(){
  const plats=['win32','linux','darwin'].filter(x=>chk('pcPlat-'+x));
  savePcMeta({platforms:plats});pcSync()}
function pcAccChanged(){
  saveSteamMeta({accountId:val('pcSteamAcc')});
  pcFillApps();pcAppChanged()}
function pcAppChanged(){
  const acc=val('pcSteamAcc'),id=val('pcSteamApp');
  saveSteamMeta({appId:id});
  const app=steamApps.find(a=>a.accountId===acc&&String(a.appId)===id);
  if(app&&app.branch&&!val('pcBranch'))$('pcBranch').value=app.branch;
  pcSync()}
function pcBranchChanged(){
  saveSteamMeta({branch:val('pcBranch')});pcSync()}
/* opções de #pcSteamApp = apps da conta selecionada; prefere o appId salvo no projeto */
function pcFillApps(){
  const acc=val('pcSteamAcc');
  const L=steamApps.filter(a=>a.accountId===acc);
  $('pcSteamApp').innerHTML=L.length?L.map(a=>`<option value="${esc(a.appId)}">${esc(a.name||a.appId)} (${esc(a.appId)})</option>`).join(''):'<option value="">— nenhum app desta conta —</option>';
  const want=pcCur&&pcCur.steam?String(pcCur.steam.appId??''):'';
  if(want&&L.some(a=>String(a.appId)===want))$('pcSteamApp').value=want}
async function setPcVerSrc(v){
  if(!pcCur)return;
  try{await saveProjMeta(pcCur.project,{versionSource:v});pcCur.versionSource=v;applyVerSrc('pc',pcCur,true)}catch(e){toast(e.message)}}

function pcSync(){
  const acc=val('pcSteamAcc'),aid=val('pcSteamApp');
  const noSteam=!acc||!aid;
  $('pcUpload').disabled=noSteam;
  if(noSteam)$('pcUpload').checked=false;
  const plats=['win32','linux','darwin'].filter(x=>chk('pcPlat-'+x));
  const app=steamApps.find(a=>a.accountId===acc&&String(a.appId)===aid);
  const nm=app?(app.name||app.appId):aid;
  const br=val('pcBranch');
  $('pcWarn').textContent=!plats.length?'marque ao menos uma plataforma':chk('pcUpload')?`vai enviar para a Steam (${nm}${br?' → branch '+br:' sem liberar'})`:'só gera os arquivos de PC'}

/* ---------- tipo de código do projeto (define pré-build, pasta do site e verificações) ---------- */
/* "Detectado: <rótulo>" já escapado, ou '' se o servidor não sugeriu tipo */
function pcDetectedHtml(){
  const id=pcCur&&pcCur.detect?pcCur.detect.suggestedType:'';
  if(!id)return '';
  const t=(pcCur.types||[]).find(x=>x.id===id);
  return esc('Detectado: '+(t?t.label:id))}
/* mensagem de erro de rede/API no #pcTypeHint, junto da dica "Detectado" */
function pcHintError(m){
  const d=pcDetectedHtml();
  $('pcTypeHint').innerHTML=(d?`<div>${d}</div>`:'')+`<div style="color:var(--bad)">${esc(m)}</div>`}
/* pinta #pcTypeHint: Detectado + instrução (custom) + avisos e erros do perfil; pr null = sem perfil (custom) */
function pcRenderTypeHint(pr){
  const t=val('pcType'),det=pcDetectedHtml(),W=(pr&&pr.warnings)||[],E=(pr&&pr.errors)||[];
  pcProfile=pr?{...pr,project:pcCur.project,type:t}:null;
  let h=det?`<div>${det}</div>`:'';
  if(t==='custom')h+='<div>Digite o comando antes do build (use - para pular) e a pasta do site.</div>';
  if(W.length||E.length)h+='<ul style="margin:4px 0 0 18px">'+W.map(w=>`<li style="color:var(--warn)">${esc(w)}</li>`).join('')+E.map(e=>`<li style="color:var(--bad)">${esc(e)}</li>`).join('')+'</ul>';
  $('pcTypeHint').innerHTML=h}
/* mostra só avisos/erros do tipo atual (não altera os campos) */
async function pcShowProfile(){
  if(!pcCur)return;
  try{pcRenderTypeHint(await api('/api/pc/profile?project='+encodeURIComponent(pcCur.project)+'&type='+encodeURIComponent(val('pcType'))))}
  catch(e){pcProfile=null;pcHintError(e.message)}}
/* troca de tipo: custom só pede o comando; os outros preenchem pré-build e pasta do site pelo perfil */
async function pcTypeChanged(){
  if(!pcCur)return;
  const t=val('pcType');
  if(t==='custom'){savePcMeta({projectType:t});pcRenderTypeHint(null);return}
  let pr;
  try{pr=await api('/api/pc/profile?project='+encodeURIComponent(pcCur.project)+'&type='+encodeURIComponent(t))}
  catch(e){savePcMeta({projectType:t});pcHintError(e.message);return}
  $('pcPre').value=pr.preBuild??'';
  $('pcWebDir').value=pr.webDir??'';
  savePcMeta({projectType:t,preBuild:val('pcPre'),webDir:val('pcWebDir')});
  pcRenderTypeHint(pr)}

/* descrição curta do build (até 200 caracteres) gerada pela IA */
async function genPcDesc(){
  if(!pcCur)return;
  if(!val('pcAi'))return toast('Configure uma IA na seção IA');
  const extra=val('pcExtra');
  if(!pcCur.changes&&!extra)return toast('Sem mudanças no git: escreva observações para a IA');
  toast('Gerando com IA…');
  try{const r=await api('/api/ai/whatsnew',{provider:val('pcAi'),project:pcCur.project,appName:val('pcAppName')||pcCur.project,version:val('pcVersion'),locales:['pt-BR'],changes:pcCur.changes||extra,extra:(extra+' Máximo de 200 caracteres: é a descrição curta de um build na Steam.').trim()});
    $('pcDesc').value=String(r['pt-BR']||'').slice(0,200);$('pcDescCnt').textContent=$('pcDesc').value.length+'/200';toast('Texto gerado — revise antes de enviar')}
  catch(e){toast(e.message)}}

function runPc(mode){
  const project=val('pcProject');
  if(!project||!pcCur)return toast('Escolha um projeto de PC');
  const v=val('pcVersion');
  if(!/^\d+(\.\d+){0,3}$/.test(v))return toast('Versão inválida (ex: 1.2.0)');
  const platforms=['win32','linux','darwin'].filter(x=>chk('pcPlat-'+x));
  if(!platforms.length)return toast('Marque ao menos uma plataforma');
  const args={project,version:v,appName:val('pcAppName'),platforms,preBuild:val('pcPre'),webDir:val('pcWebDir'),electronVersion:val('pcElectron'),zip:chk('pcZip'),projectType:val('pcType')};
  /* perfil do tipo com erros e pré-build igual ao sugerido (o usuário não digitou um próprio): não dispara */
  if(pcProfile&&pcProfile.project===project&&pcProfile.type===val('pcType')&&(pcProfile.errors||[]).length&&val('pcPre')===(pcProfile.preBuild??'')){toast(pcProfile.errors[0]);return}
  if(mode==='build'){
    if(!confirm(`Compilar ${project} v${v} para ${platforms.join(', ')}?`))return;
    run('pc.build',args,'App de PC '+project+' v'+v,project);return}
  if(!chk('pcUpload'))return toast('Marque "Enviar para a Steam" para iniciar a publicação');
  const accountId=val('pcSteamAcc'),appId=val('pcSteamApp');
  if(!accountId||!appId)return toast('Escolha a conta e o app da Steam em Contas → Steam');
  const branch=val('pcBranch');
  if(branch.toLowerCase()==='default')return toast('A branch default não pode ser liberada pelo painel');
  const app=steamApps.find(a=>a.accountId===accountId&&String(a.appId)===appId);
  const nm=app?(app.name||app.appId):appId;
  if(!confirm(`Enviar ${project} v${v} para a Steam?\n\nPlataformas: ${platforms.join(', ')}\nApp: ${nm} (${appId})\nBranch: ${branch||'nenhuma (só envia, não libera)'}`))return;
  run('steam.release',{...args,accountId,appId,branch,description:val('pcDesc'),build:chk('pcBuild'),upload:true},'Steam '+project+' v'+v,project)}

/* build rápido direto da lista de Projetos */
function quickPc(project){
  const p=projCache.find(x=>x.name===project)||{meta:{}};const m=(p.meta||{}).pc||{};
  run('pc.build',{project,version:'',appName:m.appName||'',platforms:m.platforms&&m.platforms.length?m.platforms:['win32'],preBuild:m.preBuild??'',webDir:m.webDir??'',electronVersion:m.electronVersion??'',zip:true,projectType:m.projectType||''},'Gerar app de PC '+project,project)}
/* botão "Publicar" de um projeto: abre a aba PC/Steam já com o projeto escolhido */
function openPcPublish(project){pcWanted=project;go('pc')}
/* botão "Publicar" de um app da conta Steam: abre a aba PC/Steam com a conta e o app escolhidos */
function openPcPublishApp(accountId,appId){pcWantedApp={accountId,appId};go('pc')}

/* ---------- contas Steam e apps ---------- */
/* pill de conexão de uma conta Steam (estado de steamStat) */
function steamPill(st){
  const s=st&&st.state, m=esc((st&&st.message)||'');
  if(!s||s==='checking')return '<span class="pill off"><i></i>Verificando…</span>';
  if(s==='ok')return `<span class="pill ok" title="${m}"><i></i>Conectada</span>`;
  if(s==='nologin')return `<span class="pill warn" title="${m}"><i></i>Sem login</span>`;
  if(s==='busy')return `<span class="pill off" title="${m}"><i></i>Ocupado…</span>`;
  return `<span class="pill off" title="${m}"><i></i>Não verificado</span>`}
/* span com id que envolve a pill (é trocado inteiro por steamRepaint) */
function steamPillWrap(id){return `<span id="steamPill-${esc(id)}">${steamPill(steamStat[id])}</span>`}
/* célula "Conexão" do kv do card: rótulo + mensagem curta do último check ('—' se não há) */
function steamConnCells(id){
  const st=steamStat[id];
  return `<span>Conexão</span><span id="steamConnV-${esc(id)}">${esc((st&&st.message)||'—')}</span>`}
/* botão Login: primário só quando não está conectada */
function steamLoginCls(id){const st=steamStat[id];return 'btn sm'+(st&&st.state==='ok'?'':' pri')}
/* repinta só a pill, a linha Conexão e o botão Login de uma conta (sem recarregar a grade) */
function steamRepaint(id){
  const p=$('steamPill-'+id);if(p)p.outerHTML=steamPillWrap(id);
  const c=$('steamConnV-'+id);if(c)c.textContent=(steamStat[id]&&steamStat[id].message)||'—';
  const b=$('steamLogin-'+id);if(b)b.className=steamLoginCls(id)}
/* consulta o login de uma conta (steamcmd, ~10 s): uma por vez; watch = chamada do watcher pós-Login */
async function steamCheck(id,force,watch){
  if(steamChecking){if(force&&!watch)toast('Já estou verificando outra conta');return null}
  const prev=steamStat[id];
  steamChecking=true;
  steamStat[id]={state:'checking'};
  steamRepaint(id);
  let r;
  try{r=await api('/api/steam/check?id='+encodeURIComponent(id)+(force?'&force=1':''))}
  catch(e){r={state:'error',message:e.message}}
  steamChecking=false;
  steamStat[id]=r;
  steamRepaint(id);
  loadTopbar();
  if(watch&&r.state==='ok'&&(!prev||prev.state!=='ok')){const a=steamAccs.find(x=>x.id===id);toast('Steam conectada: '+(a?a.label:id))}
  return r}
/* verifica todas as contas em sequência; pula as que têm resultado ok/nologin dos últimos 30 s */
async function steamCheckAll(){
  for(const a of steamAccs.slice()){
    const st=steamStat[a.id];
    if(st&&(st.state==='ok'||st.state==='nologin')&&st.checked*1000>Date.now()-30000)continue;
    await steamCheck(a.id,false)}}
/* depois do Login: verifica a cada 8 s por até 5 min, até a conta ficar conectada */
function steamWatchLogin(id){
  clearTimeout(steamWatchTimer);
  const t0=Date.now();
  const tick=async()=>{
    if(Date.now()-t0>300000)return;
    if($('s-steam')&&$('s-steam').classList.contains('on')&&!steamChecking){
      const r=await steamCheck(id,true,true);
      if(r&&r.state==='ok')return}
    steamWatchTimer=setTimeout(tick,8000)};
  steamWatchTimer=setTimeout(tick,8000)}

function buildSteamSection(){
  $('s-steam').innerHTML=`
  <div class="segtabs"><button data-t="accounts" onclick="go('accounts')">🍎 Apple</button><button data-t="play" onclick="go('play')"><span style="color:#34a853">▶</span> Google Play</button><button data-t="steam" onclick="go('steam')">🎮 Steam</button></div>
  <p class="hint" style="margin-top:0">Cadastre o usuário de build do Steamworks (conta com permissão de publicar builds). A senha não é gravada: clique em Login para digitar a senha e o código do Steam Guard no console; o steamcmd guarda o login. Crie em <a href="https://partner.steamgames.com" target="_blank">partner.steamgames.com</a>.</p>
  <div id="steamStatus"></div>
  <h2>Contas</h2>
  <div class="grid" id="steamAccGrid"></div>
  <h2>Adicionar conta</h2>
  <div class="card add" style="max-width:520px">
    <h3>＋ Nova conta Steam</h3><p>Usuário de build do Steamworks.</p>
    <div class="field"><label>Nome para identificar</label><input type="text" id="steamLabel" placeholder="ex: Pessoal, Cliente X"></div>
    <div class="field"><label>Usuário da Steam</label><input type="text" id="steamUser" placeholder="usuario_de_build" style="font-family:var(--mono)"></div>
    <button class="btn pri" onclick="addSteamAcc()">Adicionar</button>
  </div>`;
  document.querySelectorAll('#s-steam .segtabs button').forEach(b=>b.classList.toggle('on',b.dataset.t==='steam'));
}

async function loadSteam(){
  if(!steamBuilt){buildSteamSection();steamBuilt=true}
  let accs,st;
  try{[accs,st]=await Promise.all([api('/api/steam/accounts'),api('/api/steam/status')])}
  catch(e){$('steamAccGrid').innerHTML=`<div class="empty">${esc(e.message)}</div>`;return}
  steamAccs=accs;
  $('steamStatus').innerHTML=st.steamcmd?`<p class="hint" style="margin:0 0 12px">✔ steamcmd instalado em ${esc(st.path||'')}</p>`:'<p class="hint" style="margin:0 0 12px;color:var(--warn)">steamcmd não encontrado: reconstrua a imagem</p>';
  const dAcc=steamPrincipalId();
  $('steamAccGrid').innerHTML=steamAccs.length?steamAccs.map(a=>`<div class="card acc">
    <div class="avatar" style="background:${colorOf(String(a.id))}">${esc((a.label||'?')[0].toUpperCase())}</div>
    <h3>${esc(a.label)}</h3>
    <div class="kv"><span>Usuário</span><span style="font-family:var(--mono)">${esc(a.username||'—')}</span><span>Adicionada</span><span>${a.added?new Date(a.added*1000).toLocaleDateString('pt-BR'):'—'}</span>${steamConnCells(a.id)}</div>
    <div class="row">
      ${a.id===dAcc?'<span class="pill ok"><i></i>principal</span>':`<button class="btn sm" onclick="setSteamPrincipal('${esc(a.id)}')">★ Principal</button>`}
      ${steamPillWrap(a.id)}
      <button id="steamLogin-${esc(a.id)}" class="${steamLoginCls(a.id)}" onclick="loginSteamAcc('${esc(a.id)}')">🔑 Login</button>
      <button class="btn sm" onclick="steamCheck('${esc(a.id)}',true)">↻ Verificar</button>
      <button class="btn sm" onclick="renameSteamAcc('${esc(a.id)}')">Renomear</button>
      <button class="btn sm danger" onclick="removeSteamAcc('${esc(a.id)}')">Remover</button></div></div>`).join(''):'<div class="empty">Nenhuma conta Steam. Adicione uma abaixo.</div>';steamCheckAll()}

async function addSteamAcc(){
  const username=val('steamUser');
  if(!username)return toast('Informe o usuário da Steam');
  const label=val('steamLabel')||username;
  try{steamAccs=await api('/api/steam/accounts/add',{label,username});$('steamLabel').value='';$('steamUser').value='';toast('Conta Steam adicionada');loadSteam()}
  catch(e){toast(e.message)}}
async function renameSteamAcc(id){
  const a=steamAccs.find(x=>x.id===id);const n=prompt('Novo nome da conta:',a?a.label:'');if(!n||!n.trim())return;
  try{steamAccs=await api('/api/steam/accounts/rename',{id,label:n.trim()});loadSteam()}catch(e){toast(e.message)}}
async function removeSteamAcc(id){
  const a=steamAccs.find(x=>x.id===id);
  if(!confirm(`Remover a conta "${a?a.label:id}" do painel? Os apps dela saem da lista (nada é apagado na Steam).`))return;
  try{steamAccs=await api('/api/steam/accounts/remove',{id});delete steamStat[id];loadSteam();loadTopbar()}catch(e){toast(e.message)}}
/* conta Steam principal (topo): grava no servidor e repinta a lista de contas */
function setSteamPrincipal(id){topSet('steamAccountId',id).then(loadSteam).catch(e=>toast(e.message))}
function loginSteamAcc(id){
  const a=steamAccs.find(x=>x.id===id);if(!a)return;
  run('steam.login',{username:a.username},'Login Steam '+a.label);
  steamWatchLogin(id)}
/* ---------- Apps da conta Steam: mesmo layout dos apps do Google Play ---------- */
function buildSteamAppsSection(){
  $('s-steamapps').innerHTML=`
  <div class="segtabs"><button data-t="apps" onclick="go('apps')">🍎 Apple</button><button data-t="playapps" onclick="go('playapps')"><span style="color:#34a853">▶</span> Google Play</button><button data-t="steamapps" onclick="go('steamapps')">🎮 Steam</button></div>
  <div class="row" style="margin-bottom:8px">
    <select id="steamAppAcc" style="max-width:320px" onchange="renderSteamAccApps()"></select>
    <button class="btn" onclick="initSteamApps()">Atualizar</button>
    <span class="hint" id="steamAppsHint"></span>
  </div>
  <p class="hint" style="margin:0 0 14px">O Steamworks não tem API pública para listar os apps: cadastre o App ID e os Depot IDs de cada app (Steamworks → App Admin → SteamPipe → Depots).</p>
  <div class="card add" style="margin-bottom:22px">
    <h3>＋ Adicionar app</h3>
    <div class="row">
      <input type="text" id="steamAppId" placeholder="App ID" style="max-width:160px;font-family:var(--mono)">
      <input type="text" id="steamAppName" placeholder="Nome do app" style="flex:1">
    </div>
    <p class="hint" style="margin:10px 0 6px">Depot IDs por plataforma (deixe vazio o que não usar)</p>
    <div class="row">
      <input type="text" id="steamDepotWin" placeholder="Depot Windows" style="font-family:var(--mono)">
      <input type="text" id="steamDepotLinux" placeholder="Depot Linux" style="font-family:var(--mono)">
      <input type="text" id="steamDepotMac" placeholder="Depot macOS" style="font-family:var(--mono)">
    </div>
    <div class="row" style="margin-top:10px">
      <input type="text" id="steamAppBranch" placeholder="branch padrão (opcional)" style="flex:1;font-family:var(--mono)">
      <button class="btn pri" onclick="saveSteamApp()">Salvar app</button>
    </div>
  </div>
  <h2>Apps registrados</h2>
  <div class="regtbl" id="steamAppList" style="margin-bottom:22px"></div>
  <h2>Apps na conta <span class="hint" id="steamAccName" style="text-transform:none;letter-spacing:0;font-weight:400"></span></h2>
  <div class="grid" id="steamAccApps"></div>`;
}

/* abre "Apps da conta → 🎮 Steam": preenche contas, apps e status; seleciona a conta principal (ou a que já estava selecionada) */
async function initSteamApps(){
  const first=!steamAppsBuilt;
  if(first){buildSteamAppsSection();steamAppsBuilt=true}
  const prev=first?'':val('steamAppAcc');
  let accs,apps,st;
  try{[accs,apps,st]=await Promise.all([api('/api/steam/accounts'),api('/api/steam/apps'),api('/api/steam/status')])}
  catch(e){$('steamAppsHint').textContent='✖ '+e.message;$('steamAccApps').innerHTML=`<div class="empty">${esc(e.message)}</div>`;return}
  steamAccs=accs;steamApps=apps;
  const dAcc=steamPrincipalId();
  const pick=[prev,dAcc].find(id=>id&&steamAccs.some(a=>a.id===id))||(steamAccs[0]?steamAccs[0].id:'');
  $('steamAppAcc').innerHTML=steamAccs.length?steamAccs.map(a=>`<option value="${esc(a.id)}">${esc(a.label)}${a.id===dAcc?' ★ principal':''}</option>`).join(''):'<option value="">cadastre uma conta em Contas → Steam</option>';
  $('steamAppAcc').value=pick;
  const nApps=steamApps.length,nAcc=new Set(steamApps.map(a=>a.accountId)).size;
  $('steamAppsHint').textContent=(nApps?`· ${nApps} app(s) em ${nAcc} conta(s)`:'')+(st.steamcmd?'':' · steamcmd não encontrado');
  $('steamAppList').innerHTML=steamApps.length?steamApps.map((a,i)=>{const dep=a.depots||{};const acc=steamAccs.find(x=>x.id===a.accountId);
    const deps=['win32','linux','darwin'].filter(p=>dep[p]).map(p=>`${p} ${esc(dep[p])}`).join(' · ')||'sem depots';
    return `<div class="reg">
      <div style="min-width:0;flex:1"><div style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(a.name||a.appId)}</div>
        <div style="font-family:var(--mono);font-size:12px;color:var(--muted)">${esc(a.appId)} · ${deps}${a.branch?' · branch '+esc(a.branch):''}</div></div>
      <span class="hint">${esc(a.accountLabel||(acc?acc.label:'conta removida'))}</span>
      <button class="btn sm" onclick="editSteamApp(${i})">Editar</button>
      <button class="btn sm danger" onclick="forgetSteamApp(${i})">Esquecer</button></div>`}).join(''):'<div class="empty">Nenhum app registrado ainda. Escolha a conta, informe o App ID e os depots, depois clique em "Salvar app".</div>';
  renderSteamAccApps()}

/* redesenha "Apps na conta" pela conta selecionada em #steamAppAcc */
function renderSteamAccApps(){
  const acc=val('steamAppAcc'),A=steamAccs.find(x=>x.id===acc);
  $('steamAccName').textContent=A?'· '+A.label:'';
  const L=steamApps.map((a,i)=>[a,i]).filter(([a])=>a.accountId===acc);
  $('steamAccApps').innerHTML=!acc?'<div class="empty">Cadastre uma conta em Contas → Steam.</div>':L.length?L.map(([a,i])=>{const dep=a.depots||{};
    const deps=[['win32','Windows'],['linux','Linux'],['darwin','macOS']].map(([p,n])=>`<span>${n} ${dep[p]?'✔ <span style="font-family:var(--mono)">'+esc(dep[p])+'</span>':'—'}</span>`).join(' · ');
    return `<div class="card">
      <h3 style="margin:0">${esc(a.name||a.appId)}</h3>
      <div style="font-family:var(--mono);font-size:12px;color:var(--muted);margin:4px 0 10px">${esc(a.appId)}</div>
      <div class="hint" style="margin-bottom:6px">Depots: ${deps}</div>
      <div class="hint" style="margin-bottom:12px">Branch: ${a.branch?esc(a.branch):'default'}</div>
      <div class="row"><button class="btn sm pri" onclick="openPcPublishApp('${esc(a.accountId)}','${esc(String(a.appId))}')">Publicar</button><button class="btn sm" onclick="editSteamApp(${i})">Editar</button><button class="btn sm danger" onclick="forgetSteamApp(${i})">Esquecer</button></div></div>`}).join('')
    :'<div class="empty">Nenhum app desta conta na lista. Adicione pelo App ID acima.</div>'}

async function saveSteamApp(){
  const accountId=val('steamAppAcc'),appId=val('steamAppId');
  if(!accountId)return toast('Cadastre uma conta Steam primeiro');
  if(!appId)return toast('Informe o App ID');
  const depots={};
  [['win32','steamDepotWin'],['linux','steamDepotLinux'],['darwin','steamDepotMac']].forEach(([p,i])=>{const d=val(i);if(d)depots[p]=d});
  try{steamApps=await api('/api/steam/apps/set',{accountId,appId,name:val('steamAppName'),depots,branch:val('steamAppBranch')});
    ['steamAppId','steamAppName','steamDepotWin','steamDepotLinux','steamDepotMac','steamAppBranch'].forEach(i=>{$(i).value=''});
    toast('App Steam salvo');initSteamApps()}
  catch(e){toast(e.message)}}
function editSteamApp(i){
  const a=steamApps[i];if(!a)return;const dep=a.depots||{};
  $('steamAppAcc').value=a.accountId||'';$('steamAppId').value=a.appId||'';$('steamAppName').value=a.name||'';
  $('steamDepotWin').value=dep.win32||'';$('steamDepotLinux').value=dep.linux||'';$('steamDepotMac').value=dep.darwin||'';
  $('steamAppBranch').value=a.branch||''}
async function forgetSteamApp(i){
  const a=steamApps[i];if(!a)return;
  if(!confirm(`Tirar "${a.name||a.appId}" da lista? (Não apaga nada na Steam.)`))return;
  try{steamApps=await api('/api/steam/apps/forget',{accountId:a.accountId,appId:a.appId});initSteamApps()}catch(e){toast(e.message)}}
