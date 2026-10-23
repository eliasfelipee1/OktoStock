"""Extrai fontes citadas sem expor consultas, conteúdo cifrado ou HTML do provedor."""
from urllib.parse import urlsplit


def safe_source(citation):
    if not isinstance(citation, dict) or citation.get('type') != 'web_search_result_location':
        return None
    url = citation.get('url')
    if not isinstance(url, str) or any(ord(c) < 32 for c in url):
        return None
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
            return None
    except ValueError:
        return None
    title = citation.get('title')
    return {'url': url, 'titulo': title if isinstance(title, str) and title.strip() else parsed.hostname}


def extract(blocks):
    sources, segments, warnings = [], [], []
    searched = False
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = block.get('type')
        if kind == 'server_tool_use' and block.get('name') == 'web_search':
            searched = True
        if kind == 'web_search_tool_result':
            searched = True
            result = block.get('content')
            if isinstance(result, dict) and result.get('type') == 'web_search_tool_result_error':
                warnings.append('A pesquisa externa encontrou uma limitação. As fontes exibidas podem cobrir apenas parte da pergunta.')
        if kind == 'text' and isinstance(block.get('text'), str):
            citations = block.get('citations') or []
            refs = []
            for citation in citations if isinstance(citations, list) else []:
                source = safe_source(citation)
                if source:
                    if not any(s['url'] == source['url'] for s in sources):
                        sources.append({**source, 'id': len(sources) + 1})
                    index = next(s['id'] for s in sources if s['url'] == source['url'])
                    if index not in refs:
                        refs.append(index)
            segments.append({'texto': block['text'], 'fontes': refs})
    if searched and not sources:
        warnings.append('A pesquisa não produziu fontes citadas verificáveis nesta resposta. Não considere preços ou informações externas como confirmados.')
    return {'blocos': segments, 'fontes_web': sources, 'pesquisa_web_utilizada': searched,
            'avisos': list(dict.fromkeys(warnings))}
