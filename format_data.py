import pickle

from flask import Flask, render_template

from utils import merge_pod, merge_node

app = Flask(__name__)

f = open('dump', 'rb')
data = pickle.load(f)
print(data['compass-stack'].keys())


@app.route('/<cid>', defaults={'cid': 'compass-stack'})
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
