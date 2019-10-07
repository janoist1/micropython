import ujson

CONFIG_FILE = 'config.json'

def read():
    config = {}

    try:
        with open(CONFIG_FILE) as f:
            content = ''.join(f.readlines())
            config = ujson.loads(content)
    except OSError:
        print('Error reading config', CONFIG_FILE)

    return config


def write(config):
    with open(CONFIG_FILE, "w") as f:
        content = ujson.dumps(config)
        f.write(content)
