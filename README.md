# Adaptive-Volatile-Edge-Systems

First, we use Ansible to provide our infrastructure as code. The coordinator node hosts the placement and invocation cycles, which construct the required formulae and through interaction with a solver build the corresponding plans. 
Monitoring functionality is responsible for detecting the status of nodes in the network, their available resources as well as obtaining the communication latencies between them. Execution entails deployment of containers on nodes and setting up communication between deployed microservices. Edge nodes host Docker and report their latencies to others to the coordinator. All interactions are performed through REST APIs. The prototype is built in Python 3.7 using Z3 as the underlying SMT solver and an example microservice-based application is available in the apps folder.

## Instructions

### Prepare the target edge system 

Use either the provided Ansible playbook to configure the available physical edge nodes like Raspberry Pis or start each node on a different port on the localhost. 
*  For the former, enter in the hosts file the IPs of each node and provide the user of each device. Then execute the playbook. Finally, go on each node and execute the *run_node_api.sh* on each individual node.
```bash
./run-node-api.sh
```
*  For the latter, be sure that the localhost has all the requirements specified in the *requirements_nodes.txt*. Finally, start the node_api on a different port using: 
```bash
 python node-api.py <port_name>
```

### Run the adaptive framework

To start the framework, execute the following command and provide the required input files, i.e., the application model file and the target edge system.

```bash
 python dispatcher.py -a app_model_file -e targe_edge_nodes_file
```

A command that will find an initial placement strategy for the application and provide an invocation path to make the application operational. Once the application is operational, the framework continues to monitor the status of each node, and if a node failure occurs then the framework adapts by finding a new invocation path between the remaining available nodes. The framework stops when there is not a valid invocation path in the current edge system.

To see this behavior, once the application is operational please fail one node. The full details of the adaptive framework are presented in our research technical paper.

