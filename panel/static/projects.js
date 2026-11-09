/* ---------- Projetos: Configurar / Build por plataforma (iOS, Android, PC/Steam) ----------
   script clássico carregado depois de pc.js. Exporta os helpers pm* usados também pelo deliver.js.
   usa os globais do index.html: $, val, chk, esc, toast, api, run, fmtB, bumpLast, loadProjects, pickApp
   e das funções de vínculo: pickPlayApp, pickSteamApp (projlinks.js) */

(function pmInitStyle(){
  if(document.getElementById('pmStyle'))return;
  const s=document.createElement('style');s.id='pmStyle';
  s.textContent=`
.pm-back{position:fixed;inset:0;background:rgba(3,5,10,.72);backdrop-filter:blur(6px);z-index:30;display:flex;align-items:center;justify-content:center;padding:20px}
.pm-box{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);width:100%;max-width:780px;max-height:calc(100vh - 40px);display:flex;flex-direction:column;box-shadow:0 20px 50px rgba(0,0,0,.5)}
.pm-box [hidden]{display:none!important}
.pm-head{display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid var(--line)}
.pm-head h3{margin:0;flex:1;font-size:17px}
.pm-x{background:none;border:0;color:var(--muted);font-size:18px;cursor:pointer;padding:2px 6px;border-radius:8px}
.pm-x:hover{color:var(--text)}
.pm-body{padding:16px 18px;overflow:auto;flex:1;min-height:0}
.pm-foot{display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap;padding:12px 18px;border-top:1px solid var(--line)}
.pm-sec{margin-bottom:14px}
.pm-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.pm-card{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:10px}
.pm-card b{font-size:14px}
.pm-sw{display:block;cursor:pointer;margin-bottom:0}
.pm-sw input[type=checkbox]{width:18px;height:18px;margin:0 8px 0 0;vertical-align:middle}
.pm-reason{color:var(--warn);font-size:13px;margin-top:6px}
.pm-err{color:var(--bad);font-size:13px}
.pm-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
.pm-box .field{margin-bottom:8px}
`;
  document.head.appendChild(s)})();

/* ---------- helpers compartilhados (exportados) ---------- */
let pmCur=null; /* modal aberto: {el,onKey}; só um por vez */
function pmClose(){
  if(!pmCur)return;
  document.removeEventListener('keydown',pmCur.onKey);
  pmCur.el.remove();pmCur=null}
/* title é texto puro (escapado aqui); html é o conteúdo; buttons = [{label,cls:'pri'|'danger'|'',id,onClick}] */
function pmModal(title,html,buttons){
  pmClose();
  const el=document.createElement('div');el.className='pm-back';
  el.innerHTML=`<div class="pm-box" role="dialog" aria-modal="true"><div class="pm-head"><h3>${esc(title)}</h3><button class="pm-x" title="Fechar">✕</button></div><div class="pm-body"></div><div class="pm-foot"></div></div>`;
  const body=el.querySelector('.pm-body'), foot=el.querySelector('.pm-foot');
  body.innerHTML=html;
  const cur={el,onKey:null};
  const close=()=>{if(pmCur===cur)pmClose()};
  cur.onKey=e=>{if(e.key==='Escape')close()};
  el.addEventListener('click',e=>{if(e.target===el)close()});
  el.querySelector('.pm-x').onclick=close;
  (buttons||[]).forEach(b=>{
    const x=document.createElement('button');x.className='btn'+(b.cls?' '+b.cls:'');x.textContent=b.label;
    if(b.id)x.id=b.id;
    x.onclick=ev=>{if(b.onClick)b.onClick(ev)};
    foot.appendChild(x)});
  if(!buttons||!buttons.length)foot.remove();
  document.addEventListener('keydown',cur.onKey);
  document.body.appendChild(el);
  pmCur=cur;
  return {el,body,close}}
async function pmOverview(project){
  return api('/api/project/overview?project='+encodeURIComponent(project))}
async function pmSaveSettings(project,platform,patch){
  return api('/api/project/settings',{project,platform,patch})}
const pmFmtDate=ts=>ts?new Date(ts*1000).toLocaleString('pt-BR'):'—';
const pmSize=n=>n?fmtB(n):'—';
/* <option> da origem da versão: automática, manual e as fontes do projeto */
function pmVersionOptions(ov){
  const v=ov.version||{};
  const src=v.source||'auto';
  const opts=[['auto','Automática (próxima depois da última)'],['manual','Manual']]
    .concat((v.sources||[]).map(s=>[s.id,`${s.label} — ${s.value}`]));
  return opts.map(([id,l])=>`<option value="${esc(id)}" ${id===src?'selected':''}>${esc(l)}</option>`).join('')}
/* versão para um build: fonte com id -> valor dela; manual -> ''; auto (ou desconhecida) -> próxima depois da última da plataforma */
function pmResolveVersion(ov,source,platform){
  const v=ov.version||{};
  const s=(v.sources||[]).find(x=>x.id===source);
  if(s)return String(s.value||'');
  if(source==='manual')return '';
  const last=(v.last||{})[platform]||'';
  return last?bumpLast(last):'1.0.0'}
/* modal pequeno "Versão do projeto": origem + salvar; onDone roda depois de salvar */
async function pmVersionConfigBody(project,onDone){
  let ov;try{ov=await pmOverview(project)}catch(e){return toast(e.message)}
  pmModal('Versão do projeto',`
    <p class="hint" style="margin:0 0 12px">De onde vem a versão dos builds de <b>${esc(project)}</b>:</p>
    <div class="field"><label>Origem</label><select id="pvSrc">${pmVersionOptions(ov)}</select></div>
    <p class="hint">Automática = a próxima depois da última versão enviada. Package.json ou outra fonte = o painel lê o arquivo a cada build. Manual = você digita a versão a cada build.</p>`,
    [{label:'Cancelar',cls:'',onClick:()=>pmClose()},
     {label:'Salvar',cls:'pri',id:'pvSave',onClick:async()=>{
       try{await pmSaveSettings(project,'version',{versionSource:val('pvSrc')});toast('Versão do projeto salva');pmClose();if(onDone)onDone()}
       catch(e){toast(e.message)}}}]);
}

/* ---------- Configurar (diálogo completo do projeto) ---------- */
const pmJs=s=>JSON.stringify(String(s)).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
/* botão "Adicionar Android": fecha o diálogo e roda o init do Capacitor */
function projAddAndroid(project){pmClose();run('init.android',{},'Adicionar Android '+project,project)}
/* pill de estado: desativada / pronta / falta configurar */
const pmState=p=>!p.enabled?'<span class="pill off"><i></i>Desativado</span>':p.configured?'<span class="pill ok"><i></i>Pronto</span>':'<span class="pill warn"><i></i>Falta configurar</span>';
const pmLabelOf=(list,id)=>{const x=(list||[]).find(a=>a.id===id);return x?x.label:''};
/* Salvar do diálogo: valida e grava em sequência (targets, ios bundle, android, pc, steam) */
async function projSaveConfig(project){
  const iosOn=chk('pcfIos'), andOn=chk('pcfAnd'), pcOn=chk('pcfPc');
  const OS=[['win32','pcfWin32'],['linux','pcfLinux'],['darwin','pcfDarwin']];
  const pcPl=OS.filter(([,id])=>chk(id)).map(([p])=>p);
  const pkg=val('pcfPkg'), br=val('pcfBranch');
  if(pcOn&&!pcPl.length)return toast('Marque ao menos um sistema operacional do PC');
  if(andOn&&pkg&&!/^[A-Za-z][\w]*(\.[A-Za-z][\w]*)+$/.test(pkg))return toast('Package name inválido (ex: com.empresa.app)');
  if(pcOn&&br.toLowerCase()==='default')return toast('A branch default não pode ser liberada pelo painel');
  try{
    await pmSaveSettings(project,'targets',{ios:iosOn,android:andOn,pc:pcOn});
    if(iosOn)await pmSaveSettings(project,'ios',{bundleId:val('pcfBundle')});
    if(andOn)await pmSaveSettings(project,'android',{packageName:pkg,preBuild:val('pcfAndPre')});
    if(pcOn){
      await pmSaveSettings(project,'pc',{platforms:pcPl,projectType:val('pcfType'),appName:val('pcfAppName'),preBuild:val('pcfPcPre'),webDir:val('pcfWebDir'),electronVersion:val('pcfElectron'),zip:chk('pcfZip')});
      await pmSaveSettings(project,'steam',{branch:br})}
    toast('Configuração salva');
    await projConfigure(project);
    loadProjects().catch(()=>{});
  }catch(e){toast(e.message)}}
async function projConfigureBody(project){
  let ov;try{ov=await pmOverview(project)}catch(e){return toast(e.message)}
  const P=ov.platforms||{}, S=ov.settings||{}, A=ov.accounts||{};
  const si=S.ios||{}, sa=S.android||{}, sp=S.pc||{};
  const pI=P.ios||{}, pA=P.android||{}, pC=P.pc||{};
  /* reason existe sempre que não está pronta (mesmo desativada); fica escondida até o interruptor ser marcado */
  const reason=(id,p)=>(!p.configured&&p.reason)?`<div class="pm-reason" id="${id}Why" ${p.enabled?'':'hidden'}>${esc(p.reason)}</div>`:'';
  const detail=p=>p.detail?`<div class="hint" style="margin-top:4px">${esc(p.detail)}</div>`:'';
  const sw=(id,label,p)=>`<label class="pm-card pm-sw"><div class="pm-row" style="margin-bottom:0"><input type="checkbox" id="${id}" ${p.enabled?'checked':''}><b>${label}</b>${pmState(p)}</div>${detail(p)}${reason(id,p)}</label>`;
  const types=pC.types||[];
  const curType=sp.projectType||pC.projectType||'';
  const osOn=sp.platforms||[];
  const appRow=(sp.steamAccountId&&sp.steamAppId)?(ov.steamApps||[]).find(a=>a.accountId===sp.steamAccountId&&String(a.appId)===String(sp.steamAppId)):null;
  const steamTxt=appRow?`${appRow.name||appRow.appId} (${appRow.appId}) · conta ${pmLabelOf(A.steam,sp.steamAccountId)||appRow.accountLabel||''}`:'nenhum app vinculado';
  const src=(ov.version||{}).source||'auto';
  const vs=((ov.version||{}).sources||[]).find(s=>s.id===src);
  const vlabel=vs?vs.label:(src==='manual'?'Manual':'Automática (próxima depois da última)');
  const h=`
  <div class="pm-sec">
    <h4 style="margin:0 0 8px">Plataformas deste projeto</h4>
    <div class="pm-grid">
      ${sw('pcfIos','🍎 iPhone (iOS)',pI)}
      ${sw('pcfAnd','🤖 Android',pA)}
      ${sw('pcfPc','🖥️ Steam (PC)',pC)}
    </div>
  </div>
  <div class="pm-card" id="pcfIosBox" hidden><b>🍎 iPhone (iOS)</b>
    <div class="field" style="margin-top:8px"><label>Bundle ID</label><input type="text" id="pcfBundle" value="${esc(si.bundleId||'')}" style="font-family:var(--mono)"></div>
    <div class="pm-row"><span class="hint">Conta Apple: <b>${esc(pmLabelOf(A.apple,si.accountId)||'—')}</b></span><button class="btn sm" id="pcfPickIos">Vincular / trocar app da Apple</button></div>
  </div>
  <div class="pm-card" id="pcfAndBox" hidden><b>🤖 Android</b>
    <div class="field" style="margin-top:8px"><label>Package name</label><input type="text" id="pcfPkg" value="${esc(sa.packageName||pA.packageName||'')}" placeholder="com.exemplo.app" style="font-family:var(--mono)"></div>
    <div class="field"><label>Comando antes do Gradle</label><input type="text" id="pcfAndPre" value="${esc(sa.preBuild||'')}" style="font-family:var(--mono)"></div>
    <p class="hint" style="margin:-4px 0 8px">vazio = padrão detectado, - = pular</p>
    <div class="pm-row"><span class="hint">Conta Google Play: <b>${esc(pmLabelOf(A.play,sa.playAccountId)||'—')}</b></span><button class="btn sm" id="pcfPickAnd">Vincular / trocar app do Google Play</button>${pA.canInit?'<button class="btn sm pri" id="pcfAddAnd">Adicionar Android (npx cap add android)</button>':''}</div>
  </div>
  <div class="pm-card" id="pcfPcBox" hidden><b>🖥️ Steam (PC)</b>
    <div class="pm-row" style="margin-top:8px"><span class="hint">Sistemas operacionais:</span>
      <label class="check" style="margin:0"><input type="checkbox" id="pcfWin32" ${osOn.includes('win32')?'checked':''}>Windows</label>
      <label class="check" style="margin:0"><input type="checkbox" id="pcfLinux" ${osOn.includes('linux')?'checked':''}>Linux</label>
      <label class="check" style="margin:0"><input type="checkbox" id="pcfDarwin" ${osOn.includes('darwin')?'checked':''}>macOS</label></div>
    <div class="pm-grid">
      <div class="field"><label>Tipo de código</label><select id="pcfType">${types.length?types.map(t=>`<option value="${esc(t.id)}" ${t.id===curType?'selected':''}>${esc(t.label)}</option>`).join(''):'<option value="">—</option>'}</select></div>
      <div class="field"><label>Nome do app</label><input type="text" id="pcfAppName" value="${esc(sp.appName||'')}" placeholder="${esc(project)}"></div>
      <div class="field"><label>Comando antes do build</label><input type="text" id="pcfPcPre" value="${esc(sp.preBuild??'')}" style="font-family:var(--mono)"></div>
      <div class="field"><label>Pasta do site</label><input type="text" id="pcfWebDir" value="${esc(sp.webDir??'')}" style="font-family:var(--mono)"></div>
      <div class="field"><label>Versão do Electron</label><input type="text" id="pcfElectron" value="${esc(sp.electronVersion??'')}" style="font-family:var(--mono)"></div>
    </div>
    <p class="hint" style="margin:-4px 0 8px">vazio = padrão detectado, - = pular (comando e pasta)</p>
    <label class="check"><input type="checkbox" id="pcfZip" ${sp.zip?'checked':''}>gerar .zip</label>
    <div class="pm-row"><span class="hint">App da Steam: <b>${esc(steamTxt)}</b></span><button class="btn sm" id="pcfPickSteam">Vincular / trocar app da Steam</button></div>
    <div class="field"><label>Branch</label><input type="text" id="pcfBranch" value="${esc(sp.branch||'')}" placeholder="vazio = só envia" style="font-family:var(--mono)"></div>
  </div>
  <div class="pm-sec"><div class="hint">Versão do projeto: <b>${esc(vlabel)}</b></div><button class="btn sm" id="cfgVer" style="margin-top:6px">Configurar versão…</button></div>`;
  pmModal('⚙ Configurar '+project,h,[{label:'Fechar',cls:'',onClick:()=>pmClose()},{label:'Salvar',cls:'pri',id:'pcfSaveAll',onClick:()=>projSaveConfig(project)}]);
  /* painéis de cada plataforma aparecem só quando ativada */
  /* painéis e reason seguem o interruptor, sem salvar nada */
  const refresh=()=>{
    $('pcfIosBox').hidden=!chk('pcfIos');$('pcfAndBox').hidden=!chk('pcfAnd');$('pcfPcBox').hidden=!chk('pcfPc');
    ['pcfIos','pcfAnd','pcfPc'].forEach(id=>{const w=$(id+'Why');if(w)w.hidden=!chk(id)})};
  ['pcfIos','pcfAnd','pcfPc'].forEach(id=>{$(id).onchange=refresh});
  refresh();
  /* vínculos: fecha este diálogo e abre o da função de vínculo (ao terminar, o usuário reabre Configurar) */
  $('pcfPickIos').onclick=()=>{pmClose();pickApp(project)};
  $('pcfPickAnd').onclick=()=>{pmClose();pickPlayApp(project)};
  $('pcfPickSteam').onclick=()=>{pmClose();pickSteamApp(project)};
  const aa=$('pcfAddAnd');if(aa)aa.onclick=()=>projAddAndroid(project);
  $('cfgVer').onclick=()=>pmVersionConfig(project,()=>projConfigure(project));
}

/* spinner global (uiLoading, do index.html): some quando o diálogo já está montado; no-op se ainda não existir */
const pmBusy=msg=>(typeof uiLoading==='function')?uiLoading(msg):(()=>{});
async function pmVersionConfig(project,onDone){const done=pmBusy('Carregando…');try{await pmVersionConfigBody(project,onDone)}finally{done()}}
async function projConfigure(project){const done=pmBusy('Abrindo configurações…');try{await projConfigureBody(project)}finally{done()}}
async function projBuild(project){const done=pmBusy('Preparando o build…');try{await projBuildBody(project)}finally{done()}}

/* ---------- Build ---------- */
async function projBuildBody(project){
  let ov;try{ov=await pmOverview(project)}catch(e){return toast(e.message)}
  const P=ov.platforms||{}, S=ov.settings||{}, A=ov.accounts||{};
  const si=S.ios||{}, sa=S.android||{}, sp=S.pc||{};
  /* pronta = ativada no projeto e configurada; plataformas desativadas nem aparecem */
  const en=k=>!!((P[k]||{}).enabled);
  const isReady=k=>en(k)&&!!((P[k]||{}).configured);
  const ok={ios:isReady('ios'),android:isReady('android'),pc:isReady('pc')};
  if(!ok.ios&&!ok.android&&!ok.pc){
    pmModal('🔨 Build '+project,'<div class="empty">Nenhuma plataforma configurada e ativada ainda. Configure um destino antes de compilar.</div>',
      [{label:'Fechar',cls:'',onClick:()=>pmClose()},{label:'Abrir Configurar',cls:'pri',id:'pbGoCfg',onClick:()=>projConfigure(project)}]);
    return}
  /* leitura segura: linhas de plataformas desativadas não existem no DOM */
  const chk=id=>{const e=document.getElementById(id);return !!(e&&e.checked)};
  const val=id=>{const e=document.getElementById(id);return e?e.value.trim():''};
  const PBC={ios:'pbIos',android:'pbAnd',pc:'pbPc'};
  const PCT=[['win32','pbPcWin32','Windows'],['linux','pbPcLinux','Linux'],['darwin','pbPcDarwin','macOS']];
  const why=p=>ok[p]?'':`<div class="hint" style="margin:-2px 0 8px 26px" title="${esc((P[p]||{}).reason||'')}">${esc((P[p]||{}).reason||'Não configurado')}</div>`;
  const dis=p=>ok[p]?'checked':'disabled';
  const pcPre=sp.platforms||[];
  const types=(P.pc&&P.pc.types)||[];
  const typeLabel=(types.find(t=>t.id===((P.pc||{}).projectType))||{}).label||(P.pc||{}).projectType||'—';
  const appleOpts=(A.apple||[]).map(a=>`<option value="${esc(a.id)}" ${a.id===si.accountId?'selected':''}>${esc(a.label)}${a.hasApi?'':' — sem API da Apple'}</option>`).join('')||'<option value="">cadastre uma conta Apple</option>';
  const playOpts=(A.play||[]).map(a=>`<option value="${esc(a.id)}" ${a.id===sa.playAccountId?'selected':''}>${esc(a.label)}</option>`).join('')||'<option value="">cadastre uma conta Google Play</option>';
  const steamOpts=(A.steam||[]).map(a=>`<option value="${esc(a.id)}" ${a.id===sp.steamAccountId?'selected':''}>${esc(a.label)}</option>`).join('')||'<option value="">cadastre uma conta Steam</option>';
  const track=['internal','alpha','beta','production'].map(t=>`<option value="${t}" ${t===(sa.track||'internal')?'selected':''}>${t}</option>`).join('');
  const stat=[['completed','completed'],['draft','draft'],['inProgress','inProgress']].map(([v,l])=>`<option value="${v}" ${v===(sa.status||'completed')?'selected':''}>${l}</option>`).join('');
  const rowIos=en('ios')?`
    <div class="pm-row"><label class="check" style="margin:0"><input type="checkbox" id="pbIos" ${dis('ios')}>🍎 iOS</label>
      <select id="pbIosMode"><option value="debug">Debug (.ipa de teste)</option><option value="release">Release (assinado para a App Store)</option></select></div>${why('ios')}
    <div id="pbIosRunBox" class="pm-row" hidden><label class="check" style="margin:0"><input type="checkbox" id="pbIosRun">Instalar e abrir no iPhone</label></div>`:'';
  /* aparelhos Android conectados (topState.android, state 'device') para escolher no debug */
  const andDev=(topState.android||[]).filter(x=>x.state==='device');
  const andDevOpts='<option value="">Automático</option>'+andDev.map(x=>`<option value="${esc(x.serial)}">${esc(x.model||x.device||x.serial)}</option>`).join('');
  const rowAnd=en('android')?`
    <div class="pm-row"><label class="check" style="margin:0"><input type="checkbox" id="pbAnd" ${dis('android')}>🤖 Android</label>
      <select id="pbAndMode"><option value="debug">Debug (APK)</option><option value="release">Release (AAB assinado)</option></select></div>${why('android')}
    <div id="pbAndRunBox" class="pm-row" hidden><label class="check" style="margin:0"><input type="checkbox" id="pbAndRun">Instalar e abrir no celular Android</label>
      <select id="pbAndDev">${andDevOpts}</select></div>`:'';
  const rowPc=en('pc')?`
    <div class="pm-row"><label class="check" style="margin:0"><input type="checkbox" id="pbPc" ${dis('pc')}>🖥️ PC</label>
      ${PCT.map(([p,id,l])=>`<label class="check" style="margin:0"><input type="checkbox" id="${id}" ${pcPre.includes(p)&&ok.pc?'checked':''} ${ok.pc?'':'disabled'}>${l}</label>`).join('')}
      <span class="hint">tipo de código: ${esc(typeLabel)}</span></div>${why('pc')}`:'';
  /* bancos do projeto (ov.databases): seção só aparece quando há algum */
  const dbs=ov.databases||[];
  const DBR={prod:'Produção',dev:'Desenvolvimento',other:'Outro'};
  const dbLbl=d=>DBR[d.role]||'Outro';
  const dbProd=dbs.find(d=>d.role==='prod');
  const dbInit=(dbs.find(d=>d.role==='dev')||dbs[0]||{}).id;
  const dbSec=dbs.length?`<div class="pm-sec">
    <div class="field"><label>🗄 Banco de dados</label><select id="pbDb">${dbs.map(d=>`<option value="${esc(d.id)}" ${d.id===dbInit?'selected':''}>${esc(d.name)} — ${dbLbl(d)}</option>`).join('')}</select></div>
    <div class="hint" id="pbDbHint"></div>
  </div>`:'';

  const h=`
  <div class="pm-sec">
    ${rowIos}
    ${rowAnd}
    ${rowPc}
  </div>${dbSec}
  <div class="pm-sec">
    <div class="pm-grid">
      <div class="field"><label>Origem da versão</label><select id="pbVerSrc">${pmVersionOptions(ov)}</select></div>
      <div class="field"><label>Versão</label><input type="text" id="pbVersion" placeholder="1.0.0" style="font-family:var(--mono)"></div>
    </div>
  </div>
  <div class="pm-sec">
    <label class="check"><input type="checkbox" id="pbUpload">Enviar para a loja ao terminar</label>
    <div class="hint" id="pbDebugHint" hidden>o debug não vai para a loja</div>
    <div class="pm-card" id="pbIosBox" hidden><b>🍎 App Store</b>
      <div class="field" style="margin-top:8px"><label>Conta Apple</label><select id="pbIosAcc">${appleOpts}</select></div>
      <div class="field"><label>Bundle ID</label><input type="text" id="pbIosBundle" value="${esc(si.bundleId||'')}" style="font-family:var(--mono)"></div>
      <label class="check" id="pbIosSubBox" hidden><input type="checkbox" id="pbIosSubmit" ${si.submit?'checked':''}>enviar para revisão</label>
    </div>
    <div class="pm-card" id="pbAndBox" hidden><b>🤖 Google Play</b>
      <div class="field" style="margin-top:8px"><label>Conta Google Play</label><select id="pbAndAcc">${playOpts}</select></div>
      <div class="pm-grid">
        <div class="field"><label>Faixa</label><select id="pbAndTrack">${track}</select></div>
        <div class="field"><label>Status</label><select id="pbAndStatus">${stat}</select></div>
      </div>
    </div>
    <div class="pm-card" id="pbPcBox" hidden><b>🎮 Steam</b>
      <div class="field" style="margin-top:8px"><label>Conta Steam</label><select id="pbPcAcc">${steamOpts}</select></div>
      <div class="field"><label>App</label><select id="pbPcApp"></select></div>
      <div class="field"><label>Branch</label><input type="text" id="pbPcBranch" value="${esc(sp.branch||'')}" placeholder="branch a liberar (vazio = só enviar)" style="font-family:var(--mono)"></div>
    </div>
  </div>
  <div class="field"><label>O que há de novo (pt-BR)</label><textarea id="pbNotes" rows="4" style="width:100%;background:var(--input);border:1px solid var(--line);border-radius:9px;padding:10px;color:var(--text);font:inherit;resize:vertical"></textarea></div>
  <div class="row"><button class="btn sm" id="pbGen">✨ Gerar com IA</button></div>`;

  pmModal('🔨 Build '+project,h,[{label:'Cancelar',cls:'',onClick:()=>pmClose()},{label:'Iniciar',cls:'pri',id:'pbStart',onClick:()=>start()}]);

  /* versão: origem de arquivo fica somente leitura; manual não é sobrescrita por clique em plataforma */
  const firstPlat=()=>['ios','android','pc'].find(p=>chk(PBC[p]))||'ios';
  const refreshVer=force=>{
    const src=val('pbVerSrc');
    if(!force&&src==='manual')return;
    const fileSrc=((ov.version||{}).sources||[]).some(s=>s.id===src);
    $('pbVersion').value=pmResolveVersion(ov,src,firstPlat());
    $('pbVersion').readOnly=fileSrc};
  /* mostra só os campos que valem para as linhas marcadas */
  const pbRefresh=()=>{
    const iosRel=chk('pbIos')&&val('pbIosMode')==='release';
    const andRel=chk('pbAnd')&&val('pbAndMode')==='release';
    const pcOn=chk('pbPc'), up=chk('pbUpload');
    const dbg=(chk('pbIos')&&val('pbIosMode')==='debug')||(chk('pbAnd')&&val('pbAndMode')==='debug');
    $('pbIosBox').hidden=!iosRel;
    $('pbIosSubBox').hidden=!(iosRel&&up);
    $('pbAndBox').hidden=!(andRel&&up);
    $('pbPcBox').hidden=!(pcOn&&up);
    $('pbDebugHint').hidden=!(up&&dbg);
    /* instalar/abrir no aparelho só existe no modo debug (ignorado em release) */
    const iosRunBox=$('pbIosRunBox'),andRunBox=$('pbAndRunBox');
    if(iosRunBox)iosRunBox.hidden=!(chk('pbIos')&&val('pbIosMode')==='debug');
    if(andRunBox)andRunBox.hidden=!(chk('pbAnd')&&val('pbAndMode')==='debug');
    /* banco: com envio à loja marcado, só o prod serve; aviso em vermelho quando não é */
    const dbEl=$('pbDb'),dbHint=$('pbDbHint');
    if(dbEl&&dbHint){
      const cur=dbs.find(d=>d.id===dbEl.value)||{};
      const warn=up&&!dbProd?'Cadastre um banco prod em 🗄 Banco de dados para enviar às lojas.':up&&cur.role!=='prod'?'Só builds feitos com o banco Produção vão para a loja.':'';
      dbHint.textContent=warn;
      dbHint.style.color=warn?'var(--bad)':''}};
  /* apps da conta Steam escolhida */
  const pbFillApps=()=>{
    const acc=val('pbPcAcc');
    const L=(ov.steamApps||[]).filter(a=>a.accountId===acc);
    $('pbPcApp').innerHTML=L.length?L.map(a=>`<option value="${esc(a.appId)}" ${acc===sp.steamAccountId&&String(a.appId)===String(sp.steamAppId||'')?'selected':''}>${esc(a.name||a.appId)} (${esc(a.appId)})</option>`).join(''):'<option value="">— nenhum app desta conta —</option>'};

  $('pbVerSrc').onchange=async()=>{
    const src=val('pbVerSrc');
    try{await pmSaveSettings(project,'version',{versionSource:src});ov.version=ov.version||{};ov.version.source=src;refreshVer(true)}
    catch(e){toast(e.message)}};
  ['pbIos','pbAnd','pbPc','pbPcWin32','pbPcLinux','pbPcDarwin'].forEach(id=>{const el=$(id);if(el)el.onchange=()=>{pbRefresh();refreshVer(false)}});
  ['pbIosMode','pbAndMode','pbUpload'].forEach(id=>{const el=$(id);if(el)el.onchange=pbRefresh});
  /* bancos: ao marcar envio à loja com banco não-prod, troca para o prod (se houver) */
  if($('pbDb')){
    $('pbDb').onchange=pbRefresh;
    $('pbUpload').onchange=()=>{
      const cur=dbs.find(d=>d.id===val('pbDb'))||{};
      if(chk('pbUpload')&&dbProd&&cur.role!=='prod'){$('pbDb').value=dbProd.id;toast('Envio para a loja: banco Produção selecionado')}
      pbRefresh()}}
  $('pbPcAcc').onchange=pbFillApps;
  $('pbGen').onclick=async()=>{
    if(!ov.changes)return toast('Sem mudanças no git: escreva as notas à mão');
    toast('Gerando com IA…');
    try{
      const ai=await api('/api/ai');const prov=ai.default;
      if(!prov||!(ai.providers||{})[prov])return toast('Configure uma IA na seção IA');
      const r=await api('/api/ai/whatsnew',{provider:prov,project,appName:project,version:val('pbVersion'),locales:['pt-BR'],changes:ov.changes,extra:''});
      $('pbNotes').value=String(r['pt-BR']||'');toast('Texto gerado — revise antes de enviar')}
    catch(e){toast(e.message)}};
  pbRefresh();refreshVer(true);pbFillApps();

  /* Iniciar: valida, grava os campos usados, monta os passos e dispara o multi */
  async function start(){
    const ver=val('pbVersion');
    if(!/^\d+(\.\d+){0,3}$/.test(ver))return toast('Versão inválida (ex: 1.2.0)');
    const iosOn=chk('pbIos'), andOn=chk('pbAnd'), pcOn=chk('pbPc');
    if(!iosOn&&!andOn&&!pcOn)return toast('Marque ao menos uma plataforma');
    const iosRel=iosOn&&val('pbIosMode')==='release', andRel=andOn&&val('pbAndMode')==='release';
    const up=chk('pbUpload');
    const pcPl=PCT.filter(([,id])=>chk(id)).map(([p])=>p);
    if(pcOn&&!pcPl.length)return toast('Marque ao menos um alvo de PC');
    if(iosRel){
      if(!val('pbIosAcc'))return toast('Escolha a conta Apple');
      if(!val('pbIosBundle'))return toast('Informe o bundle ID');
      const ac=(A.apple||[]).find(x=>x.id===val('pbIosAcc'));
      if(up&&ac&&!ac.hasApi)return toast('Esta conta Apple não tem API: não dá para enviar à App Store')}
    if(up&&andRel&&!val('pbAndAcc'))return toast('Escolha a conta Google Play');
    if(up&&pcOn){
      if(!val('pbPcAcc')||!val('pbPcApp'))return toast('Escolha a conta e o app da Steam');
      if(val('pbPcBranch').toLowerCase()==='default')return toast('A branch default não pode ser liberada pelo painel')}
    /* banco: envio à loja exige banco prod (sem banco prod cadastrado, bloqueia qualquer envio) */
    const db=val('pbDb'), selDb=dbs.find(d=>d.id===db)||{};
    if(dbs.length){
      if(up&&!dbProd)return toast('Cadastre um banco prod em 🗄 Banco de dados para enviar às lojas');
      if(up&&(iosRel||andRel||pcOn)&&selDb.role!=='prod')return toast('Só dá para enviar para a loja com o banco prod')}
    /* confirmação resumida quando há envio para a loja */
    const lojas=[];
    if(up&&iosRel)lojas.push('App Store (iOS'+(chk('pbIosSubmit')?', enviar para revisão':'')+')');
    if(up&&andRel)lojas.push('Google Play (faixa '+val('pbAndTrack')+')');
    if(up&&pcOn)lojas.push('Steam (app '+val('pbPcApp')+(val('pbPcBranch')?' → branch '+val('pbPcBranch'):' sem liberar')+')');
    const dbLine=dbs.length?`\nBanco: ${selDb.name||''} (${dbLbl(selDb)})`:'';
    if(lojas.length&&!confirm(`Build ${project} v${ver}${dbLine}\n\nEnviar para: ${lojas.join(', ')}\n\nConfirmar?`))return;
    /* grava os campos usados */
    try{
      if(iosRel)await pmSaveSettings(project,'ios',{accountId:val('pbIosAcc'),bundleId:val('pbIosBundle'),iosSubmit:chk('pbIosSubmit')});
      if(andRel)await pmSaveSettings(project,'android',{playAccountId:val('pbAndAcc'),track:val('pbAndTrack'),status:val('pbAndStatus')});
      if(pcOn)await pmSaveSettings(project,'pc',{platforms:pcPl});
      if(pcOn&&up)await pmSaveSettings(project,'steam',{accountId:val('pbPcAcc'),appId:val('pbPcApp'),branch:val('pbPcBranch')});
    }catch(e){return toast(e.message)}
    /* passos: android, pc, ios (o servidor injeta project e para no primeiro erro) */
    const notes=val('pbNotes');
    const steps=[];
    const pkg=(P.android&&P.android.packageName)||sa.packageName||'';
    if(andOn){
      if(andRel)steps.push({action:'android.release',args:{packageName:pkg,kind:'aab',debug:false,versionName:ver,versionCode:'auto',preBuild:sa.preBuild||'',upload:up,playAccountId:val('pbAndAcc'),track:val('pbAndTrack'),status:val('pbAndStatus'),userFraction:null,releaseNotes:{'pt-BR':notes}},title:'Android release (AAB)'});
      else{
        const andArgs={packageName:pkg,kind:'apk',debug:true,versionName:ver,versionCode:'auto',preBuild:sa.preBuild||'',upload:false};
        /* instalar e abrir no celular: o android.py instala por adb (serial '' = automático) */
        if(chk('pbAndRun')){andArgs.install=true;andArgs.serial=val('pbAndDev')}
        steps.push({action:'android.release',args:andArgs,title:'Android debug (.apk)'})}}
    if(pcOn){
      if(up)steps.push({action:'steam.release',args:{accountId:val('pbPcAcc'),appId:val('pbPcApp'),branch:val('pbPcBranch'),description:notes.slice(0,200),platforms:pcPl,build:true,version:ver,appName:sp.appName,preBuild:sp.preBuild??'',webDir:sp.webDir??'',electronVersion:sp.electronVersion??'',zip:true,projectType:sp.projectType,upload:true},title:'App de PC + Steam'});
      else steps.push({action:'pc.build',args:{version:ver,appName:sp.appName,platforms:pcPl,preBuild:sp.preBuild??'',webDir:sp.webDir??'',electronVersion:sp.electronVersion??'',zip:true,projectType:sp.projectType},title:'App de PC'})}
    if(iosOn){
      if(iosRel)steps.push({action:'release',args:{accountId:val('pbIosAcc'),bundleId:val('pbIosBundle'),version:ver,build:'auto',steps:up?{upload:true,publish:true,submit:chk('pbIosSubmit')}:{upload:false,publish:false,submit:false},whatsNew:up?{'pt-BR':notes}:{},noEncryption:true},title:'iOS release (.ipa assinado)'});
      else if(chk('pbIosRun'))steps.push({action:'dev.run',args:{config:'debug',udid:'',conn:'all'},title:'iOS debug no iPhone'});
      else steps.push({action:'dev.build',args:{config:'debug',sign:true,ipa:true},title:'iOS debug (.ipa)'})}
    /* banco: cada etapa leva o id escolhido (só quando há bancos) */
    if(dbs.length)steps.forEach(s=>{s.args.database=db});
    pmClose();
    run('multi',{project,steps},'Build '+project,project);
  }
}
