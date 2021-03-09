from pysmt.shortcuts import Symbol, And, Plus, Int, ExactlyOne, Equals, get_formula_size, GE, Or, Not, Real
from pysmt.shortcuts import Solver
from pysmt.typing import INT, REAL
import json
import random
import time
import socket
import requests
from requests.auth import HTTPBasicAuth


def check_alive(node):
    """Check if node is alive"""
    proto, host, port = node.split(':')
    host = host.replace('//', '')
    port = int(port)
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex((host, port))
    return result == 0


def create_nodes_pos_mappings(application, topology):
    """
    Create the possible mapping of microservice on each edge node.
    :param application: the JSON dictionary where the model of the app is described
    :param topology: the list of available nodes
    :return: a dictionary where value represents a list of microservices and key is the edge node
    """

    node_maps = {}
    for node in topology:
        node_maps[str(node['id'])] = [str(m['id']) for m in application["IoTapplication"]["microservices"]]
    return node_maps


def get_topology(topology_nodes, credentials):
    """
    Get information regarding the topology, i.e., available resources and failure rates for each node.
    :param topology_nodes: the list of available nodes
    :return: a dictionary where the key is a node and the value represents the resources and a list of failure rates
    for each node
    """
    node_resources = dict()
    nodes_failures = []

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


def get_application(app_dict):
    """
    :param app_dict: the JSON dictionary where the model of the app is described,
                     the application's resource requirements are given in MB!!!
    :return: a dictionary where the key is a microservice and the value represents their resource requirements in bytes
    """
    app_resources = dict()
    microservices = []

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
                    solution.append(str(solver.get_value(i)))
                break
        count_replicas += 1
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
                if application_res[m][0] <= topology[n][0] and\
                        application_res[m][1] <= topology[n][1]:
                    continue
                else:
                    micro_candidates[m].remove(n)
    return micro_candidates


def millis():
    return int(round(time.time() * 1000))


def start_placement(nodes, credentials, application):
    """Start to find a placement strategy that satisfies all objectives"""

    topology, nodes_availability = get_topology(nodes, credentials)
    application_resources, availability_requirement, microservices_app = get_application(application)
    node_possible_mappings = create_nodes_pos_mappings(application,
                                      nodes)

    solution = {}
    start_time = millis()
    microservice_2_nodes = microservices_to_nodes(node_possible_mappings)
    print(f'Start searching for a placement strategy...')
    for m in microservices_app:
        # print(f'Current topology before placing {m} is: {topology}')
        microservice_mapping = find_replication(m, microservice_2_nodes, availability_requirement, nodes_availability)
        print(f'mapping = {microservice_mapping} for microservice {m}')
        solution[m] = microservice_mapping
        if len(microservice_mapping) == 0:
            flag = True
        else:
            flag = False
        topology = update_topology(topology, m, application_resources, microservice_mapping, flag)
        microservice_2_nodes = update_microservice_node_candidates(m, microservice_2_nodes, microservices_app, topology,
                                                                   application_resources)

    print(f'time = {str(millis() - start_time)} ms')
    print(f'Solution:')
    for s in solution:
        print(f'{s} = {solution[s]}')
    return solution

