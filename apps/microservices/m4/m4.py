from flask import Flask, request, jsonify
from flask_restful import Api
import time
import requests

app = Flask(__name__)
api = Api(app)
LOCALHOST = '127.0.0.1'
HOST_PORT = '5000'
ID = 'm4'
STOP = 'last'


@app.route(f'/{ID}', methods=['POST'])
def set_odd_comp():
    odd_comp = request.get_json()
    results = odd_comp**2
    resp = requests.post(f'http://{LOCALHOST}:{HOST_PORT}/listening_containers', json=[STOP, results], timeout=20)
    return 'ok'


@app.route('/get_results', methods=['GET'])
def get_results():
    res = odd_comp**2
    # time.sleep(20)
    return jsonify(res)


if __name__ == '__main__':

    app.run(host=LOCALHOST, port=5040)

