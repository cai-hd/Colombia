#!/bin/bash
:<<EOF
@author:fjg
@license: Apache Licence
@file: check_k8s.sh
@time: 2020/12/24
@contact: fujiangong.fujg@bytedance.com
@site:
@software: PyCharm

EOF

podRestartCheckNum=20
clusterRequestCheckPercent=80
nodeLabel="sfke.role.kubernetes.io/group=general-worker"
#nodeLabel="kubernetes.io/os=linux"
busyboxImage="cloudpricicd.sf-express.com/docker-k8sprivate-local/busybox:latest"
#busyboxImage="busybox:1.28.0"
healthCheckDir="/tmp/healthCheck"
externalDomain=("www.sf-express.com")
internalDomain=("kubernetes.default" "kube-dns.kube-system.svc.cluster.local" "www.sf-express.com")
podStatusCheck=("Running" "Completed" "CrashLoopBackOff" "ImagePullBackOff" "ContainerCreating" "Terminating" "ERROR")
machineId=$(cat /etc/machine-id)
tmpPodName="check-pod-$machineId-$(date +%F)"
export KUBECONFIG="/etc/kubernetes/admin.conf"
export PATH="/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin:/root/bin"

if [ ! -d "$healthCheckDir" ]; then
 mkdir -p "$healthCheckDir"
fi

check_check_pod(){
  if ! kubectl get pods "$tmpPodName" --no-headers >& /dev/null;then
    kubectl run "$tmpPodName" --image="$busyboxImage" --restart='Never' -- sleep 1h >& /dev/null
    sleep 10s
  fi
  local podNum=$(kubectl get pods "$tmpPodName"|grep -c Running)
  local checkTime=10
  local checked=0
  while [[ "$podNum" -ne 1 ]]&&[[ "$checked" -lt $checkTime ]] ;do
    local podNum=$(kubectl get pods "$tmpPodName"|grep -c Running)
    sleep 2s
    checked=$((checked+1))
  done
  if [[ "$podNum" -ne 1 ]]&&[[ "$checked" -eq "$checkTime" ]];then
    echo '{"alert_status":"error","check_point":"check_pod_status","check_data":""}'
    kubectl delete pods "$tmpPodName" --force >& /dev/null
    exit 1
  else
    echo '{"alert_status":"info","check_point":"check_pod_status","check_data":""}'
  fi
}

get_check_data() {
  allNodeFile="$healthCheckDir/allNodeList.txt"
  kubectl get nodes --no-headers -owide >& "$allNodeFile"
  nodeIpFile="$healthCheckDir/nodeIpList.txt"
  awk '{print $6}' "$allNodeFile" > "$nodeIpFile"
  nodeCapacityFile="$healthCheckDir/nodeCapacity.txt"
  kubectl get nodes -o custom-columns=NAME:.metadata.name,CPU:.status.capacity.cpu,MEM:.status.capacity.memory,IP:.status.addresses[0].address --no-headers --selector "$nodeLabel"> "$nodeCapacityFile"
  allPodsFile="$healthCheckDir/allPodList.txt"
  kubectl get pods --all-namespaces --no-headers -owide >& "$allPodsFile"
  allPodIpFile="$healthCheckDir/allPodIpList.txt"
  awk '{print $7}' "$allPodsFile"|grep -iv none|sort|uniq > $allPodIpFile
  nsPodIpFile="$healthCheckDir/nsPodIpList.txt"
  grep kube-system $allPodsFile|awk '{print $7}'|grep -iv none|sort|uniq > "$nsPodIpFile"
  allServiceFile="$healthCheckDir/allServiceList.txt"
  kubectl get svc --all-namespaces --no-headers -owide >& "$allServiceFile"
  svcListFile="$healthCheckDir/nsSvcList.txt"
  kubectl get svc -oyaml -o=custom-columns=NAME:.metadata.name,CLUSTER-IP:.spec.clusterIP,PORT:.spec.ports[0].port --no-headers -n kube-system|grep -iv none > "$svcListFile"
  weavePodsFile="$healthCheckDir/weavePodsList.txt"
  kubectl get pods -n kube-system -l name=weave-net -o wide --no-headers > "$weavePodsFile"
}

check_coredns_replicas(){
  local availableReplicas readyReplicas replicas ready
  read -r availableReplicas ready <<< "$(kubectl -n kube-system get deployments.apps coredns --no-headers|awk '{print $4,$2}')"
  read -r readyReplicas replicas <<< "$(echo "$ready"|awk -F '/' '{print $1,$2}')"
  if [[ "$availableReplicas" -eq 0 ]]||[[ "$readyReplicas" -eq 0 ]];then
    echo '{"alert_status":"error","check_point":"coredns_replicas","check_data":{"availableReplicas":"'"${availableReplicas}"'","readyReplicas":"'"$readyReplicas"'","replicas":"'"$replicas"'"}}'
  elif [[ "$availableReplicas" -ne "$replicas" ]]&&[[ "$readyReplicas" -ne "$replicas" ]];then
    echo '{"alert_status":"warning","check_point":"coredns_replicas","check_data":{"availableReplicas":"'"$availableReplicas"'","readyReplicas":"'"$readyReplicas"'","replicas":"'"$replicas"'"}}'
  else
    echo '{"alert_status":"info","check_point":"coredns_replicas","check_data":{"availableReplicas":"'"$availableReplicas"'","readyReplicas":"'"$readyReplicas"'","replicas":"'"$replicas"'"}}'
  fi
}
# '{"alert_status":"","check_point":"","check_data":""}'
dns_check(){
  if ! host "$1" >/dev/null;then
    echo '{"alert_status":"error","check_point":"node_dns","check_data":"'"$1"'"}'
  else
    echo '{"alert_status":"info","check_point":"node_dns","check_data":"'"$1"'"}'
  fi
}

check_node_dns() {
  for domain in "${externalDomain[@]}";do
    dns_check "$domain"
  done
}

check_pod_dns(){
  for domain in "${internalDomain[@]}";do
    if kubectl exec "$tmpPodName" -- nslookup "$domain" >& /dev/null;then
      echo '{"alert_status":"info","check_point":"pod_dns","check_data":"'"$domain"'"}'
    else
      echo '{"alert_status":"error","check_point":"pod_dns","check_data":"'"$domain"'"}'
    fi
  done
  for domain in "${externalDomain[@]}";do
    if kubectl exec "$tmpPodName" -- nslookup "$domain" >& /dev/null;then
      echo '{"alert_status":"info","check_point":"pod_dns","check_data":"'"$domain"'"}'
    else
      echo '{"alert_status":"error","check_point":"pod_dns","check_data":"'"$domain"'"}'
    fi
  done
}

check_dns(){
  #check_node_dns
  check_check_pod
  check_pod_dns
}

check_node_status(){
  local availableNode=$(wc -l "$allNodeFile"|awk '{print $1}')
  local notReadyNodeNum=$(grep -cv Ready "$allNodeFile")
  local readyNodeNum=$(grep -c Ready "$allNodeFile")
  if [[ "$notReadyNodeNum" -ne 0 ]];then
    local notReadyNode=$(grep -v Ready "$allNodeFile")
    echo '{"alert_status":"error","check_point":"node_status","check_data":{"readyNodeNum":"'"$readyNodeNum"'","notReadyNodeNum":"'"$notReadyNodeNum"'","availableNode":"'"$availableNode"'"}}'
    echo "$notReadyNode"
  else
    echo '{"alert_status":"info","check_point":"node_status","check_data":{"readyNodeNum":"'"$readyNodeNum"'","notReadyNodeNum":"'"$notReadyNodeNum"'","availableNode":"'"$availableNode"'"}}'

  fi
}

check_pods_status(){
  for status in "${podStatusCheck[@]}";do
    local num=$(awk -v podStatus="$status" 'BEGIN{count=0}{if($1=="kube-system" && $4==podStatus)count++}END{print count}' "$allPodsFile")
    if [[ "$status" == "Running" ]]||[[ "$status" == "Completed" ]];then
      echo '{"alert_status":"info","check_point":"pod_status","check_data":{"status":"'"$status"'","num":"'"$num"'"}}'
    elif [[ "$num" -ne 0 ]];then
      echo '{"alert_status":"error","check_point":"pod_status","check_data":{"status":"'"$status"'","num":"'"$num"'"}}'
	    awk -v podStatus="$status" '{if($1=="kube-system" && $4==podStatus) print $0}' "$allPodsFile"
    fi
  done
  local restartPodNum=$(awk -v restartNum=$podRestartCheckNum 'BEGIN{count=0}{if($1=="kube-system" && $5>restartNum)count++}END{print count}' "$allPodsFile")
  if [[ "$restartPodNum" -ne 0 ]];then
    echo '{"alert_status":"error","check_point":"pod_status","check_data":{"status":"restart","num":"'"$restartPodNum"'"}}'
    awk -v restartNum=$podRestartCheckNum '{if($1=="kube-system" && $5>restartNum) print $0}' "$allPodsFile"
  fi
}
check_svc_ip(){
  local svcCidr=$(pgrep kube-api -a|awk 'NR==1{for(i=1;i<=NF;i++)if($i~/service-cluster-ip-range/)print $i}'|awk -F "=" '{print $2}')
  local netmaskNum=$(echo "$svcCidr"|awk -F '/' '{print $2}')
  local svcUsageNum=$(awk '{print $4}' "$allServiceFile"|grep -civ none)
  local svcIpMax=$((2**(32-netmaskNum)-2))
  local ipUsedPercent=$(awk 'BEGIN{printf "%.4f\n","'"${svcUsageNum}"'"/"'"${svcIpMax}"'"}')
  if [[ "$svcUsageNum" -gt $((svcIpMax * 8  / 10)) ]];then
    echo '{"alert_status":"warning","check_point":"svc_ip","check_data":{"used":"'"$svcUsageNum"'","max":"'$svcIpMax'","percent":"'"$ipUsedPercent"'"}}'
  else
    echo '{"alert_status":"info","check_point":"svc_ip","check_data":{"used":"'"$svcUsageNum"'","max":"'$svcIpMax'","percent":"'"$ipUsedPercent"'"}}'
  fi
}

check_pod_ip(){
  local podCidr=$(curl -s 127.0.0.1:6784/status|grep Range|awk '{print $2}')
  if [[ ${#podCidr} -lt 9 ]];then
    return
  fi
  local ipUsageNum=$(sort "$nodeIpFile" $nodeIpFile $allPodIpFile|uniq -u|wc -l)
  local netmaskNum=$(echo "$podCidr"|awk -F '/' '{print $2}')
  local podIpMax=$((2**(32-netmaskNum)-2))
  local ipUsedPercent=$(awk 'BEGIN{printf "%.4f\n","'"${ipUsageNum}"'"/"'"${podIpMax}"'"}')
  if [[ "$ipUsageNum" -gt $((podIpMax * 8  / 10)) ]];then
    echo '{"alert_status":"warning","check_point":"pod_ip","check_data":{"used":"'"$ipUsageNum"'","max":"'$podIpMax'","percent":"'"$ipUsedPercent"'"}}'
  else
    echo '{"alert_status":"info","check_point":"pod_ip","check_data":{"used":"'"$ipUsageNum"'","max":"'$podIpMax'","percent":"'"$ipUsedPercent"'"}}'
  fi
}
unit_conversion_cpu(){
  local unit=$(echo "$1"|tr -d '0-9')
  local num=$(echo "$1"|tr -cd '0-9')
  if [[ $num -eq 0 ]];then
    echo 0
  else
    case $unit in
    m)
      echo "$num"
      ;;
    *)
      echo $((num*1000))
      ;;
    esac
  fi
}

unit_conversion_mem() {
  local unit=$(echo "$1"|tr -d '0-9')
  local num=$(echo "$1"|tr -cd '0-9')
  if [[ $num -eq 0 ]];then
    echo 0
  else
    case $unit in
    Ki)
      echo $((num/1024))
      ;;
    Mi)
      echo "$num"
      ;;
    Gi)
      echo $((num*1024))
      ;;
    esac
  fi
}

get_cluster_resources() {
  clusterCapacityCpu=0
  clusterCapacityMem=0
  clusterRequestsCpu=0
  clusterRequestsMem=0
  local clusterLimitsCpu=0
  local clusterLimitsMem=0
  while IFS= read -r line;do
    local nodeCapacityCpu nodeCapacityMem nodeName nodeRequestsCpu nodeRequestsMem nodeLimitsCpu nodeLimitsMem nodeRequestsCpuPercent nodeRequestsMemPercent nodeIp
    read -r nodeName nodeCapacityCpu nodeCapacityMem nodeIp<<< "$(echo "$line"|awk '{print $1,$2,$3,$4}')"
    nodeCapacityCpu=$(unit_conversion_cpu "$nodeCapacityCpu")
    nodeCapacityMem=$(unit_conversion_mem "$nodeCapacityMem")
    clusterCapacityCpu=$((clusterCapacityCpu+nodeCapacityCpu))
    clusterCapacityMem=$((clusterCapacityMem+nodeCapacityMem))
    local nodeDescribeFile="$healthCheckDir/$nodeName.describe"
    kubectl describe nodes "$nodeName" |sed -n '/Allocated resources/,/Events/p' > "$nodeDescribeFile"
    read -r nodeRequestsCpu nodeRequestsCpuPercent nodeLimitsCpu <<< "$(sed -n '/cpu/p' "$nodeDescribeFile"|awk '{print $2,$3,$4}')"
    local nodeRequestsCpuPercentNum=$(echo "$nodeRequestsCpuPercent"|sed 's/(//;s/%)//')
    if [[ "$nodeRequestsCpuPercentNum" -gt "$clusterRequestCheckPercent" ]];then
      echo '{"alert_status":"warning","check_point":"node_resources","check_data":{"ip":"'"$nodeIp"'","resources":"cpu","request":"'"$nodeRequestsCpu"'","max":"'"$nodeCapacityCpu"'m","percent":"'"$(echo "$nodeRequestsCpuPercent"|sed 's/(//;s/)//')"'"}}'
    else
      echo '{"alert_status":"info","check_point":"node_resources","check_data":{"ip":"'"$nodeIp"'","resources":"cpu","request":"'"$nodeRequestsCpu"'","max":"'"$nodeCapacityCpu"'m","percent":"'"$(echo "$nodeRequestsCpuPercent"|sed 's/(//;s/)//')"'"}}'

    fi
    nodeRequestsCpu=$(unit_conversion_cpu "$nodeRequestsCpu")
    nodeLimitsCpu=$(unit_conversion_cpu "$nodeLimitsCpu")
    clusterRequestsCpu=$((clusterRequestsCpu+nodeRequestsCpu))
    clusterLimitsCpu=$((clusterLimitsCpu+nodeLimitsCpu))
    read -r nodeRequestsMem nodeRequestsMemPercent nodeLimitsMem <<< "$(sed -n '/memory/p' "$nodeDescribeFile"|awk '{print $2,$3,$4}')"
    local nodeRequestsMemPercentNum=$(echo "$nodeRequestsMemPercent"|sed 's/(//;s/%)//')
    if [[ "$nodeRequestsMemPercentNum" -gt "$clusterRequestCheckPercent" ]];then
      echo '{"alert_status":"warning","check_point":"node_resources","check_data":{"ip":"'"$nodeIp"'","resources":"mem","request":"'"$nodeRequestsMem"'","max":"'"$nodeCapacityMem"'Mi","percent":"'"$(echo "$nodeRequestsMemPercent"|sed 's/(//;s/)//')"'"}}'
    else
      echo '{"alert_status":"info","check_point":"node_resources","check_data":{"ip":"'"$nodeIp"'","resources":"mem","request":"'"$nodeRequestsMem"'","max":"'"${nodeCapacityMem}"'Mi","percent":"'"$(echo "$nodeRequestsMemPercent"|sed 's/(//;s/)//')"'"}}'
    fi
    nodeRequestsMem=$(unit_conversion_mem "$nodeRequestsMem")
    nodeLimitsMem=$(unit_conversion_mem "$nodeLimitsMem")
    clusterRequestsMem=$((clusterRequestsMem+nodeRequestsMem))
    clusterLimitsMem=$((clusterLimitsMem+nodeLimitsMem))
  done < "$nodeCapacityFile"
}

check_resources_request() {
  local memUsedPercent=$(awk 'BEGIN{printf "%.4f\n","'"${clusterRequestsMem}"'"/"'"${clusterCapacityMem}"'"}')
  local cpuUsedPercent=$(awk 'BEGIN{printf "%.4f\n","'"${clusterRequestsCpu}"'"/"'"${clusterCapacityCpu}"'"}')
  if [[ "$clusterRequestsMem" -gt $((clusterCapacityMem * clusterRequestCheckPercent / 100)) ]];then
    echo '{"alert_status":"warning","check_point":"cluster_resources","check_data":{"resources":"mem","request":"'${clusterRequestsMem}'Mi","max":"'${clusterCapacityMem}'Mi","percent":"'"$(awk 'BEGIN{printf "%.0f\n","'"${memUsedPercent}"'"*100}')"'%"}}'
  else
    echo '{"alert_status":"info","check_point":"cluster_resources","check_data":{"resources":"mem","request":"'${clusterRequestsMem}'Mi","max":"'${clusterCapacityMem}'Mi","percent":"'"$(awk 'BEGIN{printf "%.0f\n","'"${memUsedPercent}"'"*100}')"'%"}}'

  fi
  if [[ "$clusterRequestsCpu" -gt $((clusterCapacityCpu * clusterRequestCheckPercent / 100)) ]];then
    echo '{"alert_status":"warning","check_point":"cluster_resources","check_data":{"resources":"cpu","request":"'${clusterRequestsCpu}'m","max":"'${clusterCapacityCpu}'m","percent":"'"$(awk 'BEGIN{printf "%.0f\n","'"${cpuUsedPercent}"'"*100}')"'%"}}'
  else
    echo '{"alert_status":"info","check_point":"cluster_resources","check_data":{"resources":"cpu","request":"'${clusterRequestsCpu}'m","max":"'${clusterCapacityCpu}'m","percent":"'"$(awk 'BEGIN{printf "%.0f\n","'"${cpuUsedPercent}"'"*100}')"'%"}}'
  fi
}

check_weave_status() {
  while IFS= read -r weave;do
    local weaveName weaveReady weaveStatus nodeIp nodeName
    read -r weaveName weaveReady weaveStatus nodeIp nodeName <<< "$(echo "$weave"|awk '{print $1,$2,$3,$6,$7}')"
    if [[ "$weaveReady" == "2/2" ]];then
      if [[ "$weaveStatus" == "Running" ]];then
        echo '{"alert_status":"info","check_point":"weave_status","check_data":{"ip":"'"$nodeIp"'","node":"'"$nodeName"'","podName":"'"$weaveName"'","ready":"'"$weaveReady"'","status":"'"$weaveStatus"'"}}'
      else
        echo '{"alert_status":"error","check_point":"weave_status","check_data":{"ip":"'"$nodeIp"'","node":"'"$nodeName"'","podName":"'"$weaveName"'","ready":"'"$weaveReady"'","status":"'"$weaveStatus"'"}}'

      fi
    else
      echo '{"alert_status":"error","check_point":"weave_status","check_data":{"ip":"'"$nodeIp"'","node":"'"$nodeName"'","podName":"'"$weaveName"'","ready":"'"$weaveReady"'","status":"'"$weaveStatus"'"}}'
    fi
  done < "$weavePodsFile"
}

# master and etcd 节点
get_check_data
check_coredns_replicas
check_node_status
check_pods_status
check_svc_ip
check_pod_ip
get_cluster_resources
check_resources_request
check_weave_status
check_dns
kubectl delete pods "$tmpPodName" --force >& /dev/null