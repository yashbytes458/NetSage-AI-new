"""
NetSage AI - Deterministic Rule Checker
Implements generic static configuration checks for Cisco lab outputs using standard Python libraries.
"""
import csv
import os
import re
import ipaddress
from typing import Dict, List, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_duplicate_ip(evidence_text: str) -> Dict[str, Any]:
    """Check 1: Parses syslog logs and ARP/IP output for explicit IP address conflicts or duplicate IP notifications."""
    pattern = r"(?:duplicate address|IP-4-DUPADDR|duplicate IP|Address collision|conflict for)\s+([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})"
    match = re.search(pattern, evidence_text, re.IGNORECASE)
    if match:
        dup_ip = match.group(1)
        return {
            "status": "FLAGGED",
            "rule": "DUPLICATE_IP",
            "details": f"Duplicate IP address {dup_ip} detected in network evidence"
        }
    return {"status": "NOT_FLAGGED", "rule": "DUPLICATE_IP", "details": "No duplicate IP evidence found"}


def check_subnet_mask_mismatch(evidence_text: str) -> Dict[str, Any]:
    """Check 2: Compares host vs gateway interface subnet masks / CIDR prefix lengths to detect mask inconsistencies."""
    masks = re.findall(r"(?:Subnet Mask:\s*|netmask\s*|/)(255\.\d+\.\d+\.\d+|\d{1,2})", evidence_text, re.IGNORECASE)
    if len(masks) >= 2:
        normalized = []
        for m in masks[:2]:
            if m.startswith("255."):
                try:
                    normalized.append(str(ipaddress.IPv4Network(f"0.0.0.0/{m}").prefixlen))
                except Exception:
                    pass
            elif m.isdigit() and 8 <= int(m) <= 32:
                normalized.append(m)

        if len(normalized) == 2 and normalized[0] != normalized[1]:
            return {
                "status": "FLAGGED",
                "rule": "SUBNET_MASK_MISMATCH",
                "details": f"Host subnet mask (/{normalized[0]}) does not match gateway subinterface mask (/{normalized[1]})"
            }
    return {"status": "NOT_FLAGGED", "rule": "SUBNET_MASK_MISMATCH", "details": "Subnet masks are consistent or insufficient mask pairs"}


def check_gateway_mismatch(evidence_text: str) -> Dict[str, Any]:
    """Check 3: Compares host default gateway IP against the actual operational interface IP and subnet."""
    gw_host_match = re.search(r"(?:Default Gateway|default-router)[:\s]+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", evidence_text, re.IGNORECASE)
    if gw_host_match:
        configured_gw = gw_host_match.group(1)
        interface_ips = re.findall(
            r"(?:ip address|GigabitEthernet[0-9/.]+|Gi[0-9/.]+|Vlan\d+|actual gateway interface[^0-9]*)[\s=]+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",
            evidence_text,
            re.IGNORECASE
        )
        # Filter out subnet masks like 255.255.255.0
        interface_ips = [ip for ip in interface_ips if not ip.startswith("255.")]
        if interface_ips and configured_gw not in interface_ips and configured_gw != "0.0.0.0":
            return {
                "status": "FLAGGED",
                "rule": "GATEWAY_MISMATCH",
                "details": f"Host configured gateway {configured_gw} does not match operational interface IP(s) {interface_ips}"
            }
    return {"status": "NOT_FLAGGED", "rule": "GATEWAY_MISMATCH", "details": "Gateway IP matches interface or no host gateway config found"}


def check_interface_down(evidence_text: str) -> Dict[str, Any]:
    """Check 4: Detects interfaces in an administratively down or line protocol down state (both prose and tabular 'show ip interface brief' outputs)."""
    details_list = []

    # Pattern A: Standard prose format '<Interface> is administratively down' or '<Interface> is down'
    prose_matches = re.findall(r"([A-Za-z0-9/.]+)\s+is\s+(administratively down|down)", evidence_text, re.IGNORECASE)
    for iface, state in prose_matches:
        if iface.lower() not in {"line", "protocol", "interface", "service"}:
            details_list.append(f"{iface} is {state}")

    # Pattern B: Tabular 'show ip interface brief' format
    # e.g. 'GigabitEthernet0/0  192.168.10.1  YES manual administratively down  down'
    # or   'Vlan50   192.168.50.1   YES manual up   down'
    tabular_pattern = r"((?:GigabitEthernet|FastEthernet|Serial|Vlan|Gi|Fa|Se|Lo)[0-9/.]+)\s+(?:[0-9.]+|unassigned)\s+\w+\s+\w+\s+(administratively down|up|down)\s+(down)"
    for match in re.finditer(tabular_pattern, evidence_text, re.IGNORECASE):
        iface, status_col, proto_col = match.group(1), match.group(2).lower(), match.group(3).lower()
        if "administratively down" in status_col:
            entry = f"{iface} is administratively down/{proto_col}"
        else:
            entry = f"{iface} status is {status_col}/{proto_col} (line protocol down)"
        if entry not in details_list:
            details_list.append(entry)

    if details_list:
        return {
            "status": "FLAGGED",
            "rule": "INTERFACE_DOWN",
            "details": ", ".join(details_list[:3])
        }
    return {"status": "NOT_FLAGGED", "rule": "INTERFACE_DOWN", "details": "No down interfaces detected"}


def parse_vlan_ranges(vlan_str: str) -> set:
    """Parses Cisco VLAN range strings (e.g. '1-29,31-4094', '1,10') into a set of integer VLAN IDs."""
    vlans = set()
    for part in vlan_str.split(','):
        part = part.strip()
        if '-' in part:
            bounds = part.split('-')
            if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit():
                vlans.update(range(int(bounds[0]), int(bounds[1]) + 1))
        elif part.isdigit():
            vlans.add(int(part))
    return vlans


def extract_intended_vlans(intent_text: str) -> List[int]:
    """Extracts intended/target VLAN numbers from symptom and topology notes only."""
    vlans = set()
    matches = re.findall(r"(?:should carry|carrying|intended to be.*carrying|should be in|map the WLAN to|in|for)\s+VLANs?\s*([0-9,\s and]+)", intent_text, re.IGNORECASE)
    for match in matches:
        for num in re.findall(r"\d+", match):
            vlans.add(int(num))
    return sorted(list(vlans))


def check_vlan_missing_or_pruned(symptom: str, topology: str, show_outputs: str) -> Dict[str, Any]:
    """Check 5: Detects native VLAN mismatches, wrong access VLAN assignments, static access port instead of trunk, or trunk pruning."""
    combined_intent = f"{symptom}\n{topology}"
    intended_vlans = extract_intended_vlans(combined_intent)

    # 1. Native VLAN mismatch check
    if "%CDP-4-NATIVE_VLAN_MISMATCH" in show_outputs or "Native VLAN mismatch" in show_outputs:
        return {
            "status": "FLAGGED",
            "rule": "VLAN_NATIVE_MISMATCH",
            "details": "Native VLAN mismatch logged between trunk endpoints"
        }
    native_matches = re.findall(r"Native vlan:\s*(\d+)", show_outputs, re.IGNORECASE)
    if len(native_matches) >= 2 and native_matches[0] != native_matches[1]:
        return {
            "status": "FLAGGED",
            "rule": "VLAN_NATIVE_MISMATCH",
            "details": f"Mismatched Native VLANs on trunk link ({native_matches[0]} vs {native_matches[1]})"
        }

    # 2. Trunk link misconfigured as static access port
    if re.search(r"intended to be an? (?:802\.1Q )?trunk", combined_intent, re.IGNORECASE) and re.search(r"Operational Mode:\s*static access", show_outputs, re.IGNORECASE):
        return {
            "status": "FLAGGED",
            "rule": "VLAN_MISCONFIGURATION",
            "details": "Inter-switch link is operating in static access mode instead of an 802.1Q trunk"
        }

    # 3. Access port VLAN mismatch check
    access_match = re.search(r"Access Mode VLAN:\s*(\d+)", show_outputs, re.IGNORECASE)
    if access_match and intended_vlans:
        configured_vlan = int(access_match.group(1))
        if configured_vlan not in intended_vlans:
            return {
                "status": "FLAGGED",
                "rule": "VLAN_MISCONFIGURATION",
                "details": f"Port configured for Access VLAN {configured_vlan}, but intended VLAN is {intended_vlans[0]}"
            }

    # 4. Trunk VLAN pruning check
    trunk_match = re.search(r"Vlans allowed on trunk:\s*([0-9,\-]+)", show_outputs, re.IGNORECASE)
    if trunk_match and intended_vlans:
        allowed_vlans = parse_vlan_ranges(trunk_match.group(1))
        for iv in intended_vlans:
            if iv not in allowed_vlans:
                return {
                    "status": "FLAGGED",
                    "rule": "VLAN_PRUNED_FROM_TRUNK",
                    "details": f"Intended VLAN {iv} is pruned/missing from allowed trunk list ({trunk_match.group(1)})"
                }

    return {"status": "NOT_FLAGGED", "rule": "VLAN_MISCONFIGURATION", "details": "No VLAN configuration issues detected"}


def check_missing_route(evidence_text: str) -> Dict[str, Any]:
    """Check 6: Inspects routing evidence for missing destination routes or absent default routes."""
    if "(no route" in evidence_text.lower() or "(no default route" in evidence_text.lower() or "no default route present" in evidence_text.lower():
        return {
            "status": "FLAGGED",
            "rule": "MISSING_ROUTE",
            "details": "Target network route or default route (0.0.0.0/0) missing from routing table"
        }
    return {"status": "NOT_FLAGGED", "rule": "MISSING_ROUTE", "details": "No route omissions detected"}


def run_rule_checker(case: Dict[str, Any]) -> Dict[str, Any]:
    """Runs all 6 deterministic rules on a single lab case."""
    symptom = case.get("symptom", "")
    topology = case.get("topology_note", "")
    show_outputs = case.get("show_outputs", "")
    evidence = f"{symptom}\n{topology}\n{show_outputs}"

    checks = [
        check_duplicate_ip(evidence),
        check_subnet_mask_mismatch(evidence),
        check_gateway_mismatch(evidence),
        check_interface_down(evidence),
        check_vlan_missing_or_pruned(symptom, topology, show_outputs),
        check_missing_route(evidence)
    ]

    flagged = [c for c in checks if c["status"] == "FLAGGED"]

    return {
        "case_id": case.get("case_id"),
        "rule_matches_found": len(flagged) > 0,
        "flagged_rules": flagged,
        "all_checks": checks
    }


def test_checker_on_cases(csv_filepath: str, sample_ids: List[str]):
    """Helper to test rule checker on sample cases from cases.csv."""
    if not os.path.isabs(csv_filepath) and not os.path.exists(csv_filepath):
        csv_filepath = os.path.join(BASE_DIR, csv_filepath)
    with open(csv_filepath, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["case_id"] in sample_ids:
                res = run_rule_checker(row)
                print(f"[{res['case_id']}] Flagged Rules: {len(res['flagged_rules'])}")
                for flag in res["flagged_rules"]:
                    print(f"  - {flag['rule']}: {flag['details']}")


if __name__ == "__main__":
    test_checker_on_cases("dataset/cases.csv", ["CASE-GW-02", "CASE-VLAN-03", "CASE-RT-01"])
