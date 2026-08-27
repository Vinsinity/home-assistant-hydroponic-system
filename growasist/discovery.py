"""Read-only local-network discovery for the standalone appliance.

Discovery only creates candidates.  It never authenticates to a device and it
never sends a state-changing request.  Vendor adapters must be enrolled by the
user before later monitoring or control work can use them.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
import binascii
import hashlib
import http.client
import ipaddress
import json
import socket
import struct
import time
from typing import Any

from custom_components.hydroponic_system.journal import utc_now


_MDNS_ADDRESS = ("224.0.0.251", 5353)
_SSDP_ADDRESS = ("239.255.255.250", 1900)
_TP_LINK_LEGACY_PORT = 9999
_TP_LINK_DISCOVERY_PORTS = (20002, 20004)
_TUYA_PORTS = (6668, 6669)
_SCAN_PORTS = (80, 443, 6668, 6669, 9999)
_MAX_NETWORK_HOSTS = 1024


def _candidate_id(vendor: str, host: str, mac: str = "") -> str:
    anchor = "".join(character for character in mac.lower() if character.isalnum())
    if not anchor:
        anchor = hashlib.sha256(host.encode("utf-8")).hexdigest()[:16]
    return f"{vendor.lower()}_{anchor}"[:80]


def _clean_mac(value: Any) -> str:
    compact = "".join(character for character in str(value or "") if character.isalnum()).upper()
    if len(compact) != 12:
        return ""
    return ":".join(compact[index:index + 2] for index in range(0, 12, 2))


def _safe_text(value: Any, maximum: int = 160) -> str:
    return str(value or "").strip()[:maximum]


def _decode_possible_base64(value: Any) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    try:
        decoded = base64.b64decode(text, validate=True).decode("utf-8").strip()
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return text
    return decoded[:160] if decoded and all(character.isprintable() for character in decoded) else text


def _xor_encrypt(payload: bytes) -> bytes:
    key = 171
    result = bytearray()
    for value in payload:
        encrypted = key ^ value
        key = encrypted
        result.append(encrypted)
    return bytes(result)


def _xor_decrypt(payload: bytes) -> bytes:
    key = 171
    result = bytearray()
    for value in payload:
        plain = key ^ value
        key = value
        result.append(plain)
    return bytes(result)


def _dns_name(value: str) -> bytes:
    encoded = bytearray()
    for label in value.rstrip(".").split("."):
        part = label.encode("utf-8")
        if not part or len(part) > 63:
            raise ValueError("Invalid DNS label")
        encoded.append(len(part))
        encoded.extend(part)
    encoded.append(0)
    return bytes(encoded)


def _read_dns_name(packet: bytes, offset: int, *, depth: int = 0) -> tuple[str, int]:
    if depth > 12:
        raise ValueError("DNS compression loop")
    labels: list[str] = []
    cursor = offset
    consumed: int | None = None
    while cursor < len(packet):
        length = packet[cursor]
        if length == 0:
            cursor += 1
            break
        if length & 0xC0 == 0xC0:
            if cursor + 1 >= len(packet):
                raise ValueError("Truncated DNS pointer")
            pointer = ((length & 0x3F) << 8) | packet[cursor + 1]
            pointed, _ = _read_dns_name(packet, pointer, depth=depth + 1)
            labels.extend(pointed.rstrip(".").split("."))
            consumed = cursor + 2
            cursor = consumed
            break
        cursor += 1
        if cursor + length > len(packet):
            raise ValueError("Truncated DNS name")
        labels.append(packet[cursor:cursor + length].decode("utf-8", "replace"))
        cursor += length
    return ".".join(label for label in labels if label) + ".", consumed or cursor


def _parse_txt(value: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    offset = 0
    while offset < len(value):
        length = value[offset]
        offset += 1
        entry = value[offset:offset + length].decode("utf-8", "replace")
        offset += length
        key, separator, item_value = entry.partition("=")
        if key:
            result[key.lower()] = item_value if separator else ""
    return result


def _parse_mdns_packet(packet: bytes) -> dict[str, list[dict[str, Any]]]:
    """Parse the small DNS record subset required for DNS-SD discovery."""
    if len(packet) < 12:
        return {"ptr": [], "srv": [], "txt": [], "a": []}
    _, _, questions, answers, authorities, additionals = struct.unpack(">HHHHHH", packet[:12])
    offset = 12
    try:
        for _ in range(questions):
            _, offset = _read_dns_name(packet, offset)
            offset += 4
        records = {"ptr": [], "srv": [], "txt": [], "a": []}
        for _ in range(answers + authorities + additionals):
            name, offset = _read_dns_name(packet, offset)
            if offset + 10 > len(packet):
                break
            record_type, _, _, length = struct.unpack(">HHIH", packet[offset:offset + 10])
            offset += 10
            start = offset
            end = start + length
            if end > len(packet):
                break
            if record_type == 1 and length == 4:
                records["a"].append({"name": name.lower(), "host": socket.inet_ntoa(packet[start:end])})
            elif record_type == 12:
                target, _ = _read_dns_name(packet, start)
                records["ptr"].append({"name": name.lower(), "target": target.lower()})
            elif record_type == 16:
                records["txt"].append({"name": name.lower(), "values": _parse_txt(packet[start:end])})
            elif record_type == 33 and length >= 6:
                _, _, port = struct.unpack(">HHH", packet[start:start + 6])
                target, _ = _read_dns_name(packet, start + 6)
                records["srv"].append({"name": name.lower(), "target": target.lower(), "port": port})
            offset = end
        return records
    except (ValueError, struct.error):
        return {"ptr": [], "srv": [], "txt": [], "a": []}


def _infer_shelly_capabilities(model: str, application: str) -> tuple[list[str], str]:
    value = f"{model} {application}".lower()
    if any(marker in value for marker in ("ht", "humidity", "sensor")):
        return ["temperature", "humidity"], "environment_sensor"
    if any(marker in value for marker in ("0-10", "dimmer", "rgb", "light")):
        return ["switch", "light", "dimmer"], "light_dimmer"
    if any(marker in value for marker in ("plug", "switch", "1pm", "2pm")):
        return ["switch"], "light_power"
    return ["device_info"], "unassigned"


def _shelly_candidate(host: str, info: dict[str, Any], *, port: int = 80) -> dict[str, Any]:
    model = _safe_text(info.get("model") or info.get("type") or info.get("app") or "Shelly")
    application = _safe_text(info.get("app") or info.get("type"))
    mac = _clean_mac(info.get("mac"))
    capabilities, suggested_role = _infer_shelly_capabilities(model, application)
    return {
        "id": _candidate_id("shelly", host, mac),
        "vendor": "Shelly",
        "name": _safe_text(info.get("name") or info.get("id") or model),
        "model": model,
        "host": host,
        "port": int(port or 80),
        "mac": mac,
        "protocol": "shelly_rpc",
        "generation": _safe_text(info.get("gen")),
        "firmware": _safe_text(info.get("ver") or info.get("fw")),
        "capabilities": capabilities,
        "suggested_role": suggested_role,
        "supported": True,
        "requires_auth": bool(info.get("auth_en")),
        "source": "shelly_mdns_http",
    }


def _tplink_candidate(host: str, info: dict[str, Any], *, port: int) -> dict[str, Any]:
    values = info.get("result") if isinstance(info.get("result"), dict) else info
    system = values.get("system") if isinstance(values.get("system"), dict) else {}
    values = system.get("get_sysinfo") if isinstance(system.get("get_sysinfo"), dict) else values
    model = _safe_text(values.get("device_model") or values.get("model") or "TP-Link/Tapo")
    name = _decode_possible_base64(values.get("device_name") or values.get("alias")) or model
    mac = _clean_mac(values.get("mac"))
    family = _safe_text(values.get("device_type") or values.get("mic_type") or values.get("type"))
    normalized_model = model.upper().replace(" ", "")
    power_strip = normalized_model.startswith(("P300", "P304", "P306", "P316", "KP303", "HS300"))
    smart_plug = normalized_model.startswith(("P100", "P105", "P110", "P115", "KP1", "KP4", "HS1"))
    known_actuator = power_strip or smart_plug
    return {
        "id": _candidate_id("tplink", host, mac),
        "vendor": "TP-Link / Tapo",
        "name": name,
        "model": model,
        "host": host,
        "port": port,
        "mac": mac,
        "protocol": "tplink_discovery",
        "generation": family,
        "firmware": _safe_text(values.get("firmware_version") or values.get("sw_ver")),
        "capabilities": (["outlet_bank"] if power_strip else ["switch"] if smart_plug else ["device_info"]),
        "suggested_role": "outlet_bank" if power_strip else "light_power" if smart_plug else "unassigned",
        "supported": known_actuator,
        "requires_auth": port in _TP_LINK_DISCOVERY_PORTS,
        "source": "tplink_udp",
    }


class NetworkDiscovery:
    """Bounded, read-only discovery over the Raspberry Pi's local IPv4 LAN."""

    def __init__(self, *, timeout: float = 2.5) -> None:
        self.timeout = max(1.0, min(8.0, float(timeout)))
        self.local_ip = self._local_ipv4()
        self.network = self._local_network(self.local_ip)

    @staticmethod
    def _local_ipv4() -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("1.1.1.1", 53))
            return str(sock.getsockname()[0])
        except OSError:
            return "127.0.0.1"
        finally:
            sock.close()

    @staticmethod
    def _local_network(local_ip: str) -> ipaddress.IPv4Network:
        if local_ip.startswith("127."):
            return ipaddress.ip_network("127.0.0.0/8")
        try:
            import fcntl  # Linux appliance; kept optional for tests on other hosts.

            for _, interface in socket.if_nameindex():
                request = struct.pack("256s", interface.encode("utf-8")[:15])
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                    address = socket.inet_ntoa(fcntl.ioctl(probe.fileno(), 0x8915, request)[20:24])
                    if address != local_ip:
                        continue
                    netmask = socket.inet_ntoa(fcntl.ioctl(probe.fileno(), 0x891B, request)[20:24])
                    return ipaddress.ip_network(f"{local_ip}/{netmask}", strict=False)
        except (ImportError, OSError):
            pass
        return ipaddress.ip_network(f"{local_ip}/24", strict=False)

    @staticmethod
    def _arp_table() -> dict[str, str]:
        result: dict[str, str] = {}
        try:
            with open("/proc/net/arp", encoding="utf-8") as arp_file:
                for line in list(arp_file)[1:]:
                    columns = line.split()
                    if len(columns) >= 4:
                        mac = _clean_mac(columns[3])
                        if mac:
                            result[columns[0]] = mac
        except OSError:
            pass
        return result

    @staticmethod
    def _merge(target: dict[str, dict[str, Any]], candidate: dict[str, Any]) -> None:
        host = str(candidate.get("host") or "")
        if not host:
            return
        candidate.setdefault("last_seen", utc_now())
        candidate.setdefault("status", "candidate")
        for existing_id, existing in list(target.items()):
            if existing.get("host") != host:
                continue
            if existing.get("vendor") == "Unknown" and candidate.get("vendor") != "Unknown":
                target.pop(existing_id, None)
                break
            if candidate.get("vendor") == "Unknown":
                return
            merged = {**existing, **{key: value for key, value in candidate.items() if value not in (None, "", [])}}
            target.pop(existing_id, None)
            target[str(merged["id"])] = merged
            return
        target[str(candidate["id"])] = candidate

    @staticmethod
    def _http_json(host: str, path: str) -> tuple[dict[str, Any] | None, int, dict[str, str]]:
        connection = http.client.HTTPConnection(host, 80, timeout=0.6)
        try:
            connection.request("GET", path, headers={"Accept": "application/json", "User-Agent": "GrowAsist-Discovery"})
            response = connection.getresponse()
            headers = {key.lower(): value for key, value in response.getheaders()}
            body = response.read(32768)
            if response.status != 200:
                return None, response.status, headers
            value = json.loads(body)
            return (value if isinstance(value, dict) else None), response.status, headers
        except (OSError, json.JSONDecodeError, http.client.HTTPException):
            return None, 0, {}
        finally:
            connection.close()

    def _probe_shelly(self, host: str, port: int = 80) -> dict[str, Any] | None:
        for path in ("/rpc/Shelly.GetDeviceInfo", "/shelly"):
            info, status, headers = self._http_json(host, path)
            if info and any(key in info for key in ("mac", "model", "type", "app", "gen")):
                return _shelly_candidate(host, info, port=port)
            if status == 401 and "shelly" in headers.get("server", "").lower():
                return _shelly_candidate(host, {"model": "Shelly", "auth_en": True}, port=port)
        return None

    def _discover_mdns(self) -> list[dict[str, Any]]:
        query = struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0) + _dns_name("_shelly._tcp.local") + struct.pack(">HH", 12, 0x8001)
        records = {"ptr": [], "srv": [], "txt": [], "a": []}
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.25)
        try:
            sock.sendto(query, _MDNS_ADDRESS)
            deadline = time.monotonic() + min(self.timeout, 1.5)
            while time.monotonic() < deadline:
                try:
                    packet, _ = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                parsed = _parse_mdns_packet(packet)
                for kind in records:
                    records[kind].extend(parsed[kind])
        except OSError:
            return []
        finally:
            sock.close()

        addresses = {item["name"]: item["host"] for item in records["a"]}
        txt = {item["name"]: item["values"] for item in records["txt"]}
        candidates = []
        seen_hosts: set[str] = set()
        for service in records["srv"]:
            if "._shelly._tcp.local." not in service["name"]:
                continue
            host = addresses.get(service["target"])
            if not host or host == self.local_ip or host in seen_hosts:
                continue
            seen_hosts.add(host)
            info = txt.get(service["name"], {})
            candidate = self._probe_shelly(host, int(service["port"]))
            if candidate is None:
                candidate = _shelly_candidate(host, {"id": service["name"].split(".")[0], **info}, port=int(service["port"]))
                candidate["source"] = "shelly_mdns"
            candidates.append(candidate)
        return candidates

    def _discover_ssdp(self) -> list[dict[str, Any]]:
        request = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 1\r\nST: ssdp:all\r\n\r\n").encode("ascii")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.2)
        responses: dict[str, dict[str, str]] = {}
        try:
            sock.sendto(request, _SSDP_ADDRESS)
            deadline = time.monotonic() + min(self.timeout, 1.5)
            while time.monotonic() < deadline:
                try:
                    data, address = sock.recvfrom(32768)
                except socket.timeout:
                    continue
                headers: dict[str, str] = {}
                for line in data.decode("utf-8", "replace").splitlines()[1:]:
                    key, separator, value = line.partition(":")
                    if separator:
                        headers[key.strip().lower()] = value.strip()
                responses[address[0]] = headers
        except OSError:
            return []
        finally:
            sock.close()
        result = []
        for host, headers in responses.items():
            if host == self.local_ip:
                continue
            server = _safe_text(headers.get("server") or headers.get("st") or "SSDP device")
            result.append({
                "id": _candidate_id("unknown", host), "vendor": "Unknown", "name": server,
                "model": _safe_text(headers.get("usn") or "SSDP"), "host": host, "port": 80,
                "mac": "", "protocol": "ssdp", "generation": "", "firmware": "",
                "capabilities": ["device_info"], "suggested_role": "unassigned",
                "supported": False, "requires_auth": True, "source": "ssdp",
            })
        return result

    def _discover_tplink(self) -> list[dict[str, Any]]:
        if self.network.num_addresses > _MAX_NETWORK_HOSTS:
            return []
        broadcast = str(self.network.broadcast_address)
        legacy_query = _xor_encrypt(json.dumps({"system": {"get_sysinfo": {}}}, separators=(",", ":")).encode())
        modern_query = binascii.unhexlify("020000010000000000000000463cb5d3")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.2)
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        try:
            sock.bind(("", 0))
            deadline = time.monotonic() + min(self.timeout, 1.8)
            next_broadcast = 0.0
            broadcast_attempts = 0
            while time.monotonic() < deadline:
                now = time.monotonic()
                if broadcast_attempts < 3 and now >= next_broadcast:
                    sock.sendto(legacy_query, (broadcast, _TP_LINK_LEGACY_PORT))
                    for port in _TP_LINK_DISCOVERY_PORTS:
                        sock.sendto(modern_query, (broadcast, port))
                    broadcast_attempts += 1
                    next_broadcast = now + 0.55
                try:
                    data, (host, port) = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                if host in seen or host == self.local_ip:
                    continue
                try:
                    decoded = _xor_decrypt(data) if port == _TP_LINK_LEGACY_PORT else data[16:]
                    info = json.loads(decoded)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(info, dict):
                    seen.add(host)
                    result.append(_tplink_candidate(host, info, port=port))
        except OSError:
            return result
        finally:
            sock.close()
        return result

    @staticmethod
    def _open_ports(host: str) -> tuple[str, list[int]]:
        open_ports = []
        for port in _SCAN_PORTS:
            try:
                with socket.create_connection((host, port), timeout=0.12):
                    open_ports.append(port)
            except OSError:
                continue
        return host, open_ports

    def _scan_subnet(self) -> list[dict[str, Any]]:
        if self.network.num_addresses > _MAX_NETWORK_HOSTS or self.local_ip.startswith("127."):
            return []
        hosts = [str(host) for host in self.network.hosts() if str(host) != self.local_ip]
        results: list[tuple[str, list[int]]] = []
        with ThreadPoolExecutor(max_workers=64) as executor:
            futures = [executor.submit(self._open_ports, host) for host in hosts]
            for future in as_completed(futures):
                host, ports = future.result()
                if ports:
                    results.append((host, ports))
        arp = self._arp_table()
        candidates = []
        for host, ports in results:
            if 80 in ports:
                shelly = self._probe_shelly(host)
                if shelly:
                    shelly["mac"] = shelly.get("mac") or arp.get(host, "")
                    shelly["id"] = _candidate_id("shelly", host, shelly["mac"])
                    candidates.append(shelly)
                    continue
            if any(port in ports for port in _TUYA_PORTS):
                vendor, protocol, supported, name = "Tuya", "tuya_local", False, "Tuya LAN adayı"
                role = "unassigned"
            elif _TP_LINK_LEGACY_PORT in ports:
                vendor, protocol, supported, name = "TP-Link / Tapo", "tplink_local", True, "TP-Link / Tapo adayı"
                role = "light_power"
            else:
                vendor, protocol, supported, name = "Unknown", "local_tcp", False, "Yerel ağ cihazı"
                role = "unassigned"
            mac = arp.get(host, "")
            candidates.append({
                "id": _candidate_id(vendor.split()[0].replace("-", ""), host, mac),
                "vendor": vendor, "name": name, "model": "", "host": host,
                "port": ports[0], "ports": ports, "mac": mac, "protocol": protocol,
                "generation": "", "firmware": "", "capabilities": ["device_info"],
                "suggested_role": role, "supported": supported,
                "requires_auth": vendor != "Unknown", "source": "bounded_subnet_probe",
            })
        return candidates

    def scan(self) -> dict[str, Any]:
        """Run all read-only discovery methods and return de-duplicated candidates."""
        started_at = utc_now()
        candidates: dict[str, dict[str, Any]] = {}
        warnings = []
        methods = (self._discover_mdns, self._discover_ssdp, self._discover_tplink, self._scan_subnet)
        with ThreadPoolExecutor(max_workers=len(methods)) as executor:
            future_map = {executor.submit(method): method.__name__ for method in methods}
            for future in as_completed(future_map):
                try:
                    for candidate in future.result():
                        self._merge(candidates, candidate)
                except Exception as error:  # One protocol must not hide other results.
                    warnings.append(f"{future_map[future]}: {type(error).__name__}")
        return {
            "started_at": started_at,
            "finished_at": utc_now(),
            "network": str(self.network),
            "local_ip": self.local_ip,
            "candidate_count": len(candidates),
            "candidates": sorted(candidates.values(), key=lambda item: (item.get("vendor", ""), item.get("host", ""))),
            "warnings": warnings,
        }
