"""Runtime configuration.

Design rule: *every* external credential is optional. The backend must start,
serve, and produce complete deterministic financial results with an empty
environment. Credentials only unlock optional capability (real Neo4j, LLM prose).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_ROOT / "data" / "synthetic"
ONTOLOGY_PATH = BACKEND_ROOT / "app" / "graph" / "ontology.ttl"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- Graph backend -------------------------------------------------
    # "memory" runs entirely in-process: no database, no credentials, same
    # query surface as Neo4j. This is the default so the system is always
    # demonstrable. "neo4j" switches to a real Aura/Community instance.
    graph_backend: Literal["memory", "neo4j"] = "memory"
    neo4j_uri: str | None = None
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None

    # ---- LLM provider (entirely optional) ------------------------------
    llm_provider: Literal["openai", "deepseek", "groq", "azure", "gemini", "none"] = "openai"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-chat"

    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"

    azure_openai_endpoint: str | None = None
    azure_openai_key: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str = "2024-12-01-preview"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    # ---- Business assumptions -----------------------------------------
    # SAP has no "cost of an idle plant" field -- it is a management
    # accounting figure, not ERP master data. It is surfaced here (and per
    # plant in the generated data) as an explicit, auditable assumption
    # rather than a magic constant buried in the calculator.
    default_idle_plant_cost_per_day: float = 180_000.0
    # Fraction of order value charged when a contractual delivery date slips.
    default_late_delivery_penalty_rate: float = 0.08
    # Divergence above this between LLM-stated and computed figures is a fault.
    llm_divergence_tolerance: float = 0.05

    # ---- API -----------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:8501"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def neo4j_configured(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_password)

    @property
    def llm_configured(self) -> bool:
        p = self.llm_provider
        if p == "none":
            return False
        return bool(
            {
                "openai": self.openai_api_key,
                "deepseek": self.deepseek_api_key,
                "groq": self.groq_api_key,
                "azure": self.azure_openai_key and self.azure_openai_endpoint,
                "gemini": self.gemini_api_key,
            }.get(p)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
