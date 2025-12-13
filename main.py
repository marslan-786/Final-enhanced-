import os
from fastapi import FastAPI, HTTPException, Query
import requests
import time
import uuid
import random

app = FastAPI()

# --- CONFIGURATION ---
# یہ وہ بیس سیریل ہے جس کے آخری حصے کو ہم رینڈم رکھیں گے لیکن شروع کا حصہ ترتیب وار بڑھائیں گے
# تاکہ سرور کو لگے کہ یہ ویلڈ سیریلز ہیں۔
SERIAL_PREFIX = "08003f498d526aeaefaf015e6db9"
serial_counter = 1727 # آپ کے دیے گئے سیریل کا آخری حصہ (approx)

# --- USER AGENTS POOL ---
USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; SM-A525F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 10; VOG-L29) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Mobile Safari/537.36"
]

current_headers = {}

# Endpoints
CREATE_JOB_URL = "https://api.imgupscaler.ai/api/image-upscaler/v2/upscale/create-job"
GET_JOB_URL_TEMPLATE = "https://api.imgupscaler.ai/api/image-upscaler/v1/universal_upscale/get-job/{}"

def generate_smart_headers():
    """Generates headers that mimic a real device switching identity"""
    global serial_counter, current_headers
    
    # 1. Serial Logic: Increment Counter + Random Hex Suffix
    serial_counter += 1
    # سیریل کا آخری حصہ (4 ہندسے) ترتیب وار بڑھا رہے ہیں
    suffix = f"{serial_counter:04d}" 
    # تھوڑا سا رینڈم سالٹ بھی ڈالیں تاکہ بالکل مشینی نہ لگے
    random_part = uuid.uuid4().hex[:4]
    
    new_serial = f"{SERIAL_PREFIX}{random_part}{suffix}"[:32] # Max 32 chars
    
    # 2. Pick Random User Agent
    ua = random.choice(USER_AGENTS)
    
    current_headers = {
        "product-serial": new_serial,
        "User-Agent": ua,
        "Origin": "https://imgupscaler.ai",
        "Referer": "https://imgupscaler.ai/",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "priority": "u=1, i",
        "x-requested-with": "mark.via.gp", # Fake App Package ID
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }
    print(f"🔄 Identity Rotated! Serial: {new_serial} | UA: {ua[:30]}...")

# پہلی بار ہیڈرز جنریٹ کریں
generate_smart_headers()

def process_single_attempt(image_bytes: bytes, filename: str):
    job_id = None
    
    # ==========================
    # STEP 1: UPLOAD (POST)
    # ==========================
    try:
        print(f"\n🚀 [STEP 1] Uploading Image...")
        
        post_headers = current_headers.copy()
        post_headers["timezone"] = "Asia/Karachi"
        post_headers["authorization"] = "" 
        
        files = {"original_image_file": (filename, image_bytes, "image/jpeg")}
        
        response = requests.post(CREATE_JOB_URL, headers=post_headers, files=files, timeout=60)
        
        try:
            data = response.json()
        except:
            print(f"❌ Upload Failed (Non-JSON): {response.text[:100]}")
            return None, "upload_failed"

        if data.get("code") == 100000:
            job_id = data["result"]["job_id"]
            print(f"✅ Job Created: {job_id}")
        else:
            print(f"⚠️ API Error Code: {data.get('code')} - {data.get('message')}")
            return None, "upload_failed"

    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return None, "connection_error"

    # ==========================
    # STEP 1.5: SYNC WAIT
    # ==========================
    print("⏳ Waiting 5s for server sync...")
    time.sleep(5)

    # ==========================
    # STEP 2: POLLING (GET)
    # ==========================
    status_url = GET_JOB_URL_TEMPLATE.format(job_id)
    print(f"🔎 [STEP 2] Polling: {status_url}")
    
    get_headers = current_headers.copy()
    
    for i in range(40): 
        time.sleep(2)
        try:
            res = requests.get(status_url, headers=get_headers, timeout=15)
            
            if res.status_code != 200:
                print(f"   ⚠️ HTTP {res.status_code}")
                continue

            res_data = res.json()
            status_msg = res_data.get("message", {}).get("en", "Unknown")

            if "Resource does not exist" in status_msg:
                print(f"   ⚠️ Job not ready yet (Syncing...). Waiting...")
                time.sleep(2) 
                continue

            result = res_data.get("result", {})
            if result and "output_url" in result:
                raw_url = result["output_url"]
                final_url = raw_url[0] if isinstance(raw_url, list) else raw_url
                print(f"🎉 [SUCCESS] URL Found: {final_url}")
                return final_url, "success"
            
            print(f"   Status: {status_msg}")
                
        except Exception as e:
            print(f"   ❌ Polling Exception: {e}")
            continue
            
    return None, "timeout"

def get_enhanced_url_with_retry(image_bytes: bytes, filename: str):
    print(f"--- NEW REQUEST: {filename} ---")
    
    for attempt in range(3):
        print(f"\n🔹 Attempt {attempt + 1}/3")
        
        # ہر کوشش سے پہلے نئی شناخت (اگر پچھلی فیل ہوئی ہو)
        if attempt > 0:
             generate_smart_headers()
        
        url, status = process_single_attempt(image_bytes, filename)
        
        if status == "success":
            return {"status": "success", "url": url}
        
        elif status == "timeout":
            print("❌ Timeout! Server slow. Rotating Identity...")
            continue 
            
        else:
            print("⚠️ Upload Error. Rotating Identity...")
            # اگلی اٹیمٹ میں نیا ہیڈر خود بخود بن جائے گا
            time.sleep(2)
            continue

    raise HTTPException(status_code=408, detail="⚠️ Server is busy. Please try again later.")

@app.get("/")
def home():
    return {"message": "API with Smart Headers & UA Rotation Running."}

@app.get("/enhance")
def enhance_via_url(url: str = Query(..., description="Image URL")):
    try:
        print(f"\n📥 [TELEGRAM] Downloading...")
        img_response = requests.get(url, timeout=45)
        
        if img_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Telegram Download Failed")
        
        return get_enhanced_url_with_retry(img_response.content, "url_image.jpg")

    except HTTPException as http_e:
        return {"status": "error", "message": http_e.detail}
    except Exception as e:
        return {"status": "error", "message": "Unexpected Server Error"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
