# tests/test_scraper.py

import unittest
from unittest.mock import patch, MagicMock
from src.mc1_scraper import (
    save_cookies,
    load_cookies,
    gather_industry_names,
    generate_urls,
    extract_quote_links,
    save_links_to_csv,
    retry_operation,
    fetch_stock_data,
    fetch_all_tickers_data,
)

# Test suite for mc1_scraper.py
class TestScraper(unittest.TestCase):

    # Mock WebDriver setup
    @patch("selenium.webdriver.Chrome")
    def test_save_cookies(self, mock_driver):
        """
        Test saving cookies to a file.
        """
        mock_driver.get_cookies.return_value = [{"name": "test_cookie", "value": "test_value"}]
        with patch("builtins.open", new_callable=MagicMock) as mock_open:
            save_cookies(mock_driver, "test_cookies.pkl")
            mock_open.assert_called_once_with("test_cookies.pkl", "wb")

    @patch("selenium.webdriver.Chrome")
    def test_load_cookies(self, mock_driver):
        """
        Test loading cookies from a file.
        """
        test_cookies = [{"name": "test_cookie", "value": "test_value", "domain": "finance.yahoo.com"}]
        with patch("builtins.open", new_callable=MagicMock) as mock_open:
            mock_open.return_value.__enter__.return_value = MagicMock()
            with patch("pickle.load", return_value=test_cookies):
                result = load_cookies(mock_driver, "test_cookies.pkl")
                self.assertTrue(result)

    @patch("selenium.webdriver.Chrome")
    def test_gather_industry_names(self, mock_driver):
        """
        Test gathering industry names.
        """
        mock_row = MagicMock()
        mock_row.find_element.return_value.text = "Mock Industry"
        mock_driver.find_elements.return_value = [mock_row] * 16

        gather_industry_names(mock_driver)
        self.assertGreater(len(mock_driver.find_elements.return_value), 0)

    @patch("selenium.webdriver.Chrome")
    def test_generate_urls(self, mock_driver):
        """
        Test URL generation for industries.
        """
        global industry_names
        industry_names = ["Gold", "Silver", "Copper"]
        urls = generate_urls()
        self.assertGreater(len(urls), 0)
        for url in urls:
            self.assertTrue(url.startswith("https://finance.yahoo.com/sectors/basic-materials/"))


    @patch("selenium.webdriver.Chrome")
    def test_extract_quote_links(self, mock_driver):
        """
        Test extracting quote links.
        """
        mock_driver.page_source = '<a href="/quote/AAPL/">AAPL</a>'
        mock_urls = ["https://finance.yahoo.com/sectors/basic-materials/"]
        links = extract_quote_links(mock_driver, mock_urls)
        self.assertGreater(len(links), 0)
        self.assertIn("/quote/AAPL/", links[0])

    @patch("builtins.open", new_callable=MagicMock)
    def test_save_links_to_csv(self, mock_open):
        """
        Test saving links to CSV.
        """
        links = ["https://finance.yahoo.com/quote/AAPL/", "https://finance.yahoo.com/quote/MSFT/"]
        save_links_to_csv(links)
        mock_open.assert_called_once_with("extracted_links.csv", mode="w", newline="", encoding="utf-8")

    @patch("requests.get")
    def test_fetch_stock_data(self, mock_get):
        """
        Test fetching stock data for a single ticker.
        """
        mock_response = {
            "chart": {
                "result": [{
                    "timestamp": [1609459200, 1609545600],
                    "indicators": {
                        "quote": [{"close": [123.45, 125.67]}]
                    }
                }]
            }
        }
        mock_get.return_value.json.return_value = mock_response
        timestamps, close_prices = fetch_stock_data("AAPL", 1609459200, 1612137600)
        self.assertEqual(len(timestamps), 2)
        self.assertEqual(len(close_prices), 2)
        self.assertAlmostEqual(close_prices[0], 123.45)

    @patch("requests.get")
    def test_fetch_all_tickers_data(self, mock_get):
        """
        Test fetching data for multiple tickers.
        """
        mock_response = {
            "chart": {
                "result": [{
                    "timestamp": [1609459200, 1609545600],
                    "indicators": {
                        "quote": [{"close": [123.45, 125.67]}]
                    }
                }]
            }
        }
        mock_get.return_value.json.return_value = mock_response
        links = ["https://finance.yahoo.com/quote/AAPL/", "https://finance.yahoo.com/quote/MSFT/"]
        data = fetch_all_tickers_data(links)
        self.assertGreater(len(data), 0)
        self.assertIn("timestamp", data.columns)
        self.assertIn("AAPL", data.columns)

    @patch("selenium.webdriver.Chrome")
    def test_retry_operation(self, mock_driver):
        """
        Test retrying a failed operation.
        """
        def mock_function():
            raise Exception("Test Exception")

        result = retry_operation(mock_function, retries=2, delay=1)
        self.assertIsNone(result)

# Run the test suite
if __name__ == "__main__":
    unittest.main()