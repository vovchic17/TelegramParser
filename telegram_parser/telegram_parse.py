from contextlib import suppress
from datetime import timedelta, timezone
from typing import TYPE_CHECKING

from config_reader import config
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError
from gspread.utils import ValueInputOption
from gspread_asyncio import AsyncioGspreadClientManager
from pyrogram.enums import ChatType
from pyrogram.errors.exceptions.bad_request_400 import UsernameNotOccupied
from pyrogram.handlers import MessageHandler

if TYPE_CHECKING:
    from gspread_asyncio import AsyncioGspreadWorksheet
    from pyrogram import Client
    from pyrogram.types import Message


class TelegramParser:
    """Telegram parser class"""

    def __init__(self, spreadsheet_key: str, client: "Client") -> None:
        self.tz = timezone(timedelta(hours=3))
        self.spreadsheet_key = spreadsheet_key
        self.agcm = AsyncioGspreadClientManager(self.__get_creds)
        self.client = client
        self.busy = False

    def __get_creds(self) -> Credentials:
        creds = Credentials.from_service_account_file(config.GOOGLE_SHEETS_API_CREDS)
        return creds.with_scopes(["https://www.googleapis.com/auth/drive"])

    async def initizlize(self) -> None:
        """Initialize worksheets"""
        agc = await self.agcm.authorize()
        self.ss = await agc.open_by_key(self.spreadsheet_key)
        self.worksheets: dict[str, AsyncioGspreadWorksheet] = {}
        if not self.client.is_connected:
            await self.client.start()
        self.client.add_handler(MessageHandler(self.feed_message))

    async def update_sheets(self) -> None:
        """Update the worksheets"""
        if self.busy:
            return
        self.busy = True
        worksheets = await self.ss.worksheets()
        for worksheet in worksheets:
            with suppress(APIError):
                await worksheet.delete_columns(5, 50)
            values = await worksheet.get_all_values()
            if not values[0]:
                await worksheet.insert_row(["Ссылка", "Дата", "Отправитель", "Текст"])
            chat = worksheet.title.lstrip("@")
            if len(values) == 1:
                with suppress(UsernameNotOccupied):  # wrong chat username
                    rows = [
                        [
                            message.link,
                            message.date.replace(tzinfo=self.tz).strftime(
                                "%H:%M %d.%m.%Y"
                            ),
                            f'=HYPERLINK("t.me/{chat}"; "@{chat}")'
                            if message.chat.type == ChatType.CHANNEL
                            else f'=HYPERLINK("t.me/{message.from_user.username}";'
                            f'"{message.from_user.first_name or ""} '
                            f'{message.from_user.last_name or ""}")'
                            if message.from_user and message.from_user.username
                            else f"{message.from_user.first_name or ""} "
                            f"{message.from_user.last_name or ""}",
                            message.text or message.caption,
                        ]
                        async for message in self.client.get_chat_history(chat)
                        if message and not message.service
                    ]
                    await worksheet.append_rows(rows, ValueInputOption.user_entered)
                    self.worksheets[chat] = worksheet
        self.busy = False

    async def feed_message(self, _: "Client", message: "Message") -> None:
        """Feed message to the parser"""
        chat = message.chat.username
        worksheet = self.worksheets.get(chat)
        if worksheet is not None and not message.service:
            with suppress(APIError):  # worksheet might be deleted
                await worksheet.insert_row(
                    [
                        message.link,
                        message.date.replace(tzinfo=self.tz).strftime("%H:%M %d.%m.%Y"),
                        f'=HYPERLINK("t.me/{chat}"; "@{chat}")'
                        if message.chat.type == ChatType.CHANNEL
                        else f'=HYPERLINK("t.me/{message.from_user.username}";'
                        f'"{message.from_user.first_name or ""} '
                        f'{message.from_user.last_name or ""}")'
                        if message.from_user and message.from_user.username
                        else f"{message.from_user.first_name or ""} "
                        f"{message.from_user.last_name or ""}",
                        message.text or message.caption,
                    ],
                    2,
                    ValueInputOption.user_entered,
                    nowait=True,
                )
