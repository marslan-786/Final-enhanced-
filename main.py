import os
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import Response
import requests
import time

app = FastAPI()

# --- Configuration ---
HEADERS = {
    "product-serial": "08002f498d526aeaefaf015e6db91727",
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36",
    "Origin": "https://imgupscaler.ai",
    "Referer": "https://imgupscaler.ai/"
}

CREATE_JOB_URL = "https://api.imgupscaler.ai/api/image-upscaler/v2/upscale/create-job"
GET_JOB_URL_TEMPLATE = "https://api.imgupscaler.ai/api/image-upscaler/v1/universal_upscale/get-job/{}"

def process_image_task(image_bytes: bytes, filename: str):
    """
    یہ فنکشن اپ لوڈ، انتظار اور ڈاؤن لوڈ کا سارا کام کرتا ہے۔
    """
    print(f"Starting Process for: {filename}")
    
    # 1. Upload Image
    try:
        files = {
            "original_image_file": (filename, image_bytes, "image/jpeg")
        }
        response = requests.post(CREATE_JOB_URL, headers=HEADERS, files=files)
        data = response.json()
        
        if response.status_code != 200 or "code" not in data or data["code"] != 100000:
            print(f"Upload Failed: {data}")
            raise Exception("Image Upload Failed on Server")
            
        job_id = data["result"]["job_id"]
        print(f"Job ID Created: {job_id}")
        
    except Exception as e:
        print(f"Error in Step 1: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
                
                # List Fix: اگر لنک لسٹ میں ہے تو اسے سٹرنگ بنائیں
                if isinstance(raw_url, list):
                    output_url = raw_url[0]
                else:
                    output_url = raw_url
                
                break
                
        except Exception as e:
            print(f"Polling Error: {e}")
            continue
            
    if not output_url:
        raise HTTPException(status_code=408, detail="Timeout: Image processing took too long.")

    print(f"Image Ready! Downloading from: {output_url}")

    # 3. Download Final Image
    final_image_response = requests.get(output_url)
    return final_image_response.content


# ================= API ENDPOINTS =================

@app.get("/")
def home():
    return {"status": "Active", "message": "Use /enhance endpoint for both URL and File upload"}

# --- METHOD 1: GET Request (URL) ---
# استعمال: /enhance?url=https://image.com/pic.jpg
@app.get("/enhance")
def enhance_via_url(url: str = Query(..., description="Image URL")):
    try:
        print(f"Processing URL: {url}")
        
        # URL سے تصویر ڈاؤن لوڈ کریں
        img_response = requests.get(url)
        if img_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Could not download image from URL")
        
        # پروسیسنگ فنکشن کو کال کریں
        processed_image = process_image_task(img_response.content, "url_image.jpg")
        
        # تصویر واپس بھیجیں
        return Response(content=processed_image, media_type="image/jpeg")

    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- METHOD 2: POST Request (File Upload) ---
# استعمال: Body -> form-data -> Key: file
@app.post("/enhance")
async def enhance_via_file(file: UploadFile = File(...)):
    try:
        # فائل ریڈ کریں
        image_bytes = await file.read()
        
        # پروسیسنگ فنکشن کو کال کریں
        processed_image = process_image_task(image_bytes, file.filename)
        
        # تصویر واپس بھیجیں
        return Response(content=processed_image, media_type="image/jpeg")

    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    # Railway کا پورٹ اٹھانے کے لیے
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
    
