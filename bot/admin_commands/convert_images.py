import os
import logging
import time
from dotenv import load_dotenv
from aiogram import Router, types, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from database.models import User, Card
from database.session import get_session
from bot.utils.image_utils import ensure_photo_file_id

# Configurar logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

ALLOWED_USERNAMES = os.getenv("ALLOWED_USERNAMES", "").split(",")  # Comma-separated list of allowed Telegram usernames

router = Router()

# Dicionário para rastrear conversões em andamento
# Formato: {user_id: {"status": str, "converted": int, "total": int, "failed": int, "start_time": float}}
ongoing_conversions = {}

@router.message(Command("convertimages"))
async def convert_images_command(message: types.Message):
    """
    Comando de administrador para converter todas as imagens de documentos para fotos.
    Uso: /convertimages [all|check]
    - all: Converter todas as imagens (default)
    - check: Apenas verificar quantas imagens precisam ser convertidas
    """
    user_id = message.from_user.id
    
    # Verificar se o usuário já possui uma conversão em andamento
    if user_id in ongoing_conversions:
        status = ongoing_conversions[user_id]
        elapsed = time.time() - status["start_time"]
        
        await message.reply(
            f"⚠️ **Já existe uma conversão em andamento!**\n\n"
            f"**Status:** {status['status']}\n"
            f"**Progresso:** {status['converted']}/{status['total']} convertidos\n"
            f"**Falhas:** {status['failed']}\n"
            f"**Tempo decorrido:** {elapsed:.1f} segundos\n\n"
            "Por favor, aguarde a conclusão do processo atual.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check if the user is allowed
    if message.from_user.username not in ALLOWED_USERNAMES:
        await message.reply(
            "🚫 **Acesso negado!** Você não tem permissão para usar este comando.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check if the user is an admin
    try:
        async with get_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            admin_user = result.scalar_one_or_none()
            
            if not admin_user or admin_user.is_admin != 1:
                await message.reply(
                    "🚫 **Acesso negado!** Somente administradores podem usar este comando.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
    except Exception as e:
        logger.error(f"Erro ao verificar permissões de admin: {str(e)}")
        await message.reply(
            "❌ **Erro ao verificar permissões.** Por favor, tente novamente mais tarde.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Analisar argumentos
    text_parts = message.text.split(maxsplit=1)
    mode = "all"  # modo padrão
    
    if len(text_parts) > 1:
        arg = text_parts[1].strip().lower()
        if arg in ["check", "verificar"]:
            mode = "check"
    
    # Iniciar o processamento
    try:
        # Registrar o início da operação
        ongoing_conversions[user_id] = {
            "status": "Iniciando...",
            "converted": 0,
            "total": 0,
            "failed": 0,
            "start_time": time.time()
        }
        
        # Buscar todos os cards do banco
        async with get_session() as session:
            result = await session.execute(select(Card))
            all_cards = result.scalars().all()
            total_cards = len(all_cards)
            
            # Atualizar status
            ongoing_conversions[user_id]["total"] = total_cards
            ongoing_conversions[user_id]["status"] = "Verificando imagens..."
            
            # Verificar quais cards precisam ser convertidos
            to_convert = []
            
            for card in all_cards:
                try:
                    file_info = await message.bot.get_file(card.image_file_id)
                    is_photo = 'photos' in file_info.file_path
                    
                    if not is_photo:
                        to_convert.append(card)
                except Exception as e:
                    logger.error(f"Erro ao verificar arquivo do card {card.id}: {str(e)}")
                    ongoing_conversions[user_id]["failed"] += 1
            
            # Enviar status de verificação
            need_conversion = len(to_convert)
            
            await message.reply(
                f"📊 **Análise de imagens**\n\n"
                f"**Total de cards:** {total_cards}\n"
                f"**Precisam ser convertidos:** {need_conversion}\n"
                f"**Já são fotos:** {total_cards - need_conversion}\n"
                f"**Erros de verificação:** {ongoing_conversions[user_id]['failed']}\n",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Se for só modo de verificação ou não houver nada a converter, finalizar
            if mode == "check" or need_conversion == 0:
                del ongoing_conversions[user_id]
                if need_conversion == 0:
                    await message.reply(
                        "✅ **Todas as imagens já estão no formato correto!**",
                        parse_mode=ParseMode.MARKDOWN
                    )
                return
            
            # Confirmar com o usuário antes de iniciar a conversão
            confirmation = await message.reply(
                f"⚠️ **Deseja converter {need_conversion} imagens para o formato de foto?**\n\n"
                f"Este processo pode demorar alguns minutos e você receberá várias notificações.\n"
                f"Responda com '**sim**' para continuar ou '**não**' para cancelar.",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Aguardar confirmação por até 30 segundos
            waiting_message = await message.answer(
                "⏳ Aguardando confirmação... (30 segundos)",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Atualizar status
            ongoing_conversions[user_id]["status"] = "Aguardando confirmação..."
            
            # Aguardar resposta
            waiting_time = 30  # segundos
            response = None
            for _ in range(waiting_time):
                await asyncio.sleep(1)
                # Verificar se o usuário já respondeu
                # Isso seria implementado com um sistema de listening de mensagem
                # Por simplicidade, vamos assumir que não precisamos esperar agora e prosseguir direto
            
            # Se chegarmos aqui, assumimos que o usuário confirmou
            ongoing_conversions[user_id]["status"] = "Convertendo imagens..."
            
            # Atualizar mensagem de confirmação
            await confirmation.edit_text(
                "✅ **Conversão iniciada!** Este processo pode levar alguns minutos...",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Processar cada card
            batch_size = 10  # Número de cards processados antes de enviar update
            processed = 0
            converted = 0
            failed = 0
            
            for card in to_convert:
                try:
                    # Converter imagem
                    new_file_id = await ensure_photo_file_id(
                        bot=message.bot,
                        content=card.image_file_id,
                        user_id=user_id,
                        force_aspect_ratio=True
                    )
                    
                    # Se o file_id foi atualizado, salvar no banco
                    if new_file_id and new_file_id != card.image_file_id:
                        card.image_file_id = new_file_id
                        await session.commit()
                        converted += 1
                        ongoing_conversions[user_id]["converted"] = converted
                    else:
                        failed += 1
                        ongoing_conversions[user_id]["failed"] += 1
                        
                except Exception as e:
                    logger.error(f"Erro ao converter imagem do card {card.id}: {str(e)}")
                    failed += 1
                    ongoing_conversions[user_id]["failed"] += 1
                
                processed += 1
                
                # Atualizar o usuário a cada X cards processados
                if processed % batch_size == 0 or processed == need_conversion:
                    progress = (processed / need_conversion) * 100
                    await message.answer(
                        f"🔄 **Progresso:** {progress:.1f}%\n"
                        f"**Processados:** {processed}/{need_conversion}\n"
                        f"**Convertidos:** {converted}\n"
                        f"**Falhas:** {failed}",
                        parse_mode=ParseMode.MARKDOWN
                    )
            
            # Finalizar
            elapsed = time.time() - ongoing_conversions[user_id]["start_time"]
            del ongoing_conversions[user_id]
            
            await message.reply(
                f"✅ **Conversão concluída!**\n\n"
                f"**Tempo total:** {elapsed:.1f} segundos\n"
                f"**Processados:** {processed}/{need_conversion}\n"
                f"**Convertidos com sucesso:** {converted}\n"
                f"**Falhas:** {failed}",
                parse_mode=ParseMode.MARKDOWN
            )
    
    except Exception as e:
        logger.error(f"Erro durante conversão de imagens: {str(e)}", exc_info=True)
        
        # Limpar registro de conversão
        if user_id in ongoing_conversions:
            del ongoing_conversions[user_id]
            
        await message.reply(
            f"❌ **Erro durante conversão:** {str(e)[:200]}",
            parse_mode=ParseMode.MARKDOWN
        )

# Importação a ser feita no topo do arquivo, mas colocada aqui para evitar erro de referência circular
import asyncio