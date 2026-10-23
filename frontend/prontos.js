'use strict';
window.oktoReadyPanel=data=>{
 const el=(tag,text,cls)=>Object.assign(document.createElement(tag),{textContent:text??'',className:cls||''});
 const box=el('section',null,'ready-overview');box.append(el('h2','Prontos por sabor'),el('p',`Meta hoje: ${Number(data.sabores[0]?.meta||0).toLocaleString('pt-BR')} por sabor · alerta abaixo de 30%.`,'subtext'));
 const cards=el('div',null,'ready-grid');
 for(const p of data.sabores){const c=el('article',null,'ready-card'+(p.abaixo_limite?' critical':''));
  c.append(el('h3',p.nome),el('strong',p.contagem_informada?Number(p.saldo).toLocaleString('pt-BR'):'—','ready-count'));
  c.append(el('p',p.contagem_informada?'porções disponíveis':'Contagem não informada','subtext'));
  if(p.contagem_informada){const meter=el('progress');meter.max=p.meta;meter.value=p.saldo;meter.setAttribute('aria-label','Estoque pronto em relação à meta');c.append(meter,el('p',`${Number(p.percentual_disponivel).toLocaleString('pt-BR',{maximumFractionDigits:1})}% da meta${p.abaixo_limite?' · PRODUZIR / REPOR':''}`));}
  if(location.pathname.endsWith('producao.html')){const action=el('button',p.contagem_informada?'Registrar produção':'Informar contagem','button');action.type='button';action.onclick=()=>window.oktoSelectReadyFlavor?.(p.produto_id);c.append(action);}
  cards.append(c);
 }
 box.append(cards);return box;
};
window.oktoReadyForms=(data,products,{onlyDiscard=false}={})=>{
 const el=(tag,text,cls)=>Object.assign(document.createElement(tag),{textContent:text||'',className:cls||''});
 const wrap=el('div');
 const editor=el('details',null,'ready-editor panel');editor.append(el('summary','Registrar porções prontas'));editor.open=true;
 const form=el('form',null,'purchase-form');
 function field(text,tag='input'){const l=el('label',text),i=el(tag);l.append(i);form.append(l);return i;}
 const product=field('Sabor','select');product.required=true;data.sabores.forEach(p=>product.append(new Option(p.nome,p.produto_id)));
 product.name='produto_id';
 const origin=field('Tipo de registro','select');origin.append(new Option('Contagem física inicial','saldo_inicial'),new Option('Produção concluída (baixa ingredientes)','producao'));
 const quantity=field('Quantidade pronta');quantity.type='number';quantity.min='0';quantity.step='1';quantity.required=true;
 const code=field('Código do lote');code.required=true;code.maxLength=120;
 const validity=field('Validade do lote pronto');validity.type='datetime-local';validity.required=true;
 const cost=field('Custo de ingredientes por porção (R$)');cost.type='number';cost.step='0.000001';cost.min='0';cost.required=true;
 origin.name='origem';quantity.name='quantidade';
 origin.onchange=()=>{const production=origin.value==='producao';cost.disabled=production;cost.required=!production;cost.parentElement.hidden=production;quantity.min=production?'1':'0';};
 product.onchange=()=>{const chosen=data.sabores.find(p=>p.produto_id===product.value);origin.options[0].disabled=!!chosen?.contagem_informada;origin.value=chosen?.contagem_informada?'producao':'saldo_inicial';origin.onchange();};
 product.onchange();
 if(!onlyDiscard)window.oktoSelectReadyFlavor=id=>{product.value=id;product.onchange();editor.open=true;editor.scrollIntoView({behavior:'smooth',block:'center'});quantity.focus({preventScroll:true});};
 const note=el('p','Contagem inicial: informe o que já está pronto. Nova produção: os ingredientes são baixados e o custo é calculado. Informe a validade definida pela cozinha.','wide');
 const b=el('button','Registrar porções prontas','button primary');b.type='submit';const msg=el('p',null,'wide');msg.setAttribute('role','status');form.append(note,b,msg);
 let key=crypto.randomUUID();form.addEventListener('input',()=>{key=crypto.randomUUID();form.dataset.dirty='true';});
 const errs={SALDO_INICIAL_JA_REGISTRADO:'O saldo inicial deste sabor já foi registrado. Use produção para novas porções.',INSUMOS_INSUFICIENTES_PARA_PRODUZIR:'Faltam ingredientes utilizáveis para registrar esta produção.',LOTE_VENCIDO:'Informe uma validade futura.',PRODUTO_SEM_CONTROLE_PRONTOS:'Este produto não possui controle de porções prontas.'};
 form.addEventListener('submit',async e=>{e.preventDefault();b.disabled=true;try{
  const payload={produto_id:product.value,idempotency_key:key,codigo:code.value,origem:origin.value,quantidade:Number(quantity.value),validade:new Date(validity.value).toISOString(),custo_unitario:origin.value==='producao'?null:cost.value};
  const r=await fetch('/demo/prontos/entradas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await r.json();
  if(!r.ok)throw Error(errs[d.detail?.codigo]||'Confira os campos; não foi possível registrar.');
  msg.textContent='Registrado. Estoque e alertas atualizados.';key=crypto.randomUUID();editor.open=false;form.reset();delete form.dataset.dirty;product.onchange();window.dispatchEvent(new Event('okto:cadastro'));
 }catch(err){msg.textContent=err.message;}finally{b.disabled=false;}});
 editor.append(form);
 if(!onlyDiscard){
   if(!data.sabores.length){wrap.append(el('p','Cadastre uma ficha técnica para começar a produção.','empty-state'));return wrap;}
   wrap.append(editor);
   const link=el('a','Registrar descarte em Perdas →','text-link');link.href='perdas.html';wrap.append(link);return wrap;
 }
 const available=data.lotes.filter(l=>Number(l.saldo)>0);
 if(!available.length){const empty=el('div',null,'empty-state');empty.append(el('strong','Nenhum lote pronto para descartar'),el('p','Registre uma contagem ou produção antes de lançar um descarte.'));const link=el('a','Ir para Produção →','text-link');link.href='producao.html';empty.append(link);wrap.append(empty);return wrap;}
 const discard=el('details',null,'ready-editor panel');discard.append(el('summary','Registrar descarte de porções prontas'));
 const df=el('form',null,'purchase-form');
 function dfield(text,tag='input'){const l=el('label',text),i=el(tag);l.append(i);df.append(l);return i;}
 const lot=dfield('Lote pronto','select');lot.required=true;available.forEach(l=>lot.append(new Option(`${l.nome} · ${l.codigo} · saldo ${l.saldo}`,l.id)));
 const amount=dfield('Quantidade descartada');amount.type='number';amount.min='1';amount.step='1';amount.required=true;
 const reason=dfield('Motivo');reason.required=true;reason.minLength=3;reason.maxLength=300;
 const dbtn=el('button','Registrar descarte','button');dbtn.type='submit';const dm=el('p',null,'wide');dm.setAttribute('role','status');df.append(dbtn,dm);let dk=crypto.randomUUID();df.addEventListener('input',()=>{dk=crypto.randomUUID();df.dataset.dirty='true';});
 df.onsubmit=async e=>{e.preventDefault();dbtn.disabled=true;try{const r=await fetch('/demo/prontos/perdas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lote_id:lot.value,idempotency_key:dk,quantidade:Number(amount.value),motivo:reason.value})});if(!r.ok)throw Error('Confira quantidade e lote. O saldo não pode ficar negativo.');dk=crypto.randomUUID();discard.open=false;df.reset();delete df.dataset.dirty;window.dispatchEvent(new Event('okto:cadastro'));}catch(err){dm.textContent=err.message;}finally{dbtn.disabled=false;}};
 discard.append(df);wrap.append(discard);return wrap;
};
