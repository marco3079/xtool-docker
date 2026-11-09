/* ---------- Gerenciar lojas publicadas: popups internos e seção de imagens ----------
   script clássico carregado depois de database.js e antes de lojas.js.
   usa os globais do index.html: $, esc, toast, api, uiLoading; e de projects.js: pmBusy.
   Não usa pmModal/pmCur: o popup de baixo (lojas.js) continua aberto por trás dos overlays.
   Globais: LOJAS_FIELDS, lojasOverlay, lojasIaPopup, lojasImagesHtml, lojasImagesBind.
   Auxiliares: prefixo lj2. API: POST /api/lojas/generate, POST /api/lojas/image/upload,
   POST /api/lojas/image/delete, e a rota de upload bruto POST /api/upload?root=work&path=... */

const LOJAS_FIELDS={whatsNew:"O que há de novo",promotionalText:"Texto promocional",description:"Descrição",keywords:"Palavras-chave",subtitle:"Subtítulo",shortDescription:"Descrição curta",fullDescription:"Descrição completa"};

(function lj2InitStyle(){
  if(document.getElementById('lj2Style'))return;
  const s=document.createElement('style');s.id='lj2Style';
  s.textContent=`
.lj2-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px;margin-top:8px}
.lj2-thumb{position:relative;background:var(--panel2);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.lj2-thumb img{display:block;width:100%;height:110px;object-fit:contain;cursor:zoom-in;background:var(--panel)}
.lj2-del{position:absolute;top:4px;right:4px;background:rgba(3,5,10,.75);border-radius:8px;padding:2px 7px;font-size:14px}
.lj2-del:hover{color:var(--bad)}
.lj2-errs{color:var(--bad);font-size:13px;margin-top:8px}
`;
  document.head.appendChild(s)})();

/* popup de carregamento (usa uiLoading do index.html; se ausente, não faz nada) */
const lj2Spin=msg=>(typeof uiLoading==='function')?uiLoading(msg):(()=>{});

/* pilha de overlays: Esc fecha só o overlay do topo, nunca o modal de baixo */
const lj2Stack=[];
window.addEventListener('keydown',e=>{
  if(e.key!=='Escape'||!lj2Stack.length)return;
  e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
  lj2Stack[lj2Stack.length-1].close();
},true);

/* overlay próprio acima do modal atual. title é texto puro; html é o conteúdo;
   buttons = [{label,cls:'pri'|'danger'|'',id,onClick}] (sem botões = sem rodapé).
   Fecha com ✕, clique fora ou Esc (só o overlay do topo). Retorna {el, body, close}. */
function lojasOverlay(title,html,buttons){
  const el=document.createElement('div');
  el.className='pm-back';
  el.style.zIndex='45';
  el.innerHTML=`<div class="pm-box" role="dialog" aria-modal="true"><div class="pm-head"><h3></h3><button class="pm-x" title="Fechar">✕</button></div><div class="pm-body"></div><div class="pm-foot"></div></div>`;
  el.querySelector('h3').textContent=String(title||'');
  const body=el.querySelector('.pm-body'), foot=el.querySelector('.pm-foot');
  body.innerHTML=html||'';
  const cur={el,close:null};
  cur.close=()=>{
    const i=lj2Stack.indexOf(cur);
    if(i>=0)lj2Stack.splice(i,1);
    el.remove();
  };
  el.addEventListener('click',e=>{if(e.target===el)cur.close()});
  el.querySelector('.pm-x').onclick=()=>cur.close();
  (buttons||[]).forEach(b=>{
    const x=document.createElement('button');
    x.className='btn'+(b.cls?' '+b.cls:'');
    x.textContent=b.label;
    if(b.id)x.id=b.id;
    x.onclick=ev=>{if(b.onClick)b.onClick(ev)};
    foot.appendChild(x);
  });
  if(!buttons||!buttons.length)foot.remove();
  lj2Stack.push(cur);
  document.body.appendChild(el);
  return {el,body,close:cur.close};
}

/* lista de erros da IA: aceita {locale: msg}, lista de strings ou lista de objetos */
function lj2ErrList(errors,labelOf){
  if(!errors)return [];
  if(Array.isArray(errors)){
    return errors.map(x=>{
      if(typeof x==='string')return x;
      if(!x||typeof x!=='object')return '';
      const loc=x.locale||x.loc||'';
      const msg=x.error||x.message||'';
      return [loc?labelOf(loc)+' ('+loc+')':'',msg].filter(Boolean).join(': ');
    }).filter(Boolean);
  }
  if(typeof errors==='object')return Object.keys(errors).map(k=>labelOf(k)+' ('+k+'): '+String(errors[k]));
  return [String(errors)];
}

/* popup "✨ Gerar com IA": escolhe campos e idiomas, gera e aplica via ctx.setValue.
   ctx: {project, store, version, build, appName, fieldList, limits, locales, catalog, getValues(), setValue(loc,field,text)}
   onDone({generated, errors}) é chamado ao fim da geração. */
async function lojasIaPopup(ctx,onDone){
  const fields=Array.isArray(ctx.fieldList)?ctx.fieldList.slice():[];
  const locs=Array.isArray(ctx.locales)?ctx.locales.slice():[];
  const catalog=Array.isArray(ctx.catalog)?ctx.catalog:[];
  const labelOf=c=>{const f=catalog.find(x=>x.code===c);return f&&f.label?f.label:c};
  if(!fields.length){toast('Esta loja não tem campos de texto para gerar');return}
  if(!locs.length){toast('Nenhum idioma configurado: marque os idiomas do app em ⚙ Configurar');return}

  const html=`
    <div class="pm-sec"><b>Campos a gerar</b>
      <div class="pm-grid" style="margin-top:8px">${fields.map(f=>`<label class="pm-sw"><input type="checkbox" data-lj2-field="${esc(f)}" checked>${esc(LOJAS_FIELDS[f]||f)}</label>`).join('')}</div>
    </div>
    <div class="pm-sec"><b>Idiomas</b>
      <div class="pm-grid" style="margin-top:8px">${locs.map(c=>`<label class="pm-sw"><input type="checkbox" data-lj2-loc="${esc(c)}" checked>${esc(labelOf(c))} <span class="hint">${esc(c)}</span></label>`).join('')}</div>
    </div>
    <div class="pm-sec"><label class="hint" for="lj2Extra">Observações para a IA (opcional)</label>
      <textarea id="lj2Extra" rows="3" style="width:100%" placeholder="Ex.: público, tom, termos a evitar"></textarea>
    </div>
    <div class="hint">A IA parte dos textos atuais da loja e das mudanças registradas no git. Revise antes de atualizar na loja.</div>
    <div class="pm-err" id="lj2Msg"></div>
    <div id="lj2Errs"></div>`;

  const done=lj2Spin('Abrindo…');
  let ov;
  try{
    ov=lojasOverlay('✨ Gerar com IA — '+(ctx.appName||ctx.project||''),html,[
      {label:'Cancelar',cls:'',id:'lj2Cancel',onClick:()=>ov.close()},
      {label:'✨ Gerar',cls:'pri',id:'lj2Gen',onClick:()=>lj2Gen()}
    ]);
  }finally{done()}

  const msgEl=()=>ov.body.querySelector('#lj2Msg');
  const errsEl=()=>ov.body.querySelector('#lj2Errs');
  const genBtn=()=>ov.el.querySelector('#lj2Gen');
  const setBtn=(busy)=>{
    const b=genBtn();
    if(!b)return;
    b.disabled=busy;
    b.textContent=busy?'Gerando…':'✨ Gerar';
  };

  const lj2Gen=async()=>{
    const b=genBtn();
    if(!b||b.disabled)return;
    const fSel=[...ov.body.querySelectorAll('input[data-lj2-field]:checked')].map(i=>i.dataset.lj2Field);
    const lSel=[...ov.body.querySelectorAll('input[data-lj2-loc]:checked')].map(i=>i.dataset.lj2Loc);
    const extra=(ov.body.querySelector('#lj2Extra').value||'').trim();
    msgEl().textContent='';
    errsEl().innerHTML='';
    if(!fSel.length){msgEl().textContent='Marque ao menos um campo.';return}
    if(!lSel.length){msgEl().textContent='Marque ao menos um idioma.';return}

    setBtn(true);
    let r;
    try{
      r=await api('/api/lojas/generate',{
        project:ctx.project,store:ctx.store,version:ctx.version,
        fields:fSel,locales:lSel,current:ctx.getValues(),extra,appName:ctx.appName
      });
    }catch(e){
      setBtn(false);
      msgEl().textContent=e.message||'Falha ao gerar os textos.';
      return;
    }
    setBtn(false);

    /* aplica só os pares loc/campo pedidos e devolvidos pela IA */
    const results=(r&&r.results)||{};
    let n=0;
    for(const loc of lSel){
      const row=results[loc];
      if(!row||typeof row!=='object')continue;
      for(const f of fSel){
        if(!Object.prototype.hasOwnProperty.call(row,f))continue;
        const t=row[f];
        if(typeof t!=='string')continue;
        ctx.setValue(loc,f,t);
        n++;
      }
    }
    const errList=lj2ErrList(r&&r.errors,labelOf);
    const open=ov.el.isConnected;
    if(open&&!errList.length)ov.close();
    if(open&&errList.length){
      errsEl().innerHTML=errList.map(t=>`<div class="lj2-errs">${esc(t)}</div>`).join('');
    }
    if(typeof onDone==='function')onDone({generated:n,errors:errList});
    if(!open&&errList.length)toast('Erros na geração: '+errList.join(' | '));
  };
}

/* ---------- imagens do idioma ativo ---------- */

/* seção de imagens: uma caixa por kind (ctx.imageKinds ou o array kinds), miniaturas com ✕ e ＋ Adicionar.
   imgs = {kind:[{id,url,name}]} do idioma `loc`. */
function lojasImagesHtml(ctx,loc,imgs,kinds){
  const ks=Array.isArray(kinds)?kinds:((ctx&&ctx.imageKinds)||[]);
  const data=(imgs&&typeof imgs==='object')?imgs:{};
  const inner=ks.map(k=>{
    const list=Array.isArray(data[k.kind])?data[k.kind]:[];
    const thumbs=list.map(im=>{
      const url=im&&im.url?String(im.url):'';
      const name=im&&im.name?String(im.name):(k.label||k.kind);
      return `<div class="lj2-thumb"><img src="${esc(url)}" alt="${esc(name)}" loading="lazy" data-lj2-zoom="${esc(url)}"><button class="pm-x lj2-del" title="Apagar imagem" data-lj2-del="${esc(im&&im.id?im.id:'')}" data-lj2-kind="${esc(k.kind)}">✕</button></div>`;
    }).join('');
    return `<div class="pm-card">
      <div class="pm-row" style="margin-bottom:0"><b>${esc(k.label||k.kind)}</b><span class="pill"><i></i>${list.length} ${list.length===1?'imagem':'imagens'}</span></div>
      ${k.hint?`<div class="hint">${esc(k.hint)}</div>`:''}
      <div class="lj2-grid">${thumbs||'<div class="hint">Nenhuma imagem ainda.</div>'}</div>
      <div class="pm-row" style="margin:10px 0 0"><button class="btn sm" data-lj2-add="${esc(k.kind)}">＋ Adicionar</button><input type="file" accept="image/png,image/jpeg" multiple hidden data-lj2-file="${esc(k.kind)}"></div>
    </div>`;
  }).join('');
  return `<div class="lj2-imgs" data-lj2-loc="${esc(loc||'')}">${inner}</div>`;
}

/* roda uma operação de imagem com trava (uma por vez) e popup de carregamento */
async function lj2Op(root,msg,fn){
  if(root._lj2Busy){toast('Aguarde a operação em andamento');return}
  root._lj2Busy=true;
  const done=lj2Spin(msg);
  try{await fn(root._lj2)}
  catch(e){toast(e.message||String(e))}
  finally{done();root._lj2Busy=false}
}

/* envia os arquivos escolhidos: /api/upload (corpo bruto) para o projeto, depois registra na loja */
async function lj2Upload(root,kind,files){
  await lj2Op(root,'Enviando imagens…',async()=>{
    for(let k=0;k<files.length;k++){
      const file=files[k];
      const st=root._lj2;
      const c=st.ctx;
      const safe=file.name.replace(/[^A-Za-z0-9._-]/g,'_');
      const rel=c.project+'/xtool/lojas-img/'+Date.now()+'-'+k+'-'+safe;
      toast('Enviando '+file.name+'…');
      const up=await fetch('/api/upload?root=work&path='+encodeURIComponent(rel),{method:'POST',body:file});
      const uj=await up.json();
      if(uj.error)throw new Error(uj.error);
      const r=await api('/api/lojas/image/upload',{project:c.project,store:c.store,version:c.version,locale:st.loc,kind,path:rel});
      if(r&&r.images&&typeof st.onChanged==='function')st.onChanged(r.images);
      toast('Enviado: '+file.name);
    }
  });
}

/* liga os eventos (delegação) uma vez por elemento root; chamadas seguintes só atualizam o estado.
   onChanged(images) recebe {kind:[{id,url,name}]} do idioma após enviar/apagar. */
function lojasImagesBind(root,ctx,loc,imgs,kinds,onChanged){
  if(!root)return;
  root._lj2={ctx,loc,kinds,onChanged};
  if(root._lj2Bound)return;
  root._lj2Bound=true;

  root.addEventListener('click',e=>{
    const t=e.target&&e.target.closest?e.target.closest('[data-lj2-add],[data-lj2-del],[data-lj2-zoom]'):null;
    if(!t||!root.contains(t))return;

    /* ampliar imagem */
    if(t.hasAttribute('data-lj2-zoom')){
      const url=t.getAttribute('data-lj2-zoom')||'';
      if(!url)return;
      const done=lj2Spin('Abrindo imagem…');
      try{
        lojasOverlay('Imagem ampliada',`<img src="${esc(url)}" alt="" style="display:block;max-width:100%;height:auto;margin:0 auto">`,[]);
      }finally{done()}
      return;
    }

    /* escolher arquivos para o kind */
    if(t.hasAttribute('data-lj2-add')){
      const kind=t.getAttribute('data-lj2-add');
      const inp=[...root.querySelectorAll('input[data-lj2-file]')].find(i=>i.dataset.lj2File===kind);
      if(inp)inp.click();
      return;
    }

    /* apagar imagem */
    if(t.hasAttribute('data-lj2-del')){
      const st=root._lj2;
      const id=t.getAttribute('data-lj2-del')||'';
      const kind=t.getAttribute('data-lj2-kind')||'';
      if(!id||!st)return;
      if(!confirm('Apagar esta imagem da loja? Ela será removida do idioma '+st.loc+'.'))return;
      lj2Op(root,'Apagando imagem…',async()=>{
        const c=root._lj2.ctx;
        const r=await api('/api/lojas/image/delete',{project:c.project,store:c.store,version:c.version,locale:root._lj2.loc,kind,id});
        if(r&&r.images&&typeof root._lj2.onChanged==='function'){
          root._lj2.onChanged(r.images);
          toast('Imagem apagada');
        }else toast('A loja não devolveu as imagens; atualize a tela');
      });
    }
  });

  /* arquivos escolhidos: confirma um a um, depois envia */
  root.addEventListener('change',e=>{
    const inp=e.target;
    if(!inp||!inp.matches||!inp.matches('input[data-lj2-file]'))return;
    const kind=inp.dataset.lj2File;
    const picked=[...(inp.files||[])];
    inp.value='';
    const ok=[];
    for(const f of picked){
      if(!/\.(png|jpe?g)$/i.test(f.name)){toast(f.name+': use PNG ou JPG');continue}
      if(f.size>10*1024*1024){toast(f.name+': passa de 10 MB');continue}
      if(!confirm('Enviar '+f.name+' agora para a loja?'))continue;
      ok.push(f);
    }
    if(ok.length)lj2Upload(root,kind,ok);
  });
}
