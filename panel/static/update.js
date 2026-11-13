/* ---------- Atualização do painel (rodapé da barra lateral + card em Configuração) ----------
   Usa: $, esc, toast, api, pmModal, pmClose (index.html / projects.js).
   Estado: updState = resposta de GET /api/update/check. */
(function(){const s=document.createElement('style');s.id='updCss';s.textContent=`
.upd-warn{background:rgba(245,176,65,.12);border:1px solid var(--warn);border-radius:12px;padding:12px 14px;margin-bottom:12px;font-size:13px}
.upd-bad{background:rgba(255,93,108,.12);border-color:var(--bad);color:var(--bad)}
.upd-list{max-height:260px;overflow:auto;font-family:var(--mono);font-size:12px;background:var(--input);border:1px solid var(--line);border-radius:10px;padding:8px 10px;margin-top:6px}
.upd-grp{margin-top:6px;font-size:12px;color:var(--muted)}
.upd-file{font-family:var(--mono);font-size:12px;padding:1px 0}
.upd-msg{font-size:13px;margin-top:6px}
.upd-err{color:var(--bad);font-size:13px;margin:8px 0}
.upd-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:10px}
#updFoot .btn{margin-top:8px;width:100%;justify-content:center}
`;document.head.appendChild(s)})();

const UPD_INTERVALO=6*3600*1000;
const UPD_LBL={modified:'Alterados',added:'Novos',removed:'Removidos'};
let updState=null;
let updBackups=null;      /* lista de GET /api/update/backups; null = carregando */
let updBackupsErr='';

function updData(iso){
  if(!iso)return '—';
  const d=new Date(iso);
  return isNaN(d)?'—':d.toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'});
}
function updHora(epoch){
  if(!epoch)return '—';
  const d=new Date(epoch*1000);
  return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
}
/* data/hora local a partir de epoch em segundos (campo date dos backups) */
function updDataEpoch(epoch){
  if(!epoch)return '—';
  const d=new Date(epoch*1000);
  return isNaN(d)?'—':d.toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'});
}

/* GET /api/update/check; force=true ignora o cache do servidor. */
async function updCheck(force){
  try{
    updState=await api('/api/update/check'+(force?'?force=1':''));
  }catch(e){
    /* falha de rede ou do próprio painel: guarda o erro para o card mostrar */
    updState={...(updState||{}),error:e.message||'Falha ao verificar atualização',upToDate:false,latest:(updState&&updState.latest)||null};
  }
  updPaint();
  if(force){
    if(updState.error)toast(updState.error);
    else if(updState.upToDate)toast('Painel em dia');
    else toast((updState.changes||[]).length+' arquivo(s) mudam no GitHub');
  }
}

/* Atualiza o rodapé (#updFoot) e o card (#updCard). */
function updPaint(){
  const s=updState||{};
  const foot=$('updFoot');
  if(foot){
    foot.innerHTML=(!s.upToDate&&!s.error&&s.latest)
      ?'<button class="btn sm pri" onclick="updOpen()">⬆ Atualização disponível</button>'
      :'';
  }
  updPaintCard();
  updLoadBackups();
}

/* Repinta só o card (#updCard). */
function updPaintCard(){
  const card=$('updCard');
  if(card)card.innerHTML=updCardHtml();
}

/* Card = resumo da atualização + seção "Versões anteriores". */
function updCardHtml(){
  return updCardMainHtml()+updBackupsHtml();
}

function updCardMainHtml(){
  const s=updState;
  if(!s)return '<h3>Atualização do painel</h3><p class="hint">Verificando…</p>';
  const inst=s.installed||{}, L=s.latest;
  const instTxt=`v${esc(inst.version||'?')} · ${inst.commit?esc(inst.commit.slice(0,7)):'commit desconhecido'}`;
  const novoTxt=L
    ?`No GitHub (main): v${esc(L.version||'?')} · <a href="${esc(L.url||'#')}" target="_blank" rel="noopener">${esc(L.short||'')}</a> · ${esc(updData(L.date))} · ${esc(L.message||'')}`
    :'No GitHub (main): —';
  let status;
  if(s.error)status='';
  else if(s.upToDate)status='<span class="pill ok"><i></i>Em dia</span>';
  else status=`<span class="pill warn"><i></i>${(s.changes||[]).length} arquivo(s) mudam</span>`;
  const erro=s.error?`<div class="upd-err">${esc(s.error)}</div>`:'';
  const podeAtualizar=!!(L&&!s.error&&!s.upToDate);
  return `<h3>Atualização do painel</h3>
    <div class="hint">Instalado: ${instTxt}</div>
    <div class="hint" style="margin-top:4px">${novoTxt}</div>
    <div class="upd-row">${status}<span class="hint">Verificado às ${esc(updHora(s.checkedAt))}</span></div>
    ${erro}
    <div class="upd-row">
      <button class="btn sm" onclick="updCheck(true)">Verificar agora</button>
      <button class="btn sm pri" onclick="updOpen()" ${podeAtualizar?'':'disabled'}>⬆ Atualizar</button>
    </div>`;
}

/* Modal de confirmação: mostra o que muda; bloqueia se houver tarefa rodando. */
async function updOpen(){
  const s=updState;
  if(!s||!s.latest){toast('Sem versão nova para mostrar. Clique em "Verificar agora".');return}
  let rodando=[];
  try{
    const jobs=await api('/api/jobs');
    rodando=(Array.isArray(jobs)?jobs:[]).filter(j=>!j.ended);
  }catch(e){
    toast('Não consegui checar as tarefas: '+e.message);
    return;
  }
  const inst=s.installed||{}, L=s.latest, ch=s.changes||[];

  /* lista agrupada, até 40 linhas */
  const grupos={modified:[],added:[],removed:[]};
  ch.forEach(c=>{(grupos[c.status]||(grupos[c.status]=[])).push(c.path)});
  let mostrados=0, linhas='';
  for(const k of ['modified','added','removed']){
    const lista=grupos[k]||[];
    if(!lista.length)continue;
    if(mostrados>=40)break;
    linhas+=`<div class="upd-grp"><b>${UPD_LBL[k]} (${lista.length})</b></div>`;
    for(const p of lista){
      if(mostrados>=40)break;
      mostrados++;
      linhas+=`<div class="upd-file">${esc(p)}</div>`;
    }
  }
  const resto=ch.length-mostrados;
  if(resto>0)linhas+=`<div class="hint" style="margin-top:6px">+${resto} arquivo(s)</div>`;

  /* mudanças fora de panel/ exigem rebuild da imagem */
  let imagemHtml='';
  if(Array.isArray(s.imageChanges)&&s.imageChanges.length){
    imagemHtml=`<div class="upd-warn">Esta atualização também muda ${s.imageChanges.map(x=>`<b>${esc(x)}</b>`).join(', ')}: depois rode <code>docker compose up -d --build</code> no PC para aplicar.</div>`;
  }else if(s.imageChanges===null){
    imagemHtml='<div class="hint" style="margin-bottom:10px">Não dá para saber se a imagem Docker mudou (commit instalado desconhecido).</div>';
  }

  const ocupado=rodando.length>0;
  const ocupadoHtml=ocupado?'<div class="upd-warn upd-bad">Há tarefas em andamento: espere terminarem para atualizar o painel.</div>':'';

  const html=`
    <div class="pm-sec">
      <div class="hint">Instalado: <b>v${esc(inst.version||'?')}</b> · ${inst.commit?esc(inst.commit.slice(0,7)):'commit desconhecido'}</div>
      <div class="hint" style="margin-top:4px">Novo: <b>v${esc(L.version||'?')}</b> · <a href="${esc(L.url||'#')}" target="_blank" rel="noopener">${esc(L.short||'')}</a> · ${esc(updData(L.date))}</div>
      <div class="upd-msg">${esc(L.message||'')}</div>
    </div>
    ${ocupadoHtml}
    ${imagemHtml}
    <div class="pm-sec">
      <b>Arquivos que mudam (${ch.length})</b>
      <div class="upd-list">${linhas||'<div class="hint">Nenhum arquivo</div>'}</div>
    </div>
    <div class="hint">O painel reinicia sozinho (≈5 s). Logins, projetos e builds não são afetados. Um backup do painel atual fica em /root/.xtool-panel-backup.</div>`;

  pmModal('⬆ Atualizar o painel',html,[
    {label:'Cancelar',onClick:()=>pmClose()},
    {label:'⬆ Atualizar agora',cls:'pri',id:'updGo',onClick:()=>updApply()}
  ]);
  const btn=document.getElementById('updGo');
  if(btn&&ocupado)btn.disabled=true;
}

/* Confirmação: POST /api/update/apply, depois espera o painel voltar com o novo commit. */
async function updApply(){
  const s=updState;
  if(!s||!s.latest)return;
  const sha=s.latest.sha;
  const btn=document.getElementById('updGo');
  const corpo=document.querySelector('.pm-back .pm-body');
  if(btn){btn.disabled=true;btn.textContent='Atualizando…'}
  try{
    await api('/api/update/apply',{sha});
  }catch(e){
    if(corpo)corpo.insertAdjacentHTML('beforeend',`<div class="upd-warn upd-bad">${esc(e.message||'Falha ao atualizar')}</div>`);
    if(btn){btn.disabled=false;btn.textContent='⬆ Atualizar agora'}
    return;
  }
  if(corpo)corpo.innerHTML=`<div class="upd-warn">Atualizando… o painel vai reiniciar. Não feche esta janela.</div><div class="hint" id="updWait">Aguardando o painel voltar…</div>`;
  updEsperarVoltar(sha);
}

/* Consulta /api/version a cada 1,5 s até o painel voltar (máx. 90 s).
   esperado = commit que tem que aparecer; null = espera o painel cair e voltar de novo. */
function updEsperarVoltar(esperado){
  const t0=Date.now();
  let caiu=false;
  const tentar=async()=>{
    try{
      const v=await api('/api/version');
      if(esperado?v.commit===esperado:caiu){location.reload();return}
    }catch(e){
      /* painel ainda reiniciando */
      caiu=true;
    }
    if(Date.now()-t0>=90000){
      const w=document.getElementById('updWait');
      if(w)w.textContent='O painel não voltou em 90 s: veja `docker logs xtool`.';
      return;
    }
    setTimeout(tentar,1500);
  };
  setTimeout(tentar,1500);
}

/* GET /api/update/backups → [{name,date,commit,short,version}] (mais novo primeiro). */
async function updLoadBackups(){
  try{
    const l=await api('/api/update/backups');
    updBackups=Array.isArray(l)?l:[];
    updBackupsErr='';
  }catch(e){
    updBackups=[];
    updBackupsErr=e.message||'Falha ao carregar as versões anteriores';
  }
  updPaintCard();
}

/* Seção "Versões anteriores" do card. */
function updBackupsHtml(){
  let corpo;
  if(updBackupsErr)corpo=`<div class="upd-err">${esc(updBackupsErr)}</div>`;
  else if(updBackups===null)corpo='<div class="hint">Carregando…</div>';
  else if(!updBackups.length)corpo='<div class="hint">Nenhuma versão anterior ainda (os backups aparecem depois da primeira atualização).</div>';
  else corpo=updBackups.map(b=>`
      <div class="upd-row" style="justify-content:space-between;margin-top:6px">
        <span>${esc(updDataEpoch(b.date))}</span>
        <span>v${esc(b.version||'?')}</span>
        <span class="hint">${esc(b.short||'commit desconhecido')}</span>
        <button class="btn sm" data-name="${esc(b.name||'')}" onclick="updRestoreOpen(this.dataset.name)">↩ Restaurar</button>
      </div>`).join('');
  return `<div style="margin-top:16px;border-top:1px solid var(--line);padding-top:12px">
    <b>Versões anteriores</b>
    <div class="hint" style="margin-top:4px">Backups do painel feitos nas atualizações (guardamos os 3 mais recentes).</div>
    ${corpo}
  </div>`;
}

/* Modal de restauração: bloqueia se houver tarefa rodando (mesma lógica do updOpen). */
/* Procura o backup pelo name (não pelo índice); null se não estiver mais na lista. */
function updBackupPorNome(name){
  return (updBackups||[]).find(x=>x.name===name)||null;
}

async function updRestoreOpen(name){
  const b=updBackupPorNome(name);
  if(!b){toast('Backup não encontrado, recarregue');return}
  let rodando=[];
  try{
    const jobs=await api('/api/jobs');
    rodando=(Array.isArray(jobs)?jobs:[]).filter(j=>!j.ended);
  }catch(e){
    toast('Não consegui checar as tarefas: '+e.message);
    return;
  }
  const ocupado=rodando.length>0;
  const ocupadoHtml=ocupado?'<div class="upd-warn upd-bad">Há tarefas em andamento: espere terminarem para restaurar o painel.</div>':'';
  const html=`
    <div class="pm-sec">
      <div class="hint">Voltar para: <b>v${esc(b.version||'?')}</b> · ${esc(b.short||'commit desconhecido')} · ${esc(updDataEpoch(b.date))}</div>
    </div>
    ${ocupadoHtml}
    <div class="upd-warn">O painel volta para esta versão. A versão atual vira um backup, e ela continua disponível na lista para voltar depois.</div>
    <div class="hint">O painel reinicia sozinho (≈5 s). Logins, projetos e builds não são afetados.</div>`;

  pmModal('↩ Restaurar versão do painel',html,[
    {label:'Cancelar',onClick:()=>pmClose()},
    {label:'↩ Restaurar agora',cls:'pri',id:'updRestGo',onClick:()=>updRestoreApply(name)}
  ]);
  const btn=document.getElementById('updRestGo');
  if(btn&&ocupado)btn.disabled=true;
}

/* Confirmação: POST /api/update/restore {name}, depois espera o painel voltar. */
async function updRestoreApply(name){
  const btn=document.getElementById('updRestGo');
  const corpo=document.querySelector('.pm-back .pm-body');
  const b=updBackupPorNome(name);
  if(!b){
    if(corpo)corpo.insertAdjacentHTML('beforeend','<div class="upd-warn upd-bad">Backup não encontrado, recarregue</div>');
    return;
  }
  if(btn){btn.disabled=true;btn.textContent='Restaurando…'}
  try{
    await api('/api/update/restore',{name:b.name});
  }catch(e){
    if(corpo)corpo.insertAdjacentHTML('beforeend',`<div class="upd-warn upd-bad">${esc(e.message||'Falha ao restaurar')}</div>`);
    if(btn){btn.disabled=false;btn.textContent='↩ Restaurar agora'}
    return;
  }
  if(corpo)corpo.innerHTML=`<div class="upd-warn">Restaurando… o painel vai reiniciar. Não feche esta janela.</div><div class="hint" id="updWait">Aguardando o painel voltar…</div>`;
  updEsperarVoltar(b.commit||null);
}

/* Verificação automática: ao abrir (3 s depois) e a cada 6 h. */
setTimeout(()=>updCheck(false),3000);
setInterval(()=>updCheck(false),UPD_INTERVALO);
