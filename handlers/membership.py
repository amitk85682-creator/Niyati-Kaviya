from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatMemberStatus

from config import logger
from group_room import group_manager

def _get_bot_name(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Get bot_name from context.bot_data"""
    return context.bot_data.get('bot_name', 'niyati')

async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle updates when the bot's own membership status in a group changes.
    Used for Phase 7 presence detection.
    """
    if not update.my_chat_member:
        return
        
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        return

    bot_name = _get_bot_name(context)
    new_status = update.my_chat_member.new_chat_member.status
    
    is_present = new_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]
    
    if is_present:
        logger.info(f"🟢 [{bot_name}] Added/Joined group {chat.title} ({chat.id})")
        await group_manager.update_presence(chat.id, bot_name, True)
    else:
        logger.info(f"🔴 [{bot_name}] Removed/Left group {chat.title} ({chat.id})")
        await group_manager.update_presence(chat.id, bot_name, False)
