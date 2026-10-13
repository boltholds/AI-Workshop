#!/usr/bin/env python3
"""Verify that a resolved Compose snapshot describes the live gateway exactly."""
import json
from pathlib import Path
import sys


def validate_gateway(config, live, image):
    service = config['services']['gateway']
    actual = live['Config']
    image_config = image['Config']
    def env(items): return dict(item.split('=', 1) for item in items or [])
    actual_env = env(actual.get('Env'))
    if actual_env.get('AI_WORKSHOP_REA_URL'):
        raise ValueError('REA is already configured; this helper only performs first installation')
    expected_env = env(image_config.get('Env')) | {k: str(v) for k, v in service.get('environment', {}).items()}
    if actual_env != expected_env:
        raise ValueError('Live gateway environment differs from current Compose configuration')
    for field, key in [('Cmd', 'command'), ('Entrypoint', 'entrypoint'), ('User', 'user')]:
        expected = service.get(key)
        # Compose null means inherit; an explicit empty command/entrypoint
        # clears the image default instead. Explicit entrypoints suppress CMD.
        if expected is None or (field == 'User' and expected == ''):
            expected = image_config.get(field)
            if field == 'Cmd' and service.get('entrypoint') is not None:
                expected = None
        observed = actual.get(field)
        if field == 'User':
            expected, observed = expected or '', observed or ''
        else:
            expected, observed = expected or [], observed or []
        if observed != expected:
            raise ValueError(
                f'Live gateway {field} differs from current Compose configuration: '
                f'live={observed!r}, expected={expected!r}; '
                f'compose={service.get(key)!r}, image={image_config.get(field)!r}'
            )
    expected_mounts = {}
    for volume in service.get('volumes', []):
        kind = volume['type']
        if kind not in {'bind', 'volume'}:
            raise ValueError('Unsupported gateway mount type')
        source = str(Path(volume['source']).resolve()) if kind == 'bind' else config['volumes'][volume['source']]['name']
        expected_mounts[volume['target']] = (kind, source, not volume.get('read_only', False))
    actual_mounts = {v['Destination']: (v['Type'], str(Path(v['Source']).resolve()) if v['Type']=='bind' else v.get('Name'), v['RW']) for v in live['Mounts']}
    if expected_mounts != actual_mounts:
        raise ValueError('Live gateway mounts differ from current Compose configuration')
    expected_ports = {}
    endpoint = None
    for port in service.get('ports', []):
        target = str(port['target']) + '/' + port.get('protocol', 'tcp')
        binding = {'HostIp': port.get('host_ip', '0.0.0.0'), 'HostPort': str(port['published'])}
        expected_ports.setdefault(target, []).append(binding)
        if target == '8765/tcp' and binding['HostIp'] == '127.0.0.1':
            endpoint = 'http://127.0.0.1:' + binding['HostPort'] + '/mcp'
    if expected_ports != (live['HostConfig'].get('PortBindings') or {}):
        raise ValueError('Live gateway ports differ from current Compose configuration')
    expected_networks = {config['networks'][key]['name'] for key in service.get('networks', {})}
    if expected_networks != set(live['NetworkSettings']['Networks']):
        raise ValueError('Live gateway networks differ from current Compose configuration')
    if service.get('restart', 'no') != live['HostConfig']['RestartPolicy']['Name']:
        raise ValueError('Live gateway restart policy differs from current Compose configuration')
    # Refuse unmodelled hardening/runtime overrides rather than discard them.
    for field in ['CapAdd', 'CapDrop', 'SecurityOpt', 'Devices', 'GroupAdd', 'ExtraHosts', 'Dns', 'DnsSearch', 'DnsOptions', 'Tmpfs', 'Ulimits', 'NanoCpus', 'Memory', 'MemorySwap', 'CpuShares', 'CpuQuota', 'CpuPeriod', 'PidsLimit', 'Sysctls', 'DeviceRequests']:
        if live['HostConfig'].get(field):
            raise ValueError('Custom gateway runtime options require an explicit rollout: ' + field)
    for field in ['Privileged', 'ReadonlyRootfs']:
        if live['HostConfig'].get(field):
            raise ValueError('Custom gateway runtime options require an explicit rollout: ' + field)
    if endpoint is None:
        raise ValueError('A published loopback gateway endpoint is required')
    return endpoint


def freeze_for_rollback(config, old_image):
    from copy import deepcopy
    result = deepcopy(config)
    result['services']['gateway']['image'] = old_image
    result['services']['gateway'].pop('build', None)
    def escape(value):
        if isinstance(value, str): return value.replace('$', '$$')
        if isinstance(value, list): return [escape(v) for v in value]
        if isinstance(value, dict): return {k: escape(v) for k, v in value.items()}
        return value
    return escape(result)


if __name__ == '__main__':
    config = json.loads(Path(sys.argv[1]).read_text())
    live = json.loads(Path(sys.argv[2]).read_text())[0]
    image = json.loads(Path(sys.argv[3]).read_text())[0]
    try:
        print(validate_gateway(config, live, image))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    Path(sys.argv[4]).write_text(json.dumps(freeze_for_rollback(config, live['Image']), indent=2) + '\n')
