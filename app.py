import os
from functools import wraps
from flask import (
    Flask, request, render_template, send_file, 
    jsonify, redirect, url_for, session, flash,
    current_app
)
from docx import Document
from docx2pdf import convert
import io
from datetime import datetime

from database_handler import (
    DatabaseManager, db, User, Role, ThrustArea, 
    Course, CourseAssignment, Syllabus, ThrustAreaAdmin, Program, CourseProgram, FacultyThrustArea
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'mysql://root:Abhinav0910@localhost/faculty_docs')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'syllabi'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

DatabaseManager.init_app(app)

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            
            user = User.query.get(session["user_id"])
            if not user or not any(role.name in allowed_roles for role in user.roles):
                flash("Unauthorized access", "error")
                return redirect(url_for("login"))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session["user_id"] = user.id
            session["roles"] = [role.name for role in user.roles]
            return redirect(url_for("dashboard"))
        
        # Fix: Use flash() instead of print()
        flash("Invalid credentials", "error")
        return render_template("login.html")
    
    return render_template("login.html")

@app.route("/dashboard")
@role_required(["admin", "thrust_area_admin", "faculty"])
def dashboard():
    user = User.query.get(session["user_id"])
    context = {
        "username": user.name,
        "roles": [role.name for role in user.roles]
    }
    
    if "admin" in session["roles"]:
        context["thrust_areas"] = ThrustArea.query.all()
        context["total_faculty"] = User.query.join(User.roles).filter(Role.name == "faculty").count()
        context["total_courses"] = Course.query.count()
    
    elif "thrust_area_admin" in session["roles"]:
        admin_areas = ThrustArea.query.join(ThrustAreaAdmin).filter(ThrustAreaAdmin.user_id == user.id).all()
        context["admin_areas"] = admin_areas
        context["courses"] = Course.query.filter(Course.thrust_area_id.in_([area.id for area in admin_areas])).all()
    
    elif "faculty" in session["roles"]:
        context["assignments"] = CourseAssignment.query.filter_by(faculty_id=user.id).all()
    
    return render_template("dashboard.html", **context)

@app.route("/get-user/<int:user_id>")
@role_required(["admin"])
def get_user(user_id):
    try:
        user = User.query.get(user_id)
        if user:
            users = User.query.join(User.roles).filter(Role.name == 'faculty').all()
            # Add administered_thrust_areas to each user
            for u in users:
                u.administered_thrust_areas = ThrustArea.query.join(ThrustAreaAdmin).filter(ThrustAreaAdmin.user_id == u.id).all()
            
            return render_template(
                "admin/manage_users.html",
                base_template='base/admin_base.html',
                users=users,
                thrust_areas=ThrustArea.query.all(),
                modify_user=user
            )
        flash("User not found", "error")
        return redirect(url_for("manage_users"))
    except Exception as e:
        flash(f"Error loading user: {str(e)}", "error")
        return redirect(url_for("manage_users"))

@app.route("/modify-faculty/<int:user_id>", methods=["POST"])
@role_required(["admin"])
def modify_faculty(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            flash("Faculty not found", "error")
            return redirect(url_for("manage_users"))

        # Get the thrust areas where this faculty is an admin
        admin_thrust_areas = ThrustArea.query.join(ThrustAreaAdmin).filter(ThrustAreaAdmin.user_id == user.id).all()
        admin_thrust_area_ids = {str(area.id) for area in admin_thrust_areas}

        # Get the selected thrust areas from the form
        selected_thrust_area_ids = set(request.form.getlist("thrust_area_ids"))

        # Check if user is trying to remove a thrust area for which they are an admin
        removed_admin_areas = admin_thrust_area_ids - selected_thrust_area_ids
        if removed_admin_areas:
            # Get the names of the thrust areas that can't be removed
            restricted_areas = [area.name for area in admin_thrust_areas if str(area.id) in removed_admin_areas]
            areas_list = ", ".join(restricted_areas)
            
            message = (
                f"Unable to update faculty profile. {user.name} is currently serving as the Thrust Area "
                f"Administrator for: {areas_list}. To modify these thrust area assignments, please first "
                "reassign the administrative role to another faculty member in the Thrust Area Management section."
            )
            flash(message, "danger")
            return redirect(url_for("manage_users"))

        # Update user details
        user.name = request.form["name"]
        user.short_form = request.form["short_form"]
        user.email = request.form["email"]
        user.mobile = request.form["mobile"]

        # Update thrust areas
        user.thrust_areas = []
        for area_id in selected_thrust_area_ids:
            area = ThrustArea.query.get(area_id)
            if area:
                user.thrust_areas.append(area)

        db.session.commit()
        flash("Faculty profile updated successfully", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error updating faculty profile: {str(e)}", "error")

    return redirect(url_for("manage_users"))

@app.route("/delete-faculty/<int:user_id>")
@role_required(["admin"])
def delete_faculty(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            flash("Faculty not found", "error")
            return redirect(url_for("manage_users"))

        # Check if user has faculty role
        faculty_role = Role.query.filter_by(name="faculty").first()
        if faculty_role not in user.roles:
            flash("User is not a faculty member", "error")
            return redirect(url_for("manage_users"))

        # Delete related records
        CourseAssignment.query.filter_by(faculty_id=user.id).delete()
        
        # Remove thrust area associations
        user.thrust_areas = []
        
        # Delete the user
        db.session.delete(user)
        db.session.commit()
        
        flash("Faculty deleted successfully", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting faculty: {str(e)}", "error")

    return redirect(url_for("manage_users"))


@app.route("/manage-users")
@role_required(["admin"])
def manage_users():
    # Get all faculty users with their administered thrust areas
    users = User.query.join(User.roles).filter(Role.name == 'faculty').all()
    
    # Add administered_thrust_areas to each user
    for user in users:
        user.administered_thrust_areas = ThrustArea.query.join(ThrustAreaAdmin).filter(ThrustAreaAdmin.user_id == user.id).all()
    
    thrust_areas = ThrustArea.query.all()
    return render_template(
        "admin/manage_users.html",
        base_template='base/admin_base.html',
        users=users,
        thrust_areas=thrust_areas
    )

@app.route("/add-user", methods=["POST"])
@role_required(["admin"])
def add_user():
    try:
        # Create user with faculty role
        user_data = {
            "username": request.form["username"],
            "password": request.form["password"],
            "name": request.form["name"],
            "email": request.form["email"],
            "mobile": request.form["mobile"],
            "short_form": request.form["short_form"],
            "roles": ["faculty"]
        }
        
        user = DatabaseManager.add_user(**user_data)
        
        # Add thrust areas
        thrust_area_ids = request.form.getlist("thrust_area_ids")
        for area_id in thrust_area_ids:
            area = ThrustArea.query.get(area_id)
            if area:
                user.thrust_areas.append(area)
        
        db.session.commit()
        flash("Faculty added successfully", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding faculty: {str(e)}", "error")
    
    return redirect(url_for("manage_users"))

#
@app.route("/manage-thrust-areas", methods=["GET"])
@role_required(["admin"])
def manage_thrust_areas():
    # Get thrust areas with their admins
    thrust_areas = ThrustArea.query.all()
    for area in thrust_areas:
        area.admins = User.query.join(ThrustAreaAdmin).filter(ThrustAreaAdmin.thrust_area_id == area.id).all()
    
    faculty = User.query.join(User.roles).filter(Role.name == "faculty").all()
    return render_template(
        "admin/manage_thrust_areas.html",
        base_template='base/admin_base.html',
        thrust_areas=thrust_areas,
        faculty=faculty
    )

@app.route("/get-faculty-for-thrust/<int:thrust_area_id>")
@role_required(["admin"])
def get_faculty_for_thrust(thrust_area_id):
    try:
        thrust_area = ThrustArea.query.get(thrust_area_id)
        if not thrust_area:
            return "Thrust area not found", 404
        
        # Get faculty members who have this thrust area but are not admins elsewhere
        faculty_members = User.query.join(User.roles)\
            .filter(Role.name == "faculty")\
            .filter(User.thrust_areas.any(id=thrust_area_id))\
            .outerjoin(ThrustAreaAdmin)\
            .filter(
                # Either no admin assignment or admin of this thrust area
                (ThrustAreaAdmin.user_id == None) | 
                (ThrustAreaAdmin.thrust_area_id == thrust_area_id)
            )\
            .all()
        
        return render_template(
            "admin/_faculty_options.html",
            faculty_members=faculty_members
        )
    except Exception as e:
        return str(e), 500


@app.route("/assign-thrust-admin", methods=["POST"])
@role_required(["admin"])
def assign_thrust_admin():
    thrust_area_id = request.form.get("thrust_area_id")
    faculty_id = request.form.get("faculty_id")
    
    if not thrust_area_id or not faculty_id:
        flash("Please select both thrust area and faculty", "error")
        return redirect(url_for("manage_thrust_areas"))
    
    try:
        # Check if faculty is already an admin for another thrust area
        existing_admin_role = ThrustAreaAdmin.query.filter_by(user_id=faculty_id).first()
        if existing_admin_role and str(existing_admin_role.thrust_area_id) != thrust_area_id:
            flash("This faculty is already an admin for another thrust area", "error")
            return redirect(url_for("manage_thrust_areas"))

        # Check for existing admin of this thrust area
        existing_admin = ThrustAreaAdmin.query.filter_by(thrust_area_id=thrust_area_id).first()
        if existing_admin:
            # Remove thrust_area_admin role from existing admin
            old_admin = User.query.get(existing_admin.user_id)
            thrust_admin_role = Role.query.filter_by(name="thrust_area_admin").first()
            
            if thrust_admin_role in old_admin.roles:
                old_admin.roles.remove(thrust_admin_role)
            
            db.session.delete(existing_admin)
        
        # Assign new admin
        new_admin = ThrustAreaAdmin(thrust_area_id=thrust_area_id, user_id=faculty_id)
        db.session.add(new_admin)
        
        # Add thrust_area_admin role to new admin
        new_faculty = User.query.get(faculty_id)
        thrust_admin_role = Role.query.filter_by(name="thrust_area_admin").first()
        
        if thrust_admin_role not in new_faculty.roles:
            new_faculty.roles.append(thrust_admin_role)
        
        db.session.commit()
        flash("Thrust area admin assigned successfully", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error assigning thrust area admin: {str(e)}", "error")
    
    return redirect(url_for("manage_thrust_areas"))
    

@app.route("/add-thrust-area", methods=["GET", "POST"])
@role_required(["admin"])
def add_thrust_area():
    if request.method == "POST":
        new_name = request.form.get("name")
        new_description = request.form.get("description")
        
        try:
            thrust_area = ThrustArea(name=new_name, description=new_description)
            db.session.add(thrust_area)
            db.session.commit()
            flash("Thrust area added successfully!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding thrust area: {str(e)}", "error")
        
        return redirect(url_for("manage_thrust_areas"))
    
    return render_template("admin/add_thrust_area.html",base_template='base/admin_base.html')


@app.route("/manage-courses")
@role_required(["admin"])
def manage_courses():
    try:
        # Modified query to properly handle grouping
        teaching_schemes = db.session.query(
            Course.semester,
            CourseAssignment.academic_year,
            db.func.group_concat(Program.name.distinct()).label('program_names'),
            db.func.min(Course.id).label('id')  # Using min() to get a representative ID
        ).join(
            CourseProgram, Course.id == CourseProgram.course_id
        ).join(
            Program, CourseProgram.program_id == Program.id
        ).join(
            CourseAssignment, Course.id == CourseAssignment.course_id
        ).group_by(
            Course.semester,
            CourseAssignment.academic_year
        ).all()

        # Format the data for template
        formatted_schemes = []
        for scheme in teaching_schemes:
            programs = [{'name': name.strip()} for name in scheme.program_names.split(',')]
            formatted_schemes.append({
                'id': scheme.id,
                'semester': scheme.semester,
                'academic_year': scheme.academic_year,
                'programs': programs
            })

        return render_template(
            "admin/manage_courses.html",
            teaching_schemes=formatted_schemes,
            base_template='base/admin_base.html'
        )
    except Exception as e:
        flash(f'Error loading teaching schemes: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route("/create-teaching-scheme")
@role_required(["admin"])
def create_teaching_scheme():
    programs = Program.query.all()
    thrust_areas = ThrustArea.query.all()
    return render_template(
        "admin/create_teaching_scheme.html",
        programs=programs,
        thrust_areas=thrust_areas,
        base_template='base/admin_base.html'
    )

@app.route("/modify-teaching-scheme/<int:scheme_id>")
@role_required(["admin"])
def modify_teaching_scheme(scheme_id):
    try:
        # Get the course and its assignments
        course = Course.query.get_or_404(scheme_id)
        assignment = CourseAssignment.query.filter_by(course_id=scheme_id).first()
        
        # Get all programs associated with this course
        programs = Program.query.join(CourseProgram).filter(CourseProgram.course_id == scheme_id).all()
        
        # Get all available thrust areas
        thrust_areas = ThrustArea.query.all()
        
        return render_template(
            "admin/modify_teaching_scheme.html",
            base_template='base/admin_base.html',
            course=course,
            assignment=assignment,
            programs=programs,
            thrust_areas=thrust_areas,
            academic_year=assignment.academic_year if assignment else None,
            semester=course.semester
        )
    except Exception as e:
        flash(f'Error loading teaching scheme: {str(e)}', 'error')
        return redirect(url_for('manage_courses'))

@app.route("/update-teaching-scheme/<int:scheme_id>", methods=['POST'])
@role_required(["admin"])
def update_teaching_scheme(scheme_id):
    try:
        course = Course.query.get_or_404(scheme_id)
        
        # Update course details
        course.code = request.form['code']
        course.name = request.form['name']
        course.thrust_area_id = request.form['thrust_area_id']
        course.semester = int(request.form['semester'])
        course.lectures = int(request.form['lectures'])
        course.tutorials = int(request.form['tutorials'])
        course.practicals = int(request.form['practicals'])
        course.credits = int(request.form['credits'])
        course.see_duration = int(request.form['see_duration'])
        course.ce_weightage = float(request.form['ce_weightage'])
        course.lpw_weightage = float(request.form['lpw_weightage'])
        course.see_weightage = float(request.form['see_weightage'])
        course.description = request.form.get('description', '')

        # Update program associations
        course.programs = []
        program_ids = request.form.getlist('program_ids')
        for program_id in program_ids:
            program = Program.query.get(program_id)
            if program:
                course.programs.append(program)

        # Update assignment if it exists
        assignment = CourseAssignment.query.filter_by(course_id=scheme_id).first()
        if assignment:
            assignment.academic_year = request.form['academic_year']

        db.session.commit()
        flash('Teaching scheme updated successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating teaching scheme: {str(e)}', 'error')
    
    return redirect(url_for('manage_courses'))

@app.route("/get-teaching-scheme/<int:scheme_id>")
@role_required(["admin"])
def get_teaching_scheme(scheme_id):
    try:
        course = Course.query.get_or_404(scheme_id)
        assignment = CourseAssignment.query.filter_by(course_id=scheme_id).first()
        
        return jsonify({
            'success': True,
            'course': {
                'id': course.id,
                'code': course.code,
                'name': course.name,
                'thrust_area_id': course.thrust_area_id,
                'semester': course.semester,
                'lectures': course.lectures,
                'tutorials': course.tutorials,
                'practicals': course.practicals,
                'credits': course.credits,
                'see_duration': course.see_duration,
                'ce_weightage': course.ce_weightage,
                'lpw_weightage': course.lpw_weightage,
                'see_weightage': course.see_weightage,
                'description': course.description,
                'program_ids': [p.id for p in course.programs],
                'academic_year': assignment.academic_year if assignment else None
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route("/delete-teaching-scheme/<int:scheme_id>", methods=['POST'])
@role_required(["admin"])
def delete_teaching_scheme(scheme_id):
    try:
        # Get the course and its assignments
        course = Course.query.get_or_404(scheme_id)
        
        # Delete related records in the correct order
        CourseAssignment.query.filter_by(course_id=scheme_id).delete()
        CourseProgram.query.filter_by(course_id=scheme_id).delete()
        
        # Finally delete the course
        db.session.delete(course)
        db.session.commit()
        
        flash('Teaching scheme deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting teaching scheme: {str(e)}', 'error')
    
    return redirect(url_for('manage_courses'))

@app.route("/add-course", methods=["POST"])
@role_required(["admin"])
def add_course():
    try:
        program_ids = request.form.getlist('program_ids')
        semester = request.form.get('semester')
        academic_year = request.form.get('academic_year')

        course = Course(
            code=request.form['code'],
            name=request.form['name'],
            thrust_area_id=request.form['thrust_area_id'],
            semester=int(request.form['semester']) if request.form.get('semester') else None,
            lectures=int(request.form['lectures']),
            tutorials=int(request.form['tutorials']),
            practicals=int(request.form['practicals']),
            credits=int(request.form['credits']),
            see_duration=int(request.form['see_duration']),
            ce_weightage=float(request.form['ce_weightage']),
            lpw_weightage=float(request.form['lpw_weightage']),
            see_weightage=float(request.form['see_weightage']),
            description=request.form.get('description', '')
        )

        db.session.add(course)
        db.session.flush()  # Get course ID before commit

        for program_id in program_ids:
            course_program = CourseProgram(course_id=course.id, program_id=program_id)
            db.session.add(course_program)

        db.session.commit()
        return str(course.id), 200  # Return course ID

    except Exception as e:
        db.session.rollback()
        return str(e), 400

      

@app.route("/edit-course", methods=["POST"])
@role_required(["admin"])
def edit_course():
    try:
        course = Course.query.get(request.form['course_id'])
        if course:
            course.code = request.form['code']
            course.name = request.form['name']
            course.thrust_area_id = request.form['thrust_area_id']
            course.semester = int(request.form['semester'])
            course.lectures = int(request.form['lectures'])
            course.tutorials = int(request.form['tutorials'])
            course.practicals = int(request.form['practicals'])
            course.credits = int(request.form['credits'])
            course.see_duration = int(request.form['see_duration'])
            course.ce_weightage = float(request.form['ce_weightage'])
            course.lpw_weightage = float(request.form['lpw_weightage'])
            course.see_weightage = float(request.form['see_weightage'])
            course.description = request.form.get('description', '')

            db.session.commit()
            flash('Course updated successfully!', 'success')
        else:
            flash('Course not found!', 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating course: {str(e)}', 'error')
    return redirect(url_for('manage_courses'))


@app.route("/delete-course/<int:course_id>", methods=["DELETE"])
@role_required(["admin"])
def delete_course(course_id):
    try:
        course = Course.query.get_or_404(course_id)

        # Delete related records first
        CourseProgram.query.filter_by(course_id=course_id).delete()
        CourseAssignment.query.filter_by(course_id=course_id).delete()

        # Delete the course
        db.session.delete(course)
        db.session.commit()

        return "Course deleted successfully", 200
    except Exception as e:
        db.session.rollback()
        return str(e), 400


# Modify the route in app.py
@app.route('/get-programs')
@role_required(["admin"])
def get_programs():
    try:
        programs = Program.query.all()
        return jsonify({
            'success': True,
            'programs': [{
                'id': program.id,
                'name': program.name,
                'code': program.code,
                'level': program.level,
                'specialization': program.specialization
            } for program in programs]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get-program-courses/<int:program_id>')
@role_required(["admin"])
def get_program_courses(program_id):
    try:
        # Fetch courses associated with the selected program
        courses = Course.query.join(CourseProgram).filter(CourseProgram.program_id == program_id).all()
        
        response_data = {
            'success': True,
            'courses': [{
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'credits': course.credits,
                'description': course.description,
                'thrust_area': course.thrust_area.name if course.thrust_area else None,
                'thrust_area_admin': [admin.name for admin in User.query.join(ThrustAreaAdmin).filter(ThrustAreaAdmin.thrust_area_id == course.thrust_area_id).all()] if course.thrust_area else []
            } for course in courses]
        }
        return jsonify(response_data)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Update your existing assign_course route
@app.route("/assign-course")
@role_required(["admin"])
def assign_course():
    course_id = request.args.get('course_id')
    program_ids = request.args.getlist('program_ids')
    semester = request.args.get('semester')
    academic_year = request.args.get('academic_year')
    
    if not all([course_id, program_ids, semester, academic_year]):
        flash("Missing required parameters", "error")
        return redirect(url_for("manage_courses"))
    
    course = Course.query.get(course_id)
    if not course:
        flash("Course not found", "error")
        return redirect(url_for("manage_courses"))
    
    # Get faculty members who are associated with the course's thrust area
    faculties = User.query.join(User.roles)\
        .join(FacultyThrustArea)\
        .filter(Role.name == 'faculty')\
        .filter(FacultyThrustArea.thrust_area_id == course.thrust_area_id)\
        .distinct().all()
    
    # Get thrust area admin for this course's thrust area
    thrust_area_admin = User.query.join(ThrustAreaAdmin)\
        .filter(ThrustAreaAdmin.thrust_area_id == course.thrust_area_id)\
        .first()
    
    programs = Program.query.filter(Program.id.in_(program_ids)).all()
    
    return render_template(
        "admin/assign_course.html",
        base_template='base/admin_base.html',
        course=course,
        faculties=faculties,
        thrust_area_admin=thrust_area_admin,
        programs=programs,
        selected_program_ids=program_ids,
        selected_semester=semester,
        selected_academic_year=academic_year
    )


@app.route("/assign-course", methods=["POST"])
@role_required(["admin"])
def assign_course_post():
    try:
        course_id = request.form.get('course_id')
        program_ids = request.form.getlist('program_ids')
        semester = request.form.get('semester')
        academic_year = request.form.get('academic_year')
        assignment_type = request.form.get('assignment_type')
        
        if assignment_type == 'direct':
            faculty_id = request.form.get('faculty_id')
            if not faculty_id:
                flash("Please select a faculty member", "error")
                return redirect(url_for('assign_course', 
                    course_id=course_id, 
                    program_ids=program_ids,
                    semester=semester,
                    academic_year=academic_year))
                
            assignment = DatabaseManager.assign_course(
                course_id=course_id,
                semester=semester,
                academic_year=academic_year,
                assignment_type='direct',
                faculty_id=faculty_id
            )
        else:
            # For through_admin assignment, get the thrust area admin automatically
            course = Course.query.get(course_id)
            thrust_area_admin = User.query.join(ThrustAreaAdmin)\
                .filter(ThrustAreaAdmin.thrust_area_id == course.thrust_area_id)\
                .first()
                
            if not thrust_area_admin:
                flash("No thrust area admin found for this course", "error")
                return redirect(url_for('assign_course',
                    course_id=course_id,
                    program_ids=program_ids,
                    semester=semester,
                    academic_year=academic_year))
                
            assignment = DatabaseManager.assign_course(
                course_id=course_id,
                semester=semester,
                academic_year=academic_year,
                assignment_type='through_admin',
                thrust_area_admin_id=thrust_area_admin.id
            )
        
        if assignment:
            flash("Course assigned successfully!", "success")
            return redirect(url_for('manage_courses'))
        else:
            flash("Error assigning course", "error")
            
    except Exception as e:
        flash(f"Error: {str(e)}", "error")
        
    return redirect(url_for('assign_course',
        course_id=course_id,
        program_ids=program_ids,
        semester=semester,
        academic_year=academic_year))

@app.route("/syllabus-form")
@role_required(["faculty"])
def syllabus_form():
    user = User.query.get(session["user_id"])
    assignments = CourseAssignment.query.filter_by(faculty_id=user.id).all()
    return render_template("syllabus_form.html", assignments=assignments)

@app.route("/generate-syllabus", methods=["POST"])
@role_required(["faculty"])
def generate_syllabus():
    assignment_id = request.form.get("assignment_id")
    assignment = CourseAssignment.query.get(assignment_id)
    
    if not assignment:
        return jsonify({"error": "Invalid assignment"}), 400
    
    try:
        # Create syllabus document
        doc = Document("Syllabus_Template_with_Placeholders.docx")
        
        # Replace placeholders with form data
        for key, value in request.form.items():
            for paragraph in doc.paragraphs:
                if f"{{{key}}}" in paragraph.text:
                    paragraph.text = paragraph.text.replace(f"{{{key}}}", str(value))
        
        # Save to memory
        doc_stream = io.BytesIO()
        doc.save(doc_stream)
        doc_stream.seek(0)
        
        # Save to database
        syllabus = DatabaseManager.save_syllabus(
            assignment_id=assignment_id,
            content=doc_stream.getvalue(),
            file_name=f"syllabus_{assignment.course.code}_{datetime.now().strftime('%Y%m%d')}.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        
        if not syllabus:
            return jsonify({"error": "Error saving syllabus"}), 500
        
        # Return file to user
        doc_stream.seek(0)
        return send_file(
            doc_stream,
            mimetype=syllabus.mime_type,
            as_attachment=True,
            download_name=syllabus.file_name
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/view-syllabi")
@role_required(["admin", "thrust_area_admin"])
def view_syllabi():
    user = User.query.get(session["user_id"])
    
    if "admin" in session["roles"]:
        syllabi = Syllabus.query.all()
    else:
        admin_areas = ThrustArea.query.join(ThrustAreaAdmin).filter(ThrustAreaAdmin.user_id == user.id).all()
        syllabi = Syllabus.query.join(CourseAssignment).join(Course).filter(
            Course.thrust_area_id.in_([area.id for area in admin_areas])
        ).all()
    
    return render_template("view_syllabi.html", syllabi=syllabi)

@app.route("/download-syllabus/<int:syllabus_id>")
@role_required(["admin", "thrust_area_admin", "faculty"])
def download_syllabus(syllabus_id):
    syllabus = Syllabus.query.get_or_404(syllabus_id)
    
    # Check permissions
    user = User.query.get(session["user_id"])
    if "faculty" in session["roles"] and syllabus.assignment.faculty_id != user.id:
        return "Unauthorized", 403
    
    return send_file(
        io.BytesIO(syllabus.content),
        mimetype=syllabus.mime_type,
        as_attachment=True,
        download_name=syllabus.file_name
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/get-course-details/<int:course_id>")
@role_required(["admin"])
def get_course_details(course_id):
    try:
        course = Course.query.get_or_404(course_id)
        return jsonify({
            'success': True,
            'course': {
                'id': course.id,
                'code': course.code,
                'name': course.name,
                'thrust_area_id': course.thrust_area_id,
                'thrust_area': course.thrust_area.name if course.thrust_area else None,
                'semester': course.semester,
                'lectures': course.lectures,
                'tutorials': course.tutorials,
                'practicals': course.practicals,
                'credits': course.credits,
                'see_duration': course.see_duration,
                'ce_weightage': course.ce_weightage,
                'lpw_weightage': course.lpw_weightage,
                'see_weightage': course.see_weightage,
                'description': course.description
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route("/update-course/<int:course_id>", methods=["POST"])
@role_required(["admin"])
def update_course(course_id):
    try:
        course = Course.query.get_or_404(course_id)
        
        # Update course details
        course.code = request.form['code']
        course.name = request.form['name']
        course.thrust_area_id = request.form['thrust_area_id']
        course.semester = int(request.form['semester']) if request.form.get('semester') else None
        course.lectures = int(request.form['lectures'])
        course.tutorials = int(request.form['tutorials'])
        course.practicals = int(request.form['practicals'])
        course.credits = int(request.form['credits'])
        course.see_duration = int(request.form['see_duration'])
        course.ce_weightage = float(request.form['ce_weightage'])
        course.lpw_weightage = float(request.form['lpw_weightage'])
        course.see_weightage = float(request.form['see_weightage'])
        course.description = request.form.get('description', '')
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'course': {
                'code': course.code,
                'name': course.name,
                'thrust_area': course.thrust_area.name if course.thrust_area else None,
                'semester': course.semester,
                'lectures': course.lectures,
                'tutorials': course.tutorials,
                'practicals': course.practicals,
                'credits': course.credits,
                'see_duration': course.see_duration,
                'ce_weightage': course.ce_weightage,
                'lpw_weightage': course.lpw_weightage,
                'see_weightage': course.see_weightage,
                'description': course.description
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

def init_db():
    with app.app_context():
        # First, drop and recreate tables to ensure schema changes take effect

        db.create_all()
        
        # Create default roles with better error handling
        roles = ['admin', 'thrust_area_admin', 'faculty']
        for role_name in roles:
            try:
                if not Role.query.filter_by(name=role_name).first():
                    db.session.add(Role(name=role_name))
                    db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"Error creating role {role_name}: {str(e)}")
        
        # Create default admin with better security
        try:
            if not User.query.filter_by(username='admin').first():
                admin_user = User(
                    username='admin',
                    name='Administrator',
                    email='admin@example.com',
                    mobile='',  # Add empty string for nullable fields
                    short_form=''
                )
                admin_user.set_password(os.environ.get('ADMIN_PASSWORD', 'admin123'))
                admin_role = Role.query.filter_by(name='admin').first()
                if admin_role:
                    admin_user.roles.append(admin_role)
                    db.session.add(admin_user)
                    db.session.commit()
            
            DatabaseManager.initialize_programs()
            
        except Exception as e:
            db.session.rollback()
            print(f"Error during database initialization: {str(e)}")


if __name__ == '__main__':
    init_db()
    app.run(debug=True)