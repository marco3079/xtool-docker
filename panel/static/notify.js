/* ---------- Notificações (card #ntfCard em Configuração) + avisos do navegador ----------
   Usa: $, val, chk, esc, toast, api (index.html).
   Estado: ntfState = resposta de GET /api/notify/config (POST /api/notify/config devolve o mesmo formato).
   Polling: GET /api/notify/events a cada 20 s; cada evento vira toast e, se permitido, Notification do navegador. */
(function(){const s=document.createElement('style');s.id='ntfCss';s.textContent=`
#ntfCard .ntf-blk+.ntf-blk{border-top:1px solid var(--line);padding-top:12px;margin-top:14px}
#ntfCard h4{margin:0 0 8px;font-size:14px}
#ntfCard input[type=number]{width:100%;padding:9px 11px;border-radius:9px;border:1px solid var(--line);background:var(--input);outline:none}
#ntfCard input[type=number]:focus{border-color:var(--accent)}
#ntfCard .ntf-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}
#ntfCard .ntf-grid .field.full{grid-column:1/-1}
#ntfCard .ntf-ev{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}
#ntfCard .ntf-err{color:var(--bad);font-size:13px;margin:6px 0}
#ntfCard .ntf-foot{display:flex;justify-content:flex-end;margin-top:14px}
@media(max-width:700px){#ntfCard .ntf-grid,#ntfCard .ntf-ev{grid-template-columns:1fr}}
`;document.head.appendChild(s)})();

const NTF_SEG={starttls:'STARTTLS',ssl:'SSL',none:'Nenhuma'};
let ntfState=null;          /* último config público */
let ntfLast=null;           /* último id de evento visto (null = ainda não sincronizado) */
let ntfApagar=new Set();    /* segredos marcados para apagar no próximo "Salvar" */

/* Mensagem de erro do último envio de um canal (vem do servidor, em lastErrors). */
function ntfErro(canal){
  const e=(ntfState&&ntfState.lastErrors&&ntfState.lastErrors[canal])||'';
  return e?`<div class="ntf-err">Último erro: ${esc(e)}</div>`:'';
}

/* Campo de segredo: vazio = mantém; o placeholder mostra a máscara do que está salvo. */
function ntfCampoSeg(rotulo,id,key,mascara){
  return `<div class="field"><label>${esc(rotulo)}</label>
    <div class="row" style="flex-wrap:nowrap">
      <input type="password" id="${id}" placeholder="${esc(mascara||'não configurado')}" autocomplete="new-password" style="flex:1;min-width:0">
      ${mascara?`<button class="btn sm danger" onclick="ntfRemover('${id}','${key}')">remover</button>`:''}
    </div></div>`;
}

/* Marca o segredo para ser apagado ao salvar (campo vazio + null). */
function ntfRemover(id,key){
  ntfApagar.add(key);
  const el=$(id);
  if(el){el.value='';el.placeholder='será apagado ao salvar'}
  toast('Será apagado ao clicar em Salvar');
}

/* Estado da permissão do navegador (#ntfPerm). */
function ntfPermTexto(){
  const el=$('ntfPerm');if(!el)return;
  if(!('Notification' in window)){el.textContent='Este navegador não tem notificações.';el.style.color='';return}
  const p=Notification.permission;
  el.textContent=p==='granted'?'Permitido neste navegador.':p==='denied'?'Bloqueado: libere nas configurações do site no navegador.':'Ainda não permitido.';
  el.style.color=p==='granted'?'var(--ok)':p==='denied'?'var(--bad)':'';
}

async function ntfPedirPermissao(){
  if(!('Notification' in window))return toast('Este navegador não tem notificações');
  try{
    const r=await Notification.requestPermission();
    ntfPermTexto();
    toast(r==='granted'?'Notificações do navegador permitidas':'Permissão não concedida');
  }catch(e){toast(e.message||'Falha ao pedir permissão')}
}

/* GET /api/notify/config e pinta #ntfCard. */
async function ntfLoad(){
  const card=$('ntfCard');if(!card)return;
  try{ntfState=await api('/api/notify/config')}
  catch(e){card.innerHTML=`<h3>Notificações</h3><div class="ntf-err">${esc(e.message||'Falha ao carregar as notificações')}</div>`;return}
  ntfPaint();
}

/* Desenha o card inteiro a partir de ntfState. */
function ntfPaint(){
  const card=$('ntfCard');if(!card||!ntfState)return;
  const C=ntfState.channels||{}, B=C.browser||{}, T=C.telegram||{}, D=C.discord||{}, E=C.email||{};
  const EV=ntfState.events||{}, RO=ntfState.eventLabels||{};
  const evKeys=Object.keys(RO).length?Object.keys(RO):Object.keys(EV);
  const evHtml=evKeys.map(k=>`<label class="check"><input type="checkbox" id="ntfEv-${esc(k)}" ${EV[k]?'checked':''}>${esc(RO[k]||k)}</label>`).join('');
  const seg=Object.keys(NTF_SEG).map(k=>`<option value="${k}" ${(E.security||'starttls')===k?'selected':''}>${NTF_SEG[k]}</option>`).join('');
  const teste=c=>`<div class="row" style="margin-top:8px"><button class="btn sm" onclick="ntfTeste('${c}')">Enviar teste</button></div>`;

  ntfApagar=new Set();
  card.innerHTML=`<h3>Notificações</h3>
    <p>Avisa quando um build ou envio termina (ou dá erro), quando a loja muda o estado de um app e quando há atualização do painel. Os testes usam a configuração salva.</p>

    <div class="ntf-blk">
      <h4>Navegador</h4>
      <label class="check"><input type="checkbox" id="ntfBrowserOn" ${B.enabled?'checked':''}>Mostrar avisos no navegador</label>
      <div class="row"><button class="btn sm" onclick="ntfPedirPermissao()">Permitir notificações do navegador</button><span class="hint" id="ntfPerm"></span></div>
      <div class="hint" style="margin-top:6px">O aviso aparece como notificação do sistema enquanto o painel estiver aberto.</div>
      ${ntfErro('browser')}
      ${teste('browser')}
    </div>

    <div class="ntf-blk">
      <h4>Telegram</h4>
      <label class="check"><input type="checkbox" id="ntfTgOn" ${T.enabled?'checked':''}>Ativar Telegram</label>
      <div class="ntf-grid">
        ${ntfCampoSeg('Token do bot','ntf-telegramToken','telegramToken',T.token)}
        <div class="field"><label>Chat ID</label><input type="text" id="ntfTgChat" value="${esc(T.chatId||'')}" placeholder="ex: 123456789"></div>
      </div>
      <div class="hint">Crie um bot com o @BotFather e mande uma mensagem para ele. O chat ID é o número do seu chat com o bot.</div>
      ${ntfErro('telegram')}
      ${teste('telegram')}
    </div>

    <div class="ntf-blk">
      <h4>Discord</h4>
      <label class="check"><input type="checkbox" id="ntfDcOn" ${D.enabled?'checked':''}>Ativar Discord</label>
      <div class="ntf-grid">
        ${ntfCampoSeg('URL do webhook','ntf-discordWebhook','discordWebhook',D.webhook)}
      </div>
      <div class="hint">No Discord: Configurações do canal → Integrações → Webhooks → Novo webhook, depois copie a URL.</div>
      ${ntfErro('discord')}
      ${teste('discord')}
    </div>

    <div class="ntf-blk">
      <h4>E-mail (SMTP)</h4>
      <label class="check"><input type="checkbox" id="ntfMailOn" ${E.enabled?'checked':''}>Ativar e-mail</label>
      <div class="ntf-grid">
        <div class="field"><label>Servidor SMTP</label><input type="text" id="ntfMailHost" value="${esc(E.host||'')}" placeholder="smtp.gmail.com"></div>
        <div class="field"><label>Porta</label><input type="number" id="ntfMailPort" value="${esc(E.port||587)}" min="1" max="65535"></div>
        <div class="field"><label>Segurança</label><select id="ntfMailSec">${seg}</select></div>
        <div class="field"><label>Usuário</label><input type="text" id="ntfMailUser" value="${esc(E.user||'')}" placeholder="voce@gmail.com"></div>
        ${ntfCampoSeg('Senha','ntf-smtpPassword','smtpPassword',E.password)}
        <div class="field"><label>Remetente</label><input type="text" id="ntfMailFrom" value="${esc(E.from||'')}" placeholder="(padrão: o usuário)"></div>
        <div class="field full"><label>Destinatário(s)</label><input type="text" id="ntfMailTo" value="${esc(E.to||'')}" placeholder="voce@exemplo.com, outro@exemplo.com"></div>
      </div>
      <div class="hint">Gmail: servidor smtp.gmail.com, porta 587, segurança STARTTLS, com uma senha de app (não a senha normal da conta).</div>
      ${ntfErro('email')}
      ${teste('email')}
    </div>

    <div class="ntf-blk">
      <h4>Eventos</h4>
      <div class="ntf-ev">${evHtml}</div>
    </div>

    <div class="ntf-foot"><button class="btn pri" onclick="ntfSalvar()">Salvar</button></div>`;
  ntfPermTexto();
}

/* POST /api/notify/config. Segredo: campo vazio = mantém; "remover" = null. */
async function ntfSalvar(){
  const body={
    channels:{
      browser:{enabled:chk('ntfBrowserOn')},
      telegram:{enabled:chk('ntfTgOn'),chatId:val('ntfTgChat')},
      discord:{enabled:chk('ntfDcOn')},
      email:{enabled:chk('ntfMailOn'),host:val('ntfMailHost'),port:parseInt(val('ntfMailPort'),10)||0,security:val('ntfMailSec'),user:val('ntfMailUser'),from:val('ntfMailFrom'),to:val('ntfMailTo')}
    },
    events:{},
    secrets:{}
  };
  document.querySelectorAll('input[id^="ntfEv-"]').forEach(i=>{body.events[i.id.slice(6)]=i.checked});
  const seg=(id,key)=>{const v=val(id);if(v)body.secrets[key]=v;else if(ntfApagar.has(key))body.secrets[key]=null};
  seg('ntf-telegramToken','telegramToken');
  seg('ntf-discordWebhook','discordWebhook');
  seg('ntf-smtpPassword','smtpPassword');
  try{
    ntfState=await api('/api/notify/config',body);
    ntfPaint();
    toast('Notificações salvas');
  }catch(e){toast(e.message||'Falha ao salvar as notificações')}
}

/* POST /api/notify/test {channel}. Resultado em toast. */
async function ntfTeste(canal){
  toast('Enviando teste…');
  try{
    const r=await api('/api/notify/test',{channel:canal});
    toast(r&&r.ok?'Teste enviado: confira o canal':'Falha no teste: '+((r&&r.error)||'erro desconhecido'));
  }catch(e){toast('Falha no teste: '+(e.message||'erro desconhecido'))}
}

/* Mostra um evento: toast sempre; Notification do navegador se o canal estiver ativo e permitido. */
function ntfMostrar(ev){
  const titulo=ev.title||'xtool Painel', texto=ev.text||'';
  toast(titulo+': '+texto);
  const ativo=!ntfState||!ntfState.channels||!ntfState.channels.browser||ntfState.channels.browser.enabled;
  if(ativo&&'Notification' in window&&Notification.permission==='granted'){
    try{new Notification(titulo,{body:texto,icon:'/static/logo.svg'})}catch(e){}
  }
}

/* GET /api/notify/events?since=N. Na 1ª chamada só guarda o último id (não mostra o passado).
   Se o id do servidor voltar menor (painel reiniciou), só ressincroniza. */
async function ntfPoll(){
  let r;
  try{r=await api('/api/notify/events?since='+(ntfLast===null?0:ntfLast))}catch(e){return}
  const antes=ntfLast;
  ntfLast=r.last;
  if(antes===null||r.last<antes)return;
  (r.events||[]).forEach(ntfMostrar);
}

/* Início: sincroniza o id de eventos já na carga da página, depois a cada 20 s.
   Card de Configuração: carregado 3 s após abrir a página (como updCheck) e ao abrir Configuração (go). */
ntfPoll();
setInterval(ntfPoll,20000);
setTimeout(ntfLoad,3000);
