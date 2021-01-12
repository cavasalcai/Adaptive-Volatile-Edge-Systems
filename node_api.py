from flask_restful import Api
import os
from flask import Flask, request, jsonify, Response
import socket
import sys
import psutil
import typing
import subprocess
from functools import wraps
import docker
import requests


app = Flask(__name__)
api = Api(app)
nodes = []


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # does not have to be reachable
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def check_auth(username: str, password: str) -> bool:
    """Check if username and password combination is valid"""
    return username == 'user' and password == 'requestaccess'


def authenticate():
    """Send a 401 response that enables basic auth"""
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


def find_latency(node: str):
    """
    Get the average latency of a node
    :param node: the ip address of a node
    :return: the average latency to communicate with the node, considering 3 pings
    """
    results = subprocess.run(['ping', '-c', '3', node], stdout=subprocess.PIPE).stdout.decode('utf-8')

    return results.split('\n')[-2].split(' = ')[1].split('/')[1]


@app.route('/start_docker_container', methods=['POST'])
@requires_auth
def start_docker_container():
    # receive the information as a list [node_ip, image]
    global node_ip
    image, exposed_port, external_port = request.get_json()
    print(f'I received the following: microservice = {image}, e_port = {external_port}, exp_port{exposed_port}')
    client = docker.from_env()
    container_id = client.containers.run(image, ports={exposed_port:external_port}, detach=True)
    print(f'The container {container_id} is running!!!!')
    return 'ok'


# @app.route('/get_numbers', methods=['GET'])
# @requires_auth
# def get_numbers():
#     resp = requests.get(node_ip + '/get_numbers', timeout=20)
#     print(f'running on node: {node_ip} are: {resp.json()}')
#     return jsonify(resp.json())


@app.route('/get_resources', methods=['GET'])
@requires_auth
def get_resources():
    print(f'Getting nodes available resources...')

    res = {'RAM': psutil.virtual_memory().available,
           'HDD': psutil.disk_usage('/').free,
           'CPU': psutil.cpu_percent(interval=1, percpu=True),
           'CPU_cores': psutil.cpu_count(),
           'CPU_logical_cores': psutil.cpu_count(logical=False),
           'IP': get_ip()}

    print(f'Done.')
    print(f'Sending nodes available resources and latency...')
    return jsonify(res)


@app.route('/nodes', methods=['POST'])
@requires_auth
def nodes_recv():
    """Receive all nodes that are part of the network and find the latency"""
    global nodes

    nodes = request.get_json()
    print(f'the received nodes are: {nodes}')
    return 'ok'


@app.route('/get_latency', methods=['GET'])
@requires_auth
def get_latency():

    latency_dict = {}
    print(f'Start finding the communication latency to all nodes in the network...')
    print(f'the nodes are: {nodes}')

    for node in nodes:
        print(f'Getting the latency of node: {node["id"]} with id = {node["ip"]}')
        _, ip, port = node['ip'].split(':')
        ip = ip.replace('//', '')
        latency_dict[node['id']] = find_latency(ip)

    return jsonify(latency_dict)


if __name__ == '__main__':

    try:
        port = int(sys.argv[1])
    except IndexError:
        port = 5000
    print(f'I am fognode {socket.gethostname()}, with address {get_ip()}')

    app.run(host=get_ip(), port=port)