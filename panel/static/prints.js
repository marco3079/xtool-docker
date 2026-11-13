/* ---------- Prints automáticos (projetos web com build estático) ----------
   script clássico carregado depois de avaliacoes.js e testes.js (index.html).
   Usa os globais: $, esc, toast, api, go (index.html), pmModal, pmClose, pmCur, pmBusy, pmFmtDate (projects.js).
   Só globais com prefixo pr (e prAbrir).
   Rotas: GET /api/prints/status, POST /api/prints/install, GET|POST /api/prints/config,
   POST /api/prints/run, GET /api/prints/runs, GET /api/prints/files, POST /api/prints/upload.
   Miniaturas: GET /api/download?root=work&path=<arquivo relativo a /work>&inline=1 (rota existente).
   Acompanhar tarefas: GET /api/jobs (campos id, running, code). */

(function prInitStyle(){
  if(document.getElementById('prStyle'))return;
  const s=document.createElement('style');s.id='prStyle';
  s.textContent=`
.pr-card{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:12px}
.pr-card h4{margin:0 0 6px;font-size:14px}
.pr-warn{border-color:var(--warn);background:rgba(245,176,65,.12)}
.pr-in{width:100%;box-sizing:border-box;padding:8px 10px;border-radius:9px;border:1px solid var(--line);background:var(--input);color:var(--text);font:inherit}
.pr-in textarea,textarea.pr-in{resize:vertical}
.pr-mono{font-family:var(--mono);font-size:12px}
.pr-col{width:48px;height:36px;padding:2px;border:1px solid var(--line);border-radius:9px;background:var(--input)}
.pr-grid2{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px 12px}
.pr-chks{display:flex;flex-wrap:wrap;gap:8px 16px;margin-bottom:6px}
.pr-chk{display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer}
.pr-scr{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:10px;background:var(--panel)}
.pr-scr-head{display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap}
.pr-scr-head b{flex:1}
.pr-loc{margin:10px 0 2px;font-size:13px}
.pr-sz{margin:6px 0 4px}
.pr-thumbs{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px;margin:0 0 10px}
.pr-item{display:flex;flex-direction:column;gap:4px;font-size:12px;cursor:pointer;border:1px solid var(--line);border-radius:10px;padding:6px;background:var(--panel2);min-width:0}
.pr-item img{width:100%;height:auto;max-height:200px;object-fit:contain;border-radius:6px;background:#000}
.pr-item span{display:flex;align-items:center;gap:6px;min-width:0}
.pr-prog{font-size:13px;margin-top:8px}
.pr-prog.ok{color:var(--ok)}
.pr-prog.bad{color:var(--bad)}
.pr-err{color:var(--bad);font-size:13px;margin:6px 0 0}
.pr-up{margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}
`;
  document.head.appendChild(s)})();

/* ---------- constantes ---------- */
const PR_LIMITE=10;
const PR_SIZES=[
  {id:'iphone69',label:'iPhone 6,9"',w:1320,h:2868},
  {id:'iphone65',label:'iPhone 6,5"',w:1284,h:2778},
  {id:'ipad13',label:'iPad 13"',w:2064,h:2752},
  {id:'playPhone',label:'Celular (Play)',w:1080,h:1920},
  {id:'playTab7',label:'Tablet 7" (Play)',w:1200,h:1920},
  {id:'playTab10',label:'Tablet 10" (Play)',w:1600,h:2560}];
const PR_STYLE_LBL={plain:'Print puro',caption:'Com fundo e legenda'};
const PR_ACTION_TYPES=['click','type','wait','eval'];

/* estado do popup aberto (um por vez). Campos:
   project, el (pm-back), body (pm-body), status (GET /api/prints/status), base (forma de formulário da config salva),
   savedKey (JSON de base), detected (webDir detectada), runs ([{id,at,count}]), run (id escolhido), files (manifest),
   upVersion, upReplace, upMsg (HTML), prog ({text,tone}), gerando, tmr (intervalo de acompanhamento), polling */
let prS=null;

function prAlive(S){return !!(S&&pmCur&&pmCur.el===S.el)}
function prErrMsg(e){return (e&&e.message)||String(e)}

/* ---------- conversões: config do servidor <-> formulário (tudo texto, para comparar com a tela) ---------- */
function prToRaw(c){
  const cfgSizes=c.sizes||[];
  return {
    webDir:c.webDir||'', build:c.build||'',
    style:c.style||'plain', background:c.background||'#1e1e2e', textColor:c.textColor||'#ffffff', font:c.font||'system-ui',
    sizes:PR_SIZES.map(s=>s.id).filter(id=>cfgSizes.includes(id)),
    localesText:(c.locales||[]).join(', '), setLocale:c.setLocale||'',
    screens:(c.screens||[]).map(s=>({
      name:s.name||'', path:s.path||'', wait:String(s.wait==null?1500:s.wait),
      actionsRaw:JSON.stringify(s.actions||[]),
      captionsRaw:Object.entries(s.captions||{}).map(([k,v])=>k+'='+v).join('\n')}))};
}

/* lê o que está na tela (mesma ordem de chaves de prToRaw; tudo string, sem validar) */
function prFromDom(S){
  const b=S.body;
  const g=k=>{const e=b.querySelector(`[data-g="${k}"]`);return e?e.value:''};
  return {
    webDir:g('webDir'), build:g('build'), style:g('style')||'plain',
    background:g('background'), textColor:g('textColor'), font:g('font'),
    sizes:PR_SIZES.map(s=>s.id).filter(id=>{const e=b.querySelector(`[data-g="size"][value="${id}"]`);return !!(e&&e.checked)}),
    localesText:g('locales'), setLocale:g('setLocale'),
    screens:[...b.querySelectorAll('[data-pr-scr]')].map(el=>{
      const f=k=>{const e=el.querySelector(`[data-f="${k}"]`);return e?e.value:''};
      return {name:f('name'),path:f('path'),wait:f('wait'),actionsRaw:f('actionsRaw'),captionsRaw:f('captionsRaw')}})};
}

/* monta o objeto de config a enviar; lança Error em PT se algo estiver inválido */
function prCheckAcao(a,n,j){
  const erro=m=>new Error(`Tela ${n}, ação ${j+1}: ${m}`);
  if(!a||typeof a!=='object'||Array.isArray(a))throw erro('deve ser um objeto, como {"type":"click","selector":"#menu"}');
  if(!PR_ACTION_TYPES.includes(a.type))throw erro('tipo desconhecido (use click, type, wait ou eval)');
  if(a.type==='click'&&!a.selector)throw erro('falta o seletor (selector)');
  if(a.type==='type'&&(!a.selector||a.text==null))throw erro('faltam selector e text');
  if(a.type==='wait'&&typeof a.ms!=='number')throw erro('falta ms (número)');
  if(a.type==='eval'&&!a.js)throw erro('falta o js');
}
function prParseCfg(raw){
  const screens=raw.screens.map((s,i)=>{
    const n=i+1;
    let actions=[];
    const t=(s.actionsRaw||'').trim();
    if(t){
      try{actions=JSON.parse(t)}catch(e){throw new Error(`Tela ${n}: as ações precisam ser um JSON válido (uma lista).`)}
      if(!Array.isArray(actions))throw new Error(`Tela ${n}: as ações precisam ser uma lista [ ].`);
      actions.forEach((a,j)=>prCheckAcao(a,n,j))}
    const captions={};
    (s.captionsRaw||'').split('\n').forEach(line=>{
      const l=line.trim();if(!l)return;
      const k=l.indexOf('=');
      if(k<1)throw new Error(`Tela ${n}: legenda inválida "${l}" (use código=texto, uma por linha).`);
      captions[l.slice(0,k).trim()]=l.slice(k+1).trim()});
    const w=String(s.wait||'').trim();
    const wait=w===''?1500:Number(w);
    if(isNaN(wait))throw new Error(`Tela ${n}: a espera precisa ser um número de ms.`);
    return {name:(s.name||'').trim(),path:(s.path||'').trim(),wait,actions,captions}});
  return {
    webDir:raw.webDir.trim(),build:raw.build.trim(),style:raw.style,
    background:raw.background.trim(),textColor:raw.textColor.trim(),font:raw.font.trim(),
    sizes:raw.sizes,
    locales:raw.localesText.split(/[\s,]+/).filter(Boolean),
    setLocale:raw.setLocale,
    screens};
}
function prMudou(S){return JSON.stringify(prFromDom(S))!==S.savedKey}
function prNovaTela(n){return {name:'Tela '+(n+1),path:'/',wait:'1500',actionsRaw:'[]',captionsRaw:''}}

/* ---------- abertura ---------- */
async function prAbrir(project){
  const done=pmBusy('Abrindo os prints…');
  let st;
  try{st=await api('/api/prints/status')}
  catch(e){toast(prErrMsg(e));return}
  finally{done()}
  const m=pmModal('📸 Prints automáticos — '+project,'',[{label:'Fechar',cls:'',onClick:()=>pmClose()}]);
  const box=m.el.querySelector('.pm-box');if(box)box.style.maxWidth='min(900px,96vw)';
  const S={project,el:m.el,body:m.body,status:st,base:null,savedKey:'',detected:'',
    runs:[],run:'',files:[],upVersion:'',upReplace:false,upMsg:'',prog:null,gerando:false,tmr:null,polling:false};
  prS=S;
  m.body.addEventListener('click',prOnClick);
  m.body.addEventListener('change',prOnChange);
  m.body.addEventListener('input',prOnInput);
  if(!st.installed||st.libsOk===false){prRender(S,null);return}
  S.body.innerHTML='<p class="hint">Carregando a configuração…</p>';
  try{await prCarregar(S)}
  catch(e){S.body.innerHTML=`<p class="pr-err">${esc(prErrMsg(e))}</p>`}}

/* carrega config e execuções do servidor e desenha a tela cheia */
async function prCarregar(S){
  const c=await api('/api/prints/config?project='+encodeURIComponent(S.project));
  S.base=prToRaw(c);
  S.detected=c.detectedWebDir||'';
  S.savedKey=JSON.stringify(S.base);
  await prRecarregarRuns(S,S.run);
  prRender(S,S.base)}

async function prRecarregarRuns(S,preferido){
  const runs=await api('/api/prints/runs?project='+encodeURIComponent(S.project));
  S.runs=Array.isArray(runs)?runs:[];
  const ids=S.runs.map(r=>r.id);
  S.run=ids.includes(preferido)?preferido:(ids[0]||'');
  S.upMsg='';
  await prCarregarArquivos(S)}

async function prCarregarArquivos(S){
  S.files=[];
  if(!S.run)return;
  const r=await api(`/api/prints/files?project=${encodeURIComponent(S.project)}&run=${encodeURIComponent(S.run)}`);
  S.files=Array.isArray(r)?r:[]}

/* ---------- desenho ---------- */
/* raw = forma de formulário a exibir (null quando a tela é de instalação) */
function prRender(S,raw){
  if(!S.status||!S.status.installed){S.body.innerHTML=prInstallHtml(S);return}
  if(S.status.libsOk===false){S.body.innerHTML=prInstallHtml(S);return}
  const c=raw||S.base;
  if(!c){S.body.innerHTML='<p class="hint">Carregando a configuração…</p>';return}
  S.body.innerHTML=`
    <div class="pr-card">
      <h4>Configuração</h4>
      ${prCfgHtml(S,c)}
      <div class="pm-row"><button class="btn pri sm" data-pr="save">💾 Salvar configuração</button></div>
    </div>
    <div class="pr-card">
      <div class="pm-row" style="justify-content:space-between">
        <h4 style="margin:0">Gerar prints</h4>
        <span class="pm-row" style="margin:0"><button class="btn sm" data-pr="tarefas">Ver em Tarefas</button><button class="btn pri sm" data-pr="run" ${S.gerando?'disabled':''}>▶ Gerar prints</button></span>
      </div>
      <p class="hint">Usa a configuração salva (salve antes de gerar). A geração roda como tarefa e a saída aparece em Tarefas.</p>
      <div data-pr-prog>${prProgHtml(S.prog)}</div>
    </div>
    <div class="pr-card">
      <h4>Resultados</h4>
      <div data-pr-res>${prResHtml(S)}</div>
    </div>`}

function prInstallHtml(S){
  const libs=!!(S.status&&S.status.installed&&S.status.libsOk===false);
  const corpo=libs
    ? `<h4>Bibliotecas do sistema sumiram</h4>
       <p class="hint">O container foi recriado e as bibliotecas do sistema (apt) sumiram. O Chromium continua baixado: basta reinstalar as dependências.</p>
       <div class="pm-row"><button class="btn pri sm" data-pr="install">🔧 Reinstalar dependências</button></div>`
    : `<h4>Chromium não instalado</h4>
       <p class="hint">Os prints são tirados com um Chromium headless (playwright-core). A instalação baixa cerca de 150 MB uma vez e guarda no volume do painel: não precisa reconstruir a imagem.</p>
       <div class="pm-row"><button class="btn pri sm" data-pr="install">⬇ Instalar Chromium</button></div>`;
  return `<div class="pr-card${libs?' pr-warn':''}">${corpo}<div data-pr-prog>${prProgHtml(S.prog)}</div></div>`}

function prCfgHtml(S,c){
  const caption=c.style==='caption';
  const ph='Detectar automaticamente'+(S.detected?' ('+S.detected+')':'');
  const estilos=Object.entries(PR_STYLE_LBL).map(([k,l])=>`<option value="${k}" ${k===c.style?'selected':''}>${esc(l)}</option>`).join('');
  const tamanhos=PR_SIZES.map(s=>`<label class="pr-chk"><input type="checkbox" data-g="size" value="${s.id}" ${c.sizes.includes(s.id)?'checked':''}> ${esc(s.label)} <span class="hint">${s.w}×${s.h} px</span></label>`).join('');
  const telas=c.screens.map((s,i)=>prScrHtml(s,i,c.screens.length,caption)).join('')
    || '<p class="hint">Nenhuma tela ainda. Adicione ao menos uma.</p>';
  return `
    <div class="pr-grid2">
      <div class="field"><label>Pasta do site</label><input type="text" class="pr-in" data-g="webDir" value="${esc(c.webDir)}" placeholder="${esc(ph)}"><span class="hint">Pasta com o index.html do build estático. Vazio = detectar.</span></div>
      <div class="field"><label>Script de build (opcional)</label><input type="text" class="pr-in" data-g="build" value="${esc(c.build)}" placeholder="ex.: build:web"><span class="hint">Roda com npm run antes dos prints. Vazio = não roda.</span></div>
    </div>
    <div class="field"><label>Estilo</label><select class="pr-in" data-g="style" style="max-width:320px">${estilos}</select></div>
    <div class="pr-grid2" data-pr-capstyle ${caption?'':'hidden'}>
      <div class="field"><label>Cor de fundo</label><input type="color" class="pr-col" data-g="background" value="${esc(c.background)}"></div>
      <div class="field"><label>Cor do texto</label><input type="color" class="pr-col" data-g="textColor" value="${esc(c.textColor)}"></div>
      <div class="field"><label>Fonte</label><input type="text" class="pr-in" data-g="font" value="${esc(c.font)}" placeholder="system-ui"></div>
    </div>
    <div class="field"><label>Tamanhos</label><div class="pr-chks">${tamanhos}</div></div>
    <div class="field"><label>Idiomas</label><input type="text" class="pr-in" data-g="locales" value="${esc(c.localesText)}" placeholder="ex.: pt-BR, en-US"><span class="hint">Códigos separados por vírgula. Vazio = os idiomas das lojas vinculadas ao projeto.</span></div>
    <div class="field"><label>JS para trocar o idioma antes de cada tela (opcional)</label><textarea class="pr-in pr-mono" rows="2" data-g="setLocale" placeholder="localStorage.setItem('lang', locale)">${esc(c.setLocale)}</textarea><span class="hint">Recebe a variável locale e roda antes de cada tela.</span></div>
    <div class="field"><label>Telas (máximo ${PR_LIMITE})</label></div>
    ${telas}
    <div class="pm-row"><button class="btn sm" data-pr="add" ${c.screens.length>=PR_LIMITE?'disabled':''}>➕ Adicionar tela</button></div>`}

function prScrHtml(s,i,total,caption){
  return `
    <div class="pr-scr" data-pr-scr>
      <div class="pr-scr-head"><b>Tela ${i+1}</b>
        <button class="btn sm" data-pr="up" data-i="${i}" ${i===0?'disabled':''} title="Subir">↑</button>
        <button class="btn sm" data-pr="down" data-i="${i}" ${i===total-1?'disabled':''} title="Descer">↓</button>
        <button class="btn sm" data-pr="rm" data-i="${i}" title="Remover tela">✕ Remover</button></div>
      <div class="pr-grid2">
        <div class="field"><label>Nome</label><input type="text" class="pr-in" data-f="name" value="${esc(s.name)}"></div>
        <div class="field"><label>Rota (/rota ou #hash)</label><input type="text" class="pr-in" data-f="path" value="${esc(s.path)}" placeholder="/"></div>
        <div class="field"><label>Espera (ms)</label><input type="number" class="pr-in" data-f="wait" min="0" value="${esc(s.wait)}"></div>
      </div>
      <div class="field"><label>Ações (lista JSON, opcional)</label><textarea class="pr-in pr-mono" rows="2" data-f="actionsRaw" placeholder='[{"type":"click","selector":"#menu"}]'>${esc(s.actionsRaw)}</textarea><span class="hint">Tipos: click (selector) · type (selector, text) · wait (ms) · eval (js).</span></div>
      <div class="field" data-pr-cap ${caption?'':'hidden'}><label>Legendas (uma por idioma: código=texto)</label><textarea class="pr-in" rows="2" data-f="captionsRaw" placeholder="pt-BR=Acompanhe suas contas">${esc(s.captionsRaw)}</textarea></div>
    </div>`}

function prProgHtml(p){return p?`<div class="pr-prog ${esc(p.tone||'')}">${esc(p.text)}</div>`:''}
function prProg(S,text,tone){
  S.prog=text?{text,tone:tone||''}:null;
  const el=S.body.querySelector('[data-pr-prog]');
  if(el)el.innerHTML=prProgHtml(S.prog)}

/* execuções, galeria e envio para a loja */
function prRunLabel(r){
  const m=/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})$/.exec(r.id||'');
  const quando=m?`${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}:${m[6]}`:(r.id||'');
  return `${quando} · ${r.count||0} imagem(ns)`}

function prResHtml(S){
  const opts=S.runs.length
    ? S.runs.map(r=>`<option value="${esc(r.id)}" ${r.id===S.run?'selected':''}>${esc(prRunLabel(r))}</option>`).join('')
    : '<option value="">nenhuma execução</option>';
  return `
    <div class="pm-row"><label>Execução</label><select class="pr-in" data-g="run" style="max-width:380px" ${S.runs.length?'':'disabled'}>${opts}</select></div>
    <div data-pr-gal>${prGalHtml(S)}</div>
    ${S.files.length?prUpHtml(S):''}
    <div data-pr-up>${S.upMsg||''}</div>`}

function prGalHtml(S){
  if(!S.run)return '<p class="hint">Nenhuma execução ainda. Clique em "Gerar prints".</p>';
  if(!S.files.length)return '<p class="hint">Esta execução não tem imagens.</p>';
  const locs=new Map();
  S.files.forEach(f=>{
    const l=f.locale||'', sz=f.size||'';
    if(!locs.has(l))locs.set(l,new Map());
    const m=locs.get(l);
    if(!m.has(sz))m.set(sz,[]);
    m.get(sz).push(f)});
  let out='';
  locs.forEach((sizes,loc)=>{
    out+=`<div class="pr-loc"><b>${esc(loc)}</b></div>`;
    sizes.forEach((arr,sz)=>{
      const sd=PR_SIZES.find(x=>x.id===sz);
      out+=`<div class="hint pr-sz">${esc(sd?sd.label:sz)}</div><div class="pr-thumbs">${arr.map(prItemHtml).join('')}</div>`})});
  return out}

function prItemHtml(f){
  const src='/api/download?root=work&path='+encodeURIComponent(f.file)+'&inline=1';
  return `<label class="pr-item"><img src="${esc(src)}" loading="lazy" alt="${esc(f.screen||'')}"><span><input type="checkbox" data-pr-pick value="${esc(f.file)}" checked> ${esc(f.screen||'')}</span></label>`}

function prUpHtml(S){
  return `
    <div class="pr-up">
      <h4>Enviar para a loja</h4>
      <div class="field" style="max-width:320px"><label>Versão da loja (exatamente como está na loja)</label><input type="text" class="pr-in" data-g="version" value="${esc(S.upVersion||'')}" placeholder="ex.: 1.8.0"></div>
      <label class="pr-chk"><input type="checkbox" data-g="replace" ${S.upReplace?'checked':''}> Substituir as imagens atuais (apaga as desse tipo e idioma antes de enviar)</label>
      <p class="hint" style="margin-top:6px">App Store: até 10 por tipo. Google Play: até 8 por tipo. O excedente não é enviado e aparece nos erros.</p>
      <div class="pm-row" style="margin-top:8px"><button class="btn pri sm" data-pr="send">⬆ Enviar selecionadas</button></div>
    </div>`}

function prResRepaint(S){
  const el=S.body.querySelector('[data-pr-res]');
  if(el)el.innerHTML=prResHtml(S)}

/* ---------- ações ---------- */
async function prSalvar(S,btn){
  let cfg;
  try{cfg=prParseCfg(prFromDom(S))}catch(e){toast(prErrMsg(e));return}
  btn.disabled=true;
  try{
    const c=await api('/api/prints/config',{project:S.project,config:cfg});
    S.base=prToRaw(c);
    S.detected=c.detectedWebDir||'';
    S.savedKey=JSON.stringify(S.base);
    toast('Configuração salva');
    prRender(S,S.base)}
  catch(e){toast(prErrMsg(e));btn.disabled=false}}

async function prGerar(S,btn){
  if(prMudou(S)){toast('Salve a configuração antes de gerar os prints');return}
  btn.disabled=true;
  try{
    const r=await api('/api/prints/run',{project:S.project});
    prProg(S,'Gerando prints… a saída aparece em Tarefas.','');
    prEsperarJob(S,r.job,r.run);
    S.gerando=true;
    prRender(S,prFromDom(S))}
  catch(e){toast(prErrMsg(e));btn.disabled=false}}

/* acompanha o job da geração (GET /api/jobs) até terminar e recarrega as execuções */
function prEsperarJob(S,jobId,runId){
  clearInterval(S.tmr);
  S.tmr=setInterval(async()=>{
    if(!prAlive(S)){clearInterval(S.tmr);return}
    if(S.polling)return;
    S.polling=true;
    try{
      const jobs=await api('/api/jobs');
      const j=(Array.isArray(jobs)?jobs:[]).find(x=>x.id===jobId);
      if(j&&j.running)return;
      clearInterval(S.tmr);
      S.gerando=false;
      const ok=!!j&&j.code===0;
      try{await prRecarregarRuns(S,runId)}catch(e){toast(prErrMsg(e))}
      if(!prAlive(S)){toast(ok?'Prints gerados':'A geração de prints terminou com erro');return}
      prProg(S,ok?'Prints gerados. Escolha a execução abaixo para revisar e enviar.':'A geração terminou com erro (veja a saída em Tarefas).',ok?'ok':'bad');
      prRender(S,prFromDom(S))}
    catch(e){/* falha de rede: tenta de novo no próximo tick */}
    finally{S.polling=false}},3000)}

async function prInstalar(S,btn){
  btn.disabled=true;
  try{
    const r=await api('/api/prints/install',{});
    toast('Instalação iniciada: acompanhe em Tarefas');
    prProg(S,'Instalando… acompanhe a saída em Tarefas. Verifico a cada 5 s.','');
    prEsperarInstalacao(S,r.job)}
  catch(e){toast(prErrMsg(e));btn.disabled=false}}

/* verifica /api/prints/status e a tarefa a cada 5 s; pronto quando instalado e com bibliotecas */
function prEsperarInstalacao(S,jobId){
  clearInterval(S.tmr);
  S.tmr=setInterval(async()=>{
    if(!prAlive(S)){clearInterval(S.tmr);return}
    if(S.polling)return;
    S.polling=true;
    try{
      const [st,jobs]=await Promise.all([api('/api/prints/status'),api('/api/jobs')]);
      const j=(Array.isArray(jobs)?jobs:[]).find(x=>x.id===jobId);
      S.status=st;
      if(st.installed&&st.libsOk!==false){
        clearInterval(S.tmr);
        prProg(S,'Chromium pronto.','ok');
        const done=pmBusy('Carregando a configuração…');
        try{await prCarregar(S)}
        catch(e){toast(prErrMsg(e));prRender(S,null)}
        finally{done()}
        return}
      if(!j||!j.running){
        clearInterval(S.tmr);
        prProg(S,'A instalação não terminou bem (veja a saída em Tarefas). Tente de novo.','bad');
        prRender(S,null)}}
    catch(e){/* tenta de novo no próximo tick */}
    finally{S.polling=false}},5000)}

async function prEnviar(S,btn){
  const picks=[...S.body.querySelectorAll('[data-pr-pick]:checked')].map(e=>e.value);
  const versao=(S.upVersion||'').trim();
  const replace=!!S.upReplace;
  if(!picks.length){toast('Selecione pelo menos uma imagem');return}
  if(!versao){toast('Informe a versão da loja');return}
  const msg=replace?'Apagar as imagens atuais desses tipos e idiomas na loja e enviar as selecionadas?':`Enviar ${picks.length} imagem(ns) para a ficha da versão ${versao} na loja?`;
  if(!confirm(msg))return;
  btn.disabled=true;
  const done=pmBusy('Enviando prints para a loja…');
  try{
    const r=await api('/api/prints/upload',{project:S.project,run:S.run,version:versao,items:picks,replace});
    const erros=Array.isArray(r.errors)?r.errors:[];
    S.upMsg=`<div><b>Enviadas: ${Number(r.uploaded)||0}</b>${erros.length?`<ul class="pr-err" style="padding-left:18px">${erros.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}</div>`;
    toast(`${Number(r.uploaded)||0} imagem(ns) enviada(s)`)}
  catch(e){S.upMsg=`<div class="pr-err">${esc(prErrMsg(e))}</div>`;toast(prErrMsg(e))}
  finally{
    done();
    btn.disabled=false;
    const el=S.body.querySelector('[data-pr-up]');
    if(el)el.innerHTML=S.upMsg}}

/* ---------- eventos (delegação no corpo do popup) ---------- */
function prOnClick(e){
  const S=prS;if(!prAlive(S))return;
  const btn=e.target.closest&&e.target.closest('[data-pr]');
  if(!btn||btn.disabled)return;
  const act=btn.dataset.pr, i=Number(btn.dataset.i);
  if(act==='save'){prSalvar(S,btn);return}
  if(act==='run'){prGerar(S,btn);return}
  if(act==='install'){prInstalar(S,btn);return}
  if(act==='send'){prEnviar(S,btn);return}
  if(act==='tarefas'){pmClose();go('jobs');return}
  if(act==='add'){const raw=prFromDom(S);raw.screens.push(prNovaTela(raw.screens.length));prRender(S,raw);return}
  if(act==='rm'){const raw=prFromDom(S);raw.screens.splice(i,1);prRender(S,raw);return}
  if(act==='up'||act==='down'){
    const raw=prFromDom(S), j=act==='up'?i-1:i+1;
    if(j<0||j>=raw.screens.length)return;
    [raw.screens[i],raw.screens[j]]=[raw.screens[j],raw.screens[i]];
    prRender(S,raw)}}

function prOnChange(e){
  const S=prS;if(!prAlive(S))return;
  const t=e.target, k=t.dataset&&t.dataset.g;
  if(k==='style'){
    const cap=t.value==='caption';
    S.body.querySelectorAll('[data-pr-cap],[data-pr-capstyle]').forEach(el=>{el.hidden=!cap})}
  else if(k==='run'){
    S.run=t.value;S.upMsg='';
    prCarregarArquivos(S).then(()=>prResRepaint(S)).catch(err=>toast(prErrMsg(err)))}
  else if(k==='replace'){S.upReplace=t.checked}}

function prOnInput(e){
  const S=prS;if(!prAlive(S))return;
  if(e.target.dataset&&e.target.dataset.g==='version')S.upVersion=e.target.value}
