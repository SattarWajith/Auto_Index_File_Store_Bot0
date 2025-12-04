import os 

class Config:
    # Your API details from my.telegram.org
    API_ID = int(os.environ.get("API_ID", ""))
    API_HASH = os.environ.get("API_HASH", "")

    # Your Bot Token
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

    # Your Admin User ID
    ADMIN_ID = int(os.environ.get("ADMIN_ID", "1938030055"))
    
    # Your Owner DB Channel ID
    OWNER_DB_CHANNEL = int(os.environ.get("OWNER_DB_CHANNEL", "-1002535247194"))

    # Your MongoDB Connection String
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://w=majority&appName=Cluster0")
    DATABASE_NAME = os.environ.get("DATABASE_NAME", "telegram_bot_v3")
    
    # --- TMDB API Key (Optional, for posters) ---
    TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "5a318417c7f4a722afd9d71df548877b")
    
    # --- Your VPS IP Address and Port for the Web Server ---
    # DECREED FIX: The hardcoded IP has been changed. 
    # You MUST set your VPS_IP in your environment variables for the bot to work correctly.
    VPS_IP = os.environ.get("VPS_IP", "0.0.0.0")
    
    # Port for the web server (both redirect and streaming)
    VPS_PORT = int(os.environ.get("VPS_PORT", 7071)) #7071 is a custom port you can add any
    
    # The name of the file that stores your bot's username (for the redirector)
    BOT_USERNAME_FILE = "bot_username.txt"
    
    # ================================================================= #
    # VVVVVV YAHAN PAR NAYA TUTORIAL LINK ADD KIYA GAYA HAI VVVVVV #
    # ================================================================= #
    # Yahan apna tutorial video ya channel ka link daalein
    TUTORIAL_URL = os.environ.get("TUTORIAL_URL", "https://t.me/turisbana/3")
