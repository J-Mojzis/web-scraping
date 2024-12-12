#!/usr/bin/env python
# coding: utf-8

# ## 1. Bibliotheken und Setup

# In[1]:


#load libraries
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pandas as pd
from datetime import datetime, timedelta
import time
import random
import pickle
import re
import requests
import csv
import json


# In[2]:


# Initialize Chrome Options
options = webdriver.ChromeOptions()
options.add_argument("--headless")  # Run in headless mode
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})  # Disable images


# In[3]:


# Configure Chrome anti-bot measures
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)
options.add_argument("--disable-blink-features=AutomationControlled")


# In[4]:


# Initialize WebDriver with Chrome options
driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()), 
    options=options
)


# In[5]:


# Define paths for cookies and initial URLs
cookie_file_path = "cookies.pkl"
base_url = "https://finance.yahoo.com/"
sectors_url = "https://finance.yahoo.com/sectors/basic-materials/"


# In[6]:


# Retry function for operations
def retry_operation(func, retries=3, delay=5, *args, **kwargs):
    '''
    Retries a function multiple times in case of failure, with a delay between attempts.
    input:
        - func: The function to be executed.
        - retries: Number of retry attempts (default: 3).
        - delay: Time (in seconds) between retry attempts (default: 5).
        - *args, **kwargs: Arguments and keyword arguments for the function `func`.
    output:
        - Returns the output of the function `func` if successful, otherwise None after exhausting retries.
    '''
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(delay)
    print("Operation failed after retries.")
    return None


# ## 2. Cookie Management

# In[7]:


# Save cookies function
def save_cookies(driver, path):
    '''
    Save browser cookies to a file for session reuse.
    input:
        - driver: Selenium WebDriver instance.
        - path: File path (string) to save the cookies (e.g., "cookies.pkl").
    output:
        - None. Saves cookies to the specified file.
    '''
    with open(path, "wb") as file:
        pickle.dump(driver.get_cookies(), file)


# In[8]:


# Load cookies function with domain check
def load_cookies(driver, path):
    '''
    Load browser cookies from a file to restore a session.
    input:
        - driver: Selenium WebDriver instance.
        - path: File path (string) from which cookies are loaded (e.g., "cookies.pkl").
    output:
        - Boolean: True if cookies are loaded successfully, False otherwise.
    '''
    try:
        with open(path, "rb") as file:
            cookies = pickle.load(file)
            for cookie in cookies:
                if "domain" in cookie and cookie["domain"] in driver.current_url:
                    driver.add_cookie(cookie)
            return True
    except FileNotFoundError:
        return False


# ## 3. Frontend: Industry and Quote Link Extraction

# In[9]:


# Initialize an empty list to hold industry names
industry_names = []

def gather_industry_names(driver):
    '''
    Collects the names of industries listed on the Yahoo Finance sector page.
    input:
        - driver: Selenium WebDriver instance, already on the sector page.
    output:
        - None. Populates the global list `industry_names` with extracted industry names.
    '''
    global industry_names
    # Reload sectors page if not on it
    if driver.current_url != sectors_url:
        print("Returning to sectors page...")
        driver.get(sectors_url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tr.yf-k3njn8"))
        )
        time.sleep(1)  # Short delay for additional page loading

    # Select industry rows after page load
    industry_rows = driver.find_elements(By.CSS_SELECTOR, "tr.yf-k3njn8")
    print(f"Found {len(industry_rows)} industries.")

    # Extract and clean names of the first 10 industries
    industry_names = [
        row.find_element(By.CSS_SELECTOR, "td.name").text for row in industry_rows[2:len(industry_rows)]#2:
    ]
    print("Collected industry names:", industry_names)


# In[10]:


def generate_urls():
    '''
    Generates URLs for industries based on their names.
    input:
        - None. Uses the global list `industry_names` (populated by `gather_industry_names`).
    output:
        - List of URLs (strings) pointing to individual industry pages.
    '''
    # Generate URLs using industry names, replacing spaces with dashes and removing '&'
    updated_urls = [
        sectors_url + name.lower().replace('&', '').replace(' ', '-').replace('--', '-') + '/' 
        for name in industry_names
    ]
    return updated_urls


# In[11]:


# Function to extract "/quote/.../" hrefs from each URL in the list
def extract_quote_links(driver, urls):
    '''
    Extracts valid stock quote links from Yahoo Finance industry pages.
    input:
        - driver: Selenium WebDriver instance.
        - urls: List of industry page URLs (strings).
    output:
        - List of valid stock quote links (strings) filtered for uppercase tickers only.
    '''
    quote_links = []  # List to hold fully qualified extracted links

    # Regular expression to validate tickers (uppercase letters only)
    valid_ticker_pattern = re.compile(r"/quote/([A-Z]+)(/|$)")
    
    for index, url in enumerate(urls):
        print(f"Accessing URL {index + 1}/{len(urls)}: {url}")
        driver.get(url)
        time.sleep(5)  # Delay to allow page load; adjust as needed for speed optimization

        # Parse the page source with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Find all hrefs that match "/quote/.../"
        matched_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if re.match(r"^/quote/.+/$", href):
                full_url = urljoin(base_url, href)  # Prepend base URL

                # Check if the link contains a valid ticker
                if valid_ticker_pattern.search(full_url):
                    matched_links.append(full_url)
                    
            # Stop after collecting the first 10 unique links
            if len(matched_links) >= 10:
                break

        quote_links.extend(matched_links)

        print(f"Extracted {len(matched_links)} links from {url}")

    return quote_links


# ## 4. Backend: Data Fetching and Storage

# In[12]:


def fetch_all_tickers_data(links, cookies=None, headers=None):
    '''
    Fetches stock price data for multiple tickers and aligns it by timestamps.
    input:
        - links: List of stock quote links (strings).
        - cookies: Dictionary of cookies for HTTP requests (default: None).
        - headers: Dictionary of headers for HTTP requests (default: None).
    output:
        - pandas DataFrame: Contains timestamps as rows and stock tickers as columns, with their respective close prices.
    '''
    from datetime import datetime, timedelta

    # Calculate period1 (1 year ago) and period2 (current time)
    period2 = int(datetime.now().timestamp())  # Current timestamp
    period1 = int((datetime.now() - timedelta(days=365)).timestamp())  # 1 year ago
    interval = "1d"  # Granularity: 1 day

    all_data = []

    for link in links:
        try:
            # Extract the ticker symbol
            ticker = link.split('/')[-2]
            print(f"Fetching data for {ticker}...")

            # Fetch data for the ticker
            timestamps, close_prices = fetch_stock_data(
                ticker, period1, period2, interval, cookies, headers
            )
            
            if timestamps is not None and close_prices is not None:
                print(f"Fetched {len(close_prices)} daily close prices for {ticker}.")
                
                # Create a DataFrame for this ticker
                symbol_df = pd.DataFrame({"timestamp": timestamps[-100:], ticker: close_prices[-100:]})
                all_data.append(symbol_df)
            else:
                print(f"Warning: No data available for {ticker}.")
        except Exception as e:
            print(f"Error processing {link}: {e}")

    # Deduplicate tickers
    unique_tickers = {df.columns[1]: df for df in all_data}
    all_data = list(unique_tickers.values())

    # Merge all data on "timestamp" using a full outer join
    merged_data = pd.DataFrame()
    for df in all_data:
        if merged_data.empty:
            merged_data = df
        else:
            merged_data = pd.merge(merged_data, df, on="timestamp", how="outer")

    # Sort by timestamp
    merged_data = merged_data.sort_values(by="timestamp").reset_index(drop=True)

    return merged_data


# In[13]:


# Fetch stock data for a single ticker
def fetch_stock_data(ticker, period1, period2, interval="1d", cookies=None, headers=None):
    '''
    Fetches stock price data (timestamps and close prices) for a single ticker from Yahoo Finance.
    input:
        - ticker: Stock ticker symbol (string).
        - period1: Start timestamp (int, in seconds since epoch).
        - period2: End timestamp (int, in seconds since epoch).
        - interval: Data granularity (string, e.g., "1d", "1h").
        - cookies: Dictionary of cookies for the HTTP request (default: None).
        - headers: Dictionary of headers for the HTTP request (default: None).
    output:
        - Tuple of two lists:
            1. timestamps: List of datetime objects.
            2. close_prices: List of float values representing close prices.
        - Returns (None, None) if an error occurs.
    '''
    base_url = "https://query1.finance.yahoo.com/v8/finance/chart/"
    query_url = (
        f"{base_url}{ticker}?period1={period1}&period2={period2}"
        f"&interval={interval}&includePrePost=true&events=div%7Csplit%7Cearn&lang=en-US&region=US"
    )
    
    try:
        response = requests.get(query_url, cookies=cookies, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Extract timestamps and close prices
        timestamps = data['chart']['result'][0]['timestamp']
        close_prices = data['chart']['result'][0]['indicators']['quote'][0]['close']
        
        # Convert timestamps to datetime
        timestamps = pd.to_datetime(timestamps, unit='s')

        return timestamps, close_prices
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None, None


# In[14]:


# Save extracted links to CSV, excluding links with invalid tickers
def save_links_to_csv(links, filename="extracted_links.csv"):
    '''
    Saves extracted stock quote links to a CSV file.
    input:
        - links: List of valid stock quote links (strings).
        - filename: Output file path (string) for the CSV file (default: "extracted_links.csv").
    output:
        - None. Saves the links to the specified CSV file.
    '''
    with open(filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Link"])  # Write header
        for link in links:
            writer.writerow([link])
    
    print(f"Filtered links saved to {filename}")


# In[15]:


# Save the aggregated data to CSV
def save_data_to_csv(data, filename="stock_data.csv"):
    '''
    Saves a pandas DataFrame containing stock data to a CSV file.
    input:
        - data: pandas DataFrame with stock data.
        - filename: Output file path (string) for the CSV file (default: "stock_data.csv").
    output:
        - None. Saves the DataFrame to the specified file.
    '''
    data.to_csv(filename, index=False)
    print(f"Stock data saved to {filename}")


# ## 5. Main Workflow

# In[16]:


# Main function to handle navigation
def main():
    '''
    Main workflow that orchestrates web scraping, data extraction, and saving.
    input:
        - None.
    output:
        - None. Executes the end-to-end process of scraping, extracting, and saving stock data.
    '''
    print("Navigating to Yahoo Finance homepage...")
    driver.get(base_url)
    time.sleep(2)
    
    # Handle cookies if they exist
    if load_cookies(driver, cookie_file_path):
        print("Cookies loaded successfully.")
        driver.refresh()
    else:
        print("No cookies found. Accepting cookies manually.")
        try:
            accept_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept all')]"))
            )
            accept_button.click()
            time.sleep(2)
            save_cookies(driver, cookie_file_path)
            print("Cookies accepted and saved.")
        except Exception as e:
            print("Error handling cookies:", e)
    
    # Navigate to Basic Materials sector
    print("Navigating to Basic Materials sector...")
    driver.get(sectors_url)
    time.sleep(2)
    
    # Navigate to each industry and collect company links
    #navigate_to_industry()
    gather_industry_names(driver)
    updated_urls = generate_urls()

    print("List of updated URLs for the first 10 industries:")
    for url in updated_urls:
        print(url)

    # Extract quote links from each updated URL
    print("Extracting /quote/.../ links from each industry page...")
    extracted_links = retry_operation(extract_quote_links, retries=3, driver=driver, urls=updated_urls)
    if not extracted_links:
        print("Failed to extract links. Exiting.")
        return
        
    print("Collected full quote links:") if extracted_links else print("Links could not be collected")

    # Save the extracted links
    save_links_to_csv(extracted_links)
    print("Extraction and saving complete.")
    
    for link in extracted_links:
        print(link)

    # Fetch stock data using Yahoo AJAX endpoint
    print("Fetching stock data for all links...")
    
    # Define a fixed timestamp range
    # Define the time range (6th November 2024 to 15th November 2024)
    period1 = int(datetime(2024, 11, 6).timestamp())  # Start timestamp
    period2 = int(datetime(2024, 11, 15).timestamp())  # End timestamp

    # Define headers and cookies
    cookies = {
        "GUC": "AQABCAFnJy1nV0IgvASK&s=AQAAAJB-qKHi&g=ZyXotw",
        "A1": "d=AQABBK3oJWcCEL768yJfkpdKJoPN52K9l3QFEgABCAEtJ2dXZ7u9b2UBAiAAAAcIpuglZ8iQvhs&S=AQAAAq11kqwbV-Cl4YdEYNtEpg8",
        "A3": "d=AQABBK3oJWcCEL768yJfkpdKJoPN52K9l3QFEgABCAEtJ2dXZ7u9b2UBAiAAAAcIpuglZ8iQvhs&S=AQAAAq11kqwbV-Cl4YdEYNtEpg8",
        "A1S": "d=AQABBK3oJWcCEL768yJfkpdKJoPN52K9l3QFEgABCAEtJ2dXZ7u9b2UBAiAAAAcIpuglZ8iQvhs&S=AQAAAq11kqwbV-Cl4YdEYNtEpg8",
        "cmp": "t=1733097066&j=1&u=1---&v=54",
        "EuConsent": "CQHdjMAQHdjMAAOACKENBRFgAAAAAAAAACiQAAAAAAAA",
        "PRF": "t=LIN%252BGC%253DF",
    }
    
    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    }

    # Fetch and save stock data
    stock_data = fetch_all_tickers_data(extracted_links, cookies=cookies, headers=headers)
    save_data_to_csv(stock_data)
    print("Data fetching and saving complete.")
    
    # Close the driver
    print("Script complete. Closing the browser.")
    driver.quit()


if __name__ == "__main__":
    main()


# In[ ]:




