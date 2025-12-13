import os
from fastapi import FastAPI, HTTPException, Query
import requests
import time
import uuid

app = FastAPI()

# --- Configuration ---
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
    print(f"🔄 Serial Rotated! New: {new_serial}")

def get_enhanced_url(image_bytes: bytes, filename: str):
    print(f"Starting Process for: {filename}")
    
    job_id = None
    
    # --- RETRY LOOP ---
    for attempt in range(5):
        try:
            files = {
                "original_image_file": (filename, image_bytes, "image/jpeg")
            }
            
            response = requests.post(CREATE_JOB_URL, headers=HEADERS, files=files)
            data = response.json()
            code = data.get("code")
            
            if code == 100000:
                job_id = data["result"]["job_id"]
                print(f"✅ Upload Success! Job ID: {job_id}")
                break 
            
            else:
                print(f"⚠️ Internal API Error (Attempt {attempt+1}): {data}")
                refresh_serial()
                time.sleep(1)
                continue

        except Exception as e:
            print(f"❌ Network Error on attempt {attempt}: {e}")
            refresh_serial()
            time.sleep(1)
            continue

    if not job_id:
        raise HTTPException(status_code=500, detail="⚠️ Server is busy (Upload Failed). Please try again.")

    # 2. Polling (Status Check)
    status_url = GET_JOB_URL_TEMPLATE.format(job_id)
    output_url = None
    
    # --- CHANGE IS HERE (Fixing Timeout) ---
    # پہلے range(20) تھا (40 سیکنڈ)، اب range(60) ہے (120 سیکنڈ / 2 منٹ)
    print("⏳ Waiting for processing...")
    for i in range(60): 
        time.sleep(2) 
        try:
            res = requests.get(status_url, headers=HEADERS)
            res_data = res.json()
            result = res_data.get("result", {})
            
            if result and "output_url" in result:
                raw_url = result["output_url"]
                if isinstance(raw_url, list):
                    output_url = raw_url[0]
                else:
                    output_url = raw_url
                break
        except:
            continue
            
    if not output_url:
        print(f"❌ Timeout for Job ID: {job_id}")
        raise HTTPException(status_code=408, detail="⚠️ Processing timeout. Image is too large or server is slow.")

    return {"status": "success", "url": output_url}


@app.get("/")
def home():
    return {"message": "API Running with Extended Timeout (120s)."}

@app.get("/enhance")
def enhance_via_url(url: str = Query(..., description="Image URL")):
    try:
        print(f"📥 Downloading from Telegram URL: {url}")
        
        # ٹیلیگرام سے ڈاؤن لوڈنگ کے لیے ٹائم آؤٹ بڑھایا گیا ہے
        img_response = requests.get(url, timeout=30)
        
        if img_response.status_code != 200:
            print(f"❌ Failed to download from Telegram. Status: {img_response.status_code}")
            raise HTTPException(status_code=400, detail="Could not download image from the provided link.")
        
        print(f"✅ Downloaded {len(img_response.content)} bytes.")
        
        result = get_enhanced_url(img_response.content, "url_image.jpg")
        return result

    except HTTPException as http_e:
        return {"status": "error", "message": http_e.detail}
    except Exception as e:
        print(f"🔥 Critical Unknown Error: {e}")
        return {"status": "error", "message": "An unexpected error occurred."}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
    
