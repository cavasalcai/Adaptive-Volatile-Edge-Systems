from flask import Flask, request, jsonify
from flask_restful import Api
import requests
import time


app = Flask(__name__)
api = Api(app)
LOCALHOST = '127.0.0.1'
HOST_PORT = '5000'
ID = 'm2'


def compute_numbers_odd(nums):
    numbers = []
    for n in nums:
        if n % 2 != 0:
            numbers.append(n)
    return sum(numbers)


@app.route(f'/{ID}', methods=['POST'])
def recv_nums():

    nums = request.get_json()
    res = compute_numbers_odd(nums)
    # time.sleep(20)
    resp = requests.post(f'http://{LOCALHOST}:{HOST_PORT}/listening_containers', json=[ID, (res, nums)], timeout=20)

    return 'ok'


if __name__ == '__main__':
    app.run(host=LOCALHOST, port=5020)

