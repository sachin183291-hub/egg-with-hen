import os
import sys
import glob

sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.ai.llm_authenticity_checker import check_image_authenticity

latest_file = max(glob.glob('backend/uploads/evidence/*.jpg'), key=os.path.getctime)
print('Latest file:', latest_file)

with open(latest_file, 'rb') as f:
    result = check_image_authenticity(f.read())
    print(result)
