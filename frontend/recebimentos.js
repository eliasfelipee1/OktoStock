'use strict';
window.oktoReceiptEditor=stock=>{
  const el=(tag,text)=>Object.assign(document.createElement(tag),{textContent:text||''});
  const details=el('details');details.className='stock-editor panel';details.append(el('summary','Registrar recebimento real de insumo'));
  const form=el('form');form.className='purchase-form';
  const label=el('label','Insumo / unidade-base'),ingredient=el('select');ingredient.required=true;ingredient.append(new Option('Selecione…',''));stock.forEach(i=>ingredient.append(new Option(`${i.nome} (${i.unidade})`,i.id)));label.append(ingredient);form.append(label);
  function field(text,type){const l=el('label',text),i=el('input');i.required=true;i.type=type;l.append(i);form.append(l);return i;}
  const code=field('Código do lote','text'),supplier=field('Fornecedor','text'),validity=field('Validade do lote','date');code.maxLength=120;supplier.maxLength=120;
  const amount=field('Quantidade recebida (g, ml ou un)','number');amount.min='0.001';amount.step='0.001';
  const cost=field('Custo por g, ml ou un (R$)','number');cost.min='0';cost.step='0.000001';
  const hint=el('p','Exemplo de conversão: um pacote de 1 kg por R$ 20 equivale a 1.000 g e R$ 0,02/g. Registre somente recebimentos reais; enviar novamente cria outro lote.');hint.className='wide';
  const button=el('button','Registrar recebimento');button.type='submit';button.className='button primary';const message=el('p');message.className='wide';message.setAttribute('role','status');form.append(hint,button,message);
  form.addEventListener('submit',async e=>{e.preventDefault();button.disabled=true;try{
    const r=await fetch('/demo/estoque/recebimentos',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({insumo_id:ingredient.value,codigo:code.value,fornecedor:supplier.value,validade:validity.value,quantidade:amount.value,custo_unitario:cost.value})});
    if(!r.ok)throw new Error('Não foi possível registrar: confira campos e validade do lote.');
    message.textContent='Recebimento registrado. Estoque e alertas atualizados.';form.reset();details.open=false;window.dispatchEvent(new Event('okto:cadastro'));
  }catch(err){message.textContent=err.message;}finally{button.disabled=false;}});
  details.append(form);return details;
};
