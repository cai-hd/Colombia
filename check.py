#!/usr/bin/env python3
# -*- coding:utf-8 _*-
"""
@author:fjg
@license: Apache Licence
@file: check.py
@time: 2021/04/09
@contact: fujiangong.fujg@bytedance.com
@site:
@software: PyCharm
"""
import time
from collections import defaultdict
import datetime
import ipaddress
from pathlib import Path
import re

import jsonpath
import requests
from kubernetes import client
from kubernetes.stream import stream

from clusters import K8sClusters, Cluster
from utils import RemoteClientCompass, config_obj, parse_resource, ONE_GIBI
from log import logger
from nodecollect import AllRun


class CheckGlobal(K8sClusters):
    def __init__(self):
        super(CheckGlobal, self).__init__()
        self.k8s_conf_list = self.get_clusters_conf()
        self.ssh_key_file = self.get_ssh_config()
        self.machines = self.get_machines()
        self.checkout = defaultdict(dict)

    def check_node_status(self):
        for cluster in self.clusters.keys():
            logger.info(f"start check cluster({cluster}) nodes status")
            node_list = jsonpath.jsonpath(self.clusters[cluster], '$.status[masters,nodes][*]')
            not_ready_list = list()
            ready_list = list()
            for node in node_list:
                if node['status'] != "Ready":
                    not_ready_list.append(node['name'])
                else:
                    ready_list.append(node['name'])
            status = True if len(not_ready_list) == 0 else False

            self.checkout[cluster]['node_status'] = {
                "data": {"ready": {'data': len(ready_list), 'name': ready_list},
                         'not_ready': {'data': len(not_ready_list), 'name': not_ready_list}}, 'status': status}

    def check_license(self):
        logger.info("start check license")
        license_info = self.get_license()
        # days
        utc_format = '%Y-%m-%dT%H:%M:%S.%fZ'
        day_end = license_info['spec']['notAfter']
        day_start = license_info['spec']['notBefore']
        day_unused = (datetime.datetime.strptime(day_end, utc_format) - datetime.datetime.now()).days
        day_status = True if day_unused > 30 else False

        # physical
        physical_cpu_total = int(license_info['spec']['quota']['physicalCpu'])
        physical_cpu_used = int(license_info['status']['used']['physicalCpu'])
        physical_cpu_unused = physical_cpu_total - physical_cpu_used
        physical_cpu_status = True if physical_cpu_used < physical_cpu_total * 0.8 else False

        self.checkout['license'] = {
            'day': {'start': day_start, 'end': day_end, 'unused': day_unused, 'status': day_status},
            'physical_cpu': {'total': physical_cpu_total, 'used': physical_cpu_used, 'unused': physical_cpu_unused,
                             'status': physical_cpu_status}}
        if 'logicalCpu' in license_info['spec']['quota'].keys():
            logical_cpu_total = int(license_info['spec']['quota']['logicalCpu'])
            logical_cpu_used = int(license_info['status']['used']['logicalCpu'])
            logical_cpu_unused = logical_cpu_total - logical_cpu_used
            logical_cpu_status = True if logical_cpu_used < logical_cpu_total * 0.8 else False
            self.checkout['license']['logical_cpu'] = {'total': logical_cpu_total, 'used': logical_cpu_used,
                                                       'unused': logical_cpu_unused, 'status': logical_cpu_status}

    @staticmethod
    def get_response(url):
        ret = requests.get(url, verify=False)
        if ret.status_code not in [200, 202] and ret.content.decode() != 'ok':
            return False, ret.content.decode()
        return True, ret.content.decode()

    def check_component_status(self):
        logger.info("start check component status")
        for cluster in self.clusters.keys():
            self.checkout[cluster]['apiserver_status'] = list()
            self.checkout[cluster]['controller_status'] = list()
            self.checkout[cluster]['scheduler_status'] = list()
            for master_ip in self.clusters[cluster]['spec']['masters']:
                apiserver_url = f"https://{master_ip}:6443/healthz"
                logger.info(f'check component apiserver {master_ip}')
                status, content = self.get_response(apiserver_url)
                self.checkout[cluster]['apiserver_status'].append({master_ip: {'data': content, 'status': status}})
                controller_url = f"https://{master_ip}:10257/healthz"
                logger.info(f'check component controller {master_ip}')
                status, content = self.get_response(controller_url)
                self.checkout[cluster]['controller_status'].append(
                    {master_ip: {'data': content, 'status': status}})
                scheduler_url = f"http://{master_ip}:10251/healthz"
                logger.info(f'check scheduler apiserver {master_ip}')
                status, content = self.get_response(scheduler_url)
                self.checkout[cluster]['scheduler_status'].append({master_ip: {'data': content, 'status': status}})

    def check_etcd_status(self):
        logger.info("start check etcd status")
        for cluster in self.clusters.keys():
            self.checkout[cluster]['etcd_status'] = dict()
            for master_ip in self.clusters[cluster]['spec']['masters']:
                logger.info(f"check etcd {master_ip}")
                ssh_obj = RemoteClientCompass(master_ip, self.machines[master_ip]['spec']['auth']['user'],
                                              int(self.machines[master_ip]['spec']['sshPort']),
                                              self.machines[master_ip]['spec']['auth']['password'],
                                              self.machines[master_ip]['spec']['auth']['key'])
                for port in ['2379', '2381']:
                    get_member_cmd = f'sudo ETCDCTL_API=3 /usr/local/etcd/bin/etcdctl --cacert=/var/lib/etcd/ssl/ca.crt --cert=/var/lib/etcd/ssl/etcd.crt --key=/var/lib/etcd/ssl/etcd.key --endpoints=https://{master_ip}:{port} endpoint health'
                    ret = ssh_obj.cmd(get_member_cmd)
                    status = ret[-1].rstrip("\r\n").split()[2].rstrip(":")
                    if status == "healthy":
                        took_time = ret[-1].rstrip("\r\n").split()[8]
                        self.checkout[cluster]['etcd_status'][f"{master_ip}:{port}"] = {'data': took_time,
                                                                                        'status': True}
                    else:
                        self.checkout[cluster]['etcd_status'][f"{master_ip}:{port}"] = {'data': ret, 'status': False}
                ssh_obj.close()

    def check_volumes_status(self):
        logger.info("start compass gluster volumes status")
        all_ip = self.clusters['compass-stack']['spec']['masters']
        node_ip = self.clusters['compass-stack']['spec']['nodes']
        all_ip.extend(node_ip)
        for master_ip in all_ip:
            ssh_obj = RemoteClientCompass(master_ip, self.machines[master_ip]['spec']['auth']['user'],
                                          int(self.machines[master_ip]['spec']['sshPort']),
                                          self.machines[master_ip]['spec']['auth']['password'],
                                          self.machines[master_ip]['spec']['auth']['key'])
            volumes_list_cmd = r"sudo gluster volume list"
            volumes_list = ssh_obj.cmd(volumes_list_cmd)
            if volumes_list:
                self.checkout['volumes_status']['compass-stack'] = dict()
                for volume in volumes_list:
                    volume = volume.rstrip("\r\n")
                    logger.info(f"check compass gluster volumes {volume} brick")
                    self.checkout['volumes_status']['compass-stack'][volume] = {'data': list(), 'status': True}
                    volume_status_info_cmd = f"sudo gluster volume status {volume} detail"
                    info = ssh_obj.cmd(volume_status_info_cmd)
                    brick_name = ""
                    for line in info:
                        if line.startswith("Brick"):
                            brick_name = line.split()[-1]
                        if line.startswith("Online"):
                            online = line.split()[-1].strip()
                            if online != "Y":
                                self.checkout['volumes_status']['compass-stack'][volume]['data'].append(brick_name)
                                self.checkout['volumes_status']['compass-stack'][volume]['status'] = False
                ssh_obj.close()
                break
        logger.info("start cargo gluster volumes status")
        ssh_obj_cargo = RemoteClientCompass(config_obj.get('cargo', 'node_ip'), config_obj.get('cargo', 'ssh_user'),
                                            int(config_obj.get('cargo', 'ssh_port')),
                                            config_obj.get('cargo', 'ssh_pwd'), config_obj.get('cargo', 'ssh_key'))
        container_list = ssh_obj_cargo.cmd(r"sudo docker ps --format '{{.Names}}'")
        if "gluster-container\r\n" in container_list:
            volumes_list_cmd = r"sudo docker exec gluster-container gluster volume list"
            volumes_list = ssh_obj_cargo.cmd(volumes_list_cmd)
            if volumes_list:
                self.checkout['volumes_status']['cargo'] = dict()
                for volume in volumes_list:
                    volume = volume.rstrip("\r\n")
                    logger.info(f"check cargo gluster volumes {volume} brick")
                    self.checkout['volumes_status']['cargo'][volume] = {'data': list(), 'status': True}
                    volume_status_info_cmd = f"sudo docker exec gluster-container gluster volume status {volume} detail"
                    info = ssh_obj_cargo.cmd(volume_status_info_cmd)
                    brick_name = ""
                    for line in info:
                        if line.startswith("Brick"):
                            brick_name = line.split()[-1]
                        if line.startswith("Online"):
                            online = line.split()[-1].strip()
                            if online != "Y":
                                self.checkout['volumes_status']['cargo'][volume]['data'].append(brick_name)
                                self.checkout['volumes_status']['cargo'][volume]['status'] = False
                ssh_obj_cargo.close()

    def load_busybox_image(self):
        logger.info(f"load and push busybox image")
        registry = self.get_cm('platform-info', 'default')['data']['cargo_registry']
        version = self.get_cm('platform-info', 'default')['data']['platform_release_version']
        # user = config_obj.get('cargo', 'harbor_user')
        # pwd = config_obj.get('cargo', 'harbor_pwd')
        # load_images_to_cargo(user, pwd, registry, './busybox-1.28.0')
        _busybox_images = f'{registry}/library/busybox:1.28.0'
        return _busybox_images, version

    def check_node_info(self):
        for cluster in self.clusters.keys():
            self.checkout[cluster]['node_info'] = dict()
        nodes_list = list()
        for machine in self.machines.keys():
            # logger.info(f"check node {machine} info")
            n = []
            n.insert(0, machine)
            cluster = self.machines[machine]['spec']['cluster']
            if cluster:
                user = self.machines[machine]['spec']['auth']['user']
                ssh_port = int(self.machines[machine]['spec']['sshPort'])
                pwd = self.machines[machine]['spec']['auth']['password']
                key = self.machines[machine]['spec']['auth']['key']
                n.insert(1, user)
                n.insert(2, ssh_port)
                n.insert(3, pwd)
                n.insert(4, key)
                n.insert(5, cluster)
            nodes_list.append(n)
        a = AllRun(nodes_list)
        a.concurrent_run()
        r = a.get_result()
        for i in r:
            for k, v in i.items():
                self.checkout[k]['node_info'].update(v)

    def get_name_alias(self):
        alias_dict = dict()
        for cluster in self.clusters.keys():
            alias = self.clusters[cluster]['metadata']['annotations'].get('resource.caicloud.io/alias', 'compass-stack')
            alias = alias.replace('/', '_')
            alias_dict[cluster] = alias
        return alias_dict

    def start_check(self):
        self.check_node_status()
        self.check_license()
        self.check_etcd_status()
        self.check_component_status()
        self.check_volumes_status()
        self.check_node_info()


class CheckK8s(Cluster):
    def __init__(self, kube_conf, checkout, version):
        super(CheckK8s, self).__init__(kube_conf)
        self.cluster_name = Path(kube_conf).name
        self.checkout = checkout
        self.pod_list = self.get_pods()
        self.svc_list = self.get_svc()
        self.nodes = self.get_node()
        self.cps_version = version

    def check_cidr(self):
        logger.info(f"check {self.cluster_name} cidr")
        cluster_info = self.get_cm('cluster-info', 'kube-system')
        svc_total = ipaddress.ip_network(cluster_info['data']['serviceIPRange'], strict=True).num_addresses - 2
        svc_used = len(jsonpath.jsonpath(self.svc_list, '$.items[*].spec.cluster_ip'))
        svc_unused = svc_total - svc_used
        svc_status = True if svc_used < svc_total * 0.8 else False
        self.checkout[self.cluster_name]['svc_cidr'] = {
            'data': {'used': svc_used, 'total': svc_total, 'unused': svc_unused,
                     'cidr': cluster_info['data']['serviceIPRange']}, 'status': svc_status}
        network_info = self.get_network()
        pod_ip_list = jsonpath.jsonpath(self.pod_list, '$.items[*].status.pod_ip')
        node_ip_list = jsonpath.jsonpath(self.nodes, '$.items[*].status.addresses[*].address')
        pod_ip_used = set(pod_ip_list).difference(set(node_ip_list))
        self.checkout[self.cluster_name]['pod_cidr'] = dict()
        for net_name in network_info.keys():
            cidr = network_info[net_name]['spec']['subnets'][0]['cidr']
            pod_total = ipaddress.ip_network(cidr).num_addresses - 2
            if net_name == "k8s-pod-network":
                cidr_ip_list = [str(i) for i in ipaddress.ip_network(cidr).hosts()]
                pod_used = len(pod_ip_used.intersection(set(cidr_ip_list)))
                pod_unused = pod_total - pod_used
            else:
                pod_unused = network_info[net_name]['status']['subnetStatuses'][0]['available']
                pod_used = pod_total - pod_unused
            pod_status = True if pod_used < pod_total * 0.8 else False
            self.checkout[self.cluster_name]['pod_cidr'][net_name] = {
                'data': {'used': pod_used, 'total': pod_total, 'cidr': cidr, 'unused': pod_unused},
                'status': pod_status}

    def check_pod_status(self):
        logger.info(f"check {self.cluster_name} pods status")
        status_list = list(set(jsonpath.jsonpath(self.pod_list, '$.items[*].status.phase')))
        status_list.append("restart > 20")
        pod_status = {}
        for x in self.pod_list['items']:
            pod_name = x['metadata']['name']
            reason = x['status'].get('reason', None)
            phase = ''.join(jsonpath.jsonpath(x, '$.status.phase'))
            if reason == "Evicted" or phase == "Pending":
                restart = 0
            else:
                restart = sum(jsonpath.jsonpath(x, '$.status.container_statuses[*].restart_count'))
            pod_status[pod_name] = {'restart': restart, 'phase': phase}
        pod_checkout = {x: {'data': 0, 'status': True, 'name': []} for x in status_list}
        for pod in pod_status.keys():
            pod_checkout[pod_status[pod]['phase']]['data'] += 1
            if pod_status[pod]['restart'] > 20:
                pod_checkout["restart > 20"]['status'] = False
                pod_checkout["restart > 20"]['data'] += 1
                pod_checkout["restart > 20"]['name'].append(pod)
            if pod_status[pod]['phase'] not in ['Running', 'Succeeded']:
                pod_checkout[pod_status[pod]['phase']]['status'] = False
                pod_checkout[pod_status[pod]['phase']]['name'].append(pod)
        if pod_checkout["restart > 20"]['data'] == 0:
            del pod_checkout["restart > 20"]
        self.checkout[self.cluster_name]['pods_status'] = pod_checkout

    def check_coredns_status(self):
        logger.info(f"check {self.cluster_name} coredns")
        coredns_deploy = self.get_coredns(self.cps_version)
        if coredns_deploy['status']['available_replicas'] == coredns_deploy['status']['ready_replicas'] == \
                coredns_deploy['status']['replicas']:
            status = True
        else:
            status = False
        self.checkout[self.cluster_name]['coredns_status'] = {
            'data': {'available': coredns_deploy['status']['available_replicas'],
                     'ready': coredns_deploy['status']['ready_replicas'],
                     'replicas': coredns_deploy['status']['replicas']}, 'status': status}

    @staticmethod
    def __get_resource_json(crt, cru, crun, crs, clt, clu, clun, cls, mrt, mru, mrun, mrs, mlt, mlu, mlun, mls):
        data = {
            "cpu.request": {"data": {"total": crt, "unused": crun, "used": cru}, "status": crs},
            "cpu.limit": {"data": {"total": clt, "unused": clun, "used": clu}, "status": cls},
            "mem.request": {"data": {"total": mrt, "unused": mrun, "used": mru}, "status": mrs},
            "mem.limit": {"data": {"total": mlt, "unused": mlun, "used": mlu}, "status": mls}
        }
        return data

    def check_clusters_quotas(self):
        logger.info(f"check {self.cluster_name} cluster quota")
        clusters = self.get_clusterquotas()
        physical_cpu_total = parse_resource(clusters['system']['status']['physical']['capacity']['cpu'])
        physical_cpu_unused = parse_resource(clusters['system']['status']['physical']['allocatable']['cpu'])
        physical_cpu_used = round(physical_cpu_total - physical_cpu_unused, 3)

        physical_cpu_status = True if physical_cpu_unused > physical_cpu_total * 0.2 else False
        physical_cpu_unused = round(physical_cpu_unused, 3)

        physical_mem_total = parse_resource(clusters['system']['status']['physical']['capacity']['memory'])
        physical_mem_unused = parse_resource(clusters['system']['status']['physical']['allocatable']['memory'])
        physical_mem_used = f"{round((physical_mem_total - physical_mem_unused) / ONE_GIBI, 3)}Gi"
        physical_mem_status = True if physical_mem_unused > physical_mem_total * 0.2 else False
        physical_mem_unused = f"{round(physical_mem_unused / ONE_GIBI, 3)}Gi"
        physical_mem_total = f"{round(physical_mem_total / ONE_GIBI, 3)}Gi"

        logical_cpu_request_total = parse_resource(clusters['system']['status']['logical']['total']['requests.cpu'])
        logical_cpu_request_used = parse_resource(clusters['system']['status']['logical']['allocated']['requests.cpu'])
        logical_cpu_request_unused = round(logical_cpu_request_total - logical_cpu_request_used, 3)
        logical_cpu_request_status = True if logical_cpu_request_used < logical_cpu_request_total * 0.8 else False
        logical_cpu_request_used = round(logical_cpu_request_used, 3)

        logical_cpu_limit_total = parse_resource(clusters['system']['status']['logical']['total']['limits.cpu'])
        logical_cpu_limit_used = parse_resource(clusters['system']['status']['logical']['allocated']['limits.cpu'])
        logical_cpu_limit_unused = round(logical_cpu_limit_total - logical_cpu_limit_used, 3)
        logical_cpu_limit_status = True if logical_cpu_limit_used < logical_cpu_limit_total * 0.8 else False
        logical_cpu_limit_used = round(logical_cpu_limit_used, 3)

        logical_mem_request_total = parse_resource(clusters['system']['status']['logical']['total']['requests.memory'])
        logical_mem_request_used = parse_resource(
            clusters['system']['status']['logical']['allocated']['requests.memory'])
        logical_mem_request_unused = f"{round((logical_mem_request_total - logical_mem_request_used) / ONE_GIBI, 3)}Gi"
        logical_mem_request_status = True if logical_mem_request_used < logical_mem_request_total * 0.8 else False
        logical_mem_request_total = f"{round(logical_mem_request_total / ONE_GIBI, 3)}Gi"
        logical_mem_request_used = f"{round(logical_mem_request_used / ONE_GIBI, 3)}Gi"

        logical_mem_limit_total = parse_resource(clusters['system']['status']['logical']['total']['limits.memory'])
        logical_mem_limit_used = parse_resource(clusters['system']['status']['logical']['allocated']['limits.memory'])
        logical_mem_limit_unused = f"{round((logical_mem_limit_total - logical_mem_limit_used) / ONE_GIBI, 3)}Gi"
        logical_mem_limit_status = True if logical_mem_limit_used < logical_mem_limit_total * 0.8 else False
        logical_mem_limit_total = f"{round(logical_mem_limit_total / ONE_GIBI, 3)}Gi"
        logical_mem_limit_used = f"{round(logical_mem_limit_used / ONE_GIBI, 3)}Gi"

        self.checkout[self.cluster_name]['cluster_quota'] = {
            "physical": {
                "cpu": {"data": {"total": physical_cpu_total, "unused": physical_cpu_unused, "used": physical_cpu_used},
                        "status": physical_cpu_status},
                "mem": {"data": {"total": physical_mem_total, "unused": physical_mem_unused, "used": physical_mem_used},
                        "status": physical_mem_status}
            },
            "logical": self.__get_resource_json(logical_cpu_request_total, logical_cpu_request_used,
                                                logical_cpu_request_unused, logical_cpu_request_status,
                                                logical_cpu_limit_total, logical_cpu_limit_used,
                                                logical_cpu_limit_unused, logical_cpu_limit_status,
                                                logical_mem_request_total, logical_mem_request_used,
                                                logical_mem_request_unused, logical_mem_request_status,
                                                logical_mem_limit_total, logical_mem_limit_used,
                                                logical_mem_limit_unused, logical_mem_limit_status)
        }

    def __get_checkout_for_tenant_and_partitions(self, objs):
        data = dict()
        for key in objs.keys():
            cpu_request_total = parse_resource(objs[key]['status']['hard']['requests.cpu'])
            cpu_request_used = parse_resource(objs[key]['status']['used']['requests.cpu'])
            cpu_request_unused = round(cpu_request_total - cpu_request_used, 3)
            cpu_request_status = True if cpu_request_used < cpu_request_total * 0.8 else False
            cpu_request_used = round(cpu_request_used, 3)

            mem_request_total = parse_resource(objs[key]['status']['hard']['requests.memory'])
            mem_request_used = parse_resource(objs[key]['status']['used']['requests.memory'])
            mem_request_unused = f"{round((mem_request_total - mem_request_used) / ONE_GIBI, 3)}Gi"
            mem_request_status = True if mem_request_used < mem_request_total * 0.8 else False
            mem_request_total = f"{round(mem_request_total / ONE_GIBI, 3)}Gi"
            mem_request_used = f"{round(mem_request_used / ONE_GIBI, 3)}Gi"

            cpu_limit_total = parse_resource(objs[key]['status']['hard']['limits.cpu'])
            cpu_limit_used = parse_resource(objs[key]['status']['used']['limits.cpu'])
            cpu_limit_unused = round(cpu_limit_total - cpu_limit_used, 3)
            cpu_limit_status = True if cpu_limit_used < cpu_limit_total * 0.8 else False
            cpu_limit_used = round(cpu_limit_used, 3)

            mem_limit_total = parse_resource(objs[key]['status']['hard']['limits.memory'])
            mem_limit_used = parse_resource(objs[key]['status']['used']['limits.memory'])
            mem_limit_unused = f"{round((mem_limit_total - mem_limit_used) / ONE_GIBI, 3)}Gi"
            mem_limit_status = True if mem_limit_used < mem_limit_total * 0.8 else False
            mem_limit_total = f"{round(mem_limit_total / ONE_GIBI, 3)}Gi"
            mem_limit_used = f"{round(mem_limit_used / ONE_GIBI, 3)}Gi"
            data[key] = self.__get_resource_json(cpu_request_total, cpu_request_used, cpu_request_unused,
                                                 cpu_request_status, cpu_limit_total, cpu_limit_used, cpu_limit_unused,
                                                 cpu_limit_status, mem_request_total, mem_request_used,
                                                 mem_request_unused, mem_request_status, mem_limit_total,
                                                 mem_limit_used, mem_limit_unused, mem_limit_status)
        return data

    def check_tenants_quotas(self):
        logger.info(f"check {self.cluster_name} tenants quotas")
        tenants = self.get_tenants()
        del tenants['system-tenant']
        data = self.__get_checkout_for_tenant_and_partitions(tenants)
        self.checkout[self.cluster_name]['tenants_quota'] = data

    def check_partitions_quotas(self):
        logger.info(f"check {self.cluster_name} partitions quotas")
        partitions = self.get_partitions()
        ignore_list = ['default', 'kube-node-lease', 'kube-public', 'kube-system']
        for part in partitions.keys():
            if partitions[part]['status']['hard'] is None or not partitions[part]['status']['hard']:
                ignore_list.append(part)
        for key in set(ignore_list):
            if key in partitions.keys():
                del partitions[key]
        data = self.__get_checkout_for_tenant_and_partitions(partitions)
        self.checkout[self.cluster_name]['partitions_quota'] = data

    def pod_exec(self, name, ns, cmd):
        resp = stream(self.core_v1_api.connect_get_namespaced_pod_exec, name, ns, command=cmd, stderr=True, stdin=True,
                      stdout=True, tty=False, container="busybox")
        return resp

    def check_dns(self):
        logger.info(f"check {self.cluster_name} dns nslookup")
        external_domain = config_obj.get('kubernetes', 'externalDomain').split()
        internal_domain = config_obj.get('kubernetes', 'internalDomain').split()
        external_domain.extend(internal_domain)
        name = 'check-pod'
        ns = 'default'
        self.checkout[self.cluster_name]['dns_nslookup'] = {}
        for domain in external_domain:
            cmd = ['nslookup', domain]
            self.pod_exec(name, ns, cmd)
            resp = self.pod_exec(name, ns, cmd)
            pattern = re.compile("can't resolve")
            result = pattern.findall(resp)
            if result:
                status = False
                self.checkout[self.cluster_name]['dns_nslookup'][domain] = status
            else:
                self.checkout[self.cluster_name]['dns_nslookup'][domain] = True

    def __get_node_pod_ip(self):
        node_pod_ip = dict()
        for pod in self.pod_list['items']:
            node_ip = pod['status']['host_ip']
            pod_ip = pod['status']['pod_ip']
            if node_ip is None or node_ip == pod_ip:
                continue
            if node_ip not in node_pod_ip.keys():
                node_pod_ip[node_ip] = list()
            node_pod_ip[node_ip].append(pod_ip)
        return node_pod_ip

    def check_network(self):
        logger.info(f"check {self.cluster_name} network：pod -> node; pod -> pod (diff node)")
        ip_dict = self.__get_node_pod_ip()
        name = 'check-pod'
        ns = 'default'
        self.checkout[self.cluster_name]['network'] = dict()
        self.checkout[self.cluster_name]['network']["pod_to_node"] = {'data': [], 'status': True}
        self.checkout[self.cluster_name]['network']["pod_to_pod"] = {'data': [], 'status': True}
        for node in ip_dict.keys():
            cmd = ['ping', '-c', '2', node]
            resp = self.pod_exec(name, ns, cmd)
            pattern = re.compile(", 0% packet loss")
            result = pattern.findall(resp)
            if not result:
                self.checkout[self.cluster_name]['network']["pod_to_node"]['data'].append(node)
                self.checkout[self.cluster_name]['network']["pod_to_node"]['status'] = False
            pod_ip = list(ip_dict[node])[0]
            cmd1 = ['ping', '-c', '2', pod_ip]
            resp1 = self.pod_exec(name, ns, cmd1)
            result1 = pattern.findall(resp1)
            if not result1:
                self.checkout[self.cluster_name]['network']["pod_to_pod"]['data'].append(f'{node}:{pod_ip}')
                self.checkout[self.cluster_name]['network']["pod_to_pod"]['status'] = False

    def create_check_pod(self, image):
        logger.info(f"{self.cluster_name} create check pod")
        while True:
            try:
                self.core_v1_api.read_namespaced_pod('check-pod', 'default')
            except client.exceptions.ApiException:
                check_pod = {'apiVersion': 'v1', 'kind': 'Pod',
                             'metadata': {'name': 'check-pod', 'labels': {'app': 'check-pod'}},
                             'spec': {'containers': [{'name': 'busybox', 'image': image,
                                                      'command': ['sh', '-c',
                                                                  'echo Hello Kubernetes! && sleep 3600']}]}}
                self.core_v1_api.create_namespaced_pod('default', body=check_pod)

            resp = self.core_v1_api.read_namespaced_pod('check-pod', 'default').to_dict()
            if resp['status']['phase'] != 'Running':
                time.sleep(5)
            else:
                return True

    def del_check_pod(self):
        try:
            self.core_v1_api.delete_namespaced_pod('check-pod', 'default')
            logger.info('delete check-pod in default ns')
        except client.exceptions.ApiException:
            logger.info('pod check-pod not in default')

    def start_check(self):
        self.check_cidr()
        self.check_pod_status()
        self.check_coredns_status()
        self.check_clusters_quotas()
        self.check_tenants_quotas()
        self.check_partitions_quotas()
        self.check_dns()
        self.check_network()
