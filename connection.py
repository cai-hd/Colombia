from os import system
from paramiko import SSHClient, AutoAddPolicy, RSAKey,Transport,SFTPClient
from paramiko.auth_handler import AuthenticationException, SSHException
from log import logger


class RemoteClient:
    """Client to interact with a remote host via SSH """

    def __init__(self, host, user="root", ssh_key_filepath="/root/.ssh/id_rsa",ssh_port=22 ):
        self.host = host
        self.user = user
        self.ssh_key_filepath = ssh_key_filepath
        self.ssh_port=ssh_port
        self.client = None
        self.conn = None
        self.t=Transport((self.host,self.ssh_port))
        self.sftp=SFTPClient.from_transport(self.t)
        self.keyfile=self.__get_ssh_key()
    @logger.catch
    def __get_ssh_key(self):
        """ Fetch locally stored SSH key."""
        try:
            self.ssh_key = RSAKey.from_private_key_file(self.ssh_key_filepath)
            logger.info(f'Found SSH key at self {self.ssh_key_filepath}')
        except SSHException as error:
            logger.error(error)
        return self.ssh_key

    @logger.catch
    def __upload_ssh_key(self):
        try:
            system(f'ssh-copy-id -i {self.ssh_key_filepath}  {self.user}@{self.host}>/dev/null 2>&1')
            logger.info(f'{self.ssh_key_filepath} uploaded to {self.host}')
        except FileNotFoundError as error:
            logger.error(error)

    @logger.catch
    def connect(self):
        """Open connection to remote host. """
        if self.conn is None:
            try:
                self.client = SSHClient()
                self.client.load_system_host_keys()
                self.client.set_missing_host_key_policy(AutoAddPolicy())
                self.client.connect(
                    self.host,
                    username=self.user,
                    key_filename=self.ssh_key_filepath,
                    look_for_keys=True,
                    timeout=5000
                )
            except AuthenticationException as error:
                logger.error(f'Authentication failed: did you remember to create an SSH key? {error}')
                raise error
        logger.info("login to {}".format(self.host))
        return self.client

    def disconnect(self):
        """Close SSH connection."""
        if self.client:
            self.client.close()

    @logger.catch
    def execute_commands(self, commands):
        """
        Execute multiple commands in succession.
        :param commands: List of unix commands as strings.
        :type commands: List[str]
        """
        self.conn = self.connect()
        stdin, stdout, stderr = self.client.exec_command(commands)
        status = stdout.channel.recv_exit_status()
        if status == 0:
            response = stdout.readlines()
            for line in response:
                logger.info(f'INPUT: {commands} | OUTPUT: {line}')
            return response
        else:
            error_msg = stderr.read().decode()
            logger.error("command {} failed  | {}".format(commands, error_msg))

    @logger.catch
    def sftp_put_file(self,local_path,dest_path):
        self.t.connect(username=self.user,pkey=self.keyfile)
        self.sftp.put(local_path,dest_path)




