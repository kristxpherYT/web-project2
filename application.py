import os
from os.path import join, dirname
from flask import Flask
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

dotenv_path = join(dirname(__file__), '.env')  # Path to .env file
load_dotenv(dotenv_path)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
socketio = SocketIO(app)


@app.route("/")
def index():
    return "Project 2: TODO"
