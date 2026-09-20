import os
import json
import time
import traceback
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

def get_not_following_back():
    login_instagram()
    user_id = cl.user_id_from_username(cl.username)
    # Get raw returns; they could be dict or list
    following_raw = cl.user_following(user_id, amount=0)
    followers_raw = cl.user_followers(user_id, amount=0)
    
    # Helper to extract list of user objects
    def extract_users(raw):
        if isinstance(raw, dict):
            # dict of pk: user
            return list(raw.values())
        elif isinstance(raw, list):
            return raw
        else:
            # fallback: try to iterate
            try:
                return list(raw)
            except Exception:
                return []
    
    following_users = extract_users(following_raw)
    followers_users = extract_users(followers_raw)
    
    # Build sets of pk
    following_pks = set()
    followers_pks = set()
    user_by_pk = {}
    
    for u in following_users:
        pk = getattr(u, 'pk', None) if not isinstance(u, dict) else u.get('pk')
        if pk is not None:
            following_pks.add(pk)
            user_by_pk[pk] = u
    
    for u in followers_users:
        pk = getattr(u, 'pk', None) if not isinstance(u, dict) else u.get('pk')
        if pk is not None:
            followers_pks.add(pk)
    
    not_following_pks = following_pks - followers_pks
    not_following_users = [user_by_pk[pk] for pk in not_following_pks if pk in user_by_pk]
    
    result = [{'pk': u.pk if not isinstance(u, dict) else u.get('pk'),
               'username': u.username if not isinstance(u, dict) else u.get('username'),
               'full_name': u.full_name if not isinstance(u, dict) else u.get('full_name')} for u in not_following_users]
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
    # Limit to first 200 for display
    limited_targets = targets[:200]
    return render_template('index.html', targets=limited_targets, insta_user=insta_user, insta_pass_set=insta_pass_set)

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
        # Return detailed error for debugging
        return jsonify({
            'success': False,
            'error': str(e),
            'type': type(e).__name__
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