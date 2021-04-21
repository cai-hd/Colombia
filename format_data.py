import pickle
import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify, make_response,flash
from redis import Redis
from flask_socketio import SocketIO,emit
from main import check
from utils import merge_pod, merge_node
import threading



app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
f = open('dump', 'rb')
data = pickle.load(f)
app.config['broker_url'] = 'redis://localhost:6379/0'
app.config['result_backend'] = 'redis://localhost:6379/0'
app.config['accept_content'] = ['json']
app.config['REDIS_URL'] = 'redis://localhost:6379/0'

socketio = SocketIO(app, async_mode='eventlet', message_queue=app.config['result_backend'])
redis = Redis("localhost")



class Listener(threading.Thread):
    def __init__(self, r, channels, app):
        threading.Thread.__init__(self)
        self.daemon = True
        self.redis = r
        self.pubsub = self.redis.pubsub()
        self.pubsub.psubscribe(channels)
        self.app = app

    def work(self, item):
        with app.test_request_context('/demo'):
            msg = item['data']
            if isinstance(msg, bytes):
                msg = item['data'].decode('utf-8')
                emit("update", {'data': msg}, namespace="/work", broadcast=True)

    def run(self):
        for item in self.pubsub.listen():
            self.work(item)




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




workerObject = None

class Worker(object):

    switch = False
    unit_of_work = 0

    def __init__(self, socketio):
        """
        assign socketio object to emit
        """
        self.socketio = socketio
        self.switch = True



    def do_work(self):
        """
        do work and emit message
        """

        while self.switch:
            self.unit_of_work += 1
            self.socketio.emit("update", {"data": self.unit_of_work}, namespace="/work")
            eventlet.sleep(1)


    def stop(self):
        """
        stop the loop
        """
        self.switch = False


@app.route('/check')
def demo():
    """
    renders demo.html
    """
    nav = [*data]
    return render_template('recheck.html',nav=nav)



@socketio.on('connect', namespace='/work')
def connect():
    """
    connect
    """

    global worker
    worker = Worker(socketio)
    emit("update", {"data": "connected"})


@socketio.on('start', namespace='/work')
def start_work():
    """
    trigger background thread
    """
    emit("update", {"data": "starting worker"})

    # notice that the method is not called - don't put braces after method name
    socketio.start_background_task(target=check)


@socketio.on('stop', namespace='/work')
def stop_work():
    """
    trigger background thread
    """

    worker.stop()
    emit("update", {"data": "worker has been stoppped"})


if __name__ == "__main__":
    r = Redis()
    client = Listener(r, ['message'],app)
    client.start()
    socketio.run(app=app, host="0.0.0.0", port=5000, debug=True)
