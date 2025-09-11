import asyncio
import re
from time import time as time_now
import math, os
import qrcode, random
from hydrogram.errors import ListenerTimeout
from hydrogram.errors.exceptions.bad_request_400 import MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty, MessageDeleteForbidden
from Script import script
from datetime import datetime, timedelta
from info import (IS_PREMIUM, PICS, TUTORIAL, SHORTLINK_API, SHORTLINK_URL, RECEIPT_SEND_USERNAME, UPI_ID, UPI_NAME, 
                  PRE_DAY_AMOUNT, SECOND_FILES_DATABASE_URL, ADMINS, URL, MAX_BTN, BIN_CHANNEL, IS_STREAM, DELETE_TIME, 
                  FILMS_LINK, LOG_CHANNEL, SUPPORT_GROUP, SUPPORT_LINK, UPDATES_LINK, LANGUAGES, QUALITY, FILE_CAPTION)
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from hydrogram import Client, filters, enums
from utils import (is_premium, get_size, is_subscribed, is_check_admin, get_wish, get_shortlink, get_readable_time, 
                   get_poster, temp, get_settings, save_group_settings)
from database.users_chats_db import db
from database.ia_filterdb import get_search_results, delete_files, db_count_documents, second_db_count_documents
from plugins.commands import get_grp_stg

BUTTONS = {}
CAP = {}

@Client.on_message(filters.private & filters.text & filters.incoming)
async def pm_search(client, message):
    if message.text.startswith("/"):
        return
    stg = db.get_bot_sttgs()
    if not stg.get('PM_SEARCH'):
        return await message.reply_text('PM search has been disabled!')
    if await is_premium(message.from_user.id, client):
        if not stg.get('AUTO_FILTER'):
            return await message.reply_text('Auto filter has been disabled!')
        s = await message.reply(f"<b><i>⚠️ Searching for `{message.text}`...</i></b>", quote=True)
        await auto_filter(client, message, s)
    else:
        files, n_offset, total = await get_search_results(message.text)
        btn = [[
            InlineKeyboardButton("🗂 CLICK HERE FOR ALL FILES 🗂", url=FILMS_LINK)
        ],[
            InlineKeyboardButton('🤑 Buy Premium 🤑', url=f"https://t.me/{temp.U_NAME}?start=premium")
        ]]
        reply_markup = InlineKeyboardMarkup(btn)
        if int(total) != 0:
            await message.reply_text(f'<b><i>🤗 Total `{total}` results found!</i></b>\n\nBuy a premium subscription to access them.', reply_markup=reply_markup)

@Client.on_message(filters.group & filters.text & filters.incoming)
async def group_search(client, message):
    user_id = message.from_user.id if message.from_user else 0
    stg = db.get_bot_sttgs()
    if stg.get('AUTO_FILTER'):
        if not user_id:
            return await message.reply("I don't work for anonymous admins!")
            
        if message.chat.id == SUPPORT_GROUP:
            files, offset, total = await get_search_results(message.text)
            if files:
                btn = [[InlineKeyboardButton("Here", url=FILMS_LINK)]]
                await message.reply_text(f'Total {total} results found in this group.', reply_markup=InlineKeyboardMarkup(btn))
            return
            
        if message.text.startswith("/"):
            return
            
        elif '@admin' in message.text.lower() or '@admins' in message.text.lower():
            if await is_check_admin(client, message.chat.id, message.from_user.id):
                return
            admins = []
            async for member in client.get_chat_members(chat_id=message.chat.id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
                if not member.user.is_bot:
                    admins.append(member.user.id)
                    if member.status == enums.ChatMemberStatus.OWNER:
                        try:
                            target_message = message.reply_to_message or message
                            sent_msg = await target_message.forward(member.user.id)
                            await sent_msg.reply_text(
                                f"#Attention\n★ User: {message.from_user.mention}\n★ Group: {message.chat.title}\n\n"
                                f"★ <a href={target_message.link}>Go to message</a>",
                                disable_web_page_preview=True
                            )
                        except Exception:
                            pass
            hidden_mentions = ''.join(f'[\u2064](tg://user?id={user_id})' for user_id in admins)
            await message.reply_text('Report sent to admins!' + hidden_mentions)
            return

        elif re.findall(r'https?://\S+|www\.\S+|t\.me/\S+|@\w+', message.text):
            if await is_check_admin(client, message.chat.id, message.from_user.id):
                return
            await message.delete()
            return await message.reply('Links are not allowed here!')
        
        elif '#request' in message.text.lower():
            if message.from_user.id in ADMINS:
                return
            clean_message = re.sub(r'#request', '', message.text, flags=re.IGNORECASE).strip()
            await client.send_message(
                LOG_CHANNEL,
                f"#Request\n★ User: {message.from_user.mention}\n★ Group: {message.chat.title}\n\n★ Message: {clean_message}"
            )
            await message.reply_text("Request sent successfully!")
            return  
        else:
            s = await message.reply(f"<b><i>⚠️ Searching for `{message.text}`...</i></b>")
            await auto_filter(client, message, s)
    else:
        k = await message.reply_text('Auto Filter is currently Off! ❌')
        await asyncio.sleep(5)
        await k.delete()
        try:
            await message.delete()
        except MessageDeleteForbidden:
            pass

@Client.on_callback_query(filters.regex(r"^next"))
async def next_page(client, query):
    ident, req, key, offset = query.data.split("_")
    if int(req) not in [query.from_user.id, 0]:
        return await query.answer("This is not for you!", show_alert=True)
    
    offset = int(offset)
    search = BUTTONS.get(key)
    cap = CAP.get(key)
    if not search:
        return await query.answer("Your request has expired. Please send a new one.", show_alert=True)

    files, n_offset, total = await get_search_results(search, offset=offset)
    if not files:
        return await query.answer("No more results found.", show_alert=True)

    temp.FILES[key] = files
    settings = await get_settings(query.message.chat.id)
    del_msg = f"\n\n<b>⚠️ This message will be deleted in {get_readable_time(DELETE_TIME)}</b>" if settings["auto_delete"] else ''
    
    files_link = ""
    if settings['links']:
        btn = []
        for file_num, file in enumerate(files, start=offset + 1):
            files_link += f"""<b>\n\n{file_num}. <a href=https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file['_id']}>[{get_size(file['file_size'])}] {file['file_name']}</a></b>"""
    else:
        btn = [[InlineKeyboardButton(text=f"[{get_size(file['file_size'])}] {file['file_name']}", callback_data=f"file#{file['_id']}")] for file in files]
    
    if settings['shortlink'] and not await is_premium(query.from_user.id, client):
        btn.insert(0, [InlineKeyboardButton("📰 Languages", callback_data=f"languages#{key}#{req}#{offset}"), InlineKeyboardButton("🔍 Quality", callback_data=f"quality#{key}#{req}#{offset}")])
        btn.insert(1, [InlineKeyboardButton("♻️ Send All ♻️", url=await get_shortlink(settings['url'], settings['api'], f'https://t.me/{temp.U_NAME}?start=all_{query.message.chat.id}_{key}'))])
    else:
        btn.insert(0, [InlineKeyboardButton("📰 Languages", callback_data=f"languages#{key}#{req}#{offset}"), InlineKeyboardButton("🔍 Quality", callback_data=f"quality#{key}#{req}#{offset}")])
        btn.insert(1, [InlineKeyboardButton("♻️ Send All", callback_data=f"send_all#{key}#{req}")])

    page_num = math.ceil(offset / MAX_BTN) + 1
    total_pages = math.ceil(total / MAX_BTN)
    
    page_buttons = []
    if offset > 0:
        page_buttons.append(InlineKeyboardButton("« Back", callback_data=f"next_{req}_{key}_{offset - MAX_BTN}"))
    
    page_buttons.append(InlineKeyboardButton(f"{page_num}/{total_pages}", callback_data="buttons"))
    
    if n_offset != 0:
        page_buttons.append(InlineKeyboardButton("Next »", callback_data=f"next_{req}_{key}_{n_offset}"))
    
    btn.append(page_buttons)
    btn.append([InlineKeyboardButton('🤑 Buy Premium 🤑', url=f"https://t.me/{temp.U_NAME}?start=premium")])
    
    await query.message.edit_text(cap + files_link + del_msg, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)

# ... (Rest of the callback handlers for languages, quality, etc. would follow a similar corrected structure) ...

# FIXED: Renamed function for clarity and fixed NameError.
@Client.on_callback_query(filters.regex(r"^spell_check"))
async def spell_check_callback(client, query):
    _, movie_id, user_id = query.data.split('#')
    if int(user_id) != 0 and query.from_user.id != int(user_id):
        return await query.answer("This is not for you!", show_alert=True)
    
    await query.answer("Checking database for this title...")
    movie = await get_poster(movie_id, id=True)
    search = movie.get('title')
    s = await query.message.edit_text(f"<b><i>✅ Corrected search to `{search}`. Searching...</i></b>")
    
    files, offset, total_results = await get_search_results(search)
    if files:
        results_tuple = (search, files, offset, total_results)
        # Pass query.message as the message object for context
        await auto_filter(client, query.message, s, spoll=results_tuple)
    else:
        k = await query.message.edit(f"😔 Sorry {query.from_user.mention}, I couldn't find <b>'{search}'</b> in my database either.")
        await client.send_message(LOG_CHANNEL, f"#No_Result (After Spellcheck)\n\nRequester: {query.from_user.mention}\nQuery: {search}")
        await asyncio.sleep(60)
        await k.delete()

# ... (Other callback handlers) ...

# FIXED: Removed redundant message deletion attempts
@Client.on_callback_query(filters.regex(r"^activate_plan"))
async def activate_plan_callback(client: Client, query: CallbackQuery):
    q = await query.message.edit('How many days do you need a premium plan for?\nSend the number of days (e.g., `30`).')
    try:
        msg = await client.listen(chat_id=query.message.chat.id, user_id=query.from_user.id, timeout=300)
        d = int(msg.text)
    except (ListenerTimeout, ValueError):
        await q.edit('Invalid input or request timed out. Please try again.')
        return
    
    await q.delete() # Delete the "How many days?" message once
    
    transaction_note = f'{d}_days_premium_for_{query.from_user.id}'
    amount = d * PRE_DAY_AMOUNT
    upi_uri = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR&tn={transaction_note}"
    
    qr = qrcode.make(upi_uri)
    qr_path = f"upi_qr_{query.from_user.id}.png"
    qr.save(qr_path)
    
    receipt_prompt = await query.message.reply_photo(
        qr_path,
        caption=(
            f"Please pay **₹{amount}** for your **{d}-day** premium plan.\n\n"
            "Scan this QR code with a UPI-supported app.\n\n"
            "After payment, please send the receipt screenshot here.\n\n"
            f"_This request will time out in 10 minutes. If you have issues, contact {RECEIPT_SEND_USERNAME}_"
        )
    )
    os.remove(qr_path)

    try:
        receipt_msg = await client.listen(chat_id=query.message.chat.id, user_id=query.from_user.id, timeout=600)
        if receipt_msg.photo:
            await receipt_prompt.delete()
            await query.message.reply('Your receipt has been sent for verification. Please wait a moment.\n'
                                      f'For support, contact: {RECEIPT_SEND_USERNAME}')
            await client.send_photo(RECEIPT_SEND_USERNAME, receipt_msg.photo.file_id, caption=f"Payment received for: `{transaction_note}`")
        else:
            await receipt_prompt.delete()
            await query.message.reply(f"That doesn't seem to be a photo. Please send your receipt to: {RECEIPT_SEND_USERNAME}")
    except ListenerTimeout:
        await receipt_prompt.delete()
        await query.message.reply(f'Your time is up! Please send your receipt directly to: {RECEIPT_SEND_USERNAME}')


# ... (Rest of your cb_handler function, keeping the other parts as they were) ...

async def auto_filter(client, msg, s, spoll=False):
    if not spoll:
        message = msg
        settings = await get_settings(message.chat.id)
        # Clean the search string more effectively
        search = re.sub(r'[\s\-_:;"\']+', ' ', message.text).strip()
        files, offset, total_results = await get_search_results(search)
        if not files:
            if settings["spell_check"]:
                # FIXED: Correct function name is called and client is passed
                await advantage_spell_check(client, message, s)
            else:
                await s.edit(f"I couldn't find any results for '{search}'.")
            return
    else:
        # For spell check callbacks, msg is the callback_query.message
        message = msg.reply_to_message  
        settings = await get_settings(message.chat.id)
        search, files, offset, total_results = spoll
    
    req = message.from_user.id if message.from_user else 0
    key = f"{message.chat.id}-{s.id}" # Use the bot's message ID for a more stable key
    temp.FILES[key] = files
    BUTTONS[key] = search
    
    # ... (The rest of the auto_filter function remains largely the same) ...
    # The button creation, IMDB fetching, and message sending logic follows here.
    # It seems correct and doesn't need major fixes.

# FIXED: Renamed for clarity, accepts 'client' object, uses it for sending messages.
async def advantage_spell_check(client, message, s):
    search = message.text
    google_search = search.replace(" ", "+")
    
    try:
        movies = await get_poster(search, bulk=True)
        if not movies:
            raise ValueError("No movies found")
    except Exception:
        btn = [[
            InlineKeyboardButton("⚠️ Instructions ⚠️", callback_data='instructions'),
            InlineKeyboardButton("🔎 Search on Google 🔍", url=f"https://www.google.com/search?q={google_search}")
        ]]
        n = await s.edit_text(text=script.NOT_FILE_TXT.format(message.from_user.mention, search), reply_markup=InlineKeyboardMarkup(btn))
        # FIXED: Used 'client' instead of 'temp.BOT'
        await client.send_message(LOG_CHANNEL, f"#No_Result\n\nRequester: {message.from_user.mention}\nQuery: {search}")
        await asyncio.sleep(60)
        try:
            await n.delete()
            await message.delete()
        except MessageDeleteForbidden:
            pass
        return

    movies = list(dict.fromkeys(movies))
    user_id = message.from_user.id if message.from_user else 0
    buttons = [
        [InlineKeyboardButton(text=movie.get('title'), callback_data=f"spell_check#{movie.movieID}#{user_id}")]
        for movie in movies[:5] # Limit to 5 suggestions to avoid clutter
    ]
    buttons.append([InlineKeyboardButton("🚫 Close 🚫", callback_data="close_data")])
    
    s = await s.edit_text(
        text=f"👋 Hello {message.from_user.mention},\n\nI couldn't find anything for <b>'{search}'</b>.\nDid you mean one of these? 👇",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    # Automatically close the suggestion message after some time
    await asyncio.sleep(300)
    try:
        await s.delete()
        await message.delete()
    except MessageDeleteForbidden:
        pass
