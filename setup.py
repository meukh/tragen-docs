from setuptools import setup
from sys import version_info

setup(
        name='tragen',
        version='1.0',
        packages=['tragen',
                  'tragen/ua_data_structure',
                  'tragen/server_tragen',
                  'tragen/client_tragen'
                  ],
        description='OPC UA traffic generation platform'
)


