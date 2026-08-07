import os
from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, Post, Subscription

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chaparita-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///seleneblack.db'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'jpg', 'jpeg', 'png', 'gif', 'webp'}

db.init_app(app)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    creators = User.query.filter_by(is_creator=True).all()
    return render_template('landing.html', creators=creators)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        is_creator = 'is_creator' in request.form
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email, is_creator=is_creator)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        
        flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile/<username>')
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(creator_id=user.id).order_by(Post.created_at.desc()).all()
    subscribed = False
    if current_user.is_authenticated and current_user.id != user.id:
        subscribed = Subscription.query.filter_by(
            subscriber_id=current_user.id, creator_id=user.id
        ).first() is not None
    return render_template('profile.html', user=user, posts=posts, subscribed=subscribed)

@app.route('/subscribe/<int:user_id>', methods=['POST'])
@login_required
def subscribe(user_id):
    if current_user.id == user_id:
        flash("You can't subscribe to yourself.", 'warning')
        return redirect(url_for('profile', username=User.query.get(user_id).username))
    
    existing = Subscription.query.filter_by(subscriber_id=current_user.id, creator_id=user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        flash('Unsubscribed.', 'info')
    else:
        sub = Subscription(subscriber_id=current_user.id, creator_id=user_id)
        db.session.add(sub)
        db.session.commit()
        flash('Subscribed!', 'success')
    
    return redirect(url_for('profile', username=User.query.get(user_id).username))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if not current_user.is_creator:
        flash('Only creators can upload content.', 'warning')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        is_premium = 'is_premium' in request.form
        file = request.files.get('media')
        
        if not file or file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for('upload'))
        
        if not allowed_file(file.filename):
            flash('Invalid file type.', 'danger')
            return redirect(url_for('upload'))
        
        filename = secure_filename(f"{current_user.id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        ext = filename.rsplit('.', 1)[1].lower()
        media_type = 'video' if ext in {'mp4', 'mov', 'avi'} else 'photo'
        
        post = Post(
            creator_id=current_user.id,
            title=title,
            description=description,
            media_type=media_type,
            media_path=filename,
            is_premium=is_premium
        )
        db.session.add(post)
        db.session.commit()
        
        flash('Content uploaded!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    
    return render_template('upload.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_creator:
        return redirect(url_for('index'))
    
    posts = Post.query.filter_by(creator_id=current_user.id).order_by(Post.created_at.desc()).all()
    subscriber_count = Subscription.query.filter_by(creator_id=current_user.id).count()
    return render_template('dashboard.html', posts=posts, subscriber_count=subscriber_count)

@app.route('/delete/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.creator_id != current_user.id:
        abort(403)
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], post.media_path)
    if os.path.exists(filepath):
        os.remove(filepath)
    
    db.session.delete(post)
    db.session.commit()
    flash('Post deleted.', 'info')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
