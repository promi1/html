import asyncio
import base64
import json
import logging
import secrets

logger = logging.getLogger(__name__)


def _generate_short_id() -> str:
    return secrets.token_hex(8)


async def run_ssh_command(ip: str, user: str, password: str, command: str,
                          port: int = 22, timeout: int = 120) -> tuple:
    """Run command on remote server via SSH. Returns (stdout, stderr, returncode)."""
    ssh_cmd = (
        f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 "
        f"-o ServerAliveInterval=30 -p {port} {user}@{ip} "
        f"'{command}'"
    )
    try:
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


async def check_server_alive(ip: str, user: str, password: str, port: int = 22) -> bool:
    stdout, stderr, rc = await run_ssh_command(ip, user, password, "echo ok", port, timeout=15)
    return rc == 0 and "ok" in stdout


async def install_xray(ip: str, user: str, password: str, port: int = 22) -> bool:
    """Install Xray on remote server."""
    logger.info(f"Installing Xray on {ip}...")

    install_cmd = (
        "export DEBIAN_FRONTEND=noninteractive && "
        "apt-get update -qq && "
        "apt-get install -y -qq curl unzip > /dev/null 2>&1 && "
        "bash -c 'bash <(curl -Ls https://raw.githubusercontent.com/mhsanaei/3x-ui/master/install.sh) --install-xray'"
        " 2>/dev/null || "
        "bash -c 'curl -Ls https://github.com/XTLS/Xray-install/raw/main/install-release.sh | bash' "
        "&& echo XRAY_INSTALL_OK"
    )

    stdout, stderr, rc = await run_ssh_command(ip, user, password, install_cmd, port, timeout=300)

    if "XRAY_INSTALL_OK" not in stdout:
        # Try alternative install
        alt_cmd = (
            "curl -Ls https://github.com/XTLS/Xray-install/raw/main/install-release.sh | bash && "
            "echo XRAY_INSTALL_OK"
        )
        stdout, stderr, rc = await run_ssh_command(ip, user, password, alt_cmd, port, timeout=300)

    if "XRAY_INSTALL_OK" in stdout:
        logger.info(f"Xray installed on {ip}")
        return True

    logger.error(f"Xray install failed on {ip}: {stderr}")
    return False


async def generate_xray_keys(ip: str, user: str, password: str, port: int = 22) -> dict:
    """Generate UUID and x25519 keys on remote server."""
    # Step 1: get UUID
    stdout_uuid, _, rc1 = await run_ssh_command(
        ip, user, password, "/usr/local/bin/xray uuid", port, timeout=15
    )
    # Step 2: get x25519 keys
    stdout_keys, _, rc2 = await run_ssh_command(
        ip, user, password, "/usr/local/bin/xray x25519", port, timeout=15
    )

    if rc1 != 0 or rc2 != 0:
        logger.error(f"Key generation commands failed on {ip}: rc={rc1},{rc2}")
        return {}

    uuid_val = stdout_uuid.strip()
    private_key = ""
    public_key = ""
    for line in stdout_keys.strip().split("\n"):
        parts = line.split()
        if not parts:
            continue
        # PrivateKey: xxx  or  Private key: xxx
        if "rivate" in line.lower():
            private_key = parts[-1]
        # PublicKey: xxx  or  Public key: xxx  or  Password (PublicKey): xxx
        elif "ublic" in line.lower():
            public_key = parts[-1]

    if uuid_val and private_key and public_key:
        return {
            "uuid": uuid_val,
            "private_key": private_key,
            "public_key": public_key,
            "short_id": _generate_short_id(),
        }

    logger.error(f"Key generation failed on {ip}: uuid={stdout_uuid} keys={stdout_keys}")
    return {}


def build_xray_config(uuid_val: str, private_key: str, short_id: str,
                       sni: str = "www.google.com", xray_port: int = 443) -> str:
    """Build Xray VLESS Reality config JSON."""
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "listen": "0.0.0.0",
            "port": xray_port,
            "protocol": "vless",
            "settings": {
                "clients": [{
                    "id": uuid_val,
                    "flow": "xtls-rprx-vision"
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
        }],
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"}
        ]
    }
    return json.dumps(config, indent=2)


async def deploy_xray_config(ip: str, user: str, password: str,
                              uuid_val: str, private_key: str, short_id: str,
                              sni: str = "www.google.com", xray_port: int = 443,
                              ssh_port: int = 22) -> bool:
    """Deploy Xray config and start service on remote server."""
    config_json = build_xray_config(uuid_val, private_key, short_id, sni, xray_port)
    b64 = base64.b64encode(config_json.encode()).decode()

    cmd = (
        f"mkdir -p /usr/local/etc/xray && "
        f"echo {b64} | base64 -d > /usr/local/etc/xray/config.json && "
        f"systemctl enable xray && "
        f"systemctl restart xray && "
        f"sleep 2 && "
        f"systemctl is-active xray && "
        f"echo CONFIG_DEPLOYED_OK"
    )

    stdout, stderr, rc = await run_ssh_command(ip, user, password, cmd, ssh_port, timeout=60)

    if "CONFIG_DEPLOYED_OK" in stdout:
        logger.info(f"Xray config deployed on {ip}")
        return True

    logger.error(f"Config deploy failed on {ip}: {stdout} | {stderr}")
    return False


async def setup_server_full(ip: str, user: str, password: str, ssh_port: int = 22,
                             sni: str = "www.google.com", xray_port: int = 443) -> dict:
    """Full auto-setup: install Xray, generate keys, deploy config."""

    # Check alive
    if not await check_server_alive(ip, user, password, ssh_port):
        return {"error": "Server unreachable via SSH"}

    # Install Xray
    if not await install_xray(ip, user, password, ssh_port):
        return {"error": "Xray installation failed"}

    # Generate keys
    keys = await generate_xray_keys(ip, user, password, ssh_port)
    if not keys:
        return {"error": "Key generation failed"}

    # Deploy config
    ok = await deploy_xray_config(
        ip, user, password,
        keys["uuid"], keys["private_key"], keys["short_id"],
        sni, xray_port, ssh_port
    )
    if not ok:
        return {"error": "Config deployment failed"}

    # Optimize network
    await optimize_network(ip, user, password, ssh_port)

    return {
        "uuid": keys["uuid"],
        "private_key": keys["private_key"],
        "public_key": keys["public_key"],
        "short_id": keys["short_id"],
        "port": xray_port,
        "sni": sni,
    }


async def optimize_network(ip: str, user: str, password: str, ssh_port: int = 22):
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
    stdout, _, _ = await run_ssh_command(ip, user, password, sysctl_cmd, ssh_port, timeout=30)
    if "NET_OPT_OK" in stdout:
        logger.info(f"Network optimized on {ip}")


async def setup_relay(relay_ip: str, relay_user: str, relay_pass: str,
                       target_ip: str, target_port: int = 443,
                       relay_port: int = 443, ssh_port: int = 22) -> bool:
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
    stdout, stderr, rc = await run_ssh_command(relay_ip, relay_user, relay_pass, cmd, ssh_port, timeout=120)
    if "RELAY_SETUP_OK" in stdout:
        logger.info(f"Relay {relay_ip} -> {target_ip}:{target_port} configured")
        return True
    logger.error(f"Relay setup failed: {stdout} | {stderr}")
    return False


def build_vless_link(ip: str, port: int, uuid_val: str, public_key: str,
                      short_id: str, sni: str, remark: str) -> str:
    """Build VLESS connection string."""
    return (
        f"vless://{uuid_val}@{ip}:{port}"
        f"?type=tcp&security=reality&pbk={public_key}&fp=chrome"
        f"&sni={sni}&sid={short_id}&spx=%2F&flow=xtls-rprx-vision"
        f"#{remark}"
    )
