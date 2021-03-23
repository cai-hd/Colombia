#!/bin/bash

if [ ! -d /tmp/healthCheck ]; then
  mkdir -p /tmp/healthCheck 
fi

logCheckDays=7
currentDay=$(date +%F)
sinceLogDay=$(date +%F -d "$logCheckDays days ago")
healthLogDir="/tmp/healthCheck";cd /tmp/healthCheck
#错误文件大小阈值，20480B=20K
maxLogSize=20480
Domain=("www.sf-express.com" "www.baidu.com")
k8sConfDir="/etc/kubernetes"
#软中断百分比阈值
maxcpuSI=80
#contrack使用百分比阈值
maxusedConntrackPercentage=80
#文件描述符百分比阈值
maxfilePercentage=80
#dockers进程描述符百分比阈值
maxdockerFDUsedPercentage=80
#磁盘使用率百分比阈值
maxDUpercentage=85
#网卡PPS阈值
maxNicPPS=300000
#网卡带宽阈值，以万兆卡计算
maxNicTraffic=1000000
#线程数使用率阈值
maxPidUsagePercentage=80
#僵尸进程个数阈值
maxZProcessNum=10
#磁盘IO队列长度阈值
maxIOAvgquSize=5
#磁盘读写wait值阈值，ms
maxIOAwait=100
#时间差阈值,单位秒(s)
maxTimeDiff=1
#定义iostat等检查时间，单位秒
maxCheckTime=5

#定义日志的最大字节数，20480B=20K
checkLogSize(){
  du -b $1 |awk -v size=$maxLogSize '{if($1>size){print "false"}else{print "true"}}'
}


common_dns_check(){
  if ! host "$1" >/dev/null;then
   echo '{"alert_status":"error","check_point":"check_node_dns","check_data":"'$1'"}'
  else
   echo '{"alert_status":"info","check_point":"check_node_dns","check_data":"'$1'"}'
  fi
}

check_node_dns() {
  for domain in "${Domain[@]}";do
    common_dns_check "$domain"
  done
}



	#检查系统负载
check_cpuload(){
cpuCount=$(lscpu |grep 'CPU(s):'|grep -v -i numa|awk '{print $NF}')
maxCpuLoad=$(($cpuCount*2))
loadAverage=$(uptime |awk -F ':' '{print  $NF}')
result=$(echo $loadAverage|awk  -F',| +' -v load=$maxCpuLoad '{if($1<load && $2<load && $3<load){print "OK"}else{print "highLoad"}}')
if [[ $result == "OK" ]]; then
  echo '{"alert_status":"info","check_point":"systemLoad","check_data":"'$loadAverage'"}'
else
  echo '{"alert_status":"error","check_point":"systemLoad","check_data":"'$loadAverage'"}'
fi
}


	#输出节点CPU request使用率
  
	#输出节点内存 request使用率
  
	#输出磁盘使用率
check_diskUsage(){
#duResult=$(df -ht xfs|grep -v Filesystem|awk '{gsub("%", "", $(NF-1));print $0}'|awk -v usage=$maxDUpercentage '$(NF-1)>usage {print $0}')
duResult=$(timeout 5s df -h|grep -v -E "token|secret|overlay2|containers|Filesystem")
if [[ ! -z $duResult ]];then
  echo '{"alert_status":"info","check_point":"diskUsage","check_data":"'$duResult'"}'
else
  echo '{"alert_status":"error","check_point":"diskUsage","check_data":"check_command_exec_failed"}' 
fi
}
	
	#输出磁盘IO情况
check_diskIO(){
DISKS=$(ls /dev/sd[a-z] /dev/vd[a-z]  2>/dev/null)
for d in $DISKS
  do
	export logFileName=$(echo "`echo $d|awk -F'/' '{print $NF}'`-`date +%F`")
    iostat -x -d $d 1 $maxCheckTime  1>/tmp/healthCheck/$logFileName.log
	cd /tmp/healthCheck
	grep -q rareq-sz  /tmp/healthCheck/$logFileName.log
	if [[ $? -eq 0 ]];then 
	  IOResult=$(cat $logFileName.log|grep -v -E '^$|Device|_x86_64_'|awk  -v avgqu=$maxIOAvgquSize -v iowait=$maxIOAwait '$12>avgqu||$10>iowait||$11>iowait {print}')
	else 
	  IOResult=$(cat $logFileName.log|grep -v -E '^$|Device|_x86_64_'|awk  -v avgqu=$maxIOAvgquSize -v iowait=$maxIOAwait '$9>avgqu||$10>iowait||$11>iowait||$12>iowait {print}')
	fi
	
	if [[ -z $IOResult ]];then
	   echo '{"alert_status":"info","check_point":"diskIO","check_data":{"disk":"'$d'"}} '
	else
	   echo '{"alert_status":"error","check_point":"diskIO","check_data":{"disk":"'$d'","ioresult":"'$IOResult'"}}' 
	fi
  done
}


	#输出网卡情况,网卡不是eth开头时修改正则匹配
check_nic(){
#NETDEV=$(ifconfig  -a |grep  -E  -o "^eth[0-9]*|^bond[0-9]*|^ens[0-9]*")
NETDEV=$(ip r|grep -v br_bond|grep -E -o "eth[0-9]*|bond[0-9]*"|sort -u)
sar -n DEV 1  $maxCheckTime 1>$healthLogDir/netStatus-$currentDay.log
for n in $NETDEV
  do
    cd /tmp/healthCheck
	nicResult=$(cat netStatus-$currentDay.log |grep $n|grep -v -E "veth*"|grep Average|awk -v nic=$n -v pps=$maxNicPPS -v traffic=$maxNicTraffic  '$(NF-7)==nic &&($(NF-6)>pps || $(NF-5)>pps ||$(NF-4)>traffic ||$(NF-3)>traffic) {print }')
	if [[ -z $nicResult ]];then
	  echo '{"alert_status":"info","check_point":"nicTraffic","check_data":{"nic":"'$n'"}} '
	else
	  echo '{"alert_status":"error","check_point":"nicTraffic","check_data":{"nic":"'$n'","nicresult":"'$nicResult'"}}' 
	fi 
  done
}

	# 输出docker状态检查
	
	## docker服务状态
check_docker(){
dockerdIsActived=$(systemctl  is-active docker)
if  [[ $dockerdIsActived == "active" ]]; then
    echo '{"alert_status":"info","check_point":"dockerProcess","check_data":""} '
  else 
    echo '{"alert_status":"error","check_point":"dockerProcess","check_data":""} '
fi
  


  
  ## docker 描述符
dockerPid=$(ps aux |grep /bin/dockerd|grep -v grep |awk '{print $2}')
if [[ ! -z $dockerPid ]] ;then
  dockerOpenfileLimit=$(cat /proc/$dockerPid/limits |grep files |awk '{print $(NF-1)}')
  usedFD=$(ls -lR  /proc/$dockerPid/fd |grep "^l"|wc -l)
  dockerFDUsedPercentage=$(awk 'BEGIN{printf "%.3f%%\n",('$usedFD'/'$dockerOpenfileLimit')*100}')
  if [[ $(echo "$(echo $dockerFDUsedPercentage|awk '{gsub("%","",$1)} {print }') > $maxdockerFDUsedPercentage"|bc) -eq 1 ]];then
	echo '{"alert_status":"error","check_point":"dockerFD","check_data":{"maxDockerFD":"'$dockerOpenfileLimit'","usedFD":"'$usedFD'","dockerFDUsedPercentage":"'$dockerFDUsedPercentage'"}} '
  else
    echo '{"alert_status":"info","check_point":"dockerFD","check_data":{"maxDockerFD":"'$dockerOpenfileLimit'","usedFD":"'$usedFD'","dockerFDUsedPercentage":"'$dockerFDUsedPercentage'"}} '
  fi 
fi 
  

  
  
  ## 检查7天内dockers日志是否有error信息
#journalctl -x  --since $sinceLogDay   -u docker  1>docker-$currentDay.log
#grep -E -i "err|ERR|error|Error" docker-$currentDay.log 1>docker-$currentDay-Error.log
#if [[ $(checkLogSize docker-$currentDay-Error.log) == "true" ]];then
#	if [[  -s  docker-$currentDay-Error.log ]]; then
#	  echo  -e "[ERROR]DOCKER__docker error logs is: $(cat docker-$currentDay-Error.log)\n\n"
#	else
#		echo  -e "[INFO]DOCKER__docker has no error logs\n\n"
#	fi
#else
#    echo -e "[ERROR]DOCKER__docker error logs is too large,log file in $healthLogDir/docker-$currentDay-Error.log"
#fi


}

check_containerd() {
  if ! pgrep -fl containerd|grep -Ev "shim|dockerd" > /dev/null ;then
    echo '{"alert_status":"error","check_point":"containerdProcess","check_data":""} '
  else
    echo '{"alert_status":"info","check_point":"containerdProcess","check_data":""} '
  fi
}

  # 输出kubelet检查结果
  ## kubelet进程状态
check_kubelet(){
kubeletIsActived=$(systemctl  is-active kubelet)
if  [[ $kubeletIsActived == "active" ]]; then
    echo '{"alert_status":"info","check_point":"kubeletProcess","check_data":""} '
else 
    echo '{"alert_status":"error","check_point":"kubeletProcess","check_data":""} '
fi
  
  ## kubelet健康端口检查
#kubeletCheckEndpoint=$(ss -tunlp|grep kubelet|grep 127.0.0.1|grep 102|awk '{print $5}')  
kubeletCheckResult=$(curl --connect-timeout 5 -sk  127.0.0.1:10248/healthz)
if [[ $kubeletCheckResult == "ok" ]] ;then
  echo '{"alert_status":"info","check_point":"kubeletPortCheck","check_data":""} '
else
  echo '{"alert_status":"error","check_point":"kubeletPortCheck","check_data":""} '
fi
  
  ## kubelet7天内日志
#journalctl -x   --since $sinceLogDay   -u kubelet 1>kubelet-$currentDay.log 
#grep -E  "E[0-9]+|err|ERR|error|Error" kubelet-$currentDay.log 1>kubelet-$currentDay-Error.log
#if [[ $(checkLogSize kubelet-$currentDay-Error.log) == "true" ]];then
#	if [[  -s  kubelet-$currentDay-Error.log ]]; then
#	  echo  -e "[ERROR]KUBELET_kubelet error logs is: $(cat kubelet-$currentDay-Error.log)\n\n"
#	else
#		echo  -e "[INFO]KUBELET_kubelet has no error logs\n\n"
#	fi
#else
#    echo -e "[ERROR]KUBELET_kubelet error logs is too large,log file in $healthLogDir/kubelet-$currentDay-Error.log"
#fi
}
  # 输出kube-proxy检查结果
check_kube_proxy(){
  ## kube-proxy 健康端口检查
kubeProxyCheckResult=$(curl --connect-timeout 5 -sk 127.0.0.1:10249/healthz)
if [[ $kubeProxyCheckResult == "ok" ]] ;then
   echo '{"alert_status":"info","check_point":"kubeProxyPortCheck","check_data":""} '
else
   echo '{"alert_status":"error","check_point":"kubeProxyPortCheck","check_data":""} '
fi 
  
  ## kube-proxy错误日志过滤 
#proxyContainerID=$(docker ps |grep kube-proxy|grep -v pause|awk '{print $1}')
#if [[ ! -z $proxyContainerID ]]; then
#	docker logs $proxyContainerID  -t --since $sinceLogDay  --details >& kube-proxy-$currentDay.log
#	grep -E  "E[0-9]+|err|ERR|error|Error" kube-proxy-$currentDay.log 1>kube-proxy-$currentDay-Error.log
#	if [[ $(checkLogSize kube-proxy-$currentDay-Error.log) == "true" ]];then
#	  if [[  -s  kube-proxy-$currentDay-Error.log ]]; then
#	    echo  -e "[ERROR]KUBE-PROXY_kube-proxy error logs is: $(cat kube-proxy-$currentDay-Error.log)\n\n"
#	  else
#		echo  -e "[INFO]KUBE-PROXY_kube-proxy has no error logs\n\n"
#	  fi
#   else
#     echo -e "[ERROR]KUBE-PROXY_kube-proxy error logs is too large,log file in $healthLogDir/kube-proxy-$currentDay-Error.log"
#   fi
#else
#    echo -e "[ERROR]KUBE-PROXY_no found kube-proxy containerd this node"
#fi
} 

 #检查最大文件打开数
check_openfiles(){
openfileUsed=$(cat /proc/sys/fs/file-nr|awk '{print $1}')
maxOpenfiles=$(cat /proc/sys/fs/file-nr|awk '{print $NF}')
filePercentage=$(awk 'BEGIN{printf "%.3f%%\n",('$openfileUsed'/'$maxOpenfiles')*100}')
if [[ $(echo "$(echo $filePercentage|awk '{gsub("%", "", $1)} {print }') > $maxfilePercentage"|bc) -eq 1 ]];then
 echo '{"alert_status":"error","check_point":"systemFD","check_data":{"maxOpenfiles":"'$maxOpenfiles'","openfileUsed":"'$openfileUsed'","filePercentage":"'$filePercentage'"}} '
else
  echo '{"alert_status":"info","check_point":"systemFD","check_data":{"maxOpenfiles":"'$maxOpenfiles'","openfileUsed":"'$openfileUsed'","filePercentage":"'$filePercentage'"}} '
fi 
}


  #conntrack使用率
check_nf_conntrack(){
conntrackMax=$(cat /proc/sys/net/nf_conntrack_max) 
usedConntrack=$(cat /proc/sys/net/netfilter/nf_conntrack_count)
usedConntrackPercentage=$(awk 'BEGIN{printf "%.3f%%\n",('$usedConntrack'/'$conntrackMax')*100}')
if [[ $(echo "$(echo $usedConntrackPercentage|awk '{gsub("%", "", $1)} {print }') > $maxusedConntrackPercentage"|bc) -eq 1 ]];then
  echo '{"alert_status":"error","check_point":"conntrack","check_data":{"conntrackMax":"'$conntrackMax'","usedConntrack":"'$usedConntrack'","usedConntrackPercentage":"'$usedConntrackPercentage'"}} '
else
  echo '{"alert_status":"info","check_point":"conntrack","check_data":{"conntrackMax":"'$conntrackMax'","usedConntrack":"'$usedConntrack'","usedConntrackPercentage":"'$usedConntrackPercentage'"}} '
fi 
}
  
check_pid(){
usedPidNUM=$(ls -ld  /proc/[0-9]* |wc -l)
pidMax=$(cat /proc/sys/kernel/pid_max)
pidUsedPercentage=$(awk 'BEGIN{printf "%.3f%%\n",('$usedPidNUM'/'$pidMax')*100}')
if [[ $(echo "$(echo $pidUsedPercentage|awk '{gsub("%", "", $1)} {print }') > $maxPidUsagePercentage"|bc) -eq 1 ]];then
  echo '{"alert_status":"error","check_point":"pidNUM","check_data":{"pidMax":"'$pidMax'","usedPidNUM":"'$usedPidNUM'","pidUsedPercentage":"'$pidUsedPercentage'"}} '
else
  echo '{"alert_status":"info","check_point":"pidNUM","check_data":{"pidMax":"'$pidMax'","usedPidNUM":"'$usedPidNUM'","pidUsedPercentage":"'$pidUsedPercentage'"}} '
fi 
}
 
 
  #Z进程检查
check_z_process(){
#ZNUM=$(top -n 1|grep Tasks|awk  -F',' '{print $NF}'|awk '{print $(NF-1)}' )
ZNUM=$(ps -A -ostat,ppid,pid,cmd | grep -e '^[Zz]'|wc -l)
if [[ $ZNUM == 0 ]];then
  echo '{"alert_status":"info","check_point":"ZProcess","check_data":""} '
else
  ZTasks=$(ps -ef | grep defunct | grep -v grep)
  echo '{"alert_status":"error","check_point":"ZProcess","check_data":{"Ztasck":"'$ZTasks'"}}' 
fi
}
  
  #时间差检查
check_ntp(){  
ntpIsSyncd=$(timedatectl  status|grep synchronized|awk -F':| +' '{print $NF}')
if [[ $ntpIsSyncd == "yes" ]]; then
	timeDiff=$(chronyc  sources|grep -E "^\^\*" |cut  -d[ -f 1|awk '{print $NF}')
	if [[ ! -z $timeDiff ]];then
	  timeNUM=$(echo $timeDiff|grep -E -o "[0-9]*")
	  timeUnit=$(echo $timeDiff|grep -E -o "[a-z]*")
	  if [[ $timeUnit == "ns" ]];then
		timeDiffNum=$(awk 'BEGIN{printf "%0.10f",'$timeNUM'/1000000000}')
	  elif [[ $timeUnit == "us" ]];then
		timeDiffNum=$(awk 'BEGIN{printf "%0.10f",'$timeNUM'/1000000}')
	  elif [[ $timeUnit == "ms" ]];then
		timeDiffNum=$(awk 'BEGIN{printf "%0.10f",'$timeNUM'/1000}')
	  else
		timeDiffNum=$timeNUM
	  fi  

	  if [[ $(echo ""$timeDiffNum" > "$maxTimeDiff""|bc) -eq 1  ]];then
		echo '{"alert_status":"error","check_point":"ntpTime","check_data":"NTP_IS_DIFF_'$timeDiff'"}'
	  else 
		echo '{"alert_status":"info","check_point":"ntpTime","check_data":"NTP_IS_SYNCED_OK"} '
	  fi
	else
	  ntpTimestatus=$(chronyc  sources)
	  echo '{"alert_status":"error","check_point":"ntpTime","check_data":"NTP_IS_SYNCING"}' 
	fi
else
    echo  '{"alert_status":"error","check_point":"ntpTime","check_data":"NTP_NOT_SYNCED"}'
fi
}


 #message日志检查
check_msg_logs(){
grep -E "Container kill faild |\
Container kill faild.count |\
Trying direct SIGKILL |\
Container kill faild because of 'container not found' or 'no such process' |\
OOM KILL |\
Abort command issued |\
NIC link is down |\
Path is down |\
OFFILE unexpectedly |\
Call Trace |\
Not respoding |\
Write error |\
IO failure |\
Filesystem read-only |\
Failing path |\
No liveness for |\
xfs_log_force:error |\
I/O error |\
EXT4-fs error |\
Uncorrected hardware memory error |\
Device offlined |\
Unrecoverable medium error during recovery on PD |\
tx_timeout |\
Container runtime is down PLEG is not healthy |\
_Call_Trace"  /var/log/messages 1>message-$currentDay-Error.log

if [[ $(checkLogSize message-$currentDay-Error.log) == "true" ]];then
  if [[  -s  message-$currentDay-Error.log ]]; then
	mlog=$(cat message-$currentDay-Error.log)
	echo '{"alert_status":"error","check_point":"messageLog","check_data":""} ' && echo -e "$mlog"
  else
	echo  '{"alert_status":"info","check_point":"messageLog","check_data":""} '
  fi
else
  echo '{"alert_status":"error","check_point":"messageLog","check_data":{"logIsLarge":"true","logPath":"'$healthLogDir/message-$currentDay-Error.log'"}} '
fi
}



check_node_dns
check_cpuload
check_diskUsage
check_diskIO
check_nic
check_docker
check_containerd
check_kubelet
check_kube_proxy
check_openfiles
check_nf_conntrack
check_pid
check_z_process
check_ntp
#check_msg_logs
exit 0