from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import requests

app = Flask(__name__)
app.secret_key = 'sekretnyi-klyuch-go-world'

# База данных (PostgreSQL или SQLite)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///go_world.db')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Загрузка файлов
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ========== МОДЕЛИ ==========
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    avatar = db.Column(db.String(200), default='/static/default-avatar.png')
    bio = db.Column(db.String(300), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship('User', backref=db.backref('posts', lazy=True))

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship('User', backref=db.backref('comments', lazy=True))

class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, nullable=False)
    followed_id = db.Column(db.Integer, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ========== МАРГО ==========
GROQ_KEY = os.environ.get("GROQ_KEY")

def ask_margo(question, username):
    if not GROQ_KEY:
        return "🤍 марGO пока не настроена"
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": f"Пользователь {username} спрашивает: {question}. Ответь кратко и дружелюбно."}],
        "max_tokens": 300
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content']
        return "🤍 марGO временно недоступна"
    except:
        return "🤍 Ошибка подключения"

# ========== РОУТЫ ==========
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Имя занято', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email занят', 'danger')
            return redirect(url_for('register'))
        user = User(username=username, email=email, password=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        flash('Регистрация успешна!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('feed'))
        flash('Неверные данные', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/feed')
@login_required
def feed():
    followed = [f.followed_id for f in Follow.query.filter_by(follower_id=current_user.id).all()]
    followed.append(current_user.id)
    posts = Post.query.filter(Post.user_id.in_(followed)).order_by(Post.created_at.desc()).all()
    for p in posts:
        p.likes_count = Like.query.filter_by(post_id=p.id).count()
        p.user_liked = Like.query.filter_by(user_id=current_user.id, post_id=p.id).first() is not None
        p.comments = Comment.query.filter_by(post_id=p.id).order_by(Comment.created_at.desc()).all()
    return render_template('feed.html', posts=posts)

@app.route('/post', methods=['POST'])
@login_required
def create_post():
    content = request.form['content']
    image = None
    if 'image' in request.files:
        f = request.files['image']
        if f and allowed_file(f.filename):
            filename = secure_filename(f"{current_user.id}_{int(datetime.utcnow().timestamp())}_{f.filename}")
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image = f"/static/uploads/{filename}"
    if content:
        db.session.add(Post(user_id=current_user.id, content=content, image=image))
        db.session.commit()
        flash('Пост опубликован!', 'success')
    return redirect(url_for('feed'))

@app.route('/like/<int:post_id>')
@login_required
def like(post_id):
    like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if like:
        db.session.delete(like)
    else:
        db.session.add(Like(user_id=current_user.id, post_id=post_id))
    db.session.commit()
    return redirect(request.referrer or url_for('feed'))

@app.route('/comment/<int:post_id>', methods=['POST'])
@login_required
def comment(post_id):
    text = request.form['text']
    if text:
        db.session.add(Comment(user_id=current_user.id, post_id=post_id, text=text))
        db.session.commit()
    return redirect(request.referrer or url_for('feed'))

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    is_following = Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first() is not None
    followers_count = Follow.query.filter_by(followed_id=user.id).count()
    following_count = Follow.query.filter_by(follower_id=user.id).count()
    return render_template('profile.html', user=user, is_following=is_following, followers_count=followers_count, following_count=following_count)

@app.route('/follow/<username>')
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first()
    if user and user.id != current_user.id:
        if not Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first():
            db.session.add(Follow(follower_id=current_user.id, followed_id=user.id))
            db.session.commit()
    return redirect(request.referrer or url_for('feed'))

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first()
    if user:
        Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).delete()
        db.session.commit()
    return redirect(request.referrer or url_for('feed'))

@app.route('/search')
@login_required
def search():
    q = request.args.get('q', '')
    users = User.query.filter(User.username.contains(q), User.id != current_user.id).limit(20).all() if q else []
    return render_template('search.html', users=users, query=q)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio = request.form['bio']
        if 'avatar' in request.files:
            f = request.files['avatar']
            if f and allowed_file(f.filename):
                filename = secure_filename(f"{current_user.id}_{f.filename}")
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                current_user.avatar = f"/static/uploads/{filename}"
        db.session.commit()
        flash('Профиль обновлён', 'success')
        return redirect(url_for('profile', username=current_user.username))
    return render_template('edit_profile.html')

@app.route('/api/margo', methods=['POST'])
@login_required
def api_margo():
    data = request.get_json()
    answer = ask_margo(data.get('question', ''), current_user.username)
    return jsonify({'answer': answer})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
