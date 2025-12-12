import os
from fastapi import FastAPI, HTTPException, Query
import requests
import time
import uuid

app = FastAPI()

# --- Configuration ---
# ابتدائی ہیڈرز
HEADERS = {
    "product-serial": "08003f498d526aeaefaf015e6db91727",
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36",
    "Origin": "https://imgupscaler.ai",
    "Referer": "https://imgupscaler.ai/"
}

CREATE_JOB_URL = "https://api.imgupscaler.ai/api/image-upscaler/v2/upscale/create-job"
GET_JOB_URL_TEMPLATE = "https://api.imgupscaler.ai/api/image-upscaler/v1/universal_upscale/get-job/{}"

def refresh_serial():
    """نیا سیریل جنریٹ کر کے ہیڈرز میں سیٹ کرتا ہے"""
    new_serial = uuid.uuid4().hex
    HEADERS["product-serial"] = new_serial
    print(f"🔄 Serial Expired! Generated New: {new_serial}")

def get_enhanced_url(image_bytes: bytes, filename: str):
    print(f"Starting Process for: {filename}")
    
    job_id = None
    
    # --- RETRY LOOP (Auto Fix Logic) ---
    # ہم 5 بار کوشش کریں گے اگر لمٹ کا ایرر آئے
    for attempt in range(5):
        try:
            files = {
                "original_image_file": (filename, image_bytes, "image/jpeg")
            }
            
            # ریکویسٹ بھیجیں
            response = requests.post(CREATE_JOB_URL, headers=HEADERS, files=files)
            data = response.json()
            
            # --- CHECK RESPONSE CODE ---
            code = data.get("code")
            
            # Case 1: Success
            if code == 100000:
                job_id = data["result"]["job_id"]
                print(f"✅ Upload Success! Job ID: {job_id}")
                break # لوپ سے باہر نکل جائیں
            
            # Case 2: Limit Reached (300019) or Invalid Serial
            elif code == 300019 or code == 300006:
                print(f"⚠️ Limit Reached (Attempt {attempt+1}/5). Refreshing Serial...")
                refresh_serial() # نیا سیریل لگائیں
                time.sleep(1)    # ایک سیکنڈ سانس لیں
                continue         # دوبارہ لوپ چلائیں (Retry)
                
            # Case 3: Other Errors
            else:
                raise Exception(f"API Error: {data}")

        except Exception as e:
            print(f"Connection Error on attempt {attempt}: {e}")
            if attempt == 4: raise HTTPException(status_code=500, detail=str(e))

    if not job_id:
        raise HTTPException(status_code=500, detail="Failed to upload after multiple attempts.")

    # 2. Polling (Status Check)
    status_url = GET_JOB_URL_TEMPLATE.format(job_id)
    output_url = None
    
    for i in range(20): # 40 seconds max wait
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
        raise HTTPException(status_code=408, detail="Timeout processing image")

    return {"status": "success", "url": output_url}


@app.get("/")
def home():
    return {"message": "Smart API: Auto-rotates serial on limit errors."}

@app.get("/enhance")
def enhance_via_url(url: str = Query(..., description="Image URL")):
    try:
        # Link se image uthao
        img_response = requests.get(url)
        if img_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Could not fetch source image")
        
        # Process karo
        result = get_enhanced_url(img_response.content, "url_image.jpg")
        return result

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
        
