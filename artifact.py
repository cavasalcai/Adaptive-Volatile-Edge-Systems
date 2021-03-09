import requests
import json
from requests.auth import HTTPBasicAuth
from flask import Flask
from flask_restful import Resource, Api
from node_api import requires_auth
from placementCycle.placement import check_alive, start_placement, millis
from invocationPathCycle.invocation import self_adapt
from typing import List
from multiprocessing import Process, Pool, Event, Manager
from functools import partial
import time
import docker
from monitoring import start_monitoring, monitoring_results
import argparse

app = Flask(__name__)
api = Api(app)


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
    :return: the updated topology and a dictionary of failed nodes IP and their associated ID
    """
    nodes_ids = {}
    for f_node in failed_nodes:
        if f_node is not None:
            for node in topology:
                if node['ip'] == f_node:
                    nodes_ids[f_node] = node['id']
                    topology.remove(node)

    return topology, nodes_ids


def update_placement_solution(solution, failed_nodes_ids):
    """
    Remove the failed node from the placement solution
    :param solution: the current placement solution

    :param failed_nodes_ids: a dictionary of failed nodes and their IDs
    :return: the updated solution
    """
    for id in failed_nodes_ids.values():
        for nodes in solution.values():
            if id in nodes:
                nodes.remove(id)
    return solution


def start_container(nodes_ip, info, credentials, node):

    resp = requests.post(nodes_ip[node] + '/start_docker_container', json=info, auth=credentials,
                         timeout=1000)
    return resp


def start_all_containers(solution, microservices_ports, credentials, nodes_ip):
    """Start all containers on their host"""
    for microservice, nodes in solution.items():
        c_port, e_port = microservices_ports[microservice]
        info = [microservice, c_port, e_port]
        pool = Pool(processes=len(nodes))
        func = partial(start_container, nodes_ip, info, credentials)
        results = pool.map(func, nodes)


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
    return m4_res.json()


def check_nodes():
    """
    Check if any of the monitored nodes has failed
    :return: a list of nodes that failed
    """
    failed_nodes = []
    for node, status in monitoring_results.items():
        if status == 'down':
            failed_nodes.append(node)
    return failed_nodes


def update_monitoring_list(failed_nodes):
    """
    Stop monitoring any node that has failed.
    :param failed_nodes: a list of failed nodes.
    """
    for node in failed_nodes:
        del monitoring_results[node]
    print(f'Updated monitoring nodes dict: {monitoring_results}')


def parse_args():
    """
    Create the options and parse the arguments given as input by the user.
    :return: an argparse object.
    """

    parser = argparse.ArgumentParser(description="Find afeasible deployment strategy such that all "
                                                 "application's requirements are satisfied.")
    parser.add_argument('-a', '--application_file', type=str, help='Give the name of the application model file.',
                        required=True)
    parser.add_argument('-e', '--edge_nodes', type=str, help='Give the name of the file containing the list of '
                                                             'edge nodes.',
                        required=True)
    args = parser.parse_args()

    return args


def main():

    args = parse_args()

    app_file = args.application_file
    edge_nodes_file = args.edge_nodes

    credentials = HTTPBasicAuth('user', 'requestaccess')
    print(f'Starting placement cycle...')
    topology, nodes_to_ips = find_topology(f'{edge_nodes_file}.json')
    app, microservice_ports = get_application(f'{app_file}.json')
    microservices_dest = find_microservice_destinations(app)

    print(f'Start node monitoring...')
    start_monitoring(nodes_to_ips)
    print(f'Start application placement...')
    solution = start_placement(topology, credentials, app)
    print(f'The found solution is {solution}')

    print(f'Start all containers!')
    start_time_start = int(round(time.time() * 1000))
    start_all_containers(solution, microservice_ports, credentials, nodes_to_ips)
    print(f'All containers are functional! required time = {int(round(time.time() * 1000)) - start_time_start}')
    print(f'Starting to find a first invocation path...')
    invocation_path = self_adapt(solution, topology, app, credentials)
    print(f'Done. The invocation path is: {invocation_path}')

    print(f'Start the application according to the invocation path')

    result = start_application(invocation_path, microservice_ports, microservices_dest, nodes_to_ips, credentials, "")
    print(f'App has finished, the result is: {result}')
    print(f'Starting the monitoring process...')

    while invocation_path:
        failed_nodes = check_nodes()
        if failed_nodes:
            print(f'Checking node status: {monitoring_results}')
            print(f'Some nodes failed: {failed_nodes}')
            topology, failed_node_ids = update_topology_after_failure(failed_nodes, topology)
            solution = update_placement_solution(solution, failed_node_ids)
            print(f'Solution after node failed: {solution}')
            print(f'Topology after node failure: {topology}')
            update_monitoring_list(failed_nodes)
            print(f'Checking node status: {monitoring_results}')
            print(f'Start finding a new invocation path!')
            invocation_path = self_adapt(solution, topology, app, credentials)
            print(f'the application has recovered with the invocation path: {invocation_path}')
            print(f'Continue to monitor the system')
    else:
        print(f'The application functionality cannot be restored using the available resourses,\
         more available edge nodes are required!!!')


if __name__ == '__main__':

    main()





