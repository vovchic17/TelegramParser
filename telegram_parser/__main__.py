import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config_reader import config
from pyrogram import Client
from pyrogram.methods.utilities.idle import idle
from telegram_parse import TelegramParser


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    client = Client("my_account", config.API_ID, config.API_HASH)
    tp = TelegramParser(config.SPREADSHEET_KEY, client)
    await tp.initizlize()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(tp.update_sheets, IntervalTrigger(seconds=5))
    scheduler.start()
    await idle()


asyncio.run(main())
