"""
Multi-source job scraper.
Uses jobspy for LinkedIn/Indeed/Glassdoor/ZipRecruiter/Google,
custom scrapers for web3.careers, prosple, ambitionbox, seek and top company sites,
and agent sources (self-hosted Firecrawl + Stagehand browser agent) in agent_sources.py.
"""
import asyncio
import hashlib
import httpx
import re
import logging
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# Valid jobspy locations and country codes
VALID_LOCATIONS = {
    # Australia
    "sydney": "Sydney, Australia",
    "melbourne": "Melbourne, Australia",
    "brisbane": "Brisbane, Australia",
    "perth": "Perth, Australia",
    "adelaide": "Adelaide, Australia",
    "hobart": "Hobart, Australia",
    "canberra": "Canberra, Australia",
    "australia": "Australia",

    # USA
    "new york": "New York, USA",
    "san francisco": "San Francisco, USA",
    "los angeles": "Los Angeles, USA",
    "chicago": "Chicago, USA",
    "denver": "Denver, USA",
    "seattle": "Seattle, USA",
    "boston": "Boston, USA",
    "usa": "USA",
    "us": "USA",

    # Default
    "remote": "Remote",
}


def _normalize_location(location: str) -> tuple[str, str]:
    """
    Normalize a location string to a valid jobspy location and country code.
    Returns (normalized_location, country_code).
    Falls back to ("Remote", "USA") if location is invalid/empty.
    """
    if not location:
        return ("Remote", "USA")

    loc_lower = location.lower().strip()

    # Check if it's a known location
    if loc_lower in VALID_LOCATIONS:
        normalized = VALID_LOCATIONS[loc_lower]
    else:
        # Try partial matching
        matched = False
        for key, val in VALID_LOCATIONS.items():
            if key in loc_lower or loc_lower in key:
                normalized = val
                matched = True
                break

        if not matched:
            # Default to Remote for unknown locations to avoid jobspy errors
            logger.warning(f"Unknown location '{location}' — defaulting to Remote")
            normalized = "Remote"

    # Determine country code
    if "australia" in normalized.lower():
        country = "Australia"
    elif "usa" in normalized.lower():
        country = "USA"
    else:
        country = "USA"  # Default to USA

    return (normalized, country)


def _make_id(source: str, url: str) -> str:
    return hashlib.md5(f"{source}:{url}".encode()).hexdigest()


def scrape_jobspy(
    titles: list[str],
    locations: list[str],
    sources: list[str],
    results_per_source: int = 50,
    hours_old: int = 72,
) -> list[dict]:
    """Use python-jobspy to scrape LinkedIn, Indeed, Glassdoor, ZipRecruiter."""
    try:
        from jobspy import scrape_jobs
        import pandas as pd
    except ImportError:
        logger.warning("python-jobspy not installed — skipping jobspy sources")
        return []

    jobspy_site_map = {
        "linkedin": "linkedin",
        "indeed": "indeed",
        "glassdoor": "glassdoor",
        "ziprecruiter": "zip_recruiter",
        "google": "google",
    }
    sites = [jobspy_site_map[s] for s in sources if s in jobspy_site_map]
    if not sites:
        return []

    jobs = []
    for title in titles:
        for location in (locations or ["Melbourne, Australia"]):
            # Normalize location to valid jobspy format
            normalized_location, country_code = _normalize_location(location)

            # Skip "Remote" for jobspy — LinkedIn/Indeed don't handle it reliably.
            # Remote jobs are picked up via Seek and other async scrapers.
            if normalized_location == "Remote":
                logger.info(f"Skipping Remote location for jobspy ({title}) — use seek/other scrapers")
                continue

            try:
                logger.info(f"Scraping {title} @ {normalized_location} (country: {country_code})")
                df = scrape_jobs(
                    site_name=sites,
                    search_term=title,
                    location=normalized_location,
                    results_wanted=results_per_source,
                    hours_old=hours_old,
                    country_indeed=country_code,
                )
                logger.info(f"Found {len(df)} jobs for {title} @ {normalized_location}")

                for _, row in df.iterrows():
                    url = str(row.get("job_url", "")) or ""
                    jobs.append({
                        "external_id": _make_id(str(row.get("site", "")), url),
                        "title": str(row.get("title", "")),
                        "company": str(row.get("company", "")),
                        "location": str(row.get("location", "")),
                        "description": str(row.get("description", "")),
                        "url": url,
                        "source": str(row.get("site", "")),
                        "salary_min": _safe_float(row.get("min_amount")),
                        "salary_max": _safe_float(row.get("max_amount")),
                        "salary_currency": str(row.get("currency", "AUD")),
                        "job_type": str(row.get("job_type", "")),
                        "remote": bool(row.get("is_remote", False)),
                        "posted_at": _parse_date(row.get("date_posted")),
                        "is_referral_post": False,
                    })
            except Exception as e:
                logger.error(f"jobspy error for {title} @ {normalized_location}: {e}", exc_info=True)
    return jobs


async def scrape_seek(titles: list[str], locations: list[str]) -> list[dict]:
    """Scrape seek.com.au jobs."""
    jobs = []
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for title in titles:
            for location in (locations or ["All Australia"]):
                try:
                    params = {
                        "keywords": title,
                        "where": location,
                        "dateRange": "3",  # last 3 days
                        "sortmode": "ListedDate",
                    }
                    resp = await client.get("https://www.seek.com.au/jobs", params=params)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for card in soup.select('[data-automation="normalJob"]')[:20]:
                        link_el = card.select_one('[data-automation="jobTitle"]')
                        company_el = card.select_one('[data-automation="jobCompany"]')
                        loc_el = card.select_one('[data-automation="jobLocation"]')
                        if not link_el:
                            continue
                        href = link_el.get("href", "")
                        url = f"https://www.seek.com.au{href}" if href.startswith("/") else href
                        jobs.append({
                            "external_id": _make_id("seek", url),
                            "title": link_el.get_text(strip=True),
                            "company": company_el.get_text(strip=True) if company_el else "",
                            "location": loc_el.get_text(strip=True) if loc_el else location,
                            "description": "",
                            "url": url,
                            "source": "seek",
                            "remote": "remote" in (loc_el.get_text("").lower() if loc_el else ""),
                            "posted_at": datetime.utcnow(),
                            "is_referral_post": False,
                        })
                except Exception as e:
                    logger.error(f"Seek scrape error: {e}")
    return jobs


async def scrape_web3careers(titles: list[str]) -> list[dict]:
    """Scrape web3.careers for Web3/blockchain jobs."""
    jobs = []
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for title in titles:
            try:
                slug = title.lower().replace(" ", "-")
                resp = await client.get(f"https://web3.careers/{slug}-jobs")
                soup = BeautifulSoup(resp.text, "html.parser")
                for row in soup.select("tr.job_row")[:30]:
                    title_el = row.select_one(".job-title")
                    company_el = row.select_one(".company-title")
                    link_el = row.select_one("a[href]")
                    if not title_el or not link_el:
                        continue
                    href = link_el["href"]
                    url = f"https://web3.careers{href}" if href.startswith("/") else href
                    tags = [t.get_text(strip=True) for t in row.select(".tag")]
                    jobs.append({
                        "external_id": _make_id("web3careers", url),
                        "title": title_el.get_text(strip=True),
                        "company": company_el.get_text(strip=True) if company_el else "",
                        "location": "Remote",
                        "description": " ".join(tags),
                        "url": url,
                        "source": "web3careers",
                        "remote": True,
                        "posted_at": datetime.utcnow(),
                        "is_referral_post": False,
                    })
            except Exception as e:
                logger.error(f"web3.careers error: {e}")
    return jobs


async def scrape_prosple(titles: list[str], locations: list[str]) -> list[dict]:
    """Scrape prosple.com for graduate/entry-level jobs."""
    jobs = []
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for title in titles:
            try:
                params = {"q": title, "country": "australia"}
                resp = await client.get("https://prosple.com/jobs", params=params)
                soup = BeautifulSoup(resp.text, "html.parser")
                for card in soup.select(".job-card, .opportunity-card")[:20]:
                    title_el = card.select_one("h2, h3, .job-title")
                    company_el = card.select_one(".company-name, .employer")
                    link_el = card.select_one("a[href]")
                    if not title_el or not link_el:
                        continue
                    href = link_el["href"]
                    url = f"https://prosple.com{href}" if href.startswith("/") else href
                    jobs.append({
                        "external_id": _make_id("prosple", url),
                        "title": title_el.get_text(strip=True),
                        "company": company_el.get_text(strip=True) if company_el else "",
                        "location": locations[0] if locations else "Australia",
                        "description": "",
                        "url": url,
                        "source": "prosple",
                        "remote": False,
                        "posted_at": datetime.utcnow(),
                        "is_referral_post": False,
                    })
            except Exception as e:
                logger.error(f"Prosple error: {e}")
    return jobs


async def scrape_ambitionbox_referrals(titles: list[str], locations: list[str]) -> list[dict]:
    """Scrape AmbitionBox for hiring/referral posts."""
    jobs = []
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for title in titles:
            try:
                params = {"q": f"{title} referral hiring"}
                resp = await client.get("https://www.ambitionbox.com/jobs", params=params)
                soup = BeautifulSoup(resp.text, "html.parser")
                for card in soup.select(".jobCard, .job-card-wrapper")[:20]:
                    title_el = card.select_one(".jobTitle, h3")
                    company_el = card.select_one(".companyName, .company-name")
                    link_el = card.select_one("a[href]")
                    if not title_el or not link_el:
                        continue
                    href = link_el["href"]
                    url = f"https://www.ambitionbox.com{href}" if href.startswith("/") else href
                    text = card.get_text().lower()
                    is_referral = any(w in text for w in ["referral", "refer", "hiring"])
                    jobs.append({
                        "external_id": _make_id("ambitionbox", url),
                        "title": title_el.get_text(strip=True),
                        "company": company_el.get_text(strip=True) if company_el else "",
                        "location": locations[0] if locations else "",
                        "description": card.get_text(strip=True)[:500],
                        "url": url,
                        "source": "ambitionbox",
                        "remote": "remote" in text,
                        "posted_at": datetime.utcnow(),
                        "is_referral_post": is_referral,
                    })
            except Exception as e:
                logger.error(f"AmbitionBox error: {e}")
    return jobs


# ── Location-aware top companies ────────────────────────────────────────────
# Each entry: (Company Name, URL template with {title} and optionally {location})
_AU_COMPANIES: list[tuple[str, str]] = [
    # Tech giants (AU presence)
    ("Google",            "https://careers.google.com/jobs/results/?q={title}&location=Australia"),
    ("Microsoft",         "https://careers.microsoft.com/v2/global/en/search?q={title}&lc=Australia"),
    ("Apple",             "https://jobs.apple.com/en-au/search#q={title}&location=australia"),
    ("Amazon",            "https://www.amazon.jobs/en/search?base_query={title}&country%5B%5D=AUS"),
    ("Meta",              "https://www.metacareers.com/jobs/?q={title}&locations%5B0%5D=Australia"),
    ("Salesforce",        "https://careers.salesforce.com/en/jobs/?search={title}&location=Australia"),
    ("Oracle",            "https://careers.oracle.com/jobs/#en/sites/jobsearch/jobs?keyword={title}&location=Australia"),
    ("SAP",               "https://jobs.sap.com/search/?q={title}&locname=Australia"),
    ("Cisco",             "https://jobs.cisco.com/jobs/SearchJobs/{title}?21178=182571"),
    ("ServiceNow",        "https://careers.servicenow.com/careers/jobs?query={title}&location=Australia"),
    ("Snowflake",         "https://careers.snowflake.com/us/en/search-results?keywords={title}&location=Australia"),
    ("Datadog",           "https://careers.datadoghq.com/all-jobs/?search={title}&location=Australia"),
    ("CrowdStrike",       "https://careers.crowdstrike.com/us/en/search-results?keywords={title}&location=Australia"),
    ("Palo Alto Networks","https://jobs.paloaltonetworks.com/en/search/?keyword={title}&location=Australia"),
    ("Fortinet",          "https://www.fortinet.com/corporate/careers/job-search?keywords={title}&location=Australia"),
    # AU Tech companies
    ("Atlassian",         "https://www.atlassian.com/company/careers/all-jobs?search={title}&location=australia"),
    ("Canva",             "https://www.canva.com/careers/jobs/?query={title}&location=Australia"),
    ("Afterpay / Block",  "https://careers.block.xyz/jobs?q={title}&location=Australia"),
    ("Xero",              "https://www.xero.com/au/about/careers/?search={title}"),
    ("SEEK",              "https://www.seek.com.au/career-advice/company/seek/jobs?q={title}"),
    ("REA Group",         "https://www.rea-group.com/about-us/our-company/careers/?q={title}"),
    ("Domain",            "https://careers.domain.com.au/jobs?q={title}"),
    ("Culture Amp",       "https://www.cultureamp.com/company/careers?q={title}"),
    ("SafetyCulture",     "https://safetyculturecareers.com/jobs?search={title}"),
    ("Airtasker",         "https://www.airtasker.com/careers/?q={title}"),
    ("Envato",            "https://envato.com/careers/?q={title}"),
    ("MYOB",              "https://www.myob.com/au/about/careers?q={title}"),
    ("Zip Co",            "https://zip.co/careers?q={title}"),
    ("WiseTech Global",   "https://www.wisetechglobal.com/careers/?search={title}"),
    ("Nuix",              "https://www.nuix.com/careers?q={title}"),
    ("Quantium",          "https://www.quantium.com/careers/?q={title}"),
    ("Freelancer.com",    "https://www.freelancer.com/careers?q={title}"),
    ("Nearmap",           "https://www.nearmap.com/careers?q={title}"),
    ("Iress",             "https://www.iress.com/careers/?q={title}"),
    # Consulting & Professional Services
    ("Deloitte AU",       "https://apply.deloitte.com/careers/SearchJobs/{title}?3_56_3=233"),
    ("PwC AU",            "https://www.pwc.com.au/careers/search-jobs.html?keyword={title}"),
    ("KPMG AU",           "https://careers.kpmg.com.au/jobs?query={title}"),
    ("EY AU",             "https://careers.ey.com/ey/search/?q={title}&locname=Australia"),
    ("Accenture AU",      "https://www.accenture.com/au-en/careers/jobsearch?query={title}&country=Australia"),
    ("IBM AU",            "https://www.ibm.com/au-en/employment/newhire/?q={title}&location=Australia"),
    ("McKinsey AU",       "https://www.mckinsey.com/careers/search-jobs#q={title}&location=Australia"),
    # Banking & Finance
    ("Commonwealth Bank", "https://www.commbank.com.au/about-us/careers/search-for-jobs.html?q={title}"),
    ("ANZ",               "https://careers.anz.com/search/?q={title}&locname=Australia"),
    ("Westpac",           "https://careers.westpac.com.au/search/?q={title}"),
    ("NAB",               "https://www.nab.com.au/about-us/careers/find-a-career?q={title}"),
    ("Macquarie Group",   "https://careers.macquarie.com/us/en/search-results?keywords={title}&location=Australia"),
    ("AMP",               "https://www.amp.com.au/careers?q={title}"),
    ("Suncorp",           "https://careers.suncorp.com.au/jobs?q={title}"),
    ("IAG",               "https://careers.iag.com.au/search/?q={title}"),
    ("QBE Insurance",     "https://careers.qbe.com/global/en/search-results?keywords={title}&location=Australia"),
    ("Medibank",          "https://careers.medibank.com.au/jobs?q={title}"),
    # Telco
    ("Telstra",           "https://careers.telstra.com/job-search?keyword={title}"),
    ("Optus",             "https://www.optus.com.au/about/careers?q={title}"),
    ("TPG Telecom",       "https://www.tpgtelecom.com.au/careers?q={title}"),
    # Retail & E-commerce
    ("Woolworths",        "https://careers.woolworthsgroup.com.au/search/?q={title}"),
    ("Coles",             "https://recruitment.coles.com.au/corporate/search/?q={title}"),
    ("Wesfarmers",        "https://www.wesfarmers.com.au/careers?q={title}"),
    # Government & Defence
    ("Defence AU",        "https://www.defence.gov.au/jobs-careers/find-a-job?query={title}"),
    ("ATO",               "https://www.ato.gov.au/about-ato/careers?q={title}"),
    ("Services Australia","https://www.servicesaustralia.gov.au/careers?q={title}"),
    # Healthcare
    ("CSL Behring",       "https://careers.csl.com/job-search?q={title}&location=Australia"),
    ("Ramsay Health",     "https://www.ramsayhealth.com/careers?q={title}"),
    ("Sonic Healthcare",  "https://careers.sonichealthcare.com/jobs?q={title}&location=Australia"),
]

_US_COMPANIES: list[tuple[str, str]] = [
    # Big Tech
    ("Google",            "https://careers.google.com/jobs/results/?q={title}&location=United+States"),
    ("Microsoft",         "https://careers.microsoft.com/v2/global/en/search?q={title}&lc=United+States"),
    ("Apple",             "https://jobs.apple.com/en-us/search#q={title}"),
    ("Amazon",            "https://www.amazon.jobs/en/search?base_query={title}&country%5B%5D=US"),
    ("Meta",              "https://www.metacareers.com/jobs/?q={title}&locations%5B0%5D=United+States"),
    ("Netflix",           "https://jobs.netflix.com/search?q={title}"),
    ("Nvidia",            "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/jobs?q={title}"),
    ("Tesla",             "https://www.tesla.com/careers/search/job?query={title}&site=US"),
    ("Intel",             "https://jobs.intel.com/en/search-jobs/{title}/37784"),
    ("AMD",               "https://careers.amd.com/careers-home/jobs?keywords={title}&location=United+States"),
    ("Qualcomm",          "https://careers.qualcomm.com/careers/search?keyword={title}&location=United+States"),
    # Enterprise Tech
    ("Salesforce",        "https://careers.salesforce.com/en/jobs/?search={title}&location=United+States"),
    ("Oracle",            "https://careers.oracle.com/jobs/#en/sites/jobsearch/jobs?keyword={title}&location=United+States"),
    ("SAP",               "https://jobs.sap.com/search/?q={title}&locname=United+States"),
    ("Cisco",             "https://jobs.cisco.com/jobs/SearchJobs/{title}?21178=175563"),
    ("ServiceNow",        "https://careers.servicenow.com/careers/jobs?query={title}&location=United+States"),
    ("Snowflake",         "https://careers.snowflake.com/us/en/search-results?keywords={title}&location=United+States"),
    ("Datadog",           "https://careers.datadoghq.com/all-jobs/?search={title}&location=United+States"),
    ("Stripe",            "https://stripe.com/jobs/search?query={title}"),
    ("Airbnb",            "https://careers.airbnb.com/positions/?q={title}"),
    ("Uber",              "https://www.uber.com/us/en/careers/jobs/?query={title}"),
    ("Lyft",              "https://www.lyft.com/careers?q={title}"),
    ("Shopify",           "https://www.shopify.com/careers/search?query={title}"),
    ("Twilio",            "https://careers.twilio.com/jobs?q={title}"),
    ("CrowdStrike",       "https://careers.crowdstrike.com/us/en/search-results?keywords={title}"),
    ("Palo Alto Networks","https://jobs.paloaltonetworks.com/en/search/?keyword={title}"),
    ("IBM",               "https://www.ibm.com/us-en/employment/newhire/?q={title}"),
    ("Atlassian",         "https://www.atlassian.com/company/careers/all-jobs?search={title}&location=united-states"),
    # Finance
    ("JPMorgan Chase",    "https://careers.jpmorgan.com/global/en/job-search/results?q={title}&location=United+States"),
    ("Goldman Sachs",     "https://higher.gs.com/roles?q={title}&location=United+States"),
    ("Morgan Stanley",    "https://morganstanley.tal.net/vx/lang-en-GB/mobile-0/appcentre-1/brand-2/xf-a25ef56f7e18/candidate/jobboard/vacancy/3/adv/?q={title}"),
    ("Citi",              "https://jobs.citi.com/jobs?q={title}&location=United+States"),
    ("BlackRock",         "https://careers.blackrock.com/jobs?q={title}&location=United+States"),
    # Consulting
    ("McKinsey",          "https://www.mckinsey.com/careers/search-jobs#q={title}"),
    ("Deloitte US",       "https://apply.deloitte.com/careers/SearchJobs/{title}"),
    ("Accenture US",      "https://www.accenture.com/us-en/careers/jobsearch?query={title}&country=United+States"),
    # Healthcare / Biotech
    ("Johnson & Johnson", "https://jobs.jnj.com/jobs?q={title}&location=United+States"),
    ("Pfizer",            "https://www.pfizer.com/careers/jobs?q={title}&location=United+States"),
    ("Moderna",           "https://modernatx.com/careers/jobs?q={title}"),
]

# Default fallback (remote / global)
_GLOBAL_COMPANIES: list[tuple[str, str]] = [
    ("Google",        "https://careers.google.com/jobs/results/?q={title}"),
    ("Microsoft",     "https://careers.microsoft.com/v2/global/en/search?q={title}"),
    ("Amazon",        "https://www.amazon.jobs/en/search?base_query={title}"),
    ("Meta",          "https://www.metacareers.com/jobs/?q={title}"),
    ("Atlassian",     "https://www.atlassian.com/company/careers/all-jobs?search={title}"),
    ("Shopify",       "https://www.shopify.com/careers/search?query={title}"),
    ("GitLab",        "https://about.gitlab.com/jobs/all-jobs/?search={title}"),
    ("Stripe",        "https://stripe.com/jobs/search?query={title}"),
]


def _get_companies_for_locations(locations: list[str]) -> list[tuple[str, str]]:
    """Return the appropriate top-company list based on user's preferred locations."""
    locs_lower = " ".join(l.lower() for l in (locations or []))
    is_au = any(k in locs_lower for k in ("australia", "melbourne", "sydney", "brisbane",
                                           "perth", "adelaide", "hobart", "canberra"))
    is_us = any(k in locs_lower for k in ("usa", "us", "united states", "new york",
                                           "san francisco", "los angeles", "chicago",
                                           "seattle", "boston", "denver"))
    if is_au and is_us:
        return _AU_COMPANIES + _US_COMPANIES
    if is_au:
        return _AU_COMPANIES
    if is_us:
        return _US_COMPANIES
    return _GLOBAL_COMPANIES


def get_top_company_urls(titles: list[str], locations: list[str] | None = None) -> list[dict]:
    """Return apply URLs for top companies for given job titles and location."""
    companies = _get_companies_for_locations(locations or [])
    results = []
    for company, url_template in companies:
        for title in titles[:3]:  # limit to first 3 titles
            url = url_template.format(title=title.replace(" ", "+"))
            results.append({
                "external_id": _make_id(company.lower(), url),
                "title": title,
                "company": company,
                "location": "Various",
                "description": f"Search for {title} at {company}",
                "url": url,
                "source": "top_companies",
                "remote": True,
                "posted_at": datetime.utcnow(),
                "is_referral_post": False,
                "match_score": None,
            })
    return results


async def run_all_scrapers(
    titles: list[str],
    locations: list[str],
    keywords: list[str],
    sources: list[str],
    hours_old: int = 72,
) -> list[dict]:
    """Run all scrapers concurrently and deduplicate results."""
    all_jobs: list[dict] = []

    # jobspy (sync) — run in thread
    loop = asyncio.get_event_loop()
    jobspy_jobs = await loop.run_in_executor(
        None, scrape_jobspy, titles, locations, sources, 50, hours_old
    )
    all_jobs.extend(jobspy_jobs)

    # async scrapers
    tasks = []
    if "seek" in sources:
        tasks.append(scrape_seek(titles, locations))
    if "web3careers" in sources:
        tasks.append(scrape_web3careers(titles))
    if "prosple" in sources:
        tasks.append(scrape_prosple(titles, locations))
    if "ambitionbox" in sources:
        tasks.append(scrape_ambitionbox_referrals(titles, locations))

    # Agent sources: self-hosted Firecrawl + Stagehand browser agent
    if "firecrawl" in sources:
        from agent.scrapers.agent_sources import firecrawl_job_search
        tasks.append(firecrawl_job_search(titles, locations, keywords))
    if "agent_browser" in sources:
        from agent.scrapers.agent_sources import agent_browser_job_search
        tasks.append(agent_browser_job_search(titles, locations))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)
        elif isinstance(r, Exception):
            logger.error(f"Scraper task failed: {r}")

    if "top_companies" in sources:
        all_jobs.extend(get_top_company_urls(titles, locations=locations))

    # deduplicate by external_id
    seen = set()
    unique = []
    for j in all_jobs:
        eid = j.get("external_id", "")
        if eid and eid not in seen:
            seen.add(eid)
            unique.append(j)

    logger.info(f"Total jobs scraped: {len(unique)}")
    return unique


def _safe_float(val) -> Optional[float]:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _parse_date(val) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None
