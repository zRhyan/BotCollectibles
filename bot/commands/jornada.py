from aiogram.types import Message
from aiogram import Bot
from aiogram.filters import Command

# Simulating a database with dictionaries (replace with actual database logic later)
registered_users = {}  # Key: Telegram ID, Value: {"username": str, "nickname": str, "cards": [], "coins": int}
nicknames = set()  # Set to track all registered nicknames

async def jornada_command(message: Message, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username or "Usuário sem @"

    if user_id in registered_users:
        nickname = registered_users[user_id]["nickname"]
        await message.answer(f"Você já está registrado como @{nickname}, {username}! 🚀")
    else:
        await message.answer(
            "Bem-vindo à sua jornada! 🎉\n"
            "Por favor, escolha um @ único para o bot te chamar (sem espaços e com até 20 caracteres):"
        )

        # Wait for the user's response
        @bot.message_handler()
        async def handle_nickname_response(nickname_message: Message):
            nickname = nickname_message.text.strip()

            # Validate nickname
            if len(nickname) > 20:
                await nickname_message.answer("O @ deve ter no máximo 20 caracteres. Tente novamente:")
                return
            if " " in nickname:
                await nickname_message.answer("O @ não pode conter espaços. Tente novamente:")
                return
            if nickname in nicknames:
                await nickname_message.answer("Este @ já está em uso. Escolha outro:")
                return

            # Save the user and nickname
            registered_users[user_id] = {"username": username, "nickname": nickname, "cards": [], "coins": 0}
            nicknames.add(nickname)
            await nickname_message.answer(
                f"Parabéns, @{nickname}! Você agora está registrado no bot e pronto para capturar cartas! 🎉"
            )