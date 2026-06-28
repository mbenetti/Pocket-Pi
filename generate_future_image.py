import os
import json
import base64
import requests

def fetch_ai_artwork():
    prompt = (
        "A futuristic, highly detailed abstract vector graphic of a glowing neon green-to-cyan "
        "pi symbol (π) emerging elegantly from a dark, glowing high-tech digital grid pocket. "
        "The background is a rich dark space black with subtle radial gridlines, circuit board traces, "
        "floating particle orbits, and cybernetic flows. Ultra-high definition, cinematic lighting, "
        "glowing volumetric aura, sleek and professional."
    )
    filename = "README_banner.png"
    
    print("📡 Initializing AI Image Generation...")
    
    # 1. Try Google Gemini (Imagen 3) if key is present
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if gemini_key:
        print("🤖 Attempting Google Imagen 3...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:generateImages?key={gemini_key}"
        payload = {
            "prompt": prompt,
            "numberOfImages": 1,
            "outputMimeType": "image/png",
            "aspectRatio": "16:9" # Perfect landscape!
        }
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                b64 = data["generatedImages"][0]["image"]["imageBytes"]
                with open(filename, "wb") as f:
                    f.write(base64.b64decode(b64))
                print("🎉 Success! Generated via Google Imagen 3.")
                return True
        except Exception as e:
            print(f"Gemini API error: {e}")
            
    # 2. Try OpenAI (DALL-E 3) if key is present
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        print("🤖 Attempting OpenAI DALL-E 3...")
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_key}"
        }
        payload = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024" # Square is also great
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                img_url = res.json()["data"][0]["url"]
                img_data = requests.get(img_url, timeout=15).content
                with open(filename, "wb") as f:
                    f.write(img_data)
                print("🎉 Success! Generated via OpenAI DALL-E 3.")
                return True
        except Exception as e:
            print(f"OpenAI API error: {e}")
            
    print("❌ Notice: No active GEMINI_API_KEY or OPENAI_API_KEY found. Keeping current procedural POCKET-π vector banner.")
    return False

if __name__ == "__main__":
    fetch_ai_artwork()
