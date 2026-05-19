import asyncio
import base64
import json
import logging
import secrets
import time
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

# Global log store for SSE streaming (setup_id -> list of log lines)
_setup_logs: dict[str, list[dict]] = {}


def _generate_short_id() -> str:
    return secrets.token_hex(8)


async def run_ssh_command(ip: str, user: str, password: str, command: str,
                          port: int = 22, timeout: int = 120,
                          ssh_key: str = "") -> tuple:
    """Run command on remote server via SSH. Returns (stdout, stderr, returncode).
    If ssh_key is provided, writes it to a temp file and uses -i flag instead of sshpass.
    """
    key_file = ""
    try:
        if ssh_key:
            import tempfile, os
            fd, key_file = tempfile.mkstemp(prefix="ssh_key_", suffix=".pem")
            os.write(fd, ssh_key.encode())
            os.close(fd)
            os.chmod(key_file, 0o600)
            ssh_cmd = (
                f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 "
                f"-o ServerAliveInterval=30 -i {key_file} -p {port} {user}@{ip} "
                f"'{command}'"
            )
        else:
            ssh_cmd = (
                f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 "
                f"-o ServerAliveInterval=30 -p {port} {user}@{ip} "
                f"'{command}'"
            )
        proc = await asyncio.create_subprocess_shell(
            ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode(), stderr.decode(), proc.returncode
    except asyncio.TimeoutError:
        logger.error(f"SSH command timed out for {ip}")
        return "", "timeout", -1
    except Exception as ex:
        logger.error(f"SSH error for {ip}: {ex}")
        return "", str(ex), -1
    finally:
        if key_file:
            import os
            try:
                os.unlink(key_file)
            except OSError:
                pass


async def check_server_alive(ip: str, user: str, password: str, port: int = 22, ssh_key: str = "") -> bool:
    stdout, stderr, rc = await run_ssh_command(ip, user, password, "echo ok", port, timeout=15, ssh_key=ssh_key)
    return rc == 0 and "ok" in stdout


def _log(setup_id: str, msg: str, level: str = "info"):
    """Add a log line to the setup log store."""
    if setup_id:
        if setup_id not in _setup_logs:
            _setup_logs[setup_id] = []
        _setup_logs[setup_id].append({"ts": time.time(), "msg": msg, "level": level})
    log_fn = getattr(logger, level, logger.info)
    log_fn(f"[{setup_id}] {msg}")


async def install_xray(ip: str, user: str, password: str, port: int = 22, ssh_key: str = "",
                        setup_id: str = "") -> bool:
    """Install Xray on remote server."""
    _log(setup_id, f"Installing dependencies (curl, unzip)...")

    deps_cmd = (
        "export DEBIAN_FRONTEND=noninteractive && "
        "apt-get update -qq && "
        "apt-get install -y -qq curl unzip > /dev/null 2>&1 && "
        "echo DEPS_OK"
    )
    stdout, stderr, rc = await run_ssh_command(ip, user, password, deps_cmd, port, timeout=120, ssh_key=ssh_key)
    if "DEPS_OK" in stdout:
        _log(setup_id, "Dependencies installed")
    else:
        _log(setup_id, f"Deps warning: {stderr[:200]}", "warning")

    _log(setup_id, "Downloading Xray binary...")
    # Direct binary download (most reliable)
    direct_cmd = (
        "curl -sL https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip "
        "-o /tmp/xray.zip && "
        "unzip -o /tmp/xray.zip -d /usr/local/bin/ xray && "
        "chmod +x /usr/local/bin/xray && "
        "rm -f /tmp/xray.zip && "
        "/usr/local/bin/xray version && "
        "echo XRAY_INSTALL_OK"
    )
    stdout, stderr, rc = await run_ssh_command(ip, user, password, direct_cmd, port, timeout=120, ssh_key=ssh_key)

    if "XRAY_INSTALL_OK" in stdout:
        # Extract version from output
        for line in stdout.split("\n"):
            if "Xray" in line and "." in line:
                _log(setup_id, f"Xray installed: {line.strip()}")
                break
        return True

    _log(setup_id, "Direct download failed, trying install script...", "warning")
    # Fallback to install script
    script_cmd = (
        "bash -c 'curl -Ls https://github.com/XTLS/Xray-install/raw/main/install-release.sh | bash' && "
        "echo XRAY_INSTALL_OK"
    )
    stdout, stderr, rc = await run_ssh_command(ip, user, password, script_cmd, port, timeout=300, ssh_key=ssh_key)

    if "XRAY_INSTALL_OK" in stdout:
        _log(setup_id, "Xray installed via script")
        return True

    _log(setup_id, f"Xray install failed: {stderr[:300]}", "error")
    return False


async def generate_xray_keys(ip: str, user: str, password: str, port: int = 22, ssh_key: str = "",
                              setup_id: str = "") -> dict:
    """Generate UUID and x25519 keys on remote server."""
    _log(setup_id, "Generating UUID...")
    stdout_uuid, _, rc1 = await run_ssh_command(
        ip, user, password, "/usr/local/bin/xray uuid", port, timeout=15, ssh_key=ssh_key
    )
    _log(setup_id, "Generating x25519 keys...")
    stdout_keys, _, rc2 = await run_ssh_command(
        ip, user, password, "/usr/local/bin/xray x25519", port, timeout=15, ssh_key=ssh_key
    )

    if rc1 != 0 or rc2 != 0:
        _log(setup_id, f"Key generation commands failed: rc={rc1},{rc2}", "error")
        return {}

    uuid_val = stdout_uuid.strip()
    private_key = ""
    public_key = ""
    for line in stdout_keys.strip().split("\n"):
        parts = line.split()
        if not parts:
            continue
        low = line.lower()
        # PrivateKey: xxx
        if "privatekey" in low.replace(" ", ""):
            private_key = parts[-1]
        # Password (PublicKey): xxx  or  PublicKey: xxx
        elif "publickey" in low.replace(" ", ""):
            public_key = parts[-1]

    if uuid_val and private_key and public_key:
        _log(setup_id, f"Keys generated (pub={public_key[:12]}...)")
        return {
            "uuid": uuid_val,
            "private_key": private_key,
            "public_key": public_key,
            "short_id": _generate_short_id(),
        }

    _log(setup_id, f"Key parsing failed. Output: {stdout_keys[:200]}", "error")
    return {}


def build_xray_config(uuid_val: str, private_key: str, short_id: str,
                       sni: str = "www.google.com", xray_port: int = 443) -> str:
    """Build Xray VLESS Reality config JSON with stats API enabled."""
    config = {
        "log": {"loglevel": "warning"},
        "stats": {},
        "api": {
            "tag": "api",
            "services": ["StatsService"]
        },
        "policy": {
            "levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True}},
            "system": {"statsInboundUplink": True, "statsInboundDownlink": True,
                       "statsOutboundUplink": True, "statsOutboundDownlink": True}
        },
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": 10085,
                "protocol": "dokodemo-door",
                "settings": {"address": "127.0.0.1"},
                "tag": "api"
            },
            {
                "listen": "0.0.0.0",
                "port": xray_port,
                "protocol": "vless",
                "tag": "vless-in",
                "settings": {
                    "clients": [{
                        "id": uuid_val,
                        "flow": "xtls-rprx-vision",
                        "email": f"user-{uuid_val[:8]}"
                    }],
                    "decryption": "none"
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": f"{sni}:443",
                        "xver": 0,
                        "serverNames": [sni, f"www.{sni}" if not sni.startswith("www.") else sni],
                        "privateKey": private_key,
                        "shortIds": [short_id, ""]
                    }
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"]
                }
            }
        ],
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"}
        ],
        "routing": {
            "rules": [{
                "inboundTag": ["api"],
                "outboundTag": "api",
                "type": "field"
            }]
        }
    }
    return json.dumps(config, indent=2)


async def deploy_xray_config(ip: str, user: str, password: str,
                              uuid_val: str, private_key: str, short_id: str,
                              sni: str = "www.google.com", xray_port: int = 443,
                              ssh_port: int = 22, ssh_key: str = "",
                              setup_id: str = "") -> bool:
    """Deploy Xray config and start service on remote server."""
    _log(setup_id, "Building Xray config...")
    config_json = build_xray_config(uuid_val, private_key, short_id, sni, xray_port)
    b64 = base64.b64encode(config_json.encode()).decode()

    _log(setup_id, "Creating systemd service...")
    service_unit = (
        "[Unit]\nDescription=Xray Service\nAfter=network.target\n\n"
        "[Service]\nExecStart=/usr/local/bin/xray run -config /usr/local/etc/xray/config.json\n"
        "Restart=on-failure\nRestartSec=3\nLimitNOFILE=65535\n\n"
        "[Install]\nWantedBy=multi-user.target"
    )
    svc_b64 = base64.b64encode(service_unit.encode()).decode()

    cmd = (
        f"mkdir -p /usr/local/etc/xray && "
        f"echo {b64} | base64 -d > /usr/local/etc/xray/config.json && "
        f"echo {svc_b64} | base64 -d > /etc/systemd/system/xray.service && "
        f"systemctl daemon-reload && "
        f"systemctl enable xray && "
        f"systemctl restart xray && "
        f"sleep 2 && "
        f"systemctl is-active xray && "
        f"echo CONFIG_DEPLOYED_OK"
    )

    _log(setup_id, "Deploying config and starting Xray...")
    stdout, stderr, rc = await run_ssh_command(ip, user, password, cmd, ssh_port, timeout=60, ssh_key=ssh_key)

    if "CONFIG_DEPLOYED_OK" in stdout:
        _log(setup_id, "Xray config deployed and service running")
        return True

    _log(setup_id, f"Config deploy failed: {stderr[:200]}", "error")
    return False


async def setup_server_full(ip: str, user: str, password: str, ssh_port: int = 22,
                             sni: str = "www.google.com", xray_port: int = 443,
                             ssh_key: str = "", setup_id: str = "") -> dict:
    """Full auto-setup: install Xray, generate keys, deploy config."""
    _log(setup_id, f"Starting setup for {ip}:{ssh_port}")

    # Check alive
    _log(setup_id, "Checking SSH connectivity...")
    if not await check_server_alive(ip, user, password, ssh_port, ssh_key=ssh_key):
        _log(setup_id, "SSH connection failed", "error")
        return {"error": "Server unreachable via SSH"}
    _log(setup_id, "SSH connection OK")

    # Install Xray
    if not await install_xray(ip, user, password, ssh_port, ssh_key=ssh_key, setup_id=setup_id):
        return {"error": "Xray installation failed"}

    # Generate keys
    keys = await generate_xray_keys(ip, user, password, ssh_port, ssh_key=ssh_key, setup_id=setup_id)
    if not keys:
        return {"error": "Key generation failed"}

    # Deploy config
    ok = await deploy_xray_config(
        ip, user, password,
        keys["uuid"], keys["private_key"], keys["short_id"],
        sni, xray_port, ssh_port, ssh_key=ssh_key, setup_id=setup_id
    )
    if not ok:
        return {"error": "Config deployment failed"}

    # Optimize network
    _log(setup_id, "Optimizing network (BBR, buffers)...")
    await optimize_network(ip, user, password, ssh_port, ssh_key=ssh_key)
    _log(setup_id, "Network optimized")

    _log(setup_id, "Setup complete!", "success")
    return {
        "uuid": keys["uuid"],
        "private_key": keys["private_key"],
        "public_key": keys["public_key"],
        "short_id": keys["short_id"],
        "port": xray_port,
        "sni": sni,
    }


async def get_setup_logs(setup_id: str, after: float = 0) -> AsyncGenerator[dict, None]:
    """Yield new log entries for a setup_id."""
    logs = _setup_logs.get(setup_id, [])
    for entry in logs:
        if entry["ts"] > after:
            yield entry


def cleanup_setup_logs(setup_id: str):
    """Remove logs for a completed setup."""
    _setup_logs.pop(setup_id, None)


async def optimize_network(ip: str, user: str, password: str, ssh_port: int = 22, ssh_key: str = ""):
    """Apply network optimizations for better VPN throughput."""
    sysctl_cmd = (
        "cat >> /etc/sysctl.conf << 'SYSCTL_EOF'\n"
        "net.core.default_qdisc=fq\n"
        "net.ipv4.tcp_congestion_control=bbr\n"
        "net.core.rmem_max=16777216\n"
        "net.core.wmem_max=16777216\n"
        "net.ipv4.tcp_rmem=4096 87380 16777216\n"
        "net.ipv4.tcp_wmem=4096 65536 16777216\n"
        "net.ipv4.tcp_fastopen=3\n"
        "SYSCTL_EOF\n"
        "sysctl -p 2>/dev/null; echo NET_OPT_OK"
    )
    stdout, _, _ = await run_ssh_command(ip, user, password, sysctl_cmd, ssh_port, timeout=30, ssh_key=ssh_key)
    if "NET_OPT_OK" in stdout:
        logger.info(f"Network optimized on {ip}")


async def setup_relay(relay_ip: str, relay_user: str, relay_pass: str,
                       target_ip: str, target_port: int = 443,
                       relay_port: int = 443, ssh_port: int = 22,
                       ssh_key: str = "") -> bool:
    """Set up iptables relay (for whitelist servers)."""
    cmd = (
        f"sysctl -w net.ipv4.ip_forward=1 && "
        f"echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf && "
        f"iptables -t nat -A PREROUTING -p tcp --dport {relay_port} -j DNAT --to-destination {target_ip}:{target_port} && "
        f"iptables -t nat -A POSTROUTING -j MASQUERADE && "
        f"apt-get install -y -qq iptables-persistent > /dev/null 2>&1; "
        f"netfilter-persistent save 2>/dev/null; "
        f"echo RELAY_SETUP_OK"
    )
    stdout, stderr, rc = await run_ssh_command(relay_ip, relay_user, relay_pass, cmd, ssh_port, timeout=120, ssh_key=ssh_key)
    if "RELAY_SETUP_OK" in stdout:
        logger.info(f"Relay {relay_ip} -> {target_ip}:{target_port} configured")
        return True
    logger.error(f"Relay setup failed: {stdout} | {stderr}")
    return False


async def query_xray_stats(ip: str, user: str, password: str, ssh_port: int = 22,
                            ssh_key: str = "", email: str = "") -> dict:
    """Query Xray stats API for traffic data via SSH.
    Returns {"uplink": bytes, "downlink": bytes} or empty dict on failure.
    """
    if email:
        cmd = (
            f"/usr/local/bin/xray api statsquery --server=127.0.0.1:10085 "
            f"-pattern 'user>>>{email}>>>traffic' 2>/dev/null && echo STATS_OK"
        )
    else:
        cmd = (
            "/usr/local/bin/xray api statsquery --server=127.0.0.1:10085 "
            "2>/dev/null && echo STATS_OK"
        )
    stdout, stderr, rc = await run_ssh_command(ip, user, password, cmd, ssh_port, timeout=15, ssh_key=ssh_key)
    if "STATS_OK" not in stdout:
        return {}

    result = {"uplink": 0, "downlink": 0}
    try:
        for line in stdout.split("\n"):
            line = line.strip()
            if "uplink" in line.lower() and "value" not in line.lower():
                continue
            if '"value"' in line or "'value'" in line:
                pass
        import re
        blocks = re.findall(r'"name":\s*"([^"]+)".*?"value":\s*"?(\d+)"?', stdout, re.DOTALL)
        for name, value in blocks:
            if "uplink" in name:
                result["uplink"] += int(value)
            elif "downlink" in name:
                result["downlink"] += int(value)
    except Exception as e:
        logger.warning(f"Failed to parse Xray stats: {e}")
    return result


def build_vless_link(ip: str, port: int, uuid_val: str, public_key: str,
                      short_id: str, sni: str, remark: str) -> str:
    """Build VLESS connection string."""
    return (
        f"vless://{uuid_val}@{ip}:{port}"
        f"?type=tcp&security=reality&pbk={public_key}&fp=chrome"
        f"&sni={sni}&sid={short_id}&spx=%2F&flow=xtls-rprx-vision"
        f"#{remark}"
    )
