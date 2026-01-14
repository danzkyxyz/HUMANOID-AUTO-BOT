import requests
import time
import random
import string
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import pytz
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

# --- KONFIGURASI ---
BASE_URL = "https://prelaunch.humanoidnetwork.org/api"
HEADERS = {
    "accept": "*/*",
    "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "content-type": "application/json",
    "origin": "https://prelaunch.humanoidnetwork.org",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
}

file_lock = threading.Lock()
tz = pytz.timezone('Asia/Jakarta')

# --- HELPER FUNCTIONS ---

def generate_human_name():
    first_names = ["budi", "eko", "santi", "agus", "dewi", "rizky", "fajar", "nina", "putra", "sari", "dian", "angga", "maya", "hendra", "mulyadi", "dimas", "ayu", "setyo", "ratna", "bagus"]
    last_names = ["santoso", "wijaya", "saputra", "hidayat", "lestari", "kusuma", "pratama", "setiawan", "ramadhan", "fitriani", "nugroho", "gunawan", "permadi", "susanto"]
    return f"{random.choice(first_names)}{random.choice(last_names)}{random.randint(10, 99)}"

def generate_random_tweet_url():
    name = generate_human_name()
    tweet_id = ''.join(random.choices(string.digits, k=15))
    return f"https://x.com/{name}/status/{tweet_id}"

def load_lines(filename):
    if not os.path.exists(filename): return []
    with open(filename, "r") as f:
        return [line.strip() for line in f if line.strip()]

def get_auth_token(wallet_address, private_key, reff_code=None):
    try:
        res_nonce = requests.post(f"{BASE_URL}/auth/nonce", json={"walletAddress": wallet_address}, headers=HEADERS, timeout=15).json()
        message = res_nonce['message']
        signed = Account.sign_message(encode_defunct(text=message), private_key=private_key)
        signature = signed.signature.hex()
        if not signature.startswith('0x'): signature = '0x' + signature
        
        payload = {"walletAddress": wallet_address, "message": message, "signature": signature}
        if reff_code: payload["referralCode"] = reff_code
        
        res_auth = requests.post(f"{BASE_URL}/auth/authenticate", json=payload, headers=HEADERS, timeout=15).json()
        return res_auth.get('token')
    except: return None

# --- LOGIKA DAILY BARU (MENU 2) ---

def process_tasks_one_by_one(token, pool, type_name):
    success_in_account = []
    h = HEADERS.copy()
    h["authorization"] = f"Bearer {token}"
    h["referer"] = "https://prelaunch.humanoidnetwork.org/training"
    
    for url in pool:
        try:
            payload = {"fileName": url.split('/')[-1], "fileType": type_name, "fileUrl": url, "recaptchaToken": ""}
            res = requests.post(f"{BASE_URL}/training", json=payload, headers=h, timeout=15)
            res_text = res.text
            
            if "limit" in res_text.lower() or "reached" in res_text.lower():
                return success_in_account, True
            
            if res.status_code == 200:
                success_in_account.append(url)
            
            if len(success_in_account) >= 3:
                return success_in_account, True
                
            time.sleep(0.2)
        except: continue
    return success_in_account, False

def clear_extra_social_tasks(token):
    h = HEADERS.copy()
    h["authorization"] = f"Bearer {token}"
    h["referer"] = "https://prelaunch.humanoidnetwork.org/tasks"
    
    extra_tasks = [
        {"taskId": "7", "url": "https://www.youtube.com/@HumanoidNetwork", "name": "YouTube"},
        {"taskId": "8", "url": "https://www.tiktok.com/@humanoidnetwork?is_from_webapp=1&sender_device=pc", "name": "TikTok"},
        {"taskId": "6", "url": "https://www.instagram.com/humanoidnetwork?igsh=MWIwZmpoZnQ5ZGh5bw==", "name": "Instagram"},
        {"taskId": "9", "url": "https://www.reddit.com/user/humanoidNetwork/", "name": "Reddit"}
    ]
    
    results = []
    for task in extra_tasks:
        try:
            payload = {"taskId": task["taskId"], "data": {"url": task["url"]}}
            res = requests.post(f"{BASE_URL}/tasks", json=payload, headers=h, timeout=15)
            status = "Berhasil" if res.status_code == 200 else "Skip/Limit"
            results.append(f"{task['name']}: {status}")
            time.sleep(0.2)
        except: pass
    return results

def daily_worker(line, m_pool, d_pool, idx, total):
    try:
        parts = line.split('|')
        if len(parts) < 2: return 
        addr = parts[0].strip()
        pk = parts[1].strip()
        
        token = get_auth_token(addr, pk)
        if not token:
            print(f"[*] Akun {idx}/{total}: {addr} -> [!] GAGAL LOGIN")
            return

        log = [f"\n[*] Akun {idx}/{total}: {addr}"]
        
        # 1. Dataset
        s_d, lim_d = process_tasks_one_by_one(token, d_pool, "dataset")
        log.append(f"    - Limit dataset {len(s_d) if not lim_d else '3'}/3")
        
        # 2. Model
        s_m, lim_m = process_tasks_one_by_one(token, m_pool, "model")
        log.append(f"    - Limit model {len(s_m) if not lim_m else '3'}/3")

        # 3. Social
        social_res = clear_extra_social_tasks(token)
        log.append(f"    - Social Task: {', '.join(social_res)}")
        
        print("\n".join(log))
    except Exception as e:
        print(f"[!] Error pada akun {idx}: {e}")

def run_daily_process():
    accounts = load_lines("pkreff.txt")
    m_pool = load_lines("modelpack.txt")
    d_pool = load_lines("datasetpack.txt")
    total = len(accounts)

    print(f"\n{'='*75}")
    print(f"MULAI PROSES : {datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')} WIB")
    print(f"TOTAL AKUN   : {total}")
    print(f"{'='*75}")

    if not accounts:
        print("File pkreff.txt tidak ditemukan atau kosong.")
        return

    with ThreadPoolExecutor(max_workers=30) as executor:
        for i, line in enumerate(accounts, 1):
            executor.submit(daily_worker, line, m_pool, d_pool, i, total)

    print(f"\n{'='*75}\nPROSES SELESAI UNTUK SEMUA AKUN.\n{'='*75}\n")

# --- LOGIKA AUTO REFF (MENU 1) ---

def clear_initial_tasks(token, addr_label):
    task_headers = HEADERS.copy()
    task_headers["authorization"] = f"Bearer {token}"
    
    # Task Baru: Update Username
    uname = generate_human_name()
    requests.post(f"{BASE_URL}/user/update-x-username", json={"twitterUsername": uname}, headers=task_headers, timeout=15)

    tasks = [
        {"taskId": "1", "data": {"url": "https://x.com/HumanoidNetwork"}},
        {"taskId": "2", "data": {"url": "https://t.me/TheHumanoidNetwork"}},
        {"taskId": "3", "data": {}},
        {"taskId": "4", "data": {"tweetId": generate_random_tweet_url()}},
        {"taskId": "5", "data": {"url": "https://discord.gg/f5C32A89q8"}},
        {"taskId": "6", "data": {"url": "https://www.instagram.com/humanoidnetwork"}},
        {"taskId": "7", "data": {"url": "https://www.youtube.com/@HumanoidNetwork"}},
        {"taskId": "8", "data": {"url": "https://www.tiktok.com/@humanoidnetwork"}},
        {"taskId": "9", "data": {"url": "https://www.reddit.com/user/humanoidNetwork/"}}
    ]
    for t in tasks:
        requests.post(f"{BASE_URL}/tasks", json=t, headers=task_headers, timeout=15)
    print(f"    [OK] Initial Tasks Completed: {addr_label}")

def worker_reff(index, reff_code):
    acc = Account.create()
    addr = Web3.to_checksum_address(acc.address)
    pk = acc.key.hex()
    addr_label = f"{addr[:10]}..."

    token = get_auth_token(addr, pk, reff_code)
    if token:
        clear_initial_tasks(token, addr_label)
        # Ambil reff code baru untuk disimpan
        h = HEADERS.copy()
        h["authorization"] = f"Bearer {token}"
        res = requests.get(f"{BASE_URL}/user", headers=h, timeout=15).json()
        new_reff = res.get('user', {}).get('referralCode', 'N/A')
        
        with file_lock:
            with open("pkreff.txt", "a") as f: f.write(f"{addr}|{pk}\n")
            with open("pkreffwithcodereff.txt", "a") as f: f.write(f"{addr}|{pk}|{new_reff}\n")
        print(f"[{index}] Sukses: {addr} | Reff Baru: {new_reff}")
    else:
        print(f"[{index}] Gagal registrasi: {addr_label}")

# --- MAIN MENU & SCHEDULER ---

def main():
    while True:
        print("\n" + "="*45)
        print("    HUMANOID NETWORK BOT - MULTI TASK")
        print("="*45)
        print("1. Auto Referral & Initial Tasks")
        print("2. Daily Task Mode (Auto Run & Standby 14:00 WIB)")
        print("0. Keluar")
        choice = input("Pilih menu: ")

        if choice == '1':
            reff_code = input("Masukkan Kode Reff Utama: ").strip()
            num = int(input("Mau buat berapa reff? "))
            with ThreadPoolExecutor(max_workers=10) as executor:
                for i in range(num): executor.submit(worker_reff, i+1, reff_code)
        
        elif choice == '2':
            print("\n[!] Memasuki Mode Daily Task...")
            first_run = True
            try:
                while True:
                    now = datetime.now(tz)
                    current_time = now.strftime("%H:%M")
                    
                    if first_run or current_time == "14:00":
                        run_daily_process()
                        first_run = False
                        if current_time == "14:00":
                            time.sleep(65)
                    
                    print(f"\r[Standby] {now.strftime('%H:%M:%S')} WIB | Menunggu jam 14:00...", end="")
                    time.sleep(30)
            except KeyboardInterrupt:
                print("\n[!] Kembali ke menu utama...")

        elif choice == '0':
            break

if __name__ == "__main__":
    main()