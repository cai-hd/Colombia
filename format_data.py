import pickle
import eventlet
from celery import Celery
from flask import Flask, render_template, request, jsonify, make_response,flash
from redis import Redis
from flask_socketio import SocketIO,emit
from main import check
from flask_celery_conf import make_celery

from utils import merge_pod, merge_node


app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
f = open('dump', 'rb')
data = pickle.load(f)
app.config['broker_url'] = 'redis://localhost:6379/0'
app.config['result_backend'] = 'redis://localhost:6379/0'
app.config['accept_content'] = ['json']
app.config['REDIS_URL'] = 'redis://localhost:6379/0'

socketio = SocketIO(app, async_mode='eventlet', message_queue=app.config['result_backend'])
eventlet.monkey_patch()
redis = Redis("localhost")
celery = make_celery(app)

import threading


class Listener(threading.Thread):
    def __init__(self, r, channels, app):
        threading.Thread.__init__(self)
        self.daemon = True
        self.redis = r
        self.pubsub = self.redis.pubsub()
        self.pubsub.psubscribe(channels)
        self.app = app

    def work(self, item):
        with app.test_request_context('/recheck'):
            msg = item['data']
            if isinstance(msg, bytes):
                msg = item['data'].decode('utf-8')
                emit("info", {'data': msg}, namespace="/task", broadcast=True)

    def run(self):
        for item in self.pubsub.listen():
            self.work(item)


@celery.task(name='task.check')
def background_task():
    check()


@socketio.on('connect', namespace='/task')
def connect_host():
    socketio.emit('info', {'data':'client connect'}, namespace='/task')


@app.route('/task')
def start_background_task():
    background_task.delay()
    return jsonify({'status': 'start'},200)


@app.route("/")
def index():
    nav = [*data]
    cid = 'compass-stack'
    data[cid]['node_info'] = merge_node(data, cid)
    data[cid]['pod_info'] = merge_pod(data, cid)
    return render_template("index.html", nav=nav, data=data[cid])


@app.route('/<cid>')
def cluster(cid):
    nav = [*data]
    data[cid]['node_info'] = merge_node(data, cid)
    data[cid]['pod_info'] = merge_pod(data, cid)
    return render_template("index.html", nav=nav, data=data[cid])


@app.route("/license")
def license():
    license = data['license']
    nav = [*data]
    return render_template("license.html", nav=nav, license=license)


@app.route("/volumes_status")
def volume():
    volume = data['volumes_status']
    nav = [*data]
    return render_template("volume.html", nav=nav, volume=volume)


@app.route("/recheck")
def recheck():
    nav = [*data]
    flash("xxxxxxxx")
    return render_template("recheck.html", nav=nav)


if __name__ == "__main__":
    r = Redis()
    client = Listener(r, ['message'],app)
    client.start()
    socketio.run(app=app, host="0.0.0.0", port=5000, debug=True)
