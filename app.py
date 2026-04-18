from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import aiohttp
import asyncio

app = Flask(__name__)
app.secret_key = 'sekretnyi-klyuch-go-world'

# База данных
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
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_online = db.Column(db.Boolean, default=False)
    
    def get_posts(self):
        return Post.query.filter_by(user_id=self.id).order_by(Post.created_at.desc()).all()

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(200), nullable=True)
    likes = db.Column(db.Integer, default=0)
    views = db.Column(db.Integer, default=0)
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ========== ОНЛАЙН-СТАТУС ==========
@app.before_request
def update_last_seen():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        current_user.is_online = True
        db.session.commit()

# ========== ФУНКЦИЯ ДЛЯ МАРГО ==========
GROQ_KEY = os.environ.get("GROQ_KEY")

async def ask_groq_for_web(question, username):
    if not GROQ_KEY:
        return "🤍 марGO пока не настроена"
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": f"Пользователь {username} спрашивает: {question}. Ответь кратко и дружелюбно, как марGO."}],
        "max_tokens": 300,
        "temperature": 0.8
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, headers=headers, json=payload, timeout=30) as r:
                if r.status == 200:
                    data = await r.json()
                    return data['choices'][0]['message']['content']
                return "Извини, я сейчас не могу ответить 🤍"
    except:
        return "Ошибка подключения 🤍"

# ========== ОСНОВНЫЕ РОУТЫ ==========
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
            user.is_online = True
            db.session.commit()
            flash(f'Добро пожаловать, {username}!', 'success')
            return redirect(url_for('feed'))
        else:
            flash('Неверное имя или пароль', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    current_user.is_online = False
    db.session.commit()
    logout_user()
    flash('Вы вышли', 'info')
    return redirect(url_for('index'))

# ========== ЛЕНТА И ПОСТЫ ==========
@app.route('/feed')
@login_required
def feed():
    followed_ids = [f.followed_id for f in Follow.query.filter_by(follower_id=current_user.id).all()]
    followed_ids.append(current_user.id)
    posts = Post.query.filter(Post.user_id.in_(followed_ids)).order_by(Post.created_at.desc()).all()
    
    for post in posts:
        post.views += 1
        post.is_following = Follow.query.filter_by(
            follower_id=current_user.id, 
            followed_id=post.user_id
        ).first() is not None
        post.user_liked = Like.query.filter_by(user_id=current_user.id, post_id=post.id).first() is not None
        post.is_author = (post.user_id == current_user.id)
    db.session.commit()
    
    return render_template('feed.html', posts=posts)

@app.route('/post', methods=['POST'])
@login_required
def create_post():
    content = request.form['content']
    image = None
    
    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{current_user.id}_{int(datetime.utcnow().timestamp())}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image = f"/static/uploads/{filename}"
    
    if content:
        post = Post(user_id=current_user.id, content=content, image=image)
        db.session.add(post)
        db.session.commit()
        flash('Пост опубликован!', 'success')
    return redirect(url_for('feed'))

@app.route('/like/<int:post_id>')
@login_required
def like(post_id):
    post = Post.query.get_or_404(post_id)
    
    existing_like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    
    if existing_like:
        db.session.delete(existing_like)
        post.likes -= 1
    else:
        new_like = Like(user_id=current_user.id, post_id=post_id)
        db.session.add(new_like)
        post.likes += 1
    
    db.session.commit()
    return redirect(request.referrer or url_for('feed'))

@app.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id:
        flash('Это не твой пост!', 'danger')
        return redirect(url_for('feed'))
    
    if request.method == 'POST':
        content = request.form['content']
        if content:
            post.content = content
            
            if 'image' in request.files:
                file = request.files['image']
                if file and allowed_file(file.filename):
                    if post.image and post.image.startswith('/static/uploads/'):
                        old_path = post.image[1:]
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    
                    filename = secure_filename(f"{current_user.id}_{int(datetime.utcnow().timestamp())}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    post.image = f"/static/uploads/{filename}"
            
            db.session.commit()
            flash('Пост обновлён!', 'success')
            return redirect(url_for('feed'))
    
    return render_template('edit_post.html', post=post)

@app.route('/delete_post/<int:post_id>')
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id:
        flash('Это не твой пост!', 'danger')
        return redirect(url_for('feed'))
    
    if post.image and post.image.startswith('/static/uploads/'):
        old_path = post.image[1:]
        if os.path.exists(old_path):
            os.remove(old_path)
    
    db.session.delete(post)
    db.session.commit()
    flash('Пост удалён', 'info')
    return redirect(url_for('feed'))

# ========== ПРОФИЛИ И ПОДПИСКИ ==========
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
    
    next_page = request.args.get('next', 'feed')
    return redirect(url_for(next_page))

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first_or_404()
    follow = Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first()
    if follow:
        db.session.delete(follow)
        db.session.commit()
        flash(f'Вы отписались от {username}', 'info')
    
    next_page = request.args.get('next', 'feed')
    return redirect(url_for(next_page))

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio = request.form['bio']
        
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{current_user.id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                current_user.avatar = f"/static/uploads/{filename}"
        
        db.session.commit()
        flash('Профиль обновлён!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    
    return render_template('edit_profile.html')

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old = request.form['old_password']
        new = request.form['new_password']
        if check_password_hash(current_user.password, old):
            current_user.password = generate_password_hash(new)
            db.session.commit()
            flash('Пароль изменён!', 'success')
            return redirect(url_for('profile', username=current_user.username))
        else:
            flash('Неверный старый пароль', 'danger')
    return render_template('change_password.html')

@app.route('/search')
@login_required
def search():
    query = request.args.get('q', '')
    users = []
    if query:
        users = User.query.filter(User.username.contains(query), User.id != current_user.id).limit(20).all()
    return render_template('search.html', users=users, query=query)

# ========== ЛИЧНЫЕ СООБЩЕНИЯ ==========
@app.route('/messages')
@login_required
def messages():
    sent = db.session.query(Message.receiver_id).filter_by(sender_id=current_user.id).distinct()
    received = db.session.query(Message.sender_id).filter_by(receiver_id=current_user.id).distinct()
    user_ids = set([r[0] for r in sent]) | set([r[0] for r in received])
    
    dialogs = []
    for uid in user_ids:
        user = User.query.get(uid)
        last_msg = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == uid)) |
            ((Message.sender_id == uid) & (Message.receiver_id == current_user.id))
        ).order_by(Message.created_at.desc()).first()
        
        unread_count = Message.query.filter_by(sender_id=uid, receiver_id=current_user.id, is_read=False).count()
        
        dialogs.append({
            'user': user,
            'last_message': last_msg,
            'unread_count': unread_count
        })
    
    dialogs.sort(key=lambda x: x['last_message'].created_at if x['last_message'] else datetime.min, reverse=True)
    return render_template('messages.html', dialogs=dialogs)

@app.route('/messages/<username>')
@login_required
def chat(username):
    other = User.query.filter_by(username=username).first_or_404()
    Message.query.filter_by(sender_id=other.id, receiver_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    
    messages_list = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == other.id)) |
        ((Message.sender_id == other.id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at.asc()).all()
    
    return render_template('chat.html', other=other, messages=messages_list)

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

# ========== API ДЛЯ МАРГО ==========
@app.route('/api/margo', methods=['POST'])
@login_required
def api_margo():
    data = request.get_json()
    question = data.get('question', '')
    username = current_user.username
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    answer = loop.run_until_complete(ask_groq_for_web(question, username))
    loop.close()
    
    return jsonify({'answer': answer})

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
