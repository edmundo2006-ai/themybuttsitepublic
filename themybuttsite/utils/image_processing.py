from flask import flash, current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename
from supabase import create_client
from io import BytesIO

def process_image_upload(image, name, default=None):
    if not image or not image.filename:
        return default
    try:
        img = Image.open(image)
        img.verify()
        image.seek(0)
    except UnidentifiedImageError:
        flash("Uploaded file is not a valid image.", "danger")
        return None
    except Exception as e:
        flash(f"Error verifying image: {str(e)}", "danger")
        return None

    # 2) Build key
    extension = (image.mimetype.split("/")[-1] or "").lower()
    if extension == "jpeg":
        extension = "jpg"
    filename = secure_filename((name or "image").replace(" ", "_").lower()) or "image"
    object_key = f"{filename}.{extension or 'jpg'}"

    # 3) Create client
    url = current_app.config["SUPABASE_URL"]
    key = current_app.config["SUPABASE_SERVICE_ROLE_KEY"]
    bucket = current_app.config.get("SUPABASE_BUCKET")
    supabase = create_client(url, key)

    # 4) Upload (file-like with a name; correct headers)
    try:
        image.seek(0)  # IMPORTANT: ensure we read real bytes
        data=image.read()
        res = supabase.storage.from_(bucket).upload(
            path=object_key,
            file=data,  # file-like, not raw bytes
            file_options={
                "content-type": image.mimetype,       # e.g. "image/jpeg"
                "cache-control": "max-age=86400",     # string, not bare number
                "upsert": "true",                    # string avoids header-type bug
            },
        )
        # v2 client typically returns dict-like; guard both patterns
        if isinstance(res, dict) and res.get("error"):
            flash(f"Upload error: {res['error'].get('message')}", "danger")
            return None
    except Exception as e:
        flash(f"Error uploading to Supabase: {str(e)}", "danger")
        return None

    return object_key
