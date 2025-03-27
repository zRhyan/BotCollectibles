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
    """
    Handles the /addcarta command to add a new card.
    Accepts images sent as photos or as Telegram files (documents).
    """
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
            "❗ **Erro:** Responda a uma mensagem contendo a imagem ou o arquivo do card e a legenda.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Extract the image file ID
    photo_file_id = None
    if message.reply_to_message.photo:
        # Get the highest resolution image
        photo_file_id = message.reply_to_message.photo[-1].file_id
    elif message.reply_to_message.document:
        # Check if the document is an image
        document = message.reply_to_message.document
        valid_extensions = {".jpg", ".jpeg", ".png"}
        if not any(document.file_name.lower().endswith(ext) for ext in valid_extensions):
            await message.reply(
                "❗ **Erro:** O arquivo enviado não é uma imagem válida. Apenas formatos `.jpg`, `.jpeg` e `.png` são aceitos.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        photo_file_id = document.file_id
    else:
        await message.reply(
            "❗ **Erro:** A mensagem respondida deve conter uma imagem ou um arquivo de imagem válido.",
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

    # Extract the caption
    caption = message.reply_to_message.caption

    # Parse the caption (e.g., "[nome do card] | [nome do grupo] | [nome da categoria] | [tag] | [raridade]")
    try:
        # Replace commas with pipes to standardize the delimiter
        caption = caption.replace(",", "|")
        parts = list(map(str.strip, caption.split("|")))

        # Ensure the required fields are present
        if len(parts) < 4:
            raise ValueError("Missing required fields in the caption.")

        card_name, group_name, category_name, rarity = parts[:4]
        tag_name = parts[4] if len(parts) > 4 else None  # Optional tag
    except ValueError:
        await message.reply(
            "⚠️ **Formato inválido!** A legenda deve estar no formato:\n"
            "`nome do card | nome do grupo | nome da categoria | raridade [| tag opcional]`\n"
            "⚠️ **Importante:**\n"
            "- Raridades permitidas: 🥇, 🥈, 🥉 (para cards normais) e 💎 (para cards de eventos).",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Validate rarity
    allowed_rarities = {"🥇", "🥈", "🥉", "💎"}
    if rarity not in allowed_rarities:
        await message.reply(
            f"❌ **Erro:** A raridade '{rarity}' é inválida.\n"
            f"Por favor, use apenas um destes emojis para a raridade: 🥇, 🥈, 🥉 e 💎.",
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

            # Ensure the tag exists (if provided)
            tag = None
            if tag_name:
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
                    "❌ **Erro:** Um card com este nome já existe no sistema.",
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

            # Associate the card with the tag (if provided)
            if tag:
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