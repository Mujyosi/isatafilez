from flask import Flask, render_template, request, redirect, url_for, session, abort, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import uuid
from moviepy.video.io.VideoFileClip import VideoFileClip
from flask_migrate import Migrate
from b2sdk.v2 import B2Api, InMemoryAccountInfo

app = Flask(__name__)

# Set up configuration
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['COMPRESSED_FOLDER'] = 'static/compressed'
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 * 1024  # 1GB file size limit
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key'  # Required for session management

# Initialize SQLAlchemy and LoginManager
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"  # Redirect to login page if not logged in

# Ensure the folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['COMPRESSED_FOLDER'], exist_ok=True)

app.config['B2_ACCOUNT_ID'] = 'sabrine222018047@gmail.com'  # Replace with your Account ID
app.config['B2_APP_KEY'] = '0d66b6394052'  # Replace with your Application Key
app.config['B2_BUCKET_NAME'] = 'mujyosi'  # Replace with your Bucket Name


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

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
@login_required  # Ensure only logged-in users can upload
def upload_file():
    if 'file' not in request.files:
        return "No file uploaded", 400

    file = request.files['file']
    if file.filename == '':
        return "No file selected", 400

    # Get folder name and title from the form
    folder_name = request.form.get('folder_name', 'default_folder')  # Get folder name or default

    
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
    
    # Create the folder if it doesn't exist
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    file_ext = file.filename.split('.')[-1]
    unique_name = f"{uuid.uuid4().hex}.{file_ext}"
    file_path = os.path.join(folder_path, unique_name)
    file.save(file_path)

    compressed_path = None
    is_compressed = False

    if file_ext in ['mp4', 'webm', 'ogg'] and os.path.getsize(file_path) > 100 * 1024 * 1024:
        compressed_name = f"compressed_{unique_name}"
        compressed_path = os.path.join(app.config['COMPRESSED_FOLDER'], compressed_name)
        compress_video(file_path, compressed_path)
        is_compressed = True

    final_path = compressed_path if is_compressed else file_path

    # Save file metadata in the database with the title
    metadata = FileMetadata(
        unique_name=unique_name,
        original_name=file.filename,
        is_compressed=is_compressed,
        file_path=final_path
    )
    db.session.add(metadata)
    db.session.commit()

    return redirect(url_for('file_link', unique_id=unique_name))



@app.route('/file/<unique_id>')
def file_link(unique_id):
    metadata = FileMetadata.query.filter_by(unique_name=unique_id).first()
    if not metadata:
        abort(404)

    file_url = metadata.file_path.replace('static/', '/static/')
    file_ext = metadata.file_path.split('.')[-1]

    is_video = file_ext in ['mp4', 'webm', 'ogg']
    return render_template('file_link.html', file_url=file_url, is_video=is_video, unique_id=unique_id)

@app.route('/download/<unique_id>')
def download_file(unique_id):
    metadata = FileMetadata.query.filter_by(unique_name=unique_id).first()
    if not metadata:
        abort(404)

    folder, filename = os.path.split(metadata.file_path)
    return send_from_directory(folder, filename, as_attachment=True)

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
        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        return "User created successfully"



@app.route('/my_files')
@login_required  # Ensure only logged-in users can view their files
def my_files():
    # Fetch files based on their folders
    folder_paths = set(os.path.dirname(file.file_path) for file in FileMetadata.query.all())
    
    # Fetch all file metadata from the database
    files_by_folder = {}
    for folder_path in folder_paths:
        files_by_folder[folder_path] = FileMetadata.query.filter(FileMetadata.file_path.like(f'{folder_path}%')).all()

    return render_template('my_files.html', files_by_folder=files_by_folder)

@app.route('/delete_file/<unique_id>', methods=['POST'])
@login_required  # Ensure only logged-in users can delete files
def delete_file(unique_id):
    # Find the file metadata from the database
    metadata = FileMetadata.query.filter_by(unique_name=unique_id).first()

    if not metadata:
        return "File not found", 404

    # Get the file path and delete the file from the server
    file_path = metadata.file_path
    if os.path.exists(file_path):
        os.remove(file_path)  # Delete the file from the server

    # Delete the file metadata from the database
    db.session.delete(metadata)
    db.session.commit()

    # Redirect to the file listing page
    return redirect(url_for('my_files'))




if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("Database tables created")
    app.run(debug=True, port=5001)
