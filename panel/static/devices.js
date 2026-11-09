/* ---------- abas Android e PC da página Dispositivos ---------- */
/* script clássico carregado depois do script principal do index.html: usa os globais $, val, esc, toast, api, run, go, colorOf, fmtB, projCache, loadTopbar.
   initAndroidDev() e initPcDev() são chamadas pelo go() ao abrir a aba (s-androiddev e s-pcdev). */
let adBuilt=false, pdBuilt=false;
let adDevs=[]; /* aparelhos da última leitura de /api/adb/devices (os botões do cartão usam o índice) */

/* ---------- aba Android (adb por Wi-Fi) ---------- */
function initAndroidDev(){
  const el=$('s-androiddev');
  if(!adBuilt){
    el.innerHTML=`<div class="segtabs"><button data-t="devices" onclick="go('devices')">📱 iPhone (iOS)</button><button data-t="androiddev" onclick="go('androiddev')">🤖 Android</button><button data-t="pcdev" onclick="go('pcdev')">🖥️ PC</button></div>
  <div class="row" style="margin-bottom:14px">
    <button class="btn" onclick="loadAndroidDev()">Atualizar</button><span class="hint" id="adHint"></span>
  </div>
  <h2>Meus celulares</h2>
  <div class="grid" id="adGrid"></div>

  <div class="card" id="adApkCard" style="margin-bottom:16px"><h3>Instalar .apk</h3><p>Escolha um arquivo de /work ou envie do seu PC.</p>
    <div class="drop" id="adApkDrop">Arraste um .apk aqui ou <a href="#" onclick="$('adApkFile').click();return false">escolha</a><input type="file" id="adApkFile" accept=".apk" hidden></div>
    <div class="field"><label>Arquivo</label><select id="adApkSel"></select></div>
    <div class="field"><label>Celular</label><select id="adApkDev"><option value="">Automático (primeiro conectado)</option></select></div>
    <button class="btn pri" onclick="adInstallApk()">Instalar</button>
  </div>

  <h2>Conectar</h2>
  <div class="card add" style="max-width:620px"><h3>＋ Conectar celular (Wi-Fi)</h3>
    <p>Android 11+: Opções do desenvolvedor → Depuração por Wi-Fi → Parear com código. O PC e o celular precisam estar na mesma rede.</p>
    <div class="field"><label>Parear</label><div class="row"><input type="text" id="adPairAddr" placeholder="ip:porta de pareamento" style="flex:1;font-family:var(--mono)"><input type="text" id="adPairCode" placeholder="código" style="max-width:110px;font-family:var(--mono)"><button class="btn" onclick="run('adb.pair',{addr:val('adPairAddr'),code:val('adPairCode')},'Parear Android')">Parear</button></div></div>
    <div class="field"><label>Conectar</label><div class="row"><input type="text" id="adAddr" placeholder="ip:porta de conexão" style="flex:1;font-family:var(--mono)"><button class="btn" onclick="run('adb.connect',{addr:val('adAddr')},'Conectar Android')">Conectar</button><button class="btn" onclick="run('adb.disconnect',{},'Desconectar Android')">Desconectar todos</button></div></div>
    <p class="hint" style="margin:0">Depois de parear ou conectar, clique em Atualizar.</p>
  </div>`;
    adBuilt=true;
    /* ligados UMA vez, quando o HTML é montado */
    dropzone($('adApkDrop'),adApkUp);
    $('adApkFile').onchange=e=>[...e.target.files].forEach(adApkUp);
  }
  el.querySelectorAll('.segtabs button').forEach(b=>b.classList.toggle('on',b.dataset.t==='androiddev'));
  loadAndroidDev();
}

async function loadAndroidDev(){
  const hint=$('adHint'), grid=$('adGrid');
  hint.textContent='Atualizando…';
  /* estado do aparelho -> [classe da pill, texto] */
  const stInfo=s=>s==='device'?['ok','Conectado']:s==='unauthorized'?['warn','Não autorizado: confirme no celular']:['off','Offline'];
  let devs=[], projects=[], projOk=false, err='';
  try{const r=await api('/api/adb/devices');devs=Array.isArray(r)?r:[]}catch(e){err=e.message}
  try{const r=await api('/api/projects');if(Array.isArray(r)){projects=r;projOk=true}}catch(e){}
  if(projOk)projCache=projects;
  adDevs=devs;

  /* APKs de todos os projetos e apps (projetos com package name Android) */
  const apks=[], apps=[];
  projects.forEach(p=>{
    (p.artifacts||[]).forEach(a=>{if(/\.apk$/i.test(a))apks.push(a)});
    const pkg=(p.meta&&p.meta.android&&p.meta.android.packageName)||(p.android&&p.android.packageName)||'';
    if(pkg)apps.push({name:p.name,pkg});
  });
  const apkOpts=apks.length?apks.map(a=>`<option value="${esc('/work/'+a)}">${esc(a)}</option>`).join(''):'<option value="">nenhum .apk — gere um build primeiro</option>';
  const appOpts=apps.length?apps.map(a=>`<option value="${esc(a.pkg)}">${esc(a.name)} · ${esc(a.pkg)}</option>`).join(''):'<option value="">nenhum app com package name</option>';

  grid.innerHTML=devs.length?devs.map((d,i)=>{
    const [cls,txt]=stInfo(d.state);
    const dis=d.state==='device'?'':'disabled';
    return `<div class="card acc">
      <div class="devhead"><div class="avatar" style="background:${colorOf(d.serial)}">🤖<span class="sdot ${cls}"></span></div>
        <span class="pill ${cls}"><i></i>${txt}</span></div>
      <h3>${esc(d.model||d.device||d.serial)}</h3>
      <div class="kv"><span>Serial</span><span style="font-family:var(--mono)">${esc(d.serial)}</span><span>Modelo</span><span>${esc(d.model||'—')}</span><span>Estado</span><span>${esc(d.state||'—')}</span></div>
      <div class="field" style="margin-top:10px"><label>APK</label><select id="adApk${i}">${apkOpts}</select></div>
      <div class="row"><button class="btn sm pri" ${dis} onclick="adAct(${i},'install')">Instalar</button></div>
      <div class="field" style="margin-top:10px"><label>App</label><select id="adApp${i}">${appOpts}</select></div>
      <div class="row"><button class="btn sm" ${dis} onclick="adAct(${i},'launch')">Abrir app</button></div>
    </div>`}).join('')
    :'<div class="empty">Nenhum celular. Pareie e conecte pelo card abaixo.</div>';

  /* select "Celular" do card Instalar .apk: só aparelhos conectados */
  const keepDev=val('adApkDev'), online=devs.filter(d=>d.state==='device');
  $('adApkDev').innerHTML='<option value="">Automático (primeiro conectado)</option>'+online.map(d=>`<option value="${esc(d.serial)}">${esc(d.model||d.device||d.serial)}</option>`).join('');
  if(online.some(d=>d.serial===keepDev))$('adApkDev').value=keepDev;

  adLoadApks().catch(()=>{});
  hint.textContent=err?'Erro: '+err:devs.length?devs.length+' celular(es) listado(s)':'';
  loadTopbar();
}

/* lista de .apk do card Instalar .apk: arquivos de /work e /downloads; want = caminho a selecionar (ex.: upload recém-feito) */
async function adLoadApks(want){
  const sel=$('adApkSel'), keep=want||sel.value;
  const [a,b]=await Promise.all([findFiles('work','',/\.apk$/i,4),findFiles('downloads','',/\.apk$/i,0)]);
  const L=[...new Set([...a,...b])];
  if(want&&!L.includes(want))L.unshift(want);
  sel.innerHTML=L.length?L.map(p=>`<option value="${esc(p)}">${esc(p)}</option>`).join(''):'<option value="">nenhum .apk encontrado</option>';
  if(keep&&L.includes(keep))sel.value=keep;
}

/* upload de um .apk do PC (botão escolher ou arrastar) */
async function adApkUp(f){
  const j=await upload(f,'work','uploads/'+f.name);
  if(j&&j.error)return;
  await adLoadApks('/work/uploads/'+f.name);
}

/* botão Instalar do card Instalar .apk */
function adInstallApk(){
  const path=val('adApkSel');if(!path)return toast('Escolha um .apk');
  run('adb.install',{serial:val('adApkDev'),path},'Instalar APK');
}

/* chamada pela Home (botão "Instalar .apk"): abre a aba Android e destaca o card */
async function adOpenInstall(){
  go('androiddev');
  await new Promise(r=>setTimeout(r,500));
  const c=$('adApkCard');if(!c)return;
  c.scrollIntoView({behavior:'smooth',block:'center'});
  c.style.outline='2px solid #4f8cff';c.style.outlineOffset='4px';
  setTimeout(()=>{c.style.outline='';c.style.outlineOffset=''},1500);
}

/* botões Instalar / Abrir app do cartão do aparelho i */
function adAct(i,kind){
  const d=adDevs[i];if(!d)return;
  if(kind==='install'){
    const path=val('adApk'+i);if(!path)return toast('Nenhum .apk: gere um build primeiro');
    run('adb.install',{serial:d.serial,path},'Instalar no celular '+(d.model||d.serial));
  }else{
    const pkg=val('adApp'+i);if(!pkg)return toast('Escolha um app com package name');
    run('adb.launch',{serial:d.serial,package:pkg},'Abrir app no celular '+(d.model||d.serial));
  }
}

/* ---------- aba PC (Windows pelo host.docker.internal) ---------- */
function initPcDev(){
  const el=$('s-pcdev');
  if(!pdBuilt){
    el.innerHTML=`<div class="segtabs"><button data-t="devices" onclick="go('devices')">📱 iPhone (iOS)</button><button data-t="androiddev" onclick="go('androiddev')">🤖 Android</button><button data-t="pcdev" onclick="go('pcdev')">🖥️ PC</button></div>
  <div class="row" style="margin-bottom:14px"><button class="btn" onclick="loadPcDev()">Atualizar</button></div>
  <div class="card" style="margin-bottom:16px"><h3>Este PC</h3><div id="pdStatus"></div></div>
  <h2>Builds de PC dos projetos</h2>
  <div class="list" id="pdProjects"></div>`;
    pdBuilt=true;
  }
  el.querySelectorAll('.segtabs button').forEach(b=>b.classList.toggle('on',b.dataset.t==='pcdev'));
  loadPcDev();
}

async function loadPcDev(){
  const stEl=$('pdStatus'), plEl=$('pdProjects');
  const PLAT={win32:'Windows',linux:'Linux',darwin:'macOS'};
  const mono=t=>`<span style="font-family:var(--mono)">${esc(t)}</span>`;
  try{
    const S=await api('/api/pc/status');
    const cls=S.connected?'ok':'off';
    stEl.innerHTML=`<div class="devhead"><div class="avatar" style="background:${colorOf('pc')}">🖥️<span class="sdot ${cls}"></span></div>
      <span class="pill ${cls}" title="O container alcança o Windows pelo host.docker.internal"><i></i>${S.connected?'PC conectado':'PC desligado'}</span></div>
      <div class="kv"><span>Windows (host)</span><span>${esc(S.host||'—')} · ${esc(S.hostIp||'—')}</span>
        <span>Serviço Apple</span><span>${S.appleService?'✅ ativo':'⚠️ desligado'}${S.usbmuxdVia?' · '+mono(S.usbmuxdVia):''}</span>
        <span>steamcmd</span><span>${S.steamcmd?'✅ '+mono(S.steamcmdPath||''):'⚠️ não instalado'}</span>
        <span>Node</span><span>${esc(S.node||'—')} · npx ${S.npx?'✅':'⚠️'}</span>
        <span>Cache do Electron</span><span>${fmtB(S.electronCacheBytes||0)}</span></div>`;
  }catch(e){stEl.innerHTML=`<p class="hint">${esc(e.message)}</p>`}

  let P=null;
  try{P=await api('/api/projects')}catch(e){plEl.innerHTML=`<div class="empty">${esc(e.message)}</div>`}
  if(Array.isArray(P)){
    projCache=P;
    const L=P.filter(p=>(p.platforms||[]).includes('pc'));
    plEl.innerHTML=L.length?L.map(p=>{
      const m=(p.meta||{}).pc||{}, lb=m.lastBuild||{}, at=lb.at, folders=lb.folders||{};
      const fold=Object.keys(folders).map(k=>`${PLAT[k]||k}: ${mono(folders[k])}`).join(' · ');
      const zips=(p.artifacts||[]).filter(a=>/\.zip$/i.test(a));
      const q=esc(JSON.stringify(p.name));
      return `<div class="item"><div class="grow">
          <div class="name">${esc(p.name)}</div>
          <div class="meta">Último build: ${m.lastVersionName?'v'+esc(m.lastVersionName):'nenhum ainda'}${typeof at==='number'?' · '+esc(new Date(at*1000).toLocaleString()):''}</div>
          ${fold?`<div class="meta" style="margin-top:4px">${fold}</div>`:''}
          ${zips.length?`<div class="row" style="margin-top:6px">${zips.map(a=>`<a class="btn sm" href="/api/download?root=work&path=${encodeURIComponent(a)}">⬇ ${esc(a.split('/').pop())}</a>`).join('')}</div>`:''}
        </div>
        <div class="row"><button class="btn sm pri" onclick="quickPc(${q})">Gerar PC</button><button class="btn sm" onclick="openPcPublish(${q})">🎮 Steam (PC)</button></div></div>`;
    }).join(''):(P.length?'<div class="empty">Nenhum projeto com build de PC.</div>':'<div class="empty">Nenhum projeto com package.json.</div>');
  }
  loadTopbar();
}
