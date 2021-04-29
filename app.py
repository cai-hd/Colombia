import eventlet

eventlet.monkey_patch()
import pickle
import time
import configparser
from flask import Flask, render_template, request, redirect, url_for, g, flash, send_file
from flask_socketio import SocketIO, emit
from flask_redis import FlaskRedis
from utils import merge_pod, merge_node
from main import check
from threading import Lock
from export_excel import format_data_for_k8s, format_other_data, set_dimension, Workbook
from utils import config_obj
thread = None
thread_lock = Lock()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dshkwnds'
app.config['REDIS_URL'] = 'redis://localhost:6379/0'
socket_io = SocketIO(app, async_mode='eventlet')
redis = FlaskRedis(app)

customer_name = config_obj.get("info", "customer")


def listener(channels):
    pub_sub = redis.pubsub()
    pub_sub.psubscribe(channels)
    with app.test_request_context('/recheck'):
        for item in pub_sub.listen():
            msg = item['data']
            if isinstance(msg, bytes):
                msg = item['data'].decode('utf-8')
                emit("update", {'data': msg}, namespace="/work", broadcast=True)


@app.before_request
def before_request():
    if redis.get("report") is None and request.endpoint not in ('recheck', 'static'):
        return redirect(url_for("recheck"))
    elif redis.get("report"):
        report = redis.get('report')
        report_dict = pickle.loads(report)
        g.data = report_dict
        g.nav = [*g.data]


@app.route("/")
def index():
    cid = 'stack'
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


@app.route("/export")
def export():
    wb = Workbook()
    default_sheet = wb.active
    wb.remove(default_sheet)
    for cluster in g.data.keys():
        if cluster not in ['license', 'volumes_status']:
            ws = wb.create_sheet(cluster)
            format_data_for_k8s(ws, cluster, g.data)
            set_dimension(ws)
    ws = wb.create_sheet("others")
    format_other_data(ws, g.data)
    set_dimension(ws)
    file_name = f'./report/{customer_name}_{time.strftime("%Y%m%d%H%M%S", time.localtime())}.xlsx'
    wb.save(file_name)
    return send_file(file_name, as_attachment=True)


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
    if thread is None or thread.is_alive() is False:
        emit("update", {"data": "connected......"})
    elif thread.is_alive():
        emit("update", {"data": "Check thread is working ......"})


@socket_io.on('start', namespace='/work')
def start_work():
    global thread
    with thread_lock:
        if thread is None or thread.is_alive() is False:
            emit("update", {"data": "starting worker"})
            thread = socket_io.start_background_task(target=check)
        elif thread.is_alive():
            emit("update", {"data": "Check thread is working ......"})


if __name__ == "__main__":
    socket_io.start_background_task(listener, "message", )
    socket_io.run(app=app, host="0.0.0.0", port=5000, debug=True)
