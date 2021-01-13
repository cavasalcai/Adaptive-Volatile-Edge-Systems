import requests
import json
from requests.auth import HTTPBasicAuth
from flask import Flask
from flask_restful import Resource, Api
from node_api import requires_auth
from placementCycle.placement import check_alive, start_placement
from invocationPathCycle.invocation import self_adapt
from typing import List
from multiprocessing import Process, Pool, Event
import time
import docker

app = Flask(__name__)
api = Api(app)
event = Event()


def monitor_node_failure(node):
    print(f'Start monitoring node {node}...')
    while not event.is_set():
        time.sleep(0.1) # sleep for 100 ms
        if not check_alive(node):
            print(f'Node with IP {node} has failed')
            event.set()
            return node


def find_microservice_destinations(app):
    """
    Find for each microservice the message destination(s)
    :param app: the application JSON dictionary
    :return: a dictionary where key = microservice_id and value = a list of dependent microservices
    """
    microservices_dest = dict()
    for m in app['IoTapplication']['microservices']:
        microservices_dest[m['id'].split('/')[1]] = [m_id['id'].split('/')[1] for m_id in m['dest']]
    return microservices_dest


def find_topology(file_name):
    """
    Find the current topology
    :param file_name: the name of the deployment input file
    :return: the topology and a dictionary having as key the node id and as value its IP
    """
    nodes_IPs = dict()
    with open('topologies/' + file_name) as f:
        topology = json.load(f)

    for node in topology["IoTtopology"]["nodes"]:
        nodes_IPs[node['id']] = node['ip']

    return topology["IoTtopology"]["nodes"], nodes_IPs


def get_application(app_file):
    """
    :param app_file: the JSON file where the model of the app is described,
                     the application's resource requirements are given in MB!!!
    :return: the application and a dictionary with key equal to microservice id and its ports
    """
    microservices_ports = dict()
    with open("apps/" + app_file) as f:
        app_dict = json.load(f)

    for m in app_dict['IoTapplication']['microservices']:
        microservices_ports[m['id']] = (m['container_port'], m['external_port'])

    return app_dict, microservices_ports


def update_topology_after_failure(failed_nodes, topology):
    """
    Remove from the topology the failed nodes
    :param failed_nodes: a list of failed nodes
    :param topology: a list of available nodes
    :return: the updated topology and the id of the failed node
    """
    node_id = -1
    for f_node in failed_nodes:
        if f_node is not None:
            for node in topology:
                if node['ip'] == f_node:
                    node_id = node['id']
                    topology.remove(node)

    return topology, node_id


def update_placement_solution(solution, failed_node_id):
    """
    Remove the failed node from the placement solution
    :param solution: the current placement solution
    :param failed_node_id: the id of the failed node
    :return: the updated solution
    """
    for nodes in solution.values():
        if failed_node_id in nodes:
            nodes.remove(failed_node_id)

    return solution


def start_all_containers(solution, microservices_ports, credentials, nodes_ip):
    """Start all containers on their host"""
    for microservice, nodes in solution.items():
        c_port, e_port = microservices_ports[microservice]
        for node in nodes:
            info = [microservice, c_port, e_port]
            resp = requests.post(nodes_ip[node] + '/start_docker_container', json=info, auth=credentials,
                                 timeout=1000)


def start_application_test(invocation_path, microservices_ports, nodes_ip, app):
    """Start the application considering the invocation path"""

    for m in app['IoTapplication']['microservices']:
        node = invocation_path[m['id']]
        _, port = microservices_ports[m['id']]
        ip = nodes_ip[node].split(':')[1].replace('//', '')
        if m['id'] == 'cosminava/m1':
            print(f'm1')
            numbers = requests.get('http://' + ip + ':' + port + '/get_numbers', timeout=20)
            nums = numbers.json()
            print(f'The numbers are: {nums}')
        elif m['id'] == 'cosminava/m2':
            print(f'm2')
            resp_m2 = requests.post('http://' + ip + ':' + port + '/nums', json=nums, timeout=20)
            m2 = requests.get('http://' + ip + ':' + port + '/compute_numbers_odd', timeout=20)
            print(f'm2 = {m2.json()}')
        elif m['id'] == 'cosminava/m3':
            resp_m3 = requests.post('http://' + ip + ':' + port + '/nums', json=nums, timeout=20)
            m3 = requests.get('http://' + ip + ':' + port + '/compute_numbers_even', timeout=20)
            print(f'm3 = {m3.json()}')
        elif m['id'] == 'cosminava/m4':
            print(f'Compute the final results of m4')
            resp_m4_e = requests.post('http://' + ip + ':' + port + '/set_even_comp', json=m3.json(), timeout=20)
            resp_m4_o = requests.post('http://' + ip + ':' + port + '/set_odd_comp', json=m2.json(), timeout=20)
            print(f'all results are set get the final computational results')
            m4_res = requests.get('http://' + ip + ':' + port + '/get_results', timeout=20)
            print(f'Finally, the results are {m4_res.json()}')


def start_application(invocation_path, microservices_ports, microservices_dest, nodes_ip, credentials, failed_node):
    """Start the application and get the results"""
    print(f'Send the required knowledge to nodes')
    for node_id, node_ip in nodes_ip.items():
        if failed_node != node_id:
            resp1 = requests.post(f'{node_ip}/microservices_dest', json=microservices_dest, auth=credentials, timeout=20)
            resp2 = requests.post(f'{node_ip}/microservices_ports', json=microservices_ports, auth=credentials, timeout=20)
            resp3 = requests.post(f'{node_ip}/invocation_path', json=invocation_path, auth=credentials, timeout=20)
            resp4 = requests.post(f'{node_ip}/nodes_ips', json=nodes_ip, auth=credentials, timeout=20)

    print(f'Starting the application....')
    node = invocation_path['cosminava/m1']
    port, _ = microservices_ports['cosminava/m1']
    ip = nodes_ip[node].split(':')[1].replace('//', '')
    numbers = requests.get('http://' + ip + ':' + port + '/start_app', timeout=2000)
    print(f'The numbers considered are: {numbers.json()}')
    print(f'Waiting for the results.....')
    time.sleep(30)
    node = invocation_path['cosminava/m4']
    ip = nodes_ip[node]
    print(f'Getting the results from {ip}/get_app_results')
    m4_res = requests.get(f'{ip}/get_app_results', auth=credentials, timeout=2000)
    print(f'The results are: {m4_res.json()}')
    return m4_res.json()


def main():

    credentials = HTTPBasicAuth('user', 'requestaccess')
    print(f'Starting placement cycle...')
    topology, nodes_to_ips = find_topology('topology_pi.json')
    app, microservice_ports = get_application('webApp.json')
    microservices_dest = find_microservice_destinations(app)
    solution = start_placement(topology, credentials, app)

    print(f'The found solution is {solution}')

    print(f'Starting all containers!')
    start_all_containers(solution, microservice_ports, credentials, nodes_to_ips)
    print(f'All containers are functional!')

    print(f'Starting to find a first invocation path...')

    invocation_path = self_adapt(solution, topology, app, credentials)

    print(f'Done. The invocation path is: {invocation_path}')

    print(f'Start the application according to the invocation path')

    result = start_application(invocation_path, microservice_ports, microservices_dest, nodes_to_ips, credentials, "")
    # start_application_test(invocation_path, microservice_ports, nodes_to_ips, app)
    print(f'App has finished, the result is: {result}')
    # start_application(invocation_path, nodes_to_ips, microservice_ports, app)
    print(f'Starting the monitoring process...')

    nodes_ip = nodes_to_ips.values()
    print(f'List of nodes: {nodes_ip}')

    try:
        pool = Pool(processes=len(nodes_ip))
        print(f'Waiting for the event')
        failed_nodes = pool.map(monitor_node_failure, nodes_ip)
        print(f'A node {failed_nodes} has failed, starting to self-adapt....')

        topology, failed_node_id = update_topology_after_failure(failed_nodes, topology)
        solution = update_placement_solution(solution, failed_node_id)
        invocation_path = self_adapt(solution, topology, app, credentials)

        print(f'Done. The invocation path is: {invocation_path}')

        print(f'ReStart the application according to the new invocation path')
        result = start_application(invocation_path, microservice_ports, microservices_dest, nodes_to_ips, credentials,
                                   failed_node_id)
        print(f'App has finished, the result is: {result}')
        print(f'Starting the monitoring process...')
    except KeyboardInterrupt:
        event.set()
    finally:
        pool.close()
        pool.join()


if __name__ == '__main__':

    main()


