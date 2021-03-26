#!/usr/bin/env python3
#-*- coding: utf-8 -*-
"""
@author:liping
@time: 2021/03/23
@contact: liping.1@bytedance.com
@software: PyCharm
"""


from connection import RemoteClient
from collections import defaultdict
import re

def strstrip(a: str)->str:
    return a.replace('\n', '').replace('\r', '')


class nodecheck(RemoteClient):
    def __init__(self,host,user="root",ssh_key_filepath="/root/.ssh/id_rsa",ssh_port=22):
        super(nodecheck,self).__init__(host,user,ssh_key_filepath,ssh_port)

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
        docker_status=defaultdict(dict)
        cmd=r'''systemctl is-active docker'''
        isDockerActive=self.execute_commands(cmd)
        if strstrip(isDockerActive[0])=="active":
            cmd=r'''dockerPid=$(ps aux |grep /bin/dockerd|grep -v grep |awk '{print $2}');cat /proc/$dockerPid/limits |grep files |awk '{print $(NF-1)}';ls -lR  /proc/$dockerPid/fd |grep '^l'|wc -l'''
            dockerFD=self.execute_commands(cmd)
            maxDockerFD=strstrip(dockerFD[0])
            usedDockerFD=strstrip(dockerFD[1])
            dockerFDPercentage=float("%0.4f"%(int(usedDockerFD)/int(maxDockerFD)))
            docker_status["docker"]["dockerProcess"]=isDockerActive
            docker_status["docker"]["maxDockerFD"]=maxDockerFD
            docker_status["docker"]["usedDockerFD"]=usedDockerFD
            docker_status["docker"]["dockerFDPercentage"] = dockerFDPercentage
            return  docker_status
        else:
            docker_status["docker"]["dockerProcess"] = isDockerActive
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
        nodeLoad=defaultdict(dict)
        cmd=r'''cpuCount=$(lscpu |grep 'CPU(s):'|grep -v -i numa|awk '{print $NF}');maxCpuLoad=$(($cpuCount*2));loadAverage=$(uptime |awk -F ':' '{print  $NF}');echo $loadAverage|awk  -F',| +' -v load=$maxCpuLoad '{if($1<load && $2<load && $3<load){print "OK"}else{print "highLoad"}}';echo $loadAverage  '''
        load=self.execute_commands(cmd)
        if strstrip(load[0])=="OK":
            nodeLoad["nodeload"]["check_result"] = True
        else:
            nodeLoad["nodeload"]["check_result"] = False

        nodeLoad["nodeload"]["loadaverage"]=strstrip(load[1])
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
        contrack=defaultdict(dict)
        cmd=r'''cat /proc/sys/net/nf_conntrack_max;cat /proc/sys/net/netfilter/nf_conntrack_count'''
        response=self.execute_commands(cmd)
        contrack["contrack"]["contrack_max"]=strstrip(response[0])
        contrack["contrack"]["contrack_used"] = strstrip(response[1])
        contrack["contrack"]["contrack_percentage"]=float("%0.4f"%(int(strstrip(response[1]))/int(strstrip(response[0]))))
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
        openfile=defaultdict(dict)
        cmd=r'''cat /proc/sys/fs/file-nr'''
        response = self.execute_commands(cmd)
        a=strstrip(response[0]).split()[2]
        b=strstrip(response[0]).split()[0]
        openfile["openfile"]["openfile_max"] =a
        openfile["openfile"]["openfile_used"] = b
        openfile["openfile"]["openfile_percentage"] = float("%0.4f" % (int(b) / int(a)))
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
        pid=defaultdict(dict)
        cmd=r'''ls -ld  /proc/[0-9]* |wc -l;cat /proc/sys/kernel/pid_max'''
        response=self.execute_commands(cmd)
        pid["pid"]["pid_max"] = strstrip(response[1])
        pid["pid"]["contrack_used"] = strstrip(response[0])
        pid["pid"]["pid_percentage"] = float("%0.4f" % (int(strstrip(response[0])) / int(strstrip(response[1]))))
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

        """
        dnslist=["www.baidu.com","www.xxffffwwx.com"]
        dns=defaultdict(list)
        for i in dnslist:
            d={}
            d["dnsname"] = i
            cmd="host {}".format(i)
            r=self.execute_commands(cmd)
            if isinstance(r,list):
                d["checkpass"]=True
                d["result"]=""
            else:
                d["checkpass"] = False
                if r.find("command not found")>=0:
                    d["result"] ="command not found"
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
        cmd=r'''iostat -x 2  5'''
        response=self.execute_commands(cmd)
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
                    if float(i[7]) > 5 or float(i[8]) > 100 or float(i[9]) > 100 or float(i[10]) > 100:
                        l.append(i)
                else:
                    if float(i[8]) > 100 or float(i[9]) > 100 or float(i[10]) > 5:
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
        diskusage=defaultdict(list)
        cmd=r'''df -h|grep -v -E "token|secret|overlay2|containers|tmpfs|kubernetes.io|Filesystem" '''
        response=self.execute_commands(cmd)
        for i in response:
            d={}
            print(i)
            j=strstrip(i).split()
            d["Filesystem"]=j[0]
            d["Size"] = j[1]
            d["Used "] = j[2]
            d["Avail"] = j[3]
            d["Use%"] = j[4]
            d["Mounted"] = j[5]
            diskusage["diskusage"].append(d)
        return diskusage

    def get_nic(self):
        pass


    def get_zprocess(self):
        """
        {
            "zprocess":{
                "checkpass":False,
                "result":['xxxxx','xxxxx']
            }

        }
        """
        zprocess=defaultdict(dict)
        cmd=r'''ps -A -ostat,ppid,pid,cmd | grep -e '^[Zz]' '''
        r=self.execute_commands(cmd)
        if isinstance(r,list):
            zprocess["zprocess"]["checkpass"]=False
            zprocess["zprocess"]["result"]=r
        else:
            zprocess["zprocess"]["checkpass"]=True
            zprocess["zprocess"]["result"]=""
        return  zprocess

    def get_ntp(self):
        """
        {
            'ntp': {
                'checkpass': False,
                'result': 'NTP_NOT_SYNCED'
            }
        }

        """
        ntp=defaultdict(dict)
        cmd=r'''timedatectl  status|grep synchronized|awk -F':| +' '{print $NF}' '''
        r=self.execute_commands(cmd)
        if strstrip(r[0])=="yes":
            cmd=r'''chronyc  sources|grep -E "^\^\*" |cut  -d[ -f 1|awk '{print $NF}' '''
            r=self.execute_commands(cmd)
            if r:
                n=re.findall('\d+',strstrip(r[0]))[0]
                unit=re.findall('[a-z]+',strstrip(r[0]))[0]
                if unit=="ns":
                    m=float("%0.6f"%(int(n)/1000000000))
                elif unit=="us":
                    m = float("%0.6f" % (int(n) / 1000000))
                elif unit=="ms":
                    m = float("%0.6f" % (int(n) / 1000))
                else:
                    m=int(n)

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
            ntp["ntp"]["checkpass"]=False
            ntp["ntp"]["result"]="NTP_NOT_SYNCED"

        return ntp

    def get_containerd(self):
        containerd=defaultdict(dict)
        cmd=r'''pgrep -fl containerd|grep -Ev "shim|dockerd|bash"  '''
        r=self.execute_commands(cmd)
        if isinstance(r,list):
            containerd["containerd"]["checkpass"]=True
        else:
            containerd["containerd"]["checkpass"] = False
        return containerd


    def get_kubelet(self):
        kubelet=defaultdict(dict)
        cmd=r'''systemctl  is-active kubelet '''
        r=self.execute_commands(cmd)
        if strstrip(r[0]) == "active":
            pass

    def get_kubeproxy(self):
        pass

n=nodecheck(host="120.221.92.23",ssh_key_filepath="./secret/id_rsa")
# n.execute_commands(r'''host www.baidfffu.com''')
c=n.get_dns()
print(c)