
@app.route('/upload', methods=['POST'])
@login_required
@ext.register_generator
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"})

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})

    # Use 'isata' as the default folder if none is provided
    folder_name = request.form.get('folder_name', 'isata')  # Default folder name 'isata'
    file_ext = file.filename.split('.')[-1]
    unique_id = uuid.uuid4().hex  # Generate a unique ID
    unique_name = f"{folder_name}/{unique_id}.{file_ext}"  # Create a path like 'isata/<unique_id>.extension'

    try:
        # Upload the file to Cloudflare R2
        s3_client.upload_fileobj(
            file,
            app.config['R2_BUCKET_NAME'],
            unique_name,
            ExtraArgs={'ContentType': file.content_type}
        )

        # Save metadata to the database
        metadata = FileMetadata(
            unique_name=unique_id,
            original_name=file.filename,
            is_compressed=False,
            file_path=unique_name  # Store the folder and file path
        )
        db.session.add(metadata)
        db.session.commit()

        # Construct the file URL with the proper format
        file_url = f"https://pub-8ddd7050ab164d438f6ef03254ee053d.r2.dev/{unique_name}"

        # Generate secure link
        secure_url = url_for('file_link', unique_id=unique_id, _external=True)
        return jsonify({"success": True, "file_url": file_url, "secure_url": secure_url})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
