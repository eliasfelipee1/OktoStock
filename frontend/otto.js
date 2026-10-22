'use strict';
// Botão flutuante do Otto, presente em todas as páginas. Sem token no navegador:
// o servidor responde pela operação configurada para esta instalação.
const OTTO_ERRORS = {
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
  return data.resposta;
}

// Formata **negrito** e `código` criando elementos; o texto da IA nunca vira HTML.
function showAnswer(output, text) {
  output.replaceChildren();
  text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/).forEach((part) => {
    if (/^\*\*.+\*\*$/.test(part)) output.append(Object.assign(document.createElement('strong'), { textContent: part.slice(2, -2) }));
    else if (/^`.+`$/.test(part)) output.append(Object.assign(document.createElement('code'), { textContent: part.slice(1, -1) }));
    else output.append(part.replace(/^#{1,6} /gm, ''));
  });
}

function bindOttoForm(input, button, output) {
  async function send() {
    const question = input.value.trim();
    if (question.length < 3) { output.textContent = 'Escreva uma pergunta com pelo menos 3 caracteres.'; return; }
    button.disabled = true;
    output.textContent = 'Otto está consultando os dados…';
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
    <label for="otto-question">Pergunte sobre estoque, vendas, fichas ou perdas</label>
    <textarea id="otto-question" maxlength="2000" placeholder="Ex.: O que está abaixo do mínimo?"></textarea>
    <div class="otto-actions"><span>Ctrl+Enter envia</span>
      <button type="button" class="button primary">Enviar</button></div>
    <p class="otto-output" role="status"></p>`;
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
