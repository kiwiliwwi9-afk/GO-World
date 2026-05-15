from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = "goworld-secret"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///go_world.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ========== МОДЕЛИ ==========
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(200))
    bio = db.Column(db.String(200), default="")
    interests = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    likes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship('User')

class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer)
    followed_id = db.Column(db.Integer)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    post_id = db.Column(db.Integer)

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
        password = generate_password_hash(request.form['password'])
        interests = request.form.getlist('interests')
        user = User(username=username, password=password, interests=','.join(interests))
        db.session.add(user)
        db.session.commit()
        flash('Регистрация успешна! Войдите', 'success')
        return redirect('/login')
    return render_template('register.html')

@app.route('/interests', methods=['GET', 'POST'])
def interests():
    if request.method == 'POST':
        interests = request.form.getlist('interests')
        if current_user.is_authenticated:
            current_user.interests = ','.join(interests)
            db.session.commit()
        return redirect('/feed')
    return render_template('interests.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect('/feed')
        flash('Неверное имя или пароль', 'danger')
    return render_template('login.html')

@app.route('/feed', methods=['GET', 'POST'])
@login_required
def feed():
    if request.method == 'POST':
        post = Post(text=request.form['text'], user_id=current_user.id)
        db.session.add(post)
        db.session.commit()
        flash('Пост опубликован!', 'success')
        return redirect('/feed')
    
    # Посты от подписок + свои
    following_ids = [f.followed_id for f in Follow.query.filter_by(follower_id=current_user.id).all()]
    following_ids.append(current_user.id)
    posts = Post.query.filter(Post.user_id.in_(following_ids)).order_by(Post.created_at.desc()).all()
    return render_template('feed.html', posts=posts)

@app.route('/like/<int:post_id>')
@login_required
def like(post_id):
    post = Post.query.get(post_id)
    if post:
        existing = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
        if existing:
            db.session.delete(existing)
            post.likes -= 1
        else:
            like = Like(user_id=current_user.id, post_id=post_id)
            db.session.add(like)
            post.likes += 1
        db.session.commit()
    return redirect('/feed')

@app.route('/profile')
@login_required
def profile():
    posts = Post.query.filter_by(user_id=current_user.id).order_by(Post.created_at.desc()).all()
    return render_template('profile.html', posts=posts)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio = request.form['bio']
        db.session.commit()
        flash('Профиль обновлён!', 'success')
        return redirect('/profile')
    return render_template('edit_profile.html')

@app.route('/follow/<int:user_id>')
@login_required
def follow(user_id):
    if user_id != current_user.id:
        existing = Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first()
        if not existing:
            follow = Follow(follower_id=current_user.id, followed_id=user_id)
            db.session.add(follow)
            db.session.commit()
    return redirect('/profile')

@app.route('/logout')
def logout():
    logout_user()
    return redirect('/')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)