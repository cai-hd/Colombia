from k8s import K8sClient
import datetime
from check import CheckGlobal, CheckK8s
from pathlib import Path
import pickle
from log import logger
from redis import Redis
import time
from typing import Dict


@logger.catch
def check() -> Dict:
    start = time.time()
    control_k8s = CheckGlobal()
    alias = control_k8s.get_name_alias()
    busybox_images, cps_version = control_k8s.load_busybox_image()
    control_k8s.start_check()
    check_out = control_k8s.checkout
    k8s_conf_list = control_k8s.k8s_conf_list
    for conf in k8s_conf_list:
        cluster_name = Path(conf).name
        k8s_obj = CheckK8s(conf, check_out, cps_version)
        if k8s_obj.create_check_pod(busybox_images):
            k8s_obj.start_check()
        k8s_obj.del_check_pod()
        k8s = K8sClient(conf)
        now = datetime.datetime.now()
        context = {}
        for i in ["node", "pod", "metric"]:
            context_method = getattr(k8s, "get_{}".format(i))
            context[i] = context_method()
            context['now'] = now
        check_out[cluster_name]['context'] = context
    for i in alias.keys():
        if alias[i] == i:
            continue
        check_out[alias[i]] = check_out[i]
        del check_out[i]
    dump = pickle.dumps(check_out)
    f = open(f'./tmp/dump-{time.strftime("%Y%m%d", time.localtime())}', 'wb')
    pickle.dump(check_out, f)
    f.close()
    r = Redis("localhost")
    r.set("report", dump)
    logger.info("report save to redis has been completed")
    end = time.time() - start
    logger.info("this task took {} seconds".format(round(end, 2)))
    return True
