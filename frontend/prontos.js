'use strict';
window.oktoReadyPanel=data=>{
 const el=(tag,text,cls)=>Object.assign(document.createElement(tag),{textContent:text??'',className:cls||''});
 const box=el('section',null,'ready-overview');box.append(el('h2','Pronta entrega · quatro sabores'),el('p','Seg–qua: 250 por sabor · qui–dom: 1.000 por sabor. Otto avisa abaixo de 30%. Metas não são contagens físicas.','subtext'));
 const cards=el('div',null,'ready-grid');
 for(const p of data.sabores){const c=el('article',null,'ready-card'+(p.abaixo_limite?' critical':''));
  c.append(el('h3',p.nome),el('strong',p.contagem_informada?Number(p.saldo).toLocaleString('pt-BR'):'Contagem pendente','ready-count'));
  c.append(el('p',`Meta hoje: ${p.meta} · alerta abaixo de ${Number(p.limite_alerta)} unidades`));
  if(p.contagem_informada){const meter=el('progress');meter.max=p.meta;meter.value=p.saldo;meter.setAttribute('aria-label','Estoque pronto em relação à meta');c.append(meter,el('p',`${Number(p.percentual_disponivel).toLocaleString('pt-BR',{maximumFractionDigits:1})}% da meta${p.abaixo_limite?' · PRODUZIR / REPOR':''}`));}
  else c.append(el('p','Registre a quantidade realmente pronta, inclusive zero.'));
  cards.append(c);
 }
 box.append(cards);return box;
};
window.oktoReadyForms=(data,products)=>{
 const el=(tag,text,cls)=>Object.assign(document.createElement(tag),{textContent:text||'',className:cls||''});
 const wrap=el('div');
 const editor=el('details',null,'ready-editor panel');editor.append(el('summary','Registrar contagem inicial ou produção concluída'));
 const form=el('form',null,'purchase-form');
 function field(text,tag='input'){const l=el('label',text),i=el(tag);l.append(i);form.append(l);return i;}
 const product=field('Sabor','select');product.required=true;product.append(new Option('Selecione…',''));data.sabores.forEach(p=>product.append(new Option(p.nome,p.produto_id)));
 const origin=field('Tipo de registro','select');origin.append(new Option('Contagem física inicial','saldo_inicial'),new Option('Produção concluída (baixa ingredientes)','producao'));
 const quantity=field('Quantidade pronta');quantity.type='number';quantity.min='0';quantity.step='1';quantity.required=true;
 const code=field('Código do lote');code.required=true;code.maxLength=120;
 const validity=field('Validade do lote pronto');validity.type='datetime-local';validity.required=true;
 const cost=field('Custo de ingredientes por porção (R$)');cost.type='number';cost.step='0.000001';cost.min='0';cost.required=true;
 origin.onchange=()=>{const production=origin.value==='producao';cost.disabled=production;cost.required=!production;quantity.min=production?'1':'0';};
 const note=el('p','Contagem inicial registra um saldo físico já existente, uma única vez por sabor. Produção exige ingredientes disponíveis e calcula o custo pelos lotes. Validade deve ser informada pela cozinha; o sistema não presume prazo de conservação.','wide');
 const b=el('button','Registrar porções prontas','button primary');b.type='submit';const msg=el('p',null,'wide');msg.setAttribute('role','status');form.append(note,b,msg);
 let key=crypto.randomUUID();form.addEventListener('input',()=>{key=crypto.randomUUID();});
 const errs={SALDO_INICIAL_JA_REGISTRADO:'O saldo inicial deste sabor já foi registrado. Use produção para novas porções.',INSUMOS_INSUFICIENTES_PARA_PRODUZIR:'Faltam ingredientes utilizáveis para registrar esta produção.',LOTE_VENCIDO:'Informe uma validade futura.',PRODUTO_SEM_CONTROLE_PRONTOS:'Este produto não possui controle de porções prontas.'};
 form.addEventListener('submit',async e=>{e.preventDefault();b.disabled=true;try{
  const payload={produto_id:product.value,idempotency_key:key,codigo:code.value,origem:origin.value,quantidade:Number(quantity.value),validade:new Date(validity.value).toISOString(),custo_unitario:origin.value==='producao'?null:cost.value};
  const r=await fetch('/demo/prontos/entradas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await r.json();
  if(!r.ok)throw Error(errs[d.detail?.codigo]||'Confira os campos; não foi possível registrar.');
  msg.textContent='Registrado. Estoque e alertas atualizados.';key=crypto.randomUUID();editor.open=false;form.reset();origin.onchange();window.dispatchEvent(new Event('okto:cadastro'));
 }catch(err){msg.textContent=err.message;}finally{b.disabled=false;}});
 editor.append(form);wrap.append(editor);
 const discard=el('details',null,'ready-editor panel');discard.append(el('summary','Registrar descarte de porções prontas'));
 const df=el('form',null,'purchase-form');
 function dfield(text,tag='input'){const l=el('label',text),i=el(tag);l.append(i);df.append(l);return i;}
 const lot=dfield('Lote pronto','select');lot.required=true;lot.append(new Option('Selecione…',''));data.lotes.forEach(l=>lot.append(new Option(`${l.nome} · ${l.codigo} · saldo ${l.saldo}`,l.id)));
 const amount=dfield('Quantidade descartada');amount.type='number';amount.min='1';amount.step='1';amount.required=true;
 const reason=dfield('Motivo');reason.required=true;reason.minLength=3;reason.maxLength=300;
 const dbtn=el('button','Registrar descarte','button');dbtn.type='submit';const dm=el('p',null,'wide');dm.setAttribute('role','status');df.append(dbtn,dm);let dk=crypto.randomUUID();df.addEventListener('input',()=>{dk=crypto.randomUUID();});
 df.onsubmit=async e=>{e.preventDefault();dbtn.disabled=true;try{const r=await fetch('/demo/prontos/perdas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lote_id:lot.value,idempotency_key:dk,quantidade:Number(amount.value),motivo:reason.value})});if(!r.ok)throw Error('Confira quantidade e lote. O saldo não pode ficar negativo.');dk=crypto.randomUUID();discard.open=false;df.reset();window.dispatchEvent(new Event('okto:cadastro'));}catch(err){dm.textContent=err.message;}finally{dbtn.disabled=false;}};
 discard.append(df);wrap.append(discard);return wrap;
};
