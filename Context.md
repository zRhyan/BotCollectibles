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
1.  (X) /add: Add cards
2.  ( ) /ban: Ban users from the bot
3.  ( ) /addb: Add banners for sale in profile
4.  ( ) /adds: Add stickers for sale in profile
5.  ( ) /adddex: Add binder/collection models for sale in profile
6.  ( ) /rclicar: Reload spins
7.  ( ) /rcoins: Reload coins
8.  ( ) /mute: Mute the bot
9.  ( ) /ping: Check bot response time
10. ( ) /addesp: Add tag
11. ( ) /historico (@nickname): Display player's last 100 card history
12. ( ) /admin (@nickname)

### 3. General Commands
1.  (X) /jornada: Register the person in the bot, requesting a unique @ for their profile.
2.  (X) /cap or /capturar: Spin/capture a card (using pokéballs).
3.  ( ) /evoluir or /ev: Evolve/customize a card (upon reaching certain card quantity milestones).
4.  ( ) /pokebola or /pb: Display a specific card (by ID or name).
5.  (X) /mochila: Show the player's complete inventory.
6.  ( ) /pokedex or /pd: Show the collection/album.
7.  ( ) /explorar: Get a free card every 12h (or defined period).
8.  ( ) /pokemart or /pokem: Store for purchasing event cards, stickers, banners.
9.  (X) /pokebanco: Display coins (pokécoins), captures, and pokéballs.
10. ( ) /doar: Donate cards or captures to another player.
11. ( ) /roubar or /r: Trading cards between players, with confirmation.
12. ( ) /ginasio: Show ranking of who has more cards of a specific type.
13. ( ) /comprarbolas: Additional purchase of spins/pokéballs.
14. ( ) /favpoke: Set favorite card.
15. ( ) /pokew: Add cards to wishlist.
16. ( ) /pokewish or /wl: Display own wishlist or others' (when tagging another user).
17. ( ) /pokerw: Remove cards from wishlist.
18. ( ) /treinador: View player profile.
19. ( ) /dbola or /deletebola: Delete specific cards.
20. ( ) /ddex: Delete an entire collection.
21. ( ) /shiny: View special/event cards (still in definition).
22. ( ) /pcat: View player's captives.
23. ( ) /amantes: Marry another player (cumulative trades until reaching marriage).
24. ( ) /discomon: Favorite an album or music in profile.
25. ( ) /especie: Display tags of groups/members.
26. ( ) /digimon [@account1] for [@account2]: Link accounts so rewards fall into a main account.
27. ( ) /favemo: Define a favorite emoji that appears in the profile.
28. ( ) /pokewish (without parameters or tagging another player) shows how many cards from the other player's wish you have.

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
1. Define Scope of Part 1: It has already been defined that only explicitly agreed functionalities remain in Part 1. Commands to give coins and extra banners to admins, for example, will be in Part 2.(X)
2. Create GitHub Repository with folder structure (docs, bot, database, tests). (X)
3. Configure Aiogram: Create basic bot that responds to /start. (X)
4. Configure PostgreSQL on Railway and test connection. (X)
5. Implement Part 1 Commands in a modular way (eventually with AI help for boilerplate). ( )
6. Test and Adjust according to client feedback. ( )

## Current project structure:
```
$ tree -I "venv/"
.
├── bot
│   ├── commands
│   │   ├── help.py
│   │   ├── jornada.py
│   │   ├── mochila.py
│   │   └── start.py
│   ├── __init__.py
│   └── main.py
├── bot.log
├── Context.md
├── Contexto.md
├── database
│   ├── crud_user.py
│   ├── __init__.py
│   ├── migrations
│   ├── models.py
│   ├── schema.sql
│   ├── session.py
│   └── test_db_connection.py
├── docs
├── Procfile
├── README.md
├── requirements.txt
└── tests

7 directories, 18 files

```
## Current Database Structure:

### 1. Users Table (`users`)
**Purpose**: Stores information about bot users.

**Columns**:
- `id` (BigInteger, Primary Key): The Telegram ID of the user.
- `username` (String, Nullable): The Telegram username of the user.
- `nickname` (String, Unique, Not Null): A unique nickname chosen by the user.
- `coins` (Integer, Default: 0): The number of coins the user has.

**Relationships**:
- One-to-Many with `inventory` (via `Inventory.user_id`)

---

### 2. Cards Table (`cards`)
**Purpose**: Stores information about collectible cards.

**Columns**:
- `id` (Integer, Primary Key, Auto-increment): The unique ID of the card.
- `name` (String, Not Null): The name of the card.
- `rarity` (String, Not Null): The rarity level of the card (e.g., *Common*, *Rare*).

**Relationships**:
- One-to-Many with `inventory` (via `Inventory.card_id`)

---

### 3. Inventory Table (`inventory`)
**Purpose**: Links users to the cards they own and tracks the quantity of each card.

**Columns**:
- `id` (Integer, Primary Key, Auto-increment): The unique ID of the inventory record.
- `user_id` (BigInteger, Foreign Key to `users.id`, Not Null): The ID of the user who owns the card.
- `card_id` (Integer, Foreign Key to `cards.id`, Not Null): The ID of the card.
- `quantity` (Integer, Default: 1): The number of this card the user owns.

**Relationships**:
- Many-to-One with `users` (via `user_id`)
- Many-to-One with `cards` (via `card_id`)

---

### Relationships Summary

- One **User** (`users`) can have many **Inventory** records (`inventory`).
- One **Card** (`cards`) can appear in many **Inventory** records (`inventory`).
- The **inventory** table acts as a **many-to-many** relationship between users and cards, with an additional `quantity` field to track how many of each card a user owns.





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