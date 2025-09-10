# MtA Alumni LinkedIn Scraping

![License: MIT](https://img.shields.io/badge/License-MIT-pink.svg)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-rebeccapurple.svg)](https://github.com/astral-sh/ruff)

The `main.py` script dynamically scrapes LinkedIn for Mount Allison University (MtA) alumni data using Selenium. The schema for each alum (using Polars data types) is as follows:

- full_name: String
- latest_title: String
- latest_company: String
- mta_degree: String
- mta_grad_year: UInt16
- location: String
- profile_url: String

(If an alum has multiple education entries for MtA—say, a Bachelor's followed by a Master's—only the most recent degree is listed. Listed "alumni" with no graduation year or with a graduation year later than the current year are excluded, as these may be current students.) The structured data is then saved to the `mta_alumni.csv` file (a sample file from a custom run is provided in this repository). Profile URLs collected in the initial phase of the scraping process are also saved to a temporary text file in a `temp/` directory, just in case the account is flagged and banned by LinkedIn midway through the scraping process (or any other error is thrown).

This script was created at the behest of MtA's Recruitment and Admissions Coordinator, Curtis Michaelis, for data analysis by the Recruitment and Admissions Office. To run it yourself, you must have Firefox installed and the GeckoDriver executable available in your system `PATH`. You must also specify the following command-line arguments in the given order:

1. the email address associated with their LinkedIn account;
2. the password for their LinkedIn account; and
3. the maximum number of times to click the "Show more results" button on the alumni page (each click loads approximately 15 to 20 additional profiles).

(DISCLAIMER: There is always the risk that your LinkedIn account may be flagged and banned should you use this script. I have taken reasonable measures to mimic human behavior, but I cannot guarantee foolproof undetectability.)
