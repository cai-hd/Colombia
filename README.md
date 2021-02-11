# Colombia

Script to generate a HTML report of CPU/memory requests vs. usage (collected via Metrics API/Heapster) for one or more Kubernetes clusters.
Diagnosis platform component status, including pod, binary components


### What the script does

via in-cluster serviceAccount, or via custom Cluster Registry REST endpoint)

Shell component information is also used

### Features

- [x] Kubernetes core component
- [x] node
- [x] pod
- [x] job
- [x] metric(Node,Pod)
- [ ] readiness
# how to use 

1. edit config.ini, Add the details of the cluster, including the node IP and API server address, and also need a token that can access the cluster
   If there is no token, you can create it in the following way
   ```shell
   # Create a service account
   kubectl create sa op 
   # Grant the new service account to the Cluster Administrator
   kubectl create clusterrolebinding  report --clusterrole cluster-admin  --serviceaccount=default:op
   # Get the token used by the service account
   SECRET_NAME=$(kubectl get serviceaccount op -o jsonpath='{.secrets[0].name}')
   
   #decode token 
   TOKEN=$(kubectl get secret $SECRET_NAME -o jsonpath='{.data.token}' | base64 --decode)
   echo $TOKEN
   
   eyJhbGciOiJSUzI1Nim5ldGVzL3NlcnZpY2VhY2NvdW50Iiwia3ViZXJuZXRlcy5pby9zZXJ2aWNlYWNjb3VudC9uYW1lc3BhY2UiOiJkZWZhdWx0Iiwia3ViZXJuZXRlcy5pby9zZXJ2aWNlYWNjb3VudC9zZWNyZXQubmFtZSI6Im9wLXRva2VuLWc0NDg0Iiwia3ViZXJuZXRlcy5pby9zZXJ2aWNlYWNjb3VudC9zZXJ2aWNlLWFjY291bnQubmFtZSI6Im9wIiwia3ViZXJuZXRlcy5pby9zZXJ2aWNlYWNjb3VudC9zZXJ2aWNlLWFjY291bnQudWlkIjoiYzhlMDRhZTQtMjNjZS00YjA4LTg2ZmQtNzRjMmZhMWNlYTliIiwic3ViIjoic3lzdGVtOnNlcnZpY2VhY2NvdW50OmRlZmF1bHQ6b3AifQ.AKMqv7hRb-_ThQt_UkOud77OV6Wc8fIhe_Mg2niSh5KMSAGztEntz_B9avEz5RRW8sXWDHOqeR0KYzKJOktQLQ60yoItpqVzh5xe4eSW05Ym9fsYcjLltDwUAGYpdqFL3_1NG4UjPvWnY4G8XwJ1LWb-X1eSuvlYz5KTaaDf15-37bkMpAX20rma7phc8dK8ZhhqIauVO-UzfjQ4VSJGJOxKbZd3ZPYORyjpnN48oHtju-HBwBlBkuWJhmqJh7ABOwug3t__yCgNaUxiD8l0gv9QxjNa-SEa1Tj9z4ZXn_mQExAcJYhSbFrBRf4f5yw7ahCx8-wrUxIQDOGGG_19mA
   ```
   
2. Running as Docker container
    ```shell
    docker build -t colombia:0.1 .  
    docker run --rm -it -v $(pwd)/output:/app/output  -v $(pwd)/config.ini:/app/config.ini colombia:0.1
    ```
   The output will be HTML files plus multiple tab-separated files:

   output/core.html
   List Kubernetes core a component page, links to all other HTML pages.
   
   output/pod.html
   
   output/job.html
   
   output/node.html
   
   output/metric.html
   


