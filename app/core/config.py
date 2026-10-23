from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = os.getenv("PROJECT_NAME")
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    SECRET_KEY: str = os.getenv("SECRET_KEY")
    ALGORITHM: str = os.getenv("ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
    # Pièces jointes (images / vidéos)
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 50
    MAX_FILES_PER_COMPLAINT: int = 5

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
