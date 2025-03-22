# Master Document - Telegram Bot (Aiogram + Railway + PostgreSQL)

## Context and Summary
This document consolidates essential information for developing a Telegram bot related to collectible cards, using Python (Aiogram), free hosting on Railway, and PostgreSQL database.

The project is divided into two main parts:
- Part 1 (Essential Functionalities): User registration, card capture system, inventory, store, coin management, trading system, and ranking.
- Part 2 (Expansions and Improvements): Card evolution, wishlist, advanced admin panel, and other additional functionalities.

## Commands - Complete List

### 1. Titles by Number of Cards in Backpack
- Novato: 1 a 1k cards
- Colecionador Casual: 1k a 3k cards
- Colecionador Hardcore: 3k a 7k cards
- Treinador Experiente: 7k a 13k cards
- Líder de Ginásio: 13k a 21k cards
- Elite Four: 21k a 35k cards
- Campeão Pokémon: 35k a 41k cards
- Professor Pokémon: 41k a 50k cards
- Treinador Profissional: 50k a 70k cards
- Completista: 70k em diante

### 2. Admin Commands
- /add: Add cards
- /ban: Ban users from the bot
- /addb: Add banners for sale in profile
- /adds: Add stickers for sale in profile
- /adddex: Add binder/collection models for sale in profile
- /rclicar: Reload spins
- /rcoins: Reload coins
- /mute: Mute the bot
- /ping: Check bot response time
- /addesp: Add tag
- /historico (player id): Display player's last 100 card history

### 3. General Commands
1. /jornada: Register the person in the bot, requesting a unique @ for their profile.
2. /cap or /capturar: Spin/capture a card (using pokéballs).
3. /evoluir or /ev: Evolve/customize a card (upon reaching certain card quantity milestones).
4. /pokebola or /pb: Display a specific card (by ID or name).
5. /mochila: Show the player's complete inventory.
6. /pokedex or /pd: Show the collection/album.
7. /explorar: Get a free card every 12h (or defined period).
8. /pokemart or /pokem: Store for purchasing event cards, stickers, banners.
9. /pokebanco: Display coins (pokécoins), captures, and pokéballs.
10. /doar: Donate cards or captures to another player.
11. /roubar or /r: Trading cards between players, with confirmation.
12. /ginasio: Show ranking of who has more cards of a specific type.
13. /comprarbolas: Additional purchase of spins/pokéballs.
14. /favpoke: Set favorite card.
15. /pokew: Add cards to wishlist.
16. /pokewish or /wl: Display own wishlist or others' (when tagging another user).
17. /pokerw: Remove cards from wishlist.
18. /treinador: View player profile.
19. /dbola or /deletebola: Delete specific cards.
20. /ddex: Delete an entire collection.
21. /shiny: View special/event cards (still in definition).
22. /pcat: View player's captives.
23. /amantes: Marry another player (cumulative trades until reaching marriage).
24. /discomon: Favorite an album or music in profile.
25. /especie: Display tags of groups/members.
26. /digimon [@account1] for [@account2]: Link accounts so rewards fall into a main account.
27. /favemo: Define a favorite emoji that appears in the profile.
28. /pokewish (without parameters or tagging another player) shows how many cards from the other player's wish you have.

### 4. User Behaviors
1. Welcome message: When entering the bot for the first time, asks to choose an @ for the profile and informs about the need to be in the news channel.
2. When reaching 50, 100, 500, 1k cards, the player can evolve/customize videos on cards.
3. Favorite card and emoji: Appear in inventory, gym, and profile.
4. Lovers Marriage: Every X card trades between two users, their relationship status rises (Courting, Meeting, Dating, Engaged, Married).
5. /pokewish command: Alone shows your own wishlist, tagging someone shows what you have from the other's wishlist.

### 5. Card Addition Flow (Requested Change)
The client wants that, when adding a card, the administrator:
1. Sends the card image with the caption.
2. Responds to this message with the command /addcarta.
3. The bot then saves the image, caption, and registers the card in the system.

This differs from the original flow which was more textual. It will be necessary to detect image and text messages (caption), and link to the /addcarta command when it's used in response.

### 6. Technological Structure
- Language: Python
- Bot Framework: Aiogram
- Database: PostgreSQL (free database on Railway)
- Hosting: Railway (with Procfile)
- Version Control: GitHub (private repository)

### 7. Project Division
- Part 1: Essential commands, registration, inventory, capture system and store, basic trades, ranking, etc.
- Part 2: Advanced evolution, admin panel, improved wishlist, extra functionalities, and any other additional requirements.

### 8. Notes and Agreements
- Delivery Time for Part 1: approximately 5 to 7 days.
- Value of Part 1: R$ 150.00.
- Value of Part 2: R$ 150.00.
- The client can pay for Part 2 in the following month.
- Command to give captures and coins to admins will be implemented in Part 2, but the foundation for /add, /addb etc. will already be in Part 1.

## Next Steps
1. Define Scope of Part 1: It has already been defined that only explicitly agreed functionalities remain in Part 1. Commands to give coins and extra banners to admins, for example, will be in Part 2.
2. Create GitHub Repository with folder structure (docs, bot, database, tests).
3. Configure Aiogram: Create basic bot that responds to /start.
4. Configure PostgreSQL on Railway and test connection.
5. Implement Part 1 Commands in a modular way (eventually with AI help for boilerplate).
6. Test and Adjust according to client feedback.

## Current project structure:
```
$ tree -I "venv/"
.
├── bot
│   ├── commands
│   │   ├── help.py
│   │   ├── jornada.py
│   │   └── start.py
│   ├── __init__.py
│   └── main.py
├── Contexto.md
├── database
│   ├── migrations
│   └── schema.sql
├── docs
├── Procfile
├── README.md
├── requirements.txt
└── tests
7 directories, 9 files
```

## requirements.txt:
```
aiogram==3.18.0
sqlalchemy==2.0.39
asyncpg==0.30.0
python-dotenv==1.0.1
psycopg2-binary==2.9.10
```

I am using FSM States to manage states.

This document is the master guide for the initial development of the bot. Any new ideas or requirement changes should be added here to avoid losing context.