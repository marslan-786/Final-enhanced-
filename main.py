import os
from fastapi import FastAPI, HTTPException, Query
import requests
import time
import uuid

app = FastAPI()

# --- CONFIGURATION (Based on Captured Logs) ---
# بیسک ہیڈرز جو ہر ریکویسٹ میں جائیں گے
BASE_HEADERS = {
    "product-serial": "e2130ffcfb9fdfe36701eeb431b2d4fc", # Default start serial
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/29.0 Chrome/136.0.0.0 Mobile Safari/537.36",
    "Origin": "https://imgupscaler.ai",
    "Referer": "https://imgupscaler.ai/",
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "priority": "u=1, i"
}

# Endpoints (Confirmed from Logs)
CREATE_JOB_URL = "https://api.imgupscaler.ai/api/image-upscaler/v2/upscale/create-job"
GET_JOB_URL_TEMPLATE = "https://api.imgupscaler.ai/api/image-upscaler/v1/universal_upscale/get-job/{}"

def refresh_serial():
    """اگر لمٹ ختم ہو جائے تو نیا سیریل بنائیں"""
    new_serial = uuid.uuid4().hex
    BASE_HEADERS["product-serial"] = new_serial
    print(f"🔄 SERIAL CHANGED: {new_serial}")

def process_single_attempt(image_bytes: bytes, filename: str):
    job_id = None
    
    # ==========================
    # STEP 1: UPLOAD (POST)
    # ==========================
    try:
        print(f"\n🚀 [STEP 1] Uploading Image...")
        
        # POST Request کے لیے ہیڈرز (Timezone لاگز میں موجود تھا)
        post_headers = BASE_HEADERS.copy()
        post_headers["timezone"] = "Asia/Karachi"
        post_headers["authorization"] = "" # لاگز میں خالی تھا، ہم بھی خالی بھیجیں گے
        
        files = {"original_image_file": (filename, image_bytes, "image/jpeg")}
        
        # API Call
        response = requests.post(CREATE_JOB_URL, headers=post_headers, files=files, timeout=60)
        
        # Debug Response
        try:
            data = response.json()
        except:
            print(f"❌ Upload Failed (Non-JSON): {response.text[:100]}")
            return None, "upload_failed"

        # Check Code
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
    # لاگز کے مطابق v2 سے v1 تک ڈیٹا جانے میں ٹائم لگتا ہے۔
    # Resource does not exist سے بچنے کے لیے یہاں 5 سیکنڈ رکیں گے۔
    print("⏳ Waiting 5s for server sync...")
    time.sleep(5)

    # ==========================
    # STEP 2: POLLING (GET)
    # ==========================
    status_url = GET_JOB_URL_TEMPLATE.format(job_id)
    print(f"🔎 [STEP 2] Polling: {status_url}")
    
    # GET Request کے ہیڈرز (لاگز میں Timezone نہیں تھا، اس لیے صرف Base Headers)
    get_headers = BASE_HEADERS.copy()
    
    for i in range(40): # 80 Seconds Max
        time.sleep(2)
        try:
            res = requests.get(status_url, headers=get_headers, timeout=15)
            
            if res.status_code != 200:
                print(f"   ⚠️ HTTP {res.status_code}")
                continue

            res_data = res.json()
            status_msg = res_data.get("message", {}).get("en", "Unknown")

            # اگر اب بھی Resource Not Found آئے
            if "Resource does not exist" in status_msg:
                print(f"   ⚠️ Job not ready yet (Syncing...). Waiting...")
                time.sleep(2) # مزید انتظار
                continue

            # Success Check
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
        
        url, status = process_single_attempt(image_bytes, filename)
        
        if status == "success":
            return {"status": "success", "url": url}
        
        elif status == "timeout":
            print("❌ Timeout! Server slow. Rotating Serial...")
            refresh_serial()
            time.sleep(2)
            continue 
            
        else:
            print("⚠️ Upload Error. Rotating Serial...")
            refresh_serial()
            time.sleep(2)
            continue

    raise HTTPException(status_code=408, detail="⚠️ Server is busy. Please try again later.")

@app.get("/")
def home():
    return {"message": "API Updated based on captured Logs (v2 Create -> v1 Get)"}

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
                
