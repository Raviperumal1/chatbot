"""
Centralized configuration. All values are read from environment variables
(see .env.example). Nothing here calls out to any external AI service -
the LLM (Ollama) and embedding model both run locally.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://zenfuture:zenfuture@localhost:5432/zenfuture_chatbot"

    # Local LLM
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # Vector store
    chroma_persist_dir: str = "./chroma_store"
    chroma_collection: str = "zenfuture_kb"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # Company
    company_name: str = "Zenfuture Technologies"
    company_website_urls: str = "https://zenfuture.in"

    # Admin
    admin_api_key: str = "change_me"


settings = Settings()
