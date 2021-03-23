import  json
from connection import RemoteClient

class nodecheck(RemoteClient):
    def __init__(self,host):
        super(nodecheck,self).__init__(host)

    def get_docker(self):
        docker_status=[]
        cmd="systemctl is-active docker"
        isDockerActive=self.execute_commands(cmd)
        if isDockerActive[0].replace('\n', '').replace('\r', '')=="active":
            cmd=r"dockerPid=$(ps aux |grep /bin/dockerd|grep -v grep |awk '{print $2}');cat /proc/$dockerPid/limits |grep files |awk '{print $(NF-1)}';ls -lR  /proc/$dockerPid/fd |grep '^l'|wc -l"
            dockerFD=self.execute_commands(cmd)