import os
import sys
import threading
from fastapi import FastAPI, HTTPException, Query
import requests
import time
import random
import mimetypes

app = FastAPI()

# --- 🔒 HARDCODED CONFIGURATION (Verified via Curl) ---
RAILWAY_API_TOKEN = "2f404c04-9128-4f41-91b7-b9f32fa378d0"
RAILWAY_SERVICE_ID = "ceb89720-2545-48ae-8657-059dd6e19464"
RAILWAY_ENVIRONMENT_ID = "5f122bca-76aa-4fd5-a8a7-58d3e056f838"
RAILWAY_GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"

# --- ROTATION LOGIC ---
prefix_counter = random.randint(10000, 99000)
STATIC_SUFFIX = "f498d526aeaefaf015e6db91727"

# --- USER AGENTS ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
]

current_headers = {}

# Endpoints
CREATE_JOB_URL = "https://api.imgupscaler.ai/api/image-upscaler/v2/upscale/create-job"
GET_JOB_URL_TEMPLATE = "https://api.imgupscaler.ai/api/image-upscaler/v1/universal_upscale/get-job/{}"

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
        "x-requested-with": "mark.via.gp", 
    }
    print(f"🔄 Identity Rotated! Serial: {new_serial}")

generate_smart_headers()

def perform_redeploy_sync():
    """
    یہ فنکشن ایک الگ تھریڈ میں چلے گا تاکہ مین سرور اسے روک نہ سکے۔
    یہ بالکل وہی کام کرے گا جو آپ کی Curl کمانڈ کر رہی ہے۔
    """
    print("\n🚨 [THREAD] Sending Redeploy Signal to Railway...")

    query = """
    mutation serviceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
        serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
    }
    """
    
    variables = {
        "serviceId": RAILWAY_SERVICE_ID,
        "environmentId": RAILWAY_ENVIRONMENT_ID
    }
    
    headers = {
        "Authorization": f"Bearer {RAILWAY_API_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            RAILWAY_GRAPHQL_URL, 
            json={"query": query, "variables": variables}, 
            headers=headers,
            timeout=10
        )
        
        print(f"📡 Railway Response Code: {response.status_code}")
        print(f"📡 Railway Response Body: {response.text}")

        if response.status_code == 200 and "data" in response.json():
            print("✅ SUCCESS: Redeploy trigger accepted!")
            print("⏳ Waiting 3 seconds before hard kill...")
            time.sleep(3)
            print("💀 KILLING SERVER NOW.")
            os._exit(0) # یہ سب سے اہم لائن ہے، یہ سرور کو زبردستی بند کر دے گا
        else:
            print("❌ FAILURE: Railway refused request.")
            
    except Exception as e:
        print(f"❌ EXCEPTION during redeploy: {str(e)}")

# --- DOWNLOADER ---
def download_image_to_memory(url: str):
    print(f"📥 [MEMORY] Fetching from Source: {url}")
    try:
        response = requests.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=30)
        if response.status_code != 200: return None, None, None
        
        content_type = response.headers.get("Content-Type", "")
        if "image" not in content_type:
             content_type = "image/jpeg"
        
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        return response.content, f"temp{ext}", content_type
    except:
        return None, None, None

def process_single_attempt(image_bytes: bytes, filename: str, mime_type: str):
    job_id = None
    try:
        files = {"original_image_file": (filename, image_bytes, mime_type)}
        response = requests.post(CREATE_JOB_URL, headers=current_headers, files=files, timeout=60)
        data = response.json()

        if data.get("code") == 100000:
            job_id = data["result"]["job_id"]
        else:
            print(f"⚠️ API Error: {data}")
            return None, "upload_failed"

    except Exception:
        return None, "connection_error"

    # Polling Logic
    time.sleep(5)
    status_url = GET_JOB_URL_TEMPLATE.format(job_id)
    
    for _ in range(20): 
        time.sleep(2)
        try:
            res = requests.get(status_url, headers=current_headers, timeout=10)
            if res.status_code == 200:
                result = res.json().get("result", {})
                if result and "output_url" in result:
                    raw = result["output_url"]
                    return (raw[0] if isinstance(raw, list) else raw), "success"
        except:
            pass
            
    return None, "timeout"

def get_enhanced_url_logic(image_bytes: bytes, filename: str, mime_type: str):
    # صرف 2 Attempts
    for attempt in range(2):
        print(f"\n🔹 Attempt {attempt + 1}/2")
        
        if attempt == 1:
             print("⚠️ First attempt failed. Rotating Identity...")
             generate_smart_headers()
        
        url, status = process_single_attempt(image_bytes, filename, mime_type)
        
        if status == "success":
            return {"status": "success", "url": url}
        
        print("⚠️ Failed.")
        time.sleep(2)

    # --- FINAL FAIL STATE ---
    print("\n❌ Both attempts failed. INITIATING REDEPLOY THREAD...")
    
    # تھریڈ سٹارٹ کریں تاکہ یہ فوراً چلے
    t = threading.Thread(target=perform_redeploy_sync)
    t.start()
    
    # یوزر کو 503 بھیج دیں
    raise HTTPException(status_code=503, detail="Server limits reached. Refreshing System... Try again in 1 minute.")

@app.get("/")
def home():
    return {"message": "Final Upscaler V3 Active", "id": prefix_counter}

@app.get("/enhance")
def enhance_via_url(url: str = Query(..., description="Image URL")):
    img_bytes, filename, mime_type = download_image_to_memory(url)
    
    if not img_bytes:
        return {"status": "error", "message": "Failed to download image."}
    
    try:
        return get_enhanced_url_logic(img_bytes, filename, mime_type)
    except HTTPException as http_e:
        raise http_e
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
