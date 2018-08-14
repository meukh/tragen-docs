import opcua
from opcua import ua
from opcua.crypto import security_policies
from threading import Thread
import random
from enum import Enum
from time import sleep

from ..ua_data_structure.uaDataStructure import *


class SubType(Enum):
    """
    Simple enum for the possible types of subscriptions.
    """
    DATA_CHANGE = 0x1
    EVENT = 0x2
    STATUS_CHANGE = 0x4

class SubHandler(object):
    """
    Subscription Handler. To receive events from server for a subscription
    """
    def datachange_notification(self, node, val, data):
        print("Python: New data change event", node, val)

    def event_notification(self, event):
        print("New event notification", event.Message.Text)

    def status_change_notification(self, status):
        print("Python: New event", status)


class ItemValueReader(Thread):
    """
    This class represents the reader thread that randomly reads a variable's
    or a property's value in the server. By default, every client of a Tragen
    context has one. It is created at initialization time of Tragen context.

    :param items_list:  list of the server's readable items (e.g variable values)
    :param period:      frequency by which the reader is sending requests 
                        the server.
    """
    def __init__(self, items_list=[], period=0.5):
        super(ItemValueReader, self).__init__()
        self.items_list = items_list
        self.period = period
        self._running = True

    def stop(self):
        self_running = False

    def run(self):
        while self._running:
            item = random.choice(self.items_list)
            item.get_value()
            sleep(self.period)


class VariableValueWriter(Thread):
    """
    This class represents the writer thread that randomly writes a variable's
    or a property's value in the server. By default, every client of a Tragen
    context has one. It is created at initialization time of Tragen context.

    :param var_list:    list of the server's readable items (e.g variable values)
    :param period:      frequency by which the writer is sending requests 
                        the server.
    """
    def __init__(self, var_list=[], period=1):
        super(VariableValueWriter, self).__init__()
        self.var_list = var_list
        self.period = period
        self._writing = True

    def stop(self):
        self._writing = False

    def run(self):
        while self._writing:
            var = random.choice(self.var_list)
            val = var.get_value()
            new_val = val*random.uniform(0.1,10)
            var.set_value(new_val)
            sleep(self.period)



class ClientTragen(opcua.Client):
    """
    This is the main Tragen client class. It adds functionalities to the inherited
    ones from opcua.Client to simplify the process of automatic traffic generation.

    :param srv_address:     full address of the server.
    :param name:            name given to the client (optional)
    """
    def __init__(self, srv_address, name=None, independant=True):
        super(ClientTragen, self).__init__(srv_address)

        self.subscriptions = {}
        self.srv_address = srv_address
        self.name = name
        self.connected = False
        self.independant = independant
        if self.independant:
            self.reader = ItemValueReader()
            self.writer = VariableValueWriter()



    def _add_subscription(self, node, subscription_type, subscription_obj, subscription_handle):
        """
        Adds a new client's subscription (to a node or an event) information to the subscription list
        Should preferably not be called from outside this class.

        :param node:    variable's node if subscription to a data change
                        event object node if an event subscription

        :param subscription_type: 
        """
        self.subscriptions[node] = {"subscription": subscription_obj, "handle": subscription_handle, "type": subscription_type}

    def subscribe_node(self, node, stype, event=None, event_obj= None, period=1000):
        handler = SubHandler()
        sub = self.create_subscription(period, handler)
        if stype == SubType.DATA_CHANGE:
            hilt = sub.subscribe_data_change(node)
        else:
            hilt = sub.subscribe_events(event_obj, event)
        self._add_subscription(node, stype, sub, hilt)

    def rec_subs(self, root, objects, ua_data_struct):
        start = ua_data_struct
        if "folders" in start and start["folders"]!={}:
            for folder in start["folders"]:
                folder_node = root.get_child("%s:%s"%(folder.namespace, folder.name))
                self.rec_subs(folder_node, folder_node, start["folders"][folder])
        if "objects" in start and start["objects"]!={}:
            for obj in start["objects"]:
                obj_node = objects.get_child("%s:%s"%(obj.namespace, obj.name))
                self.rec_subs(obj_node, obj_node, start["objects"][obj])
        if start["variables"] != []:
            for var in start["variables"]:
                if var.is_irreg_ud:
                    var_node = root.get_child("%s:%s"%(var.namespace, var.name))
                    self.subscribe_node(var_node, SubType.DATA_CHANGE)
                if var.is_reg_ud:
                    var_node = root.get_child("%s:%s"%(var.namespace, var.name))
                    ev_obj = self.get_objects_node().get_child("2:%s_NotifObject"%var.name)
                    ev_type = self.get_root_node().get_child(["0:Types", "0:EventTypes", "0:BaseEventType", "2:%s_NotifEvent"%var.name])
                    self.subscribe_node(var_node, SubType.EVENT, event_obj= ev_obj, event=ev_type)
        #if start["properties"] != []:
        #    for prt in start["properties"]:
        #        if prt.is_writable:
        #            tmp =root.get_child("%s:%s"%(prt.namespace, prt.name))
        #            tmp.set_writable()


    def initialize_subs(self, ua_data_struct):
        """
        Subscribe to nodes that are to be monitored (Typically, updatable variables in the server's
        data graph), and events (e.g node values to be monitored). Called at initialization time.

        :param ua_data_struct:  Data nodes graph
        """
        self.root_node = self.get_root_node()
        self.objects = self.get_objects_node()
        self.rec_subs(self.root_node, self.objects, ua_data_struct)

    def delete_subscription(self, subscription, handle):
        """
        Delete a subscription.
        Parameters are typically stored in the subscription list attribute.

        :param subscription:    subscription object
        :param handle:          handle (an integer)
        """
        subscription.unsubscribe(handle)
        subscription.delete()

    def delete_all_subscription(self):
        """
        Delete all subscriptions to nodes and events.
        """
        for sub in self.subscriptions.values():
            self.delete_subscription(sub["subscription"], sub["handle"])


    def set_client_agents(self, items_list, var_list, ua_data_struct):
        """
        Create and set up random reader and a writer thread (for a client) 
    
        :param items_list:  list of readable variables and properties
        :param var_list:    list of writable variables
        """
        #reader = ItemValueReader()
        #writer = VariableValueWriter()
    
        def rec_clsetup(root, objects, start):
            if "folders" in start and start["folders"]!={}:
                for folder in start["folders"]:
                    folder_node = root.get_child("%s:%s"%(folder.namespace, folder.name))
                    rec_clsetup(folder_node, folder_node, start["folders"][folder])
            if "objects" in start and start["objects"]!={}:
                for obj in start["objects"]:
                    obj_node = objects.get_child("%s:%s"%(obj.namespace, obj.name))
                    rec_clsetup(obj_node, obj_node, start["objects"][obj])
            if start["variables"] != []:
                for var in start["variables"]:
                    if var.name in items_list:
                        var_node = root.get_child("%s:%s"%(var.namespace, var.name))
                        self.reader.items_list.append(var_node)
                    if var.name in var_list:
                        var_node = root.get_child("%s:%s"%(var.namespace, var.name))
                        self.writer.var_list.append(var_node)
            if start["properties"] != []:
                for prt in start["properties"]:
                    if prt.name in items_list:
                        prt_node = root.get_child("%s:%s"%(prt.namespace, prt.name))
                        self.reader.items_list.append(prt_node)
    
        rec_clsetup(self.get_root_node(), self.get_objects_node(), ua_data_struct)
        #return writer, reader


    def setup_rw(self, ua_data_struct):
        """
        Get a list of all the readable and writable nodes.
        """
        writables, readables = [], []
        def rec_rwsetup(start):
            if "folders" in start and start["folders"]!={}:
                for folder in start["folders"]:
                    rec_rwsetup(start["folders"][folder])
            if "objects" in start and start["objects"]!={}:
                for obj in start["objects"]:
                    rec_rwsetup(start["objects"][obj])
            if start["variables"] != []:
                for var in start["variables"]:
                    readables.append(var.name)
                    if var.is_writable:
                        writables.append(var.name)
            if start["properties"] != []:
                for prt in start["properties"]:
                    readables.append(prt.name)
        
        rec_rwsetup(ua_data_struct)
    
        return writables, readables


    def init(self, ua_data_struct=None):
        """
        Connect to the server, and initialize subscriptions if the server's data nodes are provided.

        :type ua_data_struct:   UaDataStruct()
        """
        # Security policy (Uncomment to enable)
        #self.set_security(security_policies.SecurityPolicyBasic128Rsa15, "client_cert.pem", "client_private_key.pem", server_certificate_path="server_cert.pem")
        self.connect()
        self.connected = True
        self.load_type_definitions()
        if ua_data_struct is not None:
            self.initialize_subs(ua_data_struct._graph)
        if self.independant:
            writables, readables = self.setup_rw(ua_data_struct._graph)
            self.set_client_agents(readables, writables, ua_data_struct._graph)
            self.writer.start()
            self.reader.start()


