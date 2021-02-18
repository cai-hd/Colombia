import os
from k8s import K8sClient
from output import OutputManager
import datetime

THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def generate_report():
    out = OutputManager()
    k8s = K8sClient()
    now = datetime.datetime.now()
    context = {}
    for i in ["core", "node", "pod", "job", "metric"]:
        context_method = getattr(k8s, "get_{}".format(i))
        context[i] = context_method()
        context['now'] = now
        out.render_template(context, i)



if __name__ == "__main__":
    generate_report()
