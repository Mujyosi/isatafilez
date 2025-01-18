import io
import boto3
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, redirect, send_file, url_for, session, abort, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sitemap import Sitemap
import os
import uuid
from moviepy.video.io.VideoFileClip import VideoFileClip
from flask_migrate import Migrate
from b2sdk.v2 import B2Api, InMemoryAccountInfo
from botocore.exceptions import NoCredentialsError
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash
import psycopg2
import requests
import logging


app = Flask(__name__)

ext = Sitemap(app=app)
# Enable CORS
CORS(app, resources={r"/*": {"origins": ["http://localhost:5000", "https://isatafilez.vercel.app"]}})

# Set up configuration

app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 * 1024  # 1GB file size limit
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres.ksycadyzsegdpplnsgmd:Adobewindows11!@aws-0-eu-west-2.pooler.supabase.com:5432/postgres'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key'  # Required for session management

# Initialize SQLAlchemy and LoginManager
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"  # Redirect to login page if not logged in

load_dotenv()
migrate = Migrate(app, db)

DATABASE_URL = os.getenv("DATABASE_URL")


logging.basicConfig(level=logging.DEBUG)

app.config['B2_ACCOUNT_ID'] = 'sabrine222018047@gmail.com'  # Replace with your Account ID
app.config['B2_APP_KEY'] = '0d66b6394052'  # Replace with your Application Key
app.config['B2_BUCKET_NAME'] = 'mujyosi'  # Replace with your Bucket Name
# Cloudflare R2 Configuration
app.config['R2_ACCESS_KEY'] = '67b76687e1c34e888f88ae7ca6ce5d2b'
app.config['R2_SECRET_KEY'] = '1dad122b4bc2c6336bcd72a38d75aec0cb362258786ab8c5a815ecd8917fbf6d'
app.config['R2_ENDPOINT'] = 'https://0a6fe2e89e28392240be7823ce09051f.r2.cloudflarestorage.com'
app.config['R2_BUCKET_NAME'] = 'isata'  # Update this if you specified a different bucket name


serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])



# User model for Flask-Login
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)

# FileMetadata model
class FileMetadata(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unique_name = db.Column(db.String(256), nullable=False, unique=True)
    original_name = db.Column(db.String(256), nullable=False)
    is_compressed = db.Column(db.Boolean, default=False)
    file_path = db.Column(db.String(256), nullable=False)
    def __repr__(self):
        return f"<File {self.original_name}>"

# Initialize the R2 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=app.config['R2_ACCESS_KEY'],
    aws_secret_access_key=app.config['R2_SECRET_KEY'],
    endpoint_url=app.config['R2_ENDPOINT']
)



# Initialize Backblaze B2
def get_b2_api():
    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account("production", app.config['B2_ACCOUNT_ID'], app.config['B2_APP_KEY'])
    return b2_api

# Load user for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def compress_video(input_path, output_path, max_width=1280):
    try:
        with VideoFileClip(input_path) as video:
            if video.size[0] > max_width:
                video = video.resize(width=max_width)
            video.write_videofile(output_path, codec='libx264', audio_codec='aac')
    except Exception as e:
        print(f"Error compressing video: {e}")
        raise


@app.route('/create_user')
def create_user():
    # Create a new user
    username = 'Mujyosi'
    password = 'Adobewindows1!'

    # Check if the username already exists
    existing_user = User.query.filter_by(username=username).first()

    if existing_user:
        return f"Username '{username}' already exists."
    else:
        # Hash the password before saving it
        hashed_password = generate_password_hash(password, method='sha256')

        # Create new user with hashed password
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return "User created successfully"

@app.route('/')
@login_required
@ext.register_generator
def index():
    return render_template('index.html')




@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"})

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})

    # Use 'isata' as the default folder if none is provided
    folder_name = request.form.get('folder_name', 'isata')
    file_ext = file.filename.split('.')[-1]
    unique_id = uuid.uuid4().hex  # Generate a unique ID
    unique_name = f"{folder_name}/{unique_id}.{file_ext}"  # Create a path like 'isata/<unique_id>.extension'

    # Define chunk size (e.g., 1 MB)
    chunk_size = 50 * 1024 * 1024  # 50 MB per chunk

    upload_id = None  # Initialize upload_id

    try:
        # Start the multipart upload
        upload_id = s3_client.create_multipart_upload(
            Bucket=app.config['R2_BUCKET_NAME'],  # Accessing the bucket name from config
            Key=unique_name,
            ContentType=file.content_type
        )['UploadId']

        # Upload file in chunks
        part_number = 1
        parts = []

        # Read and upload in chunks
        while chunk := file.stream.read(chunk_size):
            part = s3_client.upload_part(
                Bucket=app.config['R2_BUCKET_NAME'],  # Accessing the bucket name from config
                Key=unique_name,
                PartNumber=part_number,
                UploadId=upload_id,
                Body=chunk
            )
            parts.append({'PartNumber': part_number, 'ETag': part['ETag']})
            part_number += 1

        # Complete the multipart upload
        s3_client.complete_multipart_upload(
            Bucket=app.config['R2_BUCKET_NAME'],  # Accessing the bucket name from config
            Key=unique_name,
            UploadId=upload_id,
            MultipartUpload={'Parts': parts}
        )

        # Save metadata to the database
        metadata = FileMetadata(
            unique_name=unique_id,
            original_name=file.filename,
            is_compressed=False,
            file_path=unique_name
        )
        db.session.add(metadata)
        db.session.commit()

        # Construct the file URL
        file_url = f"https://pub-8ddd7050ab164d438f6ef03254ee053d.r2.dev/{unique_name}"

        # Generate a secure URL
        secure_url = url_for('file_link', unique_id=unique_id, _external=True)

        return jsonify({"success": True, "file_url": file_url, "secure_url": secure_url})

    except Exception as e:
        if upload_id:
            # If something goes wrong, abort the multipart upload
            s3_client.abort_multipart_upload(
                Bucket=app.config['R2_BUCKET_NAME'],  # Accessing the bucket name from config
                Key=unique_name,
                UploadId=upload_id
            )
        return jsonify({"success": False, "error": str(e)})


@app.route('/access/<unique_id>')
def access_file(unique_id):
    metadata = FileMetadata.query.filter_by(unique_name=unique_id).first()
    if not metadata:
        return jsonify({"success": False, "error": "File not found"}), 404

    file_url = f"https://pub-8ddd7050ab164d438f6ef03254ee053d.r2.dev/{metadata.file_path}"
    return redirect(file_url)

@app.route('/file/<unique_id>')
@ext.register_generator
def file_link(unique_id):
    # Retrieve metadata for the file based on the unique ID
    metadata = FileMetadata.query.filter_by(unique_name=unique_id).first()
    if not metadata:
        abort(404)

    # Construct the file URL using the metadata's file path
    cloudflare_base_url = "https://pub-8ddd7050ab164d438f6ef03254ee053d.r2.dev/"
    file_url = f"{cloudflare_base_url}{metadata.file_path}"
    is_video = file_url.endswith(('.mp4', '.webm', '.ogg'))

    # Render the file link page with the secure link and preview
    return render_template('file_link.html', file_url=file_url, is_video=is_video, unique_id=unique_id)



@app.route('/download/<unique_id>')
def download_file(unique_id):
    # Retrieve metadata for the file based on the unique ID
    metadata = FileMetadata.query.filter_by(unique_name=unique_id).first()

    if not metadata:
        abort(404, description="File not found")

    # Construct the file path (same as the file URL, but for R2)
    file_path = metadata.file_path

    try:
        # Fetch the file from R2 using boto3
        file_content = io.BytesIO()
        s3_client.download_fileobj(
            app.config['R2_BUCKET_NAME'],  # Your R2 bucket name
            file_path,  # The file's path in R2
            file_content  # The object to store the file content in memory
        )
        file_content.seek(0)  # Ensure we are reading from the start of the file

        # Send the file as a response for download
        return send_file(
            file_content,
            as_attachment=True,
            download_name=metadata.original_name,
            mimetype="application/octet-stream"  # Adjust the MIME type as necessary
        )
    except NoCredentialsError:
        abort(500, description="Internal Server Error: No valid credentials for R2.")
    except Exception:
        abort(500, description="Internal Server Error while retrieving file.")


# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and user.password == password:  # Ideally, use hashed passwords
            login_user(user)
            # Redirect to the page that the user originally tried to access
            next_page = request.args.get('next')  # Get the next page from the URL (if any)
            return redirect(next_page or url_for('index'))  # Default to index if no next page

        return 'Invalid credentials', 401

    return render_template('login.html')

# Logout route
@app.route('/logout')
@login_required  # Ensure only logged-in users can log out
def logout():
    logout_user()
    return redirect(url_for('login'))



# Routes
@app.route('/my_files')
@login_required
def my_files():
    try:
        # Fetch unique folder paths from the metadata
        folder_paths = set(
            file.unique_name.split('/')[0] if '/' in file.unique_name else 'Root'
            for file in FileMetadata.query.all()
        )
        app.logger.info(f"Extracted folder paths: {folder_paths}")

        # Group files by folder
        files_by_folder = {
            folder: FileMetadata.query.filter(FileMetadata.unique_name.like(f"{folder}/%")).all()
            for folder in folder_paths
        }

        return render_template('my_files.html', files_by_folder=files_by_folder)
    except Exception as e:
        app.logger.error(f"Error fetching files: {e}")
        return jsonify({"success": False, "error": "Failed to fetch files"}), 500


@app.route('/delete_file/<unique_id>', methods=['POST'])
@login_required
def delete_file(unique_id):
    app.logger.info(f"Attempting to delete file with unique_id: {unique_id.strip()}")

    try:
        # Find the file metadata in the database
        metadata = FileMetadata.query.filter_by(unique_name=unique_id.strip()).first()

        if not metadata:
            app.logger.error(f"No file found for unique_id: {unique_id}")
            return jsonify({"success": False, "error": "File not found"}), 404

        file_key = metadata.file_path  # Use the actual file path

        # Delete the file from Cloudflare R2
        s3_client.delete_object(Bucket=app.config['R2_BUCKET_NAME'], Key=file_key)

        # Remove metadata from the database
        db.session.delete(metadata)
        db.session.commit()

        app.logger.info(f"Successfully deleted file: {unique_id}")
        return jsonify({"success": True, "message": "File deleted successfully"}), 200

    except Exception as e:
        app.logger.error(f"Error deleting file: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/privacy-policy')
@ext.register_generator 
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/terms-of-service')
@ext.register_generator 
def terms_of_service():
    return render_template('terms_of_service.html')

@app.route('/sitemap.xml')
def sitemap():
    # Generate or read your sitemap content
    sitemap_content = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url>
            <loc>https://isatafilez.onrender.com/</loc>
            <lastmod>2025-01-17</lastmod>
            <changefreq>daily</changefreq>
            <priority>1.0</priority>
        </url>
        <!-- Add more URLs here -->
    </urlset>"""
    
    return Response(sitemap_content, content_type='application/xml')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
