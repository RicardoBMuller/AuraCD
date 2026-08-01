# Revisão AuraCD 2.7

## Correção principal: próxima faixa automática

O problema estava no monitor de reprodução do backend. O campo `started_at`, usado para medir há quanto tempo a faixa estava tocando, era atualizado em todas as consultas ao driver. Quando a música acabava, o tempo calculado desde o início ficava sempre abaixo do mínimo necessário e a troca automática não era executada.

A versão 2.7 mantém o horário real de início e combina três fontes para detectar o final:

- duração conhecida no TOC do CD;
- última posição válida retornada pelo leitor;
- tempo monotônico transcorrido desde o PLAY ou RESUME.

Também foram adicionadas duas amostras consecutivas de estado parado, evitando que um `STOP` transitório do MCI pule uma faixa indevidamente.

## Visual

- identidade `AuraCD MS-2700`;
- painel inspirado em micro systems e decks Hi-Fi;
- indicadores POWER, AUTO NEXT e PCM;
- caixas acústicas decorativas em monitores grandes;
- novos detalhes no transport deck, LCD e painel de informações;
- layout responsivo preservado.

## Validação

- 10 testes automatizados aprovados;
- Python compilado sem erros;
- JavaScript validado com `node --check`;
- HTML analisado sem erro de parsing;
- chaves CSS balanceadas.
