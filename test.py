import json

with open('config.json', 'r') as file:
    CONFIG = json.loads(file.read())


print(CONFIG['SECRET_KEY'])