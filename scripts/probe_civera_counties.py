#!/usr/bin/env python3
"""
Probe California county registrar websites for Civera ElectionStats endpoints.

Civera ElectionStats uses a consistent GraphQL API at /api/graphql_pr.
Known instances use varied subdomain patterns:
    - pastelections.marincounty.gov
    - electionstats.sonomacounty.ca.gov
    - electionstats.elections.yolocounty.gov

This script probes multiple URL patterns for each of the 58 CA counties
and reports which ones respond with a valid Civera GraphQL endpoint.

Usage:
    python scripts/probe_civera_counties.py [--timeout 5] [--verbose]
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import requests

# All 58 California counties with common domain slug variants.
# Each entry: (county_name, [domain_candidates])
# Domain candidates are base domains (no subdomain prefix yet).
CA_COUNTIES: List[Tuple[str, str, List[str]]] = [
    ("Alameda", "alameda", ["acgov.org", "alamedacounty.gov", "alamedacounty.ca.gov"]),
    ("Alpine", "alpine", ["alpinecountyca.gov", "alpinecounty.gov"]),
    ("Amador", "amador", ["amadorgov.org", "amadorcounty.gov"]),
    ("Butte", "butte", ["buttecounty.net", "buttecounty.gov"]),
    ("Calaveras", "calaveras", ["co.calaveras.ca.us", "calaverasgov.us"]),
    ("Colusa", "colusa", ["countyofcolusa.org", "colusacounty.gov"]),
    ("Contra Costa", "contra-costa", ["contracostaco.org", "contracosta.ca.gov", "contracostacore.us"]),
    ("Del Norte", "del-norte", ["co.del-norte.ca.us", "dnco.org"]),
    ("El Dorado", "el-dorado", ["edcgov.us", "eldoradocounty.gov"]),
    ("Fresno", "fresno", ["co.fresno.ca.us", "fresnocountyca.gov"]),
    ("Glenn", "glenn", ["countyofglenn.net", "glenncounty.gov"]),
    ("Humboldt", "humboldt", ["humboldtgov.org", "co.humboldt.ca.us"]),
    ("Imperial", "imperial", ["co.imperial.ca.us", "imperialcounty.gov"]),
    ("Inyo", "inyo", ["inyocounty.us", "inyocounty.gov"]),
    ("Kern", "kern", ["kerncounty.com", "kernvote.com"]),
    ("Kings", "kings", ["countyofkings.com", "kingscounty.gov"]),
    ("Lake", "lake", ["co.lake.ca.us", "lakecountyca.gov"]),
    ("Lassen", "lassen", ["lassencounty.org", "co.lassen.ca.us"]),
    ("Los Angeles", "los-angeles", ["lavote.gov", "lacounty.gov"]),
    ("Madera", "madera", ["maderacounty.com", "maderacounty.gov"]),
    ("Marin", "marin", ["marincounty.gov"]),
    ("Mariposa", "mariposa", ["mariposacounty.org", "co.mariposa.ca.us"]),
    ("Mendocino", "mendocino", ["mendocinocounty.gov", "mendocinocounty.org"]),
    ("Merced", "merced", ["co.merced.ca.us", "mercedcounty.gov"]),
    ("Modoc", "modoc", ["co.modoc.ca.us", "modoccounty.gov"]),
    ("Mono", "mono", ["monocounty.ca.gov", "mono.ca.gov"]),
    ("Monterey", "monterey", ["co.monterey.ca.us", "montereycounty.gov"]),
    ("Napa", "napa", ["countyofnapa.org", "napacounty.gov"]),
    ("Nevada", "nevada", ["mynevadacounty.com", "nevadacountyca.gov"]),
    ("Orange", "orange", ["ocvote.gov", "ocgov.com"]),
    ("Placer", "placer", ["placer.ca.gov", "placercounty.gov"]),
    ("Plumas", "plumas", ["plumascounty.us", "countyofplumas.com"]),
    ("Riverside", "riverside", ["voteinfo.net", "rivco.org"]),
    ("Sacramento", "sacramento", ["saccounty.gov", "saccounty.net"]),
    ("San Benito", "san-benito", ["cosb.us", "sanbenitocounty.gov"]),
    ("San Bernardino", "san-bernardino", ["sbcounty.gov", "elections.sbcounty.gov"]),
    ("San Diego", "san-diego", ["sdcounty.ca.gov", "sdvote.com"]),
    ("San Francisco", "san-francisco", ["sfgov.org", "sfelections.org"]),
    ("San Joaquin", "san-joaquin", ["sjgov.org", "sjcrov.org"]),
    ("San Luis Obispo", "san-luis-obispo", ["slocounty.ca.gov"]),
    ("San Mateo", "san-mateo", ["smcacre.org", "smcgov.org"]),
    ("Santa Barbara", "santa-barbara", ["countyofsb.org", "sbcvote.com"]),
    ("Santa Clara", "santa-clara", ["sccgov.org", "santaclaracounty.gov"]),
    ("Santa Cruz", "santa-cruz", ["santacruzcountyca.gov", "votescount.us"]),
    ("Shasta", "shasta", ["co.shasta.ca.us", "shastacounty.gov"]),
    ("Sierra", "sierra", ["sierracounty.ca.gov"]),
    ("Siskiyou", "siskiyou", ["co.siskiyou.ca.us", "siskiyoucounty.gov"]),
    ("Solano", "solano", ["solanocounty.com", "solanocounty.gov"]),
    ("Sonoma", "sonoma", ["sonomacounty.ca.gov", "sonomacounty.gov"]),
    ("Stanislaus", "stanislaus", ["stancounty.com", "stanislausvote.com"]),
    ("Sutter", "sutter", ["co.sutter.ca.us", "suttercounty.org"]),
    ("Tehama", "tehama", ["co.tehama.ca.us", "tehamacounty.gov"]),
    ("Trinity", "trinity", ["trinitycounty.org"]),
    ("Tulare", "tulare", ["tularecounty.ca.gov", "tularecoelections.org"]),
    ("Tuolumne", "tuolumne", ["tuolumnecounty.ca.gov"]),
    ("Ventura", "ventura", ["ventura.org", "countyofventura.org"]),
    ("Yolo", "yolo", ["yolocounty.gov", "yolocounty.org"]),
    ("Yuba", "yuba", ["co.yuba.ca.us", "yubacounty.gov"]),
]

# Subdomain prefixes to try for each base domain
SUBDOMAIN_PREFIXES = [
    "electionstats",
    "electionstats.elections",
    "pastelections",
    "electionresults",
    "elections",
]

# Known instances (for validation — these should always be found)
KNOWN_INSTANCES = {
    "marin": "https://pastelections.marincounty.gov/api/graphql_pr",
    "san-joaquin": "https://electionstats.sjgov.org/api/graphql_pr",
    "sonoma": "https://electionstats.sonomacounty.ca.gov/api/graphql_pr",
    "yolo": "https://electionstats.elections.yolocounty.gov/api/graphql_pr",
}

# Query that matches the actual Civera API schema (year-filtered)
PROBE_QUERY = {
    "query": """
    query ProbeElections($from: Int!, $to: Int!) {
        searchSuggestions(filters: {
            global: { years: { from: $from, to: $to } }
            voterStats: false
            specialElectionsOnly: false
            stages: []
        }) {
            events { id name group count }
        }
    }
    """,
    "variables": {"from": 1990, "to": 2026},
}


def probe_url(url: str, timeout: int = 5) -> Optional[Dict]:
    """Probe a single URL for Civera GraphQL endpoint.

    Returns dict with response info if valid Civera endpoint, None otherwise.
    """
    try:
        resp = requests.post(
            url,
            json=PROBE_QUERY,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        # Civera endpoints return { data: { searchSuggestions: { events: [...] } } }
        events = (
            data.get("data", {})
            .get("searchSuggestions", {})
            .get("events", [])
        )
        if isinstance(events, list):
            return {
                "url": url,
                "election_count": len(events),
                "sample_elections": [e.get("name", "") for e in events[:3]],
            }
    except (requests.RequestException, json.JSONDecodeError, AttributeError):
        pass
    return None


def generate_urls(county_name: str, slug: str, domains: List[str]) -> List[str]:
    """Generate candidate URLs for a county."""
    urls = []
    for domain in domains:
        for prefix in SUBDOMAIN_PREFIXES:
            urls.append(f"https://{prefix}.{domain}/api/graphql_pr")
    return urls


def probe_county(
    county_name: str, slug: str, domains: List[str], timeout: int = 5, verbose: bool = False,
) -> Optional[Dict]:
    """Probe all URL candidates for a single county."""
    urls = generate_urls(county_name, slug, domains)

    for url in urls:
        if verbose:
            print(f"  Probing: {url}", file=sys.stderr)
        result = probe_url(url, timeout=timeout)
        if result:
            return {
                "county_name": county_name,
                "slug": slug,
                **result,
            }

    return None


def main():
    parser = argparse.ArgumentParser(description="Probe CA counties for Civera ElectionStats")
    parser.add_argument("--timeout", type=int, default=5, help="HTTP timeout per request (seconds)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all probed URLs")
    parser.add_argument("--parallel", type=int, default=8, help="Max parallel probes")
    parser.add_argument("--county", type=str, help="Probe a single county (slug)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    counties = CA_COUNTIES
    if args.county:
        counties = [(n, s, d) for n, s, d in counties if s == args.county]
        if not counties:
            print(f"Unknown county slug: {args.county}", file=sys.stderr)
            sys.exit(1)

    if not args.json:
        print(f"Probing {len(counties)} CA counties for Civera ElectionStats endpoints...")
        print(f"Timeout: {args.timeout}s, Parallelism: {args.parallel}")
        print()

    found = []
    not_found = []

    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        futures = {}
        for county_name, slug, domains in counties:
            future = executor.submit(
                probe_county, county_name, slug, domains, args.timeout, args.verbose,
            )
            futures[future] = (county_name, slug)

        for future in as_completed(futures):
            county_name, slug = futures[future]
            result = future.result()
            if result:
                found.append(result)
                if not args.json:
                    print(f"  FOUND: {county_name} County — {result['url']} ({result['election_count']} elections)")
            else:
                not_found.append(slug)

    if args.json:
        # Output in civera_instances.json format for easy copy
        instances = {}
        for r in sorted(found, key=lambda x: x["county_name"]):
            tenant = r["slug"].replace("-", "") + "ca"
            instances[r["slug"]] = {
                "graphql_url": r["url"],
                "tenant": tenant,
                "county_name": f"{r['county_name']} County",
            }
        output = {
            "_comment": f"Probed {len(counties)} CA counties, found {len(found)} with Civera ElectionStats",
            "instances": instances,
        }
        print(json.dumps(output, indent=2))
    else:
        print()
        print(f"=== RESULTS ===")
        print(f"Found: {len(found)} counties with Civera ElectionStats")
        print(f"Not found: {len(not_found)} counties")
        print()

        if found:
            print("Discovered instances:")
            for r in sorted(found, key=lambda x: x["county_name"]):
                graphql_url = r["url"]
                # Infer tenant from URL pattern
                domain = graphql_url.split("//")[1].split("/")[0]
                tenant = r["slug"].replace("-", "") + "ca"
                print(f'    "{r["slug"]}": {{')
                print(f'        "graphql_url": "{graphql_url}",')
                print(f'        "tenant": "{tenant}",')
                print(f'        "county_name": "{r["county_name"]} County",')
                print(f"    }},")
            print()

        # Validate known instances
        known_found = {r["slug"] for r in found}
        for slug, url in KNOWN_INSTANCES.items():
            if slug in known_found:
                print(f"  [OK] Known instance {slug} confirmed")
            else:
                print(f"  [WARN] Known instance {slug} NOT found (expected at {url})")


if __name__ == "__main__":
    main()
