# widhvans/store/widhvans-store-a32dae6d5f5487c7bc78b13e2cdc18082aef6c58/handlers/start.py

import logging
import re
import time 
from pyrogram import Client, filters, enums
from pyrogram.errors import UserNotParticipant, MessageNotModified, ChatAdminRequired, ChannelInvalid, PeerIdInvalid, ChannelPrivate, MessageDeleteForbidden, UserIsBlocked
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import Config
from database.db import add_user, get_file_by_unique_id, get_user, is_user_verified, claim_verification_for_file, update_user, record_daily_view
from utils.helpers import get_main_menu
from features.shortener import get_shortlink

logger = logging.getLogger(__name__)


@Client.on_message(filters.private & ~filters.command("start") & (filters.document | filters.video | filters.audio))
async def handle_private_file(client, message):
    if not client.owner_db_channel:
        return await message.reply_text("The bot is not yet configured by the admin. Please try again later.")
    
    processing_msg = await message.reply_text("⏳ Processing your file...", reply_to_message_id=message.id)
    try:
        media = getattr(message, message.media.value, None)
        if not media:
            return await processing_msg.edit_text("Could not find media in the message.")

        copied_message = await message.copy(client.owner_db_channel)
        download_link = f"http://{client.vps_ip}:{client.vps_port}/download/{copied_message.id}"
        
        buttons = [[InlineKeyboardButton("📥 Fast Download", url=download_link)]]
        keyboard = InlineKeyboardMarkup(buttons)
        
        file_name = getattr(media, "file_name", "unknown.file")
        
        await client.send_cached_media(
            chat_id=message.chat.id,
            file_id=media.file_id,
            caption=f"`{file_name}`",
            reply_markup=keyboard,
            reply_to_message_id=message.id
        )
        await processing_msg.delete()
    except UserIsBlocked:
        logger.warning(f"Could not send private file to user {message.from_user.id} as they blocked the bot.")
        await processing_msg.delete()
    except Exception as e:
        logger.exception("Error in handle_private_file")
        await processing_msg.edit_text(f"An error occurred: {e}")

async def send_file(client, requester_id, owner_id, file_unique_id):
    """Sends the correct, user-owned file to the person who requested it."""
    try:
        file_data = await get_file_by_unique_id(owner_id, file_unique_id)
        if not file_data:
            return await client.send_message(requester_id, "Sorry, this file is no longer available or the link is invalid.")
        
        owner_settings = await get_user(file_data['owner_id'])
        if not owner_settings:
             return await client.send_message(requester_id, "A configuration error occurred on the bot.")

        # --- STATS: A direct file send also counts as a view ---
        await record_daily_view(owner_id, requester_id)

        download_link = f"http://{client.vps_ip}:{client.vps_port}/download/{file_data['stream_id']}"
        
        buttons = [[InlineKeyboardButton("📥 Fast Download", url=download_link)]]
        keyboard = InlineKeyboardMarkup(buttons)
        
        file_name_raw = file_data.get('file_name', 'N/A')
        
        # --- DECREED FIX: START ---
        # Corrected the invalid regex character range from '0--9' to '0-9'.
        # This resolves the `re.error: bad character range` exception.
        file_name_semi_cleaned = re.sub(r'@[a-zA-Z0-9_]+', '', file_name_raw).strip()
        # --- DECREED FIX: END ---
        
        file_name_semi_cleaned = re.sub(r'(www\.|https?://)\S+', '', file_name_semi_cleaned).strip()
        file_name_semi_cleaned = file_name_semi_cleaned.replace('_', ' ')
        
        filename_part = ""
        filename_url = owner_settings.get("filename_url") if owner_settings else None

        if filename_url:
            filename_part = f"[{file_name_semi_cleaned}]({filename_url})"
        else:
            filename_part = f"`{file_name_semi_cleaned}`"

        caption = f"✅ **Here is your file!**\n\n{filename_part}"
        
        # --- Appending the user-requested hyperlinked text with emojis. ---
        caption += "\n\n😈 [desi 18+](https://t.me/Telegam_db_bot?start=pay) 🔥"

        # --- DECREED FIX: START ---
        # The primary error originates here. The `from_chat_id` was unresolvable.
        # 1. Switched `Config.OWNER_DB_CHANNEL` to `client.owner_db_channel` for consistency.
        # 2. Added a specific exception for `ValueError` to provide a clear error message
        #    to the admin, guiding them to the correct solution.
        await client.copy_message(
            chat_id=requester_id,
            from_chat_id=client.owner_db_channel,
            message_id=file_data['file_id'],
            caption=caption,
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )
        # --- DECREED FIX: END ---

    except UserIsBlocked:
        logger.warning(f"Could not send file to user {requester_id} as they blocked the bot.")
    except ValueError as e:
        # This is the most likely error based on the user's log.
        logger.critical(f"FATAL ERROR in send_file: Peer ID '{client.owner_db_channel}' is invalid. The bot has likely been removed from the OWNER_DB_CHANNEL or the ID is incorrect. Error: {e}")
        try:
            # Notify the requester of a temporary issue.
            await client.send_message(requester_id, "Sorry, the bot is facing a configuration issue and cannot retrieve files right now. The admin has been notified.")
            # Notify the admin with a clear, actionable message.
            await client.send_message(Config.ADMIN_ID, f"🚨 **CRITICAL ERROR** 🚨\n\nI could not send a file because my `OWNER_DB_CHANNEL` (`{client.owner_db_channel}`) is inaccessible.\n\n**Error:** `Peer id invalid`\n\n**ACTION REQUIRED:** Please ensure the Channel ID is correct and that I am an **admin** in that channel.")
        except UserIsBlocked:
            pass # Ignore if the user has blocked the bot.
    except Exception as e:
        logger.exception("Error in send_file function")
        try:
            await client.send_message(requester_id, "Something went wrong while sending the file.")
        except UserIsBlocked:
            pass


@Client.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    if message.from_user.is_bot: return
    requester_id = message.from_user.id
    await add_user(requester_id)
    
    if len(message.command) > 1:
        payload = message.command[1]
        try:
            if payload.startswith("finalget_"):
                _, owner_id_str, file_unique_id = payload.split("_", 2)
                owner_id = int(owner_id_str)
                
                file_data = await get_file_by_unique_id(owner_id, file_unique_id)
                if file_data:
                    owner_settings = await get_user(owner_id)
                    
                    if owner_settings and owner_settings.get('shortener_mode') == '12_hour':
                        was_already_verified = await is_user_verified(requester_id, owner_id)
                        # claim_verification_for_file now handles the view recording
                        claim_successful = await claim_verification_for_file(owner_id, file_unique_id, requester_id)
                        
                        if claim_successful and not was_already_verified:
                            await client.send_message(requester_id, "✅ **Verification Successful!**\n\nYou can now get direct links from this user's channels for the next 12 hours.")
                    else:
                        # For 'each_time' mode, we record the view here
                        await record_daily_view(owner_id, requester_id)

                await send_file(client, requester_id, owner_id, file_unique_id)

            elif payload.startswith("ownerget_"):
                _, owner_id_str, file_unique_id = payload.split("_", 2)
                owner_id = int(owner_id_str)
                if requester_id == owner_id:
                    await send_file(client, requester_id, owner_id, file_unique_id)
                else:
                    await message.reply_text("This is a special link for the file owner only.")

            elif payload.startswith("get_"):
                await handle_public_file_request(client, message, requester_id, payload)

        except UserIsBlocked:
             logger.warning(f"User {requester_id} blocked the bot during /start command processing.")
        except Exception as e:
            logger.exception("Error processing deep link in /start")
            try:
                await message.reply_text("Something went wrong or the link is invalid.")
            except UserIsBlocked:
                pass
    else:
        text = (
            f"Hello {message.from_user.mention}! 👋\n\n"
            "Welcome to your advanced **File Management Assistant**.\n\n"
            "I can help you store, manage, and share your files effortlessly. "
            "Whether you're looking for a quick streaming link or want to automate your channel posts, I have the tools for you.\n\n"
            "**Here's what I can do:**\n"
            "🗂️ **File Storage & Management**\n"
            "› Save unlimited files in your private channels.\n"
            "› Get fast direct download & streaming links.\n\n"
            "📢 **Powerful Auto-Posting**\n"
            "› Auto-post from storage channels to public channels.\n"
            "› Full customization of captions, posters, and buttons.\n\n"
            "Click **Let's Go 🚀** to open your settings menu and begin!"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Let's Go 🚀", callback_data=f"go_back_{requester_id}")],
            [InlineKeyboardButton("Tutorial 🎬", url=Config.TUTORIAL_URL)]
        ])
        
        await message.reply_text(text, reply_markup=keyboard)


async def handle_public_file_request(client, message, requester_id, payload):
    try:
        _, owner_id_str, file_unique_id = payload.split("_", 2)
        owner_id = int(owner_id_str)
    except (ValueError, IndexError):
        return await message.reply_text("The link is invalid or corrupted.")

    file_data = await get_file_by_unique_id(owner_id, file_unique_id)
    if not file_data: return await message.reply_text("File not found or link has expired.")
    
    owner_settings = await get_user(owner_id)
    
    fsub_channel = owner_settings.get('fsub_channel')
    if fsub_channel:
        try:
            await client.get_chat_member(chat_id=fsub_channel, user_id="me")
            try:
                await client.get_chat_member(chat_id=fsub_channel, user_id=requester_id)
            except UserNotParticipant:
                try:
                    invite_link = await client.export_chat_invite_link(fsub_channel)
                except Exception:
                    invite_link = None
                
                buttons = []
                # --- DECREED FIX: START ---
                # Only add the "Join Channel" button if the invite link was successfully created.
                # This prevents passing url=None to the button constructor.
                if invite_link:
                    buttons.append(
                        [InlineKeyboardButton("📢 Join Channel", url=invite_link)]
                    )
                # --- DECREED FIX: END ---
                
                buttons.append(
                    [InlineKeyboardButton("🔄 Retry", callback_data=f"retry_{payload}")]
                )
                
                return await message.reply_text(
                    "You must join the channel to continue.",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
        except (ChatAdminRequired, ChannelInvalid, PeerIdInvalid, ChannelPrivate, UserNotParticipant) as e:
            logger.error(f"FSub channel error for owner {owner_id} (Channel: {fsub_channel}): {e}")
            try:
                await client.send_message(
                    chat_id=owner_id,
                    text=(
                        "⚠️ **FSub Channel Error**\n\n"
                        f"A user was unable to access your file because your FSub channel (`{fsub_channel}`) is no longer valid. This can happen if the bot was removed or banned from the channel.\n\n"
                        "Your FSub channel has been **automatically disabled** to prevent further errors.\n\n"
                        "To re-enable it, please go to your bot's settings, choose **FSub**, and set up the channel again."
                    )
                )
                await update_user(owner_id, "fsub_channel", None)
            except Exception as notify_error:
                logger.error(f"Could not notify owner {owner_id} about their invalid FSub channel: {notify_error}")
            pass 
    
    try:
        with open(Config.BOT_USERNAME_FILE, 'r') as f:
            bot_username = f.read().strip().replace("@", "")
    except FileNotFoundError:
        logger.error(f"FATAL: Bot username file not found at {Config.BOT_USERNAME_FILE}. Cannot create fallback link.")
        return await message.reply_text("Bot is not configured correctly. Please contact the admin.")

    if not bot_username:
        logger.error("FATAL: Bot username is empty in the file. Cannot create fallback link.")
        return await message.reply_text("Bot is not configured correctly. Please contact the admin.")
        
    composite_id = f"{owner_id}_{file_unique_id}"
    final_delivery_link = f"https://t.me/{bot_username}?start=finalget_{composite_id}"
    
    shortener_enabled = owner_settings.get('shortener_enabled', True)
    shortener_mode = owner_settings.get('shortener_mode', 'each_time')
    text = ""
    buttons = []

    if not shortener_enabled:
        text = "✅ **Your link is ready!**\n\nClick the button below to get your file directly."
        buttons.append([InlineKeyboardButton("➡️ Get Your File ⬅️", url=final_delivery_link)])
        # --- STATS: Record view if shortener is disabled ---
        await record_daily_view(owner_id, requester_id)
    else:
        shortened_link = await get_shortlink(final_delivery_link, owner_id)
        
        if shortened_link == final_delivery_link and shortener_enabled:
            last_notified = client.shortener_fail_cache.get(requester_id, 0)
            if (time.time() - last_notified) > 3600:
                await message.reply_text(
                    "⚠️ **Shortener Unavailable!**\n\n"
                    "The owner's link shortener is currently unavailable. "
                    "A direct link has been provided instead. Please check your shortener settings if this persists.",
                    reply_to_message_id=message.id
                )
                client.shortener_fail_cache[requester_id] = time.time()
            # --- STATS: Record view if shortener fails ---
            await record_daily_view(owner_id, requester_id)
            
        if shortener_mode == 'each_time':
            text = "**Your file is almost ready!**\n\n1. Click the button below.\n2. You will be redirected back, and I will send you the file."
            buttons.append([InlineKeyboardButton("➡️ Click Here to Get Your File ⬅️", url=shortened_link)])
        elif shortener_mode == '12_hour':
            if await is_user_verified(requester_id, owner_id):
                text = "✅ **You are verified!**\n\nYour 12-hour verification is active. Click below to get your file directly."
                buttons.append([InlineKeyboardButton("➡️ Get Your File Directly ⬅️", url=final_delivery_link)])
                # --- STATS: Record view for already verified user ---
                await record_daily_view(owner_id, requester_id)
            else:
                text = "**One-Time Verification Required**\n\nTo get direct access for 12 hours, please complete this one-time verification step."
                buttons.append([InlineKeyboardButton("➡️ Click to Verify (12 Hours) ⬅️", url=shortened_link)])

    if owner_settings.get("how_to_download_link"):
        buttons.append([InlineKeyboardButton("❓ How to Download", url=owner_settings["how_to_download_link"])])
    
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


@Client.on_callback_query(filters.regex(r"^retry_"))
async def retry_handler(client, query):
    try:
        await query.message.delete()
    except (MessageDeleteForbidden, MessageNotModified):
        await query.answer("Retrying...", show_alert=False)
    except Exception as e:
        logger.warning(f"Could not edit message in retry_handler: {e}")
    
    try:
        await handle_public_file_request(client, query.message, query.from_user.id, query.data.split("_", 1)[1])
    except UserIsBlocked:
        logger.warning(f"User {query.from_user.id} blocked the bot during retry.")
        await query.answer("Could not retry because you have blocked the bot.", show_alert=True)


@Client.on_callback_query(filters.regex(r"go_back_"))
async def go_back_callback(client, query):
    user_id = int(query.data.split("_")[-1])
    if query.from_user.id != user_id:
        return await query.answer("This is not for you!", show_alert=True)
    try:
        menu_text, menu_markup = await get_main_menu(user_id)
        await query.message.edit_text(text=menu_text, reply_markup=menu_markup, parse_mode=enums.ParseMode.MARKDOWN, disable_web_page_preview=True)
    except MessageNotModified:
        await query.answer()
    except Exception as e:
        logger.error(f"Error in go_back_callback: {e}")
        await query.answer("An error occurred while loading the menu.", show_alert=True)
