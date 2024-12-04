#!/bin/bash

echo "Setting up the environment..."

# Step 1: Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Step 2: Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Step 3: Run the scraper
echo "Running the scraper..."
python3 src/mc1_scraper.py

# Step 4: Run tests
echo "Running tests..."
python3 -m unittest discover -s tests

# Step 5: Deactivate the virtual environment
deactivate

echo "Done!"