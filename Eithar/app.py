from flask import Flask,flash, render_template, request, url_for, redirect, session, jsonify
from flask_mysqldb import MySQL, MySQLdb
from flask_socketio import SocketIO, emit, join_room, leave_room, send, SocketIO
from string import ascii_uppercase
import os
from werkzeug.security import generate_password_hash, check_password_hash
import re


# Initialize Flask and MySQL-------------------------------------------------------------------------------------
app = Flask(__name__)
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'flask_users'
app.secret_key = os.urandom(24)
socketio = SocketIO(app)
mysql = MySQL(app)


# Routes-------------------------------------------------------------------------------

@app.route('/')
def register():
    return render_template("Register.html")

#--------------------------------------------------------------------------------------

@app.route('/home')
def home():
    return render_template("homepage.html")


#--------------------------------------------------------------------------------------

@app.route('/signup', methods=["GET", "POST"])
def signup():
    try:
        if request.method == 'POST':
            fullname = request.form['Fullname']
            email = request.form['email']
            password = request.form['password']
            identifier = request.form['id']
            
            print(f"Received Fullname: {fullname}")
            print(f"Received Email: {email}")
            print(f"Received Password: {password}")
            print(f"Received ID: {identifier}")

            cur = mysql.connection.cursor()
            
            password_regex = re.compile(
                r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$')
            if not password_regex.match(password):
                flash('Password must be at least 8 characters long, include a capital letter, a small letter, a number, and a special character.', 'danger')
                return redirect(url_for('register'))

            hashed_password = generate_password_hash(password)
            print(f"Hashed Password: {hashed_password}")
            
            cur.execute("INSERT INTO user (Fullname, email, password, id) VALUES (%s, %s, %s, %s)", 
                        (fullname, email, hashed_password, identifier))
            mysql.connection.commit()

            cur.close()

            flash('Sign up successful! Please log in to access your account.', 'success')
            return redirect(url_for('register'))
    except MySQLdb.IntegrityError as e:
        print(f"IntegrityError: {e}")
        flash('An internal server error occurred. Please try again later.', 'danger')
        return redirect(url_for('register'))
    except Exception as e:
        print(f"Error occurred: {e}")
        flash(f'An internal server error occurred: {e}', 'danger')
        return redirect(url_for('register'))
    return render_template("Register.html")


@app.route('/signin', methods=['POST'])
def signin(): 
    email = request.form['email']
    password = request.form['password']
    
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT * FROM admin WHERE email=%s", (email,))
    admin = cur.fetchone()

    if admin:
        print(f"Admin found: {admin['email']}")
        if password == admin['password']:  # Plain text password check
            session['user'] = 'admin'
            session['email'] = admin['email']
            session['user_id'] = admin['id']  # Ensure this is set for password change
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid email or password', 'danger')
            print("Invalid admin password")
            return redirect(url_for('register'))  # Redirect back to sign-in page on failure
    
    cur.execute("SELECT * FROM user WHERE email=%s", (email,))
    user = cur.fetchone()

    if user:
        print(f"User found: {user['email']}")
        if check_password_hash(user['password'], password): 
            session['email'] = user['email']
            session['user_id'] = user['id']
            session['Fullname'] = user.get('Fullname', '')  # Fallback in case Fullname is NULL
            session['time_credit'] = user.get('time_credit', 0)
            return redirect(url_for('profile'))
        else: 
            flash('Invalid email or password', 'danger')
            print("Invalid user password")
            return redirect(url_for('register'))  # Redirect back to sign-in page on failure
    
    flash('Invalid email or password', 'danger')
    return redirect(url_for('register'))  # Redirect back to sign-in page on failure

    
#--------------------------------------------------------------------------------------

@app.route('/check_id/<id>')
def check_id(id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM user WHERE id = %s", (id,))
    existing_id = cur.fetchone()
    cur.close()
    return {'exists': bool(existing_id)}

@app.route('/check_email/<email>')
def check_email(email):
    cur = mysql.connection.cursor()
    cur.execute("SELECT email FROM user WHERE email = %s", (email,))
    existing_email = cur.fetchone()
    cur.close()
    return {'exists': bool(existing_email)}

#--------------------------------------------------------------------------------------

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('register'))

#--------------------------------------------------------------------------------------

@app.route('/how-it-works')
def how_it_works():
    return render_template("how_it_works.html")

#--------------------------------------------------------------------------------------
@app.route('/Services')
def Services():
    user_id = session.get('user_id')
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Fetch categories and their services
    cur.execute("""
        SELECT c.id AS category_id, c.name AS category_name, s.id AS service_id, s.service_name AS service_name
        FROM categories c
        LEFT JOIN services s ON c.id = s.category_id
    """)
    category_services = cur.fetchall()

    categories = {}
    for item in category_services:
        if item['category_id'] not in categories:
            categories[item['category_id']] = {
                'name': item['category_name'],
                'services': []
            }
        if item['service_id']:
            categories[item['category_id']]['services'].append({
                'id': item['service_id'],
                'name': item['service_name']
            })

    # Fetch users (service providers) with their average ratings
    if user_id:
        cur.execute("""
            SELECT u.id, u.Fullname, COALESCE(AVG(r.rating), 0) as avg_rating 
            FROM user u
            LEFT JOIN requests r ON u.id = r.provider_id
            WHERE u.id != %s
            GROUP BY u.id
        """, (user_id,))
    else:
        cur.execute("""
            SELECT u.id, u.Fullname, COALESCE(AVG(r.rating), 0) as avg_rating
            FROM user u
            LEFT JOIN requests r ON u.id = r.provider_id
            GROUP BY u.id
        """)
    users = cur.fetchall()

    # Fetch regions 
    cur.execute("SELECT region_id, region_name FROM region")
    regions = cur.fetchall()

    cur.close()

    # Pass data to template
    return render_template("Services.html", categories=categories, users=users, regions=regions)

@app.route('/ServiceProviders/<int:service_id>')
def ServiceProviders(service_id):
    user_id = session.get('user_id')
    print(f"Fetching users for service ID: {service_id}")  # Debug statement
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Fetch users linked to the specific service ID excluding the logged-in user
    cur.execute("""
        SELECT u.id, u.Fullname, u.bio 
        FROM user u
        JOIN user_services us ON u.id = us.user_id
        WHERE us.service_id = %s AND u.id != %s
    """, (service_id, user_id))
    users = cur.fetchall()
    
    cur.close()
    
    return jsonify(users)

@app.route('/fetch_users')
def fetch_users():
    user_id = session.get('user_id')
    region_id = request.args.get('region_id')
    service_id = request.args.get('service_id')

    query = """
    SELECT DISTINCT u.id, u.Fullname, COALESCE(AVG(req.rating), 0) as avg_rating 
    FROM user u 
    LEFT JOIN user_services us ON u.id = us.user_id 
    LEFT JOIN region r ON u.region_id = r.region_id 
    LEFT JOIN requests req ON u.id = req.provider_id
    WHERE 1 = 1
    """
    
    params = []

    if user_id:
        query += " AND u.id != %s"
        params.append(user_id)
    
    if region_id:
        query += " AND u.region_id = %s"
        params.append(region_id)
    
    if service_id:
        query += " AND us.service_id = %s"
        params.append(service_id)

    query += " GROUP BY u.id"
    
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    try:
        cur.execute(query, params)
        users = cur.fetchall()
    except Exception as e:
        print(f"Error fetching users: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
    
    return jsonify(users)

#--------------------------------------------------------------------------------------

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('signin'))
    
    user_id = session['user_id']
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Fetch user information along with region name
    cur.execute("""
        SELECT u.*, r.region_name 
        FROM user u
        LEFT JOIN region r ON u.region_id = r.region_id 
        WHERE u.id = %s
    """, (user_id,))
    user_profile = cur.fetchone()

    # Fetch regions
    cur.execute("SELECT region_id, region_name FROM region")
    regions = cur.fetchall()

    # Fetch user reviews from requests table and calculate average rating
    cur.execute("""
        SELECT r.review, FLOOR(r.rating) AS rating, u.Fullname AS reviewer_name 
        FROM requests r
        JOIN user u ON r.requester_id = u.id
        WHERE r.provider_id = %s AND r.status = 'completed'
    """, (user_id,))
    reviews = cur.fetchall()
    
    if reviews:
        total_rating = sum(review['rating'] for review in reviews)
        average_rating = total_rating / len(reviews)
    else:
        average_rating = 0

    if request.method == 'POST':
        # Get data from the form
        Fullname = request.form.get('Fullname')
        email = request.form.get('email')
        password = request.form.get('password')
        location = request.form.get('location')
        region_id = request.form.get('region_id')
        bio = request.form.get('bio')

        

        # Ensure the data is not empty
        if Fullname and email:
            # Update the user information in the database
            cur.execute("""
                UPDATE user 
                SET Fullname = %s, email = %s, location = %s, region_id = %s, bio = %s
                WHERE id = %s
            """, (Fullname, email, location, region_id, bio, user_id))
            mysql.connection.commit()

            flash('Profile updated successfully!', 'success')
            return redirect(url_for('profile'))
        else:
            flash('Please fill in all the required fields.', 'error')

    # Fetch categories and services
    cur.execute("SELECT id, name FROM categories")
    categories = cur.fetchall()

    # Fetch all categories and associated services
    cur.execute("""
        SELECT c.id AS category_id, c.name AS category_name, 
               s.id AS service_id, s.service_name AS service_name
        FROM categories c
        LEFT JOIN services s ON c.id = s.category_id
    """)
    categories_services = cur.fetchall()

    # Group services by category
    from collections import defaultdict
    grouped_services = defaultdict(list)
    for row in categories_services:
        grouped_services[row['category_id']].append({
            'service_id': row['service_id'],
            'service_name': row['service_name'],
            'category_name': row['category_name']
        })

    # Fetch user's selected services
    cur.execute("""
        SELECT service_id
        FROM user_services
        WHERE user_id = %s
    """, (user_id,))
    selected_services = [service['service_id'] for service in cur.fetchall()]

    # Fetch user's provided services
    cur.execute("""
        SELECT r.id AS request_id, u.Fullname AS requester_fullname, s.service_name, r.status AS request_status,r.time_spent, r.created_at
        FROM Requests r
        JOIN user u ON r.requester_id = u.id
        JOIN services s ON r.service_id = s.id
        WHERE r.provider_id = %s
    """, (user_id,))
    provided_services = cur.fetchall()

    # Fetch user's received services
    cur.execute("""
        SELECT r.id AS request_id, u.Fullname AS provider_name, s.service_name, r.status AS request_status, r.time_spent, r.created_at
        FROM Requests r
        JOIN user u ON r.provider_id = u.id
        JOIN services s ON r.service_id = s.id
        WHERE r.requester_id = %s
    """, (user_id,))
    received_services = cur.fetchall()

    cur.close()
    
    return render_template(
        'profile.html', 
        user=user_profile, 
        categories=categories,
        grouped_services=grouped_services, 
        selected_services=selected_services,
        provided_services=provided_services,
        received_services=received_services,
        regions=regions,  # Pass regions to template
        average_rating=average_rating  # Pass average rating to template
    )

@app.route('/change_password', methods=['POST'])
def change_password():
    data = request.get_json()
    old_password = data['old_password']
    new_password = data['new_password']
    
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"success": False, "message": "User not logged in"}), 401

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT * FROM user WHERE id = %s", (user_id,))
    user = cur.fetchone()
    
    if not user or not check_password_hash(user['password'], old_password):
        return jsonify({"success": False, "message": "Old password is incorrect"}), 400

    hashed_new_password = generate_password_hash(new_password)
    cur.execute("UPDATE user SET password = %s WHERE id = %s", (hashed_new_password, user_id))
    mysql.connection.commit()
    cur.close()

    return jsonify({"success": True})

@app.route('/get_services/<int:category_id>', methods=['GET'])
def get_services(category_id):
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Fetch services for the given category
    cur.execute("""
        SELECT id AS service_id, service_name
        FROM services
        WHERE category_id = %s
    """, (category_id,))
    services = cur.fetchall()
    
    cur.close()

    return jsonify({'services': services})

@app.route('/get_user_services', methods=['GET'])
def get_user_services():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'User not logged in'}), 401

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT us.service_id, s.service_name  # Added us.service_id to the select clause
        FROM user_services us
        JOIN services s ON us.service_id = s.id
        WHERE us.user_id = %s
    """, (user_id,))
    services = cur.fetchall()
    cur.close()

    return jsonify({'services': services}), 200

@app.route('/save_service', methods=['POST'])
def save_service():
    data = request.get_json()
    user_id = session.get('user_id')
    service_id = data.get('service_id')

    if not user_id:
        return jsonify({'error': 'User not logged in'}), 401

    if not service_id:
        return jsonify({'error': 'Invalid data'}), 400

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    try:
        cur.execute("""
            SELECT * FROM user_services
            WHERE user_id = %s AND service_id = %s
        """, (user_id, service_id))
        existing_service = cur.fetchone()

        if existing_service:
            return jsonify({'error': 'Service already saved!'}), 400

        cur.execute("""
            INSERT INTO user_services (user_id, service_id)
            VALUES (%s, %s)
        """, (user_id, service_id))
        mysql.connection.commit()
        cur.close()

        return jsonify({'message': 'Service saved successfully!'}), 200

    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/delete_service', methods=['POST'])
def delete_service():
    data = request.get_json()
    print("Received data for deletion:", data)  # Debugging

    service_id = data.get('service_id')
    user_id = session.get('user_id')

    if not user_id:
        return jsonify({'error': 'User not logged in'}), 401

    if not service_id:
        return jsonify({'error': 'Invalid data'}), 400

    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            DELETE FROM user_services
            WHERE user_id = %s AND service_id = %s
        """, (user_id, service_id))
        mysql.connection.commit()
        return jsonify({'message': 'Service deleted successfully!'}), 200

    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': f'Error: {str(e)}'}), 500

    finally:
        cur.close()

@app.route('/api/service-details/<int:request_id>', methods=['GET'])
def get_service_details(request_id):
    if 'user_id' not in session:
        return jsonify({'error': 'User not logged in'}), 401

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    try:
        # Fetch service details for the given request_id
        cur.execute("""
            SELECT 
                u.Fullname AS requester_name, 
                r.time_spent, 
                r.review, 
                r.rating
            FROM requests r
            JOIN user u ON r.requester_id = u.id
            WHERE r.id = %s
        """, (request_id,))
        service_details = cur.fetchone()

        if not service_details:
            return jsonify({'error': 'Service details not found'}), 404

        return jsonify(service_details), 200

    except Exception as e:
        print(f"Error fetching service details: {e}")
        return jsonify({'error': 'An error occurred while fetching service details'}), 500

    finally:
        cur.close()
@app.route('/UsersByRegion/<region>', methods=['GET'])
def users_by_region(region):
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Fetch users by region
    cur.execute("SELECT id, Fullname, bio FROM user WHERE region = %s", (region,))
    users = cur.fetchall()
    
    cur.close()

    return jsonify(users)

#--------------------------------------------------------------------------------------
@app.route('/public_profile/<int:user_id>')
def public_profile(user_id):
    try:
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        
        # Fetch user information including region name
        cur.execute("""
            SELECT u.Fullname, u.location, u.bio, r.region_name
            FROM user u
            LEFT JOIN region r ON u.region_id = r.region_id
            WHERE u.id = %s
        """, (user_id,))
        user = cur.fetchone()
        print(f"User Info: {user}")  # Debugging
        
        # Fetch user services
        cur.execute("""
            SELECT s.id, s.service_name
            FROM services s
            JOIN user_services us ON s.id = us.service_id
            WHERE us.user_id = %s
        """, (user_id,))
        services = cur.fetchall()
        print(f"User Services: {services}")  # Debugging
        
        # Fetch user reviews from requests table
        cur.execute("""
        SELECT r.review, FLOOR(r.rating) AS rating, u.Fullname AS reviewer_name 
        FROM requests r
        JOIN user u ON r.requester_id = u.id
        WHERE r.provider_id = %s AND r.status = 'completed'
        """, (user_id,))
        reviews = cur.fetchall()
        print(f"User Reviews: {reviews}")  # Debugging
        
        # Calculate average rating
        if reviews:
            total_rating = sum(review['rating'] for review in reviews)
            average_rating = total_rating / len(reviews)
        else:
            average_rating = 0
        
        # Check if user is logged in
        if 'user_id' in session:
            cur.execute("""
            SELECT id 
            FROM requests 
            WHERE requester_id = %s AND provider_id = %s AND status = 'in_progress'
            """, (session['user_id'], user_id))
            ongoing_request = cur.fetchone()
            user1_id = session.get('user_id')
        else:
            ongoing_request = None
            user1_id = None
            
        print(f"Ongoing Request: {ongoing_request}")  # Debugging
        cur.close()
        
        # Convert rating to integer
        for review in reviews:
            review['rating'] = int(review['rating'])

        return render_template('public_profile.html', user_id=user_id, user=user, services=services, reviews=reviews, ongoing_request=ongoing_request, user1_id=user1_id, average_rating=average_rating)
    
    except Exception as e:
        print(f"Error: {e}")  # Debugging
        return f"An error occurred: {e}", 500

@app.route('/start_request', methods=['POST'])
def start_request():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    try:
        data = request.get_json()
        provider_id = data['provider_id']
        service_id = data['service_id']
        requester_id = session['user_id']

        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        
        # Check time credit for the requester
        cur.execute("SELECT time_credit FROM user WHERE id = %s", (requester_id,))
        time_credit = cur.fetchone()['time_credit']
        if time_credit <= 0:
            return jsonify({'error': 'Insufficient time credit'}), 400

        # Fetch provider and service names
        cur.execute("SELECT Fullname FROM user WHERE id = %s", (provider_id,))
        provider_name = cur.fetchone()
        if not provider_name:
            return jsonify({'error': 'Invalid provider ID'}), 400
        provider_name = provider_name['Fullname']

        cur.execute("SELECT service_name FROM services WHERE id = %s", (service_id,))
        service_name = cur.fetchone()
        if not service_name:
            return jsonify({'error': 'Invalid service ID'}), 400
        service_name = service_name['service_name']

        # Insert into requests table and get the request_id
        cur.execute("""
            INSERT INTO requests (requester_id, provider_id, service_id, status)
            VALUES (%s, %s, %s, 'in_progress')
        """, (requester_id, provider_id, service_id))
        mysql.connection.commit()

        cur.execute("SELECT LAST_INSERT_ID() AS request_id")
        request_id = cur.fetchone()['request_id']

       
        mysql.connection.commit()
        cur.close()
        
        return jsonify({'request_id': request_id})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_request_details', methods=['GET'])
def get_request_details():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    request_id = request.args.get('request_id')
    print(f"Fetching details for request ID: {request_id}")  # Debugging

    try:
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute("""
            SELECT r.requester_id, u.Fullname as requester_name, r.service_id, s.service_name, 
                   r.status, r.time_spent, r.created_at, r.review, r.rating 
            FROM requests r
            JOIN user u ON r.requester_id = u.id
            JOIN services s ON r.service_id = s.id
            WHERE r.id = %s
        """, (request_id,))
        request_details = cur.fetchone()
        cur.close()

        if not request_details:
            print(f"No details found for request ID: {request_id}")  # Debugging
            return jsonify({'error': 'No details found for the provided request ID'}), 404

        return jsonify(request_details)
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/submit_review', methods=['POST'])
def submit_review():
    try:
        data = request.get_json()
        request_id = data['request_id']
        rating = data['rating']
        comment = data['comment']
        hours = data['hours']
        
        print(f"Request Data: {data}")  # Debugging
        print(f"Request ID: {request_id}, Rating: {rating}, Comment: {comment}, Hours: {hours}")  # Debugging

        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        
        # Update the request with rating, review, and time spent, and status
        cur.execute("""
            UPDATE requests 
            SET rating = %s, review = %s, time_spent = %s, status = 'completed'
            WHERE id = %s
        """, (rating, comment, hours, request_id))
    
        
        # Update time credit for provider and requester
        cur.execute("SELECT provider_id, requester_id FROM requests WHERE id = %s", (request_id,))
        request_data = cur.fetchone()
        print(f"Request Data from DB: {request_data}")  # Debugging

        if request_data:
            provider_id = request_data['provider_id']
            requester_id = request_data['requester_id']
            
            cur.execute("UPDATE user SET time_credit = time_credit + %s WHERE id = %s", (hours, provider_id))
            cur.execute("UPDATE user SET time_credit = time_credit - %s WHERE id = %s", (hours, requester_id))
            
            # Fetch the updated time credits 
            cur.execute("SELECT time_credit FROM user WHERE id = %s", (requester_id,)) 
            requester_time_credit = cur.fetchone()['time_credit'] 
            cur.execute("SELECT time_credit FROM user WHERE id = %s", (provider_id,)) 
            provider_time_credit = cur.fetchone()['time_credit']
            
            
            mysql.connection.commit()
            cur.close()
            
            # Update session with new time credit for requester 
            session['time_credit'] = requester_time_credit

            
            return jsonify({'success': 'Review submitted successfully', 'requester_time_credit': requester_time_credit, 'provider_time_credit': provider_time_credit})
        else:
            cur.close()
            return jsonify({'error': 'Invalid request ID'}), 400

    except Exception as e:
        print(f"Error: {e}")  # Debugging
        return jsonify({'error': str(e)}), 500

#----------------------------------------FAQ----------------------------------------------

@app.route('/faq')
def faq():
    cur = mysql.connection.cursor()
    cur.execute("SELECT question, answer FROM faq")
    faqs = cur.fetchall()
    cur.close()
    return render_template('faq.html', faqs=faqs)

#--------------------------------------------------------------------------------------


@app.route('/start_chat', methods=["POST"])
def start_chat():
    data = request.get_json()
    user1_id = data.get('user1_id')  # المستخدم الحالي
    user2_id = data.get('user2_id')  # المستخدم الآخر

    # Debugging prints 
    print(f"User1 ID: {user1_id}") 
    print(f"User2 ID: {user2_id}")


    print(f"Start chat: user1_id={user1_id}, user2_id={user2_id}") # Debugging


    if not user1_id or not user2_id:
        return jsonify({"error": "Invalid user hadeell IDs"}), 400  # إذا لم يتم العثور على معرفات المستخدمين

    room_id = get_or_create_chat_room(user1_id, user2_id)
    return jsonify({'room_id': room_id})  # إعادة المعرف الفريد للغرفة

def get_or_create_chat_room(user1_id, user2_id):
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT id FROM chat_rooms 
        WHERE (user1_id = %s AND user2_id = %s) OR (user1_id = %s AND user2_id = %s)
    """, (user1_id, user2_id, user2_id, user1_id))
    room = cur.fetchone()

    if not room:  # إذا لم تكن الغرفة موجودة، يتم إنشاؤها
        cur.execute("INSERT INTO chat_rooms (user1_id, user2_id) VALUES (%s, %s)", (user1_id, user2_id))
        mysql.connection.commit()
        room_id = cur.lastrowid  # استرجاع المعرف الفريد للغرفة الجديدة
    else:
        room_id = room['id']  # الغرفة موجودة بالفعل

    cur.close()
    return room_id


#--------------------------------------------------------------------------------------
@app.route('/chat_list')
def chat_list():
    return render_template('chat.html')

@app.route('/chat/<int:room_id>')
def chat(room_id):
    if 'user_id' not in session:
        return redirect(url_for('signin'))

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # استرجاع اسم المستخدم الآخر من جدول الغرف
    cur.execute("""
        SELECT user.Fullname 
        FROM chat_rooms 
        JOIN user ON (user.id = chat_rooms.user1_id OR user.id = chat_rooms.user2_id)
        WHERE chat_rooms.id = %s AND user.id != %s
    """, (room_id, session['user_id']))
    other_user = cur.fetchone()

    # استرجاع الرسائل
    cur.execute("""
        SELECT messages.message, messages.time, user.Fullname 
        FROM messages 
        JOIN user ON messages.sender_id = user.id 
        WHERE chat_room_id = %s 
        ORDER BY messages.time
    """, (room_id,))
    messages = cur.fetchall()

    # Mark messages as read 
    cur.execute("UPDATE messages SET is_read = TRUE WHERE chat_room_id = %s AND sender_id != %s", 
                (room_id, session['user_id'])) 
    mysql.connection.commit() 
    
    cur.close()

    if other_user:
        return render_template('chat.html', user_id=session['user_id'], room_id=room_id, messages=messages, Fullname=session['Fullname'], other_Fullname=other_user['Fullname'])
    else:
        return "User not found", 404


#--------------------------------------------------------------------------------------

@socketio.on('join')
def handle_join(data):
    room_id = data['room_id']
    join_room(room_id)  # Join the specific room
    print(f"User joined room {room_id}")

@socketio.on('send_message')
def handle_send_message(data):
    room_id = data['room_id']
    message = data['message']
    Fullname = data['Fullname']
    sender_id = session['user_id']
    timestamp = data['time']

    # Store the message in the database
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO messages (chat_room_id, sender_id, message, time) VALUES (%s, %s, %s, %s)", 
            (room_id, sender_id, message, timestamp))
    mysql.connection.commit()
    message_id = cur.lastrowid
    cur.close()

   # Broadcast the message to all users in the room
    socketio.emit('receive_message', {
    'id': message_id,
    'room_id': room_id,
    'Fullname': Fullname,
    'message': message,
    'time': timestamp,
    'sender_id': sender_id
}, room=room_id)

#--------------------------------------------------------------------------------------

@app.route('/get_messages/<int:room_id>')
def get_messages(room_id):
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT messages.id, messages.message, messages.time, messages.sender_id, messages.is_read, user.Fullname
        FROM messages
        JOIN user ON messages.sender_id = user.id
        WHERE messages.chat_room_id = %s
        ORDER BY messages.time ASC  -- Ensuring messages are ordered by time in ascending order
    """, (room_id,))
    messages = cur.fetchall()
    cur.close()
    
    return jsonify(messages)  # Return the messages as a JSON response

#---------------------------Route to Get Chat Rooms-----------------------------------------------------------
@app.route('/get_chat_rooms')
def get_chat_rooms():
    user_id = session.get('user_id')

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT chat_rooms.id AS room_id, 
               user.id AS user_id, 
               user.Fullname
        FROM chat_rooms
        JOIN user ON (user.id = chat_rooms.user1_id OR user.id = chat_rooms.user2_id)
        WHERE (chat_rooms.user1_id = %s OR chat_rooms.user2_id = %s) 
        AND user.id != %s
    """, (user_id, user_id, user_id))
    chat_rooms = cur.fetchall()
    cur.close()

    return jsonify(chat_rooms)

@app.route('/taem')
def team():
    return render_template('team.html')  # Render the FAQ page

#-------------------------------------------ADMIN-------------------------------------------

# Route to get all categories
@app.route('/get_categories', methods=['GET'])
def get_categories():
    try:
        print("Fetching categories...") # Debugging statement
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, name FROM categories")
        categories = cur.fetchall()
        categories_data = [{"id": row[0], "name": row[1]} for row in categories]
        cur.close()
        return jsonify({"categories": categories_data}), 200
    except Exception as e:
        print(f"Error: {e}") # Debugging statement
        return jsonify({"error": "Failed to fetch categories", "details": str(e)}), 500

# Route to get all services
@app.route('/get_services', methods=['GET'])
def get_services_admin():
    try:
        print("Fetching services...") # Debugging statement
        cur = mysql.connection.cursor()
        query = """
        SELECT services.id, services.service_name AS service_name, categories.name AS category_name
        FROM services
        JOIN categories ON services.category_id = categories.id
        """
        cur.execute(query)
        services = cur.fetchall()
        services_data = [
            {"id": row[0], "service_name": row[1], "category_name": row[2]}
            for row in services
        ]
        cur.close()
        return jsonify({"services": services_data}), 200
    except Exception as e:
        print(f"Error: {e}") # Debugging statement
        return jsonify({"error": "Failed to fetch services", "details": str(e)}), 500

# Route to add a new category
@app.route('/add_category', methods=['POST'])
def add_category():
    data = request.get_json()
    category_name = data.get('category_name')
    if not category_name:
        return jsonify({"error": "Category name is required"}), 400
    try:
        cur = mysql.connection.cursor()
        
        # Check if the category already exists
        cur.execute("SELECT * FROM categories WHERE name = %s", (category_name,))
        existing_category = cur.fetchone()
        if existing_category:
            return jsonify({"error": "Category already exists"}), 400
        
        # Add the new category
        cur.execute("INSERT INTO categories (name) VALUES (%s)", (category_name,))
        mysql.connection.commit()
        cur.close()
        return jsonify({"message": "Category added successfully"}), 201
    except Exception as e:
        return jsonify({"error": "Failed to add category", "details": str(e)}), 500

# Route to add a new service
@app.route('/add_service', methods=['POST'])
def add_service():
    data = request.get_json()
    service_name = data.get('service_name')
    category_id = data.get('category_id')
    if not service_name or not category_id:
        return jsonify({"error": "Service name and category ID are required"}), 400
    try:
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO services (service_name, category_id) VALUES (%s, %s)", (service_name, category_id))
        mysql.connection.commit()
        cur.close()
        return jsonify({"message": "Service added successfully"}), 201
    except Exception as e:
        return jsonify({"error": "Failed to add service", "details": str(e)}), 500

@app.route('/delete_category/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    try:
        cur = mysql.connection.cursor()

        # Check if there are any services related to this category
        cur.execute("SELECT COUNT(*) FROM services WHERE category_id = %s", (category_id,))
        service_count = cur.fetchone()[0]

        if service_count > 0:
            return jsonify({"error": "Cannot delete category with existing services"}), 400

        # Delete the category
        cur.execute("DELETE FROM categories WHERE id = %s", (category_id,))
        mysql.connection.commit()
        cur.close()

        return jsonify({"message": "Category deleted successfully"}), 200
    except Exception as e:
        print(f"Error while deleting category with ID {category_id}: {e}")
        return jsonify({"error": "Failed to delete category", "details": str(e)}), 500

@app.route('/delete_service/<int:service_id>', methods=['DELETE'])
def delete_service_admin(service_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM services WHERE id = %s", (service_id,))
        mysql.connection.commit()
        cur.close()
        return jsonify({"message": "Service deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": "Failed to delete service", "details": str(e)}), 500

@app.route('/get_reviews', methods=['GET'])
def get_reviews():
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, requester_id, review FROM requests WHERE review IS NOT NULL")
        reviews = cur.fetchall()
        reviews_data = [{"id": row[0], "requester_id": row[1], "review": row[2]} for row in reviews]
        cur.close()
        return jsonify({"reviews": reviews_data}), 200
    except Exception as e:
        return jsonify({"error": "Failed to fetch reviews", "details": str(e)}), 500

@app.route('/delete_review/<int:review_id>', methods=['DELETE'])
def delete_review(review_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM requests WHERE id = %s", (review_id,))
        mysql.connection.commit()
        cur.close()
        return jsonify({"message": "Review deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": "Failed to delete review", "details": str(e)}), 500

@app.route('/get_counts', methods=['GET'])
def get_counts():
    try:
        cur = mysql.connection.cursor()

        # Count users
        cur.execute("SELECT COUNT(*) FROM user")
        user_count = cur.fetchone()[0]

        # Count categories
        cur.execute("SELECT COUNT(*) FROM categories")
        category_count = cur.fetchone()[0]

        # Count services
        cur.execute("SELECT COUNT(*) FROM services")
        service_count = cur.fetchone()[0]

        cur.close()
        return jsonify({"user_count": user_count, "category_count": category_count, "service_count": service_count}), 200
    except Exception as e:
        return jsonify({"error": "Failed to fetch counts", "details": str(e)}), 500

@app.route('/add_faq', methods=['POST'])
def add_faq():
    data = request.json
    question = data['question']
    answer = data['answer']
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO faq (question, answer) VALUES (%s, %s)", (question, answer))
    mysql.connection.commit()
    cur.close()
    return jsonify(message='FAQ added successfully')

@app.route('/get_faqs')
def get_faqs():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, question, answer FROM faq")
    faqs = cur.fetchall()
    cur.close()

    # Convert the FAQs to a list of dictionaries
    faqs_list = []
    for faq in faqs:
        faqs_list.append({
            'id': faq[0],
            'question': faq[1],
            'answer': faq[2]
        })

    return jsonify(faqs=faqs_list)

@app.route('/delete_faq/<int:id>', methods=['DELETE'])
def delete_faq(id):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM faq WHERE id = %s", (id,))
    mysql.connection.commit()
    cur.close()
    return jsonify(message='FAQ deleted successfully')

@app.route('/change_admin_password', methods=['POST'])
def change_admin_password():
    if 'user' not in session or session['user'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    data = request.json
    current_password = data.get('currentPassword')
    new_password = data.get('newPassword')

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT password FROM admin WHERE id = %s", (user_id,))
    result = cur.fetchone()

    if not result:
        return jsonify({'error': 'User not found'}), 404

    stored_password = result['password']

    if current_password != stored_password:
        return jsonify({'error': 'Current password is incorrect'}), 400

    cur.execute("UPDATE admin SET password = %s WHERE id = %s", (new_password, user_id))
    mysql.connection.commit()

    return jsonify({'message': 'Password successfully changed'})


@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user' in session and session['user'] == 'admin':
        return render_template('admin_dashboard.html')
    else:
        return redirect(url_for('signin'))



if __name__ == '__main__':
    socketio.run(app, debug=True)
