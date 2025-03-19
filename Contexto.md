Documento Mestre – Bot de Telegram (Aiogram + Railway + PostgreSQL)

Contexto e Resumo
Este documento consolida as informações essenciais para o desenvolvimento de um bot de Telegram relacionado a cartas colecionáveis, usando Python (Aiogram), hospedagem gratuita no Railway e banco de dados PostgreSQL.

O projeto está dividido em duas partes principais:

- Parte 1 (Funcionalidades Essenciais): Cadastro de usuários, sistema de captura de cartas, inventário, loja, gerenciamento de moedas, sistema de trocas e ranking.
- Parte 2 (Expansões e Melhorias): Evolução de cartas, wishlist, painel de administradores mais avançado e outras funcionalidades adicionais.

Comandos – Lista Completa

1. Títulos por Quantidade de Cartas na Mochila
- Novato: 1 a 1k cartas
- Colecionador Casual: 1k a 3k cartas
- Colecionador Hardcore: 3k a 7k cartas
- Treinador Experiente: 7k a 13k cartas
- Líder de Ginásio: 13k a 21k cartas
- Elite Four: 21k a 35k cartas
- Campeão Pokémon: 35k a 41k cartas
- Professor Pokémon: 41k a 50k cartas
- Treinador Profissional: 50k a 70k cartas
- Completista: 70k em diante

2. Comandos para Administradores
- /add: Adicionar cartas
- /ban: Banir usuários do bot
- /addb: Adicionar banners para venda no perfil
- /adds: Adicionar sticker para venda no perfil
- /adddex: Adicionar modelos de binder/coleções para venda no perfil
- /rclicar: Recarregar giros
- /rcoins: Recarregar coins
- /mute: Dar mute no bot
- /ping: Ver tempo de resposta do bot
- /addesp: Adicionar tag
- /historico (id do player): Exibir histórico dos últimos 100 cards do player

3. Comandos Gerais
1. /jornada: Inscrever a pessoa no bot, solicitando um @ único para seu perfil.
2. /cap ou /capturar: Gira/captura uma carta (com gasto de pokébolas).
3. /evoluir ou /ev: Evoluir/personalizar uma carta (ao atingir certos marcos de quantidade de cartas).
4. /pokebola ou /pb: Exibir uma carta específica (por ID ou nome).
5. /mochila: Mostra o inventário completo do jogador.
6. /pokedex ou /pd: Mostrar a coleção/álbum.
7. /explorar: Ganha uma carta de graça a cada 12h (ou período definido).
8. /pokemart ou /pokem: Loja para compra de cartas de evento, stickers, banners.
9. /pokebanco: Exibe moedas (pokécoins), capturas e pokébolas.
10. /doar: Doar cartas ou capturas para outro jogador.
11. /roubar ou /r: Troca de cartas entre jogadores, com confirmação.
12. /ginasio: Mostrar ranking de quem tem mais cartas de um tipo específico.
13. /comprarbolas: Compra adicional de giros/pokébolas.
14. /favpoke: Define carta favorita.
15. /pokew: Adiciona cartas à wishlist.
16. /pokewish ou /wl: Exibe wishlist própria ou de terceiros (ao marcar outro usuário).
17. /pokerw: Remove cartas da wishlist.
18. /treinador: Ver perfil do jogador.
19. /dbola ou /deletebola: Deletar cartas específicas.
20. /ddex: Deletar uma coleção inteira.
21. /shiny: Ver cartas especiais/de evento (ainda em definição).
22. /pcat: Ver cativeiros do jogador.
23. /amantes: Casar com outro player (trocas cumulativas até chegar em casamento).
24. /discomon: Favoritar um álbum ou música no perfil.
25. /especie: Exibir tags de grupos/membros.
26. /digimon [@conta1] para [@conta2]: Liga contas para que recompensas caiam em uma conta principal.
27. /favemo: Define um emoji favorito que aparece no perfil.
28. /pokewish (sem parâmetros ou marcando outro player) mostra quantas cartas da wish do outro player você tem.

4. Comportamentos de Usuário
1. Mensagem de boas-vindas: Ao entrar no bot pela primeira vez, pede para escolher um @ para o perfil e informa sobre necessidade de estar no canal de notícias.
2. Quando atinge 50, 100, 500, 1k cartas, o jogador pode evoluir/personalizar vídeos nas cartas.
3. Favoritar carta e emoji: Aparecem no inventário, ginásio e perfil.
4. Casamento Amantes: A cada X trocas de cartas entre dois usuários, seu status de relacionamento sobe (Cortejando, Encontrando, Namorando, Noivando, Casado).
5. Comando /pokewish: Sozinho mostra a própria wishlist, marcando alguém mostra o que você tem da wishlist do outro.

5. Fluxo de Adição de Cartas (Mudança Solicitada)
A cliente deseja que, ao adicionar uma carta, o administrador:
1. Envie a imagem da carta com a legenda.
2. Responda a essa mensagem com o comando /addcarta.
3. O bot então salva a imagem, a legenda e cadastra a carta no sistema.

Isso é diferente do fluxo original que era mais textual. Será necessário detectar mensagens de imagem e texto (legenda), e vincular ao comando /addcarta quando ele for utilizado em resposta.

6. Estrutura Tecnológica
- Linguagem: Python
- Framework de Bot: Aiogram
- Banco de Dados: PostgreSQL (banco gratuito no Railway)
- Hospedagem: Railway (com Dockerfile ou buildpack)
- Controle de Versão: GitHub (repositório privado ou público)

7. Divisão do Projeto
- Parte 1: Comandos essenciais, cadastro, inventário, sistema de captura e loja, trocas básicas, ranking, etc.
- Parte 2: Evolução avançada, painel de admin, wishlist aperfeiçoada, funcionalidades extras e quaisquer outros requisitos adicionais.

8. Observações e Acordos
- Tempo de Entrega da Parte 1: aproximadamente 5 a 7 dias.
- Valor da Parte 1: R$ 150,00.
- Valor da Parte 2: R$ 150,00.
- A cliente pode pagar a Parte 2 no mês seguinte.
- Comando para dar capturas e coins aos admins será implementado na Parte 2, porém a base para /add, /addb etc. já estará na Parte 1.


Próximos Passos
1. Definir Escopo da Parte 1: Já foi definido que ficam na Parte 1 apenas as funcionalidades explicitamente combinadas. Os comandos para dar coins e banners extras para admins, por exemplo, ficarão para a Parte 2.
2. Criar Repositório no GitHub com a estrutura de pastas (docs, bot, database, tests).
3. Configurar Aiogram: Criar bot básico que responde a /start.
4. Configurar PostgreSQL no Railway e testar conexão.
5. Implementar Comandos da Parte 1 de forma modular (eventualmente com ajuda de IA para boilerplate).
6. Testar e Ajustar conforme feedback da cliente.


Este documento é o guia mestre para o desenvolvimento inicial do bot. Qualquer nova ideia ou mudança de requisitos deve ser adicionada aqui para evitar perda de contexto.


