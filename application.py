import os
from os.path import join, dirname
from flask import Flask, request, render_template, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room, send
from dotenv import load_dotenv

dotenv_path = join(dirname(__file__), '.env')  # Path to .env file
load_dotenv(dotenv_path)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
socketio = SocketIO(app)

# Global Variables to store data on server
users = [] # user: {"user_id", "user_name", "channels_allowed[(channel_id)]", "last_channel_id"}
logged_users = []
channels = [{"channel_id": 0, "channel_name": "General"}] # channel: {"channel_id", "channel_name"}
messages = [] # message: {"message_id", "message", "user_id", "channel_id"}

@app.route("/", methods=["GET", "POST"])
def index():
    current_user = None

    if request.method == "POST":
        user_name = request.form["name"]
        current_user = {
            "user_id": len(users),
            "user_sid": None,
            "user_name": user_name,
            "channels_allowed": [0],
            "last_channel_id": 0
        }
        session["current_user"] = current_user
        users.append(current_user)
    else:
        current_user = session.get("current_user", None)
    
        if current_user is None:
            return redirect(url_for('register'))

        current_user = get_logged_user(current_user['user_id'])
        
    return render_template("views/index.html", current_user=current_user, users=users, logged_users=logged_users, messages=messages, channels=channels)

@app.route("/register")
def register():
    return render_template("views/register.html")

@app.route("/create_channel", methods=["POST"])
def create_channel():
    channel = {
        "channel_id": len(channels),
        "channel_name": request.form['channel_name']
    }
    channels.append(channel)
    return redirect(url_for('index'))

@app.route("/exit")
def exit():
    current_user = session.get("current_user", None)
    session.pop('current_user', None)

    for user_id, user in enumerate(users):
        if current_user['user_id'] == user['user_id']:
            del users[user_id]
    
    for log_id, logged_user in enumerate(logged_users):
        if logged_user['user_id'] == current_user['user_id']:
            del logged_users[log_id]

    return redirect(url_for('index'))

@app.route("/clear")
def clear_session():
    session.clear()
    return redirect(url_for('index'))

@app.route("/logged_users")
def loaded_users():
    return str(logged_users)

@app.route("/users")
def all_users():
    return str(users)

@app.route("/channels")
def channels_created():
    return str(channels)

@socketio.on("login")
def login(data):
    user_id = data['user_id']

    found = False
    for logged_user in logged_users:
        if logged_user['user_id'] == user_id:
            found = True
    
    if not found:
        for id, user in enumerate(users):
            if user['user_id'] == user_id:
                users[id]["user_sid"] = request.sid
                logged_users.append(users[id])
                emit("user logged", {"logged_user": users[id]}, broadcast=True, include_self=False)
    else:
        for log_id, log_user in enumerate(logged_users):
            if log_user['user_id'] == user_id:
                logged_users[log_id]["user_sid"] = request.sid
                emit("user logged", {"logged_user": logged_users[log_id]}, broadcast=True, include_self=False)


@socketio.on("send message")
def send_message(data):
    message = {
        "message_id": len(messages),
        "message": data['message'],
        "user_id": data['user_id'],
        "channel_id": 0
    }

    messages.append(message)

    emit("receive message", {"user_id": message['user_id'], "message": message['message']}, broadcast=True)

@socketio.on("send channel message")
def send_channel_message(data):
    channel_name = None
    
    if 'channel_name' in data.keys():
        channel_name = data["channel_name"]
        message = {
            "message_id": len(messages),
            "message": data['message'],
            "user_id": data['user_id'],
            "channel_id": get_channel_id(channel_name)
        }
        
        for user_id, user in enumerate(users):
            if data['user_id'] == user['user_id']:
                users[user_id]['user_sid'] = request.sid
        
        for log_id, logged_user in enumerate(logged_users):
            if logged_user['user_id'] == data['user_id']:
                logged_users[log_id]['user_sid'] = request.sid
        join_room(channel_name)

        messages.append(message)
        emit("receive message", {"user_id": message['user_id'], "message": message['message']}, room=channel_name)
    else:
        user_destination_id = int(data["user_destination_id"])

        for log_id, logged_user in enumerate(logged_users):
            if logged_user['user_id'] == user_destination_id:
                channel_name = logged_user["user_sid"]
                join_room(channel_name)
        emit("receive message", {"user_id": data['user_id'], "message": data['message'], "private": True}, include_self=True ,room=channel_name)

@socketio.on("join channel")
def join_channel(data):
    user_id = data['user_id']
    channel_name = data['channel_name']

    current_id = None

    for id, user in enumerate(users):
        if user['user_id'] == user_id:
            current_id = id
    
    if current_id is not None:
        channel_id = get_channel_id(channel_name)
        if channel_id is not None:
            join_room(channel_name)
            users[current_id]['channels_allowed'].append(channel_id)
            for logged_id, current_user in enumerate(logged_users):
                if current_user['user_id'] == current_id:
                    logged_users[logged_id] = users[current_id]
            emit("join channel", users[current_id]['user_name'] + ' has entered the channel.', room=channel_name)
        else:
            emit('error', {'error': 'Unable to join channel. Channel does not exist.'})

@socketio.on("leave channel")
def leave_channel(data):
    user_id = data['user_id']
    channel_name = data['channel_name']
    channel_id = get_channel_id(channel_name)
    leave_room(channel_name)
    del users[user_id]['channels_allowed'][channel_id]
    send(users[user_id]['user_name'] + ' has left the channel.', room=channel_name)

@socketio.on("current channel")
def current_channel(data):
    if 'channel_name' in data.keys():
        channel_name = data['channel_name']
        channel_id = get_channel_id(channel_name)

        for user_id, user in enumerate(users):
            if data['user_id'] == user['user_id']:
                users[user_id]['last_channel_id'] = channel_id
                session['current_user'] = users[user_id]

@socketio.on('disconnect')
def disconnect():
    user_id = get_user_id(request.sid)

    if user_id:
        users[user_id]['user_sid'] = None
        logged_users.remove(users[user_id])
        print(users[user_id]['user_name'] + " is disconnected")
        print(logged_users)

def get_channel_id(name):
    for id, channel in enumerate(channels):
        if channel['channel_name'] == name:
            return id
    return None

def get_user_id(sid):
    for id, user in enumerate(users):
        if user['user_sid'] == sid:
            return id
    return None

def get_channel_messages(id):
    channel_messages = []
    for message in messages:
        if message['channel_id'] == id:
            channel_messages.append(message)
    return channel_messages

def get_logged_user(id):
    for logged_id, user in enumerate(logged_users):
        if user['user_id'] == id:
            return user
    return None

def is_allowed(user_id, channel_id):
    current_user = None
    for user in users:
        if user['user_id'] == user_id:
            current_user = user

    if channel_id in current_user['channels_allowed']:
        return True
    return False

app.jinja_env.globals.update(get_channel_messages=get_channel_messages, get_channel_id=get_channel_id, is_allowed=is_allowed)

if __name__ == __name__:
    socketio.run(app)