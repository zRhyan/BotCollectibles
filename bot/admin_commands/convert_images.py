import os
import logging
import time
import asyncio
import traceback
from dotenv import load_dotenv
from aiogram import Router, types, Bot
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy.future import select
from database.models import User, Card
from database.session import get_session
from bot.utils.image_utils import ensure_photo_file_id

# Configurar logging específico para este módulo
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Definir nível de log para DEBUG para ver mais detalhes

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
    try:
        logger.debug(f"Comando /convertimages recebido de user_id={message.from_user.id}, username={message.from_user.username}")
        user_id = message.from_user.id
        
        # Verificar se o usuário já possui uma conversão em andamento
        if user_id in ongoing_conversions:
            status = ongoing_conversions[user_id]
            elapsed = time.time() - status["start_time"]
            
            logger.debug(f"Usuário {user_id} já tem conversão em andamento: {status}")
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
        logger.debug(f"Verificando permissões para {message.from_user.username} em {ALLOWED_USERNAMES}")
        if message.from_user.username not in ALLOWED_USERNAMES:
            logger.warning(f"Acesso negado para usuário {message.from_user.username} - não está na lista ALLOWED_USERNAMES")
            await message.reply(
                "🚫 **Acesso negado!** Você não tem permissão para usar este comando.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Check if the user is an admin
        logger.debug(f"Verificando se o usuário {user_id} é admin")
        try:
            admin_user = None
            async with get_session() as session:
                result = await session.execute(select(User).where(User.id == user_id))
                admin_user = result.scalar_one_or_none()
                
                if not admin_user:
                    logger.warning(f"Usuário {user_id} não encontrado no banco de dados")
                    await message.reply(
                        "❌ **Erro:** Seu usuário não foi encontrado no banco de dados.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                
                if admin_user.is_admin != 1:
                    logger.warning(f"Usuário {user_id} não é admin")
                    await message.reply(
                        "🚫 **Acesso negado!** Somente administradores podem usar este comando.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                
                logger.debug(f"Usuário {user_id} é admin, permissão concedida")
        except Exception as e:
            logger.error(f"Erro ao verificar permissões de admin: {str(e)}", exc_info=True)
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
        
        logger.debug(f"Modo selecionado: {mode}")
        
        # Enviar uma primeira mensagem para confirmar que o comando foi recebido
        await message.reply(
            "🔍 **Analisando cards no banco de dados...**\n"
            "Isso pode levar alguns instantes.",
            parse_mode=ParseMode.MARKDOWN
        )
        
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
            logger.debug(f"Registro de conversão iniciado para usuário {user_id}")
            
            # Buscar todos os cards do banco
            all_cards = []
            async with get_session() as session:
                result = await session.execute(select(Card))
                all_cards = result.scalars().all()
                total_cards = len(all_cards)
                
                logger.debug(f"Total de cards encontrados no banco: {total_cards}")
                
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
                            logger.debug(f"Card ID {card.id} precisa ser convertido")
                    except Exception as e:
                        logger.error(f"Erro ao verificar arquivo do card {card.id}: {str(e)}")
                        ongoing_conversions[user_id]["failed"] += 1
                
                # Enviar status de verificação
                need_conversion = len(to_convert)
                logger.debug(f"Cards que precisam ser convertidos: {need_conversion}")
                
                status_message = await message.reply(
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
                    logger.debug("Operação finalizada: modo check ou nada para converter")
                    return
                
                # Confirmar com o usuário antes de iniciar a conversão
                confirmation = await message.reply(
                    f"⚠️ **Deseja converter {need_conversion} imagens para o formato de foto?**\n\n"
                    f"Este processo pode demorar alguns minutos e você receberá várias notificações.\n"
                    f"Para continuar, responda a esta mensagem com '**sim**'.\n"
                    f"Para cancelar, responda com qualquer outra coisa ou ignore esta mensagem.",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Atualizar status
                ongoing_conversions[user_id]["status"] = "Aguardando confirmação..."
                logger.debug("Aguardando confirmação do usuário")
                
                # Remover o sistema de espera automática e usar um handler simples
                # O usuário precisa responder explicitamente
                
                # Vamos limpar a conversão atual enquanto esperamos confirmação explícita
                del ongoing_conversions[user_id]
                
                # O processamento continuará quando o usuário responder com outro comando
                # que será implementado na próxima etapa
                
        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.error(f"Erro durante análise inicial: {str(e)}\n{error_traceback}")
            
            # Limpar registro de conversão
            if user_id in ongoing_conversions:
                del ongoing_conversions[user_id]
                
            await message.reply(
                f"❌ **Erro durante análise:** {str(e)[:200]}\n"
                f"Verifique os logs para mais detalhes.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    except Exception as global_e:
        error_traceback = traceback.format_exc()
        logger.error(f"Erro global no comando convert_images: {str(global_e)}\n{error_traceback}")
        await message.reply(
            f"❌ **Erro crítico no comando:** {str(global_e)[:200]}\n"
            f"Verifique os logs para mais detalhes.",
            parse_mode=ParseMode.MARKDOWN
        )

# Implementar um comando separado para confirmar a conversão
@router.message(Command("confirmarconv"))
async def confirm_conversion(message: types.Message):
    """
    Comando para confirmar uma conversão de imagens pendente.
    Uso: /confirmarconv
    """
    try:
        logger.debug(f"Comando /confirmarconv recebido de user_id={message.from_user.id}")
        user_id = message.from_user.id
        
        # Verificar se o usuário é admin
        async with get_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            admin_user = result.scalar_one_or_none()
            
            if not admin_user or admin_user.is_admin != 1:
                logger.warning(f"Tentativa de confirmar conversão por não-admin: {user_id}")
                await message.reply(
                    "🚫 **Acesso negado!** Somente administradores podem usar este comando.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
        
        # Verificar se existem cards para converter
        all_cards = []
        to_convert = []
        
        async with get_session() as session:
            result = await session.execute(select(Card))
            all_cards = result.scalars().all()
            
            for card in all_cards:
                try:
                    file_info = await message.bot.get_file(card.image_file_id)
                    is_photo = 'photos' in file_info.file_path
                    
                    if not is_photo:
                        to_convert.append(card)
                except Exception:
                    # Ignorar erros de verificação neste ponto
                    pass
        
        need_conversion = len(to_convert)
        
        if need_conversion == 0:
            await message.reply(
                "✅ **Não há imagens para converter!**",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Iniciar registro da conversão
        ongoing_conversions[user_id] = {
            "status": "Convertendo imagens...",
            "converted": 0,
            "total": need_conversion,
            "failed": 0,
            "start_time": time.time()
        }
        
        # Informar que a conversão começou
        start_msg = await message.reply(
            f"✅ **Conversão iniciada!** Este processo pode levar alguns minutos...\n"
            f"Serão convertidas {need_conversion} imagens.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Processar cada card
        batch_size = 5  # Reduzido para evitar rate limits
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
                    async with get_session() as session:
                        # Buscar o card novamente para evitar problemas de sessão
                        card_result = await session.execute(select(Card).where(Card.id == card.id))
                        db_card = card_result.scalar_one_or_none()
                        
                        if db_card:
                            db_card.image_file_id = new_file_id
                            await session.commit()
                            converted += 1
                            ongoing_conversions[user_id]["converted"] = converted
                            logger.debug(f"Card ID {card.id} convertido com sucesso")
                        else:
                            logger.error(f"Card ID {card.id} não encontrado ao tentar salvar")
                            failed += 1
                            ongoing_conversions[user_id]["failed"] += 1
                else:
                    failed += 1
                    ongoing_conversions[user_id]["failed"] += 1
                    logger.warning(f"Falha ao obter novo file_id para card {card.id}")
                    
            except Exception as e:
                logger.error(f"Erro ao converter imagem do card {card.id}: {str(e)}", exc_info=True)
                failed += 1
                ongoing_conversions[user_id]["failed"] += 1
            
            processed += 1
            
            # Atualizar o usuário a cada X cards processados
            if processed % batch_size == 0:
                progress = (processed / need_conversion) * 100
                try:
                    await message.answer(
                        f"🔄 **Progresso:** {progress:.1f}%\n"
                        f"**Processados:** {processed}/{need_conversion}\n"
                        f"**Convertidos:** {converted}\n"
                        f"**Falhas:** {failed}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    # Pequena pausa para evitar rate limits do Telegram
                    await asyncio.sleep(1)
                except Exception as msg_error:
                    logger.error(f"Erro ao enviar atualização: {str(msg_error)}")
        
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
        logger.debug("Processo de conversão finalizado com sucesso")
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error(f"Erro durante confirmação de conversão: {str(e)}\n{error_traceback}")
        
        # Limpar registro de conversão
        if user_id in ongoing_conversions:
            del ongoing_conversions[user_id]
            
        await message.reply(
            f"❌ **Erro durante conversão:** {str(e)[:200]}\n"
            f"Verifique os logs para mais detalhes.",
            parse_mode=ParseMode.MARKDOWN
        )