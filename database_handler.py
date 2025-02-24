from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)  # Increased from default length
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True)
    mobile = db.Column(db.String(20))
    short_form = db.Column(db.String(10))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    roles = db.relationship('Role', secondary='user_roles', backref=db.backref('users', lazy='dynamic'))
    thrust_areas = db.relationship('ThrustArea', secondary='faculty_thrust_areas', backref=db.backref('faculty_members', lazy='dynamic'))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    thrust_area_id = db.Column(db.Integer, db.ForeignKey('thrust_areas.id'))
    semester = db.Column(db.Integer)
    # Teaching Scheme
    lectures = db.Column(db.Integer)  # L
    tutorials = db.Column(db.Integer)  # T
    practicals = db.Column(db.Integer)  # P
    credits = db.Column(db.Integer)  # C
    # Examination Scheme
    see_duration = db.Column(db.Integer)  # SEE Duration Hours
    ce_weightage = db.Column(db.Float)  # CE Component Weightage
    lpw_weightage = db.Column(db.Float)  # LPW Component Weightage
    see_weightage = db.Column(db.Float)  # SEE Component Weightage
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    programs = db.relationship('Program', secondary='course_programs', backref=db.backref('courses', lazy='dynamic'))
    thrust_area = db.relationship('ThrustArea', backref='courses')

class Program(db.Model):
    __tablename__ = 'programs'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    level = db.Column(db.String(20), nullable=False)  # 'btech', 'mtech', 'integrated', 'mca'
    specialization = db.Column(db.String(100))  # For programs like CSE in Cybersecurity
    is_dual_degree = db.Column(db.Boolean, default=False)  # For 2+2 or BTech+MBA programs
    duration_years = db.Column(db.Integer, nullable=False)  # 4 for BTech, 2 for MTech, 5 for Integrated, etc.
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class UserRole(db.Model):
    __tablename__ = 'user_roles'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), primary_key=True)

class ThrustArea(db.Model):
    __tablename__ = 'thrust_areas'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ThrustAreaAdmin(db.Model):
    __tablename__ = 'thrust_area_admins'
    thrust_area_id = db.Column(db.Integer, db.ForeignKey('thrust_areas.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

class CourseAssignment(db.Model):
    __tablename__ = 'course_assignments'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    thrust_area_admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    semester = db.Column(db.String(20), nullable=False)
    academic_year = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, assigned, completed
    assignment_type = db.Column(db.String(20), nullable=False)  # direct, through_admin

    course = db.relationship('Course', backref='assignments')
    faculty = db.relationship('User', foreign_keys=[faculty_id], backref='faculty_assignments')
    thrust_area_admin = db.relationship('User', foreign_keys=[thrust_area_admin_id], backref='admin_assignments')

class Syllabus(db.Model):
    __tablename__ = 'syllabi'
    id = db.Column(db.Integer, primary_key=True)
    course_assignment_id = db.Column(db.Integer, db.ForeignKey('course_assignments.id'))
    content = db.Column(db.LargeBinary)
    file_name = db.Column(db.String(255))
    mime_type = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CourseProgram(db.Model):
    __tablename__ = 'course_programs'
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id'), primary_key=True)

class FacultyThrustArea(db.Model):
    __tablename__ = 'faculty_thrust_areas'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    thrust_area_id = db.Column(db.Integer, db.ForeignKey('thrust_areas.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'thrust_area_id'),)



# Database operations class
class DatabaseManager:
    @staticmethod
    def init_app(app):
        db.init_app(app)
        
    @staticmethod
    def create_tables():
        db.create_all()
    
    @classmethod  # Changed from @staticmethod to @classmethod
    def add_user(cls, username, password, name, email=None, mobile=None, short_form=None, roles=None, thrust_area_ids=None):
        try:
            # Check if username already exists
            if User.query.filter_by(username=username).first():
                return None
            
            # Create new user
            user = User(
                username=username,
                name=name,
                email=email,
                mobile=mobile,
                short_form=short_form
            )
            user.set_password(password)
            
            # Add roles
            if roles:
                for role_name in roles:
                    role = Role.query.filter_by(name=role_name).first()
                    if role:
                        user.roles.append(role)
            
            # If user is faculty and thrust areas are provided, create associations
            if roles and "faculty" in roles and thrust_area_ids:
                for thrust_area_id in thrust_area_ids:
                    thrust_area = ThrustArea.query.get(thrust_area_id)
                    if thrust_area:
                        user.thrust_areas.append(thrust_area)
            
            db.session.add(user)
            db.session.commit()
            return user
        except IntegrityError:
            db.session.rollback()
            return None
    
    @staticmethod
    def assign_thrust_area_admin(user_id, thrust_area_id):
        try:
            admin = ThrustAreaAdmin(
                thrust_area_id=thrust_area_id,
                user_id=user_id
            )
            db.session.add(admin)
            db.session.commit()
            return True
        except IntegrityError:
            db.session.rollback()
            return False
    
    @staticmethod
    def add_course(code, name, thrust_area_id, credits=None, description=None, program_ids=None):
        try:
            course = Course(
                code=code,
                name=name,
                thrust_area_id=thrust_area_id,
                credits=credits,
                description=description
            )
            db.session.add(course)
            db.session.commit()  # Commit to get the course ID
            
            # Associate the course with selected programs
            if program_ids:
                for program_id in program_ids:
                    association = CourseProgram(course_id=course.id, program_id=program_id)
                    db.session.add(association)

            db.session.commit()
            return course
        except IntegrityError:
            db.session.rollback()
            return None
    
    # Modify the assign_course method in DatabaseManager
    @staticmethod
    def assign_course(course_id, semester, academic_year, assignment_type, faculty_id=None, thrust_area_admin_id=None):
        try:
            assignment = CourseAssignment(
                course_id=course_id,
                semester=semester,
                academic_year=academic_year,
                assignment_type=assignment_type
            )
            
            if assignment_type == 'direct':
                if not faculty_id:
                    return None
                assignment.faculty_id = faculty_id
                assignment.status = 'assigned'
            else:
                if not thrust_area_admin_id:
                    return None
                assignment.thrust_area_admin_id = thrust_area_admin_id
                assignment.status = 'pending'
                
            db.session.add(assignment)
            db.session.commit()
            return assignment
        except Exception as e:
            db.session.rollback()
            print(f"Error assigning course: {str(e)}")
            return None
    
    @staticmethod
    def save_syllabus(assignment_id, content, file_name, mime_type):
        try:
            syllabus = Syllabus(
                course_assignment_id=assignment_id,
                content=content,
                file_name=file_name,
                mime_type=mime_type
            )
            db.session.add(syllabus)
            db.session.commit()
            return syllabus
        except IntegrityError:
            db.session.rollback()
            return None
    
    @staticmethod
    def add_program(name, level, description=None):
        try:
            program = Program(
                name=name,
                level=level,
                description=description
            )
            db.session.add(program)
            db.session.commit()
            return program
        except IntegrityError:
            db.session.rollback()
            return None

    @staticmethod
    def initialize_programs():
        """Initialize the default programs in the system"""
        default_programs = [
            {
                'name': 'M.Tech - CSE',
                'code': 'MTCSE',
                'level': 'mtech',
                'duration_years': 2,
                'description': 'Master of Technology in Computer Science and Engineering'
            },
            {
                'name': 'M.Tech - CSE in Cybersecurity',
                'code': 'MTCYBER',
                'level': 'mtech',
                'specialization': 'Cybersecurity',
                'duration_years': 2,
                'description': 'Master of Technology in Computer Science with Cybersecurity'
            },
            {
                'name': 'M.Tech - Data Science',
                'code': 'MTDS',
                'level': 'mtech',
                'duration_years': 2,
                'description': 'Master of Technology in Data Science'
            },
            {
                'name': 'B.Tech - CSE',
                'code': 'BTCSE',
                'level': 'btech',
                'duration_years': 4,
                'description': 'Bachelor of Technology in Computer Science and Engineering'
            },
            {
                'name': 'Integrated B.Tech - CSE + MBA',
                'code': 'BTCSEMBA',
                'level': 'integrated',
                'is_dual_degree': True,
                'duration_years': 5,
                'description': 'Integrated Bachelor of Technology in CSE with MBA'
            },
            {
                'name': 'B.Tech - 2+2 Dual Degree',
                'code': 'BT22',
                'level': 'btech',
                'is_dual_degree': True,
                'duration_years': 4,
                'description': 'Bachelor of Technology with 2+2 Dual Degree Program'
            },
            {
                'name': 'B.Tech - AI&ML',
                'code': 'BTAIML',
                'level': 'btech',
                'duration_years': 4,
                'description': 'Bachelor of Technology in Artificial Intelligence and Machine Learning'
            },
            {
                'name': 'MCA',
                'code': 'MCA',
                'level': 'mca',
                'duration_years': 2,
                'description': 'Master of Computer Applications'
            }
        ]
        
        try:
            for prog_data in default_programs:
                existing_program = Program.query.filter_by(code=prog_data['code']).first()
                if not existing_program:
                    program = Program(**prog_data)
                    db.session.add(program)
            
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Error initializing programs: {str(e)}")
            return False

    @staticmethod
    def get_programs_by_level(level):
        return Program.query.filter_by(level=level).all()

    @staticmethod
    def get_program_courses(program_id):
        return Course.query.filter_by(program_id=program_id).order_by(Course.semester).all()