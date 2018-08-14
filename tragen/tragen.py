import sys
import opcua
from opcua import ua
from opcua.crypto import security_policies
from threading import Thread
import random
from enum import Enum
from operator import add
from time import sleep
import os

from .ua_data_structure.uaDataStructure import * 
from .client_tragen.tragenClient import *
from .server_tragen.tragenServer import *


class Tragen(object):

    """
    This is the main class of the OPC UA traffic generator.

    An instance of this class is a Tragen context. It orchestrates a custom
    communication between one opc-ua server and a set of connected clients.

    Create your server from here and indicate the number of desired clients.

    Then, create an instance of the 'UaDataStruct' class to define the nodes,
    variables, folders that will be stored in the server and describe their
    behavior through their attributes (e.g 'is_writable', 'is_reg_ud', ..)

    The last step will generate a graph of nodes that is used to populate the
    server's namespace, create threads that will simulate physical processes,
    create threads that will generate clients requests and others replying to
    said clients.


    :ivar srv_addr: 
    :vartype srv_addr: uri
    :ivar nb_client:
    :vartype nb_client: integer
    :ivar srv_name:
    :vartype srv_name: string
    :ivar namespace: 
    :vartype namespace: integer
    """

    def __init__(self, srv_addr="opc.tcp://0.0.0.0:4840/tragen0/server0/", srv_name=None, nb_client=1, namespace=1, output_directory=None):
        super(Tragen, self).__init__()

        # Creating the server
        self.server = ServerTragen(srv_uri=srv_addr, name=srv_name)
        self.srv_url = self.server.uri
        # Creating Clients
        self.clients = [ClientTragen(self.srv_url) for i in range(nb_client)]
        # Initializing the list of variable updaters
        self.var_updaters = []
        # Initializing the list of asynchronous notifiers
        self.notifiers = []
        # Initializing the list of writers and readers (a pair for each client)
        self.writers, self.readers = [], []
        # Initializing the list of method callers
        #TODO: ?
        self.method_callers = []


    def init(self, ua_srv_data=None):

        """
        Initialize the Tragen context. The server and th clients are initialized.
        The server threads modifying data and notifying the clients are set up.
        The client threads reading, writing and polling the srever are set up here.
        Should be called after the data structure has been well defined.

        :param ua_srv_data:     the server's opc ua data model (graph)
        :type ua_srv_data:      UaDataStruct()
        """

        self.srv_data = ua_srv_data
        # Setting up the server and populating the addresspace
        self.server.init(data_nodes=ua_srv_data, independant=False)
        # Connecting clients to the server and handling events/nodes subscriptions
        for client in self.clients:
            client.init(ua_data_struct=ua_srv_data, independant=False)
        # Create an updater thread for every updatable variable then start it
        self.set_updaters(self.server.get_root_node(), self.server.get_objects_node(), self.srv_data._graph)
        for var_updater in self.var_updaters:
            var_updater.start()
        # Create  notifier thread for every monitored variable then start it
        self.set_notifiers()
        for notifier in self.notifiers:
            notifier.start()
        # Create clients' agents then start them
        for client in self.clients:
            self.set_client_agents(self.server.readable_items, self.server.writable_variables, client.get_root_node(), client.get_objects_node(), self.srv_data._graph)
        for agent in self.writers + self.readers:
            agent.start()


    def set_updaters(self, root, objects, ua_data_struct):
        """
        Recursive method to set up an updater thread for every variable having the updatable
        attribute set. It is supposed to be called by init() but can be called seperately.

        :param root:            server's root node
        :param objects:         server's objects node
        :param ua_data_struct:  the server's opc ua data model (graph)
        """
        start = ua_data_struct
        if "folders" in start and start["folders"]!={}:
            for folder in start["folders"]:
                folder_node = root.get_child("%s:%s"%(folder.namespace, folder.name))
                self.set_updaters(folder_node, folder_node, start["folders"][folder])
        if "objects" in start and start["objects"]!={}:
            for obj in start["objects"]:
                obj_node = objects.get_child("%s:%s"%(obj.namespace, obj.name))
                self.set_updaters(obj_node, obj_node, start["objects"][obj])
        if start["variables"] != []:
            for var in start["variables"]:
                if var.is_irreg_ud:
                    var_node = root.get_child("%s:%s"%(var.namespace, var.name))
                    self.var_updaters.append(VariableNodeValue(var_node, regular_update=False, period = 3))
                if var.is_reg_ud:
                    var_node = root.get_child("%s:%s"%(var.namespace, var.name))
                    self.var_updaters.append(VariableNodeValue(var_node, regular_update=True))


    def set_client_agents(self, items_list, var_list, root, objects, ua_data_struct):
        """
        Create and set up random reader and a writer thread (for a client) 

        :param items_list:  list of readable variables and properties
        :param var_list:    list of writable variables
        :param root:         client's root node        
        :param objects:     client's objects node
        """
        reader = ItemValueReader()
        self.readers.append(reader)
        writer = VariableValueWriter()
        self.writers.append(writer)
        start = ua_data_struct
        if "folders" in start and start["folders"]!={}:
            for folder in start["folders"]:
                folder_node = root.get_child("%s:%s"%(folder.namespace, folder.name))
                self.set_client_agents(items_list, var_list, folder_node, folder_node, start["folders"][folder])
        if "objects" in start and start["objects"]!={}:
            for obj in start["objects"]:
                obj_node = objects.get_child("%s:%s"%(obj.namespace, obj.name))
                self.set_client_agents(items_list, var_list, obj_node, obj_node, start["objects"][obj])
        if start["variables"] != []:
            for var in start["variables"]:
                if var.name in items_list:
                    var_node = root.get_child("%s:%s"%(var.namespace, var.name))
                    reader.items_list.append(var_node)
                if var.name in var_list:
                    var_node = root.get_child("%s:%s"%(var.namespace, var.name))
                    writer.var_list.append(var_node)
        if start["properties"] != []:
            for prt in start["properties"]:
                if prt.name in items_list:
                    prt_node = root.get_child("%s:%s"%(prt.namespace, prt.name))
                    reader.items_list.append(prt_node)


    def set_notifiers(self):
        """ 
        Create and set up the server's notifiers threads for monitored items.
        """
        
        for var_name, notif_info in self.server.notifying_events.iteritems():
            ll = notif_info["tragen_var"].lower_bound
            ul = notif_info["tragen_var"].upper_bound
            limits = {}
            if ll:
                limits["lower_limit":ll]
            if ul:
                limits["upper_limit":ul]
            notifier = AsynchronousNotfication(notif_info["event_gen"], notif_info["srv_var"], var_name, auto=True, **limits)
            self.notifiers.append(notifier)


    def add_client(self, srv_addr):
        """
        Add another client to the client's list, connect 
        it tothe server's endpoint and initialize it.
        """

        new_client = ClientTragen(srv_addr)
        self.clients.append(new_client)
        if self.clients[0].connected:
            new_client.init(ua_data_struct=self.srv_data)


    def close(self):
        """
        Shut down the Tragen context: disconnect clients and stop the server.
        """
        for client in self.clients:
            client.disconnect()
        self.server.stop()
