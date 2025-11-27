
import os

def load_env():
    if os.path.exists('.env'):
        with open('.env','r') as f:
            for line in f:
                if '=' in line:
                    k,v=line.strip().split('=',1)
                    os.environ[k]=v
