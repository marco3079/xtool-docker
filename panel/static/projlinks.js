/* ---------- Projetos: vínculo com o app do Google Play (Android) e da Steam (PC) ----------
   script clássico carregado depois de deliver.js. Linhas iguais à appRow (Apple), logo abaixo dela.
   usa os globais do index.html: $, esc, toast, api, go, projCache, loadProjects, topState, colorOf, andProject;
   e de pc.js: openPcPublish; e de projects.js: pmModal, pmClose, pmSaveSettings. */

let plPlayApps=[], plPlayAccs=[], plSteamApps=[], plSteamAccs=[];
/* lista aberta no diálogo de vínculo: {project, kind:'play'|'steam', items} */
let plPickCtx=null;
const PL_DEPOT_LABEL={win32:'Windows',linux:'Linux',darwin:'macOS'};

/* carrega as 4 listas em paralelo; falha de uma não impede as outras (lista vazia) */
async function plLoadLinks(){
  const r=await Promise.allSettled([
    api('/api/play/apps'),api('/api/play/accounts'),api('/api/steam/apps'),api('/api/steam/accounts')
  ]);
  const pick=x=>(x.status==='fulfilled'&&Array.isArray(x.value))?x.value:[];
  plPlayApps=pick(r[0]);plPlayAccs=pick(r[1]);plSteamApps=pick(r[2]);plSteamAccs=pick(r[3]);
}

/* avatar com a inicial da conta, mesma cor da conta Apple (colorOf) */
function plAvatar(accountId,label){
  const ch=String(label||'?').charAt(0).toUpperCase()||'?';
  return `<span class="mini" style="background:${colorOf(accountId||'x')}">${esc(ch)}</span>`;
}

/* linha do Google Play no card do projeto (logo abaixo da linha da Apple) */
function androidRow(p,P){
  if(!(p.platforms||[]).includes('android'))return '';
  const M=(p.meta&&p.meta.android)||{};
  const detected=(p.android&&p.android.packageName)||'';
  if(!(M.packageName&&M.playAccountId)){
    return `<div class="meta" style="margin-top:4px">🤖 <a href="#" onclick="pickPlayApp(${P});return false">vincular a um app do Google Play</a>${detected?` · <span style="font-family:var(--mono)">${esc(detected)}</span>`:''}</div>`;
  }
  const pkg=M.packageName, acc=M.playAccountId;
  const app=plPlayApps.find(x=>x.packageName===pkg&&x.accountId===acc)||plPlayApps.find(x=>x.packageName===pkg)||null;
  const name=(app&&app.name)||pkg;
  const accObj=plPlayAccs.find(a=>a.id===acc);
  const accLabel=accObj?accObj.label:'conta removida';
  const pill=accObj?'<span class="pill ok"><i></i>API Google Play</span>':'<span class="pill warn"><i></i>conta removida</span>';
  return `<div class="meta linked" style="margin-top:6px"><span class="appicon">🤖</span><a href="#" title="Abrir no Android" onclick="plOpenAndroid(${P});return false"><b>${esc(name)}</b></a>
    <span style="font-family:var(--mono)">${esc(pkg)}</span> · ${plAvatar(acc,accLabel)}${esc(accLabel)} ${pill}
    · <a href="#" onclick="pickPlayApp(${P});return false">trocar</a></div>`;
}

/* linha da Steam no card do projeto */
function steamRow(p,P){
  const M=(p.meta&&p.meta.steam)||{};
  if(!(p.platforms||[]).includes('pc')&&!M.appId)return '';
  if(!M.appId){
    return `<div class="meta" style="margin-top:4px">🎮 <a href="#" onclick="pickSteamApp(${P});return false">vincular a um app da Steam</a></div>`;
  }
  const appId=String(M.appId), acc=M.accountId||'';
  const app=plSteamApps.find(x=>String(x.appId)===appId&&x.accountId===acc)||plSteamApps.find(x=>String(x.appId)===appId)||null;
  const name=(app&&app.name)||('App '+appId);
  const accObj=plSteamAccs.find(a=>a.id===acc);
  const accLabel=accObj?accObj.label:(acc?'conta removida':'sem conta');
  const st=(typeof topState!=='undefined'&&topState&&topState.steamStatus)?topState.steamStatus[acc]:undefined;
  const pill=st===true?'<span class="pill ok"><i></i>Conectada</span>':st===false?'<span class="pill warn"><i></i>Sem login</span>':'';
  return `<div class="meta linked" style="margin-top:6px"><span class="appicon">🎮</span><a href="#" title="Abrir a aba Steam (PC)" onclick="openPcPublish(${P});return false"><b>${esc(name)}</b></a>
    <span style="font-family:var(--mono)">App ID ${esc(appId)}</span>${M.branch?` · branch <b>${esc(M.branch)}</b>`:''} · ${plAvatar(acc,accLabel)}${esc(accLabel)} ${pill}
    · <a href="#" onclick="pickSteamApp(${P});return false">trocar</a></div>`;
}

/* abre a aba Publicar do Android já com o projeto escolhido */
function plOpenAndroid(project){
  const sel=$('andProject');
  const o=document.createElement('option');o.textContent=project;o.selected=true;
  sel.replaceChildren(o);go('android');
}

/* popup de carregamento (uiLoading, do index.html); sem ele, segue sem overlay */
const plLoading=msg=>(typeof uiLoading==='function')?uiLoading(msg):(()=>{});

/* diálogo: escolher o app do Google Play do projeto */
async function pickPlayApp(project){
  const done=plLoading('Carregando apps…');
  try{await plPickPlayOpen(project)}finally{done()}
}
async function plPickPlayOpen(project){
  try{await plLoadLinks()}catch(e){}
  const p=projCache.find(x=>x.name===project)||{meta:{}};
  const M=(p.meta&&p.meta.android)||{};
  const sugg=(p.android&&p.android.packageName)||'';
  const items=[...plPlayApps].sort((a,b)=>((b.packageName===sugg)?1:0)-((a.packageName===sugg)?1:0));
  plPickCtx={project,kind:'play',items};
  const linked=!!(M.packageName&&M.playAccountId);
  const list=items.length?items.map((r,i)=>{
    const on=linked&&r.packageName===M.packageName&&r.accountId===M.playAccountId;
    const sug=!on&&sugg&&r.packageName===sugg;
    const accLabel=r.accountLabel||(plPlayAccs.find(a=>a.id===r.accountId)||{}).label||'';
    return `<div class="item clickable" style="${on?'border-color:var(--accent,#4f8cff)':''}" onclick="plPickPlayItem(${i})">
      <span class="appicon">🤖</span>
      <div class="grow"><div class="name">${esc(r.name||r.packageName)} ${on?'<span class="pill ok"><i></i>vinculado</span>':sug?'<span class="pill warn"><i></i>sugerido</span>':''}</div>
      <div class="meta"><span style="font-family:var(--mono)">${esc(r.packageName)}</span> · ${esc(accLabel)}</div></div>
    </div>`;}).join(''):'<div class="empty">Nenhum app do Google Play ainda. Vá em Apps da conta → Google Play e adicione o app pelo package name.</div>';
  const buttons=[];
  if(linked)buttons.push({label:'Desvincular',cls:'danger',id:'plUnlink',onClick:()=>linkPlayApp(project,{playAccountId:'',packageName:''})});
  buttons.push({label:'Buscar mais apps',cls:'',id:'plMore',onClick:()=>{pmClose();go('playapps')}});
  buttons.push({label:'Fechar',cls:'',id:'plClose',onClick:()=>pmClose()});
  pmModal(`🤖 Vincular "${project}" a um app do Google Play`,
    `<p>O app escolhido define a <b>conta do Google Play</b> e o <b>package name</b> usados para publicar este projeto. A lista vem de <b>Apps da conta → Google Play</b>.</p>
     <div class="regtbl" style="max-height:50vh;overflow:auto;margin:12px 0">${list}</div>`,buttons);
}
function plPickPlayItem(i){
  const c=plPickCtx;if(!c||c.kind!=='play')return;
  const r=c.items[i];if(!r)return;
  linkPlayApp(c.project,{playAccountId:r.accountId,packageName:r.packageName});
}
/* grava o vínculo do Android (ou desvincula com link vazio) */
async function linkPlayApp(project,link){
  try{
    await pmSaveSettings(project,'android',link);
    toast(link.packageName?`${project} vinculado a ${link.packageName}`:`${project} desvinculado`);
    pmClose();
    loadProjects().catch(()=>{});
  }catch(e){toast(e.message)}
}

/* diálogo: escolher o app da Steam do projeto */
async function pickSteamApp(project){
  const done=plLoading('Carregando apps…');
  try{await plPickSteamOpen(project)}finally{done()}
}
async function plPickSteamOpen(project){
  try{await plLoadLinks()}catch(e){}
  const p=projCache.find(x=>x.name===project)||{meta:{}};
  const M=(p.meta&&p.meta.steam)||{};
  const items=[...plSteamApps];
  plPickCtx={project,kind:'steam',items};
  const linked=!!M.appId;
  const list=items.length?items.map((r,i)=>{
    const on=linked&&String(r.appId)===String(M.appId)&&r.accountId===M.accountId;
    const dep=r.depots||{};
    const deps=Object.keys(PL_DEPOT_LABEL).filter(k=>dep[k]).map(k=>`${PL_DEPOT_LABEL[k]} ${esc(dep[k])}`).join(' · ')||'sem depots';
    const accLabel=r.accountLabel||(plSteamAccs.find(a=>a.id===r.accountId)||{}).label||'';
    return `<div class="item clickable" style="${on?'border-color:var(--accent,#4f8cff)':''}" onclick="plPickSteamItem(${i})">
      <span class="appicon">🎮</span>
      <div class="grow"><div class="name">${esc(r.name||('App '+r.appId))} ${on?'<span class="pill ok"><i></i>vinculado</span>':''}</div>
      <div class="meta"><span style="font-family:var(--mono)">App ID ${esc(r.appId)}</span> · ${esc(accLabel)}${r.branch?` · branch ${esc(r.branch)}`:''}</div>
      <div class="meta">${deps}</div></div>
    </div>`;}).join(''):'<div class="empty">Nenhum app da Steam ainda. Vá em Apps da conta → Steam e cadastre o app com o App ID.</div>';
  const buttons=[];
  if(linked)buttons.push({label:'Desvincular',cls:'danger',id:'plUnlink',onClick:()=>linkSteamApp(project,{accountId:'',appId:'',branch:''})});
  buttons.push({label:'Buscar mais apps',cls:'',id:'plMore',onClick:()=>{pmClose();go('steamapps')}});
  buttons.push({label:'Fechar',cls:'',id:'plClose',onClick:()=>pmClose()});
  pmModal(`🎮 Vincular "${project}" a um app da Steam`,
    `<p>O app escolhido define a <b>conta Steam</b>, o <b>App ID</b> e a <b>branch</b> usados para publicar este projeto. A lista vem de <b>Apps da conta → Steam</b>.</p>
     <div class="regtbl" style="max-height:50vh;overflow:auto;margin:12px 0">${list}</div>`,buttons);
}
function plPickSteamItem(i){
  const c=plPickCtx;if(!c||c.kind!=='steam')return;
  const r=c.items[i];if(!r)return;
  linkSteamApp(c.project,{accountId:r.accountId,appId:r.appId,branch:r.branch||''});
}
/* grava o vínculo da Steam (ou desvincula com link vazio) */
async function linkSteamApp(project,link){
  try{
    await pmSaveSettings(project,'steam',link);
    toast(link.appId?`${project} vinculado ao App ID ${link.appId}`:`${project} desvinculado`);
    pmClose();
    loadProjects().catch(()=>{});
  }catch(e){toast(e.message)}
}
