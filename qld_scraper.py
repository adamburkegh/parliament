import requests
from bs4 import BeautifulSoup
import csv
import datetime
import re

URL = "https://www.parliament.qld.gov.au/Work-of-the-Assembly/Bills-and-Legislation/Bills-previous-Parliaments/57th-Parliament"
headers = {"User-Agent": "Mozilla/5.0"}

resp = requests.get(URL, headers=headers)
soup = BeautifulSoup(resp.text, "html.parser")


def bracket_date_split(entry):
    split = entry.split("(")
    if len(split) >= 2:
        x,y = split[0:2]
        x = x.strip()
        ydate = y.split(")")[0].strip()
    else:
        x,ydate = ("","")
    return x,ydate


# The bill table is inside the content area
table = soup.find("table")
rows = []

if table:
    for tr in table.find_all("tr")[1:]:  # skip header row
        tds = tr.find_all("td")
        if len(tds) >= 5:
            title = tds[0].get_text(strip=True)
            introduced = tds[3].get_text(strip=True)
            try:
                sponsor, intro_date = bracket_date_split(introduced)
            except:
                print(f"Error parsing: {introduced}")
            statusstr = tds[4].get_text(strip=True)
            status, status_date = bracket_date_split(statusstr)
            rows.append([title, "Introduced", sponsor, intro_date] )
            rows.append([title, status, sponsor, status_date] )
            if len(tds) >= 7:
                assent = tds[6].get_text(strip=True)
                if assent:
                    rows.append([title, "Assent", sponsor, assent] )



# Write to CSV
with open("qld_bills_57th.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Bill Short Title", "Status", "Sponsor", "Date"])
    writer.writerows(rows)

print("CSV file saved: qld_bills_57th.csv")

