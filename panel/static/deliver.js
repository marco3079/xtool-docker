/* ---------- Projetos: "Enviar para a loja" (diálogo de envio de builds release) ----------
   script clássico carregado DEPOIS de projects.js.
   usa os globais: $, val, chk, esc, toast, api, run, pmModal, pmClose, pmOverview, pmSaveSettings, pmFmtDate, pmSize, pmVersionConfig */

const PD_PLATS={ios:'🍎 iOS → App Store',android:'🤖 Android → Google Play',pc:'🖥️ PC → Steam'};
const PD_IDS={ios:'pdIos',android:'pdAnd',pc:'pdPc'};
const PD_TARGETS={win32:'Windows',linux:'Linux',darwin:'macOS'};
const PD_TRACKS=[['internal','Teste interno'],['alpha','Teste fechado'],['beta','Teste aberto'],['production','Produção']];
const PD_STATUSES=[['completed','Concluído'],['draft','Rascunho'],['inProgress','Lançamento gradual']];
/* diálogo aberto: {project, ov, sec:{ios,android,pc}, byId:{id: Build}, pcTargets:[alvo]} */
let pdCtx=null;

const pdSel=name=>{const el=document.querySelector(`input[name="${name}"]:checked`);return el?el.value:''};
const pdKind=b=>(b.platform==='pc'&&b.kind==='folder')?'pasta pronta':b.kind;
const pdLabel=b=>`v${esc(b.version)} · build ${esc(b.build)} · ${esc(pdKind(b))} · ${esc(pmFmtDate(b.at))} · ${esc(pmSize(b.size))}`;

/* builds não deliverable (banco Produção sem build prod) aparecem desabilitados com o motivo; o padrão é o primeiro deliverable */
function pdRadios(name,builds){
  const firstOk=builds.find(b=>b.deliverable!==false);
  return builds.map(b=>{
    const ok=b.deliverable!==false;
    const tag=ok&&b.database?` <span class="hint" style="margin-left:6px">🗄 ${esc(b.database.name)}</span>`:'';
    const why=ok?'':`<div class="hint" style="margin:0 0 6px 24px">${esc(b.deliverReason||'não pode ser enviado')}</div>`;
    return `<label class="check" style="margin:4px 0;${ok?'':'opacity:.5'}"><input type="radio" name="${esc(name)}" value="${esc(b.id)}" ${ok?'':'disabled'} ${b===firstOk?'checked':''}>${pdLabel(b)}${tag}</label>${why}`;
  }).join('');
}
function pdDisabled(p){
  return `<div class="card" style="margin-bottom:12px;opacity:.6"><label class="check"><input type="checkbox" disabled>${PD_PLATS[p]}</label><div class="hint">sem build release</div></div>`;
}
/* seção com builds release mas nenhum deliverable: aparece desabilitada, com os motivos */
function pdOff(p,inner){
  return `<div class="card" style="margin-bottom:12px;opacity:.6"><label class="check"><input type="checkbox" disabled>${PD_PLATS[p]}</label>${inner}</div>`;
}
function pdToggle(cb,sec){const el=$(sec);if(el)el.style.opacity=chk(cb)?'':'.55'}
function pdStatusChanged(){const w=$('pdAndFracWrap');if(w)w.style.display=val('pdAndStatus')==='inProgress'?'':'none'}

/* preenche #pdPcApp com os apps da conta escolhida; devolve a lista da conta */
function pdPcFill(wantApp){
  const acc=val('pdPcAcc');
  const L=((pdCtx&&pdCtx.ov.steamApps)||[]).filter(a=>a.accountId===acc);
  $('pdPcApp').innerHTML=L.length?L.map(a=>`<option value="${esc(a.appId)}">${esc(`${a.name||a.appId} (${a.appId})`)}</option>`).join(''):'<option value="">— nenhum app desta conta —</option>';
  if(wantApp&&L.some(a=>String(a.appId)===String(wantApp)))$('pdPcApp').value=String(wantApp);
  return L;
}
function pdPcAccChanged(){
  const L=pdPcFill('');
  pdPcAppChanged(L);
}
function pdPcAppChanged(L){
  const list=L||((pdCtx&&pdCtx.ov.steamApps)||[]).filter(a=>a.accountId===val('pdPcAcc'));
  const app=list.find(a=>String(a.appId)===val('pdPcApp'));
  if(app&&app.branch)$('pdPcBranch').value=app.branch;
}
function pdConfigVersion(){const c=pdCtx;if(c)pmVersionConfig(c.project,()=>projDeliver(c.project))}

/* builds escolhidos hoje no diálogo (só das seções marcadas) */
function pdPicks(){
  const c=pdCtx,r={ios:null,android:null,pc:[]};
  if(c.sec.ios&&chk('pdIos'))r.ios=c.byId[pdSel('pdIosBuild')]||null;
  if(c.sec.android&&chk('pdAnd'))r.android=c.byId[pdSel('pdAndBuild')]||null;
  if(c.sec.pc&&chk('pdPc'))c.pcTargets.forEach(t=>{if(chk('pdPcT-'+t)){const b=c.byId[pdSel('pdPcBuild-'+t)];if(b)r.pc.push({t,b})}});
  return r;
}

/* gera o "O que há de novo" com a IA padrão, a partir das mudanças do git */
async function pdGenNotes(){
  const c=pdCtx;if(!c)return;
  if(!c.ov.changes)return toast('Sem mudanças no git: escreva o texto à mão');
  const pk=pdPicks();
  const first=pk.ios||pk.android||(pk.pc[0]&&pk.pc[0].b)||null;
  toast('Gerando com IA…');
  try{
    const ai=await api('/api/ai');
    if(!ai.default)return toast('Configure uma IA na seção IA');
    const r=await api('/api/ai/whatsnew',{provider:ai.default,project:c.project,appName:c.project,version:first?first.version:'',locales:['pt-BR'],changes:c.ov.changes,extra:''});
    $('pdNotes').value=String(r['pt-BR']||'');
    toast('Texto gerado — revise antes de enviar');
  }catch(e){toast(e.message)}
}

/* popup de carregamento (uiLoading, do index.html); sem ele, segue sem overlay */
const pdLoading=msg=>(typeof uiLoading==='function')?uiLoading(msg):(()=>{});

/* abre o diálogo "Enviar para a loja" do projeto (só builds release) */
async function projDeliver(project){
  const done=pdLoading('Abrindo o envio…');
  try{await pdOpenDeliver(project)}finally{done()}
}
async function pdOpenDeliver(project){
  let ov;
  try{ov=await pmOverview(project)}catch(e){return toast(e.message)}
  const P=ov.platforms||{}, S=ov.settings||{}, A=ov.accounts||{};
  const SI=S.ios||{}, SA=S.android||{}, SP=S.pc||{};
  /* pronta = configurada E ativada neste projeto (plataforma desativada não aparece) */
  const configured=p=>!!(P[p]&&P[p].configured&&P[p].enabled);
  const rel=(ov.builds||[]).filter(b=>b.release===true&&PD_IDS[b.platform]&&configured(b.platform)&&(b.platform!=='pc'||PD_TARGETS[b.target]));
  rel.sort((a,b)=>(b.at||0)-(a.at||0));
  /* deliv: builds que podem ser enviados (sem restrição de banco); rel: todos os release, mostrados na lista */
  const deliv=rel.filter(b=>b.deliverable!==false);
  const byId={};rel.forEach(b=>{byId[b.id]=b});
  const pcTargetsAll=Object.keys(PD_TARGETS).filter(t=>rel.some(b=>b.platform==='pc'&&b.target===t));
  const pcTargets=Object.keys(PD_TARGETS).filter(t=>deliv.some(b=>b.platform==='pc'&&b.target===t));
  const sec={ios:deliv.some(b=>b.platform==='ios'),android:deliv.some(b=>b.platform==='android'),pc:pcTargets.length>0};
  pdCtx={project,ov,sec,byId,pcTargets};

  /* envio travado: nenhum build release nas plataformas configuradas */
  if(!rel.length){
    pmModal('📤 Enviar '+project,'<p>Nenhum build release ainda: gere um em 🔨 Build (modo Release).</p>',[{label:'Fechar',cls:'',id:'pdClose',onClick:()=>pmClose()}]);
    return;
  }
  /* envio travado: há builds release, mas nenhum pode ser enviado (todos sem banco prod) */
  if(!deliv.length){
    pmModal('📤 Enviar '+project,'<p>Nenhum build release feito com o banco Produção. Gere um em Build escolhendo o banco prod.</p>',[{label:'Fechar',cls:'',id:'pdClose',onClick:()=>pmClose()}]);
    return;
  }

  /* iOS */
  let secIos='';
  if(configured('ios')){
    const bundle=SI.bundleId||(P.ios&&P.ios.bundleId)||'';
    const iosRel=rel.filter(b=>b.platform==='ios');
    if(!iosRel.length)secIos=pdDisabled('ios');
    else if(!sec.ios)secIos=pdOff('ios',`<div class="field"><label>Build release</label>${pdRadios('pdIosBuild',iosRel)}</div>`);
    else secIos=`<div class="card" id="pdSecIos" style="margin-bottom:12px">
      <label class="check"><input type="checkbox" id="pdIos" checked onchange="pdToggle('pdIos','pdSecIos')"><b>${PD_PLATS.ios}</b></label>
      <div class="field"><label>Build release</label>${pdRadios('pdIosBuild',iosRel)}</div>
      <div class="field"><label>Conta Apple</label><select id="pdIosAcc">${(A.apple||[]).map(a=>`<option value="${esc(a.id)}" ${a.id===SI.accountId?'selected':''}>${esc(a.label)}${a.hasApi?'':' — sem API da Apple'}</option>`).join('')||'<option value="">nenhuma conta Apple</option>'}</select></div>
      <div class="field"><label>Bundle ID</label><input type="text" id="pdIosBundle" value="${esc(bundle)}" style="font-family:var(--mono)"></div>
      <label class="check"><input type="checkbox" id="pdIosSubmit" ${SI.submit?'checked':''}>enviar para revisão</label>
    </div>`;
  }

  /* Android */
  let secAnd='';
  if(configured('android')){
    const trackSel=SA.track||'internal', statusSel=SA.status||'completed';
    const andRel=rel.filter(b=>b.platform==='android');
    if(!andRel.length)secAnd=pdDisabled('android');
    else if(!sec.android)secAnd=pdOff('android',`<div class="field"><label>Build release</label>${pdRadios('pdAndBuild',andRel)}</div>`);
    else secAnd=`<div class="card" id="pdSecAnd" style="margin-bottom:12px">
      <label class="check"><input type="checkbox" id="pdAnd" checked onchange="pdToggle('pdAnd','pdSecAnd')"><b>${PD_PLATS.android}</b></label>
      <div class="field"><label>Build release</label>${pdRadios('pdAndBuild',andRel)}</div>
      <div class="field"><label>Conta Google Play</label><select id="pdAndAcc">${(A.play||[]).map(a=>`<option value="${esc(a.id)}" ${a.id===SA.playAccountId?'selected':''}>${esc(a.label)}</option>`).join('')||'<option value="">nenhuma conta Google Play</option>'}</select></div>
      <div class="field"><label>Faixa</label><select id="pdAndTrack">${PD_TRACKS.map(([v,l])=>`<option value="${esc(v)}" ${v===trackSel?'selected':''}>${esc(l)}</option>`).join('')}</select></div>
      <div class="field"><label>Status</label><select id="pdAndStatus" onchange="pdStatusChanged()">${PD_STATUSES.map(([v,l])=>`<option value="${esc(v)}" ${v===statusSel?'selected':''}>${esc(l)}</option>`).join('')}</select></div>
      <div class="field" id="pdAndFracWrap" style="${statusSel==='inProgress'?'':'display:none'}"><label>Percentual dos usuários (%)</label><input type="number" id="pdAndFrac" min="0.1" max="99.9" step="0.1" placeholder="ex.: 10"></div>
    </div>`;
  }

  /* PC (Steam) */
  let secPc='';
  if(configured('pc')){
    const pcRel=rel.filter(b=>b.platform==='pc');
    if(!pcRel.length)secPc=pdDisabled('pc');
    else if(!sec.pc)secPc=pdOff('pc',pcTargetsAll.map(t=>`<div class="field"><label>${esc(PD_TARGETS[t])}</label>${pdRadios('pdPcBuild-'+t,pcRel.filter(b=>b.target===t))}</div>`).join(''));
    else secPc=`<div class="card" id="pdSecPc" style="margin-bottom:12px">
      <label class="check"><input type="checkbox" id="pdPc" checked onchange="pdToggle('pdPc','pdSecPc')"><b>${PD_PLATS.pc}</b></label>
      ${pcTargetsAll.map(t=>`<div class="field"><label class="check"><input type="checkbox" id="pdPcT-${t}" ${pcTargets.includes(t)?'checked':'disabled'}>${esc(PD_TARGETS[t])}</label>${pdRadios('pdPcBuild-'+t,pcRel.filter(b=>b.target===t))}</div>`).join('')}
      <div class="field"><label>Conta Steam</label><select id="pdPcAcc" onchange="pdPcAccChanged()">${(A.steam||[]).map(a=>`<option value="${esc(a.id)}" ${a.id===SP.steamAccountId?'selected':''}>${esc(a.label)}</option>`).join('')||'<option value="">nenhuma conta Steam</option>'}</select></div>
      <div class="field"><label>App Steam</label><select id="pdPcApp" onchange="pdPcAppChanged()"></select></div>
      <div class="field"><label>Branch a liberar</label><input type="text" id="pdPcBranch" value="${esc(SP.branch||'')}" placeholder="vazio = só envia o build" style="font-family:var(--mono)"></div>
      <p class="hint" style="margin:0">A branch default não pode ser liberada pelo steamcmd.</p>
    </div>`;
  }

  /* versão do projeto */
  const V=ov.version||{}, vs=(V.sources||[]).find(s=>s.id===V.source);
  const srcTxt=vs?`${esc(vs.label)}${vs.value?` <span class="hint">(${esc(vs.value)})</span>`:''}`:esc(V.source||'—');

  const body=`${secIos}${secAnd}${secPc}
    <div class="card" style="margin-bottom:12px">
      <div class="field"><label>O que há de novo (pt-BR)</label><textarea id="pdNotes" rows="4" style="width:100%;background:var(--input);border:1px solid var(--line);border-radius:9px;padding:10px;color:var(--text);font:inherit;resize:vertical"></textarea></div>
      <div class="row"><button class="btn" onclick="pdGenNotes()">✨ Gerar com IA</button><span class="hint">Na Steam, a descrição do build usa só os primeiros 200 caracteres.</span></div>
    </div>
    <div class="card" style="margin-bottom:12px">
      <h3 style="margin:0 0 6px">Versão do projeto</h3>
      <p style="margin:0 0 8px">Origem da versão: <b>${srcTxt}</b></p>
      <div class="row"><button class="btn sm" onclick="pdConfigVersion()">Configurar versão…</button></div>
      <p class="hint" style="margin:8px 0 0">A versão de um build já pronto não muda: para outra versão gere um novo em 🔨 Build.</p>
    </div>`;

  pmModal('📤 Enviar '+project,body,[
    {label:'Cancelar',cls:'',id:'pdCancel',onClick:()=>pmClose()},
    {label:'🚀 Enviar',cls:'pri',id:'pdSend',onClick:()=>pdSubmit()}
  ]);
  if(sec.pc){
    const L=pdPcFill(SP.steamAppId);
    if(!SP.branch)pdPcAppChanged(L);
  }
}

/* valida, confirma, grava os campos e dispara os passos em sequência */
async function pdSubmit(){
  const c=pdCtx;if(!c)return;
  const project=c.project, ov=c.ov;
  const S=ov.settings||{}, A=ov.accounts||{}, P=ov.platforms||{};
  const pk=pdPicks();
  /* defesa extra: nunca enviar build marcado como não deliverable (ex.: banco Produção sem build prod) */
  const naoEnv=[pk.ios,pk.android,...pk.pc.map(x=>x.b)].find(b=>b&&b.deliverable===false);
  if(naoEnv)return toast(naoEnv.deliverReason||'Este build não pode ser enviado');
  if(c.sec.pc&&chk('pdPc')&&!pk.pc.length)return toast('Marque ao menos um alvo de PC');
  if(!pk.ios&&!pk.android&&!pk.pc.length)return toast('Marque ao menos uma plataforma');
  const notas=val('pdNotes');
  const lines=[];
  let iosAcc='',iosBundle='',iosSubmit=false,andAcc='',track='',status='',frac=null,fracPct=null,spAcc='',spApp='',spBranch='';

  if(pk.ios){
    iosAcc=val('pdIosAcc');iosBundle=val('pdIosBundle');iosSubmit=chk('pdIosSubmit');
    const acc=(A.apple||[]).find(a=>a.id===iosAcc);
    if(!acc)return toast('Escolha a conta Apple');
    if(!acc.hasApi)return toast('A conta Apple não tem API: cadastre a chave em Contas → Apple');
    if(!iosBundle)return toast('Informe o bundle ID do iOS');
    lines.push(`🍎 App Store: v${pk.ios.version} (build ${pk.ios.build}) · conta ${acc.label} · ${iosSubmit?'enviar para revisão':'só enviar'}`);
  }
  if(pk.android){
    andAcc=val('pdAndAcc');track=val('pdAndTrack');status=val('pdAndStatus');
    if(!andAcc)return toast('Escolha a conta Google Play');
    if(!(P.android&&P.android.packageName))return toast('Projeto sem package name Android');
    if(status==='inProgress'){
      const pct=Number(val('pdAndFrac').replace(',','.'));
      if(!(pct>0&&pct<100))return toast('Lançamento gradual: informe um percentual entre 0 e 100');
      fracPct=pct;frac=pct/100;
    }
    const tl=(PD_TRACKS.find(t=>t[0]===track)||[])[1]||track;
    const sl=(PD_STATUSES.find(s=>s[0]===status)||[])[1]||status;
    lines.push(`🤖 Google Play: v${pk.android.version} (build ${pk.android.build}) · faixa ${tl} · ${sl}${fracPct!==null?' '+fracPct+'%':''}`);
  }
  if(pk.pc.length){
    spAcc=val('pdPcAcc');spApp=val('pdPcApp');spBranch=val('pdPcBranch');
    if(!spAcc)return toast('Escolha a conta Steam');
    if(!spApp)return toast('Escolha o app Steam');
    if(spBranch.toLowerCase()==='default')return toast("A branch 'default' não pode ser liberada pelo steamcmd");
    const brTxt=spBranch?`branch ${spBranch}`:'sem liberar numa branch';
    lines.push(`🖥️ Steam: ${pk.pc.map(x=>`${PD_TARGETS[x.t]} v${x.b.version} (${pdKind(x.b)})`).join(', ')} · app ${spApp} · ${brTxt}`);
  }

  if(!confirm(`Enviar "${project}" para a loja?\n\n${lines.join('\n')}\n\nSó builds release.`))return;

  try{
    if(pk.ios)await pmSaveSettings(project,'ios',{accountId:iosAcc,bundleId:iosBundle,iosSubmit});
    if(pk.android)await pmSaveSettings(project,'android',{playAccountId:andAcc,track,status});
    if(pk.pc.length)await pmSaveSettings(project,'steam',{accountId:spAcc,appId:spApp,branch:spBranch});
  }catch(e){return toast(e.message)}

  /* ordem: android, pc, ios */
  const steps=[];
  if(pk.android){
    const b=pk.android;
    steps.push({action:'android.release',args:{packageName:P.android.packageName,existing:b.abs,versionName:b.version,versionCode:b.build,upload:true,playAccountId:andAcc,track,status,userFraction:frac,releaseNotes:{'pt-BR':notas}},title:'Android → Google Play (v'+b.version+')'});
  }
  if(pk.pc.length){
    const zips=pk.pc.filter(x=>x.b.kind==='zip'), folders=pk.pc.filter(x=>x.b.kind==='folder');
    if(zips.length){
      const fromZips={};zips.forEach(x=>{fromZips[x.t]=x.b.abs});
      const v=zips[0].b.version;
      steps.push({action:'steam.release',args:{accountId:spAcc,appId:spApp,branch:spBranch,description:notas.slice(0,200),platforms:zips.map(x=>x.t),fromZips,version:v,upload:true},title:'PC → Steam (v'+v+')'});
    }
    if(folders.length){
      const v=folders[0].b.version;
      steps.push({action:'steam.release',args:{accountId:spAcc,appId:spApp,branch:spBranch,description:notas.slice(0,200),platforms:folders.map(x=>x.t),build:false,version:v,upload:true},title:'PC → Steam (v'+v+')'});
    }
  }
  if(pk.ios){
    const b=pk.ios;
    steps.push({action:'release',args:{accountId:iosAcc,bundleId:iosBundle,ipaFile:b.abs,version:b.version,build:b.build,steps:{upload:true,publish:true,submit:iosSubmit},whatsNew:{'pt-BR':notas},noEncryption:true},title:'iOS → App Store (v'+b.version+')'});
  }

  pmClose();
  run('multi',{project,steps},'Enviar '+project,project);
}
