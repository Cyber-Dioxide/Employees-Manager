import json

from flask import Flask, request, render_template, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session
from datetime import datetime
from flask import jsonify
import smtplib

with open('config.json', 'r') as file:
    CONFIG = json.loads(file.read())


app = Flask(__name__)
app.secret_key = CONFIG['SECRET_KEY']
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SQLALCHEMY_DATABASE_URI'] = CONFIG['ALCHEMY_DB_URI']
db = SQLAlchemy(app)
Session(app)


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(120), nullable=False)
    password = db.Column(db.String(120), nullable=False)
    points = db.Column(db.Integer, default=0)
    tasks = db.relationship('Task', backref='employee', lazy=True)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(255), nullable=False)
    due_date = db.Column(db.DateTime, nullable=True)
    is_done = db.Column(db.Boolean, default=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)


class NewsEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    event = db.Column(db.Text, nullable=False)
    date = db.Column(db.Date, nullable=False)
    image_url = db.Column(db.String(255))


def user_is_authenticated(email, password):
    employee = Employee.query.filter_by(email=email).first()

    if employee and employee.password == password:
        return True

    return False


@app.route('/add_event', methods=['POST'])
def add_event():
    if session.get('admin_auth'):
        title = request.form.get('title')
        event = request.form.get('event')
        date = request.form.get('date')
        image_url = request.form.get('image_url')

        new_event = NewsEvent(title=title, event=event, date=date, image_url=image_url)
        db.session.add(new_event)
        db.session.commit()
        flash('Event added successfully.', 'success')
    else:
        flash('Authentication required.', 'error')
    return redirect('/admin')


@app.route('/delete_event/<int:event_id>', methods=['POST'])
def delete_event(event_id):
    if session.get('admin_auth'):
        event = NewsEvent.query.get_or_404(event_id)
        db.session.delete(event)
        db.session.commit()
        flash('Event deleted successfully.', 'success')
    else:
        flash('Authentication required.', 'error')
    return redirect('/admin')


@app.route('/mark_task_done/<int:task_id>', methods=['POST'])
def mark_task_done(task_id):
    if session.get('authenticated'):
        email = session.get('email')
        password = session.get('password')
        employee = Employee.query.filter_by(email=email, password=password).first()

        if employee:
            task = Task.query.get_or_404(task_id)
            if task.employee == employee and not task.is_done:
                task.is_done = True
                employee.points += 5  # Award 5 points for completing a task
                db.session.commit()
                flash('Task marked as done. You earned 5 points.', 'success')
            else:
                flash('You are not authorized to mark this task as done or it is already marked as done.', 'error')
        else:
            flash('Authentication failed.', 'error')
    else:
        flash('Authentication required.', 'error')

    return redirect(request.referrer)  # Redirect back to the task list page


@app.route('/logout')
def logout():
    session.clear()  # Clear all session data
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/add_employee', methods=['POST'])
def add_employee():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        role = request.form.get('role')
        password = request.form.get('password')

        # Create a new Employee instance and add it to the database
        new_employee = Employee(name=name, email=email, role=role, password=password)
        db.session.add(new_employee)
        db.session.commit()

        return redirect(url_for('admin'))  # Redirect to admin page after adding

    return redirect(url_for('admin'))  # Redirect if not a POST request


@app.route('/get_tasks')
def get_tasks():
    if session.get('authenticated'):
        email = session.get('email')
        password = session.get('password')
        employee = Employee.query.filter_by(email=email, password=password).first()
        if employee:
            tasks = [{"description": task.description, "due_date": task.due_date.strftime('%Y-%m-%d')} for task in
                     employee.tasks]
            return jsonify(tasks)
    return jsonify([])


@app.route('/add_task', methods=['POST'])
def add_task():
    if request.method == 'POST':
        employee_id = request.form.get('employee_id')
        title = request.form.get('title')
        description = request.form.get('description')
        due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%d')

        # Create a new Task instance and add it to the database
        new_task = Task(employee_id=employee_id, description=description, due_date=due_date)
        db.session.add(new_task)
        db.session.commit()

        return redirect(url_for('admin'))  # Redirect to admin page after adding

    return redirect(url_for('admin'))  # Redirect if not a POST request


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if user_is_authenticated(email, password):
            # If user is authenticated, store relevant info in session
            session['authenticated'] = True
            session['email'] = email
            session['password'] = password
            return redirect(url_for('employee'))
        else:
            return render_template('login.html', error='Invalid credentials')

    return render_template('login.html')


@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if request.method == 'POST':
        if request.form.get('key') == CONFIG['ADMIN_AUTH_KEY']:
            session['admin_auth'] = True
            return redirect(url_for('admin'))

    return render_template('auth.html')


@app.route('/send_email/<int:task_id>', methods=['POST'])
def send_email(task_id):
    if session.get('authenticated'):
        task = Task.query.get_or_404(task_id)
        employee = task.employee

        if task.is_done:
            flash('Task is already marked as done.', 'error')
            return redirect(url_for('admin'))

        # Send email using SMTP
        smtp_server = CONFIG['SMTP_SERVER']
        smtp_port = CONFIG['SMTP_PORT']
        smtp_username = CONFIG['SMTP_USERNAME']
        smtp_password = CONFIG['SMTP_PASSWD']
        sender_email = CONFIG['SENDER_EMAIL']
        receiver_email = employee.email

        subject = CONFIG['EMAIL_SUBJECT']
        message = f'Dear {employee.name},\n\nThis is a reminder for your pending task with due date {task.due_date}.' \
                  f'\n\nBest regards,\nAdmin'

        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.sendmail(sender_email, receiver_email, f'Subject: {subject}\n\n{message}')

            flash(f'Email sent to {employee.name}.', 'success')
        except Exception as e:
            flash(f'Error sending email: {str(e)}', 'error')

        return redirect(url_for('admin'))
    else:
        flash('Authentication required.', 'error')
        return redirect(url_for('login'))


ROBOHASH_API_URL = "https://robohash.org/{}?set=set{}"


def get_avatar_url(username):
    hash_code = hash(username) % 5  # Choose from sets 0 to 4
    return ROBOHASH_API_URL.format(username, hash_code)


@app.route('/', methods=['GET', 'POST'])
def employee():
    if session.get('authenticated'):
        email = session.get('email')
        password = session.get('password')
        employee = Employee.query.filter_by(email=email, password=password).first()
        if employee:
            tasks = Task.query.filter_by(employee_id=employee.id).all()
            avatar_url = get_avatar_url(employee.name)
            events = NewsEvent.query.all()
            return render_template('index.html', email=email, tasks=tasks, employee=employee, avatar_url=avatar_url , events=events)

    return render_template('login.html')


@app.route('/admin', methods=['GET'])
def admin():
    if session.get('admin_auth'):
        employees = Employee.query.all()
        tasks = Task.query.filter_by(is_done=False).all()
        tasks_all = Task.query.all()
        events = NewsEvent.query.all()
        return render_template('admin.html', tasks=tasks, employees=employees , tasks_all=tasks_all, events=events)
    else:
        flash('Authentication required.', 'error')
        return redirect('/auth')  # Redirect to the authentication route


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
