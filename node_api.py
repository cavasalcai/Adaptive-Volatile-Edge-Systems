from flask_restful import Api
import os
from flask import Flask, request, jsonify, Response
import socket
import sys
import psutil
import typing
from functools import wraps


app = Flask(__name__)
api = Api(app)


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


@app.route('/get_resources', methods=['GET'])
@requires_auth
def get_resources():
    print(f'Getting nodes available resources...')

    res = {}
    res['RAM'] = psutil.virtual_memory().available
    res['HDD'] = psutil.disk_usage('/').free
    res['CPU'] = psutil.cpu_percent(interval=1, percpu=True)
    res['CPU_cores'] = psutil.cpu_count()
    res['CPU_logical_cores'] = psutil.cpu_count(logical=False)
    # res['IP_local'] = psutil.net_connections().laddr
    # res['IP_remote'] = psutil.net_connections().raddr
    res['IP'] = get_ip()

    print(f'Done.')
    print(f'Sending nodes available resources...')
    return jsonify(res)





if __name__ == '__main__':

    try:
        port = int(sys.argv[1])
    except IndexError:
        port = 5000
    print(f'I am fognode {socket.gethostname()}, with address {get_ip()}')

    app.run(host='127.0.0.1', port=port)