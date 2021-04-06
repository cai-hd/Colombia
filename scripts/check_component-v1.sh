#!/bin/bash
:<<EOF
@author:fjg
@license: Apache Licence
@file: check_k8s-sf-all-master.sh.sh
@time: 2021/01/25
@contact: fujiangong.fujg@bytedance.com
@site:
@software: PyCharm
EOF

certCheckDay=14
healthCheckDir="/tmp/healthCheck"
k8sConfDir="/etc/kubernetes"
etcdConfigFile="/etc/etcd/cfg/etcd.conf"
export KUBECONFIG="/etc/kubernetes/admin.conf"
export PATH="/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin:/root/bin"

if [ ! -d "$healthCheckDir" ]; then
 mkdir -p "$healthCheckDir"
fi

check_kube_apiserver() {
  if ! ss -ntlp|grep kube-api > /dev/null; then
    echo '{"alert_status":"error","check_point":"apiserver_process","check_data":"no exist"}'
  else
    echo '{"alert_status":"info","check_point":"apiserver_process","check_data":"exist"}'
    local healthUrl="https://localhost:6443/healthz"
    local serverStatus=$(curl -sk "$healthUrl")
    if [[ "$serverStatus" == "ok" ]];then
      echo '{"alert_status":"info","check_point":"apiserver_health","check_data":"'"$serverStatus"'"}'
    else
      echo '{"alert_status":"error","check_point":"apiserver_health","check_data":"'"$serverStatus"'"}'
    fi
  fi
}

check_kube_scheduler() {
  if ! ss -ntlp|grep kube-schedule > /dev/null; then
    echo '{"alert_status":"error","check_point":"scheduler_process","check_data":"no exist"}'
  else
    echo '{"alert_status":"info","check_point":"scheduler_process","check_data":"exist"}'
    local healthUrl="https://localhost:10259/healthz"
    local serverStatus=$(curl -sk "$healthUrl")
    if [[ "$serverStatus" == "ok" ]];then
     echo '{"alert_status":"info","check_point":"scheduler_health","check_data":"'"$serverStatus"'"}'
    else
      echo '{"alert_status":"error","check_point":"scheduler_health","check_data":"'"$serverStatus"'"}'
    fi
  fi
}

check_kube_controller_manager() {
  if ! ss -ntlp|grep kube-controll > /dev/null; then
    echo '{"alert_status":"error","check_point":"controller_process","check_data":"no exist"}'
  else
    echo '{"alert_status":"info","check_point":"controller_process","check_data":"exist"}'
    local healthUrl="https://localhost:10257/healthz"
    local serverStatus=$(curl -sk "$healthUrl")
    if [[ "$serverStatus" == "ok" ]];then
      echo '{"alert_status":"info","check_point":"controller_health","check_data":"'"$serverStatus"'"}'
    else
      echo '{"alert_status":"error","check_point":"controller_health","check_data":"'"$serverStatus"'"}'
    fi
  fi
}

check_etcd() {
  if ! ss -ntlp|grep etcd > /dev/null; then
    echo '{"alert_status":"error","check_point":"etcd_process","check_data":"no exist"}'
  else
    echo '{"alert_status":"info","check_point":"etcd_process","check_data":"exist"}'
    local serverStatus=$(systemctl is-active etcd)
    if [[ "$serverStatus" == "active" ]];then
      echo '{"alert_status":"info","check_point":"etcd_health","check_data":"'"$serverStatus"'"}'
    else
      echo '{"alert_status":"error","check_point":"etcd_health","check_data":"'"$serverStatus"'"}'
    fi
    source $etcdConfigFile
    local endpoints=$(ETCDCTL_API=3 $(which etcdctl) --cacert="$ETCD_CA_FILE" --cert="$ETCD_CERT_FILE" --key="$ETCD_KEY_FILE" --endpoints=https://127.0.0.1:2379 member list|awk '{print $NF}'|tr '\n' ',')
    local endpointHealthFile="$healthCheckDir/etcd-endpoint-health.log"
    ETCDCTL_API=3 $(which etcdctl) --cacert="$ETCD_CA_FILE" --cert="$ETCD_CERT_FILE" --key="$ETCD_KEY_FILE" --endpoints="${endpoints%,}" endpoint health > "$endpointHealthFile"
    while IFS= read -r endpoint;do
      local endpointStatus=$(echo "$endpoint"|awk '{print $3}')
      local endpointUrl=$(echo "$endpoint"|awk '{print $1}')
      if [[ "$endpointStatus" == "healthy:" ]];then
        echo '{"alert_status":"info","check_point":"etcd_endpoint","check_data":{"url":"'"$endpointUrl"'","status":"'"${endpointStatus%:}"'"}}'
      else
        echo '{"alert_status":"error","check_point":"etcd_endpoint","check_data":{"url":"'"$endpointUrl"'","status":"'"${endpointStatus%:}"'"}}'
      fi
    done < "$endpointHealthFile"
  fi
}

check_cert_time(){
    local cert=$1
    local notAfter=$(openssl x509 -in "$cert" -noout -dates|grep notAfter|awk -F = '{print $2}')
    local remainingTime=$(($(date +%s -d "$notAfter")-$(date +%s)))
    local warningTime=$((60*60*24*certCheckDay))
    if [[ "$remainingTime" -lt "$warningTime" ]];then
      echo '{"alert_status":"warning","check_point":"cert_time","check_data":{"cert":"'"$cert"'","endTime":"'"$notAfter"'","remainingTime":"'"$((remainingTime/60/60/24))"'"}}'
    else
      echo '{"alert_status":"info","check_point":"cert_time","check_data":{"cert":"'"$cert"'","endTime":"'"$notAfter"'","remainingTime":"'"$((remainingTime/60/60/24))"'"}}'
    fi
}

check_conf_cert(){
  local configFile=$1
  if [[ "$configFile" == "kubelet.conf" ]];then
    local configAuthCert=$(grep client-certificate /etc/kubernetes/kubelet.conf|awk -F ": " '{print $2}')
    if [[ ! -f "$configAuthCert" ]];then
      grep client-cert "$configFile" |cut -d" " -f 6|base64 -d > "$healthCheckDir"/"$configFile".crt
      local configAuthCert="$healthCheckDir/$configFile.crt"
    fi
  else
    grep client-cert "$configFile" |cut -d" " -f 6|base64 -d > "$healthCheckDir"/"$configFile".crt
    local configAuthCert="$healthCheckDir/$configFile.crt"
  fi
  check_cert_time "$configAuthCert"
  echo " " > "$healthCheckDir"/"$configFile".crt
}

check_cert() {
  for cert in "$k8sConfDir"/pki/*.crt;do
    check_cert_time "$cert"
  done
  source "${etcdConfigFile}"
  check_cert_time "$ETCD_CA_FILE"
  check_cert_time "$ETCD_CERT_FILE"
  check_cert_time "$ETCD_PEER_CA_FILE"
  check_cert_time "$ETCD_PEER_CERT_FILE"
  cd "$k8sConfDir" || exit
  for conf in *.conf;do
    check_conf_cert "$conf"
  done
}



check_kube_apiserver
check_kube_controller_manager
check_kube_scheduler
check_etcd
check_cert
