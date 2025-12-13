import os
from fastapi import FastAPI, HTTPException, Query
import requests
import time
import uuid

app = FastAPI()

# --- CONFIGURATION ---
HEADERS = {
    "product-serial": "08003f498d526aeaefaf015e6db91727",
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36",
    "Origin": "https://imgupscaler.ai",
    "Referer": "https://imgupscaler.ai/"
}

# --- FIX IS HERE (Endpoints Updated) ---
# Create Job (v2)
CREATE_JOB_URL = "https://api.imgupscaler.ai/api/image-upscaler/v2/upscale/create-job"
# Get Job (Updated to v2 to match Create Job)
GET_JOB_URL_TEMPLATE = "https://api.imgupscaler.ai/api/image-upscaler/v2/upscale/get-job/{}"

def refresh_serial():
    new_serial = uuid.uuid4().hex
    HEADERS["product-serial"] = new_serial
    print(f"🔄 SERIAL CHANGED: {new_serial}")

def process_single_attempt(image_bytes: bytes, filename: str):
    job_id = None
    
    # ==========================
    # STEP 1: UPLOAD REQUEST
    # ==========================
    try:
        print(f"\n🚀 [STEP 1] Uploading Image...")
        files = {"original_image_file": (filename, image_bytes, "image/jpeg")}
        
        # API Call
        response = requests.post(CREATE_JOB_URL, headers=HEADERS, files=files, timeout=60)
        print(f"📥 [UPLOAD RESPONSE]: {response.text}") 

        try:
            data = response.json()
        except:
            print("❌ Error: Response is not JSON!")
            return None, "upload_failed"

        # Check Code
        if data.get("code") == 100000:
            job_id = data["result"]["job_id"]
            print(f"✅ Job ID Generated: {job_id}")
            
            # کبھی کبھی v2 ریسپانس میں ہی URL دے دیتا ہے، اگر ہو تو وہیں سے اٹھا لیں
            if "output_url" in data["result"]:
                 raw_url = data["result"]["output_url"]
                 if raw_url:
                     final_url = raw_url[0] if isinstance(raw_url, list) else raw_url
                     # لیکن احتیاطاً پولنگ کریں گے تاکہ یقین ہو جائے تصویر تیار ہے
                     # اگر آپ چاہیں تو یہاں فوراً return کر سکتے ہیں، لیکن پولنگ محفوظ ہے
                     pass 

        else:
            print(f"⚠️ Upload Failed Logic: Code is {data.get('code')}")
            return None, "upload_failed"

    except Exception as e:
        print(f"❌ Upload Exception: {e}")
        return None, "connection_error"

    # ==========================
    # STEP 2: POLLING STATUS
    # ==========================
    status_url = GET_JOB_URL_TEMPLATE.format(job_id)
    print(f"\n⏳ [STEP 2] Starting Polling for Job: {job_id}")
    
    # 40 بار چیک کریں گے (ہر 2 سیکنڈ بعد) - Total 80 Secs
    for i in range(40): 
        time.sleep(2)
        try:
            res = requests.get(status_url, headers=HEADERS, timeout=15)
            
            # --- PRINT RAW POLLING RESPONSE ---
            # یہ بہت زیادہ لاگز بھر دے گا، اگر چاہیں تو کمنٹ کر دیں
            # print(f"🔎 [POLL #{i+1}] Response: {res.text}") 

            if res.status_code != 200:
                print(f"   ⚠️ HTTP Error: {res.status_code}")
                continue

            res_data = res.json()
            
            # Message check
            status_msg = res_data.get("message", {}).get("en", "Unknown")
            
            # اگر اب بھی Resource not exist آئے (جو کہ v2 میں نہیں آنا چاہیے)
            if "Resource does not exist" in status_msg:
                print(f"   ⚠️ Resource not found (Poll #{i+1}). Waiting...")
                time.sleep(1)
                continue

            # Result Check
            result = res_data.get("result", {})
            
            # v2 میں status چیک کریں
            job_status = result.get("status")
            if job_status == "done" and "output_url" in result:
                raw_url = result["output_url"]
                final_url = raw_url[0] if isinstance(raw_url, list) else raw_url
                print(f"🎉 [SUCCESS] Final URL: {final_url}")
                return final_url, "success"
            else:
                print(f"   ⏳ Processing... Status: {job_status}")
                
        except Exception as e:
            print(f"   ❌ Polling Exception: {e}")
            continue
            
    return None, "timeout"

def get_enhanced_url_with_retry(image_bytes: bytes, filename: str):
    print(f"--- NEW REQUEST STARTED FOR: {filename} ---")
    
    for attempt in range(3):
        print(f"\n🔹 --- ATTEMPT {attempt + 1}/3 ---")
        
        url, status = process_single_attempt(image_bytes, filename)
        
        if status == "success":
            return {"status": "success", "url": url}
        
        elif status == "timeout":
            print("❌ Attempt Failed: Timeout! Rotating Serial...")
            refresh_serial()
            time.sleep(2)
            continue 
            
        else:
            print("⚠️ Attempt Failed: Upload Error. Rotating Serial...")
            refresh_serial()
            time.sleep(2)
            continue

    raise HTTPException(status_code=408, detail="⚠️ Server is busy. Please try again later.")

@app.get("/")
def home():
    return {"message": "API Fixed: v2 Endpoints Synced."}

@app.get("/enhance")
def enhance_via_url(url: str = Query(..., description="Image URL")):
    try:
        print(f"\n📥 [TELEGRAM] Downloading Image from URL...")
        img_response = requests.get(url, timeout=45)
        
        if img_response.status_code != 200:
            print(f"❌ Telegram Download Failed: {img_response.status_code}")
            raise HTTPException(status_code=400, detail="Telegram Download Failed")
        
        print(f"✅ Downloaded {len(img_response.content)} bytes.")
        
        result = get_enhanced_url_with_retry(img_response.content, "url_image.jpg")
        return result

    except HTTPException as http_e:
        return {"status": "error", "message": http_e.detail}
    except Exception as e:
        return {"status": "error", "message": "Unexpected Server Error"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
    
