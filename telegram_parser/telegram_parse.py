import logging
from contextlib import suppress
from datetime import timedelta, timezone
from typing import TYPE_CHECKING

from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError
from gspread.utils import ValueInputOption
from gspread_asyncio import AsyncioGspreadClientManager
from pyrogram.enums import ChatType
from pyrogram.errors.exceptions.bad_request_400 import (
    PeerIdInvalid,
    UsernameNotOccupied,
)
from pyrogram.handlers import MessageHandler

if TYPE_CHECKING:
    from gspread_asyncio import AsyncioGspreadWorksheet
    from pyrogram import Client
    from pyrogram.types import Message

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


class TelegramParser:
    """Telegram parser class"""

    def __init__(
        self, spreadsheet_key: str, client: "Client", chunk_size: int, creds_path: str
    ) -> None:
        self.tz = timezone(timedelta(hours=3))
        self.spreadsheet_key = spreadsheet_key
        self.agcm = AsyncioGspreadClientManager(self.__get_creds)
        self.client = client
        self.chunk_size = chunk_size
        self.creds_path = creds_path
        self.busy = False

    def __get_creds(self) -> Credentials:
        creds = Credentials.from_service_account_file(self.creds_path)
        return creds.with_scopes(["https://www.googleapis.com/auth/drive"])

    async def initizlize(self) -> None:
        """Initialize worksheets"""
        agc = await self.agcm.authorize()
        self.ss = await agc.open_by_key(self.spreadsheet_key)
        self.worksheets: dict[str | int, AsyncioGspreadWorksheet] = {}
        if not self.client.is_connected:
            await self.client.start()
        self.client.add_handler(MessageHandler(self.feed_message))

    async def pre_format(self, worksheet: "AsyncioGspreadWorksheet") -> None:
        """Preformat worksheet"""
        with suppress(APIError):
            await worksheet.delete_columns(5, 50)
        await worksheet.update(
            [["Ссылка", "Дата", "Отправитель", "Текст"]], "A1:D1", nowait=True
        )

    def get_sender(self, message: "Message", chat: str) -> str:
        """Get formatted sender name"""
        if message.chat.type == ChatType.CHANNEL:
            sender = f'=HYPERLINK("t.me/{chat}"; "@{chat}")'
        elif message.from_user and message.from_user.username:
            sender = (
                f'=HYPERLINK("t.me/{message.from_user.username}"; '
                f'"{message.from_user.first_name or ""} '
                f'{message.from_user.last_name or ""}")'
            )
        elif message.from_user:
            sender = (
                f"{message.from_user.first_name or ''} "
                f"{message.from_user.last_name or ''}"
            )
        else:
            sender = ""
        return sender

    async def update_sheets(self) -> None:
        """Update the worksheets"""
        if self.busy:
            return
        self.busy = True
        worksheets = await self.ss.worksheets()
        for worksheet in worksheets:
            await self.pre_format(worksheet)
            values = await worksheet.get_all_values()
            chat = worksheet.title.lstrip("@")
            # Worksheet should only contain header
            # to be filled with message history
            if len(values) != 1:
                continue
            if chat.lstrip("-").isnumeric():
                chat = int(chat)
            rows = []
            try:
                async for message in self.client.get_chat_history(chat):
                    if not message or message.service:
                        continue

                    rows.append(
                        [
                            message.link,
                            message.date.replace(tzinfo=self.tz).strftime(
                                "%H:%M %d.%m.%Y"
                            ),
                            self.get_sender(message, chat),
                            "'" + (message.text or message.caption or ""),
                        ]
                    )

                    if len(rows) == self.chunk_size:
                        await worksheet.append_rows(rows, ValueInputOption.user_entered)
                        rows = []

                if rows:
                    await worksheet.append_rows(rows, ValueInputOption.user_entered)
                self.worksheets[chat] = worksheet

            except (UsernameNotOccupied, PeerIdInvalid):
                logger.info("Chat %s not found", chat)

        self.busy = False

    async def feed_message(self, _: "Client", message: "Message") -> None:
        """Feed message to the parser"""
        worksheet = chat = None
        if worksheet := self.worksheets.get(message.chat.username):
            chat = message.chat.username
        elif worksheet := self.worksheets.get(message.chat.id):
            chat = str(message.chat.id)
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
