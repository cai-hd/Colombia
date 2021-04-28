#!/usr/bin/env python3 
# -*- coding:utf-8 _*-
""" 
@author:fjg
@license: Apache Licence 
@file: clusters.py
@time: 2021/04/06
@contact: fujiangong.fujg@bytedance.com
@site:  
@software: PyCharm 
"""

# Built-in
import yaml
import base64
import os
# others
from kubernetes import client, config
# project
from utils import config_obj, base_request, base_header


class K8sClusters:

    def __init__(self):
        self.kube_conf = config_obj.get("kubernetes", "k8s_conf_path")
        config.load_kube_config(self.kube_conf)
        self.custom_api = client.CustomObjectsApi()
        self.core_api = client.CoreV1Api()
        self.clusters = self.get_clusters()

    def get_clusters(self) -> dict:
        clusters_obj = self.custom_api.list_cluster_custom_object("resource.caicloud.io", "v1beta1", "clusters")
        clusters = {x["metadata"]["name"]: x for x in clusters_obj["items"]}
        return clusters

    def get_machines(self) -> dict:
        machines_obj = self.custom_api.list_cluster_custom_object("resource.caicloud.io", "v1beta1", "machines")
        machines = {x["metadata"]["name"]: x for x in machines_obj["items"]}
        return machines

    def get_license(self):
        path = "/apis/admin.license.caicloud.io/v1/stat"
        for master_ip in self.clusters["compass-stack"]["spec"]["masters"]:
            url = f"http://{master_ip}:6002{path}"
            status, ret = base_request(method="get", url=url, headers=base_header)
            if status:
                return ret
            else:
                continue

    def get_clusters_conf(self):
        k8s_conf_path_list = list()
        with open(self.kube_conf, "r") as ckf:
            kube_conf_template_data = yaml.full_load(ckf)
        for cluster_name in self.clusters.keys():
            cluster = self.clusters[cluster_name]
            name = cluster["metadata"]["name"]
            certificate_authority_data = cluster["spec"]["auth"]["kubeConfig"]["clusters"][name][
                "certificate-authority-data"]
            server = cluster["spec"]["auth"]["kubeConfig"]["clusters"][name]["server"]
            client_certificate_data = cluster["spec"]["auth"]["kubeConfig"]["users"]["kubectl"][
                "client-certificate-data"]
            client_key_data = cluster["spec"]["auth"]["kubeConfig"]["users"]["kubectl"]["client-key-data"]
            dir_path = os.getcwd()
            file_path = f'{dir_path}/tmp/cluster/{name}'
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as kf:
                kube_conf_template_data["clusters"][0]["cluster"]["server"] = server
                kube_conf_template_data["clusters"][0]["cluster"][
                    "certificate-authority-data"] = certificate_authority_data
                kube_conf_template_data["clusters"][0]["name"] = name
                kube_conf_template_data["contexts"][0]["context"]["cluster"] = name
                kube_conf_template_data["users"][0]["user"]["client-certificate-data"] = client_certificate_data
                kube_conf_template_data["users"][0]["user"]["client-key-data"] = client_key_data
                yaml.dump(kube_conf_template_data, kf)
            k8s_conf_path_list.append(file_path)
        return k8s_conf_path_list

    def get_ssh_config(self):
        private_pem = str()
        try:
            ssh_config = self.custom_api.get_cluster_custom_object("resource.caicloud.io", "v1beta1", "configs",
                                                                   "ssh-global")
        except client.exceptions.ApiException:
            ssh_config = self.core_api.read_namespaced_secret("login-config-ssh-global", "kube-system").to_dict()
        if ssh_config["kind"] == "Secret":
            private_pem = ssh_config["data"]['private.pem'].encode("utf-8")
        elif ssh_config["kind"] == "Config":
            private_pem = ssh_config['values']['private.pem']
        private_pem_data = base64.b64decode(private_pem).decode("utf-8")
        dir_path = os.getcwd()
        ssh_key_file_path = f'{dir_path}/tmp/private.pem'
        os.makedirs(os.path.dirname(ssh_key_file_path), exist_ok=True)
        with open(ssh_key_file_path, "w") as pm:
            pm.write(private_pem_data)
        os.chmod(ssh_key_file_path, 0o600)
        return ssh_key_file_path

    def get_cm(self, name, ns) -> dict:
        cluster_info = self.core_api.read_namespaced_config_map(name, ns).to_dict()
        return cluster_info


class Cluster:
    def __init__(self, kube_conf):
        self.kube_conf = kube_conf
        config.load_kube_config(self.kube_conf)
        self.custom_api = client.CustomObjectsApi()
        self.core_v1_api = client.CoreV1Api()
        self.app_v1_api = client.AppsV1Api()
        self.batch_v1_api = client.BatchV1Api()

    def get_partitions(self) -> dict:
        partitions_obj = self.custom_api.list_cluster_custom_object("tenant.caicloud.io", "v1alpha1", "partitions")
        partitions = {x["metadata"]["name"]: x for x in partitions_obj["items"]}
        return partitions

    def get_tenants(self) -> dict:
        tenants_obj = self.custom_api.list_cluster_custom_object("tenant.caicloud.io", "v1alpha1", "tenants")
        tenants = {x["metadata"]["name"]: x for x in tenants_obj["items"]}
        return tenants

    def get_clusterquotas(self) -> dict:
        clusterquotas_obj = self.custom_api.list_cluster_custom_object("tenant.caicloud.io", "v1alpha1",
                                                                       "clusterquotas")
        clusterquotas = {x["metadata"]["name"]: x for x in clusterquotas_obj["items"]}

        return clusterquotas

    def get_pods(self) -> dict:
        pods_obj = self.core_v1_api.list_pod_for_all_namespaces().to_dict()
        return pods_obj

    def get_deployments(self) -> dict:
        deployments_obj = self.app_v1_api.list_deployment_for_all_namespaces().to_dict()
        return deployments_obj

    def get_coredns(self) -> dict:
        coredns_obj = self.app_v1_api.read_namespaced_deployment_status(namespace="kube-system",
                                                                        name='coredns').to_dict()
        return coredns_obj

    def get_svc(self) -> dict:
        svc_obj = self.core_v1_api.list_service_for_all_namespaces().to_dict()
        return svc_obj

    def get_cm(self, name, ns) -> dict:
        cluster_info = self.core_v1_api.read_namespaced_config_map(name, ns).to_dict()
        return cluster_info

    def get_node(self) -> dict:
        nodes_obj = self.core_v1_api.list_node().to_dict()
        return nodes_obj

    def get_network(self):
        network_ojb = self.custom_api.list_cluster_custom_object("resource.caicloud.io", "v1beta1", "networks")
        network_info = {x["metadata"]["name"]: x for x in network_ojb["items"]}
        return network_info
