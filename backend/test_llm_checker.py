from app.ai.llm_authenticity_checker import check_image_authenticity
import glob

def test():
    files = glob.glob("c:\\Users\\sachi\\Downloads\\giotag project\\backend\\uploads\\evidence\\*.jpg")
    if not files:
        print("No files found")
        return
        
    for f in files[:2]:
        with open(f, "rb") as img_file:
            img = img_file.read()
        res = check_image_authenticity(img)
        print(f"File: {f}")
        print(f"Result: {res}")

if __name__ == "__main__":
    test()
