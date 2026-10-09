import os

def fix_upload_folder():
    filepath = r"c:\Users\sachi\Downloads\giotag project\flask_app.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # We need to replace `UPLOAD_FOLDER` with `app.config['UPLOAD_FOLDER']`
    # but ONLY in the function bodies we appended, not at the top.
    
    # Actually, the top already says `app.config['UPLOAD_FOLDER'] = 'uploads'`
    # so there is no `UPLOAD_FOLDER` global variable defined.
    # Therefore, replacing all occurrences of `UPLOAD_FOLDER` (that are isolated) 
    # with `app.config['UPLOAD_FOLDER']` is safe if we don't mess up existing ones.
    
    content = content.replace("UPLOAD_FOLDER,", "app.config['UPLOAD_FOLDER'],")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

fix_upload_folder()
