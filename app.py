import os
from datetime import datetime
from zoneinfo import ZoneInfo
houston_tz = ZoneInfo("America/Chicago")

# Third-party libraries
from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
import barcode
from barcode.writer import ImageWriter
import qrcode  # ⬅️ Add this at the top of your file if it's not there
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = 'supersecret123'  # 🛡️ Required for login session


# PostgreSQL database setup (Render)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://admin:IogWBRVd24QjJQZR9dfAf4cqWC5QbXX8@dpg-d09aan49c44c73dc7e1g-a.oregon-postgres.render.com/cylinders'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

from sqlalchemy import LargeBinary

class Cylinder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cylinder_type = db.Column(db.String(100))
    gas_type = db.Column(db.String(100))
    size = db.Column(db.String(50))
    status = db.Column(db.String(10))
    barcode = db.Column(db.String(50), unique=True)
    qr_code = db.Column(LargeBinary)  # ✅ Add this line
    created_by = db.Column(db.String(100))  # ✅ Track who registered the cylinder
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime)


# Track status change history
class StatusHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cylinder_id = db.Column(db.Integer, db.ForeignKey('cylinder.id'))
    old_status = db.Column(db.String(10))
    new_status = db.Column(db.String(10))
    updated_by = db.Column(db.String(100))  # ✅ Track who updated the cylinder
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class MovementLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cylinder_id = db.Column(db.Integer, db.ForeignKey('cylinder.id'))
    action = db.Column(db.String(10))  # "IN" or "OUT"
    note = db.Column(db.String(200))
    performed_by = db.Column(db.String(100))  # ✅ Track who performed the movement
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    permissions = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# 🔐 View all users (admin only)
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


# ✏️ Edit a user's role and permissions
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

# ✅ Add this before your route definitions
def has_permission(permission_name):
    return permission_name in session.get('permissions', [])

@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    if not session.get('logged_in') or session.get('role') != 'admin':
        return redirect('/login')

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return redirect('/users')



# Home page: Registration form
@app.route('/')
def home():
    if not session.get('logged_in'):
        return redirect('/login')
    return render_template('register.html')

from io import BytesIO
import qrcode
import os

@app.route('/register', methods=['POST'])
def register():
    if not session.get('logged_in'):
        return redirect('/login')
    if not has_permission('register'):
        return "⛔ You don't have permission to register cylinders.", 403

    gas_type = request.form['gas_type'].strip().upper()
    size = request.form['size']
    status = request.form['status']

    # Generate a unique barcode ID
    prefix = gas_type[:2]
    existing_barcodes = Cylinder.query.filter(Cylinder.barcode.like(f"CYL-{prefix}-%")).all()
    next_number = len(existing_barcodes) + 1
    barcode_id = f"CYL-{prefix}-{next_number}"

    # Generate QR code and store in memory
    qr_img = qrcode.make(barcode_id)
    buffer = BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_bytes = buffer.getvalue()

    # ✅ Save cylinder to database
    new_cylinder = Cylinder(
        cylinder_type="Simple",
        gas_type=gas_type,
        size=size,
        status=status,
        barcode=barcode_id,
        qr_code=qr_bytes,
        created_by=session.get('username')  # ✅ Save who registered
    )
    db.session.add(new_cylinder)
    db.session.commit()

    return f'''
    ✅ Cylinder saved to database!<br>
    Name: {gas_type}<br>
    Size: {size}<br>
    Status: {status}<br>
    Barcode: {barcode_id}<br><br>
    <img src="/qr/{barcode_id}" alt="QR Code" width="200"><br>
    <a href="/qr/{barcode_id}" download="QR-{barcode_id}.png">⬇️ Download</a><br>
    <a href="/">➕ Register Another</a> |
    <a href="/cylinders">📋 View Cylinders</a>
    '''

# app.py

@app.route('/delete_cylinder/<int:id>', methods=['GET'])
def delete_cylinder(id):
    if not session.get('logged_in') or session.get('role') != 'admin':
        return redirect('/login')

    cylinder = Cylinder.query.get_or_404(id)

    # ❗ Delete related movement logs first
    MovementLog.query.filter_by(cylinder_id=id).delete()

    # ❗ Also delete related status history if needed
    StatusHistory.query.filter_by(cylinder_id=id).delete()

    db.session.delete(cylinder)
    db.session.commit()
    return redirect(url_for('list_cylinders'))



@app.route('/cylinders')
def list_cylinders():
    if not session.get('logged_in'):
        return redirect('/login')
    if not has_permission('view_all'):
        return "⛔ You don't have permission to view cylinders.", 403

    # Distinct gas types from database
    gas_types = [row[0] for row in db.session.query(Cylinder.gas_type).distinct().all()]
    status_list = ['Full', '75%', '50%', '25%', 'Empty', 'Returned']

    selected_gas = request.args.get('gas_type')
    selected_status = request.args.get('status')

    query = Cylinder.query
    if selected_gas:
        query = query.filter(Cylinder.gas_type == selected_gas)
    if selected_status:
        query = query.filter(Cylinder.status == selected_status)

    cylinders = query.all()

    return render_template(
        'cylinders.html',
        cylinders=cylinders,
        gas_types=gas_types,
        status_list=status_list,
        selected_gas=selected_gas,
        selected_status=selected_status
    )


@app.route('/update', methods=['GET', 'POST'])
def update_status():
    if not session.get('logged_in'):
        return redirect('/login')
    cylinder = None

    if request.method == 'POST':
        barcode_input = request.form.get('barcode')

        if 'update' in request.form:
            # This is a status update
            new_status = request.form['new_status']
            cylinder = Cylinder.query.filter_by(barcode=barcode_input).first()

            if cylinder:
                old_status = cylinder.status
                cylinder.status = new_status
                cylinder.updated_at = datetime.utcnow()
                cylinder.updated_by = session.get('username')  # ✅ Track who updated

                # ✅ Log status change
                history = StatusHistory(
                    cylinder_id=cylinder.id,
                    old_status=old_status,
                    new_status=new_status
                )
                db.session.add(history)

                db.session.commit()

                return f'''
                    ✅ Status updated to <b>{new_status}</b> for {barcode_input}<br><br>
                    <a href="/update">🔄 Update Another</a> | 
                    <a href="/cylinders">📋 View All</a>
                '''
        else:
            # This is a barcode search
            cylinder = Cylinder.query.filter_by(barcode=barcode_input).first()
            if not cylinder:
                return f"❌ Cylinder with barcode <b>{barcode_input}</b> not found.<br><a href='/update'>Try Again</a>"

    return render_template('update.html', cylinder=cylinder)

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect('/login')
    if not has_permission('dashboard'):
        return "⛔ You don't have permission to view dashboard.", 403

    # Get distinct gas types
    gas_types = [row[0] for row in db.session.query(Cylinder.gas_type).distinct().all()]
    selected_gas = request.args.get('gas_type')

    # Build base query
    base_query = Cylinder.query
    if selected_gas:
        base_query = base_query.filter(Cylinder.gas_type == selected_gas)
    labels, counts = [], []
    for status in statuses:
        count = base_query.filter(Cylinder.status == status).count()
        labels.append(status)
        counts.append(count)

    # 1. Pie Chart - Status Overview (include all except 'Returned')
    status_list = ['Full', '75%', '50%', '25%', 'Empty', 'On Service']
    labels = []
    counts = []
    for status in status_list:
        count = base_query.filter(Cylinder.status == status).count()
        labels.append(status)
        counts.append(count)

    # 2. Bar Chart - Count by Gas Type (all cylinders except 'Returned')
    from sqlalchemy import func
    gas_query = Cylinder.query.filter(Cylinder.status != 'Returned')
    gas_data = gas_query.with_entities(Cylinder.gas_type, func.count(Cylinder.id)).group_by(Cylinder.gas_type).all()
    gas_labels = [g[0] for g in gas_data]
    gas_counts = [g[1] for g in gas_data]

    return render_template(
        'dashboard.html',
        gas_types=gas_types,
        selected_gas=selected_gas,
        labels=labels,
        counts=counts,
        gas_labels=gas_labels,
        gas_counts=gas_counts
    )

@app.route('/qr/<barcode>')
def serve_qr_code(barcode):
    cylinder = Cylinder.query.filter_by(barcode=barcode).first_or_404()
    if cylinder.qr_code:
        return Response(cylinder.qr_code, mimetype='image/png')
    return "❌ QR code not found", 404



from flask import Response  # make sure this is imported at the top with render_template

@app.route('/export')
def export_csv():
    cylinders = Cylinder.query.all()

    # Create CSV content
    csv_data = "ID,Cylinder Type,Gas Type,Size,Status,Barcode,Registered On,Last Updated\n"
    for cyl in cylinders:
        created = cyl.created_at.astimezone(houston_tz).strftime("%Y-%m-%d %H:%M") if cyl.created_at else ""
        updated = cyl.updated_at.strftime("%Y-%m-%d %H:%M") if cyl.updated_at else ""
        csv_data += f"{cyl.id},{cyl.cylinder_type},{cyl.gas_type},{cyl.size},{cyl.status},{cyl.barcode},{created},{updated}\n"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=cylinders_export.csv"}
    )

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
from flask import send_file


@app.route('/report')
def generate_pdf():
    if not session.get('logged_in'):
        return redirect('/login')
    status_filter = request.args.get('status')
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    query = Cylinder.query

    if status_filter:
        query = query.filter_by(status=status_filter)

    if start_date:
        query = query.filter(Cylinder.created_at >= start_date)

    if end_date:
        query = query.filter(Cylinder.created_at <= end_date)

    cylinders = query.all()

    # PDF starts here
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # TITLE PAGE
    if os.path.exists("logo.png"):
        pdf.drawImage("logo.png", 200, height - 200, width=200, preserveAspectRatio=True)

    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawCentredString(width / 2, height - 250, "Cylinder Inventory Report")

    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(width / 2, height - 270, f"Total Cylinders: {len(cylinders)}")
    houston_time = datetime.now(houston_tz)
    pdf.drawCentredString(width / 2, height - 290, houston_time.strftime("%Y-%m-%d %H:%M"))


    pdf.showPage()  # move to next page

    # TABLE HEADER
    y = height - 50
    pdf.setFont("Helvetica-Bold", 10)
    headers = ["ID", "Type", "Gas", "Size", "Status", "Registered", "Updated", "Created By", "Updated By"]
    x_positions = [40, 80, 140, 200, 260, 320, 390, 460, 540]

    for i, header in enumerate(headers):
        pdf.drawString(x_positions[i], y, header)

    # TABLE ROWS
    pdf.setFont("Helvetica", 8)
    y -= 15
    for cyl in cylinders:
        if y < 50:
            pdf.showPage()
            y = height - 50
            for i, header in enumerate(headers):
                pdf.drawString(x_positions[i], y, header)
            y -= 15

    created = cyl.created_at.astimezone(houston_tz).strftime("%Y-%m-%d") if cyl.created_at else ""
    updated = cyl.updated_at.astimezone(houston_tz).strftime("%Y-%m-%d") if cyl.updated_at else ""
    created_by = getattr(cyl, 'created_by', '—') or '—'
    updated_by = getattr(cyl, 'updated_by', '—') or '—'
    values = [cyl.id, cyl.cylinder_type, cyl.gas_type, cyl.size, cyl.status, created, updated, created_by, updated_by]
    for i, val in enumerate(values):
        pdf.drawString(x_positions[i], y, str(val))
    y -= 12

    pdf.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="cylinder_report.pdf", mimetype='application/pdf')



@app.route('/report/filter')
def report_filter_page():
    if not session.get('logged_in'):
        return redirect('/login')
    return render_template('report_filter.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # ✅ Check user in database
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['logged_in'] = True
            session['username'] = user.username
            session['role'] = user.role
            session['permissions'] = user.permissions.split(',') if user.permissions else []
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error='Invalid username or password.')
    
    # GET method
    return render_template('login.html')


from zoneinfo import ZoneInfo

@app.route('/history/<int:cylinder_id>')
def view_history(cylinder_id):
    if not session.get('logged_in'):
        return redirect('/login')

    cylinder = Cylinder.query.get_or_404(cylinder_id)
    history = StatusHistory.query.filter_by(cylinder_id=cylinder.id).order_by(StatusHistory.timestamp.desc()).all()

    # ✅ Convert timestamps to Houston time
    for h in history:
        h.timestamp = h.timestamp.astimezone(ZoneInfo("America/Chicago"))

    return render_template('history.html', cylinder=cylinder, history=history)



@app.route('/movement/<int:cylinder_id>')
def view_movement(cylinder_id):
    if not session.get('logged_in'):
        return redirect('/login')

    cylinder = Cylinder.query.get_or_404(cylinder_id)
    movements = MovementLog.query.filter_by(cylinder_id=cylinder.id).order_by(MovementLog.timestamp.desc()).all()

    # 🔁 Convert timestamps to Houston time
    for m in movements:
        if m.timestamp:
            m.timestamp = m.timestamp.astimezone(houston_tz)

    return render_template('movement.html', cylinder=cylinder, movements=movements)


@app.route('/log_out/<int:cylinder_id>')
def log_out_cylinder(cylinder_id):
    if not session.get('logged_in'):
        return redirect('/login')
    if not has_permission('log_out'):
        return "⛔ You don't have permission to log out cylinders.", 403

    cylinder = Cylinder.query.get_or_404(cylinder_id)

    # Log the OUT action
    log = MovementLog(
        cylinder_id=cylinder.id,
        action="OUT",
        note="Sent for service"
    )
    db.session.add(log)

    # Update cylinder status
    cylinder.status = "On Service"
    cylinder.updated_at = datetime.utcnow()

    db.session.commit()

    return f'''
        ✅ Cylinder <b>{cylinder.barcode}</b> has been marked as On Service.<br><br>
        <a href="/cylinders">📋 Back to All Cylinders</a>
    '''



from sqlalchemy import text

with app.app_context():
    db.create_all()

# ✅ Ensure 'created_by' column exists
with app.app_context():
    db.create_all()

    with db.engine.begin() as conn:
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='cylinder' AND column_name='created_by'
        """))
        if not result.fetchone():
            conn.execute(text("ALTER TABLE cylinder ADD COLUMN created_by VARCHAR(100);"))
            print("✅ 'created_by' column added.")
        else:
            print("✅ 'created_by' column already exists.")

    # ✅ Create admin user if not exist
    if not User.query.filter_by(username='admin').first():
        admin_user = User(
            username='admin',
            password='admin123',
            role='admin',
            permissions='register,dashboard,view_all,delete,log_out'
        )
        db.session.add(admin_user)
        db.session.commit()
        print('✅ Admin user created (username=admin, password=admin123)')
    else:
        print('✅ Admin user already exists.')




if __name__ == '__main__':
    app.run(debug=True)


    port = int(os.environ.get('PORT', 5000))  # ✅ Use Render-provided PORT
    app.run(host='0.0.0.0', port=port)
