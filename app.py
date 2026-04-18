from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'sekretnyi-klyuch-go-world'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///go_world.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
    
    def get_posts(self):
        return Post.query.filter_by(user_id=self.id).order_by(Post.created_at.desc()).all()

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    likes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    author = db.relationship('User', backref=db.backref('posts', lazy=True))

class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, nullable=False)
    followed_id = db.Column(db.Integer, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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
            flash('Имя уже занято', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email уже используется', 'danger')
            return redirect(url_for('register'))
        
        hashed = generate_password_hash(password)
        user = User(username=username, email=email, password=hashed)
        db.session.add(user)
        db.session.commit()
        
        flash('Регистрация успешна! Войдите', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash(f'Добро пожаловать, {username}!', 'success')
            return redirect(url_for('feed'))
        else:
            flash('Неверное имя или пароль', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли', 'info')
    return redirect(url_for('index'))

@app.route('/feed')
@login_required
def feed():
    # Получаем посты от тех, на кого подписан
    followed_ids = [f.followed_id for f in Follow.query.filter_by(follower_id=current_user.id).all()]
    followed_ids.append(current_user.id)
    posts = Post.query.filter(Post.user_id.in_(followed_ids)).order_by(Post.created_at.desc()).all()
    return render_template('feed.html', posts=posts)

@app.route('/post', methods=['POST'])
@login_required
def create_post():
    content = request.form['content']
    if content:
        post = Post(user_id=current_user.id, content=content)
        db.session.add(post)
        db.session.commit()
        flash('Пост опубликован!', 'success')
    return redirect(url_for('feed'))

@app.route('/like/<int:post_id>')
@login_required
def like(post_id):
    post = Post.query.get_or_404(post_id)
    post.likes += 1
    db.session.commit()
    return redirect(url_for('feed'))

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
    user = User.query.filter_by(username=username).first_or_404()
    if user.id != current_user.id:
        existing = Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first()
        if not existing:
            follow = Follow(follower_id=current_user.id, followed_id=user.id)
            db.session.add(follow)
            db.session.commit()
            flash(f'Вы подписались на {username}', 'success')
    return redirect(url_for('profile', username=username))

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first_or_404()
    follow = Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first()
    if follow:
        db.session.delete(follow)
        db.session.commit()
        flash(f'Вы отписались от {username}', 'info')
    return redirect(url_for('profile', username=username))
    @app.route('/search')
@login_required
def search():
    query = request.args.get('q', '')
    users = User.query.filter(User.username.contains(query)).all() if query else []
    return render_template('search.html', users=users, query=query)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
