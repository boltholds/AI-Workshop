import copy
import importlib.util
from pathlib import Path

import pytest


def load_helper():
    spec = importlib.util.spec_from_file_location('rea_rollout', Path('scripts/rea-rollout-config.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture():
    config = {'name': 'server', 'services': {'gateway': {'command': ['serve'], 'environment': {'TOKEN': 'test'}, 'volumes': [{'type': 'volume', 'source': 'state', 'target': '/state'}], 'ports': [{'target': 8765, 'published': '9876', 'host_ip': '127.0.0.1', 'protocol': 'tcp'}], 'networks': {'control': {}}, 'restart': 'unless-stopped'}}, 'volumes': {'state': {'name': 'server_state'}}, 'networks': {'control': {'name': 'server_control'}}}
    image = {'Config': {'Env': ['PATH=/bin'], 'User': '', 'Entrypoint': ['wai']}}
    live = {'Config': {'Env': ['PATH=/bin', 'TOKEN=test'], 'User': '', 'Entrypoint': ['wai'], 'Cmd': ['serve']}, 'Mounts': [{'Type': 'volume', 'Name': 'server_state', 'Destination': '/state', 'RW': True}], 'HostConfig': {'PortBindings': {'8765/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '9876'}]}, 'RestartPolicy': {'Name': 'unless-stopped'}}, 'NetworkSettings': {'Networks': {'server_control': {}}}}
    return config, live, image


def test_rollout_uses_resolved_custom_port():
    config, live, image = fixture()
    assert load_helper().validate_gateway(config, live, image) == 'http://127.0.0.1:9876/mcp'


@pytest.mark.parametrize('mutation', ['env', 'mount', 'port', 'network', 'command'])
def test_rollout_rejects_drift_from_live_gateway(mutation):
    config, live, image = fixture()
    if mutation == 'env': live['Config']['Env'].append('EXTRA=private')
    if mutation == 'mount': live['Mounts'].append({'Type':'bind','Source':'/custom','Destination':'/custom','RW':False})
    if mutation == 'port': live['HostConfig']['PortBindings']['8765/tcp'][0]['HostPort'] = '9999'
    if mutation == 'network': live['NetworkSettings']['Networks']['extra'] = {}
    if mutation == 'command': live['Config']['Cmd'] = ['different']
    with pytest.raises(ValueError): load_helper().validate_gateway(config, live, image)


def test_rollout_rejects_replacing_existing_rea():
    config, live, image = fixture()
    config['services']['gateway']['environment']['AI_WORKSHOP_REA_URL'] = 'http://rea-mcp:8796/mcp'
    live['Config']['Env'].append('AI_WORKSHOP_REA_URL=http://rea-mcp:8796/mcp')
    with pytest.raises(ValueError, match='already'):
        load_helper().validate_gateway(config, live, image)


def test_rollback_snapshot_preserves_secrets_and_original_options():
    config, _, _ = fixture()
    config['services']['gateway']['environment']['TOKEN'] = 'literal$SECRET'
    config['services']['gateway']['build'] = {'context': '/repo'}
    frozen = load_helper().freeze_for_rollback(config, 'sha256:old')
    gateway = frozen['services']['gateway']
    assert gateway['environment']['TOKEN'] == 'literal$$SECRET'
    assert gateway['image'] == 'sha256:old'
    assert 'build' not in gateway
    assert gateway['ports'] == config['services']['gateway']['ports']
    assert gateway['networks'] == config['services']['gateway']['networks']
    assert config['services']['gateway']['environment']['TOKEN'] == 'literal$SECRET'
