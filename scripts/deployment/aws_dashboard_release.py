"""Pinned dashboard-only release. Prepare first; activation keeps a rollback container."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

try:
    import fcntl
except ImportError:
    fcntl = None

REVISION = "41d1374426af6a0c053def6fa7a1e654e7f16065"
ARCHIVE_SHA = "a73f4e079df045219f0f24d9156182579ea8a1085eb02a2f7adf3f3e56b10131"
URL = (
    "https://codeload.github.com/zenithdevelopers7-source/dubai-property-developers/tar.gz/"
    + REVISION
)
HOST = "dubai-property-test.duckdns.org"
WEB = "dubai-property-aws-preview"
API = "dubai-property-aws-api"
VOLUME = "dubai-property-aws-preview-data"
NETWORK = "dubai-property-aws-backend"
CANDIDATE = "dubai-property-candidate-695"
PREVIOUS = "dubai-property-before-695"
IMAGE = "dubai-property-dashboard:release-695-" + REVISION[:12]
ROOT = Path("/root/.dubai-property-release-695")
STATE = ROOT / "state.json"
LOG = ROOT / "operations-private.log"
PORT = 13095
GATEWAY = r"""import {ownerSession,readSessionCookie,privateJson} from './portalAuth';

const prefixes=new Set(['leads','conversations','properties','knowledge','agents','workflows','integrations','analytics']);
/** AWS private read gateway. The service token is used on the server only. */
export async function portalProxy(request:Request,segments:string[],health=false):Promise<Response>{
  try{
    if(!await ownerSession(readSessionCookie(request)))return privateJson({error:'Sign in to your workspace.'},401);
    if(!['GET','HEAD'].includes(request.method))return privateJson({error:'API changes are not enabled in this AWS preview.'},403);
    if(!health&&(!segments.length||!prefixes.has(segments[0])||segments.some(s=>!s||s==='.'||s==='..'||!/^[a-zA-Z0-9_.-]{1,100}$/.test(s))))return privateJson({error:'Route is not available.'},404);
    const target=process.env.DUBAI_PORTAL_API_ORIGIN;
    const token=process.env.DUBAI_PORTAL_API_TOKEN||'';
    if(target!=='http://api:8000'||!/^[a-f0-9]{64}$/.test(token))return privateJson({error:'Workspace connection is unavailable.'},503);
    const query=new URL(request.url).search;if(query.length>4096)return privateJson({error:'Request is too large.'},413);
    const headers={'Accept':'application/json','Authorization':'Bearer '+token};
    const options={headers,redirect:'manual' as const,cache:'no-store' as const,signal:AbortSignal.timeout(10000)};
    if(health){
      // An online badge requires dependencies AND the authenticated read path.
      const [ready,authorized]=await Promise.all([
        fetch(target+'/ready',{...options,method:'GET'}),
        fetch(target+'/api/v1/agents',{...options,method:'GET'})
      ]);
      if(ready.status!==200||authorized.status!==200)return privateJson({error:'Workspace connection is unavailable.'},503);
      if((await ready.json()).status!=='ready')return privateJson({error:'Workspace connection is unavailable.'},503);
      await authorized.body?.cancel();
    }
    const response=await fetch(target+(health?'/health':'/api/v1/'+segments.join('/'))+(health?'':query),{
      ...options,method:request.method
    });
    if(response.status>=300&&response.status<400)return privateJson({error:'Workspace connection redirected unexpectedly.'},502);
    const outgoing=new Headers({'Cache-Control':'no-store, private','X-Content-Type-Options':'nosniff'});
    const contentType=response.headers.get('content-type');if(contentType)outgoing.set('Content-Type',contentType);
    return new Response(request.method==='HEAD'?null:response.body,{status:response.status,headers:outgoing});
  }catch{return privateJson({error:'Workspace connection is unavailable.'},503);}
}
"""


class Stop(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise Stop(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def command(args, timeout=90, output=None, env=None):
    result = subprocess.run(
        args,
        stdout=output or subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        env=env,
    )
    if result.returncode:
        with LOG.open("ab") as log:
            log.write(("Operation: " + args[0] + "\n").encode())
            log.write(result.stderr or b"")
        raise Stop(
            "A server operation failed. Private diagnostic retained; existing storage preserved."
        )
    return result.stdout.decode().strip() if output is None else ""


def docker(*args, **kwargs):
    return command(["docker", *args], **kwargs)


def inspect(name):
    return json.loads(docker("inspect", name))[0]


def exists(name):
    return bool(
        docker("ps", "-a", "--filter", "name=^/" + name + "$", "--format", "{{.ID}}")
    )


def env_map(info):
    return dict(
        row.split("=", 1) for row in info["Config"].get("Env", []) if "=" in row
    )


def fingerprint(info):
    return digest(
        json.dumps(
            {key: info[key] for key in ["Id", "Image", "Config", "HostConfig"]},
            sort_keys=True,
        ).encode()
    )


def others():
    return sorted(
        row
        for row in docker(
            "ps", "--no-trunc", "--format", "{{.ID}} {{.Names}}"
        ).splitlines()
        if row.split()[-1] not in {WEB, CANDIDATE, PREVIOUS}
    )


def config_hashes():
    paths = [
        "/etc/caddy/Caddyfile",
        "/root/.dubai-property-aws-preview/owner.env",
        "/root/.dubai-property-aws-api/gateway.env",
    ]
    return {
        name: digest(Path(name).read_bytes()) for name in paths if Path(name).is_file()
    }


def validate_live(info):
    require(
        info["State"]["Running"],
        "The current website is not running. No replacement attempted.",
    )
    require(
        info["Config"].get("User") in {"nextjs", "1001", "1001:1001"},
        "Unexpected website runtime user.",
    )
    require(
        info["HostConfig"].get("PortBindings")
        == {"3000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3000"}]},
        "Expected localhost-only website port not found.",
    )
    mounts = info.get("Mounts", [])
    require(
        len(mounts) == 1
        and mounts[0].get("Type") == "volume"
        and mounts[0].get("Name") == VOLUME
        and mounts[0].get("Destination") == "/app/portal-data"
        and mounts[0].get("RW"),
        "Website storage differs from the reviewed dedicated volume.",
    )
    require(
        info["HostConfig"].get("NetworkMode") == "bridge"
        and set(info["NetworkSettings"]["Networks"]) == {"bridge", NETWORK},
        "Website networks need review.",
    )
    require(
        json.loads(docker("network", "inspect", NETWORK))[0].get("Internal"),
        "Backend network must remain internal.",
    )
    require(inspect(API)["State"]["Running"], "The existing API must be running first.")
    env = env_map(info)
    require(
        env.get("DUBAI_PORTAL_DATA_DIR") == "/app/portal-data"
        and env.get("DUBAI_PORTAL_API_ORIGIN") == "http://api:8000",
        "Private connection settings need review.",
    )
    require(
        re.fullmatch(r"[a-f0-9]{64}", env.get("DUBAI_PORTAL_API_TOKEN", "")),
        "Private API token is not configured.",
    )
    require(
        bool(env.get("DUBAI_PORTAL_ADMIN_EMAIL"))
        and bool(env.get("DUBAI_PORTAL_PASSWORD_HASH")),
        "Existing owner sign-in configuration must be present.",
    )
    require(
        env.get("DUBAI_PORTAL_PUBLIC_ORIGIN", "https://" + HOST) == "https://" + HOST,
        "A different public origin is configured.",
    )


def volume_path(name):
    p = Path(json.loads(docker("volume", "inspect", name))[0]["Mountpoint"])
    require(
        p == Path("/var/lib/docker/volumes") / name / "_data"
        and p.is_dir()
        and not p.is_symlink(),
        "Unexpected Docker volume location. Preserved for review.",
    )
    return p


def storage_manifest(path):
    result = {}
    for p in sorted(path.rglob("*")):
        require(
            not p.is_symlink(),
            "Unexpected symlink in private storage. Nothing deleted.",
        )
        if p.is_dir() or p.name.endswith(".lock"):
            continue
        require(p.is_file(), "Unexpected file type in private storage.")
        with p.open("rb") as handle:
            h = hashlib.file_digest(handle, "sha256").hexdigest()
        result[p.relative_to(path).as_posix()] = [
            h,
            p.stat().st_mode & 0o777,
            p.stat().st_uid,
            p.stat().st_gid,
        ]
    return result


def backup_volume(path, archive):
    before = storage_manifest(path)
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(
            path,
            arcname="data",
            filter=lambda item: None if item.name.endswith(".lock") else item,
        )
    require(
        storage_manifest(path) == before,
        "Private records changed during the snapshot. Retry preparation.",
    )
    with tarfile.open(archive, "r:gz") as bundle:
        seen = set()
        for item in bundle.getmembers():
            parts = PurePosixPath(item.name).parts
            require(
                parts
                and parts[0] == "data"
                and ".." not in parts
                and not item.name.startswith("/")
                and (item.isfile() or item.isdir()),
                "Unexpected backup member. Original data preserved.",
            )
            if item.isfile():
                seen.add(item.name[5:])
                require(
                    item.name[5:] in before
                    and digest(bundle.extractfile(item).read())
                    == before[item.name[5:]][0],
                    "Private backup verification failed.",
                )
        require(seen == set(before), "Private backup inventory differs.")
    return before


def download_source(context):
    opener = build_opener(ProxyHandler({}))
    with opener.open(URL, timeout=90) as response:
        require(
            response.geturl().startswith("https://codeload.github.com/"),
            "Unexpected source download destination.",
        )
        data = response.read(25 * 1024 * 1024 + 1)
    require(
        len(data) <= 25 * 1024 * 1024 and digest(data) == ARCHIVE_SHA,
        "Pinned source archive checksum mismatch.",
    )
    prefix = "dubai-property-developers-" + REVISION + "/apps/dashboard/"
    count = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as bundle:
        for item in bundle.getmembers():
            if not item.name.startswith(prefix):
                continue
            relative = item.name[len(prefix) :]
            if not relative or item.isdir():
                continue
            if relative == ".env.example":
                continue  # Runtime configuration comes only from the existing private container.
            parts = PurePosixPath(relative).parts
            require(
                item.isfile()
                and not relative.startswith("/")
                and ".." not in parts
                and not any(part in {".git", "node_modules", ".next"} for part in parts)
                and not parts[-1].startswith(".env"),
                "Unexpected source archive member.",
            )
            target = context.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.extractfile(item).read())
            target.chmod(0o644)
            count += 1
    require(count > 100, "Dashboard source inventory is unexpectedly small.")
    require(
        json.loads((context / "package.json").read_text())["dependencies"]["next"]
        == "15.5.29",
        "Expected patched framework version not found.",
    )
    # Preserve the deployed AWS service-token/read-only gateway; do not enable new API writes.
    gateway = GATEWAY.encode("utf-8")
    (context / "src/lib/portalProxy.ts").write_bytes(gateway)
    dockerfile = (context / "Dockerfile").read_text()
    dockerfile = dockerfile.replace(
        "FROM node:22-alpine AS builder",
        "FROM node:22-alpine AS builder\nENV NODE_OPTIONS=--max-old-space-size=640",
    )
    (context / "Dockerfile").write_text(dockerfile)
    return digest(gateway)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def request(port, path, body=None, origin=None, https=False):
    headers = {"Host": HOST}
    if origin is not None:
        headers["Origin"] = origin
    if body is not None:
        headers["Content-Type"] = "application/json"
    url = ("https://" + HOST if https else "http://127.0.0.1:" + str(port)) + path
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(Request(url, data=body, headers=headers), timeout=12)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers


def checks(container, port, https=False):
    for path, codes in [
        ("/", {200}),
        ("/admin/login", {200}),
        ("/login", {200}),
        ("/catalogue", {200}),
        ("/enquire", {200}),
        ("/overview", {307}),
        ("/health", {401}),
        ("/api/v1/agents", {401}),
        ("/api/enquiries/admin", {401}),
        ("/api/agent-portal/workspace", {401}),
    ]:
        status, headers = request(port, path, https=https)
        require(
            status in codes,
            "HTTP protection or page check failed: " + path + " (" + str(status) + ")",
        )
        require(
            headers.get("X-Content-Type-Options") == "nosniff",
            "Website response protections differ.",
        )
        if path == "/overview":
            require(
                headers.get("Location") == "/admin/login",
                "Workspace sign-in redirect differs.",
            )
    for origin, expected in [
        ("https://" + HOST, 400),
        ("https://untrusted.example", 403),
        ("http://" + HOST, 403),
        ("null", 403),
    ]:
        status, _ = request(
            port, "/api/portal-auth/login", b'{"originProbe":true}', origin, https
        )
        require(
            status == expected, "Sign-in origin check failed (" + str(status) + ")."
        )
    probe = """(async()=>{
      for(const [path,status,auth] of [['/ready',200,true],['/api/v1/agents',200,true],['/api/v1/agents',401,false]]){
        const r=await fetch('http://api:8000'+path,{headers:auth?{Authorization:'Bearer '+process.env.DUBAI_PORTAL_API_TOKEN}:{},redirect:'manual',signal:AbortSignal.timeout(10000)});
        if(r.status!==status)throw Error();
        if(path==='/ready'){if((await r.json()).status!=='ready')throw Error();}else await r.body?.cancel();
      }console.log('PASS');
    })().catch(()=>{console.log('FAIL');process.exitCode=1})"""
    require(
        docker("exec", container, "node", "-e", probe).splitlines()[-1:] == ["PASS"],
        "Private API readiness or service-token check failed.",
    )


def wait_checks(container, port, https=False):
    for attempt in range(20):
        try:
            checks(container, port, https)
            return
        except (OSError, Stop):
            if attempt == 19:
                raise
            time.sleep(2)


def create_container(name, image, volume, port, env_file, labels, restart="no"):
    args = [
        "create",
        "--name",
        name,
        "--restart",
        restart,
        "--env-file",
        str(env_file),
        "--network",
        "bridge",
        "--publish",
        "127.0.0.1:" + str(port) + ":3000",
        "--mount",
        "type=volume,source=" + volume + ",target=/app/portal-data",
        "--security-opt",
        "no-new-privileges:true",
        "--cap-drop",
        "ALL",
        "--log-opt",
        "max-size=10m",
        "--log-opt",
        "max-file=3",
    ]
    for key, value in labels.items():
        args.extend(["--label", key + "=" + value])
    docker(*args, image)
    docker("network", "connect", NETWORK, name)


def save(state):
    temp = ROOT / "state.new"
    temp.write_text(json.dumps(state, indent=2))
    temp.replace(STATE)


def unchanged(state, live=True):
    require(
        others() == state["other_containers"]
        and config_hashes() == state["private_config_hashes"],
        "Another service or private configuration changed; pause for review.",
    )
    if live:
        info = inspect(WEB)
        validate_live(info)
        require(
            fingerprint(info) == state["original_fingerprint"],
            "Live website changed after preparation.",
        )


def prepare():
    if STATE.exists():
        state = json.loads(STATE.read_text())
        require(
            state["status"] == "prepared",
            "A previous release state exists. Use --status before proceeding.",
        )
        unchanged(state)
        wait_checks(CANDIDATE, PORT)
        print("PASS: Candidate already prepared. Run --activate to switch the website.")
        return
    require(
        not exists(CANDIDATE) and not exists(PREVIOUS),
        "A candidate or rollback container already exists. Preserved.",
    )
    current = inspect(WEB)
    validate_live(current)
    data_size = sum(
        p.stat().st_size for p in volume_path(VOLUME).rglob("*") if p.is_file()
    )
    require(
        shutil.disk_usage(ROOT).free >= 8 * 1024**3 + 3 * data_size,
        "Insufficient free space for the image, separate data copy and two private backups. Existing data preserved.",
    )
    available = next(
        int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    require(
        available >= 1400 * 1024**2,
        "At least 1.4 GiB available memory is required; current website preserved.",
    )
    checks(WEB, 3000)
    require(
        docker("info", "--format", "{{json .MemoryLimit}}") == "true",
        "Docker memory limits are unavailable. Existing website preserved.",
    )
    state = {
        "status": "building",
        "revision": REVISION,
        "original_id": current["Id"],
        "original_image": current["Image"],
        "original_fingerprint": fingerprint(current),
        "original_labels": current["Config"].get("Labels") or {},
        "other_containers": others(),
        "private_config_hashes": config_hashes(),
    }
    work = ROOT / ("build-" + str(time.time_ns()))
    work.mkdir(mode=0o700)
    context = work / "dashboard"
    context.mkdir(mode=0o755)
    print(
        "Downloading verified source and preserving the AWS read-only gateway.",
        flush=True,
    )
    state["gateway_sha256"] = download_source(context)
    env = env_map(current)
    require(
        all(
            "\n" not in key + value and "\r" not in key + value
            for key, value in env.items()
        ),
        "Multiline runtime configuration requires manual review.",
    )
    env["DUBAI_PORTAL_PUBLIC_ORIGIN"] = "https://" + HOST
    env_file = ROOT / "runtime-private.env"
    env_file.write_text(
        "\n".join(key + "=" + value for key, value in env.items()) + "\n"
    )
    state["runtime_env_sha256"] = digest(env_file.read_bytes())
    print(
        "Building a separate patched dashboard image. The current website stays running.",
        flush=True,
    )
    with (work / "build-private.log").open("wb") as log:
        docker(
            "build",
            "--pull",
            "--memory",
            "1024m",
            "--memory-swap",
            "1024m",
            "--cpu-period",
            "100000",
            "--cpu-quota",
            "100000",
            "--build-arg",
            "NEXT_PUBLIC_API_BASE_URL=/api/v1",
            "--build-arg",
            "NEXT_PUBLIC_PORTAL_PROXY=1",
            "--label",
            "org.opencontainers.image.revision=" + REVISION,
            "--label",
            "dubai.release.gateway=" + state["gateway_sha256"],
            "-t",
            IMAGE,
            str(context),
            timeout=1800,
            output=log,
            # Serialize resource-bounded build steps; never retry an unbounded build.
            env={**os.environ, "DOCKER_BUILDKIT": "0"},
        )
    state["image_id"] = docker("image", "inspect", IMAGE, "--format", "{{.Id}}")
    require(
        docker(
            "run",
            "--rm",
            "--network",
            "none",
            state["image_id"],
            "node",
            "-p",
            "require('next/package.json').version",
        )
        == "15.5.29",
        "Image version verification failed.",
    )
    unchanged(state)
    snapshot = work / "candidate-data-private.tar.gz"
    manifest = backup_volume(volume_path(VOLUME), snapshot)
    state["candidate_volume"] = "dubai-property-check-695-" + str(time.time_ns())
    docker("volume", "create", state["candidate_volume"])
    target = volume_path(state["candidate_volume"])
    command(
        [
            "tar",
            "--extract",
            "--gzip",
            "--file",
            str(snapshot),
            "--directory",
            str(target),
            "--strip-components=1",
            "--same-owner",
            "--same-permissions",
        ]
    )
    # Also restore root directory ownership/mode: strip-components omits the archive root entry.
    source = volume_path(VOLUME).stat()
    os.chown(target, source.st_uid, source.st_gid)
    os.chmod(target, stat.S_IMODE(source.st_mode))
    require(
        storage_manifest(target) == manifest,
        "Candidate storage copy failed verification.",
    )
    create_container(
        CANDIDATE,
        state["image_id"],
        state["candidate_volume"],
        PORT,
        env_file,
        {"dubai.release.stage": "695-candidate", "dubai.release.revision": REVISION},
    )
    try:
        docker("start", CANDIDATE)
        wait_checks(CANDIDATE, PORT)
        unchanged(state)
    except BaseException:
        docker("stop", CANDIDATE)
        raise
    state["candidate_id"] = inspect(CANDIDATE)["Id"]
    state["status"] = "prepared"
    save(state)
    print(
        "PASS: Candidate pages, sign-in origin checks, anonymous protection and private API readiness verified."
    )
    print(
        "PASS: Copied records verified on a separate volume. The live website, accounts and other applications remain unchanged."
    )
    print("NEXT: sudo python3 -B ~/step695_deploy_dubai.py --activate")


def activate(state):
    require(
        state["status"] == "prepared",
        "A prepared candidate is required. No website stopped.",
    )
    unchanged(state)
    require(
        digest((ROOT / "runtime-private.env").read_bytes())
        == state["runtime_env_sha256"],
        "Prepared private runtime settings changed. No website stopped.",
    )
    require(
        inspect(CANDIDATE)["Id"] == state["candidate_id"] and not exists(PREVIOUS),
        "Candidate or rollback identity differs.",
    )
    wait_checks(CANDIDATE, PORT)
    require(
        docker("image", "inspect", state["image_id"], "--format", "{{.Id}}")
        == state["image_id"],
        "Prepared image is missing.",
    )
    print(
        "Saving a consistent private data backup, then switching only the Dubai website.",
        flush=True,
    )
    backup = ROOT / ("portal-before-695-" + str(time.time_ns()) + ".tar.gz")
    renamed = created = False
    try:
        docker("stop", "--time", "30", WEB)
        backup_volume(volume_path(VOLUME), backup)
        unchanged(state, live=False)
        docker("rename", WEB, PREVIOUS)
        renamed = True
        labels = dict(state["original_labels"])
        labels.update(
            {"dubai.release.stage": "695", "dubai.release.revision": REVISION}
        )
        create_container(
            WEB,
            state["image_id"],
            VOLUME,
            3000,
            ROOT / "runtime-private.env",
            labels,
            "unless-stopped",
        )
        created = True
        docker("start", WEB)
        wait_checks(WEB, 3000)
        wait_checks(WEB, 3000, https=True)
        validate_live(inspect(WEB))
        unchanged(state, live=False)
    except BaseException:
        if created or (renamed and exists(WEB)):
            docker(
                "rm", "-f", WEB
            )  # Container only; never remove or restore the data volume.
        if renamed:
            docker("rename", PREVIOUS, WEB)
        docker("start", WEB)
        state["status"] = "rolled-back"
        state["backup"] = str(backup)
        save(state)
        print(
            "Previous website restored. Original volume and private backup preserved.",
            flush=True,
        )
        raise
    state.update(status="active", active_id=inspect(WEB)["Id"], backup=str(backup))
    save(state)
    try:
        docker("stop", CANDIDATE)
    except Stop:
        print(
            "NOTE: The website is active; stopping the private test candidate needs review."
        )
    print(
        "PASS: Patched Next.js 15.5.29 website is live with trusted HTTPS and protected private routes."
    )
    print(
        "PASS: Existing data volume, owner configuration, API service, Caddy and other applications preserved."
    )
    print(
        "Previous website retained stopped for rollback; no volumes or records deleted."
    )
    print(
        "Open https://"
        + HOST
        + "/admin/login with your existing account. Browser sign-in still needs your confirmation."
    )


def rollback(state):
    require(
        state["status"] == "active"
        and inspect(WEB)["Id"] == state["active_id"]
        and inspect(PREVIOUS)["Id"] == state["original_id"],
        "Rollback container identity needs review.",
    )
    unchanged(state, live=False)
    failed = "dubai-property-release-695-retained"
    require(
        not exists(failed),
        "A retained release container already exists. Nothing removed.",
    )
    docker("stop", "--time", "30", WEB)
    docker("rename", WEB, failed)
    docker("rename", PREVIOUS, WEB)
    docker("start", WEB)
    state["status"] = "rolled-back"
    save(state)
    print(
        "PASS: Previous website restarted. Current records retained; no backup restored and no volume deleted."
    )


def main():
    require(
        os.name == "posix" and os.geteuid() == 0 and fcntl is not None,
        "Run this helper in the AWS Ubuntu terminal using sudo.",
    )
    os.umask(0o077)

    def interrupted(signum, frame):
        raise Stop("Terminal interrupted; review release status before continuing.")

    for name in ["SIGINT", "SIGTERM", "SIGHUP"]:
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), interrupted)
    require(not ROOT.is_symlink(), "Unexpected release directory.")
    ROOT.mkdir(mode=0o700, exist_ok=True)
    ROOT.chmod(0o700)
    for name in [
        "release.lock",
        "state.json",
        "runtime-private.env",
        "operations-private.log",
        "state.new",
    ]:
        require(not (ROOT / name).is_symlink(), "Unexpected release control file.")
    mode = sys.argv[1:]
    require(
        mode in [[], ["--prepare"], ["--activate"], ["--status"], ["--rollback"]],
        "Unknown option.",
    )
    with (ROOT / "release.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if mode in [[], ["--prepare"]]:
            prepare()
        else:
            require(STATE.is_file(), "No prepared release state found.")
            state = json.loads(STATE.read_text())
            require(state["revision"] == REVISION, "Release revision differs.")
            if mode == ["--activate"]:
                activate(state)
            elif mode == ["--rollback"]:
                rollback(state)
            else:
                print("Release state:", state["status"])
                print("Source revision:", REVISION)


if __name__ == "__main__":
    try:
        main()
    except Stop as error:
        print("STOP:", error)
        raise SystemExit(1)
    except Exception as error:  # noqa: BLE001 -- Never expose private command/log details at this CLI boundary.
        print(
            "STOP: Release operation needs review ("
            + type(error).__name__
            + "). Private diagnostics and storage preserved."
        )
        raise SystemExit(1)
