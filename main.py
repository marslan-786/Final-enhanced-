import os
from fastapi import FastAPI, HTTPException, Query
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

def get_enhanced_url(image_bytes: bytes, filename: str):
    print(f"Starting Process for: {filename}")
    
    # 1. Upload Image
    try:
        files = {
            "original_image_file": (filename, image_bytes, "image/jpeg")
        }
        response = requests.post(CREATE_JOB_URL, headers=HEADERS, files=files)
        data = response.json()
        
        if response.status_code != 200 or "code" not in data or data["code"] != 100000:
            raise Exception(f"Upload Failed: {data}")
            
        job_id = data["result"]["job_id"]
        print(f"Job ID Created: {job_id}")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 2. Polling
    status_url = GET_JOB_URL_TEMPLATE.format(job_id)
    output_url = None
    
    for i in range(20): # 40 seconds max
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

    # --- CHANGE IS HERE ---
    # تصویر ڈاؤن لوڈ نہیں کر رہے، صرف لنک واپس کر رہے ہیں
    return {"status": "success", "url": output_url}


@app.get("/")
def home():
    return {"message": "API returns JSON URL now."}

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
    
