from pysmt.shortcuts import Symbol, And, Plus, Int, ExactlyOne, Equals, get_formula_size, GE, Or, Not, Real
from pysmt.shortcuts import Solver
from pysmt.typing import INT, REAL
import json
import random
import time
import socket
import requests
from requests.auth import HTTPBasicAuth
# from helpers_scripts.generate_input_files import *


def check_alive(node):
    """Check if node is alive"""
    proto, host, port = node.split(':')
    host = host.replace('//', '')
    port = int(port)
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex((host, port))
    return result == 0


def create_nodes_pos_mappings(app_file, topology_file):
    """
    Create the possible mapping of microservice on each edge node.
    :param app_file: the JSON file where the model of the app is described
    :param topology_file: the JSON file where the configuration of the topology is described
    :return: a dictionary where value represents a list of microservices and key is the edge node
    """
    with open("topologies/" + topology_file) as topo:
        topology = json.load(topo)

    with open("apps/" + app_file) as f:
        app_dict = json.load(f)

    node_maps = {}
    for node in topology["IoTtopology"]["nodes"]:
        node_maps[str(node['id'])] = [str(m['id']) for m in app_dict["IoTapplication"]["microservices"]]
    return node_maps


def get_topology(topology_file):
    """
    Get information regarding the topology, i.e., available resources and failure rates for each node.
    :param topology_file: the JSON file where the configuration of the topology is described
    :return: a dictionary where the key is a node and the value represents the resources and a list of failure rates
    for each node
    """
    credentials = HTTPBasicAuth('user', 'requestaccess')
    node_resources = dict()
    nodes_failures = []

    with open("topologies/" + topology_file) as topo:
        topology = json.load(topo)

    topology_nodes = topology["IoTtopology"]["nodes"]

    for node in topology_nodes:
        node_ip = node["ip"]
        if check_alive(node_ip):
            resp = requests.get(node_ip + '/get_resources', auth=credentials, timeout=20)
            node_res = resp.json()
            node_resources[str(node["id"])] = [int(node_res["RAM"]), int(node_res["HDD"])]
        nodes_failures.append((str(node["id"]), float(node['failure'])))

    return node_resources, nodes_failures


def mb_to_bytes(mb: int) -> int:
    """Convert a value given in MB to bytes"""
    return mb * 1024 * 1024


def get_application(app_file):
    """
    :param app_file: the JSON file where the model of the app is described,
                     the application's resource requirements are given in MB!!!
    :return: a dictionary where the key is a microservice and the value represents their resource requirements in bytes
    """
    app_resources = dict()
    microservices = []
    with open("apps/" + app_file) as f:
        app_dict = json.load(f)

    SLA = app_dict["IoTapplication"]["SLA"]
    avail = float(SLA["availability"])

    for micro in app_dict["IoTapplication"]["microservices"]:
        app_resources[str(micro["id"])] = [mb_to_bytes(int(micro["RAM"])), mb_to_bytes(int(micro["HDD"]))]
        microservices.append(str(micro["id"]))

    return app_resources, avail, microservices


def microservice(m1):
    """A macro method to create a SMT symbol of a single microservice"""
    return Symbol("%s" % m1, INT)


def replica(m1, r):
    """ A macro for creating a SMT symbol of a replica counter """
    return Symbol("R%s_%s" % (m1, r), INT)


def availability(Rm1):
    """A macro for creating a SMT symbol for the availability metric of a single microservice"""
    return Symbol("Av_%s" % Rm1, REAL)


def microservices_to_nodes(node_offers):
    """
    :param node_offers: a dictionary where the keys represents the nodes while the value is a list of all tasks that can
     be mapped on that node
    :return: a new dictionary where the keys represents each individual tasks while the values are all nodes where that
     task can be mapped.
    """
    mcrs_to_nodes = dict()
    for key, values in node_offers.items():
        for m in values:
            if m in mcrs_to_nodes.keys():
                mcrs_to_nodes[m].append(key)
            else:
                new_values = list()
                new_values.append(key)
                mcrs_to_nodes[m] = new_values

    return mcrs_to_nodes


# step 1: create the replication symbols and their replicas
def create_replication(replicas, microservice, nodes):
    """
    :param replicas: the total number of replicas of the current microservice
    :param microservice: the microservice that is allocated to the network
    :param nodes: a dictionary where a key represents a microservice having the value a list of possible mapping nodes
    :return: an encoding to map exactly one replica on a node and a list of replicas
    """
    replicas_list = list()
    encoding = list()
    for i in range(replicas):
        replicas_list.append(replica(microservice, i))
    replica_len = len(replicas_list)
    for n in nodes[microservice]:
        for i in range(replica_len):
            encoding.append(Equals(replicas_list[i], Int(int(n))).Implies(Not(Or(Equals(replicas_list[j], Int(int(n)))
                                                                              for j in range(i + 1, replica_len)))))
    micro_constraint = And(ExactlyOne(Equals(r, Int(int(n))) for n in nodes[microservice]) for r in replicas_list)
    return And(encoding), replicas_list, micro_constraint


# step 2: create the availability constraints
def availability_encoding(replicas, nodes):
    """
    :param replicas: a list of all replicas symbols of a microservice
    :param nodes: a tuple containing all nodes and their availability
    :return: an encoding for discovering the availability of a microservice based on its allocation
    """
    encoding = list()
    avail_obj = list()
    for r in replicas:
        avail_obj.append(availability(r))
        for n in nodes:
            encoding.append(Equals(r, Int(int(n[0]))).Implies(Equals(availability(r), Real(float(1 - n[1])))))
    return And(encoding), avail_obj


# step 3: create the problem objective
def create_objective(availabilities, app_avail):
    """
    :param availabilities: a list of all availability symbols
    :param app_avail: the availability requirement of the deployed application
    :return: the objective of our deployment
    """
    result = 1
    for elem in availabilities:
        result = result * elem

    return GE(1 - result, Real(app_avail))


def find_replication(microservice, nodes, availability_req, nodes_availability):
    """
    :param microservice: the current microservice we want to replicate
    :param nodes: a dictionary where a key represents a microservice having the value a list of possible mapping nodes
    :param availability_req: the availability requirement of the deployed application
    :param nodes_availability: a list of availability rate for each participant node
    :return: a strategy to map the microservice and its found replicas on the network
    """
    max_no_replicas = len(nodes[microservice])
    count_replicas = 1
    solution = []
    while count_replicas <= max_no_replicas:
        microservice_constraint, microservice_replicas, micro_const = create_replication(count_replicas, microservice,
                                                                                        nodes)
        availability_constraint, availability_obj = availability_encoding(microservice_replicas, nodes_availability)
        problem = create_objective(availability_obj, availability_req)
        f1 = micro_const.And(availability_constraint)
        f2 = f1.And(microservice_constraint)
        formula = f2.And(problem)
        with Solver() as solver:
            solver.add_assertion(formula)
            if solver.solve():
                for i in microservice_replicas:
                    # print("%s = %s" % (i, solver.get_value(i)))
                    solution.append(solver.get_value(i))
                break
            # else:
                # print("No solution found")
        count_replicas += 1

        # print("First encoding - micro_const", micro_const)
        # print("Second encoding - availability const", availability_constraint)
        # print("Third encoding - microservice_const", microservice_constraint)

    return solution


def update_topology(old_topology, micros, app_res, microservice_mapping, flag):
    """
    :param old_topology: the topology configuration before mapping the current microservice
    :param micros: the last microservice that was mapped
    :param app_res: the microservice resoruce requirements given in a dictionary
    :param microservice_mapping: the number of replicas and allocation of the current microservice
    :param flag: if it is true then we will use the old_topology, else we will update it
    :return: the new topology and available resources
    """
    if not flag:
        for n in microservice_mapping:
            old_topology[str(n)][0] = old_topology[str(n)][0] - app_res[micros][0]
            old_topology[str(n)][1] = old_topology[str(n)][1] - app_res[micros][1]
    return old_topology


def update_microservice_node_candidates(mapped_microservice, micro_candidates, microservices, topology, application_res):
    """
    :param mapped_microservice: the last microservice that was mapped
    :param micro_candidates: for each microservice there is a list of nodes where it can be mapped
    :param microservices: the list of all microservices of an application
    :param topology: the topology configuration before mapping the current microservice
    :param application_res: the microservice resource requirements given in a dictionary
    :return: an updated dictionary containing the microservices and their new candidate nodes
    """
    for m in microservices:
        if m == mapped_microservice:
            continue
        else:
            for n in micro_candidates[m]:
                if application_res[m][0] <= topology[n][0] and application_res[m][1] <= topology[n][1]:
                    continue
                else:
                    micro_candidates[m].remove(n)
    return micro_candidates


def millis():
    return int(round(time.time() * 1000))


def start_placement(topology_file: str, application_file: str):
    """Start to find a placement strategy that satisfies all objectives"""

    topology, nodes_availability = get_topology(topology_file)
    application_resources, availability_requirement, microservices_app = get_application(application_file)
    node_possible_mappings = create_nodes_pos_mappings(application_file,
                                      topology_file)

    solution = {}

    start_time = millis()
    microservice_2_nodes = microservices_to_nodes(node_possible_mappings)
    print(f'Start searching for a placement strategy...')
    for m in microservices_app:
        print(f'Current topology before placing {m} is: {topology}')
        microservice_mapping = find_replication(m, microservice_2_nodes, availability_requirement, nodes_availability)
        print(f'mapping = {microservice_mapping} for microservice {m}')
        solution[m] = microservice_mapping
        if len(microservice_mapping) == 0:
            flag = True
        else:
            flag = False
        topology = update_topology(topology, m, application_resources, microservice_mapping, flag)
        print(f'Current topology after placing {m} is: {topology}')
        # topology_new, _ = get_topology(topology_file)
        microservice_2_nodes = update_microservice_node_candidates(m, microservice_2_nodes, microservices_app, topology,
                                                                   application_resources)

    print(f'time = {str(millis() - start_time)} ms')
    print(f'Solution:')
    for s in solution:
        print(f'{s} = {solution[s]}')



if __name__ == '__main__':

    app_size = 7
    top_size = 50
    i = 0
    topology_folder = 'case6_app_7/'
    deployment_case = 'Failure_less_res_new98'
    app_file_name = 'App_newTest4_remember'

    # create_application_file(app_file_name + str(app_size) + '.json', app_size, 350, 0.85, [5, 18])
    # create_topology_file(topology_folder + 'topology_failure_remember' + str(top_size) + '.json', top_size, [50, 80], False, i)

    while i < 1:

        # topology, nodes_availability = get_topology(topology_folder + 'topology_failure_remember' + str(top_size) + '.json')
        # application_resources, availability_requirement, microservices_app = get_application(app_file_name + str(app_size) + '.json')
        # node_offers = create_nodes_offers(app_file_name + str(app_size) + '.json',
        #                                   topology_folder + 'topology_failure_remember' + str(top_size) + '.json')
        topology, nodes_availability = get_topology(
            topology_folder + 'topology_failure_remember' + str(top_size) + '.json')
        application_resources, availability_requirement, microservices_app = get_application('webApplication.json')
        node_offers = create_nodes_offers('webApplication.json',
                                          topology_folder + 'topology_failure_remember' + str(top_size) + '.json')


        solution = {}

        print('Running test = {} for app_size = {} and top_size = {}'.format(i, app_size, top_size))
        f = open('results/deployment/deployment_' + deployment_case + '_remember' + str(app_size) + '.txt', 'a+')
        f.write('>>' * 15 + '\r\n')
        f.write('>>' * 15 + '\r\n')
        f.write('test = ' + str(i) + '\r\n')
        f.write('app_size = ' + str(app_size) + '\r\n')
        f.write('topology_size = ' + str(top_size) + '\r\n')
        f.write('=' * 15 + '\r\n')
        f.write('=' * 15 + '\r\n')
        start_time = millis()
        microservice_2_nodes = microservices_to_nodes(node_offers)
        for m in microservices_app:
            # f.write('=' * 15 + '\r\n')
            # f.write("microservice = " + str(m) + '\r\n')
            # f.write("microservices = " + str(microservice_2_nodes) + '\r\n')
            # f.write("topology before mapping = " + str(topology) + '\r\n')
            microservice_mapping = find_replication(m, microservice_2_nodes, availability_requirement)
            # f.write("mapping = " + str(microservice_mapping) + '\r\n')
            solution[m] = microservice_mapping
            if len(microservice_mapping) == 0:
                flag = True
            else:
                flag = False
            topology = update_topology(topology, m, application_resources, microservice_mapping, flag)
            microservice_2_nodes = update_microservice_node_candidates(m, microservice_2_nodes, microservices_app, topology, application_resources)
        f.write('=' * 15 + '\r\n')
        f.write('time =  ' + str(millis() - start_time) + ' ms' + '\r\n')
        f.write('+' * 10 + '\r\n')
        for s in solution:
            f.write( str(s) + ' = ' + str(solution[s]) + '\r\n')
        # f.write('final topology = ' + str(topology) + '\r\n')
        # f.write('+' * 10 + '\r\n')
        f.close()
        i += 1
        # create_topology_file(topology_folder + 'topology_failure_remember' + str(top_size) + '.json', top_size, [50, 80], True, i)
