from pysmt.shortcuts import Symbol, And, Plus, Int, ExactlyOne, Equals, get_formula_size, LE, Or, Not, Real, GE
from pysmt.shortcuts import Solver
from pysmt.typing import INT, REAL
import random
import json
import time
import subprocess
import typing


def find_topology(file_name):
    """
    Find the current topology size
    :param file_name: the name of the deployment input file
    :return: the topology and a dictionary to save the failure probabilities of each node
    """

    nodes_failures = {}

    # read the JSON file containing the topology
    with open('topologies/' + file_name) as f:
        topology = json.load(f)

    for node in topology["IoTtopology"]["nodes"]:
        nodes_failures[str(node['id'])] = float(node['failure'])

    return topology["IoTtopology"]["nodes"], nodes_failures


def find_latency(node: str):
    """
    Get the average latency of a node
    :param node: the ip address of a node
    :return: the average latency to communicate with the node, considering 10 pings
    """
    results = subprocess.run(['ping', '-c', '10', node], stdout=subprocess.PIPE).stdout.decode('utf-8')

    return results.split('\n')[-2].split(' = ')[1].split('/')[1]


def build_latency_dict(nodes):
    """
    :param nodes: the list of nodes
    :return: a dictionary containing the latencies between two nodes, where key is a string showing the
    communication link between two nodes, while the value represents the communication latency between them.
    """
    latencies = {}
    len_nodes = len(nodes)
    for i in range(1, len_nodes):
        for j in range(i + 1, len_nodes + 1):
            s = str(i) + "-" + str(j)
            latencies[s] = random.choice(range(1, 10))
    return latencies

    # for node in nodes:
    #     node_ip = node['ip']
    # ToDO: i need to add an APi so I can get the latency between all nodes!!!


def get_latency(n1, n2, latency_dict):
    """
    :param n1: first node where a task is placed.
    :param n2: second node where a task is placed.
    :param latency_dict:  a dictionary containing the latency between dependent tasks
    :return: the latency between the two nodes, considering that the latency between n1_n2 == n2_n1.
    """
    if n1 == n2:
        latency = 0
    else:
        s = str(n1) + "-" + str(n2)
        if s in latency_dict:
            latency = latency_dict[s]
        else:
            s = str(n2) + "-" + str(n1)
            latency = latency_dict[s]
    return latency


def get_deployment_solution(file_name):
    """
    Read the deployment solution generated by the deployment strategy and create a JSON file with all valid solutions
    :param file_name: the name of the deployment input file
    :return: the JSON file name
    """
    deployment_strategy = {}
    deployment_solutions = []

    #find the size of the application
    _, _, app_size = file_name.split('_')

    # read the input file and filter the valid solutions
    with open('../results/deployment/' + file_name + '.txt', 'r') as file:
        solution = {}
        for line in file.readlines():
            if line.startswith('test'):
                _, id = line.rstrip('\r\n').split(' = ')
                solution['id'] = id
            if line.startswith('m'):
                tsk, location = line.rstrip('\r\n').split(' = ')
                if location == '[]':
                    continue
                solution[tsk] = location
                # if line.startswith('m' + app_size[8:]):
                #     deployment_solutions.append(solution)
                #     solution = {}
            if line.startswith('>>>>') and solution:
                if len(solution) == int(app_size[8:]) + 1:
                    deployment_solutions.append(solution)
                solution = {}
    deployment_strategy['deployment_strategies'] = deployment_solutions

    with open('../results/deployment/' + file_name + '_valid_solutions.json', 'w') as json_file:
        json.dump(deployment_strategy, json_file)

    return '../results/deployment/' + file_name + '_valid_solutions.json'


def task(t1):
    """ A macro method to create a SMT symbol of a single tasks"""
    return Symbol("%s" % t1, INT)


def availability(Rm1):
    """A macro for creating a SMT symbol for the availability metric of a single microservice"""
    return Symbol("Av_%s" % Rm1, REAL)


def latency(t1, t2):
    """
    :param t1: a symbol of a task.
    :param t2: a symbol of a task.
    :return: return a SMT symbol for latency between two nodes.
    """
    return Symbol("l_%s_%s" % (t1, t2), INT)


def create_latency_constraint(app):
    """
    :param app: the job model graph.
    :return: a list of latency encodings constraint.
    """
    problem = []
    dependencies = []
    tasks = []
    for t1 in app["IoTapplication"]["microservices"]:
        tasks.append(task(str(t1["id"])))
        for d in t1["dest"]:
            depend_tasks = []
            problem.append(latency(str(t1["id"]), str(d["id"])))
            depend_tasks.append(str(t1["id"]))
            depend_tasks.append(str(d["id"]))
            dependencies.append(depend_tasks)
    return LE(Plus(problem), Int(int(app["IoTapplication"]["SLA"]['e2e']))), problem, dependencies, tasks


def create_task_facts(dependencies, tasks_on_nodes, latency_dict):
    """
    :param latency_dict:  a dictionary containing the latency between dependent tasks
    :return: a SMT encoding containing the latency between two tasks.
    """
    task_facts = []
    for grp in dependencies:
        if grp[0] in tasks_on_nodes and grp[1] in tasks_on_nodes:
            for n1 in tasks_on_nodes[grp[0]]:
                for n2 in tasks_on_nodes[grp[1]]:
                    task_facts.append(And(Equals(task(grp[0]), Int(int(n1))), Equals(task(grp[1]),
                                    Int(int(n2)))).Implies(Equals(latency(grp[0], grp[1]), Int(get_latency(n1, n2, latency_dict)))))
    return And(task_facts)


def create_tasks_possibilities(tasks_on_nodes):
    """
    :return: a SMT encoding containing all task mapping possibilities.
    """
    tasks_possibilities = []
    for t, nodes in tasks_on_nodes.items():
        tasks_possibilities.append(Or(Equals(task(t), Int(int(n))) for n in nodes))
    return And(tasks_possibilities)


def find_tasks_on_nodes(deployment_solution):
    """
    Convert the JSON dict values from string to list
    :param deployment_solution: the deployment solution taken from the deployment JSON file
    :return: a new dictionary containing a solution where key is a task and value is a list of nodes
    """
    tasks_on_nodes = {}
    for task, nodes in deployment_solution.items():
        tasks_on_nodes[str(task)] = [str(elem) for elem in nodes]

    return tasks_on_nodes


def availability_encoding(tasks_on_nodes, nodes_failures):
    """
    :param tasks_on_nodes: a dictionary containing the location of every tasks
    :param nodes_failures: a dictionary where the failure rate of all nodes is stored
    :return: an encoding for discovering the availability of a microservice based on its allocation
    """
    encoding = list()
    avail_obj = list()
    for t, nodes in tasks_on_nodes.items():
        avail_obj.append(availability(task))
        for n in nodes:
            encoding.append(Equals(task(t), Int(int(n))).Implies(Equals(availability(t), Real(float(1 - nodes_failures[n])))))
    return And(encoding), avail_obj


def create_availability_objective(availabilities, app_avail):
    """
    :param availabilities: a list of all availability symbols
    :param app_avail: the availability requirement of the deployed application
    :return: the objective of our deployment
    """
    result = 1
    for elem in availabilities:
        result = result * elem

    return GE(1 - result, Real(app_avail))


# A context (with-statment) lets python take care of creating and
# destroying the solver.
def self_adapt(solution, topology_file):

    topology, nodes_failures = find_topology(topology_file)
    latency_dict = build_latency_dict(topology)

    # read the JSON file containing the application description
    with open("apps/webApplication.json") as f:
        app_dict = json.load(f)

    #create the three encodings for the SMT formula
    problem, latencies, dependencies, tasks = create_latency_constraint(app_dict)
    # stabilization_file = open('../results/stabilization/stabilization_case5_results_good', 'w+')

    # read every deployment solution and find a invocation chain
    start_time = millis()
    print(f'Starting to find an invocation chain...')
    tasks_on_nodes = find_tasks_on_nodes(solution)
    task_facts = create_task_facts(dependencies, tasks_on_nodes, latency_dict)
    task_possibilities = create_tasks_possibilities(tasks_on_nodes)
    availability_enc, avail_obj = availability_encoding(tasks_on_nodes, nodes_failures)
    problem_availability = create_availability_objective(avail_obj, app_dict["IoTapplication"]["SLA"]['availability'])

    # combine the encoding above to generate the SMT formula
    f1 = task_possibilities.And(task_facts)
    f2 = f1.And(availability_enc)
    f3 = f2.And(problem_availability)
    formula = f3.And(problem)

    invocation_path = set()

    with Solver() as solver:
        solver.add_assertion(formula)
        if solver.solve():
            for t in tasks:
                print(f'{t} = {solver.get_value(t)}')
                invocation_path.add(solver.get_value(t))
            for l in latencies:
                print(f'{l} = {solver.get_value(l)}')
        else:
            print("No solution found")
    print(f'time =  {millis() - start_time} ms')
    return invocation_path


def millis():
    return int(round(time.time() * 1000))


if __name__ == '__main__':

    self_adapt()