import json
from connection import RemoteClient
from multiprocessing import Pool,Queue
from time import sleep
from collections import defaultdict

nodes=["119.167.202.131","120.221.92.19"]
q=Queue()

"""
component_list = []
return {"desc": "component", "result": component_list}
 
 {
 "desc":"node_health",
 "result":
   [ {"1.1.1.1":{
     "check_docker":"",
     "check_uptime":"{"check_status":"info","check_data":"1,2,3"}",
     "check_disusage":"",
     "check_diskIO":"{"result":"","check_data":"","commandExStatus":""}"  
     "check_Net":""
       }
     },
   ]
 }
"""


# class Collect:
#     """
#
#     """
#
#     def get_docker(self):
#         """
#
#         :return:
#         """
#
#         #for i in ip_list:
#         #    i = ip
#         #    ssh.execute_commands
#         cmd = "systemctl status docker"
#         result = self.session.execute_commands(cmd)
#         return {"desc": "docker", "result": [i for i in result]}


def put_script(nodes):
    p=Pool()
    for i in nodes:
        r=RemoteClient(host=i)
        p.apply_async(r.sftp_put_file,args=("./scripts/check_node-v1.sh","/tmp/"))
    p.close()
    p.join()


def run_ssh(ip):
    r = RemoteClient(host=ip)
    c = r.connect()
    channel = c.invoke_shell()
    channel.send("bash /tmp/check_node-v1.sh  \n")
    buff = ''
    sleep(2)
    while not str(buff).endswith(('# ', '$ ')):
        recv = channel.recv(1024)
        buff += recv.decode("utf-8")
    r.disconnect()
    return (ip,buff.splitlines())

def run_callback(msg):
    ip,result=msg
    r = defaultdict(list)
    for i in result:
        try:
            b=json.loads(i)
            c = b['check_point']
            r[c].append({"alert_status": b['alert_status'], "check_data": b['check_data']})
        except json.JSONDecodeError as e:
            continue
    j = r['diskUsage'][0]['check_data'].split()
    j2 = [j[i:i + 6] for i in range(0, len(j), 6)]
    l = []
    for i in j2:
        d = {}
        d['Filesystem'] = i[0]
        d['Size'] = i[1]
        d['Used'] = i[2]
        d['Avail'] = i[3]
        d['Use%'] = i[4]
        d['Mounted'] = i[5]
        l.append(d)
    r['diskUsage'][0]['check_data'] = l
    q.put({ip:r})


def get_result():
    check_result=[]
    while not q.empty():
        i=q.get()
        check_result.append(i)
    return {"desc":"nodecheck","result":check_result}

def run_check(nodes):
    p = Pool()
    for i in nodes:
        p.apply_async(func=run_ssh,args=(i,),callback=run_callback)
    p.close()
    p.join()


def run(nodes):
    put_script(nodes)
    run_check(nodes)
    c=get_result()
    return c

