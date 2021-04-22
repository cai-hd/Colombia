import datetime

import eventlet
eventlet.monkey_patch()

import pickle
from flask import Flask, render_template, request, redirect, url_for, g, flash
from flask_socketio import SocketIO, emit
from flask_redis import FlaskRedis
from utils import merge_pod, merge_node
from main import check

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dshkwnds'
app.config['REDIS_URL'] = 'redis://localhost:6379/0'
socket_io = SocketIO(app, async_mode='eventlet')
redis = FlaskRedis(app)


def listener(channels):
    pub_sub = redis.pubsub()
    pub_sub.psubscribe(channels)
    with app.test_request_context('/recheck'):
        for item in pub_sub.listen():
            msg = item['data']
            if isinstance(msg, bytes):
                msg = item['data'].decode('utf-8')
                emit("update", {'data': msg}, namespace="/work", broadcast=True, include_self=True)


@app.before_request
def before_request():
    if redis.get("report") is None and request.endpoint != 'recheck':
        return redirect(url_for("recheck"))
    elif redis.get("report"):
        report = redis.get('report')
        report_dict = pickle.loads(report)
        g.data = report_dict
        g.nav = [*g.data]


@app.route("/")
def index():
    cid = 'compass-stack'
    g.data[cid]['node_info'] = merge_node(g.data, cid)
    g.data[cid]['pod_info'] = merge_pod(g.data, cid)
    return render_template("index.html", nav=g.nav, data=g.data[cid])


@app.route('/<cid>')
def cluster(cid):
    g.data[cid]['node_info'] = merge_node(g.data, cid)
    g.data[cid]['pod_info'] = merge_pod(g.data, cid)
    return render_template("index.html", nav=g.nav, data=g.data[cid])


@app.route("/license")
def license():
    license = g.data['license']
    return render_template("license.html", nav=g.nav, license=license)


@app.route("/volumes_status")
def volume():
    volume = g.data['volumes_status']
    return render_template("volume.html", nav=g.nav, volume=volume)


@app.route('/recheck')
def recheck():
    if redis.get("report") is None:
        nav = []
        message = "There is no report found in the database for the time being. It looks like this is the first run," \
                  " please click the Execute button"
        flash(message)
    else:
        nav = g.nav
    return render_template('recheck.html', nav=nav)


@socket_io.on('connect', namespace='/work')
def connect():
    emit("update", {"data": "connected"})


@socket_io.on('start', namespace='/work')
def start_work():
    emit("update", {"data": "starting worker"})
    socket_io.start_background_task(target=check)


if __name__ == "__main__":
    socket_io.start_background_task(listener, "message", )
    socket_io.run(app=app, host="0.0.0.0", port=5000, debug=True)
