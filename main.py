"""
This script dynamically scrapes LinkedIn for Mount Allison University (MtA) alumni data
using Selenium. The schema for each alum (using Polars data types) is as follows:

- full_name: String
- latest_title: String
- latest_company: String
- mta_degree: String
- mta_grad_year: UInt16
- location: String
- profile_url: String

(If an alum has multiple education entries for MtA—say, a Bachelor's followed by a
Master's—only the most recent degree is listed. Listed "alumni" with no graduation year
or with a graduation year later than the current year are excluded, as these may be
current students.) The structured data is then saved to the `mta_alumni.csv` file.
Profile URLs collected in the initial phase of the scraping process are also saved to a
temporary text file in a `temp/` directory, just in case the account is flagged and
banned by LinkedIn midway through the scraping process (or any other error is thrown).

This script was created at the behest of MtA's Recruitment and Admissions Coordinator,
Curtis Michaelis, for data analysis by the Recruitment and Admissions Office. To run it
yourself, you must have Firefox installed and the GeckoDriver executable available in
your system `PATH`. You must also specify the following command-line arguments in the
given order:

1. the email address associated with their LinkedIn account;
2. the password for their LinkedIn account; and
3. the maximum number of times to click the "Show more results" button on the alumni
   page (each click loads approximately 15 to 20 additional profiles).

(DISCLAIMER: There is always the risk that your LinkedIn account may be flagged and
banned should you use this script. I have taken reasonable measures to mimic human
behavior, but I cannot guarantee foolproof undetectability.)

Author: Luis M. B. Varona
Title: MtA Alumni LinkedIn Scraping
Date: September 10, 2025
Email: lm.varona@outlook.com
"""

# %%
import random
import re

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from sys import argv
from time import sleep
from uuid import uuid4

import polars as pl

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement


# %%
DEST = "mta_alumni.csv"
TEMP_DIR = "temp"
BATCH_SIZE = 5
CURRENT_YEAR = datetime.now().year

MIN_SHORT_WAIT: float = 0.1
MAX_SHORT_WAIT: float = 0.4
MIN_MEDIUM_WAIT: int = 2
MAX_MEDIUM_WAIT: int = 4
MIN_LONG_WAIT: int = 4
MAX_LONG_WAIT: int = 8

MIN_CLICKS_LONG_WAIT: int = 10
MAX_CLICKS_LONG_WAIT: int = 20

MIN_SCROLL_STEP: int = 50
MAX_SCROLL_STEP: int = 200

MIN_SHORT_SCROLL_DELAY: float = 0.05
MAX_SHORT_SCROLL_DELAY: float = 0.1
MIN_LONG_SCROLL_LONG_DELAY: float = 0.2
MAX_LONG_SCROLL_LONG_DELAY: float = 0.4

MIN_SCROLLS_LONG_DELAY: int = 3
MAX_SCROLLS_LONG_DELAY: int = 12

MIN_PARTIAL_SCROLL: float = 0.6
MAX_PARTIAL_SCROLL: float = 0.8

MIN_RANDOM_SCROLL: float = 0.2
MAX_RANDOM_SCROLL: float = 0.8

MAX_BUTTON_OFFSET: int = 5


# %%
@dataclass
class AlumniProfile:
    full_name: str
    latest_title: str | None
    latest_company: str | None
    mta_degree: str | None
    mta_grad_year: int
    location: str
    profile_url: str


# %%
def main() -> None:
    email = argv[1]
    password = argv[2]
    max_clicks = int(argv[3])

    alumni_profiles = []

    with webdriver.Firefox(get_stealth_options()) as driver:
        sign_in_linkedin(driver, email, password)
        show_more_alumni(driver, max_clicks)
        profile_urls = get_profile_urls(driver)

        temp_dir = Path(TEMP_DIR)
        temp_dir.mkdir(exist_ok=True)
        temp_file = temp_dir / f"profile_urls_{uuid4().hex}.txt"

        with open(temp_file, "w") as f:
            f.write("\n".join(profile_urls))
            f.write("\n")

        for ct, url in enumerate(profile_urls, 1):
            alumni_profile = scrape_profile(driver, url)
            mta_grad_year = alumni_profile.mta_grad_year

            if mta_grad_year is not None and mta_grad_year <= CURRENT_YEAR:
                alumni_profiles.append(alumni_profile)

            if ct % BATCH_SIZE == 0:
                df = profiles_to_df(alumni_profiles)
                alumni_profiles.clear()

                if ct == BATCH_SIZE:
                    df.write_csv(DEST)
                else:
                    append_to_csv(df, DEST)

        if alumni_profiles:
            append_to_csv(profiles_to_df(alumni_profiles), DEST)


# %%
def get_stealth_options() -> webdriver.FirefoxOptions:
    options = webdriver.FirefoxOptions()
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    options.set_preference("media.peerconnection.enabled", False)
    options.set_preference(
        "general.useragent.override",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36",
    )

    return options


# %%
def wait(long: bool = False) -> None:
    if long:
        min_wait, max_wait = MIN_LONG_WAIT, MAX_LONG_WAIT
    else:
        min_wait, max_wait = MIN_MEDIUM_WAIT, MAX_MEDIUM_WAIT

    sleep(random.uniform(min_wait, max_wait))


def scroll_delay(long: bool = False) -> None:
    if long:
        min_wait, max_wait = MIN_LONG_SCROLL_LONG_DELAY, MAX_LONG_SCROLL_LONG_DELAY
    else:
        min_wait, max_wait = MIN_SHORT_SCROLL_DELAY, MAX_SHORT_SCROLL_DELAY

    sleep(random.uniform(min_wait, max_wait))


def human_click(driver: webdriver.Firefox, element: WebElement) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    actions = ActionChains(driver)
    offset_x = random.randint(-1 * MAX_BUTTON_OFFSET, MAX_BUTTON_OFFSET)
    offset_y = random.randint(-1 * MAX_BUTTON_OFFSET, MAX_BUTTON_OFFSET)
    actions.move_to_element_with_offset(element, offset_x, offset_y)
    actions.pause(random.uniform(MIN_SHORT_WAIT, MAX_SHORT_WAIT))
    actions.click()
    actions.perform()


def smooth_scroll(driver: webdriver.Firefox, offset: int) -> None:
    scrolled = 0
    scrolls = 0
    scrolls_long_delay = random.randint(MIN_SCROLLS_LONG_DELAY, MAX_SCROLLS_LONG_DELAY)

    while scrolled < offset:
        scrolls += 1

        if scrolls % scrolls_long_delay == 0:
            long = True
        else:
            long = False

        scroll_delay(long)
        step = random.randint(MIN_SCROLL_STEP, MAX_SCROLL_STEP)
        step = min(step, offset - scrolled)
        driver.execute_script(f"window.scrollBy(0, {step});")
        scrolled += step


# %%
def sign_in_linkedin(driver: webdriver.Firefox, email: str, password: str) -> None:
    wait()
    source_login = "https://www.linkedin.com/login"
    driver.get(source_login)

    wait()
    email_field = driver.find_element(By.ID, "username")
    email_field.send_keys(email)

    wait()
    password_field = driver.find_element(By.ID, "password")
    password_field.send_keys(password)

    sign_in_selector = "/html/body/div[1]/main/div[2]/div[1]/form/div[4]/button"
    sign_in_button = driver.find_element(By.XPATH, sign_in_selector)
    human_click(driver, sign_in_button)


# %%
def show_more_alumni(driver: webdriver.Firefox, max_clicks: int) -> None:
    wait(True)
    source_alumni = "https://www.linkedin.com/school/mount-allison-university/people/"
    driver.get(source_alumni)

    show_more_selector = "//button[contains(@class, 'scaffold-finite-scroll__load-button') and span[text()='Show more results']]"
    more_results = True
    clicks = 0
    clicks_long_wait = random.randint(MIN_CLICKS_LONG_WAIT, MAX_CLICKS_LONG_WAIT)

    while more_results and clicks < max_clicks:
        clicks += 1

        try:
            wait()
            page_height = driver.execute_script("return document.body.scrollHeight")
            scrolled = driver.execute_script("return window.scrollY")

            if random.choice([False, True]):
                offset = page_height
            else:
                offset = random.randint(
                    int(MIN_PARTIAL_SCROLL * page_height),
                    int(MAX_PARTIAL_SCROLL * page_height),
                )

            smooth_scroll(driver, offset - scrolled)

            if clicks % clicks_long_wait == 0:
                long = True
                clicks_long_wait = random.randint(
                    MIN_CLICKS_LONG_WAIT, MAX_CLICKS_LONG_WAIT
                )
            else:
                long = False

            wait(long)
            show_more_button = driver.find_element(By.XPATH, show_more_selector)
            human_click(driver, show_more_button)
        except NoSuchElementException:
            more_results = False


# %%
def get_profile_urls(driver: webdriver.Firefox) -> set[str]:
    soup = BeautifulSoup(driver.page_source, "html.parser")
    profile_urls = set()

    for tag in soup.select("a[href^='https://www.linkedin.com/in/']"):
        pot_profile_url = tag["href"]

        if pot_profile_url.startswith("https://www.linkedin.com/in/"):
            profile_url = pot_profile_url.split("?")[0]
            profile_urls.add(profile_url)

    return profile_urls


# %%
def scrape_profile(driver: webdriver.Firefox, profile_url: str) -> AlumniProfile:
    wait(random.choice([False, True]))
    driver.get(profile_url)

    wait()
    soup = BeautifulSoup(driver.page_source, "html.parser")

    if random.choice([False, True]):
        page_height = driver.execute_script("return document.body.scrollHeight")
        target = random.randint(
            int(MIN_RANDOM_SCROLL * page_height), int(MAX_RANDOM_SCROLL * page_height)
        )
        smooth_scroll(driver, target)

    full_name = get_full_name(soup)
    latest_title, latest_company = get_latest_employment(soup)
    mta_degree, mta_grad_year = get_mta_education(soup)
    location = get_location(soup)

    return AlumniProfile(
        full_name=full_name,
        latest_title=latest_title,
        latest_company=latest_company,
        mta_degree=mta_degree,
        mta_grad_year=mta_grad_year,
        location=location,
        profile_url=profile_url,
    )


def get_full_name(soup: BeautifulSoup) -> str:
    return soup.find("h1").get_text(strip=True)


def get_latest_employment(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    def _parse_end_date_from_text(text: str) -> tuple[int, int]:
        left = text.split("·", 1)[0].strip()

        if re.search(r"\bpresent\b", left, re.IGNORECASE):
            year = CURRENT_YEAR + 1
            month = 12
        else:
            full_match = re.findall(r"([A-Za-z]{3,9})\s+(\d{4})", left)

            if full_match:
                month_str, year_str = full_match[-1]
                months = {
                    "jan": 1,
                    "feb": 2,
                    "mar": 3,
                    "apr": 4,
                    "may": 5,
                    "jun": 6,
                    "jul": 7,
                    "aug": 8,
                    "sep": 9,
                    "oct": 10,
                    "nov": 11,
                    "dec": 12,
                }
                year = int(year_str)
                month = months[month_str[:3].lower()]
            else:
                year = int(re.findall(r"\d{4}", left)[-1])
                month = 0

        return year, month

    experience_section = None

    for section in soup.select("section.artdeco-card"):
        header = section.select_one("h2 span[aria-hidden='true']")

        if header and "Experience" in header.get_text(strip=True):
            experience_section = section
            break

    latest_title = None
    latest_company = None

    if experience_section:
        roles = []

        for exp in experience_section.select("li.artdeco-list__item"):
            role_lis = [
                li
                for li in exp.select("ul li")
                if li.select_one('[data-view-name="profile-component-entity"]')
            ]

            if role_lis:
                company_tag = exp.select_one(
                    "div.display-flex.align-items-center.mr1.hoverable-link-text.t-bold > span[aria-hidden='true']"
                )
                company_text = company_tag.get_text(strip=True)

                for role in role_lis:
                    title_tag = role.select_one(
                        "div.display-flex.align-items-center.mr1.hoverable-link-text.t-bold > span[aria-hidden='true']"
                    ) or role.select_one("span[aria-hidden='true']")
                    date_tag = role.select_one("span.pvs-entity__caption-wrapper")

                    if title_tag:
                        title_text = title_tag.get_text(strip=True)
                        end_year, end_month = _parse_end_date_from_text(
                            date_tag.get_text(strip=True)
                        )

                        roles.append(
                            {
                                "title": title_text,
                                "company": company_text,
                                "end_year": end_year,
                                "end_month": end_month,
                            }
                        )
            else:
                title_tag = exp.select_one(
                    "div.display-flex.align-items-center.mr1.hoverable-link-text.t-bold > span[aria-hidden='true']"
                ) or exp.select_one("span[aria-hidden='true']")

                if title_tag:
                    company_tag = exp.select_one(
                        "span.t-14.t-normal > span[aria-hidden='true']"
                    )
                    date_tag = exp.select_one("span.pvs-entity__caption-wrapper")

                    title_text = title_tag.get_text(strip=True)
                    company_text = company_tag.get_text(strip=True)
                    date_text = date_tag.get_text(strip=True)
                    end_year, end_month = _parse_end_date_from_text(date_text)

                    roles.append(
                        {
                            "title": title_text,
                            "company": company_text,
                            "end_year": end_year,
                            "end_month": end_month,
                        }
                    )

        if roles:
            for r in roles:
                r["company"] = r["company"].rsplit("·", 1)[0].strip()

            roles.sort(key=lambda r: (r["end_year"], r["end_month"]), reverse=True)
            newest = roles[0]
            latest_title = newest["title"]
            latest_company = newest["company"]

    return latest_title, latest_company


def get_mta_education(soup: BeautifulSoup) -> tuple[str | None, int]:
    mta_degree = None
    mta_grad_year = None
    edu_section = None

    for section in soup.select("section.artdeco-card"):
        label = section.select_one("h2.pvs-header__title span[aria-hidden='true']")

        if label and label.get_text(strip=True) == "Education":
            edu_section = section
            break

    if edu_section:
        for edu in edu_section.select("li.artdeco-list__item"):
            school_tag = edu.select_one(
                "div.display-flex.align-items-center.mr1 span[aria-hidden='true']"
            )

            if school_tag and "Mount Allison University" in school_tag.get_text(
                strip=True
            ):
                degree_tag = edu.select_one(
                    "span.t-14.t-normal:not(.t-black--light) span[aria-hidden='true']"
                )

                if degree_tag:
                    mta_degree = degree_tag.get_text(strip=True)

                years_tag = edu.select_one(
                    "span.t-14.t-normal.t-black--light span.pvs-entity__caption-wrapper"
                )

                if years_tag:
                    years_text = years_tag.get_text(strip=True)
                    match = re.findall(r"\d{4}", years_text)

                    if match:
                        mta_grad_year = int(match[-1])

                break

    return mta_degree, mta_grad_year


def get_location(soup: BeautifulSoup) -> str:
    location_tag = soup.select_one(
        "span.text-body-small.inline.t-black--light.break-words"
    )

    return location_tag.get_text(strip=True)


# %%
def profiles_to_df(profiles: list[AlumniProfile]) -> pl.DataFrame:
    df = pl.DataFrame([profile.__dict__ for profile in profiles])
    return df.with_columns(pl.col("mta_grad_year").cast(pl.UInt16))


def append_to_csv(df: pl.DataFrame, dest: str) -> None:
    with open(dest, "a") as f:
        df.write_csv(f, include_header=False)


# %%
if __name__ == "__main__":
    main()
