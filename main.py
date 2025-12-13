import os
from fastapi import FastAPI, HTTPException, Query
import requests
import time
import uuid

app = FastAPI()

HEADERS = {
    "product-serial": "08003f498d526aeaefaf015e6db91727",
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36",
    "Origin": "https://imgupscaler.ai",
    "Referer": "https://imgupscaler.ai/"
}

CREATE_JOB_URL = "https://api.imgupscaler.ai/api/image-upscaler/v2/upscale/create-job"
GET_JOB_URL_TEMPLATE = "https://api.imgupscaler.ai/api/image-upscaler/v1/universal_upscale/get-job/{}"

def refresh_serial():
    new_serial = uuid.uuid4().hex
    HEADERS["product-serial"] = new_serial
    print(f"🔄 Switched to New Serial: {new_serial}")

def process_single_attempt(image_bytes: bytes, filename: str):
    job_id = None
    
    # --- STEP 1: UPLOAD ---
    try:
        files = {"original_image_file": (filename, image_bytes, "image/jpeg")}
        # Timeout بڑھا کر 60 سیکنڈ کر دیا ہے
        response = requests.post(CREATE_JOB_URL, headers=HEADERS, files=files, timeout=60)
        
        try:
            data = response.json()
        except:
            print(f"⚠️ Non-JSON Response: {response.text[:200]}")
            return None, "upload_failed"

        if data.get("code") == 100000:
            job_id = data["result"]["job_id"]
            print(f"✅ Uploaded. Job ID: {job_id}")
        else:
            # اصل ایرر پرنٹ کریں
            print(f"⚠️ API Error Response: {data}")
            return None, "upload_failed"

    except Exception as e:
        print(f"❌ Upload Connection Error: {e}")
        return None, "connection_error"

    # --- STEP 2: POLLING ---
    status_url = GET_JOB_URL_TEMPLATE.format(job_id)
    print("⏳ Polling started...")
    
    for i in range(30): # 60 Seconds Polling
        time.sleep(2)
        try:
            res = requests.get(status_url, headers=HEADERS, timeout=15)
            
            # اگر 404 یا 500 آئے
            if res.status_code != 200:
                print(f"   Status Code: {res.status_code} (Retrying...)")
                continue

            res_data = res.json()
            
            # ایرر میسج چیک کریں
            status_msg = res_data.get("message", {}).get("en", "Unknown")
            
            if "Resource does not exist" in status_msg:
                 # اگر یہ ایرر آئے تو تھوڑا لمبا انتظار کریں
                print(f"   ⚠️ Job Not Found (Syncing...). Waiting 3s...")
                time.sleep(3)
                continue
            
            print(f"   Status: {status_msg}")

            result = res_data.get("result", {})
            if result and "output_url" in result:
                raw_url = result["output_url"]
                final_url = raw_url[0] if isinstance(raw_url, list) else raw_url
                return final_url, "success"
                
        except Exception as e:
            print(f"   Polling Error: {e}")
            continue
            
    return None, "timeout"

def get_enhanced_url_with_retry(image_bytes: bytes, filename: str):
    print(f"Starting Smart Process for: {filename}")
    
    for attempt in range(3):
        print(f"\n🔹 Attempt {attempt + 1}/3")
        
        url, status = process_single_attempt(image_bytes, filename)
        
        if status == "success":
            return {"status": "success", "url": url}
        
        elif status == "timeout":
            print("❌ Timeout! Server stuck. Rotating Serial & Retrying...")
            refresh_serial()
            time.sleep(2)
            continue 
            
        else:
            print("⚠️ Upload failed. Rotating Serial & Retrying...")
            refresh_serial()
            time.sleep(2)
            continue

    raise HTTPException(status_code=408, detail="⚠️ Server is busy. Tried 3 times but failed.")

@app.get("/")
def home():
    return {"message": "API v2: Improved Error Logging & Timeout."}

@app.get("/enhance")
def enhance_via_url(url: str = Query(..., description="Image URL")):
    try:
        print(f"📥 Downloading Telegram Image...")
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
