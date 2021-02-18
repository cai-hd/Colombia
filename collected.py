import json
from connection import RemoteClient


class Collect:
    """

    """

    def get_docker(self):
        """

        :return:
        """

        #for i in ip_list:
        #    i = ip
        #    ssh.execute_commands
        cmd = "systemctl status docker"
        result = self.session.execute_commands(cmd)
        return {"desc": "docker", "result": [i for i in result]}





