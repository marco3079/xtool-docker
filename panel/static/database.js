/* ---------- Projetos: bancos de dados (Firebase, Supabase, MongoDB, PostgreSQL, MySQL, SQLite, personalizado) ----------
   script clássico carregado depois de projlinks.js. Abre um pmModal com os bancos cadastrados do projeto,
   os detectados no código e um editor de receita (comando antes do build, arquivos a copiar, variáveis de ambiente).
   usa os globais do index.html: $, esc, toast, api; e de projects.js: pmModal, pmClose, pmBusy.
   API: GET /api/project/databases?project=…  e  POST /api/project/databases (action save | delete). */

const pdbProv={firebase:'Firebase',supabase:'Supabase',mongodb:'MongoDB',postgres:'PostgreSQL',mysql:'MySQL',sqlite:'SQLite',custom:'Personalizado'};
const pdbSvc={rtdb:'Realtime Database',firestore:'Firestore'};
const pdbRoles=[['prod','Produção'],['dev','Desenvolvimento'],['other','Outro']];

const pdbProvLabel=p=>Object.prototype.hasOwnProperty.call(pdbProv,p)?pdbProv[p]:String(p||'');
const pdbProvOpts=sel=>Object.keys(pdbProv).map(k=>`<option value="${k}" ${k===sel?'selected':''}>${esc(pdbProv[k])}</option>`).join('');
const pdbRoleOpts=sel=>pdbRoles.map(([v,l])=>`<option value="${v}" ${v===sel?'selected':''}>${l}</option>`).join('');
const pdbPill=t=>`<span class="pill"><i></i>${esc(t)}</span>`;
const pdbSvcPills=s=>(s||[]).map(x=>pdbPill(Object.prototype.hasOwnProperty.call(pdbSvc,x)?pdbSvc[x]:x)).join('');

/* carrega bancos cadastrados e candidatos detectados */
async function pdbLoad(project){
  const r=await api('/api/project/databases?project='+encodeURIComponent(project));
  return {databases:Array.isArray(r.databases)?r.databases:[],found:Array.isArray(r.found)?r.found:[]};
}
/* candidatos ainda não cadastrados (mesmo provider+identifier de um banco já cadastrado não é oferecido de novo) */
function pdbCandidates(st){
  return st.found.filter(c=>!st.databases.some(d=>d.provider===c.provider&&d.identifier===c.identifier));
}

/* POST com spinner; erro vira toast e retorna null */
async function pdbPost(ctx,body,busyMsg,okMsg){
  const done=pmBusy(busyMsg||'Salvando…');
  try{
    const r=await api('/api/project/databases',Object.assign({project:ctx.project},body));
    if(okMsg)toast(okMsg);
    return r;
  }catch(e){toast(e.message);return null}
  finally{done()}
}
/* recarrega a lista do servidor e volta para a tela de lista */
async function pdbRefresh(ctx){
  const done=pmBusy('Atualizando…');
  try{ctx.st=await pdbLoad(ctx.project)}catch(e){toast(e.message)}
  finally{done()}
  ctx.mode='list';pdbRender(ctx);
}

/* ---------- telas ---------- */
function pdbRender(ctx){
  if(ctx.mode==='edit')return pdbEditRender(ctx);
  if(ctx.mode==='manual')return pdbManualRender(ctx);
  return pdbListRender(ctx);
}

function pdbListRender(ctx){
  const st=ctx.st, dbs=st.databases, cands=pdbCandidates(st);
  const N=cands.length, M=dbs.length;
  const cards=dbs.map((db,i)=>`<div class="pm-card">
      <div class="pm-row" style="margin-bottom:4px"><b>${esc(db.name||'(sem nome)')}</b>${pdbPill(pdbProvLabel(db.provider))}${pdbSvcPills(db.services)}</div>
      <div class="hint" style="font-family:var(--mono)">${esc(db.identifier||'')}</div>
      <div class="pm-row" style="margin:8px 0 0"><label class="hint" for="pdbRole${i}">Papel</label>
        <select id="pdbRole${i}" data-pdb-role="${i}">${pdbRoleOpts(db.role)}</select>
        <button class="btn sm" data-pdb-act="edit" data-pdb-i="${i}">Editar receita</button>
        <button class="btn sm danger" data-pdb-act="del" data-pdb-i="${i}">Remover</button></div>
    </div>`).join('');
  const dets=cands.map((c,i)=>`<div class="pm-card">
      <div class="pm-row" style="margin-bottom:4px"><b>${esc(c.name||c.identifier||'')}</b>${pdbPill(pdbProvLabel(c.provider))}${pdbSvcPills(c.services)}</div>
      <div class="hint" style="font-family:var(--mono)">${esc(c.identifier||'')}</div>
      <div class="hint" style="font-family:var(--mono);font-size:11px;margin-top:4px">${(c.evidence||[]).map(x=>esc(x)).join(' · ')}</div>
      <div class="pm-row" style="margin:8px 0 0"><label class="hint" for="pdbCRole${i}">Papel</label>
        <select id="pdbCRole${i}" data-pdb-crole="${i}">${pdbRoleOpts(c.suggestedRole||'other')}</select>
        <button class="btn sm pri" data-pdb-act="reg" data-pdb-i="${i}">Cadastrar</button></div>
    </div>`).join('');
  const head=`<div class="pm-sec"><div class="pm-row">
      <b>${N?`Encontrei ${N} banco(s) neste código`:'Nada detectado no código — adicione manualmente'}</b>
      <span class="hint">${M} cadastrado(s)</span>
      <button class="btn sm" style="margin-left:auto" data-pdb-act="add">+ Adicionar manualmente</button></div></div>`;
  const secCad=`<div class="pm-sec"><h4 style="margin:0 0 8px">Cadastrados</h4>${cards||'<div class="hint">Nenhum banco cadastrado ainda.</div>'}</div>`;
  const secDet=`<div class="pm-sec"><h4 style="margin:0 0 8px">Detectados</h4>${dets||'<div class="hint">Nenhum candidato novo.</div>'}</div>`;
  const foot=`<div class="pm-sec"><p class="hint">Só builds feitos com o banco Produção podem ser enviados para as lojas. Builds antigos, sem banco registrado, ficam bloqueados enquanto o projeto tiver bancos cadastrados.</p>${M?'':'<p class="hint">Enquanto não houver bancos cadastrados, o envio para as lojas não tem restrição.</p>'}</div>`;
  ctx.body.innerHTML=head+secCad+secDet+foot;
}

function pdbManualRender(ctx){
  const m=ctx.man;
  ctx.body.innerHTML=`<div class="pm-sec">
    <div class="field"><label for="pdbMName">Nome</label><input type="text" id="pdbMName" value="${esc(m.name)}"></div>
    <div class="field"><label for="pdbMProv">Provedor</label><select id="pdbMProv">${pdbProvOpts(m.provider)}</select></div>
    <div class="field"><label for="pdbMIdent">Identificador</label><input type="text" id="pdbMIdent" value="${esc(m.identifier)}" style="font-family:var(--mono)"><span class="hint">Para URL de conexão, o painel salva como digitado.</span></div>
    <div class="field"><label for="pdbMRole">Papel</label><select id="pdbMRole">${pdbRoleOpts(m.role)}</select></div>
  </div>
  <div class="pm-row"><button class="btn sm" data-pdb-act="manBack">Voltar</button><button class="btn sm pri" data-pdb-act="manNext">Continuar para a receita</button></div>`;
}

/* editor de receita: ed = {base (banco), pre, files:[{from,to}], env:[{k,v}]} */
function pdbEditOpen(ctx,db){
  const r=db.recipe||{}, envObj=r.env||{};
  ctx.ed={base:db,pre:r.preBuild||'',files:(r.copyFiles||[]).map(f=>({from:f.from||'',to:f.to||''})),env:Object.keys(envObj).map(k=>({k,v:String(envObj[k])}))};
  ctx.mode='edit';pdbRender(ctx);
}
/* lê o que está digitado no editor para ctx.ed (antes de adicionar/remover linhas, para não perder texto) */
function pdbEditRead(ctx){
  const b=ctx.body, pre=b.querySelector('#pdbEPre');
  if(!pre)return;
  ctx.ed.pre=pre.value;
  ctx.ed.files=[...b.querySelectorAll('[data-pdb-frow]')].map(r=>({from:r.querySelector('[data-pdb-from]').value,to:r.querySelector('[data-pdb-to]').value}));
  ctx.ed.env=[...b.querySelectorAll('[data-pdb-erow]')].map(r=>({k:r.querySelector('[data-pdb-ek]').value,v:r.querySelector('[data-pdb-ev]').value}));
}
function pdbEditRender(ctx){
  const ed=ctx.ed, b=ed.base;
  const files=ed.files.map((f,k)=>`<div class="pm-row" data-pdb-frow>
      <input type="text" data-pdb-from value="${esc(f.from)}" placeholder="origem" style="flex:1;min-width:120px;font-family:var(--mono)">
      <span class="hint">→</span>
      <input type="text" data-pdb-to value="${esc(f.to)}" placeholder="destino" style="flex:1;min-width:120px;font-family:var(--mono)">
      <button class="btn sm danger" data-pdb-act="edDelFile" data-pdb-i="${k}">Remover</button></div>`).join('');
  const envRows=ed.env.map((x,k)=>`<div class="pm-row" data-pdb-erow>
      <input type="text" data-pdb-ek value="${esc(x.k)}" placeholder="CHAVE" style="flex:1;min-width:120px;font-family:var(--mono)">
      <span class="hint">=</span>
      <input type="text" data-pdb-ev value="${esc(x.v)}" placeholder="valor" style="flex:2;min-width:160px;font-family:var(--mono)">
      <button class="btn sm danger" data-pdb-act="edDelEnv" data-pdb-i="${k}">Remover</button></div>`).join('');
  ctx.body.innerHTML=`<div class="pm-sec">
      <p class="hint" style="margin:0 0 10px">Receita de <b>${esc(b.name||'')}</b> (${esc(pdbProvLabel(b.provider))})</p>
      <div class="field"><label for="pdbEPre">Comando antes do build</label><input type="text" id="pdbEPre" value="${esc(ed.pre)}" style="font-family:var(--mono)"></div>
      <p class="hint" style="margin:-4px 0 10px">roda no projeto antes de compilar e escolhe o banco, ex.: npm run build:client:prod</p>
    </div>
    <div class="pm-sec"><h4 style="margin:0 0 4px">Arquivos a copiar</h4>
      <p class="hint" style="margin:0 0 8px">origem → destino, relativos à pasta do projeto</p>
      ${files||'<div class="hint" style="margin-bottom:8px">Nenhum arquivo.</div>'}
      <button class="btn sm" data-pdb-act="edAddFile">+ Adicionar arquivo</button></div>
    <div class="pm-sec"><h4 style="margin:0 0 4px">Variáveis de ambiente</h4>
      <p class="hint" style="margin:0 0 8px">CHAVE = valor</p>
      ${envRows||'<div class="hint" style="margin-bottom:8px">Nenhuma variável.</div>'}
      <button class="btn sm" data-pdb-act="edAddEnv">+ Adicionar variável</button></div>
    <p class="hint">valores ficam salvos no painel (dentro do container)</p>
    <div class="pm-row"><button class="btn sm" data-pdb-act="edBack">Voltar</button><button class="btn sm pri" data-pdb-act="edSave">Salvar receita</button></div>`;
}

/* ---------- ações ---------- */
function pdbManualNext(ctx){
  const g=id=>ctx.body.querySelector('#'+id);
  const name=g('pdbMName').value.trim(), identifier=g('pdbMIdent').value.trim();
  if(!name||!identifier)return toast('Informe o nome e o identificador');
  ctx.ed={base:{name,provider:g('pdbMProv').value,identifier,services:[],role:g('pdbMRole').value,source:'manual'},pre:'',files:[],env:[]};
  ctx.mode='edit';pdbRender(ctx);
}
async function pdbRoleChange(ctx,i,role){
  const db=ctx.st.databases[i];if(!db)return;
  await pdbPost(ctx,{action:'save',database:Object.assign({},db,{role})},'Salvando papel…','Papel atualizado');
  await pdbRefresh(ctx);
}
async function pdbDelete(ctx,db){
  if(!db)return;
  if(!confirm(`Remover o banco "${db.name||db.identifier}"?`))return;
  await pdbPost(ctx,{action:'delete',id:db.id},'Removendo…','Banco removido');
  await pdbRefresh(ctx);
}
async function pdbRegister(ctx,n){
  const c=pdbCandidates(ctx.st)[n];if(!c)return;
  const sel=ctx.body.querySelector('[data-pdb-crole="'+n+'"]');
  const database={name:c.name||c.identifier||'',provider:c.provider,identifier:c.identifier,services:c.services||[],role:sel?sel.value:'other',source:'detected',recipe:c.recipe||{preBuild:'',copyFiles:[],env:{}}};
  await pdbPost(ctx,{action:'save',database},'Cadastrando…','Banco cadastrado');
  await pdbRefresh(ctx);
}
async function pdbEditSave(ctx){
  pdbEditRead(ctx);
  const ed=ctx.ed;
  const files=ed.files.filter(f=>f.from.trim()||f.to.trim()).map(f=>({from:f.from.trim(),to:f.to.trim()}));
  if(files.some(f=>!f.from||!f.to))return toast('Preencha origem e destino de cada arquivo');
  const env={};
  for(const x of ed.env){
    const k=x.k.trim();
    if(!k){if(x.v.trim())return toast('Informe o nome de cada variável de ambiente');continue}
    env[k]=x.v;
  }
  const database=Object.assign({},ed.base,{recipe:{preBuild:ed.pre.trim(),copyFiles:files,env}});
  const r=await pdbPost(ctx,{action:'save',database},'Salvando receita…','Receita salva');
  /* em caso de erro fica no editor, com o que foi digitado */
  if(r)await pdbRefresh(ctx);
}

async function pdbAct(ctx,act,i){
  const n=Number(i);
  if(act==='add'){ctx.man={name:'',provider:'firebase',identifier:'',role:'other'};ctx.mode='manual';return pdbRender(ctx)}
  if(act==='manBack'){ctx.mode='list';return pdbRender(ctx)}
  if(act==='manNext')return pdbManualNext(ctx);
  if(act==='edit')return pdbEditOpen(ctx,ctx.st.databases[n]);
  if(act==='del')return pdbDelete(ctx,ctx.st.databases[n]);
  if(act==='reg')return pdbRegister(ctx,n);
  if(act==='edBack'){ctx.mode='list';return pdbRender(ctx)}
  if(act==='edSave')return pdbEditSave(ctx);
  /* adicionar/remover linhas do editor: lê o digitado antes de redesenhar */
  if(!ctx.ed)return;
  pdbEditRead(ctx);
  if(act==='edAddFile')ctx.ed.files.push({from:'',to:''});
  else if(act==='edDelFile')ctx.ed.files.splice(n,1);
  else if(act==='edAddEnv')ctx.ed.env.push({k:'',v:''});
  else if(act==='edDelEnv')ctx.ed.env.splice(n,1);
  pdbRender(ctx);
}

/* ---------- entrada pública: botão "🗄 Banco de dados" do card do projeto ---------- */
async function projDatabase(project){
  const done=pmBusy('Procurando bancos de dados…');
  let st;
  try{st=await pdbLoad(project)}
  catch(e){return toast(e.message)}
  finally{done()}
  const m=pmModal('🗄 Banco de dados '+project,'',[{label:'Fechar',cls:'',onClick:()=>pmClose()}]);
  const ctx={project,body:m.body,st,mode:'list',ed:null,man:null};
  /* delegação no corpo do modal: o corpo persiste, só o HTML interno é reescrito a cada render */
  m.body.addEventListener('click',e=>{
    const b=e.target.closest?e.target.closest('[data-pdb-act]'):null;
    if(b)pdbAct(ctx,b.getAttribute('data-pdb-act'),b.getAttribute('data-pdb-i'));
  });
  m.body.addEventListener('change',e=>{
    const s=e.target;
    if(s&&s.matches&&s.matches('[data-pdb-role]'))pdbRoleChange(ctx,Number(s.getAttribute('data-pdb-role')),s.value);
  });
  pdbRender(ctx);
}
