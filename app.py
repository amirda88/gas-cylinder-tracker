import os
from datetime import datetime

# Third-party libraries
from flask import Flask, render_template, request, redirect, session, url_for, Response, send_file
from flask_sqlalchemy import SQLAlchemy
import barcode
from barcode.writer import ImageWriter
import qrcode
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
from sqlalchemy import func
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'supersecret123'

# PostgreSQL database setup (Render)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://admin:IogWBRVd24QjJQZR9dfAf4cqWC5QbXX8@dpg-d09aan49c44c73dc7e1g-a.oregon-postgres.render.com/cylinders'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Define models
class Cylinder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cylinder_type = db.Column(db.String(100))
    gas_type = db.Column(db.String(100))
    size = db.Column(db.String(50))
    status = db.Column(db.String(10))
    barcode = db.Column(db.String(50), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime)

class StatusHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cylinder_id = db.Column(db.Integer, db.ForeignKey('cylinder.id'))
    old_status = db.Column(db.String(10))
    new_status = db.Column(db.String(10))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class MovementLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cylinder_id = db.Column(db.Integer, db.ForeignKey('cylinder.id'))
    action = db.Column(db.String(10))
    note = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    permissions = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def has_permission(permission_name):
    return permission_name in session.get('permissions', [])

@app.route('/users')
def view_users():
    if not session.get('logged_in'):
        return redirect('/login')
    if session.get('role') != 'admin':
        return "⛔ You don't have access to view users.", 403
    users = User.query.all()
    return render_template('users.html', users=users)

@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return redirect('/login')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        permissions = request.form['permissions']
        new_user = User(username=username, password=password, role=role, permissions=permissions)
        db.session.add(new_user)
        db.session.commit()
        return redirect('/users')
    return render_template('add_user.html')

@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if not session.get('logged_in'):
        return redirect('/login')
    if session.get('role') != 'admin':
        return "⛔ You don't have access to edit users.", 403
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.role = request.form['role']
        user.permissions = request.form['permissions']
        db.session.commit()
        return redirect('/users')
    return render_template('edit_user.html', user=user)

@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    if not session.get('logged_in') or session.get('role') != 'admin':
        return redirect('/login')
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return redirect('/users')

@app.route('/')
def home():
    if not session.get('logged_in'):
        return redirect('/login')
    return render_template('register.html')

@app.route('/register', methods=['POST'])
def register():
    if not session.get('logged_in'):
        return redirect('/login')
    if not has_permission('register'):
        return "⛔ You don't have permission to register cylinders.", 403
    gas_type = request.form['gas_type'].strip().upper()
    size = request.form['size']
    status = request.form['status']
    prefix = gas_type[:2]
    existing_barcodes = Cylinder.query.filter(Cylinder.barcode.like(f"CYL-{prefix}-%")).all()
    next_number = len(existing_barcodes) + 1
    barcode_id = f"CYL-{prefix}-{next_number}"
    output_folder = os.path.join('static', 'qrcodes')
    os.makedirs(output_folder, exist_ok=True)
    qr_path = os.path.join(output_folder, f"{barcode_id}.png")
    qr = qrcode.make(barcode_id)
    qr.save(qr_path)
    new_cylinder = Cylinder(cylinder_type="Simple", gas_type=gas_type, size=size, status=status, barcode=barcode_id)
    db.session.add(new_cylinder)
    db.session.commit()
    return f'''✅ Cylinder saved to database!<br>Name: {gas_type}<br>Size: {size}<br>Status: {status}<br>Barcode: {barcode_id}<br><br><img src="/static/qrcodes/{barcode_id}.png" alt="QR Code" width="200"><br><a href="/">➕ Register Another</a> | <a href="/cylinders">📋 View Cylinders</a>'''

# The rest of the routes would follow the same format...
