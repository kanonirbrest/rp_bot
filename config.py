import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROUP_ID = int(os.getenv("GROUP_ID", "0"))
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()]
GROUP_INVITE_LINK = os.getenv("GROUP_INVITE_LINK", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
