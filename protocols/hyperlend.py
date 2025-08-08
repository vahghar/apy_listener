import requests
import time
import os
from dotenv import load_dotenv
#from telebot import send_telegram_messagefrom web3 import Web3



load_dotenv()

RPC_URL = os.getenv("HYPURRFI_RPC_URL")
web3 = Web3(Web3.HTTPProvider(RPC_URL))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_URL = "https://api.hyperlend.finance"

CHAIN = "hyperEvm"

def get_hyperlend_apy():
    try:
        response = requests.get(f"{BASE_URL}/data/markets?chain={CHAIN}")
        response.raise_for_status()
        data = response.json()

        apy_info = []
        for reserve in data.get("reserves", []):
            symbol = reserve.get("symbol")

            supply_raw = int(reserve.get("liquidityRate", 0))
            supply_apy = (supply_raw / 1e27) * 100

            if symbol in ["USD₮0", "kHYPE", "USDe"]:
                apy_info.append(
                    f"{symbol}:\n🔼 Supply APY: {supply_apy:.2f}%\n"
                )

        if not apy_info:
            return "No data for whitelisted assets."

        return "\n".join(apy_info)

    except Exception as e:
        return f"Error fetching data: {e}"


#def send_telegram_message(message):
#    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
#    payload = {
#        "chat_id": CHAT_ID,
#        "text": message,
#        "parse_mode": "Markdown"
#    }
#    response = requests.post(url, data=payload)
#    if response.status_code != 200:
#        print("Failed to send message:", response.text)

if __name__ == "__main__":
    while True:
        apy_data = get_hyperlend_apy()
        send_telegram_message(f"📈 *Hyperlend APY Update*\n\n{apy_data}")
        #time.sleep(60 * 60)  
