import google.generativeai as genai
from app.config import settings

def test():
    genai.configure(api_key=settings.GEMINI_API_KEY)
    print("Available models:")
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(m.name)

if __name__ == "__main__":
    test()
