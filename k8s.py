import collections
import urllib3
import jsonpath
from clusters import Cluster
from log import logger
from utils import parse_resource, ONE_GIBI, ONE_MEBI

urllib3.disable_warnings()

pod_metric_fields = [
    'ns',
    'pod',
    'status',
    'cpu',
    'cpu_requests',
    'cpu_limits',
    'memory',
    'memory_requests',
    'memory_limits',
]
PodMetric = collections.namedtuple('PodMetric', pod_metric_fields)
node_metric_fields = [
    'node', 'cpu', 'memory'
]
NodeMetric = collections.namedtuple('NodeMetric', node_metric_fields)


class K8sClient(Cluster):
    def __init__(self, kube_conf):
        super(K8sClient, self).__init__(kube_conf)
        self.node_list = jsonpath.jsonpath(super(K8sClient, self).get_node(), '$.items[*].metadata.name')

    def get_metric(self):
        api_instance = self.core_v1_api
        pods = api_instance.list_pod_for_all_namespaces().items
        node_usages = [self.top_node(node) for node in self.node_list]
        pods_usages = sorted([self.top_pod(pod) for pod in pods], key=lambda x: x.memory, reverse=True)
        return {"nodes": node_usages, "pods": pods_usages}

    @logger.catch
    def top_node(self, node):
        custom = self.custom_api
        data = custom.get_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes", node)
        node = data['metadata']['name']
        cpu = parse_resource(data['usage']['cpu'])
        memory = parse_resource(data['usage']['memory'])
        return NodeMetric(node=node, cpu=cpu, memory=memory / ONE_GIBI)

    @logger.catch
    def top_pods(self):
        custom = self.custom_api
        data = custom.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "pods")
        usage_by_pod = collections.defaultdict(list)
        for pod_data in data['items']:
            pod_name = pod_data['metadata']['name']
            for container_data in pod_data['containers']:
                usage_by_pod[pod_name].append(
                    {
                        'pod': container_data['name'],
                        'cpu': parse_resource(container_data['usage']['cpu']),
                        'memory': parse_resource(container_data['usage']['memory']) / ONE_MEBI,
                    }
                )
        return usage_by_pod

    @staticmethod
    def aggregate_container_resource(pod):
        values = {
            'memory_limits': 0,
            'cpu_limits': 0,
            'memory_requests': 0,
            'cpu_requests': 0,
        }
        for container in pod.spec.containers:
            limits = getattr(container.resources, 'limits', None)
            if limits:
                values['memory_limits'] += round(parse_resource(limits.get('memory')) / ONE_GIBI, 1)
                values['cpu_limits'] += parse_resource(limits.get('cpu'))
            requests = getattr(container.resources, 'requests', None)
            if requests:
                values['memory_requests'] += round(parse_resource(requests.get('memory')) / ONE_GIBI, 1)
                values['cpu_requests'] += parse_resource(requests.get('cpu'))
        return values

    @logger.catch
    def top_pod(self, pod):
        ns = pod.metadata.namespace
        status = pod.status.phase
        data = self.top_pods().get(pod.metadata.name) or []
        cpu = round(sum(pod_data['cpu'] for pod_data in data), 3)
        memory = round(sum(pod_data['memory'] for pod_data in data))
        return PodMetric(ns=ns, pod=pod.metadata.name, status=status, cpu=cpu, memory=memory,
                         **self.aggregate_container_resource(pod))

    @logger.catch
    def get_node(self):
        api_instance = self.core_v1_api
        nodes = api_instance.list_node()
        result = []
        for i in nodes.items:
            node = dict()
            for x in i.status.addresses:
                node[x.type] = x.address
            for s in i.status.conditions:
                if s.type == "Ready":
                    node['status'] = "Ready" if s.status else "NotReady"
            node['kernel'] = i.status.node_info.kernel_version
            node['container_runtime'] = i.status.node_info.container_runtime_version
            node['cpu'] = i.status.capacity['cpu']
            node['memory'] = round(parse_resource(i.status.capacity['memory']) / ONE_GIBI)
            result.append(node)
        return {"desc": "node", "result": result}

    def get_pod(self):
        api_instance = self.core_v1_api
        pods = api_instance.list_pod_for_all_namespaces()
        result = []
        for i in pods.items:
            pod = dict()
            pod['name'] = i.metadata.name
            pod['ns'] = i.metadata.namespace
            pod['status'] = i.status.phase
            if i.status.container_statuses is not None:
                pod['restart'] = max([x.restart_count for x in i.status.container_statuses])
            else:
                pod['restart'] = None
            pod['start_time'] = f'{i.status.start_time:%Y-%m-%d %H:%M:%S }'
            pod['ip'] = i.status.pod_ip
            pod['host'] = i.status.host_ip
            result.append(pod)
        return {"desc": "pod", "result": result}
