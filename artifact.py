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

app = Flask(__name__)
api = Api(app)
event = Event()

def get_list_of_nodes(topology_file: str) -> List[str]:
    """Return a list containing all available nodes IPs"""

    topology_nodes = []

    with open('topologies/' + topology_file) as f:
        topology = json.load(f)

    nodes = topology["IoTtopology"]["nodes"]

    for node in nodes:
        topology_nodes.append(node['ip'])

    return topology_nodes


def monitor_node_failure(node):
    print(f'Start monitoring node {node}...')
    while not event.is_set():
        time.sleep(0.1) # sleep for 100 ms
        if not check_alive(node):
            print(f'Node with IP {node} has failed')
            event.set()
            return node


def find_topology(file_name):
    """
    Find the current topology
    :param file_name: the name of the deployment input file
    :return: the topology
    """
    with open('topologies/' + file_name) as f:
        topology = json.load(f)

    return topology["IoTtopology"]["nodes"]


def get_application(app_file):
    """
    :param app_file: the JSON file where the model of the app is described,
                     the application's resource requirements are given in MB!!!
    :return: the a JSON dict containing info regarding the application
    """
    with open("apps/" + app_file) as f:
        app_dict = json.load(f)

    return app_dict


def main():

    credentials = HTTPBasicAuth('user', 'requestaccess')
    print(f'Starting placement cycle...')
    topology = find_topology('topology_pi.json')
    app = get_application('webApplication.json')
    solution = start_placement(topology, credentials, app)

    print(f'The found solution is {solution}')

    nodes = get_list_of_nodes('topology_pi.json')
    print(f'List of nodes: {nodes}')

    print(f'Starting to find a first invocation path...')

    invocation_path = self_adapt(solution, topology, app, credentials)

    print(f'Done. The invocation path is: {invocation_path}')
    #
    # print(f'Starting the monitoring process...')
    #
    # try:
    #     pool = Pool(processes=len(nodes))
    #     print(f'Waiting for the event')
    #     results = pool.map(monitor_node_failure, nodes)
    #     print(f'A node {results} has failed, starting to self-adapt....')
    #
    # except KeyboardInterrupt:
    #     event.set()
    # finally:
    #     pool.close()
    #     pool.join()


if __name__ == '__main__':

    main()

