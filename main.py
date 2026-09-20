import os
import json
import time
from flask import Flask, render_template, request, redirect, url_for, flash
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
    following = cl.user_following(user_id, amount=0)  # get all
    followers = cl.user_followers(user_id, amount=0)
    not_following_back = [user for uid, user in following.items() if uid not in followers]
    # Convert to list of dicts with needed info
    result = [{'pk': uid, 'username': user.username, 'full_name': user.full_name} for uid, user in not_following_back.items()]
    save_targets(result)
    return result

@app.route('/')
def index():
    targets = load_targets()
    if not targets:
        # try to fetch fresh
        try:
            targets = get_not_following_back()
        except Exception as e:
            flash(f'Error fetching data: {e}', 'danger')
            targets = []
    return render_template('index.html', targets=targets)

@app.route('/unfollow/<pk>', methods=['POST'])
def unfollow(pk):
    try:
        login_instagram()
        cl.user_unfollow(pk)
        flash(f'Unfollowed user {pk}', 'success')
        # remove from list
        targets = load_targets()
        targets = [t for t in targets if t['pk'] != pk]
        save_targets(targets)
        time.sleep(5)  # simple rate limit
    except Exception as e:
        flash(f'Error unfollowing: {e}', 'danger')
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)