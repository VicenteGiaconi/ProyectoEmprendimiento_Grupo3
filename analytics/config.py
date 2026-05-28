from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
DJANGO_DB_PATH: str = str(BASE_DIR / "db.sqlite3")
ANALYTICS_DB_PATH: str = str(BASE_DIR / "analytics.db")

AGENT_SPEAKER: int = 0
CLIENT_SPEAKER: int = 1

# Default protocol rules seeded on first run
# key → description (sent to Gemini as evaluation criterion)
PROTOCOL_RULES: dict[str, str] = {
    "greeted": "El agente saludó al cliente al inicio de la llamada",
    "asked_for_id": "El agente solicitó identificación o número de cliente",
    "offered_solution": "El agente ofreció una solución concreta al problema del cliente",
    "said_goodbye": "El agente se despidió cordialmente al final de la llamada",
    "empathy_shown": "El agente demostró empatía con el problema o la situación del cliente",
}

# Short display labels for the default rules
PROTOCOL_RULE_LABELS: dict[str, str] = {
    "greeted": "Saludó",
    "asked_for_id": "Pidió ID",
    "offered_solution": "Ofreció solución",
    "said_goodbye": "Se despidió",
    "empathy_shown": "Mostró empatía",
}
