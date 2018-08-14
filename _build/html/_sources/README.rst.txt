.. Tragen documentation master file, created by
   sphinx-quickstart on Thu Jul 26 13:36:43 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

OPC-UA Tragen Documentation!
==================================

Python based OPC-UA traffic generator relying on the FreeOpcUa implementation of the protocol.
http://freeopcua.github.io/, https://github.com/FreeOpcUa/python-opcua

New OPC-UA client and server classes inheriting from the FreeOpcUa implementation with added functionnalities to make for an easier automatic traffic generation.
The main class 'Tragen' allows for the creation of a context of one opc-ua server and multiple clients connected to it, and orchestrates communication between them simulating real physical processes and communication btween Operation Technology devices.


Content:


.. toctree::
   :maxdepth: 2

   tragen
   tragen.server_tragen
   tragen.client_tragen
   tragen.ua_data_structure


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
