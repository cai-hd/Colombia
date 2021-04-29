import re
import sys
from configparser import ConfigParser
import paramiko
import requests
from requests.auth import HTTPBasicAuth

from log import logger

ONE_MEBI = 1024 ** 2
ONE_GIBI = 1024 ** 3
RESOURCE_PATTERN = re.compile(r"^(\d*)(\D*)$")

FACTORS = {
    "n": 1 / 1000000000,
    "u": 1 / 1000000,
    "m": 1 / 1000,
    "": 1,
    "k": 1000,
    "M": 1000 ** 2,
    "G": 1000 ** 3,
    "T": 1000 ** 4,
    "P": 1000 ** 5,
    "E": 1000 ** 6,
    "Ki": 1024,
    "Mi": 1024 ** 2,
    "Gi": 1024 ** 3,
    "Ti": 1024 ** 4,
    "Pi": 1024 ** 5,
    "Ei": 1024 ** 6,
}

config_obj = ConfigParser()
config_obj.read("config.ini")
base_header = {"X-Tenant": "system-tenant", "Content-Type": "application/json", "Accept": "application/json"}


def parse_resource(v):
    if v is None:
        return 0
    """
    Parse a Kubernetes resource value.

    >>> parse_resource('100m')
    0.1
    >>> parse_resource('100M')
    1000000000
    >>> parse_resource('2Gi')
    2147483648
    >>> parse_resource('2k')
    2048
    """
    match = RESOURCE_PATTERN.match(v)
    factor = FACTORS[match.group(2)]
    return int(match.group(1)) * factor


def base_request(method, url, data=None, headers=None):
    """
    通用的请求模板
    :param method: 请求的方法
    :param url: 请求 的路径
    :param data: 请求的内容
    :param headers: 请求的header
    :return: 返回请求是否成功，并返回请求返回的内容
    """
    method = method.lower()
    user = config_obj.get("kubernetes", "admin_user_name")
    pwd = config_obj.get("kubernetes", "admin_user_pwd")

    if method == "get":
        ret = requests.get(url, params=data, auth=HTTPBasicAuth(user, pwd), headers=headers)
    elif method == "put":
        ret = requests.put(url, data=data, auth=HTTPBasicAuth(user, pwd), headers=headers)
    elif method == "post":
        ret = requests.post(url, data=data, auth=HTTPBasicAuth(user, pwd), headers=headers)
    elif method == "delete":
        ret = requests.delete(url, auth=HTTPBasicAuth(user, pwd), headers=headers)
    else:
        sys.exit("请求方法错误")
    if ret.status_code not in [200, 202]:
        return False, ret.content
    return True, ret.json()


class RemoteClientCompass(object):
    def __init__(self, host: str, user: str, ssh_port: int = 22, pwd: str = None, ssh_key: str = None):
        self.host = host
        self.ssh_port = ssh_port
        self.user = user
        self.pwd = pwd
        self.ssh_key = ssh_key
        self.__transport = None

    @logger.catch
    def connect(self):
        if self.__transport is None:
            transport = paramiko.Transport((self.host, self.ssh_port))
            try:
                if self.ssh_key == "ssh-global":
                    private_key = paramiko.RSAKey.from_private_key_file('./tmp/private.pem')
                    transport.connect(username=self.user, pkey=private_key)
                elif self.pwd:
                    transport.connect(username=self.user, password=self.pwd)
                else:
                    logger.error(f'{self.host} has no auth')
                    raise
                logger.info(f"login to {self.host}")

            except paramiko.AuthenticationException as ssh_err:
                logger.error(f"connect to {self.host}, get some err: {ssh_err}")
                raise ssh_err
            self.__transport = transport

    @logger.catch
    def cmd(self, commands):
        self.connect()
        ssh = paramiko.SSHClient()
        ssh._transport = self.__transport
        stdin, stdout, stderr = ssh.exec_command(commands)
        status = stdout.channel.recv_exit_status()
        if status == 0:
            response = stdout.readlines()
            for line in response:
                logger.debug(f'INPUT: {commands} | OUTPUT: {line}')
            return response
        else:
            error_msg = stderr.read().decode()
            logger.error("command {} failed  | {}".format(commands, error_msg))
            return error_msg

    @logger.catch
    def sftp_put(self, src, des):
        sftp = paramiko.SFTPClient.from_transport(self.__transport)
        sftp.put(src, des)

    @logger.catch
    def close(self):
        self.__transport.close()
        logger.info(f"logout from {self.host}")




def merge_node(dump, cid):
    node_list = dump[cid]['context']['node']['result']
    node_metric_list = dump[cid]['context']['metric']['nodes']
    node_info = dump[cid]['node_info']
    for i in node_list:
        for m in node_metric_list:
            if i['Hostname'] == m.node:
                i['cpu_usage'] = m.cpu
                i['mem_usage'] = m.memory
        node_info[i['InternalIP']].update(i)
    return node_info


def merge_pod(dump, cid):
    pods = dump[cid]['context']['pod']['result']
    pod_metric_list = dump[cid]['context']['metric']['pods']
    for i in pods:
        for m in pod_metric_list:
            if i['name'] == m.pod and i['ns'] == m.ns:
                i['cpu'] = m.cpu
                i['cpu_requests'] = m.cpu_requests
                i['cpu_limits'] = m.cpu_limits
                i['memory'] = m.memory
                i['memory_requests'] = m.memory_requests
                i['memory_limits'] = m.memory_limits
    return pods

