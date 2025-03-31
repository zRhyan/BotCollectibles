from aiogram import Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from database.session import get_session
from database.models import User, Group

router = Router()

@router.message(Command(commands=["imgpd"]))
async def imgpd_command(message: Message) -> None:
    """
    Comando exclusivo para administradores: associa uma imagem a um grupo específico.
    Uso:
    - /imgpd <id ou nome do grupo> (enviado com imagem OU respondendo a imagem)
    """
    user_id = message.from_user.id

    async with get_session() as session:
        # Verifica se o usuário é admin
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user or user.is_admin != 1:
            await message.reply("❌ Você não tem permissão para usar este comando.")
            return

        # Verifica se veio com argumento
        text_parts = message.text.strip().split(maxsplit=1)
        if len(text_parts) < 2:
            await message.reply(
                "❗ Uso incorreto. Envie o comando assim: `/imgpd <id ou nome_do_grupo>`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        group_arg = text_parts[1].strip()

        # Detecta imagem: na própria mensagem ou na mensagem respondida
        image_file_id = None
        if message.photo:
            image_file_id = message.photo[-1].file_id
        elif message.reply_to_message and message.reply_to_message.photo:
            image_file_id = message.reply_to_message.photo[-1].file_id

        if not image_file_id:
            await message.reply("❗ Nenhuma imagem detectada. Envie uma imagem ou responda a uma imagem com o comando.")
            return

        # Identifica o grupo pelo ID ou nome
        group = None
        if group_arg.isdigit():
            group_id = int(group_arg)
            group_result = await session.execute(select(Group).where(Group.id == group_id))
            group = group_result.scalar_one_or_none()
        else:
            group_result = await session.execute(select(Group).where(Group.name.ilike(f"%{group_arg}%")))
            groups_found = group_result.scalars().all()
            if len(groups_found) == 1:
                group = groups_found[0]
            elif len(groups_found) > 1:
                await message.reply(
                    "⚠️ Há mais de um grupo com esse nome. Por favor, utilize o ID do grupo (veja com /pokedex)."
                )
                return
            else:
                group = None

        if not group:
            await message.reply("❌ Grupo não encontrado.")
            return

        # Atualiza a imagem
        await session.execute(
            update(Group)
            .where(Group.id == group.id)
            .values(image_file_id=image_file_id)
        )
        await session.commit()

        await message.reply(f"✅ Imagem associada com sucesso ao grupo {group.id}. {group.name}!")