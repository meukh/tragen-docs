import opcua
from opcua import ua
from opcua.crypto import security_policies
from threading import Thread
import random
from enum import Enum
from time import sleep

from tragen.ua_data_structure.uaDataStructure import *


class VariableNodeValue(Thread):
    """
    This class represents the updater thread that randomly updates a variable's
    value with regular or irregular intervals. By default, every updatable variable 
    of a Tragen context has one. It is created at initialization time of the context.

    :param var:             The server's variable node
    :param regular_update:  Boolean. If true the updates will be done at fixed intervals.
    :param period:          Interval between updates.
    :param val_stddev:      The standard deviation of the variable's value changes.
    :param pd_stddev:       The standard deviation of the interval changes.
                            Used only if regular_update is not set.
    """
    def __init__(self, var, regular_update=True, period=0.1, val_stddev=0.15, pd_stddev=0.6):
        super(VariableNodeValue, self).__init__()
        self.node = var
        self._updating = True
        self._period = period
        self._val_sd = val_stddev
        self._pd_sd = pd_stddev
        self._reg_ud = regular_update

    def stop(self):
        self._updating = False

    def run(self):
        while self._updating:
            new_val = random.normalvariate(self.node.get_value(), self._val_sd)
            self.node.set_value(new_val)
            zztime = self._period if self._reg_ud else random.normalvariate(self._period, self._pd_sd)
            sleep(zztime)


class AsynchronousNotfication(Thread):
    """
    This class represents the notifier thread that periodically checks wether the value 
    of a variable has reached its critical value or not, it will report/notify the subscribed
    client accordingly through an event. By default, every updatable variable of a Tragen 
    context, that changes periodically, has one. It is created at initialization time.

    :param event:           Event object
    :param var:             The server's variable node
    :param var_name:        
    :param lower_limit:     Lower critical value
    :param upper_limit:     Upper critical value
    :param auto:            If set, then critical values will be set automatically.
    """
    def __init__(self, event, var, var_name, lower_limit=float("-inf"), upper_limit=float("inf"), auto=False):
        super(AsynchronousNotfication, self).__init__()
        self.event = event
        self.node = var
        self.var_name = var_name
        self._running = True
        if not auto:
            self._llimit = lower_limit
            self._ulimit = upper_limit
        else:
            center = self.node.get_value()
            self._llimit = center-0.2*center
            self._ulimit = center+0.2*center
    
    def stop(self):
        self._running = False
    
    def run(self):
        while self._running:
            val = self.node.get_value()
            if val > self._ulimit:
                self._llimit = val-0.2*val
                self._ulimit = val+0.2*val
                self.event.trigger(message="[#] Warning %s! Above critical value."%self.var_name)
            if val < self._llimit:
                self._llimit = val-0.2*val
                self._ulimit = val+0.2*val
                self.event.trigger(message="[#] Warning %s! Below critical value."%self.var_name)
            # Sleep : fix period
            sleep(3)



class ServerTragen(opcua.Server):
    """
    This is the main Tragen server class. It adds functionalities to the inherited
    ones from opcua. Server to simplify the process of automatic traffic generation.

    :param srv_uri:  full address of the server.
    :param name:     name given to the server (optional)
    :param data:     Server's data nodes

    :type data:      UaDataStruct object
    """
    def __init__(self, srv_uri, name=None, data=None, address=None, port=None, path=None, independant=True, by_uri=True):
        super(ServerTragen, self).__init__()

        self.name = name
        self.uri = srv_uri
        self.data = data

        if not by_uri:
            self.uri = "%s:%s/%s"%(addr, port, path)

        self.root_node = None
        self.objects = None

        # If instantiated manually and outside a Tragen context.
        self.independant = independant
        if self.independant:
            self.var_updaters = []
            self.notifiers = []

        self.notifying_events = {} #{"var_name": {"srv_var_node": node, "tragen_var": TragenVariableNode, "event_gen": event_generator}, ...}
        self.readable_items = []
        self.writable_variables = []

    def _rec_populate(self, root, objects, ua_data_struct):
        start = ua_data_struct
        if "folders" in start and start["folders"]!={}:
            for folder in start["folders"]:
                folder_node = root.add_folder(folder.namespace, folder.name)
                self._rec_populate(folder_node, folder_node, start["folders"][folder])
        if "objects" in start and start["objects"]!={}:
            for obj in start["objects"]:
                obj_node = objects.add_object(obj.namespace, obj.name)
                self._rec_populate(obj_node, obj_node, start["objects"][obj])
        if start["variables"] != []:
            for var in start["variables"]:
                tmp = root.add_variable(var.namespace, var.name, var.value)
                self.readable_items.append(var.name)
                if var.is_writable:
                    tmp.set_writable()
                    self.writable_variables.append(var.name)
        if start["properties"] != []:
            for prt in start["properties"]:
                tmp =root.add_variable(prt.namespace, prt.name, prt.value)
                self.readable_items.append(prt.name)
                if prt.is_writable:
                    tmp.set_writable(prt.name)

    def create_notifying_events(self, root, objects, ua_data_struct):
        """
        Create AsynchronousNotfication threads to monitor variable changes 
        and report extreme variations back to clients.
        """
        start = ua_data_struct
        if "folders" in start and start["folders"]!={}:
            for folder in start["folders"]:
                folder_node = root.get_child("%s:%s"%(folder.namespace, folder.name))
                self.create_notifying_events(folder_node, folder_node, start["folders"][folder])
        if "objects" in start and start["objects"]!={}:
            for obj in start["objects"]:
                obj_node = objects.get_child("%s:%s"%(obj.namespace, obj.name))
                self.create_notifying_events(obj_node, obj_node, start["objects"][obj])
        if start["variables"] != []:
            for var in start["variables"]:
                if var.is_reg_ud:
                    var_node = root.get_child("%s:%s"%(var.namespace, var.name))
                    ev_obj = self.get_objects_node().add_object(2, "%s_NotifObject"%var.name)
                    ev_type = self.create_custom_event_type(2, "%s_NotifEvent"%var.name, ua.ObjectIds.BaseEventType)
                    ev_gen = self.get_event_generator(ev_type, ev_obj)
                    notification_info = {"srv_var": var_node, "tragen_var": var, "event_gen": ev_gen}
                    self.notifying_events["%s"%var.name] = notification_info


    def populate_ns(self, data_nodes, by_xml=False):
        """
        Populating the server's address space from the data structure/graph.
        """
        if by_xml:
            # import some nodes from an xml file
            self.import_xml(data_nodes)
        else:
            self.root_node = self.get_root_node()
            self.objects = self.get_objects_node()
            self._rec_populate(self.root_node, self.objects, data_nodes._graph)


    def set_updaters(self, ua_data_struct):
        """
        Recursive method to set up an updater thread for every variable having the updatable
        attribute set. It is supposed to be called by init() but can be called seperately.
    
        :param root:            server's root node
        :param objects:         server's objects node
        :param ua_data_struct:  the server's opc ua data model (graph)
        """
    
        var_updaters = []
    
        def rec_setupdater(root, objects, start):
            if "folders" in start and start["folders"]!={}:
                for folder in start["folders"]:
                    folder_node = root.get_child("%s:%s"%(folder.namespace, folder.name))
                    rec_setupdater(folder_node, folder_node, start["folders"][folder])
            if "objects" in start and start["objects"]!={}:
                for obj in start["objects"]:
                    obj_node = objects.get_child("%s:%s"%(obj.namespace, obj.name))
                    rec_setupdater(obj_node, obj_node, start["objects"][obj])
            if start["variables"] != []:
                for var in start["variables"]:
                    if var.is_irreg_ud:
                        var_node = root.get_child("%s:%s"%(var.namespace, var.name))
                        var_updaters.append(VariableNodeValue(var_node, regular_update=False, period = 3))
                    if var.is_reg_ud:
                        var_node = root.get_child("%s:%s"%(var.namespace, var.name))
                        var_updaters.append(VariableNodeValue(var_node, regular_update=True))
    
        rec_setupdater(self.get_root_node(), self.get_objects_node(), ua_data_struct)
        return var_updaters


    def set_notifiers(self):
        """ 
        Create and set up the server's notifiers threads for monitored items.
        """
        notifiers = []
        for var_name, notif_info in self.notifying_events.iteritems():
            ll = notif_info["tragen_var"].lower_bound
            ul = notif_info["tragen_var"].upper_bound
            limits = {}
            if ll:
                limits["lower_limit":ll]
            if ul:
                limits["upper_limit":ul]
            notifier = AsynchronousNotfication(notif_info["event_gen"], notif_info["srv_var"], var_name, auto=True, **limits)
            notifiers.append(notifier)
    
        return notifiers



    def init(self, data_nodes=None, by_xml=False):
        """
        Set an endpoint, define accepted security policies, populates the adress space,
        create the notification events (to which clients can subscribe), then starts the
        server.

        :type data_nodes:  UaDataStruct()
        """
        self.set_endpoint(self.uri)
        self.set_server_name(self.name)

        self.set_security_policy([
                ua.SecurityPolicyType.NoSecurity,
                ua.SecurityPolicyType.Basic128Rsa15_SignAndEncrypt,
                ua.SecurityPolicyType.Basic128Rsa15_Sign,
                ua.SecurityPolicyType.Basic256_SignAndEncrypt,
                ua.SecurityPolicyType.Basic256_Sign])

        #self.load_certificate("server_cert.pem")
        #self.load_private_key("server_private_key.pem")

        # populating the address space
        self.populate_ns(data_nodes, by_xml)
        # creating notification events (if there's any, for clients to subscribe to)
        self.create_notifying_events(self.get_root_node(), self.get_objects_node(), data_nodes._graph)
        
        if self.independant:
            # Create an updater thread for every updatable variable then start it
            self.var_updaters = self.set_updaters(data_nodes._graph)
            for updater in self.var_updaters:
                updater.start()
            # Create  notifier thread for every monitored variable then start it
            self.notifiers = self.set_notifiers()
            for notifier in self.notifiers:
                notifier.start()

        self.start()


