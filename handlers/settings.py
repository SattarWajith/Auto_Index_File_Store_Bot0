# widhvans/store/widhvans-store-a32dae6d5f5487c7bc78b13e2cdc18082aef6c58/handlers/settings.py

import asyncio
import base64
import logging
import aiohttp
import re
from pyrogram import Client, filters, enums
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified, UserNotParticipant, ChannelPrivate, ButtonDataInvalid
from database.db import (
    get_user, update_user, add_to_list, remove_from_list,
    get_user_file_count, add_footer_button, remove_footer_button, remove_all_footer_buttons,
    get_all_user_files, get_paginated_files, search_user_files,
    add_user, set_post_channel, set_index_db_channel, get_index_db_channel,
    get_posts_for_backup, delete_posts_from_channel
)
from utils.helpers import go_back_button, get_main_menu, create_post, clean_and_parse_filename, calculate_title_similarity, notify_and_remove_invalid_channel
from features.shortener import validate_shortener
from config import Config

logger = logging.getLogger(__name__)
ACTIVE_BACKUP_TASKS = set()


async def safe_edit_message(source, *args, **kwargs):
    try:
        if isinstance(source, CallbackQuery):
            message_to_edit = source.message
        elif isinstance(source, Message):
            message_to_edit = source
        else:
            logger.error(f"safe_edit_message called with invalid type: {type(source)}")
            return
        if 'parse_mode' not in kwargs:
            kwargs['parse_mode'] = ParseMode.MARKDOWN
        await message_to_edit.edit_text(*args, **kwargs)
    except MessageNotModified:
        try:
            if isinstance(source, CallbackQuery):
                await source.answer()
        except Exception:
            pass
    except ButtonDataInvalid:
        logger.exception("ButtonDataInvalid error while editing message")
        try:
            if isinstance(source, CallbackQuery):
                user_id = source.from_user.id
                await remove_all_footer_buttons(user_id)
                await source.answer(
                    "Your footer buttons were invalid and have been reset. Please add them again.",
                    show_alert=True
                )
                menu_text, menu_markup = await get_main_menu(user_id)
                await source.message.edit_text(text=menu_text, reply_markup=menu_markup)
                return
        except Exception as e:
            logger.error(f"Error during ButtonDataInvalid handling: {e}")
    except Exception as e:
        logger.exception("Error while editing message")
        try:
            if isinstance(source, CallbackQuery):
                await source.answer("An error occurred. Please try again.", show_alert=True)
        except Exception:
            pass
            
# --- NEW: Daily Stats Menu Handlers ---
async def get_daily_stats_menu_parts(user_id):
    user = await get_user(user_id)
    if not user: await add_user(user_id); user = await get_user(user_id)
    
    is_enabled = user.get('daily_notify_enabled', False)
    status_text = 'ON 🟢' if is_enabled else 'OFF 🔴'
    
    text = (
        "**📊 Daily Stats Dashboard**\n\n"
        "Enable this feature to receive a daily report of your file clicks right here at 11:59 PM.\n\n"
        f"**Current Status:** `{status_text}`"
    )
    
    buttons = [
        [InlineKeyboardButton(f"Turn Notifications {'OFF' if is_enabled else 'ON'}", callback_data="toggle_daily_notify")],
        [go_back_button(user_id).inline_keyboard[0][0]]
    ]
    return text, InlineKeyboardMarkup(buttons)

@Client.on_callback_query(filters.regex("^daily_stats_menu$"))
async def daily_stats_menu_handler(client, query):
    user_id = query.from_user.id
    text, markup = await get_daily_stats_menu_parts(user_id)
    await safe_edit_message(query, text=text, reply_markup=markup)

@Client.on_callback_query(filters.regex("^toggle_daily_notify$"))
async def toggle_daily_notify_handler(client, query):
    user_id = query.from_user.id
    user = await get_user(user_id)
    if not user: await add_user(user_id); user = await get_user(user_id)

    new_status = not user.get('daily_notify_enabled', False)
    await update_user(user_id, 'daily_notify_enabled', new_status)
    await query.answer(f"Daily Notifications are now {'ON' if new_status else 'OFF'}", show_alert=True)
    text, markup = await get_daily_stats_menu_parts(user_id)
    await safe_edit_message(query, text=text, reply_markup=markup)

# --- END: Daily Stats Handlers ---


async def get_shortener_menu_parts(user_id):
    user = await get_user(user_id)
    if not user: await add_user(user_id); user = await get_user(user_id)
    
    is_enabled = user.get('shortener_enabled', True)
    shortener_url = user.get('shortener_url')
    shortener_api = user.get('shortener_api')
    shortener_mode = user.get('shortener_mode', 'each_time')
    
    text = "**🔗 Shortener Settings**\n\nHere are your current settings:"
    if shortener_url and shortener_api:
        text += f"\n**Domain:** `{shortener_url}`"
        text += f"\n**API Key:** `{shortener_api}`"
    else:
        text += "\n`No shortener domain or API is set.`"
        
    status_text = 'ON 🟢' if is_enabled else 'OFF 🔴'
    mode_text = "Each Time" if shortener_mode == 'each_time' else "12 Hour Verify"
    text += f"\n\n**Status:** {status_text}"
    text += f"\n**Verification Mode:** {mode_text}"
    
    buttons = [
        [InlineKeyboardButton(f"Turn Shortener {'OFF' if is_enabled else 'ON'}", callback_data="toggle_shortener")]
    ]
    if shortener_mode == 'each_time':
        buttons.append([InlineKeyboardButton("🔄 Switch to 12 Hour Verify", callback_data="toggle_smode")])
    else:
        buttons.append([InlineKeyboardButton("🔄 Switch to Each Time", callback_data="toggle_smode")])
    
    buttons.append([InlineKeyboardButton("✏️ Set/Edit API & Domain", callback_data="set_shortener")])
    
    if shortener_url or shortener_api:
        buttons.append([InlineKeyboardButton("🗑️ Reset API & Domain", callback_data="reset_shortener")])
        
    buttons.append([go_back_button(user_id).inline_keyboard[0][0]])
    return text, InlineKeyboardMarkup(buttons)

@Client.on_callback_query(filters.regex("^reset_shortener$"))
async def reset_shortener_handler(client, query):
    user_id = query.from_user.id
    await update_user(user_id, "shortener_url", None)
    await update_user(user_id, "shortener_api", None)
    await query.answer("✅ Shortener settings have been reset.", show_alert=True)
    text, markup = await get_shortener_menu_parts(user_id)
    await safe_edit_message(query, text=text, reply_markup=markup)

async def get_poster_menu_parts(user_id):
    user = await get_user(user_id)
    if not user: await add_user(user_id); user = await get_user(user_id)
    
    is_enabled = user.get('show_poster', True)
    text = f"**🖼️ Poster Settings**\n\nIMDb Poster is currently **{'ON' if is_enabled else 'OFF'}**."
    return text, InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Turn Poster {'OFF 🔴' if is_enabled else 'ON 🟢'}", callback_data="toggle_poster")],
        [go_back_button(user_id).inline_keyboard[0][0]]
    ])

async def get_fsub_menu_parts(client, user_id):
    user = await get_user(user_id)
    if not user: await add_user(user_id); user = await get_user(user_id)
    
    fsub_ch = user.get('fsub_channel')
    text = "**📢 FSub Settings**\n\n"
    if fsub_ch:
        is_valid = await notify_and_remove_invalid_channel(client, user_id, fsub_ch, "FSub")
        if is_valid:
            try:
                chat = await client.get_chat(fsub_ch)
                text += f"Current FSub Channel: **{chat.title}** (`{fsub_ch}`)"
            except:
                text += f"Current FSub Channel ID: `{fsub_ch}`"
    else:
        text += "No FSub channel is set."
    buttons = [
        [InlineKeyboardButton("✏️ Set/Change FSub", callback_data="set_fsub")],
    ]
    if fsub_ch:
        buttons.append([InlineKeyboardButton("🗑️ Remove FSub", callback_data="remove_fsub")])
    buttons.append([go_back_button(user_id).inline_keyboard[0][0]])
    return text, InlineKeyboardMarkup(buttons)


@Client.on_callback_query(filters.regex("^how_to_download_menu$"))
async def how_to_download_menu_handler(client, query):
    user_id = query.from_user.id
    user = await get_user(user_id)
    if not user: await add_user(user_id); user = await get_user(user_id)

    download_link = user.get("how_to_download_link")

    text = "**❓ How to Download Link Settings**\n\n"
    if download_link:
        text += f"Your current 'How to Download' tutorial link is:\n`{download_link}`"
    else:
        text += "You have not set a 'How to Download' link yet."

    buttons = [
        [InlineKeyboardButton("✏️ Set/Change Link", callback_data="set_download")],
        [go_back_button(user_id).inline_keyboard[0][0]]
    ]
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


# --- Main Callback Handlers ---

@Client.on_callback_query(filters.regex("^manage_channels_menu$"))
async def manage_channels_submenu_handler(client, query):
    text = "🗂️ **Manage Channels**\n\nSelect which type of channel you want to manage."
    buttons = [
        [InlineKeyboardButton("➕ Manage Auto Post", callback_data="manage_post_ch")],
        [InlineKeyboardButton("🗃️ Manage Index DB", callback_data="manage_db_ch")],
        [go_back_button(query.from_user.id).inline_keyboard[0][0]]
    ]
    markup = InlineKeyboardMarkup(buttons)
    await safe_edit_message(query, text=text, reply_markup=markup)

@Client.on_callback_query(filters.regex("^filename_link_menu$"))
async def filename_link_menu_handler(client, query):
    user = await get_user(query.from_user.id)
    if not user: await add_user(query.from_user.id); user = await get_user(query.from_user.id)
    
    filename_url = user.get("filename_url")
    
    text = "**✍️ Filename Link Settings**\n\nThis URL will be used as a hyperlink for the filename when a user receives a file."
    if filename_url:
        text += f"\n\n**Current Link:**\n`{filename_url}`"
    else:
        text += "\n\n`You have not set a filename link yet.`"
    
    buttons = [
        [InlineKeyboardButton("✏️ Set/Change Link", callback_data="set_filename_link")],
        [go_back_button(query.from_user.id).inline_keyboard[0][0]]
    ]
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


@Client.on_callback_query(filters.regex(r"^(shortener|poster|fsub)_menu$"))
async def settings_submenu_handler(client, query):
    user_id = query.from_user.id
    menu_type = query.data.split("_")[0]
    if menu_type == "shortener": text, markup = await get_shortener_menu_parts(user_id)
    elif menu_type == "poster": text, markup = await get_poster_menu_parts(user_id)
    elif menu_type == "fsub": text, markup = await get_fsub_menu_parts(client, user_id)
    else: return
    await safe_edit_message(query, text=text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"toggle_shortener$"))
async def toggle_shortener_handler(client, query):
    user_id = query.from_user.id
    user = await get_user(user_id)
    if not user: await add_user(user_id); user = await get_user(user_id)
    
    new_status = not user.get('shortener_enabled', True)
    await update_user(user_id, 'shortener_enabled', new_status)
    await query.answer(f"Shortener is now {'ON' if new_status else 'OFF'}", show_alert=True)
    text, markup = await get_shortener_menu_parts(user_id)
    await safe_edit_message(query, text=text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"toggle_smode$"))
async def toggle_shortener_mode_handler(client, query):
    user_id = query.from_user.id
    user = await get_user(user_id)
    if not user: await add_user(user_id); user = await get_user(user_id)
    
    current_mode = user.get('shortener_mode', 'each_time')
    if current_mode == 'each_time':
        new_mode = '12_hour'
        mode_text = "12 Hour Verify"
    else:
        new_mode = 'each_time'
        mode_text = "Each Time"
    await update_user(user_id, 'shortener_mode', new_mode)
    await query.answer(f"Shortener mode set to: {mode_text}", show_alert=True)
    text, markup = await get_shortener_menu_parts(user_id)
    await safe_edit_message(query, text=text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"toggle_poster$"))
async def toggle_poster_handler(client, query):
    user_id = query.from_user.id
    user = await get_user(user_id)
    if not user: await add_user(user_id); user = await get_user(user_id)
    
    new_status = not user.get('show_poster', True)
    await update_user(user_id, 'show_poster', new_status)
    await query.answer(f"Poster is now {'ON' if new_status else 'OFF'}", show_alert=True)
    text, markup = await get_poster_menu_parts(user_id)
    await safe_edit_message(query, text=text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"my_files_(\d+)"))
async def my_files_handler(client, query):
    try:
        user_id = query.from_user.id
        page = int(query.data.split("_")[-1])
        total_files = await get_user_file_count(user_id)
        files_per_page = 5
        text = f"**📂 Your Saved Files ({total_files} Total)**\n\n"
        if total_files == 0:
            text += "You have not saved any files yet."
        else:
            files_on_page = await get_paginated_files(user_id, page, files_per_page)
            if not files_on_page: text += "No more files found on this page."
            else:
                for file in files_on_page:
                    composite_id = f"{file['owner_id']}_{file['file_unique_id']}"
                    deep_link = f"https://t.me/{client.me.username}?start=ownerget_{composite_id}"
                    text += f"**File:** `{file['file_name']}`\n**Link:** [Click Here to Get File]({deep_link})\n\n"
        buttons, nav_row = [], []
        if page > 1: nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"my_files_{page-1}"))
        if total_files > page * files_per_page: nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"my_files_{page+1}"))
        if nav_row: buttons.append(nav_row)
        buttons.append([InlineKeyboardButton("🔍 Search My Files", callback_data="search_my_files")])
        buttons.append([InlineKeyboardButton("« Go Back", callback_data=f"go_back_{user_id}")])
        await safe_edit_message(query, text=text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
    except Exception:
        logger.exception("Error in my_files_handler"); await query.answer("Something went wrong.", show_alert=True)

async def _format_and_send_search_results(client, source, user_id, search_query, page):
    files_per_page = 5
    files_list, total_files = await search_user_files(user_id, search_query, page, files_per_page)
    text = f"**🔎 Search Results for `{search_query}` ({total_files} Found)**\n\n"
    if not files_list: text += "No files found for your query."
    else:
        for file in files_list:
            composite_id = f"{file['owner_id']}_{file['file_unique_id']}"
            deep_link = f"https://t.me/{client.me.username}?start=ownerget_{composite_id}"
            text += f"**File:** `{file['file_name']}`\n**Link:** [Click Here to Get File]({deep_link})\n\n"
    buttons, nav_row = [], []

    if page > 1: nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"search_results_{page-1}"))
    if total_files > page * files_per_page: nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"search_results_{page+1}"))
    
    if nav_row: buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("📚 Back to Full List", callback_data="my_files_1")])
    buttons.append([InlineKeyboardButton("« Go Back to Settings", callback_data=f"go_back_{user_id}")])
    await safe_edit_message(source, text=text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

@Client.on_callback_query(filters.regex("search_my_files"))
async def search_my_files_prompt(client, query):
    user_id = query.from_user.id
    try:
        prompt = await query.message.edit_text("**🔍 Search Your Files**\n\nPlease send the name of the file you want to find.", reply_markup=go_back_button(user_id))
        response = await client.listen(chat_id=user_id, timeout=300, filters=filters.text)
        
        if not hasattr(client, 'search_cache'):
            client.search_cache = {}
        client.search_cache[user_id] = response.text
        
        await response.delete()
        await _format_and_send_search_results(client, query, user_id, response.text, 1)
    except asyncio.TimeoutError: await safe_edit_message(query, text="❗️ **Timeout:** Search cancelled.", reply_markup=go_back_button(user_id))
    except Exception as e:
        logger.exception("Error in search_my_files_prompt"); await safe_edit_message(query, text=f"An error occurred: {e}", reply_markup=go_back_button(user_id))

@Client.on_callback_query(filters.regex(r"search_results_(\d+)"))
async def search_results_paginator(client, query):
    try:
        page = int(query.matches[0].group(1))
        user_id = query.from_user.id
        
        if not hasattr(client, 'search_cache') or user_id not in client.search_cache:
            return await query.answer("Your search session has expired. Please start a new search.", show_alert=True)
        search_query = client.search_cache[user_id]
        
        await _format_and_send_search_results(client, query, user_id, search_query, page)
    except Exception:
        logger.exception("Error during search pagination"); await safe_edit_message(query, text="An error occurred during pagination.")

# --- New Backup Logic Handlers ---

@Client.on_callback_query(filters.regex("backup_links"))
async def backup_links_handler(client, query):
    user_id = query.from_user.id
    user = await get_user(user_id)
    if not user: await add_user(user_id); user = await get_user(user_id)
    
    post_channels = user.get('post_channels', [])
    if not post_channels: return await query.answer("You have no Auto Post channels set up to back up from.", show_alert=True)
    
    kb = []
    for ch_id in post_channels:
        try:
            chat = await client.get_chat(ch_id)
            kb.append([InlineKeyboardButton(chat.title, callback_data=f"backup_source_{ch_id}")])
        except Exception:
            continue
            
    if not kb: return await query.answer("Could not access any of your Post Channels. Please check my admin rights there.", show_alert=True)
    
    kb.append([go_back_button(user_id).inline_keyboard[0][0]])
    await safe_edit_message(query, text="**🔄 Smart Backup: Step 1/2**\n\nSelect the **source channel** you want to back up.", reply_markup=InlineKeyboardMarkup(kb))

@Client.on_callback_query(filters.regex(r"backup_source_-?\d+"))
async def select_backup_destination(client, query):
    user_id = query.from_user.id
    source_channel_id = int(query.data.split("_")[-1])
    
    client.backup_cache[user_id] = {'source_id': source_channel_id}
    
    await safe_edit_message(query, 
        text="**🔄 Smart Backup: Step 2/2**\n\nNow, forward a message from the **destination channel** where you want to send the backup.\n\nI must be an admin in the destination channel.",
        reply_markup=go_back_button(user_id)
    )
    
    try:
        response = await client.listen(chat_id=user_id, filters=filters.forwarded, timeout=300)
        
        if response and response.forward_from_chat:
            destination_channel_id = response.forward_from_chat.id
            await response.delete()
            await start_backup_process(client, query, user_id, source_channel_id, destination_channel_id)
        else:
            await safe_edit_message(query, text="Invalid forward. Backup cancelled.", reply_markup=go_back_button(user_id))

    except asyncio.TimeoutError:
        await safe_edit_message(query, text="❗️ **Timeout:** Backup cancelled.", reply_markup=go_back_button(user_id))
    except Exception as e:
        logger.exception("Error in select_backup_destination")
        await safe_edit_message(query, text=f"An error occurred: {e}", reply_markup=go_back_button(user_id))

async def start_backup_process(client, source_query, user_id, source_channel_id, destination_channel_id):
    if user_id in ACTIVE_BACKUP_TASKS:
        return await source_query.answer("A backup process is already running for you.", show_alert=True)
    
    ACTIVE_BACKUP_TASKS.add(user_id)
    status_msg = source_query.message
    
    try:
        await status_msg.edit_text("✅ Channels selected. Fetching posts from the database...")
        posts_to_backup = await get_posts_for_backup(user_id, source_channel_id)
        
        if not posts_to_backup:
            await status_msg.edit_text("No backed-up posts found for this channel.", reply_markup=go_back_button(user_id))
            return
            
        total_posts = len(posts_to_backup)
        cancel_button = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Backup", callback_data=f"cancel_backup_{user_id}")]])
        await status_msg.edit_text(f"Found {total_posts} posts. Starting backup...", reply_markup=cancel_button)

        for i, post_data in enumerate(posts_to_backup):
            if user_id not in ACTIVE_BACKUP_TASKS:
                await status_msg.edit_text("❌ Backup cancelled by user.", reply_markup=go_back_button(user_id))
                return

            try:
                caption = post_data.get('caption', '')
                poster = post_data.get('poster')
                reply_markup_dict = post_data.get('reply_markup')
                
                footer = None
                if reply_markup_dict and "inline_keyboard" in reply_markup_dict:
                    reconstructed_keyboard = [
                        [InlineKeyboardButton(**button_data) for button_data in row]
                        for row in reply_markup_dict["inline_keyboard"]
                    ]
                    footer = InlineKeyboardMarkup(reconstructed_keyboard)

                # --- DECREED FIX: START ---
                # The old URL rewriting logic was flawed. This new, robust implementation
                # correctly finds old links and replaces them with links valid for the new
                # user and current bot configuration.
                if caption:
                    # This pattern finds the full old URL and captures only the file's unique ID.
                    # It's robust against changes in domain, IP, or port.
                    pattern = r"https?://.*?/get/\d+_([^)]+)"

                    def replacer(match):
                        file_unique_id = match.group(1)
                        # Reconstruct the URL with the NEW user ID and CURRENT bot config
                        return f"http://{Config.VPS_IP}:{Config.VPS_PORT}/get/{user_id}_{file_unique_id}"

                    caption = re.sub(pattern, replacer, caption)
                # --- DECREED FIX: END ---
                
                if poster:
                    await client.send_photo(destination_channel_id, photo=poster, caption=caption, reply_markup=footer)
                else:
                    await client.send_message(destination_channel_id, caption, reply_markup=footer, disable_web_page_preview=True)
                
                if (i + 1) % 10 == 0: # Update status every 10 posts
                    await status_msg.edit_text(f"🔄 Backing up... Progress: {i + 1} / {total_posts} posts sent.", reply_markup=cancel_button)
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Failed to post one backup item for user {user_id}. Error: {e}", exc_info=True)
                await client.send_message(user_id, f"Skipped one post during backup due to an error: `{e}`")
                await asyncio.sleep(2)

        await status_msg.delete()
        await client.send_message(user_id, f"✅ **Backup Complete!**\n\nSuccessfully backed up {total_posts} posts.", reply_markup=go_back_button(user_id))
        
    except Exception as e:
        logger.exception("Major error in new backup process")
        await status_msg.edit_text(f"A major error occurred: {e}", reply_markup=go_back_button(user_id))
    finally:
        ACTIVE_BACKUP_TASKS.discard(user_id)
        if hasattr(client, 'backup_cache') and user_id in client.backup_cache:
            del client.backup_cache[user_id]

@Client.on_callback_query(filters.regex(r"cancel_backup_"))
async def cancel_backup_handler(client, query):
    user_id = int(query.data.split("_")[-1])
    if query.from_user.id != user_id: return await query.answer("This is not for you.", show_alert=True)
    if user_id in ACTIVE_BACKUP_TASKS:
        ACTIVE_BACKUP_TASKS.discard(user_id); await query.answer("Cancellation signal sent.", show_alert=True)
    else: await query.answer("No active backup process found.", show_alert=True)

@Client.on_callback_query(filters.regex("manage_footer"))
async def manage_footer_handler(client, query):
    user = await get_user(query.from_user.id)
    if not user: await add_user(query.from_user.id); user = await get_user(query.from_user.id)

    buttons = user.get('footer_buttons', [])
    text = "**👣 Manage Footer Buttons**\n\nYou can add up to 3 URL buttons to your post footers."
    kb = [[InlineKeyboardButton(f"❌ {btn['name']}", callback_data=f"rm_footer_{btn['name']}")] for btn in buttons]
    if len(buttons) < 3: kb.append([InlineKeyboardButton("➕ Add New Button", callback_data="add_footer")])
    if buttons:
        kb.append([InlineKeyboardButton("🗑️ Reset All Buttons", callback_data="reset_footer")])
    kb.append([InlineKeyboardButton("« Go Back", callback_data=f"go_back_{query.from_user.id}")])
    await safe_edit_message(query, text=text, reply_markup=InlineKeyboardMarkup(kb))

@Client.on_callback_query(filters.regex("reset_footer"))
async def reset_footer_handler(client, query):
    user_id = query.from_user.id
    await remove_all_footer_buttons(user_id)
    await query.answer("✅ All footer buttons have been reset.", show_alert=True)
    await manage_footer_handler(client, query)

@Client.on_callback_query(filters.regex("add_footer"))
async def add_footer_handler(client, query):
    user_id = query.from_user.id
    prompt_msg = None
    try:
        prompt_msg = await query.message.edit_text(
            "**➕ Add Footer Button: Step 1/2**\n\n"
            "Send the **text** for your new button.\n\n"
            "**Example:** `Visit My Channel`",
            reply_markup=go_back_button(user_id)
        )
        button_name_msg = await client.listen(chat_id=user_id, timeout=300)
        button_name = button_name_msg.text.strip()
        await button_name_msg.delete()

        if len(button_name.encode('utf-8')) > 50:
            await prompt_msg.edit_text(
                "❌ **Error!**\n\nButton text is too long. Please keep it under 50 bytes.",
                reply_markup=go_back_button(user_id)
            )
            return

        await prompt_msg.edit_text(
            f"**➕ Add Footer Button: Step 2/2**\n\n"
            f"Button Text: `{button_name}`\n\n"
            "Now, send the **URL** for the button.\n\n"
            "**Example:** `https://t.me/your_channel_name`",
            reply_markup=go_back_button(user_id)
        )
        button_url_msg = await client.listen(chat_id=user_id, timeout=300)
        button_url = button_url_msg.text.strip()
        await button_url_msg.delete()

        if not button_url.startswith(("http://", "https://")):
            button_url = "https://" + button_url

        await prompt_msg.edit_text(f"⏳ **Validating URL...**\n`{button_url}`")
        is_valid = False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(button_url, timeout=5, allow_redirects=True) as resp:
                    if resp.status in range(200, 400):
                        is_valid = True
        except Exception as e:
            logger.error(f"URL validation failed for footer button: {e}")

        if is_valid:
            await add_footer_button(user_id, button_name, button_url)
            await prompt_msg.edit_text("✅ New footer button added!")
            await asyncio.sleep(2)
            await manage_footer_handler(client, query)
        else:
            await prompt_msg.edit_text(
                "❌ **Validation Failed!**\n\nThe URL you provided appears to be invalid or inaccessible. "
                "Your button has **not** been saved.\n\n"
                "Please check the URL and try again.",
                reply_markup=go_back_button(user_id)
            )
    except asyncio.TimeoutError:
        if prompt_msg: await safe_edit_message(prompt_msg, text="❗️ **Timeout:** Cancelled.", reply_markup=go_back_button(user_id))
    except Exception as e:
        logger.exception("Error in add_footer_handler")
        if prompt_msg: await safe_edit_message(prompt_msg, text=f"An error occurred: {e}", reply_markup=go_back_button(user_id))


@Client.on_callback_query(filters.regex(r"rm_footer_"))
async def remove_footer_handler(client, query):
    await remove_footer_button(query.from_user.id, query.data.split("_", 2)[2])
    await query.answer("Button removed!", show_alert=True)
    await manage_footer_handler(client, query)

@Client.on_callback_query(filters.regex(r"manage_(post|db)_ch"))
async def manage_channels_handler(client, query):
    user_id, ch_type = query.from_user.id, query.data.split("_")[1]
    
    ch_type_key = "post_channels" if ch_type == 'post' else "index_db_channel"
    ch_type_name = "Post" if ch_type == 'post' else "Index DB"
    
    user_data = await get_user(user_id)
    if not user_data:
        await add_user(user_id)
        user_data = await get_user(user_id)

    text = f"**Manage Your {ch_type_name} Channels**\n\n"
    buttons = []
    
    channels = user_data.get(ch_type_key, [])
    if not isinstance(channels, list):
        channels = [channels] if channels else []

    if channels:
        await query.answer("Checking channel status...")
        text += "Here are your connected channels. Click to remove.\n\n"
        for ch_id in channels:
            try:
                chat = await client.get_chat(ch_id)
                member = await client.get_chat_member(ch_id, "me")
                if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                    buttons.append([InlineKeyboardButton(f"⚠️ Admin rights needed in {chat.title}", callback_data=f"rm_{ch_type}_{ch_id}")])
                else:
                    buttons.append([InlineKeyboardButton(f"✅ {chat.title}", callback_data=f"rm_{ch_type}_{ch_id}")])
            except Exception as e:
                logger.warning(f"Could not access channel {ch_id} for user {user_id}. Error: {e}")
                buttons.append([InlineKeyboardButton(f"👻 Ghost Channel - Click to Remove", callback_data=f"rm_{ch_type}_{ch_id}")])
    else:
        text += "You haven't added any channels yet."
        
    buttons.append([InlineKeyboardButton("➕ Add New Channel", callback_data=f"add_{ch_type}_ch")])
    buttons.append([InlineKeyboardButton("« Go Back", callback_data="manage_channels_menu")])
    await safe_edit_message(query, text=text, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex(r"rm_(post|db)_-?\d+"))
async def remove_channel_handler(client, query):
    _, ch_type, ch_id_str = query.data.split("_")
    user_id = query.from_user.id
    ch_id = int(ch_id_str)
    
    if ch_type == 'post':
        await remove_from_list(user_id, "post_channels", ch_id)
        deleted_count = await delete_posts_from_channel(user_id, ch_id)
        logger.info(f"Deleted {deleted_count} backed up posts for user {user_id} from channel {ch_id}.")
    else:
        await update_user(user_id, "index_db_channel", None)
        
    await query.answer("Channel removed!", show_alert=True)
    query.data = f"manage_{ch_type}_ch"
    await manage_channels_handler(client, query)

@Client.on_callback_query(filters.regex(r"add_(post|db)_ch"))
async def add_channel_prompt(client, query):
    user_id, ch_type_short = query.from_user.id, query.data.split("_")[1]
    ch_type_name = "Post" if ch_type_short == "post" else "Index DB"
    
    try:
        prompt = await query.message.edit_text(f"Forward a message from your target **{ch_type_name} Channel**.\n\nI must be an admin there.", reply_markup=go_back_button(user_id))
        response = await client.listen(chat_id=user_id, filters=filters.forwarded, timeout=300)
        
        if response.forward_from_chat:
            channel_id = response.forward_from_chat.id
            if ch_type_short == 'post':
                await set_post_channel(user_id, channel_id)
            else:
                await set_index_db_channel(user_id, channel_id)

            await response.reply_text(f"✅ Connected to **{response.forward_from_chat.title}**.", reply_markup=go_back_button(user_id))
        else: 
            await response.reply_text("This is not a valid forwarded message from a channel.", reply_markup=go_back_button(user_id))
            
        await prompt.delete()
        if response: await response.delete()
        
    except asyncio.TimeoutError:
        if 'prompt' in locals() and prompt: await safe_edit_message(prompt, text="Command timed out.")
    except Exception as e:
        logger.exception("Error in add_channel_prompt")
        await query.message.reply_text(f"An error occurred: {e}", reply_markup=go_back_button(user_id))

@Client.on_callback_query(filters.regex("^set_filename_link$"))
async def set_filename_link_handler(client, query):
    user_id = query.from_user.id
    try:
        prompt = await query.message.edit_text("Please send the full URL you want your filenames to link to.", reply_markup=go_back_button(user_id))
        response = await client.listen(chat_id=user_id, timeout=300, filters=filters.text)
        
        url_text = response.text.strip()
        if not url_text.startswith(("http://", "https://")):
            url_text = "https://" + url_text
            
        await update_user(user_id, "filename_url", url_text)
        await response.reply_text("✅ Filename link updated!", reply_markup=go_back_button(user_id))
        await prompt.delete()
    except asyncio.TimeoutError: await safe_edit_message(query, text="❗️ **Timeout:** Cancelled.", reply_markup=go_back_button(user_id))
    except:
        logger.exception("Error in set_filename_link_handler"); await safe_edit_message(query, text="An error occurred.", reply_markup=go_back_button(user_id))

@Client.on_callback_query(filters.regex("^(set_fsub|set_download|remove_fsub)$"))
async def fsub_and_download_handler(client, query):
    user_id = query.from_user.id
    action = query.data.split("_")[1]

    if action == "fsub" and query.data == "remove_fsub":
        await update_user(user_id, "fsub_channel", None)
        await query.answer("FSub channel has been removed.", show_alert=True)
        text, markup = await get_fsub_menu_parts(client, user_id)
        await safe_edit_message(query, text, reply_markup=markup)
        return

    prompts = {
        "fsub": ("📢 **Set FSub**\n\nForward a message from your FSub channel. I must be an admin there to work correctly.", "fsub_channel"),
        "download": ("❓ **Set 'How to Download'**\n\nSend your tutorial URL.", "how_to_download_link")
    }
    prompt_text, key = prompts[action]
    
    prompt = None
    response = None
    try:
        initial_text = prompt_text
        if action == "download":
            user = await get_user(user_id)
            if user and user.get(key):
                initial_text += f"\n\n**Current Link:** `{user.get(key)}`"
        prompt = await query.message.edit_text(initial_text, reply_markup=go_back_button(user_id), disable_web_page_preview=True)
        
        listen_filters = filters.forwarded if action == "fsub" else filters.text
        response = await client.listen(chat_id=user_id, timeout=300, filters=listen_filters)
        
        if action == "fsub":
            if not response.forward_from_chat:
                await safe_edit_message(prompt, "This is not a valid forwarded message from a channel.", reply_markup=go_back_button(user_id))
                return
            
            channel_id = response.forward_from_chat.id
            await safe_edit_message(prompt, "⏳ Checking permissions in the channel...")
            
            try:
                member = await client.get_chat_member(channel_id, "me")
                if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                    raise UserNotParticipant
            except (UserNotParticipant, ChannelPrivate) as e:
                logger.error(f"FSub permission check failed for user {user_id}, channel {channel_id}: {e}")
                await safe_edit_message(prompt, 
                    "❌ **Permission Denied!**\n\nThe channel is private or I'm not an admin there. "
                    "Please make sure I am a member of the channel and have been promoted to an admin, then try again.",
                    reply_markup=go_back_button(user_id)
                )
                return

            await update_user(user_id, key, channel_id)
            await safe_edit_message(prompt, f"✅ **Success!** FSub channel updated to **{response.forward_from_chat.title}**.")
            await asyncio.sleep(2)
            text, markup = await get_fsub_menu_parts(client, user_id)
            await safe_edit_message(prompt, text, reply_markup=markup)
        
        else:
            url_to_check = response.text.strip()
            if not url_to_check.startswith(("http://", "https://")): url_to_check = "https://" + url_to_check
            await safe_edit_message(prompt, f"⏳ **Validating URL...**\n`{url_to_check}`")
            
            is_valid = False
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.head(url_to_check, timeout=5, allow_redirects=True) as resp:
                        if resp.status in range(200, 400): is_valid = True
            except Exception as e: logger.error(f"URL validation failed for {url_to_check}: {e}")

            if is_valid:
                await update_user(user_id, key, url_to_check)
                await safe_edit_message(prompt, "✅ **Success!** Your 'How to Download' link has been saved.")
                await asyncio.sleep(2)
                await how_to_download_menu_handler(client, query)
            else:
                await safe_edit_message(prompt, "❌ **Validation Failed!**\n\nThe URL you provided is invalid or inaccessible. Your settings have not been saved.", reply_markup=go_back_button(user_id))

    except asyncio.TimeoutError:
        if prompt: await safe_edit_message(prompt, text="❗️ **Timeout:** Cancelled.", reply_markup=go_back_button(user_id))
    except Exception as e:
        logger.exception("Error in handler")
        if prompt: await safe_edit_message(prompt, text=f"An error occurred: {e}", reply_markup=go_back_button(user_id))
    finally:
        if response: 
            try: await response.delete()
            except: pass


@Client.on_callback_query(filters.regex("^set_shortener$"))
async def set_shortener_handler(client, query):
    user_id = query.from_user.id
    prompt_msg = None
    try:
        prompt_msg = await query.message.edit_text(
            "**🔗 Step 1/2: Set Domain**\n\n"
            "Please send your shortener website's domain name (e.g., `example.com`).",
            reply_markup=go_back_button(user_id)
        )
        domain_msg = await client.listen(chat_id=user_id, timeout=300)
        if not domain_msg or not domain_msg.text:
            await prompt_msg.edit_text("Operation cancelled: You must send text.", reply_markup=go_back_button(user_id))
            return
        domain = domain_msg.text.strip()
        await domain_msg.delete()

        await prompt_msg.edit_text(
            f"**🔗 Step 2/2: Set API Key**\n\n"
            f"Domain: `{domain}`\n"
            "Now, please send your API key.",
            reply_markup=go_back_button(user_id)
        )
        api_msg = await client.listen(chat_id=user_id, timeout=300)
        if not api_msg or not api_msg.text:
            await prompt_msg.edit_text("Operation cancelled: You must send text.", reply_markup=go_back_button(user_id))
            return
        api_key = api_msg.text.strip()
        await api_msg.delete()
        
        await prompt_msg.edit_text("⏳ **Testing your credentials...**\nPlease wait a moment.")
        is_valid = await validate_shortener(domain, api_key)

        if is_valid:
            await update_user(user_id, "shortener_url", domain)
            await update_user(user_id, "shortener_api", api_key)
            await prompt_msg.edit_text("✅ **Success!**\n\nYour shortener has been verified and saved.")
            await asyncio.sleep(3)
        else:
            await prompt_msg.edit_text(
                "❌ **Validation Failed!**\n\n"
                "The domain or API key you provided appears to be incorrect. "
                "Your settings have **not** been saved.\n\n"
                "Please check your credentials and try again.",
                reply_markup=go_back_button(user_id)
            )
            return

        text, markup = await get_shortener_menu_parts(user_id)
        await safe_edit_message(prompt_msg, text=text, reply_markup=markup)

    except asyncio.TimeoutError:
        if prompt_msg: await safe_edit_message(prompt_msg, text="❗️ **Timeout:** Command cancelled.", reply_markup=go_back_button(user_id))
    except Exception as e:
        logger.exception("Error in set_shortener_handler")
        if prompt_msg: await safe_edit_message(prompt_msg, text=f"An error occurred: {e}", reply_markup=go_back_button(user_id))
