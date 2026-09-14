"""Central configuration and defaults for Zenith."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

LLM_PROVIDER = os.getenv("ZENITH_LLM_PROVIDER", "ollama").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
LLM_TIMEOUT_SECONDS = 120
LLM_MAX_OUTPUT_TOKENS = 1600
RESUME_MAX_CHARS = 12000
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_NUM_CTX = 8192

# --- Ollama (local LLM) -------------------------------------------------
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
# Any model you have pulled works, e.g. `ollama pull llama3.2:3b`.
OLLAMA_MODEL = os.getenv("ZENITH_MODEL", "llama3.2:3b")

# --- Job search defaults (tuned for the user) ---------------------------
DEFAULT_KEYWORDS = "Software Engineer"
DEFAULT_LOCATIONS = ["Chennai", "Bengaluru"]

# LinkedIn "time posted range" options -> guest API f_TPR value
TIME_RANGE_OPTIONS = {
    "Past 24 hours": "r86400",
    "Past 3 days": "r259200",
    "Past week": "r604800",
    "Past month": "r2592000",
    "Any time": "",
}

# Be polite: seconds to wait between LinkedIn requests (min, max).
REQUEST_DELAY_RANGE = (1.2, 2.8)
FETCH_WORKERS = 3
REQUEST_COOLDOWN_SECONDS = 5 * 60

# Simple on-disk cache so re-running does not re-hit the network.
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")
CACHE_TTL_SECONDS = 60 * 30  # 30 minutes
DETAIL_CACHE_TTL_SECONDS = 60 * 60 * 24
