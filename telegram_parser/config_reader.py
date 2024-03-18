from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Config class"""

    API_ID: int
    API_HASH: str
    SPREADSHEET_KEY: str
    GOOGLE_SHEETS_API_CREDS: str
    CHUNK_SIZE: int

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


config = Settings()
