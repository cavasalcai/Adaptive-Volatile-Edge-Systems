import requests
import json
from requests.auth import HTTPBasicAuth
from flask import Flask
from flask_restful import Resource, Api
from node_api import requires_auth
from placementCycle.placement import check_alive, start_placement
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


def main():

    credentials = HTTPBasicAuth('user', 'requestaccess')
    print(f'Starting placement cycle...')
    start_placement('topology.json', 'webApplication.json')

    nodes = get_list_of_nodes('topology.json')
    print(f'List of nodes: {nodes}')

    print(f'Starting the monitoring process...')

    try:
        pool = Pool(processes=len(nodes))
        results = pool.map(monitor_node_failure, nodes)
        print(f'Waiting for the event')
        print(f'A node {results} has failed, starting to self-adapt....')
    except KeyboardInterrupt:
        event.clear()
    finally:
        pool.close()
        pool.join()





if __name__ == '__main__':

    main()

    # print(get_latency('192.168.0.129'))
