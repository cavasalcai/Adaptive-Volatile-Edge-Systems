from flask import Flask, request, jsonify
from flask_restful import Api
import random
import time
import requests

app = Flask(__name__)
api = Api(app)
LOCALHOST = '127.0.0.1'
HOST_PORT = '5000'
ID = 'm1'


@app.route('/start_app', methods=['GET'])
def get_numbers():
    numbers = range(1, 500)
    nums = random.choices(numbers, k=15)
    # time.sleep(20)
    resp = requests.post(f'http://{LOCALHOST}:{HOST_PORT}/listening_containers', json=[ID, nums], timeout=20)
    return jsonify(nums)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010)