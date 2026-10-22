'use strict';
// Edição somente das fichas ainda não ativadas; fichas usadas em vendas são imutáveis.
window.oktoRecipeEditor=(product,stock)=>{
  const el=(tag,text)=>Object.assign(document.createElement(tag),{textContent:text||''});
  const details=el('details');details.className='recipe-editor';details.append(el('summary','Preencher ficha real (por porção)'));
  const form=el('form');form.className='purchase-form';
  const hint=el('p','Informe quantidades por UMA porção, na unidade-base. Se a receita rende várias porções, divida as quantidades pelo rendimento. Não preencha valores estimados como reais.');hint.className='wide';form.append(hint);
  const lines=el('div');lines.className='wide';
  function row(value){const line=el('div');line.className='recipe-line';const select=el('select');select.required=true;select.setAttribute('aria-label','Ingrediente');select.append(new Option('Selecione ingrediente…',''));stock.forEach(i=>select.append(new Option(`${i.nome} (${i.unidade})`,i.id)));
    const qty=el('input');qty.type='number';qty.step='0.001';qty.min='0.001';qty.required=true;qty.placeholder='Por porção';qty.setAttribute('aria-label','Quantidade por porção');
    if(value){const item=stock.find(i=>i.nome===value.nome);select.value=item?.id||'';qty.value=value.quantidade;}
    const remove=el('button','Remover');remove.type='button';remove.className='button';remove.onclick=()=>line.remove();line.append(select,qty,remove);lines.append(line);}
  (product.ingredientes.length?product.ingredientes:[null]).forEach(row);
  const add=el('button','Adicionar ingrediente');add.type='button';add.className='button';add.onclick=()=>row();
  form.append(lines,add);
  function field(label,tag='input'){const l=el('label',label),input=el(tag);l.append(input);form.append(l);return input;}
  const price=field('Preço de venda (R$)');price.type='number';price.step='0.01';price.min='0.01';price.value=product.preco??'';
  const prep=field('Modo de preparo','textarea');prep.required=true;prep.maxLength=4000;prep.value=product.ficha_detalhes?.preparo||'';
  const notes=field('Observações e rendimento','textarea');notes.maxLength=2000;notes.value=product.ficha_detalhes?.observacoes||'';
  const activate=field('Validei esta ficha e autorizo ativar para vendas e alertas','select');activate.append(new Option('Salvar rascunho','false'),new Option('Validar e ativar','true'));
  const save=el('button','Salvar ficha');save.className='button primary';save.type='submit';
  const message=el('p');message.className='wide';message.setAttribute('role','status');form.append(save,message);
  form.addEventListener('submit',async e=>{e.preventDefault();save.disabled=true;
    try{const ingredients=[...lines.children].map(line=>({insumo_id:line.querySelector('select').value,quantidade:line.querySelector('input').value}));
      const r=await fetch('/demo/fichas/'+product.id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({preco:price.value||null,ingredientes:ingredients,preparo:prep.value,observacoes:notes.value,validada:activate.value==='true'})});
      if(!r.ok)throw new Error(r.status===409?'Ficha já ativada ou usada em venda. Crie uma nova versão.':'Confira ingredientes, quantidades, preparo e preço antes de ativar.');
      message.textContent='Ficha salva.';form.dataset.saved='true';window.dispatchEvent(new Event('okto:cadastro'));location.reload();
    }catch(err){message.textContent=err.message;}finally{save.disabled=false;}
  });
  form.addEventListener('input',()=>{form.dataset.dirty='true';});details.append(form);return details;
};
