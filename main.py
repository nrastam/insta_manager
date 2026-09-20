import os
import json
import time
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from instagrapi import Client

app = Flask(__name__)
app.secret_key = os.urandom(24)

DATA_FILE = os.path.join('data', 'not_following_back.json')
cl = Client()

def load_targets():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return []

def save_targets(targets):
    with open(DATA_FILE, 'w') as f:
        json.dump(targets, f, indent=2)

def login_instagram():
    username = os.getenv('INSTA_USERNAME')
    password = os.getenv('INSTA_PASSWORD')
    if not username or not password:
        raise ValueError('Instagram credentials not set in environment variables')
    cl.login(username, password)

def _to_dict(obj):
    """Convert a list of objects (User or dict) to dict keyed by pk."""
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, list):
        result = {}
        for item in obj:
            if isinstance(item, dict):
                pk = item.get('pk')
            else:
                pk = getattr(item, 'pk', None)
            if pk is not None:
                result[pk] = item
        return result
    # fallback: try to treat as dict-like
    try:
        return dict(obj)
    except Exception:
        return {}

def get_not_following_back():
    login_instagram()
    user_id = cl.user_id_from_username(cl.username)
    following_raw = cl.user_following(user_id, amount=0)  # dict or list?
    followers_raw = cl.user_followers(user_id, amount=0)
    following = _to_dict(following_raw)
    followers = _to_dict(followers_raw)
    not_following_back = [user for uid, user in following.items() if uid not in followers]
    result = [{'pk': uid, 'username': user.username, 'full_name': user.full_name} for uid, user in not_following_back.items()]
    save_targets(result)
    return result

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        expected_user = os.getenv('FRONTEND_USERNAME', 'admin')
        expected_pass = os.getenv('FRONTEND_PASSWORD', 'admin')
        if username == expected_user and password == expected_pass:
            session['logged_in'] = True
            flash('Ingelogd', 'success')
            return redirect(url_for('index'))
        else:
            flash('Ongeldige gebruikersnaam of wachtwoord', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    insta_user = os.getenv('INSTA_USERNAME')
    insta_pass_set = bool(os.getenv('INSTA_PASSWORD'))
    targets = session.get('targets', [])
    return render_template('index.html', targets=targets, insta_user=insta_user, insta_pass_set=insta_pass_set)

@app.route('/refresh', methods=['POST'])
@login_required
def refresh():
    try:
        targets = get_not_following_back()
        session['targets'] = targets
        return jsonify({
            'success': True,
            'message': f'Lijst vernieuwd: {len(targets)} accounts gevonden'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/unfollow/<pk>', methods=['POST'])
@login_required
def unfollow(pk):
    try:
        login_instagram()
        cl.user_unfollow(pk)
        flash(f'Unfollowed user {pk}', 'success')
        # remove from list
        targets = session.get('targets', [])
        targets = [t for t in targets if t['pk'] != pk]
        session['targets'] = targets
        time.sleep(5)  # simple rate limit
    except Exception as e:
        flash(f'Error unfollowing: {e}', 'danger')
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)