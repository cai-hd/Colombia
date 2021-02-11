import json


class Collect(object):
    """

    """
    def __init__(self, session):
        self.session = session

    def get_node(self):
        """

        :return:
        """
        cmd = "kubectl get node -o wide --no-headers"
        result = self.session.execute_commands(cmd)
        node_dict = lambda x: {"name": x[0],
                               "status": x[1],
                               "roles": x[2],
                               "age": x[3],
                               "version": x[4],
                               "ip": x[5],
                               "kernel": x[11],
                               "run_time": x[12]}
        node_result = [node_dict(i.split()) for i in result]
        self.k8s_node = [i['ip'] for i in node_result if i['status'] == "Ready"]
        return {"desc": "Node", "result": node_result}

    def get_pod(self):
        """

        :return:
        """
        cmd = "kubectl get po --all-namespaces --no-headers -o wide"
        result = self.session.execute_commands(cmd)
        pod_list = []
        for i in result:
            pods_line = i.split()
            pods_dict = {"ns": pods_line[0],
                         "name": pods_line[1],
                         "ready": pods_line[2],
                         "status": pods_line[3],
                         "restarts": pods_line[4],
                         "age": pods_line[5],
                         "ip": pods_line[6],
                         "node": pods_line[7]}
            pod_list.append(pods_dict)
        return {"desc": "Pods", "result": pod_list}



    def get_docker(self):
        """

        :return:
        """
        cmd = "systemctl status docker"
        result = self.session.execute_commands(cmd)
        return {"desc": "docker", "result": [i for i in result]}





