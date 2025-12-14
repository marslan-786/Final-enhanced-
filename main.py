import os
import sys
from fastapi import FastAPI, HTTPException, Query
import requests
import time
import random
import mimetypes

app = FastAPI()

# --- CONFIGURATION ---
prefix_counter = 8003 
STATIC_SUFFIX = "f498d526aeaefaf015e6db91727"

# --- RAILWAY CONFIGURATION ---
RAILWAY_API_TOKEN = os.environ.get("RAILWAY_TOKEN") 
RAILWAY_SERVICE_ID = os.environ.get("RAILWAY_SERVICE_ID")

# --- USER AGENTS POOL ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
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
    print("\n🚨 CRITICAL: Triggering Railway Redeploy Sequence...")
    if not RAILWAY_API_TOKEN or not RAILWAY_SERVICE_ID:
        print("❌ Error: RAILWAY_TOKEN is missing.")
        sys.exit(1)

    query = """
    mutation serviceRedeploy($serviceId: String!) {
        serviceRedeploy(id: $serviceId)
    }
    """
    variables = {"serviceId": RAILWAY_SERVICE_ID}
    headers = {"Authorization": f"Bearer {RAILWAY_API_TOKEN}"}

    try:
        response = requests.post(RAILWAY_GRAPHQL_URL, json={"query": query, "variables": variables}, headers=headers)
        if response.status_code == 200:
            print("✅ Redeploy Signal Sent!")
            time.sleep(2)
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        sys.exit(1)

# --- NEW: ROBUST DOWNLOADER ---
def download_image_to_memory(url: str):
    """
    یہ فنکشن امیج کو ڈاؤنلوڈ کرتا ہے، خود کو براؤزر ظاہر کرتا ہے
    اور صحیح فائل ٹائپ (JPEG/PNG) کا پتہ لگاتا ہے۔
    """
    print(f"📥 [MEMORY] Fetching from Source: {url}")
    
    # ہیڈرز تاکہ Catbox/Bacon جیسی سائٹس بلاک نہ کریں
    dl_headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://google.com"
    }
    
    try:
        response = requests.get(url, headers=dl_headers, timeout=30)
        response.raise_for_status()
        
        # Content-Type کا پتہ لگانا
        content_type = response.headers.get("Content-Type", "")
        
        # اگر سرور نے ٹائپ نہیں بتائی تو URL سے اندازہ لگاؤ
        if "image" not in content_type:
            mime_type, _ = mimetypes.guess_type(url)
            if mime_type:
                content_type = mime_type
            else:
                content_type = "image/jpeg" # Default fallback
        
        # ایکسٹینشن بنانا
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        filename = f"temp_image{ext}"
        
        print(f"✅ Downloaded to Memory ({len(response.content)} bytes) | Type: {content_type}")
        return response.content, filename, content_type

    except Exception as e:
        print(f"❌ Download Failed: {str(e)}")
        return None, None, None

def process_single_attempt(image_bytes: bytes, filename: str, mime_type: str):
    job_id = None
    try:
        print(f"\n🚀 [STEP 1] Uploading Image ({mime_type})...")
        post_headers = current_headers.copy()
        post_headers["timezone"] = "Asia/Karachi"
        post_headers["authorization"] = "" 
        
        # اہم: صحیح MIME Type بھیجنا
        files = {"original_image_file": (filename, image_bytes, mime_type)}
        
        response = requests.post(CREATE_JOB_URL, headers=post_headers, files=files, timeout=60)
        data = response.json()

        if data.get("code") == 100000:
            job_id = data["result"]["job_id"]
            print(f"✅ Job Created: {job_id}")
        else:
            print(f"⚠️ API Error: {data}")
            return None, "upload_failed"

    except Exception as e:
        print(f"⚠️ Exception: {e}")
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

def get_enhanced_url_with_retry(image_bytes: bytes, filename: str, mime_type: str):
    for attempt in range(3):
        print(f"\n🔹 Attempt {attempt + 1}/3")
        
        if attempt > 0:
             print("⚠️ Incrementing Serial Prefix...")
             generate_smart_headers()
        
        url, status = process_single_attempt(image_bytes, filename, mime_type)
        
        if status == "success":
            return {"status": "success", "url": url}
        
        print("⚠️ Failed. Retrying...")
        time.sleep(2)

    print("\n❌ All 3 attempts failed. Initiating Self-Destruct...")
    trigger_railway_redeploy()
    raise HTTPException(status_code=408, detail="Server Refreshing...")

@app.get("/")
def home():
    return {"message": "Universal Image Upscaler Active"}

@app.get("/enhance")
def enhance_via_url(url: str = Query(..., description="Image URL")):
    # 1. پہلے امیج کو اپنی میموری میں ڈاؤنلوڈ کرو
    img_bytes, filename, mime_type = download_image_to_memory(url)
    
    if not img_bytes:
        # اگر ڈاؤنلوڈ ہی نہیں ہوا تو ایرر دے دو
        return {"status": "error", "message": "Failed to download image from source URL. Source might be blocking bots."}
    
    # 2. اب میموری سے آگے بھیجو
    try:
        return get_enhanced_url_with_retry(img_bytes, filename, mime_type)
    except HTTPException as http_e:
        return {"status": "error", "message": http_e.detail}
    except Exception as e:
        return {"status": "error", "message": f"Server Error: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
