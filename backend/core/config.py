import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    data_dir: Path = PROJECT_ROOT / "data" / "runtime"
    corpus_path: Path = PROJECT_ROOT / "data" / "legal-corpus.json"
    frontend_origin: str = "http://localhost:3000"
    bff_secret: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"

    @property
    def production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            data_dir=Path(os.getenv("LUATRAG_DATA_DIR", str(PROJECT_ROOT / "data" / "runtime"))),
            corpus_path=Path(
                os.getenv("LUATRAG_CORPUS_PATH", str(PROJECT_ROOT / "data" / "legal-corpus.json"))
            ),
            frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/"),
            bff_secret=os.getenv("LUATRAG_BFF_SECRET", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        )

    def validate(self) -> None:
        if self.production and len(self.bff_secret.encode()) < 32:
            raise ValueError("Production requires LUATRAG_BFF_SECRET with at least 32 bytes.")
        if self.production and not self.frontend_origin.startswith("https://"):
            raise ValueError("Production requires an HTTPS FRONTEND_ORIGIN.")
