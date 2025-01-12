from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import sqlite3

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Connect to SQLite database using sqlite3 with absolute path
conn = sqlite3.connect('app.db')  # Absolute path to the DB file
cursor = conn.cursor()

# SQL command to add the 'title' column to the 'file_metadata' table
alter_table_sql = """
ALTER TABLE file_metadata ADD COLUMN title TEXT;
"""

# Execute the ALTER TABLE command
try:
    cursor.execute(alter_table_sql)
    print("Column 'title' added successfully!")
except sqlite3.OperationalError as e:
    print(f"Error: {e}")

# Commit the changes and close the connection
conn.commit()
conn.close()

if __name__ == '__main__':
    app.run(debug=True)
