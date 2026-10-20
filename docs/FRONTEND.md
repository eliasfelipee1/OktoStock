# Frontend HTML + CSS

Abra `frontend/index.html` diretamente no navegador ou execute `python -m uvicorn app.main:app --reload` e acesse `http://127.0.0.1:8000/painel/`. Não precisa de banco para visualizar a estrutura.

As cinco telas são visão geral, estoque, vendas, fichas técnicas e Otto. Não há JavaScript, framework, CDN ou dados fictícios. Indicadores mostram travessão e painéis mostram espera pela integração, sem afirmar que o banco real está vazio. Os registros serão cadastrados posteriormente.

A interface estática não consulta a API nem envia perguntas. Adicionar a chave ativa somente o backend do Otto. Para exibir os dados reais mantendo HTML/CSS, a próxima etapa pode usar templates renderizados pelo Python, sessão autenticada e formulários com proteção CSRF. Outra opção é autorizar JavaScript posteriormente.

A API já consulta as tabelas reais por operação autenticada. O prompt de Otto exige que dados ausentes sejam declarados, sem inventar valores ou usar o documento de receitas como cadastro. As credenciais nunca devem ficar no HTML.
