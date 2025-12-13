import os
import sys
from fastapi import FastAPI, HTTPException, Query
import requests
import time
import random

app = FastAPI()

# --- CONFIGURATION ---
prefix_counter = 8003 
STATIC_SUFFIX = "f498d526aeaefaf015e6db91727"

# --- RAILWAY CONFIGURATION ---
# یہ ٹوکن آپ کو Railway کی سیٹنگز سے ملے گا (طریقہ نیچے لکھا ہے)
RAILWAY_API_TOKEN = os.environ.get("RAILWAY_TOKEN") 
# یہ ریلوے خود بخود سیٹ کرتا ہے، آپ کو چھیڑنے کی ضرورت نہیں
RAILWAY_SERVICE_ID = os.environ.get("RAILWAY_SERVICE_ID")

# --- USER AGENTS POOL ---
USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-A736B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    # ... (باقی لسٹ وہی رہے گی) ...
    "Mozilla/5.0 (Linux; Android 10; Huawei Y9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.0.0 Mobile Safari/537.36"
]

current_headers = {}

# Endpoints
CREATE_JOB_URL = "https://api.imgupscaler.ai/api/image-upscaler/v2/upscale/create-job"
GET_JOB_URL_TEMPLATE = "https://api.imgupscaler.ai/api/image-upscaler/v1/universal_upscale/get-job/{}"
RAILWAY_GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"

def generate_smart_headers():
    global prefix_counter, current_headers
    prefix_counter += 1
    new_serial = f"0{prefix_counter}{STATIC_SUFFIX}"
    ua = random.choice(USER_AGENTS)
    
    current_headers = {
        "product-serial": new_serial,
        "User-Agent": ua,
        "Origin": "https://imgupscaler.ai",
        "Referer": "https://imgupscaler.ai/",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "priority": "u=1, i",
        "x-requested-with": "mark.via.gp", 
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }
    print(f"🔄 Identity Rotated! Serial: {new_serial}")

generate_smart_headers()

def trigger_railway_redeploy():
    """
    یہ فنکشن ریلوے کو سگنل بھیجے گا کہ سروس کو دوبارہ ڈپلائے کرو۔
    """
    print("\n🚨 CRITICAL: Triggering Railway Redeploy Sequence...")
    
    if not RAILWAY_API_TOKEN or not RAILWAY_SERVICE_ID:
        print("❌ Error: RAILWAY_TOKEN is missing. Cannot redeploy automatically.")
        # اگر ٹوکن نہیں ہے تو کم از کم ایپ کو کریش کر دو تاکہ ریلوے اسے ریسٹارٹ کر دے
        sys.exit(1)
        return

    query = """
    mutation serviceRedeploy($serviceId: String!) {
        serviceRedeploy(id: $serviceId)
    }
    """
    
    variables = {"serviceId": RAILWAY_SERVICE_ID}
    headers = {"Authorization": f"Bearer {RAILWAY_API_TOKEN}"}

    try:
        response = requests.post(
            RAILWAY_GRAPHQL_URL, 
            json={"query": query, "variables": variables}, 
            headers=headers
        )
        
        if response.status_code == 200:
            print("✅ Redeploy Signal Sent! The server will restart in a few seconds.")
            # ایپ کو یہیں روک دیں تاکہ مزید ریکویسٹ نہ لیں
            time.sleep(2)
            sys.exit(0)
        else:
            print(f"❌ Redeploy Failed: {response.text}")
            sys.exit(1) # Force restart anyway
            
    except Exception as e:
        print(f"❌ Failed to contact Railway API: {e}")
        sys.exit(1)

def process_single_attempt(image_bytes: bytes, filename: str):
    job_id = None
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
            return None, "upload_failed"

        if data.get("code") == 100000:
            job_id = data["result"]["job_id"]
            print(f"✅ Job Created: {job_id}")
        else:
            return None, "upload_failed"

    except Exception as e:
        return None, "connection_error"

    print("⏳ Waiting 5s for server sync...")
    time.sleep(5)

    status_url = GET_JOB_URL_TEMPLATE.format(job_id)
    print(f"🔎 [STEP 2] Polling: {status_url}")
    get_headers = current_headers.copy()
    
    for i in range(40): 
        time.sleep(2)
        try:
            res = requests.get(status_url, headers=get_headers, timeout=15)
            if res.status_code != 200: continue

            res_data = res.json()
            status_msg = res_data.get("message", {}).get("en", "Unknown")

            if "Resource does not exist" in status_msg:
                time.sleep(2) 
                continue

            result = res_data.get("result", {})
            if result and "output_url" in result:
                raw_url = result["output_url"]
                final_url = raw_url[0] if isinstance(raw_url, list) else raw_url
                print(f"🎉 [SUCCESS] URL Found: {final_url}")
                return final_url, "success"
        except:
            continue
            
    return None, "timeout"

def get_enhanced_url_with_retry(image_bytes: bytes, filename: str):
    print(f"--- NEW REQUEST: {filename} ---")
    
    # 3 کوششیں کریں گے
    for attempt in range(3):
        print(f"\n🔹 Attempt {attempt + 1}/3")
        
        if attempt > 0:
             print("⚠️ Previous attempt failed. Incrementing Serial Prefix...")
             generate_smart_headers()
        
        url, status = process_single_attempt(image_bytes, filename)
        
        if status == "success":
            return {"status": "success", "url": url}
        
        # اگر فیل ہوا تو لوپ دوبارہ چلے گا
        print("⚠️ Failed. Retrying...")
        time.sleep(2)

    # --- اگر 3 بار فیل ہو گیا ---
    print("\n❌ All 3 attempts failed. Initiating Self-Destruct/Redeploy...")
    trigger_railway_redeploy()
    
    # ویسے تو اوپر والا فنکشن کوڈ روک دے گا، لیکن اگر وہ فیل ہوا تو یہ ایرر آئے گا
    raise HTTPException(status_code=408, detail="⚠️ Server is refreshing. Please try again in 1 minute.")

@app.get("/")
def home():
    return {"message": "API with Auto-Redeploy System Active."}

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
    
