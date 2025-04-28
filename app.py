import os
from datetime import datetime

# Third-party libraries
from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
import barcode
from barcode.writer import ImageWriter
import qrcode  # ⬅️ Add this at the top of your file if it's not there


app = Flask(__name__)
app.secret_key = 'supersecret123'  # 🛡️ Required for login session


# Database setup
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'cylinders.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Define the Cylinder model
class Cylinder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cylinder_type = db.Column(db.String(100))
    gas_type = db.Column(db.String(100))
    size = db.Column(db.String(50))
    status = db.Column(db.String(10))
    barcode = db.Column(db.String(50), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime)

# Track status change history
class StatusHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cylinder_id = db.Column(db.Integer, db.ForeignKey('cylinder.id'))
    old_status = db.Column(db.String(10))
    new_status = db.Column(db.String(10))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class MovementLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cylinder_id = db.Column(db.Integer, db.ForeignKey('cylinder.id'))
    action = db.Column(db.String(10))  # "IN" or "OUT"
    note = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)



# Home page: Registration form
@app.route('/')
def home():
    if not session.get('logged_in'):
        return redirect('/login')
    return render_template('register.html')

# Save form data to database
@app.route('/register', methods=['POST'])
def register():
    gas_type = request.form['gas_type']
    size = request.form['size']
    status = request.form['status']

    # Generate a unique barcode ID
    barcode_id = f"CYL-{gas_type[:2].upper()}-{Cylinder.query.count() + 1}"

    # Generate QR code image
    qr_path = os.path.join('static', 'qrcodes')
    os.makedirs(qr_path, exist_ok=True)
    qr_filename = os.path.join(qr_path, f"{barcode_id}.png")

    qr = qrcode.make(barcode_id)
    qr.save(qr_filename)

    new_cylinder = Cylinder(
        cylinder_type="Simple",  # or leave empty if you'd like
        gas_type=gas_type,
        size=size,
        status=status,
        barcode=barcode_id
    )
    db.session.add(new_cylinder)
    db.session.commit()

    return f'''
    ✅ Cylinder saved to database!<br>
    Name: {gas_type}<br>
    Size: {size}<br>
    Status: {status}<br>
    Barcode: {barcode_id}<br><br>
    <img src="/static/qrcodes/{barcode_id}.png" alt="QR Code" width="200">
    <a href="/">➕ Register Another</a> |
    <a href="/cylinders">📋 View Cylinders</a>
    '''



@app.route('/cylinders')
def list_cylinders():
    if not session.get('logged_in'):
        return redirect('/login')

    # Distinct gas types from database
    gas_types = [row[0] for row in db.session.query(Cylinder.gas_type).distinct().all()]
    # Predefined status list
    status_list = ['Full', '75%', '50%', '25%', 'Empty', 'Returned']

    # Get filters from URL
    selected_gas = request.args.get('gas_type')
    selected_status = request.args.get('status')

    # Base query
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

    # Pie Chart (Statuses excluding 'Returned')
    statuses = ['Full', '75%', '50%', '25%', 'Empty']
    labels = []
    counts = []

    for status in statuses:
        count = Cylinder.query.filter(Cylinder.status == status).count()
        labels.append(status)
        counts.append(count)

    # Registration Timeline (excluding Returned)
    from collections import defaultdict
    daily_counts = defaultdict(int)
    for cyl in Cylinder.query.filter(Cylinder.status != 'Returned').all():
        if cyl.created_at:
            date_str = cyl.created_at.strftime('%Y-%m-%d')
            daily_counts[date_str] += 1

    sorted_dates = sorted(daily_counts.keys())
    bar_labels = sorted_dates
    bar_values = [daily_counts[date] for date in sorted_dates]

    # Gas Type Bar Chart (excluding Returned)
    from sqlalchemy import func
    gas_data = db.session.query(
        Cylinder.gas_type, func.count(Cylinder.id)
    ).filter(Cylinder.status != 'Returned').group_by(Cylinder.gas_type).all()

    gas_labels = [g[0] for g in gas_data]
    gas_counts = [g[1] for g in gas_data]

    # ✅ Inventory summary counts (inside the function)
    total_count = Cylinder.query.count()
    available_count = Cylinder.query.filter(Cylinder.status != "Returned").count()
    returned_count = Cylinder.query.filter(Cylinder.status == "Returned").count()

    return render_template(
        'dashboard.html',
        labels=labels,
        counts=counts,
        bar_labels=bar_labels,
        bar_values=bar_values,
        gas_labels=gas_labels,
        gas_counts=gas_counts,
        total_count=total_count,
        available_count=available_count,
        returned_count=returned_count
    )



from flask import Response  # make sure this is imported at the top with render_template

@app.route('/export')
def export_csv():
    cylinders = Cylinder.query.all()

    # Create CSV content
    csv_data = "ID,Cylinder Type,Gas Type,Size,Status,Barcode,Registered On,Last Updated\n"
    for cyl in cylinders:
        created = cyl.created_at.strftime("%Y-%m-%d %H:%M") if cyl.created_at else ""
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
    pdf.drawCentredString(width / 2, height - 290, datetime.now().strftime("%Y-%m-%d %H:%M"))

    pdf.showPage()  # move to next page

    # TABLE HEADER
    y = height - 50
    pdf.setFont("Helvetica-Bold", 10)
    headers = ["ID", "Type", "Gas", "Size", "Status", "Registered", "Updated"]
    x_positions = [50, 100, 170, 240, 310, 380, 460]

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

        created = cyl.created_at.strftime("%Y-%m-%d") if cyl.created_at else ""
        updated = cyl.updated_at.strftime("%Y-%m-%d") if cyl.updated_at else ""
        values = [cyl.id, cyl.cylinder_type, cyl.gas_type, cyl.size, cyl.status, created, updated]
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

		# ✅ Multiple hardcoded users
		if (username == 'admin' and password == 'admin123') or \
			(username == 'neda' and password == 'mypassword') or \
			(username == 'amir' and password == 'gas88'):
			session['logged_in'] = True
			return redirect(url_for('home'))
		else:
			return render_template('login.html', error='Invalid username or password.')

	return render_template('login.html')

@app.route('/history/<int:cylinder_id>')
def view_history(cylinder_id):
    if not session.get('logged_in'):
        return redirect('/login')

    cylinder = Cylinder.query.get_or_404(cylinder_id)
    history = StatusHistory.query.filter_by(cylinder_id=cylinder.id).order_by(StatusHistory.timestamp.desc()).all()

    return render_template('history.html', cylinder=cylinder, history=history)


@app.route('/movement/<int:cylinder_id>')
def view_movement(cylinder_id):
    if not session.get('logged_in'):
        return redirect('/login')

    cylinder = Cylinder.query.get_or_404(cylinder_id)
    movements = MovementLog.query.filter_by(cylinder_id=cylinder.id).order_by(MovementLog.timestamp.desc()).all()

    return render_template('movement.html', cylinder=cylinder, movements=movements)

@app.route('/log_out/<int:cylinder_id>')
def log_out_cylinder(cylinder_id):
    if not session.get('logged_in'):
        return redirect('/login')

    cylinder = Cylinder.query.get_or_404(cylinder_id)

    # Log the OUT action
    log = MovementLog(
        cylinder_id=cylinder.id,
        action="OUT",
        note="Returned to supplier"
    )
    db.session.add(log)

    # Update cylinder status
    cylinder.status = "Returned"
    cylinder.updated_at = datetime.utcnow()

    db.session.commit()

    return f'''
        ✅ Cylinder <b>{cylinder.barcode}</b> has been marked as Returned.<br><br>
        <a href="/cylinders">📋 Back to All Cylinders</a>
    '''


import os

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    print("✅ Database tables created!")  # <--- Add this
    app.run(debug=True)

    port = int(os.environ.get('PORT', 5000))  # ✅ Use Render-provided PORT
    app.run(host='0.0.0.0', port=port)

