# ./utils/coin_loader.py
def load_coin_list(file_path: str) -> list:
    try:
        with open(file_path, 'r') as f:
            return [line.strip().upper() for line in f if line.strip()]
    except:
        return ["SOL", "BTC", "ETH"]  # Default coins