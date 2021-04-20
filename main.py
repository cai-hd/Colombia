import loguru

from k8s import K8sClient
import datetime
from check import CheckGlobal, CheckK8s
from pathlib import Path
import pickle
from log import logger

@logger.catch
def check():
    control_k8s = CheckGlobal()
    busybox_images = control_k8s.load_busybox_image()
    control_k8s.start_check()
    check_out = control_k8s.checkout
    k8s_conf_list = control_k8s.k8s_conf_list
    for conf in k8s_conf_list:
        cluster_name = Path(conf).name
        k8s_obj = CheckK8s(conf, check_out)
        if k8s_obj.create_check_pod(busybox_images):
            k8s_obj.start_check()
        k8s_obj.del_check_pod()
        k8s = K8sClient(conf)
        now = datetime.datetime.now()
        context = {}
        for i in ["node", "pod", "job", "metric"]:
            context_method = getattr(k8s, "get_{}".format(i))
            context[i] = context_method()
            context['now'] = now
        check_out[cluster_name]['context'] = context
    return check_out



if __name__ == "__main__":
    # generate_report()
    check_data = check()
    f = open("dump", 'wb')
    pickle.dump(check_data, f)
    f.close()
