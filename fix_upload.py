import os

def fix_upload_endpoints():
    filepath = r"c:\Users\sachi\Downloads\giotag project\flask_app.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix upload_reference endpoint
    # Find the upload_reference function body
    old_ref = """@app.route('/upload_reference', methods=['POST'])
def upload_reference():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    file = request.files['file']"""

    new_ref = """@app.route('/upload_reference', methods=['POST'])
def upload_reference():
    file = request.files.get('video') or request.files.get('file')
    if not file:
        return jsonify({"success": False, "error": "No file uploaded"}), 400"""

    content = content.replace(old_ref, new_ref)

    # Fix the return JSON for upload_reference
    old_ret = """"settings": reference_settings"""
    new_ret = """"stats": reference_settings"""
    
    # We want to replace it inside the upload_reference block.
    # Actually just replacing `"settings": reference_settings` with `"stats": reference_settings` works.
    content = content.replace(old_ret, new_ret)

    # Fix upload endpoint just in case
    old_up = """@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    file = request.files['file']"""

    new_up = """@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('video') or request.files.get('file')
    if not file:
        return jsonify({"success": False, "error": "No file uploaded"}), 400"""

    content = content.replace(old_up, new_up)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

fix_upload_endpoints()
