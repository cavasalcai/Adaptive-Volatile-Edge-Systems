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
microservices_dest = {}
microservices_ports = {}
invocation_path = {}
nodes_ips = {}
app_results = 0
LOCALHOST = '127.0.0.1'


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
    """Start all local docker containers"""
    image, exposed_port, external_port = request.get_json()
    print(f'I received the following: microservice = {image}, e_port = {external_port}, exp_port{exposed_port}')
    client = docker.from_env()
    container_id = client.containers.run(image, network_mode='host', detach=True)
    print(f'The container {container_id} is running!!!!')
    return 'ok'


@app.route('/get_resources', methods=['GET'])
@requires_auth
def get_resources():
    """Get the node's available resources"""
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
    """Receive all nodes that are part of the network"""
    global nodes

    nodes = request.get_json()
    print(f'the received nodes are: {nodes}')
    return 'ok'


@app.route('/microservices_dest', methods=['POST'])
@requires_auth
def microservices_recv():
    """Receive all app's microservices"""
    global microservices_dest

    microservices_dest = request.get_json()
    print(f'the received microservices are: {microservices_dest}')
    return 'ok'


@app.route('/nodes_ips', methods=['POST'])
@requires_auth
def ips_recv():
    """Receive a dictionary with nodes IDs and IPs"""
    global nodes_ips

    nodes_ips = request.get_json()
    print(f'the received nodes IPs are: {nodes_ips}')
    return 'ok'


@app.route('/microservices_ports', methods=['POST'])
@requires_auth
def ports_recv():
    """Receive the current application's invocation path"""
    global microservices_ports

    microservices_ports = request.get_json()
    print(f'the received ports is: {microservices_ports}')
    return 'ok'


@app.route('/invocation_path', methods=['POST'])
@requires_auth
def invocation_recv():
    """Receive the current application's invocation path"""
    global invocation_path

    invocation_path = request.get_json()
    print(f'the received invocation_path is: {invocation_path}')
    return 'ok'


@app.route('/get_latency', methods=['GET'])
@requires_auth
def get_latency():
    """Compute the latency for every node in the network"""
    latency_dict = {}
    print(f'Start finding the communication latency to all nodes in the network...')
    print(f'the nodes are: {nodes}')

    for node in nodes:
        print(f'Getting the latency of node: {node["id"]} with id = {node["ip"]}')
        _, ip, port = node['ip'].split(':')
        ip = ip.replace('//', '')
        latency_dict[node['id']] = find_latency(ip)

    return jsonify(latency_dict)


@app.route('/listening_containers', methods=['POST'])
def listening():
    global app_results
    """Receive the output of local containers and forward it to destination nodes"""
    print(f'I am in the listening_containers !!!!!')
    container_id, recv_msg = request.get_json()
    print(f'Received the message {recv_msg} from {container_id}')
    if container_id != 'last':
        dest_microservice = microservices_dest[container_id][0]
        print(f'Sending message to dependent microservice: {dest_microservice}')
        image_microservice = f'cosminava/{dest_microservice}'
        node = invocation_path[image_microservice]
        print(f'Sending message to target node ip: {nodes_ips[node]}/forward_msgs')
        resp = requests.post(f'{nodes_ips[node]}/forward_msgs', json=(dest_microservice, recv_msg), timeout=20)
    else:
        print(f'The app has finished!!')
        app_results = recv_msg
        print(f'Finally got the results: {app_results}')
    return 'ok'


@app.route('/forward_msgs', methods=['POST'])
def forward_msg():
    global app_results
    """Forward the message to the local container"""
    print(f'I am in the forward_msgs !!!!!')
    container_id, recv_msg = request.get_json()
    print(f'Sending the message {recv_msg} to {container_id}')
    print(f'Send the message to local container')
    port, _ = microservices_ports[f'cosminava/{container_id}']
    print(f'the path is http://{LOCALHOST}:{port}/{container_id}')
    resp = requests.post(f'http://{LOCALHOST}:{port}/{container_id}', json=recv_msg, timeout=2000)

    return 'ok'


@app.route('/get_app_results', methods=['GET'])
@requires_auth
def get_results():
    return jsonify(app_results)


if __name__ == '__main__':

    try:
        port = int(sys.argv[1])
    except IndexError:
        port = 5000
    print(f'I am fognode {socket.gethostname()}, with address {get_ip()}')

    app.run(host='0.0.0.0', port=port)