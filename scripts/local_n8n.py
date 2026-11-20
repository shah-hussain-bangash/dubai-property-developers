"""Separate local n8n service. No portal credentials, source events or workflows."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

REPOSITORY = 'docker.n8n.io/n8nio/n8n'
TAG = REPOSITORY + ':2.45.5'
NAME = 'dpd-n8n-local'
VOLUME = NAME + '-data'
OWNER = 'com.dpd.local-n8n.root'
CONFIG = 'com.dpd.local-n8n.config'


class SetupError(Exception):
    pass


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(root):
    return hashlib.sha256(str(root.resolve()).casefold().encode()).hexdigest()


def safe_path(root, name):
    p = root / name
    if not p.resolve().is_relative_to(root):
        raise SetupError('Setup path is outside the project.')
    for part in (p, *p.parents):
        if part == root.parent:
            break
        if part.is_symlink() or part.is_junction():
            raise SetupError('Linked setup paths are not supported.')
    return p


def verify_project(root):
    repair = safe_path(root, 'database/project_knowledge/reports/step649_fix_local_n8n_results.json')
    report = repair if repair.exists() else safe_path(root, 'database/project_knowledge/reports/step649_local_n8n_results.json')
    data = json.loads(report.read_text(encoding='utf-8'))
    expected = 'local_n8n_fix_installed' if repair.exists() else 'local_n8n_sources_installed'
    if data.get('acceptance_status') != expected:
        raise SetupError('Install Step649 sources before starting n8n.')
    for name, value in {**data['protected_sha256'], **data['file_sha256']}.items():
        if digest(safe_path(root, name)) != value:
            raise SetupError('A protected project source changed. No n8n service was started.')
    return data


def run(args, env=None):
    if env is None:
        env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'LOCALAPPDATA', 'APPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'USERPROFILE', 'COMSPEC', 'PATHEXT'}}
    result = subprocess.run(args, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        stage = docker_stage(args)
        reason = docker_failure(result.stderr + result.stdout)
        raise SetupError(stage + ' failed [' + reason + ']. No private command output was displayed. Existing property services were not restarted.')
    return result.stdout.strip()


def docker_stage(args):
    tail = args[1:]
    if tail[:2] == ['context', 'inspect']: return 'Docker context inspection'
    if tail[:1] == ['info']: return 'Docker engine access'
    if tail[:2] == ['compose', 'version']: return 'Docker Compose plugin check'
    if tail[:1] == ['compose'] and 'config' in tail: return 'n8n Compose validation'
    if tail[:1] == ['compose'] and 'up' in tail: return 'n8n container startup'
    if tail[:1] == ['pull']: return 'Official n8n image download'
    if tail[:2] == ['volume', 'ls']: return 'n8n volume lookup'
    if tail[:2] == ['volume', 'inspect']: return 'n8n volume ownership check'
    if tail[:2] == ['image', 'inspect']: return 'Official n8n image digest check'
    if tail[:1] == ['inspect']: return 'Existing n8n container settings check'
    if tail[:1] == ['ps']: return 'n8n container lookup'
    return 'Docker setup check'


def docker_failure(text):
    text = text.lower()
    if any(v in text for v in ['access is denied', 'permission denied', 'access denied']): return 'access-denied'
    if any(v in text for v in ['template parsing', 'template:', "can't evaluate field"]): return 'context-format-error'
    if any(v in text for v in ['error during connect', 'failed to connect', 'connection refused', 'cannot find the file']): return 'engine-unavailable'
    if any(v in text for v in ['no matching manifest', 'manifest unknown', 'manifest not found']): return 'image-not-available'
    if any(v in text for v in ['no such host', 'tls handshake timeout', 'network is unreachable']): return 'network-unavailable'
    if any(v in text for v in ['not a docker command', 'unknown command', 'plugin is not valid']): return 'compose-plugin-unavailable'
    return 'command-failed-details-withheld'


def local_engine(docker):
    endpoint = run([docker, 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'])
    if endpoint not in {'npipe:////./pipe/docker_engine', 'npipe:////./pipe/dockerDesktopLinuxEngine'}:
        raise SetupError('This launcher requires the local Docker Desktop Linux engine; remote Docker contexts are refused.')
    if run([docker, 'info', '--format', '{{.OSType}}']) != 'linux':
        raise SetupError('Switch Docker Desktop to Linux containers first.')
    run([docker, 'compose', 'version'])


def pinned_image(docker, pin):
    pattern = re.escape(REPOSITORY) + r'@sha256:[a-f0-9]{64}'
    if pin.exists():
        data = json.loads(pin.read_text(encoding='utf-8'))
        if data.get('tag') != TAG or not re.fullmatch(pattern, str(data.get('image', ''))):
            raise SetupError('The saved n8n image pin changed. It was not replaced.')
        image = data['image']
        # Pull the same immutable digest if it is no longer cached locally.
        run([docker, 'pull', image])
        return image
    print('Downloading the official pinned n8n release. The property system stays running.', flush=True)
    run([docker, 'pull', TAG])
    refs = json.loads(run([docker, 'image', 'inspect', TAG, '--format', '{{json .RepoDigests}}']))
    image = next((v for v in refs if isinstance(v, str) and re.fullmatch(pattern, v)), None)
    if not image:
        raise SetupError('The official image digest could not be confirmed. No service was started.')
    pin.parent.mkdir(parents=True, exist_ok=True)
    with pin.open('x', encoding='utf-8') as handle:
        json.dump({'tag': TAG, 'image': image}, handle, indent=2)
    return image


def existing_container(docker, root_id, config_id, image=None):
    container = run([docker, 'ps', '-a', '--filter', 'name=^/' + NAME + '$', '--format', '{{.ID}}'])
    if not container:
        return None
    if not re.fullmatch('[a-f0-9]{12,64}', container):
        raise SetupError('An unexpected n8n container selection was refused.')
    checks = {
        '{{index .Config.Labels "' + OWNER + '"}}': root_id,
        '{{index .Config.Labels "' + CONFIG + '"}}': config_id,
        '{{.HostConfig.Privileged}}': 'false',
        '{{range .Mounts}}{{if eq .Destination "/home/node/.n8n"}}{{.Type}}|{{.Name}}{{end}}{{end}}': 'volume|' + VOLUME,
    }
    if image:
        checks['{{.Config.Image}}'] = image
    for template, expected in checks.items():
        if run([docker, 'inspect', '--format', template, container]) != expected:
            raise SetupError('An existing n8n container has different ownership or settings. It was not changed.')
    ports = json.loads(run([docker, 'inspect', '--format', '{{json .HostConfig.PortBindings}}', container]))
    if ports != {'5678/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '5678'}]}:
        raise SetupError('Existing n8n network exposure differs. It was not changed.')
    if run([docker, 'inspect', '--format', '{{.State.Running}}', container]) != 'true':
        raise SetupError('Your existing n8n service is stopped. It may contain active workflows. Start it deliberately in Docker Desktop when ready; this launcher will not resume it automatically.')
    return container


def check_volume(docker, root_id):
    found = run([docker, 'volume', 'ls', '--filter', 'name=^' + VOLUME + '$', '--format', '{{.Name}}'])
    if found and (found != VOLUME or run([docker, 'volume', 'inspect', '--format', '{{index .Labels "' + OWNER + '"}}', VOLUME]) != root_id):
        raise SetupError('An existing n8n data volume has different ownership. It was not changed.')
    return bool(found)


def port_free():
    try:
        with socket.socket() as server:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                server.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            server.bind(('127.0.0.1', 5678))
    except OSError:
        raise SetupError('Port5678 is already in use. Your existing service was not stopped or replaced.') from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def ready():
    opener = build_opener(ProxyHandler({}), NoRedirect())
    for attempt in range(45):
        try:
            with opener.open(Request('http://127.0.0.1:5678/healthz/readiness'), timeout=3) as response:
                if response.status == 200:
                    return
        except (HTTPError, URLError, TimeoutError, OSError):
            pass
        time.sleep(2)
    raise SetupError('n8n readiness was not confirmed. Its data volume was preserved. Check the dpd-n8n-local container in Docker Desktop; no property service was restarted.')


def main(root):
    root = root.resolve(strict=True)
    data = verify_project(root)
    docker = shutil.which('docker.exe') or shutil.which('docker')
    if not docker:
        raise SetupError('Docker Desktop is not available. The prepared sources are preserved.')
    local_engine(docker)
    root_id = identity(root)
    compose = safe_path(root, 'infra/local-n8n/compose.json')
    config_id = digest(compose)
    pin = safe_path(root, 'database/project_knowledge/reports/step649_n8n_image_pin.json')
    # Refuse collisions and stopped instances before pulling any image or starting anything.
    container = existing_container(docker, root_id, config_id)
    volume_exists = check_volume(docker, root_id)
    if not container and volume_exists:
        raise SetupError('An existing n8n data volume was found without its managed container. Review recovery manually; saved active workflows will not be resumed automatically.')
    if container and not pin.exists():
        raise SetupError('The existing n8n image pin is missing. It was not recreated.')
    if not container:
        port_free()
    image = pinned_image(docker, pin)
    if container:
        existing_container(docker, root_id, config_id, image)
        print('Existing local n8n verified. No container was recreated or resumed.', flush=True)
    else:
        env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'LOCALAPPDATA', 'APPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'USERPROFILE', 'COMSPEC', 'PATHEXT'}}
        env.update(DPD_N8N_IMAGE=image, DPD_N8N_ROOT=root_id, DPD_N8N_CONFIG=config_id)
        args = [docker, 'compose', '--project-name', NAME, '--project-directory', str(compose.parent), '--env-file', str(compose.parent / 'empty.env'), '-f', str(compose)]
        run(args + ['config', '--quiet'], env)
        print('Starting only the separate local n8n service. No property containers are refreshed.', flush=True)
        run(args + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'n8n'], env)
        container = existing_container(docker, root_id, config_id, image)
        if not container:
            raise SetupError('The separate n8n container was not found after startup.')
    ready()
    verify_project(root)
    report = safe_path(root, 'database/project_knowledge/reports/step649_local_n8n_start_results.json')
    if not report.exists():
        with report.open('x', encoding='utf-8') as handle:
            json.dump({'step': 649, 'n8n_ready': True, 'image': image, 'loopback_port': 5678, 'property_sources_preserved': True, 'property_services_restart_requested': False, 'workflows_created': 0, 'provider_accounts_connected': 0, 'messages_sent': 0, 'credentials_recorded': False}, handle, indent=2)
    print('PASS: Local n8n is ready at http://localhost:5678. Finish its owner-account setup privately in the browser.')
    print('EspoCRM, Gmail and WhatsApp are not connected. No workflow or provider credential was created by this setup.')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise SetupError('Provide the project directory.')
        main(Path(sys.argv[1]))
    except (KeyboardInterrupt, EOFError):
        print('Cancelled. Existing data volumes and property services are preserved.')
        sys.exit(1)
    except SetupError as error:
        print(str(error))
        sys.exit(1)
    except Exception:
        print('Local n8n setup needs attention. No private configuration or command output was displayed. Existing volumes were not deleted.')
        sys.exit(1)
