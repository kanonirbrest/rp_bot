import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROUP_ID = int(os.getenv("GROUP_ID", "0"))
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()]
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
TURSO_URL = os.getenv("TURSO_URL", "")
TURSO_TOKEN = os.getenv("TURSO_TOKEN", "")

# API погашения промокодов NR-* для внешних приложений (POST /api/promo/redeem)
PROMO_API_SECRET = os.getenv("PROMO_API_SECRET", "")
PROMO_DISCOUNT_PERCENT = int(os.getenv("PROMO_DISCOUNT_PERCENT", "10"))
PROMO_CAMPAIGN_VALID_UNTIL = os.getenv("PROMO_CAMPAIGN_VALID_UNTIL", "01.07.2026")
