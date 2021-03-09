import time
from placementCycle.placement import check_alive
from threading import Thread, Event
from requests.auth import HTTPBasicAuth
import requests
import json


monitoring_results = {}


def monitor_node_failure(node):
    global results_dict
    event = Event()
    print(f'Start monitoring node {node}...')
    credentials_central = HTTPBasicAuth('admin', 'requestaccess')
    while not event.is_set():
        flag = 'up'
        time.sleep(1) # sleep for 100 ms
        if not check_alive(node):
            # print(f'Node with IP {node} has failed')
            flag = 'down'
            event.set()
        monitoring_results[node] = flag
        # print(f'{results_dict} from within the thread of node = {node}')

        # resp = requests.post(f'http://{LOCALHOST}:5000/save_status', json=(node, flag), auth=credentials_central, timeout=20)


def start_monitoring(nodes_to_ips):
    threads = []
    # try:
    print(f'Starting the processes')
    for node in nodes_to_ips.values():
        p = Thread(target=monitor_node_failure, args=(node,))
        p.start()
        threads.append(p)
    print(f'Starting the monitoring process...')
    # except KeyboardInterrupt:
    #     event.set()
    #     for t in threads:
    #         t.join()


if __name__ == '__main__':

    start_monitoring()
