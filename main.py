import os
from fastapi import FastAPI, HTTPException, Query
import requests
import time
import uuid

app = FastAPI()

# --- Configuration ---
# ابتدائی ہیڈرز
HEADERS = {
    "product-serial": "08002f498d526aeaefaf015e6db91727",
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
    # یہ صرف آپ (ایڈمن) کو کنسول میں نظر آئے گا
    print(f"🔄 Serial Rotated! New: {new_serial}")

def get_enhanced_url(image_bytes: bytes, filename: str):
    print(f"Starting Process for: {filename}")
    
    job_id = None
    
    # --- RETRY LOOP ---
    # 5 بار کوشش کریں گے
    for attempt in range(5):
        try:
            files = {
                "original_image_file": (filename, image_bytes, "image/jpeg")
            }
            
            # API کو ریکویسٹ بھیجیں
            response = requests.post(CREATE_JOB_URL, headers=HEADERS, files=files)
            data = response.json()
            
            # --- CHECK RESPONSE CODE ---
            code = data.get("code")
            
            # Case 1: کامیابی (Success)
            if code == 100000:
                job_id = data["result"]["job_id"]
                print(f"✅ Upload Success! Job ID: {job_id}")
                break 
            
            # Case 2: کوئی بھی ایرر (Limit, Invalid Serial, etc.)
            else:
                # اوریجنل ایرر صرف کنسول میں پرنٹ کریں
                print(f"⚠️ Internal API Error (Attempt {attempt+1}): {data}")
                
                # فوراً سیریل چینج کریں اور دوبارہ ٹرائی کریں
                refresh_serial()
                time.sleep(1)
                continue

        except Exception as e:
            # نیٹ ورک ایرر کو بھی صرف کنسول میں دکھائیں
            print(f"❌ Connection/Network Error on attempt {attempt}: {e}")
            refresh_serial() # نیٹ ورک ایرر پر بھی سیریل بدل کر دیکھیں
            time.sleep(1)
            continue

    # اگر 5 کوششوں کے بعد بھی job_id نہ ملے
    if not job_id:
        # یوزر کو صرف یہ صاف ستھرا میسج جائے گا
        raise HTTPException(status_code=500, detail="⚠️ Server is currently busy. Please try again later.")

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
        # ٹائم آؤٹ کا بھی صاف میسج
        raise HTTPException(status_code=408, detail="⚠️ Processing timeout. Image is too large or server is slow.")

    return {"status": "success", "url": output_url}


@app.get("/")
def home():
    return {"message": "Secure API Running. Errors are hidden from user."}

@app.get("/enhance")
def enhance_via_url(url: str = Query(..., description="Image URL")):
    try:
        img_response = requests.get(url)
        if img_response.status_code != 200:
            # اگر لنک ہی خراب ہو
            return {"status": "error", "message": "Could not download image from the provided link."}
        
        result = get_enhanced_url(img_response.content, "url_image.jpg")
        return result

    except HTTPException as http_e:
        # ہمارا صاف ستھرا میسج واپس کریں
        return {"status": "error", "message": http_e.detail}
    except Exception as e:
        # کوئی اور انجانہ ایرر ہو تو اسے بھی چھپا لیں
        print(f"🔥 Critical Unknown Error: {e}")
        return {"status": "error", "message": "An unexpected error occurred. Please try again."}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
        
