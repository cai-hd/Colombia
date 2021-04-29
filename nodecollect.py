#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@author:liping
@time: 2021/03/23
@contact: liping.1@bytedance.com
@software: PyCharm
"""

import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from log import logger
from utils import RemoteClientCompass, config_obj

AllResult = list()


def strstrip(a: str) -> str:
    return a.replace('\n', '').replace('\r', '')


class nodecheck(RemoteClientCompass):
    def __init__(self, host, user, ssh_port, pwd, ssh_key):
        super(nodecheck, self).__init__(host, user, ssh_port, pwd, ssh_key)
        self.execute_commands = self.cmd

    def get_docker(self):
        """
        {
            'docker': {
                'dockerProcess': ['active\n'],
                'maxDockerFD': '65536',
                'usedDockerFD': '158',
                'dockerFDPercentage': 0.0024
            }
        }
        """
        docker_status = defaultdict(dict)
        cmd = r'''systemctl is-active docker'''
        isDockerActive = self.execute_commands(cmd)
        # if strstrip(isDockerActive[0])=="active":
        if isinstance(isDockerActive, list):
            cmd = r'''dockerPid=$(ps aux |grep /bin/dockerd|grep -v grep |awk '{print $2}');cat /proc/$dockerPid/limits |grep files |awk '{print $(NF-1)}';ls -lR  /proc/$dockerPid/fd |grep '^l'|wc -l'''
            dockerFD = self.execute_commands(cmd)
            maxDockerFD = strstrip(dockerFD[0])
            usedDockerFD = strstrip(dockerFD[1])
            dockerFDPercentage = float("%0.4f" %
                                       (int(usedDockerFD) / int(maxDockerFD)))
            docker_status["docker"]["dockerProcess"] = "active"
            docker_status["docker"]["maxDockerFD"] = maxDockerFD
            docker_status["docker"]["usedDockerFD"] = usedDockerFD
            docker_status["docker"]["dockerFDPercentage"] = dockerFDPercentage
        else:
            docker_status["docker"]["dockerProcess"] = "inactive"
            docker_status["docker"]["maxDockerFD"] = None
            docker_status["docker"]["usedDockerFD"] = None
            docker_status["docker"]["dockerFDPercentage"] = None

        return docker_status

    def get_load(self):
        """
        {
            'nodeload': {
                'check_result': True,
                'loadaverage': '0.31, 0.19, 0.16'
            }
        }
        """
        nodeLoad = defaultdict(dict)
        cmd = r'''cpuCount=$(lscpu |grep 'CPU(s):'|grep -v -i numa|awk '{print $NF}');maxCpuLoad=$(($cpuCount*2));loadAverage=$(uptime |awk -F ':' '{print  $NF}');echo $loadAverage|awk  -F',| +' -v load=$maxCpuLoad '{if($1<load && $2<load && $3<load){print "OK"}else{print "highLoad"}}';echo $loadAverage  '''
        load = self.execute_commands(cmd)
        if strstrip(load[0]) == "OK":
            nodeLoad["nodeload"]["check_result"] = True
        else:
            nodeLoad["nodeload"]["check_result"] = False

        nodeLoad["nodeload"]["loadaverage"] = strstrip(load[1])
        return nodeLoad

    def get_contrack(self):
        """
        {
            'contrack': {
                'contrack_max': '262144',
                'contrack_used': '1144',
                'percentage': 0.0044
            }
        }
        """
        contrack = defaultdict(dict)
        cmd = r'''cat /proc/sys/net/nf_conntrack_max;cat /proc/sys/net/netfilter/nf_conntrack_count'''
        response = self.execute_commands(cmd)
        contrack["contrack"]["contrack_max"] = strstrip(response[0])
        contrack["contrack"]["contrack_used"] = strstrip(response[1])
        contrack["contrack"]["contrack_percentage"] = float(
            "%0.4f" % (int(strstrip(response[1])) / int(strstrip(response[0]))))
        return contrack

    def get_openfile(self):
        """
        {
            'openfile': {
                'openfile_max': '788659',
                'openfile_used': '5568',
                'openfile_percentage': 0.0071
            }
        }
        """
        openfile = defaultdict(dict)
        cmd = r'''cat /proc/sys/fs/file-nr'''
        response = self.execute_commands(cmd)
        a = strstrip(response[0]).split()[2]
        b = strstrip(response[0]).split()[0]
        openfile["openfile"]["openfile_max"] = a
        openfile["openfile"]["openfile_used"] = b
        openfile["openfile"]["openfile_percentage"] = float(
            "%0.4f" % (int(b) / int(a)))
        return openfile

    def get_pid(self):
        """
        {
            'pid': {
                'pid_max': '32768',
                'contrack_used': '267',
                'pid_percentage': 0.0081
            }
        }
        """
        pid = defaultdict(dict)
        cmd = r'''ls -ld  /proc/[0-9]* |wc -l;cat /proc/sys/kernel/pid_max'''
        response = self.execute_commands(cmd)
        pid["pid"]["pid_max"] = strstrip(response[1])
        pid["pid"]["pid_used"] = strstrip(response[0])
        pid["pid"]["pid_percentage"] = float("%0.4f" % (
                int(strstrip(response[0])) / int(strstrip(response[1]))))
        return pid

    def get_dns(self):
        """
        {
           "dns":[
               {"dnsname":"www.baidu.com",
                "checkpass":True,
                "result":""
              },
              {"dnsname":"www.baidu.com",
                "checkpass":False,
                "result":"command not found" #or  "can't resolve"
              }
           ]
        }
c
        """
        dnslist = config_obj.get('kubernetes', 'externalDomain').split()
        dns = defaultdict(list)
        for i in dnslist:
            d = {}
            d["dnsname"] = i
            cmd = "which host || yum -y -q  install  bind-utils;host {}".format(i)
            r = self.execute_commands(cmd)
            if isinstance(r, list):
                d["checkpass"] = True
                d["result"] = ""
            else:
                d["checkpass"] = False
                if r.find("command not found") >= 0:
                    d["result"] = "command not found"
                else:
                    d["result"] = "can't resolve"
            dns["dns"].append(d)
        return dns

    def get_diskIO(self):
        """
        {
        diskio:[
          {"device":"sda",
           "check_result":{
            "isNormal":False
            "data":[[xxxx],[xxxxx]
              ]
            }
          },
          {"device":"sdb",
           "check_result":{
            "isNormal":True
            "data":[]
             }
           }
         ]
        }
        """
        diskio = defaultdict(list)
        cmd = r'''iostat -x 2  5'''
        response = self.execute_commands(cmd)
        d = defaultdict(list)
        for i in response:
            if i == "\r\n" or i == "\n":
                continue
            else:
                b = i.strip().split()
                a = re.match("[sv]d[a-z]", b[0])
                if a:
                    d[b[0]].append(b[1::])

        for k, v in d.items():
            d1 = defaultdict(dict)
            l = []
            for i in v:
                if len(i) == 13:
                    if float(
                            i[7]) > 5 or float(
                        i[8]) > 100 or float(
                        i[9]) > 100 or float(
                        i[10]) > 100:
                        l.append(i)
                else:
                    if float(
                            i[8]) > 100 or float(
                        i[9]) > 100 or float(
                        i[10]) > 5:
                        l.append(i)
            if len(l) == 0:
                d1["device"] = k
                d1["check_result"]["isNormal"] = True
                d1["check_result"]["data"] = []
            else:
                d1["device"] = k
                d1["check_result"]["isNormal"] = False
                d1["check_result"]["data"] = l
            diskio["diskio"].append(d1)
        return diskio

    def get_diskUsage(self):
        """
        {
        'diskusage': [
        {
            'Filesystem': '/dev/sda1',
            'Size': '50G',
            'Used ': '21G',
            'Avail': '30G',
            'Use%': '41%',
            'Mounted': '/'
        }, {
            'Filesystem': '/dev/sdb1',
            'Size': '150G',
            'Used ': '102G',
            'Avail': '49G',
            'Use%': '68%',
            'Mounted': '/compass'
          }
         ]
        }
        """
        diskusage = defaultdict(list)
        cmd = r'''df -h|grep -v -E "token|secret|overlay2|containers|tmpfs|kubernetes.io|Filesystem" '''
        response = self.execute_commands(cmd)
        for i in response:
            d = {}
            j = strstrip(i).split()
            d["Filesystem"] = j[0]
            d["Size"] = j[1]
            d["Used "] = j[2]
            d["Avail"] = j[3]
            d["Use%"] = j[4]
            d["Mounted"] = j[5]
            diskusage["diskusage"].append(d)
        return diskusage

    def get_nic(self):
        """
         {
        nicio:[
          {"device":"eth0",
           "check_result":{
            "isNormal":False
            "data":[[xxxx],[xxxxx]
              ]
            }
          },
          {"device":"eth1",
           "check_result":{
            "isNormal":True
            "data":""
             }
           }
         ]
        }

        pps=200000 nictraffic=500000
        """

        nicresult = defaultdict(list)
        cmd = r'''ip r|grep -v br_bond|grep -E -o "eth[0-9]*|bond[0-9]*|ens[0-9]*"|sort -u'''
        niclist = self.execute_commands(cmd)
        cmd1 = r'''sar -n DEV 1 8'''
        nicstatus = self.execute_commands(cmd1)
        for j in niclist:
            d1 = defaultdict(dict)
            c = '(Average:)(\\s)+{}'.format(strstrip(j))
            for i in nicstatus:
                if i == "\r\n" or i == "\n":
                    continue
                else:
                    if re.match(c, i):
                        # print(i)
                        k = i.split()
                        if float(
                                k[2]) > 300000 or float(
                            k[3]) > 300000 or float(
                            k[4]) > 500000 or float(
                            k[5]) > 500000:
                            d1["device"] = strstrip(j)
                            d1["check_result"]["isNormal"] = False
                            d1["check_result"]["data"] = i
                        else:
                            d1["device"] = strstrip(j)
                            d1["check_result"]["isNormal"] = True
                            d1["check_result"]["data"] = ""
                        nicresult["nicio"].append(d1)
        return nicresult

    def get_zprocess(self):
        """
        {
            "zprocess":{
                "checkpass":False,
                "result":['xxxxx','xxxxx']
            }

        }
        """
        zprocess = defaultdict(dict)
        cmd = r'''ps -A -ostat,ppid,pid,cmd | grep -e '^[Zz]' '''
        r = self.execute_commands(cmd)
        if isinstance(r, list):
            zprocess["zprocess"]["checkpass"] = False
            zprocess["zprocess"]["result"] = r
        else:
            zprocess["zprocess"]["checkpass"] = True
            zprocess["zprocess"]["result"] = []
        return zprocess

    def get_ntp(self):
        """
        {
            'ntp': {
                'checkpass': False,
                'result': 'NTP_NOT_SYNCED'
            }
        }

        """
        ntp = defaultdict(dict)
        cmd = r'''timedatectl  status|grep synchronized|awk -F':| +' '{print $NF}' '''
        r = self.execute_commands(cmd)
        if strstrip(r[0]) == "yes":
            cmd = r'''chronyc  sources|grep -E "^\^\*" |cut  -d[ -f 1|awk '{print $NF}' '''
            r = self.execute_commands(cmd)
            if r:
                n = re.findall('\\d+', strstrip(r[0]))[0]
                unit = re.findall('[a-z]+', strstrip(r[0]))[0]
                if unit == "ns":
                    m = float("%0.6f" % (int(n) / 1000000000))
                elif unit == "us":
                    m = float("%0.6f" % (int(n) / 1000000))
                elif unit == "ms":
                    m = float("%0.6f" % (int(n) / 1000))
                else:
                    m = int(n)

                if m >= 1:
                    ntp["ntp"]["checkpass"] = False
                    ntp["ntp"]["result"] = "NTP_IS_DIFF_{}".format(r[0])
                else:
                    ntp["ntp"]["checkpass"] = True
                    ntp["ntp"]["result"] = "NTP_IS_OK"
            else:
                ntp["ntp"]["checkpass"] = False
                ntp["ntp"]["result"] = "NTP_IS_SYNCING"
        else:
            ntp["ntp"]["checkpass"] = False
            ntp["ntp"]["result"] = "NTP_NOT_SYNCED"

        return ntp

    def get_containerd(self):
        containerd = defaultdict(dict)
        cmd = r'''pgrep -fl containerd|grep -Ev "shim|dockerd|bash"  '''
        r = self.execute_commands(cmd)
        if isinstance(r, list):
            containerd["containerd"]["checkpass"] = True
        else:
            containerd["containerd"]["checkpass"] = False
        return containerd

    def get_kubelet(self):
        """
        {
            'kubelet': {
                'process': 'inactive',
                'porthealth': 'failed'
            }
        }
        """
        kubelet = defaultdict(dict)
        cmd = r'''systemctl  is-active kubelet '''
        r = self.execute_commands(cmd)
        if isinstance(r, list):
            cmd = r'''curl --connect-timeout 5 -sk  127.0.0.1:10248/healthz'''
            r1 = self.execute_commands(cmd)
            if isinstance(r1, list) and strstrip(r1[0]) == "ok":
                kubelet["kubelet"]["process"] = "active"
                kubelet["kubelet"]["porthealth"] = "ok"
            else:
                kubelet["kubelet"]["process"] = "active"
                kubelet["kubelet"]["porthealth"] = "failed"
        else:
            kubelet["kubelet"]["process"] = "inactive"
            kubelet["kubelet"]["porthealth"] = "failed"

        return kubelet

    def get_kubeproxy(self):
        kubeproxy = defaultdict(dict)
        cmd = r'''curl --connect-timeout 5 -sk 127.0.0.1:10249/healthz'''
        r = self.execute_commands(cmd)
        if isinstance(r, list) and strstrip(r[0]) == "ok":
            kubeproxy["kubeproxy"]["porthealth"] = True
        else:
            kubeproxy["kubeproxy"]["porthealth"] = False
        return kubeproxy

    def start_check(self):
        check_data = dict()
        check_data.update(self.get_docker())
        check_data.update(self.get_load())
        check_data.update(self.get_contrack())
        check_data.update(self.get_openfile())
        check_data.update(self.get_pid())
        check_data.update(self.get_dns())
        check_data.update(self.get_diskIO())
        check_data.update(self.get_diskUsage())
        check_data.update(self.get_nic())
        check_data.update(self.get_zprocess())
        check_data.update(self.get_ntp())
        check_data.update(self.get_containerd())
        check_data.update(self.get_kubelet())
        check_data.update(self.get_kubeproxy())
        return check_data


class AllRun(object):
    def __init__(self, ssh_objs, max_worker=10):
        self.ssh_objs = ssh_objs
        self.max_worker = max_worker

    def single_exec(self, obj):
        ip, ssh_user, ssh_port, ssh_pass, ssh_key, cluster = obj
        n = nodecheck(ip, ssh_user, ssh_port, ssh_pass, ssh_key)
        logger.info('start check {} node {}'.format(cluster, ip))
        start = time.time()
        r = n.start_check()
        end = time.time() - start
        logger.info('{} node {} check completed, task took {} seconds'.format(cluster, ip, round(end)))
        return {cluster: {ip: r}}

    def concurrent_run(self):
        f = ThreadPoolExecutor(self.max_worker)
        for s in self.ssh_objs:
            try:
                f.submit(self.single_exec, s).add_done_callback(self.callback)
            except Exception as err:
                logger.error(err)
        f.shutdown(wait=True)

    def callback(self, ssh_result):
        sr = ssh_result.result()
        AllResult.append(sr)

    def get_result(self):
        return AllResult

# def checknode(ip: str, ssh_user:str,ssh_port:int,ssh_pass:str,ssh_key:str):
#     c = {}
#     n = nodecheck(ip, ssh_user,ssh_port,ssh_pass,ssh_key)
#     for i in [
#         "docker",
#         "load",
#         "contrack",
#         "openfile",
#         "pid",
#         "dns",
#         "diskIO",
#         "diskUsage",
#         "nic",
#         "zprocess",
#         "ntp",
#         "containerd",
#         "kubelet",
#         "kubeproxy"]:
#         m = getattr(n, "get_{}".format(i))
#         r = m()
#         c.update(r)
#     return {ip: c}
#
#
# def callback(msg):
#     q.put(msg)
#
#
# def get_result():
#     check_result = dict()
#     while not q.empty():
#         i = q.get()
#         check_result.update(i)
#     return check_result
#
#
# def checkAllNodes(nodes: []):
#     p = Pool(processes=8)
#     for i in nodes:
#         ip=i[0]
#         user=i[1]
#         port=i[2]
#         pwd=i[3]
#         key=i[4]
#         p.apply_async(
#             func=checknode,
#             args=(ip,user,port,pwd,key),
#             callback=callback)
#     p.close()
#     p.join()
#
#
# def run(nodes: []):
#     checkAllNodes(nodes)
#     results = get_result()
#     return results


# if __name__ == '__main__':
#     rr = run(["120.221.92.23"])
#     print(rr)

# n=nodecheck(host="120.221.92.23",ssh_key_filepath="./secret/id_rsa")
# # n.execute_commands(r'''host www.baidfffu.com''')
# c=n.get_nic()
# print(c)

# noderesult = checknode(ip="120.221.92.23", key_filepath="./secret/id_rsa")
# print(noderesult)
