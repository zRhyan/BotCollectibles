from aiogram import Router, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from database.models import User, Card, Group, Category, Tag, card_tags
from database.session import get_session

router = Router()

@router.message(Command(commands=["addcarta", "add"]))
async def add_card(message: types.Message):
    # Check if the user is an admin
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == message.from_user.id))
        user = result.scalar_one_or_none()

        if not user or user.is_admin == 0:
            await message.reply(
                "🚫 **Acesso negado!** Somente administradores podem usar este comando.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # Ensure the command is a reply to a message
    if not message.reply_to_message:
        await message.reply(
            "❗ **Erro:** Responda a uma mensagem contendo a imagem e a legenda do card.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Ensure the replied message contains an image
    if not message.reply_to_message.photo:
        await message.reply(
            "❗ **Erro:** A mensagem respondida deve conter uma imagem do card.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Ensure the replied message contains a caption
    if not message.reply_to_message.caption:
        await message.reply(
            "❗ **Erro:** A mensagem respondida deve conter uma legenda com os campos necessários.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Extract image file ID and caption
    photo_file_id = message.reply_to_message.photo[-1].file_id  # Get the highest resolution image
    caption = message.reply_to_message.caption

    # Parse the caption (e.g., "[nome do card] | [nome do grupo] | [nome da categoria] | [tag] | [raridade]")
    try:
        # Replace commas with pipes to standardize the delimiter
        caption = caption.replace(",", "|")
        card_name, group_name, category_name, tag_name, rarity = map(str.strip, caption.split("|"))
    except ValueError:
        await message.reply(
            "⚠️ **Formato inválido!** A legenda deve estar no formato:\n"
            "`[nome do card] | [nome do grupo] | [nome da categoria] | [tag] | [raridade]`\n"
            "ou\n"
            "`[nome do card], [nome do grupo], [nome da categoria], [tag], [raridade]`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Save the card in the database
    async with get_session() as session:
        try:
            # Ensure the category exists
            result = await session.execute(select(Category).where(Category.name == category_name))
            category = result.scalar_one_or_none()
            if not category:
                category = Category(name=category_name)
                session.add(category)
                await session.flush()  # Ensure the category ID is available

            # Ensure the group exists
            result = await session.execute(select(Group).where(Group.name == group_name, Group.category_id == category.id))
            group = result.scalar_one_or_none()
            if not group:
                group = Group(name=group_name, category_id=category.id)
                session.add(group)
                await session.flush()  # Ensure the group ID is available

            # Ensure the tag exists
            result = await session.execute(select(Tag).where(Tag.name == tag_name))
            tag = result.scalar_one_or_none()
            if not tag:
                tag = Tag(name=tag_name)
                session.add(tag)
                await session.flush()  # Ensure the tag ID is available

            # Check if the card already exists
            result = await session.execute(select(Card).where(Card.name == card_name))
            if result.scalar_one_or_none():
                await message.reply(
                    "Um card com este nome já existe no sistema.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Add the new card
            new_card = Card(
                name=card_name,
                rarity=rarity,
                image_file_id=photo_file_id,
                group_id=group.id
            )
            session.add(new_card)
            await session.flush()  # Ensure the card ID is available

            # Associate the card with the tag
            await session.execute(card_tags.insert().values(card_id=new_card.id, tag_id=tag.id))

            await session.commit()

            # Confirm success
            await message.reply(
                f"✅ **Sucesso!** O card '{card_name}' foi adicionado ao sistema! 🃏✨",
                parse_mode=ParseMode.MARKDOWN
            )

        except IntegrityError:
            await session.rollback()
            await message.reply(
                "❌ **Erro:** Ocorreu um problema ao salvar o card no banco de dados.",
                parse_mode=ParseMode.MARKDOWN
            )