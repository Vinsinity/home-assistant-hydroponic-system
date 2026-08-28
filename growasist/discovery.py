"""Read-only local-network discovery for the standalone appliance.

Discovery only creates candidates.  It never authenticates to a device and it
never sends a state-changing request.  Vendor adapters must be enrolled by the
user before later monitoring or control work can use them.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
import binascii
import csv
import hashlib
import http.client
import ipaddress
import json
from pathlib import Path
import select
import socket
import struct
import time
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree

from custom_components.hydroponic_system.journal import utc_now


_MDNS_ADDRESS = ("224.0.0.251", 5353)
_SSDP_ADDRESS = ("239.255.255.250", 1900)
_TP_LINK_LEGACY_PORT = 9999
_TP_LINK_DISCOVERY_PORTS = (20002, 20004)
_TUYA_LISTEN_PORTS = (6666, 6667)
_TUYA_TCP_PORTS = (6667, 6668, 6669)
_SCAN_PORTS = (80, 443, 1883, 6667, 6668, 6669, 7000, 8080, 8883, 9999)
_MAX_NETWORK_HOSTS = 1024
_MDNS_SERVICE_TYPES = (
    "_shelly._tcp.local",
    "_http._tcp.local",
    "_hap._tcp.local",
    "_matter._tcp.local",
    "_matterc._udp.local",
)
_OUI_PATHS = (
    Path("/var/lib/growasist/oui.csv"),
    Path("/usr/share/ieee-data/oui.csv"),
    Path("/var/lib/ieee-data/oui.csv"),
)
# The full IEEE registry is installed in the appliance image.  This small
# fallback keeps common devices useful during development and on older images.
_OUI_FALLBACK = {
    "0CEF15": "TP-Link Technologies",
    "109836": "Dell",
    "246E96": "Dell",
    "3C7895": "TP-Link Systems",
    "5C628B": "TP-Link Systems",
    "706871": "FN-LINK Technology",
    "746DFA": "TP-Link Technologies",
    "74E9D8": "Shanghai High-Flying Electronics Technology",
    "844693": "Xiaomi Communications",
    "A82948": "TP-Link Technologies",
    "E87072": "Hangzhou BroadLink Technology",
}


def _unique_text(values: Any, maximum: int = 24) -> list[str]:
    result: list[str] = []
    for value in values if isinstance(values, (list, tuple, set)) else [values]:
        item = _safe_text(value)
        if item and item not in result:
            result.append(item)
        if len(result) >= maximum:
            break
    return result


def _candidate_id(vendor: str, host: str, mac: str = "") -> str:
    anchor = "".join(character for character in mac.lower() if character.isalnum())
    if not anchor:
        anchor = hashlib.sha256(host.encode("utf-8")).hexdigest()[:16]
    return f"{vendor.lower()}_{anchor}"[:80]


def _clean_mac(value: Any) -> str:
    compact = "".join(character for character in str(value or "") if character.isalnum()).upper()
    if len(compact) != 12 or compact in {"000000000000", "FFFFFFFFFFFF"}:
        return ""
    return ":".join(compact[index:index + 2] for index in range(0, 12, 2))


def _safe_text(value: Any, maximum: int = 160) -> str:
    return str(value or "").strip()[:maximum]


def _mac_anchor(value: Any) -> str:
    return "".join(character for character in _clean_mac(value) if character.isalnum())


def _mac_is_local(value: Any) -> bool:
    compact = _mac_anchor(value)
    return bool(compact and int(compact[:2], 16) & 0x02)


class OuiRegistry:
    """Read the packaged IEEE registry without adding a Python dependency."""

    def __init__(self, paths: tuple[Path, ...] = _OUI_PATHS) -> None:
        self._vendors = dict(_OUI_FALLBACK)
        self.source = "embedded_fallback"
        for path in paths:
            if not path.is_file():
                continue
            try:
                with path.open(encoding="utf-8-sig", newline="") as source:
                    for row in csv.DictReader(source):
                        assignment = _safe_text(
                            row.get("Assignment") or row.get("Registry") or row.get("OUI")
                        ).replace("-", "").replace(":", "").upper()
                        organization = _safe_text(
                            row.get("Organization Name")
                            or row.get("Organization")
                            or row.get("Company Name")
                        )
                        if len(assignment) >= 6 and organization:
                            self._vendors[assignment[:6]] = organization
                self.source = str(path)
                break
            except (OSError, csv.Error):
                continue

    def lookup(self, mac: Any) -> str:
        compact = _mac_anchor(mac)
        return self._vendors.get(compact[:6], "") if len(compact) == 12 else ""


def _manufacturer_vendor(manufacturer: str) -> str:
    value = manufacturer.lower()
    if "tp-link" in value:
        # An IEEE registration proves the radio/network vendor, not that the
        # product is a Tapo actuator.  Protocol discovery may promote it later.
        return "TP-Link"
    if "shelly" in value or "allterco" in value:
        return "Shelly"
    if "tuya" in value:
        return "Tuya"
    return _safe_text(manufacturer) or "Unknown"


def _device_category(vendor: str, name: str = "", model: str = "") -> str:
    value = f"{vendor} {name} {model}".lower()
    if any(marker in value for marker in ("router", "gateway", "deco", "access point", "network infrastructure")):
        return "infrastructure"
    if any(marker in value for marker in ("shelly", "tapo", "tuya", "dreo", "matter")):
        return "grow_iot"
    if any(marker in value for marker in ("broadlink", "fn-link", "high-flying", "espressif")):
        return "possible_iot"
    if vendor != "Unknown":
        return "other"
    return "unknown"


def _candidate(
    host: str,
    *,
    vendor: str = "Unknown",
    name: str = "Ağ cihazı",
    model: str = "",
    mac: str = "",
    protocol: str = "network_neighbor",
    port: int = 0,
    ports: list[int] | None = None,
    confidence: int = 15,
    evidence: list[str] | None = None,
    methods: list[str] | None = None,
    supported: bool = False,
    requires_auth: bool = False,
    suggested_role: str = "unassigned",
    capabilities: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    normalized_mac = _clean_mac(mac)
    item = {
        "id": _candidate_id("lan", host, normalized_mac),
        "vendor": _safe_text(vendor) or "Unknown",
        "manufacturer": _safe_text(extra.pop("manufacturer", "")),
        "name": _safe_text(name) or _safe_text(model) or host,
        "model": _safe_text(model),
        "host": host,
        "hostname": _safe_text(extra.pop("hostname", "")),
        "port": int(port or 0),
        "ports": sorted({int(value) for value in (ports or []) if int(value) > 0}),
        "mac": normalized_mac,
        "mac_local": _mac_is_local(normalized_mac),
        "protocol": _safe_text(protocol),
        "discovery_methods": _unique_text(methods or [protocol]),
        "identity_confidence": max(0, min(100, int(confidence))),
        "evidence": _unique_text(evidence or []),
        "category": _device_category(vendor, name, model),
        "generation": "",
        "firmware": "",
        "capabilities": _unique_text(capabilities or ["device_info"]),
        "suggested_role": suggested_role,
        "supported": bool(supported),
        "adapter_available": False,
        "requires_auth": bool(requires_auth),
        "source": (methods or [protocol])[0],
    }
    item.update(extra)
    return item


def _tuya_packet_kind(packet: bytes) -> str:
    """Recognize Tuya LAN frame families without decrypting device data."""
    if len(packet) < 4:
        return ""
    marker = packet[:4]
    if marker == b"\x00\x00U\xaa":
        return "tuya_55aa"
    if marker == b"\x00\x00f\x99":
        return "tuya_6699"
    return ""


def _xml_values(payload: bytes) -> dict[str, str]:
    """Extract only display identity fields from a UPnP description."""
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return {}
    wanted = {
        "friendlyName": "name",
        "manufacturer": "manufacturer",
        "modelName": "model",
        "modelNumber": "model_number",
        "deviceType": "device_type",
    }
    values: dict[str, str] = {}
    for element in root.iter():
        key = wanted.get(element.tag.rsplit("}", 1)[-1])
        if key and key not in values and element.text:
            values[key] = _safe_text(element.text)
    return values


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
    return _candidate(
        host,
        vendor="Shelly",
        name=_safe_text(info.get("name") or info.get("id") or model),
        model=model,
        mac=mac,
        protocol="shelly_rpc",
        port=int(port or 80),
        ports=[int(port or 80)],
        confidence=98 if mac and model != "Shelly" else 88,
        evidence=["Shelly yerel kimlik yanıtı", f"Model: {model}"],
        methods=["shelly_http"],
        capabilities=capabilities,
        suggested_role=suggested_role,
        supported=True,
        requires_auth=bool(info.get("auth_en")),
        generation=_safe_text(info.get("gen")),
        firmware=_safe_text(info.get("ver") or info.get("fw")),
    )


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
    candidate = _candidate(
        host,
        vendor="TP-Link / Tapo",
        name=name,
        model=model,
        mac=mac,
        protocol="tplink_discovery",
        port=port,
        ports=[port],
        confidence=96 if model != "TP-Link/Tapo" else 82,
        evidence=["TP-Link/Tapo UDP kimlik yanıtı", f"Model: {model}"],
        methods=["tplink_udp"],
        generation=family,
        firmware=_safe_text(values.get("firmware_version") or values.get("sw_ver")),
        capabilities=(["outlet_bank"] if power_strip else ["switch"] if smart_plug else ["device_info"]),
        suggested_role="outlet_bank" if power_strip else "light_power" if smart_plug else "unassigned",
        supported=known_actuator,
        requires_auth=port in _TP_LINK_DISCOVERY_PORTS,
    )
    if normalized_model.startswith(("M4", "M5", "X20", "X50", "X60")) or "router" in family.lower():
        candidate["category"] = "infrastructure"
    return candidate


class NetworkDiscovery:
    """Bounded, read-only discovery over the Raspberry Pi's local IPv4 LAN."""

    def __init__(self, *, timeout: float = 2.5) -> None:
        self.timeout = max(1.0, min(8.0, float(timeout)))
        self.local_ip = self._local_ipv4()
        self.network = self._local_network(self.local_ip)
        self.oui = OuiRegistry()

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
            existing_confidence = int(existing.get("identity_confidence") or 0)
            candidate_confidence = int(candidate.get("identity_confidence") or 0)
            richer = candidate if candidate_confidence >= existing_confidence else existing
            supporting = existing if richer is candidate else candidate
            merged = {
                **supporting,
                **{key: value for key, value in richer.items() if value not in (None, "", [])},
            }
            merged["mac"] = _clean_mac(candidate.get("mac") or existing.get("mac"))
            merged["id"] = _candidate_id("lan", host, merged["mac"])
            merged["ports"] = sorted({
                int(port)
                for port in [*(existing.get("ports") or []), *(candidate.get("ports") or [])]
                if int(port) > 0
            })
            merged["evidence"] = _unique_text([
                *(existing.get("evidence") or []), *(candidate.get("evidence") or [])
            ])
            merged["discovery_methods"] = _unique_text([
                *(existing.get("discovery_methods") or []),
                *(candidate.get("discovery_methods") or []),
            ])
            merged["capabilities"] = _unique_text([
                *(existing.get("capabilities") or []), *(candidate.get("capabilities") or [])
            ])
            merged["supported"] = bool(existing.get("supported") or candidate.get("supported"))
            merged["requires_auth"] = bool(existing.get("requires_auth") or candidate.get("requires_auth"))
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

    def _fetch_ssdp_identity(self, host: str, location: str) -> dict[str, str]:
        try:
            target = urlsplit(location)
            if target.scheme != "http" or target.hostname != host:
                return {}
            if ipaddress.ip_address(host) not in self.network:
                return {}
            connection = http.client.HTTPConnection(host, target.port or 80, timeout=0.7)
            try:
                path = target.path or "/"
                if target.query:
                    path = f"{path}?{target.query}"
                connection.request("GET", path, headers={"Accept": "application/xml", "User-Agent": "GrowAsist-Discovery"})
                response = connection.getresponse()
                if response.status != 200:
                    return {}
                return _xml_values(response.read(65536))
            finally:
                connection.close()
        except (OSError, ValueError, http.client.HTTPException):
            return {}

    def _probe_shelly(self, host: str, port: int = 80) -> dict[str, Any] | None:
        for path in ("/rpc/Shelly.GetDeviceInfo", "/shelly"):
            info, status, headers = self._http_json(host, path)
            if info and any(key in info for key in ("mac", "model", "type", "app", "gen")):
                return _shelly_candidate(host, info, port=port)
            if status == 401 and "shelly" in headers.get("server", "").lower():
                return _shelly_candidate(host, {"model": "Shelly", "auth_en": True}, port=port)
        return None

    def _discover_mdns(self) -> list[dict[str, Any]]:
        records = {"ptr": [], "srv": [], "txt": [], "a": []}
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.25)
        try:
            for service_type in _MDNS_SERVICE_TYPES:
                query = (
                    struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0)
                    + _dns_name(service_type)
                    + struct.pack(">HH", 12, 0x8001)
                )
                sock.sendto(query, _MDNS_ADDRESS)
            deadline = time.monotonic() + min(self.timeout, 2.0)
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
        candidates: list[dict[str, Any]] = []
        seen_services: set[tuple[str, str]] = set()
        for service in records["srv"]:
            host = addresses.get(service["target"])
            if not host or host == self.local_ip:
                continue
            service_name = str(service["name"])
            service_key = (host, service_name)
            if service_key in seen_services:
                continue
            seen_services.add(service_key)
            info = txt.get(service["name"], {})
            instance = service_name.split(".")[0]
            target_name = str(service.get("target") or "").rstrip(".")
            port = int(service["port"])
            is_shelly = "._shelly._tcp.local." in service_name or "shelly" in f"{instance} {target_name}".lower()
            if is_shelly:
                candidate = self._probe_shelly(host, port)
                if candidate is None:
                    candidate = _shelly_candidate(host, {"id": instance, **info}, port=port)
                    candidate["source"] = "shelly_mdns"
                    candidate["discovery_methods"] = ["shelly_mdns"]
                    candidate["evidence"] = ["Shelly mDNS servisi", f"Servis: {instance}"]
                    candidate["identity_confidence"] = 86
            elif "._matter" in service_name:
                vendor_product = _safe_text(info.get("vp") or info.get("vid") or "")
                candidate = _candidate(
                    host,
                    vendor="Matter",
                    name=instance,
                    model=(f"VID/PID {vendor_product}" if vendor_product else "Matter cihazı"),
                    protocol="matter_mdns",
                    port=port,
                    ports=[port],
                    confidence=84,
                    evidence=["Matter DNS-SD servisi", *([f"VID/PID: {vendor_product}"] if vendor_product else [])],
                    methods=["matter_mdns"],
                    supported=True,
                    requires_auth=True,
                    hostname=target_name,
                )
            else:
                protocol = "homekit_mdns" if "._hap._tcp.local." in service_name else "http_mdns"
                candidate = _candidate(
                    host,
                    name=instance,
                    model="HomeKit cihazı" if protocol == "homekit_mdns" else "Yerel web cihazı",
                    protocol=protocol,
                    port=port,
                    ports=[port],
                    confidence=55 if protocol == "homekit_mdns" else 38,
                    evidence=[f"mDNS servisi: {service_name.split('.', 1)[1].rstrip('.')}"],
                    methods=[protocol],
                    requires_auth=True,
                    hostname=target_name,
                )
            candidates.append(candidate)
        return candidates

    def _discover_ssdp(self) -> list[dict[str, Any]]:
        request = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 1\r\nST: ssdp:all\r\n\r\n").encode("ascii")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.2)
        responses: dict[str, list[dict[str, str]]] = {}
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
                host_responses = responses.setdefault(address[0], [])
                fingerprint = (headers.get("location", ""), headers.get("usn", ""), headers.get("st", ""))
                if fingerprint not in {
                    (item.get("location", ""), item.get("usn", ""), item.get("st", ""))
                    for item in host_responses
                }:
                    host_responses.append(headers)
        except OSError:
            return []
        finally:
            sock.close()
        result = []
        for host, host_responses in responses.items():
            if host == self.local_ip:
                continue
            descriptions: list[dict[str, str]] = []
            for headers in host_responses:
                location = _safe_text(headers.get("location"), 512)
                if location:
                    identity = self._fetch_ssdp_identity(host, location)
                    if identity:
                        descriptions.append(identity)
            identity = max(descriptions, key=lambda item: len(item), default={})
            headers = host_responses[0]
            server = _safe_text(headers.get("server") or headers.get("st") or "SSDP cihazı")
            manufacturer = _safe_text(identity.get("manufacturer"))
            vendor = _manufacturer_vendor(manufacturer)
            name = _safe_text(identity.get("name") or server)
            model = _safe_text(identity.get("model") or identity.get("model_number") or headers.get("st") or "SSDP")
            result.append(_candidate(
                host,
                vendor=vendor,
                manufacturer=manufacturer,
                name=name,
                model=model,
                protocol="upnp_ssdp",
                port=80,
                ports=[80],
                confidence=76 if identity else 44,
                evidence=[
                    "UPnP/SSDP yanıtı",
                    *([f"Üretici: {manufacturer}"] if manufacturer else []),
                    *([f"Model: {model}"] if identity else []),
                ],
                methods=["ssdp", *( ["upnp_description"] if identity else [])],
                supported=vendor in {"Shelly", "TP-Link / Tapo", "Tuya"},
                requires_auth=True,
                device_type=_safe_text(identity.get("device_type")),
            ))
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

    def _discover_tuya(self) -> list[dict[str, Any]]:
        """Passively listen for Tuya's local presence broadcasts."""
        sockets: list[socket.socket] = []
        result: dict[str, dict[str, Any]] = {}
        try:
            for port in _TUYA_LISTEN_PORTS:
                listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    listener.bind(("", port))
                except OSError:
                    listener.close()
                    continue
                listener.setblocking(False)
                sockets.append(listener)
            if not sockets:
                return []
            deadline = time.monotonic() + min(self.timeout, 6.0)
            while time.monotonic() < deadline:
                readable, _, _ = select.select(sockets, [], [], 0.25)
                for listener in readable:
                    try:
                        packet, (host, source_port) = listener.recvfrom(65535)
                    except OSError:
                        continue
                    if host == self.local_ip:
                        continue
                    try:
                        if ipaddress.ip_address(host) not in self.network:
                            continue
                    except ValueError:
                        continue
                    frame = _tuya_packet_kind(packet)
                    if not frame:
                        continue
                    result[host] = _candidate(
                        host,
                        vendor="Tuya",
                        name="Tuya tabanlı cihaz",
                        model="Tuya LAN cihazı",
                        protocol="tuya_lan_broadcast",
                        port=source_port,
                        ports=[source_port],
                        confidence=88,
                        evidence=[f"Tuya LAN yayını ({frame.replace('tuya_', '')})"],
                        methods=["tuya_udp_broadcast"],
                        supported=True,
                        requires_auth=True,
                    )
            return list(result.values())
        finally:
            for listener in sockets:
                listener.close()

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
        results: dict[str, list[int]] = {}
        with ThreadPoolExecutor(max_workers=64) as executor:
            futures = [executor.submit(self._open_ports, host) for host in hosts]
            for future in as_completed(futures):
                host, ports = future.result()
                if ports:
                    results[host] = ports
        arp = self._arp_table()
        candidates: list[dict[str, Any]] = []
        observed_hosts = sorted(
            set(results) | {host for host in arp if host != self.local_ip},
            key=ipaddress.ip_address,
        )
        for host in observed_hosts:
            ports = results.get(host, [])
            mac = arp.get(host, "")
            manufacturer = self.oui.lookup(mac)
            if 80 in ports:
                shelly = self._probe_shelly(host)
                if shelly:
                    shelly["mac"] = shelly.get("mac") or mac
                    shelly["manufacturer"] = manufacturer
                    shelly["id"] = _candidate_id("lan", host, shelly["mac"])
                    shelly["ports"] = sorted(set(ports) | set(shelly.get("ports") or []))
                    if manufacturer:
                        shelly["evidence"] = _unique_text([
                            *(shelly.get("evidence") or []), f"IEEE üreticisi: {manufacturer}"
                        ])
                    candidates.append(shelly)
                    continue
            if any(port in ports for port in _TUYA_TCP_PORTS):
                vendor, protocol, supported, name = "Tuya", "tuya_lan_port", True, "Tuya tabanlı cihaz adayı"
                confidence = 68
            elif _TP_LINK_LEGACY_PORT in ports:
                vendor, protocol, supported, name = "TP-Link / Tapo", "tplink_local", True, "TP-Link / Tapo adayı"
                confidence = 72
            else:
                vendor = _manufacturer_vendor(manufacturer)
                protocol = "network_neighbor"
                supported = False
                name = manufacturer or "Ağ cihazı"
                confidence = 48 if manufacturer else 20
            port_evidence = f"Açık yerel portlar: {', '.join(str(port) for port in ports)}" if ports else "Yerel ağ komşu tablosunda görüldü"
            candidates.append(_candidate(
                host,
                vendor=vendor,
                manufacturer=manufacturer,
                name=name,
                mac=mac,
                protocol=protocol,
                port=ports[0] if ports else 0,
                ports=ports,
                confidence=confidence,
                evidence=[
                    port_evidence,
                    *([f"IEEE üreticisi: {manufacturer}"] if manufacturer else []),
                ],
                methods=["tcp_probe", "arp_neighbor"] if ports else ["arp_neighbor"],
                supported=supported,
                requires_auth=vendor in {"Tuya", "TP-Link / Tapo"},
                suggested_role="light_power" if protocol == "tplink_local" else "unassigned",
            ))
        return candidates

    def scan(self) -> dict[str, Any]:
        """Run all read-only discovery methods and return de-duplicated candidates."""
        started_at = utc_now()
        started_clock = time.monotonic()
        candidates: dict[str, dict[str, Any]] = {}
        warnings = []
        methods = (
            self._discover_mdns,
            self._discover_ssdp,
            self._discover_tplink,
            self._discover_tuya,
            self._scan_subnet,
        )
        with ThreadPoolExecutor(max_workers=len(methods)) as executor:
            future_map = {executor.submit(method): method.__name__ for method in methods}
            for future in as_completed(future_map):
                try:
                    for candidate in future.result():
                        self._merge(candidates, candidate)
                except Exception as error:  # One protocol must not hide other results.
                    warnings.append(f"{future_map[future]}: {type(error).__name__}")
        items = sorted(
            candidates.values(),
            key=lambda item: (
                {"grow_iot": 0, "possible_iot": 1, "unknown": 2, "other": 3, "infrastructure": 4}.get(str(item.get("category")), 5),
                ipaddress.ip_address(str(item.get("host"))),
            ),
        )
        protocol_counts: dict[str, int] = {}
        for item in items:
            for method in item.get("discovery_methods") or [item.get("protocol")]:
                protocol_counts[str(method)] = protocol_counts.get(str(method), 0) + 1
        return {
            "started_at": started_at,
            "finished_at": utc_now(),
            "network": str(self.network),
            "local_ip": self.local_ip,
            "candidate_count": len(items),
            "observed_host_count": len(items),
            "recognized_count": sum(int(item.get("identity_confidence") or 0) >= 70 for item in items),
            "grow_candidate_count": sum(item.get("category") in {"grow_iot", "possible_iot"} for item in items),
            "protocol_counts": protocol_counts,
            "duration_ms": int((time.monotonic() - started_clock) * 1000),
            "oui_source": self.oui.source,
            "candidates": items,
            "warnings": warnings,
        }
