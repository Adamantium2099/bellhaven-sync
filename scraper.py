import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import BASE_URL


COMMUNITIES_URL = f"{BASE_URL}/communities"
DATA_DIR = Path("data")
WEBSITE_SNAPSHOT = DATA_DIR / "website_facilities.json"


def clean_text(value):
    if not value:
        return ""
    return " ".join(value.split())


def get_soup(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def extract_community_urls(soup):
    """Extract unique Bellhaven community-detail URLs from a page."""
    return {
        urljoin(BASE_URL, link.get("href"))
        for link in soup.find_all("a", href=True)
        if re.fullmatch(
            r"/communities/[^/?#]+",
            link.get("href", ""),
        )
    }


def discover_community_urls():
    """
    Discover communities from both the paginated directory and homepage.

    The homepage can contain newly announced facilities that have not yet
    been added to the directory, so relying on the directory alone can miss
    current Bellhaven locations.
    """
    community_urls = set()

    # Crawl every page in the formal community directory.
    page = 1

    while True:
        url = (
            COMMUNITIES_URL
            if page == 1
            else f"{COMMUNITIES_URL}?page={page}"
        )

        soup = get_soup(url)
        page_urls = extract_community_urls(soup)

        new_urls = page_urls - community_urls

        if not new_urls:
            break

        community_urls.update(new_urls)
        page += 1

    # Cross-check the homepage for newly announced community links.
    homepage = get_soup(BASE_URL)
    community_urls.update(
        extract_community_urls(homepage)
    )

    return sorted(community_urls)


def find_field_value_node(soup, label):
    """Locate the value element associated with a detail-page label."""
    label_node = soup.find(
        lambda tag:
        tag.name in ["div", "dt", "p", "span"]
        and clean_text(
            tag.get_text(" ", strip=True)
        ).lower() == label.lower()
    )

    if not label_node:
        return None

    sibling = label_node.find_next_sibling()

    if sibling:
        return sibling

    return None


def extract_field(soup, label):
    """Extract an ordinary single-value detail field."""
    value_node = find_field_value_node(soup, label)

    if value_node:
        return clean_text(
            value_node.get_text(" ", strip=True)
        )

    return ""


def extract_address(soup):
    """
    Extract address components while preserving HTML line boundaries.

    Expected website representation:
        1800 N Blanchard St
        Findlay, OH 45840
    """
    value_node = find_field_value_node(soup, "Address")

    if not value_node:
        return {
            "address": "",
            "city": "",
            "state": "",
            "zip": "",
            "raw_address": "",
        }

    raw_with_lines = value_node.get_text(
        "\n",
        strip=True,
    )

    lines = [
        clean_text(line)
        for line in raw_with_lines.splitlines()
        if clean_text(line)
    ]

    raw_address = clean_text(
        value_node.get_text(" ", strip=True)
    )

    # Preferred structure: street line + city/state/ZIP line.
    if len(lines) >= 2:
        street = lines[0]
        locality = " ".join(lines[1:])

        match = re.match(
            r"^(.*?),\s*([A-Z]{2})\s+"
            r"(\d{5}(?:-\d{4})?)$",
            locality,
        )

        if match:
            return {
                "address": street,
                "city": clean_text(match.group(1)),
                "state": match.group(2),
                "zip": match.group(3),
                "raw_address": raw_address,
            }

    # Fallback for unexpected formatting.
    match = re.match(
        r"^(.*?)\s+([^,]+),\s*([A-Z]{2})\s+"
        r"(\d{5}(?:-\d{4})?)$",
        raw_address,
    )

    if match:
        return {
            "address": clean_text(match.group(1)),
            "city": clean_text(match.group(2)),
            "state": match.group(3),
            "zip": match.group(4),
            "raw_address": raw_address,
        }

    return {
        "address": raw_address,
        "city": "",
        "state": "",
        "zip": "",
        "raw_address": raw_address,
    }


def scrape_community(url):
    soup = get_soup(url)

    h1 = soup.find("h1")
    name = (
        clean_text(h1.get_text(" ", strip=True))
        if h1
        else ""
    )

    address = extract_address(soup)

    care_raw = extract_field(
        soup,
        "Care Offerings",
    )

    care_offerings = [
        clean_text(item)
        for item in re.split(
            r"[,|;/]",
            care_raw,
        )
        if clean_text(item)
    ]

    return {
        "name": name,
        "address": address["address"],
        "city": address["city"],
        "state": address["state"],
        "zip": address["zip"],
        "raw_address": address["raw_address"],
        "care_offerings": care_offerings,
        "administrator": extract_field(
            soup,
            "Administrator",
        ),
        "phone": extract_field(
            soup,
            "Phone",
        ),
        "source_url": url,
    }


def scrape_all_communities():
    urls = discover_community_urls()

    return [
        scrape_community(url)
        for url in urls
    ]


def save_snapshot(facilities):
    DATA_DIR.mkdir(exist_ok=True)

    with WEBSITE_SNAPSHOT.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            facilities,
            file,
            indent=2,
            ensure_ascii=False,
        )


def main():
    facilities = scrape_all_communities()
    save_snapshot(facilities)

    print(
        f"Bellhaven website facilities scraped: "
        f"{len(facilities)}"
    )

    print(
        f"Snapshot saved to: "
        f"{WEBSITE_SNAPSHOT}"
    )

    print()

    for facility in facilities:
        print(
            f"{facility['name']} | "
            f"{facility['address']} | "
            f"{facility['city']}, "
            f"{facility['state']} "
            f"{facility['zip']} | "
            f"{', '.join(facility['care_offerings'])}"
        )


if __name__ == "__main__":
    main()