'use strict';
// Botão flutuante do Otto, presente em todas as páginas. Sem token no navegador:
// o servidor responde pela operação configurada para esta instalação.
const OTTO_ERRORS = {
  IA_PESQUISA_CONFIGURACAO: 'O provedor recusou a configuração de pesquisa. Confira a disponibilidade da busca web e do modelo na conta Anthropic.',
  IA_CREDENCIAL_RECUSADA: 'A credencial da Anthropic foi recusada. Verifique a configuração no servidor.',
  IA_LIMITE_DO_PROVEDOR: 'Limite da Anthropic atingido. Verifique o saldo ou tente depois.',
  IA_NAO_CONFIGURADA: 'A IA ainda não está configurada no servidor.',
  IA_INDISPONIVEL: 'O provedor de IA está indisponível.',
  IA_TEMPO_ESGOTADO: 'O provedor demorou demais. Tente novamente.',
  IA_RESPOSTA_INCOMPLETA: 'A resposta do Otto ficou incompleta. Tente uma pergunta mais específica.',
  IA_RESPOSTA_VAZIA: 'O Otto não retornou texto. Tente novamente.',
  IA_RESPOSTA_INVALIDA: 'O provedor de IA retornou uma resposta inválida.',
  IA_LIMITE_DE_PERGUNTAS: 'Muitas perguntas seguidas deste computador. Aguarde um minuto e tente de novo.',
  CONTEXTO_IA_MUITO_GRANDE: 'Há dados demais para enviar ao Otto. Reduza o período consultado.',
  DEMONSTRACAO_LOCAL_INDISPONIVEL: 'Otto não está disponível para este computador. No servidor, confira LOCAL_DEMO_OPERATION_ID e DEMO_ACESSO_REMOTO.'
};

async function askOtto(question) {
  const response = await fetch('/demo/ia/perguntar', {
    method: 'POST', cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pergunta: question, dias_historico: 14 })
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(OTTO_ERRORS[data.detail?.codigo] || `Não foi possível consultar o Otto (HTTP ${response.status}).`);
  return data;
}

// Formata **negrito** e `código` criando elementos; o texto da IA nunca vira HTML.
function appendAnswerText(output, text) {
  text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/).forEach((part) => {
    if (/^\*\*.+\*\*$/.test(part)) output.append(Object.assign(document.createElement('strong'), { textContent: part.slice(2, -2) }));
    else if (/^`.+`$/.test(part)) output.append(Object.assign(document.createElement('code'), { textContent: part.slice(1, -1) }));
    else output.append(part.replace(/^#{1,6} /gm, ''));
  });
}

function showAnswer(output, answer) {
  output.replaceChildren();
  if (typeof answer === 'string') { appendAnswerText(output, answer); return; }
  const sources = new Map((answer.fontes_web || []).map(s => [s.id, s]));
  const blocks = answer.blocos?.length ? answer.blocos : [{texto: answer.resposta, fontes: []}];
  function sourceLink(source, label) {
    try {
      const url = new URL(source.url);
      if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null;
      return Object.assign(document.createElement('a'), {href: url.href, textContent: label,
        target: '_blank', rel: 'noopener noreferrer', title: source.titulo});
    } catch { return null; }
  }
  for (const block of blocks) {
    appendAnswerText(output, block.texto || '');
    for (const id of block.fontes || []) {
      const source = sources.get(id), link = source && sourceLink(source, ` [${id}]`);
      if (link) output.append(link);
    }
  }
  output.append(document.createTextNode(answer.pesquisa_web_utilizada
    ? '\nPesquisa externa realizada. Fontes citadas:'
    : answer.pesquisa_web_habilitada ? '\nEsta resposta não utilizou pesquisa externa.' : '\nPesquisa externa desabilitada.'));
  for (const source of sources.values()) {
    const link = sourceLink(source, `[${source.id}] ${source.titulo}`);
    if (link) output.append(document.createTextNode('\n'), link);
  }
  for (const warning of answer.avisos || []) output.append(document.createTextNode('\n\n'+warning));
  for (const proposal of answer.propostas_precos || []) renderPriceProposal(output, proposal);
}

function renderPriceProposal(output, proposal) {
  const el=(tag,text)=>Object.assign(document.createElement(tag),{textContent:text||''});
  const money=value=>Number(value).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
  const qty=value=>window.oktoQuantidade(value,proposal.unidade);
  const panel=el('section');panel.className='otto-price-proposal';
  panel.append(el('h3','Deseja atualizar este preço no banco?'),el('p',`${proposal.fornecedor} · ${proposal.insumo}`),el('p',proposal.produto_pesquisado));
  const old=(proposal.precos_anteriores||[]).map(q=>`${money(q.preco_embalagem)} / ${qty(q.quantidade_embalagem)}`).join('; ')||'Sem cotação ativa';
  panel.append(el('p','Anterior: '+old),el('strong',`Novo: ${money(proposal.preco_embalagem)} / ${qty(proposal.quantidade_embalagem)}`));
  try {const url=new URL(proposal.fonte_url);if(['http:','https:'].includes(url.protocol)&&!url.username&&!url.password){const link=el('a','Conferir preço na fonte');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';panel.append(link);}}catch{}
  panel.append(el('p','Salvar substitui a cotação ativa por uma referência pública. Frete, prazo e validade ficam pendentes. Custos históricos e preço de venda não mudam.'));
  panel.append(el('p','Proposta válida até '+new Date(proposal.expira_em).toLocaleString('pt-BR')));
  const actions=el('div');actions.className='otto-price-actions';
  const confirm=el('button','Confirmar atualização'),cancel=el('button','Não alterar'),message=el('p');
  confirm.type=cancel.type='button';confirm.className='button primary';cancel.className='button';message.setAttribute('role','status');
  async function decide(action){
    confirm.disabled=cancel.disabled=true;message.textContent='Processando…';
    try {
      const response=await fetch(`/demo/ia/propostas-precos/${encodeURIComponent(proposal.id)}/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(action==='confirmar'?{confirmar:true}:{})});
      const result=await response.json();
      if(!response.ok){const messages={COTACAO_ALTERADA_PESQUISE_NOVAMENTE:'A cotação mudou desde a pesquisa. Peça uma nova consulta antes de confirmar.',PROPOSTA_EXPIRADA:'A proposta expirou. Faça uma nova pesquisa.',PROPOSTA_CANCELADA:'Esta proposta já foi cancelada.',FORNECEDOR_INATIVO:'O fornecedor está inativo.'};throw new Error(messages[result.detail?.codigo]||'Não foi possível salvar. Verifique sua permissão e tente novamente.');}
      message.textContent=action==='confirmar'?'Preço salvo. Tabelas e dashboard estão sendo atualizados.':'Nenhum preço foi alterado.';
      actions.remove();
      if(action==='confirmar')window.dispatchEvent(new Event('okto:cadastro'));
    } catch(error){message.textContent=error.message;confirm.disabled=cancel.disabled=false;}
  }
  confirm.addEventListener('click',()=>decide('confirmar'));cancel.addEventListener('click',()=>decide('cancelar'));
  actions.append(confirm,cancel);panel.append(actions,message);output.append(panel);
}

function bindOttoForm(input, button, output) {
  async function send() {
    const question = input.value.trim();
    if (question.length < 3) { output.textContent = 'Escreva uma pergunta com pelo menos 3 caracteres.'; return; }
    button.disabled = true;
    output.textContent = 'Otto está consultando os dados e pode pesquisar fontes externas…';
    try { showAnswer(output, await askOtto(question)); }
    catch (error) { output.textContent = error.message; }
    finally { button.disabled = false; }
  }
  button.addEventListener('click', send);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) send();
  });
}

(function floatingButton() {
  const spark = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4"/></svg>';
  const fab = document.createElement('button');
  fab.type = 'button';
  fab.className = 'otto-fab';
  fab.setAttribute('aria-expanded', 'false');
  fab.setAttribute('aria-controls', 'otto-chat');
  fab.innerHTML = spark + '<span>Otto</span>';
  const chat = document.createElement('section');
  chat.id = 'otto-chat';
  chat.className = 'otto-chat';
  chat.hidden = true;
  chat.setAttribute('aria-label', 'Perguntar ao Otto');
  chat.innerHTML = `
    <header><strong>${spark} Otto · assistente IA</strong>
      <button type="button" class="otto-close" aria-label="Fechar">×</button></header>
    <label for="otto-question">Pergunte sobre a operação ou pesquise fontes externas</label>
    <textarea id="otto-question" maxlength="2000" placeholder="Ex.: Pesquise fornecedores de batata em Blumenau e cite as fontes."></textarea>
    <div class="otto-actions"><span>Ctrl+Enter envia</span>
      <button type="button" class="button primary">Enviar</button></div>
    <div class="otto-output" role="status"></div>`;
  document.body.append(fab, chat);
  const toggle = (open) => {
    chat.hidden = !open;
    fab.setAttribute('aria-expanded', String(open));
    if (open) chat.querySelector('textarea').focus();
  };
  fab.addEventListener('click', () => toggle(chat.hidden));
  chat.querySelector('.otto-close').addEventListener('click', () => { toggle(false); fab.focus(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !chat.hidden) { toggle(false); fab.focus(); } });
  bindOttoForm(chat.querySelector('textarea'), chat.querySelector('.otto-actions .button'), chat.querySelector('.otto-output'));
})();
