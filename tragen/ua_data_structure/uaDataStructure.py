from enum import Enum
from operator import add


class NodeType(Enum):
    FOLDER = 0
    OBJECT = 1
    VARIABLE = 2
    PROPERTY = 3
    UNDEFINED = 4

class TragenNodeStruct(object):
    """
    This is the base Tragen node class. All the typed Tragen nodes are instances of it. 
    """
    def __init__(self, name, ns=0, parent_name=None, parent=None):
        self.name = name
        self.namespace = ns
        self.parent_node = parent
        self.parent_node_name = parent_name
        self.node_type = NodeType.UNDEFINED

    def get_node_type(self):
        return self.node_type

class TragenFolder(TragenNodeStruct):
    node_type = NodeType.FOLDER
    content_struct_ptr = None

class TragenObject(TragenNodeStruct):
    node_type = NodeType.OBJECT
    content_struct_ptr = None

class TragenVariable(TragenNodeStruct):
    def __init__(self, name, value=None, **kwargs):
        super(TragenVariable, self).__init__(name, **kwargs)
        self.value = value
        self.node_type = NodeType.VARIABLE

    is_reg_ud = False
    is_irreg_ud = False
    is_writable = False
    is_monitored = False

    # Critical values
    lower_bound = None
    upper_bound = None

class TragenProperty(TragenNodeStruct):
    def __init__(self, name, value=None, **kwargs):
        if value:
            if type(value) != str:
                raise Exception("A property cannot be of type %s" %type(value))
        super(TragenProperty, self).__init__(name, **kwargs)
        self.value = value
        self.node_type = NodeType.PROPERTY

    is_ud = False
    is_writable = False


class UaDataStruct(object):
    def __init__(self, namespace=1, folder=None, parent_node=None, ua_object=None, ua_variables=[], ua_properties=[]):
        self._graph = {"folders":{}, "objects":{}, "variables":[], "properties":[]}
        #self.reg_ud_vars=[]     #list of regularly updated variables (paths?)
        #self.irreg_ud_vars=[]   #list of variables updated randomly

        if folder or ua_object or ua_variables or ua_properties:
            fldr_node = self.add_folder(folder, namespace=namespace) if folder else None
            obj_node = self.add_object(ua_object, namespace=namespace, folder_name=folder, folder_node=fldr_node) if ua_object else None
            for var_name, var_val in ua_variables:
                self.add_variable(var_name, var_value=var_val, namespace=namespace, par_name=(ua_object or folder), par_node=(obj_node or fldr_node))
            for prt_name, prt_val in ua_properties:
                self.add_property(prt_name, prt_val, namespace=namespace, par_name=(ua_object or folder), par_node=(obj_node or fldr_node))

    def add_object(self, ua_object, namespace=0, folder_name=None, folder_node=None, ua_variables=[], ua_properties=[]):
        obj = TragenObject(ua_object, ns=namespace, parent_name=folder_name)
        variables = [TragenVariable(var[0], value=var[1], ns=namespace, parent=obj, parent_name=obj.name) for var in ua_variables] if ua_variables else []
        properties = [TragenProperty(prpt[0], value=prpt[1], ns=namespace, parent=obj, parent_name=obj.name) for prpt in ua_properties] if ua_properties else []

        if not folder_name and not folder_node:
            obj.content_struct_ptr = self._graph["objects"][obj]={"variables": variables, "properties": properties}
        elif not folder_node:
            metafolder = self.find_folder(folder_name)
            # dirty fix: (nkhdem paths?) (edit: blash, diru m9ad ola blash)
            if len(metafolder)>1:
                raise Exception("Two or more folders with this name. Please refer to it using its full path.")
            elif len(metafolder)==0:
                raise Exception("No such folder: '%s'" % parent_name)
            fldr_obj, fldr_node = metafolder[0]
            if len(self.find_object(ua_object, graph=fldr_node))>=1:
                raise Exception("Another object with this name exists in this path. You may want to change the name.")
            obj.parent_node = fldr_obj
            obj.parent_node_name = fldr_obj.name
            obj.content_struct_ptr = fldr_node["objects"][obj] = {"variables": variables, "properties": properties}
        else:
            if len(self.find_object(ua_object, graph=folder_node))>=1:
                raise Exception("Another object with this name exists in this path. You may want to change the name.")
            obj.content_struct_ptr = folder_node["objects"][obj]={"variables": variables, "properties": properties}

        return obj.content_struct_ptr

    def add_folder(self, folder_name, namespace=0, parent_name=None, parent_node=None):
        folder = TragenFolder(folder_name, ns=namespace, parent_name=parent_name)
        if not parent_name and not parent_node:
            folder.content_struct_ptr = self._graph["folders"][folder] = {"folders":{}, "objects":{}, "variables":[], "properties":[]}
        elif not parent_node:
            metafolder = self.find_folder(parent_name) #dirha katred l'objet ou dictionnaire dialu ok? k
            if len(metafolder)>1:
                raise Exception("Many folders with this name. Please refer to it using its full path.")
            elif len(metafolder)==0:
                raise Exception("No such folder: '%s'" % parent_name)
            metafolder_obj, metafolder_node = metafolder[0]
            if len(self.find_folder(folder_name, graph=metafolder_node))>=1:
                raise Exception("Another folder with the name %s exists under %s. You may want to change the name."%(folder_name, metafolder_obj.name))
            folder.parent_node = metafolder_obj.name
            folder.content_struct_ptr = metafolder_node["folders"][folder] = {"folders":{}, "objects":{}, "variables":[], "properties":[]}
        else:
            if len(self.find_folder(folder_name, graph=folder_node))>=1:
                raise Exception("Another folder with this name exists in this path. You may want to change the name.")
            folder.content_struct_ptr = parent_node["folders"][folder] = {"folders":{}, "objects":{}, "variables":[], "properties":[]}

        return folder.content_struct_ptr


    def add_variable(self, var_name, var_value=None, namespace=0, par_name=None, par_node=None):
        variable = TragenVariable(var_name, value=var_value, ns=namespace, parent_name=par_name)
        if not par_name and not par_node:
            self._graph["variables"].append(variable)
        elif not par_node:
            metaobject = self.find_object(par_name)
            if len(metaobject)>1:
                raise Exception("Many objects or folders with this name. Please refer to it using its full path.")
            elif len(metaobject)==0:
                raise Exception("No such object/folder: '%s'" % object_name)
            metaobject, metaobject_node = metaobject[0]
            if len(self.find_variable(var_name, graph=metaobject_node))>=1:
                raise Exception("Another variable with the same name exists in this path. You may want to change the name.")
            variable.parent_node = metaobject_node
            variable.parent_node_name = metaobject_node.name
            metaobject_node["variables"].append(variable)
        else:
            if len(self.find_variable(var_name, graph=par_node))>=1:
                raise Exception("Another variable with the same name exists in this path. You may want to change the name.")
            par_node["variables"].append(variable)

        return variable


    def add_property(self, property_name, property_value, namespace=0, par_name=None, par_node=None):
        prpt= TragenProperty(property_name, value=property_value, ns=namespace, parent=par_node, parent_name=par_name)
        if not par_name and not par_node:
            self._graph["properties"].append(prpt)
        elif not par_node:
            metaobject = self.find_object(par_name)
            if len(metaobject)>1:
                raise Exception("Many objects with this name. Please refer to it using its full path.")
            elif len(metaobject)==0:
                raise Exception("No such object: '%s'" % par_name)
            metaobject, metaobject_node = metaobject[0]
            metaobject_node["properties"].append(prpt)
        else:
            par_node["properties"].append(prpt)

        return prpt


    def find_node(self, name, node_type, starting_point=None, path=[]):

        if node_type == NodeType.FOLDER:
            nodetype = "folders"
        if node_type == NodeType.OBJECT:
            nodetype = "objects"

        def rec_find(start):
            findings = []
            if start[nodetype]=={}:
                return []
            else:
                for obj, node in start[nodetype].iteritems():
                    if obj.name==name:
                        findings.append((obj, node))
                try:
                    return reduce(add, map(rec_find, start["folders"].values())) + findings
                except TypeError as err:
                    return findings

        if starting_point:
            return rec_find(starting_point)
        else:
            return rec_find(self._graph)

    def find_object(self, object_name, graph=None, object_path=[]):
        return self.find_node(object_name, NodeType.OBJECT, starting_point=graph)

    def find_folder(self, folder_name, graph=None, folder_path=[]):
        return self.find_node(folder_name, NodeType.FOLDER, starting_point=graph)


    def find_variable(self, var_name, graph=None, var_path=[]):
        def rec_find(start):
            findings = []
            if start["variables"]=={} and start["objects"]=={}:
                return []
            else:
                for var in start["variables"]:
                    if var.name==var_name:
                        findings.append(var)
                try:
                    return reduce(add, map(rec_find, start["folders"].values()+start["objects"].values())) + findings
                except (TypeError, KeyError):
                    return findings

        if graph:
            return rec_find(graph)
        else:
            return rec_find(self._graph)


    def show(self, starting_point=None):

        def next_trail(old_trail, comp):
            new_trail = ""
            for char in old_trail:
                if char!="|":
                    new_trail += " "
                else:
                    new_trail += char
            return new_trail + comp

        def rec_show(start, trail=""):
            try:
                for folder in start["folders"]:
                    print("%s[]] %s (ns=%d)"%(trail, folder.name, folder.namespace))
                    new_trail = next_trail(trail, " |__")
                    rec_show(start["folders"][folder], new_trail)
            except KeyError:
                pass
            try:
                for obj in start["objects"]:
                    print("%s[+] %s (ns=%d)"%(trail, obj.name, obj.namespace))
                    new_trail = next_trail(trail, " |__")
                    rec_show(start["objects"][obj], new_trail)
            except KeyError:
                pass
            for el in start["variables"]+start["properties"]:
                eltype = "Variable" if el.node_type==NodeType.VARIABLE else "Property"
                print("%s[*] %s: (%s, %s) (ns=%d)"%(trail, eltype, el.name, el.value, el.namespace))

        rec_show(self._graph)

    def add_element():
        pass

    def del_element(self, name, node=None):
        #TODO
        pass

    def _get_subfolders(self, folder_node):
        pass

    def _get_objects(self, folder_name):
        pass


