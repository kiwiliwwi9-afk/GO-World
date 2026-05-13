import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

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
    name = db.Column(db.String(80), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    avatar = db.Column(db.String(200), default='👤')
    bio = db.Column(db.String(300), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    from_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
        name = request.form['name']
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято', 'danger')
            return redirect(url_for('register'))
        
        hashed = generate_password_hash(password)
        user = User(name=name, username=username, password=hashed)
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
            flash(f'Добро пожаловать, {user.name}!', 'success')
            return redirect(url_for('feed'))
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
    followed_ids = [f.followed_id for f in Follow.query.filter_by(follower_id=current_user.id).all()]
    followed_ids.append(current_user.id)
    posts = Post.query.filter(Post.user_id.in_(followed_ids)).order_by(Post.created_at.desc()).all()
    for post in posts:
        post.is_liked = Like.query.filter_by(user_id=current_user.id, post_id=post.id).first() is not None
    notif_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    msg_count = Message.query.filter_by(receiver_id=current_user.id, is_read=False).count()
    return render_template('feed.html', posts=posts, notif_count=notif_count, msg_count=msg_count)

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
    existing = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if existing:
        db.session.delete(existing)
        post.likes -= 1
    else:
        new = Like(user_id=current_user.id, post_id=post_id)
        db.session.add(new)
        post.likes += 1
        if post.user_id != current_user.id:
            notif = Notification(user_id=post.user_id, type='like', from_user_id=current_user.id, post_id=post_id)
            db.session.add(notif)
    db.session.commit()
    return redirect(request.referrer or url_for('feed'))

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    is_following = Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first() is not None
    followers_count = Follow.query.filter_by(followed_id=user.id).count()
    following_count = Follow.query.filter_by(follower_id=user.id).count()
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).all()
    return render_template('profile.html', user=user, is_following=is_following, 
                          followers_count=followers_count, following_count=following_count, posts=posts)

@app.route('/follow/<username>')
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user.id != current_user.id:
        if not Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first():
            db.session.add(Follow(follower_id=current_user.id, followed_id=user.id))
            db.session.commit()
            notif = Notification(user_id=user.id, type='follow', from_user_id=current_user.id)
            db.session.add(notif)
            db.session.commit()
    return redirect(url_for('profile', username=username))

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first_or_404()
    follow = Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first()
    if follow:
        db.session.delete(follow)
        db.session.commit()
    return redirect(url_for('profile', username=username))

@app.route('/search')
@login_required
def search():
    query = request.args.get('q', '')
    users = User.query.filter(User.username.contains(query), User.id != current_user.id).limit(20).all() if query else []
    return render_template('search.html', users=users, query=query)

@app.route('/messages')
@login_required
def messages():
    dialogs = {}
    sent = Message.query.filter_by(sender_id=current_user.id).all()
    received = Message.query.filter_by(receiver_id=current_user.id).all()
    for msg in sent:
        dialogs[msg.receiver_id] = msg
    for msg in received:
        if msg.sender_id not in dialogs or dialogs[msg.sender_id].created_at < msg.created_at:
            dialogs[msg.sender_id] = msg
    dialog_list = []
    for uid, msg in sorted(dialogs.items(), key=lambda x: x[1].created_at, reverse=True):
        other = User.query.get(uid)
        unread = Message.query.filter_by(sender_id=uid, receiver_id=current_user.id, is_read=False).count()
        dialog_list.append({'user': other, 'last_msg': msg, 'unread': unread})
    return render_template('messages.html', dialogs=dialog_list)

@app.route('/messages/<username>')
@login_required
def chat(username):
    other = User.query.filter_by(username=username).first_or_404()
    Message.query.filter_by(sender_id=other.id, receiver_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    msgs = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == other.id)) |
        ((Message.sender_id == other.id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at.asc()).all()
    return render_template('chat.html', other=other, messages=msgs)

@app.route('/send_message/<username>', methods=['POST'])
@login_required
def send_message(username):
    other = User.query.filter_by(username=username).first_or_404()
    content = request.form['content']
    if content:
        msg = Message(sender_id=current_user.id, receiver_id=other.id, content=content)
        db.session.add(msg)
        db.session.commit()
    return redirect(url_for('chat', username=username))

@app.route('/notifications')
@login_required
def notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('notifications.html', notifications=notifs)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio = request.form['bio']
        db.session.commit()
        flash('Профиль обновлён!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    return render_template('edit_profile.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
